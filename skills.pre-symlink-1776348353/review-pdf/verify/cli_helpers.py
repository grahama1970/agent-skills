"""Helper functions for review-pdf CLI.

Handles PDF state scanning, watch metadata, extraction metrics,
auto-debug logic, and shell command execution.
"""

from __future__ import annotations
import os

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import typer
from loguru import logger

from .utils import append_jsonl, safe_json, to_float

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
PI_MONO_ROOT = _SKILLS_DIR.parent.parent
EXTRACTOR_ROOT = PI_MONO_ROOT.parent / "extractor"
WATCH_META_SUFFIX = "_watch_meta.json"
DEBUG_PDF_DIR = _SKILLS_DIR / "debug-pdf"
FIXTURE_TRICKY_DIR = _SKILLS_DIR / "fixture-tricky"
GENERATED_DIR_NAMES = {
    "extracted_runs",
    "debug_output",
    "reports",
    "results",
}
GENERATED_DIR_PREFIXES = (
    "results_iteration_",
    "results_iter",
)


def apply_extraction_event_metrics(
    aggregate: dict, extraction_events: Optional[list]
) -> None:
    events = extraction_events or []
    failed = sum(1 for event in events if event.get("status") == "extract_failed")
    succeeded = sum(1 for event in events if event.get("status") == "extracted")
    aggregate["extraction_events_count"] = len(events)
    aggregate["extraction_failed_count"] = failed
    aggregate["extraction_succeeded_count"] = succeeded


def hard_fail_reasons(aggregate: dict) -> list[str]:
    reasons: list[str] = []
    if int(aggregate.get("documents_analyzed", 0)) <= 0:
        reasons.append("no_documents_analyzed")
    if int(aggregate.get("extraction_failed_count", 0)) > 0:
        reasons.append(
            f"extraction_failed_count={aggregate['extraction_failed_count']}"
        )
    if int((aggregate.get("verdict_counts") or {}).get("FAIL", 0)) > 0:
        reasons.append(
            f"fail_verdict_count={(aggregate.get('verdict_counts') or {}).get('FAIL', 0)}"
        )
    return reasons


def enforce_hard_fail(aggregate: dict, run_id: str) -> None:
    reasons = hard_fail_reasons(aggregate)
    if not reasons:
        return
    print(f"review-pdf hard_fail run_id={run_id} reasons={';'.join(reasons)}")
    raise typer.Exit(code=1)


def append_aggregate_event(
    *,
    run_id: str,
    aggregate: dict,
    artifacts: dict,
    memory_events: Path,
    extraction_events: Optional[list] = None,
) -> None:
    event = {
        "event_type": "review_pdf_aggregate",
        "timestamp": int(time.time()),
        "run_id": run_id,
        "documents_total": aggregate["documents_total"],
        "documents_analyzed": aggregate["documents_analyzed"],
        "documents_missing": aggregate["documents_missing"],
        "verdict_counts": aggregate["verdict_counts"],
        "overall_average_score": aggregate["overall_average_score"],
        "top_issue_codes": list(aggregate["issue_histogram"].keys())[:15],
        "aggregate_json": str(artifacts["aggregate_json"]),
        "aggregate_md": str(artifacts["aggregate_md"]),
        "extraction_events_count": len(extraction_events or []),
        "extraction_failed_count": int(aggregate.get("extraction_failed_count", 0)),
        "extraction_succeeded_count": int(
            aggregate.get("extraction_succeeded_count", 0)
        ),
    }
    append_jsonl(memory_events, event)


def is_generated_pdf_path(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    for part in parts:
        if part in GENERATED_DIR_NAMES:
            return True
        if any(part.startswith(prefix) for prefix in GENERATED_DIR_PREFIXES):
            return True
    return False


def scan_pdf_state(root: Path, *, include_generated: bool) -> dict[str, float]:
    files = (
        [root]
        if root.is_file() and root.suffix.lower() == ".pdf"
        else sorted(root.rglob("*.pdf"))
    )
    state: dict[str, float] = {}
    for path in files:
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not include_generated and is_generated_pdf_path(resolved):
            continue
        state[str(resolved)] = resolved.stat().st_mtime
    return state


def changed_paths(prev: dict[str, float], curr: dict[str, float]) -> list[Path]:
    changed: list[Path] = []
    for path_str, mtime in curr.items():
        if prev.get(path_str) != mtime:
            changed.append(Path(path_str))
    return sorted(changed)


def changed_count(prev: dict[str, float], curr: dict[str, float]) -> int:
    return len(changed_paths(prev, curr))


def git_head(path: Path) -> str:
    if not path.exists():
        return "missing"
    cmd = f'cd "{path}" && git rev-parse HEAD'
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip() or "unknown"


def dependency_signature() -> str:
    return (
        f"pi_mono:{git_head(PI_MONO_ROOT)}|"
        f"extractor:{git_head(EXTRACTOR_ROOT)}"
    )


def watch_meta_path(root: Path, run_prefix: str) -> Path:
    return root / f"{run_prefix}{WATCH_META_SUFFIX}"


def load_watch_meta(path: Path) -> dict:
    payload = safe_json(path) if path.exists() else {}
    return payload if isinstance(payload, dict) else {}


def write_watch_meta(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def run_shell_command(cmd: str, timeout: int) -> dict:
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-12:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-12:]),
    }


def collect_no_docs_candidates(
    *,
    run_targets: list[Path],
    extraction_events: list[dict],
    current_state: dict[str, float],
    include_generated: bool,
    max_items: int,
) -> list[str]:
    ordered: list[str] = []

    for event in extraction_events:
        pdf_value = event.get("pdf")
        if isinstance(pdf_value, str) and pdf_value:
            ordered.append(pdf_value)

    for target in run_targets:
        if target.is_file() and target.suffix.lower() == ".pdf":
            ordered.append(str(target.resolve()))

    for path_str in sorted(current_state.keys()):
        ordered.append(path_str)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in ordered:
        if item in seen:
            continue
        seen.add(item)
        if is_http_url(item):
            deduped.append(item)
        else:
            local_path = Path(item)
            if not local_path.exists():
                continue
            resolved = local_path.resolve()
            if not include_generated and is_generated_pdf_path(resolved):
                continue
            deduped.append(str(resolved))
        if len(deduped) >= max_items:
            break
    return deduped


def run_no_docs_auto_debug(
    *,
    candidates: list[str],
    cycle_dir: Path,
    run_id: str,
) -> dict:
    auto_dir = (cycle_dir / "auto_debug").resolve()
    fixtures_dir = (auto_dir / "fixtures").resolve()
    auto_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    fixture_count = 0

    for idx, item in enumerate(candidates, start=1):
        if is_http_url(item):
            cmd = (
                f'cd "{DEBUG_PDF_DIR}" && '
                f'./run.sh analyze "{item}" --repro'
            )
            result = run_shell_command(cmd, timeout=3600)
            result["candidate"] = item
            result["mode"] = "debug_pdf_analyze_url"
            results.append(result)
            continue

        local_pdf = Path(item)
        if not local_pdf.exists():
            results.append(
                {
                    "candidate": item,
                    "mode": "local_copy",
                    "status": "missing_source",
                }
            )
            continue

        dest = (fixtures_dir / f"source_{idx:03d}_{local_pdf.name}").resolve()
        try:
            shutil.copy2(local_pdf, dest)
            fixture_count += 1
            results.append(
                {
                    "candidate": item,
                    "mode": "local_copy",
                    "status": "copied",
                    "fixture_path": str(dest),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "candidate": item,
                    "mode": "local_copy",
                    "status": "copy_failed",
                    "error": str(exc),
                }
            )

    gauntlet_path = (fixtures_dir / f"gauntlet_{run_id}.pdf").resolve()
    gauntlet_cmd = (
        f'cd "{FIXTURE_TRICKY_DIR}" && '
        f'./run.sh gauntlet --output "{gauntlet_path}"'
    )
    gauntlet_result = run_shell_command(gauntlet_cmd, timeout=1800)
    gauntlet_result["mode"] = "fixture_tricky_gauntlet"
    if gauntlet_path.exists():
        fixture_count += 1
        gauntlet_result["fixture_path"] = str(gauntlet_path)
    results.append(gauntlet_result)

    payload = {
        "run_id": run_id,
        "timestamp": int(time.time()),
        "candidate_count": len(candidates),
        "fixture_count": fixture_count,
        "results": results,
    }
    output_path = auto_dir / f"no_docs_debug_{run_id}.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["artifact_json"] = str(output_path)
    return payload
