"""Validation contract for Battle production infrastructure receipts."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


EXPECTED_SCHEMA = "battle.production_infrastructure_deployment_proof.v1"
EXPECTED_LIVE_MODE = "production_infrastructure_deployment"
LOCAL_ONLY_LIVE_MODES = {
    "local_filesystem_release_cut_and_symlink_readback",
    "local_release_symlink_only",
}

REQUIRED_TARGET_FIELDS = (
    "environment",
    "frontend_url",
    "backend_health_url",
    "websocket_url",
    "commit",
    "release_id",
)
REQUIRED_EVIDENCE_FIELDS = (
    "frontend_https_response",
    "backend_health_response",
    "websocket_connectivity",
    "tls_certificate",
    "dns_resolution",
    "ingress_route",
    "secret_configuration",
)


def validate_production_infrastructure_receipt(receipt: dict[str, Any]) -> list[str]:
    """Return fail-closed validation errors for a production infra receipt."""
    errors: list[str] = []
    if receipt.get("schema") != EXPECTED_SCHEMA:
        errors.append("production infrastructure schema mismatch")
    if receipt.get("status") != "PASS":
        errors.append("production infrastructure status is not PASS")
    if receipt.get("mocked") is not False:
        errors.append("production infrastructure receipt must be mocked=false")

    live = receipt.get("live")
    if live in LOCAL_ONLY_LIVE_MODES:
        errors.append("local deployment proof cannot satisfy production infrastructure")
    if live != EXPECTED_LIVE_MODE:
        errors.append("production infrastructure live mode mismatch")

    target = receipt.get("target")
    if not isinstance(target, dict):
        errors.append("production infrastructure target object missing")
        target = {}
    for field in REQUIRED_TARGET_FIELDS:
        if not _non_empty_string(target.get(field)):
            errors.append(f"production infrastructure target missing: {field}")

    if target.get("environment") != "production":
        errors.append("production infrastructure target.environment must be production")
    _require_url(
        errors,
        target.get("frontend_url"),
        field="target.frontend_url",
        scheme="https",
    )
    _require_url(
        errors,
        target.get("backend_health_url"),
        field="target.backend_health_url",
        scheme="https",
    )
    _require_url(
        errors,
        target.get("websocket_url"),
        field="target.websocket_url",
        scheme="wss",
    )

    evidence = receipt.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("production infrastructure evidence object missing")
        evidence = {}
    for field in REQUIRED_EVIDENCE_FIELDS:
        if not isinstance(evidence.get(field), dict) or not evidence.get(field):
            errors.append(f"production infrastructure evidence missing: {field}")

    _require_status_code(errors, evidence.get("frontend_https_response"), field="frontend_https_response")
    _require_status_code(errors, evidence.get("backend_health_response"), field="backend_health_response")
    if isinstance(evidence.get("websocket_connectivity"), dict) and evidence[
        "websocket_connectivity"
    ].get("connected") is not True:
        errors.append("production infrastructure websocket_connectivity.connected must be true")
    if isinstance(evidence.get("tls_certificate"), dict) and evidence[
        "tls_certificate"
    ].get("valid") is not True:
        errors.append("production infrastructure tls_certificate.valid must be true")
    if isinstance(evidence.get("dns_resolution"), dict) and evidence[
        "dns_resolution"
    ].get("resolves") is not True:
        errors.append("production infrastructure dns_resolution.resolves must be true")
    if isinstance(evidence.get("ingress_route"), dict) and evidence["ingress_route"].get(
        "status"
    ) != "PASS":
        errors.append("production infrastructure ingress_route.status must be PASS")
    if isinstance(evidence.get("secret_configuration"), dict) and not _non_empty_string(
        evidence["secret_configuration"].get("source")
    ):
        errors.append("production infrastructure secret_configuration.source missing")

    return errors


def _require_url(
    errors: list[str],
    value: Any,
    *,
    field: str,
    scheme: str,
) -> None:
    if not _non_empty_string(value):
        return
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if parsed.scheme != scheme or not host:
        errors.append(f"production infrastructure {field} must be {scheme} URL")
        return
    if host in {"localhost", "127.0.0.1", "::1"} or host.startswith("127."):
        errors.append(f"production infrastructure {field} must not target localhost")


def _require_status_code(errors: list[str], value: Any, *, field: str) -> None:
    if isinstance(value, dict) and value.get("status_code") != 200:
        errors.append(f"production infrastructure {field}.status_code must be 200")


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
