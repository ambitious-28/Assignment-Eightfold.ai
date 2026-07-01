"""
ATS JSON blob adapter.

The ATS uses foreign field names that do NOT match our canonical schema.
This adapter hardcodes the translation table and normalizes all values.

ATS field → Canonical field:
  candidateName → full_name
  emailAddress  → emails
  mobile        → phones
  employer      → experience[].company
  jobTitle      → experience[].title
  skillTags     → skills
  yearsExp      → years_experience
  city          → location.city
"""

from __future__ import annotations

import json
from pathlib import Path

from transformer.adapters.base import FieldValue, IntermediateRecord, SourceAdapter
from transformer.models import ExperienceEntry, Location, SkillEntry
from transformer.normalize.emails import normalize_emails, normalize_email
from transformer.normalize.location import normalize_city
from transformer.normalize.names import normalize_name
from transformer.normalize.phones import normalize_phone
from transformer.normalize.skills import normalize_skill
from transformer.normalize.years_experience import normalize_years_experience

# Hardcoded ATS → canonical translation table
_ATS_FIELD_MAP: dict[str, str] = {
    "candidateName": "full_name",
    "emailAddress": "emails",
    "mobile": "phones",
    "employer": "_experience_company",   # internal staging key
    "jobTitle": "_experience_title",     # internal staging key
    "skillTags": "skills",
    "yearsExp": "years_experience",
    "city": "_location_city",            # internal staging key
}


class ATSJSONAdapter(SourceAdapter):

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".json"

    def read(self, path: Path) -> list[IntermediateRecord]:
        try:
            with open(path, encoding="utf-8") as fh:
                raw_data = json.load(fh)
        except json.JSONDecodeError as exc:
            return [IntermediateRecord(
                source="ats_blob",
                source_file=str(path),
                warnings=[f"Malformed JSON in {path.name}: {exc}"],
            )]
        except Exception as exc:  # noqa: BLE001
            return [IntermediateRecord(
                source="ats_blob",
                source_file=str(path),
                warnings=[f"Cannot read {path.name}: {exc}"],
            )]

        if not isinstance(raw_data, list):
            return [IntermediateRecord(
                source="ats_blob",
                source_file=str(path),
                warnings=[f"{path.name}: expected JSON array at top level, got {type(raw_data).__name__}"],
            )]

        records: list[IntermediateRecord] = []
        for idx, entry in enumerate(raw_data):
            try:
                rec = self._parse_entry(entry, str(path), idx)
                if rec is not None:
                    records.append(rec)
            except Exception as exc:  # noqa: BLE001
                records.append(IntermediateRecord(
                    source="ats_blob",
                    source_file=str(path),
                    warnings=[f"entry[{idx}]: skipped due to error: {exc}"],
                ))
        return records

    def _parse_entry(self, entry: dict, source_file: str, idx: int) -> IntermediateRecord | None:
        if not isinstance(entry, dict):
            return IntermediateRecord(
                source="ats_blob",
                source_file=source_file,
                warnings=[f"entry[{idx}]: expected object, got {type(entry).__name__}"],
            )

        warnings: list[str] = []
        fields: dict[str, FieldValue] = {}

        # Staging area for fields that combine into structured objects
        experience_company: str | None = None
        experience_title: str | None = None
        location_city: str | None = None

        for ats_key, value in entry.items():
            canonical = _ATS_FIELD_MAP.get(ats_key)
            if canonical is None:
                continue  # unknown ATS field — ignore

            if canonical == "full_name":
                raw = str(value) if value is not None else ""
                norm, method, ok = normalize_name(raw)
                if not ok:
                    warnings.append(f"entry[{idx}]: bad candidateName: {raw!r}")
                fields["full_name"] = FieldValue(raw=raw, normalized=norm, method=method, ok=ok)

            elif canonical == "emails":
                # May be string or list
                if isinstance(value, list):
                    raw_list = [str(v) for v in value]
                else:
                    raw_list = [str(value)] if value else []
                normed = normalize_emails(raw_list)
                ok = bool(normed)
                if not ok and raw_list:
                    warnings.append(f"entry[{idx}]: no valid emails in emailAddress: {raw_list}")
                fields["emails"] = FieldValue(
                    raw=raw_list, normalized=normed, method="email_lowercased", ok=ok
                )

            elif canonical == "phones":
                raw = str(value) if value is not None else ""
                norm, method, ok = normalize_phone(raw)
                if not ok:
                    warnings.append(f"entry[{idx}]: bad mobile: {raw!r}")
                phones_norm = [norm] if ok and norm else []
                fields["phones"] = FieldValue(raw=raw, normalized=phones_norm, method=method, ok=ok)

            elif canonical == "_experience_company":
                experience_company = str(value) if value else None

            elif canonical == "_experience_title":
                experience_title = str(value) if value else None

            elif canonical == "skills":
                # May be list or comma-separated string
                if isinstance(value, list):
                    raw_list = [str(v).strip() for v in value if v]
                else:
                    raw_list = [s.strip() for s in str(value).split(",") if s.strip()]
                skill_entries: list[SkillEntry] = []
                for raw_skill in raw_list:
                    norm, method, ok = normalize_skill(raw_skill)
                    if ok and norm:
                        skill_entries.append(SkillEntry(name=norm, confidence=0.0, sources=[]))
                    else:
                        warnings.append(f"entry[{idx}]: skipped empty skill")
                fields["skills"] = FieldValue(
                    raw=raw_list, normalized=skill_entries, method="skill_normalized", ok=True
                )

            elif canonical == "years_experience":
                raw = value  # may be int, float, or string like "lots"
                norm, method, ok = normalize_years_experience(raw)
                if not ok:
                    warnings.append(
                        f"entry[{idx}]: yearsExp {raw!r} could not be parsed → null"
                    )
                fields["years_experience"] = FieldValue(raw=raw, normalized=norm, method=method, ok=ok)

            elif canonical == "_location_city":
                location_city = str(value).strip() if value else None

        # Assemble experience entry if we have company or title
        if experience_company or experience_title:
            from transformer.normalize.names import normalize_name as _nn, normalize_org_name as _on
            company_norm = _on(experience_company)[0] if experience_company else None
            title_norm = _nn(experience_title)[0] if experience_title else None
            entry_obj = ExperienceEntry(company=company_norm, title=title_norm)
            fields["experience"] = FieldValue(
                raw={"employer": experience_company, "jobTitle": experience_title},
                normalized=[entry_obj],
                method="ats_experience",
                ok=True,
            )

        # Assemble location if we have city
        if location_city:
            city_norm, city_method, city_ok = normalize_city(location_city)
            loc = Location(city=city_norm if city_ok else None)
            fields["location"] = FieldValue(
                raw={"city": location_city},
                normalized=loc,
                method=city_method,
                ok=city_ok,
            )

        # Skip entries with zero usable fields (all blank / all failed)
        if not fields and not warnings:
            return None

        return IntermediateRecord(
            source="ats_blob",
            source_file=source_file,
            fields=fields,
            warnings=warnings,
        )
