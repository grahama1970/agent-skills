"""Answer ranking, synthesis, and presentation for the ask skill."""

import json
from typing import Optional

from loguru import logger as log

from .deep_review import build_deep_review_prompt, finalize_deep_review_result
from .ask_config import (
    DEFAULT_ORACLE_BACKEND,
    DEFAULT_ORACLE_HEARTBEAT_INTERVAL,
    DEFAULT_ORACLE_IDLE_TIMEOUT,
    DEFAULT_ORACLE_REASONING,
    DEFAULT_ORACLE_TIMEOUT,
)
from .ask_oracle import _apply_oracle_synthesis, _rank_items
from .scillm_runtime import (
    CITATION_SCHEMA_VERSION,
    build_source_bundle,
    memory_citations_from_items,
    render_citations_markdown,
)

def _synthesise(
    result: dict,
    k: int,
    raw: bool,
    as_json: bool,
    auto_learn: bool,
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
    deep_review_request: Optional[dict] = None,
    webgpt_tab_id: str = "",
    webgpt_url: str = "",
    webgpt_create_tab: bool = False,
    webgpt_project: str = "",
    gemini_tab_id: str = "",
    gemini_url: str = "",
    run_state: object | None = None,
) -> None:
    """Build the answer string and print output."""
    question = result["question"]
    scope = result["scope"]

    if result["items"]:
        if raw:
            result["answer"] = "[raw mode -- see items]"
        else:
            ranked = _rank_items(result["items"])
            source_bundle = build_source_bundle(question=question, context_items=ranked[:k])
            parts = [
                item.get("solution", item.get("text", ""))
                for item in ranked[:k]
                if item.get("solution") or item.get("text")
            ]
            result["answer"] = "\n\n".join(parts) if parts else "No answer could be synthesized."
            result["citation_schema_version"] = CITATION_SCHEMA_VERSION
            result["source_bundle"] = {
                "source_bundle_id": source_bundle["source_bundle_id"],
                "citation_schema_version": source_bundle.get("citation_schema_version", CITATION_SCHEMA_VERSION),
                "source_ids": [source["source_id"] for source in source_bundle["sources"]],
                "sources": source_bundle["sources"],
            }
            result["citations"] = memory_citations_from_items(ranked, limit=k, supports="answer")
            result["citation_status"] = {
                "status": "PASS" if result["citations"] else "DEGRADED",
                "basis": "memory",
                "rule": "memory citations support knowledge answers but not code/review safety claims",
            }
            # Track how many meta items were filtered
            meta_count = len(result["items"]) - len(ranked)
            if meta_count > 0:
                log.debug("Filtered %d meta items from synthesis", meta_count)
        log.info("Synthesised answer from %d items", len(result["items"]))
    else:
        if oracle_model:
            result["answer"] = "[no memory context retrieved; passing original question directly to oracle]"
        elif auto_learn:
            result["answer"] = (
                f'No knowledge found for "{question}" even after auto-learning. '
                f'Try providing specific YouTube URLs: ./run.sh learn "{question}" '
                f"--scope {scope} --youtube <url>"
            )
        else:
            result["answer"] = (
                f'No knowledge found for "{question}" in scope \'{scope}\'. '
                f'Try: ./run.sh ask "{question}" --scope {scope} --auto-learn'
            )
        log.info("No knowledge found for question")

    original_question = result["question"]
    if deep_review_request and oracle_model and not raw:
        result["question"] = build_deep_review_prompt(result, deep_review_request)

    if oracle_model and not raw:
        _apply_oracle_synthesis(
            result,
            k=k,
            model=oracle_model,
            reasoning_effort=oracle_reasoning,
            timeout=oracle_timeout,
            idle_timeout=oracle_idle_timeout,
            heartbeat_interval=oracle_heartbeat_interval,
            persona=oracle_persona,
            consult_personas=oracle_consult_personas or [],
            peer=oracle_peer,
            iterations=oracle_iterations,
            backend=oracle_backend,
            persona_model=oracle_persona_model,
            peer_model=oracle_peer_model,
            persona_scope=oracle_persona_scope,
            oracle_image_paths=oracle_image_paths or [],
            roundtable=roundtable,
            roundtable_personas=roundtable_personas,
            roundtable_role_preset=roundtable_role_preset,
            roundtable_rounds=roundtable_rounds,
            roundtable_mode=roundtable_mode,
            roundtable_persist=roundtable_persist,
            parallel_review=parallel_review and not deep_review_request,
            parallel_reviewers=parallel_reviewers,
            parallel_review_personas=parallel_review_personas,
            parallel_review_focus=parallel_review_focus,
            parallel_review_role_preset=parallel_review_role_preset,
            webgpt_tab_id=webgpt_tab_id,
            webgpt_url=webgpt_url,
            webgpt_create_tab=webgpt_create_tab,
            webgpt_project=webgpt_project,
            gemini_tab_id=gemini_tab_id,
            gemini_url=gemini_url,
            run_state=run_state,
        )

    if deep_review_request:
        result["question"] = original_question
        finalize_deep_review_result(result, deep_review_request)

    # Print output
    if as_json:
        print(json.dumps(result, indent=2, default=str))
    elif raw:
        print(json.dumps({"items": result["items"]}, indent=2, default=str))
    else:
        _print_human(result, k, auto_learn)


def _print_human(result: dict, k: int, auto_learn: bool) -> None:
    """Pretty-print results for human consumption."""
    question = result["question"]
    scope = result["scope"]

    print(f'\n-- Answer: "{question}" --')
    print(f"   Scope: {scope} | Results: {len(result['items'])}", end="")
    if result.get("hybrid_mode"):
        qra = result.get("qra_count", 0)
        rag = result.get("rag_count", 0)
        print(f" | Hybrid: {qra} QRA + {rag} RAG", end="")
    if result["bridges_found"]:
        print(f" | Bridges: {', '.join(result['bridges_found'])}", end="")
    if result.get("auto_learned"):
        print(" | Auto-learned: yes", end="")
    if result.get("oracle"):
        oracle = result["oracle"]
        print(f" | Oracle: {oracle.get('model')}:{oracle.get('reasoning_effort')}", end="")
    print("\n")

    if result.get("oracle") and result.get("answer"):
        print(result["answer"])
        print()
        if result.get("citations"):
            print("Citations:")
            print(render_citations_markdown(result.get("citations", [])))
            print()

    ranked_items = _rank_items(result["items"]) if result["items"] else []
    if ranked_items:
        for i, item in enumerate(ranked_items[:k], 1):
            problem = item.get("problem", item.get("text", "")[:120])
            solution = item.get("solution", item.get("text", ""))
            bridge = item.get("via_bridge", "")
            source_type = item.get("source_type", "")
            reasoning = item.get("reasoning", "")

            tags = []
            if bridge:
                tags.append(bridge)
            if source_type:
                tags.append(source_type.upper())
            tag_str = f" [{', '.join(tags)}]" if tags else ""

            print(f"  {i}. {problem}{tag_str}")
            if reasoning:
                print(f"     Reasoning: {reasoning[:200]}...")
            if solution:
                sol_lines = solution.split("\n")
                for line in sol_lines[:5]:
                    print(f"     {line}")
                if len(sol_lines) > 5:
                    print(f"     ... ({len(sol_lines) - 5} more lines)")
            print()
    else:
        if auto_learn:
            print("  No knowledge found even after auto-learning.")
            print(f'  Provide YouTube URLs: ./run.sh learn "{question}" --scope {scope} --youtube <url>')
        else:
            print(f'  No knowledge found. Try: ./run.sh ask "{question}" --scope {scope} --auto-learn')
    if not result.get("oracle") and result.get("citations"):
        print("Citations:")
        print(render_citations_markdown(result.get("citations", [])))
        print()
    print()
