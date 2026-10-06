"""F-M9-1: CSV response builder shared by every M9 export.

Built in memory (not streamed) so the audit row is written inside the request
with the real row count — see M9 decision 6.
"""

import csv
import io
from collections.abc import Iterable
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.http import HttpResponse
from django.utils import timezone

IST = ZoneInfo("Asia/Kolkata")
UTF8_BOM = "﻿"

# A cell starting with any of these is evaluated as a formula by Excel/Sheets.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value) -> str:
    """Render one value as an Excel-safe CSV cell."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = value.astimezone(IST)
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    text = str(value)
    if isinstance(value, str) and text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def export_filename(export: str, scope: str | int) -> str:
    """e.g. children_12345_2026-09-27.csv / schools_all_2026-09-27.csv (IST date)."""
    today = timezone.now().astimezone(IST).date().isoformat()
    return f"{export}_{scope}_{today}.csv"


def build_csv_response(filename: str, header: list[str], rows: Iterable[list]) -> HttpResponse:
    """text/csv attachment: UTF-8 BOM, CRLF line endings, header always present."""
    buffer = io.StringIO()
    buffer.write(UTF8_BOM)
    writer = csv.writer(buffer)  # default dialect uses \r\n line endings
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])

    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response
