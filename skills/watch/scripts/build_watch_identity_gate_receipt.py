#!/usr/bin/env python3
"""Build a fail-closed identity gate receipt from Watch similarity receipts.

This is the boundary between live person tracking and named character labels.
YOLO/ByteTrack can produce person tracks, and crop/reference similarity can
score candidates, but Watch only promotes a named identity when every required
receipt class is present and the references are approved for identity
promotion. Canary-only reference receipts deliberately keep the UI label
withheld.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "architecture"
    / "generated"
    / "watch_realtime_identity_memory_loop_live_approval_linked_20260628T1315Z"
    / "watch_realtime_identity_memory_loop_live_receipt.json"
)
DEFAULT_OUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "architecture"
    / "generated"
    / "watch_identity_gate_receipt"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-receipt", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--qdrant-eval-receipt", type=Path)
    parser.add_argument("--accepted-character")
    parser.add_argument("--negative-control-receipt", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--threshold", type=float, default=0.72)
    parser.add_argument("--conflict-threshold", type=float, default=0.90)
    parser.add_argument("--suggestion-threshold", type=float, default=0.82)
    args = parser.parse_args()

    if args.qdrant_eval_receipt:
        source = read_json(args.qdrant_eval_receipt)
        receipt = build_qdrant_recall_identity_stop_receipt(
            source,
            source_path=args.qdrant_eval_receipt,
            accepted_character=args.accepted_character or source.get("truth_character"),
            conflict_threshold=args.conflict_threshold,
            suggestion_threshold=args.suggestion_threshold,
        )
        args.out_dir.mkdir(parents=True, exist_ok=True)
        out = args.out_dir / "watch_qdrant_recall_identity_stop_receipt.json"
        out.write_text(json.dumps(receipt, indent=2, sort_keys=False) + "\n", encoding="utf-8")

        print("watch_qdrant_recall_identity_stop_receipt", receipt["status"])
        print("evaluated_count", receipt["counts"]["evaluated_count"])
        print("supported_count", receipt["counts"]["supported_count"])
        print("conflict_count", receipt["counts"]["conflict_count"])
        print("tentative_suggestion_count", receipt["counts"]["tentative_suggestion_count"])
        print("receipt", out)
        return 0 if receipt["status"] in {"IDENTITY_RECALL_SUPPORTED", "IDENTITY_RECALL_CONFLICTS_FOUND"} else 2

    source = read_json(args.source_receipt)
    negative_control = read_json(args.negative_control_receipt) if args.negative_control_receipt else None
    receipt = build_identity_gate_receipt(
        source,
        source_path=args.source_receipt,
        threshold=args.threshold,
        negative_control_receipt=negative_control,
        negative_control_path=args.negative_control_receipt,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "watch_identity_gate_receipt.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    print("watch_identity_gate_receipt", receipt["status"])
    print("candidate_count", receipt["counts"]["candidate_count"])
    print("promoted_count", receipt["counts"]["promoted_count"])
    print("withheld_count", receipt["counts"]["withheld_count"])
    print("receipt", out)
    return 0 if receipt["status"] in {"IDENTITY_LABELS_WITHHELD", "IDENTITY_LABELS_PROMOTED"} else 2


def build_identity_gate_receipt(
    source: dict[str, Any],
    *,
    source_path: Path,
    threshold: float,
    negative_control_receipt: dict[str, Any] | None = None,
    negative_control_path: Path | None = None,
) -> dict[str, Any]:
    receipts = source.get("receipts") or {}
    similarity = receipts.get("crop_reference_similarity") or {}
    recall = receipts.get("memory_recall") or {}
    memory = receipts.get("memory_upsert") or {}
    reference_embeddings = receipts.get("reference_embeddings") or {}

    comparisons = similarity.get("comparisons") or []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for comparison in comparisons:
        crop_id = comparison.get("crop_qdrant_point_id")
        if crop_id:
            grouped[str(crop_id)].append(comparison)

    candidates: list[dict[str, Any]] = []
    for crop_point_id, items in sorted(grouped.items()):
        best = best_comparison(items)
        blockers = gate_blockers(
            best,
            similarity_receipt=similarity,
            memory_receipt=memory,
            recall_receipt=recall,
            negative_control_receipt=negative_control_receipt,
            threshold=threshold,
        )
        promoted = not blockers
        candidates.append(
            {
                "crop_qdrant_point_id": crop_point_id,
                "entity_id": best.get("entity_id"),
                "character_name": best.get("character_name"),
                "actor_name": best.get("actor_name"),
                "best_similarity": best.get("cosine_similarity"),
                "threshold": threshold,
                "reference_qdrant_point_id": best.get("reference_qdrant_point_id"),
                "reference_approval_receipt_id": best.get("reference_approval_receipt_id"),
                "reference_approval_receipt_status": best.get("reference_approval_receipt_status"),
                "reference_approval_scope": best.get("reference_approval_scope"),
                "identity_status": "IDENTITY_SUPPORTED" if promoted else "IDENTITY_WITHHELD",
                "ui_label_policy": "ALLOW_NAMED_LABEL" if promoted else "RENDER_PERSON_OBSERVATION_ONLY",
                "promotion_allowed": promoted,
                "blockers": blockers,
            }
        )

    promoted_count = sum(1 for item in candidates if item["promotion_allowed"])
    withheld_count = len(candidates) - promoted_count
    return {
        "schema": "watch.identity_gate_receipt.v1",
        "status": "IDENTITY_LABELS_PROMOTED" if promoted_count else "IDENTITY_LABELS_WITHHELD",
        "created_at": utc_now(),
        "source_realtime_identity_receipt": display_path(source_path),
        "threshold": threshold,
        "input_receipt_statuses": {
            "realtime_identity_loop": source.get("status"),
            "reference_embeddings": reference_embeddings.get("status"),
            "crop_reference_similarity": similarity.get("status"),
            "memory_upsert": memory.get("status"),
            "memory_recall": recall.get("status"),
            "negative_control": negative_control_receipt.get("status") if negative_control_receipt else None,
        },
        "source_negative_control_receipt": display_path(negative_control_path) if negative_control_path else None,
        "claim_boundary": {
            "proves": [
                "crop/reference similarity comparisons were evaluated against identity-promotion gates",
                "UI label policy is explicit for each candidate crop",
            ],
            "does_not_prove": [
                "final human-approved character identity when promotion is withheld",
                "scene truth from Brave or public image search alone",
            ],
        },
        "candidates": candidates,
        "counts": {
            "comparison_count": len(comparisons),
            "candidate_count": len(candidates),
            "promoted_count": promoted_count,
            "withheld_count": withheld_count,
            "memory_recall_item_count": (recall.get("counts") or {}).get("item_count", 0),
            "reference_embedding_count": (reference_embeddings.get("counts") or {}).get("qdrant_written", 0),
        },
    }


def build_qdrant_recall_identity_stop_receipt(
    source: dict[str, Any],
    *,
    source_path: Path,
    accepted_character: str | None,
    conflict_threshold: float = 0.90,
    suggestion_threshold: float = 0.82,
) -> dict[str, Any]:
    """Turn live Memory/Qdrant crop recall into label propagation gates.

    A YOLO track label is allowed to propagate only while crop recall supports
    the accepted identity. A high-confidence recall for a different character is
    treated as an identity handoff/control point, not as training data.
    """

    accepted_key = normalize_identity_name(accepted_character)
    results = source.get("results") or []
    decisions: list[dict[str, Any]] = []
    for result in results:
        top = result.get("top_suggestion") or {}
        top_character = top.get("character_name")
        top_key = normalize_identity_name(top_character)
        confidence = numeric_score(top.get("confidence"))
        if confidence is None:
            confidence = numeric_score(top.get("top_visual_score"))

        status = "NO_RECALL_SUGGESTION"
        ui_label_policy = "RESET_TO_YOLO_TRACK_OBSERVATION"
        label_to_render = result.get("yolo_track_key") or "YOLO track"
        stop_control_required = False
        eligible_for_training = False
        blockers: list[str] = []

        if not top_key or confidence is None:
            blockers.append("MEMORY_RECALL_TOP_SUGGESTION_MISSING")
        elif accepted_key and top_key == accepted_key and confidence >= suggestion_threshold:
            status = "ACCEPTED_LABEL_SUPPORTED_BY_RECALL"
            ui_label_policy = "ALLOW_ACCEPTED_TRACK_LABEL"
            label_to_render = str(accepted_character)
            eligible_for_training = True
        elif accepted_key and top_key != accepted_key and confidence >= conflict_threshold:
            status = "IDENTITY_CONFLICT_STOP_REQUIRED"
            ui_label_policy = "RENDER_CONFLICT_AND_STOP_TRACK_PROPAGATION"
            label_to_render = f"{top_character}? {confidence:.2f}"
            stop_control_required = True
            blockers.append("MEMORY_RECALL_HIGH_CONFIDENCE_OTHER_ACTOR")
        elif top_key and confidence >= suggestion_threshold:
            status = "TENTATIVE_RECALL_SUGGESTION"
            ui_label_policy = "RENDER_TENTATIVE_SUGGESTION_UNTIL_ACCEPTED"
            label_to_render = f"{top_character}? {confidence:.2f}"
            blockers.append("HUMAN_ACCEPTANCE_REQUIRED")
        else:
            blockers.append("MEMORY_RECALL_CONFIDENCE_BELOW_SUGGESTION_THRESHOLD")

        decisions.append(
            {
                "sample_index": result.get("sample_index"),
                "time_seconds": result.get("time_seconds"),
                "yolo_track_key": result.get("yolo_track_key") or source.get("yolo_track_key"),
                "crop_path": result.get("crop_path"),
                "accepted_character": accepted_character,
                "top_character": top_character,
                "top_actor": top.get("actor_name"),
                "top_confidence": confidence,
                "top_display_label": top.get("display_label"),
                "status": status,
                "ui_label_policy": ui_label_policy,
                "label_to_render": label_to_render,
                "stop_control_required": stop_control_required,
                "eligible_for_training": eligible_for_training,
                "blockers": blockers,
                "supporting_items": [
                    {
                        "character_name": item.get("character_name"),
                        "actor_name": item.get("actor_name"),
                        "confidence": numeric_score(item.get("confidence")),
                        "visual_score": numeric_score(item.get("visual_score")),
                        "crop_path": item.get("crop_path"),
                    }
                    for item in (result.get("items") or [])[:5]
                ],
            }
        )

    conflict_count = sum(1 for item in decisions if item["status"] == "IDENTITY_CONFLICT_STOP_REQUIRED")
    supported_count = sum(1 for item in decisions if item["status"] == "ACCEPTED_LABEL_SUPPORTED_BY_RECALL")
    tentative_count = sum(1 for item in decisions if item["status"] == "TENTATIVE_RECALL_SUGGESTION")
    no_suggestion_count = sum(1 for item in decisions if item["status"] == "NO_RECALL_SUGGESTION")

    return {
        "schema": "watch.qdrant_recall_identity_stop_receipt.v1",
        "status": "IDENTITY_RECALL_CONFLICTS_FOUND" if conflict_count else "IDENTITY_RECALL_SUPPORTED",
        "created_at": utc_now(),
        "source_qdrant_eval_receipt": display_path(source_path),
        "accepted_character": accepted_character,
        "conflict_threshold": conflict_threshold,
        "suggestion_threshold": suggestion_threshold,
        "input_transport": source.get("input_transport"),
        "mocked": source.get("mocked", False),
        "live": source.get("live", False),
        "claim_boundary": {
            "proves": [
                "live Memory/Qdrant crop recall was evaluated against the accepted track label",
                "high-confidence recall for another character creates an identity stop requirement",
                "only supported accepted-label samples are eligible for training/readiness counting",
            ],
            "does_not_prove": [
                "browser UI applied the stop point",
                "future frames are correctly labeled without re-running recall",
            ],
        },
        "counts": {
            "evaluated_count": len(decisions),
            "supported_count": supported_count,
            "conflict_count": conflict_count,
            "tentative_suggestion_count": tentative_count,
            "no_suggestion_count": no_suggestion_count,
            "training_eligible_count": sum(1 for item in decisions if item["eligible_for_training"]),
            "stop_control_required_count": sum(1 for item in decisions if item["stop_control_required"]),
        },
        "decisions": decisions,
    }


def normalize_identity_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def numeric_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def best_comparison(items: list[dict[str, Any]]) -> dict[str, Any]:
    return max(items, key=lambda item: item.get("cosine_similarity") if item.get("cosine_similarity") is not None else -1.0)


def gate_blockers(
    comparison: dict[str, Any],
    *,
    similarity_receipt: dict[str, Any],
    memory_receipt: dict[str, Any],
    recall_receipt: dict[str, Any],
    negative_control_receipt: dict[str, Any] | None,
    threshold: float,
) -> list[str]:
    blockers: list[str] = []
    score = comparison.get("cosine_similarity")
    if score is None:
        blockers.append("SIMILARITY_SCORE_MISSING")
    elif float(score) < threshold:
        blockers.append("SIMILARITY_BELOW_THRESHOLD")

    approval_status = str(comparison.get("reference_approval_receipt_status") or "").upper()
    approval_scope = str(comparison.get("reference_approval_scope") or "").upper()
    if approval_status not in {"APPROVED", "APPROVED_IDENTITY_PROMOTION"}:
        blockers.append("REFERENCE_NOT_APPROVED_FOR_IDENTITY_PROMOTION")
    if approval_scope and approval_scope != "IDENTITY_PROMOTION":
        blockers.append("REFERENCE_SCOPE_NOT_IDENTITY_PROMOTION")

    if negative_control_receipt is None:
        blockers.append("NEGATIVE_CONTROL_RECEIPT_MISSING")
    elif negative_control_receipt.get("status") != "PASSED":
        blockers.append("NEGATIVE_CONTROL_FAILED")
    elif similarity_receipt.get("status") != "SCORED_WITH_NEGATIVE_CONTROLS":
        blockers.append("NEGATIVE_CONTROL_RECEIPT_MISSING")
    if memory_receipt.get("status") != "WRITTEN":
        blockers.append("MEMORY_UPSERT_RECEIPT_MISSING")
    if recall_receipt.get("status") != "QUERIED" or (recall_receipt.get("counts") or {}).get("item_count", 0) <= 0:
        blockers.append("MEMORY_RECALL_PROOF_MISSING")
    return blockers


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
