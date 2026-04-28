"""Runtime protocol schema helpers for /ask artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RUNTIME_PROTOCOL_VERSION = "ask.runtime.v1"
REQUEST_REQUIRED = {"ask_id", "created_at", "runtime_protocol_version"}
STATUS_REQUIRED = {"ask_id", "state", "started_at", "updated_at", "runtime_protocol_version", "artifacts"}
EVENT_REQUIRED = {"ts", "ask_id", "event"}


def runtime_schema_summary() -> dict[str, Any]:
    return {
        "runtime_protocol_version": RUNTIME_PROTOCOL_VERSION,
        "request": {"required": sorted(REQUEST_REQUIRED)},
        "status": {"required": sorted(STATUS_REQUIRED)},
        "event": {"required": sorted(EVENT_REQUIRED)},
    }


def validate_request(payload: dict[str, Any]) -> list[str]:
    errors = _missing_errors("request", payload, REQUEST_REQUIRED)
    if payload.get("runtime_protocol_version") != RUNTIME_PROTOCOL_VERSION:
        errors.append("request.runtime_protocol_version must be ask.runtime.v1")
    return errors


def validate_status(payload: dict[str, Any]) -> list[str]:
    errors = _missing_errors("status", payload, STATUS_REQUIRED)
    if payload.get("runtime_protocol_version") != RUNTIME_PROTOCOL_VERSION:
        errors.append("status.runtime_protocol_version must be ask.runtime.v1")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("status.artifacts must be an object")
    else:
        for key in ("request", "status", "events", "run_dir"):
            if not artifacts.get(key):
                errors.append(f"status.artifacts.{key} is required")
    needs_attention = payload.get("needs_attention")
    if payload.get("state") == "needs_attention" and not isinstance(needs_attention, dict):
        errors.append("status.needs_attention must be present for needs_attention state")
    if isinstance(needs_attention, dict):
        for key in ("reason", "question", "safe_default", "resume_hint"):
            if key not in needs_attention:
                errors.append(f"status.needs_attention.{key} is required")
    return errors


def validate_event(payload: dict[str, Any], line_no: int | None = None) -> list[str]:
    prefix = f"event[{line_no}]" if line_no is not None else "event"
    errors = _missing_errors(prefix, payload, EVENT_REQUIRED)
    if not isinstance(payload.get("event", ""), str):
        errors.append(f"{prefix}.event must be a string")
    return errors


def validate_run_dir(run_dir: Path) -> dict[str, Any]:
    ask_id = run_dir.name
    request_path = run_dir / f"{ask_id}.request.json"
    status_path = run_dir / f"{ask_id}.status.json"
    events_path = run_dir / f"{ask_id}.events.jsonl"
    errors: list[str] = []

    request_payload = _read_json_file(request_path, errors, "request")
    status_payload = _read_json_file(status_path, errors, "status")
    if request_payload is not None:
        errors.extend(validate_request(request_payload))
        if request_payload.get("ask_id") != ask_id:
            errors.append("request.ask_id must match run directory name")
    if status_payload is not None:
        errors.extend(validate_status(status_payload))
        if status_payload.get("ask_id") != ask_id:
            errors.append("status.ask_id must match run directory name")

    if not events_path.exists():
        errors.append("events file is missing")
    else:
        for line_no, line in enumerate(events_path.read_text().splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"event[{line_no}] is not valid JSON")
                continue
            errors.extend(validate_event(event, line_no=line_no))
            if event.get("ask_id") != ask_id:
                errors.append(f"event[{line_no}].ask_id must match run directory name")

    return {"run_dir": str(run_dir), "ok": not errors, "errors": errors}


def validate_runtime_tree(root: Path) -> dict[str, Any]:
    results = []
    if root.exists():
        for run_dir in sorted(path for path in root.iterdir() if path.is_dir() and not path.is_symlink()):
            if (run_dir / f"{run_dir.name}.status.json").exists():
                results.append(validate_run_dir(run_dir))
    invalid = [result for result in results if not result["ok"]]
    return {
        "root": str(root),
        "schema": runtime_schema_summary(),
        "runs_checked": len(results),
        "invalid_runs": invalid,
        "ok": not invalid,
    }


def _missing_errors(prefix: str, payload: dict[str, Any], required: set[str]) -> list[str]:
    return [f"{prefix}.{key} is required" for key in sorted(required) if key not in payload]


def _read_json_file(path: Path, errors: list[str], label: str) -> dict[str, Any] | None:
    if not path.exists():
        errors.append(f"{label} file is missing")
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"{label} file is invalid JSON: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label} file must contain a JSON object")
        return None
    return payload
