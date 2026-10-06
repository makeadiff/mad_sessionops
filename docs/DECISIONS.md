# Decisions

ADR-lite. One entry per significant choice, with rationale and alternatives considered. Entries are append-only — if a decision is reversed, add a new entry referencing the old one, don't edit history.

Format:
- **ID** — sequential, never reused
- **Date** — when decided
- **Status** — Accepted / Superseded by X / Deprecated
- **Context** — what problem were we solving
- **Decision** — what we chose
- **Consequences** — what this costs us
- **Alternatives** — what else was on the table

---

## D001 — Django Ninja over DRF

**Date:** Planning phase
**Status:** Accepted

**Context:** The backend needs an HTTP framework on top of Django. DRF is the default; Ninja is the modern alternative.

**Decision:** Django Ninja 1.0+, with Pydantic v2 schemas.

**Consequences:**
- Automatic OpenAPI schema generation without decorators
- Pydantic v2 for validation (faster, better types)
- Smaller community, fewer Stack Overflow answers than DRF
- Custom JWT middleware (no `TokenAuthentication` equivalent out of the box)

**Alternatives:**
- **DRF** — larger community, more plugins. Rejected because its serializer model is heavier than Pydantic and we'd write more boilerplate.
- **FastAPI with Django ORM** — considered briefly. Rejected because running FastAPI and Django ORM together is glue-heavy and loses Django admin, management commands, and migration workflow.

---

## D002 — PostgreSQL on AWS RDS, ap-south-1

**Date:** Planning phase
**Status:** Accepted

**Context:** Primary data store. MAD operates in India; latency and compliance point toward an Indian region.

**Decision:** Managed Postgres 14 on AWS RDS, Mumbai (ap-south-1).

**Consequences:**
- Managed backups, point-in-time recovery, patching
- Vendor lock-in to AWS (acceptable — MAD's infra is AWS)
- RDS egress costs if we ever serve from outside ap-south-1

**Alternatives:**
- **Self-hosted Postgres on EC2** — cheaper, more ops burden. Rejected for reliability.
- **Aurora Postgres** — more expensive, marginal benefit at this scale. May revisit at scale.

---

## D003 — JWT auth via simplejwt with custom Ninja middleware

**Date:** Planning phase
**Status:** Accepted

**Context:** Frontend is a Next.js SPA calling the API from a different origin. Session-cookie auth is awkward across origins; JWT is standard for SPAs.

**Decision:** `djangorestframework-simplejwt` for token issuance and blacklist management. Custom Ninja middleware (`sessionops/auth.py`) for per-request token validation because simplejwt's DRF integration doesn't apply.

**Consequences:**
- Stateless verification (no DB hit for a valid token unless we look up the user, which we do)
- Token refresh flow is more complex than session auth
- Blacklisting on logout requires DB hit (acceptable)
- Must keep tokens short-lived (1h access, 1d refresh)

**Alternatives:**
- **Django sessions** — simpler, but cross-origin cookie config is ugly for our Next.js SPA architecture.
- **OAuth2 bearer with external IdP** — overkill for our user base.

---

## D004 — Google OAuth PKCE flow

**Date:** Planning phase
**Status:** Accepted

**Context:** MAD staff use Google Workspace accounts. SSO via Google is required. The frontend is a browser SPA.

**Decision:** Google OAuth 2.0 with PKCE (Proof Key for Code Exchange). Frontend generates verifier, backend completes the exchange.

**Consequences:**
- No client secret needed on frontend (PKCE's whole point)
- Backend still validates the id_token and issues internal JWTs — Google tokens are never passed to other endpoints
- Slightly more round-trips than implicit flow, but implicit is deprecated

**Alternatives:**
- **Implicit flow** — deprecated by OAuth spec. Rejected.
- **Server-side OAuth code flow** — requires session cookies or state storage on backend. Rejected, complicates SPA.

---

## D005 — Next.js 16 App Router (frontend)

**Date:** Planning phase
**Status:** Accepted

**Context:** Frontend framework choice.

**Decision:** Next.js 16 with App Router (not Pages Router).

**Consequences:**
- React 19 server components available
- File-based routing with nested layouts
- `proxy.ts` (renamed from `middleware.ts` in Next 16) for route guards
- Smaller ecosystem for App Router patterns than Pages Router

**Alternatives:**
- **Next.js Pages Router** — more mature, more examples. Rejected — App Router is the forward-compatible path.
- **Remix** — considered. Rejected because the team has more Next.js experience and Vercel hosting isn't ruled out.
- **Plain React + Vite** — no SSR, no built-in route guards. Rejected for the amount of setup we'd duplicate.

---

## D006 — Redux Toolkit + redux-persist for state

**Date:** Planning phase
**Status:** Accepted

**Context:** Frontend needs global state for auth, user profile, and cached school lists. Needs to persist across reloads for a decent UX.

**Decision:** Redux Toolkit with redux-persist. Tokens and user profile persist to localStorage.

**Consequences:**
- Mature tooling, good devtools
- SSR quirk: redux-persist touches localStorage at module load → crashes on server. Worked around with createNoopStorage fallback.
- More boilerplate than Zustand

**Alternatives:**
- **Zustand** — lighter, but less opinionated. Rejected because team familiarity with Redux outweighs simplicity.
- **React Query + React Context only** — good for data, weak for auth state that spans the app. Rejected.
- **Pure RSC with no client state** — Not viable because auth and interactivity require client components.

---

## D007 — MUI v6 component library

**Date:** Planning phase (confirmed in Sprint 0)
**Status:** Accepted

**Context:** Frontend needs a component library with accessibility and design consistency.

**Decision:** MUI v6 (Material UI). Emotion for styling.

**Consequences:**
- Compatible with React 19 (v5 was not)
- Large bundle but well-understood
- Grid v2 API differs from v1 — migration accounted for
- Emotion rather than styled-components

**Alternatives:**
- **Tailwind + shadcn/ui** — more control, smaller bundle. Rejected because MAD's internal design language is closer to Material than Tailwind's default aesthetic, and shadcn's copy-in model adds maintenance overhead.
- **Chakra UI** — smaller ecosystem. Rejected.
- **Ant Design** — heavier, opinionated. Rejected.

---

## D008 — Axios with queued token refresh

**Date:** Planning phase
**Status:** Accepted

**Context:** When the access token expires mid-session, multiple in-flight requests may all receive 401. Naive refresh logic triggers multiple refresh calls, racing each other.

**Decision:** Single Axios instance with a response interceptor. On 401, the interceptor queues all failed requests, triggers one refresh, and on success re-runs the queue with the new token.

**Consequences:**
- No token-refresh races
- More complex interceptor code
- Refresh failure logs the user out cleanly

**Alternatives:**
- **Fetch with manual retry** — we'd reinvent the wheel.
- **Per-request refresh check** — chatty and doesn't handle 401 from server-side invalidation.

---

## D009 — Soft delete everywhere

**Date:** Planning phase
**Status:** Accepted

**Context:** MAD needs audit trails. Mistakes must be recoverable. Historical analysis must include deactivated records.

**Decision:** No model in the domain layer gets hard-deleted. Deactivation is `is_active=False` and `removed=True`. Default queryset filters out deactivated rows; admins can include them via explicit methods.

**Consequences:**
- Every unique constraint needs careful thought (uniqueness including soft-deleted? only active?)
- Custom Manager on every domain model
- Larger tables over time (accepted — we're not Facebook)

**Alternatives:**
- **Hard delete with separate audit log table** — two sources of truth, sync risk. Rejected.
- **Archival table** — complex migration pattern. Rejected for current scale.

---

## D010 — Application-layer business rule enforcement

**Date:** Planning phase
**Status:** Accepted

**Context:** Rules like "max 5 children per section" can theoretically be enforced via DB triggers or CHECK constraints. Should they be?

**Decision:** Business rules live in the service layer (Python), not in DB constraints. DB constraints are reserved for data integrity (NOT NULL, FK, unique) — not business rules.

**Consequences:**
- Testable in isolation (service tests are fast)
- Error messages can be domain-specific
- Rules can be bypassed by direct DB access — mitigated by code review and by shell scripts always going through services
- Migrations simpler (no trigger maintenance)

**Alternatives:**
- **Partial unique indexes for "active" constraints** — clever but brittle across migrations.
- **Trigger-based enforcement** — duplicates logic across Python and PL/pgSQL, terrible DX.

---

## D011 — Single globally-active academic year

**Date:** Planning phase
**Status:** Accepted

**Context:** Should each school have its own academic year, or should the whole system share one?

**Decision:** One `schoolAcaddmicYear` globally active at a time. All schools operate under it.

**Consequences:**
- Year progression is one operation, not N
- Reporting is straightforward
- Schools with genuinely different academic calendars can't be modeled (not a use case for MAD currently)

**Alternatives:**
- **Per-school active year** — matches edge cases but makes aggregation queries brittle. Rejected.

---

## D012 — Hasura pulls into Session-Ops via webhook

**Date:** Planning phase
**Status:** Accepted

**Context:** User and Partner data lives in Hasura as the system of record. Session-Ops needs to stay current.

**Decision:** Hasura sends webhooks on CUD events. Session-Ops endpoint validates HMAC, enqueues Celery task, acknowledges immediately. Celery processes async.

**Consequences:**
- Eventual consistency (typically < 5 seconds)
- Need idempotent handlers
- Need sync health dashboard for failures
- If Hasura is down, Session-Ops data can drift — acceptable, with reconciliation job

**Alternatives:**
- **Session-Ops polls Hasura** — wasteful, introduces lag or load.
- **Direct shared DB** — tight coupling, rejected.
- **Kafka or event bus** — overengineered for our volume.

---


## D014 — Two separate repositories, not a monorepo

**Date:** Planning phase
**Status:** Accepted

**Context:** Backend and frontend are independently deployable. Should they share a repo?

**Decision:** Separate repos: `mad-sessionops-backend` and `mad-sessionops-frontend`.

**Consequences:**
- Independent release cadence
- Docs about the system live in backend repo (chosen because backend owns most of the complexity)
- Cross-cutting changes require two PRs

**Alternatives:**
- **Monorepo with turborepo** — tooling overhead, small-team friction. Rejected.

---

## D015 — Module name `sessionops`

**Date:** Sprint 0 cleanup
**Status:** Accepted

**Context:** The Django app was originally named `madui` (from an earlier iteration). Inconsistent with the product name.

**Decision:** Rename the Python module to `sessionops`. Repo names stay `mad-sessionops-backend` / `mad-sessionops-frontend`.

**Consequences:**
- One-time migration cost (done in Sprint 0)
- Imports read cleanly: `from sessionops.models import User`
- Celery commands short: `celery -A sessionops worker`

**Alternatives:**
- **`sessionops_backend`** — redundant (the repo name already says backend). Rejected.
- **Keep `madui`** — lies about what the code does. Rejected.

---

## D016 — Drop Docker for dev, keep native + Redis-only container

**Date:** Sprint 0 cleanup
**Status:** Accepted

**Context:** Initial scaffolding used `docker-compose` with 5 services. Most were unnecessary: Postgres is RDS, Django/Celery are just Python processes, there's no container-native production target.

**Decision:** Remove Docker from dev workflow. Run Django and Celery natively with `uv run`. Keep Redis as a single standalone Docker container. Remove `Dockerfile` and `docker-compose.yml` entirely (git history preserves them).

**Consequences:**
- Faster iteration (no rebuild for dep changes)
- Simpler debugging
- No Windows bind-mount weirdness
- If we ever deploy to containers, Dockerfile needs to be re-created (fine — prod Dockerfile is different anyway)

**Alternatives:**
- **Keep full compose** — kept producing bugs with zero value. Rejected.
- **Podman or Lima** — same problems, different runtime. Rejected.

---

## D017 — Pydantic v2 throughout, Django Ninja 1.0+

**Date:** Sprint 0 (implicit, surfaced during rename)
**Status:** Accepted

**Context:** Initial scaffolding pinned Django Ninja 0.21, which pins Pydantic <2. Existing schema code used Pydantic v2 features (`field_validator`).

**Decision:** Upgrade to Django Ninja 1.0+ and Pydantic v2+ across the board.

**Consequences:**
- Faster validation (Pydantic v2 is ~10x faster)
- Modern API (model_config, field_validator)
- Breaking changes from Ninja 0.x to 1.x — handled during Sprint 0

**Alternatives:**
- **Stay on Ninja 0.21 + Pydantic v1** — EOL track, rejected.

---

## D018 — Docs live in backend repo; frontend repo references them

**Date:** Sprint 0 cleanup (this session)
**Status:** Accepted

**Context:** System-level docs (business rules, data model, RBAC, glossary) describe the system, most of which is backend. Where should they physically live?

**Decision:** System docs live in `mad-sessionops-backend/docs/`. Frontend repo has its own `docs/` for frontend-specific concerns. Frontend `CLAUDE.md` points at backend docs via relative path (`../mad-sessionops-backend/docs/...`) when both repos are checked out side-by-side.

**Consequences:**
- Single source of truth for system rules
- Frontend sessions need both repos checked out for cross-cutting work
- No third "docs" repo to maintain

**Alternatives:**
- **Third docs repo** — three things to sync. Rejected.
- **Duplicate docs in both repos** — drift risk. Rejected.
- **Backend-only — frontend operates blind** — too risky. Rejected.

---

## D019 — Multi-role user model with comma-separated string

**Date:** F01 design (this session)
**Status:** Accepted

**Context:** MAD's source-of-truth user system stores user roles as a comma-separated string (e.g., `"CO Part Time,Wingman"`). Users can hold multiple roles. We sync this from Hasura.

**Decision:** Mirror this shape in our User model. Field name: `user_role`. Type: text. Stored verbatim from sync. Parsed at runtime to determine permissions.

We do NOT normalize this into a separate `UserRole` table with a M2M relationship. The string IS the canonical representation and matches what Hasura sends.

**Consequences:**
- Cannot use Django's choices validation on the field (it's a multi-value string)
- Permission checks are runtime parses, not joins
- Adding/changing allowed roles is a code change in `services/auth/role_helpers.py`, not a DB migration
- Searching "all users with role X" requires a SQL `LIKE` or full-text query — acceptable at our scale (~hundreds of users, not millions)

**Alternatives:**
- **Normalize to M2M `UserRole` table** — cleaner queries but creates sync complexity (every sync event has to diff role lists). Rejected.
- **Single role per user** — doesn't match MAD's reality. Rejected.

---

## D020 — Login gates on User table membership, not Google hosted domain

**Date:** F01 design
**Status:** Accepted

**Context:** OAuth flows often gate access by Google's `hd` (hosted domain) claim — only users from a specific Workspace domain can log in. Initial F01 draft used this approach.

**Decision:** Drop the hosted domain check. Gate access on (1) `user_login` exists in the User table, and (2) the user has at least one allowed role.

**Consequences:**
- Any Google account can attempt sign-in; rejection happens server-side based on User table lookup
- Users with non-standard email domains (e.g., personal Gmail used as a MAD login) are supported as long as their `user_login` is in our table
- One less external dependency (we don't tie ourselves to Google Workspace's domain configuration)
- The User table becomes the absolute source of truth for "who can log in"

**Alternatives:**
- **Hosted domain restriction** — brittle, ties auth to Google Workspace setup. Rejected.
- **Allowlist of email domains in code** — duplicate of User table logic. Rejected.

---

## D021 — Integer primary keys, not UUIDs

**Date:** F01 design (codifying existing convention)
**Status:** Accepted

**Context:** Initial F01 draft assumed UUID primary keys. The existing schema (User model, sync source) uses integer IDs.

**Decision:** All primary keys are `BigAutoField` (Django default). All foreign keys are integers. API path parameters are integers. Frontend TypeScript types use `number`.

**Consequences:**
- Smaller indexes, faster joins than UUIDs
- IDs are guessable (1, 2, 3…) — not a security issue because RBAC scope filtering is independent of ID guessability
- Sync from Hasura presumably uses integer IDs — alignment by default
- IDs are NOT publicly exposed in URLs that strangers can hit (auth gates everything except /login and /auth/*)

**Alternatives:**
- **UUIDs** — opaque IDs, no enumeration risk. Rejected because (a) RBAC handles enumeration risk anyway, (b) integer is what Hasura sends, (c) integer joins are faster. Could reconsider in future if requirements change.


---

## D022 — Multi-method authentication (UserAuth as one-to-many)

**Date:** F01 redesign session
**Status:** Accepted

**Context:** A user may authenticate with Google OAuth, an email+password combination, or both. Identity comes from sync (User table); credentials are local to Session-Ops. Different methods have different shapes (Google has `sub`, password has hash) and different lifecycles (a user can unlink Google but keep their password).

**Decision:** UserAuth is a one-to-many from User. Each row represents one auth method. Discriminated by `auth_type` ("google" or "password"). Type-specific columns are nullable — populated based on `auth_type`, enforced by a check constraint.

The original implementation collapsed UserAuth to a one-to-one Google-only model during F01 design. This was wrong and is reverted in F01a.

**Schema (per F01a):**
- `auth_type`: discriminator
- `google_sub`, `google_email_verified`: populated for `auth_type="google"`, null for password
- `password_hash`: populated for `auth_type="password"`, null for google
- `last_used_at`: tracks active method usage
- `deleted`, `deleted_at`: soft-delete an auth method without deleting the user
- Unique constraint: `(user, auth_type)` where `deleted=False` — at most one active method per type
- Unique constraint: `google_sub` where present — no two users share a Google identity
- Check constraint: ensures field integrity per `auth_type`

**Consequences:**
- Generic auth-method lookup by `(user_id, auth_type)` works uniformly
- Adding new auth methods (SSO providers, magic links) is a new `auth_type` value, not a new table
- F01a builds Google; F01b builds password — both share this table
- Soft-delete enables "user unlinked Google" history without losing audit trail

**Alternatives:**
- **One UserAuth per user (collapsed Google-only):** simpler but doesn't support password. Rejected.
- **Separate `GoogleAuth` and `PasswordAuth` tables:** more typed but duplicates lifecycle fields and complicates "show all auth methods for user" queries. Rejected.
- **JSON column for type-specific data:** less typed, weaker constraints. Rejected.

**Note:** F01b's `PasswordResetToken` is intentionally a separate table (not a third auth method). Reset tokens are ephemeral credentials for a state transition, not a long-lived auth method. They live in `password_reset_token`, not `user_auth`.

---

## D023 — DB-backed token storage for password reset

**Date:** F01b design
**Status:** Accepted

**Context:** Set-password and forgot-password flows email the user a link with a token. Two storage options: signed token (JWT-like, stateless) or DB row.

**Decision:** DB-backed with SHA-256 hashed tokens. Single-use enforced by `used_at` field; expiry by `expires_at`.

**Consequences:**
- Token revocation is trivial (delete row or set `used_at`)
- Single-use is enforced by an atomic UPDATE
- Can show admin "how many active tokens does this user have" if ever needed
- Slightly more DB writes vs stateless tokens — negligible at our volume
- Tokens are hashed at rest, so DB compromise doesn't directly leak active tokens

**Alternatives:**
- **Signed tokens (stateless):** harder to revoke, harder to enforce single-use. Rejected.
- **Redis-backed with TTL:** works, but couples this feature to Redis availability. The DB is already required; less surface area to use it. Rejected.



---

## D024 — FK constraints stay at DB level by default; per-table exceptions documented

**Date:** F01a redesign session
**Status:** Accepted

**Context:** Earlier work raised the question of whether FK constraints should be at the DB level (PostgreSQL FOREIGN KEY) or only at the ORM level (Django relationship without `db_constraint=True`). Concerns: migration pain, sync ordering with Hasura, data quality issues from the upcoming Bubble migration.

**Decision:** Default to DB-level FK constraints (Django default behavior). Per-FK exceptions allowed and required to be explicit:
- Use `db_constraint=False` only for FKs where there is a concrete reason (e.g., the FK target is populated by sync and may lag).
- Every `db_constraint=False` must have an inline comment explaining why.
- The Bubble migration may temporarily add `db_constraint=False` for bulk-imported tables. After data cleanup, the constraint should be re-evaluated.

**Why this default:**
- Defense in depth: app-level integrity is good but not sufficient for a solo-developed system with significant data importance
- Clarity: the schema documents relationships
- Tools: every Postgres tool (backups, replication, ORMs, dbshell) understands FK constraints
- Catches bugs early: an orphan-creating bug fails loudly at insert time, not silently

**Why per-FK exceptions are allowed:**
- Hasura sync ordering issues are real (e.g., `Partner.co_id → User` may reference a not-yet-synced user)
- The Bubble migration carries known data quality issues that won't pass strict FK checks during import
- Operational fixes occasionally need to write rows that temporarily reference nothing

**Examples already known:**
- `UserAuth.user → User`: DB-level FK with `on_delete=PROTECT` (app-managed table, integrity is strict)
- `Partner.co_id → User`: `db_constraint=False` (sync may lag) — to be added when Partner is built
- `User.reporting_manager_user_id → User`: `db_constraint=False` (sync may lag)

**Consequences:**
- A reconciliation job (Sprint 6) verifies sync-affected FKs resolve correctly and surfaces issues
- Some bugs that strict FKs would catch will instead be caught by the reconciliation job
- The trade-off is accepted for the specific tables where it applies

**Alternatives:**
- **All FKs at DB level, no exceptions:** would block sync and migration. Rejected.
- **No DB-level FKs anywhere:** loses defense in depth on tables where it would be cheap to keep. Rejected.

---

---



## D026 — Application tables live in `mad_sessionops_<env>` schema

**Date:** F01a build
**Status:** Accepted

**Context:** The Postgres database `mad_platform_dev` (or production equivalent) is shared with other MAD applications. The CRM application's tables live in `mad_crm_dev`. Session-Ops tables previously lived in a schema named `mad_platform_dev` (same as the database name, confusing) which has been renamed to `mad_sessionops_dev`.

**Decision:** All Session-Ops tables live in a schema named `mad_sessionops_<env>`:
- `mad_sessionops_dev` — development
- `mad_sessionops_prod` — production (when applicable)

The schema name is configured via the `DBSCHEMA` env var. Django connects with `search_path=<schema>,public`.

Third-party Django framework tables (django_*, auth_*, token_blacklist_*, django_celery_beat_*) live wherever Django created them — initially in the `mad_sessionops_dev` schema as well, since that's the search_path target. This is fine; we don't fight library defaults.

**Consequences:**
- Schema name reflects the application
- Schema-level isolation between MAD apps on the same database
- Migration required `ALTER SCHEMA mad_platform_dev RENAME TO mad_sessionops_dev` (one-time, atomic)
- `.env.development` sets `DBSCHEMA=mad_sessionops_dev`

**Alternatives:**
- **Tables in `public`:** simpler but loses isolation. Rejected because the database is shared.
- **Per-Django-app schemas:** over-engineering. Rejected.
- **One database per app:** heavier infrastructure. Rejected.

---

## D027 — M2 models use dual-flag soft delete, not SoftDeleteBaseModel

**Date:** M2 build (2026-05-07)
**Status:** Accepted

**Context:** M1 models (User, Partner) use `SoftDeleteBaseModel` which provides `is_active` only. M2 introduces history tables (ChildClass, ChildClassSection, etc.) where a row can be in one of three states: active, archived (history-preserved), or soft-deleted.

**Decision:** M2 models do NOT inherit `SoftDeleteBaseModel`. Each M2 model defines three explicit fields: `is_active`, `removed`, `deleted_at`. A custom `M2ActiveManager` filters `is_active=True, removed=False` by default. `all_objects = models.Manager()` is the unfiltered escape hatch.

| `is_active` | `removed` | Meaning |
|---|---|---|
| `true` | `false` | Active, current record |
| `false` | `false` | Archived (history; excluded from active queries but preserved) |
| `false` | `true` | Soft-deleted (treated as deleted, preserved in DB) |

**Consequences:**
- Consistent with Bubble-era data patterns already in the DB
- History tables can differentiate "superseded row" from "deleted row" without a separate flag
- More fields per row than M1 pattern; accepted for the richer semantics

**Alternatives:**
- **Extend SoftDeleteBaseModel with a `removed` flag:** would require changing M1 models or duplicating. Rejected.
- **Single `is_active` flag:** cannot distinguish archived from deleted. Rejected.



## D029 — Child reactivation auto-restores last known section

**Date:** M2 build (2026-05-07)
**Status:** Accepted

**Context:** The M2 spec planned for CO to pick a target section when reactivating a child (POST body `{class_section_id}`). This matches how the reactivation flow works when a child returns after switching schools. But for the common case — a child returning to the same school — making the CO re-select the same section is unnecessary friction.

**Decision:** `reactivate_child` service looks up the child's most recent `ChildClassSection` history row (`removed=False`) and restores them to that section. If that section is no longer active or is at capacity, the service raises a clear error.

**Consequences:**
- Simpler CO flow for the common case (returning child, same section)
- If section is gone or full, CO gets an error and must contact admin to resolve — acceptable edge case
- The original body param (`class_section_id`) is not used; if section reassignment on reactivation is needed, it should be done as a separate edit after reactivation

**Alternatives:**
- **CO picks section in reactivation modal:** more flexible, more friction. Deferred to a later milestone if needed.

---

## D030 — ChildRemovalLog is append-only, removal_reason is free text

**Date:** M2 build (2026-05-07)
**Status:** Accepted

**Context:** The M2 spec planned a `ChildRemovalLog` with an enum `removed_reason` (5 choices), `other_details` free text when reason=`other`, `co_id` bare int, and `school_id` redundant column. The spec also gave the log `is_active`/`removed` soft-delete flags.

**Decision:** `ChildRemovalLog` is built as a simple append-only audit table:
- `removal_reason` is free text (`TextField`) — COs can express any reason without being constrained to a 5-choice dropdown
- `removed_by` is a FK to `User` (not a bare `co_id` int) for referential clarity
- `school_id` dropped (derivable from `child.school_id`)
- `other_details` dropped (subsumed into free-text `removal_reason`)
- No `is_active`/`removed` flags — the log is append-only and rows are never modified

**Consequences:**
- Simpler table, simpler schema
- Cannot filter removal logs by category in SQL without parsing free text — if reporting by category is needed later, enum field can be added in a migration
- Log rows are permanently preserved; reactivation does not modify them

**Alternatives:**
- **Keep enum reasons:** useful for categorical reporting but adds friction at enrollment time. Deferred.
- **Soft-delete the log:** adds complexity with no benefit for an audit log. Rejected.

---

## D031 — CSV exports: view-scope access, personal data included and audited, built server-side

**Date:** M9 planning (2026-09-26 / 2026-09-27)
**Status:** Accepted

**Context:** The ops team needs spreadsheets (rosters, timetables, school summaries, setup gaps) for reporting and follow-up with schools. Until M9 the tool had no way to export data, and M1 had listed exports as out of scope. The open questions were who may export, whether personal data (child date of birth, volunteer phone numbers) is included, and where the file is generated.

**Decision:**
- **Access follows view scope (R13).** Anyone who can view a school can export it. Per-school exports use `get_school_or_403`; cross-school exports start from `schools_visible_to` (via `services/exports/scope.py::export_school_ids`). There is no separate export permission. CXO gets admin scope, as on the Schools page.
- **Personal data is included, and every export is audited.** Each successful export writes one `ExportLog` row: user, export type, school (null for cross-school), filters, school count, row count and time. The log is append-only and has no soft-delete columns (see R9 exceptions).
- **The server builds the CSV, in memory.** `services/exports/csv_writer.py::build_csv_response` returns a single `HttpResponse`: UTF-8 with a BOM, CRLF line endings, `Cache-Control: no-store`, and a leading `'` on any cell starting with `= + - @` (formula-injection guard). The audit row is written before the response is returned, so it can't be lost if the client disconnects.
- **Active academic year only.** A missing active year returns 404 through the existing `get_active_academic_year()`.
- **Datetimes in CSV cells are rendered in IST.** This is a deliberate exception to the "display conversion happens on the frontend" convention: a CSV has no frontend step to convert them, and ops users read the times directly.

**Consequences:**
- There is no new permission model to maintain, and exports can never show more than the screen does.
- Exported files contain personal data once they leave the system. The audit log records who exported what, but it doesn't control where the files go afterwards.
- `export_log` grows without bound until a retention policy is defined (deferred).
- Files are held in memory; this is fine at current volumes (the largest export is about 1 MB). Switching to streaming later only touches `csv_writer.py`.

**Alternatives:**
- **Admin-only exports:** rejected. COs and CHOs are the main users of rosters and timetables.
- **Exclude personal data:** rejected. Ops needs contact details and dates of birth for school follow-up.
- **Generate the CSV in the browser from existing list endpoints:** rejected. It would put business logic in the frontend and would need many requests for cross-school exports.
- **`StreamingHttpResponse`:** deferred. The audit write would have to happen inside the generator after the view returns, where it can be lost when the client disconnects.


## D032 — Year progression moves each school from its own year; the active year follows the newest year in use

**Date:** 2026-10-05
**Status:** Accepted (revises the single-target design in M10 / F-M10-6 and F-M10-7)

**Context:** In the first M10 design, each run had one target year. While any converted school was behind the active year, the only possible target was the active year. So the next year (e.g. 2027-28) couldn't be used until every straggler (e.g. a school still on 2025-26) had been progressed. In practice some schools stay behind on purpose, and a few want to move early, so one school held up everyone else.

**Decision:**
- Each school's target is **the year after its own active school-year**. One run can mix moves (2025-26 → 2026-27 and 2026-27 → 2027-28).
- **No skipping years.** A school two years behind is progressed twice. Each step has its own preview and Undo, and the preview warns `STILL_BEHIND`.
- **The global active year (R8) follows the newest year any school moves into.** Start flips it when a selected school's target is later than the active year. Undo never flips it back. New schools join the active year.
- **The target is fixed at Start** on `SchoolProgression.to_academic_year_id`. Execute re-plans against that pinned year and blocks with `TARGET_NOT_LATER` if the school's year changed in the meantime.
- **One school per run** (2026-10-06, same day follow-up). Each run moves exactly one school, and `start_run` rejects more than one. Every move is previewed and confirmed on its own: the admin types the school's name before Start.
- **Academic-year guardrails:** only the next year after the latest can be created. Remove is allowed only for an inactive, unused year. Rename is locked to the same conditions. There is no manual activate switch.

**Consequences:**
- Stragglers never block other schools. The Schools step shows each school's "current → next" year, a "years behind" label and a year filter.
- `ProgressionRun.from/to_academic_year_id` are now nullable and unused for new runs; the API reports `year_moves` per run and `from/to_year_label` per school.
- Schools can be on different years at once. This was already supported by R8a and the `current_year_q` scoping from F-M10-3.
