"""
Stage 7 checkpoint tests — Canonical Builder.

Run: pytest tests/test_builder.py -v
"""

from __future__ import annotations

import copy
import random

import pytest

from transformer.adapters.base import FieldValue, IntermediateRecord
from transformer.canonical.builder import build_profile
from transformer.models import (
    CanonicalProfile,
    ExperienceEntry,
    SkillEntry,
)
from transformer.util.ids import generate_candidate_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fv(raw, normalized, method: str = "test", ok: bool = True) -> FieldValue:
    return FieldValue(raw=raw, normalized=normalized, method=method, ok=ok)


def _fv_list(items: list, ok: bool = True) -> FieldValue:
    return FieldValue(raw=items, normalized=items, method="test", ok=ok)


def _fv_skill(names: list[str], source: str) -> FieldValue:
    entries = [SkillEntry(name=n, confidence=0.0, sources=[source]) for n in names]
    return FieldValue(raw=names, normalized=entries, method="test", ok=True)


def _fv_exp(company: str, title: str) -> FieldValue:
    entry = ExperienceEntry(company=company, title=title)
    return FieldValue(raw={}, normalized=[entry], method="test", ok=True)


def _make_rec(
    source: str,
    source_file: str,
    fields: dict | None = None,
    warnings: list[str] | None = None,
) -> IntermediateRecord:
    rec = IntermediateRecord(
        source=source,
        source_file=source_file,
        fields=fields or {},
    )
    if warnings:
        rec.warnings.extend(warnings)
    return rec


def _three_source_cluster() -> list[IntermediateRecord]:
    """CSV + ATS + resume for Aarav Sharma — same email binds them."""
    csv = _make_rec("recruiter_csv", "recruiter.csv", {
        "full_name": _fv("Aarav Sharma", "Aarav Sharma", "name_normalized"),
        "emails":    _fv_list(["aarav@example.com"]),
        "phones":    _fv_list(["+919876543210"]),
        "skills":    _fv_skill(["Python"], "recruiter_csv"),
        "experience": _fv_exp("TechCorp", "Engineer"),
    })
    ats = _make_rec("ats_blob", "ats.json", {
        "full_name": _fv("Aarav Sharma", "Aarav Sharma", "name_normalized"),
        "emails":    _fv_list(["aarav@example.com"]),
        "phones":    _fv_list(["+919876543210"]),
        "skills":    _fv_skill(["Python", "Docker"], "ats_blob"),
    })
    resume = _make_rec("resume", "aarav_resume.pdf", {
        "full_name": _fv("Aarav Sharma", "Aarav Sharma", "name_normalized"),
        "emails":    _fv_list(["aarav@example.com"]),
        "skills":    _fv_skill(["Kubernetes"], "resume"),
    })
    return [csv, ats, resume]


# ---------------------------------------------------------------------------
# TestCandidateId
# ---------------------------------------------------------------------------

class TestCandidateId:
    def test_email_anchored_id(self):
        id1 = generate_candidate_id(["x@example.com"], [], None, None)
        id2 = generate_candidate_id(["x@example.com"], [], "Alice", "TechCorp")
        assert id1 == id2  # email takes priority

    def test_phone_fallback(self):
        id1 = generate_candidate_id([], ["+919876543210"], None, None)
        id2 = generate_candidate_id([], ["+919876543210"], "Bob", "AcmeCorp")
        assert id1 == id2

    def test_name_company_fallback(self):
        id1 = generate_candidate_id([], [], "Aarav Sharma", "TechCorp")
        id2 = generate_candidate_id([], [], "Aarav Sharma", "TechCorp")
        assert id1 == id2

    def test_id_format(self):
        cid = generate_candidate_id(["a@b.com"], [], None, None)
        assert cid.startswith("cand_")
        assert len(cid) == 17  # "cand_" (5) + 12 hex chars

    def test_different_emails_different_id(self):
        id1 = generate_candidate_id(["alice@example.com"], [], None, None)
        id2 = generate_candidate_id(["bob@example.com"], [], None, None)
        assert id1 != id2

    def test_deterministic(self):
        args = (["x@example.com"], ["+911111111111"], "Alice", "Corp")
        assert generate_candidate_id(*args) == generate_candidate_id(*args)


# ---------------------------------------------------------------------------
# TestBuildProfile — 3-source cluster
# ---------------------------------------------------------------------------

class TestBuildProfile:
    @pytest.fixture
    def profile(self) -> CanonicalProfile:
        return build_profile(_three_source_cluster())

    def test_returns_canonical_profile(self, profile):
        assert isinstance(profile, CanonicalProfile)

    def test_full_name_populated(self, profile):
        assert profile.full_name == "Aarav Sharma"

    def test_emails_populated(self, profile):
        assert isinstance(profile.emails, list)
        assert len(profile.emails) >= 1
        assert "aarav@example.com" in profile.emails

    def test_phones_populated(self, profile):
        assert "+919876543210" in profile.phones

    def test_candidate_id_set(self, profile):
        assert profile.candidate_id.startswith("cand_")
        assert len(profile.candidate_id) == 17

    def test_candidate_id_deterministic(self):
        cluster = _three_source_cluster()
        id1 = build_profile(cluster).candidate_id
        id2 = build_profile(cluster).candidate_id
        assert id1 == id2

    def test_sources_seen_all_three(self, profile):
        assert "recruiter_csv" in profile.sources_seen
        assert "ats_blob" in profile.sources_seen
        assert "resume" in profile.sources_seen

    def test_source_seen_zero_win_still_present(self):
        """A source that won no field must still appear in sources_seen."""
        # CSV + ATS share email/phone; resume has no email/phone
        # but its source type should still be in sources_seen regardless
        cluster = _three_source_cluster()
        profile = build_profile(cluster)
        assert "resume" in profile.sources_seen

    def test_every_populated_field_has_provenance(self, profile):
        prov_fields = {p.field for p in profile.provenance}
        # Check key fields with values have provenance entries
        if profile.full_name is not None:
            assert "full_name" in prov_fields
        if profile.emails:
            assert "emails" in prov_fields
        if profile.phones:
            assert "phones" in prov_fields

    def test_provenance_winner_source_set(self, profile):
        for p in profile.provenance:
            assert p.winner_source, f"Field {p.field} has empty winner_source"

    def test_provenance_contributions_present(self, profile):
        for p in profile.provenance:
            assert len(p.contributions) >= 1, f"Field {p.field} has no contributions"

    def test_overall_confidence_range(self, profile):
        assert 0.0 <= profile.overall_confidence <= 1.0

    def test_overall_confidence_rounded(self, profile):
        assert profile.overall_confidence == round(profile.overall_confidence, 2)

    def test_skills_confidence_materialised(self, profile):
        assert len(profile.skills) >= 1
        for skill in profile.skills:
            assert skill.confidence > 0.0, f"Skill {skill.name} has zero confidence"


# ---------------------------------------------------------------------------
# TestDroppedFields
# ---------------------------------------------------------------------------

class TestDroppedFields:
    def test_dropped_field_absent_from_provenance(self):
        """A field from an unknown-tier source (confidence 0.0) is dropped → no provenance."""
        # full_name from unknown_source: tier 0.0 → confidence 0.0 < 0.40 → dropped.
        # Email is from recruiter_csv so it survives the confidence gate and anchors the ID.
        rec_name = _make_rec("unknown_source", "x.csv", {
            "full_name": _fv("Ghost", "Ghost"),
        })
        rec_email = _make_rec("recruiter_csv", "x.csv", {
            "emails": _fv_list(["ghost@example.com"]),
        })
        profile = build_profile([rec_name, rec_email])
        prov_fields = {p.field for p in profile.provenance}
        # full_name from unknown_source has tier 0.0 → confidence 0.0 < 0.40 → dropped
        assert "full_name" not in prov_fields

    def test_dropped_field_warning_present(self):
        # full_name from unknown_source: dropped. Email from recruiter_csv: anchors the ID.
        rec_name = _make_rec("unknown_source", "x.csv", {
            "full_name": _fv("Ghost", "Ghost"),
        })
        rec_email = _make_rec("recruiter_csv", "x.csv", {
            "emails": _fv_list(["ghost@example.com"]),
        })
        profile = build_profile([rec_name, rec_email])
        # At least one warning should mention the dropped field
        assert any("full_name" in w for w in profile.warnings)


# ---------------------------------------------------------------------------
# TestNoMutation
# ---------------------------------------------------------------------------

class TestNoMutation:
    def test_input_records_unchanged(self):
        cluster = _three_source_cluster()
        # Deep-copy original state for comparison
        original_fields = [copy.deepcopy(rec.fields) for rec in cluster]
        build_profile(cluster)
        for rec, orig in zip(cluster, original_fields):
            assert rec.fields.keys() == orig.keys()
            for key in orig:
                assert rec.fields[key].raw == orig[key].raw
                assert rec.fields[key].ok == orig[key].ok


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_shuffle_same_candidate_id(self):
        cluster = _three_source_cluster()
        base_id = build_profile(cluster).candidate_id
        for seed in range(5):
            shuffled = cluster[:]
            random.Random(seed).shuffle(shuffled)
            assert build_profile(shuffled).candidate_id == base_id

    def test_shuffle_same_field_values(self):
        cluster = _three_source_cluster()
        base = build_profile(cluster)
        for seed in range(5):
            shuffled = cluster[:]
            random.Random(seed).shuffle(shuffled)
            p = build_profile(shuffled)
            assert p.full_name == base.full_name
            assert set(p.emails) == set(base.emails)
            assert set(p.phones) == set(base.phones)


# ---------------------------------------------------------------------------
# TestSingleSource
# ---------------------------------------------------------------------------

class TestSingleSource:
    def test_single_source_builds_ok(self):
        rec = _make_rec("recruiter_csv", "solo.csv", {
            "full_name": _fv("Solo Person", "Solo Person"),
            "emails":    _fv_list(["solo@example.com"]),
        })
        profile = build_profile([rec])
        assert isinstance(profile, CanonicalProfile)
        assert profile.full_name == "Solo Person"

    def test_single_source_one_sources_seen(self):
        rec = _make_rec("recruiter_csv", "solo.csv", {
            "emails": _fv_list(["solo@example.com"]),
        })
        profile = build_profile([rec])
        assert profile.sources_seen == ["recruiter_csv"]

    def test_single_source_candidate_id_set(self):
        rec = _make_rec("recruiter_csv", "solo.csv", {
            "emails": _fv_list(["solo@example.com"]),
        })
        profile = build_profile([rec])
        assert profile.candidate_id.startswith("cand_")

    def test_adapter_warnings_propagated(self):
        """Warnings from IntermediateRecord.warnings propagate to profile.warnings."""
        rec = _make_rec("recruiter_csv", "w.csv",
                        {"emails": _fv_list(["a@b.com"])},
                        warnings=["bad phone: 12345"])
        profile = build_profile([rec])
        assert any("bad phone" in w for w in profile.warnings)
