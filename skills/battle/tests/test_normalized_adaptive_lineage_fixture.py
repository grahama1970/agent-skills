"""Adaptive normalizer consumes one explicit run and redacts raw paths."""

import json

from battle_skill.normalized_adaptive_lineage_fixture import (
    build_normalized_adaptive_fixture,
)


def test_normalizer_rejects_cross_run_and_projects_public_events(tmp_path) -> None:
    root = tmp_path / "campaign"
    root.mkdir()
    event = {
        "schema": "battle.campaign_event.v1",
        "seq": 1,
        "event_id": "e1",
        "battle_id": "battle-004",
        "run_id": "run",
        "campaign_clock_id": "clock",
        "generation": 1,
        "team": "red",
        "lane_id": "red-g1",
        "event_type": "fitness_materialized",
        "timing": {"elapsed_seconds": 1.0},
        "source_receipt": {"schema": "x", "sha256": "a" * 64, "status": "PASS"},
        "payload": {},
    }
    (root / "events.jsonl").write_text(json.dumps(event) + "\n")
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
    assert fixture["events"][0]["event_type"] == "fitness_materialized"
    assert "/tmp/" not in json.dumps(fixture)
