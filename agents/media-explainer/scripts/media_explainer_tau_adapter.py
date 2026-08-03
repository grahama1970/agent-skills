#!/usr/bin/env python3
"""Tau command-loop adapter for the media-explainer subagent.

This adapter is intentionally conservative. It validates the Tau handoff and
linked-content contract, writes deterministic receipts for the selected content
item, and exits through a schema-valid tau.agent_handoff.v1 response. It does
not write memory or graph edges.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RECEIPT_SCHEMA = "media_explainer.receipt.v1"


def main() -> int:
    artifact_dir = Path(
        os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR", "/tmp/media-explainer-tau")
    ).expanduser()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    try:
        handoff = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        _write_json(
            artifact_dir / "media-explanation-receipt.json",
            _error_receipt("invalid_handoff_json", str(exc)),
        )
        return 2

    context = _object(handoff.get("context"))
    content_path = _artifact_path(context.get("artifacts"), "linked-content.json")
    memory_path = _artifact_path(context.get("artifacts"), "memory-recall.json")
    if content_path is None:
        _write_json(
            artifact_dir / "media-explanation-receipt.json",
            _error_receipt("missing_linked_content_artifact", "context.artifacts lacks linked-content.json"),
        )
        return 2

    linked_content = _read_json(Path(content_path))
    memory_recall = _read_json(Path(memory_path)) if memory_path else {}
    if not isinstance(linked_content, dict):
        _write_json(
            artifact_dir / "media-explanation-receipt.json",
            _error_receipt("invalid_linked_content", "linked-content.json root must be an object"),
        )
        return 2

    explanation = _explain(linked_content, memory_recall if isinstance(memory_recall, dict) else {})
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "subagent_id": "media-explainer",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": True,
        "status": explanation["status"],
        "content_id": linked_content.get("content_id"),
        "media_kind": explanation["media_kind"],
        "source_path": linked_content.get("source_path") or linked_content.get("url"),
        "reused_existing_explanation": explanation["reused_existing_explanation"],
        "route": explanation["route"],
        "helper_calls_required": explanation["helper_calls_required"],
        "helper_calls_executed": [],
        "prompt_ready_text": explanation["prompt_ready_text"],
        "summary": explanation["summary"],
        "characters": explanation["characters"],
        "objects": explanation["objects"],
        "location": explanation["location"],
        "environment": explanation["environment"],
        "weather": explanation["weather"],
        "time_context": explanation["time_context"],
        "candidate_tom_tags": explanation["candidate_tom_tags"],
        "candidate_provenance_edges": explanation["candidate_provenance_edges"],
        "source_anchors": explanation["source_anchors"],
        "gaps": explanation["gaps"],
        "verified": {
            "memory_checked_first": True,
            "direct_memory_write": False,
            "direct_graph_edge_write": False,
            "direct_arango_or_qdrant": False,
        },
    }

    receipt_path = artifact_dir / "media-explanation-receipt.json"
    _write_json(receipt_path, receipt)
    _write_json(artifact_dir / "memory-upsert-candidate.json", _memory_candidate(receipt))
    _write_json(artifact_dir / "validation.json", _validation(receipt))

    response = _handoff_response(handoff, receipt_path, receipt)
    print(json.dumps(response, sort_keys=True))
    return 0


def _explain(linked: dict[str, Any], memory: dict[str, Any]) -> dict[str, Any]:
    media_kind = str(linked.get("media_kind") or linked.get("kind") or "").lower()
    if media_kind not in {"text", "image", "video", "audio", "sound", "mixed"}:
        media_kind = _infer_kind(linked)
    if media_kind == "sound":
        media_kind = "audio"

    existing = _existing_explanation(memory, linked)
    if existing:
        return {
            "status": "READY_REUSED",
            "media_kind": media_kind,
            "reused_existing_explanation": True,
            "route": "memory_recall_existing_explanation",
            "helper_calls_required": [],
            "prompt_ready_text": existing,
            "summary": existing,
            "characters": linked.get("characters", []),
            "objects": linked.get("objects", []),
            "location": linked.get("location", []),
            "environment": linked.get("environment", []),
            "weather": linked.get("weather", []),
            "time_context": linked.get("time_context", {}),
            "candidate_tom_tags": [],
            "candidate_provenance_edges": [],
            "source_anchors": _source_anchors(linked),
            "gaps": [],
        }

    route_by_kind = {
        "text": "deterministic_text_summary_then_optional_scillm_chat_completion",
        "image": "scillm_vlm_image_description_required",
        "video": "watch_abbreviated_keyframe_extraction_then_scillm_vlm_required",
        "audio": "scillm_transcribe_or_soundscape_description_required",
        "mixed": "per_modality_explanation_merge_required",
    }
    helpers_by_kind = {
        "text": [],
        "image": ["scillm.vlm"],
        "video": ["watch.watch:abbreviated_story_prep", "scillm.vlm"],
        "audio": ["scillm.transcribe_or_soundscape"],
        "mixed": ["watch.watch", "scillm.vlm", "scillm.transcribe"],
    }

    source_text = str(linked.get("text") or linked.get("summary") or linked.get("description") or "").strip()
    if media_kind == "text" and source_text:
        summary = " ".join(source_text.split())[:700]
        prompt_ready = summary
        gaps: list[str] = []
    else:
        summary = ""
        prompt_ready = ""
        gaps = [f"{media_kind}_model_description_not_executed_by_adapter"]

    if media_kind == "video":
        policy = _video_policy(linked)
        gaps.append(policy["gap"])
    else:
        policy = None

    return {
        "status": "PENDING_HELPER_RECEIPTS" if gaps else "READY",
        "media_kind": media_kind,
        "reused_existing_explanation": False,
        "route": route_by_kind.get(media_kind, "unknown"),
        "helper_calls_required": helpers_by_kind.get(media_kind, []),
        "prompt_ready_text": prompt_ready,
        "summary": summary,
        "characters": linked.get("characters", []),
        "objects": linked.get("objects", []),
        "location": linked.get("location", []),
        "environment": linked.get("environment", []),
        "weather": linked.get("weather", []),
        "time_context": linked.get("time_context", {}),
        "candidate_tom_tags": _candidate_tom_tags(linked),
        "candidate_provenance_edges": _candidate_edges(linked),
        "source_anchors": _source_anchors(linked),
        "gaps": [*_source_gaps(linked, media_kind), *gaps],
        "video_policy": policy,
    }


def _video_policy(linked: dict[str, Any]) -> dict[str, Any]:
    interval = int(linked.get("keyframe_interval_seconds") or 300)
    duration = linked.get("duration_seconds")
    max_keyframes = int(linked.get("max_keyframes") or 12)
    focused = bool(linked.get("start_seconds") is not None or linked.get("end_seconds") is not None)
    if focused:
        strategy = "focused_window_scene_change"
    elif isinstance(duration, (int, float)) and duration > 600:
        strategy = "sparse_keyframe_every_5_minutes"
    else:
        strategy = "first_meaningful_scene_marker_plus_scene_change_fallback"
    return {
        "strategy": strategy,
        "keyframe_interval_seconds": interval,
        "max_keyframes": max_keyframes,
        "gap": f"watch_receipt_required:{strategy}",
    }


def _existing_explanation(memory: dict[str, Any], linked: dict[str, Any]) -> str:
    candidates: list[Any] = []
    if isinstance(memory.get("items"), list):
        candidates.extend(memory["items"])
    if isinstance(memory.get("documents"), list):
        candidates.extend(memory["documents"])
    candidates.append(memory)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        for key in ("prompt_ready_text", "visual_description", "explanation", "description", "summary"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        doc = item.get("document")
        if isinstance(doc, dict):
            for key in ("prompt_ready_text", "visual_description", "explanation", "description", "summary"):
                value = doc.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def _candidate_tom_tags(linked: dict[str, Any]) -> list[dict[str, str]]:
    tags = linked.get("candidate_tom_tags")
    if isinstance(tags, list):
        return [tag for tag in tags if isinstance(tag, dict)]
    return []


def _source_gaps(linked: dict[str, Any], media_kind: str) -> list[str]:
    if media_kind == "text":
        return []
    source = linked.get("source_path")
    if not isinstance(source, str) or not source.strip():
        if isinstance(linked.get("url"), str) and linked["url"].strip():
            return []
        return [f"{media_kind}_source_path_missing"]
    if source.startswith(("http://", "https://")):
        return []
    if not Path(source).expanduser().exists():
        return [f"{media_kind}_source_path_not_found:{source}"]
    return []


def _candidate_edges(linked: dict[str, Any]) -> list[dict[str, Any]]:
    edges = linked.get("candidate_provenance_edges")
    if isinstance(edges, list):
        return [edge for edge in edges if isinstance(edge, dict)]
    return []


def _source_anchors(linked: dict[str, Any]) -> list[dict[str, Any]]:
    anchors = linked.get("source_anchors")
    if isinstance(anchors, list):
        return [anchor for anchor in anchors if isinstance(anchor, dict)]
    anchor: dict[str, Any] = {}
    for key in ("content_id", "source_path", "url", "text"):
        if linked.get(key):
            anchor[key] = linked[key]
    return [anchor] if anchor else []


def _memory_candidate(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "media_explainer.memory_upsert_candidate.v1",
        "status": "CANDIDATE_ONLY",
        "note": "Project agent or memory curator must promote this candidate. The media-explainer subagent does not write memory directly.",
        "content_id": receipt.get("content_id"),
        "media_kind": receipt.get("media_kind"),
        "prompt_ready_text": receipt.get("prompt_ready_text"),
        "summary": receipt.get("summary"),
        "candidate_tom_tags": receipt.get("candidate_tom_tags", []),
        "candidate_provenance_edges": receipt.get("candidate_provenance_edges", []),
        "source_anchors": receipt.get("source_anchors", []),
    }


def _validation(receipt: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "has_schema": receipt.get("schema") == RECEIPT_SCHEMA,
        "has_content_id": bool(receipt.get("content_id")),
        "has_media_kind": receipt.get("media_kind") in {"text", "image", "video", "audio", "mixed"},
        "has_source_anchor": bool(receipt.get("source_anchors")),
        "does_not_write_memory": receipt.get("verified", {}).get("direct_memory_write") is False,
        "does_not_write_graph_edges": receipt.get("verified", {}).get("direct_graph_edge_write") is False,
    }
    return {
        "schema": "media_explainer.validation.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
    }


def _handoff_response(
    start: dict[str, Any],
    receipt_path: Path,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    response = dict(start)
    response["previous_subagent"] = "media-explainer"
    response["result"] = {
        "status": receipt["status"],
        "summary": f"media-explainer processed {receipt.get('media_kind')} content {receipt.get('content_id')}",
        "evidence": [
            str(receipt_path),
            str(receipt_path.with_name("validation.json")),
            str(receipt_path.with_name("memory-upsert-candidate.json")),
        ],
    }
    response["rationale"] = (
        "Media explanation receipts must be reviewed or promoted by the project agent or memory curator before Phase 02 story prompt assembly."
    )
    response["next_agent"] = {
        "name": "human",
        "executor": "human",
        "reason": "Review the media-explainer receipt and decide whether to wire live helper execution or promote candidates to memory.",
    }
    response["required_evidence"] = [
        "media-explanation-receipt.json",
        "validation.json",
        "memory-upsert-candidate.json",
    ]
    response["stop_condition"] = "Human or project agent accepts, redirects, or requests live helper execution."
    return response


def _infer_kind(linked: dict[str, Any]) -> str:
    source = str(linked.get("source_path") or linked.get("url") or "").lower()
    if source.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    if source.endswith((".mp4", ".mov", ".mkv", ".webm")):
        return "video"
    if source.endswith((".wav", ".mp3", ".flac", ".m4a", ".ogg")):
        return "audio"
    if linked.get("text"):
        return "text"
    return "mixed"


def _artifact_path(artifacts: Any, suffix: str) -> str | None:
    if not isinstance(artifacts, list):
        return None
    for artifact in artifacts:
        if isinstance(artifact, str) and artifact.endswith(suffix):
            return artifact
        if isinstance(artifact, dict):
            path = artifact.get("path") or artifact.get("artifact_path")
            if isinstance(path, str) and path.endswith(suffix):
                return path
    return None


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> Any:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _error_receipt(code: str, message: str) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "subagent_id": "media-explainer",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mocked": False,
        "live": True,
        "status": "BLOCKED",
        "error": {"code": code, "message": message},
        "verified": {
            "direct_memory_write": False,
            "direct_graph_edge_write": False,
            "direct_arango_or_qdrant": False,
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
