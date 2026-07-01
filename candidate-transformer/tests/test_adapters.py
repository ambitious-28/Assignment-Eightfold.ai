"""
Stage 3 checkpoint tests — Adapters.

Run: pytest tests/test_adapters.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from transformer.adapters.recruiter_csv import RecruiterCSVAdapter
from transformer.adapters.ats_json import ATSJSONAdapter
from transformer.adapters.resume import ResumeAdapter
from transformer.adapters.recruiter_notes import RecruiterNotesAdapter
from transformer.models import ExperienceEntry, EducationEntry, SkillEntry, Location


# ---------------------------------------------------------------------------
# Recruiter CSV adapter
# ---------------------------------------------------------------------------

class TestRecruiterCSV:
    def setup_method(self):
        self.adapter = RecruiterCSVAdapter()

    def test_can_handle_csv(self, fixtures_dir):
        assert self.adapter.can_handle(fixtures_dir / "sample_recruiter.csv")

    def test_does_not_handle_json(self, fixtures_dir):
        assert not self.adapter.can_handle(fixtures_dir / "sample_ats.json")

    def test_two_rows_returns_two_records(self, fixtures_dir):
        records = self.adapter.read(fixtures_dir / "sample_recruiter.csv")
        # blank row is skipped
        data_records = [r for r in records if r.fields]
        assert len(data_records) == 2

    def test_canonical_field_names_present(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_recruiter.csv") if r.fields]
        rec = records[0]
        assert "full_name" in rec.fields
        assert "emails" in rec.fields
        assert "phones" in rec.fields
        assert "experience" in rec.fields

    def test_no_foreign_field_names(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_recruiter.csv") if r.fields]
        for rec in records:
            assert "name" not in rec.fields
            assert "email" not in rec.fields
            assert "phone" not in rec.fields
            assert "current_company" not in rec.fields

    def test_full_name_normalized(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_recruiter.csv") if r.fields]
        rec = records[0]
        assert rec.fields["full_name"].normalized == "Aarav Sharma"

    def test_emails_is_list(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_recruiter.csv") if r.fields]
        rec = records[0]
        assert isinstance(rec.fields["emails"].normalized, list)

    def test_email_lowercased(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_recruiter.csv") if r.fields]
        rec = records[0]
        assert rec.fields["emails"].normalized == ["aarav.sharma@example.com"]

    def test_phones_is_list(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_recruiter.csv") if r.fields]
        rec = records[0]
        assert isinstance(rec.fields["phones"].normalized, list)

    def test_phone_normalized_e164(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_recruiter.csv") if r.fields]
        rec = records[0]
        assert rec.fields["phones"].normalized == ["+919876543210"]

    def test_experience_company_and_title(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_recruiter.csv") if r.fields]
        rec = records[0]
        exp_entries = rec.fields["experience"].normalized
        assert isinstance(exp_entries, list) and len(exp_entries) == 1
        assert isinstance(exp_entries[0], ExperienceEntry)
        assert exp_entries[0].company is not None
        assert exp_entries[0].title is not None

    def test_source_tag(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_recruiter.csv") if r.fields]
        for rec in records:
            assert rec.source == "recruiter_csv"

    def test_empty_csv_returns_empty_list(self, fixtures_dir):
        records = self.adapter.read(fixtures_dir / "empty.csv")
        data = [r for r in records if r.fields]
        assert data == []

    def test_empty_csv_does_not_raise(self, fixtures_dir):
        # Must complete without raising
        self.adapter.read(fixtures_dir / "empty.csv")

    def test_raw_value_preserved(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_recruiter.csv") if r.fields]
        rec = records[0]
        # raw email should be the original string from CSV
        assert rec.fields["emails"].raw == "aarav.sharma@example.com"


# ---------------------------------------------------------------------------
# ATS JSON adapter
# ---------------------------------------------------------------------------

class TestATSJSON:
    def setup_method(self):
        self.adapter = ATSJSONAdapter()

    def test_can_handle_json(self, fixtures_dir):
        assert self.adapter.can_handle(fixtures_dir / "sample_ats.json")

    def test_two_entries_returns_two_records(self, fixtures_dir):
        records = self.adapter.read(fixtures_dir / "sample_ats.json")
        data = [r for r in records if r.fields]
        assert len(data) == 2

    def test_candidate_name_mapped_to_full_name(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_ats.json") if r.fields]
        rec = records[0]
        assert "full_name" in rec.fields
        assert rec.fields["full_name"].normalized == "Aarav Sharma"

    def test_foreign_field_names_absent(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_ats.json") if r.fields]
        rec = records[0]
        assert "candidateName" not in rec.fields
        assert "emailAddress" not in rec.fields
        assert "mobile" not in rec.fields

    def test_mobile_normalized_e164(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_ats.json") if r.fields]
        rec = records[0]
        assert rec.fields["phones"].normalized == ["+919876543210"]

    def test_years_exp_lots_becomes_null_with_warning(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_ats.json") if r.fields]
        rec = records[1]  # Vivaan Reddy — yearsExp:"lots"
        assert "years_experience" in rec.fields
        assert rec.fields["years_experience"].normalized is None
        assert rec.fields["years_experience"].ok is False
        assert any("lots" in w or "yearsExp" in w for w in rec.warnings)

    def test_bad_phone_produces_warning(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_ats.json") if r.fields]
        rec = records[1]  # bad-number
        assert any("bad-number" in w or "mobile" in w for w in rec.warnings)

    def test_skill_tags_list_normalized(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_ats.json") if r.fields]
        rec = records[0]
        skills = rec.fields["skills"].normalized
        assert isinstance(skills, list) and len(skills) >= 1
        skill_names = [s.name for s in skills]
        assert "Python" in skill_names
        assert "Kubernetes" in skill_names  # k8s → Kubernetes

    def test_skill_tags_string_split_by_comma(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_ats.json") if r.fields]
        rec = records[1]  # "Python, SQL"
        skills = rec.fields["skills"].normalized
        skill_names = [s.name for s in skills]
        assert "Python" in skill_names
        assert "SQL" in skill_names

    def test_city_mapped_to_location(self, fixtures_dir):
        records = [r for r in self.adapter.read(fixtures_dir / "sample_ats.json") if r.fields]
        rec = records[0]
        assert "location" in rec.fields
        loc = rec.fields["location"].normalized
        assert isinstance(loc, Location)
        assert loc.city == "Mumbai"

    def test_malformed_json_returns_warning_no_raise(self, fixtures_dir):
        records = self.adapter.read(fixtures_dir / "malformed.json")
        assert len(records) >= 1
        all_warnings = [w for r in records for w in r.warnings]
        assert any("JSON" in w or "json" in w or "Malformed" in w for w in all_warnings)

    def test_source_tag(self, fixtures_dir):
        records = self.adapter.read(fixtures_dir / "sample_ats.json")
        for rec in records:
            assert rec.source == "ats_blob"


# ---------------------------------------------------------------------------
# Resume adapter (PDF)
# ---------------------------------------------------------------------------

class TestResumeAdapter:
    def setup_method(self):
        self.adapter = ResumeAdapter()

    def test_can_handle_pdf(self, sample_resume_pdf):
        assert self.adapter.can_handle(sample_resume_pdf)

    def test_can_handle_docx(self):
        assert self.adapter.can_handle(Path("resume.docx"))

    def test_does_not_handle_csv(self):
        assert not self.adapter.can_handle(Path("file.csv"))

    def test_returns_one_record(self, sample_resume_pdf):
        records = self.adapter.read(sample_resume_pdf)
        assert len(records) == 1

    def test_extracts_email(self, sample_resume_pdf):
        records = self.adapter.read(sample_resume_pdf)
        rec = records[0]
        assert "emails" in rec.fields
        emails = rec.fields["emails"].normalized
        assert isinstance(emails, list) and len(emails) >= 1
        assert "test.candidate@example.com" in emails

    def test_extracts_phone_e164(self, sample_resume_pdf):
        records = self.adapter.read(sample_resume_pdf)
        rec = records[0]
        assert "phones" in rec.fields
        phones = rec.fields["phones"].normalized
        assert "+919876543210" in phones

    def test_extracts_linkedin(self, sample_resume_pdf):
        records = self.adapter.read(sample_resume_pdf)
        rec = records[0]
        assert "links" in rec.fields
        links = rec.fields["links"].normalized
        assert links.linkedin is not None
        assert "linkedin.com" in links.linkedin

    def test_extracts_github(self, sample_resume_pdf):
        records = self.adapter.read(sample_resume_pdf)
        rec = records[0]
        links = rec.fields["links"].normalized
        assert links.github is not None
        assert "github.com" in links.github

    def test_extracts_location(self, sample_resume_pdf):
        records = self.adapter.read(sample_resume_pdf)
        rec = records[0]
        assert "location" in rec.fields
        loc = rec.fields["location"].normalized
        assert isinstance(loc, Location)
        assert loc.city is not None

    def test_extracts_skills(self, sample_resume_pdf):
        records = self.adapter.read(sample_resume_pdf)
        rec = records[0]
        assert "skills" in rec.fields
        skills = rec.fields["skills"].normalized
        skill_names = [s.name for s in skills]
        assert "Python" in skill_names
        assert "Kubernetes" in skill_names  # k8s → Kubernetes

    def test_extracts_experience(self, sample_resume_pdf):
        records = self.adapter.read(sample_resume_pdf)
        rec = records[0]
        assert "experience" in rec.fields
        exp = rec.fields["experience"].normalized
        assert isinstance(exp, list) and len(exp) >= 1
        assert isinstance(exp[0], ExperienceEntry)
        assert exp[0].company is not None or exp[0].title is not None

    def test_extracts_education(self, sample_resume_pdf):
        records = self.adapter.read(sample_resume_pdf)
        rec = records[0]
        assert "education" in rec.fields
        edu = rec.fields["education"].normalized
        assert isinstance(edu, list) and len(edu) >= 1
        assert isinstance(edu[0], EducationEntry)
        assert edu[0].institution is not None or edu[0].degree is not None

    def test_source_tag(self, sample_resume_pdf):
        records = self.adapter.read(sample_resume_pdf)
        assert records[0].source == "resume"

    def test_does_not_raise_on_missing_file(self, tmp_path):
        records = self.adapter.read(tmp_path / "nonexistent.pdf")
        assert isinstance(records, list)


# ---------------------------------------------------------------------------
# Recruiter Notes adapter
# ---------------------------------------------------------------------------

class TestRecruiterNotes:
    def setup_method(self):
        self.adapter = RecruiterNotesAdapter()

    def test_can_handle_txt(self, fixtures_dir):
        assert self.adapter.can_handle(fixtures_dir / "sample_notes.txt")

    def test_returns_one_record(self, fixtures_dir):
        records = self.adapter.read(fixtures_dir / "sample_notes.txt")
        assert len(records) == 1

    def test_extracts_email(self, fixtures_dir):
        records = self.adapter.read(fixtures_dir / "sample_notes.txt")
        rec = records[0]
        assert "emails" in rec.fields
        assert "priya.test@example.com" in rec.fields["emails"].normalized

    def test_extracts_location(self, fixtures_dir):
        records = self.adapter.read(fixtures_dir / "sample_notes.txt")
        rec = records[0]
        assert "location" in rec.fields
        loc = rec.fields["location"].normalized
        assert isinstance(loc, Location)
        assert loc.city == "Mumbai"
        assert loc.country == "IN"

    def test_extracts_skills(self, fixtures_dir):
        records = self.adapter.read(fixtures_dir / "sample_notes.txt")
        rec = records[0]
        assert "skills" in rec.fields
        skill_names = [s.name for s in rec.fields["skills"].normalized]
        assert "Python" in skill_names

    def test_source_tag(self, fixtures_dir):
        records = self.adapter.read(fixtures_dir / "sample_notes.txt")
        assert records[0].source == "recruiter_notes"

    def test_does_not_raise_on_missing_file(self, tmp_path):
        records = self.adapter.read(tmp_path / "nonexistent.txt")
        assert isinstance(records, list)


# ---------------------------------------------------------------------------
# Robustness (PRD §9 Stage 3 checkpoint)
# ---------------------------------------------------------------------------

class TestAdapterRobustness:
    def test_empty_csv_no_raise(self, fixtures_dir):
        adapter = RecruiterCSVAdapter()
        records = adapter.read(fixtures_dir / "empty.csv")
        data = [r for r in records if r.fields]
        assert data == []

    def test_malformed_json_no_raise_with_warning(self, fixtures_dir):
        adapter = ATSJSONAdapter()
        records = adapter.read(fixtures_dir / "malformed.json")
        assert isinstance(records, list)
        all_warnings = [w for r in records for w in r.warnings]
        assert len(all_warnings) >= 1

    def test_malformed_json_zero_data_records(self, fixtures_dir):
        adapter = ATSJSONAdapter()
        records = adapter.read(fixtures_dir / "malformed.json")
        data = [r for r in records if r.fields]
        assert data == []
