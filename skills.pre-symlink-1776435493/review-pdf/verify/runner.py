"""Audit orchestration for review-pdf.

Purpose:
- run per-document audits and assemble results for batch/iterate workflows.

Inputs:
- profile artifact paths, run identifiers, execution options.

Outputs:
- document-level report dicts with issues, dimensions, escalations, and memory events.

Failure modes:
- missing structural artifacts return explicit missing status records.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from loguru import logger

from .analysis import (
    analyze_flattened_data,
    analyze_pdf_source,
    analyze_s11_structural,
    analyze_sections_data,
    collect_profiles,
    extract_s00_estimates,
    resolve_doc_inputs,
)
from .discovery import ensure_profiles, filter_profiles
from .escalation import escalation_jobs, run_jobs
from .models import DEFAULT_EXTRACTED_RUNS_DIR, Issue
from .scoring import build_issues, dimension_scores, overall_from_dimensions
from .utils import append_jsonl, detect_domain, doc_id_from_path, safe_json

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent


def _memory_summary(
    *,
    run_id: str,
    report: Dict[str, Any],
    issues: List[Issue],
    escalation_skills: List[str],
) -> Dict[str, Any]:
    return {
        "event_type": "review_pdf_summary",
        "timestamp": report["timestamp"],
        "run_id": run_id,
        "doc_id": report["doc_id"],
        "domain": report["domain"],
        "verdict": report["overall"]["verdict"],
        "grade": report["overall"]["grade"],
        "score": report["overall"]["score"],
        "issue_codes": [issue.code for issue in issues],
        "critical_issues": report["overall"]["critical_issues"],
        "high_issues": report["overall"]["high_issues"],
        "report_ref": {
            "run_dir": report["inputs"]["run_dir"],
            "profile_path": report["inputs"]["profile_path"],
            "structural_path": report["inputs"]["structural_path"],
        },
        "escalation_skills": escalation_skills,
    }


def _memory_acquire(pdf_path: Path, memory_scope: str) -> Dict[str, Any]:
    cmd = (
        f"cd {_SKILLS_DIR}/memory && "
        f'./run.sh acquire content "{pdf_path}" --scope "{memory_scope}"'
    )
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-10:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-10:]),
    }


def _taxonomy_extract(summary_text: str, taxonomy_collection: str) -> Dict[str, Any]:
    cmd = (
        f"cd {_SKILLS_DIR}/taxonomy && "
        f"./run.sh extract --text {json.dumps(summary_text)} --collection {taxonomy_collection} --fast"
    )
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    if proc.returncode != 0:
        return {"status": "failed", "returncode": proc.returncode}
    try:
        return {"status": "ok", "result": json.loads(proc.stdout)}
    except Exception:
        return {"status": "failed", "parse_error": True}


def _update_lesson_taxonomy_post_acquire(memory_scope: str, pdf_path: Path) -> None:
    """After memory acquire, ensure stored lessons have taxonomy.

    Runs a fast taxonomy sweep on lessons matching the scope+pdf that may
    have been stored without bridge_attributes by the acquire pipeline.
    """
    cmd = (
        f"cd {_SKILLS_DIR}/taxonomy && "
        f'./run.sh sweep --collection lessons --scope "{memory_scope}" '
        f'--mode keyword --limit 100'
    )
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    if proc.returncode != 0:
        logger.warning(f"taxonomy post-acquire sweep failed: rc={proc.returncode}")


def single_report(
    *,
    profile_path: Path,
    run_id: str,
    execute_jobs: bool,
    max_jobs: int,
    memory_events_path: Path,
    ingest_memory: bool = False,
    memory_scope: str = "datalake_pdf",
    taxonomy_collection: str | None = None,
) -> Dict[str, Any]:
    """Run one document audit from one S00 profile.json."""
    inputs = resolve_doc_inputs(profile_path)
    run_dir = inputs["run_dir"]
    structural_path = inputs["structural_path"]
    flattened_path = inputs.get("flattened_path")
    sections_path = inputs.get("sections_path")
    if structural_path is None and flattened_path is None and sections_path is None:
        return {
            "run_dir": str(run_dir),
            "profile_path": str(profile_path),
            "status": "missing_structural",
        }

    profile = safe_json(profile_path)
    context = safe_json(inputs["context_path"])
    source = analyze_pdf_source(inputs["pdf_path"])
    estimates = extract_s00_estimates(profile, context)

    if structural_path is not None:
        structural = safe_json(structural_path)
        actual = analyze_s11_structural(structural)
    elif flattened_path is not None:
        flattened = safe_json(flattened_path)
        if isinstance(flattened, dict):
            flattened = flattened.get("data", flattened.get("items", []))
        if not isinstance(flattened, list):
            flattened = []
        actual = analyze_flattened_data(flattened)
    else:
        sections = safe_json(sections_path)
        actual = analyze_sections_data(sections)
    issues, ratio_metrics = build_issues(estimates, actual, source)
    dimensions = dimension_scores(estimates, actual, source, ratio_metrics)
    overall = overall_from_dimensions(dimensions, issues)
    domain = detect_domain(inputs["pdf_path"], run_dir)
    doc_id = doc_id_from_path(inputs["pdf_path"], run_dir)
    jobs = escalation_jobs(issues, inputs["pdf_path"], run_dir)

    execution_results: List[Dict[str, Any]] = []
    if execute_jobs and jobs:
        execution_results = run_jobs(jobs, max_jobs=max_jobs)

    memory_ingest_result: Dict[str, Any] = {"status": "not_requested"}
    if ingest_memory and inputs["pdf_path"] is not None:
        if overall["verdict"] != "FAIL":
            memory_ingest_result = _memory_acquire(inputs["pdf_path"], memory_scope)
            # Pass taxonomy to stored lesson if review-pdf extracted it
            if memory_ingest_result.get("status") == "ok" and taxonomy_collection:
                try:
                    _update_lesson_taxonomy_post_acquire(memory_scope, inputs["pdf_path"])
                except Exception as e:
                    logger.warning(f"taxonomy post-acquire failed: {e}") if 'logger' in dir() else None
        else:
            memory_ingest_result = {
                "status": "skipped_quality_gate",
                "verdict": overall["verdict"],
                "grade": overall["grade"],
                "score": overall["score"],
            }

    timestamp = int(time.time())
    report = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "timestamp": timestamp,
        "doc_id": doc_id,
        "domain": domain,
        "inputs": {
            "run_dir": str(run_dir),
            "profile_path": str(profile_path),
            "structural_path": str(structural_path or flattened_path),
            "context_path": str(inputs["context_path"])
            if inputs["context_path"]
            else None,
            "pdf_path": str(inputs["pdf_path"]) if inputs["pdf_path"] else None,
        },
        "estimates": estimates,
        "actual": actual,
        "source_pdf": source,
        "ratios": ratio_metrics,
        "dimensions": dimensions,
        "overall": overall,
        "issues": [issue.as_dict() for issue in issues],
        "escalation_jobs": [job.as_dict() for job in jobs],
        "escalation_execution": execution_results,
        "memory_ingest": memory_ingest_result,
    }
    if taxonomy_collection:
        summary_text = (
            f"domain={domain}; verdict={overall['verdict']}; grade={overall['grade']}; "
            f"issues={[issue.code for issue in issues]}; "
            f"type_counts={actual.get('type_counts', {})}"
        )
        report["taxonomy"] = _taxonomy_extract(summary_text, taxonomy_collection)

    memory_event = _memory_summary(
        run_id=run_id,
        report=report,
        issues=issues,
        escalation_skills=sorted({job.skill for job in jobs}),
    )
    append_jsonl(memory_events_path, memory_event)
    return report


def batch_reports(
    *,
    input_path: Path,
    run_id: str,
    execute_jobs: bool,
    max_jobs_per_doc: int,
    memory_events_path: Path,
    limit: int | None = None,
    extract_missing: bool = False,
    extracted_runs_dir: Path = DEFAULT_EXTRACTED_RUNS_DIR,
    extractor_mode: str = "offline",
    ingest_memory: bool = False,
    memory_scope: str = "datalake_pdf",
    taxonomy_collection: str | None = None,
    include_generated: bool = False,
    inline_review: bool = False,
    corpus_root: Path | None = None,
) -> Tuple[List[Path], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run audits across all discovered profile paths under input path."""
    # Support INLINE_REVIEW=true env var alongside --inline-review flag
    if not inline_review and os.environ.get("INLINE_REVIEW", "").lower() in ("1", "true", "yes"):
        inline_review = True
    print(
        "review-pdf discover_profiles "
        f"root={input_path} limit={limit if limit is not None else 'none'}",
        flush=True,
    )
    profiles = filter_profiles(
        collect_profiles(input_path, limit=limit),
        include_generated=include_generated,
    )
    print(f"review-pdf discovered_profiles count={len(profiles)}", flush=True)
    max_new_profiles = None if limit is None else max(0, limit - len(profiles))
    profiles, extraction_events = ensure_profiles(
        input_path=input_path,
        profiles=profiles,
        extract_missing=extract_missing,
        extracted_runs_dir=extracted_runs_dir,
        extractor_mode=extractor_mode,
        max_new_profiles=max_new_profiles,
        include_generated=include_generated,
        inline_review=inline_review,
        corpus_root=corpus_root if corpus_root is not None else input_path,
        inline_review_run_id=run_id,
    )
    if limit is not None:
        profiles = profiles[: max(0, limit)]
    reports: List[Dict[str, Any]] = []
    total_profiles = len(profiles)
    for index, profile in enumerate(profiles, start=1):
        if index == 1 or index % 25 == 0 or index == total_profiles:
            print(
                "review-pdf analyze_progress "
                f"analyzed={index-1} total={total_profiles} "
                f"next_profile={profile}",
                flush=True,
            )
        reports.append(
            single_report(
                profile_path=profile,
                run_id=run_id,
                execute_jobs=execute_jobs,
                max_jobs=max_jobs_per_doc,
                memory_events_path=memory_events_path,
                ingest_memory=ingest_memory,
                memory_scope=memory_scope,
                taxonomy_collection=taxonomy_collection,
            )
        )
        if index == 1 or index % 25 == 0 or index == total_profiles:
            print(
                "review-pdf analyze_progress "
                f"analyzed={index} total={total_profiles}",
                flush=True,
            )
    return profiles, reports, extraction_events
