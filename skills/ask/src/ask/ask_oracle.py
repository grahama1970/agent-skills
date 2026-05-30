"""Oracle synthesis and subagent orchestration for the ask skill."""

import json
import re
import time
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
from .cursor_browser_runtime import (
    CursorBrowserBackendError,
    CursorBrowserTabError,
    call_cursor_browser,
)
from .webgpt_runtime import (
    WebgptBackendError,
    WebgptTabError,
    WebReviewBundleError,
    build_webgpt_prompt,
    call_webgpt,
    extract_file_attachments,
    resolve_web_review_delivery,
)
from .gemini_runtime import (
    GeminiBackendError,
    GeminiBackendDegradedError,
    GeminiTabError,
    build_gemini_prompt,
    call_gemini,
)
from .kimi_runtime import (
    KimiBackendError,
    KimiBackendDegradedError,
    KimiTabError,
    build_kimi_prompt,
    call_kimi,
)
from .perplexity_runtime import (
    PerplexityBackendError,
    build_perplexity_prompt,
    call_perplexity,
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

def _run_oracle_webgpt(
    base_prompt: str,
    question: str,
    persona: Optional[str],
    iterations: int,
    timeout: float,
    webgpt_tab_id: str,
    webgpt_url: str,
    webgpt_create_tab: bool,
    webgpt_project: str,
    run_state: object | None,
    oracle_state: dict,
) -> tuple[str, str, list[dict]]:
    """Send one /ask synthesis prompt to the controlled ChatGPT tab via surf.

    iterations: each /ask call is one round. Multi-turn iteration is achieved
    by calling /ask repeatedly with the same controlled tab — ChatGPT
    preserves conversation state on the tab. We honour the requested
    iterations count by issuing that many turns in a single /ask call only
    when the caller asked for them, but the canonical N-round pattern is
    handled by re-calling /ask externally.
    """
    tab_id = (webgpt_tab_id or str(oracle_state.get("webgpt_tab_id", "") or "")).strip()
    url = (webgpt_url or str(oracle_state.get("webgpt_url", "") or "")).strip()
    create_tab = bool(webgpt_create_tab)
    project = (webgpt_project or str(oracle_state.get("webgpt_project", "") or "")).strip()
    attachments = extract_file_attachments(question)
    attach_file = resolve_web_review_delivery(question, attachments, backend="webgpt")
    prompt = build_webgpt_prompt(
        base_prompt,
        attachments,
        system_preamble=(
            "You are answering a /ask oracle call. Treat retrieved memory "
            "context as supporting evidence; cite supported claims inline with "
            "source IDs like [MEMORY.1]. Distinguish supported facts from "
            "inference. Be concise and technically precise."
        ),
    )

    turns: list[dict] = []
    last_content = ""
    total_iterations = max(1, int(iterations))
    for index in range(total_iterations):
        turn_number = index + 1
        try:
            result = call_webgpt(
                prompt if turn_number == 1 else _format_webgpt_followup_prompt(turns, turn_number, total_iterations),
                tab_id=tab_id,
                url=url,
                create_tab=create_tab and turn_number == 1,
                project=project,
                attach_file=attach_file if turn_number == 1 else "",
                timeout=timeout,
                no_activate=True,
                run_state=run_state,
                iteration=turn_number,
                persona=persona,
            )
        except WebgptTabError as exc:
            raise WebgptBackendError(
                f"WebGPT oracle could not resolve a ChatGPT tab on round {turn_number}: {exc}"
            ) from exc
        # Lock in the resolved tab for subsequent rounds so the conversation
        # context is preserved.
        if not tab_id and result.controlled_tab_id:
            tab_id = result.controlled_tab_id
        turns.append({
            "iteration": turn_number,
            "backend": "webgpt",
            "controlled_tab_id": result.controlled_tab_id,
            "took_ms": result.took_ms,
            "content": result.response,
            "artifact_dir": str(result.artifact_dir),
            "no_activate": result.no_activate,
            "focus_changed": result.focus_changed,
            "raw_contains_sentinel": result.raw_contains_sentinel,
        })
        last_content = result.response

    model_served = f"webgpt:{tab_id}" if tab_id else "webgpt"
    return last_content, model_served, turns




def _run_oracle_cursor_browser(
    base_prompt: str,
    question: str,
    persona: Optional[str],
    iterations: int,
    timeout: float,
    cursor_browser_view_id: str,
    cursor_browser_url: str,
    cursor_browser_project: str,
    run_state: object | None,
    oracle_state: dict,
) -> tuple[str, str, list[dict]]:
    view_id = (cursor_browser_view_id or str(oracle_state.get("cursor_browser_view_id", "") or "")).strip()
    url = (cursor_browser_url or str(oracle_state.get("cursor_browser_url", "") or "")).strip()
    project = (cursor_browser_project or str(oracle_state.get("cursor_browser_project", "") or "")).strip()
    attachments = extract_file_attachments(question)
    resolve_web_review_delivery(question, attachments, backend="cursor-browser")
    prompt = build_webgpt_prompt(
        base_prompt,
        attachments,
        system_preamble=(
            "You are answering a /ask oracle call in Cursor Browser. "
            "Treat retrieved memory context as supporting evidence."
        ),
    )
    turns: list[dict] = []
    last_content = ""
    total_iterations = max(1, int(iterations))
    for index in range(total_iterations):
        turn_number = index + 1
        try:
            result = call_cursor_browser(
                prompt if turn_number == 1 else _format_webgpt_followup_prompt(turns, turn_number, total_iterations),
                view_id=view_id,
                url=url,
                project=project,
                timeout=timeout,
                run_state=run_state,
                iteration=turn_number,
                persona=persona,
            )
        except CursorBrowserTabError as exc:
            raise CursorBrowserBackendError(
                f"Cursor Browser oracle could not resolve a viewId on round {turn_number}: {exc}"
            ) from exc
        if not view_id and result.controlled_view_id:
            view_id = result.controlled_view_id
        turns.append({
            "iteration": turn_number,
            "backend": "cursor-browser",
            "controlled_view_id": result.controlled_view_id,
            "took_ms": result.took_ms,
            "content": result.response,
            "artifact_dir": str(result.artifact_dir),
            "raw_contains_sentinel": result.raw_contains_sentinel,
        })
        last_content = result.response
    model_served = f"cursor-browser:{view_id}" if view_id else "cursor-browser"
    return last_content, model_served, turns

def _run_oracle_webgemini(
    base_prompt: str,
    question: str,
    persona: Optional[str],
    iterations: int,
    timeout: float,
    gemini_tab_id: str,
    gemini_url: str,
    run_state: object | None,
    oracle_state: dict,
) -> tuple[str, str, list[dict]]:
    """Send one /ask synthesis prompt to the controlled Gemini tab via surf.

    iterations: each /ask call is one round. Multi-turn iteration is achieved
    by calling /ask repeatedly with the same controlled tab — Gemini
    preserves conversation state on the tab.
    """
    tab_id = (gemini_tab_id or str(oracle_state.get("gemini_tab_id", "") or "")).strip()
    url = (gemini_url or str(oracle_state.get("gemini_url", "") or "")).strip()
    attachments = extract_file_attachments(question)
    resolve_web_review_delivery(question, attachments, backend="webgemini")
    prompt = build_gemini_prompt(
        base_prompt,
        attachments,
        system_preamble=(
            "You are answering a /ask oracle call. Treat retrieved memory "
            "context as supporting evidence; cite supported claims inline with "
            "source IDs like [MEMORY.1]. Distinguish supported facts from "
            "inference. Be concise and technically precise."
        ),
    )

    turns: list[dict] = []
    last_content = ""
    total_iterations = max(1, int(iterations))
    for index in range(total_iterations):
        turn_number = index + 1
        try:
            result = call_gemini(
                prompt if turn_number == 1 else _format_gemini_followup_prompt(turns, turn_number, total_iterations),
                tab_id=tab_id,
                url=url,
                timeout=timeout,
                no_activate=True,
                run_state=run_state,
                iteration=turn_number,
                persona=persona,
            )
        except GeminiTabError as exc:
            raise GeminiBackendError(
                f"Gemini oracle could not resolve a Gemini tab on round {turn_number}: {exc}"
            ) from exc
        except GeminiBackendDegradedError as exc:
            raise  # propagate with self-correction guidance already in message
        # Lock in the resolved tab for subsequent rounds.
        if not tab_id and result.controlled_tab_id:
            tab_id = result.controlled_tab_id
        turns.append({
            "iteration": turn_number,
            "backend": "webgemini",
            "controlled_tab_id": result.controlled_tab_id,
            "took_ms": result.took_ms,
            "content": result.response,
            "artifact_dir": str(result.artifact_dir),
            "no_activate": result.no_activate,
            "focus_changed": result.focus_changed,
            "raw_contains_sentinel": result.raw_contains_sentinel,
        })
        last_content = result.response

    model_served = f"webgemini:{tab_id}" if tab_id else "webgemini"
    return last_content, model_served, turns


def _format_gemini_followup_prompt(
    turns: list[dict],
    turn_number: int,
    total_iterations: int,
) -> str:
    """Build a follow-up prompt that nudges Gemini to refine the prior answer."""
    return (
        f"This is iteration {turn_number}/{total_iterations} on the same /ask oracle question. "
        "Review your previous answer in this conversation. Identify the weakest claim or "
        "the assumption most likely to be wrong, address it, and return an improved final "
        "answer. If your previous answer is already correct and well-supported, say so "
        "explicitly and restate the conclusion concisely."
    )


def _run_oracle_webkimi(
    base_prompt: str,
    question: str,
    persona: Optional[str],
    iterations: int,
    timeout: float,
    kimi_tab_id: str,
    kimi_url: str,
    run_state: object | None,
    oracle_state: dict,
) -> tuple[str, str, list[dict]]:
    """Send one /ask synthesis prompt to the controlled Kimi tab via surf."""
    tab_id = (kimi_tab_id or str(oracle_state.get("kimi_tab_id", "") or "")).strip()
    url = (kimi_url or str(oracle_state.get("kimi_url", "") or "")).strip()
    attachments = extract_file_attachments(question)
    resolve_web_review_delivery(question, attachments, backend="webkimi")
    prompt = build_kimi_prompt(
        base_prompt,
        attachments,
        system_preamble=(
            "You are answering a /ask oracle call. Treat retrieved memory "
            "context as supporting evidence; cite supported claims inline with "
            "source IDs like [MEMORY.1]. Distinguish supported facts from "
            "inference. Be concise and technically precise."
        ),
    )

    turns: list[dict] = []
    last_content = ""
    total_iterations = max(1, int(iterations))
    for index in range(total_iterations):
        turn_number = index + 1
        try:
            result = call_kimi(
                prompt if turn_number == 1 else _format_kimi_followup_prompt(turns, turn_number, total_iterations),
                tab_id=tab_id,
                url=url,
                timeout=timeout,
                no_activate=True,
                run_state=run_state,
                iteration=turn_number,
                persona=persona,
            )
        except KimiTabError as exc:
            raise KimiBackendError(
                f"Kimi oracle could not resolve a Kimi tab on round {turn_number}: {exc}"
            ) from exc
        except KimiBackendDegradedError:
            raise
        if not tab_id and result.controlled_tab_id:
            tab_id = result.controlled_tab_id
        turns.append({
            "iteration": turn_number,
            "backend": "webkimi",
            "controlled_tab_id": result.controlled_tab_id,
            "took_ms": result.took_ms,
            "content": result.response,
            "artifact_dir": str(result.artifact_dir),
            "no_activate": result.no_activate,
            "focus_changed": result.focus_changed,
            "raw_contains_sentinel": result.raw_contains_sentinel,
        })
        last_content = result.response

    model_served = f"webkimi:{tab_id}" if tab_id else "webkimi"
    return last_content, model_served, turns


def _format_kimi_followup_prompt(
    turns: list[dict],
    turn_number: int,
    total_iterations: int,
) -> str:
    return (
        f"This is iteration {turn_number}/{total_iterations} on the same /ask oracle question. "
        "Review your previous answer in this conversation. Identify the weakest claim or "
        "the assumption most likely to be wrong, address it, and return an improved final "
        "answer. If your previous answer is already correct and well-supported, say so "
        "explicitly and restate the conclusion concisely."
    )


def _run_oracle_webperplexity(
    base_prompt: str,
    question: str,
    persona: Optional[str],
    timeout: float,
    run_state: object | None,
) -> tuple[str, str, list[dict]]:
    """One-shot Perplexity research oracle via surf (no standing tab)."""
    attachments = extract_file_attachments(question)
    resolve_web_review_delivery(question, attachments, backend="webperplexity")
    prompt = build_perplexity_prompt(
        base_prompt,
        attachments,
    )
    if persona:
        prompt = f"Persona perspective: {persona}\n\n{prompt}"
    try:
        result = call_perplexity(
            prompt,
            timeout=timeout,
            run_state=run_state,
        )
    except PerplexityBackendError as exc:
        raise PerplexityBackendError(
            f"Perplexity oracle call failed: {exc}"
        ) from exc
    turns = [{
        "iteration": 1,
        "backend": "webperplexity",
        "took_ms": result.took_ms,
        "content": result.response,
        "artifact_dir": str(result.artifact_dir),
    }]
    return result.response, "webperplexity", turns


def _format_webgpt_followup_prompt(
    turns: list[dict],
    turn_number: int,
    total_iterations: int,
) -> str:
    """Build a follow-up prompt that nudges ChatGPT to refine the prior answer.

    The previous turn's content stays in ChatGPT's own conversation memory on
    the tab — we don't need to re-include it. We only frame this turn.
    """
    return (
        f"This is iteration {turn_number}/{total_iterations} on the same /ask oracle question. "
        "Review your previous answer in this conversation. Identify the weakest claim or "
        "the assumption most likely to be wrong, address it, and return an improved final "
        "answer. If your previous answer is already correct and well-supported, say so "
        "explicitly and restate the conclusion concisely."
    )


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
    oracle_image_paths: Optional[list[str]] = None,
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
    webgpt_tab_id: str = "",
    webgpt_url: str = "",
    webgpt_create_tab: bool = False,
    webgpt_project: str = "",
    cursor_browser_view_id: str = "",
    cursor_browser_url: str = "",
    cursor_browser_project: str = "",
    gemini_tab_id: str = "",
    gemini_url: str = "",
    kimi_tab_id: str = "",
    kimi_url: str = "",
    run_state: object | None = None,
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
                run_state=run_state,
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
                image_paths=oracle_image_paths or [],
                run_state=run_state,
            )
            protocol_state = {}
        elif effective_backend == "webgpt":
            content, model_served, turns = _run_oracle_webgpt(
                base_prompt=prompt,
                question=question,
                persona=persona,
                iterations=iterations,
                timeout=timeout,
                webgpt_tab_id=webgpt_tab_id,
                webgpt_url=webgpt_url,
                webgpt_create_tab=webgpt_create_tab,
                webgpt_project=webgpt_project,
                run_state=run_state,
                oracle_state=result.get("oracle", {}),
            )
            protocol_state = {}
        elif effective_backend == "cursor-browser":
            content, model_served, turns = _run_oracle_cursor_browser(
                base_prompt=prompt,
                question=question,
                persona=persona,
                iterations=iterations,
                timeout=timeout,
                cursor_browser_view_id=cursor_browser_view_id,
                cursor_browser_url=cursor_browser_url,
                cursor_browser_project=cursor_browser_project,
                run_state=run_state,
                oracle_state=result.get("oracle", {}),
            )
            protocol_state = {}
        elif effective_backend == "webgemini":
            content, model_served, turns = _run_oracle_webgemini(
                base_prompt=prompt,
                question=question,
                persona=persona,
                iterations=iterations,
                timeout=timeout,
                gemini_tab_id=gemini_tab_id,
                gemini_url=gemini_url,
                run_state=run_state,
                oracle_state=result.get("oracle", {}),
            )
            protocol_state = {}
        elif effective_backend == "webkimi":
            content, model_served, turns = _run_oracle_webkimi(
                base_prompt=prompt,
                question=question,
                persona=persona,
                iterations=iterations,
                timeout=timeout,
                kimi_tab_id=kimi_tab_id,
                kimi_url=kimi_url,
                run_state=run_state,
                oracle_state=result.get("oracle", {}),
            )
            protocol_state = {}
        elif effective_backend == "webperplexity":
            content, model_served, turns = _run_oracle_webperplexity(
                base_prompt=prompt,
                question=question,
                persona=persona,
                timeout=timeout,
                run_state=run_state,
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
                image_paths=oracle_image_paths or [],
                run_state=run_state,
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
        if oracle_image_paths:
            result["oracle"]["image_paths"] = oracle_image_paths
            result["oracle"]["image_count"] = len(oracle_image_paths)
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
    except WebReviewBundleError as exc:
        result["answer"] = str(exc)
        result["oracle"] = {
            "model": model,
            "reasoning_effort": reasoning_effort,
            "idle_timeout_seconds": idle_timeout,
            "heartbeat_interval_seconds": heartbeat_interval,
            "backend": effective_backend,
            "source": effective_backend,
            "error": "web_review_bundle",
            "bundle_error": True,
        }
        if persona:
            result["oracle"]["persona"] = persona
        if consult_personas:
            result["oracle"]["consulted_personas"] = consult_personas
        if peer:
            result["oracle"]["peer"] = peer
        if run_state is not None and hasattr(run_state, "needs_attention"):
            result["needs_attention"] = run_state.needs_attention(
                reason="web_review_bundle_unreadable",
                question=str(exc),
                safe_default="provide_concatenated_text_or_small_zip",
                resume_hint=(
                    "Rebuild evidence as one concatenated .md/.txt file, or a .zip "
                    "with at most 5 files, then re-run $ask with only that path in "
                    "the prompt."
                ),
            )
        log.warning("Web review bundle rejected for project agent: %s", exc)
        return
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
    run_state: object | None = None,
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
    deadline = time.time() + timeout

    if parallel_review:
        review_content, model_served, review_turns, state = _run_parallel_review_protocol(
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=_remaining_timeout(deadline, stage="parallel review"),
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            base_prompt=enriched_prompt,
            backend=backend,
            reviewer_count=parallel_reviewers,
            reviewer_specs=parallel_review_personas,
            reviewer_focus=parallel_review_focus,
            role_preset=parallel_review_role_preset,
            state=state,
            run_state=run_state,
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
            timeout=_remaining_timeout(deadline, stage="roundtable"),
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
            run_state=run_state,
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
        timeout=_remaining_timeout(deadline, stage="moderator synthesis"),
        idle_timeout=idle_timeout,
        heartbeat_interval=heartbeat_interval,
        prompt=moderator_prompt,
        persona="moderator",
        turn_number=len(turns) + 1,
        backend=backend,
        run_state=run_state,
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


def _remaining_timeout(deadline: float, *, stage: str) -> float:
    remaining = deadline - time.time()
    if remaining <= 0:
        raise TimeoutError(f"oracle structured review exceeded wall-clock timeout before {stage}")
    return remaining


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
    run_state: object | None = None,
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
            run_state=run_state,
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
    run_state: object | None = None,
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
                run_state=run_state,
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
        run_state=run_state,
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
    run_state: object | None = None,
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
            run_state=run_state,
        )
        return content, model, artifact_dir
    content, model_served = _complete_oracle_call(
        model=model,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        prompt=prompt,
        run_state=run_state,
        iteration=turn_number,
        persona=persona,
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
    image_paths: Optional[list[str]] = None,
    run_state: object | None = None,
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
            image_paths=image_paths or [],
            run_state=run_state,
            iteration=1,
            persona=persona or "oracle",
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
            image_paths=image_paths or [],
            run_state=run_state,
            iteration=turn_number,
            persona=active_persona,
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
