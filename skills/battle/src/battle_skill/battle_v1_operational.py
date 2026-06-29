"""Battle v1 operational four-party Docker proof.

This module adds the first production-shaped Battle proof rung on top of the
battle-003 fixture:

* Arena Team emits a target/hidden-ground-truth receipt.
* Red Team and Blue Team run bounded worker pools asynchronously.
* Scorekeeper replays objective Docker outcomes and derives the scoreboard.
* Warm-pond winners and negative evidence are promoted through $memory.
* Monitor artifacts include a generated graph over real receipts.

The host is a control plane only. Target, probe, patch, and regression commands
are dispatched with ``docker run --network none`` through
``arena_docker_smoke.run_docker_command``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from .arena_docker_smoke import (
    MEMORY_BASE_URL,
    artifact_list,
    build_code_context_receipt,
    ensure_docker_image,
    public_scenario,
    run_brave_search_receipt,
    run_docker_command,
    run_fast_scan_receipt,
    safe_key,
)
from .config import SKILLS_DIR
from .receipts import CommandResult, to_jsonable, utc_now, write_json
from .subagent_smoke import TAU_ROOT, init_ledger, record_event


EXECUTION_SCOPE = {
    "mocked": False,
    "live": "docker_four_party_operational",
    "agentic": True,
    "docker_only": True,
    "red_blue_async": True,
    "context_receipts": True,
    "models_used": ["tau-local-deterministic-provider"],
}

TAU_LIVE_MAX_WORKER_HANDOFFS = 64

NON_CLAIMS = [
    "does_not_execute_unbounded_warm_pond_swarm",
    "does_not_prove_tau_loop_repair_cycle",
    "does_not_prove_scillm_delegate_batch_or_tool_execution",
    "does_not_integrate_qemu_or_afl_campaigns",
    "does_not_wire_chat_sidebar_to_orchestrator_actions",
    "does_not_stream_attempts_live_over_websocket",
]


def battle_execution_scope(*, tau_live_receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the Battle execution scope, widened only for explicit Tau live runs."""

    scope = dict(EXECUTION_SCOPE)
    if tau_live_receipt is not None:
        scope["live_tau_handoff"] = True
        scope["tau_live_status"] = tau_live_receipt.get("status")
        model = str(tau_live_receipt.get("model") or "")
        scope["models_used"] = [model] if model else []
        scope["tau_live_surface"] = tau_live_receipt.get("surface")
    return scope


def run_battle_v1_operational(
    *,
    fixture_dir: Path,
    out_dir: Path,
    red_persona: str = "brandon-bailey",
    blue_persona: str = "coder",
    red_workers: int = 2,
    blue_workers: int = 2,
    max_attempts: int = 4,
    tau_live: bool = False,
    tau_live_model: str = "gpt-5.5",
    memory_required: bool = True,
    memory_base_url: str = MEMORY_BASE_URL,
    research_broker: bool = True,
) -> dict[str, Any]:
    """Run one four-party Docker-only Battle v1 operational proof."""

    scenario = json.loads((fixture_dir / "scenario.json").read_text(encoding="utf-8"))
    hidden = json.loads(
        (fixture_dir / scenario["arena_team"]["hidden_ground_truth"]).read_text(
            encoding="utf-8"
        )
    )
    battle_id = str(scenario.get("battle_id", fixture_dir.name))
    run_id = f"battle-v1-operational-{uuid.uuid4().hex[:12]}"
    image = str(scenario.get("docker_image", "python:3.12-slim"))

    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "subagent-ledger.sqlite"
    init_ledger(ledger_path)

    workspace = out_dir / "workspace"
    target = workspace / "target"
    patches = workspace / "patches"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(fixture_dir / "target", target)
    shutil.copytree(fixture_dir / "patches", patches)

    write_json(out_dir / "battle-plan.json", public_scenario(scenario))
    write_json(out_dir / "hidden-ground-truth.json", hidden)

    image_receipt = ensure_docker_image(image=image, artifact_dir=out_dir / "docker")
    write_json(out_dir / "docker-image-receipt.json", image_receipt)
    if image_receipt["status"] != "PASS":
        return write_blocked_v1(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="docker_image_unavailable",
            extra={"docker_image": image, "docker_image_receipt": "docker-image-receipt.json"},
        )

    arena_receipt = run_arena_team(
        battle_id=battle_id,
        run_id=run_id,
        scenario=scenario,
        hidden=hidden,
        image=image,
        target=target,
        out_dir=out_dir,
    )
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="arena",
        persona="arena-team",
        event_type="arena_receipt",
        status=str(arena_receipt["status"]),
        artifact_path=out_dir / "arena-receipt.json",
        details=to_jsonable(arena_receipt),
    )
    if arena_receipt["status"] != "PASS":
        return write_blocked_v1(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="arena_target_failed_hidden_oracle",
            extra={"arena": arena_receipt, "arena_receipt": "arena-receipt.json"},
        )

    context_dir = out_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)

    memory_recall = recall_promoted_mutations(
        battle_id=battle_id,
        run_id=run_id,
        scenario=scenario,
        red_persona=red_persona,
        blue_persona=blue_persona,
        memory_base_url=memory_base_url,
        memory_required=memory_required,
    )
    write_json(context_dir / "memory-recall-receipt.json", memory_recall)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="memory_recall",
        status=str(memory_recall["status"]),
        artifact_path=context_dir / "memory-recall-receipt.json",
        details=to_jsonable(memory_recall),
    )
    if memory_recall["status"] == "BLOCKED" and memory_required:
        return write_blocked_v1(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="memory_recall_failed",
            extra={"context": {"memory_recall": "context/memory-recall-receipt.json"}},
        )

    code_context = build_code_context_receipt(
        battle_id=battle_id,
        run_id=run_id,
        target=target,
        out_dir=out_dir,
    )
    write_json(context_dir / "code-context-receipt.json", code_context)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="code_context",
        status=str(code_context["status"]),
        artifact_path=context_dir / "code-context-receipt.json",
        details=to_jsonable(code_context),
    )

    scan = run_fast_scan_receipt(
        battle_id=battle_id,
        run_id=run_id,
        image=image,
        target=target,
        out_dir=out_dir,
        scenario=scenario,
    )
    write_json(context_dir / "fast-scan-receipt.json", scan)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="docker_fast_scan",
        status=str(scan["status"]),
        artifact_path=context_dir / "fast-scan-receipt.json",
        details=to_jsonable(scan),
    )
    if scan["status"] != "PASS":
        return write_blocked_v1(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="docker_fast_scan_failed",
            extra={"context": {"scan": "context/fast-scan-receipt.json"}},
        )

    research = run_research_broker(
        battle_id=battle_id,
        run_id=run_id,
        scenario=scenario,
        hidden=hidden,
        scan=scan,
        code_context=code_context,
        out_dir=out_dir,
        red_persona=red_persona,
        blue_persona=blue_persona,
        enabled=research_broker,
    )
    write_json(context_dir / "research-broker-receipt.json", research)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="research_broker",
        status=str(research["status"]),
        artifact_path=context_dir / "research-broker-receipt.json",
        details=to_jsonable(research),
    )
    if research["status"] == "BLOCKED":
        return write_blocked_v1(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="research_broker_failed",
            extra={"context": {"research_broker": "context/research-broker-receipt.json"}},
        )

    warm_pond = build_operational_warm_pond(
        battle_id=battle_id,
        run_id=run_id,
        scenario=scenario,
        hidden=hidden,
        scan=scan,
        code_context=code_context,
        memory_recall=memory_recall,
        research=research,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )
    write_json(context_dir / "warm-pond-receipt.json", warm_pond)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="warm_pond_candidates",
        status=str(warm_pond["status"]),
        artifact_path=context_dir / "warm-pond-receipt.json",
        details=to_jsonable(warm_pond),
    )
    if warm_pond["status"] != "PASS":
        return write_blocked_v1(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="warm_pond_candidate_generation_failed",
            extra={"context": {"warm_pond": "context/warm-pond-receipt.json"}},
        )

    selected = select_warm_pond_combinations(warm_pond, max_attempts=max_attempts)
    tau_live_preflight = build_tau_live_preflight_receipt(
        battle_id=battle_id,
        run_id=run_id,
        tau_live=tau_live,
        requested_attempt_count=len(selected),
        selected=selected,
    )
    write_json(context_dir / "tau-live-preflight-receipt.json", tau_live_preflight)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="tau_live_preflight",
        status=str(tau_live_preflight["status"]),
        artifact_path=context_dir / "tau-live-preflight-receipt.json",
        details=to_jsonable(tau_live_preflight),
    )
    selected = tau_live_preflight["selected_attempts"]
    async_execution = run_red_blue_async_workers(
        battle_id=battle_id,
        run_id=run_id,
        image=image,
        target=target,
        patches=patches,
        out_dir=out_dir,
        ledger_path=ledger_path,
        scenario=scenario,
        warm_pond=warm_pond,
        selected=selected,
        red_persona=red_persona,
        blue_persona=blue_persona,
        red_workers=red_workers,
        blue_workers=blue_workers,
        tau_live_receipt=None,
    )
    if async_execution["status"] != "PASS":
        return write_blocked_v1(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="async_red_blue_workers_failed",
            extra={"async_execution": async_execution},
        )

    tau_context_bundle_path = write_tau_battle_context_bundle(
        out_dir=out_dir,
        battle_id=battle_id,
        run_id=run_id,
        scenario=scenario,
        memory_recall=memory_recall,
        code_context=code_context,
        scan=scan,
        research=research,
        warm_pond=warm_pond,
        selected=selected,
        async_execution=async_execution,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )
    tau_live_receipt = None
    if tau_live:
        tau_live_receipt = run_tau_live_handoff_bridge(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            scenario_id=str(scenario.get("scenario_id", battle_id)),
            red_persona=red_persona,
            blue_persona=blue_persona,
            model=tau_live_model,
            battle_context_json=tau_context_bundle_path,
            handoff_granularity="worker",
        )
        record_event(
            ledger_path,
            run_id=run_id,
            battle_id=battle_id,
            team="orchestrator",
            persona="battle-orchestrator",
            event_type="tau_live_handoff",
            status=str(tau_live_receipt["status"]),
            artifact_path=out_dir / "tau-live" / "manifest.json",
            details=to_jsonable(tau_live_receipt),
        )
        if tau_live_receipt["status"] != "PASS":
            return write_blocked_v1(
                out_dir=out_dir,
                battle_id=battle_id,
                run_id=run_id,
                reason="tau_live_handoff_failed",
                extra={
                    "tau_live": tau_live_receipt,
                    "tau_live_manifest": "tau-live/manifest.json",
                },
            )

    scorekeeper = run_scorekeeper_replay(
        battle_id=battle_id,
        run_id=run_id,
        image=image,
        target=target,
        patches=patches,
        out_dir=out_dir,
        ledger_path=ledger_path,
        scenario=scenario,
        warm_pond=warm_pond,
        selected=selected,
        arena_receipt=arena_receipt,
        red_team_receipt=async_execution["red_team_receipt"],
        blue_team_receipt=async_execution["blue_team_receipt"],
    )
    if scorekeeper["status"] != "PASS":
        return write_blocked_v1(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="scorekeeper_replay_failed",
            extra={"scorekeeper": scorekeeper, "scorekeeper_receipt": "scorekeeper/scorekeeper-receipt.json"},
        )

    memory_promotion = promote_warm_pond_memory(
        out_dir=out_dir,
        battle_id=battle_id,
        run_id=run_id,
        scenario=scenario,
        scorekeeper=scorekeeper,
        warm_pond=warm_pond,
        red_persona=red_persona,
        blue_persona=blue_persona,
        memory_base_url=memory_base_url,
        memory_required=memory_required,
    )
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="memory_promotion",
        status=str(memory_promotion["status"]),
        artifact_path=context_dir / "memory-promotion-receipt.json",
        details=to_jsonable(memory_promotion),
    )
    if memory_promotion["status"] == "BLOCKED" and memory_required:
        return write_blocked_v1(
            out_dir=out_dir,
            battle_id=battle_id,
            run_id=run_id,
            reason="memory_promotion_failed",
            extra={"context": {"memory_promotion": "context/memory-promotion-receipt.json"}},
        )

    context_receipt = build_context_receipt(
        battle_id=battle_id,
        run_id=run_id,
        memory_recall=memory_recall,
        code_context=code_context,
        scan=scan,
        research=research,
        warm_pond=warm_pond,
        async_execution=async_execution,
        scorekeeper=scorekeeper,
        memory_promotion=memory_promotion,
    )
    write_json(context_dir / "context-receipt.json", context_receipt)

    scoreboard = build_scoreboard(
        battle_id=battle_id,
        scenario=scenario,
        scorekeeper=scorekeeper,
        async_execution=async_execution,
        context_receipt=context_receipt,
        memory_promotion=memory_promotion,
    )
    write_json(out_dir / "scoreboard.json", scoreboard)

    graph = build_monitor_graph(
        battle_id=battle_id,
        scenario=scenario,
        scoreboard=scoreboard,
        arena_receipt=arena_receipt,
        red_team_receipt=async_execution["red_team_receipt"],
        blue_team_receipt=async_execution["blue_team_receipt"],
        scorekeeper=scorekeeper,
        memory_recall=memory_recall,
        research=research,
        memory_promotion=memory_promotion,
        selected=selected,
    )
    graph_dir = out_dir / "graph"
    graph_dir.mkdir(parents=True, exist_ok=True)
    write_json(graph_dir / "battle-v1-force-graph.json", graph)

    write_monitor_index_v1(
        out_dir=out_dir,
        battle_id=battle_id,
        scenario=scenario,
        scoreboard=scoreboard,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )

    execution_scope = battle_execution_scope(tau_live_receipt=tau_live_receipt)
    run_receipt = {
        "schema": "battle.run_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": scoreboard["status"],
        "verdict": scoreboard["verdict"],
        "execution": execution_scope,
        "claim_scope": "battle_v1_four_party_docker_operational_proof",
        "non_claims": NON_CLAIMS,
        "receipts": scoreboard["receipts"],
        "memory_recall_receipt": "context/memory-recall-receipt.json",
        "memory_promotion_receipt": "context/memory-promotion-receipt.json",
        "tau_live_preflight_receipt": "context/tau-live-preflight-receipt.json",
        "tau_context_bundle": "context/tau-battle-context-bundle.json",
        "tau_live_manifest": "tau-live/manifest.json" if tau_live_receipt else None,
        "monitor_graph": "graph/battle-v1-force-graph.json",
        "artifacts": artifact_list(out_dir),
    }
    write_json(out_dir / "run-receipt.json", run_receipt)
    # Refresh monitor-index and graph artifact lists now run-receipt exists.
    write_monitor_index_v1(
        out_dir=out_dir,
        battle_id=battle_id,
        scenario=scenario,
        scoreboard=scoreboard,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )
    run_receipt["artifacts"] = artifact_list(out_dir)
    write_json(out_dir / "run-receipt.json", run_receipt)
    return run_receipt


def run_arena_team(
    *,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    hidden: dict[str, Any],
    image: str,
    target: Path,
    out_dir: Path,
) -> dict[str, Any]:
    ok, command = run_docker_command(
        image=image,
        target=target,
        command=scenario["commands"]["expect_vulnerable"],
        artifact_dir=out_dir / "arena",
        name="arena-hidden-vulnerability-oracle",
    )
    receipt = {
        "schema": "battle.arena_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS" if ok else "BLOCKED",
        "team": "arena",
        "persona": "arena-team",
        "role": "create_target_and_hidden_ground_truth",
        "hidden_vulnerability_count": len(hidden.get("hidden_vulnerabilities", [])),
        "hidden_vulnerability_ids": [
            item.get("id") for item in hidden.get("hidden_vulnerabilities", [])
        ],
        "docker_image": image,
        "target_container_network": "none",
        "host_boundary": "control_plane_only",
        "commands_run": [command],
        "created_at": utc_now(),
    }
    write_json(out_dir / "arena-receipt.json", receipt)
    return receipt


def build_operational_warm_pond(
    *,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    hidden: dict[str, Any],
    scan: dict[str, Any],
    code_context: dict[str, Any],
    memory_recall: dict[str, Any],
    research: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> dict[str, Any]:
    """Build deterministic warm-pond exploit/defense candidates for v1."""

    findings = [item for item in scan.get("findings", []) if isinstance(item, dict)]
    families = {str(item.get("family")) for item in findings if item.get("family")}
    if not families:
        families = {
            "sql_injection"
            if item.get("cwe") == "CWE-89"
            else "reflected_xss"
            if item.get("cwe") == "CWE-79"
            else str(item.get("family", "unknown"))
            for item in hidden.get("hidden_vulnerabilities", [])
        }
    research_signals = build_research_signal_summary(research=research, families=families)

    exploit_candidates: list[dict[str, Any]] = []
    defense_candidates: list[dict[str, Any]] = []
    if "sql_injection" in families:
        sqli_research = research_family_evidence(research_signals, "sql_injection")
        exploit_candidates.extend(
            [
                {
                    "id": "exploit-sqli-admin-or",
                    "family": "sql_injection",
                    "symbol": "search_users",
                    "payload": "nomatch%' OR role='admin' --",
                    "source": "docker_scan_hidden_oracle_memory_seed",
                    "research_weight": sqli_research["weight"],
                    "research_sources": sqli_research["sources"],
                },
                {
                    "id": "exploit-sqli-like-wildcard",
                    "family": "sql_injection",
                    "symbol": "search_users",
                    "payload": "%' OR '1'='1' --",
                    "source": "warm_pond_mutation",
                    "research_weight": sqli_research["weight"],
                    "research_sources": sqli_research["sources"],
                },
            ]
        )
        defense_candidates.append(
            {
                "id": "defense-parameterized-like",
                "family": "sql_injection",
                "symbol": "search_users",
                "strategy": "replace interpolated SQL with parameterized LIKE query",
                "research_weight": sqli_research["weight"],
                "research_sources": sqli_research["sources"],
            }
        )
    if "reflected_xss" in families:
        xss_research = research_family_evidence(research_signals, "reflected_xss")
        exploit_candidates.extend(
            [
                {
                    "id": "exploit-xss-script-reflection",
                    "family": "reflected_xss",
                    "symbol": "render_search",
                    "payload": "<script>alert(1)</script>",
                    "source": "docker_scan_hidden_oracle_memory_seed",
                    "research_weight": xss_research["weight"],
                    "research_sources": xss_research["sources"],
                },
                {
                    "id": "exploit-xss-attribute-breakout",
                    "family": "reflected_xss",
                    "symbol": "render_search",
                    "payload": '" autofocus onfocus=alert(1) x="',
                    "source": "warm_pond_mutation",
                    "research_weight": xss_research["weight"],
                    "research_sources": xss_research["sources"],
                },
            ]
        )
        defense_candidates.append(
            {
                "id": "defense-html-escape-query",
                "family": "reflected_xss",
                "symbol": "render_search",
                "strategy": "HTML-escape query before rendering attributes or text",
                "research_weight": xss_research["weight"],
                "research_sources": xss_research["sources"],
            }
        )

    exploit_ids = {str(item.get("id")) for item in exploit_candidates}
    defense_ids = {str(item.get("id")) for item in defense_candidates}
    generated_exploit_count = 0
    generated_defense_count = 0

    def add_exploit_candidate(candidate: dict[str, Any]) -> bool:
        candidate_id = str(candidate.get("id", ""))
        if not candidate_id or candidate_id in exploit_ids:
            return False
        exploit_ids.add(candidate_id)
        exploit_candidates.append(candidate)
        return True

    def add_defense_candidate(candidate: dict[str, Any]) -> bool:
        candidate_id = str(candidate.get("id", ""))
        if not candidate_id or candidate_id in defense_ids:
            return False
        defense_ids.add(candidate_id)
        defense_candidates.append(candidate)
        return True

    configured_warm_pond = scenario.get("warm_pond")
    if isinstance(configured_warm_pond, dict):
        for candidate in configured_warm_pond.get("extra_exploit_candidates", []):
            if not isinstance(candidate, dict):
                continue
            if not candidate.get("id"):
                continue
            family = str(candidate.get("family", ""))
            if family not in families:
                continue
            research_evidence = research_family_evidence(research_signals, family)
            add_exploit_candidate(
                {
                    "id": str(candidate["id"]),
                    "family": family,
                    "symbol": str(candidate.get("symbol", "")),
                    "payload": str(candidate.get("payload", "")),
                    "source": str(candidate.get("source", "scenario_warm_pond_seed")),
                    "research_weight": research_evidence["weight"],
                    "research_sources": research_evidence["sources"],
                }
            )
        for candidate in configured_warm_pond.get("extra_defense_candidates", []):
            if not isinstance(candidate, dict):
                continue
            if not candidate.get("id"):
                continue
            family = str(candidate.get("family", ""))
            if family not in families:
                continue
            research_evidence = research_family_evidence(research_signals, family)
            add_defense_candidate(
                {
                    "id": str(candidate["id"]),
                    "family": family,
                    "symbol": str(candidate.get("symbol", "")),
                    "strategy": str(candidate.get("strategy", "")),
                    "research_weight": research_evidence["weight"],
                    "research_sources": research_evidence["sources"],
                }
            )

    configured_generator = scenario.get("warm_pond_generator")
    if isinstance(configured_generator, dict):
        for spec in configured_generator.get("exploit_payloads", []):
            if not isinstance(spec, dict):
                continue
            family = str(spec.get("family", ""))
            if family not in families:
                continue
            symbol = str(spec.get("symbol", ""))
            source = str(spec.get("source", "scenario_warm_pond_generator"))
            research_evidence = research_family_evidence(research_signals, family)
            payloads = spec.get("payloads", [])
            if not isinstance(payloads, list):
                continue
            for index, payload_spec in enumerate(payloads, start=1):
                if isinstance(payload_spec, dict):
                    payload = str(payload_spec.get("payload", ""))
                    payload_id = str(payload_spec.get("id") or f"{family}-{index:03d}")
                else:
                    payload = str(payload_spec)
                    payload_id = f"{family}-{index:03d}"
                if not payload:
                    continue
                added = add_exploit_candidate(
                    {
                        "id": f"exploit-{safe_key(payload_id)}",
                        "family": family,
                        "symbol": symbol,
                        "payload": payload,
                        "source": source,
                        "research_weight": research_evidence["weight"],
                        "research_sources": research_evidence["sources"],
                    }
                )
                generated_exploit_count += 1 if added else 0
        for spec in configured_generator.get("defense_strategies", []):
            if not isinstance(spec, dict):
                continue
            family = str(spec.get("family", ""))
            if family not in families:
                continue
            symbol = str(spec.get("symbol", ""))
            source = str(spec.get("source", "scenario_warm_pond_generator"))
            research_evidence = research_family_evidence(research_signals, family)
            strategies = spec.get("strategies", [])
            if not isinstance(strategies, list):
                continue
            for index, strategy_spec in enumerate(strategies, start=1):
                if isinstance(strategy_spec, dict):
                    strategy = str(strategy_spec.get("strategy", ""))
                    strategy_id = str(strategy_spec.get("id") or f"{family}-{index:03d}")
                else:
                    strategy = str(strategy_spec)
                    strategy_id = f"{family}-{index:03d}"
                if not strategy:
                    continue
                added = add_defense_candidate(
                    {
                        "id": f"defense-{safe_key(strategy_id)}",
                        "family": family,
                        "symbol": symbol,
                        "strategy": strategy,
                        "source": source,
                        "research_weight": research_evidence["weight"],
                        "research_sources": research_evidence["sources"],
                    }
                )
                generated_defense_count += 1 if added else 0

    combinations: list[dict[str, Any]] = []
    for exploit in exploit_candidates:
        for defense in defense_candidates:
            base_affinity = 1.0 if exploit["family"] == defense["family"] else 0.73
            research_sources = sorted(
                set(exploit.get("research_sources", []))
                | set(defense.get("research_sources", []))
            )
            research_boost = round(
                min(
                    0.2,
                    (
                        float(exploit.get("research_weight", 0.0))
                        + float(defense.get("research_weight", 0.0))
                    )
                    / 2.0,
                ),
                3,
            )
            affinity = round(base_affinity + research_boost, 3)
            combinations.append(
                {
                    "id": f"{exploit['id']}__{defense['id']}",
                    "exploit": exploit["id"],
                    "defense": defense["id"],
                    "families": sorted({exploit["family"], defense["family"]}),
                    "base_affinity": base_affinity,
                    "research_boost": research_boost,
                    "research_sources": research_sources,
                    "first_research_lane": research_signals.get("first_passed_lane"),
                    "affinity": affinity,
                    "reason": "same-family direct countermeasure"
                    if base_affinity == 1.0
                    else "cross-family exploit/defense chain",
                    "dispatch_reason": (
                        "research-weighted same-family countermeasure"
                        if base_affinity == 1.0
                        else "research-weighted cross-family chain"
                    ),
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
        "memory_recall_found": memory_recall.get("found", False),
        "research_broker_status": research.get("status"),
        "research_passed_lane_count": research.get("passed_lane_count", 0),
        "research_completion_order": research.get("completion_order", []),
        "research_signal_summary": research_signals,
        "warm_pond_generator": {
            "enabled": isinstance(configured_generator, dict),
            "generated_exploit_candidate_count": generated_exploit_count,
            "generated_defense_candidate_count": generated_defense_count,
        },
        "research_weighted_candidate_count": sum(
            1
            for item in [*exploit_candidates, *defense_candidates]
            if float(item.get("research_weight", 0.0)) > 0
        ),
        "research_weighted_combination_count": sum(
            1 for item in combinations if float(item.get("research_boost", 0.0)) > 0
        ),
        "hidden_cwes": [
            item.get("cwe") for item in hidden.get("hidden_vulnerabilities", [])
        ],
        "code_symbols": [item.get("name") for item in code_context.get("functions", [])],
        "exploit_candidate_count": len(exploit_candidates),
        "defense_candidate_count": len(defense_candidates),
        "combination_count": len(combinations),
        "exploit_candidates": exploit_candidates,
        "defense_candidates": defense_candidates,
        "combinations": combinations,
        "selection_rule": (
            "highest research-adjusted affinity, deterministic id tiebreaker, "
            "Docker replay before memory promotion"
        ),
        "created_at": utc_now(),
    }


def run_research_broker(
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
    enabled: bool,
) -> dict[str, Any]:
    """Run bounded agent-side research lanes concurrently before candidate selection."""

    if not enabled:
        return {
            "schema": "battle.research_broker_receipt.v1",
            "battle_id": battle_id,
            "run_id": run_id,
            "status": "SKIPPED",
            "reason": "research_broker_disabled",
            "mocked": False,
            "live": False,
            "created_at": utc_now(),
        }

    started = time.monotonic()
    research_dir = out_dir / "context" / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    query_context = build_research_queries(
        scenario=scenario,
        hidden=hidden,
        scan=scan,
        code_context=code_context,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )

    lanes: list[tuple[str, Any]] = [
        (
            "brave",
            lambda: run_brave_search_receipt(
                battle_id=battle_id,
                run_id=run_id,
                scenario=scenario,
                hidden=hidden,
                scan=scan,
                code_context=code_context,
                out_dir=out_dir,
                red_persona=red_persona,
                blue_persona=blue_persona,
            ),
        ),
        (
            "github_red",
            lambda: run_github_research_lane(
                battle_id=battle_id,
                run_id=run_id,
                query=query_context["red_github"],
                lane="github_red",
                persona=red_persona,
                artifact_dir=research_dir / "github-red",
            ),
        ),
        (
            "github_blue",
            lambda: run_github_research_lane(
                battle_id=battle_id,
                run_id=run_id,
                query=query_context["blue_github"],
                lane="github_blue",
                persona=blue_persona,
                artifact_dir=research_dir / "github-blue",
            ),
        ),
        (
            "dogpile_red",
            lambda: run_dogpile_research_lane(
                battle_id=battle_id,
                run_id=run_id,
                query=query_context["red_dogpile"],
                preset="red_team",
                lane="dogpile_red",
                persona=red_persona,
                artifact_dir=research_dir / "dogpile-red",
            ),
        ),
        (
            "dogpile_blue",
            lambda: run_dogpile_research_lane(
                battle_id=battle_id,
                run_id=run_id,
                query=query_context["blue_dogpile"],
                preset="blue_team",
                lane="dogpile_blue",
                persona=blue_persona,
                artifact_dir=research_dir / "dogpile-blue",
            ),
        ),
    ]

    lane_receipts: dict[str, dict[str, Any]] = {}
    completion_order: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(lanes)) as executor:
        future_to_lane = {executor.submit(func): lane for lane, func in lanes}
        for future in as_completed(future_to_lane, timeout=180):
            lane = future_to_lane[future]
            try:
                receipt = future.result(timeout=1)
            except Exception as exc:
                receipt = {
                    "schema": "battle.research_lane_receipt.v1",
                    "battle_id": battle_id,
                    "run_id": run_id,
                    "lane": lane,
                    "status": "BLOCKED",
                    "reason": f"research_lane_exception: {type(exc).__name__}: {exc}",
                    "mocked": False,
                    "live": True,
                    "created_at": utc_now(),
                }
            lane_receipts[lane] = receipt
            completion_order.append(
                {
                    "lane": lane,
                    "status": receipt.get("status"),
                    "completed_at_seconds": round(time.monotonic() - started, 6),
                }
            )

    passed = [item for item in lane_receipts.values() if item.get("status") == "PASS"]
    blocked = [item for item in lane_receipts.values() if item.get("status") == "BLOCKED"]
    status = "PASS" if passed else "BLOCKED"
    return {
        "schema": "battle.research_broker_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": status,
        "mocked": False,
        "live": True,
        "mode": "threadpool_as_completed",
        "surface": "agent_side_research_broker",
        "target_container_network": "none",
        "query_context": query_context,
        "lane_count": len(lanes),
        "passed_lane_count": len(passed),
        "blocked_lane_count": len(blocked),
        "completion_order": completion_order,
        "lanes": lane_receipts,
        "deployment_contract": (
            "Research lanes complete through as_completed; first usable findings "
            "seed warm-pond candidate weighting before Docker-only replay."
        ),
        "created_at": utc_now(),
    }


def build_research_queries(
    *,
    scenario: dict[str, Any],
    hidden: dict[str, Any],
    scan: dict[str, Any],
    code_context: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> dict[str, str]:
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
    app_context = (
        f"{scenario.get('scenario_id')} Python sqlite reflected XSS SQL injection "
        f"{families} {cwes} symbols {symbols} functions {functions}"
    )
    return {
        "red_github": f"{app_context} exploit proof payload examples",
        "blue_github": f"{app_context} parameterized sqlite html escape patch examples",
        "red_dogpile": f"{red_persona} red team fast exploit research for {app_context}",
        "blue_dogpile": f"{blue_persona} blue team fast mitigation research for {app_context}",
    }


def build_research_signal_summary(
    *,
    research: dict[str, Any],
    families: set[str],
) -> dict[str, Any]:
    """Extract deterministic family weights from live research lane receipts."""

    completion_order = [
        item
        for item in research.get("completion_order", [])
        if isinstance(item, dict)
    ]
    first_passed_lane = next(
        (
            str(item.get("lane"))
            for item in completion_order
            if item.get("status") == "PASS" and item.get("lane")
        ),
        None,
    )
    lanes = {
        str(key): value
        for key, value in research.get("lanes", {}).items()
        if isinstance(value, dict)
    }
    query_context = {
        str(key): str(value)
        for key, value in research.get("query_context", {}).items()
    }
    family_keywords = {
        "sql_injection": ["sql", "sqlite", "injection", "cwe-89", "parameterized"],
        "reflected_xss": ["xss", "html", "escape", "reflection", "cwe-79"],
    }
    family_weights: dict[str, float] = {}
    family_sources: dict[str, list[str]] = {}
    for family in sorted(families):
        keywords = family_keywords.get(family, [family.replace("_", " ")])
        sources: list[str] = []
        raw_score = 0
        for lane, receipt in lanes.items():
            if receipt.get("status") != "PASS":
                continue
            lane_text = " ".join(
                [
                    lane,
                    str(receipt.get("query", "")),
                    " ".join(query_context.values()),
                    json.dumps(receipt.get("top_results", []), sort_keys=True),
                ]
            ).lower()
            hits = sum(1 for keyword in keywords if keyword.lower() in lane_text)
            if hits:
                raw_score += hits
                sources.append(lane)
        family_weights[family] = round(min(0.2, raw_score * 0.025), 3)
        family_sources[family] = sorted(set(sources))
    return {
        "status": "PASS" if research.get("status") == "PASS" else "BLOCKED",
        "first_passed_lane": first_passed_lane,
        "family_weights": family_weights,
        "family_sources": family_sources,
        "lane_count": research.get("lane_count", 0),
        "passed_lane_count": research.get("passed_lane_count", 0),
        "completion_order": completion_order,
    }


def research_family_evidence(
    research_signals: dict[str, Any],
    family: str,
) -> dict[str, Any]:
    weights = research_signals.get("family_weights", {})
    sources = research_signals.get("family_sources", {})
    if not isinstance(weights, dict):
        weights = {}
    if not isinstance(sources, dict):
        sources = {}
    family_sources = sources.get(family, [])
    if not isinstance(family_sources, list):
        family_sources = []
    return {
        "weight": float(weights.get(family, 0.0)),
        "sources": [str(item) for item in family_sources],
    }


def run_github_research_lane(
    *,
    battle_id: str,
    run_id: str,
    query: str,
    lane: str,
    persona: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = artifact_dir / "github-search.stdout.json"
    stderr_path = artifact_dir / "github-search.stderr.txt"
    command = [
        str(SKILLS_DIR / "github-search" / "run.sh"),
        "search",
        query,
        "--limit",
        "3",
        "--json",
    ]
    return run_research_command_receipt(
        schema="battle.github_search_receipt.v1",
        battle_id=battle_id,
        run_id=run_id,
        lane=lane,
        persona=persona,
        surface="github_search_skill",
        query=query,
        command=command,
        cwd=SKILLS_DIR / "github-search",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_seconds=75,
    )


def run_dogpile_research_lane(
    *,
    battle_id: str,
    run_id: str,
    query: str,
    preset: str,
    lane: str,
    persona: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = artifact_dir / "dogpile.stdout.md"
    stderr_path = artifact_dir / "dogpile.stderr.txt"
    command = [
        str(SKILLS_DIR / "dogpile" / "run.sh"),
        "search",
        query,
        "--preset",
        preset,
        "--no-interactive",
        "--persona",
        persona,
        "--rationale",
        "Battle v1 live research broker before Docker-contained exploit/defense replay",
        "--context",
        "Use retrieval only. Do not execute PoC code on the host.",
    ]
    return run_research_command_receipt(
        schema="battle.dogpile_receipt.v1",
        battle_id=battle_id,
        run_id=run_id,
        lane=lane,
        persona=persona,
        surface="dogpile_search_skill",
        query=query,
        command=command,
        cwd=SKILLS_DIR / "dogpile",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_seconds=90,
    )


def run_research_command_receipt(
    *,
    schema: str,
    battle_id: str,
    run_id: str,
    lane: str,
    persona: str,
    surface: str,
    query: str,
    command: list[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode
        timeout_expired = False
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_timeout_stream(exc.stdout)
        stderr = _decode_timeout_stream(exc.stderr)
        exit_code = 124
        timeout_expired = True
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    status = "PASS" if exit_code == 0 and not timeout_expired else "BLOCKED"
    receipt = {
        "schema": schema,
        "battle_id": battle_id,
        "run_id": run_id,
        "lane": lane,
        "persona": persona,
        "status": status,
        "surface": surface,
        "mocked": False,
        "live": True,
        "query": query,
        "command": command,
        "exit_code": exit_code,
        "timeout_seconds": timeout_seconds,
        "timeout_expired": timeout_expired,
        "duration_seconds": round(time.monotonic() - started, 6),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_bytes": len(stdout.encode("utf-8")),
        "stderr_bytes": len(stderr.encode("utf-8")),
        "created_at": utc_now(),
    }
    if timeout_expired:
        receipt["reason"] = "research_command_timeout"
    elif exit_code != 0:
        receipt["reason"] = "research_command_failed"
    return receipt


def select_warm_pond_combinations(
    warm_pond: dict[str, Any],
    *,
    max_attempts: int,
) -> list[dict[str, Any]]:
    combinations = [item for item in warm_pond.get("combinations", []) if isinstance(item, dict)]
    return sorted(
        combinations,
        key=lambda item: (-float(item.get("affinity", 0.0)), str(item.get("id", ""))),
    )[:max_attempts]


def build_tau_live_preflight_receipt(
    *,
    battle_id: str,
    run_id: str,
    tau_live: bool,
    requested_attempt_count: int,
    selected: list[dict[str, Any]],
) -> dict[str, Any]:
    """Cap worker-granularity Tau live handoffs before starting the worker pool."""

    requested_handoff_count = requested_attempt_count * 2
    if not tau_live:
        effective_attempt_count = requested_attempt_count
        effective_handoff_count = requested_handoff_count
        capped = False
        reason = "tau_live_disabled"
    else:
        effective_attempt_count = min(
            requested_attempt_count,
            max(1, TAU_LIVE_MAX_WORKER_HANDOFFS // 2),
        )
        effective_handoff_count = effective_attempt_count * 2
        capped = effective_handoff_count < requested_handoff_count
        reason = (
            "requested_live_worker_handoffs_capped_to_tau_safe_limit"
            if capped
            else "requested_live_worker_handoffs_within_tau_safe_limit"
        )

    return {
        "schema": "battle.tau_live_preflight_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS",
        "mocked": False,
        "live": tau_live,
        "handoff_granularity": "worker",
        "reason": reason,
        "capped": capped,
        "requested_attempt_count": requested_attempt_count,
        "requested_handoff_count": requested_handoff_count,
        "max_live_handoffs": TAU_LIVE_MAX_WORKER_HANDOFFS if tau_live else None,
        "effective_attempt_count": effective_attempt_count,
        "effective_handoff_count": effective_handoff_count,
        "degrade_strategy": (
            "preserve top research-weighted warm-pond combinations and run the highest safe Tau fanout"
            if capped
            else None
        ),
        "selected_attempt_ids": [
            str(item.get("id")) for item in selected[:effective_attempt_count]
        ],
        "selected_attempts": selected[:effective_attempt_count],
        "created_at": utc_now(),
    }


def write_tau_battle_context_bundle(
    *,
    out_dir: Path,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    memory_recall: dict[str, Any],
    code_context: dict[str, Any],
    scan: dict[str, Any],
    research: dict[str, Any],
    warm_pond: dict[str, Any],
    selected: list[dict[str, Any]],
    async_execution: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> Path:
    """Write the bounded Battle context Tau should pass into Red/Blue handoffs."""

    bundle_path = out_dir / "context" / "tau-battle-context-bundle.json"
    red_team = async_execution.get("red_team_receipt", {})
    blue_team = async_execution.get("blue_team_receipt", {})
    artifacts = {
        "battle_plan": str((out_dir / "battle-plan.json").resolve()),
        "memory_recall": str((out_dir / "context" / "memory-recall-receipt.json").resolve()),
        "code_context": str((out_dir / "context" / "code-context-receipt.json").resolve()),
        "fast_scan": str((out_dir / "context" / "fast-scan-receipt.json").resolve()),
        "research_broker": str((out_dir / "context" / "research-broker-receipt.json").resolve()),
        "warm_pond": str((out_dir / "context" / "warm-pond-receipt.json").resolve()),
        "red_team": str((out_dir / "red" / "team-receipt.json").resolve()),
        "blue_team": str((out_dir / "blue" / "team-receipt.json").resolve()),
    }
    selected_attempts = [
        {
            "combination_id": item.get("id"),
            "exploit": item.get("exploit"),
            "defense": item.get("defense"),
            "research_boost": item.get("research_boost", 0.0),
            "first_research_lane": item.get("first_research_lane"),
            "research_sources": item.get("research_sources", []),
        }
        for item in selected
    ]
    payload = {
        "schema": "tau.battle_context_bundle.v1",
        "bundle_path": str(bundle_path.resolve()),
        "battle_id": battle_id,
        "run_id": run_id,
        "scenario_id": scenario.get("scenario_id"),
        "artifacts": artifacts,
        "summary": {
            "run_receipt": {
                "status": "PENDING",
                "reason": "Battle run receipt is written after Tau and scorekeeper complete.",
                "battle_id": battle_id,
                "run_id": run_id,
            },
            "tau_live_manifest": {
                "status": "PENDING",
                "reason": "This bundle is the Tau handoff input.",
            },
            "memory_recall": {
                "status": memory_recall.get("status"),
                "found": memory_recall.get("found"),
            },
            "code_context": {
                "status": code_context.get("status"),
                "symbol_count": code_context.get("symbol_count", 0),
            },
            "fast_scan": {
                "status": scan.get("status"),
                "finding_count": scan.get("finding_count", 0),
                "families": scan.get("families", []),
            },
            "research_broker": {
                "status": research.get("status"),
                "passed_lane_count": research.get("passed_lane_count", 0),
                "lane_count": research.get("lane_count", 0),
                "completion_order": research.get("completion_order", []),
            },
            "warm_pond": {
                "status": warm_pond.get("status"),
                "selection_rule": warm_pond.get("selection_rule"),
                "selected_attempt_count": len(selected_attempts),
                "selected_attempts": selected_attempts,
                "research_weighted_candidate_count": warm_pond.get(
                    "research_weighted_candidate_count", 0
                ),
                "research_weighted_combination_count": warm_pond.get(
                    "research_weighted_combination_count", 0
                ),
            },
            "teams": {
                "red": {
                    "persona": red_persona,
                    "worker_count": red_team.get("worker_count", 0),
                    "worker_receipts": red_team.get("worker_receipts", []),
                },
                "blue": {
                    "persona": blue_persona,
                    "worker_count": blue_team.get("worker_count", 0),
                    "worker_receipts": blue_team.get("worker_receipts", []),
                },
            },
        },
        "claim_scope": "battle_context_for_tau_handoff_only",
        "non_claims": [
            "does_not_prove_tau_loop_repair_cycle",
            "does_not_prove_unbounded_warm_pond_swarm",
            "does_not_execute_research_code_on_host",
        ],
        "created_at": utc_now(),
    }
    write_json(bundle_path, payload)
    return bundle_path


def run_tau_live_handoff_bridge(
    *,
    out_dir: Path,
    battle_id: str,
    run_id: str,
    scenario_id: str,
    red_persona: str,
    blue_persona: str,
    model: str,
    battle_context_json: Path | None = None,
    handoff_granularity: str = "team",
) -> dict[str, Any]:
    """Call Tau's live Battle handoff bridge and return its manifest."""

    tau_live_dir = out_dir / "tau-live"
    command = [
        "uv",
        "run",
        "--project",
        str(TAU_ROOT),
        "python",
        "-m",
        "tau_coding.battle_live_handoff",
        "--out-dir",
        str(tau_live_dir),
        "--battle-id",
        battle_id,
        "--run-id",
        run_id,
        "--scenario-id",
        scenario_id,
        "--red-persona",
        red_persona,
        "--blue-persona",
        blue_persona,
        "--model",
        model,
        "--handoff-granularity",
        handoff_granularity,
    ]
    if battle_context_json is not None:
        command.extend(["--battle-context-json", str(battle_context_json)])
    env = os.environ.copy()
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env.pop("VIRTUAL_ENV", None)
    env["PYTHONPATH"] = f"{TAU_ROOT / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}"
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=210,
            env=env,
        )
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
        timeout_expired = False
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = _decode_timeout_stream(exc.stdout)
        stderr = _decode_timeout_stream(exc.stderr)
        timeout_expired = True
    process_receipt = {
        "schema": "battle.tau_live_bridge_process.v1",
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_seconds": round(time.monotonic() - started, 6),
        "timeout_expired": timeout_expired,
    }
    write_json(tau_live_dir / "process-receipt.json", process_receipt)
    if timeout_expired:
        return {
            "schema": "tau.battle_live_handoff_proof.v1",
            "status": "BLOCKED",
            "mocked": False,
            "live": True,
            "reason": "tau_live_process_timeout",
            "process": process_receipt,
        }
    manifest_path = tau_live_dir / "manifest.json"
    if not manifest_path.exists():
        return {
            "schema": "tau.battle_live_handoff_proof.v1",
            "status": "BLOCKED",
            "mocked": False,
            "live": True,
            "reason": "tau_live_manifest_missing",
            "process": process_receipt,
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        return {
            "schema": "tau.battle_live_handoff_proof.v1",
            "status": "BLOCKED",
            "mocked": False,
            "live": True,
            "reason": "tau_live_manifest_not_object",
            "process": process_receipt,
        }
    manifest["process"] = process_receipt
    write_json(manifest_path, manifest)
    return manifest


def _decode_timeout_stream(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run_red_blue_async_workers(
    *,
    battle_id: str,
    run_id: str,
    image: str,
    target: Path,
    patches: Path,
    out_dir: Path,
    ledger_path: Path,
    scenario: dict[str, Any],
    warm_pond: dict[str, Any],
    selected: list[dict[str, Any]],
    red_persona: str,
    blue_persona: str,
    red_workers: int,
    blue_workers: int,
    tau_live_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    exploit_by_id = {item["id"]: item for item in warm_pond["exploit_candidates"]}
    defense_by_id = {item["id"]: item for item in warm_pond["defense_candidates"]}
    session_started = time.monotonic()

    red_receipts: list[dict[str, Any]] = []
    blue_receipts: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max(1, red_workers + blue_workers)) as executor:
        futures = []
        for index, combination in enumerate(selected):
            exploit = exploit_by_id[str(combination["exploit"])]
            defense = defense_by_id[str(combination["defense"])]
            futures.append(
                executor.submit(
                    red_worker_v1,
                    battle_id=battle_id,
                    run_id=run_id,
                    image=image,
                    target=target,
                    out_dir=out_dir,
                    combination=combination,
                    exploit=exploit,
                    persona=red_persona,
                    worker_index=index,
                    session_started=session_started,
                )
            )
            futures.append(
                executor.submit(
                    blue_worker_v1,
                    battle_id=battle_id,
                    run_id=run_id,
                    image=image,
                    target=target,
                    patches=patches,
                    out_dir=out_dir,
                    scenario=scenario,
                    combination=combination,
                    defense=defense,
                    persona=blue_persona,
                    worker_index=index,
                    session_started=session_started,
                )
            )

        for future in as_completed(futures, timeout=180):
            receipt = future.result(timeout=1)
            if receipt["team"] == "red":
                red_receipts.append(receipt)
            else:
                blue_receipts.append(receipt)
            record_event(
                ledger_path,
                run_id=run_id,
                battle_id=battle_id,
                team=str(receipt["team"]),
                persona=str(receipt["persona"]),
                event_type="async_worker",
                status=str(receipt["status"]),
                artifact_path=Path(str(receipt["receipt_path"])),
                details=to_jsonable(receipt),
            )

    red_receipts = sorted(red_receipts, key=lambda item: str(item["worker_id"]))
    blue_receipts = sorted(blue_receipts, key=lambda item: str(item["worker_id"]))
    overlap = compute_overlap(red_receipts, blue_receipts)

    red_tau = _tau_live_team(tau_live_receipt, "red")
    blue_tau = _tau_live_team(tau_live_receipt, "blue")
    red_team_receipt = {
        "schema": "battle.team_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "team": "red",
        "status": "PASS" if red_receipts and all(r["status"] == "PASS" for r in red_receipts) else "FAIL",
        "persona": red_persona,
        "model": str(red_tau.get("model") or "tau-local-deterministic-provider"),
        "surface": str(red_tau.get("surface") or "deterministic_tau_shaped_worker_pool"),
        "tau_live_subagent_receipt": _relative_or_none(out_dir, red_tau.get("subagent_receipt")),
        "async": True,
        "budget": {"max_workers": red_workers, "max_attempts": len(selected), "max_commands_per_worker": 1},
        "worker_count": len(red_receipts),
        "worker_receipts": [relative_to_out(out_dir, r["receipt_path"]) for r in red_receipts],
        "overlap_evidence": overlap,
        "next_agent": "battle-scorekeeper",
        "created_at": utc_now(),
    }
    blue_team_receipt = {
        "schema": "battle.team_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "team": "blue",
        "status": "PASS" if blue_receipts and all(r["status"] == "PASS" for r in blue_receipts) else "FAIL",
        "persona": blue_persona,
        "model": str(blue_tau.get("model") or "tau-local-deterministic-provider"),
        "surface": str(blue_tau.get("surface") or "deterministic_tau_shaped_worker_pool"),
        "tau_live_subagent_receipt": _relative_or_none(out_dir, blue_tau.get("subagent_receipt")),
        "async": True,
        "budget": {"max_workers": blue_workers, "max_attempts": len(selected), "max_commands_per_worker": 1},
        "worker_count": len(blue_receipts),
        "worker_receipts": [relative_to_out(out_dir, r["receipt_path"]) for r in blue_receipts],
        "overlap_evidence": overlap,
        "next_agent": "battle-scorekeeper",
        "created_at": utc_now(),
    }
    write_json(out_dir / "red" / "team-receipt.json", red_team_receipt)
    write_json(out_dir / "blue" / "team-receipt.json", blue_team_receipt)

    status = "PASS" if red_team_receipt["status"] == "PASS" and blue_team_receipt["status"] == "PASS" and overlap["overlap_detected"] else "BLOCKED"
    return {
        "schema": "battle.async_execution_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": status,
        "selected_attempt_count": len(selected),
        "red_worker_count": len(red_receipts),
        "blue_worker_count": len(blue_receipts),
        "overlap_evidence": overlap,
        "red_team_receipt": red_team_receipt,
        "blue_team_receipt": blue_team_receipt,
    }


def red_worker_v1(
    *,
    battle_id: str,
    run_id: str,
    image: str,
    target: Path,
    out_dir: Path,
    combination: dict[str, Any],
    exploit: dict[str, Any],
    persona: str,
    worker_index: int,
    session_started: float,
) -> dict[str, Any]:
    worker_id = safe_key(f"red-{worker_index}-{combination['exploit']}")
    worker_dir = out_dir / "red" / "workers" / worker_id
    workspace = worker_dir / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(target, workspace)

    started_at = utc_now()
    started_seconds = round(time.monotonic() - session_started, 6)
    ok, command = run_docker_command(
        image=image,
        target=workspace,
        command=exploit_probe_command(exploit=exploit, expect_success=True, hold_seconds=0.25),
        artifact_dir=worker_dir,
        name="red-exploit-probe",
    )
    finished_seconds = round(time.monotonic() - session_started, 6)
    receipt = {
        "schema": "battle.worker_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "team": "red",
        "worker_id": worker_id,
        "persona": persona,
        "model": "tau-local-deterministic-provider",
        "surface": "docker_exploit_probe_worker",
        "status": "PASS" if ok else "FAIL",
        "budget": {"max_commands": 1, "timeout_seconds": 60},
        "combination_id": combination["id"],
        "research_dispatch": {
            "first_research_lane": combination.get("first_research_lane"),
            "research_boost": combination.get("research_boost", 0.0),
            "research_sources": combination.get("research_sources", []),
            "dispatch_reason": combination.get("dispatch_reason"),
        },
        "exploit": exploit,
        "outcome": {"exploit_confirmed": ok},
        "async_timing": {
            "started_at": started_at,
            "finished_at": utc_now(),
            "started_at_seconds": started_seconds,
            "finished_at_seconds": finished_seconds,
            "duration_seconds": round(finished_seconds - started_seconds, 6),
        },
        "commands_run": [command],
        "created_at": utc_now(),
    }
    receipt_path = worker_dir / "worker-receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    write_json(receipt_path, receipt)
    return receipt


def blue_worker_v1(
    *,
    battle_id: str,
    run_id: str,
    image: str,
    target: Path,
    patches: Path,
    out_dir: Path,
    scenario: dict[str, Any],
    combination: dict[str, Any],
    defense: dict[str, Any],
    persona: str,
    worker_index: int,
    session_started: float,
) -> dict[str, Any]:
    worker_id = safe_key(f"blue-{worker_index}-{combination['defense']}")
    worker_dir = out_dir / "blue" / "workers" / worker_id
    workspace = worker_dir / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(target, workspace)

    started_at = utc_now()
    started_seconds = round(time.monotonic() - session_started, 6)
    patch_command = patch_and_test_command(
        regression_command=scenario["commands"]["regression"],
        hold_seconds=0.25,
    )
    ok, command = run_docker_command(
        image=image,
        target=workspace,
        command=patch_command,
        artifact_dir=worker_dir,
        name="blue-patch-and-regression",
        extra_mounts=[(patches, Path("/patches"), "ro")],
    )
    finished_seconds = round(time.monotonic() - session_started, 6)
    receipt = {
        "schema": "battle.worker_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "team": "blue",
        "worker_id": worker_id,
        "persona": persona,
        "model": "tau-local-deterministic-provider",
        "surface": "docker_patch_regression_worker",
        "status": "PASS" if ok else "FAIL",
        "budget": {"max_commands": 1, "timeout_seconds": 60},
        "combination_id": combination["id"],
        "research_dispatch": {
            "first_research_lane": combination.get("first_research_lane"),
            "research_boost": combination.get("research_boost", 0.0),
            "research_sources": combination.get("research_sources", []),
            "dispatch_reason": combination.get("dispatch_reason"),
        },
        "defense": defense,
        "outcome": {"patch_applied_and_regression_passed": ok},
        "async_timing": {
            "started_at": started_at,
            "finished_at": utc_now(),
            "started_at_seconds": started_seconds,
            "finished_at_seconds": finished_seconds,
            "duration_seconds": round(finished_seconds - started_seconds, 6),
        },
        "commands_run": [command],
        "created_at": utc_now(),
    }
    receipt_path = worker_dir / "worker-receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    write_json(receipt_path, receipt)
    return receipt


def patch_and_test_command(*, regression_command: list[str], hold_seconds: float = 0.0) -> list[str]:
    script = (
        "import shutil, subprocess, sys, time\n"
        f"time.sleep({hold_seconds!r})\n"
        "shutil.copyfile('/patches/app.py', '/workspace/app.py')\n"
        f"cmd = {regression_command!r}\n"
        "raise SystemExit(subprocess.run(cmd).returncode)\n"
    )
    return ["python", "-c", script]


def exploit_probe_command(
    *,
    exploit: dict[str, Any],
    expect_success: bool,
    hold_seconds: float = 0.0,
) -> list[str]:
    family = str(exploit.get("family", ""))
    payload = str(exploit.get("payload", ""))
    if family == "sql_injection":
        predicate = "'<li>admin</li>' in html"
    elif family == "reflected_xss":
        predicate = "payload in html"
    else:
        predicate = "False"
    script = f"""
import time
from app import render_search
payload = {payload!r}
time.sleep({hold_seconds!r})
html = render_search(payload)
success = bool({predicate})
raise SystemExit(0 if success is {expect_success!r} else 1)
"""
    return ["python", "-c", script]


def compute_overlap(red_receipts: list[dict[str, Any]], blue_receipts: list[dict[str, Any]]) -> dict[str, Any]:
    overlaps: list[dict[str, str]] = []
    for red in red_receipts:
        rt = red.get("async_timing", {})
        rs = float(rt.get("started_at_seconds", 0.0))
        rf = float(rt.get("finished_at_seconds", 0.0))
        for blue in blue_receipts:
            bt = blue.get("async_timing", {})
            bs = float(bt.get("started_at_seconds", 0.0))
            bf = float(bt.get("finished_at_seconds", 0.0))
            if rs < bf and bs < rf:
                overlaps.append(
                    {
                        "red_worker": str(red["worker_id"]),
                        "blue_worker": str(blue["worker_id"]),
                    }
                )
    return {
        "overlap_detected": bool(overlaps),
        "overlap_count": len(overlaps),
        "pairs": overlaps[:8],
        "evidence": "worker async_timing intervals overlap when red.start < blue.finish and blue.start < red.finish",
    }


def _tau_live_team(tau_live_receipt: dict[str, Any] | None, team: str) -> dict[str, Any]:
    if not tau_live_receipt:
        return {}
    teams = tau_live_receipt.get("teams")
    if not isinstance(teams, list):
        return {}
    for item in teams:
        if isinstance(item, dict) and item.get("team") == team:
            return item
    return {}


def _relative_or_none(out_dir: Path, value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return relative_to_out(out_dir, value)


def run_scorekeeper_replay(
    *,
    battle_id: str,
    run_id: str,
    image: str,
    target: Path,
    patches: Path,
    out_dir: Path,
    ledger_path: Path,
    scenario: dict[str, Any],
    warm_pond: dict[str, Any],
    selected: list[dict[str, Any]],
    arena_receipt: dict[str, Any],
    red_team_receipt: dict[str, Any],
    blue_team_receipt: dict[str, Any],
) -> dict[str, Any]:
    exploit_by_id = {item["id"]: item for item in warm_pond["exploit_candidates"]}
    defense_by_id = {item["id"]: item for item in warm_pond["defense_candidates"]}
    replay_dir = out_dir / "scorekeeper" / "replays"
    attempts: list[dict[str, Any]] = []

    for combination in selected:
        exploit = exploit_by_id[str(combination["exploit"])]
        defense = defense_by_id[str(combination["defense"])]
        attempt_id = safe_key(str(combination["id"]))
        attempt_dir = replay_dir / attempt_id
        workspace = attempt_dir / "workspace"
        if workspace.exists():
            shutil.rmtree(workspace)
        shutil.copytree(target, workspace)

        before_ok, before_cmd = run_docker_command(
            image=image,
            target=workspace,
            command=exploit_probe_command(exploit=exploit, expect_success=True),
            artifact_dir=attempt_dir,
            name="scorekeeper-exploit-before-patch",
        )
        patch_ok, patch_cmd = run_docker_command(
            image=image,
            target=workspace,
            command=patch_and_test_command(regression_command=["python", "-c", "raise SystemExit(0)"]),
            artifact_dir=attempt_dir,
            name="scorekeeper-apply-defense",
            extra_mounts=[(patches, Path("/patches"), "ro")],
        )
        after_ok, after_cmd = run_docker_command(
            image=image,
            target=workspace,
            command=exploit_probe_command(exploit=exploit, expect_success=False),
            artifact_dir=attempt_dir,
            name="scorekeeper-exploit-after-patch",
        )
        regression_ok, regression_cmd = run_docker_command(
            image=image,
            target=workspace,
            command=scenario["commands"]["regression"],
            artifact_dir=attempt_dir,
            name="scorekeeper-regression-after-patch",
        )

        status = "PASS" if before_ok and patch_ok and after_ok and regression_ok else "FAIL"
        receipt = {
            "schema": "battle.scorekeeper_attempt_receipt.v1",
            "battle_id": battle_id,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "status": status,
            "combination_id": combination["id"],
            "exploit": exploit,
            "defense": defense,
            "results": {
                "exploit_confirmed_before_patch": before_ok,
                "defense_applied": patch_ok,
                "exploit_blocked_after_patch": after_ok,
                "regression_tests_pass": regression_ok,
            },
            "commands_run": [before_cmd, patch_cmd, after_cmd, regression_cmd],
            "created_at": utc_now(),
        }
        receipt_path = attempt_dir / "attempt-receipt.json"
        receipt["receipt_path"] = str(receipt_path)
        write_json(receipt_path, receipt)
        attempts.append(receipt)
        record_event(
            ledger_path,
            run_id=run_id,
            battle_id=battle_id,
            team="scorekeeper",
            persona="battle-scorekeeper",
            event_type="scorekeeper_replay_attempt",
            status=status,
            artifact_path=receipt_path,
            details=to_jsonable(receipt),
        )

    passed = [attempt for attempt in attempts if attempt["status"] == "PASS"]
    failed = [attempt for attempt in attempts if attempt["status"] != "PASS"]
    receipt = {
        "schema": "battle.scorekeeper_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS" if attempts and not failed else "FAIL",
        "verdict": "BLUE_SUCCESS" if attempts and not failed else "RED_SUCCESS",
        "winner": "blue" if attempts and not failed else "red",
        "arena_team_is_judge": False,
        "objective_replay": True,
        "docker_only": True,
        "target_container_network": "none",
        "arena_receipt": "arena-receipt.json",
        "red_team_receipt": "red/team-receipt.json",
        "blue_team_receipt": "blue/team-receipt.json",
        "attempt_count": len(attempts),
        "passed_attempt_count": len(passed),
        "failed_attempt_count": len(failed),
        "attempt_receipts": [relative_to_out(out_dir, item["receipt_path"]) for item in attempts],
        "exploit_confirmed_before_patch": bool(attempts) and all(
            item["results"]["exploit_confirmed_before_patch"] for item in attempts
        ),
        "exploit_blocked_after_patch": bool(attempts) and all(
            item["results"]["exploit_blocked_after_patch"] for item in attempts
        ),
        "regression_tests_pass": bool(attempts) and all(
            item["results"]["regression_tests_pass"] for item in attempts
        ),
        "functionality_preserved": bool(attempts) and all(
            item["results"]["regression_tests_pass"] for item in attempts
        ),
        "created_at": utc_now(),
    }
    write_json(out_dir / "scorekeeper" / "scorekeeper-receipt.json", receipt)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="scorekeeper",
        persona="battle-scorekeeper",
        event_type="scorekeeper_receipt",
        status=str(receipt["status"]),
        artifact_path=out_dir / "scorekeeper" / "scorekeeper-receipt.json",
        details=to_jsonable(receipt),
    )
    return receipt


def recall_promoted_mutations(
    *,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    red_persona: str,
    blue_persona: str,
    memory_base_url: str,
    memory_required: bool,
) -> dict[str, Any]:
    payload = {
        "q": (
            "Battle warm pond promoted SQL injection reflected XSS parameterized "
            f"HTML escape mutations for {scenario.get('scenario_id')}"
        ),
        "k": 8,
        "collections": ["battle_mutation_memory"],
        "tags": ["battle", "warm_pond", "mutation"],
        "recall_profile": "procedural_memory",
        "recall_profile_source": "battle_v1_operational",
        "threshold": 0.0,
    }
    receipt: dict[str, Any] = {
        "schema": "battle.memory_recall_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS",
        "memory_base_url": memory_base_url,
        "collection": "battle_mutation_memory",
        "query": payload,
        "found": False,
        "item_count": 0,
        "top_keys": [],
        "required": memory_required,
    }
    try:
        with httpx.Client(
            base_url=memory_base_url,
            timeout=httpx.Timeout(10.0, connect=2.0),
        ) as client:
            response = client.post("/recall", json=payload)
            receipt["http_status"] = response.status_code
            response.raise_for_status()
            data = response.json()
            items = data.get("items", []) or []
            receipt["recall_found"] = bool(data.get("found"))
            if not items:
                list_response = client.post(
                    "/list",
                    json={"collection": "battle_mutation_memory", "limit": 8},
                )
                receipt["list_http_status"] = list_response.status_code
                list_response.raise_for_status()
                list_data = list_response.json()
                items = list_data.get("documents", []) or []
                receipt["fallback"] = {
                    "reason": "diagnostic_only_recall_returned_no_items_for_custom_collection",
                    "endpoint": "/list",
                    "total": list_data.get("total", 0),
                }
        receipt.update(
            {
                "found": bool(data.get("found")),
                "item_count": len(items),
                "top_keys": [item.get("_key") for item in items[:5] if isinstance(item, dict)],
                "meta": data.get("meta", {}),
            }
        )
    except Exception as exc:
        receipt["status"] = "BLOCKED" if memory_required else "SKIPPED"
        receipt["reason"] = f"memory_recall_failed: {type(exc).__name__}: {exc}"
    return receipt


def promote_warm_pond_memory(
    *,
    out_dir: Path,
    battle_id: str,
    run_id: str,
    scenario: dict[str, Any],
    scorekeeper: dict[str, Any],
    warm_pond: dict[str, Any],
    red_persona: str,
    blue_persona: str,
    memory_base_url: str,
    memory_required: bool,
) -> dict[str, Any]:
    context_dir = out_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    attempt_receipts = []
    for rel in scorekeeper.get("attempt_receipts", []):
        path = out_dir / str(rel)
        if path.is_file():
            attempt_receipts.append(json.loads(path.read_text(encoding="utf-8")))

    documents = []
    for attempt in attempt_receipts:
        promotion_type = "winner" if attempt["status"] == "PASS" else "negative_evidence"
        key_source = f"{scenario.get('scenario_id')}:{attempt['combination_id']}:{promotion_type}"
        key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:24]
        families = sorted(
            set(attempt.get("exploit", {}).get("family", "").split())
            | set(attempt.get("defense", {}).get("family", "").split())
        )
        document = {
            "_key": key,
            "schema": "battle.mutation_memory.v1",
            "kind": "battle_warm_pond_mutation",
            "promotion_type": promotion_type,
            "battle_id": battle_id,
            "run_id": run_id,
            "scenario_id": scenario.get("scenario_id"),
            "attempt_id": attempt["attempt_id"],
            "combination_id": attempt["combination_id"],
            "status": attempt["status"],
            "verdict": scorekeeper.get("verdict"),
            "winner": scorekeeper.get("winner"),
            "red_persona": red_persona,
            "blue_persona": blue_persona,
            "model": "tau-local-deterministic-provider",
            "exploit": attempt.get("exploit"),
            "defense": attempt.get("defense"),
            "outcome": attempt.get("results"),
            "graph_edges": [
                {"from": key, "to": "battle", "kind": "belongs_to"},
                {"from": key, "to": scenario.get("scenario_id"), "kind": "scenario"},
                {"from": key, "to": red_persona, "kind": "red_persona"},
                {"from": key, "to": blue_persona, "kind": "blue_persona"},
                {"from": key, "to": attempt.get("exploit", {}).get("symbol"), "kind": "code_symbol"},
                {"from": key, "to": attempt.get("defense", {}).get("symbol"), "kind": "defense_symbol"},
            ],
            "problem": (
                "Select a warm-pond exploit/defense mutation for a tiny Python "
                "search app with SQL injection and reflected XSS risk."
            ),
            "solution": (
                f"{promotion_type}: {attempt['combination_id']} -> "
                f"{attempt['status']} via Docker scorekeeper replay."
            ),
            "text": (
                f"Battle mutation {attempt['combination_id']} status={attempt['status']} "
                f"verdict={scorekeeper.get('verdict')} red={red_persona} blue={blue_persona}"
            ),
            "tags": [
                "battle",
                "warm_pond",
                "mutation",
                promotion_type,
                "CWE-89",
                "CWE-79",
                f"persona:{red_persona}",
                f"persona:{blue_persona}",
            ],
            "artifact_paths": {
                "attempt_receipt": relative_to_out(out_dir, attempt["receipt_path"]),
                "scorekeeper": "scorekeeper/scorekeeper-receipt.json",
                "scoreboard": "scoreboard.json",
            },
            "created_at": utc_now(),
        }
        documents.append(document)

    receipt: dict[str, Any] = {
        "schema": "battle.memory_promotion_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS",
        "memory_base_url": memory_base_url,
        "collection": "battle_mutation_memory",
        "document_count": len(documents),
        "winner_count": len([doc for doc in documents if doc["promotion_type"] == "winner"]),
        "negative_evidence_count": len(
            [doc for doc in documents if doc["promotion_type"] == "negative_evidence"]
        ),
        "document_keys": [doc["_key"] for doc in documents],
        "required": memory_required,
    }
    try:
        if not documents:
            raise RuntimeError("no_mutation_documents_to_promote")
        with httpx.Client(
            base_url=memory_base_url,
            timeout=httpx.Timeout(10.0, connect=2.0),
        ) as client:
            response = client.post(
                "/upsert",
                json={"collection": "battle_mutation_memory", "documents": documents},
            )
            receipt["http_status"] = response.status_code
            response.raise_for_status()
            receipt["response"] = response.json()
    except Exception as exc:
        receipt["status"] = "BLOCKED" if memory_required else "SKIPPED"
        receipt["reason"] = f"memory_promotion_failed: {type(exc).__name__}: {exc}"
    write_json(context_dir / "memory-promotion-receipt.json", receipt)
    return receipt


def build_context_receipt(
    *,
    battle_id: str,
    run_id: str,
    memory_recall: dict[str, Any],
    code_context: dict[str, Any],
    scan: dict[str, Any],
    research: dict[str, Any],
    warm_pond: dict[str, Any],
    async_execution: dict[str, Any],
    scorekeeper: dict[str, Any],
    memory_promotion: dict[str, Any],
) -> dict[str, Any]:
    ok = all(
        item["status"] == "PASS"
        for item in [
            memory_recall,
            code_context,
            scan,
            research,
            warm_pond,
            async_execution,
            scorekeeper,
            memory_promotion,
        ]
    )
    return {
        "schema": "battle.context_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "PASS" if ok else "BLOCKED",
        "memory_recall": "context/memory-recall-receipt.json",
        "code_context": "context/code-context-receipt.json",
        "fast_scan": "context/fast-scan-receipt.json",
        "research_broker": "context/research-broker-receipt.json",
        "warm_pond": "context/warm-pond-receipt.json",
        "memory_promotion": "context/memory-promotion-receipt.json",
        "memory": {
            "recall_status": memory_recall["status"],
            "recall_found": memory_recall.get("found"),
            "promotion_status": memory_promotion["status"],
            "promotion_count": memory_promotion.get("document_count", 0),
            "winner_count": memory_promotion.get("winner_count", 0),
            "negative_evidence_count": memory_promotion.get("negative_evidence_count", 0),
        },
        "scan": {
            "status": scan["status"],
            "finding_count": scan.get("finding_count", 0),
            "families": scan.get("families", []),
        },
        "research": {
            "status": research["status"],
            "mode": research.get("mode"),
            "lane_count": research.get("lane_count", 0),
            "passed_lane_count": research.get("passed_lane_count", 0),
            "blocked_lane_count": research.get("blocked_lane_count", 0),
            "completion_order": research.get("completion_order", []),
        },
        "warm_pond_candidates": {
            "status": warm_pond["status"],
            "exploit_candidate_count": warm_pond.get("exploit_candidate_count", 0),
            "defense_candidate_count": warm_pond.get("defense_candidate_count", 0),
            "combination_count": warm_pond.get("combination_count", 0),
            "research_weighted_candidate_count": warm_pond.get(
                "research_weighted_candidate_count", 0
            ),
            "research_weighted_combination_count": warm_pond.get(
                "research_weighted_combination_count", 0
            ),
            "selection_rule": warm_pond.get("selection_rule"),
        },
        "warm_pond_execution_summary": {
            "status": scorekeeper["status"],
            "selected_attempt_count": scorekeeper.get("attempt_count", 0),
            "passed_attempt_count": scorekeeper.get("passed_attempt_count", 0),
            "failed_attempt_count": scorekeeper.get("failed_attempt_count", 0),
        },
        "async": {
            "status": async_execution["status"],
            "red_worker_count": async_execution["red_worker_count"],
            "blue_worker_count": async_execution["blue_worker_count"],
            "overlap_evidence": async_execution["overlap_evidence"],
        },
        "artifacts": [
            "context/memory-recall-receipt.json",
            "context/code-context-receipt.json",
            "context/fast-scan-receipt.json",
            "context/research-broker-receipt.json",
            "context/warm-pond-receipt.json",
            "context/memory-promotion-receipt.json",
            "red/team-receipt.json",
            "blue/team-receipt.json",
            "scorekeeper/scorekeeper-receipt.json",
        ],
    }


def build_scoreboard(
    *,
    battle_id: str,
    scenario: dict[str, Any],
    scorekeeper: dict[str, Any],
    async_execution: dict[str, Any],
    context_receipt: dict[str, Any],
    memory_promotion: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "battle.scoreboard.v1",
        "battle_id": battle_id,
        "status": scorekeeper["status"],
        "verdict": scorekeeper["verdict"],
        "winner": scorekeeper["winner"],
        "red_score": 1.5 * scorekeeper.get("attempt_count", 0),
        "blue_score": 3.6 * scorekeeper.get("passed_attempt_count", 0),
        "tdsr": 1.0 if scorekeeper["status"] == "PASS" else 0.0,
        "fdsr": 0.0,
        "asc": scorekeeper.get("attempt_count", 0),
        "operational": {
            "four_party": True,
            "docker_only": True,
            "red_blue_async": True,
            "scorekeeper_objective_replay": True,
        },
        "async": {
            "red_worker_count": async_execution["red_worker_count"],
            "blue_worker_count": async_execution["blue_worker_count"],
            "overlap_evidence": async_execution["overlap_evidence"],
        },
        "context": {
            "enabled": True,
            "status": context_receipt["status"],
            "receipt": "context/context-receipt.json",
            "research_broker_status": context_receipt["research"]["status"],
            "research_passed_lane_count": context_receipt["research"]["passed_lane_count"],
            "memory_store_status": memory_promotion["status"],
            "memory_promotion_status": memory_promotion["status"],
            "memory_promotion_count": memory_promotion.get("document_count", 0),
        },
        "receipts": {
            "arena": "arena-receipt.json",
            "red": "red/team-receipt.json",
            "blue": "blue/team-receipt.json",
            "judge": "scorekeeper/scorekeeper-receipt.json",
            "context": "context/context-receipt.json",
        },
    }


def build_monitor_graph(
    *,
    battle_id: str,
    scenario: dict[str, Any],
    scoreboard: dict[str, Any],
    arena_receipt: dict[str, Any],
    red_team_receipt: dict[str, Any],
    blue_team_receipt: dict[str, Any],
    scorekeeper: dict[str, Any],
    memory_recall: dict[str, Any],
    research: dict[str, Any],
    memory_promotion: dict[str, Any],
    selected: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes = [
        {"id": "team:arena", "label": "Arena Team", "kind": "team", "status": arena_receipt["status"]},
        {"id": "team:red", "label": red_team_receipt["persona"], "kind": "team", "status": red_team_receipt["status"]},
        {"id": "team:blue", "label": blue_team_receipt["persona"], "kind": "team", "status": blue_team_receipt["status"]},
        {"id": "scorekeeper", "label": "Scorekeeper", "kind": "signal", "status": scorekeeper["status"]},
        {"id": "signal:memory-recall", "label": "memory recall", "kind": "signal", "status": memory_recall["status"]},
        {"id": "signal:research-broker", "label": "research broker", "kind": "signal", "status": research["status"]},
        {"id": "signal:memory-promotion", "label": "memory promotion", "kind": "signal", "status": memory_promotion["status"]},
        {"id": "signal:async-overlap", "label": "async overlap", "kind": "signal", "status": "PASS" if scoreboard["async"]["overlap_evidence"]["overlap_detected"] else "BLOCKED"},
    ]
    links = [
        {"source": "team:arena", "target": "scorekeeper", "label": "hidden target"},
        {"source": "team:red", "target": "scorekeeper", "label": "exploit evidence"},
        {"source": "team:blue", "target": "scorekeeper", "label": "patch evidence"},
        {"source": "signal:memory-recall", "target": "team:red", "label": "seeded"},
        {"source": "signal:memory-recall", "target": "team:blue", "label": "seeded"},
        {"source": "signal:research-broker", "target": "team:red", "label": "research"},
        {"source": "signal:research-broker", "target": "team:blue", "label": "research"},
        {"source": "scorekeeper", "target": "signal:memory-promotion", "label": "promotes"},
        {"source": "team:red", "target": "signal:async-overlap", "label": "overlaps"},
        {"source": "team:blue", "target": "signal:async-overlap", "label": "overlaps"},
    ]
    for combination in selected:
        node_id = f"attempt:{safe_key(str(combination['id']))}"
        nodes.append(
            {
                "id": node_id,
                "label": str(combination["id"]),
                "kind": "attempt",
                "status": scorekeeper["status"],
                "detail": "Docker scorekeeper replayed exploit before patch, patch, exploit after patch, and regression.",
            }
        )
        links.append({"source": "team:red", "target": node_id, "label": "probe"})
        links.append({"source": "team:blue", "target": node_id, "label": "defend"})
        links.append({"source": node_id, "target": "scorekeeper", "label": "replay"})
        links.append({"source": node_id, "target": "signal:memory-promotion", "label": "promoted"})
    return {
        "schema": "battle.force_graph.v1",
        "battle_id": battle_id,
        "scenario": scenario.get("scenario_id"),
        "status": scoreboard["status"],
        "nodes": nodes,
        "links": links,
    }


def write_monitor_index_v1(
    *,
    out_dir: Path,
    battle_id: str,
    scenario: dict[str, Any],
    scoreboard: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> None:
    write_json(
        out_dir / "monitor-index.json",
        {
            "schema": "battle.monitor_index.v1",
            "battle_id": battle_id,
            "campaign": "Battle v1 Operational",
            "scenario": scenario.get("scenario_id"),
            "title": scenario.get("title", "Battle v1 operational proof"),
            "status": scoreboard["status"],
            "verdict": scoreboard["verdict"],
            "players": [
                {"team": "arena", "persona": "Arena Team", "role": "target-builder", "receipt": "arena-receipt.json"},
                {"team": "red", "persona": red_persona, "role": "async-exploit-workers", "receipt": "red/team-receipt.json"},
                {"team": "blue", "persona": blue_persona, "role": "async-defense-workers", "receipt": "blue/team-receipt.json"},
                {"team": "judge", "persona": "Scorekeeper", "role": "objective-docker-replay", "receipt": "scorekeeper/scorekeeper-receipt.json"},
            ],
            "timeline": [
                {"stage": "prepare", "status": "PASS"},
                {"stage": "red", "status": "PASS"},
                {"stage": "blue", "status": "PASS"},
                {"stage": "judge", "status": scoreboard["status"]},
                {"stage": "score", "status": scoreboard["status"]},
            ],
            "scoreboard": "scoreboard.json",
            "graph": "graph/battle-v1-force-graph.json",
            "artifacts": artifact_list(out_dir),
        },
    )


def write_blocked_v1(
    *,
    out_dir: Path,
    battle_id: str,
    run_id: str,
    reason: str,
    extra: dict[str, Any],
) -> dict[str, Any]:
    receipt = {
        "schema": "battle.run_receipt.v1",
        "battle_id": battle_id,
        "run_id": run_id,
        "status": "BLOCKED",
        "verdict": "BLOCKED",
        "reason": reason,
        "execution": EXECUTION_SCOPE,
        "claim_scope": "battle_v1_four_party_docker_operational_proof",
        "non_claims": NON_CLAIMS,
        **extra,
        "artifacts": artifact_list(out_dir),
    }
    write_json(out_dir / "run-receipt.json", receipt)
    return receipt


def relative_to_out(out_dir: Path, path: str | Path) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(out_dir))
    except ValueError:
        return str(p)
