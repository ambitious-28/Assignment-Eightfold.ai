"""
Stage 9 checkpoint tests — Config + Output Validation.

Run: pytest tests/test_validation.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transformer.project.config import load_config, validate_config
from transformer.project.validate import validate_output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _good_config(**overrides) -> dict:
    """Return a minimal valid config, with optional key overrides."""
    base = {"fields": [], "on_missing": "null"}
    base.update(overrides)
    return base


def _field(path: str, **extra) -> dict:
    """Build a field spec dict."""
    return {"path": path, **extra}


# ---------------------------------------------------------------------------
# TestConfigValidation — good configs
# ---------------------------------------------------------------------------

class TestConfigValidationGood:
    def test_minimal_config_loads(self):
        validate_config({"fields": [], "on_missing": "null"})  # must not raise

    def test_empty_fields_no_on_missing(self):
        validate_config({"fields": []})  # on_missing defaults are fine

    def test_full_config_with_all_keys(self):
        config = {
            "fields": [
                {"path": "full_name", "type": "string", "required": True},
                {"path": "email", "from": "emails[0]", "type": "string"},
                {"path": "skills", "from": "skills[].name", "type": "string[]",
                 "normalize": "canonical"},
            ],
            "include_confidence": True,
            "include_provenance": False,
            "on_missing": "null",
        }
        validate_config(config)  # must not raise

    def test_on_missing_null_valid(self):
        validate_config(_good_config(on_missing="null"))

    def test_on_missing_omit_valid(self):
        validate_config(_good_config(on_missing="omit"))

    def test_on_missing_error_valid(self):
        validate_config(_good_config(on_missing="error"))

    def test_fields_with_from_remap_valid(self):
        validate_config({
            "fields": [{"path": "email", "from": "emails[0]", "type": "string"}],
        })

    def test_map_over_path_valid(self):
        validate_config({
            "fields": [{"path": "skills", "from": "skills[].name", "type": "string[]"}],
        })

    def test_indexed_path_valid(self):
        validate_config({
            "fields": [{"path": "phone", "from": "phones[0]", "type": "string"}],
        })

    def test_include_confidence_true(self):
        validate_config(_good_config(include_confidence=True))

    def test_include_provenance_false(self):
        validate_config(_good_config(include_provenance=False))

    def test_required_bool_valid(self):
        validate_config({
            "fields": [{"path": "full_name", "type": "string", "required": True}],
        })

    def test_normalize_string_valid(self):
        validate_config({
            "fields": [{"path": "phone", "from": "phones[0]", "normalize": "E164"}],
        })


# ---------------------------------------------------------------------------
# TestConfigValidation — bad configs
# ---------------------------------------------------------------------------

class TestConfigValidationBad:
    def test_bad_path_typo_skils(self):
        """PRD test: skils[].name → clear error (field not on CanonicalProfile)."""
        with pytest.raises(ValueError, match="skils"):
            validate_config({
                "fields": [{"path": "skills", "from": "skils[].name"}],
            })

    def test_bad_on_missing_value(self):
        with pytest.raises(ValueError, match="on_missing"):
            validate_config(_good_config(on_missing="throw"))

    def test_unknown_top_level_key(self):
        with pytest.raises(ValueError, match="[Uu]nknown"):
            validate_config({"fields": [], "unknown_key": 1})

    def test_unknown_field_spec_key(self):
        with pytest.raises(ValueError, match="[Uu]nknown"):
            validate_config({
                "fields": [{"path": "full_name", "type": "string", "bogus": 1}],
            })

    def test_missing_fields_key(self):
        with pytest.raises(ValueError, match="fields"):
            validate_config({"on_missing": "null"})

    def test_fields_not_a_list(self):
        with pytest.raises(ValueError, match="list"):
            validate_config({"fields": "not a list"})

    def test_field_spec_missing_path(self):
        with pytest.raises(ValueError, match="path"):
            validate_config({"fields": [{"type": "string"}]})

    def test_invalid_type_value(self):
        with pytest.raises(ValueError, match="type"):
            validate_config({
                "fields": [{"path": "full_name", "type": "blob"}],
            })

    def test_include_confidence_not_bool(self):
        with pytest.raises(ValueError, match="include_confidence"):
            validate_config(_good_config(include_confidence="yes"))

    def test_include_provenance_not_bool(self):
        with pytest.raises(ValueError, match="include_provenance"):
            validate_config(_good_config(include_provenance=1))

    def test_required_not_bool(self):
        with pytest.raises(ValueError, match="required"):
            validate_config({
                "fields": [{"path": "full_name", "required": "yes"}],
            })

    def test_nonexistent_top_level_field(self):
        """Simple path referencing a field that doesn't exist on CanonicalProfile."""
        with pytest.raises(ValueError, match="nonexistent"):
            validate_config({
                "fields": [{"path": "nonexistent", "type": "string"}],
            })

    def test_config_not_a_dict(self):
        with pytest.raises(ValueError):
            validate_config(["not", "a", "dict"])

    def test_field_spec_not_a_dict(self):
        with pytest.raises(ValueError):
            validate_config({"fields": ["not a dict"]})

    def test_path_empty_string(self):
        with pytest.raises(ValueError, match="path"):
            validate_config({"fields": [{"path": ""}]})

    def test_from_empty_string(self):
        with pytest.raises(ValueError, match="from"):
            validate_config({"fields": [{"path": "full_name", "from": ""}]})


# ---------------------------------------------------------------------------
# TestLoadConfig (file I/O)
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_load_valid_config_file(self, tmp_path):
        cfg = {"fields": [{"path": "full_name", "type": "string"}], "on_missing": "null"}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        result = load_config(p)
        assert result["on_missing"] == "null"
        assert len(result["fields"]) == 1

    def test_load_missing_file(self, tmp_path):
        with pytest.raises((ValueError, FileNotFoundError)):
            load_config(tmp_path / "nonexistent.json")

    def test_load_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="[Jj][Ss][Oo][Nn]"):
            load_config(p)

    def test_load_returns_dict(self, tmp_path):
        cfg = {"fields": [], "on_missing": "omit"}
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        result = load_config(p)
        assert isinstance(result, dict)

    def test_load_accepts_path_object(self, tmp_path):
        cfg = {"fields": []}
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        load_config(Path(p))  # must not raise

    def test_load_accepts_string_path(self, tmp_path):
        cfg = {"fields": []}
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        load_config(str(p))  # must not raise


# ---------------------------------------------------------------------------
# TestOutputValidation — passing cases
# ---------------------------------------------------------------------------

class TestOutputValidationPassing:
    def test_required_field_present_and_non_null(self):
        output = {"full_name": "Aarav Sharma"}
        config = {"fields": [{"path": "full_name", "type": "string", "required": True}]}
        validate_output(output, config)  # must not raise

    def test_optional_field_absent_ok(self):
        """Non-required field absent from output → no error."""
        output = {"full_name": "Alice"}
        config = {"fields": [
            {"path": "full_name", "type": "string"},
            {"path": "phone", "type": "string"},  # not required, not in output
        ]}
        validate_output(output, config)

    def test_type_string_valid(self):
        output = {"name": "Alice"}
        config = {"fields": [{"path": "name", "type": "string"}]}
        validate_output(output, config)

    def test_type_string_list_valid(self):
        output = {"skills": ["Python", "Docker"]}
        config = {"fields": [{"path": "skills", "type": "string[]"}]}
        validate_output(output, config)

    def test_type_number_valid(self):
        output = {"years": 5.0}
        config = {"fields": [{"path": "years", "type": "number"}]}
        validate_output(output, config)

    def test_type_number_int_valid(self):
        output = {"years": 5}
        config = {"fields": [{"path": "years", "type": "number"}]}
        validate_output(output, config)

    def test_type_boolean_valid(self):
        output = {"active": True}
        config = {"fields": [{"path": "active", "type": "boolean"}]}
        validate_output(output, config)

    def test_null_field_not_required_passes(self):
        """A null value on a non-required field should not fail type check."""
        output = {"name": None}
        config = {"fields": [{"path": "name", "type": "string"}]}
        validate_output(output, config)  # must not raise

    def test_empty_config_fields_passes(self):
        validate_output({"anything": "here"}, {"fields": []})


# ---------------------------------------------------------------------------
# TestOutputValidation — failures (PRD requirements)
# ---------------------------------------------------------------------------

class TestOutputValidationFailing:
    def test_required_field_missing(self):
        """PRD: Missing required field with on_missing:error → validation fails loudly."""
        output = {}
        config = {"fields": [{"path": "full_name", "type": "string", "required": True}]}
        with pytest.raises(ValueError, match="full_name"):
            validate_output(output, config)

    def test_required_field_null(self):
        """Required field present but null → fails."""
        output = {"full_name": None}
        config = {"fields": [{"path": "full_name", "type": "string", "required": True}]}
        with pytest.raises(ValueError, match="full_name"):
            validate_output(output, config)

    def test_type_mismatch_string_list_expected_got_scalar(self):
        """PRD: type mismatch — string[] expected, scalar given → fails."""
        output = {"skills": "Python"}   # scalar, not list
        config = {"fields": [{"path": "skills", "type": "string[]"}]}
        with pytest.raises(ValueError, match="skills"):
            validate_output(output, config)

    def test_type_mismatch_string_expected_got_list(self):
        """string expected, list given → fails."""
        output = {"name": ["Alice", "Bob"]}
        config = {"fields": [{"path": "name", "type": "string"}]}
        with pytest.raises(ValueError, match="name"):
            validate_output(output, config)

    def test_type_mismatch_number_expected_got_string(self):
        """PRD: type mismatch — number expected, string given → fails."""
        output = {"years": "five"}
        config = {"fields": [{"path": "years", "type": "number"}]}
        with pytest.raises(ValueError, match="years"):
            validate_output(output, config)

    def test_type_mismatch_boolean_expected_got_int(self):
        """boolean expected, int given → fails (bool is not int here)."""
        output = {"active": 1}   # 1 is int, not bool
        config = {"fields": [{"path": "active", "type": "boolean"}]}
        with pytest.raises(ValueError, match="active"):
            validate_output(output, config)

    def test_type_mismatch_string_list_items_not_strings(self):
        """string[] but items are not strings → fails."""
        output = {"values": [1, 2, 3]}
        config = {"fields": [{"path": "values", "type": "string[]"}]}
        with pytest.raises(ValueError, match="values"):
            validate_output(output, config)
