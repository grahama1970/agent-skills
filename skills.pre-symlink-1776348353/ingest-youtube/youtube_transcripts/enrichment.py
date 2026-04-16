"""Post-transcript enrichment via scillm proxy (httpx).

Single LLM call to Gemini 3 Flash (1M context) produces summary + QRA pairs
in one structured JSON response. No truncation needed.

The scillm proxy handles fallback cascades, JSON repair, and retries.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

import os

_PROMPT_DIR = Path(__file__).resolve().parent
while _PROMPT_DIR.name != "skills" and _PROMPT_DIR != _PROMPT_DIR.parent:
    _PROMPT_DIR = _PROMPT_DIR.parent
_PROMPT_DIR = _PROMPT_DIR / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()

SCILLM_URL = os.getenv("SCILLM_API_BASE", "http://localhost:4001") + "/v1/chat/completions"
SCILLM_KEY = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")
SCILLM_MODEL = "text-gemini-3"  # Gemini 3 Flash — 1M context for full transcripts
SCILLM_TIMEOUT = 120.0

# ---------------------------------------------------------------------------
# Single unified prompt — summary + QRA in one call
# ---------------------------------------------------------------------------

ENRICHMENT_SYSTEM_PROMPT = _load_prompt("ingest_youtube_enrichment_system_v1")


# ---------------------------------------------------------------------------
# scillm httpx call
# ---------------------------------------------------------------------------

def _call_scillm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 16384,
    temperature: float = 0.1,
) -> Optional[str]:
    """Call scillm proxy via httpx. Returns content string or None."""
    try:
        resp = httpx.post(
            SCILLM_URL,
            headers={"Authorization": f"Bearer {SCILLM_KEY}"},
            json={
                "model": SCILLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=SCILLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            logger.error("scillm returned no choices: {}", list(data.keys()))
            return None
        return choices[0].get("message", {}).get("content")
    except httpx.ConnectError:
        logger.error("scillm proxy not reachable at {}", SCILLM_URL)
        return None
    except httpx.HTTPStatusError as e:
        logger.error("scillm returned {}: {}", e.response.status_code, e.response.text[:200])
        return None
    except Exception as e:
        logger.error("scillm call failed: {}", e)
        return None


# ---------------------------------------------------------------------------
# Transcript text builder
# ---------------------------------------------------------------------------

def _build_transcript_text(
    full_text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Build text with metadata header for context."""
    header_parts = []
    if metadata:
        if metadata.get("title"):
            header_parts.append(f"Title: {metadata['title']}")
        if metadata.get("channel"):
            header_parts.append(f"Channel: {metadata['channel']}")
        if metadata.get("upload_date"):
            date = metadata["upload_date"]
            if len(date) == 8 and date.isdigit():
                date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
            header_parts.append(f"Date: {date}")
        if metadata.get("duration_sec"):
            try:
                dur = int(metadata["duration_sec"])
                header_parts.append(f"Duration: {dur // 60}:{dur % 60:02d}")
            except (ValueError, TypeError):
                pass

    header = "\n".join(header_parts)
    if header:
        return f"{header}\n\n{full_text}"
    return full_text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_transcript(
    full_text: str,
    metadata: Optional[Dict[str, Any]] = None,
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """Enrich a transcript with summary + QRA pairs in a single LLM call.

    Uses Gemini 3 Flash (1M context) via scillm — sends the full transcript
    with no truncation and gets back structured JSON with summary and QRA items.

    Args:
        full_text: Raw transcript text.
        metadata: Video metadata (title, channel, upload_date, duration_sec).
        context: Optional domain context for focused extraction.

    Returns:
        Dict with 'summary' (str) and 'qra' (list of dicts) keys.
        Empty values if scillm is unreachable.
    """
    if not full_text.strip():
        return {"summary": "", "qra": []}

    enriched_text = _build_transcript_text(full_text, metadata)

    system = ENRICHMENT_SYSTEM_PROMPT
    if context:
        system = f"You are a {context}.\n\n{system}"

    user_prompt = (
        "Analyze this transcript. Produce a summary and extract all grounded "
        "knowledge items. Every answer must be supported by the source text.\n\n"
        f"Transcript:\n{enriched_text}\n\nJSON:"
    )

    result = _call_scillm(system, user_prompt)

    if not result:
        logger.warning("Enrichment failed — scillm unreachable")
        return {"summary": "", "qra": []}

    try:
        data = json.loads(result)
    except json.JSONDecodeError as e:
        logger.error("Enrichment JSON parse failed: {}", e)
        return {"summary": "", "qra": []}

    summary = data.get("summary", "").strip()

    items = data.get("items", [])
    normalized: List[Dict[str, str]] = []
    for item in items:
        q = item.get("question", "").strip()
        a = item.get("answer", "").strip()
        r = item.get("reasoning", "").strip()
        if q and a:
            normalized.append({"question": q, "answer": a, "rationale": r})

    logger.info(
        "Enrichment complete: {} char summary, {} QRA pairs",
        len(summary), len(normalized),
    )
    return {"summary": summary, "qra": normalized}
