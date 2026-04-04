#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "typer>=0.12.0",
#   "loguru>=0.7.0",
# ]
# ///
"""Training datalake ingestion orchestrator.

Purpose:
- assess cross-industry training corpus coverage for extractor improvement.
- plan targeted URL manifests to fill sector and file-type gaps.
- acquire additional corpus content with fetcher into training roots only.

Inputs:
- training corpus root directory.
- optional URL candidate manifest files.

Outputs:
- machine-readable coverage, planning, and acquisition JSON reports.
- manifest text files for fetcher bulk acquisition.

Failure modes:
- exits non-zero when training-root guardrails fail.
- exits non-zero on fetcher failure in strict acquisition paths.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

import typer
from loguru import logger

# Re-export all public names from submodules for backward compatibility
from datalake_config import (
    SKILL_DIR,
    DOGPILE_DIR,
    FETCHER_DIR,
    MEMORY_DIR,
    TAXONOMY_DIR,
    DEFAULT_ALLOWED_ROOT,
    STATE_DIR,
    DEFAULT_MEMORY_EVENTS,
    MEMORY_SCOPE_PREFIX,
    DOC_EXTENSIONS,
    SECTOR_KEYS,
    SECTOR_DOMAIN_HINTS,
    DEFAULT_CANDIDATE_FILES,
)
from datalake_utils import (
    _run,
    _append_jsonl,
    _extract_json_object,
    _is_under,
    _validate_training_root,
    _json_load,
    _json_dump,
)
from datalake_memory import (
    _taxonomy_extract,
    _memory_learn_event,
    _store_report_to_memory,
)
from datalake_coverage import (
    _count_doc_extensions,
    _sector_pdf_counts,
    _sector_pdf_counts_from_source_domains,
    _sector_gap_counts,
    _find_consumer_summaries,
    _summary_items,
    _domain_from_url,
    _sector_for_domain,
    _source_domain_pdf_counts,
    _downloaded_url_set,
    _build_coverage_report,
)
from datalake_planning import (
    _resolve_candidate_files,
    _read_candidate_urls,
    _group_urls_by_sector,
    _write_manifest,
    _select_gap_urls,
)
from datalake_execution import (
    _run_fetcher_manifest,
    _run_cycle_internal,
)

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("assess")
def cmd_assess(
    root: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    target_pdf_per_sector: int = typer.Option(500, min=1),
    allowed_root: Path = typer.Option(
        DEFAULT_ALLOWED_ROOT,
        help="Approved training corpus root (guardrail)",
    ),
    output_json: Path = typer.Option(
        STATE_DIR / "coverage_latest.json",
        help="Coverage report output JSON path",
    ),
    taxonomy_collection: str = typer.Option("operational"),
    store_memory: bool = typer.Option(True),
    require_memory_store: bool = typer.Option(False),
    memory_scope: str = typer.Option("datalake_training_ingest"),
    memory_events: Path = typer.Option(
        DEFAULT_MEMORY_EVENTS,
        help="JSONL sink for memory event auditing",
    ),
) -> None:
    """Assess training corpus sector and file-type coverage."""
    root = _validate_training_root(root, allowed_root)
    report = _build_coverage_report(root, target_pdf_per_sector)
    _json_dump(output_json, report)
    memory_meta = _store_report_to_memory(
        event_type="training_datalake_assess",
        summary_text=(
            "Training datalake coverage assessment for extractor improvement. "
            f"pdf_total={report['totals']['pdf']} "
            f"sectors_below_target={len(report['sectors']['sectors_below_target'])}"
        ),
        payload=report,
        taxonomy_collection=taxonomy_collection,
        store_memory=store_memory,
        require_memory_store=require_memory_store,
        memory_scope=memory_scope,
        memory_events_path=memory_events,
    )
    report["taxonomy"] = memory_meta["taxonomy"]
    report["memory_store"] = memory_meta["memory_store"]
    _json_dump(output_json, report)
    sectors_below = report["sectors"]["sectors_below_target"]
    print(
        f"coverage_report={output_json} "
        f"pdf_total={report['totals']['pdf']} "
        f"sectors_below_target={len(sectors_below)}"
    )
    if sectors_below:
        print("sectors_below_target=" + ",".join(sectors_below))


@app.command("plan")
def cmd_plan(
    root: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    target_pdf_per_sector: int = typer.Option(500, min=1),
    per_sector_limit: int = typer.Option(150, min=1),
    allowed_root: Path = typer.Option(
        DEFAULT_ALLOWED_ROOT,
        help="Approved training corpus root (guardrail)",
    ),
    candidate_file: List[Path] = typer.Option(
        [],
        "--candidate-file",
        help="Additional URL manifest file(s) with one URL per line",
    ),
    output_manifest: Path = typer.Option(
        STATE_DIR / "gap_manifest_urls.txt",
        help="Selected gap URL manifest output path",
    ),
    output_plan_json: Path = typer.Option(
        STATE_DIR / "gap_plan.json",
        help="Gap plan report output JSON path",
    ),
    taxonomy_collection: str = typer.Option("operational"),
    store_memory: bool = typer.Option(True),
    require_memory_store: bool = typer.Option(False),
    memory_scope: str = typer.Option("datalake_training_ingest"),
    memory_events: Path = typer.Option(
        DEFAULT_MEMORY_EVENTS,
        help="JSONL sink for memory event auditing",
    ),
) -> None:
    """Plan URL acquisition manifest to close training corpus sector gaps."""
    root = _validate_training_root(root, allowed_root)
    selection = _select_gap_urls(
        root=root,
        target_pdf_per_sector=target_pdf_per_sector,
        per_sector_limit=per_sector_limit,
        extra_candidate_files=candidate_file,
    )
    selected_urls = selection["selected_urls"]
    _write_manifest(output_manifest, selected_urls)
    plan_payload: Dict[str, Any] = {
        "timestamp": int(time.time()),
        "root": str(root),
        "target_pdf_per_sector": target_pdf_per_sector,
        "per_sector_limit": per_sector_limit,
        "coverage_report": selection["coverage_report"],
        "candidate_files": selection["candidate_files"],
        "candidate_url_count": selection["candidate_url_count"],
        "already_downloaded_url_count": selection["already_downloaded_url_count"],
        "selected_manifest_path": str(output_manifest),
        "selected_url_count": len(selected_urls),
        "selected_by_sector": selection["selected_by_sector"],
        "available_by_sector": selection["available_by_sector"],
    }
    memory_meta = _store_report_to_memory(
        event_type="training_datalake_plan",
        summary_text=(
            "Training datalake gap plan generated. "
            f"selected_url_count={plan_payload['selected_url_count']} "
            f"candidate_url_count={plan_payload['candidate_url_count']}"
        ),
        payload=plan_payload,
        taxonomy_collection=taxonomy_collection,
        store_memory=store_memory,
        require_memory_store=require_memory_store,
        memory_scope=memory_scope,
        memory_events_path=memory_events,
    )
    plan_payload["taxonomy"] = memory_meta["taxonomy"]
    plan_payload["memory_store"] = memory_meta["memory_store"]
    _json_dump(output_plan_json, plan_payload)
    print(
        f"gap_plan={output_plan_json} "
        f"manifest={output_manifest} "
        f"selected_urls={len(selected_urls)}"
    )


@app.command("acquire")
def cmd_acquire(
    manifest_path: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),
    out_dir: Path = typer.Option(
        STATE_DIR / f"expansion_training_{int(time.time())}",
        help="Fetcher output directory",
    ),
    allowed_root: Path = typer.Option(
        DEFAULT_ALLOWED_ROOT,
        help="Approved training corpus root (guardrail)",
    ),
    soft_fail: bool = typer.Option(True, help="Allow partial fetch success"),
    output_json: Path = typer.Option(
        STATE_DIR / "acquire_latest.json",
        help="Acquisition report output JSON path",
    ),
    taxonomy_collection: str = typer.Option("operational"),
    store_memory: bool = typer.Option(True),
    require_memory_store: bool = typer.Option(False),
    memory_scope: str = typer.Option("datalake_training_ingest"),
    memory_events: Path = typer.Option(
        DEFAULT_MEMORY_EVENTS,
        help="JSONL sink for memory event auditing",
    ),
) -> None:
    """Acquire URLs from manifest into the approved training corpus root."""
    _validate_training_root(out_dir, allowed_root)
    proc = _run_fetcher_manifest(manifest_path, out_dir, soft_fail=soft_fail)
    report = {
        "timestamp": int(time.time()),
        "manifest_path": str(manifest_path),
        "out_dir": str(out_dir),
        "soft_fail": soft_fail,
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-50:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-50:]),
    }
    memory_meta = _store_report_to_memory(
        event_type="training_datalake_acquire",
        summary_text=(
            "Training datalake acquisition finished. "
            f"status={report['status']} out_dir={report['out_dir']}"
        ),
        payload=report,
        taxonomy_collection=taxonomy_collection,
        store_memory=store_memory,
        require_memory_store=require_memory_store,
        memory_scope=memory_scope,
        memory_events_path=memory_events,
    )
    report["taxonomy"] = memory_meta["taxonomy"]
    report["memory_store"] = memory_meta["memory_store"]
    _json_dump(output_json, report)
    print(f"acquire_report={output_json} status={report['status']} out_dir={out_dir}")
    if proc.returncode != 0:
        raise typer.Exit(code=1)


@app.command("cycle")
def cmd_cycle(
    root: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    target_pdf_per_sector: int = typer.Option(500, min=1),
    per_sector_limit: int = typer.Option(150, min=1),
    execute_fetch: bool = typer.Option(False, help="Execute fetcher for planned gap manifest"),
    allowed_root: Path = typer.Option(
        DEFAULT_ALLOWED_ROOT,
        help="Approved training corpus root (guardrail)",
    ),
    candidate_file: List[Path] = typer.Option(
        [],
        "--candidate-file",
        help="Additional URL manifest file(s) with one URL per line",
    ),
    output_dir: Path = typer.Option(
        STATE_DIR / "cycles",
        help="Directory for cycle reports",
    ),
    taxonomy_collection: str = typer.Option("operational"),
    store_memory: bool = typer.Option(True),
    require_memory_store: bool = typer.Option(False),
    memory_scope: str = typer.Option("datalake_training_ingest"),
    memory_events: Path = typer.Option(
        DEFAULT_MEMORY_EVENTS,
        help="JSONL sink for memory event auditing",
    ),
) -> None:
    """Run one assess-plan-(optional acquire) cycle for training corpus expansion."""
    root = _validate_training_root(root, allowed_root)
    cycle_id = int(time.time())
    cycle_dir = output_dir / f"cycle_{cycle_id}"
    cycle_dir.mkdir(parents=True, exist_ok=True)

    summary = _run_cycle_internal(
        root=root,
        target_pdf_per_sector=target_pdf_per_sector,
        per_sector_limit=per_sector_limit,
        execute_fetch=execute_fetch,
        candidate_file=candidate_file,
        cycle_dir=cycle_dir,
    )
    memory_meta = _store_report_to_memory(
        event_type="training_datalake_cycle",
        summary_text=(
            "Training datalake cycle completed. "
            f"selected_urls={summary['selected_urls']} "
            f"gap_total_after={summary['gap_total_after']}"
        ),
        payload=summary,
        taxonomy_collection=taxonomy_collection,
        store_memory=store_memory,
        require_memory_store=require_memory_store,
        memory_scope=memory_scope,
        memory_events_path=memory_events,
    )
    summary["taxonomy"] = memory_meta["taxonomy"]
    summary["memory_store"] = memory_meta["memory_store"]
    _json_dump(cycle_dir / "summary.json", summary)
    print(
        f"cycle_dir={cycle_dir} selected_urls={summary['selected_urls']} "
        f"gap_total_after={summary['gap_total_after']} execute_fetch={execute_fetch}"
    )


@app.command("loop")
def cmd_loop(
    root: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    target_pdf_per_sector: int = typer.Option(500, min=1),
    per_sector_limit: int = typer.Option(150, min=1),
    execute_fetch: bool = typer.Option(
        False,
        help="Opt-in: execute fetcher for planned gap manifest",
    ),
    allowed_root: Path = typer.Option(
        DEFAULT_ALLOWED_ROOT,
        help="Approved training corpus root (guardrail)",
    ),
    candidate_file: List[Path] = typer.Option(
        [],
        "--candidate-file",
        help="Additional URL manifest file(s) with one URL per line",
    ),
    output_dir: Path = typer.Option(
        STATE_DIR / "loops",
        help="Directory for loop cycle reports",
    ),
    target_gap_total: int = typer.Option(
        0,
        min=0,
        help="Stop when total remaining sector gap <= this value",
    ),
    max_cycles: int = typer.Option(
        0,
        min=0,
        help="0 means unbounded until convergence target is reached",
    ),
    watch: bool = typer.Option(
        True,
        help="Continue polling after convergence to catch newly added content",
    ),
    poll_seconds: int = typer.Option(300, min=10),
    taxonomy_collection: str = typer.Option("operational"),
    store_memory: bool = typer.Option(True),
    require_memory_store: bool = typer.Option(False),
    memory_scope: str = typer.Option("datalake_training_ingest"),
    memory_events: Path = typer.Option(
        DEFAULT_MEMORY_EVENTS,
        help="JSONL sink for memory event auditing",
    ),
) -> None:
    """Run continuous self-improvement cycles until coverage converges, then optionally watch."""
    root = _validate_training_root(root, allowed_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    cycle_num = 0
    monitor = TaskClient("ingest-training-datalake", total=max_cycles or None) if TaskClient else None

    while True:
        cycle_num += 1
        cycle_dir = output_dir / f"cycle_{int(time.time())}_{cycle_num}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        summary = _run_cycle_internal(
            root=root,
            target_pdf_per_sector=target_pdf_per_sector,
            per_sector_limit=per_sector_limit,
            execute_fetch=execute_fetch,
            candidate_file=candidate_file,
            cycle_dir=cycle_dir,
        )
        memory_meta = _store_report_to_memory(
            event_type="training_datalake_loop_cycle",
            summary_text=(
                "Training datalake loop cycle completed. "
                f"cycle={cycle_num} gap_total_after={summary['gap_total_after']}"
            ),
            payload=summary,
            taxonomy_collection=taxonomy_collection,
            store_memory=store_memory,
            require_memory_store=require_memory_store,
            memory_scope=memory_scope,
            memory_events_path=memory_events,
        )
        summary["taxonomy"] = memory_meta["taxonomy"]
        summary["memory_store"] = memory_meta["memory_store"]
        _json_dump(cycle_dir / "summary.json", summary)

        print(
            f"cycle={cycle_num} cycle_dir={cycle_dir} "
            f"selected_urls={summary['selected_urls']} "
            f"gap_total_after={summary['gap_total_after']}"
        )
        if monitor:
            monitor.update(item=f"cycle_{cycle_num}")

        converged = summary["gap_total_after"] <= target_gap_total
        if converged and not watch:
            print(f"converged=true target_gap_total={target_gap_total}")
            if monitor:
                monitor.finish()
            break
        if converged and watch:
            print(
                f"converged=true watch=true sleeping={poll_seconds}s "
                "for new content/candidate updates"
            )
            time.sleep(poll_seconds)
            continue
        if max_cycles > 0 and cycle_num >= max_cycles:
            print(f"max_cycles_reached={max_cycles} converged=false")
            if monitor:
                monitor.finish()
            raise typer.Exit(code=1)

        time.sleep(poll_seconds)


if __name__ == "__main__":
    app()
