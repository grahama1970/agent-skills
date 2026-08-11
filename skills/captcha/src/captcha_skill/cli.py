"""Typer CLI for the authorized local-only CAPTCHA evaluation skill.

The default invocation is read-only status so Ask may safely discover and call
the skill without inventing arguments. Live evaluation additionally requires a
valid manifest and the explicit ``--execute`` flag.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from pydantic import BaseModel, ValidationError

from .constants import DEFAULT_OUTPUT_ROOT, DEFAULT_RECAP_ROOT, DEFAULT_STORAGE_ROOT
from .errors import CaptchaSkillError, ErrorCode
from .models import EvaluationAction, RunStatus
from .policy import load_manifest, validate_authorization, write_json_atomic
from .schemas import export_schemas
from .runtime import (
    build_ask_dag,
    build_evaluation_plan,
    default_recap_python,
    execute_evaluation,
    status_report,
    verify_run,
)

app = typer.Typer(
    name="captcha",
    help=(
        "Authorization-gated ReCAP security evaluation for synthetic dynamic "
        "CAPTCHAs on loopback only."
    ),
    no_args_is_help=False,
    add_completion=False,
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _emit(value: Any, *, json_output: bool) -> None:
    payload = _jsonable(value)
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return
    if isinstance(payload, dict):
        status = payload.get("status", "UNKNOWN")
        typer.echo(f"STATUS: {status}")
        for key, item in payload.items():
            if key == "status":
                continue
            if isinstance(item, (dict, list)):
                rendered = json.dumps(item, indent=2, sort_keys=True, ensure_ascii=False)
                typer.echo(f"{key.upper()}: {rendered}")
            else:
                typer.echo(f"{key.upper()}: {item}")
    else:
        typer.echo(str(payload))


def _abort(error: CaptchaSkillError, *, json_output: bool) -> None:
    logger.error("{}: {}", error.code.value, error.message)
    _emit(error.as_dict(), json_output=json_output)
    raise typer.Exit(code=error.exit_code)


def _validation_error(error: ValidationError) -> CaptchaSkillError:
    return CaptchaSkillError(
        ErrorCode.INVALID_MANIFEST,
        "typed contract validation failed",
        {"errors": error.errors(include_url=False)},
    )


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit JSON."),
) -> None:
    """Default safely to a zero-network readiness report."""

    if ctx.invoked_subcommand is not None:
        return
    try:
        report = status_report()
        _emit(report, json_output=json_output)
    except CaptchaSkillError as exc:
        _abort(exc, json_output=json_output)


@app.command("status")
def status_command(
    recap_root: Path = typer.Option(DEFAULT_RECAP_ROOT, "--recap-root"),
    recap_python: Path | None = typer.Option(None, "--recap-python"),
    storage_root: Path = typer.Option(DEFAULT_STORAGE_ROOT, "--storage-root"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Report Ask, Surf, ReCAP, runtime, and storage readiness."""

    try:
        report = status_report(
            recap_root=recap_root,
            recap_python=recap_python,
            storage_root=storage_root,
        )
        _emit(report, json_output=json_output)
    except CaptchaSkillError as exc:
        _abort(exc, json_output=json_output)


@app.command("schemas")
def schemas_command(
    out_dir: Path = typer.Option(
        Path(__file__).resolve().parents[2] / "references",
        "--out-dir",
        file_okay=False,
    ),
    check: bool = typer.Option(False, "--check"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Write or verify JSON Schemas generated from the Pydantic contracts."""

    try:
        result = export_schemas(out_dir, check=check)
        _emit(result, json_output=json_output)
    except CaptchaSkillError as exc:
        _abort(exc, json_output=json_output)



@app.command("authorization-preflight")
def authorization_preflight_command(
    manifest_path: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
    action: EvaluationAction = typer.Option(EvaluationAction.PLAN, "--action"),
    receipt_out: Path | None = typer.Option(None, "--receipt-out"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Validate a target authorization manifest and emit a PASS receipt."""

    try:
        manifest, manifest_sha256 = load_manifest(manifest_path)
        receipt = validate_authorization(
            manifest,
            manifest_sha256=manifest_sha256,
            required_action=action,
        )
        if receipt_out is not None:
            write_json_atomic(receipt_out, receipt.model_dump(mode="json"))
        _emit(receipt, json_output=json_output)
    except CaptchaSkillError as exc:
        _abort(exc, json_output=json_output)
    except ValidationError as exc:
        _abort(_validation_error(exc), json_output=json_output)


@app.command("plan")
def plan_command(
    manifest_path: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
    recap_root: Path = typer.Option(DEFAULT_RECAP_ROOT, "--recap-root"),
    recap_python: Path | None = typer.Option(None, "--recap-python"),
    output_root: Path = typer.Option(DEFAULT_OUTPUT_ROOT, "--output-root"),
    out: Path | None = typer.Option(None, "--out"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Build a typed execution plan without launching Surf or ReCAP."""

    try:
        manifest, manifest_sha256 = load_manifest(manifest_path)
        authorization = validate_authorization(
            manifest,
            manifest_sha256=manifest_sha256,
            required_action=EvaluationAction.PLAN,
        )
        plan = build_evaluation_plan(
            manifest,
            authorization,
            recap_root=recap_root,
            recap_python=recap_python,
            output_root=output_root,
        )
        if out is not None:
            write_json_atomic(out, plan.model_dump(mode="json"))
        _emit(plan, json_output=json_output)
        if plan.readiness is not RunStatus.PASS:
            raise typer.Exit(code=2)
    except CaptchaSkillError as exc:
        _abort(exc, json_output=json_output)
    except ValidationError as exc:
        _abort(_validation_error(exc), json_output=json_output)


@app.command("evaluate")
def evaluate_command(
    manifest_path: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
    recap_root: Path = typer.Option(DEFAULT_RECAP_ROOT, "--recap-root"),
    recap_python: Path | None = typer.Option(None, "--recap-python"),
    output_root: Path = typer.Option(DEFAULT_OUTPUT_ROOT, "--output-root"),
    execute: bool = typer.Option(False, "--execute", help="Required live-effect gate."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run one bounded local ReCAP benchmark and preserve its receipts."""

    if not execute:
        _abort(
            CaptchaSkillError(
                ErrorCode.EXECUTION_NOT_CONFIRMED,
                "live benchmark execution requires --execute",
            ),
            json_output=json_output,
        )
    try:
        manifest, manifest_sha256 = load_manifest(manifest_path)
        authorization = validate_authorization(
            manifest,
            manifest_sha256=manifest_sha256,
            required_action=EvaluationAction.EVALUATE,
        )
        receipt, run_dir = execute_evaluation(
            manifest,
            authorization,
            recap_root=recap_root,
            recap_python=recap_python,
            output_root=output_root,
        )
        payload = receipt.model_dump(mode="json")
        payload["run_dir"] = str(run_dir)
        _emit(payload, json_output=json_output)
        if receipt.status is not RunStatus.PASS:
            raise typer.Exit(code=2)
    except CaptchaSkillError as exc:
        _abort(exc, json_output=json_output)
    except ValidationError as exc:
        _abort(_validation_error(exc), json_output=json_output)


@app.command("verify")
def verify_command(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify receipt consistency and evidence hashes without re-execution."""

    try:
        result = verify_run(run_dir)
        _emit(result, json_output=json_output)
    except CaptchaSkillError as exc:
        _abort(exc, json_output=json_output)


@app.command("ask-dag")
def ask_dag_command(
    manifest_path: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
    recap_root: Path = typer.Option(DEFAULT_RECAP_ROOT, "--recap-root"),
    recap_python: Path | None = typer.Option(None, "--recap-python"),
    output_root: Path = typer.Option(DEFAULT_OUTPUT_ROOT, "--output-root"),
    out: Path = typer.Option(..., "--out", dir_okay=False),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Emit an ``ask.dag.v1`` file that composes this skill through Ask."""

    try:
        manifest, manifest_sha256 = load_manifest(manifest_path)
        validate_authorization(
            manifest,
            manifest_sha256=manifest_sha256,
            required_action=EvaluationAction.ASK_DAG,
        )
        recap_python_path = recap_python or default_recap_python(recap_root)
        dag = build_ask_dag(
            manifest_path=manifest_path,
            recap_root=recap_root,
            recap_python=recap_python_path,
            output_root=output_root,
            timeout_seconds=manifest.timeout_seconds,
        )
        write_json_atomic(out, dag.model_dump(mode="json"))
        payload = dag.model_dump(mode="json")
        payload["dag_path"] = str(out.expanduser().resolve())
        payload["next_command"] = (
            f'cd "{(Path(__file__).resolve().parents[4] / "skills" / "ask")}" && '
            f'./run.sh ask "Run the authorized local ReCAP CAPTCHA evaluation" '
            f'--dag-file "{out.expanduser().resolve()}" --json'
        )
        _emit(payload, json_output=json_output)
    except CaptchaSkillError as exc:
        _abort(exc, json_output=json_output)
    except ValidationError as exc:
        _abort(_validation_error(exc), json_output=json_output)


if __name__ == "__main__":
    app()
