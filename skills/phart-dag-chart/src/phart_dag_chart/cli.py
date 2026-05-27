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
) -> None:
    """Render DAG as PHART ASCII decision tree (stdout)."""
    try:
        raw = load_dag_file(dag_file)
        if not no_validate:
            validate_dag(raw, chart_only=True)
        typer.echo(render_chart(raw, validate=not no_validate))
        raise typer.Exit(code=EXIT_OK)
    except DagChartError as exc:
        _emit_error(exc)
        raise typer.Exit(code=EXIT_VALIDATION) from None


def main() -> None:
    app()


if __name__ == "__main__":
    main()
