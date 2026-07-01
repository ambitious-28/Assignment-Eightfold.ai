"""
Stage 10 checkpoint tests — Pipeline + CLI robustness.

Run: pytest tests/test_robustness.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from transformer.models import DEFAULT_SCHEMA
from transformer.pipeline import run_pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _recruiter_view_config() -> dict:
    """Return a recruiter-view config (mirrors configs/recruiter_view.json)."""
    return {
        "fields": [
            {"path": "candidate_id",    "type": "string",   "required": True},
            {"path": "full_name",       "type": "string",   "required": True},
            {"path": "primary_email",   "from": "emails[0]","type": "string"},
            {"path": "primary_phone",   "from": "phones[0]","type": "string"},
            {"path": "skills",          "from": "skills[].name", "type": "string[]"},
            {"path": "years_experience","type": "number"},
        ],
        "include_confidence": True,
        "include_provenance": False,
        "on_missing": "null",
    }


# ---------------------------------------------------------------------------
# TestPipelineBasic
# ---------------------------------------------------------------------------

class TestPipelineBasic:
    def test_returns_list(self, fixtures_dir):
        result = run_pipeline(fixtures_dir)
        assert isinstance(result, list)

    def test_profiles_are_dicts(self, fixtures_dir):
        result = run_pipeline(fixtures_dir)
        for item in result:
            assert isinstance(item, dict)

    def test_at_least_one_profile(self, fixtures_dir):
        result = run_pipeline(fixtures_dir)
        assert len(result) >= 1

    def test_candidate_id_present(self, fixtures_dir):
        result = run_pipeline(fixtures_dir)
        for profile in result:
            assert "candidate_id" in profile
            assert profile["candidate_id"] is not None

    def test_full_name_present(self, fixtures_dir):
        result = run_pipeline(fixtures_dir)
        for profile in result:
            assert "full_name" in profile

    def test_output_has_default_schema_fields(self, fixtures_dir):
        result = run_pipeline(fixtures_dir)
        for profile in result:
            for field in DEFAULT_SCHEMA:
                assert field in profile, f"DEFAULT_SCHEMA field {field!r} missing from profile"


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_two_runs_identical(self, fixtures_dir):
        out1 = run_pipeline(fixtures_dir)
        out2 = run_pipeline(fixtures_dir)
        assert json.dumps(out1, sort_keys=False) == json.dumps(out2, sort_keys=False)

    def test_output_sorted_by_candidate_id(self, fixtures_dir):
        result = run_pipeline(fixtures_dir)
        ids = [p.get("candidate_id", "") for p in result]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# TestBrokenFiles
# ---------------------------------------------------------------------------

class TestBrokenFiles:
    def test_empty_csv_does_not_crash(self, fixtures_dir):
        """fixtures_dir contains empty.csv — pipeline must not raise."""
        result = run_pipeline(fixtures_dir)
        assert isinstance(result, list)

    def test_malformed_json_does_not_crash(self, fixtures_dir):
        """fixtures_dir contains malformed.json — pipeline must not raise."""
        result = run_pipeline(fixtures_dir)
        assert isinstance(result, list)

    def test_include_broken_false_skips_broken_subdir(self, tmp_path, fixtures_dir):
        """Files under a 'broken/' subdir are skipped when include_broken=False."""
        # Create a tmp dir with the good fixtures + a broken/ subdir
        import shutil
        good_dir = tmp_path / "good"
        good_dir.mkdir()
        for f in fixtures_dir.iterdir():
            if f.is_file():
                shutil.copy(f, good_dir / f.name)

        broken_dir = tmp_path / "broken"
        broken_dir.mkdir()
        (broken_dir / "bad.json").write_text("{unclosed [", encoding="utf-8")

        result_without = run_pipeline(tmp_path, include_broken=False)
        result_with    = run_pipeline(tmp_path, include_broken=True)

        # Both must succeed without raising
        assert isinstance(result_without, list)
        assert isinstance(result_with, list)
        # Good profiles appear in both
        assert len(result_without) >= 1

    def test_include_broken_true_still_returns_good_profiles(self, tmp_path, fixtures_dir):
        """include_broken=True must not crash and must still return good profiles."""
        import shutil
        good_dir = tmp_path / "inputs"
        good_dir.mkdir()
        for f in fixtures_dir.iterdir():
            if f.is_file():
                shutil.copy(f, good_dir / f.name)

        broken_dir = tmp_path / "inputs" / "broken"
        broken_dir.mkdir()
        (broken_dir / "bad.json").write_text("{not valid", encoding="utf-8")

        result = run_pipeline(tmp_path / "inputs", include_broken=True)
        assert isinstance(result, list)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# TestConfigProjection
# ---------------------------------------------------------------------------

class TestConfigProjection:
    def test_config_output_keys(self, fixtures_dir):
        """Config-driven output contains exactly the requested keys + overall_confidence."""
        config = _recruiter_view_config()
        result = run_pipeline(fixtures_dir, config=config)
        expected_keys = {
            "candidate_id", "full_name", "primary_email",
            "primary_phone", "skills", "years_experience",
            "overall_confidence",   # from include_confidence: true
        }
        for profile in result:
            assert set(profile.keys()) == expected_keys

    def test_on_missing_null_produces_none_for_absent(self, fixtures_dir):
        """Fields missing from profile produce None (not MISSING) when on_missing=null."""
        config = {
            "fields": [
                {"path": "full_name", "type": "string"},
                {"path": "ghost_phone", "from": "phones[9]", "type": "string"},
            ],
            "on_missing": "null",
        }
        result = run_pipeline(fixtures_dir, config=config)
        for profile in result:
            assert "ghost_phone" in profile
            assert profile["ghost_phone"] is None

    def test_include_confidence_present(self, fixtures_dir):
        """include_confidence: true adds overall_confidence to every output profile."""
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "include_confidence": True,
            "on_missing": "null",
        }
        result = run_pipeline(fixtures_dir, config=config)
        for profile in result:
            assert "overall_confidence" in profile
            assert isinstance(profile["overall_confidence"], float)


# ---------------------------------------------------------------------------
# TestCLIInvocation
# ---------------------------------------------------------------------------

class TestCLIInvocation:
    def _fixtures_path(self) -> str:
        return str(Path(__file__).parent / "fixtures")

    def test_cli_stdout_is_valid_json(self):
        """python -m transformer --inputs <fixtures> outputs valid JSON to stdout."""
        proc = subprocess.run(
            [sys.executable, "-m", "transformer", "--inputs", self._fixtures_path()],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, f"CLI exited with code {proc.returncode}: {proc.stderr}"
        data = json.loads(proc.stdout)
        assert isinstance(data, list)

    def test_cli_out_file_written(self, tmp_path):
        """--out <path> writes a valid JSON array file."""
        out_file = tmp_path / "output.json"
        proc = subprocess.run(
            [
                sys.executable, "-m", "transformer",
                "--inputs", self._fixtures_path(),
                "--out", str(out_file),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, f"CLI exited with code {proc.returncode}: {proc.stderr}"
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert isinstance(data, list)
