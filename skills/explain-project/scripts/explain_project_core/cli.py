"""Thin Typer CLI for explain-project.

Commands validate/load data, route questions, emit deterministic proof artifacts,
or start the local cockpit API. Product logic lives in package modules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from .catalog import (
    CatalogError,
    read_jsonl,
    summaries,
    write_sample,
)
from .models import (
    CockpitProof,
    CockpitScript,
    FailureCode,
    FeatureExplainer,
    TriagedFailure,
)
from .proof import (
    default_proof_script,
    run_script,
    validate_proof,
)
from .routing import route
from .server import serve

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
)


def _emit(value: Any) -> None:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(
            by_alias=True,
            mode="json",
        )
    else:
        payload = value

    typer.echo(
        json.dumps(payload, indent=2)
    )


def _validation_errors(
    error: ValidationError,
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []

    for item in error.errors():
        entry = dict(item)

        if "ctx" in entry:
            entry["ctx"] = {
                key: str(value)
                for key, value in entry["ctx"].items()
            }

        cleaned.append(entry)

    return cleaned


def _resolve_input(
    repo: Path,
    path: Path,
) -> Path:
    if path.is_absolute():
        return path

    if path.exists():
        return path

    return repo / path


def _load(
    path: Path,
) -> list[FeatureExplainer]:
    try:
        return read_jsonl(path)

    except CatalogError as error:
        _emit(
            TriagedFailure(
                failure_code=error.code,
                message=str(error),
                errors=error.errors,
            )
        )
        raise typer.Exit(1) from error


@app.command("validate")
def validate_command(
    path: Path,
) -> None:
    rows = _load(path)

    _emit(
        {
            "schema": "explain_project.validation.v1",
            "status": "PASS",
            "records": len(rows),
            "features": sorted(
                row.feature_id
                for row in rows
            ),
        }
    )


@app.command("list")
def list_command(
    path: Path,
) -> None:
    rows = _load(path)

    _emit(
        {
            "schema": "explain_project.list.v1",
            "records": [
                item.model_dump(mode="json")
                for item in summaries(rows)
            ],
        }
    )


@app.command("ask")
def ask_command(
    path: Path,
    question: str = typer.Option(
        ...,
        "--question",
    ),
) -> None:
    rows = _load(path)
    decision = route(
        rows,
        question,
    )

    payload: dict[str, Any] = {
        "schema": "explain_project.answer_route.v1",
        "status": "PASS",
        "question": question,
        "route": decision.model_dump(
            by_alias=True,
            mode="json",
        ),
    }

    if (
        decision.status == "MATCHED"
        and decision.matched_feature is not None
    ):
        row = next(
            item
            for item in rows
            if (
                item.feature_id
                == decision.matched_feature
            )
        )

        payload.update(
            {
                "matched_feature": row.feature_id,
                "family": row.question_family,
                "teleprompter_points": (
                    row.teleprompter_points
                ),
                "diagram": row.diagram.model_dump(
                    mode="json"
                ),
                "source_ranges": [
                    item.model_dump(mode="json")
                    for item in row.source_ranges
                ],
                "debugger_stops": [
                    item.model_dump(mode="json")
                    for item in row.debugger_stops
                ],
                "proof_boundary": (
                    row.proof_boundary
                ),
            }
        )

    _emit(payload)


@app.command("sample")
def sample_command(
    output: Path = typer.Option(
        ...,
        "--output",
    ),
) -> None:
    write_sample(output)

    _emit(
        {
            "schema": "explain_project.sample.v1",
            "status": "PASS",
            "output": str(output),
        }
    )


@app.command("cockpit-proof")
def cockpit_proof_command(
    path: Path,
    question: str = typer.Option(
        ...,
        "--question",
    ),
    output: Path | None = typer.Option(
        None,
        "--out",
    ),
) -> None:
    rows = _load(path)

    proof = run_script(
        rows,
        default_proof_script(question),
    )

    if output is not None:
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        output.write_text(
            proof.model_dump_json(
                by_alias=True,
                indent=2,
            ),
            encoding="utf-8",
        )

    _emit(proof)

    if proof.status != "PASS":
        raise typer.Exit(1)


@app.command("interaction-manifest")
def interaction_manifest_command(
    base_url: str = typer.Option(
        "http://127.0.0.1:8766",
        "--base-url",
    ),
) -> None:
    """Emit a qid-only test-interactions manifest template."""

    qids = [
        "cockpit:question:manual-input",
        "cockpit:question:manual-submit",
        "cockpit:explainer:slider",
        "cockpit:explainer:page-input",
        "cockpit:explainer:search",
        "cockpit:explainer:paste-toggle",
        "cockpit:source:reveal",
        "cockpit:debugger:prepare",
        "cockpit:step:previous",
        "cockpit:step:next",
    ]

    _emit(
        {
            "version": 1,
            "app": "explain-project",
            "base_url": base_url.rstrip("/"),
            "discovery": {
                "qid_only_executable_selectors": True,
                "route_isolated": True,
                "source": "explain-project static manifest",
            },
            "surfaces": [
                {
                    "name": "cockpit-main",
                    "path": "/",
                    "qid_compliance": True,
                    "isolate_interactions": True,
                    "elements": [
                        {
                            "name": qid.replace(":", "-"),
                            "interactions": [
                                {
                                    "action": "click",
                                    "target": f"[data-qid='{qid}']",
                                    "description": (
                                        "Exercise explain-project "
                                        f"control {qid}"
                                    ),
                                    "assert_timing": "before",
                                    "assert_title": f"[data-qid='{qid}']",
                                    "assert_qs_action": f"[data-qid='{qid}']",
                                }
                            ],
                        }
                        for qid in qids
                    ],
                }
            ],
        }
    )


@app.command("cockpit")
def cockpit_command(
    explainers: Path = typer.Option(
        ...,
        "--explainers",
    ),
    repo: Path = typer.Option(
        Path("."),
        "--repo",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
    ),
    script: Path | None = typer.Option(
        None,
        "--script",
    ),
    output: Path | None = typer.Option(
        None,
        "--out",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
    ),
    port: int = typer.Option(
        8766,
        "--port",
        min=1,
        max=65535,
    ),
    memory_url: str = typer.Option(
        "http://127.0.0.1:8601",
        "--memory-url",
    ),
) -> None:
    resolved_explainers = _resolve_input(
        repo,
        explainers,
    )

    rows = _load(
        resolved_explainers.resolve()
    )

    if not headless:
        serve(
            rows,
            host=host,
            port=port,
            memory_url=memory_url,
        )
        return

    if script is None or output is None:
        _emit(
            TriagedFailure(
                failure_code=FailureCode.INVALID_SCRIPT,
                message=(
                    "--headless requires "
                    "--script and --out"
                ),
            )
        )
        raise typer.Exit(2)

    resolved_script = _resolve_input(
        repo,
        script,
    )

    try:
        script_model = CockpitScript.model_validate_json(
            resolved_script.read_text(
                encoding="utf-8"
            )
        )
        proof = run_script(
            rows,
            script_model,
        )

    except ValidationError as error:
        _emit(
            TriagedFailure(
                failure_code=(
                    FailureCode
                    .PYDANTIC_VALIDATION_FAILED
                ),
                message=(
                    "cockpit script "
                    "validation failed"
                ),
                errors=_validation_errors(error),
            )
        )
        raise typer.Exit(1) from error

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        proof.model_dump_json(
            by_alias=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    _emit(
        {
            "schema": "explain_project.cockpit_run.v1",
            "status": proof.status,
            "out": str(output),
        }
    )

    if proof.status != "PASS":
        raise typer.Exit(1)


@app.command("validate-proof")
def validate_proof_command(
    path: Path,
    expect_valid: bool = typer.Option(
        False,
        "--expect-valid",
    ),
) -> None:
    try:
        proof = CockpitProof.model_validate_json(
            path.read_text(
                encoding="utf-8"
            )
        )

    except ValidationError as error:
        _emit(
            TriagedFailure(
                failure_code=(
                    FailureCode
                    .PYDANTIC_VALIDATION_FAILED
                ),
                message=(
                    "cockpit proof "
                    "validation failed"
                ),
                errors=_validation_errors(error),
            )
        )
        raise typer.Exit(1) from error

    failures = validate_proof(proof)

    _emit(
        {
            "schema": (
                "explain_project."
                "cockpit_proof_validation.v1"
            ),
            "status": (
                "PASS"
                if not failures
                else "FAIL"
            ),
            "failures": failures,
        }
    )

    if (
        failures
        or (
            expect_valid
            and proof.status != "PASS"
        )
    ):
        raise typer.Exit(1)
