"""Batch QRA extraction via chutes-call gateway — extracted from ingest_website.py."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from loguru import logger

# chutes-call client for batch LLM calls
_CHUTES_CALL_DIR = str(Path(__file__).resolve().parent.parent / "chutes-call")
if _CHUTES_CALL_DIR not in sys.path:
    sys.path.insert(0, _CHUTES_CALL_DIR)
try:
    from client import batch_sync as _chutes_batch_sync
    CHUTES_CALL_AVAILABLE = True
except ImportError:
    _chutes_batch_sync = None  # type: ignore[assignment]
    CHUTES_CALL_AVAILABLE = False

# Memory daemon connection
_MEMORY_SOCKET = f"/run/user/{os.getuid()}/embry/memory.sock"
_MEMORY_HTTP = os.environ.get("MEMORY_SERVICE_URL", "http://127.0.0.1:8601")


def _memory_client() -> httpx.Client:
    """Get httpx client for memory daemon (Unix socket preferred, HTTP fallback)."""
    socket = Path(_MEMORY_SOCKET)
    if socket.exists():
        transport = httpx.HTTPTransport(uds=str(socket))
        return httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)
    return httpx.Client(base_url=_MEMORY_HTTP, timeout=30.0)


# QRA system prompt (from doc2qra/qra_prompts.py — inlined to avoid venv dep)
QRA_SYSTEM_PROMPT = (
    "You are a knowledge extraction assistant. You MUST respond with valid JSON only.\n"
    "Do not include any text before or after the JSON. Do not use markdown code blocks.\n"
    'Return ONLY a JSON object matching this exact schema:\n\n'
    '{"items": [\n'
    '  {"question": "string", "reasoning": "string", "answer": "string"},\n'
    '  ...\n]}\n\n'
    "CRITICAL RULES:\n"
    "- Extract ALL meaningful facts, concepts, and relationships from the text\n"
    "- GROUNDING: Every answer MUST be directly supported by text in the source.\n"
    "- question: A clear, specific question that the text answers\n"
    "- reasoning: Brief explanation of where/how the answer is found in the text\n"
    "- answer: The factual answer, using words from the source text when possible\n"
    "- Include as many items as the text supports (could be 1 to 50+)\n"
    '- If text is too short, garbled, or lacks factual content, return {"items": []}\n'
)


def batch_qra_via_chutes(
    pages: dict[str, str],
    scope: str,
    domain: str,
    progress_cb=None,
) -> tuple[int, dict]:
    """Extract QRAs from all pages via chutes-call batch, then store to memory.

    Args:
        pages: {url: content} dict of extracted page content.
        scope: Memory scope to store in.
        domain: Source domain for tagging.
        progress_cb: Optional callback(page_url, qra_count) per page result.

    Returns:
        (total_qras_stored, stats_dict)
    """
    # Build batch requests — one per page
    requests = []
    page_urls = []
    for page_url, content in pages.items():
        text_sample = content[:3000]
        requests.append({
            "messages": [
                {"role": "system", "content": QRA_SYSTEM_PROMPT},
                {"role": "user", "content": (
                    "Extract all grounded knowledge items from this text. "
                    "Every answer must be supported by the source text.\n\n"
                    f"Text:\n{text_sample}\n\nJSON:"
                )},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
            "temperature": 0.1,
        })
        page_urls.append(page_url)

    logger.info("Sending {} pages to chutes-call /batch for QRA extraction", len(requests))

    # Call chutes-call batch endpoint (synchronous, non-streaming)
    try:
        responses = _chutes_batch_sync(
            requests=requests,
            concurrency=5,
            tenacious=True,
            caller="ingest-website",
        )
    except Exception as exc:
        logger.error("chutes-call batch failed: {}", exc)
        return 0, {"qras": 0, "store_fail": 0}

    # Parse responses and store QRAs to memory
    total_stored = 0
    store_stats: dict = {"qras": 0, "store_fail": 0}
    client = _memory_client()

    try:
        for i, resp in enumerate(responses):
            page_url = page_urls[i] if i < len(page_urls) else f"page_{i}"
            if not resp.ok or not resp.content:
                logger.warning("QRA extraction failed for {}: {}", page_url, resp.error)
                store_stats["store_fail"] += 1
                continue

            # Parse JSON response
            try:
                data = resp.json_content or json.loads(resp.content)
            except (json.JSONDecodeError, TypeError):
                logger.warning("QRA JSON parse failed for {}", page_url)
                store_stats["store_fail"] += 1
                continue

            items = data.get("items", []) if isinstance(data, dict) else []
            if not items:
                continue

            # Store each QRA pair to memory
            page_stored = 0
            tags = [f"source:{domain}", "ingested_web", "qra"]
            for item in items:
                question = item.get("question", "")
                answer = item.get("answer", "")
                reasoning = item.get("reasoning", "")
                if not question or not answer:
                    continue
                solution = f"**Reasoning:** {reasoning}\n\n**Answer:** {answer}" if reasoning else answer
                try:
                    mem_resp = client.post("/learn", json={
                        "problem": question,
                        "solution": solution,
                        "scope": scope,
                        "tags": tags,
                    })
                    if mem_resp.status_code == 200:
                        page_stored += 1
                except Exception as exc:
                    logger.debug("Memory store failed for QRA: {}", exc)

            total_stored += page_stored
            store_stats["qras"] += page_stored
            if progress_cb:
                progress_cb(page_url, page_stored)
    finally:
        client.close()

    return total_stored, store_stats
