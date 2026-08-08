"""Nearest-real-slide layout retrieval over the author's deck corpus (#1315).

The house corpus is consistent by construction — the same author, chrome, and
layout habits across five decks — which makes it a pattern-recognition target
rather than something to imitate by hand. This module indexes every REAL slide
(rendered PNG + title text + a measured layout signature) into Qdrant using the
same multimodal embedder ``visual_sync`` already uses, then answers: "which of
the author's real slides is closest to the slide I need?" and returns that
slide's measured geometry to compile against.

Inputs: the PPTX corpus directory and its rendered PNGs. Outputs: LayoutSignature
records (fractional zones, deterministic from the PPTX) and retrieval hits with
cosine scores. Failure modes: a missing render or an unreachable embedder raises
with the endpoint visible — retrieval never silently falls back to invented
geometry, because a made-up layout is exactly the failure this module exists to
prevent.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Literal

import httpx
from pydantic import Field

from .house_spec import EMU_PER_INCH
from .models import StrictModel
from .visual_sync import EMBED_URL, HTTP_TIMEOUT, QDRANT_URL, VECTOR_SIZE

HOUSE_COLLECTION = "pitchdeck_house_slides_v1"


class LayoutBlock(StrictModel):
    kind: Literal["text", "picture", "shape"]
    x: float
    y: float
    w: float
    h: float
    words: int = 0


class LayoutSignature(StrictModel):
    """Measured structure of ONE real slide — the thing worth copying."""

    schema_: Literal["pitchdeck.layout_signature.v1"] = Field(
        default="pitchdeck.layout_signature.v1", alias="schema"
    )
    deck: str
    slide_index: int
    title: str
    blocks: list[LayoutBlock]
    picture_count: int
    text_block_count: int
    total_words: int

    @property
    def structure_key(self) -> str:
        return f"{self.text_block_count}t{self.picture_count}p"


def extract_signatures(decks_dir: Path) -> list[LayoutSignature]:
    """Measure every slide in the corpus (deterministic; no rendering needed)."""
    from pptx import Presentation

    signatures: list[LayoutSignature] = []
    for deck in sorted(decks_dir.glob("*.pptx")):
        presentation = Presentation(str(deck))
        width_in = presentation.slide_width / EMU_PER_INCH
        height_in = presentation.slide_height / EMU_PER_INCH
        for index, slide in enumerate(presentation.slides, start=1):
            blocks: list[LayoutBlock] = []
            title = ""
            for shape in slide.shapes:
                try:
                    x = shape.left / EMU_PER_INCH / width_in
                    y = shape.top / EMU_PER_INCH / height_in
                    w = shape.width / EMU_PER_INCH / width_in
                    h = shape.height / EMU_PER_INCH / height_in
                except (TypeError, AttributeError, ZeroDivisionError):
                    continue
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and w > 0 and h > 0):
                    continue
                is_picture = shape.shape_type is not None and "PICTURE" in str(shape.shape_type)
                text = shape.text_frame.text.strip() if shape.has_text_frame else ""
                if is_picture:
                    kind = "picture"
                elif text:
                    kind = "text"
                else:
                    kind = "shape"
                if kind == "text" and not title and y < 0.25 and 2 <= len(text.split()) <= 14:
                    title = " ".join(text.split())
                blocks.append(
                    LayoutBlock(
                        kind=kind,
                        x=round(x, 4), y=round(y, 4), w=round(w, 4), h=round(h, 4),
                        words=len(text.split()),
                    )
                )
            signatures.append(
                LayoutSignature(
                    deck=deck.stem,
                    slide_index=index,
                    title=title,
                    blocks=blocks,
                    picture_count=sum(1 for b in blocks if b.kind == "picture"),
                    text_block_count=sum(1 for b in blocks if b.kind == "text"),
                    total_words=sum(b.words for b in blocks),
                )
            )
    if not signatures:
        raise ValueError(f"no slides measured under {decks_dir}")
    return signatures


def _embed(client: httpx.Client, *, text: str | None = None, image: Path | None = None) -> list[float]:
    # Service contract (embry-embedding-mm /embed): `text` plus optional
    # `image_b64` — the same call visual_sync already makes.
    payload: dict = {"text": text or ""}
    if image is not None:
        payload["image_b64"] = base64.b64encode(image.read_bytes()).decode("ascii")
    response = client.post(EMBED_URL, json=payload, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    body = response.json()
    vector = body.get("embedding") or body.get("vector") or body.get("embeddings")
    if isinstance(vector, list) and vector and isinstance(vector[0], list):
        vector = vector[0]
    if not isinstance(vector, list) or len(vector) != VECTOR_SIZE:
        raise ValueError(f"embedder returned an unusable vector for {EMBED_URL}: keys={sorted(body)}")
    return vector


def index_house_slides(decks_dir: Path, renders_dir: Path) -> dict:
    """Index every real slide (image + title + signature) for retrieval."""
    signatures = extract_signatures(decks_dir)
    renders = {p.name: p for p in renders_dir.glob("*.png")}
    points: list[dict] = []
    missing_renders: list[str] = []
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        existing = client.get(f"{QDRANT_URL}/collections/{HOUSE_COLLECTION}")
        if existing.status_code != 200:
            client.put(
                f"{QDRANT_URL}/collections/{HOUSE_COLLECTION}",
                json={"vectors": {
                    "text_mm": {"size": VECTOR_SIZE, "distance": "Cosine"},
                    "image_mm": {"size": VECTOR_SIZE, "distance": "Cosine"},
                }},
            ).raise_for_status()
        for signature in signatures:
            candidates = [n for n in renders if n.startswith(signature.deck) and f"-{signature.slide_index:02d}" in n]
            if not candidates:
                candidates = [n for n in renders if n.startswith(signature.deck) and f"-{signature.slide_index}." in n]
            if not candidates:
                missing_renders.append(f"{signature.deck}#{signature.slide_index}")
                continue
            image = renders[sorted(candidates)[0]]
            vectors = {"image_mm": _embed(client, image=image)}
            if signature.title:
                vectors["text_mm"] = _embed(client, text=signature.title)
            points.append({
                "id": int(hashlib.sha256(f"{signature.deck}:{signature.slide_index}".encode()).hexdigest()[:12], 16),
                "vector": vectors,
                "payload": {
                    **signature.model_dump(by_alias=True, mode="json"),
                    "image_path": str(image),
                },
            })
        for batch_start in range(0, len(points), 32):
            client.put(
                f"{QDRANT_URL}/collections/{HOUSE_COLLECTION}/points",
                json={"points": points[batch_start:batch_start + 32]},
            ).raise_for_status()
    return {
        "collection": HOUSE_COLLECTION,
        "indexed": len(points),
        "measured": len(signatures),
        "missing_renders": missing_renders,
    }


def find_nearest_layout(query_text: str, *, limit: int = 3, structure: str | None = None) -> list[dict]:
    """Retrieve the author's real slides closest to a described need.

    ``structure`` (e.g. "2t1p") filters to slides with the same block census,
    so a proof slide retrieves proof-shaped layouts rather than merely
    topically similar ones."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        vector = _embed(client, text=query_text)
        body: dict = {"vector": {"name": "text_mm", "vector": vector}, "limit": limit, "with_payload": True}
        response = client.post(f"{QDRANT_URL}/collections/{HOUSE_COLLECTION}/points/search", json=body)
        response.raise_for_status()
        hits = response.json()["result"]
    results = []
    for hit in hits:
        payload = hit["payload"]
        if structure and f"{payload['text_block_count']}t{payload['picture_count']}p" != structure:
            continue
        results.append({
            "score": round(hit["score"], 4),
            "deck": payload["deck"],
            "slide_index": payload["slide_index"],
            "title": payload["title"],
            "structure": f"{payload['text_block_count']}t{payload['picture_count']}p",
            "image_path": payload["image_path"],
            "blocks": payload["blocks"],
        })
    return results
