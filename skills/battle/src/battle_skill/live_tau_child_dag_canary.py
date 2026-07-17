"""Live Tau child DAG canary for Battle PR3."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .arena_battle_proof import _write_json
from .exploit_combiner import run_specimen_in_docker
from .exploit_specimens import ExploitSpecimen


LIVE_TAU_CANARY_SCHEMA = "battle.live_tau_child_dag_canary_receipt.v1"
TAU_PREFLIGHT_SCHEMA = "battle.tau_preflight_receipt.v1"

DEFAULT_TAU_ROOT = Path("/home/graham/workspace/experiments/tau")
REQUIRED_TAU_ARTIFACTS = [
    "research_receipts.json",
    "exploit_genome.json",
    "exploit_specimen.py",
    "specimen.json",
    "provider-authorship-receipt.json",
    "provider-code-author-boundary-receipt.json",
    "exploit-code-author-node-receipt.json",
]
FULL_CHILD_RUN_ARTIFACTS = [
    "compile_receipt.json",
    "battle_exploit_runner_handoff.json",
]
FORBIDDEN_OUTPUT_REFERENCES = [
    "arena/private/",
    "hidden-ground-truth.json",
    "hidden-vulnerability-ledger.json",
    "judge/oracle/",
]


def run_live_tau_child_dag_canary(
    *,
    battle_id: str,
    out_dir: Path,
    spawn_architect_proof: Path,
    tau_root: Path = DEFAULT_TAU_ROOT,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    """Invoke the real local Tau DAG runner and fail closed at the first gap."""

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    spawn_root = _resolve_spawn_architect_root(spawn_architect_proof)
    spawn_receipt = _read_json(spawn_root / "spawn-architect-receipt.json")
    dag_path = spawn_root / str(spawn_receipt["artifacts"]["child_exploit_dag"])
    child_packet_path = spawn_root / str(spawn_receipt["artifacts"]["child_knowledge_packet"])
    spawn_policy_path = spawn_root / str(spawn_receipt["artifacts"]["spawn_policy_decision"])

    events: list[dict[str, Any]] = [
        _event("live_tau_canary_started", artifact="live-tau-child-dag-canary-receipt.json", detail={"battle_id": battle_id})
    ]
    preflight = write_tau_preflight_receipt(
        out_dir=out_dir,
        tau_root=tau_root,
        dag_path=dag_path,
        child_packet_path=child_packet_path,
        spawn_policy_path=spawn_policy_path,
    )
    events.append(_event("tau_preflight_recorded", artifact="tau-preflight-receipt.json", detail={"status": preflight["status"]}))
    if preflight["status"] != "PASS":
        receipt = _top_receipt(
            battle_id=battle_id,
            status="BLOCKED",
            reason="tau_preflight_failed",
            out_dir=out_dir,
            spawn_architect_proof=spawn_root,
            preflight=preflight,
            tau_receipt=None,
            events=events,
            missing_artifacts=REQUIRED_TAU_ARTIFACTS,
            specimen_run_receipt=None,
        )
        _write_outputs(out_dir, receipt, events)
        return receipt

    tau_run_dir = out_dir / "tau-dag-run"
    tau_run_dir.mkdir(parents=True, exist_ok=True)
    tau_stdout = out_dir / "tau-dag-stdout.txt"
    tau_stderr = out_dir / "tau-dag-stderr.txt"
    tau_command = [
        "uv",
        "run",
        "tau",
        "dag-run",
        str(dag_path),
        "--no-resume",
        "--receipt-dir",
        str(tau_run_dir),
        "--agents-root",
        str(Path(__file__).resolve().parents[4] / "agents"),
    ]
    started = time.perf_counter()
    try:
        tau_result = subprocess.run(
            tau_command,
            cwd=tau_root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        tau_elapsed = round(time.perf_counter() - started, 6)
        tau_stdout.write_text(tau_result.stdout, encoding="utf-8")
        tau_stderr.write_text(tau_result.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        tau_elapsed = round(time.perf_counter() - started, 6)
        tau_stdout.write_text(exc.stdout or "", encoding="utf-8")
        tau_stderr.write_text(exc.stderr or "", encoding="utf-8")
        tau_result = subprocess.CompletedProcess(tau_command, returncode=124, stdout=exc.stdout or "", stderr=exc.stderr or "")

    tau_receipt_path = tau_run_dir / "dag-receipt.json"
    tau_receipt = _read_json(tau_receipt_path) if tau_receipt_path.exists() else _parse_json_text(tau_stdout.read_text(encoding="utf-8"))
    if isinstance(tau_receipt, dict) and not tau_receipt_path.exists():
        _write_json(tau_receipt_path, tau_receipt)
    if not isinstance(tau_receipt, dict):
        tau_receipt = None
    events.append(
        _event(
            "tau_child_dag_invoked",
            artifact="tau-dag-run/dag-receipt.json" if tau_receipt_path.exists() else "tau-dag-stderr.txt",
            detail={"exit_code": tau_result.returncode, "tau_receipt_present": tau_receipt is not None},
        )
    )

    private_leaks = _private_reference_findings(_child_output_artifact_paths(tau_run_dir))
    if private_leaks:
        receipt = _top_receipt(
            battle_id=battle_id,
            status="FAIL",
            reason="private_artifact_reference",
            out_dir=out_dir,
            spawn_architect_proof=spawn_root,
            preflight=preflight,
            tau_receipt=tau_receipt,
            events=events,
            missing_artifacts=[],
            specimen_run_receipt=None,
            private_reference_findings=private_leaks,
            tau_command=tau_command,
            tau_exit_code=tau_result.returncode,
            tau_elapsed_seconds=tau_elapsed,
        )
        _write_outputs(out_dir, receipt, events)
        return receipt

    if tau_receipt is None:
        receipt = _top_receipt(
            battle_id=battle_id,
            status="BLOCKED",
            reason="missing_tau_receipt",
            out_dir=out_dir,
            spawn_architect_proof=spawn_root,
            preflight=preflight,
            tau_receipt=None,
            events=events,
            missing_artifacts=REQUIRED_TAU_ARTIFACTS,
            specimen_run_receipt=None,
            tau_command=tau_command,
            tau_exit_code=tau_result.returncode,
            tau_elapsed_seconds=tau_elapsed,
        )
        _write_outputs(out_dir, receipt, events)
        return receipt

    missing_artifacts = _missing_required_tau_artifacts(tau_run_dir)
    pr3c_boundary = _pr3c_boundary_status(tau_run_dir)
    handoff_path = _find_artifact(tau_run_dir, "battle_exploit_runner_handoff.json")
    code_path = _find_artifact(tau_run_dir, "exploit_specimen.py")
    specimen_run_receipt: dict[str, Any] | None = None
    if handoff_path and code_path and not _missing_full_child_run_artifacts(tau_run_dir):
        specimen_run_receipt = _run_tau_child_specimen(
            battle_id=battle_id,
            out_dir=out_dir,
            code_path=code_path,
            docker_image="python:3.12-slim",
        )
        events.append(_event("battle_child_specimen_runner_invoked", artifact="specimen_run_receipt.json", detail={"status": specimen_run_receipt["status"]}))
    else:
        events.append(_event("tau_child_artifacts_missing", artifact="tau-dag-run/dag-receipt.json", detail={"missing_artifacts": missing_artifacts}))

    status = "PASS" if pr3c_boundary["status"] == "PASS" else "BLOCKED"
    reason = "pr3c_provider_authorship_boundary_reached" if status == "PASS" else _blocked_reason(tau_receipt=tau_receipt, missing_artifacts=missing_artifacts)
    receipt = _top_receipt(
        battle_id=battle_id,
        status=status,
        reason=reason,
        out_dir=out_dir,
        spawn_architect_proof=spawn_root,
        preflight=preflight,
        tau_receipt=tau_receipt,
        events=events,
        missing_artifacts=missing_artifacts,
        specimen_run_receipt=specimen_run_receipt,
        pr3c_boundary=pr3c_boundary,
        tau_command=tau_command,
        tau_exit_code=tau_result.returncode,
        tau_elapsed_seconds=tau_elapsed,
    )
    _write_outputs(out_dir, receipt, events)
    return receipt


def write_tau_preflight_receipt(
    *,
    out_dir: Path,
    tau_root: Path,
    dag_path: Path,
    child_packet_path: Path,
    spawn_policy_path: Path,
) -> dict[str, Any]:
    tau_root = tau_root.expanduser().resolve()
    doctor_stdout = out_dir / "tau-doctor-stdout.txt"
    doctor_stderr = out_dir / "tau-doctor-stderr.txt"
    dag_probe_stdout = out_dir / "tau-dag-run-probe-stdout.txt"
    dag_probe_stderr = out_dir / "tau-dag-run-probe-stderr.txt"
    uv_path = shutil.which("uv")
    doctor_result = _run_command(["uv", "run", "tau", "doctor"], cwd=tau_root, stdout_path=doctor_stdout, stderr_path=doctor_stderr, timeout_seconds=60)
    dag_probe = _run_command(["uv", "run", "tau", "dag-run"], cwd=tau_root, stdout_path=dag_probe_stdout, stderr_path=dag_probe_stderr, timeout_seconds=30)
    doctor_payload = _parse_json_text(doctor_stdout.read_text(encoding="utf-8"))
    dag_probe_text = dag_probe.stdout + dag_probe.stderr
    dag_run_available = "dag-run" in dag_probe_text or "Usage: tau" in dag_probe_text
    errors: list[str] = []
    if uv_path is None:
        errors.append("uv command unavailable")
    if not tau_root.exists():
        errors.append(f"Tau root missing: {tau_root}")
    if doctor_result.returncode != 0 or not isinstance(doctor_payload, dict) or doctor_payload.get("status") != "PASS":
        errors.append("uv run tau doctor did not return PASS")
    if not dag_run_available:
        errors.append("uv run tau dag-run route unavailable")
    for label, path in {
        "child_exploit_dag": dag_path,
        "child_knowledge_packet": child_packet_path,
        "spawn_policy_decision": spawn_policy_path,
    }.items():
        if not path.exists():
            errors.append(f"{label} missing: {path}")
    receipt = {
        "schema": TAU_PREFLIGHT_SCHEMA,
        "status": "PASS" if not errors else "BLOCKED",
        "mocked": False,
        "live": True,
        "tau_root": str(tau_root),
        "tau_git_commit": _git_commit(tau_root),
        "uv_path": uv_path,
        "uv_version": _uv_version(),
        "doctor": {
            "command": ["uv", "run", "tau", "doctor"],
            "exit_code": doctor_result.returncode,
            "stdout_path": _rel(out_dir, doctor_stdout),
            "stderr_path": _rel(out_dir, doctor_stderr),
            "status": doctor_payload.get("status") if isinstance(doctor_payload, dict) else None,
        },
        "dag_run_probe": {
            "command": ["uv", "run", "tau", "dag-run"],
            "exit_code": dag_probe.returncode,
            "stdout_path": _rel(out_dir, dag_probe_stdout),
            "stderr_path": _rel(out_dir, dag_probe_stderr),
            "available": dag_run_available,
        },
        "required_inputs": {
            "child_exploit_dag": {"path": str(dag_path), "exists": dag_path.exists()},
            "child_knowledge_packet": {"path": str(child_packet_path), "exists": child_packet_path.exists()},
            "spawn_policy_decision": {"path": str(spawn_policy_path), "exists": spawn_policy_path.exists()},
        },
        "errors": errors,
        "claims": {
            "proves": ["Battle checked the local Tau runtime route and required PR2 input artifacts."] if not errors else [],
            "does_not_prove": ["Tau executed the child DAG.", "A child exploit was generated.", "A child specimen was run."],
        },
    }
    _write_json(out_dir / "tau-preflight-receipt.json", receipt)
    return receipt


def _run_tau_child_specimen(*, battle_id: str, out_dir: Path, code_path: Path, docker_image: str) -> dict[str, Any]:
    specimen_dir = out_dir / "child-specimen"
    specimen_dir.mkdir(parents=True, exist_ok=True)
    (specimen_dir / "exploit.py").write_text(code_path.read_text(encoding="utf-8"), encoding="utf-8")
    target_dir = out_dir / "target"
    from .arena_subagent import _write_target_files

    _write_target_files(target_dir)
    specimen = ExploitSpecimen(
        specimen_id="tau-child-0001",
        parent_specimen_id=None,
        exploit_id=f"{battle_id}-tau-child",
        generation=0,
        chosen_method_ids=[],
        inherited_method_ids=[],
        generated_code_path="exploit.py",
        language="python",
        rationale="Tau-generated child specimen from live DAG handoff.",
        assumptions=["runnable/contact does not imply exploit success"],
        expected_observation="live Tau child specimen Docker run",
        created_by="tau_red_exploit_combiner",
        created_at=_utc_stamp(),
        agentic=True,
    )
    receipt = run_specimen_in_docker(
        out_dir=out_dir,
        specimen=specimen,
        specimen_dir=specimen_dir,
        target_dir=target_dir,
        docker_image=docker_image,
    ).to_dict()
    _write_json(out_dir / "specimen_run_receipt.json", receipt)
    return receipt


def _top_receipt(
    *,
    battle_id: str,
    status: str,
    reason: str,
    out_dir: Path,
    spawn_architect_proof: Path,
    preflight: dict[str, Any],
    tau_receipt: dict[str, Any] | None,
    events: list[dict[str, Any]],
    missing_artifacts: list[str],
    specimen_run_receipt: dict[str, Any] | None,
    pr3c_boundary: dict[str, Any] | None = None,
    private_reference_findings: list[dict[str, Any]] | None = None,
    tau_command: list[str] | None = None,
    tau_exit_code: int | None = None,
    tau_elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    scoreboard = {
        "schema": "battle.live_tau_child_dag_canary_scoreboard.v1",
        "battle_id": battle_id,
        "tau_preflight_passed": preflight.get("status") == "PASS",
        "tau_execution_attempted": tau_command is not None,
        "tau_receipt_present": tau_receipt is not None,
        "required_tau_artifacts_present": len(missing_artifacts) == 0,
        "child_specimen_run": specimen_run_receipt is not None,
        "pr3c_provider_authorship_boundary": pr3c_boundary.get("status") == "PASS" if isinstance(pr3c_boundary, dict) else False,
        "provider_live": pr3c_boundary.get("provider_live") if isinstance(pr3c_boundary, dict) else None,
        "judge_verified_exploits": 0,
        "verdict": status,
        "reason": reason,
    }
    return {
        "schema": LIVE_TAU_CANARY_SCHEMA,
        "battle_id": battle_id,
        "status": status,
        "reason": reason,
        "mocked": False,
        "live": "tau_dag_runtime",
        "agentic": True,
        "fixture_fallback_used": False,
        "tau_execution": "attempted" if tau_command else "not_attempted",
        "proof_mode": "live_tau_child_dag_canary",
        "spawn_architect_proof": str(spawn_architect_proof),
        "artifacts": {
            "tau_preflight_receipt": "tau-preflight-receipt.json",
            "tau_dag_stdout": "tau-dag-stdout.txt" if tau_command else None,
            "tau_dag_stderr": "tau-dag-stderr.txt" if tau_command else None,
            "tau_dag_receipt": "tau-dag-run/dag-receipt.json" if tau_receipt is not None else None,
            "specimen_run_receipt": "specimen_run_receipt.json" if specimen_run_receipt is not None else None,
            "events": "events.jsonl",
            "normalized": "normalized/battle-004-live-tau-child-dag.normalized.json",
        },
        "tau_command": tau_command,
        "tau_exit_code": tau_exit_code,
        "tau_elapsed_seconds": tau_elapsed_seconds,
        "tau_receipt_status": tau_receipt.get("status") if isinstance(tau_receipt, dict) else None,
        "tau_receipt_verdict": tau_receipt.get("verdict") if isinstance(tau_receipt, dict) else None,
        "missing_tau_artifacts": missing_artifacts,
        "pr3c_boundary": pr3c_boundary or {},
        "private_reference_findings": private_reference_findings or [],
        "scoreboard": scoreboard,
        "claims": {
            "proves": _proves_for(status=status, specimen_run_receipt=specimen_run_receipt, pr3c_boundary=pr3c_boundary),
            "does_not_prove": [
                "The provider-authored code compiled.",
                "The provider-authored code ran.",
                "Any exploit succeeded.",
                "Any specimen bypassed Blue.",
                "Any Blue detection, kill, or block occurred.",
                "Judge verified exploit success.",
                "Packet-level behavior was captured.",
            ],
        },
    }


def _proves_for(*, status: str, specimen_run_receipt: dict[str, Any] | None, pr3c_boundary: dict[str, Any] | None = None) -> list[str]:
    proves = [
        "Battle attempted the real local Tau DAG runtime without fixture fallback.",
        "Battle recorded Tau preflight and DAG invocation stdout/stderr artifacts.",
    ]
    if status == "PASS" and isinstance(pr3c_boundary, dict) and pr3c_boundary.get("status") == "PASS":
        proves.append("Tau reached the PR3c provider-authorship boundary with provider_live:true, agentic:true, and fixture_fallback_used:false.")
    if status == "PASS" and specimen_run_receipt is not None:
        proves.extend(["Tau produced the required child DAG artifacts.", "Battle ran the Tau child specimen in Docker."])
    return proves


def _write_outputs(out_dir: Path, receipt: dict[str, Any], events: list[dict[str, Any]]) -> None:
    events.append(_event("live_tau_canary_receipt_written", artifact="live-tau-child-dag-canary-receipt.json", detail={"status": receipt["status"], "reason": receipt["reason"]}))
    _write_events(out_dir / "events.jsonl", events)
    _write_json(
        out_dir / "normalized" / "battle-004-live-tau-child-dag.normalized.json",
        {
            "schema": "battle.live_tau_child_dag_canary_normalized.v1",
            "battle_id": receipt["battle_id"],
            "mocked": False,
            "live": "tau_dag_runtime",
            "proof_mode": "live_tau_child_dag_canary",
            "events": events,
            "scoreboard": receipt["scoreboard"],
            "claims": receipt["claims"],
        },
    )
    _write_json(out_dir / "live-tau-child-dag-canary-receipt.json", receipt)


def _resolve_spawn_architect_root(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.is_dir():
        return path
    if path.name == "spawn-architect-receipt.json":
        return path.parent
    raise RuntimeError(f"spawn architect proof must be a directory or spawn-architect-receipt.json: {path}")


def _missing_required_tau_artifacts(tau_run_dir: Path) -> list[str]:
    return [name for name in REQUIRED_TAU_ARTIFACTS if _find_artifact(tau_run_dir, name) is None]


def _missing_full_child_run_artifacts(tau_run_dir: Path) -> list[str]:
    return [name for name in FULL_CHILD_RUN_ARTIFACTS if _find_artifact(tau_run_dir, name) is None]


def _child_output_artifact_paths(tau_run_dir: Path) -> list[Path]:
    return [path for name in REQUIRED_TAU_ARTIFACTS if (path := _find_artifact(tau_run_dir, name)) is not None]


def _pr3c_boundary_status(tau_run_dir: Path) -> dict[str, Any]:
    paths = {name: _find_artifact(tau_run_dir, name) for name in REQUIRED_TAU_ARTIFACTS}
    missing = [name for name, path in paths.items() if path is None]
    errors = [f"missing required PR3c artifact: {name}" for name in missing]
    code_author_receipt = _read_optional_json(paths.get("exploit-code-author-node-receipt.json"))
    authorship = _read_optional_json(paths.get("provider-authorship-receipt.json"))
    boundary = _read_optional_json(paths.get("provider-code-author-boundary-receipt.json"))
    specimen = _read_optional_json(paths.get("specimen.json"))

    provider_live = (
        _truthy_receipt_field(code_author_receipt, "provider_live")
        and _truthy_receipt_field(authorship, "provider_live")
        and _truthy_receipt_field(boundary, "provider_live")
        and _truthy_receipt_field(specimen, "provider_live")
    )
    agentic = (
        _truthy_receipt_field(code_author_receipt, "agentic")
        and _truthy_receipt_field(authorship, "agentic")
        and _truthy_receipt_field(boundary, "agentic")
        and _truthy_receipt_field(specimen, "agentic")
    )
    fixture_fallback_used = any(
        _truthy_receipt_field(payload, "fixture_fallback_used")
        for payload in (code_author_receipt, authorship, boundary)
        if isinstance(payload, dict)
    )
    if code_author_receipt.get("status") != "PASS":
        errors.append("exploit-code-author-node-receipt.json status is not PASS")
    if authorship.get("status") != "PASS":
        errors.append("provider-authorship-receipt.json status is not PASS")
    if boundary.get("status") != "PASS":
        errors.append("provider-code-author-boundary-receipt.json status is not PASS")
    if not provider_live:
        errors.append("provider_live true attestation missing across PR3c receipts")
    if not agentic:
        errors.append("agentic true attestation missing across PR3c receipts")
    if fixture_fallback_used:
        errors.append("fixture fallback was used in PR3c provider boundary")
    if boundary.get("compile_status") != "NOT_RUN":
        errors.append("provider-code-author-boundary-receipt.json compile_status is not NOT_RUN")
    if boundary.get("runtime_status") != "NOT_RUN":
        errors.append("provider-code-author-boundary-receipt.json runtime_status is not NOT_RUN")
    if boundary.get("judge_verified_exploits") != 0:
        errors.append("provider-code-author-boundary-receipt.json judge_verified_exploits is not 0")
    code_sha = specimen.get("code_sha256")
    if not (isinstance(code_sha, str) and code_sha.startswith("sha256:")):
        errors.append("specimen.json missing sha256 code hash binding")

    return {
        "schema": "battle.pr3c_provider_authorship_boundary_status.v1",
        "status": "PASS" if not errors else "BLOCKED",
        "provider_live": bool(provider_live),
        "agentic": bool(agentic),
        "fixture_fallback_used": bool(fixture_fallback_used),
        "compile_status": boundary.get("compile_status"),
        "runtime_status": boundary.get("runtime_status"),
        "judge_verified_exploits": boundary.get("judge_verified_exploits") if boundary else 0,
        "code_sha256": code_sha,
        "artifacts": {name: str(path) for name, path in paths.items() if path is not None},
        "errors": errors,
    }


def _read_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return _read_json(path)
    except (OSError, json.JSONDecodeError, RuntimeError):
        return {}


def _truthy_receipt_field(payload: dict[str, Any], field: str) -> bool:
    return isinstance(payload, dict) and payload.get(field) is True


def _find_artifact(root: Path, name: str) -> Path | None:
    matches = sorted(root.rglob(name)) if root.exists() else []
    if matches:
        return matches[0]
    return _find_artifact_from_node_receipts(root, name)


def _find_artifact_from_node_receipts(root: Path, name: str) -> Path | None:
    if not root.exists():
        return None
    for receipt_path in sorted(root.rglob("*node-receipt.json")):
        try:
            receipt = _read_json(receipt_path)
        except (OSError, json.JSONDecodeError, RuntimeError):
            continue
        for item in receipt.get("evidence", []):
            if not isinstance(item, dict) or item.get("kind") != name:
                continue
            evidence_path = item.get("path")
            if not isinstance(evidence_path, str) or not evidence_path:
                continue
            path = Path(evidence_path)
            if path.exists():
                return path
    return None


def _private_reference_findings(paths: list[Path]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in paths:
        files = [path] if path.is_file() else sorted(path.rglob("*")) if path.exists() else []
        for item in files:
            if not item.is_file() or item.stat().st_size > 2_000_000:
                continue
            text = item.read_text(encoding="utf-8", errors="ignore")
            for forbidden in FORBIDDEN_OUTPUT_REFERENCES:
                if forbidden in text:
                    findings.append({"artifact": str(item), "forbidden_reference": forbidden})
    return findings


def _blocked_reason(*, tau_receipt: dict[str, Any], missing_artifacts: list[str]) -> str:
    if tau_receipt.get("status") != "PASS":
        return str(tau_receipt.get("verdict") or tau_receipt.get("reason") or "tau_dag_blocked").lower()
    if missing_artifacts:
        return "missing_tau_child_artifacts"
    return "tau_dag_blocked"


def _run_command(command: list[str], *, cwd: Path, stdout_path: Path, stderr_path: Path, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        result = subprocess.CompletedProcess(command, returncode=124, stdout=exc.stdout or "", stderr=exc.stderr or "")
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    return result


def _git_commit(repo: Path) -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _uv_version() -> str | None:
    result = subprocess.run(["uv", "--version"], text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _parse_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def _write_events(path: Path, events: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")


def _event(event_type: str, *, artifact: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"event_type": event_type, "artifact": artifact, "detail": detail, "source_time": _utc_stamp()}


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
