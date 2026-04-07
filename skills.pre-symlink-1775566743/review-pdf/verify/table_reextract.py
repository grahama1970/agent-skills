"""Table-density prioritization and re-extraction queue for continuous classifier learning.

When USE_MERGE_CLASSIFIER=true, this module identifies table-heavy PDFs that
lack S05c (merged tables) output and queues them for re-extraction so the
merge classifier can learn from new data.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path

from loguru import logger

from .triage import _slug_for_doc
from .utils import safe_json


def _extract_worker_id(input_path: Path) -> int | None:
    """Extract worker_id from a learn_datalake worker temp dir name.

    Worker dirs are named like /tmp/learn_datalake_worker_3_07msatir.
    Returns None if the path doesn't look like a worker dir.
    """
    m = re.search(r"learn_datalake_worker_(\d+)_", str(input_path))
    return int(m.group(1)) if m else None

# Env-gated: only activate re-extraction queue when classifier is active
TABLE_REEXTRACT_ENABLED = os.environ.get("USE_MERGE_CLASSIFIER", "false").lower() == "true"
TABLE_REEXTRACT_PER_CYCLE = int(os.environ.get("TABLE_REEXTRACT_PER_CYCLE", "10"))


def _read_s00_table_pages(profile_path: Path) -> int:
    """Extract table_pages count from an S00 profile. Returns 0 on any failure."""
    try:
        data = safe_json(profile_path)
        elements = data.get("elements", {})
        return int(elements.get("table_pages", 0))
    except Exception:
        return 0


def _profile_has_s05c(profile_path: Path) -> bool:
    """Check if a profile's run directory has S05c output (merged tables)."""
    run_dir = profile_path.parent.parent  # profile is at <run>/00_profile_detector/profile.json
    # Check both the actual pipeline output path and the legacy path
    s05c_path = run_dir / "05c_table_merger" / "json_output" / "05c_merged_tables.json"
    if s05c_path.exists():
        return True
    # Legacy path (in case of alternate naming)
    s05c_legacy = run_dir / "05c_merged_tables" / "05c_merged_tables.json"
    return s05c_legacy.exists()


def _find_table_heavy_reextraction_candidates(
    profiles: list[Path], max_candidates: int = 10
) -> list[tuple[Path, int]]:
    """Find table-heavy profiles that need re-extraction with the merge classifier.

    Returns list of (source_pdf_path, table_pages) sorted by table_pages descending.
    Only includes profiles that:
    1. Have S00 elements.table_pages >= 3
    2. Do NOT have S05c output (never ran with merge classifier)
    """
    if not TABLE_REEXTRACT_ENABLED:
        return []

    candidates: list[tuple[Path, int]] = []
    for profile_path in profiles:
        tp = _read_s00_table_pages(profile_path)
        if tp < 3:
            continue
        if _profile_has_s05c(profile_path):
            continue
        # Get source PDF path
        data = safe_json(profile_path)
        source = data.get("file")
        if not source or not Path(source).exists():
            continue
        candidates.append((Path(source).resolve(), tp))

    # Sort by table_pages descending — heaviest tables first
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:max_candidates]


def _queue_table_reextractions(
    profiles: list[Path],
    existing_sources: set[str],
    extracted_runs_dir: Path,
    input_path: Path | None = None,
    corpus_root: Path | None = None,
    max_reextracts: int | None = None,
) -> int:
    """Queue table-heavy PDFs for re-extraction with the merge classifier.

    When USE_MERGE_CLASSIFIER=true, this finds table-heavy PDFs without S05c
    output, symlinks them into the worker's input directory so the discovery
    loop naturally picks them up, and removes stale run directories.

    Scans the corpus results directory for profiles (handles worker partitioning).

    Returns the number of PDFs queued for re-extraction.
    """
    if not TABLE_REEXTRACT_ENABLED:
        print("review-pdf table_reextract DISABLED (USE_MERGE_CLASSIFIER not set)", flush=True)
        return 0

    limit = max_reextracts if max_reextracts is not None else TABLE_REEXTRACT_PER_CYCLE
    print(
        f"review-pdf table_reextract_check profiles={len(profiles)} "
        f"corpus_root={corpus_root} limit={limit}",
        flush=True,
    )

    # If profiles list is small (worker partitioning), scan corpus results dir.
    # Cap scan at 5000 to avoid spending too long on startup.
    scan_profiles = list(profiles)
    if len(scan_profiles) < 50 and corpus_root is not None:
        results_dir = corpus_root / "results"
        if results_dir.exists():
            scan_count = 0
            for run_dir in results_dir.iterdir():
                if scan_count >= 5000:
                    break
                if not run_dir.is_dir():
                    continue
                p = run_dir / "00_profile_detector" / "profile.json"
                if p.exists():
                    scan_profiles.append(p)
                    scan_count += 1
            print(f"review-pdf table_reextract_corpus_scan added={scan_count} total={len(scan_profiles)}", flush=True)
        else:
            print(f"review-pdf table_reextract_corpus_scan results_dir_missing={results_dir}", flush=True)
    else:
        print(f"review-pdf table_reextract_skip_corpus_scan profiles={len(scan_profiles)} corpus_root={corpus_root}", flush=True)

    candidates = _find_table_heavy_reextraction_candidates(scan_profiles, max_candidates=limit)
    print(f"review-pdf table_reextract_candidates count={len(candidates)}", flush=True)

    # Partition candidates by worker_id so parallel workers don't all queue the
    # same PDFs (root cause of 79-process fork bomb, 141 GB RAM — 2026-03-03).
    worker_id = _extract_worker_id(input_path) if input_path is not None else None
    if worker_id is not None and len(candidates) > 0:
        # Deterministic partition: hash each candidate path, mod by estimated
        # worker count (use 12 as upper bound — over-partitioning is safe,
        # under-partitioning is not).
        num_buckets = int(os.environ.get("LEARN_DATALAKE_WORKERS", "12"))
        candidates = [
            (p, tp) for p, tp in candidates
            if int(hashlib.md5(str(p).encode()).hexdigest()[:8], 16) % num_buckets == worker_id
        ]
        print(
            f"review-pdf table_reextract_partitioned "
            f"worker_id={worker_id} buckets={num_buckets} owned={len(candidates)}",
            flush=True,
        )

    queued = 0
    for source_pdf, table_pages in candidates:
        resolved = str(source_pdf)
        # Remove from existing so the discovery loop picks it up
        existing_sources.discard(resolved)
        # Also remove the stale run directory so extraction creates fresh output
        slug = _slug_for_doc(source_pdf)
        stale_run = extracted_runs_dir / slug
        if stale_run.exists():
            try:
                if stale_run.is_symlink():
                    target = stale_run.resolve()
                    stale_run.unlink()
                    if target.exists():
                        shutil.rmtree(target, ignore_errors=True)
                else:
                    shutil.rmtree(stale_run, ignore_errors=True)
            except Exception as exc:
                logger.warning(f"Failed to remove stale run for re-extraction: {stale_run}: {exc}")
                continue
        # Symlink the candidate PDF into the worker's input directory so
        # _discover_extractable_files() will find it during the scan.
        if input_path is not None and source_pdf.exists():
            link_dest = input_path / source_pdf.name
            if not link_dest.exists():
                try:
                    link_dest.parent.mkdir(parents=True, exist_ok=True)
                    link_dest.symlink_to(source_pdf)
                except Exception as exc:
                    logger.warning(f"Failed to symlink {source_pdf} into {input_path}: {exc}")
        queued += 1
        print(
            f"review-pdf table_reextract_queued "
            f"table_pages={table_pages} doc={resolved}",
            flush=True,
        )

    if queued > 0:
        print(
            f"review-pdf table_reextract_summary "
            f"queued={queued} classifier=active",
            flush=True,
        )
    return queued
