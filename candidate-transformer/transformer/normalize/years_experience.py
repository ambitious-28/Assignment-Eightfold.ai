"""Years of experience normalization. Stdlib only."""

from __future__ import annotations

import re


def normalize_years_experience(raw: str | int | float) -> tuple[float | None, str, bool]:
    """
    Parse years of experience to a float.

    Returns (years_float, method, ok).
    Valid range: 0–60.

    Patterns handled:
      "5" / "5.0"            → 5.0,  "years_parsed"
      "5+"  / "5 years" / "5 yrs" / "~5"  → 5.0, "years_parsed"
      "5-7" / "5 to 7"      → 5.0,  "years_range_lower"  (take lower bound)
      "lots" / free text / out-of-range → (None, "years_parse_failed", False)
    """
    if raw is None:
        return None, "years_parse_failed", False

    # Already numeric
    if isinstance(raw, (int, float)):
        val = float(raw)
        if 0.0 <= val <= 60.0:
            return val, "years_passthrough", True
        return None, "years_parse_failed", False

    s = str(raw).strip()
    if not s:
        return None, "years_parse_failed", False

    # Range: "5-7" or "5 to 7" — take lower bound
    m = re.match(r"^~?(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)(?:\s*(?:years?|yrs?))?$", s, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        if 0.0 <= val <= 60.0:
            return val, "years_range_lower", True
        return None, "years_parse_failed", False

    # Single value with optional suffix: "5", "5+", "5 years", "5 yrs", "~5"
    m = re.match(r"^~?(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)?$", s, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        if 0.0 <= val <= 60.0:
            return val, "years_parsed", True
        return None, "years_parse_failed", False

    return None, "years_parse_failed", False
