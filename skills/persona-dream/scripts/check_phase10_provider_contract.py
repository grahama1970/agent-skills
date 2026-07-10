#!/usr/bin/env python3
"""Check Phase 10 provider-contract dry-run fixtures."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from write_phase10_provider_contract import (
    BLOCKED_STATUS,
    PASS_STATUS,
    build_contract,
    sha256_json,
    write_json,
)


CHECK_PASS_STATUS = "PASS_PHASE10_PROVIDER_CONTRACT_DRY_RUN_GATE"
CHECK_BLOCKED_STATUS = "BLOCKED_PHASE10_PROVIDER_CONTRACT_DRY_RUN_GATE"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


REQUIRED_CONTRACT_SECTIONS = [
    "provider_id",
    "fal_model_endpoint",
    "registry_refresh_status",
    "normalized_request_schema",
    "provider_request",
    "field_mapping",
    "provider_media_publication_plan",
    "cost_contract",
    "entitlement_contract",
    "async_return_contract",
    "manual_acceptance",
    "phase10_contract_blockers",
    "phase11_live_readiness_blockers",
    "non_claims",
]


def validate_contract_shape(contract: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for section in REQUIRED_CONTRACT_SECTIONS:
        if section not in contract:
            blockers.append("BLOCKED_PHASE10_REQUIRED_SECTION_MISSING")
            break

    provider_request = contract.get("provider_request") if isinstance(contract.get("provider_request"), dict) else {}
    body = provider_request.get("body")
    if not provider_request.get("payload_sha256") or provider_request.get("payload_sha256") != sha256_json(body):
        blockers.append("BLOCKED_PHASE10_PAYLOAD_HASH_MISMATCH")

    input_payload = body.get("input") if isinstance(body, dict) and isinstance(body.get("input"), dict) else {}
    mapping = contract.get("field_mapping") if isinstance(contract.get("field_mapping"), list) else []
    mapped_fields = {
        item.get("provider_field")
        for item in mapping
        if isinstance(item, dict) and item.get("provider_field")
    }
    for key in input_payload:
        if f"input.{key}" not in mapped_fields:
            blockers.append("BLOCKED_PHASE10_REQUIRED_FIELD_UNMAPPED")
            break
    for item in mapping:
        if not isinstance(item, dict):
            continue
        if not item.get("source") and not item.get("source_artifact"):
            blockers.append("BLOCKED_PHASE10_MAPPING_SOURCE_MISSING")
            break

    async_contract = contract.get("async_return_contract") if isinstance(contract.get("async_return_contract"), dict) else {}
    if async_contract.get("selected_async_mode") != "polling":
        blockers.append("BLOCKED_POLLING_PLAN_NOT_ACCEPTED")
    polling = async_contract.get("polling_plan") if isinstance(async_contract.get("polling_plan"), dict) else {}
    if polling.get("accepted_for_phase10_dry_run") is not True:
        blockers.append("BLOCKED_POLLING_PLAN_NOT_ACCEPTED")
    if not polling.get("task_id_source"):
        blockers.append("BLOCKED_POLLING_TASK_ID_MAPPING_MISSING")
    if not polling.get("terminal_states"):
        blockers.append("BLOCKED_POLLING_TERMINAL_STATES_MISSING")

    if not isinstance(contract.get("phase10_contract_blockers"), list) or not isinstance(
        contract.get("phase11_live_readiness_blockers"), list
    ):
        blockers.append("BLOCKED_PHASE10_REQUIRED_SECTION_MISSING")
    if contract.get("status") == PASS_STATUS and not contract.get("phase11_live_readiness_blockers"):
        blockers.append("BLOCKED_PHASE11_LIVE_BLOCKERS_MISSING")
    for non_claim in (
        "does not prove current live fal schema compatibility",
        "does not prove provider submission",
        "does not prove provider return",
        "does not prove Watch observation",
        "does not prove memory persistence",
    ):
        if non_claim not in contract.get("non_claims", []):
            blockers.append("BLOCKED_PHASE10_REQUIRED_SECTION_MISSING")
            break
    return sorted(set(blockers))


def apply_tamper(contract_path: Path, tamper: dict[str, Any]) -> None:
    if not tamper:
        return
    contract = read_json(contract_path)
    for key in tamper.get("remove_sections") or []:
        contract.pop(key, None)
    for provider_field in tamper.get("remove_field_mappings") or []:
        mapping = contract.get("field_mapping") if isinstance(contract.get("field_mapping"), list) else []
        contract["field_mapping"] = [
            item for item in mapping if not (isinstance(item, dict) and item.get("provider_field") == provider_field)
        ]
    for provider_field in tamper.get("remove_mapping_sources") or []:
        mapping = contract.get("field_mapping") if isinstance(contract.get("field_mapping"), list) else []
        for item in mapping:
            if isinstance(item, dict) and item.get("provider_field") == provider_field:
                item.pop("source", None)
                item.pop("source_artifact", None)
    if "mutate_request_input" in tamper:
        body = contract.get("provider_request", {}).get("body", {})
        input_payload = body.get("input") if isinstance(body.get("input"), dict) else {}
        for key, value in tamper["mutate_request_input"].items():
            input_payload[key] = value
    if "async_contract" in tamper:
        contract["async_return_contract"] = tamper["async_contract"]
    write_json(contract_path, contract)


def run_fixture(fixture_path: Path, fixtures_root: Path, output_root: Path) -> dict[str, Any]:
    fixture = read_json(fixture_path)
    fixture_name = str(fixture_path.parent.relative_to(fixtures_root))
    out_dir = output_root / "phase10-provider-contract-fixture-results" / fixture_name
    packet_path = out_dir / "video_provider_packet.json"
    registry_refresh_path = out_dir / "provider_registry_refresh_receipt.v1.json"
    media_lock_path = out_dir / "media_lock_manifest.v1.json"
    scorecard_path = out_dir / "video_provider_scorecard.v1.json"
    contract_root = out_dir / "phase10_provider_contract"
    packet = fixture.get("video_provider_packet") or {}
    if isinstance(packet, dict) and isinstance(fixture.get("media_lock"), dict):
        write_json(media_lock_path, fixture["media_lock"])
        packet = dict(packet)
        packet["media_lock_path"] = str(media_lock_path)
    if isinstance(packet, dict) and isinstance(fixture.get("video_provider_scorecard"), dict):
        write_json(scorecard_path, fixture["video_provider_scorecard"])
        packet = dict(packet)
        packet["video_provider_scorecard_path"] = str(scorecard_path)
    write_json(packet_path, packet)
    write_json(registry_refresh_path, fixture.get("registry_refresh_receipt") or {})
    result = build_contract(packet_path, registry_refresh_path, contract_root)
    contract_path = Path(result["contract_path"])
    apply_tamper(contract_path, fixture.get("tamper_contract") if isinstance(fixture.get("tamper_contract"), dict) else {})
    contract = read_json(contract_path)
    shape_blockers = validate_contract_shape(contract)
    expected = fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
    errors: list[str] = []
    combined_status = BLOCKED_STATUS if shape_blockers else result["status"]
    combined_dry_run_blockers = sorted(set(result["dry_run_blockers"]) | set(shape_blockers))

    if expected.get("status") and combined_status != expected["status"]:
        errors.append(f"status_mismatch:{combined_status}:expected:{expected['status']}")
    if expected.get("live_submit_status") and contract.get("live_submit_status") != expected["live_submit_status"]:
        errors.append(
            f"live_submit_status_mismatch:{contract.get('live_submit_status')}:expected:{expected['live_submit_status']}"
        )
    for blocker in expected.get("dry_run_blockers") or []:
        if blocker not in combined_dry_run_blockers:
            errors.append(f"missing_dry_run_blocker:{blocker}")
    for blocker in expected.get("live_call_blockers") or []:
        if blocker not in result["live_call_blockers"]:
            errors.append(f"missing_live_call_blocker:{blocker}")

    for field in (
        "actual_provider_call_attempts",
        "provider_live",
        "paid_call_authorized",
        "provider_accessible_url_created",
        "submitted",
        "provider_ready",
        "live_submit_ready",
        "mocked",
    ):
        expected_value = 0 if field == "actual_provider_call_attempts" else False
        if result.get(field) != expected_value:
            errors.append(f"receipt_{field}_unexpected:{result.get(field)}")
        if contract.get(field) != expected_value:
            errors.append(f"contract_{field}_unexpected:{contract.get(field)}")

    if contract.get("provider_request", {}).get("submitted") is not False:
        errors.append("provider_request_submitted_not_false")
    if "live video generation" not in contract.get("claims", {}).get("does_not_prove", []):
        errors.append("missing_non_claim_live_video_generation")

    return {
        "fixture": fixture_name,
        "status": combined_status,
        "live_submit_status": contract.get("live_submit_status"),
        "provider_id": result.get("provider_id"),
        "provider_route": result.get("provider_route"),
        "dry_run_blockers": combined_dry_run_blockers,
        "live_call_blockers": result["live_call_blockers"],
        "contract_path": result["contract_path"],
        "errors": errors,
    }


def run_no_network_side_effect_check(fixtures_root: Path, output_root: Path) -> dict[str, Any]:
    good_fixture = fixtures_root / "good_kling_contract" / "fixture.json"
    fixture = read_json(good_fixture)
    out_dir = output_root / "phase10-no-network-side-effects"
    packet_path = out_dir / "video_provider_packet.json"
    registry_refresh_path = out_dir / "provider_registry_refresh_receipt.v1.json"
    media_lock_path = out_dir / "media_lock_manifest.v1.json"
    contract_root = out_dir / "phase10_provider_contract"

    packet = dict(fixture.get("video_provider_packet") or {})
    write_json(media_lock_path, fixture.get("media_lock") or {})
    packet["media_lock_path"] = str(media_lock_path)
    write_json(packet_path, packet)
    write_json(registry_refresh_path, fixture.get("registry_refresh_receipt") or {})

    calls: list[str] = []
    original_socket = socket.socket
    original_run = subprocess.run
    original_urlopen = urllib.request.urlopen

    def fail_socket(*args: Any, **kwargs: Any) -> Any:
        calls.append("socket.socket")
        raise AssertionError("network socket use is forbidden in Phase 10 dry-run check")

    def fail_run(*args: Any, **kwargs: Any) -> Any:
        command = args[0] if args else kwargs.get("args")
        if isinstance(command, (list, tuple)) and command and str(command[0]) in {"curl", "wget", "fal"}:
            calls.append(f"subprocess.run:{command[0]}")
            raise AssertionError("provider/network subprocess use is forbidden in Phase 10 dry-run check")
        return original_run(*args, **kwargs)

    def fail_urlopen(*args: Any, **kwargs: Any) -> Any:
        calls.append("urllib.request.urlopen")
        raise AssertionError("urllib network use is forbidden in Phase 10 dry-run check")

    try:
        socket.socket = fail_socket  # type: ignore[assignment]
        subprocess.run = fail_run  # type: ignore[assignment]
        urllib.request.urlopen = fail_urlopen  # type: ignore[assignment]
        result = build_contract(packet_path, registry_refresh_path, contract_root)
    finally:
        socket.socket = original_socket  # type: ignore[assignment]
        subprocess.run = original_run  # type: ignore[assignment]
        urllib.request.urlopen = original_urlopen  # type: ignore[assignment]

    errors: list[str] = []
    if calls:
        errors.append(f"unexpected_network_calls:{calls}")
    if result.get("actual_provider_call_attempts") != 0:
        errors.append(f"actual_provider_call_attempts_unexpected:{result.get('actual_provider_call_attempts')}")
    return {
        "status": "PASS_PHASE10_NO_NETWORK_SIDE_EFFECTS" if not errors else "BLOCKED_PHASE10_NETWORK_SIDE_EFFECTS",
        "errors": errors,
        "network_calls_observed": calls,
        "contract_path": result.get("contract_path"),
        "actual_provider_call_attempts": result.get("actual_provider_call_attempts"),
    }


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    results = [
        run_fixture(path, fixtures_root, receipt_out.parent)
        for path in sorted(fixtures_root.glob("*/fixture.json"))
    ]
    no_network = run_no_network_side_effect_check(fixtures_root, receipt_out.parent)
    errors = [f"{result['fixture']}:{error}" for result in results for error in result["errors"]]
    errors.extend(f"no_network:{error}" for error in no_network["errors"])
    observed_statuses = sorted({result["status"] for result in results})
    observed_dry_blockers = sorted({blocker for result in results for blocker in result["dry_run_blockers"]})
    observed_live_blockers = sorted({blocker for result in results for blocker in result["live_call_blockers"]})

    if no_network["status"] != "PASS_PHASE10_NO_NETWORK_SIDE_EFFECTS":
        errors.append(f"no_network_status_mismatch:{no_network['status']}")
    if len(results) != 15:
        errors.append(f"fixture_count_mismatch:{len(results)}:expected:15")
    for status in (PASS_STATUS, BLOCKED_STATUS):
        if status not in observed_statuses:
            errors.append(f"missing_observed_status:{status}")
    expected_dry_blockers = {
        "BLOCKED_PROVIDER_REGISTRY_REFRESH_NOT_PASS",
        "BLOCKED_SUBMITTED_IN_PHASE10_DRY_RUN",
        "BLOCKED_PAID_CALL_AUTHORIZED_IN_PHASE10_DRY_RUN",
        "BLOCKED_PHASE10_PROVIDER_ID_MISMATCH",
        "BLOCKED_PHASE10_ENDPOINT_MISMATCH",
        "BLOCKED_VIDEO_PROVIDER_PACKET_NOT_PASS",
        "BLOCKED_PHASE10_REVISION_MISMATCH",
        "BLOCKED_PHASE10_PAYLOAD_HASH_MISMATCH",
        "BLOCKED_PHASE10_REQUIRED_SECTION_MISSING",
        "BLOCKED_PHASE10_REQUIRED_FIELD_UNMAPPED",
        "BLOCKED_PHASE10_MAPPING_SOURCE_MISSING",
        "BLOCKED_PROVIDER_LIVE_IN_PHASE10_DRY_RUN",
        "BLOCKED_ACTUAL_PROVIDER_CALL_ATTEMPTS_IN_PHASE10_DRY_RUN",
        "BLOCKED_PROVIDER_ACCESSIBLE_URL_CREATED_IN_PHASE10_DRY_RUN",
        "BLOCKED_POLLING_PLAN_NOT_ACCEPTED",
        "BLOCKED_POLLING_TASK_ID_MAPPING_MISSING",
        "BLOCKED_POLLING_TERMINAL_STATES_MISSING",
    }
    for blocker in sorted(expected_dry_blockers - set(observed_dry_blockers)):
        errors.append(f"missing_expected_dry_run_blocker:{blocker}")
    for blocker in (
        "BLOCKED_PROVIDER_ACCESSIBLE_URLS_MISSING",
        "BLOCKED_COST_ESTIMATE_UNVERIFIED",
        "BLOCKED_PAID_CALL_AUTHORIZATION_MISSING",
    ):
        if blocker not in observed_live_blockers:
            errors.append(f"missing_expected_live_blocker:{blocker}")

    receipt = {
        "schema": "persona_dream.phase10.provider_contract_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": CHECK_PASS_STATUS if not errors else CHECK_BLOCKED_STATUS,
        "fixture_count": len(results),
        "observed_statuses": observed_statuses,
        "observed_dry_run_blockers": observed_dry_blockers,
        "observed_live_call_blockers": observed_live_blockers,
        "errors": errors,
        "results": results,
        "no_network_side_effect_check": no_network,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "proof_kind": "fixture_contract_test",
        "fixture_backed": True,
        "live_external_evidence": False,
        "mocked_provider_response": False,
        "claims": {
            "proves": [
                "Phase 10 provider-contract fixtures compiled dry-run provider contracts",
                "submitted/live/paid provider packet states fail closed",
                "missing provider registry refresh evidence fails closed",
                "live-readiness blockers are retained without submitting provider calls",
            ],
            "does_not_prove": [
                "current fal provider schema compatibility",
                "provider-accessible media URLs",
                "URL probe success",
                "cost approval",
                "manual acceptance",
                "paid-call authorization",
                "live provider readiness",
                "live video generation",
            ],
        },
    }
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-root", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run_fixtures(args.fixtures_root.resolve(), args.receipt_out.resolve())
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == CHECK_PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
