"""API error classification for smart recovery.

Slimmed-down version of hermes-agent's error_classifier.py (810 lines → ~150).
Focuses on what code-runner needs:
- Classify errors → recovery action (retry/compress/abort)
- Detect context overflow → trigger compression
- Distinguish billing vs rate limit → avoid futile retries

Skips credential rotation and provider fallback (handled by /scillm proxy).
"""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Any, Optional


class FailoverReason(enum.Enum):
    """Why an API call failed — determines recovery strategy."""

    # Transient — retry with backoff
    rate_limit = "rate_limit"          # 429 or quota throttling
    server_error = "server_error"      # 500/502
    overloaded = "overloaded"          # 503/529
    timeout = "timeout"                # Connection/read timeout

    # Context — compress and retry
    context_overflow = "context_overflow"    # Context too large
    payload_too_large = "payload_too_large"  # 413

    # Fatal — abort (no point retrying)
    billing = "billing"                # 402 or credit exhaustion
    auth = "auth"                      # 401/403
    model_not_found = "model_not_found"  # 404 or invalid model
    format_error = "format_error"      # 400 bad request

    # Catch-all
    unknown = "unknown"


@dataclass
class ClassifiedError:
    """Structured classification with recovery hints."""

    reason: FailoverReason
    status_code: Optional[int] = None
    message: str = ""

    # Recovery action hints
    retryable: bool = True
    should_compress: bool = False

    @property
    def is_transient(self) -> bool:
        """True if error is likely transient and worth retrying."""
        return self.reason in (
            FailoverReason.rate_limit,
            FailoverReason.server_error,
            FailoverReason.overloaded,
            FailoverReason.timeout,
        )

    @property
    def is_context_related(self) -> bool:
        """True if error is due to context/payload size."""
        return self.reason in (
            FailoverReason.context_overflow,
            FailoverReason.payload_too_large,
        )


# ── Pattern sets for message-based classification ──────────────────────

_BILLING_PATTERNS = [
    "insufficient credits",
    "insufficient_quota",
    "credit balance",
    "credits have been exhausted",
    "payment required",
    "billing hard limit",
    "exceeded your current quota",
    "account is deactivated",
]

_RATE_LIMIT_PATTERNS = [
    "rate limit",
    "rate_limit",
    "too many requests",
    "throttled",
    "requests per minute",
    "tokens per minute",
    "try again in",
    "please retry after",
    "resource_exhausted",
]

_CONTEXT_OVERFLOW_PATTERNS = [
    "context length",
    "context size",
    "maximum context",
    "token limit",
    "too many tokens",
    "reduce the length",
    "exceeds the limit",
    "context window",
    "prompt is too long",
    "max_tokens",
    "maximum number of tokens",
]

_MODEL_NOT_FOUND_PATTERNS = [
    "is not a valid model",
    "invalid model",
    "model not found",
    "model_not_found",
    "does not exist",
    "no such model",
    "unknown model",
]

_TRANSPORT_ERROR_TYPES = frozenset({
    "ReadTimeout", "ConnectTimeout", "PoolTimeout",
    "ConnectError", "RemoteProtocolError",
    "ConnectionError", "ConnectionResetError",
    "TimeoutError", "ReadError",
    "APIConnectionError", "APITimeoutError",
})


def classify_api_error(
    error: Exception,
    *,
    approx_tokens: int = 0,
    context_length: int = 128000,
) -> ClassifiedError:
    """Classify an API error into a recovery recommendation.

    Args:
        error: The exception from the API call.
        approx_tokens: Approximate token count of current context.
        context_length: Maximum context length for current model.

    Returns:
        ClassifiedError with reason and recovery hints.
    """
    status_code = _extract_status_code(error)
    error_type = type(error).__name__
    error_msg = str(error).lower()

    def _result(reason: FailoverReason, **overrides) -> ClassifiedError:
        defaults = {
            "reason": reason,
            "status_code": status_code,
            "message": str(error)[:500],
            "retryable": reason in (
                FailoverReason.rate_limit,
                FailoverReason.server_error,
                FailoverReason.overloaded,
                FailoverReason.timeout,
                FailoverReason.context_overflow,
                FailoverReason.payload_too_large,
            ),
            "should_compress": reason in (
                FailoverReason.context_overflow,
                FailoverReason.payload_too_large,
            ),
        }
        defaults.update(overrides)
        return ClassifiedError(**defaults)

    # ── Status code classification ──────────────────────────────────

    if status_code == 401 or status_code == 403:
        return _result(FailoverReason.auth, retryable=False)

    if status_code == 402:
        # Disambiguate: billing exhaustion vs transient usage limit
        has_transient = any(p in error_msg for p in ["try again", "retry", "resets"])
        if has_transient:
            return _result(FailoverReason.rate_limit)
        return _result(FailoverReason.billing, retryable=False)

    if status_code == 404:
        return _result(FailoverReason.model_not_found, retryable=False)

    if status_code == 413:
        return _result(FailoverReason.payload_too_large)

    if status_code == 429:
        return _result(FailoverReason.rate_limit)

    if status_code == 400:
        # Check for context overflow in 400
        if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
            return _result(FailoverReason.context_overflow)
        if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
            return _result(FailoverReason.model_not_found, retryable=False)
        # Generic 400 + large context → probable overflow
        if approx_tokens > context_length * 0.6:
            return _result(FailoverReason.context_overflow)
        return _result(FailoverReason.format_error, retryable=False)

    if status_code in (500, 502):
        return _result(FailoverReason.server_error)

    if status_code in (503, 529):
        return _result(FailoverReason.overloaded)

    # ── Message pattern classification (no status code) ─────────────

    if any(p in error_msg for p in _BILLING_PATTERNS):
        return _result(FailoverReason.billing, retryable=False)

    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return _result(FailoverReason.rate_limit)

    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return _result(FailoverReason.context_overflow)

    # ── Transport errors ────────────────────────────────────────────

    if error_type in _TRANSPORT_ERROR_TYPES or isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return _result(FailoverReason.timeout)

    # ── Fallback ────────────────────────────────────────────────────

    return _result(FailoverReason.unknown)


def _extract_status_code(error: Exception) -> Optional[int]:
    """Extract HTTP status code from exception."""
    for attr in ("status_code", "status"):
        code = getattr(error, attr, None)
        if isinstance(code, int) and 100 <= code < 600:
            return code
    # Check cause chain
    cause = getattr(error, "__cause__", None) or getattr(error, "__context__", None)
    if cause and cause is not error:
        return _extract_status_code(cause)
    return None


def classify_response_error(
    status_code: int,
    body: dict[str, Any] | None = None,
    approx_tokens: int = 0,
) -> ClassifiedError:
    """Classify from HTTP response (when not an exception).

    Use this when you have status_code + body but not an exception object.
    """
    # Build a fake error message from body
    msg = ""
    if body:
        err = body.get("error", {})
        if isinstance(err, dict):
            msg = err.get("message", "")
        elif isinstance(err, str):
            msg = err
        if not msg:
            msg = body.get("message", "")

    class _FakeError(Exception):
        def __init__(self, message: str, code: int):
            super().__init__(message)
            self.status_code = code

    return classify_api_error(
        _FakeError(msg, status_code),
        approx_tokens=approx_tokens,
    )
