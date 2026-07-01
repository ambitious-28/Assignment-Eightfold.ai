"""
Stage 9 — Projection config loader + validator.

Loads a JSON config file and validates its structure before any profiles are projected.
Catching errors here (typos like "skils[].name", bad on_missing values, unknown keys)
gives a clear failure message before any profile work begins.

Public API:
    load_config(path)      → dict (raises ValueError on any problem)
    validate_config(config) → None (raises ValueError on any problem)
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

from transformer.models import CanonicalProfile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_TOP_KEYS = frozenset({"fields", "on_missing", "include_confidence", "include_provenance"})
_VALID_ON_MISSING = frozenset({"null", "omit", "error"})
_VALID_TYPES = frozenset({"string", "string[]", "number", "number[]", "boolean"})
_VALID_FIELD_SPEC_KEYS = frozenset({"path", "from", "type", "required", "normalize"})

# Valid CanonicalProfile field names (computed once at import time)
_CANONICAL_FIELDS: frozenset[str] = frozenset(
    f.name for f in dataclasses.fields(CanonicalProfile)
)

# Path syntax patterns (same as path_resolver.py)
_MAP_RE   = re.compile(r'^([A-Za-z_]\w*)\[\]\.([A-Za-z_]\w*)$')   # skills[].name
_INDEX_RE = re.compile(r'^([A-Za-z_]\w*)\[(\d+)\]$')               # emails[0]
_SIMPLE_RE = re.compile(r'^([A-Za-z_]\w*)$')                        # full_name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(path: str | Path) -> dict:
    """
    Load a projection config from a JSON file, validate it, and return the dict.

    Args:
        path: File path to the JSON config file.

    Returns:
        A validated config dict.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file contains invalid JSON or the config is structurally invalid.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        config = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Config file contains invalid JSON: {exc}") from exc

    validate_config(config)
    return config


def validate_config(config: dict) -> None:
    """
    Validate a config dict.

    Raises ValueError with a descriptive message on the first validation error.
    Does not return a value; raises or completes silently.
    """
    if not isinstance(config, dict):
        raise ValueError("Config must be a JSON object (dict)")

    # Unknown top-level keys
    unknown = set(config.keys()) - _VALID_TOP_KEYS
    if unknown:
        raise ValueError(f"Unknown config keys: {sorted(unknown)}")

    # fields — required, must be a list
    if "fields" not in config:
        raise ValueError("Config missing required key 'fields'")
    if not isinstance(config["fields"], list):
        raise ValueError("'fields' must be a list")

    # on_missing
    if "on_missing" in config:
        om = config["on_missing"]
        if om not in _VALID_ON_MISSING:
            raise ValueError(
                f"'on_missing' must be one of {sorted(_VALID_ON_MISSING)}, got {om!r}"
            )

    # include_confidence / include_provenance
    for bool_key in ("include_confidence", "include_provenance"):
        if bool_key in config and not isinstance(config[bool_key], bool):
            raise ValueError(f"'{bool_key}' must be a boolean, got {type(config[bool_key]).__name__!r}")

    # Validate each field spec
    for i, spec in enumerate(config["fields"]):
        _validate_field_spec(spec, index=i)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_field_spec(spec: Any, index: int) -> None:
    """Validate a single field spec dict. Raises ValueError on any error."""
    prefix = f"fields[{index}]"

    if not isinstance(spec, dict):
        raise ValueError(f"{prefix}: each field spec must be a dict, got {type(spec).__name__!r}")

    # Unknown keys in field spec
    unknown = set(spec.keys()) - _VALID_FIELD_SPEC_KEYS
    if unknown:
        raise ValueError(f"{prefix}: unknown field spec keys: {sorted(unknown)}")

    # path is required
    if "path" not in spec:
        raise ValueError(f"{prefix}: field spec missing required key 'path'")
    if not isinstance(spec["path"], str) or not spec["path"].strip():
        raise ValueError(f"{prefix}: 'path' must be a non-empty string")

    # 'from' if present
    if "from" in spec:
        if not isinstance(spec["from"], str) or not spec["from"].strip():
            raise ValueError(f"{prefix}: 'from' must be a non-empty string")

    # Validate source path (syntactically + field existence)
    source_path = spec.get("from", spec["path"])
    _validate_source_path(source_path, prefix)

    # type
    if "type" in spec:
        if spec["type"] not in _VALID_TYPES:
            raise ValueError(
                f"{prefix}: 'type' must be one of {sorted(_VALID_TYPES)}, got {spec['type']!r}"
            )

    # required
    if "required" in spec and not isinstance(spec["required"], bool):
        raise ValueError(f"{prefix}: 'required' must be a boolean")

    # normalize — just must be a string if present
    if "normalize" in spec and not isinstance(spec["normalize"], str):
        raise ValueError(f"{prefix}: 'normalize' must be a string")


def _validate_source_path(path: str, prefix: str) -> None:
    """
    Validate that 'path' is syntactically valid and references a known CanonicalProfile field.
    """
    # Try map-over pattern first (skills[].name)
    m = _MAP_RE.match(path)
    if m:
        root_field = m.group(1)
        _check_field_exists(root_field, path, prefix)
        return

    # Try indexed pattern (emails[0])
    m = _INDEX_RE.match(path)
    if m:
        root_field = m.group(1)
        _check_field_exists(root_field, path, prefix)
        return

    # Try simple field (full_name)
    m = _SIMPLE_RE.match(path)
    if m:
        root_field = m.group(1)
        _check_field_exists(root_field, path, prefix)
        return

    # Nothing matched → invalid syntax
    raise ValueError(
        f"{prefix}: source path {path!r} has invalid syntax. "
        "Expected one of: 'field', 'field[N]', 'field[].attr'"
    )


def _check_field_exists(field_name: str, path: str, prefix: str) -> None:
    """Raise ValueError if field_name is not a known CanonicalProfile attribute."""
    if field_name not in _CANONICAL_FIELDS:
        raise ValueError(
            f"{prefix}: source path {path!r} references unknown field {field_name!r}. "
            f"Valid fields: {sorted(_CANONICAL_FIELDS)}"
        )
