"""LLM-based single-section QRA extraction for doc2qra skill.

Provides synchronous LLM extraction for individual sections with
gateway fallback and provider chain retry on rate limits.
"""

from __future__ import annotations

import json
from typing import Dict, List

from .config import get_llm_provider_chain
from .qra_gateway import is_gateway_available, _gw_validate, parse_gateway_items
from .qra_heuristic import extract_qa_heuristic
from .qra_prompts import QRA_SYSTEM_PROMPT, QRA_PROMPT
from .utils import clean_json_string, log


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
    # Gateway path: route through /assistant validate()
    if is_gateway_available():
        try:
            gw_result = _gw_validate(
                input_data={
                    "section_title": section_title,
                    "section_content": section_content[:3000],
                },
                task="qra-extraction-from-sections",
            )
            result = parse_gateway_items(gw_result, section_title=section_title)
            if result:
                return result
            log("Gateway returned no items, falling back to direct scillm", style="yellow")
        except Exception as e:
            log(f"Gateway failed, falling back to direct scillm: {e}", style="yellow")

    # Fallback: use provider chain with 429 fallback
    try:
        from scillm import completion
    except ImportError:
        return extract_qa_heuristic(section_content, source, section_title)

    providers = get_llm_provider_chain()
    if not providers:
        return extract_qa_heuristic(section_content, source, section_title)

    prompt = QRA_PROMPT.format(text=section_content[:3000])

    for provider in providers:
        provider_name = provider.get("name", provider["model"][:20])
        try:
            resp = completion(
                model=provider["model"],
                api_base=provider["api_base"],
                api_key=provider["api_key"],
                custom_llm_provider="openai_like",
                messages=[
                    {"role": "system", "content": QRA_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=4096,
                temperature=0.1,
                timeout=30,
            )
            content = resp.choices[0].message.content
            try:
                from scillm.extras.json_utils import clean_json_string as scillm_clean
                content = scillm_clean(content)
            except ImportError:
                content = clean_json_string(content)
            data = json.loads(content)
            items = data.get("items", []) if isinstance(data, dict) else []
            result = []
            for item in items:
                if item.get("question") and item.get("answer"):
                    problem = item["question"]
                    if section_title:
                        problem = f"[{section_title}] {problem}"
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
            error_str = str(e)
            is_429 = "429" in error_str or "rate" in error_str.lower()
            if is_429:
                log(f"LLM [{provider_name}] rate-limited, trying next provider", style="yellow")
                continue
            log(f"LLM [{provider_name}] extraction failed: {e}", style="red")
            continue

    return extract_qa_heuristic(section_content, source, section_title)
