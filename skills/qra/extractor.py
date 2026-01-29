"""QRA Extractor - Q&A extraction logic with LLM batch processing.

This module handles:
- System prompt building with domain context
- Batch LLM calls for parallel extraction
- Response parsing and heuristic fallback
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from qra.config import (
    DEBUG_DIR,
    DEFAULT_CONCURRENCY,
    DEFAULT_TIMEOUT,
    DEFAULT_WALL_TIME,
    MAX_CONTENT_PER_REQUEST,
    MAX_TOKENS,
    QRA_BASE_RULES,
    QRA_JSON_FORMAT,
    QRA_USER_PROMPT,
    TEMPERATURE,
    get_scillm_config,
)
from qra.utils import clean_json_string, log, split_sentences

# =============================================================================
# System Prompt Building
# =============================================================================


def build_system_prompt(context: Optional[str] = None) -> str:
    """Build QRA system prompt with optional domain context.

    Context can be:
    - Simple phrase: "ML researcher" -> becomes "You are a ML researcher"
    - Rich context (multi-line): Used as full guidance, supports markdown

    Args:
        context: Optional domain context or persona

    Returns:
        Complete system prompt
    """
    json_instruction = f"""You MUST respond with valid JSON only.
Do not include any text before or after the JSON. Do not use markdown code blocks.
Return ONLY a JSON object matching this exact schema:

{QRA_JSON_FORMAT}
"""

    if context:
        # Check if rich context (multi-line with guidance)
        is_rich_context = "\n" in context.strip() or len(context) > 200

        if is_rich_context:
            # Rich context: use as primary guidance
            return f"""{context}

{json_instruction}
{QRA_BASE_RULES}"""
        else:
            # Simple context: wrap as persona
            return f"""You are a {context}.

Extract knowledge items that are relevant to your expertise and domain.
Skip content that is outside your area of focus.
Prioritize actionable information over generic descriptions.

{json_instruction}
{QRA_BASE_RULES}"""

    # No context: generic extraction
    return f"""You are a knowledge extraction assistant.

Extract meaningful facts, concepts, methods, and relationships.
Prefer: definitions, algorithms, data structures, implementation patterns, key findings.

{json_instruction}
{QRA_BASE_RULES}"""


# =============================================================================
# Response Parsing
# =============================================================================


def parse_qra_response(
    content: Any,
    section_idx: int,
    section_title: str,
    source: str,
    clean_fn: Optional[Callable[[str], str]] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Parse LLM JSON response into QRA dicts.

    Args:
        content: LLM response (string or dict)
        section_idx: Index of source section
        section_title: Title of source section
        source: Source identifier
        clean_fn: Optional JSON cleaning function

    Returns:
        Tuple of (qra_items, valid_response) where valid_response indicates
        whether the LLM returned a valid JSON response (even if empty items).
        If valid_response is True but items is empty, the LLM intentionally
        skipped this section - don't use heuristic fallback.
    """
    try:
        if isinstance(content, dict):
            data = content
        else:
            cleaned = clean_fn(content) if clean_fn else clean_json_string(content)
            data = json.loads(cleaned)

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
                solution = (
                    f"**Reasoning:** {reasoning}\n\n**Answer:** {answer}"
                    if reasoning
                    else answer
                )

                result.append(
                    {
                        "problem": problem,
                        "solution": solution,
                        "question": item["question"],
                        "reasoning": reasoning,
                        "answer": answer,
                        "section_idx": section_idx,
                        "section_title": section_title,
                        "source": source,
                    }
                )
        # Return True for valid_response even if result is empty
        return result, True
    except json.JSONDecodeError as e:
        log(f"JSON parse error: {e}", style="yellow")
        return [], False
    except Exception as e:
        log(f"Parse error: {e}", style="yellow")
        return [], False


def heuristic_fallback(
    content: str, section_title: str, source: str
) -> List[Dict[str, Any]]:
    """Simple heuristic extraction when LLM fails.

    Creates a single QRA pair from the section content.

    Args:
        content: Section text content
        section_title: Section title
        source: Source identifier

    Returns:
        List with single heuristic QRA dict
    """
    if not content.strip():
        return []

    if section_title:
        problem = (
            f"What is {section_title}?"
            if not section_title.endswith("?")
            else section_title
        )
    else:
        sents = split_sentences(content)
        problem = sents[0][:200] if sents else "Unknown topic"

    solution = content[:1000] if len(content) > 1000 else content

    return [
        {
            "problem": f"[{source}] {problem}" if source else problem,
            "solution": solution,
            "question": problem,
            "reasoning": "",
            "answer": solution,
            "source": source,
        }
    ]


# =============================================================================
# Batch Extraction
# =============================================================================


async def extract_qra_batch(
    sections: List[Tuple[str, str]],
    source: str = "",
    context: Optional[str] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout: int = DEFAULT_TIMEOUT,
) -> List[Dict[str, Any]]:
    """Extract QRA from sections using parallel LLM calls.

    Uses scillm batch processing for efficient parallel extraction.
    Falls back to heuristic extraction if API unavailable.

    Args:
        sections: List of (title, content) tuples
        source: Source identifier
        context: Optional domain context/persona
        concurrency: Max parallel requests
        timeout: Per-request timeout

    Returns:
        List of QRA dicts
    """
    config = get_scillm_config()

    if not config["api_key"]:
        log("CHUTES_API_KEY not set, using heuristic fallback", style="yellow")
        return _fallback_extraction(sections, source)

    # Import scillm batch function
    batch_acompletions_iter = None
    scillm_clean_json = None

    try:
        from scillm.batch import parallel_acompletions_iter as batch_acompletions_iter
        from scillm.extras.json_utils import clean_json_string as scillm_clean_json
    except ImportError:
        try:
            from scillm import batch_acompletions_iter
            from scillm.extras.json_utils import (
                clean_json_string as scillm_clean_json,
            )
        except ImportError:
            pass

    if batch_acompletions_iter is None:
        log("scillm not available, using heuristic fallback", style="yellow")
        return _fallback_extraction(sections, source)

    clean_fn = scillm_clean_json or clean_json_string

    # Build system prompt with optional context
    system_prompt = build_system_prompt(context)
    system_msg = {"role": "system", "content": system_prompt}

    # Build requests
    requests = []
    metadata = []

    for idx, (section_title, section_content) in enumerate(sections):
        user_prompt = QRA_USER_PROMPT.format(
            text=section_content[:MAX_CONTENT_PER_REQUEST]
        )
        requests.append(
            {
                "model": config["model"],
                "messages": [system_msg, {"role": "user", "content": user_prompt}],
                "response_format": {"type": "json_object"},
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
            }
        )
        metadata.append(
            {"idx": idx, "title": section_title, "content": section_content}
        )

    log(f"Batch: {len(requests)} sections, concurrency={concurrency}")
    if context:
        log(f"Context: {context[:60]}...", style="cyan")

    # Debug logging
    debug_data = _init_debug_log(config, system_prompt, context, requests)

    all_qa: List[Dict[str, Any]] = []
    done = ok = err = 0

    async for ev in batch_acompletions_iter(
        requests,
        api_base=config["api_base"],
        api_key=config["api_key"],
        custom_llm_provider="openai_like",
        concurrency=concurrency,
        timeout=timeout,
        wall_time_s=DEFAULT_WALL_TIME,
        tenacious=True,
    ):
        done += 1
        req_idx = ev.get("index", done - 1)
        meta = metadata[req_idx] if req_idx < len(metadata) else {
            "idx": req_idx,
            "title": "",
            "content": "",
        }
        section_idx = meta["idx"]
        section_title = meta["title"]

        # Log response for debugging
        debug_data["responses"].append(
            {
                "index": req_idx,
                "section_title": section_title,
                "ok": ev.get("ok", False),
                "error": ev.get("error"),
                "content_preview": str(ev.get("content", ""))[:500]
                if ev.get("content")
                else None,
            }
        )

        if ev.get("ok") and ev.get("content"):
            ok += 1
            qa_items, valid_response = parse_qra_response(
                ev["content"], section_idx, section_title, source, clean_fn
            )
            if qa_items:
                all_qa.extend(qa_items)
                log(
                    f"[{done}/{len(requests)}] '{section_title[:30]}' -> "
                    f"{len(qa_items)} QRAs",
                    style="green",
                )
            elif valid_response:
                # LLM returned valid JSON with empty items
                log(
                    f"[{done}/{len(requests)}] '{section_title[:30]}' -> "
                    "skip (no actionable content)",
                    style="dim",
                )
            else:
                # Parse failed - use heuristic fallback
                fallback = heuristic_fallback(meta["content"], section_title, source)
                for fb in fallback:
                    fb["section_idx"] = section_idx
                    fb["section_title"] = section_title
                all_qa.extend(fallback)
                log(
                    f"[{done}/{len(requests)}] '{section_title[:30]}' -> "
                    "heuristic fallback",
                    style="yellow",
                )
        else:
            err += 1
            log(
                f"[{done}/{len(requests)}] '{section_title[:30]}' -> "
                f"error: {ev.get('error', 'unknown')}",
                style="red",
            )
            fallback = heuristic_fallback(meta["content"], section_title, source)
            for fb in fallback:
                fb["section_idx"] = section_idx
                fb["section_title"] = section_title
            all_qa.extend(fallback)

    log(f"Batch complete: {ok} ok, {err} errors, {len(all_qa)} QRAs", style="bold")

    # Save final debug file
    _save_debug_log(debug_data, ok, err, len(all_qa))

    return all_qa


def _fallback_extraction(
    sections: List[Tuple[str, str]], source: str
) -> List[Dict[str, Any]]:
    """Fallback extraction when LLM unavailable.

    Args:
        sections: List of (title, content) tuples
        source: Source identifier

    Returns:
        List of heuristic QRA dicts
    """
    all_qa = []
    for idx, (title, content) in enumerate(sections):
        qras = heuristic_fallback(content, title, source)
        for qra in qras:
            qra["section_idx"] = idx
            qra["section_title"] = title
        all_qa.extend(qras)
    return all_qa


def _init_debug_log(
    config: Dict[str, str],
    system_prompt: str,
    context: Optional[str],
    requests: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Initialize debug log file.

    Args:
        config: scillm config
        system_prompt: System prompt used
        context: Domain context
        requests: LLM requests

    Returns:
        Debug data dict
    """
    DEBUG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    debug_data = {
        "timestamp": timestamp,
        "model": config["model"],
        "api_base": config["api_base"],
        "system_prompt": system_prompt,
        "context_provided": context[:500] if context else None,
        "num_requests": len(requests),
        "sample_user_prompt": requests[0]["messages"][1]["content"][:500]
        if requests
        else None,
        "responses": [],
        "_debug_file": str(DEBUG_DIR / f"batch_{timestamp}.json"),
    }

    # Save initial debug info
    debug_file = Path(debug_data["_debug_file"])
    debug_file.write_text(
        json.dumps(debug_data, indent=2, default=str), encoding="utf-8"
    )
    log(f"Debug log: {debug_file}", style="dim")

    return debug_data


def _save_debug_log(
    debug_data: Dict[str, Any], ok: int, err: int, total_qras: int
) -> None:
    """Save final debug log with summary.

    Args:
        debug_data: Debug data dict
        ok: Successful requests
        err: Failed requests
        total_qras: Total QRAs extracted
    """
    debug_data["summary"] = {"ok": ok, "errors": err, "total_qras": total_qras}
    debug_file = Path(debug_data["_debug_file"])
    debug_file.write_text(
        json.dumps(debug_data, indent=2, default=str), encoding="utf-8"
    )
    log(f"Debug saved: {debug_file}", style="dim")
