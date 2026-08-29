"""Typer CLI: validate and chart subcommands for DAG JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from phart_dag_chart.chart import render_chart
from phart_dag_chart.dag_validate import validation_report, validate_dag
from phart_dag_chart.errors import DagChartError
from phart_dag_chart.load import load_dag_file
from phart_dag_chart.watch import progress_path_from_options, render_watch_frame, watch_until_terminal

app = typer.Typer(
    name="phart-dag-chart",
    help="Validate ask/scillm DAG JSON and render PHART ASCII decision-tree charts.",
    no_args_is_help=True,
    add_completion=False,
)

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_USAGE = 2


def _emit_error(exc: DagChartError) -> None:
    sys.stderr.write(exc.format_stderr())


def _emit_report(report: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(report, indent=2, sort_keys=True))
        return
    if report.get("ok"):
        typer.echo(
            f"ok: {report.get('node_count', 0)} nodes, {report.get('layer_count', 0)} layers "
            f"(graph_id={report.get('graph_id') or '—'})"
        )
        for warning in report.get("warnings") or []:
            typer.echo(f"warning [{warning.get('code')}]: {warning.get('message')}", err=True)
    else:
        for err in report.get("errors") or []:
            typer.echo(f"error [{err.get('code')}]: {err.get('message')}", err=True)
            if err.get("hint"):
                typer.echo(f"hint: {err['hint']}", err=True)


@app.command("validate")
def cmd_validate(
    dag_file: Annotated[Path, typer.Argument(help="Path to DAG JSON file")],
    json_out: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON report")] = False,
) -> None:
    """Validate DAG structure (schema, deps, cycles) without rendering."""
    try:
        raw = load_dag_file(dag_file)
        report = validation_report(raw, chart_only=True)
        _emit_report(report, as_json=json_out)
        raise typer.Exit(code=EXIT_OK)
    except DagChartError as exc:
        _emit_error(exc)
        report = {
            "ok": False,
            "errors": [{"severity": "error", "code": exc.code, "message": exc.message, **({"hint": exc.hint} if exc.hint else {})}],
            "warnings": [],
        }
        if json_out:
            typer.echo(json.dumps(report, indent=2, sort_keys=True))
        raise typer.Exit(code=EXIT_VALIDATION) from None


@app.command("chart")
def cmd_chart(
    dag_file: Annotated[Path, typer.Argument(help="Path to DAG JSON file")],
    no_validate: Annotated[bool, typer.Option("--no-validate", help="Skip validation (not recommended)")] = False,
    plain: Annotated[bool, typer.Option("--plain", help="Raw ASCII without markdown fences")] = False,
) -> None:
    """Render DAG as PHART ASCII decision tree (stdout)."""
    try:
        raw = load_dag_file(dag_file)
        if not no_validate:
            validate_dag(raw, chart_only=True)
        typer.echo(render_chart(raw, validate=not no_validate, plain=plain))
        raise typer.Exit(code=EXIT_OK)
    except DagChartError as exc:
        _emit_error(exc)
        raise typer.Exit(code=EXIT_VALIDATION) from None


@app.command("watch")
def cmd_watch(
    dag_file: Annotated[Path, typer.Argument(help="Path to DAG JSON file")],
    progress_file: Annotated[
        Path | None,
        typer.Option("--progress", help="Tau dag-progress.json path. Defaults to --run-dir/dag-progress.json."),
    ] = None,
    run_dir: Annotated[Path | None, typer.Option("--run-dir", help="Tau run directory containing dag-progress.json")] = None,
    interval: Annotated[float, typer.Option("--interval", min=0.1, help="Polling interval in seconds")] = 1.0,
    max_seconds: Annotated[float, typer.Option("--max-seconds", min=0.1, help="Maximum watch window")] = 600.0,
    once: Annotated[bool, typer.Option("--once", help="Render one frame and exit without polling")] = False,
    no_clear: Annotated[bool, typer.Option("--no-clear", help="Do not clear the terminal between frames")] = False,
    no_chart: Annotated[bool, typer.Option("--no-chart", help="Hide the PHART ASCII graph; show compact status only")] = False,
) -> None:
    """Watch Tau progress JSON and re-render a compact terminal DAG view."""
    try:
        progress_path = progress_path_from_options(
            dag_file=dag_file,
            run_dir=run_dir,
            progress_file=progress_file,
        )
        if once:
            typer.echo(render_watch_frame(dag_file, progress_path, include_chart=not no_chart))
            raise typer.Exit(code=EXIT_OK)
        status = watch_until_terminal(
            dag_file,
            progress_path,
            interval_seconds=interval,
            max_seconds=max_seconds,
            include_chart=not no_chart,
            clear=not no_clear,
            emit=typer.echo,
        )
        raise typer.Exit(code=EXIT_OK if status == "PASS" else EXIT_VALIDATION)
    except DagChartError as exc:
        _emit_error(exc)
        raise typer.Exit(code=EXIT_VALIDATION) from None


def main() -> None:
    app()


if __name__ == "__main__":
    main()

@app.command("research-round")
def cmd_research_round(
    output: Annotated[Path, typer.Argument(help="Where to write the round DAG JSON")],
    coarse: Annotated[str, typer.Option(help="Comma-separated coarse fanout leaves")] = "web-sweep,github-org,youtube-talks,docs-fetch",
    targeted: Annotated[str, typer.Option(help="Comma-separated targeted fanout leaves")] = "people,stack,bridge,primary-sources",
    chart_after: Annotated[bool, typer.Option("--chart/--no-chart", help="Render the chart to stdout after writing")] = True,
) -> None:
    """Generate a self-expanding research-round DAG - no bespoke code needed.

    Emits the canonical shape: concurrent coarse leaves -> synthesize ->
    refine (role=expansion, authors the targeted queries) -> concurrent
    targeted leaves -> synthesize -> dry-gate (role=gate: settle or compile
    the next linked round) -> ingest -> recall-verify (role=terminal).
    """
    coarse_ids = [c.strip() for c in coarse.split(",") if c.strip()]
    targeted_ids = [t.strip() for t in targeted.split(",") if t.strip()]
    if not coarse_ids or not targeted_ids:
        _emit_error(DagChartError("research-round needs at least one coarse and one targeted leaf"))
        raise typer.Exit(1)
    nodes: list[dict[str, Any]] = []
    for cid in coarse_ids:
        leaf_type = "dogpile.search" if cid == "web-sweep" else "skill.run"
        nodes.append({"id": f"r1-{cid}", "type": leaf_type, "depends_on": []})
    nodes.append({"id": "r1-synthesize", "type": "ask.oracle",
                  "depends_on": [f"r1-{c}" for c in coarse_ids]})
    nodes.append({"id": "r1-refine-questions", "type": "ask.oracle",
                  "role": "expansion", "depends_on": ["r1-synthesize"]})
    for tid in targeted_ids:
        nodes.append({"id": f"r2-{tid}", "type": "dogpile.search",
                      "depends_on": ["r1-refine-questions"]})
    nodes.append({"id": "r2-synthesize", "type": "ask.oracle",
                  "depends_on": [f"r2-{t}" for t in targeted_ids]})
    nodes.append({"id": "dry-gate", "type": "ask.oracle", "role": "gate",
                  "depends_on": ["r2-synthesize"]})
    nodes.append({"id": "chunk-and-ingest", "type": "memory.recall",
                  "depends_on": ["dry-gate"]})
    nodes.append({"id": "recall-verify", "type": "memory.recall",
                  "role": "terminal", "depends_on": ["chunk-and-ingest"]})
    dag = {"schema": "ask.dag.v1", "nodes": nodes}
    validate_dag(dag)
    output.write_text(json.dumps(dag, indent=1) + "\n")
    typer.echo(f"wrote {output} ({len(nodes)} nodes)")
    if chart_after:
        typer.echo(render_chart(dag))

