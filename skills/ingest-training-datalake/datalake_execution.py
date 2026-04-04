"""Fetcher and cycle execution for training datalake ingestion."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from loguru import logger

from datalake_config import FETCHER_DIR
from datalake_coverage import _build_coverage_report
from datalake_planning import _select_gap_urls, _write_manifest
from datalake_utils import _json_dump, _run


def _run_fetcher_manifest(manifest_path: Path, out_dir: Path, soft_fail: bool) -> subprocess.CompletedProcess[str]:
    cmd = (
        f"cd {FETCHER_DIR} && ./run.sh get-manifest \"{manifest_path}\" "
        f"--out \"{out_dir}\" {'--soft-fail' if soft_fail else ''}"
    )
    return _run(cmd, timeout=21600)


def _run_cycle_internal(
    *,
    root: Path,
    target_pdf_per_sector: int,
    per_sector_limit: int,
    execute_fetch: bool,
    candidate_file: List[Path],
    cycle_dir: Path,
) -> Dict[str, Any]:
    coverage_before = _build_coverage_report(root, target_pdf_per_sector)
    gap_total_before = int(sum(coverage_before["sectors"]["pdf_gap_counts"].values()))

    coverage_path = cycle_dir / "coverage_before.json"
    gap_manifest_path = cycle_dir / "gap_manifest_urls.txt"
    gap_plan_path = cycle_dir / "gap_plan.json"
    acquire_path = cycle_dir / "acquire.json"
    coverage_after_path = cycle_dir / "coverage_after.json"

    _json_dump(coverage_path, coverage_before)

    selection = _select_gap_urls(
        root=root,
        target_pdf_per_sector=target_pdf_per_sector,
        per_sector_limit=per_sector_limit,
        extra_candidate_files=candidate_file,
    )
    _write_manifest(gap_manifest_path, selection["selected_urls"])
    gap_payload = {
        "timestamp": int(time.time()),
        "root": str(root),
        "target_pdf_per_sector": target_pdf_per_sector,
        "per_sector_limit": per_sector_limit,
        "coverage_report": selection["coverage_report"],
        "candidate_files": selection["candidate_files"],
        "candidate_url_count": selection["candidate_url_count"],
        "already_downloaded_url_count": selection["already_downloaded_url_count"],
        "selected_manifest_path": str(gap_manifest_path),
        "selected_url_count": len(selection["selected_urls"]),
        "selected_by_sector": selection["selected_by_sector"],
        "available_by_sector": selection["available_by_sector"],
    }
    _json_dump(gap_plan_path, gap_payload)

    acquire_report: Optional[Dict[str, Any]] = None
    if execute_fetch and selection["selected_urls"]:
        fetch_out_dir = root / f"expansion_training_{int(time.time())}"
        proc = _run_fetcher_manifest(gap_manifest_path, fetch_out_dir, soft_fail=True)
        acquire_report = {
            "timestamp": int(time.time()),
            "manifest_path": str(gap_manifest_path),
            "out_dir": str(fetch_out_dir),
            "soft_fail": True,
            "status": "ok" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "stdout_tail": "\n".join(proc.stdout.splitlines()[-50:]),
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-50:]),
        }
        _json_dump(acquire_path, acquire_report)
        if proc.returncode != 0:
            logger.error("fetcher acquisition failed during cycle")
            raise typer.Exit(code=1)

    coverage_after = _build_coverage_report(root, target_pdf_per_sector)
    gap_total_after = int(sum(coverage_after["sectors"]["pdf_gap_counts"].values()))
    _json_dump(coverage_after_path, coverage_after)

    summary = {
        "timestamp": int(time.time()),
        "root": str(root),
        "cycle_dir": str(cycle_dir),
        "coverage_before": str(coverage_path),
        "coverage_after": str(coverage_after_path),
        "gap_plan": str(gap_plan_path),
        "gap_manifest": str(gap_manifest_path),
        "selected_urls": len(selection["selected_urls"]),
        "execute_fetch": execute_fetch,
        "acquire_report": str(acquire_path) if acquire_report is not None else None,
        "gap_total_before": gap_total_before,
        "gap_total_after": gap_total_after,
    }
    _json_dump(cycle_dir / "summary.json", summary)
    return summary
