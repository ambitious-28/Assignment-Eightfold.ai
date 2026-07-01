"""Name normalization — trim, collapse whitespace, title-case. Stdlib only."""

from __future__ import annotations


def normalize_name(raw: str) -> tuple[str | None, str, bool]:
    """
    Normalize a person name: strip + collapse internal whitespace + title-case.

    Returns (cleaned_name, "name_normalized", ok).
    Empty after strip → (None, "name_empty", False).
    """
    if not raw:
        return None, "name_empty", False

    cleaned = " ".join(raw.strip().split())
    if not cleaned:
        return None, "name_empty", False

    return cleaned.title(), "name_normalized", True


def normalize_org_name(raw: str) -> tuple[str | None, str, bool]:
    """
    Normalize an organization or institution name: strip + collapse whitespace only.

    Deliberately does NOT title-case so that acronyms (IIT, BITS, NIT) and
    CamelCase brand names (TechCorp, FinEdge, CloudNative) are preserved as-is.

    Returns (cleaned_name, "org_name_normalized", ok).
    Empty after strip → (None, "name_empty", False).
    """
    if not raw:
        return None, "name_empty", False

    cleaned = " ".join(raw.strip().split())
    if not cleaned:
        return None, "name_empty", False

    return cleaned, "org_name_normalized", True


def name_match_key(name: str) -> str:
    """
    Produce a lowercase, whitespace-collapsed key for identity matching.

    NOT stored as output — used only for record clustering.
    """
    return " ".join(name.strip().lower().split())
