from pathlib import Path

import pytest

from battle_skill.live_transport_server import (
    build_live_transport_source,
    prove_live_transport_server,
)


FIXTURE = Path("spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json")


def test_live_transport_source_builds_snapshot_and_ordered_events():
    source = build_live_transport_source(fixture_path=FIXTURE, battle_id="battle-004")

    assert source.snapshot["schema"] == "battle.snapshot.v1"
    assert source.snapshot["battle_id"] == "battle-004"
    assert source.snapshot["last_seq"] == len(source.events)
    assert len(source.events) > 0
    assert [event["seq"] for event in source.events] == list(range(1, len(source.events) + 1))
    assert all(event["schema"] == "battle.live_event.v1" for event in source.events)


def test_live_transport_source_rejects_battle_id_mismatch():
    with pytest.raises(ValueError, match="battle_id"):
        build_live_transport_source(fixture_path=FIXTURE, battle_id="battle-999")


def test_prove_live_transport_server_exercises_snapshot_sse_and_resume(tmp_path):
    receipt = prove_live_transport_server(fixture_path=FIXTURE, battle_id="battle-004", out_dir=tmp_path)

    assert receipt["status"] == "PASS"
    assert receipt["mocked"] is False
    assert receipt["live"] == "local_http_sse_adapter"
    assert receipt["snapshot_schema"] == "battle.snapshot.v1"
    assert receipt["event_schema"] == "battle.live_event.v1"
    assert receipt["event_count"] == receipt["last_seq"]
    assert receipt["resume_from_last_event_id"] == 2
    assert receipt["resumed_event_count"] == receipt["event_count"] - 2
    assert receipt["future_last_event_id_status"] == 400
    assert receipt["raw_path_boundary"]["raw_paths_leaked"] is False
    assert "exploit succeeded" not in " ".join(receipt["claim_boundary"]["proves"]).lower()
    assert (tmp_path / "live-transport-server-proof.json").exists()
    assert (tmp_path / "snapshot-response.json").exists()
    assert (tmp_path / "events.sse").read_text(encoding="utf-8").startswith("id: 1\n")
    assert "event: battle.live_event\n" in (tmp_path / "events.sse").read_text(encoding="utf-8")
