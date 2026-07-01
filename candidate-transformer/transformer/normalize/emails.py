"""Email normalization — lowercase, trim, dedupe. Stdlib only."""

from __future__ import annotations


def normalize_email(raw: str) -> tuple[str | None, str, bool]:
    """
    Normalize a single email address.

    Returns (normalized, method, ok).
    Rules: strip whitespace, lowercase, must contain exactly one '@'
    with non-empty local-part and domain.
    """
    if not raw:
        return None, "email_invalid", False

    cleaned = raw.strip().lower()
    if not cleaned:
        return None, "email_invalid", False

    parts = cleaned.split("@")
    if len(parts) != 2:
        return None, "email_invalid", False

    local, domain = parts
    if not local or not domain or "." not in domain:
        return None, "email_invalid", False

    return cleaned, "email_lowercased", True


def normalize_emails(raws: list[str]) -> list[str]:
    """
    Normalize a list of raw email strings.

    Drops failures, deduplicates (case-insensitive), preserves stable order
    of first occurrence.
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in raws:
        value, _, ok = normalize_email(raw)
        if ok and value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
