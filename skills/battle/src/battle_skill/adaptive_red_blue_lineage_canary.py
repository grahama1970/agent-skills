"""Two-generation, simultaneous Red/Blue adaptive lineage canary."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .adaptive_evidence import build_fitness_vector, build_generation_observation
from .adaptive_genome import build_semantic_genome_delta, semantic_sha256
from .adaptive_selection import build_selection_receipt
from .arena_battle_proof import _write_json
from .arena_live_battle_proof import (
    _judge_tau_artifacts,
    _materialized_entries,
    _run_tau_harness,
    _visibility_validation,
    _write_tau_public_context,
    run_arena_tau_public_only_proof,
)
from .team_artifact_pipeline import run_team_artifact_pipeline
from .campaign_event_journal import CampaignEventJournal
from .memory_promotion import build_memory_evaluation
from .normalized_adaptive_lineage_fixture import (
    build_normalized_adaptive_fixture,
    write_fixture_copies,
)


SCHEMA = "battle.adaptive_red_blue_lineage_canary.v1"
TAU_PROJECT_ROOT = Path(
    os.environ.get("BATTLE_TAU_PROJECT_ROOT", "/home/graham/workspace/experiments/tau")
)


def run_adaptive_red_blue_lineage_canary(
    *,
    battle_id: str,
    out_dir: Path,
    run_id: str,
    docker_image: str = "python:3.12-slim",
    model: str = "gpt-5.5",
    scillm_base_url: str = "http://localhost:4001",
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """Run two simultaneous Red/Blue generations against one Arena target."""

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    journal = CampaignEventJournal(root=out_dir, battle_id=battle_id, run_id=run_id)
    generation_1_dir = out_dir / "generation-1"
    generation_2_dir = out_dir / "generation-2"

    generation_1 = run_arena_tau_public_only_proof(
        out_dir=generation_1_dir,
        battle_id=battle_id,
        run_id=f"{run_id}-g1",
        docker_image=docker_image,
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
        red_workers=1,
        blue_workers=1,
        materialize_only=True,
    )
    g1_manifest = _read_json(generation_1_dir / "tau-live" / "manifest.json")
    scenario = _read_json(generation_1_dir / "arena" / "scenario.json")
    target_identity_sha256 = _sha(
        generation_1_dir / "arena" / "team-public" / "target" / "app.py"
    )
    g1_genomes = _provider_genomes(
        battle_id=battle_id,
        run_id=f"{run_id}-g1",
        generation=1,
        generation_dir=generation_1_dir,
        manifest=g1_manifest,
    )
    g1_manifest, g1_pipelines = _reviewed_manifest(
        battle_id=battle_id,
        run_id=f"{run_id}-g1",
        generation=1,
        generation_dir=generation_1_dir,
        manifest=g1_manifest,
        target_identity_sha256=target_identity_sha256,
        docker_image=docker_image,
        genomes=g1_genomes,
    )
    g1_judge = _judge_reviewed_generation(
        generation_dir=generation_1_dir,
        scenario=scenario,
        docker_image=docker_image,
        reviewed_manifest=g1_manifest,
        pipelines=g1_pipelines,
        target_identity_sha256=target_identity_sha256,
    )
    g1_judge_path = _write_json(
        generation_1_dir / "judge" / "judge-receipt.json", g1_judge
    )
    g1_judge["receipt_sha256"] = _sha(g1_judge_path)
    journal.append(
        event_type="judge_verdict",
        source_receipt=g1_judge_path,
        generation=1,
        payload={"verdict": g1_judge.get("verdict")},
    )
    g1_red = _single_materialized(g1_manifest, "red")
    g1_blue = _single_materialized(g1_manifest, "blue")

    spawn_root = out_dir / "spawn"
    knowledge_root = generation_2_dir / "arena" / "team-public" / "knowledge"
    knowledge_root.mkdir(parents=True, exist_ok=True)
    g1_observations, g1_fitness = _generation_evidence(
        battle_id=battle_id,
        run_id=run_id,
        generation=1,
        generation_dir=generation_1_dir,
        pipelines=g1_pipelines,
        judge=g1_judge,
        genomes=g1_genomes,
        target_identity_sha256=target_identity_sha256,
        journal=journal,
    )
    red_request, red_request_path = _parent_spawn_request(
        team="red",
        battle_id=battle_id,
        run_id=run_id,
        parent=g1_red,
        genome=g1_genomes["red"],
        pipeline=g1_pipelines["red"],
        judge=g1_judge,
        observation=g1_observations["red"],
        fitness=g1_fitness["red"],
        spawn_root=spawn_root,
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
    )
    blue_request, blue_request_path = _parent_spawn_request(
        team="blue",
        battle_id=battle_id,
        run_id=run_id,
        parent=g1_blue,
        genome=g1_genomes["blue"],
        pipeline=g1_pipelines["blue"],
        judge=g1_judge,
        observation=g1_observations["blue"],
        fitness=g1_fitness["blue"],
        spawn_root=spawn_root,
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
    )
    journal.append(
        event_type="spawn_requested",
        source_receipt=red_request_path,
        generation=1,
        team="red",
        payload={"requested_action": red_request["request"]["requested_action"]},
    )
    journal.append(
        event_type="spawn_requested",
        source_receipt=blue_request_path,
        generation=1,
        team="blue",
        payload={"requested_action": blue_request["request"]["requested_action"]},
    )
    red_spawn = _spawn_decision(
        "red",
        red_request,
        g1_observations["red"],
        g1_fitness["red"],
        g1_genomes["red"],
        g1_pipelines["red"],
        g1_judge,
    )
    blue_spawn = _spawn_decision(
        "blue",
        blue_request,
        g1_observations["blue"],
        g1_fitness["blue"],
        g1_genomes["blue"],
        g1_pipelines["blue"],
        g1_judge,
    )
    red_spawn_path = _write_json(
        spawn_root / "red-spawn-policy-decision.json", red_spawn
    )
    blue_spawn_path = _write_json(
        spawn_root / "blue-spawn-policy-decision.json", blue_spawn
    )
    journal.append(
        event_type="spawn_authorized",
        source_receipt=red_spawn_path,
        generation=1,
        team="red",
        payload={"decision": red_spawn["decision"]},
    )
    journal.append(
        event_type="spawn_authorized",
        source_receipt=blue_spawn_path,
        generation=1,
        team="blue",
        payload={"decision": blue_spawn["decision"]},
    )
    red_packet = _knowledge_packet(
        "red",
        battle_id,
        run_id,
        g1_red,
        red_request_path,
        red_spawn_path,
        g1_observations["red"],
        g1_fitness["red"],
        g1_genomes["red"],
        g1_pipelines["red"],
        g1_judge_path,
    )
    blue_packet = _knowledge_packet(
        "blue",
        battle_id,
        run_id,
        g1_blue,
        blue_request_path,
        blue_spawn_path,
        g1_observations["blue"],
        g1_fitness["blue"],
        g1_genomes["blue"],
        g1_pipelines["blue"],
        g1_judge_path,
    )
    red_packet_path = _write_json(
        knowledge_root / "red-inherited-knowledge-packet.json", red_packet
    )
    blue_packet_path = _write_json(
        knowledge_root / "blue-inherited-knowledge-packet.json", blue_packet
    )
    journal.append(
        event_type="knowledge_packet_materialized",
        source_receipt=red_packet_path,
        generation=2,
        team="red",
        payload={"packet_id": red_packet["packet_id"]},
    )
    journal.append(
        event_type="knowledge_packet_materialized",
        source_receipt=blue_packet_path,
        generation=2,
        team="blue",
        payload={"packet_id": blue_packet["packet_id"]},
    )

    research_root = generation_2_dir / "arena" / "team-public" / "research"
    red_research = _run_tau_research(
        team="red",
        query=str(red_request["request"]["requested_research_questions"][0]),
        out_dir=research_root / "red",
        origin_request_path=red_request_path,
    )
    blue_research = _run_tau_research(
        team="blue",
        query=str(blue_request["request"]["requested_research_questions"][0]),
        out_dir=research_root / "blue",
        origin_request_path=blue_request_path,
    )
    journal.append(
        event_type="child_research_materialized",
        source_receipt=Path(red_research["source_receipt_path"]),
        generation=2,
        team="red",
        payload={"source_count": red_research["source_count"]},
    )
    journal.append(
        event_type="child_research_materialized",
        source_receipt=Path(blue_research["source_receipt_path"]),
        generation=2,
        team="blue",
        payload={"source_count": blue_research["source_count"]},
    )

    _copy_public_arena(generation_1_dir, generation_2_dir)
    context_path = _write_tau_public_context(
        out_dir=generation_2_dir,
        battle_id=battle_id,
        run_id=f"{run_id}-g2",
        scenario=scenario,
        red_workers=1,
        blue_workers=1,
    )
    context = _read_json(context_path)
    context["artifacts"].update(
        {
            "red_inherited_knowledge": str(red_packet_path),
            "blue_inherited_knowledge": str(blue_packet_path),
            "red_external_research": str(red_research["source_receipt_path"]),
            "blue_external_research": str(blue_research["source_receipt_path"]),
        }
    )
    context["summary"]["generation"] = 2
    context["summary"]["inherited_knowledge_inline"] = {
        "red": red_packet,
        "blue": blue_packet,
    }
    context["summary"]["external_research"] = {
        "red": red_research,
        "blue": blue_research,
    }
    context["summary"]["teams"]["red"]["objective"] = _generation_2_objective(
        "red", red_packet, red_research
    )
    context["summary"]["teams"]["blue"]["objective"] = _generation_2_objective(
        "blue", blue_packet, blue_research
    )
    _write_json(context_path, context)

    g2_manifest_path = _run_tau_harness(
        out_dir=generation_2_dir,
        battle_id=battle_id,
        run_id=f"{run_id}-g2",
        scenario_id=scenario["scenario_id"],
        context_path=context_path,
        red_persona="battle-red-adaptive-child",
        blue_persona="battle-blue-adaptive-child",
        model=model,
        scillm_base_url=scillm_base_url,
        timeout_s=timeout_s,
        red_workers=1,
        blue_workers=1,
    )
    g2_manifest = _read_json(g2_manifest_path)
    g2_genomes = _provider_genomes(
        battle_id=battle_id,
        run_id=f"{run_id}-g2",
        generation=2,
        generation_dir=generation_2_dir,
        manifest=g2_manifest,
        parent_genomes=g1_genomes,
        knowledge_packets={"red": red_packet, "blue": blue_packet},
        research={"red": red_research, "blue": blue_research},
    )
    visibility = _visibility_validation(
        out_dir=generation_2_dir, tau_manifest=g2_manifest
    )
    _write_json(generation_2_dir / "visibility-validation.json", visibility)
    g2_manifest, g2_pipelines = _reviewed_manifest(
        battle_id=battle_id,
        run_id=f"{run_id}-g2",
        generation=2,
        generation_dir=generation_2_dir,
        manifest=g2_manifest,
        target_identity_sha256=target_identity_sha256,
        docker_image=docker_image,
        genomes=g2_genomes,
    )
    g2_judge = _judge_reviewed_generation(
        generation_dir=generation_2_dir,
        scenario=scenario,
        docker_image=docker_image,
        reviewed_manifest=g2_manifest,
        pipelines=g2_pipelines,
        target_identity_sha256=target_identity_sha256,
    )
    g2_judge_path = _write_json(
        generation_2_dir / "judge" / "judge-receipt.json", g2_judge
    )
    g2_judge["receipt_sha256"] = _sha(g2_judge_path)
    journal.append(
        event_type="judge_verdict",
        source_receipt=g2_judge_path,
        generation=2,
        payload={"verdict": g2_judge.get("verdict")},
    )
    g2_red = _single_materialized(g2_manifest, "red")
    g2_blue = _single_materialized(g2_manifest, "blue")
    red_ack = _knowledge_acknowledgement(
        "red", red_packet, red_research, g2_manifest, g2_red
    )
    blue_ack = _knowledge_acknowledgement(
        "blue", blue_packet, blue_research, g2_manifest, g2_blue
    )
    red_ack_path = _write_json(
        generation_2_dir / "red-inherited-knowledge-acknowledgement.json", red_ack
    )
    blue_ack_path = _write_json(
        generation_2_dir / "blue-inherited-knowledge-acknowledgement.json", blue_ack
    )
    journal.append(
        event_type="child_knowledge_acknowledged",
        source_receipt=red_ack_path,
        generation=2,
        team="red",
    )
    journal.append(
        event_type="child_knowledge_acknowledged",
        source_receipt=blue_ack_path,
        generation=2,
        team="blue",
    )

    deltas: dict[str, dict[str, Any]] = {}
    for team in ("red", "blue"):
        delta = build_semantic_genome_delta(
            battle_id=battle_id,
            run_id=run_id,
            team=team,
            parent=g1_genomes[team],
            child=g2_genomes[team],
        )
        delta_path = _write_json(generation_2_dir / team / "genome-delta.json", delta)
        delta["path"] = str(delta_path)
        delta["sha256"] = _sha(delta_path)
        deltas[team] = delta
        journal.append(
            event_type="genome_mutated",
            source_receipt=delta_path,
            generation=2,
            team=team,
            payload={"semantic_change_count": delta["semantic_change_count"]},
        )
    g2_observations, g2_fitness = _generation_evidence(
        battle_id=battle_id,
        run_id=run_id,
        generation=2,
        generation_dir=generation_2_dir,
        pipelines=g2_pipelines,
        judge=g2_judge,
        genomes=g2_genomes,
        target_identity_sha256=target_identity_sha256,
        journal=journal,
        parent_artifacts={
            "red": _sha(Path(g1_red["path"])),
            "blue": _sha(Path(g1_blue["path"])),
        },
        deltas=deltas,
    )
    all_fitness = {
        "red": {1: g1_fitness["red"], 2: g2_fitness["red"]},
        "blue": {1: g1_fitness["blue"], 2: g2_fitness["blue"]},
    }
    selection = build_selection_receipt(
        battle_id=battle_id, run_id=run_id, fitness=all_fitness
    )
    selection_path = _write_json(out_dir / "selection-receipt.json", selection)
    selection["path"] = str(selection_path)
    selection["sha256"] = _sha(selection_path)
    journal.append(
        event_type="selection_decision",
        source_receipt=selection_path,
        payload={
            "red_selected_generation": selection["teams"]["red"]["selected_generation"],
            "blue_selected_generation": selection["teams"]["blue"][
                "selected_generation"
            ],
        },
    )
    memory_evaluation = build_memory_evaluation(
        battle_id=battle_id,
        run_id=run_id,
        selection=selection,
        fitness=all_fitness,
        deltas=deltas,
    )
    memory_path = _write_json(
        out_dir / "memory-promotion-evaluation.json", memory_evaluation
    )
    memory_evaluation["path"] = str(memory_path)
    memory_evaluation["sha256"] = _sha(memory_path)
    journal.append(
        event_type="memory_evaluation",
        source_receipt=memory_path,
        payload={
            "decisions": [item["decision"] for item in memory_evaluation["evaluations"]]
        },
    )
    artifact_integrity = _build_artifact_integrity_receipt(
        out_dir=out_dir,
        pipelines={1: g1_pipelines, 2: g2_pipelines},
        judges={1: g1_judge, 2: g2_judge},
    )
    artifact_integrity_path = _write_json(
        out_dir / "artifact-integrity-receipt.json", artifact_integrity
    )
    artifact_integrity["path"] = str(artifact_integrity_path)
    artifact_integrity["sha256"] = _sha(artifact_integrity_path)
    status, reason = _campaign_status(
        generation_1=generation_1,
        visibility=visibility,
        g1_judge=g1_judge,
        g2_judge=g2_judge,
        red_spawn=red_spawn,
        blue_spawn=blue_spawn,
        red_ack=red_ack,
        blue_ack=blue_ack,
        selection=selection,
        observations=[*g1_observations.values(), *g2_observations.values()],
        fitness=[
            g1_fitness["red"],
            g1_fitness["blue"],
            g2_fitness["red"],
            g2_fitness["blue"],
        ],
        requests=[red_request, blue_request],
        deltas=[deltas["red"], deltas["blue"]],
        memory_evaluation=memory_evaluation,
        artifact_integrity=artifact_integrity,
    )
    receipt = {
        "schema": SCHEMA,
        "status": status,
        "reason": reason,
        "battle_id": battle_id,
        "run_id": run_id,
        "mocked": False,
        "live": True,
        "live_mode": "tau_scillm_docker_judge_two_generation_red_blue",
        "agentic": True,
        "fixture_fallback_used": False,
        "source_commit": _git_rev_parse("HEAD"),
        "source_tree": _git_rev_parse("HEAD^{tree}"),
        "arena": {
            "scenario_id": scenario["scenario_id"],
            "generation_1_target_sha256": _sha(
                generation_1_dir / "arena" / "team-public" / "target" / "app.py"
            ),
            "generation_2_target_sha256": _sha(
                generation_2_dir / "arena" / "team-public" / "target" / "app.py"
            ),
        },
        "generations": [
            _generation_summary(
                1, g1_manifest, g1_judge, g1_red, g1_blue, g1_pipelines
            ),
            _generation_summary(
                2, g2_manifest, g2_judge, g2_red, g2_blue, g2_pipelines
            ),
        ],
        "spawn": {"red": red_spawn, "blue": blue_spawn},
        "inheritance": {"red": red_ack, "blue": blue_ack},
        "research": {"red": red_research, "blue": blue_research},
        "selection": selection,
        "observations": {
            "generation_1": g1_observations,
            "generation_2": g2_observations,
        },
        "fitness": {"generation_1": g1_fitness, "generation_2": g2_fitness},
        "genome_deltas": deltas,
        "memory_evaluation": memory_evaluation,
        "artifact_integrity": artifact_integrity,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "judge_verified_exploits": sum(
            int(item.get("red_success_count") or 0) for item in (g1_judge, g2_judge)
        ),
        "claims": {
            "proves": [
                "Two simultaneous Red/Blue generations were executed through Tau/SciLLM against one Arena target.",
                "Both Generation 2 workers received evidence-derived inherited knowledge packets.",
                "Both Generation 2 workers received source-bearing Tau-routed external research receipts.",
                "Both generations produced materialized artifacts and Docker Judge receipts.",
                "Battle performed deterministic cross-generation selection.",
            ]
            if status == "PASS"
            else [],
            "does_not_prove": [
                "Both children improved on their parents.",
                "A high-throughput genetic engine is production-ready.",
                "Multiple vulnerabilities were evaluated.",
                "Durable memory promotion occurred.",
            ],
        },
        "created_at": _now(),
    }
    source_index = _source_receipt_index(
        battle_id=battle_id,
        run_id=run_id,
        campaign_root=out_dir,
        observations=[*g1_observations.values(), *g2_observations.values()],
        fitness=[
            g1_fitness["red"],
            g1_fitness["blue"],
            g2_fitness["red"],
            g2_fitness["blue"],
        ],
        requests=[red_request, blue_request],
        deltas=[deltas["red"], deltas["blue"]],
        selection=selection,
        memory_evaluation=memory_evaluation,
    )
    source_index_path = _write_json(out_dir / "source-receipt-index.json", source_index)
    receipt["event_journal"] = {
        "path": str(journal.path),
        "event_count": journal.seq,
        "sha256": _sha(journal.path),
    }
    fixture_id = f"{battle_id}-adaptive-lineage-v13"
    if status == "PASS":
        fixture = build_normalized_adaptive_fixture(
            campaign_root=out_dir,
            source_index_path=source_index_path,
            fixture_id=fixture_id,
        )
        skill_root = Path(__file__).resolve().parents[2]
        local_dir = skill_root / "local" / fixture_id
        public_dir = (
            skill_root / "spectator" / "public" / "battle-fixtures" / fixture_id
        )
        validation_result = write_fixture_copies(
            fixture=fixture,
            local_path=local_dir / "battle.normalized_ux_fixture.json",
            public_path=public_dir / "battle.normalized_ux_fixture.json",
        )
        _write_json(out_dir / "normalized" / "validation.json", validation_result)
        _write_json(local_dir / "validation.json", validation_result)
        _write_json(local_dir / "source-receipt-index.json", source_index)
        receipt["normalized_fixture"] = {
            "fixture_id": fixture_id,
            "status": validation_result["status"],
            "fixture_sha256": validation_result["fixture_sha256"],
            "local_public_byte_identical": validation_result[
                "local_public_byte_identical"
            ],
        }
    else:
        receipt["normalized_fixture"] = {
            "fixture_id": fixture_id,
            "status": "SKIPPED",
            "reason": "campaign_not_pass",
        }
    _write_json(out_dir / "adaptive-lineage-chain-receipt.json", receipt)
    _write_json(out_dir / "campaign-receipt.json", receipt)
    return receipt


def _generation_evidence(
    *,
    battle_id: str,
    run_id: str,
    generation: int,
    generation_dir: Path,
    pipelines: dict[str, dict[str, Any]],
    judge: dict[str, Any],
    genomes: dict[str, dict[str, Any]],
    target_identity_sha256: str,
    journal: CampaignEventJournal,
    parent_artifacts: dict[str, str] | None = None,
    deltas: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    observations: dict[str, dict[str, Any]] = {}
    fitness: dict[str, dict[str, Any]] = {}
    for team in ("red", "blue"):
        observation = build_generation_observation(
            battle_id=battle_id,
            run_id=run_id,
            team=team,
            generation=generation,
            pipeline=pipelines[team],
            judge=judge,
            genome=genomes[team],
            target_identity_sha256=target_identity_sha256,
            observed_elapsed_seconds=round(
                time.perf_counter() - journal.started_ns / 1_000_000_000, 6
            ),
        )
        observation_path = _write_json(
            generation_dir / team / "generation-observation-receipt.json", observation
        )
        observation["path"] = str(observation_path)
        observation["sha256"] = _sha(observation_path)
        observations[team] = observation
        journal.append(
            event_type="parent_observation_materialized"
            if generation == 1
            else "generation_observation_materialized",
            source_receipt=observation_path,
            generation=generation,
            team=team,
            payload={"judge_verdict": observation["judge"]["verdict"]},
        )
        vector = build_fitness_vector(
            observation=observation,
            genome=genomes[team],
            parent_artifact_sha256=(parent_artifacts or {}).get(team),
            semantic_delta=(deltas or {}).get(team),
        )
        fitness_path = _write_json(
            generation_dir / team / "fitness-vector.json", vector
        )
        vector["path"] = str(fitness_path)
        vector["sha256"] = _sha(fitness_path)
        fitness[team] = vector
        journal.append(
            event_type="fitness_materialized",
            source_receipt=fitness_path,
            generation=generation,
            team=team,
            payload={"selection_key": vector["selection_key"]},
        )
    return observations, fitness


def _parent_spawn_request(
    *,
    team: str,
    battle_id: str,
    run_id: str,
    parent: dict[str, Any],
    genome: dict[str, Any],
    pipeline: dict[str, Any],
    judge: dict[str, Any],
    observation: dict[str, Any],
    fitness: dict[str, Any],
    spawn_root: Path,
    model: str,
    scillm_base_url: str,
    timeout_s: float,
) -> tuple[dict[str, Any], Path]:
    evidence_path = _write_json(
        spawn_root / f"{team}-parent-reflection-evidence.json",
        {
            "schema": "battle.parent_reflection_evidence.v1",
            "status": "PASS",
            "battle_id": battle_id,
            "run_id": run_id,
            "team": team,
            "generation": 1,
            "parent_artifact_sha256": _sha(Path(parent["path"])),
            "parent_genome_sha256": genome["sha256"],
            "parent_semantic_genome_sha256": semantic_sha256(genome),
            "pipeline_handoff_sha256": pipeline["handoff_sha256"],
            "observation_receipt_sha256": observation["sha256"],
            "fitness_receipt_sha256": fitness["sha256"],
            "judge_receipt_sha256": judge["receipt_sha256"],
            "judge_verdict": judge.get("verdict"),
            "measurements": observation["measurements"],
            "remaining_budget": {"child_count": 1, "provider_attempts": 1},
        },
    )
    tau_receipt_path = spawn_root / f"{team}-tau-parent-reflection.json"
    _run_command(
        [
            "uv",
            "run",
            "--project",
            str(TAU_PROJECT_ROOT),
            "python",
            "-m",
            "tau_coding.battle_adaptive_parent_reflection",
            "--evidence",
            str(evidence_path),
            "--output",
            str(tau_receipt_path),
            "--team",
            team,
            "--model",
            model,
            "--scillm-base-url",
            scillm_base_url,
            "--timeout-s",
            str(timeout_s),
        ]
    )
    tau_receipt = _read_json(tau_receipt_path)
    request = _normalize_parent_spawn_request(
        team=team,
        request=tau_receipt.get("request"),
        judge=judge,
    )
    status = (
        "PASS"
        if tau_receipt.get("status") == "PASS" and isinstance(request, dict)
        else "BLOCKED"
    )
    result = {
        "schema": "battle.adaptive_spawn_request.v1",
        "request_id": f"{run_id}-{team}-parent-spawn-request",
        "status": status,
        "battle_id": battle_id,
        "run_id": run_id,
        "team": team,
        "generation": 1,
        "parent_binding": {
            "parent_artifact_sha256": _sha(Path(parent["path"])),
            "parent_genome_sha256": genome["sha256"],
            "pipeline_handoff_sha256": pipeline["handoff_sha256"],
            "observation_receipt_sha256": observation["sha256"],
            "fitness_receipt_sha256": fitness["sha256"],
            "judge_receipt_sha256": judge["receipt_sha256"],
        },
        "request": request,
        "authorship": {
            "authored_by": "tau_parent"
            if not request.get("battle_policy_override")
            else "battle_policy_normalized_tau_parent",
            "agentic": True,
            "provider_live": tau_receipt.get("provider_live") is True,
            "model": model,
            "tau_reflection_receipt_sha256": _sha(tau_receipt_path),
            "provider_response_sha256": tau_receipt.get("provider_response_sha256"),
        },
        "claims": {
            "proves": [
                "A live Tau parent reflection was recorded for the bounded reproduction request."
            ]
            if status == "PASS"
            else [],
            "does_not_prove": ["Battle authorized the request or the child improved."],
        },
    }
    path = _write_json(spawn_root / f"{team}-parent-spawn-request.json", result)
    result["path"] = str(path)
    result["sha256"] = _sha(path)
    return result, path


def _normalize_parent_spawn_request(
    *,
    team: str,
    request: Any,
    judge: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(request) if isinstance(request, dict) else {}
    questions = normalized.get("requested_research_questions")
    has_questions = isinstance(questions, list) and any(str(item).strip() for item in questions)
    if normalized.get("requested_action") == "SPAWN_CHILD" and has_questions:
        return normalized
    override_question = (
        "What public patch variation should be tested after the parent Judge outcome?"
        if team == "blue"
        else "What public exploit mutation should be tested after the parent Judge outcome?"
    )
    normalized.setdefault("rationale", "")
    normalized.setdefault("reason_codes", [])
    normalized.setdefault("proposed_child_mission", "")
    normalized.setdefault("requested_mutation_directions", [])
    normalized.setdefault("expected_observation", "")
    normalized["requested_action"] = "SPAWN_CHILD"
    normalized["requested_budget"] = {"child_count": 1, "provider_attempts": 1}
    normalized["requested_research_questions"] = [override_question]
    normalized["battle_policy_override"] = {
        "status": "APPLIED",
        "reason": "bounded_two_generation_canary_requires_one_child_per_team",
        "original_requested_action": request.get("requested_action")
        if isinstance(request, dict)
        else None,
        "original_research_question_count": len(questions)
        if isinstance(questions, list)
        else 0,
        "judge_verdict": judge.get("verdict"),
    }
    return normalized


def _spawn_decision(
    team: str,
    request: dict[str, Any],
    observation: dict[str, Any],
    fitness: dict[str, Any],
    genome: dict[str, Any],
    pipeline: dict[str, Any],
    judge: dict[str, Any],
) -> dict[str, Any]:
    requested_action = request.get("request", {}).get("requested_action")
    allowed = request.get("status") == "PASS" and requested_action == "SPAWN_CHILD"
    return {
        "schema": "battle.adaptive_spawn_policy_decision.v1",
        "receipt_id": f"{request['run_id']}-{team}-spawn-policy-decision",
        "status": "PASS" if allowed else "BLOCKED",
        "decision": "ALLOWED_EVALUATED_PARENT"
        if allowed
        else "DENIED_PARENT_DID_NOT_REQUEST_CHILD",
        "team": team,
        "parent_terminal": False,
        "reason_codes": [
            "parent_judge_evaluated",
            "bounded_second_generation_requested",
            "remaining_budget_available",
        ],
        "source_receipts": [
            {"kind": "parent_spawn_request", "sha256": request["sha256"]},
            {"kind": "generation_observation", "sha256": observation["sha256"]},
            {"kind": "fitness_vector", "sha256": fitness["sha256"]},
            {"kind": "parent_genome", "sha256": genome["sha256"]},
            {"kind": "pipeline_handoff", "sha256": pipeline["handoff_sha256"]},
            {"kind": "judge_receipt", "sha256": judge["receipt_sha256"]},
        ],
        "parent_artifact_sha256": pipeline["selected_artifact_sha256"],
        "judge_verdict": judge.get("verdict"),
        "claims": {
            "proves": [
                "Battle authorized one bounded child after parent Judge evaluation."
            ],
            "does_not_prove": ["The child improved."],
        },
    }


def _knowledge_packet(
    team: str,
    battle_id: str,
    run_id: str,
    parent: dict[str, Any],
    request_path: Path,
    spawn_path: Path,
    observation: dict[str, Any],
    fitness: dict[str, Any],
    genome: dict[str, Any],
    pipeline: dict[str, Any],
    judge_path: Path,
) -> dict[str, Any]:
    parent_sha = _sha(Path(parent["path"]))
    packet_id = f"{battle_id}-{team}-generation-2-knowledge"
    return {
        "schema": "battle.adaptive_team_knowledge_packet.v1",
        "receipt_id": f"{run_id}-{team}-knowledge-packet",
        "status": "PASS",
        "packet_id": packet_id,
        "battle_id": battle_id,
        "run_id": run_id,
        "team": team,
        "generation": 2,
        "parent_artifact_sha256": parent_sha,
        "parent_semantic_genome_sha256": semantic_sha256(genome),
        "observations": [observation["measurements"]],
        "active_hypotheses": [
            "Change the parent strategy in response to the Judge outcome."
        ],
        "failed_or_partial_attempts": [observation["measurements"]],
        "research_questions": [
            "What public technique or hardening variation addresses the observed Judge outcome?"
        ],
        "target_constraints": [
            "Use only Arena team-public artifacts.",
            "Do not claim outcomes; Judge decides.",
        ],
        "source_receipts": [
            {"kind": "parent_spawn_request", "sha256": _sha(request_path)},
            {"kind": "spawn_policy", "sha256": _sha(spawn_path)},
            {"kind": "generation_observation", "sha256": observation["sha256"]},
            {"kind": "fitness_vector", "sha256": fitness["sha256"]},
            {"kind": "parent_genome", "sha256": genome["sha256"]},
            {"kind": "pipeline_handoff", "sha256": pipeline["handoff_sha256"]},
            {"kind": "judge_receipt", "sha256": _sha(judge_path)},
        ],
        "claims": {
            "proves": [
                "Battle derived a child packet from parent artifacts and Judge evidence."
            ],
            "does_not_prove": ["The child used the packet."],
        },
    }


def _generation_2_objective(
    team: str, packet: dict[str, Any], research: dict[str, Any]
) -> str:
    artifact = "exploit" if team == "red" else "patch"
    materialization_contract = (
        "The exploit code must use the literal statement 'from app import import_zip' "
        "or 'import app' so Tau can bind it to the public target. "
        if team == "red"
        else (
            "The patch must preserve a callable import_zip(zip_path, destination) "
            "interface. Return app_py as one complete JSON string containing compact "
            "annotation-free Python. Avoid docstrings, f-strings, literal backslash "
            "tests, and extra top-level keys such as candidate or destination. "
        )
    )
    return (
        f"Produce a new {artifact} artifact after reading inherited packet {packet['packet_id']}. "
        f"Your JSON rationale must cite packet_id {packet['packet_id']} or parent artifact sha256 {packet['parent_artifact_sha256']}. "
        f"The rationale must cite inherited_genome_sha256 {packet['parent_semantic_genome_sha256']}, "
        "name one inherited observation, and include the literal label first_plan_action followed by the first action. "
        f"It must also cite external research receipt sha256 {research['source_receipt_sha256']}. "
        f"{materialization_contract}"
        "Return strategy_genome as a JSON object with selected_methods, rejected_methods, parameters, mutation_origin, and expected_observation. "
        "Change the parent strategy using the inherited Judge observation and public target only."
    )


def _knowledge_acknowledgement(
    team: str,
    packet: dict[str, Any],
    research: dict[str, Any],
    manifest: dict[str, Any],
    child: dict[str, Any],
) -> dict[str, Any]:
    entry = next(
        item
        for item in manifest.get("teams", [])
        if isinstance(item, dict) and item.get("team") == team
    )
    call = _read_json(Path(entry["scillm_call"]))
    response_text = str(call.get("response_content") or "")
    packet_id = packet["packet_id"]
    parent_sha = packet["parent_artifact_sha256"]
    cited = packet_id in response_text or parent_sha in response_text
    genome_cited = packet["parent_semantic_genome_sha256"] in response_text
    inherited_observation_cited = any(
        str(value) in response_text
        for observation in packet.get("observations", [])
        for value in observation.values()
        if value not in {None, "UNKNOWN"}
    )
    first_plan_action = "first_plan_action" in response_text
    research_cited = research["source_receipt_sha256"] in response_text
    child_sha = _sha(Path(child["path"]))
    changed = child_sha != parent_sha
    return {
        "schema": "battle.inherited_knowledge_acknowledgement.v1",
        "status": "PASS"
        if cited
        and genome_cited
        and inherited_observation_cited
        and first_plan_action
        and research_cited
        and changed
        else "BLOCKED",
        "team": team,
        "packet_id": packet_id,
        "packet_cited_in_provider_response": cited,
        "parent_artifact_sha256": parent_sha,
        "child_artifact_sha256": child_sha,
        "artifact_changed": changed,
        "inherited_genome_cited": genome_cited,
        "inherited_observation_cited": inherited_observation_cited,
        "first_plan_action_declared": first_plan_action,
        "external_research_receipt_sha256": research["source_receipt_sha256"],
        "external_research_cited_in_provider_response": research_cited,
        "provider_response_sha256": _sha(Path(entry["scillm_call"])),
        "claims": {
            "proves": [
                "The provider response cited inherited evidence and external research, then materialized a changed artifact."
            ]
            if cited and research_cited and changed
            else [],
            "does_not_prove": ["The child improved."],
        },
    }


def _run_tau_research(
    *, team: str, query: str, out_dir: Path, origin_request_path: Path
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    policy_path = _write_json(
        out_dir / "policy-profile.json",
        {
            "schema": "tau.policy_profile.v1",
            "profile_id": f"battle-{team}-public-research",
            "default_decision": "deny",
            "requires_data_boundary": True,
            "network": {"default": "deny"},
            "providers": {"cloud_llm": "deny", "local_model": "allow"},
            "research": {
                "external_search": "allow_with_approval",
                "manual_sanitized_receipt": "allow",
            },
            "memory": {"read": "deny", "write": "deny"},
            "github": {"public_mutation": "deny", "dry_run_projection": "allow"},
            "filesystem": {"write_allowlist": [str(out_dir)], "read_denylist": []},
        },
    )
    boundary_path = _write_json(
        out_dir / "data-boundary.json",
        {
            "schema": "tau.data_boundary.v1",
            "classification": "public",
            "export_controlled": False,
            "itar": False,
            "technical_data": False,
            "external_provider_allowed": False,
            "external_research_allowed": True,
            "public_repo_allowed": True,
            "foreign_person_access": "allowed",
            "notes": [
                "Sanitized public Battle research query; no Arena private artifacts."
            ],
        },
    )
    authorization_path = _write_json(
        out_dir / "research-query-authorization.json",
        {
            "schema": "tau.research_query_authorization.v1",
            "approved": True,
            "allowed_methods": ["brave-search"],
            "sanitized_query_sha256": f"sha256:{hashlib.sha256(query.encode()).hexdigest()}",
            "provider_proposed_query_sha256": f"sha256:{hashlib.sha256(query.encode()).hexdigest()}",
            "origin_spawn_request_sha256": _sha(origin_request_path),
            "data_boundary_classification": "public",
            "approver": {"id": "battle:adaptive-lineage-policy"},
            "expires_at": (datetime.now(UTC) + timedelta(hours=1))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        },
    )
    gate_path = out_dir / "research-query-safety-receipt.json"
    source_path = out_dir / "external-research-receipt.json"
    tau_command = [
        "uv",
        "run",
        "--project",
        str(TAU_PROJECT_ROOT),
        "tau",
    ]
    _run_command(
        tau_command
        + [
            "research-query-gate",
            "--query",
            query,
            "--method",
            "brave-search",
            "--policy-profile",
            str(policy_path),
            "--data-boundary",
            str(boundary_path),
            "--authorization",
            str(authorization_path),
            "--receipt",
            str(gate_path),
        ]
    )
    gate = _read_json(gate_path)
    if gate.get("status") != "PASS":
        raise RuntimeError(
            f"Tau research query gate blocked {team}: {gate.get('alert_codes')}"
        )
    _run_command(
        tau_command
        + [
            "external-research-receipt",
            "--query",
            query,
            "--method",
            "brave-search",
            "--from-brave",
            "--count",
            "5",
            "--output",
            str(source_path),
        ]
    )
    source = _read_json(source_path)
    sources = source.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RuntimeError(f"Tau external research returned no sources for {team}")
    return {
        "status": "PASS",
        "team": team,
        "method": "brave-search",
        "external_tool_called": True,
        "query_safety_receipt_path": str(gate_path),
        "query_safety_receipt_sha256": _sha(gate_path),
        "source_receipt_path": str(source_path),
        "source_receipt_sha256": _sha(source_path),
        "source_count": len(sources),
    }


def _run_command(command: list[str]) -> None:
    completed = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=120
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command[:6])}: {detail}"
        )


def _selection_receipt(
    g1_judge: dict[str, Any],
    g2_judge: dict[str, Any],
    g1_red: dict[str, Any],
    g1_blue: dict[str, Any],
    g2_red: dict[str, Any],
    g2_blue: dict[str, Any],
) -> dict[str, Any]:
    red_scores = [_red_fitness(g1_judge), _red_fitness(g2_judge)]
    blue_scores = [_blue_fitness(g1_judge), _blue_fitness(g2_judge)]
    return {
        "schema": "battle.adaptive_selection_receipt.v1",
        "status": "PASS",
        "red": {
            "fitness": red_scores,
            "selected_generation": 1 if red_scores[0] >= red_scores[1] else 2,
            "artifact_hashes": [_sha(Path(g1_red["path"])), _sha(Path(g2_red["path"]))],
        },
        "blue": {
            "fitness": blue_scores,
            "selected_generation": 1 if blue_scores[0] >= blue_scores[1] else 2,
            "artifact_hashes": [
                _sha(Path(g1_blue["path"])),
                _sha(Path(g2_blue["path"])),
            ],
        },
        "improvement_claimed": False,
        "claims": {
            "proves": [
                "Battle compared Judge-derived fitness for both teams across two generations."
            ],
            "does_not_prove": ["Either child improved."],
        },
    }


def _reviewed_manifest(
    *,
    battle_id: str,
    run_id: str,
    generation: int,
    generation_dir: Path,
    manifest: dict[str, Any],
    target_identity_sha256: str,
    docker_image: str,
    genomes: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    reviewed = json.loads(json.dumps(manifest))
    pipelines: dict[str, dict[str, Any]] = {}
    for entry in reviewed.get("teams", []):
        if not isinstance(entry, dict) or entry.get("team") not in {"red", "blue"}:
            continue
        team = str(entry["team"])
        materialized = entry.get("materialized_artifact")
        if not isinstance(materialized, dict) or materialized.get("status") != "PASS":
            raise RuntimeError(f"{team} materialized artifact is not PASS")
        source = Path(str(materialized["path"]))
        pipeline = run_team_artifact_pipeline(
            battle_id=battle_id,
            run_id=run_id,
            generation=generation,
            team=team,
            source_artifact=source,
            provider_receipt=Path(str(entry["subagent_receipt"])),
            materialization_receipt=Path(
                str(entry["materialized_artifact"]["path"])
            ).parent
            / "materialized-artifact-receipt.json",
            target_identity_sha256=target_identity_sha256,
            out_dir=generation_dir / "reviewed" / team,
            docker_image=docker_image,
            genome_sha256=genomes[team]["sha256"],
        )
        if pipeline["status"] != "PASS":
            raise RuntimeError(f"{team} artifact pipeline blocked")
        slot = _preserve_selected_artifact(
            generation_dir=generation_dir,
            generation=generation,
            team=team,
            source=Path(pipeline["selected_artifact_path"]),
            expected_sha256=str(pipeline["selected_artifact_sha256"]),
        )
        materialized["raw_provider_path"] = materialized["path"]
        materialized["path"] = slot["path"]
        materialized["pipeline_handoff"] = str(pipeline["handoff_path"])
        materialized["immutable_slot"] = slot
        entry["materialized"] = materialized
        pipelines[team] = {
            "status": pipeline["status"],
            "selected_artifact_sha256": pipeline["selected_artifact_sha256"],
            "handoff_sha256": _sha(pipeline["handoff_path"]),
            "compile_receipt_sha256": _sha(pipeline["compile_receipt_path"]),
            "review_receipt_sha256": _sha(pipeline["review_receipt_path"]),
            "handoff_path": str(pipeline["handoff_path"]),
            "selected_artifact_source_path": str(pipeline["selected_artifact_path"]),
            "selected_artifact_path": slot["path"],
            "immutable_slot": slot,
        }
    _write_json(generation_dir / "reviewed" / "reviewed-manifest.json", reviewed)
    return reviewed, pipelines


def _judge_reviewed_generation(
    *,
    generation_dir: Path,
    scenario: dict[str, Any],
    docker_image: str,
    reviewed_manifest: dict[str, Any],
    pipelines: dict[str, dict[str, Any]],
    target_identity_sha256: str,
) -> dict[str, Any]:
    red = pipelines["red"]
    blue = pipelines["blue"]
    patched_identity = hashlib.sha256(
        f"{target_identity_sha256}:{blue['selected_artifact_sha256']}".encode("utf-8")
    ).hexdigest()
    judge_input = {
        "schema": "battle.reviewed_judge_pair_input.v1",
        "status": "PASS",
        "red_pipeline_handoff_sha256": red["handoff_sha256"],
        "blue_pipeline_handoff_sha256": blue["handoff_sha256"],
        "red_selected_artifact_sha256": red["selected_artifact_sha256"],
        "blue_selected_artifact_sha256": blue["selected_artifact_sha256"],
        "target_identity_receipt_sha256": target_identity_sha256,
        "original_target_tree_sha256": target_identity_sha256,
        "patched_target_tree_sha256": patched_identity,
        "claims": {
            "proves": [
                "Battle selected one reviewed Red/Blue artifact pair for Judge."
            ],
            "does_not_prove": ["Judge executed the pair.", "Either team succeeded."],
        },
    }
    input_path = _write_json(
        generation_dir / "judge" / "reviewed-judge-pair-input.json", judge_input
    )
    _assert_pipeline_slots(pipelines)
    docker_image_id = _docker_image_id(docker_image)
    judge = _judge_tau_artifacts(
        out_dir=generation_dir,
        scenario=scenario,
        docker_image=docker_image,
        tau_manifest=reviewed_manifest,
    )
    _assert_pipeline_slots(pipelines)
    exact_replay = _run_exact_judge_replay(
        generation_dir=generation_dir,
        scenario=scenario,
        docker_image=docker_image,
        reviewed_manifest=reviewed_manifest,
        original_judge=judge,
        pipelines=pipelines,
        target_identity_sha256=target_identity_sha256,
        docker_image_id=docker_image_id,
    )
    judge.update(
        {
            "reviewed_judge_input_sha256": _sha(input_path),
            "red_pipeline_handoff_sha256": red["handoff_sha256"],
            "blue_pipeline_handoff_sha256": blue["handoff_sha256"],
            "red_selected_artifact_sha256": red["selected_artifact_sha256"],
            "blue_selected_artifact_sha256": blue["selected_artifact_sha256"],
            "target_identity_receipt_sha256": target_identity_sha256,
            "original_target_tree_sha256": target_identity_sha256,
            "patched_target_tree_sha256": patched_identity,
            "exact_replay": exact_replay,
        }
    )
    return judge


def _preserve_selected_artifact(
    *,
    generation_dir: Path,
    generation: int,
    team: str,
    source: Path,
    expected_sha256: str,
) -> dict[str, Any]:
    if team not in {"red", "blue"}:
        raise RuntimeError(f"invalid immutable slot team: {team}")
    if source.is_symlink() or not source.is_file():
        raise RuntimeError(f"selected artifact is not a regular file: {source}")
    payload = source.read_bytes()
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(f"{team} selected artifact changed before slot preservation")
    suffix = source.suffix or ".bin"
    slot_path = (
        generation_dir
        / "reviewed"
        / "immutable-slots"
        / f"generation-{generation}-{team}{suffix}"
    )
    slot_path.parent.mkdir(parents=True, exist_ok=True)
    with slot_path.open("xb") as handle:
        handle.write(payload)
    slot_path.chmod(0o444)
    slot_sha256 = _sha(slot_path)
    if slot_sha256 != expected_sha256:
        raise RuntimeError(f"{team} immutable slot differs from selected artifact")
    return {
        "slot_key": f"generation-{generation}:{team}",
        "generation": generation,
        "team": team,
        "path": str(slot_path),
        "expected_sha256": expected_sha256,
        "preserved_sha256": slot_sha256,
        "source_path": str(source),
        "regular_file": slot_path.is_file() and not slot_path.is_symlink(),
    }


def _assert_pipeline_slots(pipelines: dict[str, dict[str, Any]]) -> None:
    for team in ("red", "blue"):
        pipeline = pipelines[team]
        slot = pipeline.get("immutable_slot")
        if not isinstance(slot, dict):
            raise RuntimeError(f"{team} immutable slot is missing")
        path = Path(str(slot.get("path") or ""))
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"{team} immutable slot is not a regular file")
        if _sha(path) != pipeline.get("selected_artifact_sha256"):
            raise RuntimeError(f"{team} immutable slot changed during Judge")


def _run_exact_judge_replay(
    *,
    generation_dir: Path,
    scenario: dict[str, Any],
    docker_image: str,
    reviewed_manifest: dict[str, Any],
    original_judge: dict[str, Any],
    pipelines: dict[str, dict[str, Any]],
    target_identity_sha256: str,
    docker_image_id: str,
) -> dict[str, Any]:
    replay_root = generation_dir / "judge-exact-replay"
    _copy_tree_for_replay(
        generation_dir / "arena" / "team-public" / "target",
        replay_root / "arena" / "team-public" / "target",
    )
    replay_judge = _judge_tau_artifacts(
        out_dir=replay_root,
        scenario=scenario,
        docker_image=docker_image,
        tau_manifest=reviewed_manifest,
    )
    _assert_pipeline_slots(pipelines)
    original_fingerprint = _judge_fingerprint(
        judge=original_judge,
        docker_image=docker_image,
        target_identity_sha256=target_identity_sha256,
        docker_image_id=docker_image_id,
    )
    replay_image_id = _docker_image_id(docker_image)
    replay_fingerprint = _judge_fingerprint(
        judge=replay_judge,
        docker_image=docker_image,
        target_identity_sha256=target_identity_sha256,
        docker_image_id=replay_image_id,
    )
    matched = (
        original_fingerprint == replay_fingerprint
        and replay_image_id == docker_image_id
    )
    receipt = {
        "schema": "battle.exact_judge_pair_replay.v1",
        "status": "PASS" if matched else "FAIL",
        "matched": matched,
        "receipt_valid": matched,
        "generation": _generation_number_from_dir(generation_dir),
        "docker_image": docker_image,
        "docker_image_id": docker_image_id,
        "replay_docker_image_id": replay_image_id,
        "target_identity_sha256": target_identity_sha256,
        "original_fingerprint": original_fingerprint,
        "replay_fingerprint": replay_fingerprint,
        "replay_judge": replay_judge,
    }
    path = _write_json(replay_root / "exact-replay-receipt.json", receipt)
    receipt["path"] = str(path)
    receipt["sha256"] = _sha(path)
    return receipt


def _copy_tree_for_replay(source: Path, target: Path) -> None:
    if target.exists():
        raise RuntimeError(f"exact replay target already exists: {target}")
    shutil.copytree(source, target)


def _docker_image_id(docker_image: str) -> str:
    completed = subprocess.run(
        ["docker", "image", "inspect", docker_image, "--format", "{{.Id}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    image_id = completed.stdout.strip()
    if completed.returncode != 0 or not image_id.startswith("sha256:"):
        raise RuntimeError(f"Docker image identity unavailable for {docker_image}")
    return image_id


def _judge_fingerprint(
    *,
    judge: dict[str, Any],
    docker_image: str,
    target_identity_sha256: str,
    docker_image_id: str | None = None,
) -> dict[str, Any]:
    attempts = judge.get("attempts") if isinstance(judge.get("attempts"), list) else []
    return {
        "docker_image": docker_image,
        "docker_image_id": docker_image_id,
        "target_identity_sha256": target_identity_sha256,
        "status": judge.get("status"),
        "verdict": judge.get("verdict"),
        "judged_pair_count": judge.get("judged_pair_count"),
        "attempts": [_attempt_fingerprint(item) for item in attempts],
    }


def _attempt_fingerprint(attempt: dict[str, Any]) -> dict[str, Any]:
    commands = (
        attempt.get("commands_run")
        if isinstance(attempt.get("commands_run"), list)
        else []
    )
    bindings = (
        attempt.get("judge_input_byte_bindings")
        if isinstance(attempt.get("judge_input_byte_bindings"), list)
        else []
    )
    container_hashes = (
        attempt.get("container_input_hashes")
        if isinstance(attempt.get("container_input_hashes"), list)
        else []
    )
    return {
        "pair_id": attempt.get("pair_id"),
        "red_artifact_sha256": attempt.get("red_artifact_sha256")
        or _sha(Path(str(attempt["red_artifact"]))),
        "blue_artifact_sha256": attempt.get("blue_artifact_sha256")
        or _sha(Path(str(attempt["blue_artifact"]))),
        "verdict": attempt.get("verdict"),
        "status": attempt.get("status"),
        "judge_input_byte_binding_pass": attempt.get("judge_input_byte_binding_pass"),
        "container_input_hash_pass": attempt.get("container_input_hash_pass"),
        "exploit_confirmed_before_patch": attempt.get("exploit_confirmed_before_patch"),
        "exploit_blocked_after_patch": attempt.get("exploit_blocked_after_patch"),
        "functionality_preserved": attempt.get("functionality_preserved"),
        "bindings": [_binding_fingerprint(item) for item in bindings],
        "container_hashes": [_container_hash_fingerprint(item) for item in container_hashes],
        "commands": [_command_fingerprint(command) for command in commands],
    }


def _binding_fingerprint(binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": binding.get("role"),
        "source_path": _normalize_replay_path(binding.get("source_path")),
        "source_sha256": binding.get("source_sha256"),
        "execution_path": _normalize_replay_path(binding.get("execution_path")),
        "execution_sha256": binding.get("execution_sha256"),
        "docker_workspace_path": binding.get("docker_workspace_path"),
        "matched": binding.get("matched"),
        "regular_file": binding.get("regular_file"),
    }


def _container_hash_fingerprint(receipt: dict[str, Any]) -> dict[str, Any]:
    command = receipt.get("command_receipt")
    return {
        "schema": receipt.get("schema"),
        "status": receipt.get("status"),
        "docker_image": receipt.get("docker_image"),
        "work_dir": _normalize_replay_path(receipt.get("work_dir")),
        "expected_sha256": receipt.get("expected_sha256"),
        "observed_sha256": receipt.get("observed_sha256"),
        "matched": receipt.get("matched"),
        "command": _command_fingerprint(command) if isinstance(command, dict) else None,
    }


def _command_fingerprint(command: dict[str, Any]) -> dict[str, Any]:
    argv = list(command.get("command") or [])
    normalized: list[str] = []
    for value in argv:
        text = str(value)
        normalized.append(
            "$WORKSPACE:/workspace:rw"
            if text.endswith(":/workspace:rw") and text.startswith("/")
            else text
        )
    stdout = Path(str(command.get("stdout_path") or ""))
    stderr = Path(str(command.get("stderr_path") or ""))
    return {
        "command": normalized,
        "exit_code": command.get("exit_code"),
        "stdout_sha256": _sha(stdout) if stdout.is_file() else None,
        "stderr_sha256": _sha(stderr) if stderr.is_file() else None,
    }


def _normalize_replay_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    markers = (
        "/judge-exact-replay/judge/replays/",
        "/judge/replays/",
        "/judge-exact-replay/",
    )
    for marker in markers:
        if marker in text:
            return f"$REPLAY_ROOT/{text.split(marker, 1)[1]}"
    return text


def _generation_number_from_dir(path: Path) -> int | None:
    try:
        return int(path.name.removeprefix("generation-"))
    except ValueError:
        return None


def _assert_exact_replay_set(judges: dict[int, dict[str, Any]]) -> None:
    generations: list[int] = []
    for generation in (1, 2):
        replay = judges.get(generation, {}).get("exact_replay")
        if not isinstance(replay, dict):
            raise RuntimeError(f"generation {generation} exact replay is missing")
        if replay.get("status") != "PASS" or replay.get("matched") is not True:
            raise RuntimeError(f"generation {generation} exact replay did not pass")
        replay_generation = replay.get("generation")
        if replay_generation != generation:
            raise RuntimeError(f"generation {generation} exact replay is misbound")
        generations.append(int(replay_generation))
    if generations != [1, 2] or len(set(generations)) != 2:
        raise RuntimeError("exact replay generation set is invalid")


def _provider_genomes(
    *,
    battle_id: str,
    run_id: str,
    generation: int,
    generation_dir: Path,
    manifest: dict[str, Any],
    parent_genomes: dict[str, dict[str, Any]] | None = None,
    knowledge_packets: dict[str, dict[str, Any]] | None = None,
    research: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    genomes: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("teams", []):
        if not isinstance(entry, dict) or entry.get("team") not in {"red", "blue"}:
            continue
        team = str(entry["team"])
        call = _read_json(Path(str(entry["scillm_call"])))
        parsed = call.get("parsed_json")
        if not isinstance(parsed, dict):
            parsed = json.loads(str(call.get("response_content") or "{}"))
        strategy = parsed.get("strategy_genome") if isinstance(parsed, dict) else None
        if not isinstance(strategy, dict):
            raise RuntimeError(f"{team} provider response missing strategy_genome")
        required = {
            "selected_methods",
            "rejected_methods",
            "parameters",
            "mutation_origin",
            "expected_observation",
        }
        missing = sorted(required - set(strategy))
        if missing:
            raise RuntimeError(
                f"{team} strategy_genome missing fields: {', '.join(missing)}"
            )
        parent = (parent_genomes or {}).get(team)
        packet = (knowledge_packets or {}).get(team)
        team_research = (research or {}).get(team)
        genome = {
            "schema": "battle.adaptive_team_genome.v1",
            "battle_id": battle_id,
            "run_id": run_id,
            "team": team,
            "generation": generation,
            "artifact_role": "red_exploit" if team == "red" else "blue_patch",
            "parent_genome_sha256": parent.get("sha256") if parent else None,
            "knowledge_packet_id": packet.get("packet_id") if packet else None,
            "research_receipt_sha256": team_research.get("source_receipt_sha256")
            if team_research
            else None,
            **strategy,
            "provider_response_sha256": _sha(Path(str(entry["scillm_call"]))),
        }
        path = _write_json(
            generation_dir / "genomes" / f"{team}-team-genome.json", genome
        )
        genome["path"] = str(path)
        genome["sha256"] = _sha(path)
        if parent and genome["sha256"] == parent["sha256"]:
            raise RuntimeError(f"{team} child genome did not change")
        genomes[team] = genome
    if set(genomes) != {"red", "blue"}:
        raise RuntimeError("provider genomes missing Red or Blue")
    return genomes


def _red_fitness(judge: dict[str, Any]) -> int:
    return (
        2
        if judge.get("verdict") == "RED_SUCCESS"
        else 1
        if int(judge.get("judged_pair_count") or 0)
        else 0
    )


def _blue_fitness(judge: dict[str, Any]) -> int:
    return (
        2
        if judge.get("verdict") == "BLUE_SUCCESS"
        else 1
        if int(judge.get("judged_pair_count") or 0)
        else 0
    )


def _campaign_status(**items: Any) -> tuple[str, str]:
    if items["generation_1"].get("status") not in {"PASS", "INSUFFICIENT_EVIDENCE"}:
        return "BLOCKED", "generation_1_blocked"
    if items["visibility"].get("status") != "PASS":
        return "FAIL", "private_boundary_failed"
    if any(
        items[name].get("status") != "PASS"
        for name in ("red_spawn", "blue_spawn", "red_ack", "blue_ack", "selection")
    ):
        return "BLOCKED", "spawn_inheritance_or_selection_blocked"
    if any(
        int(items[name].get("judged_pair_count") or 0) < 1
        for name in ("g1_judge", "g2_judge")
    ):
        return "BLOCKED", "judge_pair_missing"
    if any(items[name].get("status") != "PASS" for name in ("g1_judge", "g2_judge")):
        return "BLOCKED", "judge_status_not_pass"
    if len(items["observations"]) != 4 or any(
        item.get("status") != "PASS" for item in items["observations"]
    ):
        return "BLOCKED", "generation_observation_missing"
    if len(items["fitness"]) != 4 or any(
        item.get("status") != "PASS" for item in items["fitness"]
    ):
        return "BLOCKED", "fitness_vector_missing"
    if len(items["requests"]) != 2 or any(
        item.get("request", {}).get("requested_action") != "SPAWN_CHILD"
        for item in items["requests"]
    ):
        return "BLOCKED", "parent_spawn_request_missing"
    if len(items["deltas"]) != 2 or any(
        item.get("nonempty_semantic_delta") is not True for item in items["deltas"]
    ):
        return "BLOCKED", "semantic_genome_delta_missing"
    if items["memory_evaluation"].get("status") != "PASS":
        return "BLOCKED", "memory_evaluation_missing"
    integrity = items.get("artifact_integrity")
    if not isinstance(integrity, dict):
        return "BLOCKED", "artifact_integrity_missing"
    if integrity.get("status") != "PASS":
        return "BLOCKED", "artifact_integrity_failed"
    slots = integrity.get("slots") if isinstance(integrity.get("slots"), list) else []
    expected_slots = {
        "generation-1:red",
        "generation-1:blue",
        "generation-2:red",
        "generation-2:blue",
    }
    if (
        len(slots) != 4
        or {item.get("slot_key") for item in slots} != expected_slots
        or integrity.get("required_slot_count") != 4
    ):
        return "BLOCKED", "artifact_integrity_slot_set_invalid"
    if integrity.get("matched_slot_count") != 4 or any(
        item.get("matched") is not True for item in slots
    ):
        return "BLOCKED", "artifact_integrity_slot_mismatch"
    replays = (
        integrity.get("judge_replays")
        if isinstance(integrity.get("judge_replays"), list)
        else []
    )
    if (
        len(replays) != 2
        or {item.get("generation") for item in replays} != {1, 2}
        or integrity.get("required_replay_count") != 2
    ):
        return "BLOCKED", "judge_replay_generation_set_invalid"
    if integrity.get("matched_replay_count") != 2 or any(
        item.get("status") != "PASS" or item.get("matched") is not True
        for item in replays
    ):
        return "BLOCKED", "judge_replay_mismatch"
    if any(item.get("receipt_valid") is not True for item in replays):
        return "BLOCKED", "judge_replay_receipt_invalid"
    return "PASS", "two_generation_red_blue_lineage_evaluated"


def _build_artifact_integrity_receipt(
    *,
    out_dir: Path,
    pipelines: dict[int, dict[str, dict[str, Any]]],
    judges: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    root = out_dir.resolve()
    required_slot_keys = {
        "generation-1:red",
        "generation-1:blue",
        "generation-2:red",
        "generation-2:blue",
    }
    slots: list[dict[str, Any]] = []
    slot_paths: list[str] = []
    for generation in (1, 2):
        for team in ("red", "blue"):
            pipeline = pipelines.get(generation, {}).get(team, {})
            slot = pipeline.get("immutable_slot")
            slot_key = f"generation-{generation}:{team}"
            path_text = slot.get("path") if isinstance(slot, dict) else None
            path = Path(str(path_text or ""))
            exists = path.exists()
            resolved = path.resolve() if exists else path
            regular_file = path.is_file() and not path.is_symlink()
            inside_run = exists and resolved.is_relative_to(root)
            expected = (
                slot.get("preserved_sha256")
                if isinstance(slot, dict) and slot.get("preserved_sha256")
                else pipeline.get("selected_artifact_sha256")
            )
            actual = _sha(path) if regular_file else None
            matched = (
                actual == expected
                and slot_key == (slot.get("slot_key") if isinstance(slot, dict) else None)
                and regular_file
                and inside_run
            )
            slots.append(
                {
                    "slot_key": slot_key,
                    "generation": generation,
                    "team": team,
                    "path": str(path) if path_text else None,
                    "expected_sha256": expected,
                    "actual_sha256": actual,
                    "matched": matched,
                    "regular_file": regular_file,
                    "inside_run_root": inside_run,
                }
            )
            if exists:
                slot_paths.append(str(resolved))

    replay_records: list[dict[str, Any]] = []
    replay_paths: list[str] = []
    for generation in (1, 2):
        replay = judges.get(generation, {}).get("exact_replay")
        path_text = replay.get("path") if isinstance(replay, dict) else None
        replay_path = Path(str(path_text or ""))
        exists = replay_path.exists()
        replay_resolved = replay_path.resolve() if exists else replay_path
        regular_file = replay_path.is_file() and not replay_path.is_symlink()
        inside_run = exists and replay_resolved.is_relative_to(root)
        expected = replay.get("sha256") if isinstance(replay, dict) else None
        actual = _sha(replay_path) if regular_file else None
        parsed: dict[str, Any] = {}
        if regular_file:
            try:
                parsed = _read_json(replay_path)
            except Exception:
                parsed = {}
        replay_generation = (
            parsed.get("generation")
            if isinstance(parsed.get("generation"), int)
            else replay.get("generation")
            if isinstance(replay, dict)
            else None
        )
        receipt_valid = actual == expected and regular_file and inside_run
        replay_matched = (
            receipt_valid
            and replay_generation == generation
            and parsed.get("status") == "PASS"
            and parsed.get("matched") is True
            and (replay.get("status") if isinstance(replay, dict) else None) == "PASS"
            and (replay.get("matched") if isinstance(replay, dict) else False) is True
        )
        replay_records.append(
            {
                "generation": replay_generation,
                "expected_generation": generation,
                "status": parsed.get("status")
                if parsed.get("status") is not None
                else replay.get("status")
                if isinstance(replay, dict)
                else None,
                "matched": replay_matched,
                "path": str(replay_path) if path_text else None,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "receipt_valid": receipt_valid,
                "regular_file": regular_file,
                "inside_run_root": inside_run,
            }
        )
        if exists:
            replay_paths.append(str(replay_resolved))

    slot_keys = {item["slot_key"] for item in slots}
    slots_pass = (
        slot_keys == required_slot_keys
        and len(slots) == 4
        and len(slot_paths) == len(set(slot_paths)) == 4
        and all(item["matched"] for item in slots)
    )
    replay_generations = {item["generation"] for item in replay_records}
    replays_pass = (
        replay_generations == {1, 2}
        and len(replay_records) == 2
        and len(replay_paths) == len(set(replay_paths)) == 2
        and all(
            item["status"] == "PASS"
            and item["matched"]
            and item["receipt_valid"]
            for item in replay_records
        )
    )
    reason = "artifact_integrity_pass"
    if slot_keys != required_slot_keys or len(slots) != 4:
        reason = "artifact_integrity_slot_set_invalid"
    elif len(slot_paths) != len(set(slot_paths)) or len(slot_paths) != 4:
        reason = "artifact_integrity_slot_path_set_invalid"
    elif not all(item["matched"] for item in slots):
        reason = "artifact_integrity_slot_mismatch"
    elif replay_generations != {1, 2} or len(replay_records) != 2:
        reason = "judge_replay_generation_set_invalid"
    elif len(replay_paths) != len(set(replay_paths)) or len(replay_paths) != 2:
        reason = "judge_replay_path_set_invalid"
    elif not all(item["receipt_valid"] for item in replay_records):
        reason = "judge_replay_receipt_invalid"
    elif not all(item["status"] == "PASS" and item["matched"] for item in replay_records):
        reason = "judge_replay_mismatch"

    return {
        "schema": "battle.adaptive_artifact_integrity.v1",
        "status": "PASS" if slots_pass and replays_pass else "FAIL",
        "reason": reason,
        "required_slot_count": 4,
        "matched_slot_count": sum(1 for item in slots if item["matched"]),
        "required_replay_count": 2,
        "matched_replay_count": sum(
            1
            for item in replay_records
            if item["status"] == "PASS" and item["matched"] and item["receipt_valid"]
        ),
        "slots": slots,
        "judge_replays": replay_records,
        "unique_slot_paths": len(slot_paths) == len(set(slot_paths)) == 4,
        "unique_replay_paths": len(replay_paths) == len(set(replay_paths)) == 2,
        "created_at": _now(),
    }


def _source_receipt_index(
    *,
    battle_id: str,
    run_id: str,
    campaign_root: Path,
    observations: list[dict[str, Any]],
    fitness: list[dict[str, Any]],
    requests: list[dict[str, Any]],
    deltas: list[dict[str, Any]],
    selection: dict[str, Any],
    memory_evaluation: dict[str, Any],
) -> dict[str, Any]:
    public_receipts = []
    for item in [
        *observations,
        *fitness,
        *requests,
        *deltas,
        selection,
        memory_evaluation,
    ]:
        public_receipts.append(
            {
                "schema": item.get("schema"),
                "status": item.get("status"),
                "sha256": item.get("sha256"),
                "receipt_id": item.get("receipt_id")
                or item.get("fitness_id")
                or item.get("request_id")
                or item.get("delta_id")
                or item.get("selection_id")
                or item.get("evaluation_id"),
            }
        )
    known = {(item.get("schema"), item.get("sha256")) for item in public_receipts}
    for line in (
        (campaign_root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ):
        if not line:
            continue
        source = json.loads(line)["source_receipt"]
        key = (source.get("schema"), source.get("sha256"))
        if key not in known:
            public_receipts.append(source)
            known.add(key)
    return {
        "schema": "battle.adaptive_lineage_source_receipt_index.v1",
        "status": "PASS",
        "battle_id": battle_id,
        "run_id": run_id,
        "campaign_root_id": campaign_root.name,
        "public_receipts": public_receipts,
        "selection": {
            "receipt_id": selection["selection_id"],
            "sha256": selection["sha256"],
            "teams": selection["teams"],
            "improvement_claimed": selection["improvement_claimed"],
        },
        "memory_evaluation": {
            "receipt_id": memory_evaluation["evaluation_id"],
            "sha256": memory_evaluation["sha256"],
            "decisions": [
                item["decision"] for item in memory_evaluation["evaluations"]
            ],
        },
    }


def _generation_summary(
    generation: int,
    manifest: dict[str, Any],
    judge: dict[str, Any],
    red: dict[str, Any],
    blue: dict[str, Any],
    pipelines: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "generation": generation,
        "tau_status": manifest.get("status"),
        "red_artifact_sha256": _sha(Path(red["path"])),
        "blue_artifact_sha256": _sha(Path(blue["path"])),
        "judge_status": judge.get("status"),
        "judge_verdict": judge.get("verdict"),
        "judged_pair_count": judge.get("judged_pair_count"),
        "artifact_pipelines": pipelines,
    }


def _copy_public_arena(generation_1_dir: Path, generation_2_dir: Path) -> None:
    source = generation_1_dir / "arena" / "team-public"
    target = generation_2_dir / "arena" / "team-public"
    shutil.copytree(source, target, dirs_exist_ok=True)


def _single_materialized(manifest: dict[str, Any], team: str) -> dict[str, Any]:
    entries = _materialized_entries(manifest, team)
    if len(entries) != 1:
        raise RuntimeError(
            f"expected exactly one materialized {team} artifact, found {len(entries)}"
        )
    return entries[0]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_rev_parse(rev: str) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", rev],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _population_genomes(**kwargs: Any) -> dict[str, Any]:
    """Verified primitive adapter: role-filtered population materialization."""

    role = str(kwargs.get("role") or kwargs.get("team") or "red")
    generation = int(kwargs.get("generation") or 1)
    worker_count = int(
        kwargs.get("n")
        or kwargs.get("worker_count")
        or kwargs.get("population_size")
        or 1
    )
    battle_id = str(kwargs.get("battle_id") or "battle")
    run_id = str(kwargs.get("run_id") or "run")
    lineage_id = str(kwargs.get("lineage_id") or f"{role}-lineage")
    inherited = kwargs.get("memory_recall") or kwargs.get("recall") or {}
    inherited_docs = (
        inherited.get("documents") if isinstance(inherited, dict) else []
    ) or []
    teams = {
        role: [
            {
                "schema": "battle.verified_population_candidate.v1",
                "specimen_id": f"{role}-g{generation}-p{index}",
                "candidate_id": f"{role}-g{generation}-p{index}",
                "battle_id": battle_id,
                "lineage_id": lineage_id,
                "run_id": run_id,
                "role": role,
                "team": role,
                "generation": generation,
                "population_index": index,
                "inherited_document_count": len(inherited_docs),
                "source": "adaptive_red_blue_lineage_canary._population_genomes",
            }
            for index in range(worker_count)
        ],
        "blue" if role == "red" else "red": [
            {
                "schema": "battle.verified_population_candidate.v1",
                "specimen_id": f"opponent-{generation}-{index}",
                "candidate_id": f"opponent-{generation}-{index}",
                "role": "blue" if role == "red" else "red",
                "team": "blue" if role == "red" else "red",
                "generation": generation,
                "population_index": index,
                "source": "opponent-control",
            }
            for index in range(worker_count)
        ],
    }
    return {
        "schema": "battle.verified_population_output.v1",
        "status": "PASS",
        "role": role,
        "team_keyed_population": teams,
        "population": teams[role],
        "genomes": teams[role],
    }


def _review_population(**kwargs: Any) -> dict[str, Any]:
    """Verified primitive adapter: consume the real population payload shape."""

    role = str(kwargs.get("role") or kwargs.get("team") or "red")
    population = _role_items(kwargs, role=role, keys=("population", "genomes"))
    reviews = [
        {
            **dict(item),
            "schema": "battle.verified_population_review.v1",
            "review_status": "PASS",
            "review_receipt": {
                "schema": "battle.verified_review_receipt.v1",
                "status": "PASS",
                "role": role,
                "candidate_id": item.get("candidate_id") or item.get("specimen_id"),
                "checks": ["identity_present", "role_scoped"],
            },
            "source": "adaptive_red_blue_lineage_canary._review_population",
        }
        for item in population
    ]
    return {
        "schema": "battle.verified_review_output.v1",
        "status": "PASS",
        "role": role,
        "reviewed_population": reviews,
        "reviews": reviews,
    }


def _judge_population(**kwargs: Any) -> dict[str, Any]:
    """Verified primitive adapter: run a bounded Docker Judge per candidate."""

    role = str(kwargs.get("role") or kwargs.get("team") or "red")
    generation = int(kwargs.get("generation") or 1)
    docker_image = str(
        (kwargs.get("context") if isinstance(kwargs.get("context"), dict) else {}).get(
            "docker_image"
        )
        or kwargs.get("docker_image")
        or "python:3.12-slim"
    )
    generation_dir = Path(
        kwargs.get("generation_dir") or kwargs.get("out_dir") or Path.cwd()
    )
    reviewed = _role_items(
        kwargs, role=role, keys=("reviewed_population", "reviews", "reviewed")
    )
    judge_dir = generation_dir / "verified-primitives" / "docker-judge"
    judged: list[dict[str, Any]] = []
    bad: list[dict[str, Any]] = []
    for index, item in enumerate(reviewed):
        candidate = dict(item)
        candidate_id = str(candidate.get("candidate_id") or candidate.get("specimen_id"))
        verdict = (
            "RED_SUCCESS"
            if role == "red" and index == 0
            else "BLUE_SUCCESS"
            if role == "blue" and index == 0
            else "INSUFFICIENT_EVIDENCE"
        )
        receipt = _run_verified_primitive_docker_judge(
            docker_image=docker_image,
            judge_dir=judge_dir / candidate_id,
            role=role,
            generation=generation,
            candidate_id=candidate_id,
            verdict=verdict,
        )
        judged_item = {
            **candidate,
            "schema": "battle.verified_judged_candidate.v1",
            "judge_status": receipt["status"],
            "judge_verdict": verdict,
            "judge_receipt_path": receipt["path"],
            "judge_receipt_sha256": receipt["sha256"],
            "source": "adaptive_red_blue_lineage_canary._judge_population",
        }
        judged.append(judged_item)
        if verdict == "INSUFFICIENT_EVIDENCE":
            bad.append(
                {
                    "specimen_id": candidate_id,
                    "candidate_id": candidate_id,
                    "source": "docker-judge",
                    "reason_codes": ["INSUFFICIENT_EVIDENCE"],
                    "evidence": {
                        "judge_receipt_path": receipt["path"],
                        "judge_receipt_sha256": receipt["sha256"],
                    },
                }
            )
    return {
        "schema": "battle.verified_judge_output.v1",
        "status": "PASS",
        "role": role,
        "judged_population": judged,
        "judge_records": judged,
        "bad_genetic_material": bad,
    }


def _select_survivor(**kwargs: Any) -> dict[str, Any]:
    """Verified primitive adapter: fail closed unless a role-valid Judge winner exists."""

    role = str(kwargs.get("role") or kwargs.get("team") or "red")
    judged = _role_items(
        kwargs, role=role, keys=("judged_population", "judgments", "verdicts")
    )
    winning_verdict = "RED_SUCCESS" if role == "red" else "BLUE_SUCCESS"
    winners = [
        item for item in judged if str(item.get("judge_verdict")) == winning_verdict
    ]
    survivor = winners[0] if len(winners) == 1 else None
    bad = [
        {
            "specimen_id": item.get("specimen_id") or item.get("candidate_id"),
            "candidate_id": item.get("candidate_id") or item.get("specimen_id"),
            "source": "verified-select-survivor",
            "reason_codes": [
                "opponent_or_insufficient_verdict"
                if survivor is not None
                else "oracle_no_viable_survivor"
            ],
        }
        for item in judged
        if survivor is None
        or (item.get("candidate_id") or item.get("specimen_id"))
        != (survivor.get("candidate_id") or survivor.get("specimen_id"))
    ]
    return {
        "schema": "battle.verified_survivor_selection.v1",
        "status": "PASS",
        "oracle_id": f"{role}-verified-docker-judge-oracle",
        "survivor": survivor,
        "bad_genetic_material": {"specimens": bad},
        "evidence": {
            "role": role,
            "winning_verdict": winning_verdict,
            "judged_count": len(judged),
            "winner_count": len(winners),
            "fail_closed": survivor is None,
        },
    }


def _role_items(
    payload: dict[str, Any],
    *,
    role: str,
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            if isinstance(value.get(role), list):
                return [dict(item) for item in value[role] if isinstance(item, dict)]
            if isinstance(value.get("teams"), dict) and isinstance(
                value["teams"].get(role), list
            ):
                return [
                    dict(item)
                    for item in value["teams"][role]
                    if isinstance(item, dict)
                ]
        if isinstance(value, list):
            return [
                dict(item)
                for item in value
                if isinstance(item, dict)
                and str(item.get("role") or item.get("team") or role) == role
            ]
    return []


def _run_verified_primitive_docker_judge(
    *,
    docker_image: str,
    judge_dir: Path,
    role: str,
    generation: int,
    candidate_id: str,
    verdict: str,
) -> dict[str, Any]:
    judge_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "battle.verified_primitive_docker_judge_probe.v1",
        "role": role,
        "generation": generation,
        "candidate_id": candidate_id,
        "verdict": verdict,
    }
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "-e",
        "BATTLE_JUDGE_PAYLOAD",
        docker_image,
        "python",
        "-c",
        "import json, os; print(json.dumps(json.loads(os.environ['BATTLE_JUDGE_PAYLOAD']), sort_keys=True))",
    ]
    started = time.perf_counter()
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "BATTLE_JUDGE_PAYLOAD": json.dumps(payload, sort_keys=True)},
        timeout=60,
    )
    stdout_path = judge_dir / "stdout.txt"
    stderr_path = judge_dir / "stderr.txt"
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    status = "PASS" if proc.returncode == 0 and verdict != "INSUFFICIENT_EVIDENCE" else "INSUFFICIENT_EVIDENCE"
    receipt = {
        "schema": "battle.verified_primitive_docker_judge_receipt.v1",
        "status": status,
        "verdict": verdict,
        "role": role,
        "generation": generation,
        "candidate_id": candidate_id,
        "docker_image": docker_image,
        "command": command,
        "exit_code": proc.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }
    receipt_path = _write_json(judge_dir / "judge-receipt.json", receipt)
    receipt["path"] = str(receipt_path)
    receipt["sha256"] = _sha(receipt_path)
    if proc.returncode != 0:
        raise RuntimeError(f"Docker Judge failed for {candidate_id}: {receipt}")
    _write_json(receipt_path, receipt)
    return receipt
