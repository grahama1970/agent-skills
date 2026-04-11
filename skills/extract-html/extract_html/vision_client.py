"""vision_client - extract_html.

VLM-based image text extraction using scillm proxy at localhost:4001.
"""

from __future__ import annotations

import base64
import asyncio
import os
from typing import Dict, List, Optional

import httpx
from loguru import logger

# scillm proxy config
SCILLM_API_BASE = os.environ.get("SCILLM_API_BASE", "http://localhost:4001")
SCILLM_PROXY_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

# ---------------------------------------------------------------------------
# Shadow gateway: route through /assistant validate() cascade
# ---------------------------------------------------------------------------
_use_gateway = os.environ.get("EXTRACT_HTML_USE_GATEWAY", "1") == "1"
_gateway_available = False
if _use_gateway:
    try:
        _assistant_dir = str(_SKILLS_DIR / "assistant")
        if _assistant_dir not in sys.path:
            sys.path.insert(0, _assistant_dir)
        from assistant import validate as _gw_validate
        _gateway_available = True
    except ImportError:
        _gateway_available = False


def _b64_data_url(image_bytes: bytes, mime: str) -> str:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _guess_mime(path_or_url: str) -> str:
    p = path_or_url.lower()
    if p.endswith(".png"):
        return "image/png"
    if p.endswith(".jpg") or p.endswith(".jpeg"):
        return "image/jpeg"
    if p.endswith(".webp"):
        return "image/webp"
    if p.endswith(".gif"):
        return "image/gif"
    # fallback; many endpoints accept jpeg
    return "image/jpeg"


async def _vision_one(
    *,
    api_base: str = None,  # Ignored - uses scillm proxy
    api_key: str = None,   # Ignored - uses scillm proxy
    model: str = None,     # Ignored - uses "vlm" via scillm proxy
    image_bytes: bytes,
    image_id: str,
    alt: Optional[str],
    timeout: int = 120,
) -> str:
    """
    Calls VLM via scillm proxy at localhost:4001.
    Uses model="vlm" which routes to the best available VLM provider.
    Returns extracted text.
    """
    mime = _guess_mime(image_id)
    img_url = _b64_data_url(image_bytes, mime)

    prompt = (
        "Extract all readable text from this image. "
        "Preserve tables as plain text rows/columns where possible. "
        "Return ONLY the extracted text (no markdown fences)."
    )
    if alt:
        prompt += f"\nALT TEXT (from HTML): {alt}"

    messages = [
        {"role": "system", "content": "You are a precise OCR+layout extraction engine."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": img_url}},
            ],
        },
    ]

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{SCILLM_API_BASE}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {SCILLM_PROXY_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "vlm",  # Proxy routes to best available VLM provider
                "messages": messages,
                "temperature": 0,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def extract_text_batched(
    *,
    api_base: str,
    api_key: str,
    model: str,
    images: List[dict],
    concurrency: int = 8,
    timeout_s: float = 120.0,
) -> Dict[str, str]:
    """
    images: list of {id, bytes, alt}
    Returns mapping id -> extracted_text
    """
    sem = asyncio.Semaphore(max(1, concurrency))
    results: Dict[str, str] = {}

    async def run_one(img: dict) -> None:
        async with sem:
            try:
                txt = await _vision_one(
                    api_base=api_base,
                    api_key=api_key,
                    model=model,
                    image_bytes=img["bytes"],
                    image_id=img["id"],
                    alt=img.get("alt"),
                    timeout=int(timeout_s),
                )
                results[img["id"]] = txt
            except Exception as e:
                logger.warning("Vision extraction failed for {}: {}", img["id"], e)
                results[img["id"]] = ""

    await asyncio.gather(*(run_one(img) for img in images))

    return results
