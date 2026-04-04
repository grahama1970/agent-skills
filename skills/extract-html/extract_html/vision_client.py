"""vision_client - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import base64
import asyncio
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Wire up scillm (sibling skill) for VLM completions
# ---------------------------------------------------------------------------
_SKILLS_DIR = Path(__file__).resolve().parents[2]
_SCILLM_DIR = str(_SKILLS_DIR / "scillm")
if _SCILLM_DIR not in sys.path:
    sys.path.insert(0, _SCILLM_DIR)

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
    api_base: str,
    api_key: str,
    model: str,
    image_bytes: bytes,
    image_id: str,
    alt: Optional[str],
    timeout: int = 120,
) -> str:
    """
    Calls VLM via scillm acompletion with vision content.
    Routes through /assistant gateway cascade when available.
    Returns extracted text.
    """
    # --- Gateway path: try cascade first ---
    if _gateway_available:
        try:
            import base64 as _b64
            img_b64 = _b64.b64encode(image_bytes).decode("utf-8")
            gw_result = _gw_validate(
                input_data={"image_b64": img_b64, "alt_text": alt or ""},
                task="vision-ocr-extractor",
            )
            if gw_result and gw_result.result:
                text = gw_result.result.get("text", "")
                if text and len(text) > 50:
                    return text
        except Exception as e:
            logger.debug("gateway vision extraction failed, falling through to scillm: {}", e)

    # --- Direct scillm path (fallback) ---
    from scillm import acompletion

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

    resp = await acompletion(
        model=model,
        api_base=api_base,
        api_key=api_key,
        custom_llm_provider="openai_like",
        messages=messages,
        temperature=0,
        timeout=timeout,
    )

    return resp.choices[0].message.content.strip()


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
