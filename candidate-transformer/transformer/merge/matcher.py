"""
Identity resolution — groups IntermediateRecords into clusters (one per real person).

Algorithm:
  1. Sort records deterministically (stable integer assignment).
  2. Build blocking index: match_key → list of record indices.
  3. For each bucket with ≥2 records, apply over-merge guard per pair.
     If passes → union in Union-Find.
  4. Collect Union-Find groups → clusters.
  5. Sort clusters + intra-cluster records deterministically.

Match keys (only two — email and phone):
  email:<normalized_email>          — shared email
  phone:<e164_phone>                — shared E.164 phone

Over-merge guard: name+company is NEVER used as a merge criterion.
"Rahul Kumar" at "Infosys" is a completely realistic scenario with Indian names
at large companies. Silently merging two real people is irreversible corruption.
If a record has no email and no phone it stays as a standalone low-confidence
profile. A missed merge (duplicate profiles) is recoverable; a false merge is not.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from transformer.adapters.base import FieldValue, IntermediateRecord
from transformer.models import SOURCE_ORDER
from transformer.normalize.names import name_match_key


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        # Path compression (halving)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        # Always attach the larger root index to the smaller → smaller wins as root.
        # This is deterministic because indices were assigned in a fixed sorted order.
        lo, hi = min(px, py), max(px, py)
        self.parent[hi] = lo

    def groups(self) -> dict[int, list[int]]:
        """Return mapping root → [member indices]."""
        g: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            g[self.find(i)].append(i)
        return dict(g)


# ---------------------------------------------------------------------------
# Key extraction helpers
# ---------------------------------------------------------------------------

def _get_emails(rec: IntermediateRecord) -> frozenset[str]:
    fv = rec.fields.get("emails")
    if fv and fv.ok and fv.normalized:
        return frozenset(fv.normalized)
    return frozenset()


def _get_phones(rec: IntermediateRecord) -> frozenset[str]:
    fv = rec.fields.get("phones")
    if fv and fv.ok and fv.normalized:
        return frozenset(fv.normalized)
    return frozenset()


def _get_name_key(rec: IntermediateRecord) -> str:
    fv = rec.fields.get("full_name")
    if fv and fv.ok and fv.normalized:
        return name_match_key(fv.normalized)
    return ""



def _record_sort_key(rec: IntermediateRecord) -> tuple:
    """Stable sort key for deterministic index assignment."""
    priority = SOURCE_ORDER.index(rec.source) if rec.source in SOURCE_ORDER else 999
    return (priority, rec.source_file, _get_name_key(rec))


# ---------------------------------------------------------------------------
# Over-merge guard
# ---------------------------------------------------------------------------

def _can_merge(a: IntermediateRecord, b: IntermediateRecord) -> bool:
    """
    Return True if records a and b represent the same person.

    Rules:
      - Shared normalized email → YES
      - Shared E.164 phone      → YES
      - No shared email or phone → NO (name+company never used — see module docstring)
    """
    # Shared email
    if _get_emails(a) & _get_emails(b):
        return True

    # Shared phone
    if _get_phones(a) & _get_phones(b):
        return True

    return False


# ---------------------------------------------------------------------------
# Blocking index
# ---------------------------------------------------------------------------

def _build_blocking_keys(rec: IntermediateRecord) -> list[str]:
    """Return all blocking keys for a record (email and phone only)."""
    keys: list[str] = []

    for email in sorted(_get_emails(rec)):      # sorted for determinism
        keys.append(f"email:{email}")

    for phone in sorted(_get_phones(rec)):
        keys.append(f"phone:{phone}")

    return keys


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def cluster_records(records: list[IntermediateRecord]) -> list[list[IntermediateRecord]]:
    """
    Group IntermediateRecords into clusters, one per real person.

    Guarantees:
    - Deterministic: same inputs → identical output regardless of input order.
    - Over-merge guard: name alone never merges two records.
    - Transitive: if A=B and B=C, all three are in one cluster.
    - Scale: blocking index keeps matching ~O(n) rather than O(n²).

    Returns a list of clusters. Each cluster is a sorted list of IntermediateRecords.
    Clusters are sorted by (source_priority, source_file) of their first record.
    """
    if not records:
        return []

    # 1. Sort records deterministically → assign stable integer indices
    sorted_records = sorted(records, key=_record_sort_key)
    n = len(sorted_records)
    uf = _UnionFind(n)

    # 2. Build blocking index: key → sorted list of record indices
    index: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(sorted_records):
        for key in _build_blocking_keys(rec):
            index[key].append(i)

    # 3. For each bucket with ≥2 records, check over-merge guard and union
    for key in sorted(index.keys()):           # sorted key iteration → determinism
        bucket = index[key]
        if len(bucket) < 2:
            continue
        # Compare all pairs within bucket
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                idx_a, idx_b = bucket[i], bucket[j]
                if _can_merge(sorted_records[idx_a], sorted_records[idx_b]):
                    uf.union(idx_a, idx_b)

    # 4. Collect groups from Union-Find
    groups = uf.groups()

    # 5. Build and sort clusters
    clusters: list[list[IntermediateRecord]] = []
    for root in sorted(groups.keys()):         # sorted root order → deterministic cluster order
        member_indices = sorted(groups[root])  # sort member indices → deterministic record order
        cluster = [sorted_records[i] for i in member_indices]
        clusters.append(cluster)

    return clusters
