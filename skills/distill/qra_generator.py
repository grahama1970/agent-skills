#!/usr/bin/env python3
"""QRA (Question, Reasoning, Answer) generation for distill skill.

Provides:
- LLM-based QRA extraction with scillm batch processing
- Heuristic fallback extraction
- Grounding validation to filter hallucinations
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Tuple

from .config import (
    DEFAULT_BATCH_TIMEOUT,
    DEFAULT_CONCURRENCY,
    DEFAULT_GROUNDING_THRESHOLD,
    DEFAULT_TIMEOUT,
    get_scillm_config,
)
from .utils import clean_json_string, log
from .text_handler import split_sentences


# =============================================================================
# QRA Prompts
# =============================================================================


def build_qra_system_prompt(context: str = None) -> str:
    """Build QRA system prompt with optional domain context.

    Args:
        context: Optional domain context/persona for focused extraction

    Returns:
        System prompt string
    """
    base_prompt = """You are a knowledge extraction assistant. You MUST respond with valid JSON only.
Do not include any text before or after the JSON. Do not use markdown code blocks.
Return ONLY a JSON object matching this exact schema:

{{"items": [
  {{"question": "string", "reasoning": "string", "answer": "string"}},
  ...
]}}

CRITICAL RULES:
- Extract ALL meaningful facts, concepts, and relationships from the text
- GROUNDING: Every answer MUST be directly supported by text in the source. Do NOT hallucinate.
- question: A clear, specific question that the text answers
- reasoning: Brief explanation of where/how the answer is found in the text
- answer: The factual answer, using words from the source text when possible
- Include as many items as the text supports (could be 1 to 50+)
- If text is too short, garbled, or lacks factual content, return {{"items": []}}
- Prefer extracting: definitions, methods, results, comparisons, key findings
"""

    if context:
        context_section = f"""You are a {context}.

Extract knowledge items that are relevant to your expertise and domain.
Skip content that is outside your area of focus.
Prioritize information that would be valuable to someone with your background.

"""
        return context_section + base_prompt

    return base_prompt


# Default prompt (no context)
QRA_SYSTEM_PROMPT = build_qra_system_prompt()

QRA_PROMPT = """Extract all grounded knowledge items from this text. Every answer must be supported by the source text.

Text:
{text}

JSON:"""


# =============================================================================
# QRA Extraction - LLM Based
# =============================================================================


def extract_qra_llm(
    section_content: str,
    source: str = "",
    section_title: str = "",
) -> List[Dict[str, str]]:
    """Extract QRA (Question, Reasoning, Answer) triplets using LLM.

    Args:
        section_content: Text content to extract from
        source: Source identifier
        section_title: Title of the section

    Returns:
        List of QRA dicts with problem, solution, reasoning, answer keys
    """
    try:
        from scillm import completion
        from scillm.extras.json_utils import clean_json_string as scillm_clean
    except ImportError:
        return extract_qa_heuristic(section_content, source, section_title)

    config = get_scillm_config()
    prompt = QRA_PROMPT.format(text=section_content[:3000])  # Limit input size

    try:
        resp = completion(
            model=config["model"],
            messages=[{"role": "user", "content": prompt}],
            api_base=config["api_base"],
            api_key=config["api_key"],
            timeout=30,
        )
        content = resp.choices[0].message.content or ""
        content = scillm_clean(content)
        data = json.loads(content)
        items = data.get("items", [])
        result = []
        for item in items:
            if item.get("question") and item.get("answer"):
                problem = item["question"]
                if section_title:
                    problem = f"[{section_title}] {problem}"
                # Combine reasoning + answer for solution
                reasoning = item.get("reasoning", "")
                answer = item["answer"]
                if reasoning:
                    solution = f"**Reasoning:** {reasoning}\n\n**Answer:** {answer}"
                else:
                    solution = answer
                result.append({
                    "problem": problem,
                    "solution": solution,
                    "reasoning": reasoning,
                    "answer": answer,
                })
        return result
    except Exception as e:
        log(f"LLM extraction failed: {e}", style="red")
        return extract_qa_heuristic(section_content, source, section_title)


# Legacy alias
extract_qa_llm = extract_qra_llm


# =============================================================================
# QRA Extraction - Batch Processing
# =============================================================================


async def extract_qra_batch(
    sections: List[Tuple[str, str]],
    source: str = "",
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout: int = DEFAULT_TIMEOUT,
    context: str = None,
) -> List[Dict[str, Any]]:
    """Extract QRA from all sections using parallel LLM calls.

    Uses scillm batch_acompletions_iter for streaming progress.
    Per SCILLM_PAVED_PATH_CONTRACT.md - logs each section as it completes.

    Args:
        sections: List of (section_title, section_content) tuples
        source: Source identifier for the content
        concurrency: Max parallel requests (default 6)
        timeout: Per-request timeout in seconds
        context: Optional domain context/persona for focused extraction

    Returns:
        List of QRA dicts with section metadata
    """
    config = get_scillm_config()

    if not config["api_key"]:
        log("CHUTES_API_KEY not set, falling back to heuristic extraction", style="yellow")
        return _fallback_heuristic_extraction(sections, source)

    # Try to import scillm batch functions - check multiple locations
    batch_acompletions_iter = None
    scillm_clean_json = None

    try:
        # Try local scillm fork first (preferred)
        from scillm.batch import parallel_acompletions_iter as batch_acompletions_iter
        from scillm.extras.json_utils import clean_json_string as scillm_clean_json
    except ImportError:
        try:
            # Try main scillm module
            from scillm import batch_acompletions_iter
            from scillm.extras.json_utils import clean_json_string as scillm_clean_json
        except ImportError:
            pass

    if batch_acompletions_iter is None:
        log("scillm not available, falling back to heuristic extraction", style="yellow")
        return _fallback_heuristic_extraction(sections, source)

    # Use our fallback if scillm's json utils not available
    clean_fn = scillm_clean_json if scillm_clean_json else clean_json_string

    # Build batch requests - per SCILLM contract, model goes INSIDE each request dict
    requests = []
    metadata = []  # Parallel array for section metadata

    # Use system prompt for strict JSON schema enforcement
    system_prompt = build_qra_system_prompt(context) if context else QRA_SYSTEM_PROMPT
    system_msg = {"role": "system", "content": system_prompt}
    if context:
        log(f"Using domain context: {context[:50]}...", style="cyan")

    for idx, (section_title, section_content) in enumerate(sections):
        user_prompt = QRA_PROMPT.format(text=section_content[:3000])
        requests.append({
            "model": config["model"],
            "messages": [system_msg, {"role": "user", "content": user_prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
            "temperature": 0.1,
        })
        metadata.append({"idx": idx, "title": section_title})

    log(f"Batch: {len(requests)} sections, concurrency={concurrency}, model={config['model'][:40]}")

    all_qa: List[Dict[str, Any]] = []
    done = ok = err = 0

    try:
        async for ev in batch_acompletions_iter(
            requests,
            api_base=config["api_base"],
            api_key=config["api_key"],
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
                    qa_items = _parse_qra_response(
                        ev["content"], section_idx, section_title, source, clean_fn
                    )
                    if qa_items:
                        all_qa.extend(qa_items)
                        log(f"[{done}/{len(requests)}] '{section_title[:30]}...' -> {len(qa_items)} QRAs", style="green")
                    else:
                        qa_pairs = _section_heuristic_fallback(sections, section_idx, source)
                        all_qa.extend(qa_pairs)
                        log(f"[{done}/{len(requests)}] '{section_title[:30]}...' -> empty parse, heuristic fallback", style="yellow")
                except Exception as parse_err:
                    err += 1
                    log(f"[{done}/{len(requests)}] '{section_title[:30]}...' -> {parse_err}", style="red")
                    qa_pairs = _section_heuristic_fallback(sections, section_idx, source)
                    all_qa.extend(qa_pairs)
            else:
                err += 1
                status = ev.get("status", "unknown")
                error = str(ev.get("error", ""))[:50]
                log(f"[{done}/{len(requests)}] '{section_title[:30]}...' -> {status} {error}", style="red")
                qa_pairs = _section_heuristic_fallback(sections, section_idx, source)
                all_qa.extend(qa_pairs)

        log(f"Batch complete: {ok} ok, {err} errors, {len(all_qa)} total QRAs", style="bold")

    except Exception as e:
        log(f"Batch extraction failed: {e}, falling back to heuristic", style="red")
        return _fallback_heuristic_extraction(sections, source)

    return all_qa


def _parse_qra_response(
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
# QRA Extraction - Heuristic Fallback
# =============================================================================


def extract_qa_heuristic(
    section_content: str,
    source: str = "",
    section_title: str = "",
) -> List[Dict[str, str]]:
    """Heuristic Q&A extraction from a section.

    Uses section title as question context, content as answer.

    Args:
        section_content: Text content to extract from
        source: Source identifier
        section_title: Title of the section

    Returns:
        List of QA dicts with problem and solution keys
    """
    content = section_content.strip()
    if not content:
        return []

    # Build problem from section title or first sentence
    if section_title:
        # Section title tells us what this is about
        problem = f"What is {section_title}?" if not section_title.endswith("?") else section_title
    else:
        # Use first sentence as context
        sents = split_sentences(content)
        problem = sents[0][:200] if sents else "Unknown topic"

    # Add source prefix
    if source:
        problem = f"[{source}] {problem}"

    # Solution is the section content (truncated if needed)
    solution = content[:1000] if len(content) > 1000 else content

    return [{"problem": problem, "solution": solution}]


def _section_heuristic_fallback(
    sections: List[Tuple[str, str]],
    section_idx: int,
    source: str,
) -> List[Dict[str, Any]]:
    """Heuristic fallback for a single failed section.

    Args:
        sections: Full sections list
        section_idx: Index of failed section
        source: Source identifier

    Returns:
        List of QA dicts with section metadata
    """
    title, content = sections[section_idx]
    qa_pairs = extract_qa_heuristic(content, source=source, section_title=title)
    for qa in qa_pairs:
        qa["section_idx"] = section_idx
        qa["section_title"] = title
        qa["source"] = source
        qa["type"] = "text"
    return qa_pairs


def _fallback_heuristic_extraction(
    sections: List[Tuple[str, str]],
    source: str,
) -> List[Dict[str, Any]]:
    """Full heuristic fallback when batch fails.

    Args:
        sections: List of (title, content) tuples
        source: Source identifier

    Returns:
        List of QA dicts with section metadata
    """
    all_qa = []
    for idx, (title, content) in enumerate(sections):
        qa_pairs = extract_qa_heuristic(content, source=source, section_title=title)
        for qa in qa_pairs:
            qa["section_idx"] = idx
            qa["section_title"] = title
            qa["source"] = source
            qa["type"] = "text"
        all_qa.extend(qa_pairs)
    return all_qa


# Re-export grounding functions from dedicated module for backwards compatibility
from .grounding import check_grounding, validate_and_filter_qras
