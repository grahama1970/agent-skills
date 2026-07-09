from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from battle_skill.child_knowledge_packet import build_child_knowledge_packet
from battle_skill.exploit_combiner import run_exploit_combiner_proof


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_child_knowledge_packet_preserves_parent_failures_and_boundaries(tmp_path: Path) -> None:
    parent = run_exploit_combiner_proof(
        battle_id="battle-004",
        out_dir=tmp_path / "combiner",
        max_attempts=4,
        docker_image="python:3.12-slim",
        model="not-used",
        scillm_base_url="not-used",
    )
    packet = build_child_knowledge_packet(battle_id="battle-004", parent_combiner_receipt=parent)
    jsonschema.validate(packet, _load_schema("battle.child_knowledge_packet.v1.schema.json"))

    assert packet["schema"] == "battle.child_knowledge_packet.v1"
    assert packet["parent_lane_id"] == "payload-857-combiner"
    assert packet["child_lane_id"] == "payload-857-child-dag-001"
    assert "arena/team-public/target/app.py" in packet["arena_public_context_refs"]
    assert "arena/private/**" in packet["forbidden_context_refs"]
    assert "zip_slip_basic" in packet["inherited_methods"]
    assert len(packet["parent_specimens"]) == 3
    assert {item["status"] for item in packet["parent_specimens"]} == {
        "SPECIMEN_COMPILE_FAILED",
        "SPECIMEN_RUNTIME_FAILED",
    }
    assert any("Judge replay" in item for item in packet["blocked_ideas"])
