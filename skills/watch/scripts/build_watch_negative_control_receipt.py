#!/usr/bin/env python3
"""Build Watch crop/reference negative-control receipt.

This receipt is the explicit guardrail between "a crop matched a reference" and
"Watch may render a named identity." Canary references, self-derived crop
references, and missing independent negative controls must fail closed.
"""

from __future__ import annotations

import argparse
import json
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
    / "watch_negative_control_receipt"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-receipt", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--threshold", type=float, default=0.72)
    args = parser.parse_args()

    source = read_json(args.source_receipt)
    receipt = build_negative_control_receipt(source, source_path=args.source_receipt, threshold=args.threshold)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "watch_negative_control_receipt.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    print("watch_negative_control_receipt", receipt["status"])
    print("comparison_count", receipt["counts"]["comparison_count"])
    print("failure_count", receipt["counts"]["failure_count"])
    print("receipt", out)
    return 0 if receipt["status"] in {"PASSED", "FAILED_CANARY_REFERENCES_NOT_INDEPENDENT", "FAILED_NEGATIVE_CONTROL"} else 2


def build_negative_control_receipt(
    source: dict[str, Any],
    *,
    source_path: Path,
    threshold: float,
) -> dict[str, Any]:
    similarity = ((source.get("receipts") or {}).get("crop_reference_similarity") or {})
    comparisons = similarity.get("comparisons") or []
    failures: list[dict[str, Any]] = []
    by_crop: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for comparison in comparisons:
        crop_id = comparison.get("crop_qdrant_point_id")
        if crop_id:
            by_crop[str(crop_id)].append(comparison)

    for crop_id, crop_comparisons in sorted(by_crop.items()):
        best = max(
            crop_comparisons,
            key=lambda item: item.get("cosine_similarity") if item.get("cosine_similarity") is not None else -1.0,
        )
        score = best.get("cosine_similarity")
        approval_scope = str(best.get("reference_approval_scope") or "").upper()
        approval_status = str(best.get("reference_approval_receipt_status") or "").upper()
        if approval_scope == "CANARY_PIPELINE_ONLY" and score is not None and float(score) >= threshold:
            failures.append(
                {
                    "crop_qdrant_point_id": crop_id,
                    "reference_qdrant_point_id": best.get("reference_qdrant_point_id"),
                    "entity_id": best.get("entity_id"),
                    "character_name": best.get("character_name"),
                    "actor_name": best.get("actor_name"),
                    "cosine_similarity": score,
                    "threshold": threshold,
                    "reference_approval_receipt_id": best.get("reference_approval_receipt_id"),
                    "reference_approval_receipt_status": approval_status,
                    "reference_approval_scope": approval_scope,
                    "failure_code": "CANARY_REFERENCE_HIGH_SIMILARITY_NOT_INDEPENDENT",
                    "reason": (
                        "The best reference match is scoped to CANARY_PIPELINE_ONLY. "
                        "This may prove plumbing, but it is not an independent "
                        "identity reference and cannot promote a named character label."
                    ),
                }
            )

    status = "PASSED"
    if failures:
        status = "FAILED_CANARY_REFERENCES_NOT_INDEPENDENT"
    elif similarity.get("status") != "SCORED_WITH_NEGATIVE_CONTROLS":
        status = "FAILED_NEGATIVE_CONTROL"

    return {
        "schema": "watch.negative_control_receipt.v1",
        "status": status,
        "created_at": utc_now(),
        "source_realtime_identity_receipt": display_path(source_path),
        "threshold": threshold,
        "input_similarity_status": similarity.get("status"),
        "claim_boundary": {
            "proves": [
                "crop/reference similarity was checked for canary-only high-similarity leakage",
                "identity promotion remains blocked when references are not independent production references",
            ],
            "does_not_prove": [
                "true negative-control coverage for production identity verification when status is failed",
                "human-approved character identity",
            ],
        },
        "failures": failures,
        "counts": {
            "comparison_count": len(comparisons),
            "candidate_crop_count": len(by_crop),
            "failure_count": len(failures),
        },
    }


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
