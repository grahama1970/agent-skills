#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

READY_STATUSES = {"READY", "READY_RETRY"}
DEFAULT_TAU_ROOT = Path(os.environ.get("TAU_ROOT") or "/home/graham/workspace/experiments/tau")
DEFAULT_AGENT_REGISTRY_ROOT = Path(
    os.environ.get("AGENT_SKILLS_AGENT_REGISTRY_ROOT")
    or Path(__file__).resolve().parents[2]
)
DEFAULT_UV_BIN = os.environ.get("UV_BIN") or "/home/graham/.local/bin/uv"
DEFAULT_GITHUB_REPO = os.environ.get("MONITOR_SPARTA_GITHUB_REPO", "grahama1970/chatgpt-lab")
DEFAULT_GOAL_ID = os.environ.get("MONITOR_SPARTA_GOAL_ID", "monitor-sparta-subagent-loop")
DEFAULT_GOAL_VERSION = int(os.environ.get("MONITOR_SPARTA_GOAL_VERSION", "1"))
DEFAULT_GOAL_HASH = os.environ.get("MONITOR_SPARTA_GOAL_HASH", "sha256:monitor-sparta-subagent-loop")

DISPLAY_BY_SUBAGENT = {
    "dba-auditor-v2": "Dewey",
    "prompt-health-auditor": "Petey",
    "qra-auditor": "Qbert",
    "research-auditor": "Ryan",
}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@contextlib.contextmanager
def queue_lock(queue_path: Path) -> Iterator[None]:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = queue_path.with_suffix(queue_path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL in {path}:{lineno}: {exc}") from exc
            if isinstance(value, dict):
                rows.append(value)
    return rows


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(row), sort_keys=True, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def latest_by_issue(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        issue_id = row.get("issue_id")
        if issue_id:
            latest[str(issue_id)] = dict(row)
    return latest


def claim_one(
    queue_path: Path,
    *,
    owner: str,
    run_id: str,
    allowed_lanes: set[str],
    claim_statuses: set[str] | None = None,
    issue_id: str | None = None,
) -> dict[str, Any] | None:
    statuses = set(claim_statuses or READY_STATUSES)
    requested_issue_id = str(issue_id).strip() if issue_id else None
    with queue_lock(queue_path):
        latest = latest_by_issue(read_jsonl(queue_path))
        candidates = [
            row
            for row in latest.values()
            if row.get("status") in statuses
            and str(row.get("owner_subagent") or "") == owner
            and str(row.get("lane") or "") in allowed_lanes
            and (requested_issue_id is None or str(row.get("issue_id") or "") == requested_issue_id)
        ]
        candidates.sort(key=lambda row: (int(row.get("priority") or 999), str(row.get("created_at") or ""), str(row.get("issue_id") or "")))
        if not candidates:
            return None
        issue = dict(candidates[0])
        update = dict(issue)
        update["status"] = "RUNNING"
        update["claimed_by"] = owner
        update["claimed_run_id"] = run_id
        update["claimed_at"] = utc_now()
        update["updated_at"] = utc_now()
        update["history_event"] = "issue_claimed"
        append_jsonl(queue_path, update)
        return update


def update_issue(queue_path: Path, issue: Mapping[str, Any], *, status: str, run_id: str, event: str, fields: Mapping[str, Any] | None = None) -> dict[str, Any]:
    with queue_lock(queue_path):
        row = dict(issue)
        row.update(dict(fields or {}))
        row["status"] = status
        row["updated_at"] = utc_now()
        row["completed_run_id"] = run_id
        row["history_event"] = event
        append_jsonl(queue_path, row)
        return row


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_tau_agent_handoff(
    *,
    previous_subagent: str,
    next_agent: str,
    reason: str,
    result_status: str,
    result_summary: str,
    context_summary: str,
    rationale: str,
    stop_condition: str,
    issue_id: str | None = None,
    evidence: Sequence[str] | None = None,
    artifacts: Sequence[str] | None = None,
    required_evidence: Sequence[str] | None = None,
    executor: str = "either",
    github_repo: str = DEFAULT_GITHUB_REPO,
    goal_id: str = DEFAULT_GOAL_ID,
    goal_version: int = DEFAULT_GOAL_VERSION,
    goal_hash: str = DEFAULT_GOAL_HASH,
) -> dict[str, Any]:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": {
            "repo": github_repo,
            "target": issue_id or "new",
        },
        "goal": {
            "goal_id": goal_id,
            "goal_version": goal_version,
            "goal_hash": goal_hash,
        },
        "previous_subagent": previous_subagent,
        "context": {
            "summary": context_summary,
            "artifacts": [str(path) for path in (artifacts or []) if path],
        },
        "result": {
            "status": result_status,
            "summary": result_summary,
            "evidence": [str(path) for path in (evidence or []) if path],
        },
        "rationale": rationale,
        "next_agent": {
            "name": next_agent,
            "executor": executor,
            "reason": reason,
        },
        "required_evidence": [str(item) for item in (required_evidence or []) if item],
        "stop_condition": stop_condition,
    }


def validate_tau_agent_handoff(
    handoff_path: Path,
    *,
    tau_root: Path = DEFAULT_TAU_ROOT,
    agent_registry_root: Path | None = DEFAULT_AGENT_REGISTRY_ROOT,
    active_goal_hash: str = DEFAULT_GOAL_HASH,
) -> dict[str, Any]:
    script = (
        "import json, sys; "
        "from pathlib import Path; "
        "from tau_coding.generated_ticket import validate_agent_handoff; "
        "payload=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')); "
        "registry=Path(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None; "
        "result=validate_agent_handoff(payload, active_goal_hash=sys.argv[2], agent_registry_root=registry); "
        "print(json.dumps({'ok': result.ok, 'next_agent': result.next_agent, 'errors': list(result.errors)}, sort_keys=True))"
    )
    cmd = [DEFAULT_UV_BIN, "run", "python", "-c", script, str(handoff_path), active_goal_hash]
    if agent_registry_root is not None:
        cmd.append(str(agent_registry_root))
    proc = subprocess.run(
        cmd,
        cwd=str(tau_root),
        env={**os.environ, "PYTHONPATH": str(tau_root / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")},
        text=True,
        capture_output=True,
        check=False,
    )
    payload: dict[str, Any]
    try:
        payload = json.loads(proc.stdout)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    payload.update(
        {
            "schema": "tau.agent_handoff.validation_receipt.v1",
            "handoff_path": str(handoff_path),
            "tau_root": str(tau_root),
            "agent_registry_root": str(agent_registry_root) if agent_registry_root is not None else None,
            "active_goal_hash": active_goal_hash,
            "exit_code": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-4000:],
            "mocked": False,
            "live": False,
        }
    )
    payload["ok"] = bool(payload.get("ok")) and proc.returncode == 0
    return payload


def write_tau_handoff_artifacts(
    run_dir: Path,
    *,
    filename_stem: str,
    handoff: Mapping[str, Any],
    active_goal_hash: str = DEFAULT_GOAL_HASH,
) -> dict[str, Any]:
    handoff_path = run_dir / f"{filename_stem}.tau_handoff.json"
    validation_path = run_dir / f"{filename_stem}.tau_validation.json"
    write_json(handoff_path, handoff)
    validation = validate_tau_agent_handoff(handoff_path, active_goal_hash=active_goal_hash)
    write_json(validation_path, validation)
    return {
        "schema": "tau.agent_handoff.artifacts.v1",
        "handoff_path": str(handoff_path),
        "validation_path": str(validation_path),
        "validation": validation,
        "ok": bool(validation.get("ok")),
    }


def run_registry_decision(
    *,
    memory_root: Path,
    output: Path,
    key: str | None = None,
    decision_type: str,
    decision: str,
    status: str,
    issuer_subagent: str,
    issuer_display_name: str,
    subject_subagent: str,
    subject_display_name: str,
    lane: str,
    issue_id: str,
    summary: str,
    rationale: str,
    decision_reason: str,
    next_action: Mapping[str, Any] | None = None,
    needed_agent: str | None = None,
    needed_display_name: str | None = None,
    collection: str | None = None,
    category: str | None = None,
    framework: str | None = None,
    run_id: str | None = None,
    receipt_path: Path | None = None,
    artifact_paths: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(memory_root / "scripts" / "validation" / "subagent_approval_registry.py"),
        "decision",
        "--decision-type",
        decision_type,
        "--decision",
        decision,
        "--status",
        status,
        "--issuer-subagent",
        issuer_subagent,
        "--issuer-display-name",
        issuer_display_name,
        "--subject-subagent",
        subject_subagent,
        "--subject-display-name",
        subject_display_name,
        "--lane",
        lane,
        "--issue-id",
        issue_id,
        "--summary",
        summary,
        "--rationale",
        rationale,
        "--decision-reason",
        decision_reason,
        "--next-action-json",
        json.dumps(dict(next_action or {}), sort_keys=True),
        "--output",
        str(output),
    ]
    if receipt_path:
        cmd.extend(["--receipt-path", str(receipt_path)])
    if artifact_paths is not None:
        cmd.extend(["--artifact-paths-json", json.dumps(dict(artifact_paths), sort_keys=True)])
    if key:
        cmd.extend(["--key", key])
    if needed_agent:
        cmd.extend(["--needed-agent", needed_agent])
    if needed_display_name:
        cmd.extend(["--needed-display-name", needed_display_name])
    if collection:
        cmd.extend(["--collection", collection])
    if category:
        cmd.extend(["--category", category])
    if framework:
        cmd.extend(["--framework", framework])
    if run_id:
        cmd.extend(["--issuer-run-id", run_id])
    proc = subprocess.run(cmd, cwd=str(memory_root), text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return {
            "ok": False,
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except Exception:
        payload = {"ok": True, "stdout": proc.stdout[-4000:]}
    payload["cmd"] = cmd
    payload["exit_code"] = proc.returncode
    return payload


def run_registry_latest_approval(
    *,
    memory_root: Path,
    output: Path,
    category: str,
    framework: str | None,
    lane: str,
    approval_type: str = "prompt_health",
    consumer_subagent: str = "qra-auditor",
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(memory_root / "scripts" / "validation" / "subagent_approval_registry.py"),
        "latest-approval",
        "--approval-type",
        approval_type,
        "--consumer-subagent",
        consumer_subagent,
        "--category",
        category,
        "--lane",
        lane,
        "--output",
        str(output),
    ]
    if framework:
        cmd.extend(["--framework", framework])
    proc = subprocess.run(cmd, cwd=str(memory_root), text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return {
            "ok": False,
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except Exception:
        payload = {"ok": True, "stdout": proc.stdout[-4000:]}
    payload["cmd"] = cmd
    payload["exit_code"] = proc.returncode
    return payload


def run_registry_check(
    *,
    memory_root: Path,
    output: Path,
    category: str,
    framework: str | None,
    lane: str,
    prompt_contract_hash: str,
    expected_response_hash: str | None,
    validator_hash: str | None,
    approval_type: str = "prompt_health",
    consumer_subagent: str = "qra-auditor",
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(memory_root / "scripts" / "validation" / "subagent_approval_registry.py"),
        "check",
        "--approval-type",
        approval_type,
        "--consumer-subagent",
        consumer_subagent,
        "--category",
        category,
        "--lane",
        lane,
        "--prompt-contract-hash",
        prompt_contract_hash,
        "--output",
        str(output),
    ]
    if framework:
        cmd.extend(["--framework", framework])
    if expected_response_hash:
        cmd.extend(["--expected-response-hash", expected_response_hash])
    if validator_hash:
        cmd.extend(["--validator-hash", validator_hash])
    proc = subprocess.run(cmd, cwd=str(memory_root), text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return {
            "ok": False,
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except Exception:
        payload = {"ok": True, "stdout": proc.stdout[-4000:]}
    payload["cmd"] = cmd
    payload["exit_code"] = proc.returncode
    return payload
