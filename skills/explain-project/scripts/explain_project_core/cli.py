"""Thin Typer CLI for explain-project.

Commands validate/load data, route questions, emit deterministic proof artifacts,
or start the local cockpit API. Product logic lives in package modules.
"""

from __future__ import annotations

import hashlib
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
    AdapterReceipt,
    CockpitProof,
    CockpitScript,
    DebuggerProofReference,
    DebuggerRevealStatus,
    ExcalidrawProposalStatus,
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
from .scaffold import (
    answer_question,
    run_project_state,
    write_milestone,
    write_scaffold,
)
from .server import serve

SKILL_DIR = Path(__file__).resolve().parents[2]

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

    for candidate in (
        path,
        repo / path,
        SKILL_DIR / path,
        SKILL_DIR / repo / path,
    ):
        if candidate.exists():
            return candidate

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


@app.command("scaffold")
def scaffold_command(
    repo: Path = typer.Option(
        ...,
        "--repo",
        help="Project root to explain.",
    ),
    entrypoint: Path = typer.Option(
        ...,
        "--entrypoint",
        help="Project entrypoint, relative to --repo unless absolute.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Destination explainer JSONL. Defaults to docs/explain/explainers.jsonl.",
    ),
    project_state: Path | None = typer.Option(
        None,
        "--project-state",
        help="Existing $project-state JSON receipt to bind.",
    ),
    run_state: bool = typer.Option(
        False,
        "--run-project-state",
        help="Run a quick $project-state JSON report before writing the scaffold.",
    ),
) -> None:
    """Create a starter explainer for any project from its entrypoint."""

    resolved_repo = repo.resolve()
    resolved_entrypoint = _resolve_input(
        resolved_repo,
        entrypoint,
    ).resolve()
    resolved_output = (
        output
        if output is not None
        else resolved_repo / "docs/explain/explainers.jsonl"
    )
    if not resolved_output.is_absolute():
        resolved_output = resolved_repo / resolved_output

    resolved_project_state = project_state
    if resolved_project_state is not None and not resolved_project_state.is_absolute():
        resolved_project_state = resolved_repo / resolved_project_state
    if run_state:
        resolved_project_state = run_project_state(
            resolved_repo,
            resolved_output.parent / "project-state.quick.json",
        )

    _emit(
        write_scaffold(
            resolved_repo,
            resolved_entrypoint,
            resolved_output,
            resolved_project_state,
        )
    )


@app.command("milestone")
def milestone_command(
    repo: Path = typer.Option(
        ...,
        "--repo",
        help="Project root to refresh.",
    ),
    entrypoint: Path = typer.Option(
        ...,
        "--entrypoint",
        help="Project entrypoint, relative to --repo unless absolute.",
    ),
    milestone: str = typer.Option(
        "current",
        "--milestone",
        help="Milestone name used under docs/explain/milestones/.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Override milestone bundle directory.",
    ),
) -> None:
    """Refresh per-milestone project-state and explainer scaffold."""

    resolved_repo = repo.resolve()
    resolved_entrypoint = _resolve_input(
        resolved_repo,
        entrypoint,
    ).resolve()
    resolved_output_dir = output_dir
    if resolved_output_dir is not None and not resolved_output_dir.is_absolute():
        resolved_output_dir = resolved_repo / resolved_output_dir

    _emit(
        write_milestone(
            resolved_repo,
            resolved_entrypoint,
            milestone,
            resolved_output_dir,
        )
    )


@app.command("answer-question")
def answer_question_command(
    repo: Path = typer.Option(..., "--repo"),
    question: str = typer.Option(..., "--question"),
    out: Path = typer.Option(..., "--out"),
    entrypoint: Path | None = typer.Option(None, "--entrypoint"),
    debug_command: str | None = typer.Option(
        None,
        "--debug-command",
        help="Optional command to run under $debugger from --repo.",
    ),
) -> None:
    """Create a question-first cockpit bundle for a project question."""

    resolved_repo = repo.resolve()
    resolved_entrypoint = None
    if entrypoint is not None:
        resolved_entrypoint = _resolve_input(
            resolved_repo,
            entrypoint,
        ).resolve()
    _emit(
        answer_question(
            resolved_repo,
            question,
            out.resolve(),
            resolved_entrypoint,
            debug_command,
        )
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
        "cockpit:explainer:search-input",
        "cockpit:explainer:paste-toggle",
        "cockpit:source:reveal",
        "cockpit:debugger:prepare",
        "cockpit:step:previous",
        "cockpit:step:next",
        "cockpit:health:status:live-evidence",
        "cockpit:health:status:source",
        "cockpit:health:status:debugger",
        "cockpit:health:status:web-ui",
        "cockpit:service:surf",
        "cockpit:service:surf-tab-input",
        "cockpit:service:surf-tab-apply",
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


@app.command("debugger-source-reveal-receipt")
def debugger_source_reveal_receipt_command(
    status: Path = typer.Option(
        ...,
        "--status",
        help="Debugger VS Code bridge status JSON.",
    ),
    workspace: Path = typer.Option(
        Path("."),
        "--workspace",
        help="Workspace root used to resolve relative source paths.",
    ),
    source_file: Path = typer.Option(
        ...,
        "--source-file",
    ),
    start_line: int = typer.Option(
        ...,
        "--start-line",
        min=1,
    ),
    end_line: int = typer.Option(
        ...,
        "--end-line",
        min=1,
    ),
    feature_id: str = typer.Option(
        ...,
        "--feature-id",
    ),
    step_id: str = typer.Option(
        ...,
        "--step-id",
    ),
    request_revision: int = typer.Option(
        ...,
        "--request-revision",
        min=0,
    ),
) -> None:
    """Validate a $debugger source reveal status and emit a cockpit receipt."""

    if end_line < start_line:
        _emit(
            TriagedFailure(
                failure_code=(
                    FailureCode
                    .PYDANTIC_VALIDATION_FAILED
                ),
                message="end_line must be >= start_line",
            )
        )
        raise typer.Exit(2)

    try:
        raw = status.read_text(
            encoding="utf-8"
        )
        reveal_status = DebuggerRevealStatus.model_validate_json(
            raw
        )
    except ValidationError as error:
        _emit(
            TriagedFailure(
                failure_code=(
                    FailureCode
                    .PYDANTIC_VALIDATION_FAILED
                ),
                message="debugger reveal status validation failed",
                errors=_validation_errors(error),
            )
        )
        raise typer.Exit(1)

    expected = source_file
    if not expected.is_absolute():
        expected = workspace / expected

    actual = Path(reveal_status.reveal.file)

    if actual.resolve() != expected.resolve() or not (
        start_line <= reveal_status.reveal.line <= end_line
    ):
        _emit(
            TriagedFailure(
                failure_code=(
                    FailureCode
                    .ADAPTER_RECEIPT_MISMATCH
                ),
                message=(
                    "debugger reveal status does not match "
                    "the requested source range"
                ),
            )
        )
        raise typer.Exit(1)

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()

    _emit(
        AdapterReceipt(
            receipt_id=reveal_status.id,
            adapter="source_reveal",
            request_revision=request_revision,
            feature_id=feature_id,
            step_id=step_id,
            status="REVEALED",
            detail=(
                f"debugger_status={status}; "
                f"sha256:{digest}; "
                f"revealed={actual}:{reveal_status.reveal.line}"
            ),
        )
    )


@app.command("excalidraw-proposal-receipt")
def excalidraw_proposal_receipt_command(
    receipt: Path = typer.Option(
        ...,
        "--receipt",
        help="ops-excalidraw push-board/describe proposal receipt JSON.",
    ),
    feature_id: str = typer.Option(..., "--feature-id"),
    step_id: str = typer.Option(..., "--step-id"),
    request_revision: int = typer.Option(
        ...,
        "--request-revision",
        min=0,
    ),
) -> None:
    """Convert an ops-excalidraw proposal receipt into cockpit state."""

    try:
        raw = receipt.read_text(encoding="utf-8")
        proposal = ExcalidrawProposalStatus.model_validate_json(raw)
    except ValidationError as error:
        _emit(
            TriagedFailure(
                failure_code=(
                    FailureCode
                    .PYDANTIC_VALIDATION_FAILED
                ),
                message=(
                    "ops-excalidraw proposal receipt validation failed"
                ),
                errors=_validation_errors(error),
            )
        )
        raise typer.Exit(1)

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    _emit(
        AdapterReceipt(
            receipt_id=f"excalidraw-proposal-{digest[:16]}",
            adapter="excalidraw_proposal",
            request_revision=request_revision,
            feature_id=feature_id,
            step_id=step_id,
            status="PROPOSED",
            detail=(
                f"ops_excalidraw_receipt={receipt}; "
                f"sha256:{digest}; "
                f"version={proposal.version}; "
                f"elements={proposal.elements}"
            ),
        )
    )


@app.command("debugger-runtime-proof-receipt")
def debugger_runtime_proof_receipt_command(
    proof: Path = typer.Option(
        ...,
        "--proof",
        help="Canonical debugger.proof.v1 JSON from $debugger validate.",
    ),
    workspace: Path = typer.Option(
        Path("."),
        "--workspace",
        help="Workspace root used to resolve relative source paths.",
    ),
    target_file: Path = typer.Option(
        ...,
        "--target-file",
    ),
    start_line: int = typer.Option(
        ...,
        "--start-line",
        min=1,
    ),
    end_line: int = typer.Option(
        ...,
        "--end-line",
        min=1,
    ),
    feature_id: str = typer.Option(
        ...,
        "--feature-id",
    ),
    step_id: str = typer.Option(
        ...,
        "--step-id",
    ),
    request_revision: int = typer.Option(
        ...,
        "--request-revision",
        min=0,
    ),
    local: list[str] | None = typer.Option(
        None,
        "--local",
        help="Local variable required in the debugger proof. Repeatable.",
    ),
    proves: str = typer.Option(
        ...,
        "--proves",
    ),
) -> None:
    """Convert validated $debugger runtime proof into a cockpit receipt."""

    if end_line < start_line:
        _emit(
            TriagedFailure(
                failure_code=(
                    FailureCode
                    .PYDANTIC_VALIDATION_FAILED
                ),
                message="end_line must be >= start_line",
            )
        )
        raise typer.Exit(2)

    try:
        raw = proof.read_text(
            encoding="utf-8"
        )
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        _emit(
            TriagedFailure(
                failure_code=(
                    FailureCode
                    .PYDANTIC_VALIDATION_FAILED
                ),
                message=str(error),
            )
        )
        raise typer.Exit(1)

    expected = target_file
    if not expected.is_absolute():
        expected = workspace / expected

    frame = (
        data.get("stopped", {})
        .get("frame", {})
    )
    captures = data.get("captures", {})
    locals_map = captures.get("locals", {})
    assessment = data.get("assessment", {})

    actual = Path(str(frame.get("file", "")))
    line = int(frame.get("line", 0) or 0)
    missing_locals = [
        name
        for name in (local or [])
        if name not in locals_map
    ]

    if (
        data.get("schema") != "debugger.proof.v1"
        or assessment.get("proofValid") is not True
        or assessment.get("variableInspectionValid") is not True
        or actual.resolve() != expected.resolve()
        or not (start_line <= line <= end_line)
        or missing_locals
    ):
        _emit(
            TriagedFailure(
                failure_code=(
                    FailureCode
                    .ADAPTER_RECEIPT_MISMATCH
                ),
                message=(
                    "debugger runtime proof does not match "
                    "the requested source range or locals"
                ),
                errors=[
                    {
                        "actual_file": str(actual),
                        "actual_line": line,
                        "expected_file": str(expected),
                        "start_line": start_line,
                        "end_line": end_line,
                        "missing_locals": missing_locals,
                    }
                ],
            )
        )
        raise typer.Exit(1)

    digest = hashlib.sha256(
        proof.read_bytes()
    ).hexdigest()

    _emit(
        AdapterReceipt(
            receipt_id=(
                "debugger-proof-"
                f"{digest[:16]}"
            ),
            adapter="debugger_proof",
            request_revision=request_revision,
            feature_id=feature_id,
            step_id=step_id,
            status="PROOF_RECEIVED",
            detail=(
                f"debugger_proof={proof}; "
                f"stopped={actual}:{line}"
            ),
            proof=DebuggerProofReference(
                proof_path=str(proof),
                sha256=f"sha256:{digest}",
                validated=True,
                proves=proves,
            ),
        )
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
            repo=repo,
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


@app.command("propose-docstring-links")
def propose_docstring_links_command(
    repo: Path = typer.Option(..., "--repo"),
    explainers: Path = typer.Option(..., "--explainers"),
    out: Path = typer.Option(..., "--out"),
    include_source_ranges: bool = typer.Option(
        False,
        "--include-source-ranges",
        help=(
            "Also propose for source-range symbol owners "
            "without debugger stops."
        ),
    ),
) -> None:
    """Propose docstring diagram-link lines for each debugger breakpoint.

    Reads a strict explainer JSONL, finds every step with a debugger
    stop (or every source-range symbol with --include-source-ranges),
    locates the owning top-level function, and writes a typed proposal
    artifact (explain_project.docstring_link_proposal.v1) containing
    the exact docstring line to add per breakpoint. Never mutates
    source; the human/project-agent applies the patch once.
    """

    rows = read_jsonl(explainers)
    proposals: list[dict[str, Any]] = []

    for row in rows:
        diagram = row.diagram
        pointer = (
            f"Excalidraw source: {diagram.source_path}"
        )
        if diagram.source_kind != "excalidraw":
            pointer = f"Diagram: {diagram.source_path}"

        seen_functions: set[tuple[str, str]] = set()
        targets: list[tuple[str, int]] = []
        for step in row.steps:
            if step.debugger_stop_index is None:
                continue
            stop = row.debugger_stops[
                step.debugger_stop_index
            ]
            targets.append((stop.file, stop.line))
        if include_source_ranges:
            for source_range in row.source_ranges:
                targets.append(
                    (source_range.file, source_range.start_line)
                )
        for target_file, target_line in targets:
            stop_file, stop_line = target_file, target_line
            source = (repo / stop_file).resolve()
            if not source.is_file():
                continue
            lines = source.read_text(
                encoding="utf-8"
            ).splitlines()
            line_no = min(
                max(stop_line - 1, 0), len(lines) - 1
            )

            owning = None
            for i in range(line_no, -1, -1):
                text = lines[i]
                if text.startswith("def "):
                    owning = text.split("(")[0][4:].strip()
                    break
                if text.startswith("class "):
                    owning = text.split("(")[0][6:].strip()
                    break
                if text.startswith("async def "):
                    owning = text.split("(")[0][10:].strip()
                    break

            key = (str(stop.file), owning or "")
            if owning is None or key in seen_functions:
                continue

            # Docstring already carries a diagram pointer?
            # Bound the check to the owning function's own docstring
            # (def line to its closing triple quote), not a raw window.
            def_line = next(
                i for i in range(line_no, -1, -1)
                if lines[i].lstrip().startswith(
                    ("def ", "class ", "async def ")
                )
            )
            doc = []
            opened = False
            for j in range(def_line, min(def_line + 40, len(lines))):
                if '"""' in lines[j]:
                    count = lines[j].count('"""')
                    if not opened and count >= 2:
                        doc.append(lines[j])
                        break
                    if not opened:
                        opened = True
                    else:
                        doc.append(lines[j])
                        break
                if opened:
                    doc.append(lines[j])
                elif j > def_line + 2:
                    break
            window = "\n".join(doc)
            already_linked = (
                "Excalidraw source:" in window
                or "Diagram ID:" in window
                or "Diagram:" in window
            )
            if already_linked:
                continue
            seen_functions.add(key)

            proposals.append({
                "file": str(stop_file),
                "function": owning,
                "breakpoint_line": stop_line,
                "proposed_docstring_line": pointer,
                "diagram_id": diagram.source_path,
            })

    artifact = {
        "schema":
            "explain_project.docstring_link_proposal.v1",
        "repo": str(repo),
        "mutation": "proposal-only",
        "proposals": proposals,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(artifact, indent=2) + "\n",
        encoding="utf-8",
    )
    typer.echo(
        f"proposed {len(proposals)} docstring link(s) -> {out}"
    )
