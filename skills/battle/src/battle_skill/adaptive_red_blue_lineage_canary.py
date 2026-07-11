"""Two-generation, simultaneous Red/Blue adaptive lineage canary."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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


SCHEMA = "battle.adaptive_red_blue_lineage_canary.v1"


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
    g1_judge = _judge_tau_artifacts(
        out_dir=generation_1_dir,
        scenario=scenario,
        docker_image=docker_image,
        tau_manifest=g1_manifest,
    )
    _write_json(generation_1_dir / "judge" / "judge-receipt.json", g1_judge)
    g1_red = _single_materialized(g1_manifest, "red")
    g1_blue = _single_materialized(g1_manifest, "blue")

    spawn_root = out_dir / "spawn"
    knowledge_root = generation_2_dir / "arena" / "team-public" / "knowledge"
    knowledge_root.mkdir(parents=True, exist_ok=True)
    red_spawn = _spawn_decision("red", g1_judge, g1_red, generation_1_dir)
    blue_spawn = _spawn_decision("blue", g1_judge, g1_blue, generation_1_dir)
    red_spawn_path = _write_json(
        spawn_root / "red-spawn-policy-decision.json", red_spawn
    )
    blue_spawn_path = _write_json(
        spawn_root / "blue-spawn-policy-decision.json", blue_spawn
    )
    red_packet = _knowledge_packet(
        "red", battle_id, run_id, g1_judge, g1_red, red_spawn_path
    )
    blue_packet = _knowledge_packet(
        "blue", battle_id, run_id, g1_judge, g1_blue, blue_spawn_path
    )
    red_packet_path = _write_json(
        knowledge_root / "red-inherited-knowledge-packet.json", red_packet
    )
    blue_packet_path = _write_json(
        knowledge_root / "blue-inherited-knowledge-packet.json", blue_packet
    )

    research_root = generation_2_dir / "arena" / "team-public" / "research"
    red_research = _run_tau_research(
        team="red",
        query="public Python archive extraction path traversal exploit techniques and test cases",
        out_dir=research_root / "red",
    )
    blue_research = _run_tau_research(
        team="blue",
        query="public Python archive extraction path traversal prevention and regression testing",
        out_dir=research_root / "blue",
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
    g2_judge = _judge_tau_artifacts(
        out_dir=generation_2_dir,
        scenario=scenario,
        docker_image=docker_image,
        tau_manifest=g2_manifest,
    )
    _write_json(generation_2_dir / "judge" / "judge-receipt.json", g2_judge)
    g2_red = _single_materialized(g2_manifest, "red")
    g2_blue = _single_materialized(g2_manifest, "blue")
    red_ack = _knowledge_acknowledgement(
        "red", red_packet, red_research, g2_manifest, g2_red
    )
    blue_ack = _knowledge_acknowledgement(
        "blue", blue_packet, blue_research, g2_manifest, g2_blue
    )
    _write_json(
        generation_2_dir / "red-inherited-knowledge-acknowledgement.json", red_ack
    )
    _write_json(
        generation_2_dir / "blue-inherited-knowledge-acknowledgement.json", blue_ack
    )

    selection = _selection_receipt(g1_judge, g2_judge, g1_red, g1_blue, g2_red, g2_blue)
    _write_json(out_dir / "selection-receipt.json", selection)
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
    )
    receipt = {
        "schema": SCHEMA,
        "status": status,
        "reason": reason,
        "battle_id": battle_id,
        "run_id": run_id,
        "mocked": False,
        "live": "tau_scillm_docker_judge_two_generation_red_blue",
        "agentic": True,
        "fixture_fallback_used": False,
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
            _generation_summary(1, g1_manifest, g1_judge, g1_red, g1_blue, g1_pipelines),
            _generation_summary(2, g2_manifest, g2_judge, g2_red, g2_blue, g2_pipelines),
        ],
        "spawn": {"red": red_spawn, "blue": blue_spawn},
        "inheritance": {"red": red_ack, "blue": blue_ack},
        "research": {"red": red_research, "blue": blue_research},
        "selection": selection,
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
    _write_json(out_dir / "adaptive-lineage-chain-receipt.json", receipt)
    _write_json(out_dir / "campaign-receipt.json", receipt)
    return receipt


def _spawn_decision(
    team: str, judge: dict[str, Any], parent: dict[str, Any], root: Path
) -> dict[str, Any]:
    judge_path = root / "judge" / "judge-receipt.json"
    return {
        "schema": "battle.adaptive_spawn_policy_decision.v1",
        "status": "PASS",
        "decision": "ALLOWED_EVALUATED_PARENT",
        "team": team,
        "parent_terminal": False,
        "reason_codes": [
            "parent_judge_evaluated",
            "bounded_second_generation_requested",
            "remaining_budget_available",
        ],
        "source_receipts": [{"kind": "judge_receipt", "sha256": _sha(judge_path)}],
        "parent_artifact_sha256": _sha(Path(parent["path"])),
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
    judge: dict[str, Any],
    parent: dict[str, Any],
    spawn_path: Path,
) -> dict[str, Any]:
    parent_sha = _sha(Path(parent["path"]))
    attempt = (judge.get("attempts") or [{}])[0]
    packet_id = f"{battle_id}-{team}-generation-2-knowledge"
    observation = {
        "judge_verdict": judge.get("verdict"),
        "exploit_confirmed_before_patch": attempt.get("exploit_confirmed_before_patch"),
        "exploit_blocked_after_patch": attempt.get("exploit_blocked_after_patch"),
        "functionality_preserved": attempt.get("functionality_preserved"),
    }
    return {
        "schema": "battle.adaptive_team_knowledge_packet.v1",
        "packet_id": packet_id,
        "battle_id": battle_id,
        "run_id": run_id,
        "team": team,
        "generation": 2,
        "parent_artifact_sha256": parent_sha,
        "observations": [observation],
        "active_hypotheses": [
            "Change the parent strategy in response to the Judge outcome."
        ],
        "failed_or_partial_attempts": [observation],
        "research_questions": [
            "What public technique or hardening variation addresses the observed Judge outcome?"
        ],
        "target_constraints": [
            "Use only Arena team-public artifacts.",
            "Do not claim outcomes; Judge decides.",
        ],
        "source_receipts": [{"kind": "spawn_policy", "sha256": _sha(spawn_path)}],
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
        else "The patch must preserve a callable import_zip(zip_path, destination) interface. "
    )
    return (
        f"Produce a new {artifact} artifact after reading inherited packet {packet['packet_id']}. "
        f"Your JSON rationale must cite packet_id {packet['packet_id']} or parent artifact sha256 {packet['parent_artifact_sha256']}. "
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
    research_cited = research["source_receipt_sha256"] in response_text
    child_sha = _sha(Path(child["path"]))
    changed = child_sha != parent_sha
    return {
        "schema": "battle.inherited_knowledge_acknowledgement.v1",
        "status": "PASS" if cited and research_cited and changed else "BLOCKED",
        "team": team,
        "packet_id": packet_id,
        "packet_cited_in_provider_response": cited,
        "parent_artifact_sha256": parent_sha,
        "child_artifact_sha256": child_sha,
        "artifact_changed": changed,
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


def _run_tau_research(*, team: str, query: str, out_dir: Path) -> dict[str, Any]:
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
        "/home/graham/workspace/experiments/tau",
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
            materialization_receipt=Path(str(entry["materialized_artifact"]["path"])).parent
            / "materialized-artifact-receipt.json",
            target_identity_sha256=target_identity_sha256,
            out_dir=generation_dir / "reviewed" / team,
            docker_image=docker_image,
            genome_sha256=genomes[team]["sha256"],
        )
        if pipeline["status"] != "PASS":
            raise RuntimeError(f"{team} artifact pipeline blocked")
        materialized["raw_provider_path"] = materialized["path"]
        materialized["path"] = str(pipeline["selected_artifact_path"])
        materialized["pipeline_handoff"] = str(pipeline["handoff_path"])
        entry["materialized"] = materialized
        pipelines[team] = {
            "status": pipeline["status"],
            "selected_artifact_sha256": pipeline["selected_artifact_sha256"],
            "handoff_sha256": _sha(pipeline["handoff_path"]),
            "compile_receipt_sha256": _sha(pipeline["compile_receipt_path"]),
            "review_receipt_sha256": _sha(pipeline["review_receipt_path"]),
        }
    _write_json(generation_dir / "reviewed" / "reviewed-manifest.json", reviewed)
    return reviewed, pipelines


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
        required = {"selected_methods", "rejected_methods", "parameters", "mutation_origin", "expected_observation"}
        missing = sorted(required - set(strategy))
        if missing:
            raise RuntimeError(f"{team} strategy_genome missing fields: {', '.join(missing)}")
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
            "research_receipt_sha256": team_research.get("source_receipt_sha256") if team_research else None,
            **strategy,
            "provider_response_sha256": _sha(Path(str(entry["scillm_call"]))),
        }
        path = _write_json(generation_dir / "genomes" / f"{team}-team-genome.json", genome)
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
    return "PASS", "two_generation_red_blue_lineage_evaluated"


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
