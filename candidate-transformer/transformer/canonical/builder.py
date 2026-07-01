"""
Stage 7 — Canonical builder.

Assembles one CanonicalProfile from a cluster of IntermediateRecords.

Steps:
  1. arbitrate_cluster  → per-field winners
  2. score_arbitration  → per-field confidence scores + drop_warnings
  3. Apply confidence gate (None fields become null in profile)
  4. Populate CanonicalProfile fields from winners
  5. Build ProvenanceEntry list (populated fields only)
  6. compute_overall_confidence
  7. generate_candidate_id
  8. Collect sources_seen (all source_files in cluster)
  9. Aggregate warnings (drops + adapter-level)

This module is the last stage left-of-the-wall.
After build_profile() returns, the record is treated as immutable.
Downstream projection operates on a deep copy.
"""

from __future__ import annotations

from transformer.adapters.base import IntermediateRecord
from transformer.merge.arbitrate import arbitrate_cluster
from transformer.merge.confidence import (
    compute_overall_confidence,
    score_arbitration,
    score_skill,
)
from transformer.models import (
    CanonicalProfile,
    Links,
    Location,
    ProvenanceEntry,
    SkillEntry,
)
from transformer.util.ids import generate_candidate_id


def build_profile(cluster: list[IntermediateRecord]) -> CanonicalProfile:
    """
    Assemble one CanonicalProfile from a cluster of IntermediateRecords.

    Input records are never mutated.

    Args:
        cluster: Non-empty list of IntermediateRecords belonging to the same person.

    Returns:
        A fully populated CanonicalProfile (the single internal truth for this candidate).
    """
    # ------------------------------------------------------------------
    # Step 1 — Arbitrate: pick a winner per field across all sources.
    # ------------------------------------------------------------------
    arbitration = arbitrate_cluster(cluster)

    # ------------------------------------------------------------------
    # Step 2 — Score confidence; identify fields to drop.
    # ------------------------------------------------------------------
    field_scores, drop_warnings = score_arbitration(arbitration)

    # ------------------------------------------------------------------
    # Step 3 — Build winners dict, applying the confidence gate.
    #           Fields with None score are treated as null.
    # ------------------------------------------------------------------
    winners: dict = {}
    for field, result in arbitration.items():
        if field_scores.get(field) is None:
            winners[field] = None   # dropped
        else:
            winners[field] = result.winner_value

    # ------------------------------------------------------------------
    # Step 4 — Populate CanonicalProfile fields.
    # ------------------------------------------------------------------
    full_name: str | None = winners.get("full_name")
    emails: list[str]     = winners.get("emails") or []
    phones: list[str]     = winners.get("phones") or []
    location: Location    = winners.get("location") or Location()
    links: Links          = winners.get("links")   or Links()
    headline: str | None  = winners.get("headline")
    years_experience      = winners.get("years_experience")

    # Skills — materialise per-skill confidence before attaching.
    raw_skills: list[SkillEntry] = winners.get("skills") or []
    for skill in raw_skills:
        skill.confidence = score_skill(skill)

    experience = winners.get("experience") or []
    education  = winners.get("education")  or []

    # ------------------------------------------------------------------
    # Step 5 — Build ProvenanceEntry list (populated fields only).
    #           Sort by field name for determinism.
    # ------------------------------------------------------------------
    provenance: list[ProvenanceEntry] = []
    for field in sorted(arbitration.keys()):
        result     = arbitration[field]
        winner_val = winners[field]
        confidence = field_scores.get(field)
        if winner_val is None or confidence is None:
            continue    # dropped or empty — no provenance entry
        provenance.append(ProvenanceEntry(
            field=field,
            final_value=winner_val,
            method=result.method,
            confidence=confidence,
            winner_source=result.winner_source,
            contributions=list(result.contributions),   # shallow copy for safety
        ))

    # ------------------------------------------------------------------
    # Step 6 — Compute overall_confidence.
    # ------------------------------------------------------------------
    overall_confidence = compute_overall_confidence(field_scores)

    # ------------------------------------------------------------------
    # Step 7 — Generate deterministic candidate_id.
    # ------------------------------------------------------------------
    primary_company = experience[0].company if experience else None
    candidate_id = generate_candidate_id(
        emails=emails,
        phones=phones,
        full_name=full_name,
        company=primary_company,
        city=location.city,
        headline=headline,
    )

    # ------------------------------------------------------------------
    # Step 8 — Collect sources_seen (logical source type per cluster record).
    # Using rec.source (e.g. "recruiter_csv") rather than rec.source_file keeps
    # this field deterministic across OSes and working-directory locations.
    # ------------------------------------------------------------------
    sources_seen = sorted(set(rec.source for rec in cluster))

    # ------------------------------------------------------------------
    # Step 9 — Aggregate warnings.
    # ------------------------------------------------------------------
    warnings: list[str] = list(drop_warnings)
    for rec in sorted(cluster, key=lambda r: r.source):
        warnings.extend(rec.warnings)

    # ------------------------------------------------------------------
    # Assemble and return.
    # ------------------------------------------------------------------
    return CanonicalProfile(
        candidate_id=candidate_id,
        full_name=full_name,
        emails=emails,
        phones=phones,
        location=location,
        links=links,
        headline=headline,
        years_experience=years_experience,
        skills=raw_skills,
        experience=experience,
        education=education,
        provenance=provenance,
        overall_confidence=overall_confidence,
        sources_seen=sources_seen,
        warnings=warnings,
    )
