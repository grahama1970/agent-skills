from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from battle_skill.adaptive_lineage_engine import (
    AdaptiveLineageEngine,
    GenerationRequest,
    JudgedPopulation,
    OracleSelection,
    PopulationStageResult,
    RecallResult,
)
from battle_skill.adaptive_lineage_memory import (
    FakeMemoryHttpClient,
    MemoryBackend,
    public_document_tags,
)
from battle_skill.adaptive_lineage_verified_primitives import (
    PrimitiveBackedOracle,
    PrimitiveBundle,
    VerifiedPopulationHooks,
    load_verified_primitive_bundle,
)

BATTLE_ID = "battle-004"
LINEAGE_ID = "red-main"
COLLECTION = "battle_lineage_graph"


def generation_request(
    tmp_path: Path,
    *,
    generation: int = 1,
    maximum: int = 4,
    population_size: int = 3,
    role: str = "red",
    materialize_only: bool = False,
) -> GenerationRequest:
    return GenerationRequest(
        battle_id=BATTLE_ID,
        lineage_id=LINEAGE_ID,
        run_id=f"run-{role}-g{generation}",
        role=role,
        generation=generation,
        population_size=population_size,
        max_generations=maximum,
        max_recall_hops=3,
        recall_k=64,
        materialize_only=materialize_only,
        out_dir=tmp_path,
        subgraph_scope={},
    )


def shared_public_root(*, edges: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "_key": "arena-public-root",
        "schema": "battle.lineage_memory_node.v2",
        "collection": COLLECTION,
        "battle_id": BATTLE_ID,
        "lineage_id": LINEAGE_ID,
        "scope": f"battle:{BATTLE_ID}:public",
        "node_kind": "arena",
        "retrieval_seed": True,
        "text": "Public arena and judge lineage root.",
        "tags": public_document_tags(
            battle_id=BATTLE_ID,
            lineage_id=LINEAGE_ID,
        ),
        "graph_edges_raw": edges or [],
    }


def backend_with_root(
    *, edges: list[dict[str, str]] | None = None
) -> tuple[MemoryBackend, FakeMemoryHttpClient]:
    fake = FakeMemoryHttpClient([shared_public_root(edges=edges)])
    backend = MemoryBackend(client=fake, collection=COLLECTION)
    return backend, fake


class AllBadPopulation:
    def synthesize(
        self, *, request: GenerationRequest, recall: RecallResult
    ) -> PopulationStageResult:
        assert recall.receipt["daemon_multihop"] is True
        return PopulationStageResult(
            items=tuple(
                {"specimen_id": f"s-{index}", "source": f"source-{index}"}
                for index in range(request.population_size)
            )
        )

    def review(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
    ) -> PopulationStageResult:
        return PopulationStageResult(
            items=tuple({**item, "review_status": "PASS"} for item in generated.items)
        )

    def judge(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
        reviewed: PopulationStageResult,
    ) -> PopulationStageResult:
        judged = tuple(
            {**item, "judge_verdict": "INSUFFICIENT_EVIDENCE"}
            for item in reviewed.items
        )
        bad = tuple(
            {
                "specimen_id": item["specimen_id"],
                "source": "judge",
                "reason_codes": ["INSUFFICIENT_EVIDENCE"],
            }
            for item in judged
        )
        return PopulationStageResult(items=judged, bad_genetic_material=bad)


class NoSurvivorOracle:
    oracle_id = "all-bad-oracle"

    def select(
        self,
        judged_population: JudgedPopulation,
        *,
        request: GenerationRequest,
        recall: RecallResult,
    ) -> OracleSelection:
        return OracleSelection(
            survivor=None,
            bad_genetic_material={
                "specimens": [
                    {
                        "specimen_id": item["specimen_id"],
                        "source": "oracle",
                        "reason_codes": ["INSUFFICIENT_EVIDENCE"],
                    }
                    for item in judged_population.judged.items
                ]
            },
            evidence={"verdict": "NO_SURVIVOR"},
            oracle_id=self.oracle_id,
        )


class RareSurvivorPopulation(AllBadPopulation):
    survivor_id = "s-3"

    def judge(
        self,
        *,
        request: GenerationRequest,
        recall: RecallResult,
        generated: PopulationStageResult,
        reviewed: PopulationStageResult,
    ) -> PopulationStageResult:
        judged = tuple(
            {
                **item,
                "judge_verdict": "RED_SUCCESS"
                if item["specimen_id"] == self.survivor_id
                else "INSUFFICIENT_EVIDENCE",
            }
            for item in reviewed.items
        )
        return PopulationStageResult(
            items=judged,
            bad_genetic_material=tuple(
                {
                    "specimen_id": item["specimen_id"],
                    "source": "judge",
                    "reason_codes": ["INSUFFICIENT_EVIDENCE"],
                }
                for item in judged
                if item["specimen_id"] != self.survivor_id
            ),
        )


class PickRareSurvivorOracle:
    oracle_id = "pick-rare-survivor"

    def select(
        self,
        judged_population: JudgedPopulation,
        *,
        request: GenerationRequest,
        recall: RecallResult,
    ) -> OracleSelection:
        survivor = judged_population.judged_by_id[RareSurvivorPopulation.survivor_id]
        return OracleSelection(
            survivor=survivor,
            bad_genetic_material={"specimens": []},
            evidence={"verdict": "RED_SUCCESS", "judge_replay": True},
            oracle_id=self.oracle_id,
        )


def test_a_all_bad_generation_is_common_valid_terminal(tmp_path: Path) -> None:
    """A: battle-004 shape: 9 insufficient attempts, 0 survivors."""

    memory, fake = backend_with_root()
    receipt = AdaptiveLineageEngine(
        population_hooks=AllBadPopulation(),
        oracle=NoSurvivorOracle(),
        memory_hooks=memory,
    ).run_generation(generation_request(tmp_path, population_size=9))

    assert receipt["status"] == "TERMINATED_VALID"
    assert receipt["survivor"] is None
    assert receipt["terminated_reason"] == "no_survivor"
    assert receipt["stop_reason"] == "no_survivor"
    assert receipt["bad_genetic_material"]["bad_count"] == 9
    assert receipt["bad_genetic_material"]["bad_rate"] == 1.0
    assert receipt["bad_genetic_material"]["all_bad"] is True
    assert not any(call["path"] == "/store" for call in fake.calls)


def test_b_rare_survivor_is_stored_then_inherited_next_generation(
    tmp_path: Path,
) -> None:
    """B: reproduction crosses /store and returns through daemon multihop recall."""

    memory, fake = backend_with_root()
    first = AdaptiveLineageEngine(
        population_hooks=RareSurvivorPopulation(),
        oracle=PickRareSurvivorOracle(),
        memory_hooks=memory,
    ).run_generation(
        generation_request(
            tmp_path,
            generation=1,
            maximum=3,
            population_size=5,
        )
    )

    assert first["status"] == "ACTIVE"
    assert first["stop_reason"] == "survivor_reproduced"
    assert first["bad_genetic_material"]["bad_rate"] == (5 - 1) / 5
    assert first["reproduction"]["survivor_store_ack"]["ok"] is True
    store_calls = [call for call in fake.calls if call["path"] == "/store"]
    assert len(store_calls) == 2
    assert store_calls[0]["json"]["document"]["node_kind"] == "survivor"
    assert "visibility:public" in store_calls[0]["json"]["document"]["tags"]
    assert store_calls[1]["json"]["document"]["node_kind"] == "bad_genetic_material"
    assert "visibility:role-only" in store_calls[1]["json"]["document"]["tags"]

    inherited = memory.recall(
        request=generation_request(
            tmp_path,
            generation=2,
            maximum=3,
            population_size=5,
        )
    )
    survivor_items = [
        item for item in inherited.documents if item.get("node_kind") == "survivor"
    ]
    assert len(survivor_items) == 1
    assert survivor_items[0]["candidate_id"] == RareSurvivorPopulation.survivor_id
    assert survivor_items[0]["scores"]["graph"] > 0.0
    recall_calls = [call for call in fake.calls if call["path"] == "/recall"]
    assert set(recall_calls[-1]["json"]) == {
        "q",
        "k",
        "scope",
        "collections",
        "tags",
    }


def test_c_red_recall_never_crosses_public_edge_into_blue_private_doc(
    tmp_path: Path,
) -> None:
    """C: public connectivity cannot widen a role's permitted subgraph."""

    root = shared_public_root(
        edges=[
            {"edge_type": "related_to", "target_id": "red-private"},
            {"edge_type": "related_to", "target_memory_id": "blue-private"},
        ]
    )
    red_doc = {
        "_key": "red-private",
        "schema": "battle.lineage_memory_node.v2",
        "collection": COLLECTION,
        "battle_id": BATTLE_ID,
        "lineage_id": LINEAGE_ID,
        "scope": f"battle:{BATTLE_ID}:role:red",
        "role": "red",
        "node_kind": "survivor",
        "text": "Red private survivor.",
        "tags": [
            "battle",
            f"battle:{BATTLE_ID}",
            f"lineage:{LINEAGE_ID}",
            "role:red",
            "access:red",
            "visibility:public",
        ],
        "graph_edges_raw": [],
    }
    blue_doc = {
        "_key": "blue-private",
        "schema": "battle.lineage_memory_node.v2",
        "collection": COLLECTION,
        "battle_id": BATTLE_ID,
        "lineage_id": LINEAGE_ID,
        "scope": f"battle:{BATTLE_ID}:role:blue",
        "role": "blue",
        "node_kind": "survivor",
        "text": "Blue private survivor.",
        "tags": [
            "battle",
            f"battle:{BATTLE_ID}",
            f"lineage:{LINEAGE_ID}",
            "role:blue",
            "access:blue",
            "visibility:public",
        ],
        "graph_edges_raw": [],
    }
    fake = FakeMemoryHttpClient([root, red_doc, blue_doc])
    memory = MemoryBackend(client=fake, collection=COLLECTION)

    recall = memory.recall(request=generation_request(tmp_path, role="red"))
    ids = {item["_key"] for item in recall.documents}

    assert ids == {"arena-public-root", "red-private"}
    assert "blue-private" not in ids
    assert next(
        item for item in recall.documents if item["_key"] == "red-private"
    )["scores"]["graph"] > 0.0


def test_live_daemon_recall_quarantines_forbidden_hits_before_context(
    tmp_path: Path,
) -> None:
    red_doc = {
        "_key": "red-private",
        "schema": "battle.lineage_memory_node.v2",
        "collection": COLLECTION,
        "battle_id": BATTLE_ID,
        "lineage_id": LINEAGE_ID,
        "scope": f"battle:{BATTLE_ID}:role:red",
        "role": "red",
        "node_kind": "survivor",
        "text": "Red private survivor.",
        "tags": [
            "battle",
            f"battle:{BATTLE_ID}",
            f"lineage:{LINEAGE_ID}",
            "role:red",
            "access:red",
            "visibility:public",
        ],
        "graph_edges_raw": [],
    }
    forbidden = {
        **red_doc,
        "_key": "blue-private",
        "scope": f"battle:{BATTLE_ID}:role:blue",
        "role": "blue",
        "tags": [
            "battle",
            f"battle:{BATTLE_ID}",
            f"lineage:{LINEAGE_ID}",
            "role:blue",
            "access:blue",
            "visibility:public",
        ],
    }

    class LeakyRecallClient(FakeMemoryHttpClient):
        def _recall(self, payload: Mapping[str, Any]) -> dict[str, Any]:
            body = super()._recall(payload)
            body["items"].append(forbidden)
            return body

    memory = MemoryBackend(client=LeakyRecallClient([red_doc]), collection=COLLECTION)
    recall = memory.recall(request=generation_request(tmp_path, role="red"))

    assert [item["_key"] for item in recall.documents] == ["red-private"]
    assert recall.receipt["dropped_forbidden_item_ids"] == ["blue-private"]
    assert recall.receipt["dropped_forbidden_item_count"] == 1


def test_primitive_backed_oracle_plugs_all_four_verified_helpers(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def population_genomes(
        *,
        red_workers: int,
        materialize_only: bool,
        memory_recall: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        calls.append("population")
        assert red_workers == 3
        assert materialize_only is False
        assert memory_recall["multihop_owner"] == "memory_daemon"
        return {
            "genomes": [
                {"specimen_id": f"p-{index}", "source": f"source-{index}"}
                for index in range(red_workers)
            ]
        }

    def review_population(
        *, population: list[Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        calls.append("review")
        return {"reviews": [{**item, "review_status": "PASS"} for item in population]}

    def judge_population(
        *, reviewed_population: list[Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        calls.append("judge")
        return {
            "judged_population": [
                {
                    **item,
                    "judge_verdict": "RED_SUCCESS"
                    if item["specimen_id"] == "p-2"
                    else "INSUFFICIENT_EVIDENCE",
                }
                for item in reviewed_population
            ]
        }

    def select_survivor(
        *, judged_population: list[Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        calls.append("select")
        return {
            "survivor": "p-2",
            "evidence": {"verdict": "RED_SUCCESS", "judge_replay": True},
            "bad_genetic_material": {
                "specimens": [
                    {
                        "specimen_id": item["specimen_id"],
                        "reason_codes": ["INSUFFICIENT_EVIDENCE"],
                    }
                    for item in judged_population
                    if item["specimen_id"] != "p-2"
                ]
            },
        }

    bundle = PrimitiveBundle(
        population_genomes=population_genomes,
        review_population=review_population,
        judge_population=judge_population,
        select_survivor=select_survivor,
    )
    memory, _fake = backend_with_root()
    receipt = AdaptiveLineageEngine(
        population_hooks=VerifiedPopulationHooks(bundle),
        oracle=PrimitiveBackedOracle(bundle),
        memory_hooks=memory,
    ).run_generation(generation_request(tmp_path))

    assert calls == ["population", "review", "judge", "select"]
    assert receipt["oracle"]["survivor_id"] == "p-2"
    assert receipt["bad_genetic_material"]["bad_count"] == 2


def test_materialize_only_emits_n_and_skips_review_judge_oracle(
    tmp_path: Path,
) -> None:
    class MaterializePopulation:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def synthesize(
            self, *, request: GenerationRequest, recall: RecallResult
        ) -> PopulationStageResult:
            self.calls.append("population")
            return PopulationStageResult(
                items=tuple(
                    {"specimen_id": f"m-{index}"}
                    for index in range(request.population_size)
                )
            )

        def review(self, **_: Any) -> PopulationStageResult:
            raise AssertionError("review must be skipped in materialize_only mode")

        def judge(self, **_: Any) -> PopulationStageResult:
            raise AssertionError("judge must be skipped in materialize_only mode")

    population = MaterializePopulation()
    memory, fake = backend_with_root()
    receipt = AdaptiveLineageEngine(
        population_hooks=population,
        oracle=None,
        memory_hooks=memory,
    ).run_generation(
        generation_request(
            tmp_path,
            population_size=6,
            materialize_only=True,
        )
    )

    assert population.calls == ["population"]
    assert receipt["status"] == "MATERIALIZED"
    assert receipt["population"]["generated_count"] == 6
    assert receipt["population"]["unjudged_count"] == 6
    assert receipt["review_skipped"] is True
    assert receipt["judge_skipped"] is True
    assert receipt["oracle_skipped"] is True
    assert not any(call["path"] == "/store" for call in fake.calls)


def test_memory_write_ack_requires_applied_write_without_errors() -> None:
    accepted = [
        {"ok": True, "_key": "doc-1"},
        {"status": "PASS", "upserted": 1},
        {"ok": True, "results": [{"_key": "doc-1"}]},
    ]
    rejected = [
        {"ok": True},
        {"status": "PASS", "upserted": 0},
        {"ok": True, "_key": "doc-1", "errors": [{"message": "boom"}]},
        {"ok": True, "results": [{"_key": "doc-1", "error": True}]},
    ]
    for response in accepted:
        MemoryBackend._require_write_ack("/store", response)
    for response in rejected:
        try:
            MemoryBackend._require_write_ack("/store", response)
        except Exception as exc:
            assert "did not acknowledge success" in str(exc)
        else:
            raise AssertionError(f"write ack should have failed: {response}")


def test_repository_verified_primitive_bundle_exposes_real_adapters() -> None:
    bundle = load_verified_primitive_bundle()
    assert bundle.population_genomes.__name__ == "_population_genomes"
    assert bundle.review_population.__name__ == "_review_population"
    assert bundle.judge_population.__name__ == "_judge_population"
    assert bundle.select_survivor.__name__ == "_select_survivor"
