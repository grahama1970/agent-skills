"""Watch/loop command for continuous PDF quality auditing.

Continuously monitors PDF directories, runs incremental reviews,
handles no-docs auto-debug, and tracks convergence state.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import typer

from .models import DEFAULT_EXTRACTED_RUNS_DIR, DEFAULT_REPORT_DIR, MEMORY_EVENTS_PATH
from .reporting import aggregate_reports, print_summary, write_reports
from .runner import batch_reports
from .utils import append_jsonl, safe_json
from .cli_helpers import (
    apply_extraction_event_metrics,
    hard_fail_reasons,
    enforce_hard_fail,
    append_aggregate_event,
    scan_pdf_state,
    changed_paths,
    dependency_signature,
    watch_meta_path,
    load_watch_meta,
    write_watch_meta,
    collect_no_docs_candidates,
    run_no_docs_auto_debug,
)


def register_loop_command(app: typer.Typer) -> None:
    """Register loop/watch command on the given app."""

    @app.command("loop")
    @app.command("watch")
    def cmd_loop(
        input_dir: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=True),
        output_dir: Optional[Path] = typer.Option(None, help="Output directory root"),
        run_prefix: str = typer.Option("review_pdf_loop", help="Run id prefix"),
        target_score: float = typer.Option(
            0.95, min=0.0, max=1.0, help="Target integrity score"
        ),
        target_fail_ratio: float = typer.Option(
            0.01, min=0.0, max=1.0, help="Acceptable fail ratio before loop marks healthy"
        ),
        watch: bool = typer.Option(
            True, help="Keep running and monitor for new/changed PDFs"
        ),
        poll_seconds: int = typer.Option(
            300, min=5, help="Watch polling interval in seconds"
        ),
        max_cycles: int = typer.Option(0, min=0, help="0 means unbounded loop"),
        execute_jobs: bool = typer.Option(True, help="Execute escalation jobs each cycle"),
        max_jobs_per_doc: int = typer.Option(1, min=0),
        extract_missing: bool = typer.Option(
            True, help="Extract PDFs when S00 profile is missing"
        ),
        extracted_runs_dir: Path = typer.Option(
            DEFAULT_EXTRACTED_RUNS_DIR, help="Where fallback extractor runs are stored"
        ),
        extractor_mode: str = typer.Option(
            "offline", help="Extractor mode: offline|fast|accurate"
        ),
        ingest_memory: bool = typer.Option(
            True, help="Ingest each reviewed PDF into graph memory"
        ),
        memory_scope: str = typer.Option(
            "datalake_pdf", help="Memory scope for graph ingestion"
        ),
        taxonomy_collection: Optional[str] = typer.Option(
            "operational", help="Taxonomy collection tag for review summaries"
        ),
        memory_events: Path = typer.Option(
            MEMORY_EVENTS_PATH, help="Mandatory memory summary jsonl sink"
        ),
        incremental: bool = typer.Option(
            True,
            help="Review only changed PDFs when watch state is available; force full run on code changes",
        ),
        include_generated: bool = typer.Option(
            False,
            help="Include generated/result trees (extracted_runs, results*) in watch/discovery",
        ),
        inline_review: bool = typer.Option(
            False,
            help="Run inline persona review loop (Margaret/Jennifer) after each extraction, storing results in /memory",
        ),
        corpus_root: Optional[Path] = typer.Option(
            None,
            help="Corpus root for inline review coverage estimation (defaults to input_dir)",
        ),
        no_docs_debug_threshold: int = typer.Option(
            1, min=1, help="Trigger automatic no-docs debug when streak reaches this value"
        ),
        auto_debug_max_docs: int = typer.Option(
            3, min=1, max=25, help="Maximum source PDFs captured per no-docs auto-debug run"
        ),
    ) -> None:
        """Continuously audit and improve until target quality; optionally watch for new PDFs."""
        root = output_dir or DEFAULT_REPORT_DIR
        state_path = root / f"{run_prefix}_watch_state.json"
        meta_path = watch_meta_path(root, run_prefix)
        prev_state = safe_json(state_path) if state_path.exists() else {}
        prev_meta = load_watch_meta(meta_path)
        cycle = 0

        while True:
            cycle += 1
            if max_cycles and cycle > max_cycles:
                break

            current_state = scan_pdf_state(
                input_dir,
                include_generated=include_generated,
            )
            changed_path_list = changed_paths(prev_state, current_state)
            changed = len(changed_path_list)
            dep_signature = dependency_signature()
            dep_signature_changed = (
                bool(prev_meta) and prev_meta.get("dependency_signature") != dep_signature
            )
            has_previous_state = bool(prev_state)
            if cycle > 1 and watch and incremental and changed == 0 and not dep_signature_changed:
                print(f"watch cycle={cycle} changed_pdfs=0 sleeping={poll_seconds}s")
                time.sleep(poll_seconds)
                continue
            if (
                not watch
                and incremental
                and has_previous_state
                and changed == 0
                and not dep_signature_changed
            ):
                prior_healthy = bool(prev_meta.get("healthy", False))
                print(
                    "review-pdf incremental_skip "
                    f"cycle={cycle} changed_pdfs=0 prior_healthy={prior_healthy}",
                )
                if prior_healthy:
                    return
                raise typer.Exit(code=1)

            run_id = f"{run_prefix}_c{cycle}_{int(time.time())}"
            cycle_dir = root / run_id
            run_targets: list[Path] = [input_dir]
            incremental_target_cap = min(
                500,
                max(50, int(max(1, len(current_state)) * 0.1)),
            )
            if (
                incremental
                and has_previous_state
                and changed > 0
                and not dep_signature_changed
                and changed <= incremental_target_cap
            ):
                run_targets = changed_path_list
                print(
                    "review-pdf incremental_targets "
                    f"cycle={cycle} count={len(run_targets)}",
                )
            elif (
                incremental
                and has_previous_state
                and changed > 0
                and not dep_signature_changed
            ):
                print(
                    "review-pdf incremental_fallback_full "
                    f"cycle={cycle} changed={changed} "
                    f"cap={incremental_target_cap}",
                )
            elif incremental and dep_signature_changed:
                print(
                    "review-pdf dependency_signature_changed "
                    f"cycle={cycle} forcing_full_run signature={dep_signature}",
                )

            reports: list[dict] = []
            extraction_events: list[dict] = []
            for index, target in enumerate(run_targets, start=1):
                if len(run_targets) > 1:
                    print(
                        "review-pdf target_progress "
                        f"index={index}/{len(run_targets)} target={target}",
                    )
                _, target_reports, target_events = batch_reports(
                    input_path=target,
                    run_id=run_id,
                    execute_jobs=execute_jobs,
                    max_jobs_per_doc=max_jobs_per_doc,
                    memory_events_path=memory_events,
                    extract_missing=extract_missing,
                    extracted_runs_dir=extracted_runs_dir,
                    extractor_mode=extractor_mode,
                    ingest_memory=ingest_memory,
                    memory_scope=memory_scope,
                    taxonomy_collection=taxonomy_collection,
                    include_generated=include_generated,
                    inline_review=inline_review,
                    corpus_root=corpus_root,
                )
                reports.extend(target_reports)
                extraction_events.extend(target_events)

            aggregate = aggregate_reports(reports, run_id)
            aggregate["changed_pdf_count"] = changed if cycle > 1 else len(current_state)
            aggregate["extraction_events"] = extraction_events
            apply_extraction_event_metrics(aggregate, extraction_events)
            artifacts = write_reports(cycle_dir, reports, aggregate)
            append_aggregate_event(
                run_id=run_id,
                aggregate=aggregate,
                artifacts=artifacts,
                memory_events=memory_events,
                extraction_events=extraction_events,
            )
            print_summary(aggregate, artifacts)
            hf_reasons = hard_fail_reasons(aggregate)
            prior_no_docs_streak = int(prev_meta.get("no_docs_streak", 0))
            has_no_docs = "no_documents_analyzed" in hf_reasons
            no_docs_streak = (prior_no_docs_streak + 1) if has_no_docs else 0
            auto_debug_payload: dict = {"status": "not_triggered"}
            if has_no_docs and no_docs_streak >= no_docs_debug_threshold:
                candidates = collect_no_docs_candidates(
                    run_targets=run_targets,
                    extraction_events=extraction_events,
                    current_state=current_state,
                    include_generated=include_generated,
                    max_items=auto_debug_max_docs,
                )
                auto_debug_payload = run_no_docs_auto_debug(
                    candidates=candidates,
                    cycle_dir=cycle_dir,
                    run_id=run_id,
                )
                append_jsonl(
                    memory_events,
                    {
                        "event_type": "review_pdf_no_docs_debug",
                        "timestamp": int(time.time()),
                        "run_id": run_id,
                        "streak": no_docs_streak,
                        "candidate_count": int(auto_debug_payload.get("candidate_count", 0)),
                        "fixture_count": int(auto_debug_payload.get("fixture_count", 0)),
                        "artifact_json": auto_debug_payload.get("artifact_json"),
                    },
                )
                print(
                    "review-pdf auto_debug_no_docs "
                    f"streak={no_docs_streak} "
                    f"candidates={auto_debug_payload.get('candidate_count', 0)} "
                    f"fixtures={auto_debug_payload.get('fixture_count', 0)}",
                )

            fail_count = aggregate["verdict_counts"].get("FAIL", 0)
            analyzed = max(1, aggregate["documents_analyzed"])
            fail_ratio = fail_count / analyzed
            healthy = (
                len(hf_reasons) == 0
                and aggregate["overall_average_score"] >= target_score
                and fail_ratio <= target_fail_ratio
            )
            print(
                f"loop cycle={cycle} healthy={healthy} score={aggregate['overall_average_score']:.4f} "
                f"fail_ratio={fail_ratio:.4f} target_score={target_score:.4f}"
            )

            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(current_state, indent=2), encoding="utf-8")
            write_watch_meta(
                meta_path,
                {
                    "timestamp": int(time.time()),
                    "run_id": run_id,
                    "healthy": healthy,
                    "overall_average_score": aggregate["overall_average_score"],
                    "fail_ratio": fail_ratio,
                    "changed_pdf_count": aggregate["changed_pdf_count"],
                    "documents_analyzed": aggregate["documents_analyzed"],
                    "hard_fail_reasons": hf_reasons,
                    "no_docs_streak": no_docs_streak,
                    "no_docs_debug_threshold": no_docs_debug_threshold,
                    "auto_debug": auto_debug_payload,
                    "dependency_signature": dep_signature,
                    "aggregate_json": str(artifacts["aggregate_json"]),
                },
            )
            prev_state = current_state
            prev_meta = load_watch_meta(meta_path)

            enforce_hard_fail(aggregate, run_id)

            healthy = (
                aggregate["overall_average_score"] >= target_score
                and fail_ratio <= target_fail_ratio
            )

            if not watch:
                if healthy:
                    return
                if max_cycles == 0 or cycle >= max_cycles:
                    raise typer.Exit(code=1)
            elif max_cycles and cycle >= max_cycles and not healthy:
                raise typer.Exit(code=1)
            elif watch:
                time.sleep(poll_seconds)
