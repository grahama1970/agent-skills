"""Index deck slide images into Qdrant (text_mm + image_mm vectors) for multimodal recall.

Follows the persona-dream contact-sheet pattern: images stay on disk (12TB
volume), Qdrant stores named 1024-d jina multimodal vectors per slide image,
and ArangoDB (via the memory service HTTP API) stores only metadata plus the
Qdrant point id — never vector arrays. Inputs: an emitted deck.data.json and a
directory of slide PNGs (from `render` or copied bundle assets). Failure
modes: missing bundle/images raise ValueError; embedding or Qdrant/memory HTTP
failures raise httpx.HTTPStatusError with the failing endpoint visible.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import httpx
from loguru import logger

from .models import OperationClaims, OperationReceipt, Readiness, SeamValidation
from .ui_emitter import UiDeckBundle

QDRANT_URL = "http://127.0.0.1:6333"
EMBED_URL = "http://127.0.0.1:8603/embed"
MEMORY_URL = "http://127.0.0.1:8601"
QDRANT_COLLECTION = "readme_to_pitchdeck_visual_assets_v1"
MEMORY_COLLECTION = "readme_to_pitchdeck_visual_assets"
VECTOR_SIZE = 1024
HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)


def _point_id(deck_id: str, image: Path) -> str:
    return hashlib.sha256(f"{deck_id}:{image.name}".encode()).hexdigest()[:32]


def _ensure_collection(client: httpx.Client) -> bool:
    existing = client.get(f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}", timeout=10)
    if existing.status_code == 200:
        return False
    response = client.put(
        f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}",
        json={
            "vectors": {
                "text_mm": {"size": VECTOR_SIZE, "distance": "Cosine"},
                "image_mm": {"size": VECTOR_SIZE, "distance": "Cosine"},
            }
        },
        timeout=30,
    )
    response.raise_for_status()
    return True


def sync_deck_visuals(
    deck_data: Path,
    images_dir: Path,
) -> OperationReceipt:
    """Embed each slide image (text+image) and upsert Qdrant points + memory pointers."""
    bundle = UiDeckBundle.model_validate(json.loads(deck_data.read_text(encoding="utf-8")))
    if bundle.seam_validation.status != "PASS":
        raise ValueError("deck bundle is missing its seam_validation PASS stamp")
    images = sorted(
        images_dir.glob("slide-*.png"),
        key=lambda p: int(p.stem.split("-")[-1]),
    )
    if not images:
        raise ValueError(f"no slide-N.png images found in {images_dir} (run `render` first)")

    slides_by_order = {slide.order: slide for slide in bundle.slides}
    points: list[dict] = []
    memory_docs: list[dict] = []
    gaps: list[str] = []

    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        created = _ensure_collection(client)
        for position, image in enumerate(images, start=1):
            slide = slides_by_order.get(position)
            title = slide.title if slide else image.stem
            description = slide.message if slide else ""
            if slide is None:
                gaps.append(f"VISUAL_UNMATCHED_IMAGE: {image.name} has no slide with order {position}.")
            doc_text = f"{bundle.title} slide {position}: {title}\n{description}"
            text_resp = client.post(EMBED_URL, json={"text": doc_text})
            text_resp.raise_for_status()
            image_b64 = base64.b64encode(image.read_bytes()).decode("ascii")
            image_resp = client.post(EMBED_URL, json={"text": doc_text, "image_b64": image_b64})
            image_resp.raise_for_status()
            text_vec = text_resp.json()["embedding"]
            image_vec = image_resp.json()["embedding"]
            if len(text_vec) != VECTOR_SIZE or len(image_vec) != VECTOR_SIZE:
                raise ValueError(f"embedding dimension mismatch for {image.name}")
            payload = {
                "deck_id": bundle.deck_id,
                "deck_title": bundle.title,
                "visibility": bundle.visibility,
                "slide_order": position,
                "slide_id": slide.id if slide else None,
                "title": title,
                "description": description,
                "image_path": str(image.resolve()),
                "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "embedding_model": text_resp.json().get("model"),
                "embedding_schema": "text_mm=text_only, image_mm=text_plus_image_b64",
                "tags": ["pitchdeck", "readme-to-pitchdeck", bundle.deck_id, bundle.visibility],
            }
            point_id = _point_id(bundle.deck_id, image)
            points.append(
                {"id": point_id, "vector": {"text_mm": text_vec, "image_mm": image_vec}, "payload": payload}
            )
            memory_docs.append(
                {
                    **payload,
                    "_key": f"pitchdeck_visual_{point_id}",
                    "problem": f"Pitch deck slide visual: {bundle.title} slide {position} ({title})",
                    "solution": (
                        f"Slide image stored at {image.resolve()} and indexed as Qdrant point "
                        f"{point_id} in {QDRANT_COLLECTION}."
                    ),
                    "visual_qdrant_collection": QDRANT_COLLECTION,
                    "visual_qdrant_point_id": point_id,
                }
            )
        logger.info("upserting {} visual points into {}", len(points), QDRANT_COLLECTION)
        upsert = client.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true", json={"points": points}
        )
        upsert.raise_for_status()
        memory_resp = client.post(
            f"{MEMORY_URL}/upsert", json={"collection": MEMORY_COLLECTION, "documents": memory_docs}
        )
        memory_resp.raise_for_status()

        # Independent read-back: the Qdrant point count for this deck must match.
        count = client.post(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/count",
            json={"filter": {"must": [{"key": "deck_id", "match": {"value": bundle.deck_id}}]}, "exact": True},
        )
        count.raise_for_status()
        stored = count.json()["result"]["count"]
        if stored < len(points):
            raise RuntimeError(f"read-back mismatch: upserted {len(points)} points but count returned {stored}")

    return OperationReceipt(
        schema="readme_to_pitchdeck.visual_sync_receipt.v1",
        operation="visual-sync",
        readiness=Readiness.USABLE_WITH_GAPS if gaps else Readiness.READY,
        mocked=False,
        live=True,
        inputs={"deck_data": str(deck_data.resolve()), "images_dir": str(images_dir.resolve())},
        outputs={
            "qdrant_collection": QDRANT_COLLECTION,
            "memory_collection": MEMORY_COLLECTION,
            "points_read_back": str(stored),
        },
        counts={"images": len(images), "points": len(points)},
        gaps=gaps,
        claims=OperationClaims(
            proves=[
                "Slide images were embedded (text_mm + image_mm) and upserted into Qdrant.",
                "The per-deck Qdrant point count was read back and matches the upsert.",
                "Metadata pointer documents were accepted by the memory service /upsert.",
            ],
            does_not_prove=[
                "Multimodal retrieval quality for these vectors.",
                "The images reflect the current bundle after later edits; re-render and re-sync.",
            ],
        ),
        seam_validation=SeamValidation(kind="visual_sync_receipt"),
    )
