"""Runtime artifacts for ask executions."""

from __future__ import annotations

from .env import load_dotenv_once

load_dotenv_once()

import json
import os
import re
import secrets
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime_schema import RUNTIME_PROTOCOL_VERSION


SKILL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = SKILL_ROOT / ".ask_artifacts" / "runs"
DEFAULT_ARTIFACT_ROOT = SKILL_ROOT / ".ask_artifacts"
RUN_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
TERMINAL_STATES = {"answered", "completed", "no_results", "failed", "cancelled", "needs_attention", "stale"}
RESUMABLE_STATES = {"created", "running"}
INDEX_FILENAME = "index.jsonl"


def default_run_root() -> Path:
    return Path(os.environ.get("ASK_RUN_OUTPUT_DIR", str(DEFAULT_RUN_ROOT))).expanduser()


def safe_run_id(value: str) -> str:
    cleaned = RUN_ID_RE.sub("-", value.strip()).strip("-._")
    return cleaned or "ask-run"


def make_run_id(question: str) -> str:
    import hashlib

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    digest = hashlib.sha256(question.encode("utf-8")).hexdigest()[:8]
    return f"ask-{stamp}-{digest}-{secrets.token_hex(4)}"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    tmp.replace(path)


def artifact_root(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root).expanduser()
    return Path(os.environ.get("ASK_ARTIFACT_ROOT", str(DEFAULT_ARTIFACT_ROOT))).expanduser()


def new_run_id(mode: str = "ask") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return safe_run_id(f"{mode}-{stamp}-{secrets.token_hex(4)}")


def mode_artifact_dir(mode: str, run_id: str, root: Path | str | None = None) -> Path:
    return artifact_root(root) / safe_run_id(mode) / safe_run_id(run_id)


def _mode_events_path(run_id: str, mode: str, root: Path | str | None = None) -> Path:
    return mode_artifact_dir(mode, run_id, root) / "events.jsonl"


def append_event(
    run_id: str,
    mode: str,
    event: str,
    data: dict[str, Any] | None = None,
    root: Path | str | None = None,
    **fields: Any,
) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": safe_run_id(run_id),
        "mode": safe_run_id(mode),
        "event": event,
        **(data or {}),
        **fields,
    }
    events_path = _mode_events_path(run_id, mode, root)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def write_status(run_id: str, mode: str, state: str, root: Path | str | None = None, **fields: Any) -> dict[str, Any]:
    run_dir = mode_artifact_dir(mode, run_id, root)
    payload = {
        "run_id": safe_run_id(run_id),
        "mode": safe_run_id(mode),
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            "run_dir": str(run_dir),
            "request": str(run_dir / "request.json"),
            "status": str(run_dir / "status.json"),
            "events": str(run_dir / "events.jsonl"),
        },
        **fields,
    }
    atomic_write_json(run_dir / "status.json", payload)
    return payload


def create_run(
    mode: str,
    question: str = "",
    run_id: str | None = None,
    root: Path | str | None = None,
    context_policy: dict[str, Any] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    actual_run_id = safe_run_id(run_id or new_run_id(mode))
    actual_mode = safe_run_id(mode)
    run_dir = mode_artifact_dir(actual_mode, actual_run_id, root)
    run_dir.mkdir(parents=True, exist_ok=True)
    request = {
        "run_id": actual_run_id,
        "mode": actual_mode,
        "question": question,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "context_policy": context_policy or build_context_policy(actual_mode),
        **fields,
    }
    atomic_write_json(run_dir / "request.json", request)
    status = write_status(actual_run_id, actual_mode, "running", root=root, question=question)
    append_event(actual_run_id, actual_mode, "created", root=root, question=question)
    return {
        "run_id": actual_run_id,
        "mode": actual_mode,
        "run_dir": str(run_dir),
        "request_path": str(run_dir / "request.json"),
        "status_path": str(run_dir / "status.json"),
        "events_path": str(run_dir / "events.jsonl"),
        "request": request,
        "status": status,
    }


def complete_run(
    run_id: str,
    mode: str,
    artifact_paths: list[str] | None = None,
    root: Path | str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload = write_status(
        run_id,
        mode,
        "completed",
        root=root,
        completed_at=datetime.now(timezone.utc).isoformat(),
        artifact_paths=artifact_paths or [],
        **fields,
    )
    append_event(run_id, mode, "completed", root=root, artifact_paths=artifact_paths or [])
    return payload


def fail_run(run_id: str, mode: str, error: str, root: Path | str | None = None) -> dict[str, Any]:
    payload = write_status(run_id, mode, "failed", root=root, error=error)
    append_event(run_id, mode, "failed", root=root, error=error)
    return payload


def _read_mode_run(status_path: Path) -> dict[str, Any] | None:
    try:
        status = json.loads(status_path.read_text())
        request_path = status_path.with_name("request.json")
        events_path = status_path.with_name("events.jsonl")
        request = json.loads(request_path.read_text()) if request_path.exists() else {}
        events = read_event_tail(events_path, 1000)
    except (OSError, json.JSONDecodeError):
        return None
    return {
        "run_id": status.get("run_id", status_path.parent.name),
        "mode": status.get("mode", status_path.parent.parent.name),
        "run_dir": str(status_path.parent),
        "request": request,
        "status": status,
        "events": events,
    }


def get_run(run_id: str, root: Path | str | None = None) -> dict[str, Any] | None:
    base = artifact_root(root)
    safe_id = safe_run_id(run_id)
    for status_path in sorted(base.glob(f"*/{safe_id}/status.json")):
        loaded = _read_mode_run(status_path)
        if loaded:
            return loaded
    return None


def build_context_policy(
    mode: str,
    *,
    review_context: str = "fresh",
    inherit_memory: str = "summary",
    inherit_skills: str = "selected",
    inherit_project_context: str = "no",
    memory_as_evidence: bool | None = None,
) -> dict[str, Any]:
    if mode == "deep-review":
        use_memory_as_evidence = False
    else:
        use_memory_as_evidence = bool(memory_as_evidence) if memory_as_evidence is not None else inherit_memory == "full"
    return {
        "mode": mode,
        "review_context": review_context,
        "inherit_memory": inherit_memory,
        "inherit_skills": inherit_skills,
        "inherit_project_context": inherit_project_context,
        "memory_as_evidence": use_memory_as_evidence,
    }


def review_and_fix_policy(target: str, worktree: str | None = None) -> dict[str, Any]:
    if not worktree:
        return {
            "target": target,
            "allowed": False,
            "needs_attention": "needs_repo_access",
            "safe_default": "review_only",
            "resume_hint": "Provide an isolated worktree for review-and-fix.",
        }
    return {
        "target": target,
        "worktree": worktree,
        "allowed": True,
        "write_policy": "isolated_worktree_only",
    }


class AskRunState:
    """Append-only event log plus atomic status/request artifacts for one ask run."""

    def __init__(
        self,
        ask_id: str,
        output_root: Path | str | None = None,
        *,
        overwrite: bool = False,
        resume: bool = False,
    ) -> None:
        self.ask_id = safe_run_id(ask_id)
        self.output_root = Path(output_root).expanduser() if output_root else default_run_root()
        self.run_dir = self.output_root / self.ask_id
        self.request_path = self.run_dir / f"{self.ask_id}.request.json"
        self.status_path = self.run_dir / f"{self.ask_id}.status.json"
        self.events_path = self.run_dir / f"{self.ask_id}.events.jsonl"
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.state = "created"
        self.resume = resume
        if resume and overwrite:
            raise ValueError("Use either resume or overwrite, not both")
        if resume:
            if not self.run_dir.exists():
                raise FileNotFoundError(f"Run does not exist for resume: {self.run_dir}")
            existing_status = self._existing_status()
            state = existing_status.get("state")
            if state not in RESUMABLE_STATES:
                raise FileExistsError(f"Run is not resumable: {self.run_dir} state={state or 'unknown'}")
            self.started_at = str(existing_status.get("started_at") or self.started_at)
            self.state = str(state)
        if self.run_dir.exists() and not overwrite and not resume:
            raise FileExistsError(f"Run already exists: {self.run_dir}")
        if overwrite and self.run_dir.exists():
            if self.run_dir.is_symlink():
                raise FileExistsError(f"Refusing to overwrite symlinked run dir: {self.run_dir}")
            shutil.rmtree(self.run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=resume)

    @property
    def artifacts(self) -> dict[str, str]:
        return {
            "request": str(self.request_path),
            "status": str(self.status_path),
            "events": str(self.events_path),
            "artifact_manifest": str(self.run_dir / "artifact_manifest.json"),
            "run_dir": str(self.run_dir),
        }

    def write_request(self, payload: dict[str, Any]) -> None:
        if self.resume:
            if not self.request_path.exists():
                raise FileNotFoundError(f"Cannot resume run without original request: {self.request_path}")
            existing_request = self._read_existing_request()
            if not existing_request:
                raise ValueError(f"Cannot resume run with missing or malformed original request: {self.request_path}")
            conflicts = {
                key: (existing_request.get(key), payload.get(key))
                for key in ("command", "question", "scope")
                if existing_request.get(key) != payload.get(key)
            }
            if conflicts:
                raise ValueError(f"Resume request conflicts with existing run request: {conflicts}")
            current_status = self._read_current_status()
            self.event("resumed", current_step=current_status.get("current_step", ""))
            self.update("running", request=existing_request, resumed=True, current_step=current_status.get("current_step", ""))
            return
        request = {
            "ask_id": self.ask_id,
            "created_at": self.started_at,
            "runtime_protocol_version": RUNTIME_PROTOCOL_VERSION,
            **payload,
        }
        atomic_write_json(self.request_path, request)
        self.event("request_written")
        self.update("running", request=request)

    def step_started(self, name: str, **fields: Any) -> None:
        self.event(f"{name}_started", **fields)
        self.update("running", current_step=name, **fields)

    def step_finished(self, name: str, **fields: Any) -> None:
        self.event(f"{name}_finished", **fields)
        self.update("running", current_step=name, **fields)

    def event(self, event_type: str, **fields: Any) -> None:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ask_id": self.ask_id,
            "event": event_type,
            **fields,
        }
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")

    def add_artifacts(self, artifacts: dict[str, Any]) -> None:
        payload = self._read_current_status()
        merged = dict(payload.get("artifacts", self.artifacts))
        for key, value in artifacts.items():
            if value:
                merged[key] = str(value)
        payload["artifacts"] = merged
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(self.status_path, payload)
        self.event("artifacts_registered", artifacts={k: str(v) for k, v in artifacts.items() if v})

    def update(self, state: str, **fields: Any) -> None:
        self.state = state
        current = self._read_current_status()
        artifacts = dict(self.artifacts)
        artifacts.update(current.get("artifacts", {}))
        payload = {
            "ask_id": self.ask_id,
            "state": state,
            "started_at": self.started_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "runtime_protocol_version": RUNTIME_PROTOCOL_VERSION,
            "artifacts": artifacts,
            "controller_pid": os.getpid(),
            **fields,
        }
        if "needs_attention" in current and "needs_attention" not in payload:
            payload["needs_attention"] = current["needs_attention"]
        for key in ("request", "route_decision"):
            if key in current and key not in payload:
                payload[key] = current[key]
        atomic_write_json(self.status_path, payload)
        self._append_index(payload)
        self._write_artifact_manifest(payload)

    def needs_attention(
        self,
        *,
        reason: str,
        question: str,
        safe_default: str = "pause",
        resume_hint: str = "",
        **fields: Any,
    ) -> dict[str, Any]:
        payload = {
            "reason": reason,
            "question": question,
            "safe_default": safe_default,
            "resume_hint": resume_hint,
            **fields,
        }
        self.event("needs_attention", **payload)
        self.update("needs_attention", needs_attention=payload)
        return payload

    def finish(self, result: dict[str, Any], state: str | None = None) -> None:
        oracle = result.get("oracle") or {}
        has_oracle_answer = bool(oracle) and bool(str(result.get("answer", "")).strip()) and not oracle.get("error")
        image_generation = result.get("image_generation") or {}
        has_image_generation = bool(image_generation.get("files"))
        final_state = state or ("answered" if result.get("items") or has_oracle_answer or has_image_generation else "no_results")
        summary = {
            "question": result.get("question", ""),
            "scope": result.get("scope", ""),
            "items_count": len(result.get("items", [])),
            "auto_learned": bool(result.get("auto_learned")),
            "image_generation_enabled": has_image_generation,
            "image_generation_model": image_generation.get("model", ""),
            "image_generation_files_count": len(image_generation.get("files", [])),
            "oracle_enabled": bool(result.get("oracle")),
            "oracle_model": oracle.get("model", ""),
            "oracle_model_served": oracle.get("model_served", ""),
            "oracle_model_alias": oracle.get("model_alias"),
            "answer_chars": len(str(result.get("answer", ""))),
            "deep_review_enabled": bool(result.get("deep_review")),
            "session_path": result.get("session_path", ""),
        }
        self.event("finished", state=final_state, **summary)
        self.update(final_state, result_summary=summary)

    def fail(self, exc: BaseException) -> None:
        error = {"type": type(exc).__name__, "message": str(exc)}
        self.event("failed", error=error)
        self.update("failed", error=error)

    def _read_current_status(self) -> dict[str, Any]:
        if not self.status_path.exists():
            return {
                "ask_id": self.ask_id,
                "state": self.state,
                "started_at": self.started_at,
                "runtime_protocol_version": RUNTIME_PROTOCOL_VERSION,
                "artifacts": self.artifacts,
            }
        try:
            return json.loads(self.status_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {
                "ask_id": self.ask_id,
                "state": self.state,
                "started_at": self.started_at,
                "runtime_protocol_version": RUNTIME_PROTOCOL_VERSION,
                "artifacts": self.artifacts,
            }

    def _write_artifact_manifest(self, status_payload: dict[str, Any]) -> None:
        artifacts = dict(status_payload.get("artifacts") or self.artifacts)
        manifest = {
            "schema_version": "ask.artifact_manifest.v1",
            "ask_id": self.ask_id,
            "state": status_payload.get("state", self.state),
            "updated_at": status_payload.get("updated_at", datetime.now(timezone.utc).isoformat()),
            "request": artifacts.get("request", str(self.request_path)),
            "status": artifacts.get("status", str(self.status_path)),
            "events": artifacts.get("events", str(self.events_path)),
            "route_decision": status_payload.get("route_decision") or (status_payload.get("request") or {}).get("route_decision"),
            "needs_attention": status_payload.get("needs_attention"),
            "result_summary": status_payload.get("result_summary"),
            "artifacts": artifacts,
        }
        atomic_write_json(self.run_dir / "artifact_manifest.json", manifest)

    def _existing_status_state(self) -> str | None:
        payload = self._existing_status()
        state = payload.get("state")
        return str(state) if state else None

    def _existing_status(self) -> dict[str, Any]:
        if not self.status_path.exists():
            return {}
        try:
            payload = json.loads(self.status_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _read_existing_request(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.request_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _append_index(self, status_payload: dict[str, Any]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ask_id": self.ask_id,
            "state": status_payload.get("state", self.state),
            "command": status_payload.get("request", {}).get("command", "ask"),
            "question": status_payload.get("request", {}).get("question", ""),
            "started_at": status_payload.get("started_at", self.started_at),
            "updated_at": status_payload.get("updated_at", ""),
            "status_path": str(self.status_path),
            "_status_path": str(self.status_path),
            "run_dir": str(self.run_dir),
        }
        index_path = self.output_root / INDEX_FILENAME
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


class NoopRunState:
    """Drop-in run-state used when artifact persistence is unavailable."""

    disabled = True

    def __init__(self, ask_id: str, reason: str = "") -> None:
        self.ask_id = safe_run_id(ask_id)
        self.reason = reason
        self.state = "disabled"

    @property
    def artifacts(self) -> dict[str, str]:
        return {"runtime_artifacts": "disabled", "reason": self.reason}

    def write_request(self, payload: dict[str, Any]) -> None:
        return None

    def step_started(self, name: str, **fields: Any) -> None:
        return None

    def step_finished(self, name: str, **fields: Any) -> None:
        return None

    def event(self, event_type: str, **fields: Any) -> None:
        return None

    def add_artifacts(self, artifacts: dict[str, Any]) -> None:
        return None

    def update(self, state: str, **fields: Any) -> None:
        self.state = state

    def needs_attention(
        self,
        *,
        reason: str,
        question: str,
        safe_default: str = "pause",
        resume_hint: str = "",
        **fields: Any,
    ) -> dict[str, Any]:
        return {
            "reason": reason,
            "question": question,
            "safe_default": safe_default,
            "resume_hint": resume_hint,
            **fields,
        }

    def finish(self, result: dict[str, Any], state: str | None = None) -> None:
        oracle = result.get("oracle") or {}
        has_oracle_answer = bool(oracle) and bool(str(result.get("answer", "")).strip()) and not oracle.get("error")
        image_generation = result.get("image_generation") or {}
        has_image_generation = bool(image_generation.get("files"))
        self.state = state or ("answered" if result.get("items") or has_oracle_answer or has_image_generation else "no_results")

    def fail(self, exc: BaseException) -> None:
        self.state = "failed"


def resolve_run_target(target: str, output_root: Path | str | None = None) -> Path:
    path = Path(target).expanduser()
    if path.exists():
        if path.is_dir():
            matches = sorted(path.glob("*.status.json"))
            if matches:
                return matches[-1]
        return path

    root = Path(output_root).expanduser() if output_root else default_run_root()
    run_dir = root / safe_run_id(target)
    matches = sorted(run_dir.glob("*.status.json"))
    if matches:
        return matches[-1]
    return run_dir / f"{safe_run_id(target)}.status.json"


def read_status(target: str, tail_events: int = 0, output_root: Path | str | None = None) -> dict[str, Any]:
    status_path = resolve_run_target(target, output_root)
    if not status_path.exists():
        raise FileNotFoundError(f"Run status not found: {target}")
    payload = json.loads(status_path.read_text())
    payload = annotate_runtime_liveness(payload)
    if tail_events > 0:
        events_path = Path(payload.get("artifacts", {}).get("events", ""))
        payload["event_tail"] = read_event_tail(events_path, tail_events)
    return payload


def annotate_runtime_liveness(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a status payload with derived stale-state detection.

    The status file itself remains append-only/read-only for status commands.
    If a run says it is still running but the recorded controller process is
    gone, callers should see a terminal stale state rather than a misleading
    live running state.
    """
    if payload.get("state") != "running":
        return payload
    pid_alive = _pid_is_alive(payload.get("controller_pid"))
    if pid_alive is not False:
        return payload
    annotated = dict(payload)
    annotated["state"] = "stale"
    annotated["observed_state"] = "stale"
    annotated["recorded_state"] = "running"
    annotated["stale_reason"] = "controller_pid_not_alive"
    return annotated


def _pid_is_alive(pid: Any) -> bool | None:
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return None
    if pid_int <= 0:
        return None
    try:
        os.kill(pid_int, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def read_event_tail(events_path: Path, limit: int) -> list[dict[str, Any]]:
    if not events_path.exists():
        return []
    lines = events_path.read_text().splitlines()[-limit:]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"event": "unparseable_event", "raw": line})
    return events


def watch_status(
    target: str,
    interval: float = 1.0,
    tail_events: int = 5,
    timeout_seconds: float = 300,
    output_root: Path | str | None = None,
) -> None:
    payload = read_status(target, tail_events=tail_events, output_root=output_root)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    state = payload.get("state", "unknown")
    if state in TERMINAL_STATES:
        return
    events_path = Path(payload.get("artifacts", {}).get("events", ""))
    event_position = events_path.stat().st_size if events_path.exists() else 0
    last_state = state
    next_status_check = time.time() + interval
    deadline = time.time() + timeout_seconds
    while True:
        event_seen = False
        if events_path.exists():
            with events_path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(event_position)
                for line in handle:
                    event_position = handle.tell()
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    print(json.dumps({"event_stream": event}, indent=2, sort_keys=True, default=str))
                    event_seen = True
        now = time.time()
        if event_seen or now >= next_status_check:
            payload = read_status(target, tail_events=tail_events, output_root=output_root)
            state = payload.get("state", "unknown")
            if state != last_state:
                print(json.dumps(payload, indent=2, sort_keys=True, default=str))
                last_state = state
            next_status_check = now + interval
        if state in TERMINAL_STATES:
            return
        if now >= deadline:
            raise TimeoutError(f"Timed out watching /ask run '{target}' after {timeout_seconds:g}s")
        time.sleep(min(interval, 0.25))


def list_runs(
    output_root: Path | str | None = None,
    limit: int = 20,
    *,
    root: Path | str | None = None,
    last: int | None = None,
    mode: str | None = None,
) -> list[dict[str, Any]]:
    if root is not None or last is not None or mode is not None:
        return _list_mode_runs(root=root, limit=last or limit, mode=mode)
    run_root = Path(output_root).expanduser() if output_root else default_run_root()
    if not run_root.exists():
        return _list_mode_runs(root=None, limit=limit) if output_root is None else []
    indexed = _list_runs_from_index(run_root, limit=limit)
    if indexed:
        runs = indexed[:limit]
        if output_root is None:
            runs.extend(_list_mode_runs(root=None, limit=limit))
            runs.sort(key=lambda item: str(item.get("updated_at") or item.get("ts") or ""), reverse=True)
        return runs[:limit]
    statuses: list[dict[str, Any]] = []
    for status_path in run_root.glob("*/*.status.json"):
        try:
            payload = json.loads(status_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        payload["_status_path"] = str(status_path)
        statuses.append(payload)
    if output_root is None:
        statuses.extend(_list_mode_runs(root=None, limit=limit))
    statuses.sort(key=lambda item: str(item.get("updated_at") or item.get("started_at") or ""), reverse=True)
    return statuses[:limit]


def _list_mode_runs(root: Path | str | None = None, limit: int = 20, mode: str | None = None) -> list[dict[str, Any]]:
    base = artifact_root(root)
    if not base.exists():
        return []
    pattern = f"{safe_run_id(mode)}/*/status.json" if mode else "*/status.json"
    status_paths = list(base.glob(pattern)) if mode else list(base.glob("*/*/status.json"))
    runs: list[dict[str, Any]] = []
    for status_path in status_paths:
        loaded = _read_mode_run(status_path)
        if not loaded:
            continue
        status = loaded["status"]
        runs.append(
            {
                "run_id": loaded["run_id"],
                "mode": loaded["mode"],
                "state": status.get("state", ""),
                "updated_at": status.get("updated_at", ""),
                "run_dir": loaded["run_dir"],
                "status": status,
            }
        )
    runs.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return runs[:limit]


def _list_runs_from_index(root: Path, limit: int = 20) -> list[dict[str, Any]]:
    index_path = root / INDEX_FILENAME
    if not index_path.exists():
        return []
    latest: dict[str, dict[str, Any]] = {}
    for line in index_path.read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ask_id = str(entry.get("ask_id", ""))
        status_path = Path(str(entry.get("status_path", "")))
        if not ask_id or not status_path.exists():
            continue
        latest[ask_id] = entry
    runs = sorted(latest.values(), key=lambda item: str(item.get("updated_at") or item.get("ts") or ""), reverse=True)
    return runs[:limit]


def _validated_run_status(run_dir: Path) -> dict[str, Any] | None:
    if run_dir.is_symlink():
        return None
    status_path = run_dir / f"{run_dir.name}.status.json"
    if not status_path.is_file():
        return None
    try:
        payload = json.loads(status_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("runtime_protocol_version") != RUNTIME_PROTOCOL_VERSION:
        return None
    if payload.get("ask_id") != run_dir.name:
        return None
    artifact_run_dir = payload.get("artifacts", {}).get("run_dir")
    if not artifact_run_dir:
        return None
    try:
        if Path(artifact_run_dir).expanduser().resolve() != run_dir.resolve():
            return None
    except OSError:
        return None
    payload["_status_path"] = str(status_path)
    return payload


def _parse_status_timestamp(value: Any) -> float | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return None


def _run_age_basis(status: dict[str, Any], run_dir: Path) -> float | None:
    parsed = _parse_status_timestamp(status.get("updated_at"))
    if parsed is not None:
        return parsed
    try:
        return (run_dir / f"{run_dir.name}.status.json").stat().st_mtime
    except OSError:
        return None


def prune_runs(output_root: Path | str | None = None, older_than_days: int = 14, dry_run: bool = False) -> dict[str, Any]:
    root = Path(output_root).expanduser() if output_root else default_run_root()
    root = root.resolve()
    cutoff = time.time() - older_than_days * 24 * 60 * 60
    removed: list[str] = []
    kept: list[str] = []
    if not root.exists():
        return {"run_root": str(root), "older_than_days": older_than_days, "dry_run": dry_run, "removed": [], "kept": []}
    for run_dir in sorted(path for path in root.iterdir() if path.is_dir() or path.is_symlink()):
        try:
            resolved_parent = run_dir.resolve().parent
        except OSError:
            kept.append(str(run_dir))
            continue
        if resolved_parent != root:
            kept.append(str(run_dir))
            continue
        status = _validated_run_status(run_dir)
        if status is None:
            kept.append(str(run_dir))
            continue
        if status.get("state") not in TERMINAL_STATES:
            kept.append(str(run_dir))
            continue
        age_basis = _run_age_basis(status, run_dir)
        if age_basis is None:
            kept.append(str(run_dir))
            continue
        if age_basis >= cutoff:
            kept.append(str(run_dir))
            continue
        removed.append(str(run_dir))
        if not dry_run:
            shutil.rmtree(run_dir)
    return {
        "run_root": str(root),
        "older_than_days": older_than_days,
        "dry_run": dry_run,
        "removed": removed,
        "kept": kept,
    }
