"""Phone normalization — E.164 format, default region IN."""

from __future__ import annotations

import phonenumbers


def normalize_phone(raw: str) -> tuple[str | None, str, bool]:
    """
    Normalize a raw phone string to E.164 format.

    Returns (normalized, method, ok).
    Default region is IN (India) for bare 10-digit numbers.
    Any unparseable or invalid number → (None, "e164_failed", False).
    """
    if not raw or not raw.strip():
        return None, "e164_failed", False

    try:
        parsed = phonenumbers.parse(raw.strip(), "IN")
    except phonenumbers.phonenumberutil.NumberParseException:
        return None, "e164_failed", False

    if not phonenumbers.is_valid_number(parsed):
        return None, "e164_failed", False

    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return e164, "e164_normalized", True
