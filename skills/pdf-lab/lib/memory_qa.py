"""Memory/Qdrant QA for PDF Lab extraction artifacts.

The report is deliberately conservative. It writes and checks only real
artifact-backed records; it does not fabricate visual coverage when crops or
multimodal image vectors are unavailable.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "memory_chunks_mm_jina_v4_1024"
MM_EMBEDDING_URL = "http://localhost:8603"
JINA_V4_QUERY_PREFIX = "Query: "
JINA_V4_PASSAGE_PREFIX = "Passage: "
V1_REQUIRED_VISUAL_ELEMENT_TYPES = {"table", "figure", "image"}


@dataclass(frozen=True)
class MemoryQaConfig:
    extraction_path: Path
    evidence_manifest_path: Path
    output_path: Path
    public_root: Path
    sample_size: int = 8
    apply_memory: bool = False
    memory_socket: str = MEMORY_SOCKET
    qdrant_url: str = QDRANT_URL
    qdrant_collection: str = QDRANT_COLLECTION
    embedding_url: str = MM_EMBEDDING_URL


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def _resolve_public_uri(public_root: Path, uri: str | None) -> Path | None:
    if not uri:
        return None
    path = Path(uri)
    if path.is_absolute() and path.exists():
        return path
    return public_root / uri.lstrip("/")


def _safe_key(value: str) -> str:
    return value.replace("/", "_")


def _sha16(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _image_key(run_id: str, owner_key: str, image_hash: str | None, kind: str) -> str:
    return _safe_key(f"img:{kind}:{run_id}:{owner_key}:{str(image_hash or '')[:16]}")


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _element_type(element: dict[str, Any]) -> str:
    return str(element.get("type") or element.get("element_type") or "").lower()


def _has_crop_eligible_bbox(element: dict[str, Any]) -> bool:
    bbox = element.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    try:
        x1, y1, x2, y2 = [float(value) for value in bbox]
    except (TypeError, ValueError):
        return False
    return (max(x1, x2) - min(x1, x2)) > 0.0001 and (max(y1, y2) - min(y1, y2)) > 0.0001


def _bounded_text(value: Any, limit: int = 1200) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit]


def _sample_recall_elements(elements: list[dict[str, Any]], sample_size: int) -> list[dict[str, Any]]:
    buckets = ["table", "requirement", "list_item", "caption", "section_header", "paragraph"]
    excluded_fallback_types = {"running_header", "running_footer"}
    selected: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    seen_hashes: set[str] = set()

    def add_candidate(element: dict[str, Any]) -> None:
        if len(selected) >= sample_size:
            return
        if _element_type(element) in excluded_fallback_types:
            return
        key = _safe_key(str(element.get("element_key") or ""))
        text = _bounded_text(element.get("text", ""), 600)
        if not key or len(text) < 40:
            return
        text_hash = _text_hash(text)
        if key in seen_keys or text_hash in seen_hashes:
            return
        seen_keys.add(key)
        seen_hashes.add(text_hash)
        selected.append(element)

    for bucket in buckets:
        for element in elements:
            if _element_type(element) == bucket:
                add_candidate(element)
                break

    for element in elements:
        add_candidate(element)
        if len(selected) >= sample_size:
            break
    return selected


def _build_memory_documents(manifest: dict[str, Any], public_root: Path) -> dict[str, list[dict[str, Any]]]:
    run_id = str(manifest["run_id"])
    source_pdf_hash = str(manifest["source_pdf_hash"])
    now = datetime.now(timezone.utc).isoformat()
    pages = [page for page in manifest.get("pages") or [] if isinstance(page, dict)]
    sections = [section for section in manifest.get("sections") or [] if isinstance(section, dict)]
    elements = [element for element in manifest.get("elements") or [] if isinstance(element, dict)]
    page_image_by_page = {int(page["page"]): page for page in pages if isinstance(page, dict) and page.get("page")}

    extraction_run = {
        "_key": _safe_key(f"run:{run_id}"),
        "record_type": "extraction_run",
        "run_id": run_id,
        "source_pdf_uri": manifest.get("source_pdf_uri"),
        "source_pdf_hash": source_pdf_hash,
        "extraction_uri": manifest.get("extraction_uri"),
        "page_count": manifest.get("page_count"),
        "element_count": len(elements),
        "created_at": now,
        "artifact_uri": str(manifest.get("manifest_uri") or str(manifest.get("source_manifest") or "")),
    }

    page_docs: list[dict[str, Any]] = []
    page_image_docs: list[dict[str, Any]] = []
    section_docs: list[dict[str, Any]] = []
    section_image_docs: list[dict[str, Any]] = []
    element_docs: list[dict[str, Any]] = []
    element_image_docs: list[dict[str, Any]] = []
    run_edges: list[dict[str, Any]] = []
    page_image_edges: list[dict[str, Any]] = []
    section_image_edges: list[dict[str, Any]] = []
    element_image_edges: list[dict[str, Any]] = []

    for page in pages:
        page_number = int(page.get("page") or 0)
        page_key = _safe_key(f"page:{run_id}:{page_number:04d}")
        page_image_path = _resolve_public_uri(public_root, page.get("page_image_uri"))
        provenance = {
            "source_pdf_uri": manifest.get("source_pdf_uri"),
            "source_pdf_hash": source_pdf_hash,
            "run_id": run_id,
            "page": page_number,
            "created_at": now,
        }
        page_docs.append({
            "_key": page_key,
            "record_type": "pdf_page",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "page": page_number,
            "text_preview": f"PDF page {page_number} from {Path(str(manifest.get('source_pdf_uri') or '')).name}",
            "page_image_uri": str(page_image_path) if page_image_path else None,
            "page_image_hash": page.get("page_image_hash"),
            "provenance": provenance,
        })
        page_image_key = _image_key(run_id, page_key, page.get("page_image_hash"), "page")
        page_image_docs.append({
            "_key": page_image_key,
            "record_type": "pdf_page_image",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "page": page_number,
            "kind": "page_image",
            "image_uri": str(page_image_path) if page_image_path else None,
            "image_hash": page.get("page_image_hash"),
            "qdrant_collection": QDRANT_COLLECTION,
            "qdrant_vector_names": ["image_mm"],
            "provenance": provenance,
        })
        run_edges.append({
            "_key": _safe_key(f"run_has_page:{run_id}:{page_key}"),
            "_from": f"pdf_extraction_runs/{extraction_run['_key']}",
            "_to": f"pdf_pages/{page_key}",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "created_at": now,
            "method": "pdf_lab_memory_qa",
        })
        page_image_edges.append({
            "_key": _safe_key(f"page_has_image:{page_key}:{page_image_key}"),
            "_from": f"pdf_pages/{page_key}",
            "_to": f"pdf_page_images/{page_image_key}",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "created_at": now,
            "method": "pdf_lab_memory_qa",
        })

    for section in sections:
        page = int(section.get("page") or 0)
        section_key = _safe_key(str(section.get("section_key") or section.get("section_id") or f"section:{run_id}:{page}:{_sha16(str(section.get('title')))}"))
        crop_path = _resolve_public_uri(public_root, section.get("crop_uri"))
        page_image_path = _resolve_public_uri(public_root, section.get("page_image_uri"))
        provenance = {
            "source_pdf_uri": manifest.get("source_pdf_uri"),
            "source_pdf_hash": source_pdf_hash,
            "run_id": run_id,
            "page": page,
            "bbox": section.get("bbox"),
            "created_at": now,
        }
        section_docs.append({
            "_key": section_key,
            "record_type": "pdf_section",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "section_id": section.get("section_id"),
            "title": section.get("title"),
            "page": page,
            "bbox": section.get("bbox"),
            "coordinate_space": section.get("coordinate_space"),
            "text_preview": _bounded_text(section.get("text", "")),
            "full_text_hash": _text_hash(str(section.get("text") or "")),
            "crop_uri": str(crop_path) if crop_path else None,
            "crop_hash": section.get("crop_hash"),
            "page_image_uri": str(page_image_path) if page_image_path else None,
            "provenance": provenance,
        })
        section_image_key = _image_key(run_id, section_key, section.get("crop_hash"), "section")
        section_image_docs.append({
            "_key": section_image_key,
            "record_type": "pdf_section_image",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "section_id": section.get("section_id"),
            "section_key": section_key,
            "page": page,
            "kind": "section_crop",
            "crop_uri": str(crop_path) if crop_path else None,
            "crop_hash": section.get("crop_hash"),
            "page_image_uri": str(page_image_path) if page_image_path else None,
            "bbox": section.get("bbox"),
            "coordinate_space": section.get("coordinate_space"),
            "qdrant_collection": QDRANT_COLLECTION,
            "qdrant_vector_names": ["image_mm"],
            "provenance": provenance,
        })
        run_edges.append({
            "_key": _safe_key(f"run_has_section:{run_id}:{section_key}"),
            "_from": f"pdf_extraction_runs/{extraction_run['_key']}",
            "_to": f"pdf_sections/{section_key}",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "created_at": now,
            "method": "pdf_lab_memory_qa",
        })
        section_image_edges.append({
            "_key": _safe_key(f"section_has_image:{section_key}:{section_image_key}"),
            "_from": f"pdf_sections/{section_key}",
            "_to": f"pdf_section_images/{section_image_key}",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "created_at": now,
            "method": "pdf_lab_memory_qa",
        })

    for element in elements:
        page = int(element.get("page") or 0)
        element_key = _safe_key(str(element.get("element_key") or f"elt:{source_pdf_hash[:16]}:{page}:{_sha16(str(element.get('element_id')))}"))
        crop_path = _resolve_public_uri(public_root, element.get("crop_uri"))
        page_image_path = _resolve_public_uri(public_root, element.get("page_image_uri"))
        provenance = {
            "source_pdf_uri": manifest.get("source_pdf_uri"),
            "source_pdf_hash": source_pdf_hash,
            "run_id": run_id,
            "artifact_uri": manifest.get("extraction_uri"),
            "json_pointer": element.get("json_pointer"),
            "page": page,
            "bbox": element.get("bbox"),
            "created_at": now,
        }
        element_doc = {
            "_key": element_key,
            "record_type": "pdf_element",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "element_id": element.get("element_id"),
            "page": page,
            "element_type": _element_type(element),
            "bbox": element.get("bbox"),
            "coordinate_space": element.get("coordinate_space"),
            "json_pointer": element.get("json_pointer"),
            "text_preview": _bounded_text(element.get("text", "")),
            "full_text_hash": _text_hash(str(element.get("text") or "")),
            "crop_uri": str(crop_path) if crop_path else None,
            "page_image_uri": str(page_image_path) if page_image_path else None,
            "crop_hash": element.get("crop_hash"),
            "preset_source": element.get("preset_applied"),
            "provenance": provenance,
        }
        element_docs.append(element_doc)

        page_image = page_image_by_page.get(page, {})
        element_image_key = _image_key(run_id, element_key, element.get("crop_hash"), "element")
        image_doc = {
            "_key": element_image_key,
            "record_type": "pdf_element_image",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "element_id": element.get("element_id"),
            "element_key": element_key,
            "element_type": _element_type(element),
            "page": page,
            "kind": "element_crop",
            "crop_uri": str(crop_path) if crop_path else None,
            "crop_hash": element.get("crop_hash"),
            "page_image_uri": str(page_image_path) if page_image_path else None,
            "page_image_hash": page_image.get("page_image_hash") or element.get("page_image_hash"),
            "bbox": element.get("bbox"),
            "coordinate_space": element.get("coordinate_space"),
            "width": element.get("crop_width"),
            "height": element.get("crop_height"),
            "qdrant_collection": QDRANT_COLLECTION,
            "qdrant_vector_names": ["image_mm", "text_mm"],
            "provenance": provenance,
        }
        element_image_docs.append(image_doc)

        run_edges.append({
            "_key": _safe_key(f"run_has_element:{run_id}:{element_key}"),
            "_from": f"pdf_extraction_runs/{extraction_run['_key']}",
            "_to": f"pdf_elements/{element_key}",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "created_at": now,
            "method": "pdf_lab_memory_qa",
        })
        element_image_edges.append({
            "_key": _safe_key(f"element_has_image:{element_key}:{element_image_key}"),
            "_from": f"pdf_elements/{element_key}",
            "_to": f"pdf_element_images/{element_image_key}",
            "run_id": run_id,
            "source_pdf_hash": source_pdf_hash,
            "created_at": now,
            "method": "pdf_lab_memory_qa",
        })

    return {
        "pdf_extraction_runs": [extraction_run],
        "pdf_pages": page_docs,
        "pdf_page_images": page_image_docs,
        "pdf_sections": section_docs,
        "pdf_section_images": section_image_docs,
        "pdf_elements": element_docs,
        "pdf_element_images": element_image_docs,
        "pdf_extraction_run_has_artifact": run_edges,
        "pdf_page_has_image": page_image_edges,
        "pdf_section_has_image": section_image_edges,
        "pdf_element_has_image": element_image_edges,
    }


def _post_memory_upsert(socket_path: str, collection: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    batches: list[dict[str, Any]] = []
    transport = httpx.HTTPTransport(uds=socket_path)
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        for index in range(0, len(documents), 100):
            batch = documents[index:index + 100]
            response = client.post(
                "/upsert",
                json={"collection": collection, "documents": batch, "skip_embedding": True},
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise TypeError("/upsert returned a non-object response")
            batches.append(data)
            total += len(batch)
            if total % 500 == 0 or total == len(documents):
                print(f"[pdf-lab:memory] {collection} {total}/{len(documents)}", file=sys.stderr, flush=True)
    return {"collection": collection, "document_count": total, "batches": len(batches), "last_response": batches[-1] if batches else None}


def _qdrant_scroll_keys(qdrant_url: str, collection: str, arango_collection: str) -> set[str]:
    keys: set[str] = set()
    offset: Any = None
    while True:
        body: dict[str, Any] = {
            "filter": {"must": [{"key": "arango_collection", "match": {"value": arango_collection}}]},
            "limit": 256,
            "with_payload": True,
            "with_vector": False,
        }
        if offset is not None:
            body["offset"] = offset
        response = httpx.post(f"{qdrant_url.rstrip('/')}/collections/{collection}/points/scroll", json=body, timeout=20.0)
        response.raise_for_status()
        result = response.json().get("result", {})
        for point in result.get("points") or []:
            payload = point.get("payload") or {}
            key = payload.get("arango_key")
            if isinstance(key, str):
                keys.add(key)
        offset = result.get("next_page_offset")
        if offset is None:
            return keys


def _embed_text(embedding_url: str, text: str) -> list[float]:
    response = httpx.post(
        f"{embedding_url.rstrip('/')}/v1/embeddings",
        json={"input": [text], "dimensions": 1024},
        timeout=20.0,
    )
    response.raise_for_status()
    vector = response.json()["data"][0]["embedding"]
    if not isinstance(vector, list) or len(vector) != 1024:
        raise ValueError(f"text embedding dimension was {len(vector) if isinstance(vector, list) else 'invalid'}, expected 1024")
    return [float(value) for value in vector]


def _embed_query_text(embedding_url: str, text: str) -> list[float]:
    return _embed_text(embedding_url, f"{JINA_V4_QUERY_PREFIX}{text}")


def _embed_passage_text(embedding_url: str, text: str) -> list[float]:
    return _embed_text(embedding_url, f"{JINA_V4_PASSAGE_PREFIX}{text}")


def _search_text_vector(qdrant_url: str, collection: str, vector: list[float], limit: int) -> list[dict[str, Any]]:
    response = httpx.post(
        f"{qdrant_url.rstrip('/')}/collections/{collection}/points/search",
        json={"vector": {"name": "text_mm", "vector": vector}, "limit": limit, "with_payload": True},
        timeout=20.0,
    )
    response.raise_for_status()
    result = response.json().get("result") or []
    return [point for point in result if isinstance(point, dict)]


def _search_text_vectors(qdrant_url: str, collection: str, vectors: list[list[float]], limit: int) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for vector in vectors:
        for point in _search_text_vector(qdrant_url, collection, vector, limit):
            point_id = str(point.get("id") or "")
            if point_id and point_id not in merged:
                merged[point_id] = point
    return list(merged.values())


def build_memory_qa_report(config: MemoryQaConfig) -> dict[str, Any]:
    extraction = read_json(config.extraction_path)
    evidence_manifest = read_json(config.evidence_manifest_path)
    extraction_elements = extraction.get("elements") or []
    crop_required_extraction_elements = [
        element
        for element in extraction_elements
        if isinstance(element, dict) and _has_crop_eligible_bbox(element)
    ]
    evidence_pages = [page for page in evidence_manifest.get("pages") or [] if isinstance(page, dict)]
    evidence_sections = [section for section in evidence_manifest.get("sections") or [] if isinstance(section, dict)]
    evidence_elements = [element for element in evidence_manifest.get("elements") or [] if isinstance(element, dict)]
    memory_documents = _build_memory_documents(evidence_manifest, config.public_root)
    page_keys = {document["_key"] for document in memory_documents["pdf_pages"]}
    page_image_keys = {document["_key"] for document in memory_documents["pdf_page_images"]}
    section_keys = {document["_key"] for document in memory_documents["pdf_sections"]}
    section_image_keys = {document["_key"] for document in memory_documents["pdf_section_images"]}
    element_keys = {document["_key"] for document in memory_documents["pdf_elements"]}
    element_image_keys = {document["_key"] for document in memory_documents["pdf_element_images"]}
    required_visual_element_keys = {
        _safe_key(str(element.get("element_key") or element.get("element_id") or ""))
        for element in evidence_elements
        if _element_type(element) in V1_REQUIRED_VISUAL_ELEMENT_TYPES
    }
    required_visual_element_image_keys = {
        document["_key"]
        for document in memory_documents["pdf_element_images"]
        if str(document.get("element_type") or "").lower() in V1_REQUIRED_VISUAL_ELEMENT_TYPES
    }

    crop_missing: list[str] = []
    page_missing: list[str] = []
    section_crop_missing: list[str] = []
    page_image_missing: list[str] = []
    for page in evidence_pages:
        page_image = _resolve_public_uri(config.public_root, page.get("page_image_uri"))
        if page_image is None or not page_image.exists():
            page_image_missing.append(str(page.get("page_image_uri")))
    for section in evidence_sections:
        crop = _resolve_public_uri(config.public_root, section.get("crop_uri"))
        if crop is None or not crop.exists():
            section_crop_missing.append(str(section.get("crop_uri")))
    for element in evidence_elements:
        crop = _resolve_public_uri(config.public_root, element.get("crop_uri"))
        page_image = _resolve_public_uri(config.public_root, element.get("page_image_uri"))
        if crop is None or not crop.exists():
            crop_missing.append(str(element.get("crop_uri")))
        if page_image is None or not page_image.exists():
            page_missing.append(str(element.get("page_image_uri")))

    upsert_results: dict[str, Any] = {}
    upsert_error: str | None = None
    upsert_errors: dict[str, str] = {}
    if config.apply_memory:
        for collection, documents in memory_documents.items():
            if not documents:
                continue
            try:
                upsert_results[collection] = _post_memory_upsert(config.memory_socket, collection, documents)
            except Exception as exc:  # report, do not hide
                upsert_errors[collection] = f"{type(exc).__name__}: {exc}"
        if upsert_errors:
            upsert_error = "; ".join(f"{collection}: {error}" for collection, error in upsert_errors.items())

    qdrant_error: str | None = None
    text_indexed: dict[str, set[str]] = {
        "pdf_pages": set(),
        "pdf_sections": set(),
        "pdf_elements": set(),
    }
    visual_indexed: dict[str, set[str]] = {
        "pdf_page_images": set(),
        "pdf_section_images": set(),
        "pdf_element_images": set(),
    }
    try:
        text_indexed["pdf_pages"] = _qdrant_scroll_keys(config.qdrant_url, config.qdrant_collection, "pdf_pages") & page_keys
        text_indexed["pdf_sections"] = _qdrant_scroll_keys(config.qdrant_url, config.qdrant_collection, "pdf_sections") & section_keys
        text_indexed["pdf_elements"] = _qdrant_scroll_keys(config.qdrant_url, config.qdrant_collection, "pdf_elements") & element_keys
        visual_indexed["pdf_page_images"] = _qdrant_scroll_keys(config.qdrant_url, config.qdrant_collection, "pdf_page_images") & page_image_keys
        visual_indexed["pdf_section_images"] = _qdrant_scroll_keys(config.qdrant_url, config.qdrant_collection, "pdf_section_images") & section_image_keys
        visual_indexed["pdf_element_images"] = _qdrant_scroll_keys(config.qdrant_url, config.qdrant_collection, "pdf_element_images") & element_image_keys
    except Exception as exc:
        qdrant_error = f"{type(exc).__name__}: {exc}"

    sample_checks: list[dict[str, Any]] = []
    sampled_elements = _sample_recall_elements(evidence_elements, config.sample_size)
    for element in sampled_elements:
        element_key = _safe_key(str(element.get("element_key") or ""))
        text = str(element.get("text") or "").strip()
        if not text:
            sample_checks.append({"element_key": element_key, "status": "skipped", "reason": "empty_text"})
            continue
        try:
            vectors = [
                _embed_query_text(config.embedding_url, text),
                _embed_passage_text(config.embedding_url, text),
                _embed_text(config.embedding_url, text),
            ]
            points = _search_text_vectors(config.qdrant_url, config.qdrant_collection, vectors, 50)
            returned_keys = [
                str((point.get("payload") or {}).get("arango_key"))
                for point in points
                if isinstance(point.get("payload"), dict)
            ]
            sample_checks.append({
                "element_key": element_key,
                "page": element.get("page"),
                "element_type": _element_type(element),
                "text_hash": _text_hash(text),
                "status": "passed" if element_key in returned_keys else "failed",
                "returned_keys": returned_keys[:5],
            })
        except Exception as exc:
            sample_checks.append({
                "element_key": element_key,
                "page": element.get("page"),
                "element_type": _element_type(element),
                "status": "failed",
                "reason": f"{type(exc).__name__}: {exc}",
            })

    passed_sample_checks = sum(1 for check in sample_checks if check.get("status") == "passed")
    full_crop_coverage = len(evidence_elements) >= len(crop_required_extraction_elements) and len(crop_required_extraction_elements) > 0
    text_indexed_pages = len(text_indexed["pdf_pages"])
    text_indexed_sections = len(text_indexed["pdf_sections"])
    text_indexed_elements = len(text_indexed["pdf_elements"])
    visual_indexed_pages = len(visual_indexed["pdf_page_images"])
    visual_indexed_sections = len(visual_indexed["pdf_section_images"])
    visual_indexed_elements = len(visual_indexed["pdf_element_images"])
    visual_indexed_required_elements = len(visual_indexed["pdf_element_images"] & required_visual_element_image_keys)
    visual_optional_element_count = max(0, len(evidence_elements) - len(required_visual_element_keys))
    visual_optional_indexed_elements = max(0, visual_indexed_elements - visual_indexed_required_elements)
    text_indexed_total = text_indexed_pages + text_indexed_sections + text_indexed_elements
    visual_indexed_total = visual_indexed_pages + visual_indexed_sections + visual_indexed_elements
    required_visual_element_count = len(required_visual_element_image_keys)
    passed = (
        upsert_error is None
        and qdrant_error is None
        and not crop_missing
        and not page_missing
        and not page_image_missing
        and not section_crop_missing
        and full_crop_coverage
        and text_indexed_elements >= len(evidence_elements) > 0
        and visual_indexed_pages >= len(evidence_pages) > 0
        and visual_indexed_sections >= len(evidence_sections) > 0
        and visual_indexed_required_elements >= required_visual_element_count
        and passed_sample_checks == len(sample_checks)
        and len(sample_checks) > 0
    )

    return {
        "schema_version": "pdf_lab_memory_qdrant_qa_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "implemented": True,
        "passed": passed,
        "run_id": evidence_manifest.get("run_id"),
        "source_pdf": extraction.get("source_pdf") or evidence_manifest.get("source_pdf_uri"),
        "policy": (
            "Final agent QA must store extracted page, section, and element metadata/crops in ArangoDB memory, "
            "index text vectors for every extracted element, index visual vectors for pages, sections, tables, "
            "and figures/images, and verify stratified recall against original page/crop evidence. "
            "Paragraph/list/header/footer crop image vectors are optional background/on-demand work."
        ),
        "summary": {
            "evidence_pages": len(evidence_pages),
            "evidence_sections": len(evidence_sections),
            "extraction_elements": len(extraction_elements),
            "crop_required_extraction_elements": len(crop_required_extraction_elements),
            "evidence_elements": len(evidence_elements),
            "full_crop_coverage": full_crop_coverage,
            "memory_upsert_applied": config.apply_memory,
            "memory_upserted_pages": upsert_results.get("pdf_pages", {}).get("document_count", 0) if config.apply_memory else 0,
            "memory_upserted_page_images": upsert_results.get("pdf_page_images", {}).get("document_count", 0) if config.apply_memory else 0,
            "memory_upserted_sections": upsert_results.get("pdf_sections", {}).get("document_count", 0) if config.apply_memory else 0,
            "memory_upserted_section_images": upsert_results.get("pdf_section_images", {}).get("document_count", 0) if config.apply_memory else 0,
            "memory_upserted_elements": upsert_results.get("pdf_elements", {}).get("document_count", 0) if config.apply_memory else 0,
            "memory_upserted_element_images": upsert_results.get("pdf_element_images", {}).get("document_count", 0) if config.apply_memory else 0,
            "text_indexed_pages": text_indexed_pages,
            "text_indexed_sections": text_indexed_sections,
            "text_indexed_elements": text_indexed_elements,
            "text_indexed_total": text_indexed_total,
            "visual_indexed_pages": visual_indexed_pages,
            "visual_indexed_sections": visual_indexed_sections,
            "visual_indexed_elements": visual_indexed_elements,
            "visual_required_element_types": sorted(V1_REQUIRED_VISUAL_ELEMENT_TYPES),
            "visual_required_elements": required_visual_element_count,
            "visual_indexed_required_elements": visual_indexed_required_elements,
            "visual_optional_elements": visual_optional_element_count,
            "visual_indexed_optional_elements": visual_optional_indexed_elements,
            "visual_indexed_total": visual_indexed_total,
            "sample_checks": len(sample_checks),
            "sample_checks_passed": passed_sample_checks,
            "qdrant_collection": config.qdrant_collection,
        },
        "gates": [
            {
                "name": "full_crop_coverage",
                "passed": full_crop_coverage and not page_image_missing and not section_crop_missing and not crop_missing,
                "detail": (
                    f"{len(evidence_pages)} page images, {len(evidence_sections)} section crops, "
                    f"and {len(evidence_elements)} element crops for {len(extraction_elements)} extracted elements."
                ),
            },
            {
                "name": "memory_upsert",
                "passed": config.apply_memory and upsert_error is None,
                "detail": "ArangoDB memory upsert applied via canonical /upsert." if config.apply_memory else "Run with --apply-memory to persist evidence metadata.",
            },
            {
                "name": "text_qdrant_recall",
                "passed": (
                    text_indexed_elements >= len(evidence_elements) > 0
                    and passed_sample_checks == len(sample_checks)
                    and len(sample_checks) > 0
                ),
                "detail": (
                    f"elements {text_indexed_elements}/{len(evidence_elements)} have required text vectors; "
                    f"page text vectors {text_indexed_pages}/{len(evidence_pages)} and "
                    f"section text vectors {text_indexed_sections}/{len(evidence_sections)} are non-blocking metadata; "
                    f"{passed_sample_checks}/{len(sample_checks)} element recall checks passed."
                ),
            },
            {
                "name": "visual_qdrant_recall",
                "passed": (
                    visual_indexed_pages >= len(evidence_pages) > 0
                    and visual_indexed_sections >= len(evidence_sections) > 0
                    and visual_indexed_required_elements >= required_visual_element_count
                ),
                "detail": (
                    f"pages {visual_indexed_pages}/{len(evidence_pages)}, sections {visual_indexed_sections}/{len(evidence_sections)}, "
                    f"required table/figure/image elements {visual_indexed_required_elements}/{required_visual_element_count} "
                    f"have visual vectors. Optional text-element crops indexed: {visual_optional_indexed_elements}/{visual_optional_element_count}."
                ),
            },
        ],
        "errors": {
            "memory_upsert": upsert_error,
            "memory_upsert_by_collection": upsert_errors,
            "qdrant": qdrant_error,
            "missing_page_image_assets": page_image_missing[:20],
            "missing_section_crops": section_crop_missing[:20],
            "missing_crops": crop_missing[:20],
            "missing_page_images": page_missing[:20],
        },
        "upsert_results": upsert_results,
        "sample_checks": sample_checks,
        "notes": [
            "This report is real-data backed. A false `passed` value means the QA pipeline ran but did not satisfy the full final gate.",
            "PNG assets remain on disk; ArangoDB memory stores paths, hashes, and provenance only.",
            "The v1 final visual gate requires page images, section crops, and table/figure/image element crops to have matching Qdrant visual vectors.",
            "Paragraph, list, header, footer, and other text-element crop vectors are optional background/on-demand work.",
        ],
    }


def write_memory_qa_report(config: MemoryQaConfig) -> dict[str, Any]:
    report = build_memory_qa_report(config)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
