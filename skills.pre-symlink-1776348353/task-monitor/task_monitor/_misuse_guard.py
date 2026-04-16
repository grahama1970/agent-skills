"""Misuse guard for the task-monitor skill.

Copy of misuse_guard_template.py with task-monitor-specific validators.
Catches common agent mistakes and logs to /memory for nightly analysis.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from loguru import logger


# ============================================================================
# Misuse Event Logging (to /memory for nightly analysis)
# ============================================================================

def log_misuse_event(
    skill: str,
    endpoint: str,
    error_type: str,
    sent_value: str,
    correct_value: str | None = None,
    caller: str | None = None,
) -> None:
    """Log misuse to /memory for nightly /monitor-misuse analysis."""
    try:
        import httpx

        key_source = f"{skill}:{endpoint}:{error_type}:{sent_value}"
        doc_key = hashlib.sha256(key_source.encode()).hexdigest()[:16]

        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=2.0) as client:
            resp = client.post("/store", json={
                "document": {
                    "_key": doc_key,
                    "skill": skill,
                    "endpoint": endpoint,
                    "error_type": error_type,
                    "sent_value": sent_value,
                    "correct_value": correct_value,
                    "was_known": correct_value is not None,
                    "caller": caller,
                    "ts": int(time.time()),
                    "count": 1,
                },
                "collection": "misuse_events",
            })
            if resp.status_code != 200:
                logger.warning(f"Failed to log misuse event: {resp.status_code}")
    except Exception as exc:
        logger.warning(f"Misuse event logging failed (non-fatal): {exc}")


class ValidationError(Exception):
    """Raised when validation fails. Includes helpful fix instructions."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_type: str = "unknown",
        sent_value: str = "",
        correct_value: str | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        self.sent_value = sent_value
        self.correct_value = correct_value
        super().__init__(message)


@dataclass
class MisuseGuard:
    """Defensive validation with helpful error messages."""

    skill_name: str
    max_errors_before_block: int = 5
    block_duration_s: int = 60
    validators: list[tuple[str, Callable]] = field(default_factory=list)

    _client_errors: dict = field(default_factory=lambda: defaultdict(list))
    _blocked_clients: dict = field(default_factory=dict)

    def add_validator(self, name: str, fn: Callable[[dict], dict | None]):
        self.validators.append((name, fn))

    def validate(
        self,
        body: dict,
        client_id: str = "default",
        endpoint: str = "/unknown",
        caller: str | None = None,
    ) -> dict:
        self._check_blocked(client_id)

        try:
            for name, fn in self.validators:
                result = fn(body)
                if result is not None:
                    body = result
            self._client_errors.pop(client_id, None)
            return body

        except ValidationError as exc:
            self._record_error(client_id)
            log_misuse_event(
                skill=self.skill_name,
                endpoint=endpoint,
                error_type=exc.error_type,
                sent_value=exc.sent_value,
                correct_value=exc.correct_value,
                caller=caller,
            )
            raise

    def _check_blocked(self, client_id: str) -> None:
        if client_id in self._blocked_clients:
            unblock_time = self._blocked_clients[client_id]
            now = time.monotonic()
            if now < unblock_time:
                remaining = int(unblock_time - now)
                raise ValidationError(
                    f"Too many invalid requests. Blocked for {remaining}s. "
                    f"Fix your request format and try again.",
                    status_code=429,
                )
            else:
                del self._blocked_clients[client_id]
                self._client_errors.pop(client_id, None)

    def _record_error(self, client_id: str) -> None:
        now = time.monotonic()
        errors = self._client_errors[client_id]
        errors.append(now)
        self._client_errors[client_id] = [t for t in errors if now - t < 60]
        if len(self._client_errors[client_id]) >= self.max_errors_before_block:
            self._blocked_clients[client_id] = now + self.block_duration_s


# ============================================================================
# Task-monitor-specific validators
# ============================================================================

def require_task_name(body: dict) -> dict:
    """Validator: 'name' field is required for task registration."""
    name = body.get("name")
    if not name:
        raise ValidationError(
            "'name' is required for task registration. "
            "Example: {\"name\": \"youtube-extraction\", \"total\": 1946}",
            error_type="missing_required",
            sent_value=str(name) if name is not None else "(missing)",
        )
    return body


def require_state_file(body: dict) -> dict:
    """Validator: 'state_file' is required for task registration."""
    state_file = body.get("state_file")
    if not state_file:
        raise ValidationError(
            "'state_file' is required. This is the path to the .batch_state.json file. "
            "Example: {\"name\": \"task\", \"state_file\": \"/path/to/.batch_state.json\"}",
            error_type="missing_required",
            sent_value=str(state_file) if state_file is not None else "(missing)",
        )
    return body


def warn_missing_total(body: dict) -> dict:
    """Validator: warn if 'total' is missing (progress tracking won't work)."""
    total = body.get("total")
    if total is None:
        # Log as warning but don't reject - some tasks don't know total upfront
        logger.warning(
            "Task registered without 'total' - progress percentage unavailable. "
            "Set 'total' for progress bars and ETA calculation."
        )
    return body


def reject_unregistered_push(body: dict, registered_tasks: set) -> Callable:
    """Factory: create validator that rejects pushes to unregistered tasks."""
    def validator(body: dict) -> dict:
        task_name = body.get("name")
        if task_name and task_name not in registered_tasks:
            raise ValidationError(
                f"Task '{task_name}' is not registered. Register first via POST /tasks. "
                f"Example: curl -X POST http://localhost:8765/tasks -d '{{\"name\": \"{task_name}\", ...}}'",
                error_type="unregistered_task",
                sent_value=task_name,
            )
        return body
    return validator


def validate_quality_metrics(body: dict) -> dict:
    """Validator: ensure quality metrics have expected fields."""
    metrics = body.get("metrics", {})
    known_fields = {"schema_valid_rate", "grounding_rate", "taxonomy_rate", "error_rate"}

    # Auto-fix: if top-level fields look like metrics, nest them
    if any(k in body for k in known_fields):
        body["metrics"] = {k: body.pop(k) for k in known_fields if k in body}
        logger.info("Auto-fixed: moved top-level metric fields into 'metrics' object")

    return body


def reject_daemon_not_running_hint(body: dict) -> dict:
    """Validator: detect if caller is trying to use API without daemon running."""
    # This is checked server-side by the HTTP 500 handler, but we can add
    # helpful context if we detect common patterns
    return body


# ============================================================================
# Pre-configured guard instances
# ============================================================================

def create_register_guard() -> MisuseGuard:
    """Guard for POST /tasks (register) endpoint."""
    guard = MisuseGuard(skill_name="task-monitor")
    guard.add_validator("require_name", require_task_name)
    guard.add_validator("require_state_file", require_state_file)
    guard.add_validator("warn_missing_total", warn_missing_total)
    return guard


def create_state_update_guard() -> MisuseGuard:
    """Guard for POST /tasks/{name}/state endpoint."""
    guard = MisuseGuard(skill_name="task-monitor")
    return guard


def create_quality_guard() -> MisuseGuard:
    """Guard for POST /tasks/{name}/quality endpoint."""
    guard = MisuseGuard(skill_name="task-monitor")
    guard.add_validator("validate_quality_metrics", validate_quality_metrics)
    return guard
