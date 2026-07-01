"""
Stage 6 checkpoint tests — Confidence Scoring.

Run: pytest tests/test_confidence.py -v
"""

from __future__ import annotations

import pytest

from transformer.adapters.base import FieldValue, IntermediateRecord
from transformer.merge.arbitrate import ArbitrationResult, arbitrate_cluster
from transformer.merge.confidence import (
    CONFIDENCE_THRESHOLD,
    compute_overall_confidence,
    score_arbitration,
    score_field,
    score_skill,
)
from transformer.models import Contribution, SkillEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    winner_source: str,
    contributions: list[Contribution] | None = None,
    conflicted: bool = False,
    winner_value=None,
    method: str = "test",
) -> ArbitrationResult:
    if contributions is None:
        # Default: one contribution — the winner itself (agreed=True)
        contributions = [Contribution(
            source=winner_source,
            raw_value=None,
            normalized=None,
            agreed=True,
        )]
    return ArbitrationResult(
        winner_value=winner_value,
        winner_source=winner_source,
        method=method,
        contributions=contributions,
        conflicted=conflicted,
    )


def _contrib(source: str, agreed: bool) -> Contribution:
    return Contribution(source=source, raw_value=None, normalized=None, agreed=agreed)


# ---------------------------------------------------------------------------
# Formula verification (exact arithmetic)
# ---------------------------------------------------------------------------

class TestFormulaExact:
    def test_csv_ats_agree_phone(self):
        """CSV + ATS both agree → 0.90 + 0.05×(2-1) = 0.95"""
        result = _make_result(
            winner_source="recruiter_csv",
            contributions=[_contrib("recruiter_csv", True), _contrib("ats_blob", True)],
            conflicted=False,
        )
        assert score_field(result) == pytest.approx(0.95)

    def test_ats_winner_conflicted(self):
        """ATS winner, conflicted → 0.85 + 0 - 0.10 = 0.75"""
        result = _make_result(
            winner_source="ats_blob",
            contributions=[_contrib("ats_blob", True), _contrib("resume", False)],
            conflicted=True,
        )
        assert score_field(result) == pytest.approx(0.75)

    def test_notes_only_location(self):
        """recruiter_notes only → 0.50 + 0 - 0 = 0.50"""
        result = _make_result(
            winner_source="recruiter_notes",
            contributions=[_contrib("recruiter_notes", True)],
            conflicted=False,
        )
        assert score_field(result) == pytest.approx(0.50)

    def test_csv_single_source(self):
        """CSV alone → 0.90"""
        result = _make_result(
            winner_source="recruiter_csv",
            contributions=[_contrib("recruiter_csv", True)],
        )
        assert score_field(result) == pytest.approx(0.90)

    def test_resume_single_source(self):
        """resume alone → 0.60"""
        result = _make_result(
            winner_source="resume",
            contributions=[_contrib("resume", True)],
        )
        assert score_field(result) == pytest.approx(0.60)

    def test_three_sources_agree(self):
        """CSV + ATS + resume all agree → 0.90 + 0.05×2 = 1.00"""
        result = _make_result(
            winner_source="recruiter_csv",
            contributions=[
                _contrib("recruiter_csv", True),
                _contrib("ats_blob", True),
                _contrib("resume", True),
            ],
            conflicted=False,
        )
        assert score_field(result) == pytest.approx(1.00)


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------

class TestClamping:
    def test_clamp_upper(self):
        """Many agreeing sources → score capped at 1.0."""
        contributions = [_contrib("recruiter_csv", True)] * 10
        result = _make_result(
            winner_source="recruiter_csv",
            contributions=contributions,
            conflicted=False,
        )
        assert score_field(result) == pytest.approx(1.0)

    def test_clamp_lower(self):
        """An unknown source (tier 0.0) with conflict → max(0.0 - 0.10, 0.0) = 0.0 → dropped."""
        result = _make_result(
            winner_source="unknown_source",  # tier = 0.0
            contributions=[_contrib("unknown_source", True)],
            conflicted=True,
        )
        # 0.0 - 0.10 = -0.10 → clamped to 0.0 → below threshold → None
        assert score_field(result) is None


# ---------------------------------------------------------------------------
# Threshold gate
# ---------------------------------------------------------------------------

class TestThresholdGate:
    def test_exactly_0_40_is_kept(self):
        """notes-only + conflict → 0.50 - 0.10 = 0.40 — exactly at boundary, must be KEPT."""
        result = _make_result(
            winner_source="recruiter_notes",
            contributions=[_contrib("recruiter_notes", True)],
            conflicted=True,
        )
        score = score_field(result)
        assert score is not None
        assert score == pytest.approx(0.40)

    def test_below_threshold_returns_none(self):
        """A value that comes in below 0.40 is dropped (returns None)."""
        # notes (0.50) - 0.10 (conflict) = 0.40, still kept.
        # To get below 0.40 we need an unknown source (0.0) with no conflict.
        result = _make_result(
            winner_source="unknown_source",
            contributions=[_contrib("unknown_source", True)],
            conflicted=False,
        )
        assert score_field(result) is None

    def test_score_arbitration_returns_none_for_dropped(self):
        """score_arbitration sets field to None when confidence is below threshold."""
        arbitration = {
            "full_name": _make_result(
                winner_source="unknown_source",
                contributions=[_contrib("unknown_source", True)],
            ),
        }
        scores, warnings = score_arbitration(arbitration)
        assert scores["full_name"] is None

    def test_score_arbitration_warning_for_dropped(self):
        """A drop must produce exactly one warning mentioning the field name."""
        arbitration = {
            "full_name": _make_result(
                winner_source="unknown_source",
                contributions=[_contrib("unknown_source", True)],
            ),
        }
        _, warnings = score_arbitration(arbitration)
        assert len(warnings) == 1
        assert "full_name" in warnings[0]

    def test_resume_conflict_kept(self):
        """resume (0.60) + conflict → 0.60 - 0.10 = 0.50 — above threshold, kept."""
        result = _make_result(
            winner_source="resume",
            contributions=[_contrib("resume", True), _contrib("ats_blob", False)],
            conflicted=True,
        )
        score = score_field(result)
        assert score is not None
        assert score == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

class TestSkillScoring:
    def test_csv_only_skill(self):
        """Skill from CSV only → 0.90 + 0.05×(1-1) = 0.90"""
        skill = SkillEntry(name="Python", confidence=0.0, sources=["recruiter_csv"])
        assert score_skill(skill) == pytest.approx(0.90)

    def test_csv_and_resume_skill(self):
        """Skill from CSV + resume → best_tier=0.90, agreeing=2 → 0.90 + 0.05 = 0.95"""
        skill = SkillEntry(name="Python", confidence=0.0, sources=["recruiter_csv", "resume"])
        assert score_skill(skill) == pytest.approx(0.95)

    def test_notes_only_skill(self):
        """Skill from notes only → 0.50"""
        skill = SkillEntry(name="SQL", confidence=0.0, sources=["recruiter_notes"])
        assert score_skill(skill) == pytest.approx(0.50)

    def test_three_source_skill(self):
        """CSV + ATS + resume → 0.90 + 0.05×2 = 1.00"""
        skill = SkillEntry(
            name="Python", confidence=0.0,
            sources=["recruiter_csv", "ats_blob", "resume"],
        )
        assert score_skill(skill) == pytest.approx(1.0)

    def test_skill_not_threshold_gated(self):
        """Even a low-confidence skill (unknown source) is kept (not gated)."""
        skill = SkillEntry(name="Cobol", confidence=0.0, sources=["unknown_source"])
        # tier 0.0, not dropped
        result = score_skill(skill)
        assert result == pytest.approx(0.0)  # clamped, but still a float (not None)

    def test_empty_sources_skill(self):
        """No sources → score = 0.0 (clamped)."""
        skill = SkillEntry(name="Go", confidence=0.0, sources=[])
        assert score_skill(skill) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# overall_confidence
# ---------------------------------------------------------------------------

class TestOverallConfidence:
    def test_hand_computed_example(self):
        """
        full_name=0.95 (2×), emails=0.95 (2×), phones=0.95 (2×),
        location=0.50 (1×), headline=0.80 (1×)
        = (0.95*2 + 0.95*2 + 0.95*2 + 0.50*1 + 0.80*1) / (2+2+2+1+1)
        = (1.90 + 1.90 + 1.90 + 0.50 + 0.80) / 8
        = ~6.9999... / 8 = ~0.8749... → rounds to 0.87 (float arithmetic)
        """
        scores = {
            "full_name": 0.95,
            "emails": 0.95,
            "phones": 0.95,
            "location": 0.50,
            "headline": 0.80,
        }
        result = compute_overall_confidence(scores)
        # Verify it is close to 0.875 (exact math) and is rounded to 2dp
        assert abs(result - 0.875) < 0.01
        assert result == round(result, 2)

    def test_dropped_fields_excluded(self):
        """None fields must not affect the mean."""
        scores = {"full_name": 0.90, "location": None}
        # Only full_name counts: weighted sum = 0.90*2 = 1.80, weight = 2 → 0.90
        assert compute_overall_confidence(scores) == pytest.approx(0.90)

    def test_all_none_returns_zero(self):
        """No non-None scores → overall = 0.0."""
        scores = {"full_name": None, "emails": None, "phones": None}
        assert compute_overall_confidence(scores) == 0.0

    def test_empty_dict_returns_zero(self):
        assert compute_overall_confidence({}) == 0.0

    def test_rounded_to_two_decimal_places(self):
        """Result must be rounded to exactly 2 dp."""
        scores = {"headline": 1.0 / 3.0}  # 0.333…
        result = compute_overall_confidence(scores)
        assert result == round(result, 2)
        assert isinstance(result, float)

    def test_identity_fields_get_double_weight(self):
        """full_name at 2× weight vs headline at 1× weight."""
        scores = {"full_name": 1.0, "headline": 0.0}
        # (1.0*2 + 0.0*1) / (2+1) = 2/3 ≈ 0.67
        assert compute_overall_confidence(scores) == pytest.approx(0.67)


# ---------------------------------------------------------------------------
# score_arbitration integration
# ---------------------------------------------------------------------------

class TestScoreArbitration:
    def test_returns_scores_for_all_fields(self):
        arbitration = {
            "full_name": _make_result("recruiter_csv", [_contrib("recruiter_csv", True)]),
            "emails":    _make_result("ats_blob",      [_contrib("ats_blob", True)]),
        }
        scores, _ = score_arbitration(arbitration)
        assert "full_name" in scores
        assert "emails" in scores

    def test_no_dropped_fields_no_warnings(self):
        arbitration = {
            "full_name": _make_result("recruiter_csv", [_contrib("recruiter_csv", True)]),
        }
        _, warnings = score_arbitration(arbitration)
        assert warnings == []

    def test_experience_uses_base_only(self):
        """experience field → base(winner_source) only, no adjustment."""
        arbitration = {
            "experience": _make_result(
                "recruiter_csv",
                contributions=[_contrib("recruiter_csv", True), _contrib("ats_blob", True)],
                conflicted=True,  # ignored for experience
            ),
        }
        scores, _ = score_arbitration(arbitration)
        # Should be 0.90 (base only), not 0.90 - 0.10
        assert scores["experience"] == pytest.approx(0.90)

    def test_education_uses_base_only(self):
        arbitration = {
            "education": _make_result(
                "resume",
                contributions=[_contrib("resume", True)],
                conflicted=True,  # ignored for education
            ),
        }
        scores, _ = score_arbitration(arbitration)
        assert scores["education"] == pytest.approx(0.60)

    def test_skills_field_scores_as_mean(self):
        """skills field score = average of per-skill scores."""
        skill_a = SkillEntry("Python", 0.0, ["recruiter_csv"])       # 0.90
        skill_b = SkillEntry("SQL",    0.0, ["recruiter_notes"])     # 0.50
        arbitration = {
            "skills": ArbitrationResult(
                winner_value=[skill_a, skill_b],
                winner_source="recruiter_csv",
                method="union",
                contributions=[_contrib("recruiter_csv", True), _contrib("recruiter_notes", True)],
                conflicted=False,
            ),
        }
        scores, _ = score_arbitration(arbitration)
        assert scores["skills"] == pytest.approx((0.90 + 0.50) / 2, abs=1e-4)

    def test_empty_skills_returns_none(self):
        arbitration = {
            "skills": ArbitrationResult(
                winner_value=[],
                winner_source="recruiter_csv",
                method="union",
                contributions=[],
                conflicted=False,
            ),
        }
        scores, _ = score_arbitration(arbitration)
        assert scores["skills"] is None


# ---------------------------------------------------------------------------
# Integration: arbitrate_cluster → score_arbitration
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def _fv(self, raw, normalized, method="test", ok=True) -> FieldValue:
        return FieldValue(raw=raw, normalized=normalized, method=method, ok=ok)

    def _rec(self, source: str, fields: dict) -> IntermediateRecord:
        return IntermediateRecord(source=source, source_file="test", fields=fields)

    def test_csv_wins_high_confidence(self):
        """CSV alone on full_name → 0.90."""
        rec = self._rec("recruiter_csv", {
            "full_name": self._fv("Aarav Sharma", "Aarav Sharma"),
        })
        arb = arbitrate_cluster([rec])
        scores, warnings = score_arbitration(arb)
        assert scores["full_name"] == pytest.approx(0.90)
        assert warnings == []

    def test_conflict_reduces_confidence(self):
        """CSV vs resume with different names → conflicted → 0.90 - 0.10 = 0.80."""
        csv = self._rec("recruiter_csv", {
            "full_name": self._fv("Aarav Sharma", "Aarav Sharma"),
        })
        res = self._rec("resume", {
            "full_name": self._fv("A. Sharma", "A. Sharma"),
        })
        arb = arbitrate_cluster([csv, res])
        scores, _ = score_arbitration(arb)
        assert scores["full_name"] == pytest.approx(0.80)

    def test_agreement_boosts_confidence(self):
        """CSV + ATS agree on full_name → 0.90 + 0.05 = 0.95."""
        csv = self._rec("recruiter_csv", {
            "full_name": self._fv("Aarav Sharma", "Aarav Sharma"),
        })
        ats = self._rec("ats_blob", {
            "full_name": self._fv("Aarav Sharma", "Aarav Sharma"),
        })
        arb = arbitrate_cluster([csv, ats])
        scores, _ = score_arbitration(arb)
        assert scores["full_name"] == pytest.approx(0.95)
