"""Misuse guard for the chutes-call skill.

Copy of misuse_guard_template.py with chutes-call-specific validators.
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
# Chutes-call-specific validators
# ============================================================================

def require_messages(body: dict) -> dict:
    """Validator: 'messages' field is required and must be non-empty list."""
    messages = body.get("messages")
    if not messages:
        raise ValidationError(
            "'messages' is required. Must be a list with at least one message. "
            "Example: {\"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}",
            error_type="missing_required",
            sent_value=str(messages) if messages is not None else "(missing)",
        )
    if not isinstance(messages, list):
        raise ValidationError(
            "'messages' must be a list. "
            f"Got {type(messages).__name__}. "
            "Example: {\"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}",
            error_type="wrong_type",
            sent_value=str(type(messages).__name__),
            correct_value="list",
        )
    return body


def validate_message_structure(body: dict) -> dict:
    """Validator: each message must have 'role' and 'content'."""
    messages = body.get("messages", [])
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise ValidationError(
                f"Message {i} must be a dict with 'role' and 'content'. "
                f"Got {type(msg).__name__}. "
                "Example: {\"role\": \"user\", \"content\": \"Hello\"}",
                error_type="wrong_message_type",
                sent_value=str(type(msg).__name__),
            )
        if "role" not in msg:
            raise ValidationError(
                f"Message {i} missing 'role'. "
                "Required fields: role, content. "
                "Valid roles: system, user, assistant",
                error_type="missing_role",
                sent_value=str(msg)[:100],
            )
        if "content" not in msg:
            raise ValidationError(
                f"Message {i} missing 'content'. "
                "Required fields: role, content. "
                "Example: {\"role\": \"user\", \"content\": \"Hello\"}",
                error_type="missing_content",
                sent_value=str(msg)[:100],
            )
    return body


# Known model corrections (typos → correct)
MODEL_CORRECTIONS = {
    "deepseek-v3": "deepseek-ai/DeepSeek-V3",
    "deepseek": "deepseek-ai/DeepSeek-V3",
    "deepseak-v3": "deepseek-ai/DeepSeek-V3",
    "deepsek-v3": "deepseek-ai/DeepSeek-V3",
    "qwen-32b": "Qwen/Qwen3-32B",
    "qwen3-32b": "Qwen/Qwen3-32B",
    "qwen": "Qwen/Qwen3-32B",
}


def correct_model_typos(body: dict) -> dict:
    """Validator: catch common model name typos and suggest correction."""
    model = body.get("model", "").lower()
    if model in MODEL_CORRECTIONS:
        correct = MODEL_CORRECTIONS[model]
        raise ValidationError(
            f"Model '{body.get('model')}' is incorrect. Use '{correct}'. "
            f"Example: {{\"model\": \"{correct}\", \"messages\": [...]}}",
            error_type="wrong_model",
            sent_value=body.get("model", ""),
            correct_value=correct,
        )
    return body


def reject_scillm_params(body: dict) -> dict:
    """Validator: reject scillm-specific params that don't work here."""
    scillm_only = ["skill", "directive", "system_directive", "system"]
    found = [k for k in scillm_only if k in body]
    if found:
        raise ValidationError(
            f"Parameters {found} are scillm-specific and not supported by chutes-call. "
            f"Use 'messages' array with a system message instead. "
            f"Example: {{\"messages\": [{{\"role\": \"system\", \"content\": \"...\"}}, ...]}}",
            error_type="wrong_api",
            sent_value=str(found),
            correct_value="messages array with system role",
        )
    return body


def warn_excessive_batch_size(body: dict) -> dict:
    """Validator: warn if batch size exceeds recommended limit."""
    requests = body.get("requests", [])
    if len(requests) > 100:
        logger.warning(
            f"Large batch ({len(requests)} requests). Consider chunking into batches of 50. "
            f"Large batches increase queue depth and latency for all callers."
        )
    return body


def validate_concurrency(body: dict) -> dict:
    """Validator: ensure concurrency doesn't exceed semaphore."""
    concurrency = body.get("concurrency", 5)
    if concurrency > 5:
        raise ValidationError(
            f"Concurrency {concurrency} exceeds Chutes account limit of 5. "
            f"Set concurrency <= 5 or omit (defaults to 5). "
            f"Example: {{\"requests\": [...], \"concurrency\": 5}}",
            error_type="excessive_concurrency",
            sent_value=str(concurrency),
            correct_value="5",
        )
    return body


# ============================================================================
# Pre-configured guard instances
# ============================================================================

def create_chat_guard() -> MisuseGuard:
    """Guard for POST /chat endpoint."""
    guard = MisuseGuard(skill_name="chutes-call")
    guard.add_validator("require_messages", require_messages)
    guard.add_validator("validate_structure", validate_message_structure)
    guard.add_validator("correct_model", correct_model_typos)
    guard.add_validator("reject_scillm_params", reject_scillm_params)
    return guard


def create_batch_guard() -> MisuseGuard:
    """Guard for POST /batch endpoint."""
    guard = MisuseGuard(skill_name="chutes-call")
    guard.add_validator("warn_batch_size", warn_excessive_batch_size)
    guard.add_validator("validate_concurrency", validate_concurrency)
    return guard
