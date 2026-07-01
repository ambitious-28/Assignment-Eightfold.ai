from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Sub-record types
# ---------------------------------------------------------------------------

@dataclass
class Location:
    city: str | None = None
    region: str | None = None
    country: str | None = None  # ISO-3166 alpha-2, e.g. "IN"


@dataclass
class Links:
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    other: list[str] = field(default_factory=list)


@dataclass
class Contribution:
    """Per-source receipt for a single field value."""
    source: str
    raw_value: str | None
    normalized: str | None
    agreed: bool  # True if this source's normalized value == winner


@dataclass
class ProvenanceEntry:
    """
    Enriched provenance for one field.

    Default Eightfold schema flattens this to {field, source, method}
    (source = winner_source).  The full enriched form is emitted when
    the projection config sets include_provenance=true with full detail.
    """
    field: str
    final_value: Any
    method: str
    confidence: float
    winner_source: str
    contributions: list[Contribution] = field(default_factory=list)


@dataclass
class SkillEntry:
    name: str          # canonical skill name (after alias map)
    confidence: float
    sources: list[str] = field(default_factory=list)


@dataclass
class ExperienceEntry:
    company: str | None = None
    title: str | None = None
    start: str | None = None   # YYYY-MM
    end: str | None = None     # YYYY-MM or "Present"
    summary: str | None = None


@dataclass
class EducationEntry:
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    end_year: int | None = None


# ---------------------------------------------------------------------------
# Top-level canonical profile  (left-of-wall truth)
# ---------------------------------------------------------------------------

@dataclass
class CanonicalProfile:
    """
    The single internal truth for one candidate.

    Assembled by canonical/builder.py.  Downstream projection operates on a
    deep copy — this record is never mutated after construction.
    """
    # Eightfold fixed fields
    candidate_id: str = ""
    full_name: str | None = None
    emails: list[str] = field(default_factory=list)       # lowercased, deduped
    phones: list[str] = field(default_factory=list)       # E.164
    location: Location = field(default_factory=Location)
    links: Links = field(default_factory=Links)
    headline: str | None = None
    years_experience: float | None = None
    skills: list[SkillEntry] = field(default_factory=list)
    experience: list[ExperienceEntry] = field(default_factory=list)
    education: list[EducationEntry] = field(default_factory=list)
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    overall_confidence: float = 0.0

    # Our additions (justified in README)
    sources_seen: list[str] = field(default_factory=list)
    # ^ roll-up of every source file that contributed (even if it won no field)
    warnings: list[str] = field(default_factory=list)
    # ^ records what was dropped/skipped and why (provenance only shows values
    #   that made it IN; warnings make robustness + "never invented" visible)


# ---------------------------------------------------------------------------
# Schema constants  (fixed — never change without updating tests)
# ---------------------------------------------------------------------------

SOURCE_TIERS: dict[str, float] = {
    "recruiter_csv": 0.90,
    "ats_blob": 0.85,
    "linkedin_export": 0.70,   # reserved / not implemented
    "resume": 0.60,
    "recruiter_notes": 0.50,
}

# Deterministic tiebreak order; lower index = higher priority.
# Used by arbitrate.py when tier + agreement are equal.
SOURCE_ORDER: list[str] = [
    "recruiter_csv",
    "ats_blob",
    "linkedin_export",
    "resume",
    "recruiter_notes",
]

# All canonical output field names (Eightfold 13 + our 2 additions).
DEFAULT_SCHEMA: list[str] = [
    "candidate_id",
    "full_name",
    "emails",
    "phones",
    "location",
    "links",
    "headline",
    "years_experience",
    "skills",
    "experience",
    "education",
    "provenance",
    "overall_confidence",
    # Our additions
    "sources_seen",
    "warnings",
]

# Identity fields get 2× weight in overall_confidence calculation.
IDENTITY_FIELDS: frozenset[str] = frozenset({"full_name", "emails", "phones"})
