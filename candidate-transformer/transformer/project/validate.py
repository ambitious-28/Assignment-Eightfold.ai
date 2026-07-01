"""
Stage 9 — Output validator.

Validates a projected output dict against the field declarations in the config.

Two checks:
  1. required=true fields must be present and non-null.
  2. type declarations must match the actual Python type of the value.

Raises ValueError with a descriptive message on the first failure.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_output(output: dict, config: dict) -> None:
    """
    Validate a projected output dict against the config schema.

    Args:
        output: The dict returned by projector.project().
        config: The validated config dict (from config.load_config or config.validate_config).

    Raises:
        ValueError: On the first validation failure, with a descriptive message.
    """
    for spec in config.get("fields", []):
        output_key: str = spec["path"]
        required: bool  = bool(spec.get("required", False))
        type_decl: str | None = spec.get("type")

        value_present = output_key in output
        value = output.get(output_key)

        # --- Required check ---
        if required:
            if not value_present:
                raise ValueError(
                    f"Required field {output_key!r} is missing from projected output."
                )
            if value is None:
                raise ValueError(
                    f"Required field {output_key!r} is null in projected output."
                )

        # --- Type check ---
        if type_decl and value_present and value is not None:
            _check_type(output_key, value, type_decl)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_type(key: str, value: Any, type_decl: str) -> None:
    """Raise ValueError if value does not match the declared type."""
    ok = _matches_type(value, type_decl)
    if not ok:
        actual = type(value).__name__
        raise ValueError(
            f"Field {key!r}: expected type {type_decl!r} but got {actual!r} "
            f"(value={value!r})."
        )


def _matches_type(value: Any, type_decl: str) -> bool:
    """Return True if value matches the declared type string."""
    if type_decl == "string":
        return isinstance(value, str)

    if type_decl == "string[]":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)

    if type_decl == "number":
        # bool is a subclass of int in Python — exclude it explicitly
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    if type_decl == "number[]":
        return (
            isinstance(value, list)
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
        )

    if type_decl == "boolean":
        return isinstance(value, bool)

    # Unknown type_decl — pass through (config validator should have caught this)
    return True
