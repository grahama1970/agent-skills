from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, Mapping

import pytest

from battle_skill.adaptive_lineage_engine import (
    AdaptiveLineageContractError,
    FitnessOracle,
    GenerationRequest,
    JudgedPopulation,
    PopulationStageResult,
    RecallResult,
    candidate_id,
)
from battle_skill.adaptive_lineage_memory import (
    FakeMemoryHttpClient,
    MemoryBackend,
    public_document_tags,
)
from battle_skill.adaptive_lineage_oracles import (
    ArenaCreatorOracle,
    BlueOracle,
    JudgeOracle,
    MemoryResearchNegativeEvidenceSink,
    RedOracle,
    ResearcherOracle,
    TauArenaPopulationHooks,
    UnconfiguredTauArenaCreatorDagBackend,
    build_live_role_runtime,
)
from battle_skill.adaptive_lineage_verified_primitives import VerifiedPopulationHooks

BATTLE_ID = "battle-round3"
LINEAGE_ID = "lineage-main"
COLLECTION = "battle_lineage_graph"
ALL_ROLES = ("arena-creator", "red", "blue", "judge", "researcher")


def request(tmp_path: Path, role: str, *, population_size: int = 3) -> GenerationRequest:
    return GenerationRequest(
        battle_id=BATTLE_ID,
        lineage_id=LINEAGE_ID,
        run_id=f"run-{role}",
        role=role,
        generation=1,
        population_size=population_size,
        max_generations=3,
        max_recall_hops=3,
        out_dir=tmp_path,
        subgraph_scope={},
    )


def judged_population(items: list[Mapping[str, Any]]) -> JudgedPopulation:
    normalized = tuple(dict(item) for item in items)
    return JudgedPopulation(
        generated=PopulationStageResult(items=normalized),
        reviewed=PopulationStageResult(items=normalized),
        judged=PopulationStageResult(items=normalized),
    )


def public_root(*, edges: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "_key": "shared-public-root",
        "schema": "battle.lineage_memory_node.v2",
        "collection": COLLECTION,
        "battle_id": BATTLE_ID,
        "lineage_id": LINEAGE_ID,
        "scope": f"battle:{BATTLE_ID}:public",
        "node_kind": "shared_public",
        "retrieval_seed": True,
        "text": "Shared Arena and role-safe Judge evidence.",
        "tags": public_document_tags(
            battle_id=BATTLE_ID,
            lineage_id=LINEAGE_ID,
        ),
        "graph_edges_raw": edges or [],
    }


def private_doc(role: str, *, access_role: str | None = None) -> dict[str, Any]:
    access_role = access_role or role
    return {
        "_key": f"{role}-private",
        "schema": "battle.lineage_memory_node.v2",
        "collection": COLLECTION,
        "battle_id": BATTLE_ID,
        "lineage_id": LINEAGE_ID,
        "scope": f"battle:{BATTLE_ID}:role:{role}",
        "role": role,
        "node_kind": "survivor",
        "text": f"{role} private lineage evidence.",
        "tags": [
            "battle",
            f"battle:{BATTLE_ID}",
            f"lineage:{LINEAGE_ID}",
            f"role:{role}",
            f"access:{access_role}",
            "visibility:public",
        ],
        "graph_edges_raw": [],
    }


def recalled(
    tmp_path: Path,
    role: str,
    *,
    extra_documents: list[Mapping[str, Any]] | None = None,
) -> tuple[GenerationRequest, RecallResult, MemoryBackend, FakeMemoryHttpClient]:
    role_private = private_doc(role)
    root = public_root(
        edges=[
            {"edge_type": "role_context", "target_id": role_private["_key"]}
        ]
    )
    documents = [root, role_private, *(extra_documents or [])]
    fake = FakeMemoryHttpClient(documents)
    memory = MemoryBackend(client=fake, collection=COLLECTION)
    role_request = request(tmp_path, role)
    return role_request, memory.recall(request=role_request), memory, fake


def viable_item(role: str) -> dict[str, Any]:
    if role == "red":
        return {"specimen_id": "red-win", "judge_verdict": "RED_SUCCESS"}
    if role == "blue":
        return {"specimen_id": "blue-win", "judge_verdict": "BLUE_SUCCESS"}
    if role == "judge":
        return {
            "specimen_id": "judge-sound",
            "methodology_evidence": {
                "deterministic": True,
                "replay_consistent": True,
                "non_gameable": True,
                "real_replay": True,
                "replay_count": 3,
            },
        }
    if role == "researcher":
        return {
            "specimen_id": "finding-useful",
            "usefulness_evidence": {
                "led_to_survivor_id": "red-win",
                "selection_receipt_ref": "receipt:red-win",
                "led_to_survivor": True,
            },
        }
    if role == "arena-creator":
        return {
            "specimen_id": "arena-balanced",
            "past_game_judge_outcomes": [
                "RED_SUCCESS",
                "BLUE_SUCCESS",
                "RED_SUCCESS",
                "BLUE_SUCCESS",
            ],
        }
    raise AssertionError(role)


def oracle_for_test(role: str) -> FitnessOracle:
    if role == "red":
        return RedOracle()
    if role == "blue":
        return BlueOracle()
    if role == "judge":
        return JudgeOracle()
    if role == "researcher":
        return ResearcherOracle()
    if role == "arena-creator":
        return ArenaCreatorOracle()
    raise AssertionError(role)


def test_red_oracle_picks_red_success_and_none_when_all_insufficient(
    tmp_path: Path,
) -> None:
    role_request, recall, _memory, _fake = recalled(tmp_path, "red")
    oracle = RedOracle()
    population = judged_population(
        [
            {"specimen_id": "red-bad-0", "judge_verdict": "INSUFFICIENT_EVIDENCE"},
            {"specimen_id": "red-good", "judge_verdict": "RED_SUCCESS"},
            {"specimen_id": "red-bad-1", "judge_verdict": "INSUFFICIENT_EVIDENCE"},
        ]
    )

    selection = oracle.select(population, request=role_request, recall=recall)
    assert candidate_id(selection.survivor or {}) == "red-good"
    assert selection.evidence["success_count"] == 1
    assert {
        item["specimen_id"]
        for item in selection.bad_genetic_material["specimens"]
    } == {"red-bad-0", "red-bad-1"}

    all_bad = judged_population(
        [
            {"specimen_id": f"red-{index}", "judge_verdict": "INSUFFICIENT_EVIDENCE"}
            for index in range(9)
        ]
    )
    dead = oracle.select(all_bad, request=role_request, recall=recall)
    assert dead.survivor is None
    assert dead.evidence["all_insufficient"] is True
    assert len(dead.bad_genetic_material["specimens"]) == 9


def test_blue_oracle_picks_blue_success(tmp_path: Path) -> None:
    role_request, recall, _memory, _fake = recalled(tmp_path, "blue")
    selection = BlueOracle().select(
        judged_population(
            [
                {"specimen_id": "blue-bad", "judge_verdict": "RED_SUCCESS"},
                {"specimen_id": "blue-good", "judge_verdict": "BLUE_SUCCESS"},
            ]
        ),
        request=role_request,
        recall=recall,
    )
    assert candidate_id(selection.survivor or {}) == "blue-good"
    assert selection.evidence["success_count"] == 1


def test_judge_oracle_rejects_spoofed_marker_without_real_replay(
    tmp_path: Path,
) -> None:
    role_request, recall, _memory, _fake = recalled(tmp_path, "judge")
    spoofed = {
        "specimen_id": "judge-marker-spoof",
        "methodology_evidence": {
            "deterministic": True,
            "replay_consistent": True,
            "non_gameable": True,
            "success_marker": "EXPLOIT_SUCCESS",
            "success_marker_only": True,
            "real_replay": False,
            "replay_count": 0,
        },
    }
    sound = {
        "specimen_id": "judge-real-replay",
        "methodology_evidence": {
            "deterministic": True,
            "replay_consistent": True,
            "non_gameable": True,
            "real_replay": True,
            "replay_count": 3,
            "replay_receipts": ["r1", "r2", "r3"],
        },
    }

    selection = JudgeOracle().select(
        judged_population([spoofed, sound]),
        request=role_request,
        recall=recall,
    )
    assert candidate_id(selection.survivor or {}) == "judge-real-replay"
    spoof_record = next(
        item
        for item in selection.bad_genetic_material["specimens"]
        if item["specimen_id"] == "judge-marker-spoof"
    )
    assert "spoofed_success_marker_without_real_replay" in spoof_record["reason_codes"]

    only_spoof = JudgeOracle().select(
        judged_population([spoofed]),
        request=role_request,
        recall=recall,
    )
    assert only_spoof.survivor is None


def test_researcher_oracle_retains_dead_ends_via_memory_upsert(
    tmp_path: Path,
) -> None:
    role_request, recall, memory, fake = recalled(tmp_path, "researcher")
    oracle = ResearcherOracle(MemoryResearchNegativeEvidenceSink(memory))
    useful = viable_item("researcher")
    dead_end = {
        "specimen_id": "finding-dead-end",
        "text": "A path already disproved by Judge replay.",
        "usefulness_evidence": {
            "led_to_survivor": False,
            "downstream_verdict": "INSUFFICIENT_EVIDENCE",
        },
    }

    selection = oracle.select(
        judged_population([dead_end, useful]),
        request=role_request,
        recall=recall,
    )
    assert candidate_id(selection.survivor or {}) == "finding-useful"
    retention = selection.evidence["negative_evidence_retention"]
    assert retention["retained_count"] == 1
    upserts = [call for call in fake.calls if call["path"] == "/upsert"]
    assert len(upserts) == 1
    stored = upserts[0]["json"]["documents"][0]
    assert stored["node_kind"] == "research_dead_end"
    assert "visibility:role-only" in stored["tags"]
    assert "do-not-research-again" in stored["tags"]
    assert stored["scope"] == f"battle:{BATTLE_ID}:role:researcher"


def test_arena_creator_selects_balanced_history_and_rejects_battle004_shape(
    tmp_path: Path,
) -> None:
    role_request, recall, _memory, _fake = recalled(tmp_path, "arena-creator")
    oracle = ArenaCreatorOracle(min_decisive_games=2, min_balance_score=0.8)
    balanced = viable_item("arena-creator")
    one_sided = {
        "specimen_id": "arena-one-sided",
        "past_game_judge_outcomes": ["RED_SUCCESS", "RED_SUCCESS", "RED_SUCCESS"],
    }
    degenerate = {
        "specimen_id": "arena-battle-004-shape",
        "past_game_judge_outcomes": ["INSUFFICIENT_EVIDENCE"] * 9,
    }

    selection = oracle.select(
        judged_population([one_sided, balanced, degenerate]),
        request=role_request,
        recall=recall,
    )
    assert candidate_id(selection.survivor or {}) == "arena-balanced"
    checks = selection.evidence["checks"]
    assert checks["arena-balanced"]["balance_score"] == 1.0
    degenerate_bad = next(
        item
        for item in selection.bad_genetic_material["specimens"]
        if item["specimen_id"] == "arena-battle-004-shape"
    )
    assert "degenerate_all_insufficient_arena" in degenerate_bad["reason_codes"]

    dead = oracle.select(
        judged_population([degenerate]),
        request=role_request,
        recall=recall,
    )
    assert dead.survivor is None


@pytest.mark.parametrize("role", ALL_ROLES)
def test_each_oracle_is_limited_to_its_role_plus_public_subgraph(
    tmp_path: Path,
    role: str,
) -> None:
    foreign_role = "blue" if role != "blue" else "red"
    foreign = private_doc(foreign_role, access_role=role)
    role_request, recall, _memory, _fake = recalled(
        tmp_path,
        role,
        extra_documents=[foreign],
    )
    recalled_ids = {item["_key"] for item in recall.documents}
    assert recalled_ids == {"shared-public-root", f"{role}-private"}
    assert f"{foreign_role}-private" not in recalled_ids

    oracle = oracle_for_test(role)
    assert isinstance(oracle, FitnessOracle)
    selection = oracle.select(
        judged_population([viable_item(role)]),
        request=role_request,
        recall=recall,
    )
    assert selection.survivor is not None

    forged = RecallResult(
        documents=(*recall.documents, foreign),
        confidence=1.0,
        should_scan=False,
        receipt={"schema": "forged-isolation-probe"},
    )
    with pytest.raises(AdaptiveLineageContractError, match="ISOLATION BREACH"):
        oracle.select(
            judged_population([viable_item(role)]),
            request=role_request,
            recall=forged,
        )


def test_live_runtime_wires_real_memory_and_verified_canary_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "battle_skill._round3_fake_canary"
    module = types.ModuleType(module_name)
    module._population_genomes = lambda **_kwargs: []
    module._review_population = lambda **_kwargs: []
    module._judge_population = lambda **_kwargs: []
    module._select_survivor = lambda **_kwargs: None
    monkeypatch.setitem(sys.modules, module_name, module)

    role_request, _recall, memory, _fake = recalled(tmp_path, "red")
    runtime = build_live_role_runtime(
        role_request.role,
        memory=memory,
        primitive_module=module_name,
    )
    assert isinstance(runtime.oracle, RedOracle)
    assert isinstance(runtime.population_hooks, VerifiedPopulationHooks)
    assert runtime.memory is memory
    assert runtime.engine.memory_hooks is memory

    arena_runtime = build_live_role_runtime(
        "arena-creator",
        memory=memory,
    )
    assert isinstance(arena_runtime.population_hooks, TauArenaPopulationHooks)
    assert isinstance(
        arena_runtime.population_hooks.backend,
        UnconfiguredTauArenaCreatorDagBackend,
    )

    with pytest.raises(AdaptiveLineageContractError, match="population_hooks"):
        build_live_role_runtime("judge", memory=memory)
