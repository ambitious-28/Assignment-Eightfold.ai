"""
Stage 5 checkpoint tests — Arbitration.

Run: pytest tests/test_arbitrate.py -v
"""

from __future__ import annotations

import random

import pytest

from transformer.adapters.base import FieldValue, IntermediateRecord
from transformer.merge.arbitrate import ArbitrationResult, arbitrate_cluster
from transformer.models import (
    Contribution,
    EducationEntry,
    ExperienceEntry,
    Location,
    SkillEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fv(raw, normalized, method="test", ok=True) -> FieldValue:
    return FieldValue(raw=raw, normalized=normalized, method=method, ok=ok)


def _fv_list(items: list, ok=True) -> FieldValue:
    return FieldValue(raw=items, normalized=items, method="test", ok=ok)


def _fv_fail(raw) -> FieldValue:
    return FieldValue(raw=raw, normalized=None, method="normalization_failed", ok=False)


def make_rec(
    source: str,
    source_file: str = "test",
    fields: dict | None = None,
) -> IntermediateRecord:
    return IntermediateRecord(source=source, source_file=source_file, fields=fields or {})


# ---------------------------------------------------------------------------
# Scalar arbitration: full_name
# ---------------------------------------------------------------------------

class TestScalarArbitration:
    def test_csv_wins_over_resume(self):
        """CSV (tier 0.90) beats resume (tier 0.60) on name."""
        csv_rec = make_rec("recruiter_csv", fields={
            "full_name": _fv("Aarav Sharma", "Aarav Sharma", "name_normalized")
        })
        resume_rec = make_rec("resume", fields={
            "full_name": _fv("A. Sharma", "A. Sharma", "name_normalized")
        })
        results = arbitrate_cluster([csv_rec, resume_rec])
        assert "full_name" in results
        r = results["full_name"]
        assert r.winner_value == "Aarav Sharma"
        assert r.winner_source == "recruiter_csv"

    def test_conflict_recorded_when_values_differ(self):
        csv_rec = make_rec("recruiter_csv", fields={
            "full_name": _fv("Acme Corp", "Acme Corp")
        })
        resume_rec = make_rec("resume", fields={
            "full_name": _fv("Acme Inc", "Acme Inc")
        })
        results = arbitrate_cluster([csv_rec, resume_rec])
        assert results["full_name"].conflicted is True

    def test_no_conflict_when_values_agree(self):
        a = make_rec("recruiter_csv", fields={"full_name": _fv("Aarav", "Aarav")})
        b = make_rec("ats_blob",      fields={"full_name": _fv("Aarav", "Aarav")})
        results = arbitrate_cluster([a, b])
        assert results["full_name"].conflicted is False

    def test_winner_source_is_highest_tier(self):
        """ATS beats resume; CSV beats ATS."""
        ats = make_rec("ats_blob",      fields={"full_name": _fv("Bob", "Bob")})
        res = make_rec("resume",         fields={"full_name": _fv("Bob", "Bob")})
        results = arbitrate_cluster([ats, res])
        assert results["full_name"].winner_source == "ats_blob"

    def test_agreement_breaks_tie_within_same_tier(self):
        """Two CSV records — one agrees with ATS, other doesn't. Agreement value wins."""
        csv1 = make_rec("recruiter_csv", "a.csv", {"full_name": _fv("Aarav Sharma", "Aarav Sharma")})
        csv2 = make_rec("recruiter_csv", "b.csv", {"full_name": _fv("Aarav Kumar", "Aarav Kumar")})
        ats  = make_rec("ats_blob",              {"full_name": _fv("Aarav Sharma", "Aarav Sharma")})
        results = arbitrate_cluster([csv1, csv2, ats])
        # "Aarav Sharma" has agreement count 2 (csv1 + ats); "Aarav Kumar" has count 1
        assert results["full_name"].winner_value == "Aarav Sharma"

    def test_all_failed_normalization_returns_none(self):
        a = make_rec("recruiter_csv", fields={"full_name": _fv_fail("???")})
        b = make_rec("ats_blob",      fields={"full_name": _fv_fail("   ")})
        results = arbitrate_cluster([a, b])
        assert results["full_name"].winner_value is None

    def test_years_experience_arbitrated(self):
        csv = make_rec("recruiter_csv", fields={"years_experience": _fv("5", 5.0)})
        ats = make_rec("ats_blob",      fields={"years_experience": _fv("7", 7.0)})
        results = arbitrate_cluster([csv, ats])
        r = results["years_experience"]
        assert r.winner_source == "recruiter_csv"  # higher tier
        assert r.winner_value == 5.0

    def test_single_source_no_conflict(self):
        rec = make_rec("recruiter_csv", fields={"full_name": _fv("Solo", "Solo")})
        results = arbitrate_cluster([rec])
        r = results["full_name"]
        assert r.winner_value == "Solo"
        assert r.conflicted is False


# ---------------------------------------------------------------------------
# Contributions
# ---------------------------------------------------------------------------

class TestContributions:
    def _get_contrib_sources(self, result: ArbitrationResult) -> list[str]:
        return [c.source for c in result.contributions]

    def test_contributions_include_all_sources(self):
        a = make_rec("recruiter_csv", fields={"full_name": _fv("Alice", "Alice")})
        b = make_rec("ats_blob",      fields={"full_name": _fv("Alice", "Alice")})
        c = make_rec("resume",         fields={"full_name": _fv("A.", "A.")})
        results = arbitrate_cluster([a, b, c])
        sources = self._get_contrib_sources(results["full_name"])
        assert set(sources) == {"recruiter_csv", "ats_blob", "resume"}

    def test_winner_contrib_agreed_true(self):
        a = make_rec("recruiter_csv", fields={"full_name": _fv("Alice", "Alice")})
        b = make_rec("ats_blob",      fields={"full_name": _fv("Alice", "Alice")})
        results = arbitrate_cluster([a, b])
        for c in results["full_name"].contributions:
            assert c.agreed is True

    def test_loser_contrib_agreed_false(self):
        csv = make_rec("recruiter_csv", fields={"full_name": _fv("Acme Corp", "Acme Corp")})
        res = make_rec("resume",         fields={"full_name": _fv("Acme Inc", "Acme Inc")})
        results = arbitrate_cluster([csv, res])
        r = results["full_name"]
        loser_contribs = [c for c in r.contributions if c.source == "resume"]
        assert loser_contribs[0].agreed is False

    def test_failed_ok_in_contributions(self):
        """A source whose normalization failed should still appear in contributions."""
        good = make_rec("recruiter_csv", fields={"full_name": _fv("Alice", "Alice")})
        bad  = make_rec("ats_blob",      fields={"full_name": _fv_fail("???")})
        results = arbitrate_cluster([good, bad])
        sources = self._get_contrib_sources(results["full_name"])
        assert "ats_blob" in sources

    def test_failed_ok_not_chosen_as_winner(self):
        good = make_rec("ats_blob",      fields={"full_name": _fv("Alice", "Alice")})
        bad  = make_rec("recruiter_csv", fields={"full_name": _fv_fail("bad")})
        results = arbitrate_cluster([good, bad])
        # recruiter_csv failed → ats_blob wins even though csv has higher tier
        assert results["full_name"].winner_value == "Alice"
        assert results["full_name"].winner_source == "ats_blob"

    def test_contributions_sorted_deterministically(self):
        a = make_rec("recruiter_csv", fields={"full_name": _fv("X", "X")})
        b = make_rec("ats_blob",      fields={"full_name": _fv("X", "X")})
        c = make_rec("resume",         fields={"full_name": _fv("X", "X")})
        r1 = arbitrate_cluster([a, b, c])["full_name"]
        r2 = arbitrate_cluster([c, a, b])["full_name"]
        assert [x.source for x in r1.contributions] == [x.source for x in r2.contributions]


# ---------------------------------------------------------------------------
# Array union: emails
# ---------------------------------------------------------------------------

class TestEmailUnion:
    def test_emails_from_three_sources_unioned(self):
        a = make_rec("recruiter_csv", fields={"emails": _fv_list(["a@x.com"])})
        b = make_rec("ats_blob",      fields={"emails": _fv_list(["b@x.com"])})
        c = make_rec("resume",         fields={"emails": _fv_list(["c@x.com"])})
        results = arbitrate_cluster([a, b, c])
        union = results["emails"].winner_value
        assert set(union) == {"a@x.com", "b@x.com", "c@x.com"}

    def test_emails_deduplicated(self):
        a = make_rec("recruiter_csv", fields={"emails": _fv_list(["x@x.com"])})
        b = make_rec("ats_blob",      fields={"emails": _fv_list(["x@x.com", "y@x.com"])})
        results = arbitrate_cluster([a, b])
        union = results["emails"].winner_value
        assert union.count("x@x.com") == 1

    def test_primary_email_from_highest_tier(self):
        """emails[0] must come from the highest-tier source."""
        csv = make_rec("recruiter_csv", fields={"emails": _fv_list(["csv@x.com"])})
        res = make_rec("resume",         fields={"emails": _fv_list(["resume@x.com"])})
        results = arbitrate_cluster([csv, res])
        assert results["emails"].winner_value[0] == "csv@x.com"

    def test_winner_source_is_highest_tier(self):
        csv = make_rec("recruiter_csv", fields={"emails": _fv_list(["a@x.com"])})
        res = make_rec("resume",         fields={"emails": _fv_list(["b@x.com"])})
        results = arbitrate_cluster([csv, res])
        assert results["emails"].winner_source == "recruiter_csv"


# ---------------------------------------------------------------------------
# Array union: phones
# ---------------------------------------------------------------------------

class TestPhoneUnion:
    def test_phones_union_deduped(self):
        csv = make_rec("recruiter_csv", fields={"phones": _fv_list(["+919876543210"])})
        ats = make_rec("ats_blob",      fields={"phones": _fv_list(["+919876543210", "+911111111111"])})
        nts = make_rec("recruiter_notes", fields={"phones": _fv_list(["+922222222222"])})
        results = arbitrate_cluster([csv, ats, nts])
        union = results["phones"].winner_value
        assert "+919876543210" in union
        assert "+911111111111" in union
        assert "+922222222222" in union
        assert union.count("+919876543210") == 1

    def test_primary_phone_from_highest_tier(self):
        csv = make_rec("recruiter_csv",   fields={"phones": _fv_list(["+911111111111"])})
        notes = make_rec("recruiter_notes", fields={"phones": _fv_list(["+922222222222"])})
        results = arbitrate_cluster([csv, notes])
        assert results["phones"].winner_value[0] == "+911111111111"


# ---------------------------------------------------------------------------
# Array union: skills
# ---------------------------------------------------------------------------

class TestSkillUnion:
    def test_skills_from_two_sources_unioned(self):
        csv = make_rec("recruiter_csv", fields={"skills": FieldValue(
            raw=["Python"], normalized=[SkillEntry("Python", 0.0, [])], method="test", ok=True
        )})
        res = make_rec("resume", fields={"skills": FieldValue(
            raw=["k8s"], normalized=[SkillEntry("Kubernetes", 0.0, [])], method="test", ok=True
        )})
        results = arbitrate_cluster([csv, res])
        names = [s.name for s in results["skills"].winner_value]
        assert "Python" in names
        assert "Kubernetes" in names

    def test_duplicate_skill_merged_one_entry(self):
        """Same skill from two sources → one SkillEntry with both sources listed."""
        csv = make_rec("recruiter_csv", fields={"skills": FieldValue(
            raw=["Python"], normalized=[SkillEntry("Python", 0.0, [])], method="test", ok=True
        )})
        ats = make_rec("ats_blob", fields={"skills": FieldValue(
            raw=["Python"], normalized=[SkillEntry("Python", 0.0, [])], method="test", ok=True
        )})
        results = arbitrate_cluster([csv, ats])
        skill_entries = results["skills"].winner_value
        python_entries = [s for s in skill_entries if s.name == "Python"]
        assert len(python_entries) == 1
        # Both sources should be in the sources list
        assert set(python_entries[0].sources) == {"recruiter_csv", "ats_blob"}

    def test_skills_sorted_alphabetically(self):
        """Skills should be in deterministic alphabetical order."""
        rec = make_rec("recruiter_csv", fields={"skills": FieldValue(
            raw=["SQL", "Python", "Docker"],
            normalized=[SkillEntry("SQL", 0.0, []), SkillEntry("Python", 0.0, []),
                        SkillEntry("Docker", 0.0, [])],
            method="test", ok=True
        )})
        results = arbitrate_cluster([rec])
        names = [s.name for s in results["skills"].winner_value]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# Array union: experience
# ---------------------------------------------------------------------------

class TestExperienceUnion:
    def test_experience_entries_from_two_sources(self):
        csv = make_rec("recruiter_csv", fields={"experience": FieldValue(
            raw={}, normalized=[ExperienceEntry(company="TechCorp", title="Engineer")],
            method="test", ok=True
        )})
        res = make_rec("resume", fields={"experience": FieldValue(
            raw={}, normalized=[ExperienceEntry(company="StartupXYZ", title="Developer")],
            method="test", ok=True
        )})
        results = arbitrate_cluster([csv, res])
        entries = results["experience"].winner_value
        companies = [e.company for e in entries]
        assert "Techcorp" in companies or "TechCorp" in companies
        assert "Startupxyz" in companies or "StartupXYZ" in companies

    def test_same_job_deduplicated(self):
        """Same company+title from two sources → one entry (fields merged)."""
        csv = make_rec("recruiter_csv", fields={"experience": FieldValue(
            raw={}, normalized=[ExperienceEntry(company="Techcorp", title="Engineer", start=None)],
            method="test", ok=True
        )})
        res = make_rec("resume", fields={"experience": FieldValue(
            raw={}, normalized=[ExperienceEntry(company="Techcorp", title="Engineer", start="2020-01")],
            method="test", ok=True
        )})
        results = arbitrate_cluster([csv, res])
        entries = results["experience"].winner_value
        techcorp_entries = [e for e in entries if e.company and "techcorp" in e.company.lower()]
        assert len(techcorp_entries) == 1
        # Date from resume should be merged in (csv had None)
        assert techcorp_entries[0].start == "2020-01"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def _repr(self, results: dict) -> str:
        parts = []
        for field in sorted(results.keys()):
            r = results[field]
            parts.append(f"{field}:{r.winner_value}:{r.winner_source}:{r.conflicted}")
        return "|".join(parts)

    def test_shuffle_same_winners(self):
        records = [
            make_rec("recruiter_csv", fields={"full_name": _fv("Alice", "Alice"),
                                               "emails": _fv_list(["a@x.com"])}),
            make_rec("ats_blob",      fields={"full_name": _fv("Alice", "Alice"),
                                               "emails": _fv_list(["b@x.com"])}),
            make_rec("resume",         fields={"full_name": _fv("A. Smith", "A. Smith"),
                                               "emails": _fv_list(["c@x.com"])}),
        ]
        base = self._repr(arbitrate_cluster(records))
        for seed in range(5):
            shuffled = records[:]
            random.Random(seed).shuffle(shuffled)
            assert self._repr(arbitrate_cluster(shuffled)) == base

    def test_no_fields_returns_empty_dict(self):
        rec = IntermediateRecord(source="recruiter_csv", source_file="empty.csv")
        results = arbitrate_cluster([rec])
        assert results == {}
