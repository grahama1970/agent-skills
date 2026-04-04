"""Plausibility / answerability check microservice.

Persistent FastAPI container that replaces slow `claude -p` subprocess spawns
with a fast HTTP call. Builds the SPARTA answerability prompt internally and
calls an LLM backend (Chutes or scillm) via OpenAI-compatible API.

Endpoint:
    POST /check  -> {"answerable": bool, "reason": str, "clarifying_questions": [...]}
    GET  /health -> {"status": "ok"}
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="plausibility-check",
    description="SPARTA answerability check as a service",
)

# ---------------------------------------------------------------------------
# LLM backend config (from environment)
# ---------------------------------------------------------------------------
SCILLM_BASE_URL = os.getenv("SCILLM_BASE_URL", "http://host.docker.internal:4001/v1")
SCILLM_MODEL = os.getenv("SCILLM_TEXT_MODEL", "text")
SCILLM_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-dev-proxy-123")

CHUTES_API_BASE = os.getenv("CHUTES_API_BASE", "https://llm.chutes.ai/v1")
CHUTES_MODEL = os.getenv("CHUTES_TEXT_MODEL", "deepseek-ai/DeepSeek-V3")
CHUTES_KEY = os.getenv("CHUTES_API_KEY", "")

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class CheckRequest(BaseModel):
    question: str
    not_in_corpus: list[dict[str, Any]] = Field(default_factory=list)
    resolution_map: dict[str, Any] = Field(default_factory=dict)


class CheckResponse(BaseModel):
    answerable: bool
    plausible: bool  # backward compat alias
    reason: str
    clarifying_questions: list[str] = Field(default_factory=list)
    checked: bool = True
    error: Optional[str] = None
    backend: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Prompt builder (extracted from plausibility.py)
# ---------------------------------------------------------------------------
def _build_prompt(
    question: str,
    not_in_corpus: list[dict[str, Any]],
    resolution_map: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    """Build the answerability prompt. Returns (prompt, unmatched, resolved)."""
    unmatched = [w.get("term", "?") for w in not_in_corpus]
    resolved = [
        f"{k} ({v.get('name', k)})"
        for k, v in resolution_map.items()
        if isinstance(v, dict) and v.get("exists")
    ]
    prompt = (
        f"Question: {question}\n\n"
        "EVIDENCE FROM SPARTA CORPUS SEARCH (8,979 controls, space vehicle cybersecurity):\n"
        f"  RESOLVED (confirmed matches): {', '.join(resolved) or 'none'}\n"
        f"  UNRESOLVED (zero hits in entire corpus): {', '.join(unmatched)}\n\n"
        "Given this evidence, is this question ANSWERABLE from the SPARTA corpus?\n\n"
        "CRITICAL RULES:\n"
        "1. RESOLVED terms are CONFIRMED to exist in the corpus. Do NOT reject a question\n"
        "   because a resolved term 'doesn't exist in real life.' If it resolved, it IS in\n"
        "   the dataset and the question CAN be answered from corpus data.\n"
        "2. 'F-36' is a KNOWN datalake entity with thousands of QRAs. If F-36 resolved,\n"
        "   the question is answerable. Do NOT reject F-36 as 'not a real aircraft.'\n"
        "3. UNRESOLVED terms that are common English phrases, sentence fragments, or\n"
        "   generic security concepts (supply chain, countermeasures, injection attacks,\n"
        "   DLL side-loading, dual-engine, weld inspection, formal verification) are\n"
        "   NOT grounds for rejection. Only reject if the unresolved term is a SPECIFIC\n"
        "   fabricated entity (fake control ID, invented technology, fictional subsystem).\n"
        "4. If the question has 2+ resolved entities anchoring it to real controls,\n"
        "   it is almost certainly answerable. Err on the side of answerable=true.\n\n"
        "ANSWERABLE (true) when:\n"
        "- The question has resolved entities that anchor it to SPARTA controls\n"
        "- Unresolved terms are real aerospace/defense/security concepts or hardware\n"
        "- Unresolved terms are common phrases or sentence fragments\n"
        "- The question references F-36 and it resolved in the corpus\n\n"
        "NOT ANSWERABLE (false) when:\n"
        "- The question's premise relies on a SPECIFIC fabricated entity that doesn't\n"
        "  exist (X23-MUSTARD, ZZ-PHANTOM-7, holographic heads-up display, quantum\n"
        "  encryption module, blockchain supply chain ledger, neural interface helmet)\n"
        "- Fabricated control IDs with no match in 8,979 controls\n"
        "- The COMBINATION of terms creates an impossible/absurd scenario (underwater\n"
        "  sonar on an aircraft, Kerberos on DAL-A avionics)\n\n"
        "If NOT answerable, suggest clarifying questions that WOULD be answerable.\n\n"
        "Respond with ONLY a JSON object:\n"
        '{"answerable": true/false, "reason": "...", '
        '"clarifying_questions": ["question that would be answerable"]}'
    )
    return prompt, unmatched, resolved


# ---------------------------------------------------------------------------
# Deterministic gate (fabricated IDs)
# ---------------------------------------------------------------------------
def _check_deterministic(
    not_in_corpus: list[dict[str, Any]],
    resolution_map: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Hard deterministic gates. Returns result if gate fires, None otherwise."""
    id_like = [w for w in not_in_corpus if w.get("type") == "id_like"]
    if id_like:
        terms = [w.get("term", "?") for w in id_like]
        unmatched = [w.get("term", "?") for w in not_in_corpus]
        resolved = [
            k for k, v in resolution_map.items()
            if isinstance(v, dict) and v.get("exists")
        ]
        return {
            "answerable": False,
            "plausible": False,
            "reason": f"Fabricated ID-like terms: {', '.join(terms)}",
            "clarifying_questions": [],
            "checked": True,
            "error": None,
            "backend": "deterministic",
            "evidence": {
                "unmatched_terms": unmatched,
                "resolved_terms": resolved,
                "id_like_unresolved": terms,
            },
            "duration_ms": 0,
        }
    return None


# ---------------------------------------------------------------------------
# LLM call + response parsing
# ---------------------------------------------------------------------------
def _call_llm(url: str, model: str, api_key: str, prompt: str) -> str:
    """OpenAI-compatible chat completion call."""
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if "openrouter.ai" in url:
        body["max_tokens"] = 300
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def _parse_llm_response(
    text: str,
    backend: str,
    unmatched: list[str],
    resolved: list[str],
) -> dict[str, Any]:
    """Parse LLM response into answerability result."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        payload = json.loads(text[start:end])
        answerable = payload.get("answerable", payload.get("plausible"))
        if answerable is not None:
            return {
                "answerable": bool(answerable),
                "plausible": bool(answerable),
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
    if ('"answerable": false' in text_lower
            or '"plausible": false' in text_lower
            or "not answerable" in text_lower):
        return {
            "answerable": False,
            "plausible": False,
            "reason": text[:200],
            "clarifying_questions": [],
            "checked": True,
            "error": None,
            "backend": backend,
            "evidence": {
                "unmatched_terms": unmatched,
                "resolved_terms": resolved,
            },
        }

    raise ValueError(f"unparseable LLM response: {text[:100]}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    backends = []
    if SCILLM_KEY:
        backends.append("scillm")
    if CHUTES_KEY:
        backends.append("chutes")
    if OPENROUTER_KEY:
        backends.append("openrouter")
    return {"status": "ok", "backends": backends}


@app.post("/check", response_model=CheckResponse)
async def check(req: CheckRequest):
    """Check if a question is answerable from the SPARTA corpus."""
    t0 = time.monotonic()

    # No unmatched terms -> answerable, skip LLM
    not_in_corpus = [
        w for w in req.not_in_corpus
        if w.get("category") == "not_in_corpus"
    ]
    if not not_in_corpus:
        return CheckResponse(
            answerable=True,
            plausible=True,
            reason="no unmatched terms",
            checked=False,
            backend="skip",
            duration_ms=0,
        )

    # Deterministic gate (fabricated IDs)
    det = _check_deterministic(not_in_corpus, req.resolution_map)
    if det:
        det["duration_ms"] = int((time.monotonic() - t0) * 1000)
        return CheckResponse(**det)

    # Build prompt
    prompt, unmatched, resolved = _build_prompt(
        req.question, not_in_corpus, req.resolution_map,
    )

    # Try backends in priority order: scillm -> Chutes -> OpenRouter
    backends = []
    if SCILLM_KEY:
        backends.append((
            "scillm",
            f"{SCILLM_BASE_URL}/chat/completions",
            SCILLM_MODEL,
            SCILLM_KEY,
        ))
    if CHUTES_KEY:
        backends.append((
            "chutes",
            f"{CHUTES_API_BASE}/chat/completions",
            CHUTES_MODEL,
            CHUTES_KEY,
        ))
    if OPENROUTER_KEY:
        backends.append((
            "openrouter",
            "https://openrouter.ai/api/v1/chat/completions",
            "anthropic/claude-sonnet-4",
            OPENROUTER_KEY,
        ))

    last_error = None
    for backend_name, url, model, key in backends:
        try:
            text = _call_llm(url, model, key, prompt)
            result = _parse_llm_response(text, backend_name, unmatched, resolved)
            result["duration_ms"] = int((time.monotonic() - t0) * 1000)
            return CheckResponse(**result)
        except Exception as exc:
            last_error = exc
            continue

    # All backends failed -- default answerable
    duration_ms = int((time.monotonic() - t0) * 1000)
    return CheckResponse(
        answerable=True,
        plausible=True,
        reason=f"All backends failed: {last_error}",
        checked=False,
        error=str(last_error)[:200] if last_error else "no backends",
        backend="none",
        duration_ms=duration_ms,
    )
