"""Normalize genetic lifecycle receipts into a Pixi replay fixture."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ux_contract_validator import validate_fixture, validate_fixture_schema


NORMALIZED_UX_SCHEMA = "battle.normalized_ux_fixture.v1"
GENETIC_LIFECYCLE_SCHEMA = "battle.genetic_lifecycle_events.v1"
FIXTURE_ID = "battle-004-pr6-genetic-pixi"
FIXTURE_ROUTE = "#battle/receipt?engine=pixi&fixture=battle-004-pr6-genetic-pixi"
PUBLIC_FIXTURE_URL = "/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"
BASE_FIXTURE = "local/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json"
SYNTHESIS_FIXTURE = "local/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json"
COMPILE_FIXTURE = "local/battle-004-pr3d-compile/battle.normalized_compile_fixture.json"
RUNTIME_JUDGE_FIXTURE = "local/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json"
POPULATION_FIXTURE = "local/battle-004-pr5-population/battle.normalized_population_fixture.json"

PATH_LEAK_MARKERS = (
    "tau-dag-run/",
    "command-loop/",
    "command-artifacts/",
    "/home/",
    "/tmp/",
    "/mnt/",
    "/workspace",
    "provider-workspace",
    "pr3c-provider-workspaces",
    "outputs/provider-worker-result.json",
    "inputs/tau-scillm-worker-work-order.json",
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
REQUIRED_EVENT_TYPES = [
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
MUST_NOT_CLAIM = [
    "research_completed_is_exploit_success",
    "genome_selected_is_exploit_success",
    "code_generated_is_exploit_success",
    "compile_passed_is_runnable",
    "compile_passed_is_exploit_success",
    "target_contact_is_exploit_success",
    "runnable_is_exploit_success",
    "blue_detection",
    "blue_bypass",
    "blue_kill",
    "blue_block",
    "judge_success_without_judge_receipt",
    "packet_level_behavior",
    "memory_promotion",
]


def normalize_genetic_pixi_fixture(
    *,
    source_dir: Path,
    out_dir: Path,
    public_out_dir: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Write a PR6/UX7 genetic lifecycle replay fixture from normalized backend fixtures."""

    root = source_dir.resolve()
    sources = _load_sources(root)
    fixture = _fixture(root=root, sources=sources, generated_at=generated_at)
    report = validate_normalized_genetic_pixi_fixture(fixture)
    source_index = _source_index(root=root, sources=sources)

    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = out_dir / "battle.normalized_ux_fixture.json"
    validation_path = out_dir / "validation.json"
    source_index_path = out_dir / "source-receipt-index.json"
    _write_json(fixture_path, fixture)
    _write_json(validation_path, report)
    _write_json(source_index_path, source_index)
    if public_out_dir is not None:
        public_out_dir.mkdir(parents=True, exist_ok=True)
        public_fixture = public_out_dir / "battle.normalized_ux_fixture.json"
        shutil.copyfile(fixture_path, public_fixture)
        if _sha256_file(public_fixture) != _sha256_file(fixture_path):
            raise RuntimeError("public genetic Pixi fixture hash mismatch after copy")
    return fixture


def validate_normalized_genetic_pixi_fixture_path(path: Path) -> dict[str, Any]:
    return validate_normalized_genetic_pixi_fixture(_read_json(path))


def validate_normalized_genetic_pixi_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    validate_fixture_schema(fixture)
    validate_fixture(fixture)
    errors: list[str] = []
    if fixture.get("schema") != NORMALIZED_UX_SCHEMA:
        errors.append("schema must be battle.normalized_ux_fixture.v1")
    genetic = fixture.get("genetic_lifecycle") if isinstance(fixture.get("genetic_lifecycle"), dict) else {}
    if genetic.get("schema") != GENETIC_LIFECYCLE_SCHEMA:
        errors.append("genetic_lifecycle.schema must be battle.genetic_lifecycle_events.v1")
    if genetic.get("route") != FIXTURE_ROUTE:
        errors.append("genetic_lifecycle.route must point to the UX7 Pixi receipt route")
    if genetic.get("fixture_url") != PUBLIC_FIXTURE_URL:
        errors.append("genetic_lifecycle.fixture_url must point to the published public fixture")
    if genetic.get("evidence_mode") != "composite_demonstration_fixture":
        errors.append("genetic_lifecycle.evidence_mode must disclose composite demonstration provenance")
    if genetic.get("causal_continuity_proven") is not False:
        errors.append("genetic_lifecycle.causal_continuity_proven must be false for the PR6 composite")
    if genetic.get("source_run_count") != 4:
        errors.append("genetic_lifecycle.source_run_count must disclose all four source fixtures")
    if genetic.get("timeline_source") != "synthetic_presentation_order":
        errors.append("genetic_lifecycle.timeline_source must disclose synthetic presentation timing")
    present = set(genetic.get("present_event_types", []))
    not_emitted = set(genetic.get("not_emitted_event_types", []))
    if present | not_emitted != set(REQUIRED_EVENT_TYPES):
        errors.append("present_event_types plus not_emitted_event_types must cover required UX7 event vocabulary")
    for forbidden in {"judge_exploit_success", "genome_promoted"}:
        if forbidden in present:
            errors.append(f"{forbidden} must remain NOT_EMITTED without Judge/promotion receipts")
    events = fixture.get("events") if isinstance(fixture.get("events"), list) else []
    genetic_events = [event for event in events if event.get("event_type") in REQUIRED_EVENT_TYPES]
    if not genetic_events:
        errors.append("genetic Pixi fixture must include receipt-backed genetic events")
    event_types = {event.get("event_type") for event in genetic_events}
    if event_types != present:
        errors.append("genetic_lifecycle.present_event_types must match genetic events in events[]")
    orders = [event.get("order_index") for event in genetic_events]
    if orders != sorted(orders):
        errors.append("genetic events must be ordered by order_index")
    for event in genetic_events:
        event_type = event.get("event_type")
        if not isinstance(event.get("elapsed_seconds"), (int, float)):
            errors.append(f"{event_type}: elapsed_seconds is required")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        evidence = event.get("evidence") if isinstance(event.get("evidence"), dict) else {}
        presentation = event.get("presentation") if isinstance(event.get("presentation"), dict) else {}
        if not payload.get("lane_id"):
            errors.append(f"{event_type}: payload.lane_id is required")
        if event_type not in {"research_started", "research_receipt_materialized", "genome_selected", "method_added", "method_rejected", "code_author_started", "judge_pending"} and not payload.get("specimen_id"):
            errors.append(f"{event_type}: payload.specimen_id is required")
        if not evidence.get("receipt_id") or not evidence.get("receipt_path"):
            errors.append(f"{event_type}: evidence receipt_id and receipt_path are required")
        if presentation.get("victory_allowed") is not False:
            errors.append(f"{event_type}: victory_allowed must be false")
        if presentation.get("kill_allowed") is not False:
            errors.append(f"{event_type}: kill_allowed must be false")
        if presentation.get("containment_allowed") is not False:
            errors.append(f"{event_type}: containment_allowed must be false")
        claim_boundary = event.get("claim_boundary") if isinstance(event.get("claim_boundary"), dict) else {}
        if event_type == "compile_passed" and claim_boundary.get("compile_passed_is_not_runnable") is not True:
            errors.append("compile_passed event must explicitly state compile_passed_is_not_runnable")
        if event_type == "target_contact_unproven" and claim_boundary.get("target_contact_is_not_exploit_success") is not True:
            errors.append("target_contact_unproven event must explicitly state target_contact_is_not_exploit_success")
        if event_type == "judge_pending" and payload.get("judge_verified_exploits") != 0:
            errors.append("judge_pending event must keep judge_verified_exploits at 0")
    claims = genetic.get("claim_boundary") if isinstance(genetic.get("claim_boundary"), dict) else {}
    must_not_claim = set(claims.get("must_not_claim", []))
    for item in MUST_NOT_CLAIM:
        if item not in must_not_claim:
            errors.append(f"genetic_lifecycle.claim_boundary.must_not_claim missing {item}")
    serialized = json.dumps(fixture, sort_keys=True)
    for marker in [*PATH_LEAK_MARKERS, *PRIVATE_MARKERS]:
        if marker in serialized:
            errors.append(f"normalized genetic Pixi fixture exposes forbidden marker: {marker}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(serialized):
            errors.append("normalized genetic Pixi fixture exposes secret-like material")
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "schema": "battle.normalized_genetic_pixi_fixture_validation.v1",
        "status": "PASS",
        "battle_id": fixture["battle_id"],
        "fixture_id": FIXTURE_ID,
        "genetic_event_count": len(genetic_events),
        "present_event_types": sorted(present),
        "not_emitted_event_types": sorted(not_emitted),
        "raw_paths_redacted": genetic.get("provenance", {}).get("raw_paths_redacted"),
    }


def _fixture(*, root: Path, sources: dict[str, dict[str, Any]], generated_at: str | None) -> dict[str, Any]:
    base = _sanitize(copy.deepcopy(sources["base"]))
    events = [event for event in base.get("events", []) if isinstance(event, dict)]
    next_order = max([int(event.get("order_index", index)) for index, event in enumerate(events)] or [0]) + 1
    genetic_events = _genetic_events(sources=sources, start_order=next_order)
    all_events = sorted([*events, *genetic_events], key=lambda event: (_number(event.get("elapsed_seconds")), int(event.get("order_index", 0))))
    for index, event in enumerate(all_events):
        event["order_index"] = index

    fixture = base
    fixture["generated_at"] = generated_at or _utc_stamp()
    fixture["source_proof_dir"] = f"local/{FIXTURE_ID}"
    fixture["events"] = all_events
    fixture["timeline"] = _timeline(base.get("timeline", {}), all_events)
    fixture["receipts"] = _receipts(base.get("receipts", []))
    fixture["claims"] = _claims(base.get("claims", {}))
    fixture["ux_contract"] = _ux_contract(base.get("ux_contract", {}), fixture=fixture)
    fixture["genetic_lifecycle"] = _genetic_lifecycle_contract(events=genetic_events, sources=sources)
    fixture["spectator_shell"] = _spectator_shell(base.get("spectator_shell", {}), event_count=len(all_events))
    fixture["scoreboard"] = _scoreboard(base.get("scoreboard", {}), sources=sources)
    fixture["proof_blockers"] = list(base.get("proof_blockers", []))
    return _sanitize(fixture)


def _genetic_events(*, sources: dict[str, dict[str, Any]], start_order: int) -> list[dict[str, Any]]:
    synthesis = sources["synthesis"]
    compile_fixture = sources["compile"]
    runtime = sources["runtime_judge"]
    population = sources["population"]
    cards = population.get("specimen_cards", [])
    selected_card = _find_card(cards, "specimen-0004") or (cards[-1] if cards else {})
    failed_card = _find_card(cards, "specimen-0001") or (cards[0] if cards else {})
    target_run = _find_runtime_run(runtime, "specimen-0004") or {}
    selected_methods = synthesis.get("genome", {}).get("selected_method_ids", [])
    deferred_methods = synthesis.get("genome", {}).get("deferred_method_ids", [])
    code_specimen_id = compile_fixture.get("provider_authorship", {}).get("specimen_id") or "payload-857-child-dag-001-provider-specimen-0001"
    lane_id = "payload-857-red-1"
    receipt_refs = {
        "synthesis": "local/battle-004-pr3c-synthesis/battle.normalized_synthesis_fixture.json",
        "compile": "local/battle-004-pr3d-compile/battle.normalized_compile_fixture.json",
        "runtime_judge": "local/battle-004-pr4-runtime-judge/battle.normalized_runtime_judge_fixture.json",
        "population": "local/battle-004-pr5-population/battle.normalized_population_fixture.json",
    }
    event_specs = [
        ("research_started", 86.0, lane_id, None, None, "Research node started", "research_scan", "synthesis", {"research_method": synthesis.get("research", {}).get("method"), "provider_live": synthesis.get("research", {}).get("provider_live")}),
        ("research_receipt_materialized", 88.5, lane_id, None, None, "Source-bearing research receipts materialized", "research_receipt", "synthesis", {"source_count": synthesis.get("research", {}).get("source_count")}),
        ("genome_selected", 91.0, lane_id, None, selected_methods[0] if selected_methods else None, "Exploit genome selected", "genome_lock", "synthesis", {"selected_method_ids": selected_methods, "deferred_method_ids": deferred_methods}),
        ("method_added", 93.0, lane_id, None, selected_methods[-1] if selected_methods else None, "Method added to genome", "gene_shard_join", "synthesis", {"method_id": selected_methods[-1] if selected_methods else None}),
        ("method_rejected", 94.5, lane_id, None, deferred_methods[0] if deferred_methods else None, "Method rejected/deferred by genome filter", "gene_shard_fade", "synthesis", {"method_id": deferred_methods[0] if deferred_methods else None}),
        ("code_author_started", 97.0, lane_id, code_specimen_id, None, "Provider code-author node started", "code_authoring", "synthesis", {"provider_live": synthesis.get("provider_authorship", {}).get("provider_live")}),
        ("specimen_materialized", 102.0, lane_id, code_specimen_id, None, "Provider-authored specimen materialized", "code_glyph", "synthesis", {"code_sha256": synthesis.get("provider_authorship", {}).get("code_sha256"), "authored_by": synthesis.get("provider_authorship", {}).get("authored_by")}),
        ("compile_failed", 108.0, lane_id, code_specimen_id, None, "Compile attempt failed and stderr was summarized", "compile_error", "compile", {"compile_status": compile_fixture.get("compile", {}).get("status"), "stderr_summary": compile_fixture.get("compile", {}).get("stderr_summary")}),
        ("target_contact_unproven", 116.0, "payload-857-receipt", selected_card.get("specimen_id"), None, "Specimen contacted target surface without exploit proof", "endpoint_pulse", "runtime_judge", {"runtime_status": selected_card.get("runtime_status"), "target_contact": target_run.get("target_contact") or selected_card.get("target_contact")}),
        ("judge_pending", 121.0, "payload-857-receipt", selected_card.get("specimen_id"), None, "Judge success event is not emitted; Judge remains not run", "judge_pending", "runtime_judge", {"judge_status": runtime.get("judge", {}).get("judge_status"), "judge_verified_exploits": runtime.get("judge", {}).get("judge_verified_exploits", 0)}),
        ("branch_abandoned", 126.0, "payload-857-receipt", failed_card.get("specimen_id"), None, "Failed branch retained as negative evidence", "branch_fade", "population", {"selection": failed_card.get("selection"), "does_not_prove": ["Tau chose abandon_branch without a branch decision receipt"]}),
    ]
    events = []
    for index, (event_type, elapsed, event_lane_id, specimen_id, method_id, summary, effect, source_key, payload) in enumerate(event_specs, start=start_order):
        events.append(
            _event(
                event_type=event_type,
                order_index=index,
                elapsed_seconds=elapsed,
                lane_id=event_lane_id,
                specimen_id=specimen_id,
                method_id=method_id,
                summary=summary,
                pixi_effect=effect,
                source_key=source_key,
                receipt_path=receipt_refs[source_key],
                payload=payload,
            )
        )
    repair = compile_fixture.get("repair", {})
    if repair.get("repair_attempted") is True:
        events.extend(
            [
                _event(
                    event_type="repair_started",
                    order_index=start_order + len(events),
                    elapsed_seconds=111.0,
                    lane_id=lane_id,
                    specimen_id=code_specimen_id,
                    method_id=None,
                    summary="Repair attempt started",
                    pixi_effect="repair_pulse",
                    source_key="compile",
                    receipt_path=receipt_refs["compile"],
                    payload={"repair": repair},
                ),
                _event(
                    event_type="repair_materialized",
                    order_index=start_order + len(events) + 1,
                    elapsed_seconds=113.0,
                    lane_id=lane_id,
                    specimen_id=code_specimen_id,
                    method_id=None,
                    summary="Repair materialized",
                    pixi_effect="repair_glyph",
                    source_key="compile",
                    receipt_path=receipt_refs["compile"],
                    payload={"repair": repair},
                ),
            ]
        )
    if compile_fixture.get("compile", {}).get("compile_passed") is True or selected_card.get("compile_status") == "COMPILE_PASSED":
        events.append(
            _event(
                event_type="compile_passed",
                order_index=start_order + len(events),
                elapsed_seconds=114.0,
                lane_id="payload-857-receipt",
                specimen_id=selected_card.get("specimen_id"),
                method_id=None,
                summary="Later specimen compile status passed; not runtime proof",
                pixi_effect="compile_lock",
                source_key="population",
                receipt_path=receipt_refs["population"],
                payload={"compile_status": selected_card.get("compile_status"), "runtime_status": selected_card.get("runtime_status")},
            )
        )
    return sorted(events, key=lambda event: (float(event["elapsed_seconds"]), int(event["order_index"])))


def _event(
    *,
    event_type: str,
    order_index: int,
    elapsed_seconds: float,
    lane_id: str,
    specimen_id: str | None,
    method_id: str | None,
    summary: str,
    pixi_effect: str,
    source_key: str,
    receipt_path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    playhead_x = min(98, round(8 + elapsed_seconds * 0.7, 2))
    claim_boundary = {
        "victory_requires_judge_receipt": True,
        "compile_passed_is_not_runnable": event_type == "compile_passed" or None,
        "target_contact_is_not_exploit_success": event_type == "target_contact_unproven" or None,
        "does_not_prove": [
            "exploit success",
            "Blue kill",
            "Blue block",
            "packet-level behavior",
            "memory promotion",
        ],
    }
    return {
        "id": f"{FIXTURE_ID}:{event_type}:{order_index}",
        "ts": elapsed_seconds,
        "battle_id": "battle-004",
        "team": "red",
        "actor_id": lane_id,
        "actor_kind": "red_lane",
        "event_type": event_type,
        "summary": summary,
        "proof_mode": "receipt_backed_fixture",
        "order_index": order_index,
        "elapsed_seconds": elapsed_seconds,
        "payload": {
            "lane_id": lane_id,
            "specimen_id": specimen_id,
            "method_id": method_id,
            "receipt_id": f"ux7-{source_key}",
            "playhead_x": playhead_x,
            **payload,
        },
        "evidence": {
            "receipt_id": f"ux7-{source_key}",
            "receipt_path": receipt_path,
            "artifact_ref": receipt_path,
            "proof_mode": "receipt_backed_fixture",
        },
        "presentation": {
            "pixi_effect": pixi_effect,
            "victory_allowed": False,
            "kill_allowed": False,
            "containment_allowed": False,
            "must_not_render_as": ["victory", "kill", "containment", "Judge success"],
        },
        "claim_boundary": {k: v for k, v in claim_boundary.items() if v is not None},
    }


def _genetic_lifecycle_contract(*, events: list[dict[str, Any]], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    present = [event["event_type"] for event in events]
    not_emitted = [event_type for event_type in REQUIRED_EVENT_TYPES if event_type not in present]
    return {
        "schema": GENETIC_LIFECYCLE_SCHEMA,
        "fixture_id": FIXTURE_ID,
        "evidence_mode": "composite_demonstration_fixture",
        "causal_continuity_proven": False,
        "source_run_count": 4,
        "timeline_source": "synthetic_presentation_order",
        "route": FIXTURE_ROUTE,
        "fixture_url": PUBLIC_FIXTURE_URL,
        "required_event_types": REQUIRED_EVENT_TYPES,
        "present_event_types": present,
        "not_emitted_event_types": not_emitted,
        "not_emitted_reasons": {
            "repair_started": "PR3d source fixture had repair_attempted=false" if "repair_started" in not_emitted else None,
            "repair_materialized": "PR3d source fixture had repair_attempted=false" if "repair_materialized" in not_emitted else None,
            "judge_exploit_success": "missing Judge exploit-success receipt",
            "genome_promoted": "missing memory/promotion receipt",
        },
        "event_payload_field_map": {
            "lane_id": "payload.lane_id",
            "specimen_id": "payload.specimen_id",
            "method_id": "payload.method_id",
            "receipt_id": "payload.receipt_id and evidence.receipt_id",
            "elapsed_seconds": "elapsed_seconds",
            "playhead_x": "payload.playhead_x",
            "claim_boundary": "claim_boundary",
        },
        "claim_boundary": {
            "may_claim": [
                "research_started",
                "research_receipt_materialized",
                "genome_selected",
                "method_added",
                "method_rejected",
                "code_author_started",
                "specimen_materialized",
                "compile_failed",
                "compile_passed",
                "target_contact_unproven",
                "judge_pending_as_not_run",
                "branch_negative_evidence_retained",
            ],
            "must_not_claim": MUST_NOT_CLAIM,
            "victory_requires_judge_receipt": True,
            "target_contact_is_not_exploit_success": True,
            "compile_passed_is_not_runnable": True,
        },
        "source_fixtures": {
            "synthesis": SYNTHESIS_FIXTURE,
            "compile": COMPILE_FIXTURE,
            "runtime_judge": RUNTIME_JUDGE_FIXTURE,
            "population": POPULATION_FIXTURE,
        },
        "provenance": {
            "raw_paths_redacted": True,
            "tau_runtime_paths_exposed": False,
            "command_loop_paths_exposed": False,
            "provider_workspace_paths_exposed": False,
            "docker_raw_paths_exposed": False,
            "source_fixture_hashes": {
                name: _sha256_json(data)
                for name, data in sources.items()
                if name != "base"
            },
        },
    }


def _timeline(base: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    timeline = copy.deepcopy(base) if isinstance(base, dict) else {}
    timeline["event_count"] = len(events)
    timeline["lane_count"] = max(int(timeline.get("lane_count") or 2), 2)
    timeline["max_x"] = max(float(timeline.get("max_x") or 100), 110)
    return timeline


def _ux_contract(base: dict[str, Any], *, fixture: dict[str, Any]) -> dict[str, Any]:
    ux = copy.deepcopy(base) if isinstance(base, dict) else {}
    values = ux.setdefault("receipt_backed_values", {})
    values["event_count"] = len(fixture.get("events", []))
    values["lane_count"] = len(fixture.get("lanes", []))
    values["playhead_current_x"] = fixture.get("timeline", {}).get("playhead", {}).get("current_x")
    guards = ux.setdefault("required_render_guards", [])
    for guard in [
        "Render genetic lifecycle effects only from genetic_lifecycle.present_event_types and matching receipt-backed events.",
        "Do not render victory, kill, or containment for research, genome selection, code materialization, compile pass, or target contact.",
        "Do not render judge_exploit_success unless the event exists and carries a Judge exploit-success receipt.",
        "Do not read Tau command-loop, provider workspace, Docker raw paths, or raw stderr paths from the frontend.",
    ]:
        if guard not in guards:
            guards.append(guard)
    authoritative = ux.setdefault("authoritative_fields", {})
    authoritative["genetic_lifecycle"] = "UX7 genetic Pixi event vocabulary, present/not-emitted event list, field map, and claim boundary."
    return ux


def _claims(base: dict[str, Any]) -> dict[str, Any]:
    claims = copy.deepcopy(base) if isinstance(base, dict) else {}
    proves = claims.setdefault("proves", [])
    for item in [
        "Battle published a normalized genetic lifecycle Pixi replay fixture.",
        "The fixture exposes receipt-backed genetic events without raw Tau/provider/Docker paths.",
    ]:
        if item not in proves:
            proves.append(item)
    does_not_prove = claims.setdefault("does_not_prove", [])
    for item in [
        "Research completion proves exploit success.",
        "Genome selection proves exploit success.",
        "Code materialization proves exploit success.",
        "Compile pass proves runtime success.",
        "Target contact proves exploit success.",
        "Judge exploit success, Blue block, packet behavior, or memory promotion.",
    ]:
        if item not in does_not_prove:
            does_not_prove.append(item)
    return claims


def _receipts(base: list[Any]) -> list[dict[str, Any]]:
    receipts = [item for item in copy.deepcopy(base) if isinstance(item, dict)]
    receipts.extend(
        [
            _receipt("ux7-synthesis", SYNTHESIS_FIXTURE, "normalized_synthesis_fixture", "PR3c synthesis/code-author fixture."),
            _receipt("ux7-compile", COMPILE_FIXTURE, "normalized_compile_fixture", "PR3d compile fixture."),
            _receipt("ux7-runtime_judge", RUNTIME_JUDGE_FIXTURE, "normalized_runtime_judge_fixture", "PR4 runtime/Judge fixture."),
            _receipt("ux7-population", POPULATION_FIXTURE, "normalized_population_fixture", "PR5 population fixture."),
        ]
    )
    return receipts


def _receipt(receipt_id: str, path: str, receipt_type: str, summary: str) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "receipt_type": receipt_type,
        "receipt_path": path,
        "artifact_ref": path,
        "proof_mode": "receipt_backed_fixture",
        "summary": summary,
    }


def _scoreboard(base: dict[str, Any], *, sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    scoreboard = copy.deepcopy(base) if isinstance(base, dict) else {}
    scoreboard["genetic_lifecycle_event_count"] = len(sources.get("population", {}).get("specimen_cards", []))
    scoreboard["judge_verified_exploits"] = 0
    scoreboard["target_contact_is_not_exploit_success"] = True
    scoreboard["compile_passed_is_not_runnable"] = True
    return scoreboard


def _spectator_shell(base: dict[str, Any], *, event_count: int) -> dict[str, Any]:
    shell = copy.deepcopy(base) if isinstance(base, dict) else {}
    shell["fixture_label"] = "BATTLE-004 Genetic Pixi Replay"
    shell["route"] = FIXTURE_ROUTE
    ticker = shell.get("event_ticker") if isinstance(shell.get("event_ticker"), dict) else {}
    ticker["count"] = event_count
    ticker["latest_text"] = "GENETIC LIFECYCLE EVENTS · receipt-backed"
    shell["event_ticker"] = ticker
    return shell


def _source_index(*, root: Path, sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "battle.normalized_genetic_pixi_source_index.v1",
        "fixture_id": FIXTURE_ID,
        "source_root": "skills/battle",
        "source_fixtures": {
            "base": BASE_FIXTURE,
            "synthesis": SYNTHESIS_FIXTURE,
            "compile": COMPILE_FIXTURE,
            "runtime_judge": RUNTIME_JUDGE_FIXTURE,
            "population": POPULATION_FIXTURE,
        },
        "source_fixture_hashes": {name: _sha256_json(data) for name, data in sources.items()},
        "raw_paths_redacted": True,
    }


def _load_sources(root: Path) -> dict[str, dict[str, Any]]:
    paths = {
        "base": BASE_FIXTURE,
        "synthesis": SYNTHESIS_FIXTURE,
        "compile": COMPILE_FIXTURE,
        "runtime_judge": RUNTIME_JUDGE_FIXTURE,
        "population": POPULATION_FIXTURE,
    }
    sources: dict[str, dict[str, Any]] = {}
    for name, relative in paths.items():
        path = root / relative
        if not path.exists():
            raise FileNotFoundError(f"missing UX7 source fixture {name}: {path}")
        sources[name] = _read_json(path)
    return sources


def _find_card(cards: list[Any], specimen_id: str) -> dict[str, Any] | None:
    for card in cards:
        if isinstance(card, dict) and card.get("specimen_id") == specimen_id:
            return card
    return None


def _find_runtime_run(runtime_fixture: dict[str, Any], specimen_id: str) -> dict[str, Any] | None:
    for run in runtime_fixture.get("runtime", {}).get("specimen_runs", []):
        if isinstance(run, dict) and run.get("specimen_id") == specimen_id:
            return run
    return None


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        sanitized = value
        for marker in PATH_LEAK_MARKERS:
            if marker in sanitized:
                sanitized = "[redacted-path]"
                break
        return sanitized
    return value


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
