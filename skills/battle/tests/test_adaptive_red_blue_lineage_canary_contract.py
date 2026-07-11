from __future__ import annotations

from battle_skill.adaptive_red_blue_lineage_canary import (
    _campaign_status,
    _generation_2_objective,
)


def test_generation_two_objectives_bind_inheritance_research_and_materialization() -> (
    None
):
    packet = {
        "packet_id": "battle-004-red-generation-2-knowledge",
        "parent_artifact_sha256": "parent-sha",
    }
    research = {"source_receipt_sha256": "research-sha"}

    red = _generation_2_objective("red", packet, research)
    blue = _generation_2_objective("blue", packet, research)

    for objective in (red, blue):
        assert packet["packet_id"] in objective
        assert packet["parent_artifact_sha256"] in objective
        assert research["source_receipt_sha256"] in objective
        assert "public target only" in objective
    assert "from app import import_zip" in red
    assert "callable import_zip(zip_path, destination)" in blue


def test_campaign_status_requires_both_lineages_and_both_judge_pairs() -> None:
    values = {
        "generation_1": {"status": "PASS"},
        "visibility": {"status": "PASS"},
        "g1_judge": {"judged_pair_count": 1},
        "g2_judge": {"judged_pair_count": 1},
        "red_spawn": {"status": "PASS"},
        "blue_spawn": {"status": "PASS"},
        "red_ack": {"status": "PASS"},
        "blue_ack": {"status": "PASS"},
        "selection": {"status": "PASS"},
    }

    assert _campaign_status(**values) == (
        "PASS",
        "two_generation_red_blue_lineage_evaluated",
    )

    values["blue_ack"] = {"status": "BLOCKED"}
    assert _campaign_status(**values) == (
        "BLOCKED",
        "spawn_inheritance_or_selection_blocked",
    )
