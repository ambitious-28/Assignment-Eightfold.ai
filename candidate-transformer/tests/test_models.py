"""
Stage 1 checkpoint tests — Models & schema constants.

Run: pytest tests/test_models.py -v
"""

import pytest
from transformer.models import (
    CanonicalProfile,
    Contribution,
    DEFAULT_SCHEMA,
    EducationEntry,
    ExperienceEntry,
    IDENTITY_FIELDS,
    Links,
    Location,
    ProvenanceEntry,
    SkillEntry,
    SOURCE_ORDER,
    SOURCE_TIERS,
)


# ---------------------------------------------------------------------------
# CanonicalProfile construction
# ---------------------------------------------------------------------------

class TestCanonicalProfile:
    def test_constructs_with_no_args(self):
        p = CanonicalProfile()
        assert p is not None

    def test_all_eightfold_fields_present(self):
        p = CanonicalProfile()
        eightfold_fields = [
            "candidate_id", "full_name", "emails", "phones",
            "location", "links", "headline", "years_experience",
            "skills", "experience", "education", "provenance",
            "overall_confidence",
        ]
        for f in eightfold_fields:
            assert hasattr(p, f), f"Missing Eightfold field: {f}"

    def test_our_additions_present(self):
        p = CanonicalProfile()
        assert hasattr(p, "sources_seen")
        assert hasattr(p, "warnings")

    def test_list_fields_default_to_empty_list(self):
        p = CanonicalProfile()
        for attr in ("emails", "phones", "skills", "experience", "education", "provenance",
                     "sources_seen", "warnings"):
            assert getattr(p, attr) == [], f"{attr} should default to []"

    def test_location_is_location_instance(self):
        p = CanonicalProfile()
        assert isinstance(p.location, Location)

    def test_links_is_links_instance(self):
        p = CanonicalProfile()
        assert isinstance(p.links, Links)

    def test_candidate_id_defaults_to_empty_string(self):
        assert CanonicalProfile().candidate_id == ""

    def test_overall_confidence_defaults_to_zero(self):
        assert CanonicalProfile().overall_confidence == 0.0

    def test_nullable_fields_default_to_none(self):
        p = CanonicalProfile()
        for attr in ("full_name", "headline", "years_experience"):
            assert getattr(p, attr) is None, f"{attr} should default to None"

    def test_independent_default_factory(self):
        """Mutating one profile's list must not affect another."""
        p1 = CanonicalProfile()
        p2 = CanonicalProfile()
        p1.emails.append("a@example.com")
        assert p2.emails == [], "default_factory must produce independent lists"
        p1.warnings.append("some warning")
        assert p2.warnings == []


# ---------------------------------------------------------------------------
# Sub-record dataclasses
# ---------------------------------------------------------------------------

class TestSubRecords:
    def test_location_defaults_all_none(self):
        loc = Location()
        assert loc.city is None
        assert loc.region is None
        assert loc.country is None

    def test_links_defaults(self):
        lnk = Links()
        assert lnk.linkedin is None
        assert lnk.github is None
        assert lnk.portfolio is None
        assert lnk.other == []

    def test_skill_entry_requires_name_and_confidence(self):
        s = SkillEntry(name="Python", confidence=0.9)
        assert s.name == "Python"
        assert s.confidence == 0.9
        assert s.sources == []

    def test_experience_entry_all_none_by_default(self):
        e = ExperienceEntry()
        assert e.company is None and e.title is None

    def test_education_entry_all_none_by_default(self):
        e = EducationEntry()
        assert e.institution is None and e.end_year is None

    def test_contribution_fields(self):
        c = Contribution(source="recruiter_csv", raw_value="98765-43210",
                         normalized="+919876543210", agreed=True)
        assert c.source == "recruiter_csv"
        assert c.agreed is True

    def test_provenance_entry_defaults(self):
        p = ProvenanceEntry(
            field="phones[0]",
            final_value="+919876543210",
            method="e164_normalized",
            confidence=0.95,
            winner_source="recruiter_csv",
        )
        assert p.contributions == []


# ---------------------------------------------------------------------------
# SOURCE_TIERS
# ---------------------------------------------------------------------------

class TestSourceTiers:
    def test_is_dict(self):
        assert isinstance(SOURCE_TIERS, dict)

    def test_implemented_sources_present(self):
        for src in ("recruiter_csv", "ats_blob", "resume", "recruiter_notes"):
            assert src in SOURCE_TIERS, f"{src} missing from SOURCE_TIERS"

    def test_correct_values(self):
        assert SOURCE_TIERS["recruiter_csv"] == 0.90
        assert SOURCE_TIERS["ats_blob"] == 0.85
        assert SOURCE_TIERS["resume"] == 0.60
        assert SOURCE_TIERS["recruiter_notes"] == 0.50

    def test_recruiter_csv_highest_implemented(self):
        implemented = {k: v for k, v in SOURCE_TIERS.items() if k != "linkedin_export"}
        assert SOURCE_TIERS["recruiter_csv"] == max(implemented.values())

    def test_recruiter_notes_lowest(self):
        assert SOURCE_TIERS["recruiter_notes"] == min(SOURCE_TIERS.values())


# ---------------------------------------------------------------------------
# SOURCE_ORDER
# ---------------------------------------------------------------------------

class TestSourceOrder:
    def test_is_list(self):
        assert isinstance(SOURCE_ORDER, list)

    def test_recruiter_csv_first(self):
        assert SOURCE_ORDER[0] == "recruiter_csv"

    def test_recruiter_notes_last(self):
        assert SOURCE_ORDER[-1] == "recruiter_notes"

    def test_all_tier_keys_present(self):
        for src in SOURCE_TIERS:
            assert src in SOURCE_ORDER, f"{src} missing from SOURCE_ORDER"

    def test_no_duplicates(self):
        assert len(SOURCE_ORDER) == len(set(SOURCE_ORDER))


# ---------------------------------------------------------------------------
# DEFAULT_SCHEMA
# ---------------------------------------------------------------------------

class TestDefaultSchema:
    def test_is_list(self):
        assert isinstance(DEFAULT_SCHEMA, list)

    def test_contains_all_eightfold_fields(self):
        required = [
            "candidate_id", "full_name", "emails", "phones",
            "location", "links", "headline", "years_experience",
            "skills", "experience", "education", "provenance",
            "overall_confidence",
        ]
        for f in required:
            assert f in DEFAULT_SCHEMA, f"Eightfold field {f!r} missing from DEFAULT_SCHEMA"

    def test_contains_our_additions(self):
        assert "sources_seen" in DEFAULT_SCHEMA
        assert "warnings" in DEFAULT_SCHEMA

    def test_total_field_count(self):
        # 13 Eightfold + 2 additions = 15
        assert len(DEFAULT_SCHEMA) == 15

    def test_no_duplicates(self):
        assert len(DEFAULT_SCHEMA) == len(set(DEFAULT_SCHEMA))


# ---------------------------------------------------------------------------
# IDENTITY_FIELDS
# ---------------------------------------------------------------------------

class TestIdentityFields:
    def test_is_frozenset(self):
        assert isinstance(IDENTITY_FIELDS, frozenset)

    def test_contains_correct_fields(self):
        assert IDENTITY_FIELDS == {"full_name", "emails", "phones"}
