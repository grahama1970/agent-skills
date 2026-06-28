"""Arena Team hidden-vulnerability Docker race proof.

This proof rung is intentionally small: Arena Team prepares a target with hidden
ground truth, Red and Blue race asynchronously, and every executable target
command runs through Docker. The host only copies fixture files, dispatches
containers, records receipts, and scores timing evidence.
"""

from __future__ import annotations

import ast
import json
import os
import shlex
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from .receipts import CommandResult, to_jsonable, utc_now, write_json
from .subagent_smoke import (
    goal_payload,
    handoff_payload,
    init_ledger,
    probe_persona,
    record_event,
    run_tau_agent_harness_turn,
    skipped_harness_turn,
    subagent_receipt_payload,
    validate_tau_receipt,
)


SCILLM_ROOT = Path(
    os.getenv("SCILLM_ROOT", "/home/graham/workspace/experiments/scillm")
).resolve()
SCILLM_PYTHON = Path(
    os.getenv(
        "BATTLE_SCILLM_PYTHON",
        "/home/graham/workspace/experiments/agent-skills/.tmp_venv/bin/python3",
    )
)
MEMORY_BASE_URL = os.getenv("BATTLE_MEMORY_BASE_URL", "http://127.0.0.1:8601")
SKILLS_ROOT = Path(__file__).resolve().parents[3]

EXECUTION_SCOPE = {
    "mocked": False,
    "live": "docker_hidden_vulnerability_race",
    "agentic": False,
    "models_used": [],
}

NON_CLAIMS = [
    "does_not_prove_tau_subagent_execution",
    "does_not_prove_scillm_or_external_model_execution",
    "does_not_prove_multi_mutation_swarm",
    "does_not_prove_memory_promotion",
    "does_not_prove_live_streaming_react_d3_monitor",
]


def non_claims_for(
    *,
    agentic: bool,
    scillm_plan: bool = False,
    context_receipts: bool = False,
) -> list[str]:
    if not agentic and not scillm_plan:
        if context_receipts:
            return [
                claim
                for claim in NON_CLAIMS
                if claim != "does_not_prove_memory_promotion"
            ] + ["does_not_prove_memory_graph_promotion_or_cross_round_reuse"]
        return NON_CLAIMS
    claims = [
        "does_not_prove_multi_mutation_swarm",
        "does_not_prove_live_streaming_react_d3_monitor",
    ]
    if context_receipts:
        claims.append("does_not_prove_memory_graph_promotion_or_cross_round_reuse")
    else:
        claims.append("does_not_prove_memory_promotion")
    if not agentic:
        claims.append("does_not_prove_tau_subagent_execution")
    else:
        claims.append("does_not_prove_tau_loop_repair_cycle")
    if not scillm_plan:
        claims.append("does_not_prove_scillm_or_external_model_execution")
    else:
        claims.append("does_not_prove_scillm_delegate_batch_or_tool_execution")
    return claims


def run_arena_docker_smoke(
    *,
    fixture_dir: Path,
    out_dir: Path,
    red_persona: str = "brandon-bailey",
    blue_persona: str = "coder",
    agentic: bool = False,
    scillm_plan: bool = False,
    scillm_model: str = "opencode/kimi-k2.6",
    context_receipts: bool = False,
) -> dict[str, Any]:
    """Run one Arena -> async Red/Blue -> Scorekeeper proof in Docker."""

    scenario = json.loads((fixture_dir / "scenario.json").read_text(encoding="utf-8"))
    hidden = json.loads(
        (fixture_dir / scenario["arena_team"]["hidden_ground_truth"]).read_text(
            encoding="utf-8"
        )
    )
    battle_id = str(scenario.get("battle_id", fixture_dir.name))
    run_id = f"arena-docker-smoke-{uuid.uuid4().hex[:12]}"
    image = str(scenario.get("docker_image", "python:3.12-slim"))
    race = scenario.get("race", {})
    goal = goal_payload(battle_id=battle_id, scenario=scenario)
    execution_scope = {
        **EXECUTION_SCOPE,
        "agentic": agentic,
        "scillm_plan": scillm_plan,
        "context_receipts": context_receipts,
        "models_used": [
            *(["tau-local-deterministic-provider"] if agentic else []),
            *([scillm_model] if scillm_plan else []),
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    tau_dir = out_dir / "tau"
    tau_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "subagent-ledger.sqlite"
    init_ledger(ledger_path)
    write_json(out_dir / "battle-plan.json", public_scenario(scenario))

    workspace = out_dir / "workspace"
    target = workspace / "target"
    patches = workspace / "patches"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(fixture_dir / "target", target)
    shutil.copytree(fixture_dir / "patches", patches)

    arena_receipt = {
        "schema": "battle.arena_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS",
        "team": "arena",
        "role": "builds_project_and_secretly_plants_vulnerability",
        "target_workspace": str(target),
        "hidden_ground_truth_artifact": "hidden-ground-truth.json",
        "hidden_vulnerability_count": len(hidden.get("hidden_vulnerabilities", [])),
        "docker_image": image,
        "execution_boundary": "host_control_plane_only_target_commands_run_in_docker",
        "created_at": utc_now(),
    }
    write_json(out_dir / "arena-receipt.json", arena_receipt)
    write_json(out_dir / "hidden-ground-truth.json", hidden)

    image_receipt = ensure_docker_image(image=image, artifact_dir=out_dir / "docker")
    write_json(out_dir / "docker-image-receipt.json", image_receipt)
    if image_receipt["status"] != "PASS":
        return write_blocked(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="docker_image_unavailable",
            execution_scope=execution_scope,
            extra={"docker_image": image, "image_receipt": "docker-image-receipt.json"},
        )

    context_receipt = (
        prepare_context_receipts(
            scenario=scenario,
            hidden=hidden,
            battle_id=battle_id,
            run_id=run_id,
            image=image,
            target=target,
            out_dir=out_dir,
            ledger_path=ledger_path,
            red_persona=red_persona,
            blue_persona=blue_persona,
        )
        if context_receipts
        else skipped_context_receipt(battle_id=battle_id, run_id=run_id)
    )
    if context_receipts and context_receipt["status"] != "PASS":
        return write_blocked(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="context_receipts_failed",
            execution_scope=execution_scope,
            extra={
                "context": context_receipt,
                "context_receipt": "context/context-receipt.json",
            },
        )

    tau_receipt = prepare_tau_receipts(
        scenario=scenario,
        battle_id=battle_id,
        run_id=run_id,
        goal=goal,
        out_dir=out_dir,
        tau_dir=tau_dir,
        ledger_path=ledger_path,
        red_persona=red_persona,
        blue_persona=blue_persona,
        agentic=agentic,
        scillm_plan=scillm_plan,
        scillm_model=scillm_model,
    )
    if tau_receipt["status"] != "PASS":
        return write_blocked(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="tau_agentic_boundary_failed",
            execution_scope=execution_scope,
            extra={"tau": tau_receipt, "tau_receipt": "tau/team-receipt.json"},
        )

    planted_ok, planted_cmd = run_docker_command(
        image=image,
        target=target,
        command=scenario["commands"]["expect_vulnerable"],
        artifact_dir=out_dir / "arena",
        name="arena-hidden-vulnerability-oracle",
    )
    if not planted_ok:
        return write_blocked(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="arena_hidden_vulnerability_oracle_failed",
            execution_scope=execution_scope,
            extra={"command": planted_cmd},
        )

    warm_pond_execution_receipt = (
        run_warm_pond_execution_receipt(
            battle_id=battle_id,
            run_id=run_id,
            scenario=scenario,
            image=image,
            target=target,
            patches=patches,
            out_dir=out_dir,
            ledger_path=ledger_path,
            red_persona=red_persona,
            blue_persona=blue_persona,
        )
        if context_receipts
        else skipped_warm_pond_execution_receipt(battle_id=battle_id, run_id=run_id)
    )
    if context_receipts:
        warm_pond_execution_path = out_dir / "context" / "warm-pond-execution-receipt.json"
        record_event(
            ledger_path,
            run_id=run_id,
            battle_id=battle_id,
            team="orchestrator",
            persona="battle-orchestrator",
            event_type="warm_pond_execution",
            status=str(warm_pond_execution_receipt["status"]),
            artifact_path=warm_pond_execution_path,
            details=to_jsonable(warm_pond_execution_receipt),
        )
        context_receipt["warm_pond_execution"] = "context/warm-pond-execution-receipt.json"
        context_receipt["warm_pond_execution_summary"] = {
            "status": warm_pond_execution_receipt["status"],
            "selected_attempt_count": warm_pond_execution_receipt.get("selected_attempt_count", 0),
            "passed_attempt_count": warm_pond_execution_receipt.get("passed_attempt_count", 0),
            "failed_attempt_count": warm_pond_execution_receipt.get("failed_attempt_count", 0),
        }
        context_receipt["artifacts"].append("context/warm-pond-execution-receipt.json")
        context_receipt["non_claims"] = [
            claim
            for claim in context_receipt.get("non_claims", [])
            if claim != "does_not_execute_warm_pond_candidates_yet"
        ] + [
            "does_not_execute_unbounded_warm_pond_swarm",
            "does_not_promote_warm_pond_winners_across_rounds_yet",
        ]
        write_json(out_dir / "context" / "context-receipt.json", context_receipt)
    if context_receipts and warm_pond_execution_receipt["status"] != "PASS":
        return write_blocked(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="warm_pond_execution_failed",
            execution_scope=execution_scope,
            extra={
                "warm_pond_execution": warm_pond_execution_receipt,
                "warm_pond_execution_receipt": "context/warm-pond-execution-receipt.json",
            },
        )

    started = time.monotonic()
    red_delay = float(race.get("red_delay_seconds", 1.0))
    blue_delay = float(race.get("blue_delay_seconds", 0.0))
    timeout = float(race.get("timeout_seconds", 30.0))

    with ThreadPoolExecutor(max_workers=2) as executor:
        red_future = executor.submit(
            red_worker,
            image=image,
            target=target,
            command=scenario["commands"]["expect_vulnerable"],
            out_dir=out_dir,
            delay_seconds=red_delay,
            started=started,
        )
        blue_future = executor.submit(
            blue_worker,
            image=image,
            target=target,
            patches=patches,
            regression_command=scenario["commands"]["regression"],
            out_dir=out_dir,
            delay_seconds=blue_delay,
            started=started,
        )
        red_result = red_future.result(timeout=timeout + red_delay + 10)
        blue_result = blue_future.result(timeout=timeout + blue_delay + 10)

    safe_ok, safe_cmd = run_docker_command(
        image=image,
        target=target,
        command=scenario["commands"]["expect_safe"],
        artifact_dir=out_dir / "scorekeeper",
        name="scorekeeper-exploit-safe",
    )
    regression_ok, regression_cmd = run_docker_command(
        image=image,
        target=target,
        command=scenario["commands"]["regression"],
        artifact_dir=out_dir / "scorekeeper",
        name="scorekeeper-regression",
    )

    red_exploited = red_result["exploit_exit_code"] == 0
    blue_patched = blue_result["patch_exit_code"] == 0
    if blue_patched and safe_ok and regression_ok and not red_exploited:
        verdict = "BLUE_SUCCESS"
        status = "PASS"
        winner = "blue"
    elif red_exploited:
        verdict = "RED_SUCCESS"
        status = "FAIL"
        winner = "red"
    elif blue_patched and not regression_ok:
        verdict = "FAKE_DEFENSE"
        status = "FAIL"
        winner = "red"
    else:
        verdict = "BLOCKED"
        status = "BLOCKED"
        winner = "none"

    red_receipt = {
        "schema": "battle.red_receipt.v1",
        "battle_id": battle_id,
        "round_number": 1,
        "status": "PASS" if red_exploited else "FAIL",
        "finding_id": "hidden-sqli-xss-chain" if red_exploited else None,
        "exploit_confirmed": red_exploited,
        "commands_run": [red_result["command"]],
        "race": red_result,
        "persona": red_persona,
        "subagent_receipt": "tau/red-subagent-receipt.json",
        "next_agent": "battle-scorekeeper",
        "created_at": utc_now(),
    }
    blue_receipt = {
        "schema": "battle.blue_receipt.v1",
        "battle_id": battle_id,
        "round_number": 1,
        "status": "PASS" if blue_patched else "FAIL",
        "patch_artifact": "blue/patch.diff",
        "changed_files": list(scenario.get("expected_changed_files", [])),
        "commands_run": [blue_result["command"]],
        "race": blue_result,
        "persona": blue_persona,
        "subagent_receipt": "tau/blue-subagent-receipt.json",
        "next_agent": "battle-scorekeeper",
        "created_at": utc_now(),
    }
    judge_receipt = {
        "schema": "battle.judge_receipt.v1",
        "battle_id": battle_id,
        "round_number": 1,
        "status": status,
        "verdict": verdict,
        "winner": winner,
        "arena_team_is_judge": False,
        "exploit_confirmed_before_patch": planted_ok,
        "red_exploited_before_patch": red_exploited,
        "blue_patch_completed": blue_patched,
        "exploit_blocked_after_patch": safe_ok,
        "regression_tests_pass": regression_ok,
        "functionality_preserved": safe_ok and regression_ok,
        "commands_run": [safe_cmd, regression_cmd],
        "next_agent": "human",
        "created_at": utc_now(),
    }
    scoreboard = {
        "schema": "battle.scoreboard.v1",
        "battle_id": battle_id,
        "status": status,
        "verdict": verdict,
        "winner": winner,
        "race": {
            "red_delay_seconds": red_delay,
            "blue_delay_seconds": blue_delay,
            "red_finished_at_seconds": red_result["finished_at_seconds"],
            "blue_finished_at_seconds": blue_result["finished_at_seconds"],
            "exploit_before_patch": red_exploited,
            "patch_before_exploit": blue_patched and not red_exploited,
        },
        "tau": {
            "agentic": agentic,
            "receipts_valid": tau_receipt["tau_receipts_valid"],
            "harness": tau_receipt["harness"],
            "personas": tau_receipt["personas"],
        },
        "context": {
            "enabled": context_receipts,
            "status": context_receipt["status"],
            "receipt": "context/context-receipt.json"
            if context_receipts
            else None,
            "warm_pond_execution_status": warm_pond_execution_receipt["status"],
            "warm_pond_executed_attempts": warm_pond_execution_receipt.get(
                "selected_attempt_count", 0
            ),
            "warm_pond_passed_attempts": warm_pond_execution_receipt.get(
                "passed_attempt_count", 0
            ),
        },
        "red_score": 1.5 if red_exploited else 0.0,
        "blue_score": 3.6 if winner == "blue" else 0.0,
        "tdsr": 1.0 if winner == "blue" else 0.0,
        "fdsr": 1.0 if verdict == "FAKE_DEFENSE" else 0.0,
        "asc": 1 if red_exploited else 0,
        "receipts": {
            "arena": "arena-receipt.json",
            "red": "red-receipt.json",
            "blue": "blue-receipt.json",
            "judge": "judge/judge-receipt.json",
            "tau": "tau/team-receipt.json",
            **({"context": "context/context-receipt.json"} if context_receipts else {}),
        },
    }

    write_json(out_dir / "red-receipt.json", red_receipt)
    write_json(out_dir / "blue-receipt.json", blue_receipt)
    write_json(out_dir / "judge" / "judge-receipt.json", judge_receipt)
    write_json(out_dir / "scoreboard.json", scoreboard)
    memory_store_receipt = (
        store_battle_memory_outcome(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            scenario=scenario,
            scoreboard=scoreboard,
            judge_receipt=judge_receipt,
            red_persona=red_persona,
            blue_persona=blue_persona,
        )
        if context_receipts
        else skipped_memory_store_receipt(battle_id=battle_id, run_id=run_id)
    )
    if context_receipts:
        memory_store_path = out_dir / "context" / "memory-store-receipt.json"
        record_event(
            ledger_path,
            run_id=run_id,
            battle_id=battle_id,
            team="orchestrator",
            persona="battle-orchestrator",
            event_type="memory_store",
            status=str(memory_store_receipt["status"]),
            artifact_path=memory_store_path,
            details=memory_store_receipt,
        )
        context_receipt["memory_store"] = "context/memory-store-receipt.json"
        context_receipt["memory"]["store_status"] = memory_store_receipt["status"]
        context_receipt["artifacts"].append("context/memory-store-receipt.json")
        write_json(out_dir / "context" / "context-receipt.json", context_receipt)
        scoreboard["context"]["memory_store_status"] = memory_store_receipt["status"]
        write_json(out_dir / "scoreboard.json", scoreboard)
    if context_receipts and memory_store_receipt["status"] != "PASS":
        status = "BLOCKED"
        verdict = "BLOCKED"
        scoreboard["status"] = status
        scoreboard["verdict"] = verdict
        scoreboard["reason"] = "memory_outcome_store_failed"
        write_json(out_dir / "scoreboard.json", scoreboard)
    run_receipt = {
        "schema": "battle.run_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": status,
        "verdict": verdict,
        "execution": execution_scope,
        "claim_scope": "arena_hidden_vulnerability_docker_race_proof",
        "non_claims": non_claims_for(
            agentic=agentic,
            scillm_plan=scillm_plan,
            context_receipts=context_receipts,
        ),
        "context_receipt": "context/context-receipt.json"
        if context_receipts
        else None,
        "memory_store_receipt": "context/memory-store-receipt.json"
        if context_receipts
        else None,
        "artifacts": artifact_list(out_dir),
    }
    write_json(out_dir / "run-receipt.json", run_receipt)
    write_json(
        out_dir / "monitor-index.json",
        {
            "schema": "battle.monitor_index.v1",
            "battle_id": battle_id,
            "campaign": "Battle",
            "scenario": scenario.get("scenario_id"),
            "title": scenario.get("title"),
            "status": status,
            "verdict": verdict,
            "players": [
                {"team": "arena", "persona": "Arena Team", "role": "target-builder", "receipt": "arena-receipt.json"},
                {"team": "red", "persona": red_persona, "role": "exploit-racer", "receipt": "red-receipt.json"},
                {"team": "blue", "persona": blue_persona, "role": "patch-racer", "receipt": "blue-receipt.json"},
                {"team": "judge", "persona": "Scorekeeper", "role": "objective-recorder", "receipt": "judge/judge-receipt.json"},
            ],
            "scoreboard": "scoreboard.json",
            "artifacts": artifact_list(out_dir),
        },
    )
    return run_receipt


def skipped_context_receipt(*, battle_id: str, run_id: str) -> dict[str, Any]:
    return {
        "schema": "battle.context_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "SKIPPED",
        "reason": "context_receipts_disabled",
    }


def skipped_memory_store_receipt(*, battle_id: str, run_id: str) -> dict[str, Any]:
    return {
        "schema": "battle.memory_store_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "SKIPPED",
        "reason": "context_receipts_disabled",
    }


def prepare_context_receipts(
    *,
    scenario: dict[str, Any],
    hidden: dict[str, Any],
    battle_id: str,
    run_id: str,
    image: str,
    target: Path,
    out_dir: Path,
    ledger_path: Path,
    red_persona: str,
    blue_persona: str,
) -> dict[str, Any]:
    context_dir = out_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)

    memory_recall = run_memory_recall_receipt(
        battle_id=battle_id,
        run_id=run_id,
        scenario=scenario,
        hidden=hidden,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )
    memory_recall_path = write_json(context_dir / "memory-recall-receipt.json", memory_recall)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="memory_recall",
        status=str(memory_recall["status"]),
        artifact_path=memory_recall_path,
        details=memory_recall,
    )

    code_context = build_code_context_receipt(
        battle_id=battle_id,
        run_id=run_id,
        target=target,
        out_dir=out_dir,
    )
    code_context_path = write_json(context_dir / "code-context-receipt.json", code_context)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="code_context",
        status=str(code_context["status"]),
        artifact_path=code_context_path,
        details=code_context,
    )

    scan = run_fast_scan_receipt(
        battle_id=battle_id,
        run_id=run_id,
        image=image,
        target=target,
        out_dir=out_dir,
        scenario=scenario,
    )
    scan_path = write_json(context_dir / "fast-scan-receipt.json", scan)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="fast_scan",
        status=str(scan["status"]),
        artifact_path=scan_path,
        details=to_jsonable(scan),
    )

    brave_search = run_brave_search_receipt(
        battle_id=battle_id,
        run_id=run_id,
        scenario=scenario,
        hidden=hidden,
        scan=scan,
        code_context=code_context,
        out_dir=out_dir,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )
    brave_path = write_json(context_dir / "brave-search-receipt.json", brave_search)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="brave_search",
        status=str(brave_search["status"]),
        artifact_path=brave_path,
        details=brave_search,
    )

    research = build_research_receipt(
        battle_id=battle_id,
        run_id=run_id,
        scenario=scenario,
        hidden=hidden,
        memory_recall=memory_recall,
        code_context=code_context,
        scan=scan,
        brave_search=brave_search,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )
    research_path = write_json(context_dir / "research-receipt.json", research)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="research_seed",
        status=str(research["status"]),
        artifact_path=research_path,
        details=research,
    )

    warm_pond = build_warm_pond_receipt(
        battle_id=battle_id,
        run_id=run_id,
        scenario=scenario,
        hidden=hidden,
        scan=scan,
        brave_search=brave_search,
        code_context=code_context,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )
    warm_pond_path = write_json(context_dir / "warm-pond-receipt.json", warm_pond)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="warm_pond_candidates",
        status=str(warm_pond["status"]),
        artifact_path=warm_pond_path,
        details=warm_pond,
    )

    ok = (
        memory_recall["status"] == "PASS"
        and code_context["status"] == "PASS"
        and scan["status"] == "PASS"
        and brave_search["status"] == "PASS"
        and research["status"] == "PASS"
        and warm_pond["status"] == "PASS"
    )
    receipt = {
        "schema": "battle.context_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS" if ok else "BLOCKED",
        "memory_recall": "context/memory-recall-receipt.json",
        "code_context": "context/code-context-receipt.json",
        "fast_scan": "context/fast-scan-receipt.json",
        "brave_search": "context/brave-search-receipt.json",
        "research": "context/research-receipt.json",
        "warm_pond": "context/warm-pond-receipt.json",
        "memory": {
            "base_url": MEMORY_BASE_URL,
            "recall_status": memory_recall["status"],
            "recall_found": memory_recall.get("battle_round_memory", {}).get("found"),
            "persona_red_found": memory_recall.get("red_persona_memory", {}).get("found"),
            "persona_blue_found": memory_recall.get("blue_persona_memory", {}).get("found"),
        },
        "code": {
            "symbol_count": code_context.get("symbol_count", 0),
            "treesitter_status": code_context.get("treesitter", {}).get("status"),
        },
        "scan": {
            "status": scan["status"],
            "finding_count": scan.get("finding_count", 0),
            "families": scan.get("families", []),
        },
        "brave": {
            "status": brave_search["status"],
            "query_count": len(brave_search.get("queries", [])),
            "result_count": brave_search.get("result_count", 0),
        },
        "warm_pond_candidates": {
            "status": warm_pond["status"],
            "exploit_candidate_count": warm_pond.get("exploit_candidate_count", 0),
            "defense_candidate_count": warm_pond.get("defense_candidate_count", 0),
            "combination_count": warm_pond.get("combination_count", 0),
        },
        "artifacts": [
            "context/memory-recall-receipt.json",
            "context/code-context-receipt.json",
            "context/fast-scan-receipt.json",
            "context/brave-search-receipt.json",
            "context/research-receipt.json",
            "context/warm-pond-receipt.json",
        ],
        "non_claims": [
            "does_not_prove_dogpile_research",
            "does_not_prove_treesitter_success_when_treesitter_status_is_blocked",
            "does_not_execute_warm_pond_candidates_yet",
        ],
    }
    write_json(context_dir / "context-receipt.json", receipt)
    return receipt


def run_memory_recall_receipt(
    *,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    hidden: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> dict[str, Any]:
    queries = {
        "battle_round_memory": {
            "q": (
                "What prior Battle memories discuss hidden SQL injection, reflected "
                "XSS, patch-before-exploit races, and Blue parameterized SQL fixes?"
            ),
            "k": 5,
            "collections": ["battle_round_memory"],
            "scope": "battle",
        },
        "red_persona_memory": {
            "q": (
                f"What persona memory should guide {red_persona} when selecting "
                "a Red Team exploit hypothesis for SQL injection and XSS?"
            ),
            "k": 5,
            "collections": ["persona_memory"],
            "tags": [f"persona:{red_persona}"],
        },
        "blue_persona_memory": {
            "q": (
                f"What persona memory should guide {blue_persona} when selecting "
                "a Blue Team defense for SQL injection and XSS?"
            ),
            "k": 5,
            "collections": ["persona_memory"],
            "tags": [f"persona:{blue_persona}"],
        },
    }
    receipt: dict[str, Any] = {
        "schema": "battle.memory_recall_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS",
        "memory_base_url": MEMORY_BASE_URL,
        "scenario_id": scenario.get("scenario_id"),
        "hidden_vulnerability_ids": [
            item.get("id") for item in hidden.get("hidden_vulnerabilities", [])
        ],
        "queries": queries,
    }
    try:
        with httpx.Client(
            base_url=MEMORY_BASE_URL,
            timeout=httpx.Timeout(10.0, connect=2.0),
        ) as client:
            for name, payload in queries.items():
                response = client.post("/recall", json=payload)
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])
                receipt[name] = {
                    "status": "PASS",
                    "found": bool(data.get("found")),
                    "should_scan": bool(data.get("should_scan")),
                    "confidence": data.get("confidence"),
                    "item_count": len(items),
                    "top_keys": [item.get("_key") for item in items[:3]],
                    "top_scores": [item.get("scores") for item in items[:3]],
                    "meta": data.get("meta", {}),
                }
    except Exception as exc:
        receipt["status"] = "BLOCKED"
        receipt["reason"] = f"memory_recall_failed: {type(exc).__name__}: {exc}"
    return receipt


def build_code_context_receipt(
    *,
    battle_id: str,
    run_id: str,
    target: Path,
    out_dir: Path,
) -> dict[str, Any]:
    app_path = target / "app.py"
    source = app_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    string_literals: list[str] = []
    call_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.FunctionDef):
            functions.append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": getattr(node, "end_lineno", node.lineno),
                    "args": [arg.arg for arg in node.args.args],
                }
            )
        elif isinstance(node, ast.ClassDef):
            classes.append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": getattr(node, "end_lineno", node.lineno),
                }
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value and len(string_literals) < 20:
                string_literals.append(node.value[:160])
        elif isinstance(node, ast.Call):
            name = call_name(node.func)
            if name:
                call_names.append(name)

    vulnerable_terms = [
        term
        for term in ["execute", "LIKE", "query", "parse_qs", "render_search"]
        if term in source
    ]
    treesitter = run_treesitter_diagnostic(app_path=app_path, out_dir=out_dir)
    return {
        "schema": "battle.code_context_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS" if functions else "BLOCKED",
        "source": "python_ast_with_optional_treesitter_diagnostic",
        "target_file": str(app_path),
        "imports": sorted(set(imports)),
        "functions": functions,
        "classes": classes,
        "symbol_count": len(functions) + len(classes),
        "call_names": sorted(set(call_names))[:40],
        "string_literal_count": len(string_literals),
        "string_literals_sample": string_literals[:8],
        "vulnerability_terms": vulnerable_terms,
        "treesitter": treesitter,
    }


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def run_treesitter_diagnostic(*, app_path: Path, out_dir: Path) -> dict[str, Any]:
    artifact_dir = out_dir / "context"
    stdout_path = artifact_dir / "treesitter.stdout.json"
    stderr_path = artifact_dir / "treesitter.stderr.txt"
    command = [
        str(SKILLS_ROOT / "treesitter" / "run.sh"),
        "symbols",
        str(app_path),
        "--json",
    ]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        return {
            "status": "BLOCKED",
            "reason": "treesitter_timeout",
            "command": command,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    payload: dict[str, Any] = {
        "status": "PASS" if proc.returncode == 0 else "BLOCKED",
        "command": command,
        "exit_code": proc.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    if proc.returncode == 0:
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = []
            payload["status"] = "BLOCKED"
            payload["reason"] = "treesitter_invalid_json"
        payload["symbol_count"] = len(parsed) if isinstance(parsed, list) else 0
    else:
        payload["reason"] = "treesitter_command_failed"
    return payload


def run_fast_scan_receipt(
    *,
    battle_id: str,
    run_id: str,
    image: str,
    target: Path,
    out_dir: Path,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    scan_script = r"""
import json
from pathlib import Path

source = Path("app.py").read_text(encoding="utf-8")
findings = []
if "f\"SELECT" in source or "f'SELECT" in source or "execute(sql)" in source:
    findings.append({
        "id": "scan-sqli-string-format",
        "family": "sql_injection",
        "cwe": "CWE-89",
        "symbol": "search_users",
        "evidence": "SQL query appears to be constructed from string interpolation before execute.",
        "entry_point": "/search?q=<term>",
    })
if "value=\"{query}\"" in source or "Results for {query}" in source:
    findings.append({
        "id": "scan-reflected-query-html",
        "family": "reflected_xss",
        "cwe": "CWE-79",
        "symbol": "render_search",
        "evidence": "Raw query appears in rendered HTML without escaping.",
        "entry_point": "/search?q=<term>",
    })
print(json.dumps({
    "schema": "battle.fast_scan_output.v1",
    "target_file": "app.py",
    "finding_count": len(findings),
    "findings": findings,
}, indent=2))
"""
    ok, command = run_docker_command(
        image=image,
        target=target,
        command=["python", "-c", scan_script],
        artifact_dir=out_dir / "context",
        name="fast-scan",
    )
    scan_output: dict[str, Any] = {}
    parse_error: str | None = None
    if command.stdout_path:
        try:
            scan_output = json.loads(Path(command.stdout_path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

    findings = scan_output.get("findings", []) if isinstance(scan_output, dict) else []
    families = sorted(
        {
            str(item.get("family"))
            for item in findings
            if isinstance(item, dict) and item.get("family")
        }
    )
    status = "PASS" if ok and isinstance(findings, list) and parse_error is None else "BLOCKED"
    receipt = {
        "schema": "battle.fast_scan_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": status,
        "scenario_id": scenario.get("scenario_id"),
        "surface": "docker_static_source_scan",
        "mocked": False,
        "live": "docker_no_network",
        "command": command,
        "finding_count": len(findings),
        "families": families,
        "findings": findings,
    }
    if parse_error:
        receipt["reason"] = f"scan_json_parse_failed: {parse_error}"
    return receipt


def run_brave_search_receipt(
    *,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    hidden: dict[str, Any],
    scan: dict[str, Any],
    code_context: dict[str, Any],
    out_dir: Path,
    red_persona: str,
    blue_persona: str,
) -> dict[str, Any]:
    artifact_dir = out_dir / "context"
    stdout_path = artifact_dir / "brave-search.stdout.json"
    stderr_path = artifact_dir / "brave-search.stderr.txt"
    queries = scan_brave_queries(
        scenario=scenario,
        hidden=hidden,
        scan=scan,
        code_context=code_context,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )
    command = [
        str(SKILLS_ROOT / "brave-search" / "run.sh"),
        "batch",
        "--queries-file",
        "-",
        "--count",
        "2",
        "--workers",
        "4",
        "--search-type",
        "brave",
        "--rate-limit",
        "0",
    ]
    try:
        proc = subprocess.run(
            command,
            input=json.dumps(queries),
            cwd=str(SKILLS_ROOT / "brave-search"),
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        return {
            "schema": "battle.brave_search_receipt.v1",
            "battle_id": battle_id,
            "run_id": run_id,
            "status": "BLOCKED",
            "reason": "brave_search_timeout",
            "queries": queries,
            "command": command,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }

    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    parsed: dict[str, Any] = {}
    parse_error: str | None = None
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        parse_error = str(exc)

    results = []
    if isinstance(parsed, dict):
        for entry in parsed.values():
            if not isinstance(entry, dict):
                continue
            web = entry.get("web", {})
            if isinstance(web, dict):
                for item in web.get("results", []) or []:
                    if isinstance(item, dict):
                        results.append(
                            {
                                "title": item.get("title", ""),
                                "url": item.get("url", ""),
                                "description": item.get("description", ""),
                            }
                        )

    status = "PASS" if proc.returncode == 0 and parse_error is None else "BLOCKED"
    receipt = {
        "schema": "battle.brave_search_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": status,
        "surface": "brave_search_batch",
        "mocked": False,
        "live": True,
        "queries": queries,
        "query_count": len(queries),
        "result_count": len(results),
        "top_results": results[:8],
        "command": command,
        "exit_code": proc.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    if parse_error:
        receipt["reason"] = f"brave_json_parse_failed: {parse_error}"
    elif proc.returncode != 0:
        receipt["reason"] = "brave_search_command_failed"
    return receipt


def scan_brave_queries(
    *,
    scenario: dict[str, Any],
    hidden: dict[str, Any],
    scan: dict[str, Any],
    code_context: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> list[str]:
    families = " ".join(scan.get("families", []))
    cwes = " ".join(
        str(item.get("cwe"))
        for item in hidden.get("hidden_vulnerabilities", [])
        if item.get("cwe")
    )
    symbols = " ".join(
        item.get("symbol", "")
        for item in scan.get("findings", [])
        if isinstance(item, dict)
    )
    functions = " ".join(item.get("name", "") for item in code_context.get("functions", []))
    base = scenario.get("entry_point", {}).get("path", "/search?q=<term>")
    return [
        f"{base} {families} {cwes} exploit payload python sqlite",
        f"{symbols} {functions} Python sqlite SQL injection reflected XSS mitigation html.escape",
        f"{red_persona} red team combine SQL injection reflected XSS exploit strategy",
        f"{blue_persona} blue team patch SQL injection reflected XSS parameterized query escaping",
    ]


def build_research_receipt(
    *,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    hidden: dict[str, Any],
    memory_recall: dict[str, Any],
    code_context: dict[str, Any],
    scan: dict[str, Any],
    brave_search: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> dict[str, Any]:
    cwes = [item.get("cwe") for item in hidden.get("hidden_vulnerabilities", [])]
    symbols = [item["name"] for item in code_context.get("functions", [])]
    queries = [
        f"{scenario.get('scenario_id')} {' '.join(cwes)} exploit defense",
        "Python sqlite parameterized query reflected XSS html.escape mitigation",
        f"{red_persona} Red Team hidden SQL injection reflected XSS exploit hypothesis",
        f"{blue_persona} Blue Team parameterized SQL HTML escaping patch strategy",
    ]
    return {
        "schema": "battle.research_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS",
        "source": "memory_recall_and_code_context_seed",
        "external_search": {
            "brave_search": brave_search["status"],
            "dogpile": "not_exercised_in_this_proof",
        },
        "recommended_queries": queries,
        "scan_findings": scan.get("findings", []),
        "brave_top_results": brave_search.get("top_results", []),
        "memory_found": {
            "battle_round_memory": memory_recall.get("battle_round_memory", {}).get("found"),
            "red_persona_memory": memory_recall.get("red_persona_memory", {}).get("found"),
            "blue_persona_memory": memory_recall.get("blue_persona_memory", {}).get("found"),
        },
        "code_symbols": symbols,
        "cwes": cwes,
        "next_round_seed": {
            "red": "try exploit variants around search_users and render_search",
            "blue": "prioritize parameterized SQL and output encoding before Red delay expires",
        },
    }


def build_warm_pond_receipt(
    *,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    hidden: dict[str, Any],
    scan: dict[str, Any],
    brave_search: dict[str, Any],
    code_context: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> dict[str, Any]:
    findings = [
        item for item in scan.get("findings", []) if isinstance(item, dict)
    ]
    exploit_candidates = []
    defense_candidates = []
    for finding in findings:
        family = finding.get("family")
        symbol = finding.get("symbol")
        if family == "sql_injection":
            exploit_candidates.extend(
                [
                    {
                        "id": "exploit-sqli-admin-or",
                        "family": family,
                        "symbol": symbol,
                        "payload": "nomatch%' OR role='admin' --",
                        "source": "fast_scan_plus_hidden_oracle_family",
                    },
                    {
                        "id": "exploit-sqli-like-wildcard",
                        "family": family,
                        "symbol": symbol,
                        "payload": "%' OR '1'='1' --",
                        "source": "fast_scan_plus_brave_seed",
                    },
                ]
            )
            defense_candidates.extend(
                [
                    {
                        "id": "defense-parameterized-like",
                        "family": family,
                        "symbol": symbol,
                        "strategy": "replace interpolated SQL with parameterized LIKE query",
                    },
                    {
                        "id": "defense-sql-regression-oracle",
                        "family": family,
                        "symbol": symbol,
                        "strategy": "add regression that admin is not returned for SQL payload",
                    },
                ]
            )
        elif family == "reflected_xss":
            exploit_candidates.extend(
                [
                    {
                        "id": "exploit-xss-script-reflection",
                        "family": family,
                        "symbol": symbol,
                        "payload": "<script>alert(1)</script>",
                        "source": "fast_scan_plus_hidden_oracle_family",
                    },
                    {
                        "id": "exploit-xss-attribute-breakout",
                        "family": family,
                        "symbol": symbol,
                        "payload": '\" autofocus onfocus=alert(1) x=\"',
                        "source": "fast_scan_plus_brave_seed",
                    },
                ]
            )
            defense_candidates.extend(
                [
                    {
                        "id": "defense-html-escape-query",
                        "family": family,
                        "symbol": symbol,
                        "strategy": "HTML-escape query before rendering into attributes or text",
                    },
                    {
                        "id": "defense-xss-regression-oracle",
                        "family": family,
                        "symbol": symbol,
                        "strategy": "add regression that script payload is escaped",
                    },
                ]
            )

    combinations = []
    for exploit in exploit_candidates:
        for defense in defense_candidates:
            if exploit["family"] == defense["family"]:
                affinity = 1.0
            else:
                affinity = 0.72
            combinations.append(
                {
                    "id": f"{exploit['id']}__{defense['id']}",
                    "exploit": exploit["id"],
                    "defense": defense["id"],
                    "families": sorted({exploit["family"], defense["family"]}),
                    "affinity": affinity,
                    "reason": "same-family direct countermeasure"
                    if affinity == 1.0
                    else "cross-family chain candidate",
                }
            )

    return {
        "schema": "battle.warm_pond_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS" if exploit_candidates and defense_candidates else "BLOCKED",
        "scenario_id": scenario.get("scenario_id"),
        "red_persona": red_persona,
        "blue_persona": blue_persona,
        "hidden_cwes": [
            item.get("cwe") for item in hidden.get("hidden_vulnerabilities", [])
        ],
        "code_symbols": [item.get("name") for item in code_context.get("functions", [])],
        "brave_result_count": brave_search.get("result_count", 0),
        "exploit_candidate_count": len(exploit_candidates),
        "defense_candidate_count": len(defense_candidates),
        "combination_count": len(combinations),
        "exploit_candidates": exploit_candidates,
        "defense_candidates": defense_candidates,
        "combinations": combinations,
        "selection_rule": "promote candidates only after Docker scorekeeper evidence; retain failures as negative evidence",
        "execution": "not_executed_in_this_receipt_candidates_only",
    }


def skipped_warm_pond_execution_receipt(*, battle_id: str, run_id: str) -> dict[str, Any]:
    return {
        "schema": "battle.warm_pond_execution_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "SKIPPED",
        "reason": "context_receipts_disabled",
        "selected_attempt_count": 0,
        "passed_attempt_count": 0,
        "failed_attempt_count": 0,
        "attempts": [],
    }


def run_warm_pond_execution_receipt(
    *,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    image: str,
    target: Path,
    patches: Path,
    out_dir: Path,
    ledger_path: Path,
    red_persona: str,
    blue_persona: str,
) -> dict[str, Any]:
    """Execute a bounded warm-pond candidate matrix in isolated Docker workspaces."""

    context_dir = out_dir / "context"
    warm_pond_path = context_dir / "warm-pond-receipt.json"
    execution_dir = context_dir / "warm-pond-execution"
    execution_dir.mkdir(parents=True, exist_ok=True)

    warm_pond = json.loads(warm_pond_path.read_text(encoding="utf-8"))
    exploit_by_id = {
        item["id"]: item
        for item in warm_pond.get("exploit_candidates", [])
        if isinstance(item, dict) and item.get("id")
    }
    defense_by_id = {
        item["id"]: item
        for item in warm_pond.get("defense_candidates", [])
        if isinstance(item, dict) and item.get("id")
    }
    combinations = [
        item
        for item in warm_pond.get("combinations", [])
        if isinstance(item, dict)
        and item.get("exploit") in exploit_by_id
        and item.get("defense") in defense_by_id
    ]
    max_attempts = int(scenario.get("warm_pond", {}).get("max_execution_attempts", 4))
    selected = sorted(
        combinations,
        key=lambda item: (-float(item.get("affinity", 0.0)), str(item.get("id", ""))),
    )[:max_attempts]

    attempts: list[dict[str, Any]] = []
    if selected:
        with ThreadPoolExecutor(max_workers=min(4, len(selected))) as executor:
            futures = [
                executor.submit(
                    execute_warm_pond_attempt,
                    battle_id=battle_id,
                    run_id=run_id,
                    image=image,
                    target=target,
                    patches=patches,
                    execution_dir=execution_dir,
                    combination=combination,
                    exploit=exploit_by_id[str(combination["exploit"])],
                    defense=defense_by_id[str(combination["defense"])],
                    regression_command=scenario["commands"]["regression"],
                )
                for combination in selected
            ]
            for future in futures:
                attempt = future.result(timeout=90)
                attempts.append(attempt)
                record_event(
                    ledger_path,
                    run_id=run_id,
                    battle_id=battle_id,
                    team="red_blue",
                    persona=f"{red_persona}+{blue_persona}",
                    event_type="warm_pond_attempt",
                    status=str(attempt["status"]),
                    artifact_path=Path(attempt["receipt_path"]),
                    details=to_jsonable(attempt),
                )

    passed = [attempt for attempt in attempts if attempt["status"] == "PASS"]
    failed = [attempt for attempt in attempts if attempt["status"] != "PASS"]
    receipt = {
        "schema": "battle.warm_pond_execution_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS" if selected and not failed else "BLOCKED",
        "mocked": False,
        "live": "docker_no_network_bounded_candidate_execution",
        "source_candidates": "context/warm-pond-receipt.json",
        "selection_rule": "highest_affinity_then_id",
        "max_execution_attempts": max_attempts,
        "selected_attempt_count": len(selected),
        "passed_attempt_count": len(passed),
        "failed_attempt_count": len(failed),
        "attempts": attempts,
        "non_claims": [
            "does_not_execute_unbounded_warm_pond_swarm",
            "does_not_promote_warm_pond_winners_across_rounds_yet",
            "does_not_run_dogpile_or_github_search_candidates",
        ],
    }
    if not selected:
        receipt["reason"] = "no_warm_pond_combinations_selected"
    write_json(context_dir / "warm-pond-execution-receipt.json", receipt)
    return receipt


def execute_warm_pond_attempt(
    *,
    battle_id: str,
    run_id: str,
    image: str,
    target: Path,
    patches: Path,
    execution_dir: Path,
    combination: dict[str, Any],
    exploit: dict[str, Any],
    defense: dict[str, Any],
    regression_command: list[str],
) -> dict[str, Any]:
    attempt_id = safe_key(str(combination["id"]))
    attempt_dir = execution_dir / "attempts" / attempt_id
    workspace = attempt_dir / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(target, workspace)

    before_ok, before_cmd = run_docker_command(
        image=image,
        target=workspace,
        command=exploit_probe_command(exploit=exploit, expect_success=True),
        artifact_dir=attempt_dir,
        name="exploit-before-patch",
    )
    patch_ok, patch_cmd = run_docker_command(
        image=image,
        target=workspace,
        command=[
            "python",
            "-c",
            "import shutil; shutil.copyfile('/patches/app.py', '/workspace/app.py')",
        ],
        artifact_dir=attempt_dir,
        name="apply-defense",
        extra_mounts=[(patches, Path("/patches"), "ro")],
    )
    after_ok, after_cmd = run_docker_command(
        image=image,
        target=workspace,
        command=exploit_probe_command(exploit=exploit, expect_success=False),
        artifact_dir=attempt_dir,
        name="exploit-after-patch",
    )
    regression_ok, regression_cmd = run_docker_command(
        image=image,
        target=workspace,
        command=regression_command,
        artifact_dir=attempt_dir,
        name="regression-after-patch",
    )

    status = "PASS" if before_ok and patch_ok and after_ok and regression_ok else "FAIL"
    receipt = {
        "schema": "battle.warm_pond_attempt_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "status": status,
        "combination_id": combination["id"],
        "families": combination.get("families", []),
        "affinity": combination.get("affinity"),
        "exploit": exploit,
        "defense": defense,
        "workspace": str(workspace),
        "isolation": "copied_workspace_reverted_by_discarding_attempt_directory",
        "results": {
            "exploit_succeeded_before_patch": before_ok,
            "defense_applied": patch_ok,
            "exploit_blocked_after_patch": after_ok,
            "regression_passed": regression_ok,
        },
        "commands_run": [before_cmd, patch_cmd, after_cmd, regression_cmd],
        "created_at": utc_now(),
    }
    receipt_path = attempt_dir / "attempt-receipt.json"
    write_json(receipt_path, receipt)
    receipt["receipt_path"] = str(receipt_path)
    write_json(receipt_path, receipt)
    return receipt


def exploit_probe_command(*, exploit: dict[str, Any], expect_success: bool) -> list[str]:
    family = str(exploit.get("family", ""))
    payload = str(exploit.get("payload", ""))
    if family == "sql_injection":
        predicate = "'<li>admin</li>' in html"
    elif family == "reflected_xss":
        predicate = "payload in html"
    else:
        predicate = "False"
    script = f"""
from app import render_search
payload = {payload!r}
html = render_search(payload)
success = bool({predicate})
raise SystemExit(0 if success is {expect_success!r} else 1)
"""
    return ["python", "-c", script]


def store_battle_memory_outcome(
    *,
    out_dir: Path,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    scoreboard: dict[str, Any],
    judge_receipt: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> dict[str, Any]:
    context_dir = out_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    key = safe_key(f"{battle_id}:{run_id}:round-1")
    document = {
        "_key": key,
        "schema": "battle.round_memory.v1",
        "kind": "battle_round_outcome",
        "battle_id": battle_id,
        "run_id": run_id,
        "scenario_id": scenario.get("scenario_id"),
        "round_number": 1,
        "status": scoreboard.get("status"),
        "verdict": scoreboard.get("verdict"),
        "winner": scoreboard.get("winner"),
        "red_persona": red_persona,
        "blue_persona": blue_persona,
        "patch_before_exploit": scoreboard.get("race", {}).get("patch_before_exploit"),
        "exploit_before_patch": scoreboard.get("race", {}).get("exploit_before_patch"),
        "exploit_blocked_after_patch": judge_receipt.get("exploit_blocked_after_patch"),
        "regression_tests_pass": judge_receipt.get("regression_tests_pass"),
        "problem": (
            "Battle hidden SQL injection and reflected XSS race over a tiny "
            "/search?q=<term> Python app."
        ),
        "solution": (
            f"Outcome {scoreboard.get('verdict')}: Blue used parameterized SQL "
            "and HTML escaping before Red's delayed exploit attempt."
        ),
        "text": (
            f"Battle {battle_id} {scenario.get('scenario_id')} winner="
            f"{scoreboard.get('winner')} verdict={scoreboard.get('verdict')} "
            f"red={red_persona} blue={blue_persona}"
        ),
        "tags": [
            "battle",
            "battle_round_memory",
            "security",
            "CWE-89",
            "CWE-79",
            "patch_before_exploit",
            f"persona:{red_persona}",
            f"persona:{blue_persona}",
        ],
        "artifact_paths": {
            "run_receipt": str(out_dir / "run-receipt.json"),
            "scoreboard": str(out_dir / "scoreboard.json"),
            "judge_receipt": str(out_dir / "judge" / "judge-receipt.json"),
        },
        "created_at": utc_now(),
    }
    receipt: dict[str, Any] = {
        "schema": "battle.memory_store_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS",
        "memory_base_url": MEMORY_BASE_URL,
        "collection": "battle_round_memory",
        "document_key": key,
    }
    try:
        with httpx.Client(
            base_url=MEMORY_BASE_URL,
            timeout=httpx.Timeout(10.0, connect=2.0),
        ) as client:
            response = client.post(
                "/upsert",
                json={"collection": "battle_round_memory", "documents": [document]},
            )
            receipt["http_status"] = response.status_code
            response.raise_for_status()
            receipt["response"] = response.json()
    except Exception as exc:
        receipt["status"] = "BLOCKED"
        receipt["reason"] = f"memory_store_failed: {type(exc).__name__}: {exc}"
    write_json(context_dir / "memory-store-receipt.json", receipt)
    return receipt


def safe_key(value: str) -> str:
    return "".join(char if char.isalnum() or char in "_-" else "_" for char in value)


def prepare_tau_receipts(
    *,
    scenario: dict[str, Any],
    battle_id: str,
    run_id: str,
    goal: dict[str, Any],
    out_dir: Path,
    tau_dir: Path,
    ledger_path: Path,
    red_persona: str,
    blue_persona: str,
    agentic: bool,
    scillm_plan: bool,
    scillm_model: str,
) -> dict[str, Any]:
    persona_probes = {
        "red": probe_persona(red_persona),
        "blue": probe_persona(blue_persona),
    }
    model_selection = {
        "schema": "battle.model_selection.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "agentic": agentic,
        "scillm_plan": scillm_plan,
        "red": {
            "persona": red_persona,
            "model": "tau-local-deterministic-provider" if agentic else None,
            "surface": "tau_agent_harness" if agentic else "not_exercised",
            "scillm": scillm_model if scillm_plan else "not_exercised",
            "reason": "Fast deterministic attack-selection proof before live scillm routing.",
        },
        "blue": {
            "persona": blue_persona,
            "model": "tau-local-deterministic-provider" if agentic else None,
            "surface": "tau_agent_harness" if agentic else "not_exercised",
            "scillm": scillm_model if scillm_plan else "not_exercised",
            "reason": "Fast deterministic patch-selection proof before live scillm routing.",
        },
    }
    model_selection_path = write_json(tau_dir / "model-selection.json", model_selection)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="model_selection",
        status="PASS",
        artifact_path=model_selection_path,
        details=model_selection,
    )

    red_scillm = (
        run_scillm_action_selection(
            out_dir=tau_dir,
            team="red",
            persona=red_persona,
            model=scillm_model,
            prompt=(
                "You are a Battle Red Team action selector. The Arena brief is "
                f"{scenario.get('arena_team', {}).get('public_brief')!r}. "
                "Choose one bounded exploit hypothesis for a hidden SQLi/XSS race. "
                "Do not write code. Reply in one sentence."
            ),
        )
        if scillm_plan
        else skipped_scillm_selection("red", scillm_model)
    )
    write_json(tau_dir / "red-scillm-selection.json", red_scillm)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="red",
        persona=red_persona,
        event_type="scillm_action_selection",
        status=str(red_scillm.get("status", "BLOCKED")),
        artifact_path=tau_dir / "red-scillm-selection.json",
        details=red_scillm,
    )

    blue_scillm = (
        run_scillm_action_selection(
            out_dir=tau_dir,
            team="blue",
            persona=blue_persona,
            model=scillm_model,
            prompt=(
                "You are a Battle Blue Team action selector. The Arena brief is "
                f"{scenario.get('arena_team', {}).get('public_brief')!r}. "
                "Choose one bounded defense for a hidden SQLi/XSS race. "
                "Do not write code. Reply in one sentence."
            ),
        )
        if scillm_plan
        else skipped_scillm_selection("blue", scillm_model)
    )
    write_json(tau_dir / "blue-scillm-selection.json", blue_scillm)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="blue",
        persona=blue_persona,
        event_type="scillm_action_selection",
        status=str(blue_scillm.get("status", "BLOCKED")),
        artifact_path=tau_dir / "blue-scillm-selection.json",
        details=blue_scillm,
    )

    if scillm_plan and (
        red_scillm.get("status") != "PASS" or blue_scillm.get("status") != "PASS"
    ):
        receipt = {
            "schema": "battle.tau_team_receipt.v1",
            "battle_id": battle_id,
            "run_id": run_id,
            "status": "BLOCKED",
            "agentic": agentic,
            "scillm_plan": scillm_plan,
            "tau_receipts_valid": False,
            "reason": "scillm_action_selection_failed",
            "scillm": {
                "red": red_scillm,
                "blue": blue_scillm,
            },
            "artifacts": [
                "tau/model-selection.json",
                "tau/red-scillm-selection.json",
                "tau/blue-scillm-selection.json",
                "subagent-ledger.sqlite",
            ],
        }
        write_json(tau_dir / "team-receipt.json", receipt)
        return receipt

    red_handoff = handoff_payload(
        run_id=run_id,
        goal=goal,
        battle_id=battle_id,
        scenario=scenario,
        team="red",
        persona=red_persona,
        previous_subagent="battle-orchestrator",
        next_subagent="battle-red",
        objective="Select one bounded exploit attempt for the Arena hidden-vulnerability race.",
        required_evidence=["red-receipt.json", "judge/judge-receipt.json"],
    )
    red_handoff["context"]["battle"]["docker_boundary"] = (
        "Executable exploit probes run only through Docker scorekeeper commands."
    )
    red_handoff_path = write_json(tau_dir / "red-handoff.json", red_handoff)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="red",
        persona=red_persona,
        event_type="handoff_written",
        status="PASS",
        artifact_path=red_handoff_path,
        details={"next_subagent": "battle-red"},
    )

    blue_handoff = handoff_payload(
        run_id=run_id,
        goal=goal,
        battle_id=battle_id,
        scenario=scenario,
        team="blue",
        persona=blue_persona,
        previous_subagent="battle-red",
        next_subagent="battle-blue",
        objective="Select one bounded defense for the Arena hidden-vulnerability race.",
        required_evidence=["blue-receipt.json", "judge/judge-receipt.json"],
    )
    blue_handoff["context"]["battle"]["docker_boundary"] = (
        "Executable patch and regression commands run only through Docker."
    )
    blue_handoff_path = write_json(tau_dir / "blue-handoff.json", blue_handoff)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="blue",
        persona=blue_persona,
        event_type="handoff_written",
        status="PASS",
        artifact_path=blue_handoff_path,
        details={"next_subagent": "battle-blue"},
    )

    red_harness = (
        run_tau_agent_harness_turn(
            out_dir=tau_dir,
            team="red",
            persona=red_persona,
            prompt=(
                "You are the Red Battle subagent. For the Arena hidden-vulnerability "
                "race, select exactly one bounded exploit action and do not execute code."
            ),
            assistant_content="Red selects the delayed hidden SQL injection and reflected XSS exploit oracle.",
        )
        if agentic
        else skipped_harness_turn("red")
    )
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="red",
        persona=red_persona,
        event_type="tau_agent_harness_turn",
        status=str(red_harness.get("status", "BLOCKED")),
        artifact_path=tau_dir / "red-harness-events.json",
        details=red_harness,
    )

    blue_harness = (
        run_tau_agent_harness_turn(
            out_dir=tau_dir,
            team="blue",
            persona=blue_persona,
            prompt=(
                "You are the Blue Battle subagent. For the Arena hidden-vulnerability "
                "race, select exactly one bounded patch action and do not execute code."
            ),
            assistant_content="Blue selects parameterized SQL queries and HTML escaping before Red's delayed exploit.",
        )
        if agentic
        else skipped_harness_turn("blue")
    )
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="blue",
        persona=blue_persona,
        event_type="tau_agent_harness_turn",
        status=str(blue_harness.get("status", "BLOCKED")),
        artifact_path=tau_dir / "blue-harness-events.json",
        details=blue_harness,
    )

    red_receipt = subagent_receipt_payload(
        run_id=run_id,
        goal=goal,
        battle_id=battle_id,
        team="red",
        persona=red_persona,
        status="PASS" if red_harness["status"] in {"PASS", "SKIPPED"} else "BLOCKED",
        summary=str(
            red_harness.get(
                "assistant_content",
                "Selected the delayed hidden SQL injection/XSS exploit oracle.",
            )
        ),
        evidence=[
            "tau/red-handoff.json",
            "tau/model-selection.json",
            *(
                ["tau/red-scillm-selection.json"]
                if red_scillm["status"] != "SKIPPED"
                else []
            ),
            *(
                ["tau/red-harness-events.json"]
                if red_harness["status"] != "SKIPPED"
                else []
            ),
        ],
        next_subagent="battle-scorekeeper",
        next_reason="Red selected an exploit attempt; Docker race will determine whether it lands.",
        stop_condition="Red produced a schema-valid action-selection receipt.",
        agentic=agentic,
    )
    red_receipt_path = write_json(tau_dir / "red-subagent-receipt.json", red_receipt)
    red_validation = validate_tau_receipt(
        red_receipt_path,
        active_goal_hash=str(goal["goal_hash"]),
    )
    write_json(tau_dir / "red-validation.json", red_validation)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="red",
        persona=red_persona,
        event_type="tau_receipt_validation",
        status="PASS" if red_validation["ok"] else "BLOCKED",
        artifact_path=tau_dir / "red-validation.json",
        details=red_validation,
    )

    blue_receipt = subagent_receipt_payload(
        run_id=run_id,
        goal=goal,
        battle_id=battle_id,
        team="blue",
        persona=blue_persona,
        status="PASS" if blue_harness["status"] in {"PASS", "SKIPPED"} else "BLOCKED",
        summary=str(
            blue_harness.get(
                "assistant_content",
                "Selected the deterministic SQL parameterization and HTML escaping patch.",
            )
        ),
        evidence=[
            "tau/blue-handoff.json",
            "tau/model-selection.json",
            *(
                ["tau/blue-scillm-selection.json"]
                if blue_scillm["status"] != "SKIPPED"
                else []
            ),
            *(
                ["tau/blue-harness-events.json"]
                if blue_harness["status"] != "SKIPPED"
                else []
            ),
        ],
        next_subagent="battle-scorekeeper",
        next_reason="Blue selected a defense; Docker scorekeeper will replay exploit and regression checks.",
        stop_condition="Blue produced a schema-valid action-selection receipt.",
        agentic=agentic,
    )
    blue_receipt_path = write_json(tau_dir / "blue-subagent-receipt.json", blue_receipt)
    blue_validation = validate_tau_receipt(
        blue_receipt_path,
        active_goal_hash=str(goal["goal_hash"]),
    )
    write_json(tau_dir / "blue-validation.json", blue_validation)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="blue",
        persona=blue_persona,
        event_type="tau_receipt_validation",
        status="PASS" if blue_validation["ok"] else "BLOCKED",
        artifact_path=tau_dir / "blue-validation.json",
        details=blue_validation,
    )

    harness_ok = bool(
        (not agentic)
        or (
            red_harness.get("status") == "PASS"
            and blue_harness.get("status") == "PASS"
        )
    )
    tau_ok = bool(red_validation["ok"] and blue_validation["ok"] and harness_ok)
    receipt = {
        "schema": "battle.tau_team_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS" if tau_ok else "BLOCKED",
        "agentic": agentic,
        "scillm_plan": scillm_plan,
        "tau_receipts_valid": tau_ok,
        "model_selection": "tau/model-selection.json",
        "scillm": {
            "red": red_scillm,
            "blue": blue_scillm,
        },
        "harness": {
            "red": red_harness,
            "blue": blue_harness,
        },
        "personas": {
            team: {
                "persona": probe.persona,
                "local_agent_persona": probe.local_agent_persona,
                "external_persona_hits": probe.external_persona_hits,
            }
            for team, probe in persona_probes.items()
        },
        "artifacts": [
            "tau/model-selection.json",
            *(
                ["tau/red-scillm-selection.json"]
                if red_scillm["status"] != "SKIPPED"
                else []
            ),
            "tau/red-handoff.json",
            *(
                ["tau/red-harness-events.json"]
                if red_harness["status"] != "SKIPPED"
                else []
            ),
            "tau/red-subagent-receipt.json",
            "tau/red-validation.json",
            *(
                ["tau/blue-scillm-selection.json"]
                if blue_scillm["status"] != "SKIPPED"
                else []
            ),
            "tau/blue-handoff.json",
            *(
                ["tau/blue-harness-events.json"]
                if blue_harness["status"] != "SKIPPED"
                else []
            ),
            "tau/blue-subagent-receipt.json",
            "tau/blue-validation.json",
            "subagent-ledger.sqlite",
        ],
        "non_claims": [
            *(
                []
                if agentic
                else ["does_not_prove_tau_agent_harness_execution"]
            ),
            "does_not_prove_scillm_or_external_model_execution",
            "does_not_execute_target_code_outside_docker",
            "does_not_prove_memory_promotion",
        ],
    }
    write_json(tau_dir / "team-receipt.json", receipt)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="scorekeeper",
        persona="battle-scorekeeper",
        event_type="tau_team_receipt",
        status=str(receipt["status"]),
        artifact_path=tau_dir / "team-receipt.json",
        details=receipt,
    )
    return receipt


def skipped_scillm_selection(team: str, model: str) -> dict[str, Any]:
    return {
        "schema": "battle.scillm_action_selection.v1",
        "team": team,
        "model": model,
        "status": "SKIPPED",
        "reason": "scillm_plan_disabled",
    }


def run_scillm_action_selection(
    *,
    out_dir: Path,
    team: str,
    persona: str,
    model: str,
    prompt: str,
) -> dict[str, Any]:
    artifact_dir = out_dir / "scillm"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = artifact_dir / f"{team}-selection.stdout.txt"
    stderr_path = artifact_dir / f"{team}-selection.stderr.txt"
    command = [
        str(SCILLM_PYTHON),
        "-m",
        "scillm.cli",
        model,
        prompt,
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{SCILLM_ROOT / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}"
    )
    env.setdefault("SCILLM_CALLER_SKILL", "battle")

    if not env.get("SCILLM_API_KEY"):
        return {
            "schema": "battle.scillm_action_selection.v1",
            "team": team,
            "persona": persona,
            "model": model,
            "status": "BLOCKED",
            "reason": "missing_SCILLM_API_KEY",
            "command": command,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
    if not SCILLM_PYTHON.exists():
        return {
            "schema": "battle.scillm_action_selection.v1",
            "team": team,
            "persona": persona,
            "model": model,
            "status": "BLOCKED",
            "reason": "scillm_python_missing",
            "command": command,
            "python": str(SCILLM_PYTHON),
        }
    if not (SCILLM_ROOT / "src" / "scillm" / "cli.py").is_file():
        return {
            "schema": "battle.scillm_action_selection.v1",
            "team": team,
            "persona": persona,
            "model": model,
            "status": "BLOCKED",
            "reason": "scillm_source_cli_missing",
            "command": command,
            "scillm_root": str(SCILLM_ROOT),
        }

    try:
        proc = subprocess.run(
            command,
            cwd=str(SCILLM_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        return {
            "schema": "battle.scillm_action_selection.v1",
            "team": team,
            "persona": persona,
            "model": model,
            "status": "BLOCKED",
            "reason": "scillm_action_selection_timeout",
            "command": command,
            "timeout_seconds": 60,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }

    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    response_text = proc.stdout.strip()
    status = "PASS" if proc.returncode == 0 and bool(response_text) else "BLOCKED"
    return {
        "schema": "battle.scillm_action_selection.v1",
        "team": team,
        "persona": persona,
        "model": model,
        "surface": "chat",
        "status": status,
        "reason": "ok" if status == "PASS" else "scillm_action_selection_failed",
        "command": command,
        "exit_code": proc.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "response_text": response_text,
        "mocked": False,
        "live": True,
        "target_execution": "not_executed_by_scillm_control_plane_only",
    }


def red_worker(
    *,
    image: str,
    target: Path,
    command: list[str],
    out_dir: Path,
    delay_seconds: float,
    started: float,
) -> dict[str, Any]:
    time.sleep(delay_seconds)
    ok, result = run_docker_command(
        image=image,
        target=target,
        command=command,
        artifact_dir=out_dir / "red",
        name="red-delayed-exploit",
    )
    return {
        "team": "red",
        "status": "PASS" if ok else "FAIL",
        "delay_seconds": delay_seconds,
        "finished_at_seconds": round(time.monotonic() - started, 3),
        "exploit_exit_code": result.exit_code,
        "command": result,
    }


def blue_worker(
    *,
    image: str,
    target: Path,
    patches: Path,
    regression_command: list[str],
    out_dir: Path,
    delay_seconds: float,
    started: float,
) -> dict[str, Any]:
    time.sleep(delay_seconds)
    before = (target / "app.py").read_text(encoding="utf-8")
    after = (patches / "app.py").read_text(encoding="utf-8")
    patch_dir = out_dir / "blue"
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_diff = patch_dir / "patch.diff"
    patch_diff.write_text(
        "\n".join(
            [
                "--- a/app.py",
                "+++ b/app.py",
                "@@ deterministic Arena fixture patch @@",
                "- " + before.splitlines()[0],
                "+ " + after.splitlines()[0],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ok, result = run_docker_command(
        image=image,
        target=target,
        command=[
            "sh",
            "-lc",
            "cp /patches/app.py /workspace/app.py && "
            + shlex.join(regression_command),
        ],
        artifact_dir=patch_dir,
        name="blue-patch-and-regression",
        extra_mounts=[(patches, Path("/patches"), "ro")],
    )
    return {
        "team": "blue",
        "status": "PASS" if ok else "FAIL",
        "delay_seconds": delay_seconds,
        "finished_at_seconds": round(time.monotonic() - started, 3),
        "patch_exit_code": result.exit_code,
        "command": result,
    }


def ensure_docker_image(*, image: str, artifact_dir: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    inspect = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if inspect.returncode == 0:
        return {
            "schema": "battle.docker_image_receipt.v1",
            "image": image,
            "status": "PASS",
            "source": "local_image",
        }
    pull = subprocess.run(
        ["docker", "pull", image],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    stdout = artifact_dir / "docker-pull.stdout.txt"
    stderr = artifact_dir / "docker-pull.stderr.txt"
    stdout.write_text(pull.stdout, encoding="utf-8")
    stderr.write_text(pull.stderr, encoding="utf-8")
    return {
        "schema": "battle.docker_image_receipt.v1",
        "image": image,
        "status": "PASS" if pull.returncode == 0 else "BLOCKED",
        "source": "docker_pull",
        "exit_code": pull.returncode,
        "stdout_path": str(stdout),
        "stderr_path": str(stderr),
    }


def run_docker_command(
    *,
    image: str,
    target: Path,
    command: list[str],
    artifact_dir: Path,
    name: str,
    extra_mounts: list[tuple[Path, Path, str]] | None = None,
) -> tuple[bool, CommandResult]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    docker_command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        f"{target.resolve()}:/workspace:rw",
        "-w",
        "/workspace",
    ]
    for src, dst, mode in extra_mounts or []:
        docker_command.extend(["-v", f"{src.resolve()}:{dst}:{mode}"])
    docker_command.append(image)
    docker_command.extend(command)
    proc = subprocess.run(
        docker_command,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    stdout_path = artifact_dir / f"{name}.stdout.txt"
    stderr_path = artifact_dir / f"{name}.stderr.txt"
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    result = CommandResult(
        command=docker_command,
        exit_code=proc.returncode,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )
    return proc.returncode == 0, result


def public_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    payload = dict(scenario)
    arena = dict(payload.get("arena_team", {}))
    arena.pop("hidden_ground_truth", None)
    payload["arena_team"] = arena
    return payload


def write_blocked(
    *,
    out_dir: Path,
    battle_id: str,
    run_id: str,
    reason: str,
    execution_scope: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    receipt = {
        "schema": "battle.run_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "BLOCKED",
        "verdict": "BLOCKED",
        "reason": reason,
        "execution": execution_scope,
        "claim_scope": "arena_hidden_vulnerability_docker_race_proof",
        "non_claims": non_claims_for(
            agentic=bool(execution_scope.get("agentic")),
            scillm_plan=bool(execution_scope.get("scillm_plan")),
            context_receipts=bool(execution_scope.get("context_receipts")),
        ),
        **extra,
        "artifacts": artifact_list(out_dir),
    }
    write_json(out_dir / "run-receipt.json", receipt)
    return receipt


def artifact_list(out_dir: Path) -> list[str]:
    return [
        str(path.relative_to(out_dir))
        for path in sorted(out_dir.rglob("*"))
        if path.is_file()
    ]
