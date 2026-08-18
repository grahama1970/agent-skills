"""CLI implementation for memory-backed ask queries and oracle review routing."""

import json
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
import httpx
from loguru import logger as log

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

from .ask_auto_learn import _auto_learn
from .ask_config import (
    DEFAULT_ORACLE_BACKEND,
    DEFAULT_ORACLE_HEARTBEAT_INTERVAL,
    DEFAULT_ORACLE_IDLE_TIMEOUT,
    DEFAULT_ORACLE_MODEL,
    DEFAULT_ORACLE_REASONING,
    DEFAULT_ORACLE_TIMEOUT,
    ORACLE_BACKENDS,
    SCILLM_API_KEY,
    SCILLM_BASE_URL,
    SUBAGENT_RUNNER,
)
from .argue import ARGUE_TIE_BREAKERS, run_argue
from .ask_dag import (
    AskDagError,
    dag_dry_run_summary,
    draft_ask_dag_from_question,
    execute_ask_dag,
    load_ask_dag,
    natural_language_dag_attention,
    should_orchestrate_from_text,
)
from .scillm_agents import run_visible_subagent_turn
from .chain_specs import apply_chain_options
from .cae_gap_review import DEFAULT_CAE_JUDGE, DEFAULT_CAE_REVIEWERS, run_cae_gap_review
from .deep_review import build_deep_review_request, infer_deep_review
from .delegate import DelegateError, load_delegate_registry, resolve_delegate_invocation
from .dry_run_spec import build_ask_dry_run_spec, print_execution_spec
from .doctor import build_oracle_lane_health, probe_selected_oracle_lane
from .parallel_review import MAX_REVIEWERS, ParallelReviewError, run_parallel_review, validate_code_runner_allowed_files
from .ask_oracle import _is_meta_item
from .ask_persona_profiles import _format_persona_suggestion
from .ask_relevance import _has_relevant_domain_items, _try_evidence_case
from .preflight import EVIDENCE_CASE, NEEDS_ATTENTION, NORMAL_ANSWER, run_sparta_preflight
from .ask_results import _synthesise
from .ask_routing import (
    _is_operational_question,
    _parse_natural_cae_gap_review_query,
    _parse_missing_persona_roundtable_query,
    _parse_natural_argue_query,
    _parse_natural_persona_query,
    _parse_natural_parallel_review_query,
    _parse_natural_roundtable_query,
    _parse_natural_visible_subagent_query,
    _should_auto_oracle_persona,
)
from .reviewer_specs import focus_from_reviewer_specs, load_selected_reviewer_specs
from .review_protocols import is_date_sensitive_question
from .run_state import AskRunState, NoopRunState, build_context_policy, make_run_id
from .session_writer import SessionWriter
from .skills_exec import run_skill, parse_memory_output, run_memory_recall
from .persona_routing import (
    extract_bridges,
    extract_persona_from_question,
    find_relevant_personas,
    suggest_persona_consultation,
)
from .hybrid import ask_hybrid, learn_back
from .image_generation import generate_image_with_codex_oauth, generate_image_with_scillm
from .model_aliases import ModelAliasRoute, resolve_model_alias_route

WEBGPT_DEPRECATION_MESSAGE = (
    "WebGPT/ChatGPT routing has been removed from /ask. "
    "Use $surf webgpt.submit or the project-level $webgpt workflow directly."
)

app = typer.Typer(help="/ask ask - Query accumulated knowledge")

SKILL_MENTION_RE = re.compile(
    r"(?<![\w/])(?:\$([A-Za-z][A-Za-z0-9_-]{1,80})|/(?!home/|tmp/|mnt/|var/|usr/|etc/|opt/|run/)([A-Za-z][A-Za-z0-9_-]{1,80})\b(?!/))"
)
VISIBLE_SUBAGENT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _extract_skill_mentions(text: str) -> list[str]:
    return sorted({dollar or slash for dollar, slash in SKILL_MENTION_RE.findall(text) if dollar or slash})


def _lane_health_map() -> dict[str, dict]:
    return {item["lane"]: item for item in build_oracle_lane_health()}


def _build_route_decision(
    request: dict,
    lane_health: Optional[dict[str, dict]] = None,
    *,
    live_selected_lane: bool = False,
) -> dict:
    """Describe the selected ask lane after CLI inference has normalized options."""
    lane_health = lane_health or _lane_health_map()
    selected_mode = "memory_ask"
    reasons: list[str] = ["default_memory_backed_ask"]
    if request.get("delegate_dry_run"):
        selected_mode = "delegate_dry_run"
        reasons = ["explicit_delegate_dry_run"]
    elif request.get("image_generate"):
        selected_mode = "image_generation"
        reasons = ["explicit_image_generate"]
    elif request.get("ask_dag"):
        selected_mode = "dag_orchestration"
        reasons = ["ask_dag_present"]
    elif request.get("deep_review"):
        selected_mode = "deep_review"
        reasons = ["deep_review_requested_or_inferred"]
    elif request.get("cae_gap_review"):
        selected_mode = "cae_gap_review"
        reasons = ["cae_gap_review_requested_or_inferred"]
    elif request.get("argue"):
        selected_mode = "argue"
        reasons = ["argue_requested_or_inferred"]
    elif request.get("parallel_review"):
        selected_mode = "parallel_review"
        reasons = ["parallel_review_requested_or_inferred"]
    elif request.get("roundtable"):
        selected_mode = "roundtable"
        reasons = ["roundtable_requested_or_inferred"]
    elif request.get("oracle"):
        selected_mode = "oracle"
        reasons = ["oracle_requested_or_inferred"]

    oracle_backend = str(request.get("oracle_backend") or DEFAULT_ORACLE_BACKEND)
    selected_backend = (
        "delegate"
        if selected_mode == "delegate_dry_run"
        else
        str(request.get("image_model") or "")
        if selected_mode == "image_generation"
        else oracle_backend if request.get("oracle") else "memory"
    )
    evidence_policy = "runtime_artifacts"
    if selected_mode in {"deep_review", "parallel_review", "cae_gap_review", "argue"}:
        evidence_policy = "runtime_artifacts_and_verifier"
    elif selected_backend in {"webgemini", "webkimi", "webperplexity", "cursor-browser"}:
        evidence_policy = "browser_sentinel_and_runtime_artifacts"
    elif selected_backend == "scillm":
        evidence_policy = "scillm_response_and_runtime_artifacts"

    alternatives: list[dict] = []
    if selected_mode == "delegate_dry_run":
        alternatives.append({
            "lane": "delegate_resolver",
            "status": "selected",
            "reason": "explicit_delegate_dry_run",
        })
    elif selected_mode != "image_generation":
        alternatives.append({
            "lane": "memory_ask",
            "status": "available",
            "reason": "local_memory_retrieval_path",
        })
    if request.get("oracle"):
        for backend in sorted(ORACLE_BACKENDS):
            health = lane_health.get(backend, {})
            health_state = str(health.get("state") or "available")
            alternatives.append({
                "lane": f"oracle:{backend}",
                "status": "selected" if backend == oracle_backend else health_state,
                "reason": "explicit_or_inferred_oracle_backend" if backend == oracle_backend else str(health.get("detail") or "configured_oracle_backend"),
            })
    if live_selected_lane and request.get("oracle") and selected_backend != "auto":
        selected_health = probe_selected_oracle_lane(selected_backend)
        lane_health[selected_backend] = selected_health
    else:
        selected_health = lane_health.get(selected_backend, {}) if request.get("oracle") else {}
    unavailable_lane_reasons: list[dict] = []
    if request.get("oracle") and selected_backend != "auto":
        selected_state = str(selected_health.get("state") or "available")
        if selected_state != "available":
            unavailable_lane_reasons.append({
                "lane": selected_backend,
                "state": selected_state,
                "detail": str(selected_health.get("detail") or "selected lane is not available"),
                "safe_default": str(selected_health.get("safe_default") or "do_not_route_to_lane"),
            })

    return {
        "schema_version": "ask.route_decision.v1",
        "selected_mode": selected_mode,
        "selected_backend": selected_backend,
        "oracle_backend": oracle_backend if request.get("oracle") else None,
        "oracle_model": request.get("oracle_model"),
        "reasons": reasons,
        "alternatives_considered": alternatives,
        "required_evidence_policy": evidence_policy,
        "fail_closed": selected_mode in {"deep_review", "parallel_review", "cae_gap_review", "argue"}
        or selected_backend in {"webgemini", "webkimi", "webperplexity", "cursor-browser"},
        "unavailable_lane_reasons": unavailable_lane_reasons,
    }



# ---------------------------------------------------------------------------
# Core ask() function
# ---------------------------------------------------------------------------

def ask(
    question: str,
    scope: str = "ask",
    k: int = 5,
    use_bridges: bool = False,
    raw: bool = False,
    as_json: bool = False,
    auto_learn: bool = False,
    collection: str = "behavioral",
    hybrid: bool = False,
    persona_id: Optional[str] = None,
    oracle_model: Optional[str] = None,
    oracle_reasoning: str = DEFAULT_ORACLE_REASONING,
    oracle_timeout: float = DEFAULT_ORACLE_TIMEOUT,
    oracle_idle_timeout: float = DEFAULT_ORACLE_IDLE_TIMEOUT,
    oracle_heartbeat_interval: float = DEFAULT_ORACLE_HEARTBEAT_INTERVAL,
    oracle_persona: Optional[str] = None,
    oracle_consult_personas: Optional[list[dict]] = None,
    oracle_peer: Optional[str] = None,
    oracle_iterations: int = 1,
    oracle_backend: str = DEFAULT_ORACLE_BACKEND,
    oracle_persona_model: Optional[str] = None,
    oracle_peer_model: Optional[str] = None,
    oracle_model_alias: Optional[dict] = None,
    oracle_persona_scope: str = "personas",
    oracle_image_paths: Optional[list[str]] = None,
    roundtable: bool = False,
    roundtable_personas: Optional[str] = None,
    roundtable_role_preset: str = "adversarial-review",
    roundtable_rounds: int = 2,
    roundtable_mode: str = "adversarial",
    roundtable_persist: str = "summary",
    argue: bool = False,
    decision_required: bool = False,
    tie_breaker: Optional[str] = None,
    parallel_review: bool = False,
    parallel_reviewers: int = 3,
    parallel_review_personas: Optional[str] = None,
    parallel_review_focus: Optional[str] = None,
    parallel_review_role_preset: str = "adversarial-review",
    review_target: Optional[str] = None,
    parallel_review_runner: str = "scillm",
    review_dag: str = "hybrid",
    read_only_review: bool = True,
    code_runner_handoff: bool = False,
    implement_with: Optional[str] = None,
    apply_fixes: bool = False,
    code_runner_allowed_files: Optional[list[str]] = None,
    code_runner_dod_commands: Optional[list[str]] = None,
    implementation_non_goals: Optional[list[str]] = None,
    implementation_risk_notes: Optional[list[str]] = None,
    dogpile_mode: str = "auto",
    deep_review: bool = False,
    deep_review_target: Optional[str] = None,
    deep_review_profile: str = "max_available",
    deep_reviewers: int = 5,
    deep_review_focus: Optional[str] = None,
    deep_review_fallback_policy: str = "fail_closed",
    deep_review_persist: str = "summary",
    deep_review_output_root: str = ".ask_artifacts/deep-review",
    cae_gap_review: bool = False,
    cae_reviewers: Optional[str] = None,
    cae_judge: str = DEFAULT_CAE_JUDGE,
    cae_max_rounds: int = 3,
    webgpt_tab_id: str = "",
    webgpt_url: str = "",
    webgpt_create_tab: bool = False,
    webgpt_project: str = "",
    webgpt_once: bool = False,
    gemini_tab_id: str = "",
    gemini_url: str = "",
    kimi_tab_id: str = "",
    kimi_url: str = "",
    cursor_browser_view_id: str = "",
    cursor_browser_url: str = "",
    cursor_browser_project: str = "",
    visible_subagent: Optional[dict] = None,
    mentioned_skills: Optional[list[str]] = None,
    ask_dag: Optional[dict] = None,
    run_state: Optional[AskRunState] = None,
) -> dict:
    """Query accumulated knowledge.

    Args:
        question: The question to ask.
        scope: Memory scope to query.
        k: Number of results to retrieve.
        use_bridges: Also traverse bridge attributes.
        raw: Return raw memory results without synthesis.
        as_json: Format output as JSON.
        auto_learn: If True, trigger learn pipeline when no results found.
        collection: Taxonomy collection (for auto-learn).
        hybrid: Use hybrid RAG+QRA retrieval (separate collection queries).
        persona_id: Persona identifier for session tracking (None for human).
        oracle_model: Optional scillm model for final oracle synthesis.
        oracle_reasoning: Reasoning effort for oracle synthesis.
        oracle_timeout: HTTP timeout for oracle synthesis.
        oracle_idle_timeout: Maximum subagent silence before marking stalled.
        oracle_heartbeat_interval: Seconds between persisted subagent heartbeat snapshots.
        oracle_persona: Persona/subagent perspective for oracle synthesis.
        oracle_consult_personas: Suggested personas to include as advisory context.
        oracle_peer: Optional second persona/subagent for deliberation.
        oracle_iterations: Number of oracle deliberation calls.
        oracle_backend: Oracle execution backend: auto, scillm, or subagent-runner.
        oracle_persona_model: Optional model for primary persona turns.
        oracle_peer_model: Optional model for peer persona turns.
        oracle_model_alias: Resolved provider-family shorthand metadata.
        oracle_persona_scope: Preferred memory scope for persona profiles.
        oracle_image_paths: Image files to attach to direct scillm oracle calls.
        roundtable: Run sequential state-machine persona deliberation.
        roundtable_personas: Comma-separated persona[:protocol_role] participants.
        roundtable_role_preset: Role preset for shorthand participant specs.
        roundtable_rounds: Number of sequential roundtable rounds.
        roundtable_mode: Roundtable mode label.
        roundtable_persist: summary or full protocol state in the result.
        argue: Run two parallel FOR/AGAINST /scillm calls followed by a judge call.
        decision_required: Force FOR/AGAINST instead of allowing calibrated abstention.
        tie_breaker: Decision-required tie-breaker policy.
        parallel_review: Run independent parallel adversarial reviewers first.
        parallel_reviewers: Number of default reviewers when no personas are specified.
        parallel_review_personas: Comma-separated reviewer persona[:role] specs.
        parallel_review_focus: Comma-separated focus labels for default reviewers.
        parallel_review_role_preset: Role preset for parallel reviewers.
        review_target: Explicit parallel-review target: paths, git:diff, artifact, or manifest.
        parallel_review_runner: Review adapter; currently scillm.
        review_dag: Review DAG mode: judge-best or hybrid.
        read_only_review: Keep reviewer calls read-only.
        code_runner_handoff: Emit /code-runner handoff artifact for actionable findings.
        implement_with: Implementation backend (code-runner handoff or scillm-agent standing worker).
        apply_fixes: Alias for explicit code-runner implementation intent.
        dogpile_mode: auto, off, or force freshness policy for oracle subagents.
        deep_review: Run deep review with JSON/markdown artifacts.
        cae_gap_review: Run evidence-case-backed CAE reviewer/judge loop.
        visible_subagent: Visible subagent routing contract from the CLI.
        mentioned_skills: Skill names detected in the original visible-subagent utterance.
        ask_dag: Validated ask.dag.v1 document to execute before synthesis.

    Returns:
        dict with answer, sources, bridges.
    """
    if any([oracle_backend == "webgpt", webgpt_tab_id, webgpt_url, webgpt_create_tab, webgpt_project, webgpt_once]):
        raise ValueError(WEBGPT_DEPRECATION_MESSAGE)

    started_at = time.time()
    session = SessionWriter(scope=scope, persona_id=persona_id)
    session.add_turn("user", question)

    result: dict = {
        "question": question,
        "scope": scope,
        "items": [],
        "bridges_found": [],
        "answer": "",
        "auto_learned": False,
        "hybrid_mode": hybrid,
    }
    if visible_subagent is not None:
        _validate_visible_subagent_route(visible_subagent)
        transport = str(visible_subagent.get("transport") or "")
        if transport == "scillm_app_server_turn_steer" and oracle_backend != "scillm":
            raise RuntimeError(
                "Visible subagent requires the scillm Codex app-server transport; "
                "ordinary synthesis, subagent-runner, PTY stdin, tmux send-keys, and terminal input are not allowed."
            )
    skip_argv_bound_lookup = (
        bool(oracle_model)
        and _question_too_large_for_child_argv(question)
        and not any([hybrid, use_bridges, auto_learn, cae_gap_review, parallel_review, deep_review, argue])
    )
    if skip_argv_bound_lookup:
        preflight_decision = {
            "route": "normal_answer",
            "reason": "large_oracle_prompt_skipped_argv_bound_preflight",
            "skipped": True,
        }
    else:
        preflight_decision = run_sparta_preflight(question, scope, k, run_state=run_state)
    result["preflight"] = preflight_decision
    if preflight_decision.get("route") == NEEDS_ATTENTION:
        attention_payload = {
            "reason": preflight_decision.get("reason", "sparta_preflight_needs_attention"),
            "question": "SPARTA preflight found unresolved or fabricated identifiers that require confirmation before answering.",
            "safe_default": "pause",
            "resume_hint": "Verify the unresolved SPARTA identifiers, then ask again with corrected or grounded identifiers.",
            "preflight": preflight_decision,
        }
        if run_state:
            attention_payload = run_state.needs_attention(**attention_payload)
        result["needs_attention"] = attention_payload
        return result

    if parallel_review and not deep_review:
        if not review_target:
            attention = {
                "reason": "missing_parallel_review_target",
                "question": "Parallel review requires an explicit --review-target such as git:diff or a path list.",
                "safe_default": "do_not_run_review",
                "resume_hint": "Run again with --review-target <git:diff|paths|artifact>.",
            }
            if run_state:
                attention = run_state.needs_attention(**attention)
            result["needs_attention"] = attention
            return result
        if (apply_fixes or (implement_with and implement_with != "scillm-agent")) and not any(command.strip() for command in (code_runner_dod_commands or [])):
            attention = {
                "reason": "missing_code_runner_dod",
                "question": "Explicit code-runner implementation intent requires at least one --code-runner-dod-command.",
                "safe_default": "do_not_invoke_code_runner",
                "resume_hint": "Run again with --code-runner-dod-command <safe validation command>.",
            }
            if run_state:
                attention = run_state.needs_attention(**attention)
            result["needs_attention"] = attention
            return result

    if ask_dag:
        if not run_state:
            raise RuntimeError("DAG execution requires ask runtime artifacts.")
        run_state.step_started("dag", schema_version=ask_dag.get("schema_version", ""))
        dag_result = execute_ask_dag(
            ask_dag,
            question=question,
            scope=scope,
            run_state=run_state,
            oracle_model=oracle_model or DEFAULT_ORACLE_MODEL,
            oracle_reasoning=oracle_reasoning,
            oracle_timeout=oracle_timeout,
            oracle_image_paths=oracle_image_paths or [],
        )
        result["dag"] = {
            "schema_version": dag_result["schema_version"],
            "manifest_path": dag_result["manifest_path"],
            "nodes": [
                {
                    "id": node.get("id"),
                    "type": node.get("type"),
                    "ok": node.get("ok"),
                    "artifact_path": node.get("artifact_path"),
                }
                for node in dag_result.get("nodes", [])
            ],
            "context_items_count": len(dag_result.get("context_items", [])),
        }
        result["items"].extend(dag_result.get("context_items", []))
        run_state.step_finished(
            "dag",
            manifest_path=dag_result["manifest_path"],
            context_items_count=len(dag_result.get("context_items", [])),
        )

    if oracle_model:
        result["oracle"] = {
            "model": oracle_model,
            "reasoning_effort": oracle_reasoning,
            "idle_timeout_seconds": oracle_idle_timeout,
            "heartbeat_interval_seconds": oracle_heartbeat_interval,
        }
        if oracle_persona:
            result["oracle"]["persona"] = oracle_persona
        if oracle_consult_personas:
            result["oracle"]["consulted_personas"] = oracle_consult_personas
        if oracle_peer:
            result["oracle"]["peer"] = oracle_peer
        result["oracle"]["iterations_requested"] = oracle_iterations
        result["oracle"]["backend"] = oracle_backend
        if oracle_persona_model:
            result["oracle"]["persona_model"] = oracle_persona_model
        if oracle_peer_model:
            result["oracle"]["peer_model"] = oracle_peer_model
        if oracle_model_alias:
            result["oracle"]["model_alias"] = oracle_model_alias
        if oracle_image_paths:
            result["oracle"]["image_paths"] = oracle_image_paths
            result["oracle"]["image_count"] = len(oracle_image_paths)
        if roundtable:
            result["oracle"]["roundtable"] = {
                "personas": roundtable_personas or "",
                "role_preset": roundtable_role_preset,
                "rounds": roundtable_rounds,
                "mode": roundtable_mode,
                "persist": roundtable_persist,
            }
        if argue:
            result["oracle"]["argue"] = {
                "decision_required": decision_required,
                "tie_breaker": tie_breaker or "",
            }
        if parallel_review:
            result["oracle"]["parallel_review"] = {
                "reviewers": parallel_reviewers,
                "personas": parallel_review_personas or "",
                "focus": parallel_review_focus or "",
                "role_preset": parallel_review_role_preset,
            }
        if cae_gap_review:
            result["oracle"]["cae_gap_review"] = {
                "reviewers": cae_reviewers or DEFAULT_CAE_REVIEWERS,
                "judge": cae_judge,
                "max_rounds": cae_max_rounds,
            }
        result["oracle"]["dogpile_mode"] = dogpile_mode
        result["oracle"]["dogpile_recommended"] = _should_use_dogpile(question, dogpile_mode)

    deep_review_request = None
    if deep_review:
        if run_state:
            run_state.step_started("deep_review_request", target=deep_review_target or "")
        deep_review_request = build_deep_review_request(
            question=question,
            explicit_target=deep_review_target,
            profile=deep_review_profile,
            reviewers=deep_reviewers,
            focus=deep_review_focus,
            fallback_policy=deep_review_fallback_policy,
            dogpile_mode=dogpile_mode,
            output_root=deep_review_output_root,
            model=oracle_model,
            reasoning=oracle_reasoning,
            backend=oracle_backend,
        )
        result["deep_review"] = {
            "profile": deep_review_profile,
            "target": deep_review_request["target"],
            "persist": deep_review_persist,
        }
        if run_state:
            run_state.step_finished("deep_review_request", target=deep_review_request["target"])
        if deep_review_request["target"].get("requires_target"):
            attention = {
                "reason": "missing_deep_review_target",
                "question": deep_review_request["target"].get("message", "Deep review requires an explicit target."),
                "safe_default": "do_not_run_review",
                "resume_hint": "Run again with --deep-review-target <paths|diff|plan|artifact>.",
            }
            if run_state:
                attention = run_state.needs_attention(**attention)
            result["needs_attention"] = attention
            return result

    if parallel_review and not deep_review:
        parallel_result = run_parallel_review(
            question=question,
            target=review_target,
            reviewers=parallel_reviewers,
            personas=parallel_review_personas,
            focus=parallel_review_focus,
            runner=parallel_review_runner,
            read_only=read_only_review,
            model=oracle_model,
            timeout=oracle_timeout,
            run_state=run_state,
            dag_mode=review_dag,
            code_runner_handoff=code_runner_handoff,
            implement_with=implement_with,
            apply_fixes=apply_fixes,
            code_runner_allowed_files=code_runner_allowed_files or [],
            code_runner_dod_commands=code_runner_dod_commands or [],
            implementation_non_goals=implementation_non_goals or [],
            risk_notes=implementation_risk_notes or [],
        )
        parallel_result["scope"] = scope
        return parallel_result

    # Step 1: Memory recall (hybrid or standard)
    if skip_argv_bound_lookup:
        if run_state:
            run_state.step_started("memory_recall", scope=scope, k=k)
            run_state.step_finished(
                "memory_recall",
                returncode=0,
                items_count=0,
                skipped=True,
                reason="large_oracle_prompt_skipped_argv_bound_recall",
            )
        result["memory_lookup_skipped"] = {
            "reason": "large_oracle_prompt_skipped_argv_bound_recall",
            "question_bytes": len(question.encode("utf-8", errors="replace")),
        }
    elif hybrid:
        if run_state:
            run_state.step_started("hybrid_recall", scope=scope, k=k)
        log.info("Hybrid querying memory: q=%r scope=%r k=%d", question, scope, k)
        hybrid_result = ask_hybrid(question, scope, k, use_bridges=use_bridges)
        result["items"] = hybrid_result["items"]
        result["bridges_found"] = hybrid_result.get("bridges_found", [])
        result["qra_count"] = hybrid_result.get("qra_count", 0)
        result["rag_count"] = hybrid_result.get("rag_count", 0)
        log.info(
            "Hybrid recall: %d QRA + %d RAG -> %d items",
            result.get("qra_count", 0), result.get("rag_count", 0), len(result["items"]),
        )
        if run_state:
            run_state.step_finished("hybrid_recall", items_count=len(result["items"]))
    else:
        if run_state:
            run_state.step_started("memory_recall", scope=scope, k=k)
        log.info("Querying memory: q=%r scope=%r k=%d", question, scope, k)
        recall_result = run_memory_recall(question, scope, k)

        if recall_result["returncode"] == 0:
            items = parse_memory_output(recall_result["stdout"])
            result["items"].extend(items)
            log.info("Direct recall: %d items found", len(items))
            if run_state:
                run_state.step_finished("memory_recall", returncode=0, items_count=len(items))
        else:
            log.warning(
                "Memory recall failed: code=%d, stderr=%s",
                recall_result["returncode"], recall_result["stderr"][:100],
            )
            if run_state:
                run_state.step_finished("memory_recall", returncode=recall_result["returncode"], error=recall_result["stderr"][:200])

        # Step 2: Bridge traversal (optional, standard mode only)
        if use_bridges:
            if run_state:
                run_state.step_started("bridge_traversal")
            bridges = extract_bridges(question)
            result["bridges_found"] = bridges
            log.info("Bridge traversal: found bridges %s", bridges)

            for bridge in bridges:
                bridge_query = f"{question} {bridge.lower()}"
                log.debug("Bridge recall: bridge=%s q=%r", bridge, bridge_query)
                bridge_result = run_memory_recall(bridge_query, scope, k=3, timeout=10)

                if bridge_result["returncode"] == 0:
                    bridge_items = parse_memory_output(bridge_result["stdout"])
                    existing_problems = {i.get("problem", "") for i in result["items"]}
                    added = 0
                    for item in bridge_items:
                        if item.get("problem", "") not in existing_problems:
                            item["via_bridge"] = bridge
                            result["items"].append(item)
                            existing_problems.add(item.get("problem", ""))
                            added += 1
                    log.debug("Bridge %s: %d new items (from %d total)", bridge, added, len(bridge_items))
                else:
                    log.warning("Bridge recall for %s failed: code=%d", bridge, bridge_result["returncode"])
            if run_state:
                run_state.step_finished("bridge_traversal", bridges=bridges, items_count=len(result["items"]))

    # Step 2b: Evidence-case fallback for non-trivial queries.
    # Fires when: (a) no results at all, OR (b) only meta/irrelevant results.
    # When the question is analytical (not a direct control lookup like "SV-123"),
    # build a structured evidence case BEFORE answering.
    domain_items = [i for i in result["items"] if not _is_meta_item(i)]
    has_domain_answer = _has_relevant_domain_items(domain_items, question)
    # Operational questions (about the pipeline/datalake itself) always use evidence
    # cases — BM25 matches on words like "table" or "extraction" return datalake
    # content about satellites, not pipeline health data.
    is_operational = _is_operational_question(question)
    preflight_route = result.get("preflight", {}).get("route")
    should_build_evidence_case = preflight_route == EVIDENCE_CASE or cae_gap_review
    if should_build_evidence_case:
        if run_state:
            run_state.step_started(
                "evidence_case",
                operational=is_operational,
                has_domain_answer=has_domain_answer,
                preflight_route=preflight_route,
            )
        evidence_result = _try_evidence_case(question, scope)
        if evidence_result:
            result["evidence_case"] = evidence_result
            verdict = evidence_result.get("verdict", {})
            # Replace irrelevant items with evidence-based answer.
            # The original BM25 results were not relevant to this question —
            # the evidence case is now the primary answer source.
            evidence_items = []
            if verdict.get("score", 0) >= 0.65:
                # Build transparent solution with grounding evidence
                reasoning = verdict.get("reasoning", "")
                solution_parts = [reasoning] if reasoning else []

                # Extract grounding evidence from gate trace
                gate_trace = evidence_result.get("gate_trace", [])
                for step in gate_trace:
                    if step.get("gate") == "step_2_recall":
                        ge = step.get("data", {}).get("grounding_evidence", {})
                        if isinstance(ge, dict):
                            unresolved_id = ge.get("unresolved_id_like", 0)
                            resolved = ge.get("resolved", 0)
                            if unresolved_id > 0:
                                terms = ge.get("unresolved_terms", [])
                                term_names = [t.get("term", "?")
                                              for t in terms
                                              if isinstance(t, dict) and t.get("type") == "id_like"]
                                solution_parts.append(
                                    f"\n[Grounding: {resolved} resolved, "
                                    f"{unresolved_id} UNRESOLVED: {', '.join(term_names)}]"
                                )
                            elif resolved > 0:
                                solution_parts.append(
                                    f"\n[Grounding: {resolved} terms resolved]"
                                )
                    if "technique" in step.get("gate", ""):
                        solution_parts.append(
                            f"\n[Technique: {step.get('detail', '')[:120]}]"
                        )

                evidence_items.append({
                    "problem": question,
                    "solution": "\n".join(solution_parts),
                    "via": "evidence_case",
                    "evidence_case_id": evidence_result.get("claim", {}).get("id", ""),
                    "grade": verdict.get("grade", ""),
                    "score": verdict.get("score", 0),
                })
            # Only include raw evidence nodes when synthesis is absent
            if not evidence_items:
                for ev in evidence_result.get("evidence", []):
                    ev_result = ev.get("result", {})
                    top_item = ev_result.get("top_item", "")
                    if top_item and len(top_item) > 20:
                        evidence_items.append({
                            "problem": f"[{ev.get('layer', '?')}] {ev.get('method', 'EXAMINE')}",
                            "solution": top_item,
                            "via": "evidence_case",
                            "confidence": ev.get("confidence", 0),
                        })
            if evidence_items:
                result["items"] = evidence_items  # Replace, don't append
        if run_state:
            run_state.step_finished("evidence_case", used=bool(evidence_result), items_count=len(result["items"]))
        if not evidence_result:
            attention = {
                "reason": "evidence_case_required_but_unavailable",
                "question": "SPARTA preflight required /create-evidence-case before answering as grounded.",
                "safe_default": "do_not_answer_as_grounded",
                "resume_hint": "Install or fix /create-evidence-case, then rerun the same question. Do not downgrade this to ordinary /ask synthesis without an explicit policy change.",
                "preflight": result.get("preflight", {}),
                "scope": scope,
            }
            if run_state:
                attention = run_state.needs_attention(**attention)
            result["needs_attention"] = attention
            return result
        if cae_gap_review:
            cae_result = run_cae_gap_review(
                question=question,
                scope=scope,
                evidence_case=evidence_result,
                reviewers=cae_reviewers or DEFAULT_CAE_REVIEWERS,
                judge=cae_judge,
                max_rounds=cae_max_rounds,
                model=oracle_model or DEFAULT_ORACLE_MODEL,
                reasoning_effort=oracle_reasoning,
                timeout=oracle_timeout,
                idle_timeout=oracle_idle_timeout,
                heartbeat_interval=oracle_heartbeat_interval,
                backend=oracle_backend,
                dogpile_mode=dogpile_mode,
                run_state=run_state,
            )
            result["cae_gap_review"] = cae_result
            result["answer"] = cae_result["answer"]
            result["oracle"] = {
                "model": oracle_model or DEFAULT_ORACLE_MODEL,
                "reasoning_effort": oracle_reasoning,
                "backend": oracle_backend,
                "source": "cae_gap_review",
                "cae_gap_review": {
                    "reviewers": cae_result["reviewers"],
                    "judge": cae_result["judge"],
                    "rounds_completed": cae_result["rounds_completed"],
                    "halt_reason": cae_result["halt_reason"],
                    "dogpile_mode": dogpile_mode,
                },
            }
            return result

    # Step 2c: Auto-learn if still no domain results
    if not domain_items and auto_learn:
        if run_state:
            run_state.step_started("auto_learn", collection=collection)
        result = _auto_learn(result, question, scope, collection, k, use_bridges)
        if run_state:
            run_state.step_finished("auto_learn", items_count=len(result.get("items", [])), auto_learned=bool(result.get("auto_learned")))

    if visible_subagent is not None:
        if str(visible_subagent.get("transport") or "") == "subagent_runner_tmux":
            delivery = _run_visible_subagent_tmux(
                question=question,
                route=visible_subagent,
                memory_items=result["items"],
                mentioned_skills=mentioned_skills or [],
                run_state=run_state,
                timeout=oracle_timeout,
                idle_timeout=oracle_idle_timeout,
                model=oracle_model or DEFAULT_ORACLE_MODEL,
                reasoning=oracle_reasoning or DEFAULT_ORACLE_REASONING,
            )
        else:
            delivery = _run_visible_subagent_scillm(
                question=question,
                route=visible_subagent,
                memory_items=result["items"],
                mentioned_skills=mentioned_skills or [],
                run_state=run_state,
                timeout=oracle_timeout,
            )
        result["visible_subagent"] = visible_subagent
        result["mentioned_skills"] = mentioned_skills or []
        result["visible_subagent_delivery"] = delivery
        result["answer"] = _format_visible_subagent_answer(delivery)
        if run_state:
            run_state.event("visible_subagent_delivery", **delivery)
        session.add_turn("assistant", result.get("answer", ""), metadata={
            "items_count": len(result["items"]),
            "visible_subagent_delivery": delivery,
        })
        session_path = session.write()
        if session_path:
            result["session_path"] = str(session_path)
        if run_state:
            run_state.event("session_written", session_path=result.get("session_path", ""))
        _record_ask_telemetry(
            result=result,
            started_at=started_at,
            status="ok",
            oracle_model=oracle_model,
            oracle_reasoning=oracle_reasoning,
            oracle_backend=oracle_backend,
            oracle_idle_timeout=oracle_idle_timeout,
            oracle_heartbeat_interval=oracle_heartbeat_interval,
            oracle_persona=oracle_persona,
            oracle_peer=oracle_peer,
            oracle_iterations=oracle_iterations,
        )
        return result

    # Step 3: Synthesise answer or run argue protocol
    if run_state:
        run_state.step_started("synthesis", oracle_enabled=oracle_model is not None, deep_review=deep_review, argue=argue)
    if argue:
        argue_response = run_argue(
            question=question,
            context_items=result["items"],
            current_answer=result.get("answer", ""),
            model=oracle_model or DEFAULT_ORACLE_MODEL,
            reasoning_effort=oracle_reasoning,
            timeout=oracle_timeout,
            run_state=run_state or NoopRunState("argue"),
            decision_required=decision_required,
            tie_breaker=tie_breaker,
        )
        result.update(argue_response)
    else:
        _synthesise(
            result,
            k,
            raw,
            as_json,
            auto_learn,
            oracle_model=oracle_model,
            oracle_reasoning=oracle_reasoning,
            oracle_timeout=oracle_timeout,
            oracle_idle_timeout=oracle_idle_timeout,
            oracle_heartbeat_interval=oracle_heartbeat_interval,
            oracle_persona=oracle_persona,
            oracle_consult_personas=oracle_consult_personas,
            oracle_peer=oracle_peer,
            oracle_iterations=oracle_iterations,
            oracle_backend=oracle_backend,
            oracle_persona_model=oracle_persona_model,
            oracle_peer_model=oracle_peer_model,
            oracle_persona_scope=oracle_persona_scope,
            oracle_image_paths=oracle_image_paths or [],
            roundtable=roundtable,
            roundtable_personas=roundtable_personas,
            roundtable_role_preset=roundtable_role_preset,
            roundtable_rounds=roundtable_rounds,
            roundtable_mode=roundtable_mode,
            roundtable_persist=roundtable_persist,
            parallel_review=parallel_review,
            parallel_reviewers=parallel_reviewers,
            parallel_review_personas=parallel_review_personas,
            parallel_review_focus=parallel_review_focus,
            parallel_review_role_preset=parallel_review_role_preset,
            deep_review_request=deep_review_request,
            cursor_browser_view_id=cursor_browser_view_id,
            cursor_browser_url=cursor_browser_url,
            cursor_browser_project=cursor_browser_project,
            gemini_tab_id=gemini_tab_id,
            gemini_url=gemini_url,
            kimi_tab_id=kimi_tab_id,
            kimi_url=kimi_url,
            run_state=run_state,
        )
    if run_state:
        run_state.step_finished(
            "synthesis",
            answer_chars=len(str(result.get("answer", ""))),
            items_count=len(result.get("items", [])),
            deep_review_artifacts=result.get("deep_review", {}).get("artifact_paths", {}),
        )
        if result.get("deep_review", {}).get("artifact_paths"):
            run_state.add_artifacts(result["deep_review"]["artifact_paths"])
    if (
        deep_review_request
        and deep_review_fallback_policy == "fail_closed"
        and result.get("deep_review", {}).get("verifier_status") == "FAIL"
    ):
        attention = {
            "reason": "deep_review_verifier_failed",
            "question": "Deep review verifier failed; do not treat this run as SAFE or release-ready.",
            "safe_default": "do_not_use_review_verdict",
            "resume_hint": "Inspect review.md, review.json, and events.jsonl; fix the review runtime or target bundle, then rerun.",
            "verifier_failures": result.get("deep_review", {}).get("verifier_failures", []),
            "artifact_paths": result.get("deep_review", {}).get("artifact_paths", {}),
        }
        if run_state:
            attention = run_state.needs_attention(**attention)
        result["needs_attention"] = attention
        return result

    # Step 4: Learn-back for persona accumulation
    if persona_id and result["items"]:
        learn_back(result, persona_id, scope)

    # Write session transcript
    session.add_turn("assistant", result.get("answer", ""), metadata={
        "items_count": len(result["items"]),
        "bridges_found": result.get("bridges_found", []),
        "auto_learned": result.get("auto_learned", False),
        "hybrid_mode": result.get("hybrid_mode", False),
    })
    session_path = session.write()
    if session_path:
        result["session_path"] = str(session_path)
    if run_state:
        run_state.event("session_written", session_path=result.get("session_path", ""))

    _record_ask_telemetry(
        result=result,
        started_at=started_at,
        status="ok",
        oracle_model=oracle_model,
        oracle_reasoning=oracle_reasoning,
        oracle_backend=oracle_backend,
        oracle_idle_timeout=oracle_idle_timeout,
        oracle_heartbeat_interval=oracle_heartbeat_interval,
        oracle_persona=oracle_persona,
        oracle_peer=oracle_peer,
        oracle_iterations=oracle_iterations,
    )

    return result


def _format_visible_subagent_answer(delivery: dict) -> str:
    persona = delivery.get("persona", "subagent")
    transport = delivery.get("transport", "scillm_agents")
    state = delivery.get("state", "started")
    final_text = str(delivery.get("final_text") or delivery.get("response_text") or "").strip()
    if final_text:
        return f"{persona}: {final_text}"
    attach_command = delivery.get("attach_command", "")
    if attach_command:
        return f"{persona} {state} through {transport}. Attach: {attach_command}"
    worker_id = delivery.get("worker_id", "")
    if worker_id:
        return f"{persona} {state} through {transport} as worker {worker_id}."
    return f"{persona} {state} through {transport}."


def _visible_subagent_worker_id(route: dict) -> str:
    configured = os.environ.get("ASK_VISIBLE_SUBAGENT_WORKER_ID", "").strip()
    if configured:
        _validate_visible_identifier("worker_id", configured, "environment")
        return configured
    persona = str(route.get("persona") or "nico").strip().lower()
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", persona).strip("-")
    worker_id = cleaned or "nico"
    _validate_visible_identifier("worker_id", worker_id, "route")
    return worker_id


def _visible_memory_context(items: list[dict], limit: int = 8) -> list[dict]:
    context: list[dict] = []
    for item in items[:limit]:
        key = str(item.get("key") or item.get("_key") or item.get("id") or item.get("problem") or "")[:120]
        summary = str(item.get("summary") or item.get("solution") or item.get("text") or item.get("problem") or "")[:1000]
        if key or summary:
            safe_key = key or f"memory-{len(context) + 1}"
            context.append({"key": safe_key, "summary": summary or safe_key})
    return context


def _validate_visible_subagent_route(route: object) -> None:
    if not isinstance(route, dict) or route.get("mode") != "visible_subagent":
        raise ValueError("visible_subagent must be a visible_subagent route")
    allowed_keys = {
        "mode",
        "persona",
        "visibility",
        "turn_type",
        "operation",
        "memory_first",
        "transport",
        "trigger_phrase",
        "original_utterance",
        "handoff_id",
        "lease_id",
    }
    extra_keys = set(route) - allowed_keys
    if extra_keys:
        raise ValueError(f"visible_subagent route has unsupported fields: {sorted(extra_keys)}")
    persona = route.get("persona")
    if not isinstance(persona, str) or not persona.strip():
        raise ValueError("visible_subagent persona is required")
    if route.get("visibility") != "human_project_conversation":
        raise ValueError("visible_subagent visibility must be human_project_conversation")
    for id_field in ("handoff_id", "lease_id"):
        id_value = route.get(id_field)
        if id_value is not None:
            if not isinstance(id_value, str):
                raise ValueError(f"visible_subagent {id_field} must be a safe identifier")
            _validate_visible_identifier(id_field, id_value, "route")
    operation = route.get("operation")
    turn_type = route.get("turn_type")
    transport = route.get("transport")
    if operation not in {"launch", "steer"}:
        raise ValueError("visible_subagent operation must be launch or steer")
    if turn_type not in {"advisory", "review", "implementation_guidance", "steering"}:
        raise ValueError("visible_subagent turn_type is not supported")
    if transport != "scillm_app_server_turn_steer":
        raise ValueError("visible_subagent transport must be scillm_app_server_turn_steer")
    if transport == "scillm_app_server_turn_steer" and operation == "steer" and turn_type != "steering":
        raise ValueError("visible_subagent operation=steer requires turn_type=steering")
    if transport == "scillm_app_server_turn_steer" and operation == "launch" and turn_type == "steering":
        raise ValueError("visible_subagent turn_type=steering requires operation=steer")


def _validate_visible_identifier(name: str, value: str, source: str) -> None:
    if not VISIBLE_SUBAGENT_ID_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"visible_subagent {name} from {source} must be a safe identifier")


def _resolve_visible_subagent_id(name: str, route: dict) -> tuple[str, str]:
    route_value = str(route.get(name) or "").strip()
    env_name = f"ASK_VISIBLE_SUBAGENT_{name.upper()}"
    env_value = os.environ.get(env_name, "").strip()
    for source, value in (("route", route_value), ("environment", env_value)):
        if value:
            _validate_visible_identifier(name, value, source)
    if route_value and env_value and route_value != env_value:
        raise ValueError(f"visible_subagent {name} route/env conflict")
    if route_value:
        return route_value, "route"
    if env_value:
        return env_value, "environment"
    return "", ""


def _visible_subagent_thread_id() -> str:
    return os.environ.get("ASK_VISIBLE_SUBAGENT_THREAD_ID", "").strip()


def _safe_visible_fragment(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return cleaned or fallback


def _visible_tmux_session_name(route: dict) -> str:
    configured = os.environ.get("ASK_VISIBLE_SUBAGENT_TMUX_SESSION", "").strip()
    if configured:
        _validate_visible_identifier("tmux_session", configured, "environment")
        return configured
    persona = _safe_visible_fragment(str(route.get("persona") or "nico").lower(), "nico")
    project = _safe_visible_fragment(Path.cwd().name.lower().replace("_", "-"), "project")
    session = f"{persona}-{project}"
    _validate_visible_identifier("tmux_session", session, "route")
    return session


def _visible_tmux_binding_path(tmux_session: str) -> Path:
    digest = hashlib.sha256(str(Path.cwd()).encode("utf-8", errors="replace")).hexdigest()[:12]
    root = Path(os.environ.get(
        "ASK_VISIBLE_SUBAGENT_BINDING_ROOT",
        str(Path(tempfile.gettempdir()) / "ask-visible-subagents"),
    )).expanduser()
    return root / digest / f"{tmux_session}.json"


def _tmux_has_session(tmux_session: str) -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", tmux_session],
        capture_output=True,
        text=True,
    ).returncode == 0


def _write_visible_subagent_clean_viewer(visible_dir: Path) -> tuple[Path, Path]:
    cleaner = visible_dir / "clean-transcript.py"
    follower = visible_dir / "follow-clean-transcript.sh"
    cleaner.write_text(
        r'''#!/usr/bin/env python3
import re
import sys
from pathlib import Path

ansi = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")

def clean(text: str) -> str:
    text = ansi.sub("", text).replace("\r", "\n")
    lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.strip() in {"-", "│", "┃", "█", "▌"}:
            continue
        if len(line.strip()) == 1 and line.startswith(" " * max(0, len(line) - 1)):
            continue
        lines.append(line)
    return "\n".join(lines[-240:])

path = Path(sys.argv[1])
print(clean(path.read_text(errors="replace")) if path.exists() else "")
''',
        encoding="utf-8",
    )
    follower.write_text(
        r'''#!/usr/bin/env bash
set -euo pipefail
session_dir="$1"
transcript="$session_dir/transcript.log"
status="$session_dir/status.json"
commands="$session_dir/commands.jsonl"
cleaner="$(dirname "$0")/clean-transcript.py"
while true; do
  clear
  if [[ -f "$status" ]]; then
    jq -r '
      "Nico visible subagent",
      "transport: /ask -> subagent-runner -> Codex PTY",
      "status: \(.status)  pid=\(.pid // "unknown") watcher_pid=\(.watcher_pid // "unknown")",
      "session_dir: \(.artifact_dir // "")",
      "cwd: \(.cwd // "")",
      "command: " + ((.command // []) | join(" "))
    ' "$status" 2>/dev/null || true
  else
    echo "Nico visible subagent"
    echo "transport: /ask -> subagent-runner -> Codex PTY"
    echo "status: waiting for status.json"
  fi
  echo
  echo "Human attach: tmux a -t ${TMUX_SESSION_NAME:-nico}"
  echo "Project-agent input path: subagent-runner send-input <session_dir> '<message>'"
  echo
  echo "Project-agent inputs:"
  if [[ -s "$commands" ]]; then
    jq -r 'select(.action=="input") | "- " + (.text|tostring)' "$commands" 2>/dev/null | tail -8 || true
  else
    echo "- (none yet)"
  fi
  echo
  echo "Clean transcript:"
  python3 "$cleaner" "$transcript" 2>/dev/null || true
  sleep 1
done
''',
        encoding="utf-8",
    )
    cleaner.chmod(0o755)
    follower.chmod(0o755)
    return cleaner, follower


def _run_visible_subagent_tmux(
    *,
    question: str,
    route: dict,
    memory_items: list[dict],
    mentioned_skills: list[str],
    run_state: Optional[AskRunState],
    timeout: float,
    idle_timeout: float,
    model: str,
    reasoning: str,
) -> dict:
    """Launch or steer a human-visible tmux-backed subagent through /ask."""
    _validate_visible_subagent_route(route)
    persona = str(route.get("persona") or "Nico").strip() or "Nico"
    tmux_session = _visible_tmux_session_name(route)
    binding_path = _visible_tmux_binding_path(tmux_session)
    runner = Path(SUBAGENT_RUNNER)
    if not runner.exists():
        raise RuntimeError(f"subagent-runner not found: {runner}")

    if run_state:
        run_state.step_started(
            "visible_subagent_tmux",
            persona=persona,
            tmux_session=tmux_session,
        )

    existing_binding: dict = {}
    if binding_path.exists():
        try:
            existing_binding = json.loads(binding_path.read_text())
        except (OSError, json.JSONDecodeError):
            existing_binding = {}
    existing_session_dir = str(existing_binding.get("session_dir") or "")
    if existing_session_dir and Path(existing_session_dir).exists() and _tmux_has_session(tmux_session):
        send = subprocess.run(
            [str(runner), "send-input", existing_session_dir, question, "--source", "controller"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if send.returncode != 0:
            raise RuntimeError(f"visible subagent send-input failed: {send.stderr.strip()}")
        try:
            send_payload = json.loads(send.stdout)
        except json.JSONDecodeError:
            send_payload = {}
        delivery = {
            **existing_binding,
            "state": "running",
            "operation": "steer",
            "persona": persona,
            "transport": "subagent_runner_tmux",
            "input_id": send_payload.get("input_id", ""),
            "tmux_session": tmux_session,
            "attach_command": f"tmux a -t {tmux_session}",
            "send_input_command": f"{runner} send-input {existing_session_dir} '<message>'",
        }
        if run_state:
            run_state.add_artifacts({
                "visible_subagent_binding": binding_path,
                "visible_subagent_session": existing_session_dir,
                "visible_subagent_transcript": Path(existing_session_dir) / "transcript.log",
            })
            run_state.step_finished("visible_subagent_tmux", delivery_state="running", tmux_session=tmux_session)
        return delivery

    run_dir = Path(getattr(run_state, "run_dir", Path(tempfile.gettempdir()) / "ask-visible-subagent")).expanduser()
    visible_dir = run_dir / "visible-subagent"
    visible_dir.mkdir(parents=True, exist_ok=True)
    cleaner, follower = _write_visible_subagent_clean_viewer(visible_dir)
    prompt_file = visible_dir / f"{_safe_visible_fragment(persona.lower(), 'persona')}-prompt.md"
    spec_file = visible_dir / f"{_safe_visible_fragment(persona.lower(), 'persona')}-spec.json"
    output_dir = visible_dir / "sessions"
    memory_context = _visible_memory_context(memory_items)
    prompt_file.write_text(
        "\n".join([
            f"You are {persona}, a persistent visible subagent in a live project-agent/human collaboration.",
            "Stay in the session after answering. Ask clarifying questions when needed.",
            "The project agent will continue the conversation through /ask send-input, not through hidden manual fallback.",
            "The human may attach to the tmux session to watch the conversation.",
            "",
            f"Original trigger: {route.get('original_utterance', '')}",
            f"Turn type: {route.get('turn_type', 'advisory')}",
            f"Mentioned skills: {', '.join(mentioned_skills) if mentioned_skills else '(none)'}",
            "",
            "Memory context:",
            json.dumps(memory_context, indent=2, default=str),
            "",
            "Current project-agent message:",
            question,
        ]),
        encoding="utf-8",
    )
    command = [
        "bash",
        "-lc",
        (
            'codex --model "$ASK_VISIBLE_SUBAGENT_MODEL" '
            '-c "reasoning_effort=\\"$ASK_VISIBLE_SUBAGENT_REASONING\\"" '
            '--sandbox "$ASK_VISIBLE_SUBAGENT_CODEX_SANDBOX" '
            '--ask-for-approval never '
            '--no-alt-screen '
            '--cd "$ASK_VISIBLE_SUBAGENT_CWD" '
            '"$(cat "$ASK_VISIBLE_SUBAGENT_PROMPT_FILE")"'
        ),
    ]
    task_id = f"ask-visible-{_safe_visible_fragment(persona.lower(), 'persona')}-{int(time.time())}"
    spec = {
        "task_id": task_id,
        "title": f"/ask visible subagent {persona}",
        "prompt": "Persistent visible subagent prompt is stored in ASK_VISIBLE_SUBAGENT_PROMPT_FILE.",
        "backend": "codex",
        "command": command,
        "cwd": str(Path.cwd()),
        "output_dir": str(output_dir),
        "timeout_seconds": int(max(timeout, 300)),
        "idle_timeout_seconds": int(max(idle_timeout, 300)),
        "env": {
            "ASK_VISIBLE_SUBAGENT_MODEL": model,
            "ASK_VISIBLE_SUBAGENT_REASONING": reasoning,
            "ASK_VISIBLE_SUBAGENT_CODEX_SANDBOX": os.environ.get("ASK_VISIBLE_SUBAGENT_CODEX_SANDBOX", "read-only"),
            "ASK_VISIBLE_SUBAGENT_CWD": str(Path.cwd()),
            "ASK_VISIBLE_SUBAGENT_PROMPT_FILE": str(prompt_file),
        },
        "tags": ["ask", "visible-subagent", "persistent", "tmux", persona.lower()],
    }
    spec_file.write_text(json.dumps(spec, indent=2, default=str), encoding="utf-8")
    started = subprocess.run(
        [str(runner), "start", str(spec_file)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if started.returncode != 0:
        raise RuntimeError(f"visible subagent start failed: {started.stderr.strip()}")
    start_data = json.loads(started.stdout)
    session_dir = str(start_data["artifact_dir"])
    if _tmux_has_session(tmux_session):
        subprocess.run(["tmux", "kill-session", "-t", tmux_session], capture_output=True, text=True, timeout=10)
    tmux = subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            tmux_session,
            "-n",
            "nico-codex-live",
            f"TMUX_SESSION_NAME={tmux_session} {follower} {session_dir}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if tmux.returncode != 0:
        raise RuntimeError(f"visible subagent tmux attach failed: {tmux.stderr.strip()}")
    binding = {
        "persona": persona,
        "transport": "subagent_runner_tmux",
        "state": "running",
        "operation": "launch",
        "tmux_session": tmux_session,
        "session_dir": session_dir,
        "transcript": str(Path(session_dir) / "transcript.log"),
        "status": str(Path(session_dir) / "status.json"),
        "events": str(Path(session_dir) / "events.jsonl"),
        "spec": str(spec_file),
        "prompt": str(prompt_file),
        "clean_transcript": str(cleaner),
        "clean_follow_command": f"{follower} {session_dir}",
        "attach_command": f"tmux a -t {tmux_session}",
        "send_input_command": f"{runner} send-input {session_dir} '<message>'",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    binding_path.write_text(json.dumps(binding, indent=2, default=str), encoding="utf-8")
    if run_state:
        run_state.add_artifacts({
            "visible_subagent_binding": binding_path,
            "visible_subagent_session": session_dir,
            "visible_subagent_transcript": Path(session_dir) / "transcript.log",
            "visible_subagent_prompt": prompt_file,
            "visible_subagent_spec": spec_file,
            "visible_subagent_clean_transcript": cleaner,
            "visible_subagent_clean_follow": follower,
        })
        run_state.step_finished("visible_subagent_tmux", delivery_state="running", tmux_session=tmux_session)
    return binding


def _run_visible_subagent_scillm(
    *,
    question: str,
    route: dict,
    memory_items: list[dict],
    mentioned_skills: list[str],
    run_state: Optional[AskRunState],
    timeout: float,
) -> dict:
    """Launch or steer a visible subagent through scillm's Codex app-server agent API."""
    _validate_visible_subagent_route(route)
    ask_id = getattr(run_state, "ask_id", "") if run_state is not None else ""
    if run_state:
        worker_id = os.environ.get("ASK_VISIBLE_SUBAGENT_WORKER_ID", "").strip()
        if not worker_id:
            persona = str(route.get("persona") or "nico").strip().lower()
            worker_id = re.sub(r"[^a-z0-9_-]+", "-", persona).strip("-") or "nico"
        run_state.step_started(
            "visible_subagent_scillm",
            worker_id=worker_id,
            handoff_id=route.get("handoff_id"),
            turn_type=route.get("turn_type", "advisory"),
        )
    try:
        delivery = run_visible_subagent_turn(
            question=question,
            route=route,
            memory_items=memory_items,
            mentioned_skills=mentioned_skills,
            ask_id=ask_id,
            timeout=timeout,
        )
        if run_state:
            run_state.step_finished("visible_subagent_scillm", delivery_state=delivery.get("state", "delivered"))
        return delivery
    except Exception as exc:
        if run_state:
            run_state.step_finished("visible_subagent_scillm", error=f"{type(exc).__name__}: {exc}")
        raise




# ---------------------------------------------------------------------------
# Evidence-case fallback (Step 2b) — global default for found=false
# ---------------------------------------------------------------------------

import re as _re


def _is_direct_control_lookup(query: str) -> bool:
    """Detect if a query is a direct control/QRA ID lookup.

    Direct lookups (e.g. "SV-123", "AC-2(1)") just need a corpus search,
    not a full evidence case.
    """
    q = query.strip()
    # STIG/CCI/SRG IDs
    if _re.match(r'^(SV|V|CCI|SRG)-\d', q, _re.IGNORECASE):
        return True
    # NIST control IDs
    if _re.match(r'^[A-Z]{2}-\d', q):
        return True
    # Short lookup (< 5 words, no question mark)
    if len(q.split()) <= 4 and '?' not in q:
        return True
    return False


def _should_use_dogpile(question: str, mode: str) -> bool:
    if mode == "force":
        return True
    if mode == "off":
        return False
    return is_date_sensitive_question(question)


def _question_too_large_for_child_argv(question: str) -> bool:
    return len(question.encode("utf-8", errors="replace")) > 12000




def _record_ask_telemetry(
    result: dict,
    started_at: float,
    status: str,
    oracle_model: Optional[str],
    oracle_reasoning: str,
    oracle_backend: str,
    oracle_idle_timeout: float,
    oracle_heartbeat_interval: float,
    oracle_persona: Optional[str],
    oracle_peer: Optional[str],
    oracle_iterations: int,
) -> None:
    """Store ask execution telemetry in memory for future timeout policy."""
    finished_at = time.time()
    duration_ms = int((finished_at - started_at) * 1000)
    question = str(result.get("question", ""))
    document = {
        "_key": hashlib.sha256(f"{started_at}:{question}".encode()).hexdigest()[:32],
        "type": "ask_call",
        "ts": datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat(),
        "date": datetime.fromtimestamp(started_at, tz=timezone.utc).date().isoformat(),
        "question": question,
        "scope": result.get("scope", ""),
        "status": status,
        "duration_ms": duration_ms,
        "items_count": len(result.get("items", [])),
        "auto_learned": bool(result.get("auto_learned")),
        "hybrid_mode": bool(result.get("hybrid_mode")),
        "oracle_enabled": oracle_model is not None,
        "oracle_model": oracle_model or "",
        "oracle_reasoning": oracle_reasoning,
        "oracle_idle_timeout_seconds": oracle_idle_timeout,
        "oracle_heartbeat_interval_seconds": oracle_heartbeat_interval,
        "oracle_backend_requested": oracle_backend,
        "oracle_backend_served": result.get("oracle", {}).get("backend", ""),
        "oracle_model_served": result.get("oracle", {}).get("model_served", ""),
        "oracle_persona": oracle_persona or "",
        "oracle_peer": oracle_peer or "",
        "oracle_iterations_requested": oracle_iterations,
        "oracle_iterations_completed": result.get("oracle", {}).get("iterations_completed", 0),
        "deep_review_enabled": bool(result.get("deep_review")),
        "deep_review_verdict": result.get("deep_review", {}).get("verdict", ""),
        "deep_review_verifier_status": result.get("deep_review", {}).get("verifier_status", ""),
        "session_path": result.get("session_path", ""),
    }
    if result.get("error"):
        document["error"] = str(result["error"])[:1000]
    try:
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=5.0) as client:
            response = client.post(
                "/upsert",
                json={"collection": "ask_call_log", "documents": [document]},
            )
            response.raise_for_status()
    except Exception as exc:
        log.warning("Failed to store ask telemetry: %s", exc)
@app.command()
def main(
    question_parts: list[str] = typer.Argument(..., help="Question to ask. Supports: Brandon what should we do?"),
    scope: str = typer.Option(
        os.environ.get("ASK_DEFAULT_SCOPE", "ask"), help="Memory scope to query (default: ask)",
    ),
    k: int = typer.Option(5, help="Number of results (default: 5)"),
    bridges: bool = typer.Option(False, help="Also traverse bridge attributes"),
    raw: bool = typer.Option(False, help="Return raw memory results"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    image_generate: bool = typer.Option(False, "--image-generate", help="Generate image artifact(s) through scillm"),
    image_model: str = typer.Option("gpt-image-2", "--image-model", help="Image generation model"),
    image_size: str = typer.Option("auto", "--image-size", help="Image size, for example auto or 1024x1024"),
    image_quality: str = typer.Option("auto", "--image-quality", help="Image quality, for example auto, medium, or high"),
    image_count: int = typer.Option(1, "--image-count", help="Number of images to generate"),
    image_output: Optional[str] = typer.Option(None, "--image-output", help="Output file or directory for generated image(s)"),
    image_output_format: str = typer.Option("png", "--image-output-format", help="Image file format: png, jpeg, or webp"),
    image_timeout: float = typer.Option(300.0, "--image-timeout", help="Image generation timeout in seconds"),
    image_auth: str = typer.Option("codex-oauth", "--image-auth", help="Image backend auth: codex-oauth (default, OAuth) or api-key (scillm images endpoint)"),
    auto_learn: bool = typer.Option(False, help="Auto-discover and learn if no knowledge found"),
    collection: str = typer.Option("behavioral", help="Taxonomy collection for auto-learn (default: behavioral)"),
    hybrid: bool = typer.Option(False, help="Use hybrid RAG+QRA retrieval (separate collection queries)"),
    consult_personas: bool = typer.Option(False, help="Find and suggest relevant personas to consult"),
    persona_scope: str = typer.Option("personas", help="Scope to search for personas (default: personas)"),
    persona_id: Optional[str] = typer.Option(None, help="Persona identifier for session tracking (None for human)"),
    oracle: bool = typer.Option(False, help="Use scillm/Codex for final oracle synthesis"),
    oracle_backend: str = typer.Option(DEFAULT_ORACLE_BACKEND, help="Oracle backend: auto, scillm, subagent-runner"),
    oracle_model: str = typer.Option(DEFAULT_ORACLE_MODEL, help="Oracle synthesis model"),
    oracle_reasoning: Optional[str] = typer.Option(
        None,
        help="Oracle reasoning effort (default: high; deep-review default: xhigh)",
    ),
    oracle_timeout: float = typer.Option(DEFAULT_ORACLE_TIMEOUT, help="Oracle HTTP timeout in seconds"),
    oracle_idle_timeout: float = typer.Option(DEFAULT_ORACLE_IDLE_TIMEOUT, help="Oracle subagent idle timeout in seconds"),
    oracle_heartbeat_interval: float = typer.Option(DEFAULT_ORACLE_HEARTBEAT_INTERVAL, help="Oracle heartbeat memory write interval in seconds"),
    oracle_persona: Optional[str] = typer.Option(None, help="Persona/subagent perspective for oracle synthesis"),
    oracle_peer: Optional[str] = typer.Option(None, help="Second persona/subagent for oracle deliberation"),
    oracle_persona_model: Optional[str] = typer.Option(None, help="Model for primary persona turns"),
    oracle_peer_model: Optional[str] = typer.Option(None, help="Model for peer persona turns"),
    oracle_iterations: int = typer.Option(1, help="Number of sequential oracle deliberation calls"),
    oracle_image_paths: Optional[list[str]] = typer.Option(None, "--oracle-image", help="Image file to attach to direct scillm oracle calls (repeatable)"),
    roundtable: bool = typer.Option(False, help="Run a sequential protocolized persona roundtable"),
    roundtable_personas: Optional[str] = typer.Option(None, help="Comma-separated persona[:protocol_role] participants"),
    roundtable_role_preset: str = typer.Option("adversarial-review", help="Roundtable role preset"),
    roundtable_rounds: int = typer.Option(2, help="Number of roundtable rounds"),
    roundtable_mode: str = typer.Option("adversarial", help="Roundtable mode label"),
    roundtable_persist: str = typer.Option("summary", help="Roundtable persistence: summary or full"),
    argue: bool = typer.Option(False, "--argue", help="Run two parallel /scillm advocates followed by a judge"),
    decision_required: bool = typer.Option(False, "--decision-required", help="Force a FOR/AGAINST argue verdict with explicit uncertainty"),
    tie_breaker: Optional[str] = typer.Option(None, "--tie-breaker", help="Tie-breaker for --decision-required"),
    parallel_review: bool = typer.Option(False, help="Run independent parallel adversarial reviewers"),
    parallel_reviewers: int = typer.Option(3, help="Number of default parallel reviewers"),
    parallel_review_personas: Optional[str] = typer.Option(None, help="Comma-separated reviewer persona[:protocol_role] specs"),
    parallel_review_focus: Optional[str] = typer.Option(None, help="Comma-separated reviewer focus labels"),
    parallel_review_role_preset: str = typer.Option("adversarial-review", help="Parallel reviewer role preset"),
    review_target: Optional[str] = typer.Option(None, "--review-target", help="Explicit parallel-review target: git:diff, paths, artifact, or manifest"),
    parallel_review_runner: str = typer.Option("scillm", "--parallel-review-runner", help="Parallel review runner adapter: scillm"),
    review_dag: str = typer.Option("hybrid", "--review-dag", help="Review DAG mode: judge-best or hybrid"),
    read_only_review: bool = typer.Option(True, "--read-only/--allow-edits", help="Keep parallel review read-only"),
    code_runner_handoff: bool = typer.Option(False, "--code-runner-handoff", help="Emit /code-runner handoff artifact for actionable findings"),
    implement_with: Optional[str] = typer.Option(None, "--implement-with", help="Implementation backend: code-runner (handoff) or scillm-agent (standing worker)"),
    apply_fixes: bool = typer.Option(False, "--apply-fixes", help="Explicitly request code-runner implementation intent; /ask prepares artifacts but does not edit"),
    code_runner_allowed_files: Optional[list[str]] = typer.Option(None, "--code-runner-allowed-file", help="Allowed file for code-runner task (repeatable)"),
    code_runner_dod_commands: Optional[list[str]] = typer.Option(None, "--code-runner-dod-command", help="Definition-of-done command for code-runner task (repeatable)"),
    implementation_non_goals: Optional[list[str]] = typer.Option(None, "--implementation-non-goal", help="Non-goal for code-runner task (repeatable)"),
    implementation_risk_notes: Optional[list[str]] = typer.Option(None, "--implementation-risk-note", help="Risk note for code-runner task (repeatable)"),
    dogpile_mode: str = typer.Option("auto", "--dogpile", help="Freshness policy: auto, off, or force"),
    deep_review: bool = typer.Option(False, help="Run first-class deep review with markdown and JSON artifacts"),
    deep_review_target: Optional[str] = typer.Option(None, help="Explicit review target: paths, diff, plan, manifest, or artifact"),
    deep_review_profile: str = typer.Option("max_available", help="Deep-review profile label"),
    deep_reviewers: int = typer.Option(5, help="Reviewer breadth requested for deep review"),
    deep_review_focus: Optional[str] = typer.Option(None, help="Comma-separated deep-review focus labels"),
    deep_review_fallback_policy: str = typer.Option("fail_closed", help="Deep-review downgrade policy: fail_closed or warn"),
    deep_review_persist: str = typer.Option("summary", help="Deep-review persistence: summary or full"),
    deep_review_output_root: str = typer.Option(".ask_artifacts/deep-review", help="Deep-review artifact directory"),
    cae_gap_review: bool = typer.Option(False, "--cae-gap-review", help="Run evidence-case-backed CAE reviewer/judge loop"),
    cae_reviewers: Optional[str] = typer.Option(None, "--cae-reviewers", help="Comma-separated persona:role CAE reviewers"),
    cae_judge: str = typer.Option(DEFAULT_CAE_JUDGE, "--cae-judge", help="CAE judge persona label"),
    cae_max_rounds: int = typer.Option(3, "--cae-max-rounds", help="Maximum CAE clarify/reroute rounds"),
    review_context: str = typer.Option("fresh", "--review-context", help="Context policy: fresh or inherited"),
    inherit_memory: str = typer.Option("summary", "--inherit-memory", help="Context policy memory inheritance: none, summary, or full"),
    inherit_skills: str = typer.Option("selected", "--inherit-skills", help="Context policy skill inheritance: none, selected, or all"),
    inherit_project_context: str = typer.Option("no", "--inherit-project-context", help="Context policy project inheritance: no, summary, or full"),
    chain: Optional[str] = typer.Option(None, "--chain", help="Saved review chain spec name or path"),
    reviewer_specs: Optional[list[str]] = typer.Option(None, "--reviewer-spec", help="Reviewer spec name or path (repeatable)"),
    orchestrate: bool = typer.Option(False, "--orchestrate", help="Draft and execute an ask DAG from the natural-language request"),
    agent_worker: Optional[str] = typer.Option(None, "--agent-worker", help="scillm implementation worker_id for coding DAG nodes"),
    dag_json: str = typer.Option("", "--dag-json", help="Inline ask/scillm-style DAG JSON document to execute before synthesis"),
    dag_file: str = typer.Option("", "--dag-file", help="Path to an ask/scillm-style DAG JSON document to execute before synthesis"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview execution spec and risk analysis without mutation"),
    delegate_dry_run: bool = typer.Option(False, "--delegate-dry-run", help="Resolve explicit delegate syntax and write an envelope without executing a runtime"),
    ask_id: Optional[str] = typer.Option(None, "--ask-id", help="Stable runtime artifact id for this ask call"),
    run_output_root: Optional[str] = typer.Option(None, "--run-output-root", help="Directory for ask runtime artifacts"),
    overwrite_run: bool = typer.Option(False, "--overwrite", help="Replace an existing run directory for --ask-id"),
    resume_run: bool = typer.Option(False, "--resume", help="Resume a non-terminal existing run directory for --ask-id"),
    webgpt_tab_id: str = typer.Option("", "--webgpt-tab-id", help="Deprecated. WebGPT/ChatGPT routing has been removed from /ask and this option fails closed."),
    webgpt_url: str = typer.Option("", "--webgpt-url", help="Deprecated. WebGPT/ChatGPT routing has been removed from /ask and this option fails closed."),
    webgpt_create_tab: bool = typer.Option(False, "--webgpt-create-tab", help="Deprecated. WebGPT/ChatGPT routing has been removed from /ask and this option fails closed."),
    webgpt_project: str = typer.Option("", "--webgpt-project", help="Deprecated. WebGPT/ChatGPT routing has been removed from /ask and this option fails closed."),
    browser_oracle_from: str = typer.Option("", "--browser-oracle-from", help="Directory for $browser-oracle walk-up (.ask/browser-oracles.yaml) for supported browser backends."),
    cursor_browser_view_id: str = typer.Option("", "--cursor-browser-view-id", help="Cursor Browser viewId for --oracle-backend cursor-browser (from browser_tabs; NOT a Chrome tab id)."),
    cursor_browser_url: str = typer.Option("", "--cursor-browser-url", help="ChatGPT URL to resolve in Cursor Browser for --oracle-backend cursor-browser."),
    cursor_browser_project: str = typer.Option("", "--cursor-browser-project", help="Bind to ~/.pi/cursor-browser-projects/<name>.json (stores viewId)."),
    webgpt_once: bool = typer.Option(
        False,
        "--once",
        help="Deprecated WebGPT-only flag. Fails closed when provided.",
    ),
    gemini_tab_id: str = typer.Option("", "--gemini-tab-id", help="Chrome tab id to control for --oracle-backend webgemini. Optional: auto-resolved from a single open gemini.google.com tab."),
    gemini_url: str = typer.Option("", "--gemini-url", help="Gemini conversation URL to resolve to an open Chrome tab for --oracle-backend webgemini."),
    kimi_tab_id: str = typer.Option("", "--kimi-tab-id", help="Chrome tab id to control for --oracle-backend webkimi. Optional: auto-resolved from a single open kimi.ai tab."),
    kimi_url: str = typer.Option("", "--kimi-url", help="Kimi conversation URL to resolve to an open Chrome tab for --oracle-backend webkimi."),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    original_utterance = " ".join(part for part in question_parts)
    stdin_question = False
    if len(question_parts) == 1 and question_parts[0] == "-":
        stdin_question = sys.stdin.read()
        if not stdin_question.strip():
            raise typer.BadParameter("stdin question is empty", param_hint="question")
        question_parts = [stdin_question]
        stdin_question = True

    missing_persona_attention: dict | None = None
    model_alias_route: ModelAliasRoute | None = None
    explicit_oracle = oracle
    try:
        model_alias_route = resolve_model_alias_route(
            question_parts,
            scillm_base_url=SCILLM_BASE_URL,
            scillm_api_key=SCILLM_API_KEY,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="question") from exc
    if model_alias_route:
        question_parts = model_alias_route.question_parts
        oracle = True
        oracle_backend = model_alias_route.oracle_backend
        oracle_model = model_alias_route.resolved_model

    if any([oracle_backend == "webgpt", webgpt_tab_id, webgpt_url, webgpt_create_tab, webgpt_project, webgpt_once]):
        raise typer.BadParameter(
            WEBGPT_DEPRECATION_MESSAGE,
            param_hint="--oracle-backend",
        )

    explicit_webgpt_oracle = False

    visible_subagent_route: dict | None = None
    dag_orchestration_attention: dict | None = None
    ask_dag: dict | None = None
    try:
        ask_dag = load_ask_dag(dag_json=dag_json, dag_file=dag_file)
    except AskDagError as exc:
        raise typer.BadParameter(str(exc), param_hint="--dag-json") from exc

    question, inferred_cae_gap_review = _parse_natural_cae_gap_review_query(question_parts)
    if stdin_question:
        inferred_cae_gap_review = False
    if explicit_oracle:
        inferred_cae_gap_review = False
    if inferred_cae_gap_review:
        cae_gap_review = True
        oracle = True
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "subagent-runner"

    routed_question_parts = [question] if inferred_cae_gap_review else question_parts
    question, inferred_parallel_review, inferred_parallel_reviewers, inferred_parallel_focus = (
        _parse_natural_parallel_review_query(routed_question_parts)
    )
    if stdin_question:
        inferred_parallel_review = False
        inferred_parallel_reviewers = None
        inferred_parallel_focus = None
    if inferred_parallel_review and not explicit_oracle:
        parallel_review = True
        oracle = True
        if inferred_parallel_reviewers is not None:
            parallel_reviewers = inferred_parallel_reviewers
        if inferred_parallel_focus and not parallel_review_focus:
            parallel_review_focus = inferred_parallel_focus
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "subagent-runner"

    argue_question_parts = [question] if (inferred_parallel_review or inferred_cae_gap_review) else question_parts
    question, inferred_argue = _parse_natural_argue_query(argue_question_parts)
    if stdin_question:
        inferred_argue = False
    if inferred_argue:
        argue = True
        oracle = True
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "scillm"

    roundtable_question_parts = [question] if (inferred_parallel_review or inferred_argue or inferred_cae_gap_review) else question_parts
    question, inferred_roundtable_personas, inferred_roundtable = _parse_natural_roundtable_query(roundtable_question_parts)
    if stdin_question:
        inferred_roundtable_personas = None
        inferred_roundtable = False
    if inferred_roundtable:
        roundtable = True
        oracle = True
        if not roundtable_personas:
            roundtable_personas = inferred_roundtable_personas
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "subagent-runner"
    elif not roundtable and not stdin_question:
        missing_topic, missing_personas = _parse_missing_persona_roundtable_query(roundtable_question_parts)
        if missing_personas:
            question = missing_topic
            missing_persona_attention = {
                "reason": "missing_roundtable_personas",
                "question": (
                    "The prompt names roundtable participants that do not resolve to stored personas: "
                    + ", ".join(missing_personas)
                    + "."
                ),
                "safe_default": "clarify_before_roundtable",
                "resume_hint": (
                    "Choose one path: use generic protocol roles, select existing personas, "
                    "or create the missing personas with /interview and /create-persona before rerunning."
                ),
                "missing_personas": missing_personas,
                "clarification_options": [
                    "Use generic protocol roles for this one review without stored persona profiles.",
                    "Select existing stored personas to stand in for these roles.",
                    "Create the missing personas through /interview and /create-persona.",
                    "Cancel the roundtable until persona identities are explicit.",
                ],
                "suggested_skills": ["/interview", "/create-persona"],
            }

    persona_question_parts = [question] if (inferred_roundtable or inferred_parallel_review or inferred_argue or inferred_cae_gap_review) else question_parts
    if not stdin_question and not any([roundtable, parallel_review, argue, cae_gap_review, deep_review]):
        (
            visible_question,
            visible_persona,
            visible_trigger,
            visible_turn_type,
            inferred_visible_subagent,
        ) = _parse_natural_visible_subagent_query(
            persona_question_parts,
            explicit_persona=oracle_persona,
        )
        if inferred_visible_subagent:
            question = visible_question
            oracle_persona = visible_persona
            oracle = True
            if oracle_backend == DEFAULT_ORACLE_BACKEND:
                oracle_backend = "scillm"
            elif oracle_backend != "scillm":
                raise typer.BadParameter(
                    "Visible subagent conversation requires the scillm Codex App Server transport; "
                    "tmux/send-keys fallbacks are not allowed.",
                    param_hint="--oracle-backend",
                )
            visible_subagent_route = {
                "mode": "visible_subagent",
                "persona": visible_persona,
                "visibility": "human_project_conversation",
                "turn_type": visible_turn_type,
                "operation": "steer" if visible_turn_type == "steering" else "launch",
                "memory_first": True,
                "transport": "scillm_app_server_turn_steer",
                "trigger_phrase": visible_trigger,
                "original_utterance": original_utterance,
            }
            persona_question_parts = [question]
    question, inferred_persona, inferred_peer, inferred_oracle = _parse_natural_persona_query(
        persona_question_parts,
        explicit_persona=oracle_persona,
    )
    if stdin_question:
        inferred_persona = None
        inferred_peer = None
        inferred_oracle = False
    if inferred_persona:
        oracle_persona = inferred_persona
    if inferred_peer and not oracle_peer:
        oracle_peer = inferred_peer
        if oracle_iterations == 1:
            oracle_iterations = 2
    if inferred_oracle:
        oracle = True
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "subagent-runner"
    elif not image_generate and not oracle and not raw and not stdin_question and _should_auto_oracle_persona(question):
        oracle = True
        consult_personas = True
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "subagent-runner"
    if roundtable or parallel_review or argue or cae_gap_review:
        oracle = True
        if argue:
            oracle_backend = "scillm"
        elif oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "subagent-runner"

    if chain:
        chain_options = apply_chain_options({
            "deep_review": deep_review,
            "parallel_review": parallel_review,
            "parallel_reviewers": parallel_reviewers,
            "deep_reviewers": deep_reviewers,
            "deep_review_focus": deep_review_focus,
            "parallel_review_focus": parallel_review_focus,
            "oracle_backend": oracle_backend,
            "oracle_reasoning": oracle_reasoning,
        }, chain)
        deep_review = bool(chain_options.get("deep_review", deep_review))
        parallel_review = bool(chain_options.get("parallel_review", parallel_review))
        parallel_reviewers = int(chain_options.get("parallel_reviewers", parallel_reviewers))
        deep_reviewers = int(chain_options.get("deep_reviewers", deep_reviewers))
        deep_review_focus = chain_options.get("deep_review_focus", deep_review_focus)
        parallel_review_focus = chain_options.get("parallel_review_focus", parallel_review_focus)
        oracle_backend = str(chain_options.get("oracle_backend", oracle_backend))
        oracle_reasoning = chain_options.get("oracle_reasoning", oracle_reasoning)

    loaded_reviewer_specs = load_selected_reviewer_specs(reviewer_specs)
    reviewer_focus = focus_from_reviewer_specs(loaded_reviewer_specs)
    if reviewer_focus:
        deep_review_focus = ",".join(filter(None, [deep_review_focus, reviewer_focus]))
        parallel_review_focus = ",".join(filter(None, [parallel_review_focus, reviewer_focus]))

    if deep_review or (not image_generate and not oracle and infer_deep_review(question)):
        deep_review = True
        oracle = True
        parallel_review = True
        parallel_reviewers = max(parallel_reviewers, deep_reviewers)
        if deep_review_focus and not parallel_review_focus:
            parallel_review_focus = deep_review_focus
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "scillm"
        if oracle_reasoning is None:
            oracle_reasoning = "xhigh"

    if oracle_reasoning is None:
        oracle_reasoning = DEFAULT_ORACLE_REASONING

    if debug:
        log.enable("")
    if oracle_backend not in ORACLE_BACKENDS:
        raise typer.BadParameter(
            f"Unknown oracle backend '{oracle_backend}'. Use one of: {', '.join(sorted(ORACLE_BACKENDS))}.",
            param_hint="--oracle-backend",
        )
    if dogpile_mode not in {"auto", "off", "force"}:
        raise typer.BadParameter(
            "Dogpile mode must be one of: auto, off, force.",
            param_hint="--dogpile",
        )
    if image_count < 1:
        raise typer.BadParameter(
            "Image count must be >= 1.",
            param_hint="--image-count",
        )
    if image_generate and any([
        raw,
        oracle,
        auto_learn,
        hybrid,
        consult_personas,
        roundtable,
        argue,
        parallel_review,
        deep_review,
        cae_gap_review,
    ]):
        raise typer.BadParameter(
            "--image-generate is a standalone artifact-generation mode. Remove memory, oracle, and review options.",
            param_hint="--image-generate",
        )
    if roundtable_persist not in {"summary", "full"}:
        raise typer.BadParameter(
            "Roundtable persistence must be summary or full.",
            param_hint="--roundtable-persist",
        )
    if deep_review_fallback_policy not in {"fail_closed", "warn"}:
        raise typer.BadParameter(
            "Deep-review fallback policy must be fail_closed or warn.",
            param_hint="--deep-review-fallback-policy",
        )
    if deep_review_persist not in {"summary", "full"}:
        raise typer.BadParameter(
            "Deep-review persistence must be summary or full.",
            param_hint="--deep-review-persist",
        )
    if review_context not in {"fresh", "inherited"}:
        raise typer.BadParameter(
            "Review context must be fresh or inherited.",
            param_hint="--review-context",
        )
    if inherit_memory not in {"none", "summary", "full"}:
        raise typer.BadParameter(
            "Memory inheritance must be none, summary, or full.",
            param_hint="--inherit-memory",
        )
    if inherit_skills not in {"none", "selected", "all"}:
        raise typer.BadParameter(
            "Skill inheritance must be none, selected, or all.",
            param_hint="--inherit-skills",
        )
    if inherit_project_context not in {"no", "summary", "full"}:
        raise typer.BadParameter(
            "Project context inheritance must be no, summary, or full.",
            param_hint="--inherit-project-context",
        )
    if oracle and raw:
        raise typer.BadParameter(
            "Oracle synthesis needs retrieved context. Remove --raw, or run without --oracle.",
            param_hint="--raw",
        )
    if oracle and oracle_iterations < 1:
        raise typer.BadParameter(
            "Oracle iterations must be >= 1.",
            param_hint="--oracle-iterations",
        )
    if roundtable and roundtable_rounds < 1:
        raise typer.BadParameter(
            "Roundtable rounds must be >= 1.",
            param_hint="--roundtable-rounds",
        )
    if tie_breaker and not decision_required:
        raise typer.BadParameter(
            "--tie-breaker only applies with --decision-required.",
            param_hint="--tie-breaker",
        )
    if decision_required and not tie_breaker:
        raise typer.BadParameter(
            "--decision-required requires --tie-breaker.",
            param_hint="--tie-breaker",
        )
    if tie_breaker and tie_breaker not in ARGUE_TIE_BREAKERS:
        raise typer.BadParameter(
            f"Tie-breaker must be one of: {', '.join(sorted(ARGUE_TIE_BREAKERS))}.",
            param_hint="--tie-breaker",
        )
    if parallel_review and parallel_reviewers < 1:
        raise typer.BadParameter(
            "Parallel reviewers must be >= 1.",
            param_hint="--parallel-reviewers",
        )
    if parallel_review and parallel_reviewers > MAX_REVIEWERS:
        raise typer.BadParameter(
            f"Parallel reviewers must be <= {MAX_REVIEWERS}.",
            param_hint="--parallel-reviewers",
        )
    if parallel_review and parallel_review_runner != "scillm":
        raise typer.BadParameter(
            "Only the scillm parallel-review runner is implemented.",
            param_hint="--parallel-review-runner",
        )
    if parallel_review and review_dag not in {"judge-best", "hybrid"}:
        raise typer.BadParameter(
            "Review DAG must be judge-best or hybrid.",
            param_hint="--review-dag",
        )
    if cae_gap_review and cae_max_rounds < 1:
        raise typer.BadParameter(
            "CAE max rounds must be >= 1.",
            param_hint="--cae-max-rounds",
        )
    if implement_with and implement_with not in {"code-runner", "scillm-agent"}:
        raise typer.BadParameter(
            "Only --implement-with code-runner or scillm-agent is supported.",
            param_hint="--implement-with",
        )
    if apply_fixes:
        implement_with = implement_with or "code-runner"
    if implement_with:
        code_runner_handoff = True
    if any([
        code_runner_handoff,
        implement_with,
        apply_fixes,
        code_runner_allowed_files,
        code_runner_dod_commands,
        implementation_non_goals,
        implementation_risk_notes,
    ]) and not parallel_review:
        raise typer.BadParameter(
            "Implementation handoff options require --parallel-review.",
            param_hint="--parallel-review",
        )
    if code_runner_allowed_files:
        try:
            validate_code_runner_allowed_files(code_runner_allowed_files, Path.cwd())
        except ParallelReviewError as exc:
            raise typer.BadParameter(str(exc), param_hint="--code-runner-allowed-file") from exc
    if deep_review and deep_reviewers < 1:
        raise typer.BadParameter(
            "Deep-review reviewers must be >= 1.",
            param_hint="--deep-reviewers",
        )
    if overwrite_run and resume_run:
        raise typer.BadParameter(
            "Use either --overwrite or --resume, not both.",
            param_hint="--overwrite",
        )
    if oracle and oracle_idle_timeout < 30:
        raise typer.BadParameter(
            "Oracle idle timeout must be >= 30 seconds.",
            param_hint="--oracle-idle-timeout",
        )
    if oracle and oracle_heartbeat_interval < 5:
        raise typer.BadParameter(
            "Oracle heartbeat interval must be >= 5 seconds.",
            param_hint="--oracle-heartbeat-interval",
        )
    if not oracle and any([
        oracle_persona,
        oracle_peer,
        oracle_persona_model,
        oracle_peer_model,
        bool(oracle_image_paths),
        roundtable,
        roundtable_personas,
        argue,
        parallel_review,
        parallel_review_personas,
        cae_gap_review,
        cae_reviewers,
        oracle_backend != DEFAULT_ORACLE_BACKEND,
        oracle_idle_timeout != DEFAULT_ORACLE_IDLE_TIMEOUT,
        oracle_heartbeat_interval != DEFAULT_ORACLE_HEARTBEAT_INTERVAL,
    ]):
        raise typer.BadParameter(
            "Oracle-specific options require --oracle.",
            param_hint="--oracle",
        )

    run_id = ask_id or make_run_id(question)
    mentioned_skills = _extract_skill_mentions(original_utterance)
    should_draft_dag = (
        orchestrate or (not ask_dag and should_orchestrate_from_text(original_utterance))
    ) and not visible_subagent_route and not parallel_review and not delegate_dry_run
    if should_draft_dag and not ask_dag:
        try:
            ask_dag = draft_ask_dag_from_question(
                question,
                scope=scope,
                mentioned_skills=mentioned_skills,
                agent_worker_id=agent_worker,
                default_oracle_model=oracle_model,
            )
        except AskDagError as exc:
            dag_orchestration_attention = natural_language_dag_attention(exc)
    if visible_subagent_route and run_output_root is None:
        run_output_root = ".ask_artifacts/visible-subagent"
    context_policy = build_context_policy(
        (
            "image-generation"
            if image_generate
            else "deep-review" if deep_review else "cae-gap-review" if cae_gap_review else "argue" if argue else "ask"
        ),
        review_context=review_context,
        inherit_memory=inherit_memory,
        inherit_skills=inherit_skills,
        inherit_project_context=inherit_project_context,
    )
    request_payload = {
        "command": "ask",
        "original_utterance": original_utterance,
        "question": question,
        "scope": scope,
        "k": k,
        "bridges": bridges,
        "raw": raw,
        "image_generate": image_generate,
        "image_model": image_model if image_generate else None,
        "image_size": image_size if image_generate else None,
        "image_quality": image_quality if image_generate else None,
        "image_count": image_count if image_generate else None,
        "image_output": image_output if image_generate else None,
        "image_output_format": image_output_format if image_generate else None,
        "image_timeout": image_timeout if image_generate else None,
        "auto_learn": auto_learn,
        "collection": collection,
        "hybrid": hybrid,
        "consult_personas": consult_personas,
        "persona_scope": persona_scope,
        "persona_id": persona_id,
        "oracle": oracle,
        "oracle_backend": oracle_backend,
        "oracle_model": oracle_model if oracle else None,
        "oracle_model_alias": model_alias_route.as_dict() if model_alias_route else None,
        "oracle_reasoning": oracle_reasoning,
        "oracle_timeout": oracle_timeout,
        "oracle_idle_timeout": oracle_idle_timeout,
        "oracle_heartbeat_interval": oracle_heartbeat_interval,
        "oracle_persona": oracle_persona,
        "oracle_peer": oracle_peer,
        "oracle_image_paths": oracle_image_paths or [],
        "oracle_iterations": oracle_iterations,
        "roundtable": roundtable,
        "roundtable_personas": roundtable_personas,
        "argue": argue,
        "decision_required": decision_required,
        "tie_breaker": tie_breaker,
        "parallel_review": parallel_review,
        "parallel_reviewers": parallel_reviewers,
        "parallel_review_personas": parallel_review_personas,
        "parallel_review_focus": parallel_review_focus,
        "review_target": review_target,
        "parallel_review_runner": parallel_review_runner,
        "review_dag": review_dag,
        "read_only_review": read_only_review,
        "code_runner_handoff": code_runner_handoff,
        "implement_with": implement_with,
        "apply_fixes": apply_fixes,
        "code_runner_allowed_files": code_runner_allowed_files or [],
        "code_runner_dod_commands": code_runner_dod_commands or [],
        "implementation_non_goals": implementation_non_goals or [],
        "implementation_risk_notes": implementation_risk_notes or [],
        "dogpile_mode": dogpile_mode,
        "deep_review": deep_review,
        "deep_review_target": deep_review_target,
        "deep_review_profile": deep_review_profile,
        "deep_reviewers": deep_reviewers,
        "deep_review_focus": deep_review_focus,
        "deep_review_output_root": deep_review_output_root,
        "cae_gap_review": cae_gap_review,
        "cae_reviewers": cae_reviewers or DEFAULT_CAE_REVIEWERS if cae_gap_review else None,
        "cae_judge": cae_judge,
        "cae_max_rounds": cae_max_rounds,
        "context_policy": context_policy,
        "ask_dag": dag_dry_run_summary(ask_dag),
        "chain": chain,
        "reviewer_specs": reviewer_specs or [],
        "orchestrate": should_draft_dag,
        "agent_worker": agent_worker,
        "suggested_personas_count": 0,
        "mentioned_skills": mentioned_skills,
        "visible_subagent": visible_subagent_route,
        "delegate_dry_run": delegate_dry_run,
    }
    delegate_envelope: dict | None = None
    delegate_attention: dict | None = None
    if delegate_dry_run:
        try:
            registry = load_delegate_registry(Path(__file__).resolve().parents[4])
            delegate_envelope = resolve_delegate_invocation(original_utterance, registry, request_id=run_id)
            request_payload["delegate"] = delegate_envelope
        except DelegateError as exc:
            delegate_attention = exc.as_needs_attention()
            request_payload["delegate_error"] = delegate_attention
    if missing_persona_attention:
        request_payload["missing_persona_clarification"] = missing_persona_attention
    if dag_orchestration_attention:
        request_payload["dag_orchestration_clarification"] = dag_orchestration_attention
    route_decision = _build_route_decision(request_payload, live_selected_lane=not dry_run)
    request_payload["route_decision"] = route_decision
    if dry_run:
        print_execution_spec(build_ask_dry_run_spec(request_payload), as_json=as_json)
        raise typer.Exit(code=0)

    suggested_personas: list[dict] = []
    if consult_personas:
        bridges_for_personas = extract_bridges(question)
        suggested_personas = find_relevant_personas(
            question,
            bridges=bridges_for_personas,
            scope=persona_scope,
        )
        request_payload["suggested_personas_count"] = len(suggested_personas)

    require_runtime_artifacts = image_generate or bool(oracle_image_paths) or bool(ask_dag) or deep_review or parallel_review or argue or cae_gap_review
    try:
        run_state = AskRunState(run_id, output_root=run_output_root, overwrite=overwrite_run, resume=resume_run)
        run_state.write_request(request_payload)
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(
            f"{exc}. Use a unique --ask-id, --overwrite, or --resume.",
            param_hint="--ask-id",
        ) from exc
    except OSError as exc:
        if require_runtime_artifacts:
            raise
        typer.echo(f"Warning: Runtime artifacts disabled: {exc}", err=True)
        run_state = NoopRunState(run_id, reason=str(exc))
    run_state.event("ask_started")
    run_state.event("route_decision", route_decision=route_decision)
    run_state.update("running", route_decision=route_decision)
    if route_decision.get("unavailable_lane_reasons"):
        first_reason = route_decision["unavailable_lane_reasons"][0]
        attention = run_state.needs_attention(
            reason="selected_oracle_lane_unavailable",
            question=f"Selected oracle lane is not available: {first_reason.get('lane')}",
            safe_default=str(first_reason.get("safe_default") or "do_not_route_to_lane"),
            resume_hint="Run ./run.sh doctor --json, fix the selected lane, or choose a different --oracle-backend.",
            route_decision=route_decision,
            unavailable_lane_reasons=route_decision["unavailable_lane_reasons"],
        )
        result = {
            "question": question,
            "scope": scope,
            "items": [],
            "bridges_found": [],
            "answer": "",
            "auto_learned": False,
            "hybrid_mode": hybrid,
            "needs_attention": attention,
            "ask_id": run_state.ask_id,
            "runtime_artifacts": run_state.artifacts,
            "route_decision": route_decision,
        }
        run_state.finish(result, state="needs_attention")
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print("\n-- /ask needs attention --")
            print(f"   Reason: {attention.get('reason', 'unknown')}")
            print(f"   Question: {attention.get('question', '')}")
            if attention.get("resume_hint"):
                print(f"   Resume: {attention['resume_hint']}")
            print()
        raise typer.Exit(code=2)
    if visible_subagent_route:
        run_state.event(
            "visible_subagent_route",
            visible_subagent=visible_subagent_route,
            mentioned_skills=mentioned_skills,
        )

    if delegate_dry_run:
        if delegate_attention:
            attention = run_state.needs_attention(**delegate_attention)
            result = {
                "question": question,
                "scope": scope,
                "items": [],
                "bridges_found": [],
                "answer": "",
                "auto_learned": False,
                "hybrid_mode": hybrid,
                "delegate": None,
                "needs_attention": attention,
                "ask_id": run_state.ask_id,
                "runtime_artifacts": run_state.artifacts,
                "route_decision": route_decision,
            }
            run_state.finish(result, state="needs_attention")
            if as_json:
                print(json.dumps(result, indent=2, default=str))
            else:
                print("\n-- /ask delegate needs attention --")
                print(f"   Reason: {attention.get('reason', 'unknown')}")
                print(f"   Question: {attention.get('question', '')}")
                if attention.get("resume_hint"):
                    print(f"   Resume: {attention['resume_hint']}")
                print()
            raise typer.Exit(code=2)
        result = {
            "question": question,
            "scope": scope,
            "items": [],
            "bridges_found": [],
            "answer": "Delegate envelope resolved. No runtime executed.",
            "auto_learned": False,
            "hybrid_mode": hybrid,
            "delegate": delegate_envelope,
            "ask_id": run_state.ask_id,
            "runtime_artifacts": run_state.artifacts,
            "route_decision": route_decision,
        }
        run_state.event("delegate_resolved", delegate=delegate_envelope)
        run_state.finish(result, state="completed")
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print("\n-- /ask delegate dry run --")
            print(f"   Actor: {delegate_envelope['actor']['id']} ({delegate_envelope['actor']['kind']})")
            print(f"   Mode: {delegate_envelope['mode']}")
            print(f"   Runtime: {delegate_envelope['runtime']['selected']}")
            print(f"   Status: {run_state.artifacts.get('status')}")
            print()
        raise typer.Exit(code=0)

    if image_generate:
        try:
            if str(image_auth).strip().lower() in {"codex-oauth", "oauth", "codex"}:
                result = generate_image_with_codex_oauth(
                    question,
                    run_state=run_state,
                    model=image_model,
                    size=image_size,
                    quality=image_quality,
                    count=image_count,
                    output=image_output,
                    output_format=image_output_format,
                    timeout=image_timeout,
                )
            else:
                result = generate_image_with_scillm(
                    question,
                    run_state=run_state,
                    model=image_model,
                    size=image_size,
                    quality=image_quality,
                    count=image_count,
                    output=image_output,
                    output_format=image_output_format,
                    timeout=image_timeout,
                )
            result["ask_id"] = run_state.ask_id
            result["runtime_artifacts"] = run_state.artifacts
            run_state.finish(result, state="answered")
        except Exception as exc:
            run_state.fail(exc)
            failure_result = {
                "question": question,
                "scope": "image-generation",
                "ask_id": run_state.ask_id,
                "runtime_artifacts": run_state.artifacts,
                "status": "failed",
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }
            if as_json:
                print(json.dumps(failure_result, indent=2, default=str))
            else:
                print("\n-- /ask image generation failed --")
                print(f"   Error: {type(exc).__name__}: {exc}")
                print(f"   Status: {run_state.artifacts.get('status')}")
                print()
            raise typer.Exit(code=1) from exc

        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print("\n-- /ask image generation --")
            # `result` IS the image-generation payload; it has no nested
            # "image_generation" key, and reaching for one crashed every
            # non-JSON call with a KeyError after the image was already written.
            for file_info in result.get("files") or []:
                print(f"   Image: {file_info['path']}")
            manifest = (result.get("runtime_artifacts") or {}).get("artifact_manifest")
            if manifest:
                print(f"   Manifest: {manifest}")
            print()
        raise typer.Exit(code=0)

    if dag_orchestration_attention:
        attention = run_state.needs_attention(**dag_orchestration_attention)
        result = {
            "question": question,
            "scope": scope,
            "items": [],
            "bridges_found": [],
            "answer": "",
            "auto_learned": False,
            "hybrid_mode": hybrid,
            "needs_attention": attention,
            "ask_id": run_state.ask_id,
            "runtime_artifacts": run_state.artifacts,
        }
        run_state.finish(result, state="needs_attention")
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print("\n-- /ask needs attention --")
            print(f"   Reason: {attention.get('reason', 'unknown')}")
            print(f"   Question: {attention.get('question', '')}")
            if attention.get("resume_hint"):
                print(f"   Resume: {attention['resume_hint']}")
            print()
        raise typer.Exit(code=2)

    if missing_persona_attention:
        attention = run_state.needs_attention(**missing_persona_attention)
        result = {
            "question": question,
            "scope": scope,
            "items": [],
            "bridges_found": [],
            "answer": "",
            "auto_learned": False,
            "hybrid_mode": hybrid,
            "needs_attention": attention,
            "ask_id": run_state.ask_id,
            "runtime_artifacts": run_state.artifacts,
        }
        run_state.finish(result, state="needs_attention")
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print("\n-- /ask needs attention --")
            print(f"   Reason: {attention.get('reason', 'unknown')}")
            print(f"   Question: {attention.get('question', '')}")
            if attention.get("resume_hint"):
                print(f"   Resume: {attention['resume_hint']}")
            print()
        raise typer.Exit(code=2)

    started_at = time.time()
    try:
        result = ask(
            question=question,
            scope=scope,
            k=k,
            use_bridges=bridges,
            raw=raw,
            as_json=as_json,
            auto_learn=auto_learn,
            collection=collection,
            hybrid=hybrid,
            persona_id=persona_id,
            oracle_model=oracle_model if oracle else None,
            oracle_reasoning=oracle_reasoning,
            oracle_timeout=oracle_timeout,
            oracle_idle_timeout=oracle_idle_timeout,
            oracle_heartbeat_interval=oracle_heartbeat_interval,
            oracle_persona=oracle_persona,
            oracle_consult_personas=suggested_personas if oracle else None,
            oracle_peer=oracle_peer,
            oracle_image_paths=oracle_image_paths or [],
            oracle_iterations=oracle_iterations,
            oracle_backend=oracle_backend,
            oracle_persona_model=oracle_persona_model,
            oracle_peer_model=oracle_peer_model,
            oracle_model_alias=model_alias_route.as_dict() if model_alias_route else None,
            roundtable=roundtable,
            roundtable_personas=roundtable_personas,
            roundtable_role_preset=roundtable_role_preset,
            roundtable_rounds=roundtable_rounds,
            roundtable_mode=roundtable_mode,
            roundtable_persist=roundtable_persist,
            argue=argue,
            decision_required=decision_required,
            tie_breaker=tie_breaker,
            parallel_review=parallel_review,
            parallel_reviewers=parallel_reviewers,
            parallel_review_personas=parallel_review_personas,
            parallel_review_focus=parallel_review_focus,
            parallel_review_role_preset=parallel_review_role_preset,
            review_target=review_target,
            parallel_review_runner=parallel_review_runner,
            review_dag=review_dag,
            read_only_review=read_only_review,
            code_runner_handoff=code_runner_handoff,
            implement_with=implement_with,
            apply_fixes=apply_fixes,
            code_runner_allowed_files=code_runner_allowed_files or [],
            code_runner_dod_commands=code_runner_dod_commands or [],
            implementation_non_goals=implementation_non_goals or [],
            implementation_risk_notes=implementation_risk_notes or [],
            dogpile_mode=dogpile_mode,
            deep_review=deep_review,
            deep_review_target=deep_review_target,
            deep_review_profile=deep_review_profile,
            deep_reviewers=deep_reviewers,
            deep_review_focus=deep_review_focus,
            deep_review_fallback_policy=deep_review_fallback_policy,
            deep_review_persist=deep_review_persist,
            deep_review_output_root=deep_review_output_root,
            cae_gap_review=cae_gap_review,
            cae_reviewers=cae_reviewers,
            cae_judge=cae_judge,
            cae_max_rounds=cae_max_rounds,
            cursor_browser_view_id=cursor_browser_view_id,
            cursor_browser_url=cursor_browser_url,
            cursor_browser_project=cursor_browser_project,
            gemini_tab_id=gemini_tab_id,
            gemini_url=gemini_url,
            kimi_tab_id=kimi_tab_id,
            kimi_url=kimi_url,
            visible_subagent=visible_subagent_route,
            mentioned_skills=mentioned_skills,
            ask_dag=ask_dag,
            run_state=run_state,
        )
    except Exception as exc:
        _record_ask_telemetry(
            result={
                "question": question,
                "scope": scope,
                "items": [],
                "auto_learned": False,
                "hybrid_mode": hybrid,
                "error": f"{type(exc).__name__}: {exc}",
            },
            started_at=started_at,
            status=f"error:{type(exc).__name__}",
            oracle_model=oracle_model if oracle else None,
            oracle_reasoning=oracle_reasoning,
            oracle_backend=oracle_backend,
            oracle_idle_timeout=oracle_idle_timeout,
            oracle_heartbeat_interval=oracle_heartbeat_interval,
            oracle_persona=oracle_persona,
            oracle_peer=oracle_peer,
            oracle_iterations=oracle_iterations,
        )
        run_state.fail(exc)
        failure_result = {
            "question": question,
            "scope": scope,
            "ask_id": run_state.ask_id,
            "runtime_artifacts": run_state.artifacts,
            "status": "failed",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
        if as_json:
            print(json.dumps(failure_result, indent=2, default=str))
        else:
            print("\n-- /ask failed --")
            print(f"   Error: {type(exc).__name__}: {exc}")
            print(f"   Status: {run_state.artifacts.get('status')}")
            print()
        raise typer.Exit(code=1) from exc

    if consult_personas:
        suggestion = _format_persona_suggestion(suggested_personas)
        if suggestion:
            print(suggestion)
            result["suggested_personas"] = suggested_personas

    result["ask_id"] = run_state.ask_id
    result["runtime_artifacts"] = run_state.artifacts
    if visible_subagent_route:
        result["visible_subagent"] = visible_subagent_route
        result["mentioned_skills"] = mentioned_skills
    if result.get("needs_attention"):
        run_state.finish(result, state="needs_attention")
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            attention = result["needs_attention"]
            print("\n-- /ask needs attention --")
            print(f"   Reason: {attention.get('reason', 'unknown')}")
            print(f"   Question: {attention.get('question', '')}")
            if attention.get("resume_hint"):
                print(f"   Resume: {attention['resume_hint']}")
            print()
        raise typer.Exit(code=2)
    if result.get("parallel_review") or result.get("argue") or result.get("cae_gap_review"):
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(result.get("answer", ""))
    run_state.finish(result)
    oracle = result.get("oracle", {})
    has_oracle_answer = bool(oracle) and bool(str(result.get("answer", "")).strip()) and not oracle.get("error")
    sys.exit(0 if result["items"] or result.get("parallel_review") or result.get("argue") or result.get("cae_gap_review") or has_oracle_answer else 1)


if __name__ == "__main__":
    app()
