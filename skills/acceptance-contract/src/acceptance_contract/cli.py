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
from .reporting import build_report, progress_summary, run_create_report

app = typer.Typer(no_args_is_help=True, add_completion=False)


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def load_bundle(path: Path) -> AcceptanceBundle:
    try:
        return AcceptanceBundle.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        typer.echo(json.dumps({"schema": "acceptance_contract.validation_failure.v1", "errors": exc.errors()}, indent=2), err=True)
        raise typer.Exit(1) from exc


def write_outputs(bundle: AcceptanceBundle, out: Path) -> tuple[Path, Path, Path, Path | None]:
    out.mkdir(parents=True, exist_ok=True)
    bundle_path = out / "acceptance_bundle.json"
    report_json = out / "acceptance_report.json"
    report_md = out / "acceptance_report.md"
    write_json(bundle_path, bundle)
    report = build_report(bundle)
    write_json(report_json, report)
    goal_path = None
    if bundle.immutable_goal is not None:
        goal_path = out / bundle.immutable_goal.path
        goal_path.write_text(bundle.immutable_goal.markdown, encoding="utf-8")
    run_create_report(skill_dir(), report_json, report_md)
    return bundle_path, report_json, report_md, goal_path


def receipt(status: str, bundle_path: Path, report_json: Path, report_md: Path, goal_path: Path | None, bundle: AcceptanceBundle, *, action: str) -> dict[str, object]:
    return {
        "schema": "acceptance_contract.run_receipt.v1",
        "status": status,
        "action": action,
        "bundle": str(bundle_path),
        "report_json": str(report_json),
        "report_markdown": str(report_md),
        "goal_draft": str(goal_path) if goal_path else None,
        "source_sha256": bundle.source.sha256,
        "requirements": len(bundle.requirements),
        "acceptance_cases": len(bundle.acceptance_cases),
        "open_questions": len(bundle.open_questions),
        "progress": progress_summary(bundle),
        "goal_policy": "draft_only_human_approval_required",
    }


@app.command()
def schema() -> None:
    """Print the acceptance_contract.bundle.v1 JSON schema."""
    typer.echo(json.dumps(AcceptanceBundle.model_json_schema(), indent=2))


@app.command()
def validate(bundle: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)]) -> None:
    """Validate an acceptance bundle JSON file."""
    loaded = load_bundle(bundle)
    typer.echo(json.dumps({"schema": "acceptance_contract.validation_result.v1", "status": "PASS", "requirements": len(loaded.requirements), "open_questions": len(loaded.open_questions), "progress": progress_summary(loaded)}, indent=2))


@app.command()
def status(bundle: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)]) -> None:
    """Print the machine-readable progress meter for an acceptance bundle."""
    loaded = load_bundle(bundle)
    typer.echo(json.dumps(progress_summary(loaded), indent=2))


@app.command()
def extract(
    input_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory.")] = Path("/tmp/acceptance-contract"),
    project_name: Annotated[str, typer.Option("--project-name", help="Project name for report and goal draft.")] = "project",
    goal_mode: Annotated[GoalMode, typer.Option("--goal-mode", help="create, amend, or none. Always draft-only.")] = GoalMode.CREATE,
    allow_repo: Annotated[bool, typer.Option("--allow-repo", help="Allow a repository root as source. Off by default to prevent implementation-derived contracts.")] = False,
) -> None:
    """Extract requirements from a file, directory, or zip bundle."""
    try:
        bundle = build_bundle(input_path.resolve(), project_name, goal_mode, allow_repo=allow_repo)
        bundle_path, report_json, report_md, goal_path = write_outputs(bundle, out)
        typer.echo(json.dumps(receipt("PASS", bundle_path, report_json, report_md, goal_path, bundle, action="extracted"), indent=2))
    except (OSError, ValueError, ValidationError, subprocess.CalledProcessError) as exc:
        logger.error("acceptance-contract extraction failed: {}", exc)
        typer.echo(json.dumps({"schema": "acceptance_contract.run_receipt.v1", "status": "FAILED", "error": str(exc)}, indent=2), err=True)
        raise typer.Exit(1) from exc


@app.command()
def ensure(
    input_path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory that must contain or receive acceptance_bundle.json.")] = Path("/tmp/acceptance-contract"),
    project_name: Annotated[str, typer.Option("--project-name", help="Project name for report and goal draft.")] = "project",
    goal_mode: Annotated[GoalMode, typer.Option("--goal-mode", help="create, amend, or none. Always draft-only.")] = GoalMode.CREATE,
    allow_repo: Annotated[bool, typer.Option("--allow-repo", help="Allow a repository root as source. Off by default to prevent implementation-derived contracts.")] = False,
) -> None:
    """Validate an existing frozen contract or extract it when missing."""
    try:
        expected = build_bundle(input_path.resolve(), project_name, goal_mode, allow_repo=allow_repo)
        bundle_path = out / "acceptance_bundle.json"
        if not bundle_path.exists():
            written_bundle, report_json, report_md, goal_path = write_outputs(expected, out)
            typer.echo(json.dumps(receipt("PASS", written_bundle, report_json, report_md, goal_path, expected, action="created_missing_contract"), indent=2))
            return
        loaded = load_bundle(bundle_path)
        if loaded.source.sha256 != expected.source.sha256:
            raise ValueError(f"stale acceptance contract: {bundle_path} source_sha256={loaded.source.sha256} expected={expected.source.sha256}")
        report_json = out / "acceptance_report.json"
        report_md = out / "acceptance_report.md"
        goal_path = out / loaded.immutable_goal.path if loaded.immutable_goal else None
        typer.echo(json.dumps(receipt("PASS", bundle_path, report_json, report_md, goal_path, loaded, action="validated_existing_contract"), indent=2))
    except (OSError, ValueError, ValidationError, subprocess.CalledProcessError) as exc:
        logger.error("acceptance-contract ensure failed: {}", exc)
        typer.echo(json.dumps({"schema": "acceptance_contract.run_receipt.v1", "status": "FAILED", "error": str(exc)}, indent=2), err=True)
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
