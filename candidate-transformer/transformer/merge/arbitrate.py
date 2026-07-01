"""
Arbitration — per-field winner selection within a cluster.

For each canonical field across a cluster of IntermediateRecords:
  - Scalar fields   → one winner by tier → agreement → SOURCE_ORDER.
  - Array fields    → union (deduped), not single-winner.
  - Structured      → sub-field arbitration (location, links).

Losers are retained in contributions for provenance.
Conflicts are recorded (multiple distinct normalized values detected).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from transformer.adapters.base import FieldValue, IntermediateRecord
from transformer.models import (
    Contribution,
    EducationEntry,
    ExperienceEntry,
    Links,
    Location,
    SkillEntry,
    SOURCE_ORDER,
    SOURCE_TIERS,
)
from transformer.normalize.names import name_match_key


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ArbitrationResult:
    """Outcome of picking a winner for one canonical field."""
    winner_value: Any                   # normalized winning value (None if all failed)
    winner_source: str                  # source that won (or highest-tier for arrays)
    method: str                         # normalization method of the winning value
    contributions: list[Contribution]   # ALL contributing sources, winners and losers
    conflicted: bool                    # True if ≥2 sources had different normalized values


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCALAR_FIELDS = ["full_name", "headline", "years_experience"]
_SOURCE_PRIORITY = {src: i for i, src in enumerate(SOURCE_ORDER)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tier(source: str) -> float:
    return SOURCE_TIERS.get(source, 0.0)


def _order(source: str) -> int:
    return _SOURCE_PRIORITY.get(source, 999)


def _collect_field(
    cluster: list[IntermediateRecord],
    field_name: str,
) -> list[tuple[str, FieldValue]]:
    """Return [(source, FieldValue), ...] for all records that have this field."""
    result = []
    for rec in cluster:
        fv = rec.fields.get(field_name)
        if fv is not None:
            result.append((rec.source, fv))
    return result


def _pick_scalar_winner(
    candidates: list[tuple[str, Any, str]],  # [(source, normalized_value, method), ...]
    all_candidates: list[tuple[str, Any, str]] | None = None,
) -> tuple[str, Any, str]:
    """
    Pick the winning (source, value, method) triple.

    Priority:
      1. Source reliability tier (highest wins).
      2. Agreement — value agreed on by most sources (across ALL tiers).
      3. Fixed tiebreak: SOURCE_ORDER index (lower = higher priority).
    """
    if not candidates:
        return ("", None, "")

    # Use all_candidates for agreement counting (includes sources at lower tiers)
    count_from = all_candidates if all_candidates is not None else candidates
    value_counts: Counter[Any] = Counter(
        c[1] for c in count_from if c[1] is not None
    )

    # Sort: tier DESC, agreement_count DESC, SOURCE_ORDER ASC
    sorted_cands = sorted(
        candidates,
        key=lambda c: (-_tier(c[0]), -value_counts.get(c[1], 0), _order(c[0])),
    )

    # Top tier group
    if not sorted_cands:
        return ("", None, "")
    top_tier = _tier(sorted_cands[0][0])
    top_group = [c for c in sorted_cands if _tier(c[0]) == top_tier]

    # Within top group: agreement then SOURCE_ORDER (already sorted above)
    return top_group[0]


def _make_contributions(
    source_fvs: list[tuple[str, FieldValue]],
    winner_value: Any,
) -> list[Contribution]:
    """Build Contribution list from all source FieldValues."""
    contribs: list[Contribution] = []
    for source, fv in sorted(source_fvs, key=lambda sf: (_order(sf[0]), sf[0])):
        norm_str = str(fv.normalized) if fv.normalized is not None else None
        win_str = str(winner_value) if winner_value is not None else None
        contribs.append(Contribution(
            source=source,
            raw_value=str(fv.raw) if fv.raw is not None else None,
            normalized=norm_str,
            agreed=fv.ok and (norm_str == win_str),
        ))
    return contribs


def _is_conflicted(source_fvs: list[tuple[str, FieldValue]]) -> bool:
    """True if ≥2 ok sources have different normalized values."""
    ok_values = {str(fv.normalized) for _, fv in source_fvs if fv.ok and fv.normalized is not None}
    return len(ok_values) > 1


def _location_conflicted(source_fvs: list[tuple[str, FieldValue]]) -> bool:
    """
    True only when two sources provide DIFFERENT non-null values for the same sub-field.
    A source with only city=Mumbai does NOT conflict with city=Mumbai+region+country —
    it is less complete, not contradictory. Only a city mismatch (Mumbai vs Pune) is a real conflict.
    """
    cities    = {fv.normalized.city    for _, fv in source_fvs
                 if fv.ok and fv.normalized and fv.normalized.city}
    regions   = {fv.normalized.region  for _, fv in source_fvs
                 if fv.ok and fv.normalized and fv.normalized.region}
    countries = {fv.normalized.country for _, fv in source_fvs
                 if fv.ok and fv.normalized and fv.normalized.country}
    return len(cities) > 1 or len(regions) > 1 or len(countries) > 1


# ---------------------------------------------------------------------------
# Scalar arbitration
# ---------------------------------------------------------------------------

def _arbitrate_scalar(
    cluster: list[IntermediateRecord],
    field_name: str,
) -> ArbitrationResult | None:
    """Arbitrate a scalar field (full_name, headline, years_experience)."""
    source_fvs = _collect_field(cluster, field_name)
    if not source_fvs:
        return None

    ok_candidates = [
        (src, fv.normalized, fv.method)
        for src, fv in source_fvs
        if fv.ok and fv.normalized is not None
    ]
    all_candidates = [
        (src, fv.normalized, fv.method)
        for src, fv in source_fvs
    ]

    if not ok_candidates:
        # All sources failed normalization
        contribs = _make_contributions(source_fvs, None)
        return ArbitrationResult(
            winner_value=None, winner_source="", method="normalization_failed",
            contributions=contribs, conflicted=False,
        )

    w_source, w_value, w_method = _pick_scalar_winner(ok_candidates, all_candidates)
    contribs = _make_contributions(source_fvs, w_value)
    return ArbitrationResult(
        winner_value=w_value,
        winner_source=w_source,
        method=w_method,
        contributions=contribs,
        conflicted=_is_conflicted(source_fvs),
    )


# ---------------------------------------------------------------------------
# Location arbitration (sub-field by sub-field)
# ---------------------------------------------------------------------------

def _arbitrate_location(cluster: list[IntermediateRecord]) -> ArbitrationResult | None:
    source_fvs = _collect_field(cluster, "location")
    if not source_fvs:
        return None

    # Gather sub-field candidates from each source's Location object
    city_cands: list[tuple[str, Any, str]] = []
    region_cands: list[tuple[str, Any, str]] = []
    country_cands: list[tuple[str, Any, str]] = []

    for src, fv in source_fvs:
        if not fv.ok or fv.normalized is None:
            continue
        loc: Location = fv.normalized
        method = fv.method
        if loc.city:
            city_cands.append((src, loc.city, method))
        if loc.region:
            region_cands.append((src, loc.region, method))
        if loc.country:
            country_cands.append((src, loc.country, method))

    if not (city_cands or region_cands or country_cands):
        return None

    city_w = _pick_scalar_winner(city_cands)[1] if city_cands else None
    region_w = _pick_scalar_winner(region_cands)[1] if region_cands else None
    country_w = _pick_scalar_winner(country_cands)[1] if country_cands else None

    # Winner source = highest-tier source that contributed any sub-field
    all_src = [s for s, _ in source_fvs if _.ok]
    winner_src = sorted(all_src, key=lambda s: (_tier(s), -_order(s)))[-1] if all_src else ""

    result_loc = Location(city=city_w, region=region_w, country=country_w)
    contribs = _make_contributions(source_fvs, result_loc)

    return ArbitrationResult(
        winner_value=result_loc,
        winner_source=winner_src,
        method="location_arbitrated",
        contributions=contribs,
        conflicted=_location_conflicted(source_fvs),
    )


# ---------------------------------------------------------------------------
# Links arbitration (sub-field by sub-field)
# ---------------------------------------------------------------------------

def _arbitrate_links(cluster: list[IntermediateRecord]) -> ArbitrationResult | None:
    source_fvs = _collect_field(cluster, "links")
    if not source_fvs:
        return None

    li_cands: list[tuple[str, Any, str]] = []
    gh_cands: list[tuple[str, Any, str]] = []
    port_cands: list[tuple[str, Any, str]] = []
    other_union: list[str] = []
    seen_other: set[str] = set()

    for src, fv in source_fvs:
        if not fv.ok or fv.normalized is None:
            continue
        lnk: Links = fv.normalized
        if lnk.linkedin:
            li_cands.append((src, lnk.linkedin, fv.method))
        if lnk.github:
            gh_cands.append((src, lnk.github, fv.method))
        if lnk.portfolio:
            port_cands.append((src, lnk.portfolio, fv.method))
        for u in lnk.other:
            if u not in seen_other:
                seen_other.add(u)
                other_union.append(u)

    if not (li_cands or gh_cands or port_cands or other_union):
        return None

    li_w = _pick_scalar_winner(li_cands)[1] if li_cands else None
    gh_w = _pick_scalar_winner(gh_cands)[1] if gh_cands else None
    port_w = _pick_scalar_winner(port_cands)[1] if port_cands else None

    all_src = [s for s, fv in source_fvs if fv.ok]
    winner_src = sorted(all_src, key=lambda s: (_tier(s), -_order(s)))[-1] if all_src else ""

    result_links = Links(linkedin=li_w, github=gh_w, portfolio=port_w, other=sorted(other_union))
    contribs = _make_contributions(source_fvs, result_links)

    return ArbitrationResult(
        winner_value=result_links,
        winner_source=winner_src,
        method="links_arbitrated",
        contributions=contribs,
        conflicted=False,
    )


# ---------------------------------------------------------------------------
# Array union: emails
# ---------------------------------------------------------------------------

def _arbitrate_emails(cluster: list[IntermediateRecord]) -> ArbitrationResult | None:
    source_fvs = _collect_field(cluster, "emails")
    if not source_fvs:
        return None

    # Determine primary email: from highest-tier source (SOURCE_ORDER tiebreak)
    best_sources = sorted(
        [(src, fv) for src, fv in source_fvs if fv.ok and fv.normalized],
        key=lambda sf: (-_tier(sf[0]), _order(sf[0])),
    )
    primary_emails: list[str] = best_sources[0][1].normalized if best_sources else []

    # Union all (deduped), primary first
    seen: set[str] = set()
    union: list[str] = []
    for email in primary_emails:
        if email not in seen:
            seen.add(email)
            union.append(email)
    for src, fv in sorted(source_fvs, key=lambda sf: (-_tier(sf[0]), _order(sf[0]))):
        if fv.ok and fv.normalized:
            for email in fv.normalized:
                if email not in seen:
                    seen.add(email)
                    union.append(email)

    winner_src = best_sources[0][0] if best_sources else ""
    contribs = _make_contributions(source_fvs, union[0] if union else None)

    return ArbitrationResult(
        winner_value=union,
        winner_source=winner_src,
        method="email_union",
        contributions=contribs,
        # Conflicted when the union has more emails than the highest-tier source alone
        # — means at least one other source contributed a different email address.
        conflicted=len(union) > len(set(primary_emails)),
    )


# ---------------------------------------------------------------------------
# Array union: phones
# ---------------------------------------------------------------------------

def _arbitrate_phones(cluster: list[IntermediateRecord]) -> ArbitrationResult | None:
    source_fvs = _collect_field(cluster, "phones")
    if not source_fvs:
        return None

    best_sources = sorted(
        [(src, fv) for src, fv in source_fvs if fv.ok and fv.normalized],
        key=lambda sf: (-_tier(sf[0]), _order(sf[0])),
    )
    primary_phones: list[str] = best_sources[0][1].normalized if best_sources else []

    seen: set[str] = set()
    union: list[str] = []
    for phone in primary_phones:
        if phone not in seen:
            seen.add(phone)
            union.append(phone)
    for src, fv in sorted(source_fvs, key=lambda sf: (-_tier(sf[0]), _order(sf[0]))):
        if fv.ok and fv.normalized:
            for phone in fv.normalized:
                if phone not in seen:
                    seen.add(phone)
                    union.append(phone)

    winner_src = best_sources[0][0] if best_sources else ""
    contribs = _make_contributions(source_fvs, union[0] if union else None)

    return ArbitrationResult(
        winner_value=union,
        winner_source=winner_src,
        method="phone_union",
        contributions=contribs,
        # Conflicted when the union has more phones than the highest-tier source alone
        # — means at least one other source contributed a different phone number.
        conflicted=len(union) > len(set(primary_phones)),
    )


# ---------------------------------------------------------------------------
# Array union: skills (by canonical name)
# ---------------------------------------------------------------------------

def _arbitrate_skills(cluster: list[IntermediateRecord]) -> ArbitrationResult | None:
    source_fvs = _collect_field(cluster, "skills")
    if not source_fvs:
        return None

    # Collect per-canonical-name: list of contributing sources
    name_to_sources: dict[str, list[str]] = defaultdict(list)
    name_to_entry: dict[str, SkillEntry] = {}

    for src, fv in sorted(source_fvs, key=lambda sf: (-_tier(sf[0]), _order(sf[0]))):
        if not fv.ok or not fv.normalized:
            continue
        entries: list[SkillEntry] = fv.normalized
        for entry in entries:
            if entry.name not in name_to_entry:
                name_to_entry[entry.name] = entry
            name_to_sources[entry.name].append(src)

    if not name_to_entry:
        return None

    # Build union (sorted alphabetically for determinism)
    union: list[SkillEntry] = []
    for name in sorted(name_to_entry.keys()):
        sources = sorted(set(name_to_sources[name]), key=_order)
        union.append(SkillEntry(name=name, confidence=0.0, sources=sources))

    # Winner source = highest-tier source that contributed any skill
    all_ok_sources = [src for src, fv in source_fvs if fv.ok and fv.normalized]
    winner_src = min(all_ok_sources, key=lambda s: (_order(s), s)) if all_ok_sources else ""

    contribs = _make_contributions(source_fvs, [s.name for s in union])

    return ArbitrationResult(
        winner_value=union,
        winner_source=winner_src,
        method="skill_union",
        contributions=contribs,
        conflicted=False,
    )


# ---------------------------------------------------------------------------
# Array union: experience (dedup by company+title)
# ---------------------------------------------------------------------------

def _exp_key(entry: ExperienceEntry) -> str:
    c = name_match_key(entry.company) if entry.company else ""
    t = name_match_key(entry.title) if entry.title else ""
    return f"{c}||{t}"


def _is_dominated(sparse: ExperienceEntry, rich: ExperienceEntry) -> bool:
    """True if sparse is a strict subset of rich (same company, compatible title, less info)."""
    if not sparse.company or not rich.company:
        return False
    if name_match_key(sparse.company) != name_match_key(rich.company):
        return False
    if sparse.start or sparse.end or sparse.summary:
        return False  # sparse has own dates/summary — keep it
    if not (rich.start or rich.end or rich.summary):
        return False  # rich has no extra info — not truly richer
    st = name_match_key(sparse.title or "")
    rt = name_match_key(rich.title or "")
    return st == rt or st in rt or rt in st


def _deduplicate_experience(entries: list[ExperienceEntry]) -> list[ExperienceEntry]:
    """Remove entries that are dominated by a richer entry at the same company."""
    result = []
    for i, entry in enumerate(entries):
        dominated = any(
            _is_dominated(entry, other)
            for j, other in enumerate(entries)
            if j != i
        )
        if not dominated:
            result.append(entry)
    return result


def _merge_exp_entries(high: ExperienceEntry, low: ExperienceEntry) -> ExperienceEntry:
    """Merge two experience entries for the same job — high-tier wins on conflicts."""
    return ExperienceEntry(
        company=high.company or low.company,
        title=high.title or low.title,
        start=high.start or low.start,
        end=high.end or low.end,
        summary=high.summary or low.summary,
    )


def _arbitrate_experience(cluster: list[IntermediateRecord]) -> ArbitrationResult | None:
    source_fvs = _collect_field(cluster, "experience")
    if not source_fvs:
        return None

    seen_keys: dict[str, ExperienceEntry] = {}

    for src, fv in sorted(source_fvs, key=lambda sf: (-_tier(sf[0]), _order(sf[0]))):
        if not fv.ok or not fv.normalized:
            continue
        for entry in fv.normalized:
            key = _exp_key(entry)
            if key not in seen_keys:
                seen_keys[key] = entry
            else:
                # Merge: higher-tier already in dict wins on conflicts
                seen_keys[key] = _merge_exp_entries(seen_keys[key], entry)

    if not seen_keys:
        return None

    # Sort by start date (newest first), then by key for determinism
    def _exp_sort_key(e: ExperienceEntry) -> tuple:
        return (e.start or "0000-00", name_match_key(e.company or ""), name_match_key(e.title or ""))

    union = sorted(seen_keys.values(), key=_exp_sort_key, reverse=True)
    union = _deduplicate_experience(union)

    all_ok_sources = [src for src, fv in source_fvs if fv.ok and fv.normalized]
    winner_src = min(all_ok_sources, key=lambda s: (_order(s), s)) if all_ok_sources else ""
    contribs = _make_contributions(source_fvs, str(len(union)) + " entries")

    return ArbitrationResult(
        winner_value=union,
        winner_source=winner_src,
        method="experience_union",
        contributions=contribs,
        conflicted=False,
    )


# ---------------------------------------------------------------------------
# Array union: education (dedup by institution+degree)
# ---------------------------------------------------------------------------

def _edu_key(entry: EducationEntry) -> str:
    i = name_match_key(entry.institution) if entry.institution else ""
    d = name_match_key(entry.degree) if entry.degree else ""
    return f"{i}||{d}"


def _merge_edu_entries(high: EducationEntry, low: EducationEntry) -> EducationEntry:
    return EducationEntry(
        institution=high.institution or low.institution,
        degree=high.degree or low.degree,
        field=high.field or low.field,
        end_year=high.end_year or low.end_year,
    )


def _arbitrate_education(cluster: list[IntermediateRecord]) -> ArbitrationResult | None:
    source_fvs = _collect_field(cluster, "education")
    if not source_fvs:
        return None

    seen_keys: dict[str, EducationEntry] = {}

    for src, fv in sorted(source_fvs, key=lambda sf: (-_tier(sf[0]), _order(sf[0]))):
        if not fv.ok or not fv.normalized:
            continue
        for entry in fv.normalized:
            key = _edu_key(entry)
            if key not in seen_keys:
                seen_keys[key] = entry
            else:
                seen_keys[key] = _merge_edu_entries(seen_keys[key], entry)

    if not seen_keys:
        return None

    union = sorted(seen_keys.values(), key=lambda e: (-(e.end_year or 0), _edu_key(e)))

    all_ok_sources = [src for src, fv in source_fvs if fv.ok and fv.normalized]
    winner_src = min(all_ok_sources, key=lambda s: (_order(s), s)) if all_ok_sources else ""
    contribs = _make_contributions(source_fvs, str(len(union)) + " entries")

    return ArbitrationResult(
        winner_value=union,
        winner_source=winner_src,
        method="education_union",
        contributions=contribs,
        conflicted=False,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def arbitrate_cluster(cluster: list[IntermediateRecord]) -> dict[str, ArbitrationResult]:
    """
    For each canonical field present in the cluster, select a winner.

    Scalar fields: tier → agreement → SOURCE_ORDER.
    Array fields (emails, phones, skills, experience, education): union + dedup.
    Structured scalars (location, links): sub-field arbitration.

    Returns: field_name → ArbitrationResult.
    Does not mutate input records.
    """
    results: dict[str, ArbitrationResult] = {}

    # Scalar fields
    for field_name in SCALAR_FIELDS:
        result = _arbitrate_scalar(cluster, field_name)
        if result is not None:
            results[field_name] = result

    # Structured scalars
    loc_result = _arbitrate_location(cluster)
    if loc_result is not None:
        results["location"] = loc_result

    links_result = _arbitrate_links(cluster)
    if links_result is not None:
        results["links"] = links_result

    # Array unions
    for fn, arbitrator in [
        ("emails", _arbitrate_emails),
        ("phones", _arbitrate_phones),
        ("skills", _arbitrate_skills),
        ("experience", _arbitrate_experience),
        ("education", _arbitrate_education),
    ]:
        result = arbitrator(cluster)
        if result is not None:
            results[fn] = result

    return results
