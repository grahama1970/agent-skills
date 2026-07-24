from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from battle_skill.adaptive_lineage_engine import (
    AdaptiveLineageContractError,
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
    context: Mapping[str, Any] | None = None,
) -> GenerationRequest:
    return GenerationRequest(
        context=dict(context or {}),
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
    assert not any(
        call["path"] in ("/store", "/upsert") for call in fake.calls
    )


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
    # A generation reproduces the survivor and its bad genetic material
    # together, so the write is ONE batched /upsert, not two /store calls
    # (/memory contract: "/upsert for batches, /store only for a single doc").
    assert not any(call["path"] == "/store" for call in fake.calls)
    upsert_calls = [call for call in fake.calls if call["path"] == "/upsert"]
    assert len(upsert_calls) == 1
    written = upsert_calls[0]["json"]["documents"]
    assert len(written) == 2
    assert written[0]["node_kind"] == "survivor"
    assert "visibility:public" in written[0]["tags"]
    assert written[1]["node_kind"] == "bad_genetic_material"
    assert "visibility:role-only" in written[1]["tags"]

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


def test_verified_hooks_drive_the_real_canary_primitive_contract(
    tmp_path: Path,
) -> None:
    """Pin the LIVE signatures and shapes of the four canary primitives.

    Captured 2026-07-24 from battle_skill.adaptive_red_blue_lineage_canary::

      _population_genomes(*, battle_id, run_id, generation, generation_dir,
                          manifest) -> {"red": [...], "blue": [...]}
      _review_population(*, ..., manifest, target_identity_sha256,
                         docker_image, genomes)
                      -> (reviewed_manifest, {"red": [...], "blue": [...]})
      _judge_population(*, generation_dir, scenario, docker_image,
                        reviewed_manifest, review_pipelines) -> dict
      _select_survivor(judge, team) -> dict

    The primitives are two-team and interleave good/bad specimens inside each
    team list by ``status``; the engine is role-scoped. Arena facts (manifest,
    scenario, docker_image, target_identity_sha256) reach them only through
    request.context.
    """

    seen: dict[str, Any] = {}
    manifest = {"teams": [{"team": "blue", "worker_id": "blue-0"}]}
    scenario = {"battle_id": BATTLE_ID, "cwe": "CWE-22"}

    def population_genomes(
        *,
        battle_id: str,
        run_id: str,
        generation: int,
        generation_dir: Path,
        manifest: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        seen["population_manifest"] = manifest
        return {
            "red": [{"worker_id": "red-0", "status": "PASS"}],
            "blue": [
                {"worker_id": "blue-0", "status": "PASS"},
                {"worker_id": "blue-1", "status": "PASS"},
                {"worker_id": "blue-2", "status": "BAD", "reason": "no genome"},
            ],
        }

    def review_population(
        *,
        battle_id: str,
        run_id: str,
        generation: int,
        generation_dir: Path,
        manifest: dict[str, Any],
        target_identity_sha256: str,
        docker_image: str,
        genomes: dict[str, list[dict[str, Any]]],
    ) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
        seen["review_genomes"] = genomes
        seen["target_identity_sha256"] = target_identity_sha256
        seen["review_docker_image"] = docker_image
        return (
            {"reviewed": True, "teams": manifest["teams"]},
            {
                "red": [{"worker_id": "red-0", "status": "PASS"}],
                "blue": [
                    {"worker_id": "blue-0", "status": "PASS"},
                    {"worker_id": "blue-1", "status": "BLOCKED"},
                ],
            },
        )

    def judge_population(
        *,
        generation_dir: Path,
        scenario: dict[str, Any],
        docker_image: str,
        reviewed_manifest: dict[str, Any],
        review_pipelines: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        seen["judge_scenario"] = scenario
        seen["judge_reviewed_manifest"] = reviewed_manifest
        seen["judge_review_pipelines"] = review_pipelines
        # Live Judge payload: pair-keyed replay attempts.
        return {
            "attempts": [
                {"pair_id": "red-0__blue-0", "verdict": "BLUE_SUCCESS"},
                {"pair_id": "red-0__blue-1", "verdict": "RED_SUCCESS"},
            ]
        }

    def select_survivor(judge: dict[str, Any], team: str) -> dict[str, Any]:
        seen["select_judge"] = judge
        seen["select_team"] = team
        # Live _select_survivor return shape.
        return {
            "team": team,
            "population_size": 2,
            "survivor_worker_ids": ["blue-0"],
            "selected_survivor": "blue-0",
            "bad_worker_ids": ["blue-1"],
            "bad_genetic_material_rate": 0.5,
            "outcomes": {
                "blue-0": {"won": True, "verdicts": ["BLUE_SUCCESS"]},
                "blue-1": {"won": False, "verdicts": ["RED_SUCCESS"]},
            },
        }

    bundle = PrimitiveBundle(
        population_genomes=population_genomes,
        review_population=review_population,
        judge_population=judge_population,
        select_survivor=select_survivor,
    )
    # The live Judge replays against the arena target in the generation dir.
    tmp_path.joinpath(
        "generation-0001", "arena", "team-public", "target"
    ).mkdir(parents=True)
    memory, _fake = backend_with_root()
    receipt = AdaptiveLineageEngine(
        population_hooks=VerifiedPopulationHooks(bundle),
        oracle=PrimitiveBackedOracle(bundle),
        memory_hooks=memory,
    ).run_generation(
        generation_request(
            tmp_path,
            role="blue",
            context={
                "manifest": manifest,
                "scenario": scenario,
                "docker_image": "python:3.12-slim",
                "target_identity_sha256": "abc123",
            },
        )
    )

    # Arena facts reached the primitives through request.context.
    assert seen["population_manifest"] == manifest
    assert seen["target_identity_sha256"] == "abc123"
    assert seen["review_docker_image"] == "python:3.12-slim"
    assert seen["judge_scenario"] == scenario

    # review received the team-keyed genome map, not a flattened item list.
    assert set(seen["review_genomes"]) == {"red", "blue"}

    # judge received review's 2-tuple payload, split correctly.
    assert seen["judge_reviewed_manifest"]["reviewed"] is True
    assert set(seen["judge_review_pipelines"]) == {"red", "blue"}

    # The oracle received the Judge's own pair-keyed payload and this role's team.
    assert [a["pair_id"] for a in seen["select_judge"]["attempts"]] == [
        "red-0__blue-0",
        "red-0__blue-1",
    ]
    assert seen["select_team"] == "blue"

    # The worker-id survivor is honored even though the Judge payload is
    # pair-keyed, so the id is absent from the judged items by construction.
    assert receipt["oracle"]["survivor_id"] == "blue-0"

    # Bad genetic material accumulates across the whole generation: blue-2 died
    # at the population stage (no valid strategy_genome) and blue-1 died at the
    # Judge (replayed, never won). Only blue-0 survived.
    assert receipt["bad_genetic_material"]["bad_count"] == 2

    # Role scoping: red specimens are never this lineage's population, and the
    # review 2-tuple was not misread as (items, bad).
    assert receipt["population"]["generated_count"] == 3

    # Bad specimens stay IN the population (a generation materializes N, most
    # of them bad) while still being recorded as bad genetic material.
    assert seen["review_genomes"]["blue"] == [
        {"worker_id": "blue-0", "status": "PASS"},
        {"worker_id": "blue-1", "status": "PASS"},
        {"worker_id": "blue-2", "status": "BAD", "reason": "no genome"},
    ]
    assert receipt["oracle"]["survivor_id"] == "blue-0"


def test_judge_stage_fails_closed_without_the_arena_it_replays_against(
    tmp_path: Path,
) -> None:
    """The live Judge copies <generation_dir>/arena/team-public/target.

    Unmet, that surfaced as a bare FileNotFoundError from shutil.copytree only
    AFTER every specimen had been compiled in Docker. Name the requirement
    instead, and only for the live judge contract.
    """

    def judge_population(
        *,
        generation_dir: Path,
        scenario: dict[str, Any],
        docker_image: str,
        reviewed_manifest: dict[str, Any],
        review_pipelines: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        raise AssertionError("judge must not run without its arena")

    hooks = VerifiedPopulationHooks(
        PrimitiveBundle(
            population_genomes=lambda **_: {"blue": []},
            review_population=lambda **_: ({}, {"blue": []}),
            judge_population=judge_population,
            select_survivor=lambda judge, team: {},
        )
    )
    request = generation_request(tmp_path, role="blue")
    empty = PopulationStageResult(items=())

    with pytest.raises(AdaptiveLineageContractError, match="arena target"):
        hooks.judge(
            request=request,
            recall=RecallResult(),
            generated=empty,
            reviewed=empty,
        )

    # Staging the arena clears the preflight; the judge is reached and fails on
    # its own contract instead (this fake declares the live signature but the
    # request carries none of the arena facts it needs).
    request.out_dir.joinpath(
        "generation-0001", "arena", "team-public", "target"
    ).mkdir(parents=True)
    with pytest.raises(AdaptiveLineageContractError, match="unsupported arguments"):
        hooks.judge(
            request=request,
            recall=RecallResult(),
            generated=empty,
            reviewed=empty,
        )

    # The preflight is gated on the live judge contract, so a fake judge that
    # does not replay against an arena is never asked for one.
    plain_hooks = VerifiedPopulationHooks(
        PrimitiveBundle(
            population_genomes=lambda **_: {"blue": []},
            review_population=lambda **_: ({}, {"blue": []}),
            judge_population=lambda **_: {"judged_population": []},
            select_survivor=lambda judge, team: {},
        )
    )
    assert (
        plain_hooks.judge(
            request=generation_request(tmp_path / "no-arena", role="blue"),
            recall=RecallResult(),
            generated=empty,
            reviewed=empty,
        ).items
        == ()
    )


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
    assert not any(
        call["path"] in ("/store", "/upsert") for call in fake.calls
    )


# Real /memory daemon ack shapes, captured live 2026-07-24 against
# http://127.0.0.1:8601. The daemon does NOT return {"ok": true}; it returns
# these two shapes. _require_write_ack must accept both, or every real write
# raises even though it persisted (confirmed live: POST /list showed total:1
# after an upsert whose ack the pre-fix check rejected).
def test_require_write_ack_accepts_real_store_daemon_shape() -> None:
    MemoryBackend._require_write_ack(
        "/store",
        {
            "stored": True,
            "collection": COLLECTION,
            "_key": "k",
            "deprecated": True,
        },
    )


def test_require_write_ack_accepts_real_upsert_daemon_shape() -> None:
    for applied in ({"inserted": 1, "updated": 0}, {"inserted": 0, "updated": 1}):
        MemoryBackend._require_write_ack(
            "/upsert",
            {
                "collection": COLLECTION,
                **applied,
                "errors": [],
                "total": 1,
                "writeahead_path": "artifacts/memory_upsert_writeahead/x.jsonl",
            },
        )


def test_require_write_ack_rejects_upsert_with_per_document_errors() -> None:
    with pytest.raises(AdaptiveLineageContractError):
        MemoryBackend._require_write_ack(
            "/upsert",
            {"inserted": 0, "updated": 0, "errors": ["boom"], "total": 1},
        )


def test_require_write_ack_rejects_upsert_that_wrote_nothing() -> None:
    with pytest.raises(AdaptiveLineageContractError):
        MemoryBackend._require_write_ack(
            "/upsert",
            {"inserted": 0, "updated": 0, "errors": [], "total": 0},
        )
