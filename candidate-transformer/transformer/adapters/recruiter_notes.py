"""
Recruiter notes adapter — free text .txt. One file = one person.

Extracts: emails, phones, location, skills, name (heuristic).
Lowest-reliability source; base confidence 0.50.
"""

from __future__ import annotations

import re
from pathlib import Path

import phonenumbers

from transformer.adapters.base import FieldValue, IntermediateRecord, SourceAdapter
from transformer.models import Location, SkillEntry
from transformer.normalize.emails import normalize_emails
from transformer.normalize.location import normalize_location_phrase
from transformer.normalize.names import normalize_name
from transformer.normalize.phones import normalize_phone
from transformer.normalize.skills import SKILL_ALIASES, normalize_skill

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_LOCATION_PREFIX_RE = re.compile(
    r"(?:location|based in|address|city|residing at|from)\s*[:\-]?\s*(.+)", re.IGNORECASE
)
_SKILLS_PREFIX_RE = re.compile(r"skills?\s*[:\-]\s*(.+)", re.IGNORECASE)
_NAME_PREFIX_RE = re.compile(r"(?:candidate|name)\s*[:\-]\s*(.+)", re.IGNORECASE)
_NAME_BLACKLIST_RE = re.compile(r"[@\d/\\|]|https?://|www\.", re.IGNORECASE)


class RecruiterNotesAdapter(SourceAdapter):

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".txt"

    def read(self, path: Path) -> list[IntermediateRecord]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return [IntermediateRecord(
                source="recruiter_notes",
                source_file=str(path),
                warnings=[f"Cannot read {path.name}: {exc}"],
            )]

        warnings: list[str] = []
        fields: dict[str, FieldValue] = {}
        lines = text.splitlines()

        self._extract_emails(text, fields, warnings)
        self._extract_phones(text, fields, warnings)
        self._extract_name(lines, fields, warnings)
        self._extract_location(lines, fields, warnings)
        self._extract_skills(text, lines, fields, warnings)

        return [IntermediateRecord(
            source="recruiter_notes",
            source_file=str(path),
            fields=fields,
            warnings=warnings,
        )]

    # -----------------------------------------------------------------------

    def _extract_emails(self, text: str, fields: dict, warnings: list) -> None:
        raw_emails = _EMAIL_RE.findall(text)
        normed = normalize_emails(raw_emails)
        if normed:
            fields["emails"] = FieldValue(
                raw=raw_emails, normalized=normed, method="email_lowercased", ok=True
            )

    def _extract_phones(self, text: str, fields: dict, warnings: list) -> None:
        phones: list[str] = []
        raw_phones: list[str] = []
        for match in phonenumbers.PhoneNumberMatcher(text, "IN"):
            raw = match.raw_string
            norm, _, ok = normalize_phone(raw)
            if ok and norm and norm not in phones:
                phones.append(norm)
                raw_phones.append(raw)
        if phones:
            fields["phones"] = FieldValue(
                raw=raw_phones, normalized=phones, method="e164_normalized", ok=True
            )

    def _extract_name(self, lines: list[str], fields: dict, warnings: list) -> None:
        # 1. Explicit "Candidate: Name" or "Name: Name" prefix
        for line in lines:
            m = _NAME_PREFIX_RE.match(line.strip())
            if m:
                raw = m.group(1).strip()
                norm, method, ok = normalize_name(raw)
                if ok:
                    fields["full_name"] = FieldValue(raw=raw, normalized=norm, method=method, ok=ok)
                    return

        # 2. Heuristic: first non-empty line with ≤5 words, all caps start, no email/digit/URL
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _NAME_BLACKLIST_RE.search(stripped):
                continue
            words = stripped.split()
            if 1 <= len(words) <= 5 and stripped[0].isupper():
                norm, method, ok = normalize_name(stripped)
                if ok:
                    fields["full_name"] = FieldValue(raw=stripped, normalized=norm, method=method, ok=ok)
                    return

    def _extract_location(self, lines: list[str], fields: dict, warnings: list) -> None:
        for line in lines:
            stripped = line.strip()

            # Explicit prefix
            m = _LOCATION_PREFIX_RE.match(stripped)
            if m:
                loc_text = m.group(1).strip()
                loc_dict = normalize_location_phrase(loc_text)
                if any(v for v in loc_dict.values()):
                    fields["location"] = FieldValue(
                        raw=loc_text,
                        normalized=Location(**loc_dict),
                        method="location_phrase_parsed",
                        ok=True,
                    )
                    return

        # Fallback: any line with comma that looks like "City, Country"
        for line in lines:
            stripped = line.strip()
            if "," in stripped and not _EMAIL_RE.search(stripped):
                loc_dict = normalize_location_phrase(stripped)
                if any(v for v in loc_dict.values()):
                    fields["location"] = FieldValue(
                        raw=stripped,
                        normalized=Location(**loc_dict),
                        method="location_phrase_parsed",
                        ok=True,
                    )
                    return

    def _extract_skills(self, text: str, lines: list[str], fields: dict, warnings: list) -> None:
        seen: set[str] = set()
        skill_entries: list[SkillEntry] = []
        raw_list: list[str] = []

        # 1. Explicit "Skills: ..." line
        for line in lines:
            m = _SKILLS_PREFIX_RE.match(line.strip())
            if m:
                tokens = re.split(r"[,|•\-]+", m.group(1))
                for token in tokens:
                    token = token.strip()
                    if not token:
                        continue
                    norm, method, ok = normalize_skill(token)
                    if ok and norm and norm.lower() not in seen:
                        seen.add(norm.lower())
                        skill_entries.append(SkillEntry(name=norm, confidence=0.0, sources=[]))
                        raw_list.append(token)

        # 2. Scan all text for known alias matches (only alias_mapped, not passthrough)
        # — prevents free-text words from being misidentified as skills.
        # Sort by descending alias length so longer aliases (e.g. "spring boot") are matched
        # and masked before shorter sub-aliases (e.g. "spring") can fire.
        all_text_lower = text.lower()
        masked = list(all_text_lower)  # mutable char list; matched spans replaced with spaces
        for alias_key, canonical_name in sorted(
            SKILL_ALIASES.items(), key=lambda kv: -len(kv[0])
        ):
            pattern = r"\b" + re.escape(alias_key) + r"\b"
            masked_str = "".join(masked)
            m = re.search(pattern, masked_str)
            if m:
                # Always mask the matched span — even if already in seen (e.g. added by
                # the Skills: prefix in step 1) so shorter sub-aliases cannot fire on the
                # same text region (e.g. "spring" must not match inside "spring boot").
                for i in range(m.start(), m.end()):
                    masked[i] = " "
                if canonical_name.lower() not in seen:
                    seen.add(canonical_name.lower())
                    skill_entries.append(SkillEntry(name=canonical_name, confidence=0.0, sources=[]))
                    raw_list.append(alias_key)

        if skill_entries:
            fields["skills"] = FieldValue(
                raw=raw_list, normalized=skill_entries, method="skill_notes_extracted", ok=True
            )
