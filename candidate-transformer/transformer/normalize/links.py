"""URL / links normalization. Stdlib only."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z\d+\-.]*://")


def normalize_url(raw: str, method: str = "url_cleaned") -> tuple[str | None, str, bool]:
    """
    Clean and validate a URL.

    - Strips whitespace.
    - Prepends "https://" if no scheme is present.
    - Validates that the result has a non-empty scheme and netloc.
    - Does NOT modify path, query params, or fragment.

    Returns (cleaned_url, method, ok).
    Invalid → (None, "url_invalid", False).
    """
    if not raw or not raw.strip():
        return None, "url_invalid", False

    s = raw.strip()

    # Prepend scheme if missing
    if not _SCHEME_RE.match(s):
        s = "https://" + s

    parsed = urlparse(s)
    if not parsed.scheme or not parsed.netloc:
        return None, "url_invalid", False

    return s, method, True


def normalize_linkedin_url(raw: str) -> tuple[str | None, str, bool]:
    """Normalize a LinkedIn profile URL."""
    return normalize_url(raw, method="linkedin_url_cleaned")


def normalize_github_url(raw: str) -> tuple[str | None, str, bool]:
    """Normalize a GitHub profile URL."""
    return normalize_url(raw, method="github_url_cleaned")
