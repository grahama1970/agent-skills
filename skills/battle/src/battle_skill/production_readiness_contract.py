"""Fail-closed production readiness contract for Battle receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .packaged_deployment_smoke import _now_utc
from .production_infrastructure_contract import (
    EXPECTED_SCHEMA as EXPECTED_PRODUCTION_INFRASTRUCTURE_SCHEMA,
    validate_production_infrastructure_receipt,
)


REQUIRED_EXTERNAL_RECEIPTS = {
    "production_infrastructure": "Production infrastructure deployment receipt is missing or not PASS.",
    "production_websocket": "Production-shaped WebSocket auth/fanout/reconnect receipt is missing or not PASS.",
    "unbounded_swarm": "Unbounded swarm execution receipt is missing or not PASS.",
}
EXPECTED_EXTERNAL_SCHEMAS = {
    "production_infrastructure": EXPECTED_PRODUCTION_INFRASTRUCTURE_SCHEMA,
    "production_websocket": "battle.production_websocket_transport_proof.v1",
    "unbounded_swarm": "battle.unbounded_swarm_execution_proof.v1",
}


def validate_production_readiness(
    *,
    out_dir: Path,
    repo_root: Path,
    containerized_receipt: Path,
    packaged_receipt: Path | None = None,
    local_deployment_alignment_receipt: Path | None = None,
    production_infrastructure_receipt: Path | None = None,
    production_websocket_receipt: Path | None = None,
    unbounded_swarm_receipt: Path | None = None,
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    repo_root = repo_root.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    local_checks: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    errors: list[str] = []

    containerized = _load_receipt(containerized_receipt)
    local_checks.append(
        _local_containerized_check(containerized_receipt.resolve(), containerized)
    )
    if local_checks[-1]["status"] != "PASS":
        errors.extend(local_checks[-1]["errors"])

    if packaged_receipt is not None:
        packaged = _load_receipt(packaged_receipt)
        local_checks.append(_local_packaged_check(packaged_receipt.resolve(), packaged))
        if local_checks[-1]["status"] != "PASS":
            errors.extend(local_checks[-1]["errors"])

    if local_deployment_alignment_receipt is not None:
        deployment_alignment = _load_receipt(local_deployment_alignment_receipt)
        local_checks.append(
            _local_deployment_alignment_check(
                local_deployment_alignment_receipt.resolve(),
                deployment_alignment,
            )
        )
        if local_checks[-1]["status"] != "PASS":
            errors.extend(local_checks[-1]["errors"])

    external_inputs = {
        "production_infrastructure": production_infrastructure_receipt,
        "production_websocket": production_websocket_receipt,
        "unbounded_swarm": unbounded_swarm_receipt,
    }
    external_checks = [
        _external_check(name, path)
        for name, path in external_inputs.items()
    ]
    for check in external_checks:
        if check["status"] != "PASS":
            blockers.append(
                {
                    "id": f"{check['id']}_missing_or_not_pass",
                    "reason": REQUIRED_EXTERNAL_RECEIPTS[check["id"]],
                }
            )

    status = "FAIL" if errors else "BLOCKED" if blockers else "PASS"
    websocket_passed = any(
        check["id"] == "production_websocket" and check["status"] == "PASS"
        for check in external_checks
    )
    swarm_passed = any(
        check["id"] == "unbounded_swarm" and check["status"] == "PASS"
        for check in external_checks
    )
    receipt = {
        "schema": "battle.production_readiness_contract.v1",
        "status": status,
        "mocked": False,
        "live": "receipt_contract_validation",
        "repo_root": str(repo_root),
        "local_source_commits": {
            "containerized_package": _package_source_commit(containerized),
            "packaged_package": _package_source_commit(packaged) if packaged_receipt is not None else None,
        },
        "local_working_frontend_backend_status": "PASS" if not errors else "FAIL",
        "local_deployment_alignment_status": _local_check_status(
            local_checks,
            "local_deployment_alignment",
        ),
        "local_checks": local_checks,
        "external_checks": external_checks,
        "blockers": blockers,
        "errors": errors,
        "claim_boundary": {
            "proves": [
                "Local Battle frontend/backend container receipt is structurally present and fail-closed checked.",
                "Local deployment alignment is recorded separately from production infrastructure.",
                "Production readiness remains blocked unless external production receipts are supplied.",
            ]
            + (
                [
                    "A production-shaped local WebSocket receipt proves auth rejection, reconnect resume, and two-client fanout on the local adapter."
                ]
                if websocket_passed
                else []
            )
            + (
                [
                    "A Docker-backed dynamic swarm receipt proves 12 isolated no-network workers with a recorded concurrency envelope."
                ]
                if swarm_passed
                else []
            ),
            "does_not_prove": _does_not_prove(
                blockers=blockers,
                websocket_passed=websocket_passed,
                swarm_passed=swarm_passed,
            ),
        },
        "created_at": _now_utc(),
    }
    (out_dir / "production-readiness-contract.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def _local_containerized_check(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if receipt.get("schema") != "battle.containerized_deployment_smoke.v1":
        errors.append("containerized receipt schema mismatch")
    if receipt.get("status") != "PASS":
        errors.append("containerized receipt status is not PASS")
    if receipt.get("mocked") is not False:
        errors.append("containerized receipt must be mocked=false")
    if receipt.get("live") != "containerized_http_sse_websocket_adapter_plus_vite_preview":
        errors.append("containerized receipt live mode mismatch")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    if counts.get("pr8_failed") != 0:
        errors.append("containerized PR8 failures are nonzero")
    if counts.get("test_interactions_failed") != 0:
        errors.append("containerized test-interactions failures are nonzero")
    if counts.get("test_interactions_warned") != 0:
        errors.append("containerized test-interactions warnings are nonzero")
    if counts.get("visual_findings") != 0:
        errors.append("containerized visual findings are nonzero")
    proofs = receipt.get("proofs") if isinstance(receipt.get("proofs"), dict) else {}
    for key in (
        "backend_live_transport_receipt",
        "pr8_live_transport_summary",
        "test_interactions_results",
        "visual_findings",
        "screenshot",
    ):
        if not proofs.get(key):
            errors.append(f"containerized proof path missing: {key}")
    return {
        "id": "containerized_local_frontend_backend",
        "status": "PASS" if not errors else "FAIL",
        "path": str(path),
        "errors": errors,
    }


def _local_packaged_check(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if receipt.get("schema") != "battle.packaged_deployment_smoke.v1":
        errors.append("packaged receipt schema mismatch")
    if receipt.get("status") != "PASS":
        errors.append("packaged receipt status is not PASS")
    if receipt.get("mocked") is not False:
        errors.append("packaged receipt must be mocked=false")
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    if counts.get("pr8_failed") != 0:
        errors.append("packaged PR8 failures are nonzero")
    if counts.get("test_interactions_failed") != 0:
        errors.append("packaged test-interactions failures are nonzero")
    if counts.get("test_interactions_warned") != 0:
        errors.append("packaged test-interactions warnings are nonzero")
    if counts.get("visual_findings") != 0:
        errors.append("packaged visual findings are nonzero")
    return {
        "id": "packaged_local_frontend_backend",
        "status": "PASS" if not errors else "FAIL",
        "path": str(path),
        "errors": errors,
    }


def _local_deployment_alignment_check(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if receipt.get("schema") != "battle.local_deployment_alignment_proof.v1":
        errors.append("local deployment alignment receipt schema mismatch")
    if receipt.get("status") != "PASS":
        errors.append("local deployment alignment receipt status is not PASS")
    if receipt.get("mocked") is not False:
        errors.append("local deployment alignment receipt must be mocked=false")
    if receipt.get("live") != "local_filesystem_release_cut_and_symlink_readback":
        errors.append("local deployment alignment live mode mismatch")
    if receipt.get("commit") != receipt.get("origin_main"):
        errors.append("local deployment alignment commit does not match origin_main")
    if receipt.get("release_digest") != receipt.get("expected_digest"):
        errors.append("local deployment alignment release digest mismatch")
    if receipt.get("current_digest") != receipt.get("expected_digest"):
        errors.append("local deployment alignment current digest mismatch")
    if receipt.get("current_symlink_resolved_after") != receipt.get("release_dir"):
        errors.append("local deployment alignment current symlink target mismatch")
    return {
        "id": "local_deployment_alignment",
        "status": "PASS" if not errors else "FAIL",
        "path": str(path),
        "errors": errors,
    }


def _external_check(name: str, path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"id": name, "status": "MISSING", "path": None}
    receipt = _load_receipt(path)
    expected_schema = EXPECTED_EXTERNAL_SCHEMAS[name]
    errors = _external_receipt_errors(name, receipt, expected_schema)
    status = "PASS" if not errors else "BLOCKED"
    return {
        "id": name,
        "status": status,
        "path": str(path.resolve()),
        "schema": receipt.get("schema"),
        "expected_schema": expected_schema,
        "mocked": receipt.get("mocked"),
        "live": receipt.get("live"),
        "errors": errors,
    }


def _external_receipt_errors(
    name: str,
    receipt: dict[str, Any],
    expected_schema: str,
) -> list[str]:
    if name == "production_infrastructure":
        return validate_production_infrastructure_receipt(receipt)
    errors: list[str] = []
    if receipt.get("schema") != expected_schema:
        errors.append(f"{name} receipt schema mismatch")
    if receipt.get("status") != "PASS":
        errors.append(f"{name} receipt status is not PASS")
    if receipt.get("mocked") is not False:
        errors.append(f"{name} receipt must be mocked=false")
    return errors


def _load_receipt(path: Path) -> dict[str, Any]:
    with path.expanduser().resolve().open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"receipt is not a JSON object: {path}")
    return data


def _package_source_commit(receipt: dict[str, Any]) -> str | None:
    package = receipt.get("package") if isinstance(receipt.get("package"), dict) else {}
    value = package.get("source_commit")
    return value if isinstance(value, str) and value else None


def _local_check_status(checks: list[dict[str, Any]], check_id: str) -> str | None:
    for check in checks:
        if check.get("id") == check_id:
            status = check.get("status")
            return status if isinstance(status, str) else None
    return None


def _does_not_prove(
    *,
    blockers: list[dict[str, str]],
    websocket_passed: bool,
    swarm_passed: bool,
) -> list[str]:
    if not blockers:
        return []
    claims = [
        "Production infrastructure is deployed.",
        "Cloud, Kubernetes, DNS, certificate, ingress, or secret-management behavior.",
        "Battle or RelayForge is production ready.",
    ]
    if not swarm_passed:
        claims.insert(-1, "Unbounded swarm execution works.")
    else:
        claims.insert(-1, "Mathematically infinite swarm execution or production cluster autoscaling.")
    if websocket_passed:
        claims.insert(
            2,
            "Production TLS/certificate-backed WebSocket deployment or production-scale fanout capacity.",
        )
    else:
        claims.insert(
            2,
            "Production-shaped WebSocket auth, fanout, compression, or reconnect behavior.",
        )
    return claims
