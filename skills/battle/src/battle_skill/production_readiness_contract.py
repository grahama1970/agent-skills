"""Fail-closed production readiness contract for Battle receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .packaged_deployment_smoke import _now_utc


REQUIRED_EXTERNAL_RECEIPTS = {
    "production_infrastructure": "Production infrastructure deployment receipt is missing or not PASS.",
    "production_websocket": "Production WebSocket TLS/auth/fanout/reconnect receipt is missing or not PASS.",
    "unbounded_swarm": "Unbounded swarm execution receipt is missing or not PASS.",
}


def validate_production_readiness(
    *,
    out_dir: Path,
    repo_root: Path,
    containerized_receipt: Path,
    packaged_receipt: Path | None = None,
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
        "local_checks": local_checks,
        "external_checks": external_checks,
        "blockers": blockers,
        "errors": errors,
        "claim_boundary": {
            "proves": [
                "Local Battle frontend/backend container receipt is structurally present and fail-closed checked.",
                "Production readiness remains blocked unless external production receipts are supplied.",
            ],
            "does_not_prove": [
                "Production infrastructure is deployed.",
                "Production WebSocket TLS, auth, fanout, compression, or reconnect behavior.",
                "Cloud, Kubernetes, DNS, certificate, ingress, or secret-management behavior.",
                "Unbounded swarm execution works.",
                "Battle or RelayForge is production ready.",
            ]
            if blockers
            else [],
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


def _external_check(name: str, path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"id": name, "status": "MISSING", "path": None}
    receipt = _load_receipt(path)
    status = "PASS" if receipt.get("status") == "PASS" and receipt.get("mocked") is False else "BLOCKED"
    return {
        "id": name,
        "status": status,
        "path": str(path.resolve()),
        "schema": receipt.get("schema"),
        "mocked": receipt.get("mocked"),
    }


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
