"""F-M10-5: block user writes to a school while it is being progressed.

Every school write router is mounted under /api/schools/ (routes.py), so one
path check covers them all, for every role including admin. Safe methods pass
(admins can still read). Sync / admin / internal endpoints use other prefixes.
"""

import re

from django.http import JsonResponse

_SCHOOL_PATH = re.compile(r"^/api/schools/(\d+)/")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class ProgressionFreezeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in _SAFE_METHODS:
            match = _SCHOOL_PATH.match(request.path)
            if match:
                from sessionops.services.progression.freeze import is_school_frozen

                if is_school_frozen(int(match.group(1))):
                    return JsonResponse(
                        {
                            "error": {
                                "code": "school_progressing",
                                "message": (
                                    "This school is being moved to the next academic year. "
                                    "Changes are paused until that finishes."
                                ),
                            }
                        },
                        status=409,
                    )
        return self.get_response(request)
