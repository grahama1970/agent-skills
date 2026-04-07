"""Batch QRA extraction for doc2qra skill.

Provides parallel LLM-based QRA extraction across multiple sections
using scillm batch processing with provider chain fallback on rate
limits and errors.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Tuple

from .config import (
    DEFAULT_BATCH_TIMEOUT,
    DEFAULT_CONCURRENCY,
    DEFAULT_TIMEOUT,
    get_llm_provider_chain,
    preflight_budget_check,
)
from .qra_heuristic import fallback_heuristic_extraction, section_heuristic_fallback
from .qra_prompts import QRA_SYSTEM_PROMPT, QRA_PROMPT, build_qra_system_prompt
from .utils import clean_json_string, log


# =============================================================================
# Response Parsing
# =============================================================================


def parse_qra_response(
    content: Any,
    section_idx: int,
    section_title: str,
    source: str,
    clean_json_fn: Callable[[str], str],
) -> List[Dict[str, Any]]:
    """Parse LLM JSON response into QRA dicts.

    Args:
        content: Response content (str or dict)
        section_idx: Index of the section
        section_title: Title of the section
        source: Source identifier
        clean_json_fn: Function to clean JSON strings

    Returns:
        List of parsed QRA dicts
    """
    try:
        # Handle content that's already a dict
        if isinstance(content, dict):
            data = content
        else:
            cleaned = clean_json_fn(content) if clean_json_fn else content
            data = json.loads(cleaned)

        # Handle different response formats
        items = data.get("items", []) if isinstance(data, dict) else []
        if not items and isinstance(data, list):
            items = data
        if not items and isinstance(data, dict) and "question" in data:
            items = [data]

        result = []
        for item in items:
            if item.get("question") and item.get("answer"):
                problem = item["question"]
                if section_title:
                    problem = f"[{section_title}] {problem}"

                reasoning = item.get("reasoning", "")
                answer = item["answer"]
                solution = f"**Reasoning:** {reasoning}\n\n**Answer:** {answer}" if reasoning else answer

                result.append({
                    "problem": problem,
                    "solution": solution,
                    "reasoning": reasoning,
                    "answer": answer,
                    "section_idx": section_idx,
                    "section_title": section_title,
                    "source": source,
                    "type": "text",
                })
        return result
    except json.JSONDecodeError as e:
        log(f"JSON parse error: {e} - content: {str(content)[:100]}...", style="yellow")
        return []
    except Exception as e:
        log(f"Parse error: {e}", style="yellow")
        return []


# =============================================================================
# Single-Provider Batch
# =============================================================================


async def _run_batch_with_provider(
    provider: Dict[str, str],
    sections: List[Tuple[str, str]],
    source: str,
    concurrency: int,
    timeout: int,
    context: str = None,
    section_indices: List[int] = None,
) -> Tuple[List[Dict[str, Any]], List[int]]:
    """Run batch extraction against a single provider.

    Returns (qra_results, failed_section_indices).
    Failed sections include 429s, timeouts, and parse errors.
    """
    batch_acompletions_iter = None
    scillm_clean_json = None

    try:
        from scillm.batch import parallel_acompletions_iter as batch_acompletions_iter
        from scillm.extras.json_utils import clean_json_string as scillm_clean_json
    except ImportError:
        try:
            from scillm import batch_acompletions_iter
            from scillm.extras.json_utils import clean_json_string as scillm_clean_json
        except ImportError:
            pass

    if batch_acompletions_iter is None:
        return [], list(range(len(sections)))

    clean_fn = scillm_clean_json if scillm_clean_json else clean_json_string

    # Build batch requests
    system_prompt = build_qra_system_prompt(context) if context else QRA_SYSTEM_PROMPT
    system_msg = {"role": "system", "content": system_prompt}

    # If retrying specific sections, use those indices; otherwise all
    indices = section_indices if section_indices is not None else list(range(len(sections)))

    requests = []
    metadata = []
    for idx in indices:
        section_title, section_content = sections[idx]
        user_prompt = QRA_PROMPT.format(text=section_content[:3000])
        requests.append({
            "model": provider["model"],
            "messages": [system_msg, {"role": "user", "content": user_prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
            "temperature": 0.1,
        })
        metadata.append({"idx": idx, "title": section_title})

    provider_name = provider.get("name", provider["model"][:20])
    log(f"Batch [{provider_name}]: {len(requests)} sections, concurrency={concurrency}, model={provider['model'][:40]}")

    all_qa: List[Dict[str, Any]] = []
    failed_indices: List[int] = []
    done = ok = err_429 = err_other = 0

    try:
        async for ev in batch_acompletions_iter(
            requests,
            api_base=provider["api_base"],
            api_key=provider["api_key"],
            custom_llm_provider="openai_like",
            concurrency=concurrency,
            timeout=timeout,
            wall_time_s=DEFAULT_BATCH_TIMEOUT,
            tenacious=True,
        ):
            done += 1
            req_idx = ev.get("index", done - 1)
            meta = metadata[req_idx] if req_idx < len(metadata) else {"idx": req_idx, "title": f"Section {req_idx}"}
            section_idx = meta["idx"]
            section_title = meta["title"]

            if ev.get("ok") and ev.get("content"):
                ok += 1
                try:
                    qa_items = parse_qra_response(
                        ev["content"], section_idx, section_title, source, clean_fn
                    )
                    if qa_items:
                        all_qa.extend(qa_items)
                        log(f"[{done}/{len(requests)}] '{section_title[:30]}...' -> {len(qa_items)} QRAs [{provider_name}]", style="green")
                    else:
                        failed_indices.append(section_idx)
                        log(f"[{done}/{len(requests)}] '{section_title[:30]}...' -> empty parse [{provider_name}]", style="yellow")
                except Exception as parse_err:
                    err_other += 1
                    failed_indices.append(section_idx)
                    log(f"[{done}/{len(requests)}] '{section_title[:30]}...' -> {parse_err} [{provider_name}]", style="red")
            else:
                status = ev.get("status", "unknown")
                error = str(ev.get("error", ""))[:80]
                is_429 = status == 429 or "429" in error or "rate" in error.lower()
                if is_429:
                    err_429 += 1
                else:
                    err_other += 1
                failed_indices.append(section_idx)
                log(f"[{done}/{len(requests)}] '{section_title[:30]}...' -> {status} {error[:50]} [{provider_name}]", style="red")

        log(f"Batch [{provider_name}] complete: {ok} ok, {err_429} rate-limited, {err_other} errors, {len(all_qa)} QRAs", style="bold")

    except Exception as e:
        log(f"Batch [{provider_name}] failed: {e}", style="red")
        # All remaining sections are failed
        completed_indices = {m["idx"] for m in metadata[:done]}
        failed_indices = [idx for idx in indices if idx not in completed_indices or idx in failed_indices]

    return all_qa, failed_indices


# =============================================================================
# Multi-Provider Batch with Fallback
# =============================================================================


async def extract_qra_batch(
    sections: List[Tuple[str, str]],
    source: str = "",
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout: int = DEFAULT_TIMEOUT,
    context: str = None,
) -> List[Dict[str, Any]]:
    """Extract QRA from all sections using parallel LLM calls with provider fallback.

    Provider chain: Chutes -> DeepSeek -> OpenRouter. Falls back on 429/errors.
    Uses scillm batch_acompletions_iter for streaming progress.

    Args:
        sections: List of (section_title, section_content) tuples
        source: Source identifier for the content
        concurrency: Max parallel requests (default 6)
        timeout: Per-request timeout in seconds
        context: Optional domain context/persona for focused extraction

    Returns:
        List of QRA dicts with section metadata
    """
    # Pre-flight budget check: may re-route away from Chutes if quota is low
    estimated = len(sections) + 1
    preflight_config = preflight_budget_check(estimated)
    providers = get_llm_provider_chain()
    if not providers:
        log("No LLM providers configured, falling back to heuristic extraction", style="yellow")
        return fallback_heuristic_extraction(sections, source)

    # If preflight re-routed to a different provider, swap it to the front
    if preflight_config.get("api_base") and providers:
        preflight_base = preflight_config["api_base"]
        if preflight_base != providers[0].get("api_base"):
            preflight_entry = {
                "model": preflight_config["model"],
                "api_base": preflight_base,
                "api_key": preflight_config["api_key"],
                "name": "preflight",
            }
            providers = [preflight_entry] + [p for p in providers if p.get("api_base") != preflight_base]

    if context:
        log(f"Using domain context: {context[:50]}...", style="cyan")

    all_qa: List[Dict[str, Any]] = []
    remaining_indices: List[int] = None  # None = all sections

    for i, provider in enumerate(providers):
        provider_name = provider.get("name", provider["model"][:20])
        qa_results, failed_indices = await _run_batch_with_provider(
            provider, sections, source, concurrency, timeout, context,
            section_indices=remaining_indices,
        )
        all_qa.extend(qa_results)

        if not failed_indices:
            break  # All sections succeeded

        # If there are more providers, retry failed sections with next provider
        if i < len(providers) - 1:
            log(f"{len(failed_indices)} sections failed on {provider_name}, falling back to {providers[i+1].get('name', '?')}", style="yellow bold")
            remaining_indices = failed_indices
        else:
            # Last provider -- heuristic fallback for remaining failures
            log(f"{len(failed_indices)} sections failed on all providers, heuristic fallback", style="yellow")
            for idx in failed_indices:
                qa_pairs = section_heuristic_fallback(sections, idx, source)
                all_qa.extend(qa_pairs)

    log(f"Total QRAs extracted: {len(all_qa)} from {len(sections)} sections", style="bold")
    return all_qa
