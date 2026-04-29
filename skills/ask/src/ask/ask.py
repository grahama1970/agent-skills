"""CLI implementation for memory-backed ask queries and oracle review routing."""

import json
import hashlib
import os
import subprocess
import sys
import time
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
)
from .argue import ARGUE_TIE_BREAKERS, run_argue
from .chain_specs import apply_chain_options
from .deep_review import build_deep_review_request, infer_deep_review
from .dry_run_spec import build_ask_dry_run_spec, print_execution_spec
from .parallel_review import MAX_REVIEWERS, ParallelReviewError, run_parallel_review, validate_code_runner_allowed_files
from .ask_oracle import _is_meta_item
from .ask_persona_profiles import _format_persona_suggestion
from .ask_relevance import _has_relevant_domain_items, _try_evidence_case
from .preflight import EVIDENCE_CASE, NEEDS_ATTENTION, NORMAL_ANSWER, run_sparta_preflight
from .ask_results import _synthesise
from .ask_routing import (
    _is_operational_question,
    _parse_natural_argue_query,
    _parse_natural_persona_query,
    _parse_natural_parallel_review_query,
    _parse_natural_roundtable_query,
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

app = typer.Typer(help="/ask ask - Query accumulated knowledge")



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
    oracle_persona_scope: str = "personas",
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
        oracle_persona_scope: Preferred memory scope for persona profiles.
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
        implement_with: Explicit implementation backend request; currently code-runner only.
        apply_fixes: Alias for explicit code-runner implementation intent.
        dogpile_mode: auto, off, or force freshness policy for oracle subagents.
        deep_review: Run Web-GPT-style deep review with JSON/markdown artifacts.

    Returns:
        dict with answer, sources, bridges.
    """
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
        result["oracle"]["dogpile_mode"] = dogpile_mode
    preflight = run_sparta_preflight(question, scope, k, run_state=run_state)
    result["preflight"] = preflight
    preflight_route = preflight.get("route")
    if preflight_route == NEEDS_ATTENTION:
        attention = {
            "reason": preflight.get("reason", "sparta_preflight_needs_attention"),
            "question": question,
            "safe_default": "pause",
            "resume_hint": "Resolve or verify the SPARTA identifier, then rerun /ask.",
            "preflight": preflight,
        }
        if run_state:
            attention = run_state.needs_attention(**attention)
        result["needs_attention"] = attention
        return result
    if preflight_route == EVIDENCE_CASE:
        if run_state:
            run_state.step_started("evidence_case", source="sparta_preflight")
        evidence_result = _try_evidence_case(question, scope)
        result["evidence_case"] = evidence_result
        result["evidence_case_artifact"] = evidence_result
        if evidence_result:
            result["items"] = [{
                "problem": question,
                "solution": "Structured evidence was retrieved and assembled by /create-evidence-case.",
                "via": "evidence_case",
                "evidence_case_id": evidence_result.get("claim", {}).get("id", ""),
            }]
            result["answer"] = "Structured evidence was retrieved and assembled by /create-evidence-case. Review the evidence_case artifact."
        if run_state:
            run_state.step_finished("evidence_case", used=bool(evidence_result), items_count=len(result["items"]))
        return result

    deep_review_request = None
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
        if (apply_fixes or implement_with) and not any(command.strip() for command in (code_runner_dod_commands or [])):
            attention = {
                "reason": "missing_code_runner_dod",
                "question": "Explicit implementation intent requires at least one --code-runner-dod-command.",
                "safe_default": "do_not_invoke_code_runner",
                "resume_hint": "Run again with --code-runner-dod-command <safe validation command>.",
            }
            if run_state:
                attention = run_state.needs_attention(**attention)
            result["needs_attention"] = attention
            return result
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
    if hybrid:
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
    if (is_operational or not has_domain_answer) and not _is_direct_control_lookup(question):
        if run_state:
            run_state.step_started("evidence_case", operational=is_operational, has_domain_answer=has_domain_answer)
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

    # Step 2c: Auto-learn if still no domain results
    if not domain_items and auto_learn:
        if run_state:
            run_state.step_started("auto_learn", collection=collection)
        result = _auto_learn(result, question, scope, collection, k, use_bridges)
        if run_state:
            run_state.step_finished("auto_learn", items_count=len(result.get("items", [])), auto_learned=bool(result.get("auto_learned")))

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
    implement_with: Optional[str] = typer.Option(None, "--implement-with", help="Explicit implementation backend request; currently code-runner only"),
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
    review_context: str = typer.Option("fresh", "--review-context", help="Context policy: fresh or inherited"),
    inherit_memory: str = typer.Option("summary", "--inherit-memory", help="Context policy memory inheritance: none, summary, or full"),
    inherit_skills: str = typer.Option("selected", "--inherit-skills", help="Context policy skill inheritance: none, selected, or all"),
    inherit_project_context: str = typer.Option("no", "--inherit-project-context", help="Context policy project inheritance: no, summary, or full"),
    chain: Optional[str] = typer.Option(None, "--chain", help="Saved review chain spec name or path"),
    reviewer_specs: Optional[list[str]] = typer.Option(None, "--reviewer-spec", help="Reviewer spec name or path (repeatable)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview execution spec and risk analysis without mutation"),
    ask_id: Optional[str] = typer.Option(None, "--ask-id", help="Stable runtime artifact id for this ask call"),
    run_output_root: Optional[str] = typer.Option(None, "--run-output-root", help="Directory for ask runtime artifacts"),
    overwrite_run: bool = typer.Option(False, "--overwrite", help="Replace an existing run directory for --ask-id"),
    resume_run: bool = typer.Option(False, "--resume", help="Resume a non-terminal existing run directory for --ask-id"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    question, inferred_parallel_review, inferred_parallel_reviewers, inferred_parallel_focus = (
        _parse_natural_parallel_review_query(question_parts)
    )
    if inferred_parallel_review:
        parallel_review = True
        oracle = True
        if inferred_parallel_reviewers is not None:
            parallel_reviewers = inferred_parallel_reviewers
        if inferred_parallel_focus and not parallel_review_focus:
            parallel_review_focus = inferred_parallel_focus
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "subagent-runner"

    argue_question_parts = [question] if inferred_parallel_review else question_parts
    question, inferred_argue = _parse_natural_argue_query(argue_question_parts)
    if inferred_argue:
        argue = True
        oracle = True
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "scillm"

    roundtable_question_parts = [question] if (inferred_parallel_review or inferred_argue) else question_parts
    question, inferred_roundtable_personas, inferred_roundtable = _parse_natural_roundtable_query(roundtable_question_parts)
    if inferred_roundtable:
        roundtable = True
        oracle = True
        if not roundtable_personas:
            roundtable_personas = inferred_roundtable_personas
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "subagent-runner"

    persona_question_parts = [question] if (inferred_roundtable or inferred_parallel_review or inferred_argue) else question_parts
    question, inferred_persona, inferred_peer, inferred_oracle = _parse_natural_persona_query(
        persona_question_parts,
        explicit_persona=oracle_persona,
    )
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
    elif not oracle and not raw and _should_auto_oracle_persona(question):
        oracle = True
        consult_personas = True
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "subagent-runner"
    if roundtable or parallel_review or argue:
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

    if deep_review or infer_deep_review(question):
        deep_review = True
        oracle = True
        parallel_review = True
        parallel_reviewers = max(parallel_reviewers, deep_reviewers)
        if deep_review_focus and not parallel_review_focus:
            parallel_review_focus = deep_review_focus
        if oracle_backend == DEFAULT_ORACLE_BACKEND:
            oracle_backend = "subagent-runner"
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
    if implement_with and implement_with != "code-runner":
        raise typer.BadParameter(
            "Only --implement-with code-runner is supported.",
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
            "Code-runner handoff options require --parallel-review.",
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
        roundtable,
        roundtable_personas,
        argue,
        parallel_review,
        parallel_review_personas,
        oracle_backend != DEFAULT_ORACLE_BACKEND,
        oracle_idle_timeout != DEFAULT_ORACLE_IDLE_TIMEOUT,
        oracle_heartbeat_interval != DEFAULT_ORACLE_HEARTBEAT_INTERVAL,
    ]):
        raise typer.BadParameter(
            "Oracle-specific options require --oracle.",
            param_hint="--oracle",
        )

    run_id = ask_id or make_run_id(question)
    context_policy = build_context_policy(
        "deep-review" if deep_review else "argue" if argue else "ask",
        review_context=review_context,
        inherit_memory=inherit_memory,
        inherit_skills=inherit_skills,
        inherit_project_context=inherit_project_context,
    )
    request_payload = {
        "command": "ask",
        "question": question,
        "scope": scope,
        "k": k,
        "bridges": bridges,
        "raw": raw,
        "auto_learn": auto_learn,
        "collection": collection,
        "hybrid": hybrid,
        "consult_personas": consult_personas,
        "persona_scope": persona_scope,
        "persona_id": persona_id,
        "oracle": oracle,
        "oracle_backend": oracle_backend,
        "oracle_model": oracle_model if oracle else None,
        "oracle_reasoning": oracle_reasoning,
        "oracle_timeout": oracle_timeout,
        "oracle_idle_timeout": oracle_idle_timeout,
        "oracle_heartbeat_interval": oracle_heartbeat_interval,
        "oracle_persona": oracle_persona,
        "oracle_peer": oracle_peer,
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
        "context_policy": context_policy,
        "chain": chain,
        "reviewer_specs": reviewer_specs or [],
        "suggested_personas_count": 0,
    }
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

    require_runtime_artifacts = deep_review or parallel_review or argue
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
            oracle_iterations=oracle_iterations,
            oracle_backend=oracle_backend,
            oracle_persona_model=oracle_persona_model,
            oracle_peer_model=oracle_peer_model,
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
        raise

    if consult_personas:
        suggestion = _format_persona_suggestion(suggested_personas)
        if suggestion:
            print(suggestion)
            result["suggested_personas"] = suggested_personas

    result["ask_id"] = run_state.ask_id
    result["runtime_artifacts"] = run_state.artifacts
    if result.get("needs_attention"):
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
    if result.get("parallel_review") or result.get("argue"):
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(result.get("answer", ""))
    run_state.finish(result)
    sys.exit(0 if result["items"] or result.get("parallel_review") or result.get("argue") else 1)


if __name__ == "__main__":
    app()
