from __future__ import annotations

from pathlib import Path
from typing import Any

from transformer.adapters.recruiter_csv import RecruiterCSVAdapter
from transformer.adapters.ats_json import ATSJSONAdapter
from transformer.adapters.resume import ResumeAdapter
from transformer.adapters.recruiter_notes import RecruiterNotesAdapter
from transformer.merge.matcher import cluster_records
from transformer.canonical.builder import build_profile
from transformer.project.projector import project


# Adapter instances (created once; each is stateless)
_ADAPTERS = [
    RecruiterCSVAdapter(),
    ATSJSONAdapter(),
    ResumeAdapter(),
    RecruiterNotesAdapter(),
]


def run_pipeline(
    inputs_dir: str | Path,
    config: dict | None = None,
    include_broken: bool = False,
    warnings_out: list[str] | None = None,
) -> list[dict]:
    """
    Run the full candidate transformation pipeline.

    Args:
        inputs_dir:    Directory to walk for input files.
        config:        Optional validated projection config dict.
                       If None, uses the default Eightfold schema.
        include_broken: If False (default), skip any file whose path contains
                       a path component named "broken".
        warnings_out:  Optional list to collect all CanonicalProfile.warnings
                       across all built profiles (used by --verbose CLI flag).

    Returns:
        A list of projected output dicts, sorted by candidate_id for
        deterministic ordering across runs.
    """
    inputs_dir = Path(inputs_dir)

    # --- 1. Discover files ---
    all_files: list[Path] = []
    for path in sorted(inputs_dir.rglob("*")):  # sorted for determinism
        if not path.is_file():
            continue
        if path.name == ".gitkeep":
            continue
        if not include_broken and "broken" in path.parts:
            continue
        all_files.append(path)

    # --- 2. Dispatch to adapters, collect IntermediateRecords ---
    from transformer.adapters.base import IntermediateRecord  # local import for clarity
    all_records: list[IntermediateRecord] = []
    for path in all_files:
        adapter = next((a for a in _ADAPTERS if a.can_handle(path)), None)
        if adapter is None:
            continue  # unrecognised file type — skip silently
        records = adapter.read(path)  # never raises
        all_records.extend(records)

    if not all_records:
        return []

    # --- 3. Cluster ---
    clusters = cluster_records(all_records)

    # --- 4. Build + project ---
    results: list[dict] = []
    for cluster in clusters:
        # Viability check: a cluster must have at least one identity signal
        # (email, phone, or full_name) to constitute a real candidate.
        # Garbage records (e.g. a malformed ATS entry with no fields) are
        # silently skipped here — the adapter already logged warnings on the
        # individual records. This prevents empty "ghost" profiles in the output.
        if not _is_viable_cluster(cluster):
            cluster_warnings = [w for rec in cluster for w in rec.warnings]
            if warnings_out is not None:
                warnings_out.extend(cluster_warnings)
            continue

        profile = build_profile(cluster)
        if warnings_out is not None:
            warnings_out.extend(profile.warnings)
        output = project(profile, config)
        results.append(output)

    # --- 5. Sort deterministically by candidate_id ---
    results.sort(key=lambda d: d.get("candidate_id", ""))

    return results


def _is_viable_cluster(cluster: list) -> bool:
    """
    Return True if the cluster has at least one identity signal.

    A viable cluster must have at least one record with a non-empty, successfully
    normalized email, phone, or full_name. Clusters that fail this check are pure
    garbage (e.g. malformed adapter output) — they should not produce a profile.
    """
    for rec in cluster:
        for field in ("emails", "phones", "full_name"):
            fv = rec.fields.get(field)
            if fv and fv.ok and fv.normalized:
                return True
    return False
