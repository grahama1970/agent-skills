"""Publish and validate the Battle live transport contract for UX8."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema


LIVE_TRANSPORT_CONTRACT_SCHEMA = "battle.live_transport_contract.v1"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.live_transport_contract.v1.schema.json"
FIXTURE_ID = "battle-004-pr8-live-transport"
SNAPSHOT_ENDPOINT = "/battle/live/battle-004/snapshot"
SSE_ENDPOINT = "/battle/live/battle-004/events"
FRONTEND_ROUTE = "#battle/live?engine=pixi&battle=battle-004"
GENETIC_EVENT_TYPES = [
    "research_started",
    "research_receipt_materialized",
    "genome_selected",
    "method_added",
    "method_rejected",
    "code_author_started",
    "specimen_materialized",
    "compile_failed",
    "repair_started",
    "repair_materialized",
    "compile_passed",
    "target_contact_unproven",
    "judge_pending",
    "judge_exploit_success",
    "genome_promoted",
    "branch_abandoned",
]
PATH_LEAK_MARKERS = (
    "tau-dag-run/",
    "command-loop/",
    "command-artifacts/",
    "provider-workspace",
    "pr3c-provider-workspaces",
    "outputs/provider-worker-result.json",
    "inputs/tau-scillm-worker-work-order.json",
    "/tmp/",
    "/home/",
    "/mnt/",
    "/workspace",
    "C:\\",
    "D:\\",
)
PRIVATE_MARKERS = (
    "arena/private/",
    "hidden-ground-truth.json",
    "hidden-vulnerability-ledger.json",
    "judge/oracle/",
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
)
MAY_CLAIM = [
    "backend_live_transport_contract_published",
    "sse_endpoint_shape_defined",
    "initial_snapshot_endpoint_shape_defined",
    "event_ordering_semantics_defined",
    "reconnect_semantics_defined",
    "gap_semantics_defined",
    "raw_path_boundary_defined",
]
MUST_NOT_CLAIM = [
    "sse_endpoint_implemented",
    "websocket_endpoint_implemented",
    "live_stream_executed",
    "live_genetic_events_emitted",
    "exploit_success",
    "blue_detection",
    "blue_kill",
    "blue_block",
    "judge_success_without_judge_receipt",
    "packet_level_behavior",
    "memory_promotion",
]


def publish_live_transport_contract(
    *,
    out_dir: Path,
    public_out_dir: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Write the UX8 backend live transport contract."""

    contract = _contract(generated_at=generated_at)
    report = validate_live_transport_contract(contract)
    out_dir.mkdir(parents=True, exist_ok=True)
    contract_path = out_dir / "battle.live_transport_contract.json"
    validation_path = out_dir / "validation.json"
    _write_json(contract_path, contract)
    _write_json(validation_path, report)
    if public_out_dir is not None:
        public_out_dir.mkdir(parents=True, exist_ok=True)
        public_contract = public_out_dir / "battle.live_transport_contract.json"
        shutil.copyfile(contract_path, public_contract)
        if _sha256_file(public_contract) != _sha256_file(contract_path):
            raise RuntimeError("public live transport contract hash mismatch after copy")
    return contract


def validate_live_transport_contract_path(path: Path) -> dict[str, Any]:
    return validate_live_transport_contract(_read_json(path))


def validate_live_transport_contract(contract: dict[str, Any]) -> dict[str, Any]:
    schema = _read_json(SCHEMA_PATH)
    jsonschema.validate(contract, schema)
    errors: list[str] = []
    if contract.get("schema") != LIVE_TRANSPORT_CONTRACT_SCHEMA:
        errors.append("schema must be battle.live_transport_contract.v1")
    if contract.get("status") != "CONTRACT_PUBLISHED":
        errors.append("status must be CONTRACT_PUBLISHED")
    if contract.get("mocked") is not False:
        errors.append("mocked must be false")
    if contract.get("live") != "contract_only":
        errors.append("live must be contract_only until a real SSE endpoint exists")
    transport = contract.get("transport") if isinstance(contract.get("transport"), dict) else {}
    if transport.get("kind") != "sse":
        errors.append("transport.kind must be sse")
    if transport.get("endpoint") != SSE_ENDPOINT:
        errors.append("transport.endpoint must match the documented SSE endpoint")
    snapshot = contract.get("initial_snapshot") if isinstance(contract.get("initial_snapshot"), dict) else {}
    if snapshot.get("endpoint") != SNAPSHOT_ENDPOINT:
        errors.append("initial_snapshot.endpoint must match the documented snapshot endpoint")
    event_stream = contract.get("event_stream") if isinstance(contract.get("event_stream"), dict) else {}
    if event_stream.get("ordered_by") != "seq":
        errors.append("event_stream.ordered_by must be seq")
    if set(event_stream.get("genetic_event_types_when_live", [])) != set(GENETIC_EVENT_TYPES):
        errors.append("event_stream.genetic_event_types_when_live must include the UX7 genetic vocabulary")
    reconnect = contract.get("reconnect") if isinstance(contract.get("reconnect"), dict) else {}
    if reconnect.get("last_event_id_header") != "Last-Event-ID":
        errors.append("reconnect must use Last-Event-ID")
    gap = contract.get("gap_semantics") if isinstance(contract.get("gap_semantics"), dict) else {}
    if gap.get("gap_response") != "fail_closed_and_refetch_snapshot":
        errors.append("gap_semantics.gap_response must fail closed and refetch snapshot")
    boundary = contract.get("raw_path_boundary") if isinstance(contract.get("raw_path_boundary"), dict) else {}
    frontend_banned = set(boundary.get("frontend_must_not_read", []))
    transport_banned = set(boundary.get("transport_must_not_emit", []))
    for required in ["tau-dag-run/**", "command-loop/command-artifacts/**", "provider workspace directories", "Docker mount paths", "raw stdout/stderr paths", "Judge oracle internals"]:
        if required not in frontend_banned:
            errors.append(f"raw_path_boundary.frontend_must_not_read missing {required}")
        if required not in transport_banned:
            errors.append(f"raw_path_boundary.transport_must_not_emit missing {required}")
    claims = contract.get("claim_boundary") if isinstance(contract.get("claim_boundary"), dict) else {}
    may_claim = set(claims.get("may_claim", []))
    must_not_claim = set(claims.get("must_not_claim", []))
    for item in MAY_CLAIM:
        if item not in may_claim:
            errors.append(f"claim_boundary.may_claim missing {item}")
    for item in MUST_NOT_CLAIM:
        if item not in must_not_claim:
            errors.append(f"claim_boundary.must_not_claim missing {item}")
    forbidden_may = {"sse_endpoint_implemented", "live_stream_executed", "exploit_success", "judge_success_without_judge_receipt"}
    if forbidden_may & may_claim:
        errors.append("claim_boundary.may_claim contains forbidden live/outcome claims")
    handoff = contract.get("frontend_handoff") if isinstance(contract.get("frontend_handoff"), dict) else {}
    if handoff.get("route") != FRONTEND_ROUTE:
        errors.append("frontend_handoff.route must match the UX8 live route")
    leak_scan_payload = json.loads(json.dumps(contract))
    if isinstance(leak_scan_payload, dict):
        leak_scan_payload["raw_path_boundary"] = {}
    serialized = json.dumps(leak_scan_payload, sort_keys=True)
    for marker in [*PATH_LEAK_MARKERS, *PRIVATE_MARKERS]:
        if marker in serialized:
            errors.append(f"live transport contract exposes forbidden marker: {marker}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(serialized):
            errors.append("live transport contract exposes secret-like material")
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "schema": "battle.live_transport_contract_validation.v1",
        "status": "PASS",
        "battle_id": contract["battle_id"],
        "run_id": contract["run_id"],
        "transport": transport.get("kind"),
        "snapshot_endpoint": snapshot.get("endpoint"),
        "sse_endpoint": transport.get("endpoint"),
        "genetic_event_type_count": len(event_stream.get("genetic_event_types_when_live", [])),
        "live": contract.get("live"),
        "mocked": contract.get("mocked"),
        "raw_paths_forbidden": True,
    }


def _contract(*, generated_at: str | None) -> dict[str, Any]:
    return {
        "schema": LIVE_TRANSPORT_CONTRACT_SCHEMA,
        "battle_id": "battle-004",
        "run_id": FIXTURE_ID,
        "generated_at": generated_at or _utc_stamp(),
        "status": "CONTRACT_PUBLISHED",
        "mocked": False,
        "live": "contract_only",
        "authority": "backend_receipts_to_normalized_snapshot_and_events_to_renderer",
        "transport": {
            "kind": "sse",
            "method": "GET",
            "endpoint": SSE_ENDPOINT,
            "content_type": "text/event-stream",
            "event_schema": "battle.live_event.v1",
            "line_format": {
                "id": "seq",
                "event": "battle.live_event",
                "data": "battle.live_event.v1 JSON",
            },
        },
        "initial_snapshot": {
            "method": "GET",
            "endpoint": SNAPSHOT_ENDPOINT,
            "schema": "battle.snapshot.v1",
            "purpose": "Initial state before consuming ordered SSE events.",
        },
        "event_stream": {
            "schema": "battle.live_event.v1",
            "ordered_by": "seq",
            "id_field": "event_id",
            "seq_field": "seq",
            "receipt_ref_field": "payload.receipt_id",
            "immutable_receipt_refs_required": True,
            "normalized_event_only": True,
            "genetic_event_types_when_live": GENETIC_EVENT_TYPES,
            "terminal_outcome_rules": {
                "judge_exploit_success": "emit only with Judge exploit-success receipt",
                "blue_block": "emit only with Blue/Judge receipt",
                "genome_promoted": "emit only with memory/promotion receipt",
            },
        },
        "reconnect": {
            "last_event_id_header": "Last-Event-ID",
            "resume_from": "next_seq_after_last_acknowledged",
            "duplicate_policy": "client_deduplicates_by_seq_and_event_id",
            "server_may_send_snapshot_required": True,
        },
        "gap_semantics": {
            "gap_detection": "non_contiguous_seq",
            "gap_response": "fail_closed_and_refetch_snapshot",
            "snapshot_resync_required": True,
            "client_must_not_interpolate_missing_events": True,
        },
        "raw_path_boundary": {
            "frontend_must_not_read": [
                "tau-dag-run/**",
                "command-loop/command-artifacts/**",
                "provider workspace directories",
                "Docker mount paths",
                "raw stdout/stderr paths",
                "Judge oracle internals",
            ],
            "transport_must_not_emit": [
                "tau-dag-run/**",
                "command-loop/command-artifacts/**",
                "provider workspace directories",
                "Docker mount paths",
                "raw stdout/stderr paths",
                "Judge oracle internals",
            ],
        },
        "claim_boundary": {
            "may_claim": list(MAY_CLAIM),
            "must_not_claim": list(MUST_NOT_CLAIM),
            "live_contract_is_not_endpoint_execution": True,
            "target_contact_is_not_exploit_success": True,
            "compile_passed_is_not_runnable": True,
        },
        "frontend_handoff": {
            "route": FRONTEND_ROUTE,
            "snapshot_endpoint": SNAPSHOT_ENDPOINT,
            "sse_endpoint": SSE_ENDPOINT,
            "stop_condition": "frontend can implement SSE client against this contract without reading raw backend runtime paths",
        },
        "source_contracts": {
            "file_backed_manifest_schema": "battle.transport_manifest.v1",
            "snapshot_schema": "battle.snapshot.v1",
            "event_schema": "battle.live_event.v1",
            "genetic_lifecycle_schema": "battle.genetic_lifecycle_events.v1",
        },
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
