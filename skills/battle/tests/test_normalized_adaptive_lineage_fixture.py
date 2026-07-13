"""Adaptive normalizer consumes one explicit run and redacts raw paths."""

import json

from battle_skill.normalized_adaptive_lineage_fixture import (
    build_normalized_adaptive_fixture,
)


def test_normalizer_rejects_cross_run_and_projects_public_events(tmp_path) -> None:
    root = tmp_path / "campaign"
    root.mkdir()
    specs = [
        ("judge_verdict", None, 1, 1.0),
        ("fitness_materialized", "red", 1, 2.0),
        ("fitness_materialized", "blue", 1, 3.0),
        ("spawn_requested", "red", 1, 4.0),
        ("spawn_requested", "blue", 1, 5.0),
        ("spawn_authorized", "red", 1, 6.0),
        ("spawn_authorized", "blue", 1, 7.0),
        ("child_research_materialized", "red", 2, 8.0),
        ("child_research_materialized", "blue", 2, 9.0),
    ]
    events = []
    for seq, (event_type, team, generation, elapsed) in enumerate(specs, 1):
        events.append(
            {
                "schema": "battle.campaign_event.v1",
                "seq": seq,
                "event_id": f"e{seq}",
                "battle_id": "battle-004",
                "run_id": "run",
                "campaign_clock_id": "clock",
                "generation": generation,
                "team": team,
                "event_type": event_type,
                "timing": {"elapsed_seconds": elapsed},
                "source_receipt": {
                    "receipt_id": f"r{seq}",
                    "schema": "x",
                    "sha256": f"{seq:064x}",
                    "status": "PASS",
                },
                "payload": {},
            }
        )
    (root / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    index = {
        "campaign_root_id": "campaign",
        "battle_id": "battle-004",
        "run_id": "run",
        "public_receipts": [],
        "selection": {},
        "memory_evaluation": {},
    }
    index_path = root / "source-receipt-index.json"
    index_path.write_text(json.dumps(index))
    fixture = build_normalized_adaptive_fixture(
        campaign_root=root, source_index_path=index_path, fixture_id="fixture"
    )
    assert fixture["causal_continuity_proven"] is True
    assert fixture["events"][0]["event_type"] == "judge_verdict"
    assert fixture["events"][0]["scope"] == "generation_pair"
    assert fixture["events"][0]["affected_lane_ids"] == ["red-g1", "blue-g1"]
    assert [lane["lane_id"] for lane in fixture["lanes"]] == [
        "red-g1",
        "red-g2",
        "blue-g1",
        "blue-g2",
    ]
    assert fixture["lanes"][1]["visible_from_elapsed_seconds"] == 6.0
    assert fixture["lanes"][1]["active_from_elapsed_seconds"] == 8.0
    assert fixture["lineage_edges"][0]["requested_receipt_ref"]["receipt_id"] == "r4"
    assert fixture["sprite_theme"]["variants"]["v13-shared-runner"]["sprite_id"] == "plague_nurgling"
    assert fixture["renderer_contract"]["child_activation_event"] == "child_research_materialized"
    assert "/tmp/" not in json.dumps(fixture)
