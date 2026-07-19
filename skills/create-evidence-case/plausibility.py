"""Answerability check for evidence cases.

Given all collected evidence (entity extraction, QRA recall, resolution map),
determine whether a question is answerable from the SPARTA corpus.

Two modes:

  1. Interactive (agent in loop): Deterministic code returns evidence.
     The agent (Claude Code) reads the evidence and decides.

  2. Headless batch: LLM call for questions where not_in_corpus evidence
     exists. The LLM reads the evidence and decides answerability.

If NOT answerable, the LLM provides:
  - A rationale explaining why
  - Clarifying questions for /memory clarify and the next conversation turn

Deterministic gates (always applied, no LLM needed):
  - fabricated_id: ID-like term with no exact match in sparta_controls

LLM backend: scillm proxy (localhost:4001) → Gemini Flash directly.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True), override=False)

SCILLM_BASE = os.getenv("SCILLM_API_BASE", "http://localhost:4001")
SCILLM_PLAUSIBILITY_MODEL = os.getenv("SCILLM_PLAUSIBILITY_MODEL", "gemini-flash")


def _check_deterministic(
    not_in_corpus: list[dict[str, Any]],
    resolution_map: dict[str, Any],
) -> dict[str, Any] | None:
    """Hard deterministic gates. Returns result if gate fires, None otherwise."""
    unmatched = [w.get("term", "?") for w in not_in_corpus]
    resolved = [
        k for k, v in resolution_map.items()
        if isinstance(v, dict) and v.get("exists")
    ]

    # Gate 1: Fabricated ID-like terms (X23-MUSTARD, ZZ-PHANTOM-7)
    id_like = [w for w in not_in_corpus if w.get("type") == "id_like"]
    if id_like:
        terms = [w.get("term", "?") for w in id_like]
        return {
            "plausible": False,
            "reason": f"Fabricated ID-like terms: {', '.join(terms)}",
            "checked": True,
            "error": None,
            "backend": "deterministic",
            "evidence": {
                "unmatched_terms": unmatched,
                "resolved_terms": resolved,
                "id_like_unresolved": terms,
            },
        }

    return None


def _build_prompt(
    question: str,
    not_in_corpus: list[dict[str, Any]],
    resolution_map: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    """Build the answerability prompt and return (prompt, unmatched, resolved)."""
    unmatched = [w.get("term", "?") for w in not_in_corpus]
    resolved = [
        f"{k} ({v.get('name', k)})"
        for k, v in resolution_map.items()
        if isinstance(v, dict) and v.get("exists")
    ]
    prompt = (
        f"Question: {question}\n\n"
        "EVIDENCE FROM SPARTA CORPUS SEARCH (8,979 controls, space vehicle cybersecurity):\n"
        f"  IN CORPUS (confirmed via PHRASE match, {len(resolved)} total): {', '.join(resolved) or 'none'}\n"
        f"  NOT IN CORPUS (zero phrase hits, {len(unmatched)} total): {', '.join(unmatched) or 'none'}\n\n"
        "Is this question ANSWERABLE using ONLY data in the SPARTA corpus?\n\n"
        "IMPORTANT: The IN CORPUS and NOT IN CORPUS lists above are EXHAUSTIVE search results.\n"
        "Do NOT independently judge whether terms exist — trust ONLY the evidence above.\n"
        "If the NOT IN CORPUS list says 'none', then ALL terms were found. Answer: answerable.\n\n"
        "RULES:\n"
        "1. NOT IN CORPUS list is 'none' or empty → answerable. No further analysis needed.\n"
        "2. ANY term in NOT IN CORPUS list → not answerable. Must clarify.\n"
        "3. When not answerable, suggest a clarifying question using ONLY terms that ARE in corpus.\n"
        "   Example: 'FADEC is not in our SPARTA corpus. Did you mean to ask about\n"
        "   flight control system countermeasures using SV-CF-1?'\n\n"
        "Respond with ONLY a JSON object:\n"
        '{"answerable": true/false, "reason": "...", '
        '"clarifying_questions": ["question using only corpus terms"]}'
    )
    return prompt, unmatched, resolved


def _parse_llm_response(text: str, backend: str, unmatched: list[str], resolved: list[str]) -> dict[str, Any]:
    """Parse LLM response into answerability result."""
    import re
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        payload = json.loads(text[start:end])
        # Accept both "answerable" (new) and "plausible" (legacy) keys
        answerable = payload.get("answerable", payload.get("plausible"))
        if answerable is not None:
            return {
                "answerable": bool(answerable),
                "plausible": bool(answerable),  # backward compat
                "reason": str(payload.get("reason", "")),
                "clarifying_questions": payload.get("clarifying_questions", []),
                "checked": True,
                "error": None,
                "backend": backend,
                "evidence": {
                    "unmatched_terms": unmatched,
                    "resolved_terms": resolved,
                },
            }

    text_lower = text.lower()
    if '"answerable": false' in text_lower or '"plausible": false' in text_lower or "not answerable" in text_lower:
        return {
            "answerable": False,
            "plausible": False,
            "reason": text[:200],
            "clarifying_questions": [],
            "checked": True,
            "error": None,
            "backend": backend,
        }

    raise ValueError(f"unparseable: {text[:100]}")


def _call_scillm(prompt: str, model: str | None = None) -> str:
    """Call scillm Docker proxy for a single-shot plausibility decision.

    POST to localhost:4001 (Section B paved path). The proxy handles
    retries and JSON validation internally.
    """
    model = model or SCILLM_PLAUSIBILITY_MODEL
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }).encode()
    from runner import resolve_scillm_api_key

    req = urllib.request.Request(
        f"{SCILLM_BASE}/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {resolve_scillm_api_key()}",
            "X-Caller-Skill": "create-evidence-case",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"scillm malformed response: {exc} — {json.dumps(data)[:300]}") from exc
    if not text:
        raise RuntimeError(f"scillm returned empty response: {json.dumps(data)[:200]}")
    return text


def _check_llm_headless(
    question: str,
    not_in_corpus: list[dict[str, Any]],
    resolution_map: dict[str, Any],
) -> dict[str, Any]:
    """Headless LLM call for plausibility decision via scillm proxy.

    Primary: Gemini Flash via scillm (94.4% accuracy on 36 fixtures).
    Fallback: scillm text cascade (Chutes → DeepSeek → Gemini).
    Default: answerable=True when all backends fail.
    """
    prompt, unmatched, resolved = _build_prompt(question, not_in_corpus, resolution_map)

    # Primary: Gemini Flash directly via scillm
    try:
        text = _call_scillm(prompt)
        return _parse_llm_response(text, f"scillm:{SCILLM_PLAUSIBILITY_MODEL}", unmatched, resolved)
    except Exception as exc:
        logger.debug("scillm {} failed: {}", SCILLM_PLAUSIBILITY_MODEL, exc)

    # Fallback: the configured free Gemini deployment.
    try:
        text = _call_scillm(prompt, model="gemini-flash-free2")
        return _parse_llm_response(text, "scillm:gemini-flash-free2", unmatched, resolved)
    except Exception as exc:
        logger.debug("scillm text cascade failed: {}", exc)

    logger.warning("All plausibility backends failed")
    return {"answerable": True, "plausible": True, "checked": False, "reason": "all backends failed", "error": "all backends failed", "backend": "none"}


def check_plausibility(
    question: str,
    entity_warnings: list[dict[str, Any]],
    resolution_map: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    """Check if question is answerable given collected evidence.

    1. Clean questions (no not_in_corpus) → answerable, skip (unless force=True).
    2. Deterministic gates fire first (fabricated IDs) → not answerable.
    3. LLM reads evidence and decides answerability.
       If not answerable, LLM provides rationale + clarifying questions
       for /memory clarify and the next conversation turn.

    Args:
        force: If True, always consult the LLM even without not_in_corpus
               warnings. Used when caller detects weak resolution that
               entity extraction didn't flag.
    """
    not_in_corpus = [
        w for w in entity_warnings
        if w.get("category") == "not_in_corpus"
    ]
    if not not_in_corpus and not force:
        return {"answerable": True, "plausible": True, "checked": False, "reason": "no unmatched terms"}

    # Deterministic gate
    if not_in_corpus:
        det = _check_deterministic(not_in_corpus, resolution_map)
        if det:
            return det

    # Agent reads evidence and decides answerability
    return _check_llm_headless(question, not_in_corpus, resolution_map)
