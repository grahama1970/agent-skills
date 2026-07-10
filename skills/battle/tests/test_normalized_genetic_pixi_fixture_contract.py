from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from battle_skill.normalized_genetic_pixi_fixture import (
    REQUIRED_EVENT_TYPES,
    normalize_genetic_pixi_fixture,
    validate_normalized_genetic_pixi_fixture,
)


BATTLE_ROOT = Path(__file__).resolve().parents[1]


def test_genetic_pixi_fixture_publishes_ux7_events_and_claim_boundary(tmp_path: Path) -> None:
    out = tmp_path / "local" / "battle-004-pr6-genetic-pixi"
    public = tmp_path / "public" / "battle-004-pr6-genetic-pixi"

    fixture = normalize_genetic_pixi_fixture(
        source_dir=BATTLE_ROOT,
        out_dir=out,
        public_out_dir=public,
        generated_at="2026-07-10T22:20:00Z",
    )

    report = validate_normalized_genetic_pixi_fixture(fixture)
    assert report["status"] == "PASS"
    assert fixture["schema"] == "battle.normalized_ux_fixture.v1"
    assert fixture["genetic_lifecycle"]["schema"] == "battle.genetic_lifecycle_events.v1"
    assert fixture["genetic_lifecycle"]["route"] == "#battle/receipt?engine=pixi&fixture=battle-004-pr6-genetic-pixi"
    assert fixture["genetic_lifecycle"]["fixture_url"] == "/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"

    present = set(fixture["genetic_lifecycle"]["present_event_types"])
    not_emitted = set(fixture["genetic_lifecycle"]["not_emitted_event_types"])
    assert present | not_emitted == set(REQUIRED_EVENT_TYPES)
    assert "judge_exploit_success" in not_emitted
    assert "genome_promoted" in not_emitted
    assert "research_started" in present
    assert "specimen_materialized" in present
    assert "compile_failed" in present
    assert "compile_passed" in present
    assert "target_contact_unproven" in present
    assert "judge_pending" in present

    events = [event for event in fixture["events"] if event["event_type"] in REQUIRED_EVENT_TYPES]
    assert {event["event_type"] for event in events} == present
    assert [event["order_index"] for event in events] == sorted(event["order_index"] for event in events)
    for event in events:
        assert isinstance(event["elapsed_seconds"], (int, float))
        assert event["payload"]["lane_id"]
        assert event["payload"]["receipt_id"] == event["evidence"]["receipt_id"]
        assert event["presentation"]["victory_allowed"] is False
        assert event["presentation"]["kill_allowed"] is False
        assert event["presentation"]["containment_allowed"] is False
    compile_passed = next(event for event in events if event["event_type"] == "compile_passed")
    assert compile_passed["claim_boundary"]["compile_passed_is_not_runnable"] is True
    target_contact = next(event for event in events if event["event_type"] == "target_contact_unproven")
    assert target_contact["claim_boundary"]["target_contact_is_not_exploit_success"] is True
    judge_pending = next(event for event in events if event["event_type"] == "judge_pending")
    assert judge_pending["payload"]["judge_verified_exploits"] == 0

    serialized = json.dumps(fixture, sort_keys=True)
    for marker in ["tau-dag-run/", "command-loop/", "command-artifacts/", "/tmp/", "/home/", "provider-workspace"]:
        assert marker not in serialized
    assert _sha256(out / "battle.normalized_ux_fixture.json") == _sha256(public / "battle.normalized_ux_fixture.json")


def test_genetic_pixi_fixture_rejects_judge_success_without_receipt(tmp_path: Path) -> None:
    fixture = normalize_genetic_pixi_fixture(
        source_dir=BATTLE_ROOT,
        out_dir=tmp_path / "out",
        generated_at="2026-07-10T22:20:00Z",
    )
    fixture["events"].append(
        {
            **fixture["events"][-1],
            "id": "bad-judge-success",
            "event_type": "judge_exploit_success",
            "summary": "bad success",
            "order_index": fixture["events"][-1]["order_index"] + 1,
        }
    )
    fixture["genetic_lifecycle"]["present_event_types"].append("judge_exploit_success")
    fixture["genetic_lifecycle"]["not_emitted_event_types"].remove("judge_exploit_success")
    fixture["timeline"]["event_count"] = len(fixture["events"])
    fixture["ux_contract"]["receipt_backed_values"]["event_count"] = len(fixture["events"])
    fixture["spectator_shell"]["event_ticker"]["count"] = len(fixture["events"])

    with pytest.raises(ValueError, match="judge_exploit_success"):
        validate_normalized_genetic_pixi_fixture(fixture)


def test_genetic_pixi_fixture_rejects_path_leakage(tmp_path: Path) -> None:
    fixture = normalize_genetic_pixi_fixture(
        source_dir=BATTLE_ROOT,
        out_dir=tmp_path / "out",
        generated_at="2026-07-10T22:20:00Z",
    )
    fixture["genetic_lifecycle"]["source_fixtures"]["leak"] = "/tmp/raw-provider-workspace/exploit_specimen.py"

    with pytest.raises(ValueError, match="forbidden marker"):
        validate_normalized_genetic_pixi_fixture(fixture)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
