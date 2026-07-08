#!/usr/bin/env python3
"""Create receipt-backed status surfaces and Tau DAG handoff contracts."""

from __future__ import annotations

import hashlib
import html
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer


app = typer.Typer(add_completion=False, help="Create receipt-backed status surfaces.")

PASS_RENDER = "PASS_STATUS_SURFACE_RENDER"
PASS_VALIDATE = "PASS_STATUS_SURFACE_VALIDATION"
PASS_TAU_DAG = "PASS_TAU_STATUS_SURFACE_DAG_CONTRACT"
BLOCKED_RENDER = "BLOCKED_STATUS_SURFACE_RENDER"
BLOCKED_VALIDATE = "BLOCKED_STATUS_SURFACE_VALIDATION"
BLOCKED_TAU_DAG = "BLOCKED_TAU_STATUS_SURFACE_DAG_CONTRACT"
FORBIDDEN_TRUE = {
    "provider_live": "BLOCKED_PROVIDER_LIVE_CLAIM",
    "paid_call_authorized": "BLOCKED_PAID_CALL_AUTHORIZED_CLAIM",
    "provider_ready": "BLOCKED_PROVIDER_READY_CLAIM",
    "live_submit_ready": "BLOCKED_LIVE_SUBMIT_READY_CLAIM",
    "manual_acceptance_claimed": "BLOCKED_MANUAL_ACCEPTANCE_CLAIM",
    "submitted": "BLOCKED_SUBMITTED_CLAIM",
}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(payload.get("status", "UNKNOWN"))
    if str(payload.get("status", "")).startswith("BLOCKED"):
        raise typer.Exit(1)


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def units_from_progress(progress: dict[str, Any]) -> list[dict[str, Any]]:
    units = progress.get("units")
    if isinstance(units, list):
        return [unit for unit in units if isinstance(unit, dict)]
    return []


def normalize_source(progress: dict[str, Any], input_path: Path) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    for field, blocker in FORBIDDEN_TRUE.items():
        if progress.get(field) is True:
            add_blocker(blockers, blocker)
    units = units_from_progress(progress)
    if not units:
        add_blocker(blockers, "BLOCKED_STATUS_SURFACE_UNITS_MISSING")
    total = int(progress.get("expected_unit_count") or progress.get("unit_count") or len(units) or 0)
    passed = int(progress.get("pass_count") or sum(1 for unit in units if str(unit.get("status")).startswith("PASS")))
    blocked = int(progress.get("blocked_count") or sum(1 for unit in units if unit.get("status") == "BLOCKED"))
    stale = int(progress.get("stale_count") or sum(1 for unit in units if unit.get("status") == "STALE"))
    percent = float(progress.get("progress_percent") if progress.get("progress_percent") is not None else (passed / total * 100 if total else 0))
    surface_units = []
    for unit in units:
        unit_id = str(unit.get("unit_id") or "")
        status = str(unit.get("status") or "UNKNOWN")
        if not unit_id:
            add_blocker(blockers, "BLOCKED_STATUS_SURFACE_UNIT_ID_MISSING")
        if status.startswith("PASS"):
            if not unit.get("receipt_path"):
                add_blocker(blockers, "BLOCKED_STATUS_SURFACE_RECEIPT_MISSING")
            sha = unit.get("receipt_sha256")
            if not isinstance(sha, str) or not sha.startswith("sha256:"):
                add_blocker(blockers, "BLOCKED_STATUS_SURFACE_RECEIPT_HASH_MISSING")
        surface_units.append(
            {
                "unit_id": unit_id,
                "phase": unit.get("phase"),
                "label": unit.get("label") or unit_id,
                "status": status,
                "evidence_state": unit.get("evidence_state") or "CURRENT",
                "receipt_path": unit.get("receipt_path"),
                "receipt_sha256": unit.get("receipt_sha256"),
                "live_blockers": unit.get("live_blockers") or [],
            }
        )
    source = {
        "source_schema": progress.get("schema"),
        "source_status": progress.get("status"),
        "source_path": str(input_path),
        "source_sha256": sha256_file(input_path),
        "label": progress.get("label") or "LOCAL_EVIDENCE_PROGRESS",
        "unit_count": len(surface_units),
        "expected_unit_count": total,
        "pass_count": passed,
        "blocked_count": blocked,
        "stale_count": stale,
        "progress_percent": round(percent, 2),
        "units": surface_units,
    }
    return source, blockers


def status_color(status: str) -> str:
    if status.startswith("PASS"):
        return "#00ff66"
    if status == "BLOCKED":
        return "#ff3b30"
    if status == "STALE":
        return "#ffd000"
    return "#8fa3b8"


def render_html(surface: dict[str, Any]) -> str:
    rows = []
    for unit in surface["units"]:
        color = status_color(str(unit["status"]))
        blockers = ", ".join(unit.get("live_blockers") or [])
        rows.append(
            "<tr>"
            f"<td><span class='bar' style='background:{color}'></span>{html.escape(str(unit['label']))}</td>"
            f"<td>{html.escape(str(unit.get('phase') or ''))}</td>"
            f"<td>{html.escape(str(unit['status']))}</td>"
            f"<td>{html.escape(str(unit.get('evidence_state') or ''))}</td>"
            f"<td>{html.escape(blockers)}</td>"
            "</tr>"
        )
    percent = max(0.0, min(100.0, float(surface["progress_percent"])))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(surface['title'])}</title>
<style>
body {{ margin: 0; background: #050708; color: #f5f7fa; font-family: Arial, Helvetica, sans-serif; }}
main {{ padding: 32px; max-width: 1200px; }}
h1 {{ font-size: 40px; letter-spacing: 0; margin: 0 0 20px; }}
.signal {{ background: #ffd000; color: #000; padding: 20px 24px; display: flex; justify-content: space-between; align-items: center; }}
.signal strong {{ font-size: 52px; }}
.progress {{ height: 32px; border: 4px solid #f5f7fa; margin: 24px 0; background: #111; }}
.fill {{ width: {percent:.2f}%; height: 100%; background: #00ff66; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
th, td {{ border-bottom: 1px solid #2a3540; padding: 14px 10px; text-align: left; font-size: 15px; }}
th {{ color: #9fb4c7; text-transform: uppercase; font-size: 12px; }}
.bar {{ display: inline-block; width: 8px; height: 28px; margin-right: 12px; vertical-align: middle; }}
.nonclaims {{ color: #9fb4c7; margin-top: 24px; line-height: 1.5; }}
</style>
</head>
<body>
<main>
<div class="signal"><h1>{html.escape(surface['title'])}</h1><strong>{percent:.0f}%</strong></div>
<div class="progress"><div class="fill"></div></div>
<p>{surface['pass_count']} passed / {surface['expected_unit_count']} expected units. {surface['blocked_count']} blocked, {surface['stale_count']} stale.</p>
<table>
<thead><tr><th>Unit</th><th>Phase</th><th>Status</th><th>Evidence</th><th>Live blockers</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<div class="nonclaims"><strong>Does not prove:</strong> manual acceptance, provider readiness, paid-call authorization, live Tau execution, or live provider generation.</div>
</main>
</body>
</html>
"""


@app.command()
def render(
    input: Annotated[Path, typer.Option("--input", exists=True, readable=True)],
    output_dir: Annotated[Path, typer.Option("--output-dir")],
    title: Annotated[str, typer.Option("--title")] = "Status Surface",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    progress = read_json(input)
    source, blockers = normalize_source(progress, input)
    output_dir.mkdir(parents=True, exist_ok=True)
    surface_path = output_dir / "status_surface.json"
    html_path = output_dir / "status_surface.html"
    surface = {
        "schema": "create_status_surface.status_surface.v1",
        "generated_at": now(),
        "title": title,
        "status": PASS_RENDER if not blockers else BLOCKED_RENDER,
        "mocked": False,
        "live": False,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "manual_acceptance_claimed": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
        "live_tau_dag_execution_started": False,
        **source,
        "blockers": blockers,
        "claims": {
            "proves": [
                "a local status surface was derived from a receipt-backed progress artifact",
                "provider readiness, manual acceptance, paid-call authorization, and live submission were not claimed",
            ],
            "does_not_prove": [
                "visual quality acceptance",
                "manual acceptance",
                "provider readiness",
                "live Tau DAG execution",
                "live provider generation",
            ],
        },
    }
    write_json(surface_path, surface)
    html_path.write_text(render_html(surface), encoding="utf-8")
    receipt = {
        "schema": "create_status_surface.status_surface_receipt.v1",
        "generated_at": now(),
        "status": surface["status"],
        "mocked": False,
        "live": False,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "manual_acceptance_claimed": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
        "live_tau_dag_execution_started": False,
        "input_path": str(input),
        "input_sha256": source["source_sha256"],
        "surface_path": str(surface_path),
        "surface_sha256": sha256_file(surface_path),
        "html_path": str(html_path),
        "html_sha256": sha256_file(html_path),
        "unit_count": surface["unit_count"],
        "progress_percent": surface["progress_percent"],
        "blockers": blockers,
        "claims": surface["claims"],
    }
    receipt_path = output_dir / "status_surface_receipt.json"
    write_json(receipt_path, receipt)
    emit(receipt, json_output)


@app.command()
def validate(
    surface: Annotated[Path, typer.Option("--surface", exists=True, readable=True)],
    receipt_out: Annotated[Path, typer.Option("--receipt-out")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    payload = read_json(surface)
    blockers: list[str] = []
    if payload.get("schema") != "create_status_surface.status_surface.v1":
        add_blocker(blockers, "BLOCKED_STATUS_SURFACE_SCHEMA")
    for field, blocker in FORBIDDEN_TRUE.items():
        if payload.get(field) is True:
            add_blocker(blockers, blocker)
    if payload.get("actual_provider_call_attempts") != 0:
        add_blocker(blockers, "BLOCKED_PROVIDER_CALL_ATTEMPT_IN_STATUS_SURFACE")
    if payload.get("live_tau_dag_execution_started") is not False:
        add_blocker(blockers, "BLOCKED_LIVE_TAU_EXECUTION_CLAIM")
    units = payload.get("units")
    if not isinstance(units, list) or not units:
        add_blocker(blockers, "BLOCKED_STATUS_SURFACE_UNITS_MISSING")
    for unit in units or []:
        if not isinstance(unit, dict):
            add_blocker(blockers, "BLOCKED_STATUS_SURFACE_UNIT_SCHEMA")
            continue
        if str(unit.get("status", "")).startswith("PASS"):
            if not unit.get("receipt_path"):
                add_blocker(blockers, "BLOCKED_STATUS_SURFACE_RECEIPT_MISSING")
            sha = unit.get("receipt_sha256")
            if not isinstance(sha, str) or not sha.startswith("sha256:"):
                add_blocker(blockers, "BLOCKED_STATUS_SURFACE_RECEIPT_HASH_MISSING")
    receipt = {
        "schema": "create_status_surface.status_surface_validation_receipt.v1",
        "generated_at": now(),
        "status": PASS_VALIDATE if not blockers else BLOCKED_VALIDATE,
        "mocked": False,
        "live": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "actual_provider_call_attempts": 0,
        "live_tau_dag_execution_started": False,
        "surface": str(surface),
        "surface_sha256": sha256_file(surface),
        "unit_count": len(units or []),
        "blockers": blockers,
        "claims": {
            "proves": ["status_surface.json schema and claim boundaries were checked locally"],
            "does_not_prove": ["manual acceptance", "provider readiness", "live Tau DAG execution"],
        },
    }
    write_json(receipt_out, receipt)
    emit(receipt, json_output)


def dag_contract(surface_receipt: dict[str, Any], receipt_path: Path) -> dict[str, Any]:
    goal_material = f"{surface_receipt.get('surface_sha256')}|{surface_receipt.get('input_sha256')}"
    goal_hash = f"sha256:{hashlib.sha256(goal_material.encode('utf-8')).hexdigest()}"
    return {
        "schema": "tau.dag_contract.v1",
        "dag_id": "create-status-surface-local-proof",
        "goal": {
            "goal_id": "create-status-surface",
            "goal_version": 1,
            "goal_hash": goal_hash,
        },
        "target": {
            "repo": "grahama1970/agent-skills",
            "target": "status-surface-local-artifacts",
            "allowed_paths": [
                str(surface_receipt.get("surface_path")),
                str(surface_receipt.get("html_path")),
                str(receipt_path),
            ],
        },
        "entry_node": "render-status-surface",
        "terminal_nodes": ["human"],
        "limits": {
            "resume": True,
            "default_timeout_seconds": 120,
            "max_total_attempts": 2,
        },
        "nodes": [
            {
                "id": "render-status-surface",
                "agent": "create-status-surface",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": "skills/create-status-surface/run.sh render --input <progress> --output-dir <output>",
                "required_evidence": [
                    "status_surface.json",
                    "status_surface.html",
                    "status_surface_receipt.json",
                ],
                "emits": [
                    "create_status_surface.status_surface.v1",
                    "create_status_surface.status_surface_receipt.v1",
                ],
            },
            {
                "id": "validate-status-surface",
                "agent": "create-status-surface",
                "executor": "local",
                "max_attempts": 1,
                "command_spec": "skills/create-status-surface/run.sh validate --surface <surface> --receipt-out <receipt>",
                "required_evidence": [
                    "status_surface_validation_receipt.json",
                ],
                "emits": [
                    "create_status_surface.status_surface_validation_receipt.v1",
                ],
            },
            {
                "id": "human",
                "agent": "human",
                "executor": "human",
            },
        ],
        "edges": [
            {"from": "render-status-surface", "to": "validate-status-surface"},
            {"from": "validate-status-surface", "to": "human"},
        ],
        "required_evidence": [
            "status_surface_receipt.json",
            "status_surface_validation_receipt.json",
            "provider_live:false",
            "actual_provider_call_attempts:0",
        ],
        "fail_closed_on": [
            "goal_hash_mismatch",
            "target_changed",
            "unexpected_node",
            "unexpected_edge",
            "missing_required_evidence",
            "provider_ready_claimed",
            "manual_acceptance_claimed",
            "paid_call_authorized",
            "live_tau_dag_execution_claimed",
            "provider_call_attempted",
        ],
        "claims": {
            "proves": [
                "status-surface artifacts can be represented as a Tau DAG contract for local inspection",
            ],
            "does_not_prove": [
                "Tau executed the DAG",
                "provider readiness",
                "manual acceptance",
                "live provider generation",
            ],
        },
    }


@app.command("tau-dag")
def tau_dag(
    surface_receipt: Annotated[Path, typer.Option("--surface-receipt", exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    receipt = read_json(surface_receipt)
    blockers: list[str] = []
    if receipt.get("status") != PASS_RENDER:
        add_blocker(blockers, "BLOCKED_STATUS_SURFACE_RECEIPT_NOT_PASS")
    if receipt.get("actual_provider_call_attempts") != 0:
        add_blocker(blockers, "BLOCKED_PROVIDER_CALL_ATTEMPT_IN_STATUS_SURFACE")
    if receipt.get("live_tau_dag_execution_started") is not False:
        add_blocker(blockers, "BLOCKED_LIVE_TAU_EXECUTION_CLAIM")
    dag = dag_contract(receipt, surface_receipt)
    if blockers:
        dag["blocked"] = True
        dag["blockers"] = blockers
    write_json(output, dag)
    result = {
        "schema": "create_status_surface.tau_dag_write_receipt.v1",
        "generated_at": now(),
        "status": PASS_TAU_DAG if not blockers else BLOCKED_TAU_DAG,
        "mocked": False,
        "live": False,
        "actual_provider_call_attempts": 0,
        "live_tau_dag_execution_started": False,
        "surface_receipt": str(surface_receipt),
        "surface_receipt_sha256": sha256_file(surface_receipt),
        "dag_path": str(output),
        "dag_sha256": sha256_file(output),
        "blockers": blockers,
    }
    emit(result, json_output)


@app.command("tau-check")
def tau_check(
    dag: Annotated[Path, typer.Option("--dag", exists=True, readable=True)],
    receipt_out: Annotated[Path, typer.Option("--receipt-out")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    payload = read_json(dag)
    blockers: list[str] = []
    if payload.get("schema") != "tau.dag_contract.v1":
        add_blocker(blockers, "BLOCKED_TAU_DAG_SCHEMA")
    if not isinstance(payload.get("goal"), dict) or not str(payload.get("goal", {}).get("goal_hash", "")).startswith("sha256:"):
        add_blocker(blockers, "BLOCKED_TAU_DAG_GOAL_HASH")
    node_ids = {node.get("id") for node in payload.get("nodes", []) if isinstance(node, dict)}
    if payload.get("entry_node") not in node_ids:
        add_blocker(blockers, "BLOCKED_TAU_DAG_ENTRY_NODE")
    if "human" not in payload.get("terminal_nodes", []):
        add_blocker(blockers, "BLOCKED_TAU_DAG_HUMAN_TERMINAL_MISSING")
    for node in payload.get("nodes", []):
        if not isinstance(node, dict):
            add_blocker(blockers, "BLOCKED_TAU_DAG_NODE_SCHEMA")
            continue
        if node.get("executor") == "provider":
            add_blocker(blockers, "BLOCKED_TAU_DAG_PROVIDER_EXECUTOR")
        if node.get("executor") == "local" and not node.get("command_spec"):
            add_blocker(blockers, "BLOCKED_TAU_DAG_LOCAL_COMMAND_SPEC_MISSING")
    for edge in payload.get("edges", []):
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            add_blocker(blockers, "BLOCKED_TAU_DAG_EDGE_TARGET")
    fail_closed = payload.get("fail_closed_on")
    for required in ("provider_ready_claimed", "manual_acceptance_claimed", "provider_call_attempted"):
        if not isinstance(fail_closed, list) or required not in fail_closed:
            add_blocker(blockers, "BLOCKED_TAU_DAG_FAIL_CLOSED_INCOMPLETE")
    receipt = {
        "schema": "create_status_surface.tau_status_surface_dag_validation_receipt.v1",
        "generated_at": now(),
        "status": PASS_TAU_DAG if not blockers else BLOCKED_TAU_DAG,
        "mocked": False,
        "live": False,
        "actual_provider_call_attempts": 0,
        "live_tau_dag_execution_started": False,
        "dag": str(dag),
        "dag_sha256": sha256_file(dag),
        "node_count": len(payload.get("nodes", [])),
        "edge_count": len(payload.get("edges", [])),
        "blockers": blockers,
        "claims": {
            "proves": ["Tau DAG contract shape and fail-closed invariants were checked locally"],
            "does_not_prove": ["Tau executed the DAG", "provider readiness", "live provider generation"],
        },
    }
    write_json(receipt_out, receipt)
    emit(receipt, json_output)


@app.command("tau-doctor")
def tau_doctor(
    receipt_out: Annotated[Path, typer.Option("--receipt-out")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    skill_root = Path(__file__).resolve().parents[1]
    tau_run = skill_root.parent / "tau" / "run.sh"
    blockers: list[str] = []
    command_result: dict[str, Any]
    if not tau_run.exists():
        add_blocker(blockers, "BLOCKED_TAU_SKILL_WRAPPER_MISSING")
        command_result = {"command": [str(tau_run), "doctor"], "exit_code": 127, "stdout": "", "stderr": "missing tau run.sh"}
    else:
        completed = subprocess.run([str(tau_run), "doctor"], text=True, capture_output=True, check=False, timeout=180)
        parsed_stdout: dict[str, Any] | None = None
        if completed.stdout.strip():
            try:
                parsed = json.loads(completed.stdout)
                if isinstance(parsed, dict):
                    parsed_stdout = parsed
            except json.JSONDecodeError:
                parsed_stdout = None
        command_result = {
            "command": [str(tau_run), "doctor"],
            "exit_code": completed.returncode,
            "stdout_sha256": f"sha256:{hashlib.sha256(completed.stdout.encode('utf-8')).hexdigest()}",
            "stderr_sha256": f"sha256:{hashlib.sha256(completed.stderr.encode('utf-8')).hexdigest()}",
            "stderr_tail": completed.stderr[-2000:],
            "parsed_stdout": {
                "schema": parsed_stdout.get("schema") if parsed_stdout else None,
                "ok": parsed_stdout.get("ok") if parsed_stdout else None,
                "provider_live": parsed_stdout.get("provider_live") if parsed_stdout else None,
                "can_call_tau_cli": parsed_stdout.get("can_call_tau_cli") if parsed_stdout else None,
                "can_call_tau_doctor": parsed_stdout.get("can_call_tau_doctor") if parsed_stdout else None,
                "can_run_local_sanity": parsed_stdout.get("can_run_local_sanity") if parsed_stdout else None,
                "can_run_provider_live_lane": parsed_stdout.get("can_run_provider_live_lane") if parsed_stdout else None,
                "tau_runtime_status": (parsed_stdout.get("tau_runtime_doctor") or {}).get("status")
                if parsed_stdout
                else None,
            },
        }
        if completed.returncode != 0:
            add_blocker(blockers, "BLOCKED_TAU_DOCTOR_FAILED")
        if parsed_stdout and parsed_stdout.get("provider_live") is not False:
            add_blocker(blockers, "BLOCKED_TAU_DOCTOR_PROVIDER_LIVE")
    receipt = {
        "schema": "create_status_surface.tau_doctor_bridge_receipt.v1",
        "generated_at": now(),
        "status": "PASS_TAU_DOCTOR_BRIDGE" if not blockers else "BLOCKED_TAU_DOCTOR_BRIDGE",
        "mocked": False,
        "live": True,
        "provider_live": False,
        "paid_call_authorized": False,
        "actual_provider_call_attempts": 0,
        "live_tau_dag_execution_started": False,
        "tau_run": str(tau_run),
        "command_result": command_result,
        "blockers": blockers,
        "claims": {
            "proves": ["the create-status-surface skill can invoke the local Tau wrapper doctor command"],
            "does_not_prove": ["Tau DAG execution", "Herdr provider execution", "GitHub mutation", "provider readiness"],
        },
    }
    write_json(receipt_out, receipt)
    emit(receipt, json_output)


if __name__ == "__main__":
    app()
