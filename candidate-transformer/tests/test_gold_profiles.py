"""
Stage 11 checkpoint tests — Gold profile comparison.

Run: pytest tests/test_gold_profiles.py -v

Tests:
  1. Pipeline on samples/ produces the right number of profiles
  2. Over-merge guard: Priya Sharma A and B are separate profiles
  3. Gold profile comparison (exact field values)
  4. Edge-case assertions (garbage values, alias map, union fields)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transformer.pipeline import run_pipeline

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
GOLD_DIR    = Path(__file__).parent.parent / "gold"


# ---------------------------------------------------------------------------
# Module-level fixture: run pipeline once, index by candidate_id
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pipeline_output() -> dict[str, dict]:
    """Run pipeline on samples/ (no broken), return dict[candidate_id → profile]."""
    profiles = run_pipeline(SAMPLES_DIR, include_broken=False)
    return {p["candidate_id"]: p for p in profiles}


@pytest.fixture(scope="module")
def all_profiles_list() -> list[dict]:
    """Raw sorted list from pipeline (preserves order for count checks)."""
    return run_pipeline(SAMPLES_DIR, include_broken=False)


def _load_gold(filename: str) -> dict:
    return json.loads((GOLD_DIR / filename).read_text(encoding="utf-8"))


def _profile_by_email(pipeline_output: dict, email: str) -> dict | None:
    for p in pipeline_output.values():
        if email in p.get("emails", []):
            return p
    return None


# ---------------------------------------------------------------------------
# TestProfileCount
# ---------------------------------------------------------------------------

class TestProfileCount:
    def test_total_profiles(self, all_profiles_list):
        """14 named candidates; the bad ATS entry is skipped (not a profile)."""
        assert len(all_profiles_list) == 14

    def test_named_profiles_count(self, all_profiles_list):
        """Exactly 14 profiles with a non-null full_name."""
        named = [p for p in all_profiles_list if p.get("full_name")]
        assert len(named) == 14

    def test_aarav_dedup_appears_once(self, pipeline_output):
        """Aarav has 2 CSV rows with same email → must appear as exactly 1 profile."""
        aarav_profiles = [
            p for p in pipeline_output.values()
            if "aarav.sharma@example.com" in p.get("emails", [])
        ]
        assert len(aarav_profiles) == 1


# ---------------------------------------------------------------------------
# TestOverMergeGuard  (PRD critical test)
# ---------------------------------------------------------------------------

class TestOverMergeGuard:
    def test_priya_a_and_b_are_separate(self, pipeline_output):
        """Priya Sharma A and B share only a name — must remain as 2 distinct clusters."""
        priya_profiles = [
            p for p in pipeline_output.values()
            if p.get("full_name") == "Priya Sharma"
        ]
        assert len(priya_profiles) == 2, (
            f"Expected 2 Priya Sharma profiles, got {len(priya_profiles)}"
        )

    def test_priya_a_has_correct_email(self, pipeline_output):
        p = _profile_by_email(pipeline_output, "priya.a@sharma.example.com")
        assert p is not None
        assert p["full_name"] == "Priya Sharma"

    def test_priya_b_has_correct_email(self, pipeline_output):
        p = _profile_by_email(pipeline_output, "priya.b@sharma.example.com")
        assert p is not None
        assert p["full_name"] == "Priya Sharma"

    def test_priya_a_and_b_have_different_ids(self, pipeline_output):
        pa = _profile_by_email(pipeline_output, "priya.a@sharma.example.com")
        pb = _profile_by_email(pipeline_output, "priya.b@sharma.example.com")
        assert pa is not None and pb is not None
        assert pa["candidate_id"] != pb["candidate_id"]


# ---------------------------------------------------------------------------
# TestGoldProfiles — exact field comparison
# ---------------------------------------------------------------------------

class TestGoldProfiles:
    def _compare(self, actual: dict, gold: dict, fields: list[str]) -> None:
        for field in fields:
            assert actual.get(field) == gold.get(field), (
                f"Field {field!r}: got {actual.get(field)!r}, expected {gold.get(field)!r}"
            )

    def test_aarav_sharma_matches_gold(self, pipeline_output):
        gold = _load_gold("aarav_sharma.json")
        actual = pipeline_output.get(gold["candidate_id"])
        assert actual is not None, "Aarav Sharma not found in pipeline output"
        self._compare(actual, gold, [
            "candidate_id", "full_name", "emails", "phones",
            "overall_confidence", "years_experience",
        ])
        # Skills must be identical set
        assert sorted(s["name"] for s in actual["skills"]) == sorted(
            s["name"] for s in gold["skills"]
        )

    def test_vivaan_reddy_matches_gold(self, pipeline_output):
        gold = _load_gold("vivaan_reddy.json")
        actual = pipeline_output.get(gold["candidate_id"])
        assert actual is not None, "Vivaan Reddy not found in pipeline output"
        self._compare(actual, gold, [
            "candidate_id", "full_name", "emails",
            "overall_confidence", "years_experience",
        ])

    def test_priya_a_matches_gold(self, pipeline_output):
        gold = _load_gold("priya_sharma_a.json")
        actual = pipeline_output.get(gold["candidate_id"])
        assert actual is not None, "Priya Sharma A not found in pipeline output"
        self._compare(actual, gold, [
            "candidate_id", "full_name", "emails", "phones",
            "overall_confidence",
        ])

    def test_priya_b_matches_gold(self, pipeline_output):
        gold = _load_gold("priya_sharma_b.json")
        actual = pipeline_output.get(gold["candidate_id"])
        assert actual is not None, "Priya Sharma B not found in pipeline output"
        self._compare(actual, gold, [
            "candidate_id", "full_name", "emails", "phones",
            "overall_confidence",
        ])


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_vivaan_has_null_years_experience(self, pipeline_output):
        """ATS `yearsExp:'lots'` → unparseable → years_experience must be null."""
        p = _profile_by_email(pipeline_output, "vivaan.reddy@example.com")
        assert p is not None
        assert p["years_experience"] is None

    def test_vivaan_has_warnings(self, pipeline_output):
        """Bad phone and bad yearsExp from ATS must produce warnings."""
        p = _profile_by_email(pipeline_output, "vivaan.reddy@example.com")
        assert p is not None
        assert len(p["warnings"]) > 0

    def test_ishaan_k8s_normalized_to_kubernetes(self, pipeline_output):
        """Resume lists 'k8s' — alias map must normalise to 'Kubernetes'."""
        p = _profile_by_email(pipeline_output, "ishaan.verma@example.com")
        assert p is not None
        skill_names = [s["name"] for s in p.get("skills", [])]
        assert "Kubernetes" in skill_names, f"Expected 'Kubernetes' in {skill_names}"
        assert "k8s" not in skill_names

    def test_saanvi_has_both_phones_unioned(self, pipeline_output):
        """Phone conflict between CSV and ATS → both phones appear in union."""
        p = _profile_by_email(pipeline_output, "saanvi.gupta@example.com")
        assert p is not None
        phones = p.get("phones", [])
        assert len(phones) == 2
        assert "+919876511100" in phones
        assert "+919876599900" in phones

    def test_meera_has_both_emails_unioned(self, pipeline_output):
        """Email conflict between CSV and ATS → both emails appear (union)."""
        # Meera merges via phone; both emails are collected
        p = _profile_by_email(pipeline_output, "meera.joshi@personal.com")
        assert p is not None
        emails = p.get("emails", [])
        assert len(emails) == 2
        assert "meera.joshi@personal.com" in emails
        assert "meera.work@fintechco.com" in emails

    def test_kabir_notes_only_low_confidence(self, pipeline_output):
        """Notes-only candidate (recruiter_notes base=0.50) has low overall_confidence."""
        p = _profile_by_email(pipeline_output, "kabir.singh@example.com")
        assert p is not None
        assert p["overall_confidence"] <= 0.60

    def test_aarav_has_four_sources(self, pipeline_output):
        """Hero candidate has data from all 4 source types."""
        p = _profile_by_email(pipeline_output, "aarav.sharma@example.com")
        assert p is not None
        assert len(p["sources_seen"]) == 4

    def test_bad_ats_entry_does_not_produce_profile(self, pipeline_output):
        """The 'not a dict' ATS entry is a non-viable cluster — no ghost profile emitted."""
        null_profiles = [
            p for p in pipeline_output.values()
            if p.get("full_name") is None
        ]
        assert len(null_profiles) == 0

    def test_determinism(self):
        """Two runs on samples/ produce byte-identical JSON."""
        run1 = run_pipeline(SAMPLES_DIR, include_broken=False)
        run2 = run_pipeline(SAMPLES_DIR, include_broken=False)
        assert json.dumps(run1) == json.dumps(run2)

    def test_include_broken_does_not_crash(self):
        """include_broken=True: broken files processed gracefully, good profiles preserved."""
        result = run_pipeline(SAMPLES_DIR, include_broken=True)
        named = [p for p in result if p.get("full_name")]
        assert len(named) == 14
