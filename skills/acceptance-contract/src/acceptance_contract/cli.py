"""Typer CLI for the acceptance-contract skill.

Commands validate external data at the boundary, keep all outputs on disk as
JSON-first artifacts, and call create-report only after the acceptance bundle is
valid. Missing inputs, unsafe zip members, malformed JSON, and report validation
errors fail closed.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger
from pydantic import ValidationError

from .extract import build_bundle, write_json
from .models import AcceptanceBundle, GoalMode
from .reporting import build_report, run_create_report

app = typer.Typer(no_args_is_help=True, add_completion=False)


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def load_bundle(path: Path) -> AcceptanceBundle:
    try:
        return AcceptanceBundle.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        typer.echo(json.dumps({"schema": "acceptance_contract.validation_failure.v1", "errors": exc.errors()}, indent=2), err=True)
        raise typer.Exit(1) from exc


@app.command()
def schema() -> None:
    """Print the acceptance_contract.bundle.v1 JSON schema."""
    typer.echo(json.dumps(AcceptanceBundle.model_json_schema(), indent=2))


@app.command()
def validate(bundle: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)]) -> None:
    """Validate an acceptance bundle JSON file."""
    loaded = load_bundle(bundle)
    typer.echo(json.dumps({"schema": "acceptance_contract.validation_result.v1", "status": "PASS", "requirements": len(loaded.requirements), "open_questions": len(loaded.open_questions)}, indent=2))


@app.command()
def extract(
    input_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory.")] = Path("/tmp/acceptance-contract"),
    project_name: Annotated[str, typer.Option("--project-name", help="Project name for report and goal draft.")] = "project",
    goal_mode: Annotated[GoalMode, typer.Option("--goal-mode", help="create, amend, or none. Always draft-only.")] = GoalMode.CREATE,
) -> None:
    """Extract requirements from a file, directory, or zip bundle."""
    try:
        bundle = build_bundle(input_path.resolve(), project_name, goal_mode)
        out.mkdir(parents=True, exist_ok=True)
        bundle_path = out / "acceptance_bundle.json"
        report_json = out / "acceptance_report.json"
        report_md = out / "acceptance_report.md"
        write_json(bundle_path, bundle)
        report = build_report(bundle)
        write_json(report_json, report)
        if bundle.immutable_goal is not None:
            (out / bundle.immutable_goal.path).write_text(bundle.immutable_goal.markdown, encoding="utf-8")
        run_create_report(skill_dir(), report_json, report_md)
        typer.echo(
            json.dumps(
                {
                    "schema": "acceptance_contract.run_receipt.v1",
                    "status": "PASS",
                    "bundle": str(bundle_path),
                    "report_json": str(report_json),
                    "report_markdown": str(report_md),
                    "goal_draft": str(out / bundle.immutable_goal.path) if bundle.immutable_goal else None,
                    "requirements": len(bundle.requirements),
                    "acceptance_cases": len(bundle.acceptance_cases),
                    "open_questions": len(bundle.open_questions),
                    "goal_policy": "draft_only_human_approval_required",
                },
                indent=2,
            )
        )
    except (OSError, ValueError, ValidationError, subprocess.CalledProcessError) as exc:
        logger.error("acceptance-contract extraction failed: {}", exc)
        typer.echo(json.dumps({"schema": "acceptance_contract.run_receipt.v1", "status": "FAILED", "error": str(exc)}, indent=2), err=True)
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
