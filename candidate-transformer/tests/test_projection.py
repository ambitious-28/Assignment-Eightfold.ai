"""
Stage 8 checkpoint tests — Path Resolver + Projector.

Run: pytest tests/test_projection.py -v
"""

from __future__ import annotations

import copy
import dataclasses

import pytest

from transformer.models import (
    CanonicalProfile,
    Contribution,
    DEFAULT_SCHEMA,
    ProvenanceEntry,
    SkillEntry,
)
from transformer.project.path_resolver import MISSING, resolve
from transformer.project.projector import project


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

def _profile() -> CanonicalProfile:
    """A minimal but representative CanonicalProfile for testing."""
    contrib = Contribution(
        source="recruiter_csv",
        raw_value="Aarav Sharma",
        normalized="Aarav Sharma",
        agreed=True,
    )
    prov = ProvenanceEntry(
        field="full_name",
        final_value="Aarav Sharma",
        method="name_normalized",
        confidence=0.90,
        winner_source="recruiter_csv",
        contributions=[contrib],
    )
    return CanonicalProfile(
        candidate_id="cand_abc123def456",
        full_name="Aarav Sharma",
        emails=["aarav@example.com", "aarav2@example.com"],
        phones=["+919876543210"],
        headline=None,
        years_experience=5.0,
        skills=[
            SkillEntry("Python", 0.90, ["recruiter_csv"]),
            SkillEntry("Docker", 0.85, ["ats_blob"]),
        ],
        overall_confidence=0.92,
        provenance=[prov],
        sources_seen=["ats.json", "recruiter.csv"],
        warnings=[],
    )


# ---------------------------------------------------------------------------
# TestPathResolver
# ---------------------------------------------------------------------------

class TestPathResolver:
    def test_simple_field(self):
        p = _profile()
        assert resolve(p, "full_name") == "Aarav Sharma"

    def test_simple_field_none(self):
        p = _profile()
        # headline is None — not MISSING, explicitly null
        assert resolve(p, "headline") is None

    def test_simple_field_float(self):
        p = _profile()
        assert resolve(p, "years_experience") == 5.0

    def test_indexed_first(self):
        p = _profile()
        assert resolve(p, "emails[0]") == "aarav@example.com"

    def test_indexed_second(self):
        p = _profile()
        assert resolve(p, "emails[1]") == "aarav2@example.com"

    def test_indexed_out_of_range(self):
        p = _profile()
        assert resolve(p, "emails[5]") is MISSING

    def test_indexed_empty_list(self):
        p = _profile()
        # phones has 1 element; index 1 is out of range
        assert resolve(p, "phones[1]") is MISSING

    def test_map_over_names(self):
        p = _profile()
        result = resolve(p, "skills[].name")
        assert result == ["Python", "Docker"]

    def test_map_over_confidence(self):
        p = _profile()
        result = resolve(p, "skills[].confidence")
        assert result == [0.90, 0.85]

    def test_map_over_empty(self):
        """Map-over on an empty list returns []."""
        p = _profile()
        # experience is empty list by default
        result = resolve(p, "experience[].company")
        assert result == []

    def test_unknown_field(self):
        p = _profile()
        assert resolve(p, "nonexistent_field") is MISSING

    def test_missing_is_not_none(self):
        """MISSING sentinel must be distinct from None."""
        assert MISSING is not None


# ---------------------------------------------------------------------------
# TestDefaultProjection
# ---------------------------------------------------------------------------

class TestDefaultProjection:
    def test_default_has_all_schema_fields(self):
        out = project(_profile())
        for field in DEFAULT_SCHEMA:
            assert field in out, f"DEFAULT_SCHEMA field {field!r} missing from output"

    def test_default_has_correct_field_count(self):
        out = project(_profile())
        assert len(out) == len(DEFAULT_SCHEMA)

    def test_default_provenance_flattened(self):
        out = project(_profile())
        prov = out["provenance"]
        assert isinstance(prov, list)
        assert len(prov) == 1
        entry = prov[0]
        # Flattened form: only these 3 keys
        assert set(entry.keys()) == {"field", "source", "method"}
        assert entry["field"] == "full_name"
        assert entry["source"] == "recruiter_csv"
        assert entry["method"] == "name_normalized"

    def test_default_candidate_id_present(self):
        out = project(_profile())
        assert out["candidate_id"] == "cand_abc123def456"

    def test_default_emails_list(self):
        out = project(_profile())
        assert isinstance(out["emails"], list)
        assert "aarav@example.com" in out["emails"]

    def test_default_skills_list_of_dicts(self):
        out = project(_profile())
        skills = out["skills"]
        assert isinstance(skills, list)
        assert len(skills) == 2
        assert isinstance(skills[0], dict)
        assert "name" in skills[0]

    def test_default_overall_confidence_present(self):
        out = project(_profile())
        assert out["overall_confidence"] == 0.92

    def test_default_field_order_matches_schema(self):
        out = project(_profile())
        assert list(out.keys()) == DEFAULT_SCHEMA


# ---------------------------------------------------------------------------
# TestConfigProjection
# ---------------------------------------------------------------------------

class TestConfigProjection:
    def test_remap_primary_email(self):
        """emails[0] remapped to output key 'primary_email'."""
        config = {
            "fields": [
                {"path": "primary_email", "from": "emails[0]", "type": "string"},
            ],
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert "primary_email" in out
        assert out["primary_email"] == "aarav@example.com"
        assert "emails" not in out  # only requested fields appear

    def test_remap_skill_names(self):
        """skills[].name → list of name strings."""
        config = {
            "fields": [
                {"path": "skills", "from": "skills[].name", "type": "string[]"},
            ],
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert out["skills"] == ["Python", "Docker"]

    def test_path_without_from_uses_canonical_field(self):
        """If 'from' is omitted, 'path' is used as source path."""
        config = {
            "fields": [
                {"path": "full_name", "type": "string"},
            ],
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert out["full_name"] == "Aarav Sharma"

    def test_on_missing_null(self):
        """MISSING path + on_missing=null → key present with None value."""
        config = {
            "fields": [
                {"path": "secondary_phone", "from": "phones[9]", "type": "string"},
            ],
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert "secondary_phone" in out
        assert out["secondary_phone"] is None

    def test_on_missing_omit(self):
        """MISSING path + on_missing=omit → key entirely absent from output."""
        config = {
            "fields": [
                {"path": "secondary_phone", "from": "phones[9]", "type": "string"},
                {"path": "full_name", "type": "string"},
            ],
            "on_missing": "omit",
        }
        out = project(_profile(), config)
        assert "secondary_phone" not in out
        assert "full_name" in out  # present fields unaffected

    def test_on_missing_error(self):
        """MISSING path + on_missing=error → ValueError raised."""
        config = {
            "fields": [
                {"path": "ghost", "from": "nonexistent_field", "type": "string"},
            ],
            "on_missing": "error",
        }
        with pytest.raises(ValueError):
            project(_profile(), config)

    def test_include_confidence_true(self):
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "include_confidence": True,
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert "overall_confidence" in out
        assert out["overall_confidence"] == 0.92

    def test_include_confidence_false(self):
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "include_confidence": False,
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert "overall_confidence" not in out

    def test_include_confidence_default_is_false(self):
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert "overall_confidence" not in out

    def test_include_provenance_true(self):
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "include_provenance": True,
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert "provenance" in out
        assert isinstance(out["provenance"], list)
        assert len(out["provenance"]) == 1

    def test_include_provenance_false(self):
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "include_provenance": False,
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert "provenance" not in out

    def test_include_provenance_default_is_false(self):
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert "provenance" not in out

    def test_provenance_enriched_has_contributions(self):
        """With include_provenance=true, entries must have 'contributions' key."""
        config = {
            "fields": [],
            "include_provenance": True,
            "on_missing": "null",
        }
        out = project(_profile(), config)
        for entry in out["provenance"]:
            assert "contributions" in entry
            assert "winner_source" in entry
            assert "confidence" in entry

    def test_empty_fields_spec_returns_empty_dict(self):
        config = {"fields": [], "on_missing": "null"}
        out = project(_profile(), config)
        assert out == {}

    def test_multiple_fields_all_remapped(self):
        config = {
            "fields": [
                {"path": "name",  "from": "full_name",  "type": "string"},
                {"path": "email", "from": "emails[0]",  "type": "string"},
                {"path": "phone", "from": "phones[0]",  "type": "string"},
            ],
            "on_missing": "null",
        }
        out = project(_profile(), config)
        assert out["name"]  == "Aarav Sharma"
        assert out["email"] == "aarav@example.com"
        assert out["phone"] == "+919876543210"


# ---------------------------------------------------------------------------
# TestWallAssertion
# ---------------------------------------------------------------------------

class TestWallAssertion:
    def _snapshot(self, profile: CanonicalProfile) -> dict:
        return dataclasses.asdict(profile)

    def test_default_projection_does_not_mutate(self):
        p = _profile()
        before = self._snapshot(p)
        project(p)
        after = self._snapshot(p)
        assert before == after

    def test_config_projection_does_not_mutate(self):
        p = _profile()
        before = self._snapshot(p)
        config = {
            "fields": [
                {"path": "name",  "from": "full_name", "type": "string"},
                {"path": "email", "from": "emails[0]", "type": "string"},
                {"path": "skills_list", "from": "skills[].name", "type": "string[]"},
            ],
            "include_confidence": True,
            "include_provenance": True,
            "on_missing": "null",
        }
        project(p, config)
        after = self._snapshot(p)
        assert before == after

    def test_multiple_projections_same_result(self):
        """Projecting the same profile twice produces identical output."""
        p = _profile()
        out1 = project(p)
        out2 = project(p)
        assert out1 == out2
