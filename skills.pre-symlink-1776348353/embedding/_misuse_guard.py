"""Misuse guard for the embedding skill.

Copy of misuse_guard_template.py with embedding-specific validators.
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
# Embedding-specific validators
# ============================================================================

def require_text_field(body: dict) -> dict:
    """Validator: 'text' field is required and non-empty."""
    text = body.get("text")
    if not text:
        raise ValidationError(
            "'text' is required and cannot be empty. "
            "Example: {\"text\": \"your query here\"}",
            error_type="missing_required",
            sent_value=str(text) if text is not None else "(missing)",
        )
    return body


def require_texts_field(body: dict) -> dict:
    """Validator: 'texts' field is required for batch endpoint."""
    texts = body.get("texts")
    if not texts:
        raise ValidationError(
            "'texts' is required and cannot be empty. "
            "Example: {\"texts\": [\"query 1\", \"query 2\"]}",
            error_type="missing_required",
            sent_value=str(texts) if texts is not None else "(missing)",
        )
    if not isinstance(texts, list):
        raise ValidationError(
            "'texts' must be a list of strings. "
            f"Got {type(texts).__name__}. "
            "Example: {\"texts\": [\"query 1\", \"query 2\"]}",
            error_type="wrong_type",
            sent_value=str(type(texts).__name__),
            correct_value="list",
        )
    return body


def reject_wrong_port_hint(body: dict) -> dict:
    """Validator: detect if caller sent multimodal request to text endpoint."""
    # If body has image_url or modality hints, they're on the wrong port
    if "image_url" in body or "image" in body or body.get("multimodal"):
        raise ValidationError(
            "Image/multimodal requests must go to port 8603, not 8602. "
            "Port 8602 = text (384d, MiniLM). Port 8603 = multimodal (2048d, Qwen3-VL). "
            "Example: curl http://127.0.0.1:8603/v1/embeddings -d '{\"input\": [...]}'",
            error_type="wrong_port",
            sent_value="port 8602 with multimodal payload",
            correct_value="port 8603",
        )
    return body


def warn_empty_vector_assignment(body: dict) -> dict:
    """Validator: reject null/empty vectors (common ArangoDB mistake)."""
    embedding = body.get("embedding")
    if embedding is not None and (embedding == [] or embedding is None):
        raise ValidationError(
            "Never set 'embedding' to null or []. Omit the field entirely. "
            "Explicit null blocks ArangoDB vector index operations. "
            "See SKILL.md: 'Never set embedding fields to null'",
            error_type="null_embedding",
            sent_value="[] or null",
            correct_value="(omit field)",
        )
    return body


# ============================================================================
# Pre-configured guard instance
# ============================================================================

def create_embedding_guard() -> MisuseGuard:
    """Create a MisuseGuard configured for the embedding skill."""
    guard = MisuseGuard(skill_name="embedding")
    guard.add_validator("wrong_port_hint", reject_wrong_port_hint)
    guard.add_validator("null_vector", warn_empty_vector_assignment)
    return guard


def create_embed_guard() -> MisuseGuard:
    """Guard for /embed endpoint."""
    guard = create_embedding_guard()
    guard.add_validator("require_text", require_text_field)
    return guard


def create_batch_guard() -> MisuseGuard:
    """Guard for /embed/batch endpoint."""
    guard = create_embedding_guard()
    guard.add_validator("require_texts", require_texts_field)
    return guard
