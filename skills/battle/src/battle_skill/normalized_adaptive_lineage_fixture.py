"""Project one adaptive campaign journal into a public-safe UX fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import validate  # type: ignore[import-untyped]

FORBIDDEN_PATH_MARKERS = (
    "/tmp/",
    "/home/",
    "/mnt/",
    "tau-live",
    "tau-dag-run/",
    "command-loop/",
    "command-artifacts/",
    "provider-workspace",
    "reviewed/",
    "arena/private",
    "/judge/",
    "scillm",
)
TEAMS = ("red", "blue")
V13_PROJECTION = "adaptive_lineage_v13"
V14_MEMORY_PROJECTION = "adaptive_memory_v14"


def _lane_id(team: str, generation: int) -> str:
    return f"{team}-g{generation}"


def _find_event(
    events: list[dict[str, Any]], *, event_type: str, team: str | None
) -> dict[str, Any]:
    matches = [
        event
        for event in events
        if event.get("event_type") == event_type and event.get("team") == team
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one {event_type} event for {team or 'campaign'}")
    return matches[0]


def _v13_public_lanes(
    events: list[dict[str, Any]], elapsed_end: float
) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for team in TEAMS:
        authorized = _find_event(events, event_type="spawn_authorized", team=team)
        research = _find_event(
            events, event_type="child_research_materialized", team=team
        )
        for generation in (1, 2):
            lane_id = _lane_id(team, generation)
            is_child = generation == 2
            lanes.append(
                {
                    "lane_id": lane_id,
                    "team": team,
                    "generation": generation,
                    "role": "child" if is_child else "parent",
                    "parent_lane_id": _lane_id(team, 1) if is_child else None,
                    "display_name": (
                        f"{team.upper()} G{generation} "
                        f"{'CHILD' if is_child else 'PARENT'}"
                    ),
                    "visible_from_elapsed_seconds": (
                        authorized["timing"]["elapsed_seconds"] if is_child else 0.0
                    ),
                    "active_from_elapsed_seconds": (
                        research["timing"]["elapsed_seconds"] if is_child else 0.0
                    ),
                    "end_elapsed_seconds": elapsed_end,
                    "actor_visual": {
                        "variant_id": "v13-shared-runner",
                        "cosmetic_only": True,
                        "semantic_authority": False,
                    },
                }
            )
    return lanes


def _v13_lineage_edges(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for team in TEAMS:
        requested = _find_event(events, event_type="spawn_requested", team=team)
        authorized = _find_event(events, event_type="spawn_authorized", team=team)
        edges.append(
            {
                "edge_id": f"{team}-g1-to-g2",
                "edge_kind": "spawn",
                "team": team,
                "parent_lane_id": _lane_id(team, 1),
                "child_lane_id": _lane_id(team, 2),
                "requested_receipt_ref": requested["source_receipt"],
                "authorized_receipt_ref": authorized["source_receipt"],
                "visible_from_elapsed_seconds": authorized["timing"][
                    "elapsed_seconds"
                ],
            }
        )
    return edges


def _memory_generations(index: dict[str, Any]) -> tuple[int, int]:
    lifecycle = index.get("memory_lifecycle")
    if not isinstance(lifecycle, dict):
        raise ValueError("adaptive memory source index lacks memory_lifecycle")
    source_generation = lifecycle.get("source_generation")
    memory_generation = lifecycle.get("memory_generation")
    if not isinstance(source_generation, int) or not isinstance(memory_generation, int):
        raise ValueError("adaptive memory generations must be integers")
    if memory_generation <= source_generation:
        raise ValueError("memory generation must follow source generation")
    return source_generation, memory_generation


def _memory_public_lanes(
    events: list[dict[str, Any]], index: dict[str, Any], elapsed_end: float
) -> list[dict[str, Any]]:
    source_generation, memory_generation = _memory_generations(index)
    lanes: list[dict[str, Any]] = []
    for team in TEAMS:
        promoted = _find_event(events, event_type="memory_promoted", team=team)
        used = _find_event(
            events, event_type="memory_use_acknowledged", team=team
        )
        for generation in (source_generation, memory_generation):
            is_child = generation == memory_generation
            lanes.append(
                {
                    "lane_id": _lane_id(team, generation),
                    "team": team,
                    "generation": generation,
                    "role": "child" if is_child else "parent",
                    "parent_lane_id": (
                        _lane_id(team, source_generation) if is_child else None
                    ),
                    "display_name": (
                        f"{team.upper()} G{generation} "
                        f"{'MEMORY CHILD' if is_child else 'SOURCE'}"
                    ),
                    "visible_from_elapsed_seconds": (
                        promoted["timing"]["elapsed_seconds"] if is_child else 0.0
                    ),
                    "active_from_elapsed_seconds": (
                        used["timing"]["elapsed_seconds"] if is_child else 0.0
                    ),
                    "end_elapsed_seconds": elapsed_end,
                    "actor_visual": {
                        "variant_id": "v13-shared-runner",
                        "cosmetic_only": True,
                        "semantic_authority": False,
                    },
                }
            )
    return lanes


def _memory_lineage_edges(
    events: list[dict[str, Any]], index: dict[str, Any]
) -> list[dict[str, Any]]:
    source_generation, memory_generation = _memory_generations(index)
    edges: list[dict[str, Any]] = []
    for team in TEAMS:
        promoted = _find_event(events, event_type="memory_promoted", team=team)
        written = _find_event(events, event_type="memory_written", team=team)
        recalled = _find_event(events, event_type="memory_recalled", team=team)
        used = _find_event(
            events, event_type="memory_use_acknowledged", team=team
        )
        edges.append(
            {
                "edge_id": f"{team}-g{source_generation}-to-g{memory_generation}",
                "edge_kind": "memory_continuation",
                "team": team,
                "parent_lane_id": _lane_id(team, source_generation),
                "child_lane_id": _lane_id(team, memory_generation),
                "promoted_receipt_ref": promoted["source_receipt"],
                "written_receipt_ref": written["source_receipt"],
                "recalled_receipt_ref": recalled["source_receipt"],
                "use_receipt_ref": used["source_receipt"],
                "visible_from_elapsed_seconds": promoted["timing"][
                    "elapsed_seconds"
                ],
            }
        )
    return edges


def _event_scope(
    event: dict[str, Any], *, lane_ids: set[str]
) -> tuple[str | None, str, list[str]]:
    team = event.get("team")
    generation = event.get("generation")
    if team in TEAMS and isinstance(generation, int):
        lane_id = _lane_id(team, generation)
        if lane_id not in lane_ids:
            raise ValueError(f"event maps to unknown lane {lane_id}")
        return lane_id, "lane", [lane_id]
    if event.get("event_type") in {
        "judge_verdict",
        "memory_generation_evaluated",
    } and isinstance(generation, int):
        affected = [
            _lane_id(team_name, generation)
            for team_name in TEAMS
            if _lane_id(team_name, generation) in lane_ids
        ]
        if len(affected) != len(TEAMS):
            raise ValueError("generation-pair event lacks both team lanes")
        return None, "generation_pair", affected
    return None, "campaign", sorted(lane_ids)


def _public_events(
    events: list[dict[str, Any]], *, lane_ids: set[str]
) -> list[dict[str, Any]]:
    public_events: list[dict[str, Any]] = []
    for event in events:
        lane_id, scope, affected_lane_ids = _event_scope(
            event, lane_ids=lane_ids
        )
        timing = event.get("timing") if isinstance(event.get("timing"), dict) else {}
        public_event = {
            "seq": event["seq"],
            "event_id": event["event_id"],
            "elapsed_seconds": timing["elapsed_seconds"],
            "event_type": event["event_type"],
            "generation": event.get("generation"),
            "team": event.get("team"),
            "lane_id": lane_id,
            "scope": scope,
            "affected_lane_ids": affected_lane_ids,
            "receipt_ref": event["source_receipt"],
            "payload": event.get("payload", {}),
        }
        for key in (
            "source_created_at",
            "source_elapsed_seconds",
            "timing_source",
            "projection_tie_break_applied",
        ):
            if key in timing:
                public_event[key] = timing[key]
        public_events.append(public_event)
    return public_events


def _v13_renderer_contract() -> dict[str, Any]:
    return {
        "schema": "battle.adaptive_lineage_renderer_contract.v1",
        "time_authority": "event.elapsed_seconds_is_receipt_commit_time",
        "event_order_authority": "event.seq",
        "child_visibility_event": "spawn_authorized",
        "child_pending_state": "AUTHORIZED_PENDING",
        "child_activation_event": "child_research_materialized",
        "pair_judge_event_is_global": True,
        "selection_is_not_victory": True,
        "no_promotion_is_not_promoted": True,
        "sprite_identity_is_cosmetic_only": True,
    }


def _memory_renderer_contract() -> dict[str, Any]:
    return {
        "schema": "battle.adaptive_lineage_renderer_contract.v1",
        "time_authority": (
            "event.elapsed_seconds_is_receipt_created_at_projection; "
            "equal timestamps use deterministic tie-break order"
        ),
        "event_order_authority": "event.seq",
        "child_visibility_event": "memory_promoted",
        "child_pending_state": "MEMORY_PENDING",
        "child_activation_event": "memory_use_acknowledged",
        "pair_judge_event_is_global": True,
        "selection_is_not_victory": True,
        "no_promotion_is_not_promoted": True,
        "memory_use_is_not_improvement": True,
        "sprite_identity_is_cosmetic_only": True,
    }


def _sprite_theme(theme_id: str) -> dict[str, Any]:
    return {
        "schema": "battle.sprite_theme.v1",
        "theme_id": theme_id,
        "proof_scope": "cosmetic_identity_only",
        "shared_atlas": True,
        "semantic_authority": False,
        "variants": {
            "v13-shared-runner": {
                "sprite_id": "plague_nurgling",
                "scale": 1.0,
            }
        },
    }


def build_normalized_adaptive_fixture(
    *, campaign_root: Path, source_index_path: Path, fixture_id: str
) -> dict[str, Any]:
    """Build a V13 or V14 public fixture from one explicit journal and index."""
    index = _read_json(source_index_path)
    if index.get("campaign_root_id") != campaign_root.name:
        raise ValueError("source index campaign identity mismatch")
    events = [
        json.loads(line)
        for line in (campaign_root / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    if not events or any(
        event.get("run_id") != index.get("run_id") for event in events
    ):
        raise ValueError("journal is empty or contains cross-run events")
    if [event["seq"] for event in events] != list(range(1, len(events) + 1)):
        raise ValueError("journal sequence is not contiguous")
    elapsed = [event["timing"]["elapsed_seconds"] for event in events]
    if elapsed != sorted(elapsed):
        raise ValueError("journal elapsed time decreases")

    projection_kind = str(index.get("projection_kind") or V13_PROJECTION)
    if projection_kind == V14_MEMORY_PROJECTION:
        source_generation, memory_generation = _memory_generations(index)
        generation_ids = [source_generation, memory_generation]
        lanes = _memory_public_lanes(events, index, elapsed[-1])
        lineage_edges = _memory_lineage_edges(events, index)
        renderer_contract = _memory_renderer_contract()
        live_source = "adaptive_memory_v14"
        theme_id = "v14-shared-plague-nurgling"
        claim_boundary = {
            "may_claim": [
                "team-scoped memory promotion",
                "live memory write and exact recall",
                "provider acknowledgement of recalled memory use",
                "changed memory-informed artifacts",
                "Docker and Judge evaluation of the memory-informed generation",
            ],
            "must_not_claim": [
                "memory improved either team",
                "Judge exploit success unless Judge says RED_SUCCESS",
                "Memory service ACL enforcement",
                "population-scale or production readiness",
            ],
        }
    elif projection_kind == V13_PROJECTION:
        generation_ids = [1, 2]
        lanes = _v13_public_lanes(events, elapsed[-1])
        lineage_edges = _v13_lineage_edges(events)
        renderer_contract = _v13_renderer_contract()
        live_source = "adaptive_red_blue_lineage_v2"
        theme_id = "v13-shared-plague-nurgling"
        claim_boundary = {
            "may_claim": [
                "two receipt-continuous Red/Blue generations",
                "parent-authored spawn requests",
                "semantic genome mutation",
                "deterministic selection",
                "memory-policy evaluation",
            ],
            "must_not_claim": [
                "Judge exploit success unless Judge says RED_SUCCESS",
                "child improvement unless selection proves it",
                "durable memory write or recall",
                "population-scale or production readiness",
            ],
        }
    else:
        raise ValueError(f"unsupported adaptive projection kind: {projection_kind}")

    lane_ids = {str(lane["lane_id"]) for lane in lanes}
    fixture: dict[str, Any] = {
        "schema": "battle.normalized_adaptive_lineage_fixture.v1",
        "fixture_id": fixture_id,
        "battle_id": index["battle_id"],
        "run_id": index["run_id"],
        "proof_mode": "receipt_backed_fixture",
        "live_source": live_source,
        "causal_continuity_proven": True,
        "campaign": {
            "campaign_clock_id": events[0]["campaign_clock_id"],
            "elapsed_seconds": elapsed[-1],
            "generation_count": len(generation_ids),
            "generation_ids": generation_ids,
            "teams": ["red", "blue"],
        },
        "lanes": lanes,
        "lineage_edges": lineage_edges,
        "sprite_theme": _sprite_theme(theme_id),
        "renderer_contract": renderer_contract,
        "events": _public_events(events, lane_ids=lane_ids),
        "receipt_refs": index["public_receipts"],
        "selection": index["selection"],
        "memory_evaluation": index["memory_evaluation"],
        "claim_boundary": claim_boundary,
        "provenance": {
            "raw_paths_redacted": True,
            "source_run_count": int(index.get("source_run_count") or 1),
            "source_proof_id": campaign_root.name,
            "projection_kind": projection_kind,
        },
    }
    if projection_kind == V14_MEMORY_PROJECTION:
        fixture["memory_lifecycle"] = index["memory_lifecycle"]
        fixture["source_campaign"] = index["source_campaign"]

    serialized = json.dumps(fixture, sort_keys=True)
    if any(marker in serialized for marker in FORBIDDEN_PATH_MARKERS):
        raise ValueError("normalized fixture exposes a raw runtime path")
    return fixture


def write_fixture_copies(
    *, fixture: dict[str, Any], local_path: Path, public_path: Path
) -> dict[str, Any]:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "battle.normalized_adaptive_lineage_fixture.v1.schema.json"
    )
    validate(instance=fixture, schema=_read_json(schema_path))
    payload = json.dumps(fixture, indent=2, sort_keys=True) + "\n"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(payload, encoding="utf-8")
    public_path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return {
        "schema": "battle.normalized_adaptive_lineage_validation.v1",
        "status": "PASS",
        "local_public_byte_identical": local_path.read_bytes()
        == public_path.read_bytes(),
        "fixture_sha256": digest,
        "event_count": len(fixture.get("events", [])),
        "lane_count": len(fixture.get("lanes", [])),
        "lineage_edge_count": len(fixture.get("lineage_edges", [])),
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value
