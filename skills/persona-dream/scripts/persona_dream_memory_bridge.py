#!/usr/bin/env python3
"""Persist persona-dream phase artifacts through the memory daemon.

This bridge is intentionally narrow: Tau and ux-lab can call it after a phase
artifact is written. It stores the artifact pointer, extracted entity coverage,
linked media vertices, and media/TOM grounding edges through memory `/upsert`.
The memory service owns Arango persistence and Qdrant semantic sync.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXTRACT_ENTITIES_RUN = ROOT / "extract-entities" / "run.sh"
DEFAULT_MEMORY_URL = "http://127.0.0.1:8601"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--artifact-type", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--memory-url", default=DEFAULT_MEMORY_URL)
    parser.add_argument("--project-id", default="embry-kai-sick-day")
    parser.add_argument("--persona", default="embry")
    parser.add_argument("--collection", default="persona_memory")
    args = parser.parse_args(argv)

    artifact_path = Path(args.artifact).expanduser().resolve()
    run_root = Path(args.run_root).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    if not artifact_path.exists():
        write_json(receipt_path, {
            "schema": "persona_dream.memory_bridge_receipt.v1",
            "status": "BLOCKED_ARTIFACT_MISSING",
            "mocked": False,
            "live": True,
            "artifact": str(artifact_path),
        })
        return 2

    artifact = read_json(artifact_path)
    artifact_hash = sha256_file(artifact_path)
    text = artifact_text(artifact)
    entity_context_path = receipt_path.with_name("entity_context.json")
    entity_context = extract_entities(text, entity_context_path)
    key_base = sanitize_key(f"{args.project_id}:{args.phase}:{args.artifact_type}:{artifact_hash[:16]}")

    artifact_doc = {
        "_key": key_base,
        "schema": "persona_dream.memory_artifact.v1",
        "kind": "persona_dream_phase_artifact",
        "project_id": args.project_id,
        "persona": args.persona,
        "phase": args.phase,
        "artifact_type": args.artifact_type,
        "artifact_path": str(artifact_path),
        "run_root": str(run_root),
        "source_artifact_sha256": artifact_hash,
        "source_artifact_schema": artifact.get("schema"),
        "status": artifact.get("status") or artifact.get("validation_status") or "STORED",
        "tags": [
            "persona-dream",
            f"persona:{args.persona}",
            f"phase:{args.phase}",
            f"artifact:{args.artifact_type}",
        ],
        "retrieval_text": text[:12000],
        "entity_context_path": str(entity_context_path),
        "created_at": now_iso(),
    }
    coverage_doc = {
        "_key": f"{key_base}_entity_coverage",
        "schema": "persona_dream.entity_coverage.v1",
        "kind": "persona_dream_entity_coverage",
        "project_id": args.project_id,
        "persona": args.persona,
        "phase": args.phase,
        "artifact_type": args.artifact_type,
        "artifact_memory_key": key_base,
        "artifact_path": str(artifact_path),
        "entity_context_path": str(entity_context_path),
        "grounding_ok": entity_context.get("grounding_ok"),
        "entities": entity_context.get("entities", []),
        "context_terms": entity_context.get("context_terms", []),
        "tags": ["persona-dream", "entity-coverage", f"phase:{args.phase}"],
        "retrieval_text": json.dumps(entity_context, ensure_ascii=False)[:12000],
        "created_at": now_iso(),
    }

    assets = linked_assets(artifact)
    asset_docs = [asset_document(asset, args, artifact_path) for asset in assets]
    edge_docs = [
        edge_document(key_base, asset_doc["_key"], asset_doc, args, idx)
        for idx, asset_doc in enumerate(asset_docs)
    ]

    upsert_result = post_json(args.memory_url, "/upsert", {
        "collection": args.collection,
        "documents": [artifact_doc, coverage_doc],
    })
    asset_result: Any = None
    edge_result: Any = None
    if asset_docs:
        asset_result = post_json(args.memory_url, "/upsert", {
            "collection": "persona_dream_media_assets",
            "documents": asset_docs,
        })
    if edge_docs:
        edge_result = post_json(args.memory_url, "/upsert", {
            "collection": "tom_edges",
            "documents": edge_docs,
        })

    recall_query = (
        f"persona-dream {args.phase} {args.artifact_type} {args.project_id} "
        f"{artifact.get('schema') or ''} {text[:500]}"
    )
    recall = post_json(args.memory_url, "/recall", {
        "q": recall_query,
        "collections": [args.collection],
        "k": 8,
    })
    recall_items = recall.get("items") if isinstance(recall, dict) else []
    score_counts = count_score_modes(recall_items if isinstance(recall_items, list) else [])
    status = "PASS" if recall_items else "BLOCKED_RECALL_EMPTY"

    receipt = {
        "schema": "persona_dream.memory_bridge_receipt.v1",
        "status": status,
        "mocked": False,
        "live": True,
        "memory_url": args.memory_url,
        "collection": args.collection,
        "artifact": str(artifact_path),
        "artifact_memory_key": key_base,
        "entity_context": str(entity_context_path),
        "documents_written": [artifact_doc["_key"], coverage_doc["_key"]],
        "media_assets_written": [doc["_key"] for doc in asset_docs],
        "media_edges_written": [doc["_key"] for doc in edge_docs],
        "upsert_result": summarize(upsert_result),
        "asset_upsert_result": summarize(asset_result),
        "edge_upsert_result": summarize(edge_result),
        "recall_probe": {
            "query": recall_query[:1000],
            "count": len(recall_items) if isinstance(recall_items, list) else 0,
            "score_counts": score_counts,
        },
        "created_at": now_iso(),
    }
    write_json(receipt_path, receipt)
    return 0 if status == "PASS" else 3


def artifact_text(payload: dict[str, Any]) -> str:
    keep: dict[str, Any] = {}
    for key in (
        "story",
        "script",
        "panel",
        "interaction_matrix",
        "entity_environment_script_table",
        "timed_beats",
        "timed_transcript",
        "asset_usage",
        "linked_assets",
        "requirements",
        "source_context",
        "quality_checks",
        "location",
        "environment",
        "core_idea",
    ):
        if key in payload:
            keep[key] = payload[key]
    if not keep:
        keep = payload
    return json.dumps(keep, ensure_ascii=False, sort_keys=True)


def linked_assets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for key in ("linked_assets", "asset_usage"):
        value = payload.get(key)
        if isinstance(value, list):
            assets.extend(item for item in value if isinstance(item, dict))
    source_context = payload.get("source_context")
    if isinstance(source_context, dict) and isinstance(source_context.get("linked_assets"), list):
        assets.extend(item for item in source_context["linked_assets"] if isinstance(item, dict))
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for asset in assets:
        ident = str(asset.get("id") or asset.get("asset_id") or asset.get("memory_key") or asset.get("title") or "")
        if not ident or ident in seen:
            continue
        seen.add(ident)
        unique.append(asset)
    return unique


def asset_document(asset: dict[str, Any], args: argparse.Namespace, artifact_path: Path) -> dict[str, Any]:
    asset_id = str(asset.get("id") or asset.get("asset_id") or asset.get("memory_key") or asset.get("title") or "asset")
    key = sanitize_key(f"{args.project_id}:asset:{asset_id}")
    title = str(asset.get("title") or asset.get("name") or asset_id)
    description = str(asset.get("description") or asset.get("visual_consistency_note") or asset.get("used_for") or "")
    return {
        "_key": key,
        "schema": "persona_dream.media_asset.v1",
        "kind": "persona_dream_media_asset",
        "project_id": args.project_id,
        "persona": args.persona,
        "asset_id": asset_id,
        "title": title,
        "description": description,
        "source": asset.get("source") or asset.get("url") or asset.get("path"),
        "artifact_path": str(artifact_path),
        "tags": ["persona-dream", "media-asset", f"persona:{args.persona}"],
        "retrieval_text": f"{title}\n{description}\n{json.dumps(asset, ensure_ascii=False)}",
        "created_at": now_iso(),
    }


def edge_document(source_key: str, target_key: str, asset_doc: dict[str, Any], args: argparse.Namespace, idx: int) -> dict[str, Any]:
    return {
        "_key": sanitize_key(f"{source_key}:uses:{target_key}:{idx}"),
        "_from": f"persona_memory/{source_key}",
        "_to": f"persona_dream_media_assets/{target_key}",
        "schema": "persona_dream.tom_media_edge.v1",
        "kind": "tom_media_grounding_edge",
        "project_id": args.project_id,
        "persona": args.persona,
        "relationship_type": "uses_media_asset",
        "tom_state_type": "grounding",
        "title": asset_doc.get("title"),
        "tags": ["persona-dream", "tom-edge", "media-edge", f"phase:{args.phase}"],
        "created_at": now_iso(),
    }


def extract_entities(text: str, output_path: Path) -> dict[str, Any]:
    if not EXTRACT_ENTITIES_RUN.exists():
        payload = {
            "schema": "persona_dream.entity_context_unavailable.v1",
            "grounding_ok": False,
            "error": f"missing {EXTRACT_ENTITIES_RUN}",
        }
        write_json(output_path, payload)
        return payload
    completed = subprocess.run(
        [str(EXTRACT_ENTITIES_RUN), "extract", "--json", text[:20000]],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if completed.returncode != 0:
        payload = {
            "schema": "persona_dream.entity_context_error.v1",
            "grounding_ok": False,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
        write_json(output_path, payload)
        return payload
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "schema": "persona_dream.entity_context_parse_error.v1",
            "grounding_ok": False,
            "stdout": completed.stdout[-4000:],
        }
    write_json(output_path, payload)
    return payload if isinstance(payload, dict) else {"grounding_ok": False, "entities": []}


def post_json(base_url: str, path: str, payload: dict[str, Any]) -> Any:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"memory {path} HTTP {error.code}: {detail}") from error


def count_score_modes(items: list[Any]) -> dict[str, int]:
    counts = {"bm25": 0, "graph": 0, "dense": 0}
    for item in items:
        if not isinstance(item, dict):
            continue
        scores = item.get("scores")
        if not isinstance(scores, dict):
            continue
        for key in counts:
            if float(scores.get(key) or 0) > 0:
                counts[key] += 1
    return counts


def summarize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: value.get(key) for key in ("ok", "status", "count", "upserted", "updated") if key in value}
    return value


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root must be object: {path}")
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sanitize_key(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in value).strip("_")[:240]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())
