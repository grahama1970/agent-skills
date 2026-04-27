"""Runtime state and artifact helpers for /ask."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ASK_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = ASK_ROOT / ".ask_artifacts"

VALID_REVIEW_CONTEXTS = {"fresh", "fork"}
VALID_INHERIT_MEMORY = {"yes", "no", "summary"}
VALID_INHERIT_SKILLS = {"yes", "no", "selected"}
VALID_INHERIT_PROJECT_CONTEXT = {"yes", "no"}

NEEDS_ATTENTION_STATES = {
    "needs_target",
    "needs_repo_access",
    "needs_model_fallback",
    "needs_memory_health",
    "needs_freshness_confirmation",
    "needs_verifier_fix",
    "stalled_no_heartbeat",
    "stalled_no_artifact_progress",
}

DEFAULT_CONTEXT_POLICIES: dict[str, dict[str, Any]] = {
    "ask": {
        "review_context": "fresh",
        "inherit_memory": "yes",
        "inherit_skills": "selected",
        "inherit_project_context": "no",
        "memory_as_evidence": False,
    },
    "oracle": {
        "review_context": "fresh",
        "inherit_memory": "summary",
        "inherit_skills": "selected",
        "inherit_project_context": "no",
        "memory_as_evidence": False,
    },
    "parallel-review": {
        "review_context": "fresh",
        "inherit_memory": "summary",
        "inherit_skills": "selected",
        "inherit_project_context": "no",
        "memory_as_evidence": False,
    },
    "roundtable": {
        "review_context": "fresh",
        "inherit_memory": "summary",
        "inherit_skills": "selected",
        "inherit_project_context": "no",
        "memory_as_evidence": False,
    },
    "deep-review": {
        "review_context": "fresh",
        "inherit_memory": "summary",
        "inherit_skills": "selected",
        "inherit_project_context": "no",
        "memory_as_evidence": False,
    },
    "review-and-fix": {
        "review_context": "fork",
        "inherit_memory": "summary",
        "inherit_skills": "selected",
        "inherit_project_context": "yes",
        "memory_as_evidence": False,
        "requires_worktree": True,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_run_id(mode: str) -> str:
    safe_mode = "".join(ch if ch.isalnum() else "-" for ch in mode.lower()).strip("-") or "ask"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{safe_mode}-{os.getpid()}-{int(time.time() * 1000) % 100000:05d}"


def artifact_root(root: str | Path | None = None) -> Path:
    path = Path(root) if root else DEFAULT_ARTIFACT_ROOT
    if not path.is_absolute():
        path = ASK_ROOT / path
    return path


def mode_artifact_dir(mode: str, run_id: str, root: str | Path | None = None) -> Path:
    return artifact_root(root) / mode / run_id


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def create_run(
    mode: str,
    *,
    question: str = "",
    target: str | None = None,
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    resolved_run_id = run_id or new_run_id(mode)
    run_dir = mode_artifact_dir(mode, resolved_run_id, root=root)
    run_dir.mkdir(parents=True, exist_ok=True)
    request = {
        "run_id": resolved_run_id,
        "mode": mode,
        "question": question,
        "target": target or "",
        "artifact_dir": str(run_dir),
        "created_at": utc_now(),
        "metadata": metadata or {},
    }
    status = {
        "run_id": resolved_run_id,
        "mode": mode,
        "state": "running",
        "started_at": request["created_at"],
        "updated_at": request["created_at"],
        "last_heartbeat": request["created_at"],
        "artifact_dir": str(run_dir),
        "verifier_status": "",
        "final_verdict": "",
        "needs_attention": "",
        "failure_reason": "",
        "artifact_paths": [],
    }
    _write_json(run_dir / "request.json", request)
    _write_json(run_dir / "status.json", status)
    append_event(resolved_run_id, mode, "run_started", root=root, data={"target": target or ""})
    return {**request, "status": status}


def append_event(
    run_id: str,
    mode: str,
    event: str,
    *,
    data: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> None:
    run_dir = mode_artifact_dir(mode, run_id, root=root)
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"time": utc_now(), "event": event, "data": data or {}}, sort_keys=True) + "\n")


def write_status(
    run_id: str,
    mode: str,
    *,
    root: str | Path | None = None,
    **updates: Any,
) -> dict[str, Any]:
    run_dir = mode_artifact_dir(mode, run_id, root=root)
    status_path = run_dir / "status.json"
    status = _read_json(status_path) if status_path.exists() else {"run_id": run_id, "mode": mode}
    status.update(updates)
    status["updated_at"] = utc_now()
    if "last_heartbeat" not in updates:
        status["last_heartbeat"] = status["updated_at"]
    _write_json(status_path, status)
    return status


def complete_run(
    run_id: str,
    mode: str,
    *,
    artifact_paths: list[str] | None = None,
    final_verdict: str = "",
    verifier_status: str = "",
    root: str | Path | None = None,
) -> dict[str, Any]:
    append_event(run_id, mode, "run_completed", root=root, data={"final_verdict": final_verdict})
    return write_status(
        run_id,
        mode,
        root=root,
        state="completed",
        completed_at=utc_now(),
        artifact_paths=artifact_paths or [],
        final_verdict=final_verdict,
        verifier_status=verifier_status,
        needs_attention="",
    )


def fail_run(
    run_id: str,
    mode: str,
    reason: str,
    *,
    needs_attention: str = "",
    root: str | Path | None = None,
) -> dict[str, Any]:
    if needs_attention and needs_attention not in NEEDS_ATTENTION_STATES:
        raise ValueError(f"Unknown needs-attention state: {needs_attention}")
    append_event(run_id, mode, "run_failed", root=root, data={"reason": reason, "needs_attention": needs_attention})
    return write_status(
        run_id,
        mode,
        root=root,
        state="failed",
        failed_at=utc_now(),
        failure_reason=reason,
        needs_attention=needs_attention,
    )


def _iter_status_files(root: str | Path | None = None) -> list[Path]:
    base = artifact_root(root)
    if not base.exists():
        return []
    return sorted(base.glob("*/*/status.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def list_runs(*, last: int = 10, mode: str | None = None, root: str | Path | None = None) -> list[dict[str, Any]]:
    runs = []
    for status_path in _iter_status_files(root):
        status = _read_json(status_path)
        if mode and status.get("mode") != mode:
            continue
        runs.append(status)
        if len(runs) >= last:
            break
    return runs


def get_run(run_id: str, *, root: str | Path | None = None) -> dict[str, Any] | None:
    for status_path in _iter_status_files(root):
        status = _read_json(status_path)
        if status.get("run_id") == run_id:
            request_path = status_path.parent / "request.json"
            return {"status": status, "request": _read_json(request_path) if request_path.exists() else {}}
    return None


def build_context_policy(
    mode: str,
    *,
    review_context: str | None = None,
    inherit_memory: str | None = None,
    inherit_skills: str | None = None,
    inherit_project_context: str | None = None,
) -> dict[str, Any]:
    policy = dict(DEFAULT_CONTEXT_POLICIES.get(mode, DEFAULT_CONTEXT_POLICIES["ask"]))
    if review_context is not None:
        if review_context not in VALID_REVIEW_CONTEXTS:
            raise ValueError(f"review_context must be one of {sorted(VALID_REVIEW_CONTEXTS)}")
        policy["review_context"] = review_context
    if inherit_memory is not None:
        if inherit_memory not in VALID_INHERIT_MEMORY:
            raise ValueError(f"inherit_memory must be one of {sorted(VALID_INHERIT_MEMORY)}")
        policy["inherit_memory"] = inherit_memory
    if inherit_skills is not None:
        if inherit_skills not in VALID_INHERIT_SKILLS:
            raise ValueError(f"inherit_skills must be one of {sorted(VALID_INHERIT_SKILLS)}")
        policy["inherit_skills"] = inherit_skills
    if inherit_project_context is not None:
        if inherit_project_context not in VALID_INHERIT_PROJECT_CONTEXT:
            raise ValueError(f"inherit_project_context must be one of {sorted(VALID_INHERIT_PROJECT_CONTEXT)}")
        policy["inherit_project_context"] = inherit_project_context
    policy["mode"] = mode
    return policy


def review_and_fix_policy(target: str, *, worktree: str | None = None) -> dict[str, Any]:
    if not worktree:
        return {
            "allowed": False,
            "target": target,
            "needs_attention": "needs_repo_access",
            "reason": "review-and-fix lanes require an explicit isolated worktree",
        }
    return {
        "allowed": True,
        "target": target,
        "worktree": worktree,
        "needs_attention": "",
        "write_policy": "isolated_worktree_only",
    }
