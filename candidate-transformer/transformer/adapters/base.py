"""
Adapter interface and IntermediateRecord definition.

IntermediateRecord is the common currency between adapters and the merge stage.
Every field carries both its raw value (for provenance) and its normalized value
(for matching/arbitration), plus metadata about the normalization.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FieldValue:
    """
    A single field's contribution from one source.

    raw       — the value exactly as it appeared in the source file.
    normalized — post-normalization result (None if failed / field absent).
    method    — description of the normalization applied.
    ok        — False means normalization failed; caller emits null + warning.
    """
    raw: Any
    normalized: Any
    method: str
    ok: bool


@dataclass
class IntermediateRecord:
    """
    One candidate's data from one source file, mapped to canonical field names.

    source      — "recruiter_csv" | "ats_blob" | "resume" | "recruiter_notes"
    source_file — absolute path to the originating file
    fields      — canonical_field_name → FieldValue
    warnings    — parse/normalization failures encountered for this record

    Supported field keys:
        full_name, emails, phones, location, links, headline,
        years_experience, skills, experience, education
    """
    source: str
    source_file: str
    fields: dict[str, FieldValue] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class SourceAdapter(ABC):
    """
    Abstract base for all source adapters.

    Implementations must:
    - Never raise from read() — catch all exceptions, add warnings, return partial list.
    - Never invent values — missing/unparseable fields are absent from record.fields.
    - Store raw_value exactly as it appeared in the source.
    """

    @abstractmethod
    def can_handle(self, path: Path) -> bool:
        """Return True if this adapter handles the given file path."""
        ...

    @abstractmethod
    def read(self, path: Path) -> list[IntermediateRecord]:
        """
        Read the file at path and return a list of IntermediateRecords.

        Must never raise. On any error, add a warning and return what was
        successfully parsed (may be empty list).
        """
        ...
