"""Cosine similarity between page image and extracted text embeddings via multimodal backend."""

from __future__ import annotations

import base64
import math
from pathlib import Path

import httpx

from .render import render_page, crop_element, render_and_crop_elements
from loguru import logger

_MM_URL = "http://localhost:8603"
_MODEL = "Qwen/Qwen3-VL-Embedding-2B"
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def embed_text_multimodal(text: str) -> list[float] | None:
    """Embed text via the Qwen3-VL multimodal backend (2048d)."""
    try:
        r = httpx.post(f"{_MM_URL}/v1/embeddings", json={"model": _MODEL, "input": [text]}, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except Exception as e:
        logger.warning("embed_text_multimodal failed: {}", e)
        return None


def embed_image(image_path: Path) -> list[float] | None:
    """Embed a PNG image via Qwen3-VL pooling endpoint, mean-pooling token vectors."""
    try:
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        payload = {
            "model": _MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]}],
        }
        r = httpx.post(f"{_MM_URL}/pooling", json=payload, timeout=_TIMEOUT)
        r.raise_for_status()
        tokens = r.json()["data"][0]["data"]
        n = len(tokens)
        if n == 0:
            return None
        return [sum(col) / n for col in zip(*tokens)]
    except Exception as e:
        logger.warning("embed_image failed for {}: {}", image_path, e)
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Standard cosine similarity: dot(a,b) / (||a|| * ||b||)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def visual_score(image_path: Path, extracted_text: str) -> float:
    """Cosine similarity between page image and extracted text in multimodal space."""
    img_vec = embed_image(image_path)
    txt_vec = embed_text_multimodal(extracted_text)
    if img_vec is None or txt_vec is None:
        return 0.0
    return cosine_similarity(img_vec, txt_vec)


def score_extraction(pages: list[dict], extracted_sections: list[dict]) -> float:
    """Mean visual_score across pages that have images.

    Args:
        pages: dicts with "image_path" (str/Path) and optionally "page_num" (int).
        extracted_sections: dicts with "text" (str) and optionally "page" (int).
    """
    scores: list[float] = []
    for page in pages:
        ip = page.get("image_path")
        if not ip:
            continue
        ip = Path(ip)
        if not ip.exists():
            continue
        pn = page.get("page_num")
        if pn is not None:
            text = " ".join(s["text"] for s in extracted_sections if s.get("page") == pn and s.get("text"))
        else:
            text = " ".join(s["text"] for s in extracted_sections if s.get("text"))
        if not text.strip():
            continue
        scores.append(visual_score(ip, text))
    return sum(scores) / len(scores) if scores else 0.0


def verify_element(pdf_path: Path, page_num: int, bbox: tuple, extracted_text: str, page_height: float) -> float:
    """Verify a single element by comparing its cropped image to extracted text."""
    page_img = render_page(pdf_path, page_num)
    crop_path = crop_element(page_img, bbox, page_height)
    img_vec = embed_image(crop_path)
    txt_vec = embed_text_multimodal(extracted_text)
    if img_vec is None or txt_vec is None:
        return 0.0
    return cosine_similarity(img_vec, txt_vec)


def verify_page(pdf_path: Path, page_num: int, blocks: list[dict], page_height: float) -> list[dict]:
    """Verify all blocks on a page by comparing cropped images to extracted text."""
    elements = render_and_crop_elements(pdf_path, page_num, blocks, page_height)
    results = []
    for el in elements:
        score = 0.0
        if el["image_path"] and el.get("text", "").strip():
            img_vec = embed_image(Path(el["image_path"]))
            txt_vec = embed_text_multimodal(el["text"])
            if img_vec is not None and txt_vec is not None:
                score = cosine_similarity(img_vec, txt_vec)
        results.append({"block_type": el["block_type"], "text": el.get("text", "")[:60],
                         "bbox": el["bbox"], "visual_score": score, "image_path": el["image_path"]})
    return results


def verify_document(pdf_path: Path, extraction: dict, max_pages: int = 5) -> dict:
    """Verify extraction quality across pages using visual-text cosine similarity."""
    page_scores, all_low, total = [], [], 0
    for page in extraction.get("pages", [])[:max_pages]:
        page_num = page.get("page_num", 0)
        page_height = page.get("height", 792.0)
        blocks = page.get("blocks", [])
        verified = verify_page(Path(pdf_path), page_num, blocks, page_height)
        scores = [v["visual_score"] for v in verified if v["visual_score"] > 0]
        page_scores.append(sum(scores) / len(scores) if scores else 0.0)
        all_low.extend(v for v in verified if v["visual_score"] < 0.5)
        total += len(verified)
    mean = sum(page_scores) / len(page_scores) if page_scores else 0.0
    return {"page_scores": page_scores, "mean_score": mean, "low_confidence": all_low, "total_elements": total}
