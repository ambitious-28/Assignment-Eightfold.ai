"""Date normalization — target format YYYY-MM. Stdlib only."""

from __future__ import annotations

import re

_MONTH_MAP: dict[str, str] = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    "january": "01", "february": "02", "march": "03", "april": "04",
    "june": "06", "july": "07", "august": "08", "september": "09",
    "october": "10", "november": "11", "december": "12",
}

_YEAR_MIN = 1950
_YEAR_MAX = 2100


def _valid_ym(year: int, month: int) -> bool:
    return _YEAR_MIN <= year <= _YEAR_MAX and 1 <= month <= 12


def normalize_date(raw: str) -> tuple[str | None, str, bool]:
    """
    Parse raw date string to YYYY-MM.

    Returns (normalized, method, ok).
    Patterns tried in order:
      1. YYYY-MM             already canonical
      2. YYYY-MM-DD          strip day
      3. Mon YYYY / Month YYYY
      4. MM/YYYY or MM-YYYY
      5. YYYY/MM
      6. Bare YYYY           ambiguous month → drop
      7. Anything else       → (None, "date_parse_failed", False)
    """
    if not raw or not raw.strip():
        return None, "date_parse_failed", False

    s = raw.strip()

    # 1. YYYY-MM
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if _valid_ym(y, mo):
            return f"{y:04d}-{mo:02d}", "date_passthrough", True
        return None, "date_parse_failed", False

    # 2. YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})-(\d{2})-\d{2}", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if _valid_ym(y, mo):
            return f"{y:04d}-{mo:02d}", "date_day_stripped", True
        return None, "date_parse_failed", False

    # 3. Mon YYYY  /  Month YYYY  (e.g. "Jan 2021", "January 2021")
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", s)
    if m:
        mon_str = m.group(1).lower()
        y = int(m.group(2))
        mo_str = _MONTH_MAP.get(mon_str)
        if mo_str and _valid_ym(y, int(mo_str)):
            return f"{y:04d}-{mo_str}", "date_month_name_parsed", True
        return None, "date_parse_failed", False

    # 4. MM/YYYY  or  MM-YYYY
    m = re.fullmatch(r"(\d{1,2})[/\-](\d{4})", s)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        if _valid_ym(y, mo):
            return f"{y:04d}-{mo:02d}", "date_mmyyyy_parsed", True
        return None, "date_parse_failed", False

    # 5. YYYY/MM
    m = re.fullmatch(r"(\d{4})/(\d{2})", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if _valid_ym(y, mo):
            return f"{y:04d}-{mo:02d}", "date_yyyymm_parsed", True
        return None, "date_parse_failed", False

    # 6. Bare YYYY — ambiguous month, drop
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return None, "date_year_only", False

    return None, "date_parse_failed", False


def normalize_end_year(raw: str | int) -> tuple[int | None, str, bool]:
    """
    Parse an education graduation year to an integer.

    Returns (year_int, method, ok).
    Valid range: 1950–2100.
    """
    if raw is None:
        return None, "grad_year_failed", False

    if isinstance(raw, int):
        if _YEAR_MIN <= raw <= _YEAR_MAX:
            return raw, "grad_year_passthrough", True
        return None, "grad_year_failed", False

    s = str(raw).strip()
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        y = int(m.group(1))
        if _YEAR_MIN <= y <= _YEAR_MAX:
            return y, "grad_year_parsed", True
    return None, "grad_year_failed", False
