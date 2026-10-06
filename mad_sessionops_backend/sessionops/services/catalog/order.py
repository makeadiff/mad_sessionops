"""Class catalog order, derived from the next-class chain (no admin input).

`Class.sequence` is kept as a stored sort key so every existing
`.order_by("sequence")` keeps working, but admins no longer type it: it is
recomputed after every catalog write from Next class.

Ordering: classes linked by Next class form a chain (5th → 6th → 7th → 8th);
chains are listed in order of their lowest class code, and within a chain by
how far each class is from the chain's last class. Unlinked classes are
chains of one.
"""

from sessionops.models import Class


def _code_key(code: str) -> tuple:
    """Numeric codes sort numerically ("9" < "10"), then the rest alphabetically."""
    code = code.strip()
    return (0, int(code), "") if code.isdigit() else (1, 0, code.lower())


def compute_order(classes: list[Class]) -> list[Class]:
    """Return `classes` in catalog order (pure; no queries)."""
    by_id = {c.pk: c for c in classes}

    # Height = steps to the end of the chain (8th = 0, 7th = 1, ...). Listing by
    # descending height keeps classes that share a next class side by side
    # (5A and 5B → 6th are both just before 6th). The next-class graph is
    # acyclic (validate_next_class), so this terminates.
    height: dict[int, int] = {}

    def _height(pk: int) -> int:
        if pk not in height:
            nxt = by_id[pk].next_class_id_id
            height[pk] = 1 + _height(nxt) if nxt in by_id else 0
        return height[pk]

    # Group linked classes (union-find over next-class edges).
    parent = {pk: pk for pk in by_id}

    def _find(pk: int) -> int:
        while parent[pk] != pk:
            parent[pk] = parent[parent[pk]]
            pk = parent[pk]
        return pk

    for c in classes:
        if c.next_class_id_id in by_id:
            parent[_find(c.pk)] = _find(c.next_class_id_id)

    chain_key: dict[int, tuple] = {}
    for c in classes:
        root = _find(c.pk)
        key = _code_key(c.class_code)
        chain_key[root] = min(chain_key.get(root, key), key)

    return sorted(
        classes,
        key=lambda c: (chain_key[_find(c.pk)], -_height(c.pk), _code_key(c.class_code)),
    )


def recompute_sequences() -> None:
    """Rewrite Class.sequence (1..n) for every non-removed class from the chain."""
    classes = list(Class.objects.filter(removed=False))
    changed = []
    for position, cls in enumerate(compute_order(classes), start=1):
        if cls.sequence != position:
            cls.sequence = position
            changed.append(cls)
    if changed:
        Class.objects.bulk_update(changed, ["sequence"])
