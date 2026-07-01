"""
Stage 4 checkpoint tests — Identity resolution (matcher).

Run: pytest tests/test_matcher.py -v
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import pytest

from transformer.adapters.base import FieldValue, IntermediateRecord
from transformer.merge.matcher import cluster_records, _can_merge
from transformer.models import ExperienceEntry, SkillEntry


# ---------------------------------------------------------------------------
# Helpers to build test records without touching real files
# ---------------------------------------------------------------------------

def _fv_str(raw: str, norm: str | None = None, ok: bool = True) -> FieldValue:
    return FieldValue(raw=raw, normalized=norm if norm is not None else raw,
                      method="test", ok=ok)


def _fv_list(items: list[str], ok: bool = True) -> FieldValue:
    return FieldValue(raw=items, normalized=items, method="test", ok=ok)


def make_record(
    source: str = "recruiter_csv",
    source_file: str = "test.csv",
    name: str | None = None,
    emails: list[str] | None = None,
    phones: list[str] | None = None,
    company: str | None = None,
) -> IntermediateRecord:
    """Build a minimal IntermediateRecord for testing."""
    fields: dict[str, FieldValue] = {}
    if name is not None:
        from transformer.normalize.names import normalize_name
        norm, method, ok = normalize_name(name)
        fields["full_name"] = FieldValue(raw=name, normalized=norm, method=method, ok=ok)
    if emails is not None:
        fields["emails"] = _fv_list(emails)
    if phones is not None:
        fields["phones"] = _fv_list(phones)
    if company is not None:
        from transformer.normalize.names import normalize_name
        comp_norm = normalize_name(company)[0]
        entry = ExperienceEntry(company=comp_norm)
        fields["experience"] = FieldValue(
            raw={"company": company}, normalized=[entry], method="test", ok=True
        )
    return IntermediateRecord(source=source, source_file=source_file, fields=fields)


# Canonical test subjects
def priya_a() -> IntermediateRecord:
    return make_record(
        source="recruiter_csv", source_file="csv_a.csv",
        name="Priya Sharma", emails=["priya.a@example.com"], company="AcmeCorp"
    )


def priya_b() -> IntermediateRecord:
    return make_record(
        source="recruiter_csv", source_file="csv_b.csv",
        name="Priya Sharma", emails=["priya.b@example.com"], company="BetaInc"
    )


def aarav_csv() -> IntermediateRecord:
    return make_record(
        source="recruiter_csv", source_file="recruiter.csv",
        name="Aarav Sharma", emails=["aarav@example.com"], phones=["+919876543210"]
    )


def aarav_ats() -> IntermediateRecord:
    return make_record(
        source="ats_blob", source_file="ats.json",
        name="Aarav Sharma", emails=["aarav@example.com"], phones=["+919876543210"]
    )


def aarav_resume() -> IntermediateRecord:
    return make_record(
        source="resume", source_file="aarav_resume.pdf",
        name="Aarav Sharma", emails=["aarav@example.com"]
    )


# ---------------------------------------------------------------------------
# Basic merge tests
# ---------------------------------------------------------------------------

class TestBasicClustering:
    def test_single_record_own_cluster(self):
        rec = make_record(name="Solo Person", emails=["solo@example.com"])
        clusters = cluster_records([rec])
        assert len(clusters) == 1
        assert len(clusters[0]) == 1

    def test_empty_input(self):
        assert cluster_records([]) == []

    def test_same_email_merges(self):
        a = make_record(source="recruiter_csv", emails=["x@example.com"], phones=["+911111111111"])
        b = make_record(source="ats_blob",      emails=["x@example.com"], phones=["+922222222222"])
        clusters = cluster_records([a, b])
        assert len(clusters) == 1
        assert len(clusters[0]) == 2

    def test_same_phone_merges(self):
        a = make_record(source="recruiter_csv", name="Alice", phones=["+919876543210"])
        b = make_record(source="ats_blob",      name="Bob",   phones=["+919876543210"])
        clusters = cluster_records([a, b])
        assert len(clusters) == 1

    def test_different_people_separate_clusters(self):
        a = make_record(emails=["alice@example.com"])
        b = make_record(emails=["bob@example.com"])
        clusters = cluster_records([a, b])
        assert len(clusters) == 2

    def test_three_sources_same_email_one_cluster(self):
        clusters = cluster_records([aarav_csv(), aarav_ats(), aarav_resume()])
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_name_company_no_match_without_email_or_phone(self):
        """Same name + same company alone does NOT merge — email or phone required."""
        a = make_record(source="recruiter_csv", name="Rohan Mehta", company="TechCorp")
        b = make_record(source="ats_blob",      name="Rohan Mehta", company="TechCorp")
        clusters = cluster_records([a, b])
        assert len(clusters) == 2


# ---------------------------------------------------------------------------
# Over-merge guard — THE CRITICAL TEST
# ---------------------------------------------------------------------------

class TestOverMergeGuard:
    def test_priya_sharma_two_clusters(self):
        """
        CRITICAL: Two 'Priya Sharma' records with different emails AND different
        companies must produce 2 clusters — NOT 1.
        """
        clusters = cluster_records([priya_a(), priya_b()])
        assert len(clusters) == 2, (
            "Over-merge guard FAILED: two different Priya Sharmas were merged into one cluster"
        )

    def test_priya_sharma_same_email_one_cluster(self):
        """If the two Priyas share an email, they ARE the same person → 1 cluster."""
        a = make_record(name="Priya Sharma", emails=["priya@example.com"], company="AcmeCorp")
        b = make_record(name="Priya Sharma", emails=["priya@example.com"], company="BetaInc")
        clusters = cluster_records([a, b])
        assert len(clusters) == 1

    def test_name_only_no_merge(self):
        """Name alone, no company, no email, no phone → must NOT merge."""
        a = make_record(source="recruiter_csv", name="Common Name")
        b = make_record(source="ats_blob",      name="Common Name")
        clusters = cluster_records([a, b])
        assert len(clusters) == 2

    def test_name_only_one_has_no_company(self):
        """Same name, one has company, one does not → name+company key requires BOTH → no merge."""
        a = make_record(name="Priya Sharma", company="AcmeCorp")
        b = make_record(name="Priya Sharma")  # no company
        clusters = cluster_records([a, b])
        assert len(clusters) == 2

    def test_same_name_different_company_no_merge(self):
        """Same name, different companies, no email/phone → 2 clusters."""
        a = make_record(name="Priya Sharma", company="AcmeCorp")
        b = make_record(name="Priya Sharma", company="BetaInc")
        clusters = cluster_records([a, b])
        assert len(clusters) == 2

    def test_can_merge_shared_email(self):
        a = make_record(emails=["x@y.com"])
        b = make_record(emails=["x@y.com"])
        assert _can_merge(a, b) is True

    def test_can_merge_shared_phone(self):
        a = make_record(phones=["+919876543210"])
        b = make_record(phones=["+919876543210"])
        assert _can_merge(a, b) is True

    def test_cannot_merge_name_company_only(self):
        """name+company without email/phone must NOT merge."""
        a = make_record(name="Rohan Mehta", company="TechCorp")
        b = make_record(name="Rohan Mehta", company="TechCorp")
        assert _can_merge(a, b) is False

    def test_cannot_merge_name_only(self):
        a = make_record(name="Common Name")
        b = make_record(name="Common Name")
        assert _can_merge(a, b) is False

    def test_cannot_merge_different_everything(self):
        a = make_record(name="Alice", emails=["alice@example.com"])
        b = make_record(name="Bob",   emails=["bob@example.com"])
        assert _can_merge(a, b) is False


# ---------------------------------------------------------------------------
# Transitivity
# ---------------------------------------------------------------------------

class TestTransitivity:
    def test_transitive_merge(self):
        """A shares email with B; B shares phone with C; all three should be in one cluster."""
        a = make_record(source="recruiter_csv", emails=["shared@example.com"])
        b = make_record(source="ats_blob",      emails=["shared@example.com"],
                        phones=["+919999999999"])
        c = make_record(source="resume",        phones=["+919999999999"])
        clusters = cluster_records([a, b, c])
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_no_false_transitivity(self):
        """A shares email with B; C shares email with D; A,B and C,D should be separate."""
        a = make_record(source="recruiter_csv", emails=["ab@example.com"])
        b = make_record(source="ats_blob",      emails=["ab@example.com"])
        c = make_record(source="recruiter_csv", emails=["cd@example.com"])
        d = make_record(source="ats_blob",      emails=["cd@example.com"])
        clusters = cluster_records([a, b, c, d])
        assert len(clusters) == 2


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def _canonical_repr(self, clusters: list[list[IntermediateRecord]]) -> str:
        """A hashable string representation of cluster membership."""
        cluster_strs = []
        for cluster in clusters:
            members = tuple(sorted(
                (r.source, r.source_file, r.fields.get("full_name", FieldValue("", "", "", False)).normalized or "")
                for r in cluster
            ))
            cluster_strs.append(str(members))
        return str(sorted(cluster_strs))

    def test_shuffle_same_cluster_count(self):
        records = [aarav_csv(), aarav_ats(), aarav_resume(), priya_a(), priya_b()]
        base = cluster_records(records)
        for seed in range(5):
            shuffled = records[:]
            random.Random(seed).shuffle(shuffled)
            result = cluster_records(shuffled)
            assert len(result) == len(base), f"Cluster count changed on seed {seed}"

    def test_shuffle_same_membership(self):
        records = [aarav_csv(), aarav_ats(), aarav_resume(), priya_a(), priya_b()]
        base_repr = self._canonical_repr(cluster_records(records))
        for seed in range(5):
            shuffled = records[:]
            random.Random(seed).shuffle(shuffled)
            result_repr = self._canonical_repr(cluster_records(shuffled))
            assert result_repr == base_repr, f"Cluster membership changed on seed {seed}"

    def test_deterministic_with_many_records(self):
        records = [
            make_record(source="recruiter_csv", emails=[f"user{i}@example.com"])
            for i in range(20)
        ]
        base_repr = self._canonical_repr(cluster_records(records))
        for seed in range(3):
            shuffled = records[:]
            random.Random(seed).shuffle(shuffled)
            assert self._canonical_repr(cluster_records(shuffled)) == base_repr


# ---------------------------------------------------------------------------
# Scale / blocking
# ---------------------------------------------------------------------------

class TestScaleAndBlocking:
    def test_100_unrelated_records_no_false_merges(self):
        records = [
            make_record(emails=[f"unique{i}@example.com"])
            for i in range(100)
        ]
        clusters = cluster_records(records)
        assert len(clusters) == 100

    def test_50_pairs_gives_50_clusters(self):
        records = []
        for i in range(50):
            records.append(make_record(source="recruiter_csv",
                                       emails=[f"pair{i}@example.com"]))
            records.append(make_record(source="ats_blob",
                                       emails=[f"pair{i}@example.com"]))
        clusters = cluster_records(records)
        assert len(clusters) == 50
        for cluster in clusters:
            assert len(cluster) == 2

    def test_records_with_no_keys_each_own_cluster(self):
        """Records with no email/phone/name shouldn't be merged together."""
        # Records that have no usable match keys
        a = IntermediateRecord(source="recruiter_csv", source_file="a.csv")
        b = IntermediateRecord(source="ats_blob",      source_file="b.json")
        clusters = cluster_records([a, b])
        assert len(clusters) == 2


# ---------------------------------------------------------------------------
# Priya Sharma scenario (PRD §10 candidates #3/#4)
# ---------------------------------------------------------------------------

class TestPriyaSharmaPRDScenario:
    """
    PRD §10: Priya Sharma A and B — same full name, different emails + companies.
    Must remain as 2 separate profiles. This is the critical correctness gate.
    """

    def test_priya_pair_stays_separate(self):
        clusters = cluster_records([priya_a(), priya_b()])
        assert len(clusters) == 2

    def test_priya_pair_with_extra_records_stays_separate(self):
        """Adding unrelated records must not accidentally bridge the two Priyas."""
        unrelated = make_record(name="Rohan Mehta", emails=["rohan@example.com"])
        clusters = cluster_records([priya_a(), priya_b(), unrelated])
        assert len(clusters) == 3

    def test_both_priya_clusters_have_exactly_one_record(self):
        clusters = cluster_records([priya_a(), priya_b()])
        sizes = sorted(len(c) for c in clusters)
        assert sizes == [1, 1]
