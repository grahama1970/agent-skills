"""Build PR3c provider authorship receipts from Tau and Battle evidence."""

from __future__ import annotations

import json
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROVIDER_AUTHORSHIP_SCHEMA = "battle.provider_authorship_receipt.v1"
PROVIDER_CODE_AUTHOR_BOUNDARY_SCHEMA = "battle.provider_code_author_boundary_receipt.v1"


def build_provider_authorship_receipt(
    *,
    out_path: Path,
    battle_id: str,
    dag_id: str | None,
    node_id: str,
    child_lane_id: str | None,
    goal_hash: str | None,
    battle_work_order_path: Path,
    tau_work_order_path: Path,
    launch_receipt_path: Path,
    worker_result_path: Path | None,
    worker_validation_path: Path | None,
    artifact_validation: dict[str, Any],
    launch_receipt: dict[str, Any] | None,
    worker_result: dict[str, Any] | None,
    worker_validation: dict[str, Any] | None,
) -> dict[str, Any]:
    provider_live = _provider_live(launch_receipt, worker_validation)
    transport_identity = _transport_identity(
        launch_receipt=launch_receipt,
        worker_result=worker_result,
        worker_validation=worker_validation,
        artifact_validation=artifact_validation,
    )
    worker_validation_passed = bool(
        isinstance(worker_validation, dict) and worker_validation.get("status") == "PASS"
    )
    status = (
        "PASS"
        if provider_live
        and worker_validation_passed
        and artifact_validation.get("status") == "PASS"
        and transport_identity["status"] == "PASS"
        else "BLOCKED"
    )
    errors: list[str] = []
    if not provider_live:
        errors.append("PROVIDER_EXECUTION_ATTESTATION_MISSING")
    elif not worker_validation_passed:
        errors.append("TAU_WORKER_VALIDATION_BLOCKED")
    if artifact_validation.get("status") != "PASS":
        errors.extend([str(item) for item in artifact_validation.get("errors", [])])
    errors.extend(transport_identity["errors"])

    route = _route(launch_receipt, worker_validation)
    receipt = {
        "schema": PROVIDER_AUTHORSHIP_SCHEMA,
        "status": status,
        "mocked": False,
        "live": "tau_provider_artifact_authoring",
        "agentic": provider_live,
        "provider_live": provider_live,
        "fixture_fallback_used": False,
        "battle_id": battle_id,
        "dag_id": dag_id,
        "node_id": node_id,
        "child_lane_id": child_lane_id,
        "goal_hash": goal_hash,
        "execution_mode": "tau_provider" if provider_live else "blocked",
        "authored_by": "tau_provider" if provider_live else "none",
        "requested_provider": route.get("provider"),
        "requested_model": route.get("model"),
        "requested_surface": route.get("surface"),
        "observed_provider": _observed_provider(launch_receipt, worker_validation),
        "observed_model": _observed_model(launch_receipt, worker_validation),
        "provider_run_id": _value(launch_receipt, "run_id"),
        "provider_session_id": _value(launch_receipt, "session_id"),
        "provider_request_id": transport_identity["provider_request_id"],
        "provider_response_id": transport_identity["provider_response_id"],
        "provider_call_count": transport_identity["provider_call_count"],
        "provider_run_status": _value(launch_receipt, "scillm_run_status"),
        "battle_work_order_path": str(battle_work_order_path),
        "tau_work_order_path": str(tau_work_order_path),
        "tau_launch_receipt_path": str(launch_receipt_path),
        "tau_worker_result_path": str(worker_result_path) if worker_result_path else None,
        "tau_worker_validation_receipt_path": str(worker_validation_path) if worker_validation_path else None,
        "code_artifact_path": artifact_validation.get("code_artifact_path"),
        "code_artifact_sha256": artifact_validation.get("code_artifact_sha256"),
        "code_artifact_bytes": artifact_validation.get("code_artifact_bytes"),
        "validation": {
            "goal_hash_bound": bool(goal_hash),
            "provider_route_bound": bool(route),
            "transport_request_id_bound": bool(transport_identity["provider_request_id"]),
            "transport_response_id_bound": bool(transport_identity["provider_response_id"]),
            "provider_call_count_bound": transport_identity["provider_call_count"] == 1,
            "output_declared_by_worker": _declares(worker_result, "outputs/exploit_specimen.py"),
            "output_hash_bound": bool(artifact_validation.get("code_artifact_sha256")),
            "transport_source_hash_bound": bool(
                transport_identity["transport_source_sha256"]
            ),
            "transport_source_hash_matches": transport_identity[
                "transport_source_hash_matches"
            ],
            "output_inside_allowed_root": "OUTPUT_PATH_ESCAPE" not in artifact_validation.get("errors", []),
            "private_reference_scan_passed": not any(str(error).startswith("PRIVATE_REFERENCE") for error in artifact_validation.get("errors", [])),
            "claim_boundary_passed": True,
        },
        "transport_source_sha256": transport_identity["transport_source_sha256"],
        "compile_status": "NOT_RUN",
        "runtime_status": "NOT_RUN",
        "target_contact": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "judge_verified_exploits": 0,
        "errors": errors,
        "claims": {
            "proves": [
                "Tau invoked an attested provider/model route.",
                "The provider route materialized the bound exploit specimen artifact.",
                "Battle validated artifact provenance and claim boundaries.",
            ]
            if status == "PASS"
            else [],
            "does_not_prove": [
                "The code compiles.",
                "The code runs.",
                "The code contacts the target.",
                "The code exploits the target.",
                "Any Blue detection, kill, or block occurred.",
                "Judge verified exploit success.",
            ],
        },
        "created_at": _utc_stamp(),
    }
    _write_json(out_path, receipt)
    return receipt


def build_phase1_boundary_receipt(
    *,
    out_path: Path,
    authorship: dict[str, Any],
) -> dict[str, Any]:
    status = "PASS" if authorship.get("status") == "PASS" else "BLOCKED"
    receipt = {
        "schema": PROVIDER_CODE_AUTHOR_BOUNDARY_SCHEMA,
        "status": status,
        "mocked": False,
        "live": "tau_provider_artifact_authoring",
        "agentic": bool(authorship.get("agentic")),
        "provider_live": bool(authorship.get("provider_live")),
        "fixture_fallback_used": False,
        "battle_id": authorship.get("battle_id"),
        "dag_id": authorship.get("dag_id"),
        "node_id": authorship.get("node_id"),
        "child_lane_id": authorship.get("child_lane_id"),
        "goal_hash": authorship.get("goal_hash"),
        "compile_status": "NOT_RUN",
        "runtime_status": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "judge_verified_exploits": 0,
        "provider_authorship_receipt": out_path.name.replace("provider-code-author-boundary-receipt", "provider-authorship-receipt"),
        "errors": authorship.get("errors", []),
        "claims": authorship.get("claims", {}),
        "created_at": _utc_stamp(),
    }
    _write_json(out_path, receipt)
    return receipt


def _provider_live(launch: dict[str, Any] | None, validation: dict[str, Any] | None) -> bool:
    return bool(
        isinstance(launch, dict)
        and isinstance(validation, dict)
        and launch.get("provider_live") is True
        and validation.get("provider_live") is True
        and launch.get("live") is True
    )


def _route(*receipts: dict[str, Any] | None) -> dict[str, Any]:
    for receipt in receipts:
        if isinstance(receipt, dict) and isinstance(receipt.get("model_provider_route"), dict):
            return dict(receipt["model_provider_route"])
    return {}


def _transport_identity(
    *,
    launch_receipt: dict[str, Any] | None,
    worker_result: dict[str, Any] | None,
    worker_validation: dict[str, Any] | None,
    artifact_validation: dict[str, Any],
) -> dict[str, Any]:
    """Extract transport-owned identity that model text cannot self-attest."""

    request_id = _first_value(
        launch_receipt,
        worker_validation,
        worker_result,
        keys=("provider_request_id", "request_id", "scillm_request_id"),
    )
    response_id = _first_value(
        launch_receipt,
        worker_validation,
        worker_result,
        keys=("provider_response_id", "response_id", "scillm_response_id"),
    )
    call_count = _first_int(
        launch_receipt,
        worker_validation,
        worker_result,
        keys=("provider_call_count", "provider_attempt_count", "attempt_count"),
    )
    artifact_sha = artifact_validation.get("code_artifact_sha256")
    source_sha = _transport_source_sha256(worker_result, worker_validation)
    source_hash_matches = bool(
        isinstance(artifact_sha, str)
        and isinstance(source_sha, str)
        and artifact_sha == source_sha
    )

    errors: list[str] = []
    if not request_id:
        errors.append("PROVIDER_REQUEST_ID_MISSING")
    if not response_id:
        errors.append("PROVIDER_RESPONSE_ID_MISSING")
    if call_count is None:
        errors.append("PROVIDER_CALL_COUNT_MISSING")
    elif call_count != 1:
        errors.append("PROVIDER_CALL_COUNT_INVALID")
    if not source_sha:
        errors.append("PROVIDER_SOURCE_HASH_MISSING")
    elif not source_hash_matches:
        errors.append("PROVIDER_SOURCE_HASH_MISMATCH")

    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "provider_request_id": request_id,
        "provider_response_id": response_id,
        "provider_call_count": call_count,
        "transport_source_sha256": source_sha,
        "transport_source_hash_matches": source_hash_matches,
    }


def _transport_source_sha256(*receipts: dict[str, Any] | None) -> str | None:
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        for key in (
            "source_sha256",
            "code_artifact_sha256",
            "artifact_sha256",
            "output_sha256",
            "transport_source_sha256",
        ):
            value = receipt.get(key)
            if isinstance(value, str) and value.startswith("sha256:"):
                return value
        for key in ("source", "source_text", "exploit_source", "artifact_source", "code", "code_text"):
            value = receipt.get(key)
            if isinstance(value, str) and value:
                return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
        artifacts = receipt.get("artifacts") or receipt.get("result_artifacts")
        if isinstance(artifacts, list):
            for item in artifacts:
                if not isinstance(item, dict):
                    continue
                if item.get("path") != "outputs/exploit_specimen.py":
                    continue
                value = item.get("sha256")
                if isinstance(value, str) and value.startswith("sha256:"):
                    return value
    return None


def _first_value(
    *receipts: dict[str, Any] | None, keys: tuple[str, ...]
) -> str | None:
    for receipt in receipts:
        for key in keys:
            value = _value(receipt, key)
            if value:
                return value
    return None


def _first_int(
    *receipts: dict[str, Any] | None, keys: tuple[str, ...]
) -> int | None:
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        for key in keys:
            value = receipt.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def _observed_provider(*receipts: dict[str, Any] | None) -> str | None:
    for receipt in receipts:
        value = _value(receipt, "observed_provider") or _value(receipt, "provider")
        if value:
            return value
    return None


def _observed_model(*receipts: dict[str, Any] | None) -> str | None:
    for receipt in receipts:
        value = _value(receipt, "observed_model") or _value(receipt, "model")
        if value:
            return value
    return None


def _value(receipt: dict[str, Any] | None, key: str) -> str | None:
    value = receipt.get(key) if isinstance(receipt, dict) else None
    return value if isinstance(value, str) and value else None


def _declares(result: dict[str, Any] | None, artifact: str) -> bool:
    values = result.get("artifacts") if isinstance(result, dict) else None
    if not isinstance(values, list):
        return False
    for value in values:
        if value == artifact:
            return True
        if isinstance(value, dict) and value.get("path") == artifact:
            return True
    return False


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
