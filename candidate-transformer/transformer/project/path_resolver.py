"""
Stage 8 — Path resolver for projection layer.

Resolves path expressions against a CanonicalProfile.

Supported patterns:
  "full_name"       → profile.full_name              (simple field)
  "emails[0]"       → profile.emails[0]              (indexed array access)
  "skills[].name"   → [s.name for s in profile.skills]  (map-over-array)

Returns MISSING (module-level singleton) when the path does not resolve.
Returns None when the field exists but its value is None (explicit null).
"""

from __future__ import annotations

import re
from typing import Any

from transformer.models import CanonicalProfile

# ---------------------------------------------------------------------------
# Public sentinel
# ---------------------------------------------------------------------------

MISSING = object()
"""Returned by resolve() when a path expression does not resolve.

Distinct from None so callers can differentiate:
  - MISSING → the path had no value (apply on_missing policy)
  - None    → the value is explicitly null
"""

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Must be checked BEFORE indexed pattern (longer prefix match)
_MAP_RE   = re.compile(r'^(\w+)\[\]\.(\w+)$')   # skills[].name
_INDEX_RE = re.compile(r'^(\w+)\[(\d+)\]$')      # emails[0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve(profile: CanonicalProfile, path: str) -> Any:
    """
    Resolve a path expression against a CanonicalProfile.

    Patterns (checked in order):
      1. Map-over-array  — `field[].attr`  → list of attr values across array
      2. Indexed access  — `field[N]`      → element at index N (or MISSING)
      3. Simple field    — `field`         → the field value (or MISSING)

    Returns:
        The resolved value (may be None for explicit nulls).
        MISSING if the path does not resolve.
    """
    # Pattern 1: map-over-array  e.g. skills[].name
    m = _MAP_RE.match(path)
    if m:
        field_name, attr = m.group(1), m.group(2)
        if not hasattr(profile, field_name):
            return MISSING
        lst = getattr(profile, field_name)
        if lst is None:
            return MISSING
        return [getattr(item, attr, None) for item in lst]

    # Pattern 2: indexed access  e.g. emails[0]
    m = _INDEX_RE.match(path)
    if m:
        field_name, idx = m.group(1), int(m.group(2))
        lst = getattr(profile, field_name, None)
        if not lst or idx >= len(lst):
            return MISSING
        return lst[idx]

    # Pattern 3: simple field  e.g. full_name
    return getattr(profile, path, MISSING)
