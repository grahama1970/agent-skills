"""Batch QRA extraction for doc2qra skill.

Provides parallel LLM-based QRA extraction across multiple sections
using httpx calls to scillm proxy at localhost:4001.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable, Dict, List, Tuple

import httpx

from .config import DEFAULT_CONCURRENCY, DEFAULT_TIMEOUT
from .qra_heuristic import fallback_heuristic_extraction, section_heuristic_fallback
from .qra_prompts import QRA_SYSTEM_PROMPT, QRA_PROMPT, build_qra_system_prompt
from .utils import clean_json_string, log

# scillm proxy config
SCILLM_API_BASE = os.environ.get("SCILLM_API_BASE", "http://localhost:4001")
SCILLM_PROXY_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")


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
# Single Section Request (httpx)
# =============================================================================


async def _extract_section(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    idx: int,
    section_title: str,
    section_content: str,
    source: str,
    system_prompt: str,
) -> Tuple[int, List[Dict[str, Any]], bool]:
    """Extract QRA from a single section via scillm proxy.

    Returns (section_idx, qra_items, success).
    """
    user_prompt = QRA_PROMPT.format(text=section_content[:3000])

    async with semaphore:
        try:
            resp = await client.post(
                f"{SCILLM_API_BASE}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {SCILLM_PROXY_KEY}",
                    "Content-Type": "application/json",
                    "x-expect-json": "true",  # Enable JSON repair
                },
                json={
                    "model": "text",  # Proxy routes to best available provider
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            qa_items = parse_qra_response(content, idx, section_title, source, clean_json_string)
            return idx, qa_items, bool(qa_items)
        except Exception as e:
            log(f"Section {idx} '{section_title[:30]}...' failed: {e}", style="red")
            return idx, [], False


# =============================================================================
# Batch Extraction (httpx + asyncio)
# =============================================================================


async def extract_qra_batch(
    sections: List[Tuple[str, str]],
    source: str = "",
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout: int = DEFAULT_TIMEOUT,
    context: str = None,
) -> List[Dict[str, Any]]:
    """Extract QRA from all sections using parallel httpx calls to scillm proxy.

    The scillm proxy at localhost:4001 handles provider routing and fallbacks.

    Args:
        sections: List of (section_title, section_content) tuples
        source: Source identifier for the content
        concurrency: Max parallel requests (default 6)
        timeout: Per-request timeout in seconds
        context: Optional domain context/persona for focused extraction

    Returns:
        List of QRA dicts with section metadata
    """
    if not sections:
        return []

    if context:
        log(f"Using domain context: {context[:50]}...", style="cyan")

    system_prompt = build_qra_system_prompt(context) if context else QRA_SYSTEM_PROMPT
    semaphore = asyncio.Semaphore(concurrency)
    all_qa: List[Dict[str, Any]] = []
    failed_indices: List[int] = []

    log(f"Batch: {len(sections)} sections, concurrency={concurrency}, timeout={timeout}s")

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [
            _extract_section(client, semaphore, idx, title, content, source, system_prompt)
            for idx, (title, content) in enumerate(sections)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                log(f"Batch task exception: {result}", style="red")
                continue
            idx, qa_items, success = result
            if success:
                all_qa.extend(qa_items)
                log(f"Section {idx} -> {len(qa_items)} QRAs", style="green")
            else:
                failed_indices.append(idx)

    # Heuristic fallback for failures
    if failed_indices:
        log(f"{len(failed_indices)} sections failed, using heuristic fallback", style="yellow")
        for idx in failed_indices:
            qa_pairs = section_heuristic_fallback(sections, idx, source)
            all_qa.extend(qa_pairs)

    log(f"Total QRAs extracted: {len(all_qa)} from {len(sections)} sections", style="bold")
    return all_qa
