"""Gateway-based QRA extraction for doc2qra skill.

Routes QRA extraction through the /assistant validate() shadow method
when available. Provides the gateway tier used by both direct extraction
and the cascade runner.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Tuple

from .qra_heuristic import section_heuristic_fallback
from .utils import log


# ---------------------------------------------------------------------------
# Shadow method gateway: route through /assistant validate() when available
# ---------------------------------------------------------------------------
_use_gateway = os.environ.get("DOC2QRA_USE_GATEWAY", "1") == "1"
_gateway_available = False
_gw_validate = None
if _use_gateway:
    try:
        # Resolve assistant skill dir: sibling of doc2qra in the skills directory
        _skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _assistant_dir = os.path.join(_skills_dir, "assistant")
        if os.path.isdir(_assistant_dir) and _assistant_dir not in sys.path:
            sys.path.insert(0, _assistant_dir)
        from assistant import validate as _gw_validate
        _gateway_available = True
    except ImportError:
        _gateway_available = False


def is_gateway_available() -> bool:
    """Return whether the /assistant gateway is available."""
    return _gateway_available


def parse_gateway_items(gw_result, section_idx=None, section_title="", source=""):
    """Parse gateway TierResult into QRA dicts.

    Shared helper used by extract_qra_llm, extract_qra_gateway, and cascade tiers.

    Args:
        gw_result: TierResult from /assistant validate()
        section_idx: Optional section index for metadata
        section_title: Section title for prefixing questions
        source: Source identifier

    Returns:
        List of QRA dicts
    """
    items = gw_result.result.get("items", []) if isinstance(gw_result.result, dict) else []
    if isinstance(gw_result.result, dict) and not items:
        if gw_result.result.get("question"):
            items = [gw_result.result]
    qa_items = []
    for item in items:
        if item.get("question") and item.get("answer"):
            problem = item["question"]
            if section_title:
                problem = f"[{section_title}] {problem}"
            reasoning = item.get("reasoning", "")
            answer = item["answer"]
            solution = f"**Reasoning:** {reasoning}\n\n**Answer:** {answer}" if reasoning else answer
            entry = {"problem": problem, "solution": solution, "reasoning": reasoning, "answer": answer}
            if section_idx is not None:
                entry.update({"section_idx": section_idx, "section_title": section_title, "source": source, "type": "text"})
            qa_items.append(entry)
    return qa_items


def extract_qra_gateway(
    sections: List[Tuple[str, str]],
    source: str = "",
) -> List[Dict[str, Any]]:
    """Extract QRAs by routing each section through /assistant gateway.

    Separated from extract_qra_batch to enable independent cascade tier usage.

    Args:
        sections: List of (section_title, section_content) tuples
        source: Source identifier

    Returns:
        List of QRA dicts with section metadata, or empty list if gateway unavailable
    """
    if not _gateway_available:
        return []

    log(f"Gateway: routing {len(sections)} sections through /assistant cascade")
    all_qa: List[Dict[str, Any]] = []
    gw_ok = 0

    for idx, (section_title, section_content) in enumerate(sections):
        try:
            gw_result = _gw_validate(
                input_data={
                    "section_title": section_title,
                    "section_content": section_content[:3000],
                },
                task="qra-extraction-from-sections",
            )
            qa_items = parse_gateway_items(gw_result, section_idx=idx, section_title=section_title, source=source)
            if qa_items:
                all_qa.extend(qa_items)
                gw_ok += 1
                log(f"[{idx+1}/{len(sections)}] '{section_title[:30]}...' -> {len(qa_items)} QRAs (gateway)", style="green")
            else:
                qa_pairs = section_heuristic_fallback(sections, idx, source)
                all_qa.extend(qa_pairs)
                log(f"[{idx+1}/{len(sections)}] '{section_title[:30]}...' -> heuristic fallback", style="yellow")
        except Exception as e:
            log(f"[{idx+1}/{len(sections)}] Gateway error: {e}, heuristic fallback", style="yellow")
            qa_pairs = section_heuristic_fallback(sections, idx, source)
            all_qa.extend(qa_pairs)

    log(f"Gateway batch complete: {gw_ok}/{len(sections)} ok, {len(all_qa)} total QRAs", style="bold")
    return all_qa
