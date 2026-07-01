"""
Deterministic candidate_id generation (PRD §2.3).

candidate_id = "cand_" + sha1(strongest_match_key)[:12]

strongest_match_key priority:
  1. normalized primary email        (emails[0])
  2. normalized primary phone        (phones[0])
  3. compound fallback               name|company|city|headline
     — combines all available discriminating fields so two people with the same
       name (e.g. two "Priya Sharma") get different IDs if anything else differs
  4. None  — no identity data; caller must not reach here (viability check)

Note: name+company alone is NOT used as a match key in the matcher (see matcher.py),
so it is not used here either. The compound fallback is only for ID stability when
no email or phone is available — it is never used for clustering decisions.
"""

from __future__ import annotations

import hashlib

from transformer.normalize.names import name_match_key


def generate_candidate_id(
    emails: list[str],
    phones: list[str],
    full_name: str | None,
    company: str | None,
    city: str | None = None,
    headline: str | None = None,
) -> str:
    """
    Return a deterministic candidate_id derived from the strongest identity anchor.

    Args:
        emails:    Normalized (lowercased) email list — emails[0] is the primary.
        phones:    Normalized E.164 phone list — phones[0] is the primary.
        full_name: Normalized full name (or None).
        company:   Normalized company name from experience[0] (or None).
        city:      Normalized city from location (or None) — used in fallback compound key.
        headline:  Normalized headline (or None) — used in fallback compound key.

    Returns:
        A string of the form "cand_<12 hex chars>".

    Raises:
        ValueError: If no identity data is available. This should be prevented
                    upstream by the pipeline's viability check.
    """
    key = _strongest_key(emails, phones, full_name, company, city, headline)
    if key is None:
        raise ValueError(
            "generate_candidate_id: cluster has no email, phone, or name. "
            "This cluster should have been filtered by the pipeline viability check "
            "before reaching the builder."
        )
    digest = hashlib.sha1(key.encode()).hexdigest()[:12]
    return f"cand_{digest}"


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _strongest_key(
    emails: list[str],
    phones: list[str],
    full_name: str | None,
    company: str | None,
    city: str | None = None,
    headline: str | None = None,
) -> str | None:
    """Return the strongest available identity key, or None if no data exists."""
    if emails:
        return emails[0]
    if phones:
        return phones[0]
    # Compound fallback: combine all available discriminating fields.
    # Using just name alone risks collisions for common names (e.g. "Priya Sharma").
    # Adding company, city, and headline makes the key practically unique even
    # when no email or phone is available.
    name_k    = name_match_key(full_name) if full_name else ""
    company_k = name_match_key(company)   if company   else ""
    city_k    = (city or "").strip().lower()
    headline_k = (headline or "").strip().lower()
    if name_k:
        return f"{name_k}|{company_k}|{city_k}|{headline_k}"
    return None
