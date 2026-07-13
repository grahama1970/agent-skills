"""Project one adaptive campaign journal into a public-safe UX fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import validate  # type: ignore[import-untyped]

FORBIDDEN_PATH_MARKERS = ("/tmp/", "tau-live", "reviewed/", "arena/private", "scillm")
TEAMS = ("red", "blue")


def _lane_id(team: str, generation: int) -> str:
    return f"{team}-g{generation}"


def _find_event(
    events: list[dict[str, Any]], *, event_type: str, team: str
) -> dict[str, Any]:
    matches = [
        event
        for event in events
        if event.get("event_type") == event_type and event.get("team") == team
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one {event_type} event for {team}")
    return matches[0]


def _public_lanes(events: list[dict[str, Any]], elapsed_end: float) -> list[dict[str, Any]]:
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
                    "display_name": f"{team.upper()} G{generation} {'CHILD' if is_child else 'PARENT'}",
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


def _lineage_edges(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for team in TEAMS:
        requested = _find_event(events, event_type="spawn_requested", team=team)
        authorized = _find_event(events, event_type="spawn_authorized", team=team)
        edges.append(
            {
                "edge_id": f"{team}-g1-to-g2",
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


def _event_scope(event: dict[str, Any]) -> tuple[str | None, str, list[str]]:
    team = event.get("team")
    generation = event.get("generation")
    if team in TEAMS and generation in (1, 2):
        lane_id = _lane_id(team, generation)
        affected = [lane_id]
        if event.get("event_type") == "spawn_authorized" and generation == 1:
            affected.append(_lane_id(team, 2))
        return lane_id, "lane", affected
    if event.get("event_type") == "judge_verdict" and generation in (1, 2):
        return None, "generation_pair", [
            _lane_id(team_name, generation) for team_name in TEAMS
        ]
    return None, "campaign", [
        _lane_id(team_name, generation_number)
        for team_name in TEAMS
        for generation_number in (1, 2)
    ]


def build_normalized_adaptive_fixture(
    *, campaign_root: Path, source_index_path: Path, fixture_id: str
) -> dict[str, Any]:
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
    public_events = []
    for event in events:
        lane_id, scope, affected_lane_ids = _event_scope(event)
        public_events.append(
            {
            "seq": event["seq"],
            "event_id": event["event_id"],
            "elapsed_seconds": event["timing"]["elapsed_seconds"],
            "event_type": event["event_type"],
            "generation": event.get("generation"),
            "team": event.get("team"),
            "lane_id": lane_id,
            "scope": scope,
            "affected_lane_ids": affected_lane_ids,
            "receipt_ref": event["source_receipt"],
            "payload": event.get("payload", {}),
            }
        )
    lanes = _public_lanes(events, elapsed[-1])
    lineage_edges = _lineage_edges(events)
    fixture = {
        "schema": "battle.normalized_adaptive_lineage_fixture.v1",
        "fixture_id": fixture_id,
        "battle_id": index["battle_id"],
        "run_id": index["run_id"],
        "proof_mode": "receipt_backed_fixture",
        "live_source": "adaptive_red_blue_lineage_v2",
        "causal_continuity_proven": True,
        "campaign": {
            "campaign_clock_id": events[0]["campaign_clock_id"],
            "elapsed_seconds": elapsed[-1],
            "generation_count": 2,
            "teams": ["red", "blue"],
        },
        "lanes": lanes,
        "lineage_edges": lineage_edges,
        "sprite_theme": {
            "schema": "battle.sprite_theme.v1",
            "theme_id": "v13-shared-plague-nurgling",
            "proof_scope": "cosmetic_identity_only",
            "shared_atlas": True,
            "semantic_authority": False,
            "variants": {
                "v13-shared-runner": {
                    "sprite_id": "plague_nurgling",
                    "scale": 1.0,
                }
            },
        },
        "renderer_contract": {
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
        },
        "events": public_events,
        "receipt_refs": index["public_receipts"],
        "selection": index["selection"],
        "memory_evaluation": index["memory_evaluation"],
        "claim_boundary": {
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
        },
        "provenance": {
            "raw_paths_redacted": True,
            "source_run_count": 1,
            "source_proof_id": campaign_root.name,
        },
    }
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
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value
