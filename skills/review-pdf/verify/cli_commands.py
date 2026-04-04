"""Core review-pdf CLI commands: check, batch, iterate.

These are the primary review commands that analyze PDF documents
and produce quality reports.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from .models import DEFAULT_EXTRACTED_RUNS_DIR, DEFAULT_REPORT_DIR, MEMORY_EVENTS_PATH
from .reporting import aggregate_reports, print_summary, write_reports
from .runner import batch_reports
from .utils import append_jsonl
from .cli_helpers import (
    apply_extraction_event_metrics,
    enforce_hard_fail,
    append_aggregate_event,
)


def register_check_commands(app: typer.Typer) -> None:
    """Register check/review/audit commands on the given app."""

    @app.command("check")
    @app.command("review")
    @app.command("audit")
    def cmd_check(
        input_path: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=True),
        output_dir: Optional[Path] = typer.Option(None, help="Output directory"),
        run_id: Optional[str] = typer.Option(None, help="Run identifier"),
        execute_jobs: bool = typer.Option(
            False, help="Execute auto-executable escalation jobs"
        ),
        max_jobs_per_doc: int = typer.Option(
            2, min=0, help="Max executed jobs per document"
        ),
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
            False, help="Ingest each reviewed PDF into graph memory"
        ),
        memory_scope: str = typer.Option(
            "datalake_pdf", help="Memory scope for graph ingestion"
        ),
        taxonomy_collection: Optional[str] = typer.Option(
            None,
            help="Optional taxonomy collection tag: lore|operational|sparta|behavioral",
        ),
        memory_events: Path = typer.Option(
            MEMORY_EVENTS_PATH, help="Mandatory memory summary jsonl sink"
        ),
        include_generated: bool = typer.Option(
            False,
            help="Include generated/result trees (extracted_runs, results*) in discovery",
        ),
        inline_review: bool = typer.Option(
            False,
            help="Run inline persona review loop (Margaret/Jennifer) after each extraction, storing results in /memory",
        ),
        corpus_root: Optional[Path] = typer.Option(
            None,
            help="Corpus root for inline review coverage estimation (defaults to input_path)",
        ),
    ) -> None:
        """Run review on one run directory or on all runs under a root path."""
        run_id = run_id or f"review_pdf_{int(time.time())}"
        out_dir = output_dir or (DEFAULT_REPORT_DIR / run_id)
        _, reports, extraction_events = batch_reports(
            input_path=input_path,
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
        aggregate = aggregate_reports(reports, run_id)
        aggregate["extraction_events"] = extraction_events
        apply_extraction_event_metrics(aggregate, extraction_events)
        artifacts = write_reports(out_dir, reports, aggregate)
        append_aggregate_event(
            run_id=run_id,
            aggregate=aggregate,
            artifacts=artifacts,
            memory_events=memory_events,
            extraction_events=extraction_events,
        )
        print_summary(aggregate, artifacts)
        enforce_hard_fail(aggregate, run_id)


def register_batch_command(app: typer.Typer) -> None:
    """Register batch command on the given app."""

    @app.command("batch")
    def cmd_batch(
        input_dir: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
        output_dir: Optional[Path] = typer.Option(None, help="Output directory"),
        run_id: Optional[str] = typer.Option(None, help="Run identifier"),
        limit: Optional[int] = typer.Option(None, help="Limit number of documents"),
        execute_jobs: bool = typer.Option(
            False, help="Execute auto-executable escalation jobs"
        ),
        max_jobs_per_doc: int = typer.Option(
            1, min=0, help="Max executed jobs per document"
        ),
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
            False, help="Ingest each reviewed PDF into graph memory"
        ),
        memory_scope: str = typer.Option(
            "datalake_pdf", help="Memory scope for graph ingestion"
        ),
        taxonomy_collection: Optional[str] = typer.Option(
            None,
            help="Optional taxonomy collection tag: lore|operational|sparta|behavioral",
        ),
        memory_events: Path = typer.Option(
            MEMORY_EVENTS_PATH, help="Mandatory memory summary jsonl sink"
        ),
        include_generated: bool = typer.Option(
            False,
            help="Include generated/result trees (extracted_runs, results*) in discovery",
        ),
        inline_review: bool = typer.Option(
            False,
            help="Run inline persona review loop (Margaret/Jennifer) after each extraction, storing results in /memory",
        ),
        corpus_root: Optional[Path] = typer.Option(
            None,
            help="Corpus root for inline review coverage estimation (defaults to input_dir)",
        ),
    ) -> None:
        """Run corpus batch review for profile artifacts under a directory."""
        run_id = run_id or f"review_pdf_batch_{int(time.time())}"
        out_dir = output_dir or (DEFAULT_REPORT_DIR / run_id)
        profiles, reports, extraction_events = batch_reports(
            input_path=input_dir,
            run_id=run_id,
            execute_jobs=execute_jobs,
            max_jobs_per_doc=max_jobs_per_doc,
            memory_events_path=memory_events,
            limit=limit,
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
        logger.info(f"review-pdf batch analyzed {len(profiles)} profiles")
        aggregate = aggregate_reports(reports, run_id)
        aggregate["extraction_events"] = extraction_events
        apply_extraction_event_metrics(aggregate, extraction_events)
        artifacts = write_reports(out_dir, reports, aggregate)
        append_aggregate_event(
            run_id=run_id,
            aggregate=aggregate,
            artifacts=artifacts,
            memory_events=memory_events,
            extraction_events=extraction_events,
        )
        print_summary(aggregate, artifacts)
        enforce_hard_fail(aggregate, run_id)


def register_iterate_command(app: typer.Typer) -> None:
    """Register iterate command on the given app."""

    @app.command("iterate")
    def cmd_iterate(
        input_dir: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
        cycles: int = typer.Option(2, min=1, max=8),
        output_dir: Optional[Path] = typer.Option(None, help="Output directory root"),
        run_prefix: str = typer.Option("review_pdf_iter", help="Run id prefix"),
        execute_jobs: bool = typer.Option(True, help="Execute jobs each cycle"),
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
        include_generated: bool = typer.Option(
            False,
            help="Include generated/result trees (extracted_runs, results*) in discovery",
        ),
        inline_review: bool = typer.Option(
            False,
            help="Run inline persona review loop (Margaret/Jennifer) after each extraction, storing results in /memory",
        ),
        corpus_root: Optional[Path] = typer.Option(
            None,
            help="Corpus root for inline review coverage estimation (defaults to input_dir)",
        ),
    ) -> None:
        """Run self-improvement cycles and write convergence history jsonl."""
        root = output_dir or DEFAULT_REPORT_DIR
        history_path = root / f"{run_prefix}_history.jsonl"
        latest_aggregate: dict = {}
        for cycle in range(1, cycles + 1):
            run_id = f"{run_prefix}_c{cycle}_{int(time.time())}"
            cycle_dir = root / run_id
            _, reports, extraction_events = batch_reports(
                input_path=input_dir,
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
            aggregate = aggregate_reports(reports, run_id)
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
            append_jsonl(
                history_path,
                {
                    "timestamp": int(time.time()),
                    "run_id": run_id,
                    "overall_average_score": aggregate["overall_average_score"],
                    "fail_count": aggregate["verdict_counts"].get("FAIL", 0),
                    "warn_count": aggregate["verdict_counts"].get("WARN", 0),
                },
            )
            latest_aggregate = aggregate
            enforce_hard_fail(aggregate, run_id)

        print(f"history_jsonl={history_path}")
        rows = [
            json.loads(line)
            for line in history_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if rows:
            first = rows[0]
            last = rows[-1]
            delta = float(last["overall_average_score"]) - float(
                first["overall_average_score"]
            )
            trend = "IMPROVING" if delta > 0 else ("REGRESSING" if delta < 0 else "STABLE")
            print(f"trend={trend}")
            print(
                f"score_first={first['overall_average_score']} "
                f"score_last={last['overall_average_score']}"
            )

        enforce_hard_fail(latest_aggregate, latest_aggregate.get("run_id", run_prefix))
