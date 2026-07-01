"""
Recruiter CSV adapter.

Expected columns: name, email, phone, current_company, title
One candidate per row; a person may appear in multiple rows.
"""

from __future__ import annotations

import csv
from pathlib import Path

from transformer.adapters.base import FieldValue, IntermediateRecord, SourceAdapter
from transformer.models import ExperienceEntry
from transformer.normalize.emails import normalize_email
from transformer.normalize.names import normalize_name, normalize_org_name
from transformer.normalize.phones import normalize_phone


class RecruiterCSVAdapter(SourceAdapter):

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".csv"

    def read(self, path: Path) -> list[IntermediateRecord]:
        records: list[IntermediateRecord] = []
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for row_num, row in enumerate(reader, start=2):  # 2 = first data row
                    try:
                        rec = self._parse_row(row, str(path))
                        if rec is not None:
                            records.append(rec)
                    except Exception as exc:  # noqa: BLE001
                        # Per-row failure: warn and continue
                        records.append(IntermediateRecord(
                            source="recruiter_csv",
                            source_file=str(path),
                            warnings=[f"row {row_num}: skipped due to error: {exc}"],
                        ))
        except FileNotFoundError:
            pass  # caller already knows file exists; shouldn't happen
        except Exception as exc:  # noqa: BLE001
            return [IntermediateRecord(
                source="recruiter_csv",
                source_file=str(path),
                warnings=[f"file-level error reading {path}: {exc}"],
            )]
        return records

    def _parse_row(self, row: dict, source_file: str) -> IntermediateRecord | None:
        """Parse one CSV row into an IntermediateRecord. Returns None for blank rows."""
        # Normalize keys to lowercase + strip
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}

        # Skip completely blank rows
        relevant = ("name", "email", "phone", "current_company", "title")
        if not any(row.get(k) for k in relevant):
            return None

        warnings: list[str] = []
        fields: dict[str, FieldValue] = {}

        # full_name
        raw_name = row.get("name", "")
        if raw_name:
            norm, method, ok = normalize_name(raw_name)
            if not ok:
                warnings.append(f"Could not normalize name: {raw_name!r}")
            fields["full_name"] = FieldValue(raw=raw_name, normalized=norm, method=method, ok=ok)

        # emails (single email → list)
        raw_email = row.get("email", "")
        if raw_email:
            norm, method, ok = normalize_email(raw_email)
            if not ok:
                warnings.append(f"Could not normalize email: {raw_email!r}")
            emails_norm = [norm] if ok and norm else []
            fields["emails"] = FieldValue(raw=raw_email, normalized=emails_norm, method=method, ok=ok)

        # phones (single phone → list)
        raw_phone = row.get("phone", "")
        if raw_phone:
            norm, method, ok = normalize_phone(raw_phone)
            if not ok:
                warnings.append(f"Could not normalize phone: {raw_phone!r}")
            phones_norm = [norm] if ok and norm else []
            fields["phones"] = FieldValue(raw=raw_phone, normalized=phones_norm, method=method, ok=ok)

        # experience — company + title from this row
        raw_company = row.get("current_company", "")
        raw_title = row.get("title", "")
        if raw_company or raw_title:
            company_norm, _, _ = normalize_org_name(raw_company) if raw_company else (None, "", False)
            title_norm, _, _ = normalize_name(raw_title) if raw_title else (None, "", False)
            entry = ExperienceEntry(company=company_norm, title=title_norm)
            fields["experience"] = FieldValue(
                raw={"company": raw_company, "title": raw_title},
                normalized=[entry],
                method="csv_experience",
                ok=True,
            )

        return IntermediateRecord(
            source="recruiter_csv",
            source_file=source_file,
            fields=fields,
            warnings=warnings,
        )
