"""Typer CLI for review-pdf.

Purpose:
- expose single-doc, batch, iterative, compare, and history commands.

Inputs:
- run dirs / profile paths and optional execution/report flags.

Outputs:
- report artifacts and non-zero exit on FAIL-level quality outcomes.

Failure modes:
- invalid paths, malformed history files, and FAIL verdicts return non-zero exit.

This is the assembler module. Implementation lives in:
- cli_helpers.py: Helper functions and PDF state scanning
- cli_commands.py: check, batch, iterate commands
- cli_watch.py: loop/watch command
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from .models import MEMORY_EVENTS_PATH
from .utils import safe_json, to_float

# Re-export for backward compatibility
from .cli_helpers import (
    apply_extraction_event_metrics,
    hard_fail_reasons,
    enforce_hard_fail,
    append_aggregate_event,
    is_generated_pdf_path,
    scan_pdf_state,
    changed_paths,
    changed_count,
    dependency_signature,
    watch_meta_path,
    load_watch_meta,
    write_watch_meta,
    is_http_url,
    run_shell_command,
    collect_no_docs_candidates,
    run_no_docs_auto_debug,
    PI_MONO_ROOT,
    EXTRACTOR_ROOT,
    WATCH_META_SUFFIX,
    DEBUG_PDF_DIR,
    FIXTURE_TRICKY_DIR,
    GENERATED_DIR_NAMES,
    GENERATED_DIR_PREFIXES,
)

app = typer.Typer(no_args_is_help=True, add_completion=False)

# Register commands from sub-modules
from .cli_commands import register_check_commands, register_batch_command, register_iterate_command
from .cli_watch import register_loop_command

register_check_commands(app)
register_batch_command(app)
register_iterate_command(app)
register_loop_command(app)


@app.command("compare")
def cmd_compare(
    aggregate_a: Path = typer.Argument(..., exists=True, dir_okay=False),
    aggregate_b: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Compare two aggregate json reports."""
    a = safe_json(aggregate_a)
    b = safe_json(aggregate_b)
    a_fail = int((a.get("verdict_counts") or {}).get("FAIL", 0))
    b_fail = int((b.get("verdict_counts") or {}).get("FAIL", 0))
    a_score = to_float(a.get("overall_average_score"), 0.0)
    b_score = to_float(b.get("overall_average_score"), 0.0)
    print("review-pdf compare")
    print(f"a={aggregate_a}")
    print(f"b={aggregate_b}")
    print(f"score_a={a_score:.4f} score_b={b_score:.4f} delta={b_score - a_score:+.4f}")
    print(f"fail_a={a_fail} fail_b={b_fail} delta={b_fail - a_fail:+d}")


@app.command("convergence")
def cmd_convergence(
    history_jsonl: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Read history jsonl and summarize score/fail deltas."""
    rows = [
        json.loads(line)
        for line in history_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        print("no history rows")
        raise typer.Exit(code=1)
    first = rows[0]
    last = rows[-1]
    delta_score = to_float(last.get("overall_average_score")) - to_float(
        first.get("overall_average_score")
    )
    delta_fail = int(last.get("fail_count", 0)) - int(first.get("fail_count", 0))
    if delta_score == 0 and delta_fail == 0:
        trend = "STABLE"
    elif delta_score > 0 and delta_fail <= 0:
        trend = "IMPROVING"
    else:
        trend = "REGRESSING"
    print("review-pdf convergence")
    print(f"history={history_jsonl}")
    print(f"runs={len(rows)}")
    print(f"trend={trend}")
    print(f"score_delta={delta_score:+.4f}")
    print(f"fail_delta={delta_fail:+d}")


@app.command("status")
def cmd_status(
    aggregate_json: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Show one-line status from aggregate report."""
    aggregate = safe_json(aggregate_json)
    verdicts = aggregate.get("verdict_counts", {})
    print("review-pdf status")
    print(f"run_id={aggregate.get('run_id')}")
    print(f"documents_analyzed={aggregate.get('documents_analyzed')}")
    print(f"overall_average_score={aggregate.get('overall_average_score')}")
    print(
        "verdicts="
        f"PASS:{verdicts.get('PASS', 0)} "
        f"WARN:{verdicts.get('WARN', 0)} "
        f"FAIL:{verdicts.get('FAIL', 0)}"
    )


@app.command("history")
def cmd_history(
    memory_events: Path = typer.Option(
        MEMORY_EVENTS_PATH, help="Memory summary event log path"
    ),
    limit: int = typer.Option(20, min=1, max=500),
) -> None:
    """Show recent memory summary events for review-pdf."""
    if not memory_events.exists():
        print(f"no memory events at {memory_events}")
        return
    rows = [
        json.loads(line)
        for line in memory_events.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summary_rows = [
        row for row in rows if row.get("event_type") == "review_pdf_summary"
    ]
    for row in summary_rows[-limit:]:
        print(
            f"{row.get('timestamp')} "
            f"run_id={row.get('run_id')} "
            f"doc_id={row.get('doc_id')} "
            f"verdict={row.get('verdict')} "
            f"score={row.get('score')}"
        )
