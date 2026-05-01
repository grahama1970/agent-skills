"""Oracle synthesis and subagent orchestration for the ask skill."""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import httpx
from loguru import logger as log

from .oracle_adapters import (
    _META_SOURCES,
    _META_TAGS,
    _complete_oracle_call,
    _complete_oracle_subagent_call,
    _default_oracle_peer,
    _format_deliberation_transcript,
    _is_codex_agent_model,
    _resolve_oracle_backend,
    _run_oracle_subagent_iterations,
)
from .ask_persona_profiles import (
    _format_persona_profile_for_prompt,
    _load_oracle_persona_profiles,
)
from .review_protocols import (
    build_moderator_prompt,
    build_parallel_reviewer_prompt,
    build_roundtable_turn_prompt,
    default_parallel_participants,
    parse_participant_specs,
    parse_protocol_turn,
)
from .skills_exec import parse_memory_output, run_memory_recall
from .scillm_runtime import (
    CITATION_SCHEMA_VERSION,
    build_source_bundle,
    memory_citations_from_items,
    normalize_citations,
)


INLINE_CITATION_RE = re.compile(r"\[(MEMORY\.\d+|QUESTION|DOGPILE\.\d+|FETCHER\.\d+)\]")

def _is_meta_item(item: dict) -> bool:
    """Detect system meta-knowledge (routing rules, skill descriptions).

    Meta items are useful for the system but should NOT be served as answers
    to domain questions. They pollute synthesis with instructions.
    """
    # Tag-based detection
    tags = item.get("tags", [])
    if isinstance(tags, list) and any(t in _META_TAGS for t in tags):
        return True
    # Source-based detection
    source = item.get("source", item.get("_source", ""))
    if source in _META_SOURCES:
        return True
    # Content heuristic: if solution talks about skill chains / RecallResult
    solution = item.get("solution", "")
    if any(kw in solution for kw in ("RecallResult", "fallback_chain", "should_build_evidence", "run.sh")):
        return True
    return False


def _rank_items(items: list[dict]) -> list[dict]:
    """Rank items by relevance: domain content first, meta filtered out."""
    domain = [i for i in items if not _is_meta_item(i)]
    if domain:
        # Sort by BM25 score descending if available
        domain.sort(key=lambda i: i.get("scores", {}).get("bm25", 0), reverse=True)
        return domain
    # Fallback: return all items if everything is meta (shouldn't happen)
    return items

def _apply_oracle_synthesis(
    result: dict,
    k: int,
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    persona: Optional[str],
    consult_personas: list[dict],
    peer: Optional[str],
    iterations: int,
    backend: str,
    persona_model: Optional[str],
    peer_model: Optional[str],
    persona_scope: str,
    roundtable: bool = False,
    roundtable_personas: Optional[str] = None,
    roundtable_role_preset: str = "adversarial-review",
    roundtable_rounds: int = 2,
    roundtable_mode: str = "adversarial",
    roundtable_persist: str = "summary",
    parallel_review: bool = False,
    parallel_reviewers: int = 3,
    parallel_review_personas: Optional[str] = None,
    parallel_review_focus: Optional[str] = None,
    parallel_review_role_preset: str = "adversarial-review",
) -> None:
    """Use an oracle backend for final high-reasoning synthesis."""
    question = result["question"]
    ranked_items = _rank_items(result["items"]) if result["items"] else []
    source_bundle = build_source_bundle(question=question, context_items=ranked_items[:k])
    context = _format_oracle_context(ranked_items[:k])
    fallback_answer = result.get("answer", "")
    persona_profiles = _load_oracle_persona_profiles(
        persona=persona,
        peer=peer,
        consult_personas=consult_personas,
        persona_scope=persona_scope,
    )
    persona_context = _format_oracle_persona_context(persona, consult_personas, persona_profiles)
    freshness_policy = result.get("oracle", {})
    dogpile_line = (
        f"Dogpile/freshness policy: mode={freshness_policy.get('dogpile_mode', 'auto')}; "
        f"fresh external discovery recommended={freshness_policy.get('dogpile_recommended', False)}. "
        "If recommended and the answer depends on current external state, use /dogpile before finalizing."
    )
    effective_backend = _resolve_oracle_backend(
        backend=backend,
        iterations=iterations,
        persona=persona,
        peer=peer,
        consult_personas=consult_personas,
    )
    if (roundtable or parallel_review) and backend == "auto":
        effective_backend = "subagent-runner"

    prompt = (
        "Question:\n"
        f"{question}\n\n"
        "Persona/subagent context:\n"
        f"{persona_context or '[none specified]'}\n\n"
        "Retrieved memory context:\n"
        f"{context or '[no memory context retrieved]'}\n\n"
        f"{dogpile_line}\n\n"
        "Current non-oracle synthesis:\n"
        f"{fallback_answer or '[none]'}\n\n"
        "Answer the question directly. Use the retrieved memory context when it is relevant. "
        "Cite supported claims inline with source IDs like [MEMORY.1]. "
        "Memory citations count for knowledge/persona/project-context answers, but not for "
        "code or review safety claims. For current external facts, say fresh sources are needed "
        "unless dogpile/fetcher evidence is present. "
        "If the context is weak or incomplete, say that explicitly and separate supported facts "
        "from your inference. Keep the answer concise and technically precise."
    )

    try:
        if parallel_review or roundtable:
            content, model_served, turns, protocol_state = _run_structured_review_protocol(
                model=model,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                idle_timeout=idle_timeout,
                heartbeat_interval=heartbeat_interval,
                base_prompt=prompt,
                backend=effective_backend,
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
            )
        elif effective_backend == "subagent-runner":
            content, model_served, turns = _run_oracle_subagent_iterations(
                model=model,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                idle_timeout=idle_timeout,
                heartbeat_interval=heartbeat_interval,
                base_prompt=prompt,
                persona=persona,
                consult_personas=consult_personas,
                peer=peer,
                iterations=iterations,
                persona_model=persona_model,
                peer_model=peer_model,
            )
            protocol_state = {}
        else:
            content, model_served, turns = _run_oracle_iterations(
                model=model,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                base_prompt=prompt,
                persona=persona,
                consult_personas=consult_personas,
                peer=peer,
                iterations=iterations,
                persona_model=persona_model,
                peer_model=peer_model,
            )
            protocol_state = {}
        result["answer"] = content
        result["oracle"] = {
            "model": model,
            "reasoning_effort": reasoning_effort,
            "idle_timeout_seconds": idle_timeout,
            "heartbeat_interval_seconds": heartbeat_interval,
            "model_served": model_served,
            "backend": effective_backend,
            "source": effective_backend,
            "iterations_requested": iterations,
            "iterations_completed": len(turns),
        }
        if persona:
            result["oracle"]["persona"] = persona
        if consult_personas:
            result["oracle"]["consulted_personas"] = consult_personas
        if peer:
            result["oracle"]["peer"] = peer
        if persona_model:
            result["oracle"]["persona_model"] = persona_model
        if peer_model:
            result["oracle"]["peer_model"] = peer_model
        if freshness_policy.get("model_alias"):
            result["oracle"]["model_alias"] = freshness_policy["model_alias"]
        result["oracle"]["dogpile_mode"] = freshness_policy.get("dogpile_mode", "auto")
        result["oracle"]["dogpile_recommended"] = freshness_policy.get("dogpile_recommended", False)
        if persona_profiles:
            result["oracle"]["persona_profiles"] = persona_profiles
        if parallel_review:
            result["oracle"]["parallel_review"] = {
                "reviewers_requested": parallel_reviewers,
                "personas": parallel_review_personas or "",
                "focus": parallel_review_focus or "",
                "role_preset": parallel_review_role_preset,
            }
        if roundtable:
            result["oracle"]["roundtable"] = {
                "personas": roundtable_personas or "",
                "role_preset": roundtable_role_preset,
                "rounds": roundtable_rounds,
                "mode": roundtable_mode,
                "persist": roundtable_persist,
            }
        if protocol_state:
            result["oracle"]["protocol_state"] = _format_protocol_state_for_result(
                protocol_state,
                persist=roundtable_persist,
            )
        if len(turns) > 1:
            result["oracle"]["deliberation"] = turns
        result["citation_schema_version"] = CITATION_SCHEMA_VERSION
        result["source_bundle"] = {
            "source_bundle_id": source_bundle["source_bundle_id"],
            "citation_schema_version": source_bundle.get("citation_schema_version", CITATION_SCHEMA_VERSION),
            "source_ids": [source["source_id"] for source in source_bundle["sources"]],
            "sources": source_bundle["sources"],
        }
        result["citations"] = _citations_from_inline_ids(content, ranked_items[:k])
        if not result["citations"]:
            result["citations"] = memory_citations_from_items(ranked_items, limit=k, supports="oracle_answer")
            citation_status = "DEGRADED" if result["citations"] else "MISSING"
        else:
            citation_status = "PASS"
        result["citation_status"] = {
            "status": citation_status,
            "basis": "memory",
            "rule": "memory citations support knowledge answers but not code/review safety claims",
        }
        log.info("Oracle synthesis complete: model=%s reasoning=%s", model, reasoning_effort)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        result["oracle"] = {
            "model": model,
            "reasoning_effort": reasoning_effort,
            "idle_timeout_seconds": idle_timeout,
            "heartbeat_interval_seconds": heartbeat_interval,
            "backend": effective_backend,
            "source": effective_backend,
            "error": str(exc),
        }
        if persona:
            result["oracle"]["persona"] = persona
        if consult_personas:
            result["oracle"]["consulted_personas"] = consult_personas
        if peer:
            result["oracle"]["peer"] = peer
        if persona_model:
            result["oracle"]["persona_model"] = persona_model
        if peer_model:
            result["oracle"]["peer_model"] = peer_model
        if freshness_policy.get("model_alias"):
            result["oracle"]["model_alias"] = freshness_policy["model_alias"]
        if persona_profiles:
            result["oracle"]["persona_profiles"] = persona_profiles
        result["oracle"]["iterations_requested"] = iterations
        result["answer"] = fallback_answer
        log.warning("Oracle synthesis failed; using non-oracle answer: %s", exc)


def _run_structured_review_protocol(
    *,
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    base_prompt: str,
    backend: str,
    roundtable: bool,
    roundtable_personas: Optional[str],
    roundtable_role_preset: str,
    roundtable_rounds: int,
    roundtable_mode: str,
    roundtable_persist: str,
    parallel_review: bool,
    parallel_reviewers: int,
    parallel_review_personas: Optional[str],
    parallel_review_focus: Optional[str],
    parallel_review_role_preset: str,
) -> tuple[str, str, list[dict], dict]:
    """Run parallel reviewers, a sequential roundtable, or both."""
    turns: list[dict] = []
    state: dict = {
        "claims": [],
        "critiques": [],
        "open_issues": [],
        "turns": [],
        "parallel_reviews": [],
        "roundtable_turns": [],
    }
    model_served = model
    enriched_prompt = base_prompt

    if parallel_review:
        review_content, model_served, review_turns, state = _run_parallel_review_protocol(
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            base_prompt=enriched_prompt,
            backend=backend,
            reviewer_count=parallel_reviewers,
            reviewer_specs=parallel_review_personas,
            reviewer_focus=parallel_review_focus,
            role_preset=parallel_review_role_preset,
            state=state,
        )
        turns.extend(review_turns)
        enriched_prompt = (
            f"{base_prompt}\n\n"
            "Independent parallel review findings to use as prior state:\n"
            f"{review_content}\n"
        )

    if roundtable:
        roundtable_content, model_served, roundtable_turns, state = _run_roundtable_protocol(
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            base_prompt=enriched_prompt,
            backend=backend,
            persona_specs=roundtable_personas,
            role_preset=roundtable_role_preset,
            rounds=roundtable_rounds,
            mode=roundtable_mode,
            persist=roundtable_persist,
            state=state,
        )
        turns.extend(roundtable_turns)
        return roundtable_content, model_served, turns, state

    moderator_prompt = build_moderator_prompt(
        base_prompt=enriched_prompt,
        state=state,
        mode="parallel-review",
        persist=roundtable_persist,
    )
    content, model_served, artifact_dir = _run_protocol_turn(
        model=model,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        idle_timeout=idle_timeout,
        heartbeat_interval=heartbeat_interval,
        prompt=moderator_prompt,
        persona="moderator",
        turn_number=len(turns) + 1,
        backend=backend,
    )
    moderator_turn = {
        "iteration": len(turns) + 1,
        "persona": "moderator",
        "protocol_role": "synthesis_lead",
        "model": model_served,
        "backend": backend if artifact_dir else "scillm",
        "content": content,
    }
    if artifact_dir:
        moderator_turn["artifact_dir"] = artifact_dir
    turns.append(moderator_turn)
    state["final_synthesis"] = content
    return content, model_served, turns, state


def _run_parallel_review_protocol(
    *,
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    base_prompt: str,
    backend: str,
    reviewer_count: int,
    reviewer_specs: Optional[str],
    reviewer_focus: Optional[str],
    role_preset: str,
    state: dict,
) -> tuple[str, str, list[dict], dict]:
    participants = parse_participant_specs(reviewer_specs, role_preset=role_preset)
    if not participants:
        participants = default_parallel_participants(
            reviewer_count,
            focus=reviewer_focus,
            role_preset=role_preset,
        )
    participants = participants[:max(1, reviewer_count)]
    turns: list[dict] = []
    model_served = model

    def run_one(index: int, participant: dict) -> dict:
        prompt = build_parallel_reviewer_prompt(
            base_prompt=base_prompt,
            participant=participant,
            mode="parallel-review",
        )
        content, served, artifact_dir = _run_protocol_turn(
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            prompt=prompt,
            persona=str(participant["persona"]),
            turn_number=index + 1,
            backend=backend,
        )
        parsed = parse_protocol_turn(content)
        parsed.update(
            {
                "iteration": index + 1,
                "persona": participant["persona"],
                "protocol_role": participant["protocol_role"],
                "role_label": participant["role_label"],
                "model": served,
                "backend": backend if artifact_dir else "scillm",
                "content": content,
            }
        )
        if artifact_dir:
            parsed["artifact_dir"] = artifact_dir
        return parsed

    with ThreadPoolExecutor(max_workers=len(participants)) as executor:
        futures = {
            executor.submit(run_one, index, participant): index
            for index, participant in enumerate(participants)
        }
        for future in as_completed(futures):
            turn = future.result()
            turns.append(turn)
            model_served = str(turn.get("model", model_served))

    turns.sort(key=lambda item: int(item.get("iteration", 0)))
    for turn in turns:
        state["parallel_reviews"].append(turn)
        state["turns"].append(turn)
        state["critiques"].extend(turn.get("critiques") or [])
        state["open_issues"].extend(turn.get("blocking_findings") or [])
        state["open_issues"].extend(turn.get("open_issues") or [])
    summary = json.dumps(
        [
            {
                "persona": turn.get("persona"),
                "protocol_role": turn.get("protocol_role"),
                "summary": turn.get("summary", ""),
                "critiques": turn.get("critiques", []),
                "blocking_findings": turn.get("blocking_findings", []),
            }
            for turn in turns
        ],
        indent=2,
        default=str,
    )
    return summary, model_served, turns, state


def _run_roundtable_protocol(
    *,
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    base_prompt: str,
    backend: str,
    persona_specs: Optional[str],
    role_preset: str,
    rounds: int,
    mode: str,
    persist: str,
    state: dict,
) -> tuple[str, str, list[dict], dict]:
    participants = parse_participant_specs(persona_specs, role_preset=role_preset)
    if not participants:
        participants = default_parallel_participants(3, role_preset=role_preset)
    total_rounds = max(1, rounds)
    total_turns = len(participants) * total_rounds
    turns: list[dict] = []
    model_served = model

    for round_index in range(total_rounds):
        for participant_index, participant in enumerate(participants):
            turn_number = round_index * len(participants) + participant_index + 1
            prompt = build_roundtable_turn_prompt(
                base_prompt=base_prompt,
                participant=participant,
                state=state,
                turn_number=turn_number,
                total_turns=total_turns,
                mode=mode,
            )
            content, model_served, artifact_dir = _run_protocol_turn(
                model=model,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                idle_timeout=idle_timeout,
                heartbeat_interval=heartbeat_interval,
                prompt=prompt,
                persona=str(participant["persona"]),
                turn_number=turn_number,
                backend=backend,
            )
            parsed = parse_protocol_turn(content)
            parsed.update(
                {
                    "iteration": turn_number,
                    "round": round_index + 1,
                    "persona": participant["persona"],
                    "protocol_role": participant["protocol_role"],
                    "role_label": participant["role_label"],
                    "model": model_served,
                    "backend": backend if artifact_dir else "scillm",
                    "content": content,
                }
            )
            if artifact_dir:
                parsed["artifact_dir"] = artifact_dir
            turns.append(parsed)
            state["roundtable_turns"].append(parsed)
            state["turns"].append(parsed)
            state["claims"].extend(parsed.get("claims") or [])
            state["critiques"].extend(parsed.get("critiques") or [])
            state["open_issues"].extend(parsed.get("open_issues") or [])

    moderator_prompt = build_moderator_prompt(
        base_prompt=base_prompt,
        state=state,
        mode=f"roundtable:{mode}",
        persist=persist,
    )
    content, model_served, artifact_dir = _run_protocol_turn(
        model=model,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        idle_timeout=idle_timeout,
        heartbeat_interval=heartbeat_interval,
        prompt=moderator_prompt,
        persona="moderator",
        turn_number=total_turns + 1,
        backend=backend,
    )
    moderator_turn = {
        "iteration": total_turns + 1,
        "persona": "moderator",
        "protocol_role": "synthesis_lead",
        "model": model_served,
        "backend": backend if artifact_dir else "scillm",
        "content": content,
    }
    if artifact_dir:
        moderator_turn["artifact_dir"] = artifact_dir
    turns.append(moderator_turn)
    state["final_synthesis"] = content
    return content, model_served, turns, state


def _run_protocol_turn(
    *,
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    prompt: str,
    persona: str,
    turn_number: int,
    backend: str,
) -> tuple[str, str, str]:
    """Run one protocol turn and return content, served model, optional artifact dir."""
    if backend == "subagent-runner" and _is_codex_agent_model(model):
        content, artifact_dir = _complete_oracle_subagent_call(
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            prompt=prompt,
            persona=persona,
            turn_number=turn_number,
        )
        return content, model, artifact_dir
    content, model_served = _complete_oracle_call(
        model=model,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        prompt=prompt,
    )
    return content, model_served, ""


def _format_protocol_state_for_result(state: dict, *, persist: str) -> dict:
    """Keep default protocol state compact unless full persistence is requested."""
    if persist == "full":
        return state
    return {
        "claims_count": len(state.get("claims", [])),
        "critiques_count": len(state.get("critiques", [])),
        "open_issues": state.get("open_issues", [])[:20],
        "parallel_reviews": [
            {
                "persona": turn.get("persona"),
                "protocol_role": turn.get("protocol_role"),
                "summary": turn.get("summary", ""),
                "blocking_findings": turn.get("blocking_findings", [])[:10],
                "critiques": (turn.get("critiques") or [])[:5],
            }
            for turn in state.get("parallel_reviews", [])
        ],
        "roundtable_turns": [
            {
                "persona": turn.get("persona"),
                "protocol_role": turn.get("protocol_role"),
                "claims": (turn.get("claims") or [])[:5],
                "critiques": (turn.get("critiques") or [])[:5],
                "open_issues": (turn.get("open_issues") or [])[:5],
            }
            for turn in state.get("roundtable_turns", [])
        ],
        "final_synthesis": state.get("final_synthesis", ""),
    }


def _run_oracle_iterations(
    model: str,
    reasoning_effort: str,
    timeout: float,
    base_prompt: str,
    persona: Optional[str],
    consult_personas: list[dict],
    peer: Optional[str],
    iterations: int,
    persona_model: Optional[str],
    peer_model: Optional[str],
) -> tuple[str, str, list[dict]]:
    """Run one or more sequential oracle calls as subagent-style deliberation."""
    total_iterations = max(1, iterations)
    if total_iterations == 1:
        active_model = persona_model or model
        content, model_served = _complete_oracle_call(
            model=active_model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            prompt=base_prompt,
        )
        return content, model_served, [{
            "iteration": 1,
            "persona": persona or "oracle",
            "model": active_model,
            "backend": "scillm",
            "content": content,
        }]

    peer_name = peer or _default_oracle_peer(consult_personas)
    primary_name = persona or "primary oracle"
    turns: list[dict] = []
    model_served = model

    for index in range(total_iterations):
        turn_number = index + 1
        active_persona = primary_name if index % 2 == 0 else peer_name
        active_model = (persona_model or model) if index % 2 == 0 else (peer_model or model)
        transcript = _format_deliberation_transcript(turns)
        prompt = (
            f"{base_prompt}\n\n"
            "Deliberation transcript so far:\n"
            f"{transcript or '[none]'}\n\n"
            f"Iteration {turn_number}/{total_iterations}. You are {active_persona}. "
            "Challenge weak assumptions, incorporate useful prior turns, and return the best current answer. "
            "If this is the final iteration, produce the final answer."
        )
        content, model_served = _complete_oracle_call(
            model=active_model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            prompt=prompt,
        )
        turns.append({
            "iteration": turn_number,
            "persona": active_persona,
            "model": model_served,
            "backend": "scillm",
            "content": content,
        })

    return turns[-1]["content"], str(turns[-1].get("model", model)), turns


def _format_oracle_context(items: list[dict], max_chars: int = 24000) -> str:
    """Render retrieved memory items into bounded context for oracle synthesis."""
    sections: list[str] = []
    remaining = max_chars
    for index, item in enumerate(items, 1):
        problem = str(item.get("problem", "")).strip()
        solution = str(item.get("solution", item.get("text", ""))).strip()
        reasoning = str(item.get("reasoning", "")).strip()
        source = str(item.get("source", item.get("_source", ""))).strip()
        bridge = str(item.get("via_bridge", "")).strip()
        section = (
            f"[MEMORY.{index}]\n"
            f"Problem: {problem}\n"
            f"Source: {source or 'unknown'}\n"
            f"Bridge: {bridge or 'none'}\n"
            f"Solution: {solution}\n"
        )
        if reasoning:
            section += f"Reasoning: {reasoning}\n"
        if len(section) > remaining:
            sections.append(section[:remaining].rstrip())
            break
        sections.append(section.rstrip())
        remaining -= len(section)
        if remaining <= 0:
            break
    return "\n\n".join(sections)


def _citations_from_inline_ids(content: str, items: list[dict]) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    seen: set[str] = set()
    for source_id in INLINE_CITATION_RE.findall(content or ""):
        if source_id in seen:
            continue
        seen.add(source_id)
        if source_id.startswith("MEMORY."):
            index = int(source_id.split(".", 1)[1]) - 1
            item = items[index] if 0 <= index < len(items) else {}
            text = str(item.get("solution") or item.get("answer") or item.get("text") or item.get("problem") or "").strip()
            citations.append({
                "source_id": source_id,
                "source_kind": "memory",
                "quote_or_summary": text[:280],
                "supports": "oracle_answer",
            })
        elif source_id == "QUESTION":
            citations.append({
                "source_id": "QUESTION",
                "source_kind": "question",
                "quote_or_summary": "User question",
                "supports": "oracle_answer",
            })
    return normalize_citations(citations, supports="oracle_answer")


def _format_oracle_persona_context(
    persona: Optional[str],
    consult_personas: list[dict],
    persona_profiles: dict[str, dict],
) -> str:
    """Render persona/subagent instructions for oracle synthesis."""
    lines: list[str] = []
    if persona:
        lines.append(
            f"Primary persona/subagent: {persona}. Answer from this perspective while preserving factual accuracy."
        )
        if persona in persona_profiles:
            lines.append(_format_persona_profile_for_prompt(persona, persona_profiles[persona]))
    if consult_personas:
        lines.append("Advisory personas/subagents:")
        for item in consult_personas:
            name = item.get("name", "unknown")
            role = item.get("role", "expert")
            bridges = ", ".join(item.get("bridges", [])) or "domain match"
            expertise = ", ".join(item.get("expertise", []))
            detail = f"- {name} ({role}) [{bridges}]"
            if expertise:
                detail += f"; expertise: {expertise}"
            lines.append(detail)
            if name in persona_profiles:
                lines.append(_format_persona_profile_for_prompt(name, persona_profiles[name]))
    return "\n".join(lines)
