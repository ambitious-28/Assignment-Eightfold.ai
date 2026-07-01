"""Headline normalization — strip + collapse whitespace. Stdlib only."""

from __future__ import annotations


def normalize_headline(raw: str) -> tuple[str | None, str, bool]:
    """
    Clean a free-text headline.

    - Strip leading/trailing whitespace.
    - Collapse internal whitespace runs to a single space.
    - No structural transformation — headline content is preserved as-is.

    Returns (cleaned_headline, "headline_cleaned", ok).
    Empty after strip → (None, "headline_empty", False).
    """
    if not raw:
        return None, "headline_empty", False

    cleaned = " ".join(raw.strip().split())
    if not cleaned:
        return None, "headline_empty", False

    return cleaned, "headline_cleaned", True
