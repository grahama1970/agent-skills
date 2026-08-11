"""Centralized error codes for the CAPTCHA security-evaluation skill.

Inputs are typed manifests and local filesystem paths. Outputs are structured
failure records suitable for CLI JSON and durable run receipts. Failures are
fail-closed; callers never receive a successful status after a policy or seam
validation error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Closed vocabulary for failures exposed at skill boundaries."""

    INVALID_MANIFEST = "invalid_manifest"
    AUTHORIZATION_EXPIRED = "authorization_expired"
    ACTION_NOT_AUTHORIZED = "action_not_authorized"
    TARGET_NOT_LOOPBACK = "target_not_loopback"
    MODEL_ENDPOINT_NOT_LOOPBACK = "model_endpoint_not_loopback"
    THIRD_PARTY_PROVIDER_DENIED = "third_party_provider_denied"
    UNSAFE_BENCHMARK_MODE = "unsafe_benchmark_mode"
    RECAP_CHECKOUT_MISSING = "recap_checkout_missing"
    RECAP_REPOSITORY_MISMATCH = "recap_repository_mismatch"
    RECAP_COMMIT_MISMATCH = "recap_commit_mismatch"
    RECAP_SOURCE_DIRTY = "recap_source_dirty"
    RECAP_RUNTIME_MISSING = "recap_runtime_missing"
    RECAP_RUNTIME_INVALID = "recap_runtime_invalid"
    SURF_UNAVAILABLE = "surf_unavailable"
    SURF_CONTRACT_INVALID = "surf_contract_invalid"
    TARGET_UNAVAILABLE = "target_unavailable"
    MODEL_ENDPOINT_UNAVAILABLE = "model_endpoint_unavailable"
    MODEL_CREDENTIAL_MISSING = "model_credential_missing"
    MODEL_ID_MISMATCH = "model_id_mismatch"
    EXECUTION_NOT_CONFIRMED = "execution_not_confirmed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_TIMEOUT = "execution_timeout"
    RESULT_MISSING = "result_missing"
    RESULT_INVALID = "result_invalid"
    RECEIPT_INVALID = "receipt_invalid"
    ASK_INTEGRATION_MISSING = "ask_integration_missing"
    IO_ERROR = "io_error"


@dataclass(slots=True)
class CaptchaSkillError(Exception):
    """Typed, non-ignorable skill failure."""

    code: ErrorCode
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    exit_code: int = 2

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"

    def as_dict(self) -> dict[str, Any]:
        """Serialize the failure without leaking environment values."""

        return {
            "ok": False,
            "status": "BLOCKED",
            "failure_code": self.code.value,
            "message": self.message,
            "details": self.details,
        }
