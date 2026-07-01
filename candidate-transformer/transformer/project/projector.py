"""
Stage 8 — Projector: maps a CanonicalProfile to a JSON-serializable output dict.

Two modes:
  default (no config) — emit all DEFAULT_SCHEMA fields; provenance flattened to
                        {field, source, method} per PRD §2.2.
  config-driven       — only emit fields listed in config["fields"]; apply
                        remapping, on_missing policy, and include_* toggles.

The original CanonicalProfile is NEVER mutated — projection operates on a deep copy.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any

from transformer.models import CanonicalProfile, DEFAULT_SCHEMA
from transformer.project.path_resolver import MISSING, resolve


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def project(
    profile: CanonicalProfile,
    config: dict | None = None,
) -> dict:
    """
    Project a CanonicalProfile to a JSON-serializable output dict.

    Args:
        profile: The canonical record (never mutated).
        config:  Optional projection config dict. If None, emit the full
                 default Eightfold schema.

    Returns:
        A JSON-serializable dict.
    """
    working = copy.deepcopy(profile)

    if config is None:
        return _project_default(working)
    return _project_config(working, config)


# ---------------------------------------------------------------------------
# Default projection (no config)
# ---------------------------------------------------------------------------

def _project_default(profile: CanonicalProfile) -> dict:
    """Emit all DEFAULT_SCHEMA fields; provenance flattened to {field, source, method}."""
    full = dataclasses.asdict(profile)

    # Flatten provenance to Eightfold default schema format
    full["provenance"] = [
        {
            "field":  p["field"],
            "source": p["winner_source"],
            "method": p["method"],
        }
        for p in (full.get("provenance") or [])
    ]

    # Emit fields in DEFAULT_SCHEMA order (drop any internal-only keys)
    return {field: full[field] for field in DEFAULT_SCHEMA if field in full}


# ---------------------------------------------------------------------------
# Config-driven projection
# ---------------------------------------------------------------------------

def _project_config(profile: CanonicalProfile, config: dict) -> dict:
    """Apply config-driven field mapping, on_missing policy, and toggles."""
    on_missing: str = config.get("on_missing", "null")
    include_confidence: bool = bool(config.get("include_confidence", False))
    include_provenance: bool = bool(config.get("include_provenance", False))
    fields_spec: list[dict] = config.get("fields", [])

    out: dict = {}

    for spec in fields_spec:
        output_key: str = spec["path"]
        source_path: str = spec.get("from", spec["path"])

        value = resolve(profile, source_path)

        if value is MISSING:
            if on_missing == "omit":
                continue
            elif on_missing == "error":
                raise ValueError(
                    f"Field {output_key!r} (from {source_path!r}) is missing "
                    "and on_missing is 'error'."
                )
            else:  # "null"
                out[output_key] = None
        else:
            out[output_key] = _serialize(value)

    if include_confidence:
        out["overall_confidence"] = profile.overall_confidence

    if include_provenance:
        out["provenance"] = _enrich_provenance(profile)

    return out


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize(value: Any) -> Any:
    """Recursively convert dataclass instances to dicts for JSON serialization."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


def _enrich_provenance(profile: CanonicalProfile) -> list[dict]:
    """Return full enriched provenance (all ProvenanceEntry fields + contributions)."""
    result = []
    for p in profile.provenance:
        result.append({
            "field":         p.field,
            "final_value":   _serialize(p.final_value),
            "method":        p.method,
            "confidence":    p.confidence,
            "winner_source": p.winner_source,
            "contributions": [
                {
                    "source":     c.source,
                    "raw_value":  c.raw_value,
                    "normalized": c.normalized,
                    "agreed":     c.agreed,
                }
                for c in p.contributions
            ],
        })
    return result
