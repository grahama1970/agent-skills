#!/usr/bin/env python3
"""Deterministic section-by-section Dreamer runner.

This script is the executable guardrail for Dreamer orchestration. It scans the
Persona-Dream pipeline in canonical order, selects the first blocked/stale/missing
phase, writes a work order for that owner, and optionally executes only that
phase's deterministic local command.

It intentionally does not call live or paid providers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "persona_dream.dreamer_sequential_runner.v2"
PASS_PREFIXES = ("PASS", "PHASE_02_COMPLETE", "COMPLETE", "PROVIDER_READY")
FAIL_VALUES = {"FAIL", "FAILED", "BLOCKED", "NEEDS_CHANGES", "ERROR", "TIMEOUT", "PARTIAL"}
SCILLM_DEFAULT_BASE_URL = "http://localhost:4001"
SCILLM_DEFAULT_AUTH = "Bearer sk-dev-proxy-123"


@dataclass(frozen=True)
class Phase:
    phase_id: str
    report_anchor: str
    owner: str
    receipt_candidates: tuple[str, ...]
    artifact_candidates: tuple[str, ...] = ()
    execute_command: tuple[str, ...] | None = None
    provider_sensitive: bool = False


PHASES: tuple[Phase, ...] = (
    Phase(
        "idea",
        "#idea-phase",
        "dreamer",
        ("pipeline_review_8892/phase_01_idea_anti_hallucination_gate_receipt.json",),
        ("pipeline_review_8892/artifacts/phase_01_idea_anti_hallucination_gate.json",),
    ),
    Phase(
        "memories",
        "#memories-used",
        "dba-auditor",
        ("pipeline_review_8892/phase_02_memory_anti_hallucination_gate_receipt.json",),
        ("pipeline_review_8892/artifacts/phase_02_memory_anti_hallucination_gate.json",),
        ("pipeline-phase02-recall",),
    ),
    Phase(
        "story",
        "#story-phase",
        "script-writer",
        (
            "pipeline_review_8892/phase_03_story_package_anti_hallucination_gate_receipt.json",
            "story_package/story_package_phase3_gate_receipt_v2.json",
        ),
        ("pipeline_review_8892/artifacts/phase_03_story_package_anti_hallucination_gate.json",),
    ),
    Phase(
        "producer",
        "#producer-phase",
        "producer",
        ("pipeline_review_8892/phase_04_creative_leadership_anti_hallucination_gate_receipt.json",),
        ("pipeline_review_8892/artifacts/phase_04_creative_leadership_anti_hallucination_gate.json",),
    ),
    Phase(
        "references",
        "#refs-phase",
        "dreamer",
        ("pipeline_review_8892/phase_05_contact_sheets_anti_hallucination_gate_receipt.json",),
        ("pipeline_review_8892/artifacts/phase_05_contact_sheets_anti_hallucination_gate.json",),
        ("phase-05-contact-sheet-gate", "--write-gate", "--json"),
    ),
    Phase(
        "script",
        "#script-phase",
        "script-writer",
        (
            "pipeline_review_8892/rollback_snapshots/script_three_column_matrix_repair_20260620T144222Z/script_three_column_matrix_repair_receipt.json",
            "pipeline_review_8892/rollback_snapshots/script_production_table_repair_20260620T143048Z/script_production_table_repair_receipt.json",
            "pipeline_review_8892/rollback_snapshots/full_script_scope_repair_20260620T141119Z/full_script_scope_repair_receipt.json",
        ),
        ("timed_beats.json", "pipeline_review_8892/06-script.html"),
    ),
    Phase(
        "voice",
        "#voice-section",
        "voice-lane",
        (
            "voice_clone_candidates/kling_voice_id_source_receipt.json",
            "pipeline_review_8892/voice_clone_candidates/kling_voice_id_source_receipt.json",
            "pipeline_review_8892/rollback_snapshots/full_report_voice_section_restore_20260620T124203Z/voice_section_restore_receipt.json",
        ),
        ("pipeline_review_8892/07-voice.html",),
        provider_sensitive=True,
    ),
    Phase(
        "panels",
        "#panels-phase",
        "persona-dream-panel-repair-gate",
        (
            "pipeline_review_8892/artifacts/panel_entity_environment_interaction_gate_receipt.json",
            "storyboard/panel_entity_environment_interaction_gate_receipt.json",
        ),
        (
            "pipeline_review_8892/artifacts/active_panel_visual_identity_gate_20260620T0308Z_FAIL.json",
            "pipeline_review_8892/artifacts/panel_visual_gate_course_corrections_20260620T0312Z/aggregate_visual_gate_course_corrections.json",
        ),
    ),
    Phase(
        "gate",
        "#gate-phase",
        "dreamer",
        ("provider_packet/readiness_receipt.json", "provider_packet/provider_packet_validation_receipt.json"),
        ("pipeline_review_8892/artifacts/ci_gate_checks.json",),
    ),
    Phase(
        "provider_dry_run",
        "#provider-dry-run",
        "dreamer",
        ("provider_packet/provider_request_dry_run.json", "provider_packet/kling_omni_scene_packet_dry_run.json"),
        provider_sensitive=True,
    ),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def candidate_paths(run_root: Path, rels: tuple[str, ...]) -> list[Path]:
    return [run_root / rel for rel in rels]


def first_existing(run_root: Path, rels: tuple[str, ...]) -> Path | None:
    existing = [p for p in candidate_paths(run_root, rels) if p.exists()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def value_status(data: dict[str, Any]) -> tuple[str, list[str]]:
    blockers: list[str] = []
    raw_values: list[str] = []
    for key in ("status", "verdict", "phase_verdict", "gate"):
        value = data.get(key)
        if isinstance(value, str):
            raw_values.append(value)
    for key in ("unresolved_blockers", "blockers", "blocking_findings", "blocking_repairs", "failures"):
        value = data.get(key)
        if isinstance(value, list) and value:
            blockers.extend(str(item) for item in value[:20])
    for key in ("failure_count", "blocked_or_failed_count", "dimension_failure_count", "sidecar_failure_count"):
        value = data.get(key)
        if isinstance(value, int) and value > 0:
            blockers.append(f"{key}={value}")

    if blockers:
        return "FAIL", blockers
    if any(value in FAIL_VALUES for value in raw_values):
        return "FAIL", raw_values
    if any(value.startswith(PASS_PREFIXES) for value in raw_values):
        return "PASS", []
    return "UNKNOWN", raw_values or ["no status/verdict fields"]


def phase_status(run_root: Path, phase: Phase) -> dict[str, Any]:
    receipt = first_existing(run_root, phase.receipt_candidates)
    artifacts = [p for p in candidate_paths(run_root, phase.artifact_candidates) if p.exists()]
    if receipt is None:
        return {
            "phase": phase.phase_id,
            "status": "MISSING",
            "owner": phase.owner,
            "report_anchor": phase.report_anchor,
            "receipt": None,
            "artifacts": [str(p) for p in artifacts],
            "blockers": ["missing_phase_receipt"],
        }

    data = read_json(receipt)
    if data is None:
        return {
            "phase": phase.phase_id,
            "status": "FAIL",
            "owner": phase.owner,
            "report_anchor": phase.report_anchor,
            "receipt": str(receipt),
            "receipt_sha256": sha256_path(receipt),
            "artifacts": [str(p) for p in artifacts],
            "blockers": ["receipt_json_parse_failed"],
        }

    status, blockers = value_status(data)
    artifact_failures: list[str] = []
    for artifact in artifacts:
        artifact_data = read_json(artifact)
        if artifact_data is None:
            continue
        artifact_status, artifact_blockers = value_status(artifact_data)
        if artifact_status == "FAIL":
            artifact_failures.extend(f"{artifact.name}:{item}" for item in artifact_blockers)
        if phase.phase_id == "panels" and artifact_data.get("overall") not in (None, "PASS"):
            failing = artifact_data.get("failing_panels", [])
            artifact_failures.append(f"{artifact.name}:overall={artifact_data.get('overall')} failing_panels={failing}")
    if artifact_failures:
        status = "FAIL"
        blockers.extend(artifact_failures)

    return {
        "phase": phase.phase_id,
        "status": status,
        "owner": phase.owner,
        "report_anchor": phase.report_anchor,
        "receipt": str(receipt),
        "receipt_sha256": sha256_path(receipt),
        "artifacts": [str(p) for p in artifacts],
        "blockers": blockers,
    }


def build_work_order(run_root: Path, out_dir: Path, active: dict[str, Any]) -> Path:
    work_order = {
        "schema": "persona_dream.dreamer_phase_work_order.v1",
        "created_at": now_iso(),
        "run_root": str(run_root),
        "active_phase": active["phase"],
        "owner": active["owner"],
        "report_anchor": active["report_anchor"],
        "receipt": active.get("receipt"),
        "receipt_sha256": active.get("receipt_sha256"),
        "blockers": active.get("blockers", []),
        "instructions": {
            "mode": "repair_only_this_phase",
            "must_not_advance_to_later_phases": True,
            "must_emit_receipt": True,
            "live_or_paid_provider_call_authorized": False,
        },
    }
    path = out_dir / f"{active['phase']}_work_order.json"
    atomic_write_json(path, work_order)
    return path


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_active_phase(script_dir: Path, run_root: Path, phase: Phase, out_dir: Path) -> dict[str, Any]:
    if phase.execute_command is None:
        return {
            "executed": False,
            "reason": "no_deterministic_execute_command_for_phase",
        }
    if phase.provider_sensitive:
        return {
            "executed": False,
            "reason": "provider_sensitive_phase_not_executed_by_runner",
        }

    run_sh = script_dir.parent / "run.sh"
    cmd = [str(run_sh), *phase.execute_command, "--run-root", str(run_root)]
    if phase.phase_id == "references" and "--json" not in cmd:
        cmd.append("--json")
    proc = subprocess.run(
        cmd,
        cwd=str(script_dir.parent),
        capture_output=True,
        text=True,
        timeout=900,
    )
    result = {
        "executed": True,
        "command": cmd,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }
    atomic_write_json(out_dir / f"{phase.phase_id}_command_result.json", result)
    return result


def owner_prompt(active: dict[str, Any], work_order_path: Path, run_root: Path) -> str:
    return f"""You are the bounded owner for one Persona-Dream pipeline phase.

Do not work on later phases. Do not call Kling, live providers, paid providers,
or direct provider APIs. Do not declare global completion.

Active phase: {active['phase']}
Owner: {active['owner']}
Run root: {run_root}
Report anchor: {active['report_anchor']}
Work order JSON: {work_order_path}
Current receipt: {active.get('receipt')}
Current blockers:
{json.dumps(active.get('blockers', []), indent=2)}

Task:
1. Read the work order and relevant local artifacts.
2. Repair or diagnose only this active phase.
3. Emit a concrete receipt path or explain the exact blocker preventing repair.
4. Preserve rollback/supersession evidence for any file mutation.
5. Stop after this phase; do not advance to panels, gate, movie, or provider submission.
"""


def scillm_opencode_run(
    *,
    active: dict[str, Any],
    work_order_path: Path,
    run_root: Path,
    out_dir: Path,
    base_url: str,
    auth_header: str,
    opencode_agent: str,
    timeout_s: int,
) -> dict[str, Any]:
    """Dispatch the active phase to Scillm OpenCode serve and save response."""
    if active["phase"] in {"voice", "provider_dry_run"}:
        return {
            "executed": False,
            "dispatch": "scillm-opencode",
            "reason": "provider_sensitive_phase_not_dispatched",
        }

    payload = {
        "prompt": owner_prompt(active, work_order_path, run_root),
        "agent": opencode_agent,
        "skills": ["memory", "scillm", "persona-dream", "best-practices-subagent"],
        "timeout_s": timeout_s,
        "cleanup_session": True,
        "cwd": "/home/graham/workspace/experiments/agent-skills",
        "scillm_metadata": {
            "schema": "persona_dream.scillm_opencode_dispatch.v1",
            "phase": active["phase"],
            "owner": active["owner"],
            "run_root": str(run_root),
            "work_order": str(work_order_path),
        },
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/scillm/opencode/runs",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": auth_header,
            "X-Caller-Skill": "persona-dream",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    dispatch_receipt = {
        "schema": "persona_dream.scillm_opencode_dispatch_receipt.v1",
        "created_at": now_iso(),
        "endpoint": str(request.full_url),
        "request": payload,
        "response": None,
        "status_code": None,
        "ok": False,
    }
    try:
        with urllib.request.urlopen(request, timeout=timeout_s + 30) as response:
            body = response.read().decode("utf-8", errors="replace")
            dispatch_receipt["status_code"] = response.status
            try:
                dispatch_receipt["response"] = json.loads(body)
            except json.JSONDecodeError:
                dispatch_receipt["response"] = {"raw_body": body[-8000:]}
            dispatch_receipt["ok"] = 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        dispatch_receipt["status_code"] = exc.code
        dispatch_receipt["response"] = {"error": body[-8000:]}
    except Exception as exc:
        dispatch_receipt["response"] = {"error": repr(exc)}

    path = out_dir / f"{active['phase']}_scillm_opencode_dispatch_receipt.json"
    atomic_write_json(path, dispatch_receipt)
    return {
        "executed": bool(dispatch_receipt["ok"]),
        "dispatch": "scillm-opencode",
        "dispatch_receipt": str(path),
        "status_code": dispatch_receipt["status_code"],
        "ok": dispatch_receipt["ok"],
        "scillm_status": (dispatch_receipt.get("response") or {}).get("status")
        if isinstance(dispatch_receipt.get("response"), dict)
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Dreamer pipeline deterministically, one section at a time.")
    parser.add_argument("command", choices=("status", "step"), help="status writes active-phase receipt; step executes active deterministic phase command or dispatch when available")
    parser.add_argument("--run-root", required=True, help="Persona-Dream run root")
    parser.add_argument("--output-dir", default=None, help="Receipt output directory")
    parser.add_argument(
        "--dispatch",
        choices=("local", "scillm-opencode"),
        default="local",
        help="Execution backend for step. local runs known deterministic commands; scillm-opencode launches the active phase owner as a bounded subagent.",
    )
    parser.add_argument("--scillm-base-url", default=SCILLM_DEFAULT_BASE_URL)
    parser.add_argument("--scillm-auth", default=SCILLM_DEFAULT_AUTH)
    parser.add_argument("--opencode-agent", default="build", help="OpenCode serve agent profile, not a chat model name")
    parser.add_argument("--timeout-s", type=int, default=900, help="Default Scillm/OpenCode timeout")
    parser.add_argument("--json", action="store_true", help="Print full JSON receipt")
    args = parser.parse_args()

    run_root = Path(args.run_root).resolve()
    if not run_root.exists():
        print(json.dumps({"error": f"run root not found: {run_root}"}), file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.output_dir).resolve() if args.output_dir else run_root / "pipeline_review_8892" / "artifacts" / "dreamer_sequential_runner" / stamp
    statuses = [phase_status(run_root, phase) for phase in PHASES]
    active_idx = next((i for i, item in enumerate(statuses) if item["status"] != "PASS"), None)
    active = None if active_idx is None else statuses[active_idx]
    active_phase = None if active is None else PHASES[active_idx]
    work_order_path = None
    execution = None

    if active is not None:
        work_order_path = build_work_order(run_root, out_dir, active)
        if args.command == "step" and active_phase is not None:
            if args.dispatch == "scillm-opencode":
                execution = scillm_opencode_run(
                    active=active,
                    work_order_path=work_order_path,
                    run_root=run_root,
                    out_dir=out_dir,
                    base_url=args.scillm_base_url,
                    auth_header=args.scillm_auth,
                    opencode_agent=args.opencode_agent,
                    timeout_s=args.timeout_s,
                )
            else:
                execution = run_active_phase(Path(__file__).resolve().parent, run_root, active_phase, out_dir)
            statuses = [phase_status(run_root, phase) for phase in PHASES]
            active_idx = next((i for i, item in enumerate(statuses) if item["status"] != "PASS"), None)
            active = None if active_idx is None else statuses[active_idx]

    receipt = {
        "schema": SCHEMA,
        "created_at": now_iso(),
        "command": args.command,
        "run_root": str(run_root),
        "phase_order": [phase.phase_id for phase in PHASES],
        "phase_statuses": statuses,
        "active_phase": None if active is None else active["phase"],
        "active_owner": None if active is None else active["owner"],
        "active_report_anchor": None if active is None else active["report_anchor"],
        "active_blockers": [] if active is None else active.get("blockers", []),
        "work_order": None if work_order_path is None else str(work_order_path),
        "execution": execution,
        "dispatch": args.dispatch,
        "advance_allowed": active is None,
        "live_call_performed": False,
        "paid_call_performed": False,
        "stop_condition": "all phases pass" if active is None else f"repair {active['phase']} and rerun this runner",
    }
    receipt_path = out_dir / "dreamer_sequential_runner_receipt.json"
    atomic_write_json(receipt_path, receipt)
    latest = run_root / "pipeline_review_8892" / "artifacts" / "dreamer_sequential_runner_latest.json"
    atomic_write_json(latest, {"receipt": str(receipt_path), "updated_at": now_iso(), "active_phase": receipt["active_phase"]})

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"receipt={receipt_path}")
        print(f"active_phase={receipt['active_phase']}")
        print(f"active_owner={receipt['active_owner']}")
        print(f"advance_allowed={receipt['advance_allowed']}")
        if receipt["active_blockers"]:
            print("blockers=" + "; ".join(str(item) for item in receipt["active_blockers"][:10]))
    return 0 if receipt["advance_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
