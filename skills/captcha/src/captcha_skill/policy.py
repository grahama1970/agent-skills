"""Fail-closed authorization and hashing helpers for local ReCAP evaluation.

The policy intentionally cannot be widened to public hosts at runtime. Both the
synthetic CAPTCHA target and model endpoint must use literal loopback IPs.
All DNS hostnames, including ``localhost``, are rejected to avoid rebinding and
host-file ambiguity.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from .constants import POLICY_VERSION, RECAP_COMMIT
from .errors import CaptchaSkillError, ErrorCode
from .models import (
    AuthorizationManifest,
    AuthorizationReceipt,
    EvaluationAction,
    SeamValidation,
    TestMode,
)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value deterministically for receipts."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash an evidence file without loading it entirely into memory."""

    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CaptchaSkillError(
            ErrorCode.IO_ERROR,
            f"could not hash evidence file: {path}",
            {"path": str(path), "error": str(exc)},
        ) from exc
    return digest.hexdigest()


def write_json_atomic(path: Path, value: Any) -> None:
    """Write JSON atomically so partial receipts cannot be mistaken for proof."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        temp_path.replace(path)
    except OSError as exc:
        raise CaptchaSkillError(
            ErrorCode.IO_ERROR,
            f"could not write JSON artifact: {path}",
            {"path": str(path), "error": str(exc)},
        ) from exc


def load_json_object(path: Path) -> dict[str, Any]:
    """Read a JSON object and reject arrays/scalars at the boundary."""

    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptchaSkillError(
            ErrorCode.INVALID_MANIFEST,
            f"could not parse JSON object: {path}",
            {"path": str(path), "error": str(exc)},
        ) from exc
    if not isinstance(value, dict):
        raise CaptchaSkillError(
            ErrorCode.INVALID_MANIFEST,
            "authorization input must be a JSON object",
            {"path": str(path), "actual_type": type(value).__name__},
        )
    return value


def load_manifest(path: Path) -> tuple[AuthorizationManifest, str]:
    """Parse and hash an authorization manifest."""

    value = load_json_object(path)
    try:
        manifest = AuthorizationManifest.model_validate(value)
    except ValidationError as exc:
        raise CaptchaSkillError(
            ErrorCode.INVALID_MANIFEST,
            "authorization manifest failed schema validation",
            {"path": str(path), "errors": exc.errors(include_url=False)},
        ) from exc
    normalized = manifest.model_dump(mode="json")
    return manifest, sha256_bytes(canonical_json_bytes(normalized))


def _validate_loopback_url(
    value: str,
    *,
    error_code: ErrorCode,
    label: str,
    require_root_path: bool,
) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise CaptchaSkillError(
            error_code,
            f"{label} must use http or https",
            {"scheme": parsed.scheme},
        )
    if parsed.username is not None or parsed.password is not None:
        raise CaptchaSkillError(
            error_code,
            f"{label} must not contain embedded credentials",
        )
    if parsed.query or parsed.fragment:
        raise CaptchaSkillError(
            error_code,
            f"{label} must not contain a query or fragment",
        )
    if require_root_path and parsed.path not in {"", "/"}:
        raise CaptchaSkillError(
            error_code,
            f"{label} must be a server root URL",
            {"path": parsed.path},
        )
    hostname = parsed.hostname
    if hostname is None:
        raise CaptchaSkillError(error_code, f"{label} is missing a hostname")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as exc:
        raise CaptchaSkillError(
            error_code,
            f"{label} must use a literal loopback IP",
            {"hostname": hostname},
        ) from exc
    if not address.is_loopback:
        raise CaptchaSkillError(
            error_code,
            f"{label} must resolve by construction to loopback",
            {"hostname": hostname},
        )


def validate_authorization(
    manifest: AuthorizationManifest,
    *,
    manifest_sha256: str,
    required_action: EvaluationAction,
    now: datetime | None = None,
) -> AuthorizationReceipt:
    """Apply non-negotiable policy and issue a typed PASS receipt."""

    current = now or utc_now()
    if manifest.expires_at.tzinfo is None or manifest.expires_at.utcoffset() is None:
        raise CaptchaSkillError(
            ErrorCode.INVALID_MANIFEST,
            "expires_at must include a timezone",
        )
    if manifest.expires_at <= current:
        raise CaptchaSkillError(
            ErrorCode.AUTHORIZATION_EXPIRED,
            "authorization has expired",
            {
                "expires_at": manifest.expires_at.isoformat(),
                "validated_at": current.isoformat(),
            },
        )
    if required_action not in manifest.allowed_actions:
        raise CaptchaSkillError(
            ErrorCode.ACTION_NOT_AUTHORIZED,
            f"manifest does not authorize action '{required_action.value}'",
            {
                "allowed_actions": sorted(item.value for item in manifest.allowed_actions),
            },
        )
    acknowledgements = manifest.acknowledgements.model_dump()
    missing = sorted(key for key, accepted in acknowledgements.items() if not accepted)
    if missing:
        raise CaptchaSkillError(
            ErrorCode.INVALID_MANIFEST,
            "all safety acknowledgements must be true",
            {"missing_acknowledgements": missing},
        )
    if manifest.provider != "dynamic":
        raise CaptchaSkillError(
            ErrorCode.THIRD_PARTY_PROVIDER_DENIED,
            "only ReCAP's synthetic dynamic provider is permitted",
        )
    if manifest.recap_commit != RECAP_COMMIT:
        raise CaptchaSkillError(
            ErrorCode.RECAP_COMMIT_MISMATCH,
            "authorization is not bound to the approved ReCAP commit",
            {"expected": RECAP_COMMIT, "actual": manifest.recap_commit},
        )
    if manifest.test_mode not in {TestMode.ONCE, TestMode.CUSTOM}:
        raise CaptchaSkillError(
            ErrorCode.UNSAFE_BENCHMARK_MODE,
            "only bounded once/custom modes are permitted",
        )

    _validate_loopback_url(
        str(manifest.target_url),
        error_code=ErrorCode.TARGET_NOT_LOOPBACK,
        label="target_url",
        require_root_path=True,
    )
    _validate_loopback_url(
        str(manifest.model_base_url),
        error_code=ErrorCode.MODEL_ENDPOINT_NOT_LOOPBACK,
        label="model_base_url",
        require_root_path=False,
    )

    limitations = [
        "Synthetic ReCAP dynamic provider only.",
        "Target and model endpoint use literal loopback IP addresses.",
        "No credentials, cookies, proxies, stealth, or third-party CAPTCHA providers.",
        (
            "A PASS measures this bounded synthetic run; it does not authorize "
            "or prove live-site bypass."
        ),
    ]
    return AuthorizationReceipt(
        schema_version="captcha.authorization_receipt.v1",
        authorization_id=manifest.authorization_id,
        action=required_action,
        validated_at=current,
        expires_at=manifest.expires_at,
        manifest_sha256=manifest_sha256,
        target_url=str(manifest.target_url),
        model_base_url=str(manifest.model_base_url),
        policy_version=POLICY_VERSION,
        limitations=limitations,
        seam_validation=SeamValidation(kind="captcha.authorization_manifest"),
    )
