"""LLM-based single-section QRA extraction for doc2qra skill.

Provides synchronous LLM extraction for individual sections with
gateway fallback and scillm proxy at localhost:4001.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List

import httpx

from .qra_gateway import is_gateway_available, _gw_validate, parse_gateway_items  # noqa: F401 - used in gateway path
from .qra_heuristic import extract_qa_heuristic
from .qra_prompts import QRA_SYSTEM_PROMPT, QRA_PROMPT
from .utils import clean_json_string, log

# scillm proxy config
SCILLM_API_BASE = os.environ.get("SCILLM_API_BASE", "http://localhost:4001")
SCILLM_PROXY_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")


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

    # Fallback: call scillm proxy at localhost:4001
    prompt = QRA_PROMPT.format(text=section_content[:3000])

    try:
        resp = httpx.post(
            f"{SCILLM_API_BASE}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {SCILLM_PROXY_KEY}",
                "X-Caller-Skill": "doc2qra",
                "Content-Type": "application/json",
                "x-expect-json": "true",  # Enable JSON repair
            },
            json={
                "model": "text",  # Proxy routes to best available provider
                "messages": [
                    {"role": "system", "content": QRA_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        content = clean_json_string(content)
        parsed = json.loads(content)
        items = parsed.get("items", []) if isinstance(parsed, dict) else []
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
        log(f"scillm proxy call failed: {e}", style="red")
        return extract_qa_heuristic(section_content, source, section_title)
