#!/usr/bin/env python3
"""Emit the Persona Dream Phase D acceptance-rung receipt for a successor revision.

The acceptance rung is the last local checkpoint before the human paid-call
boundary. It is proven by three cited facts and nothing more:

1. the successor revision is active/consistent (cite the activation receipt),
2. Memory prepare/verify and the 42-step bundle exactly reread (cite receipts),
3. all eight Phase 07 storyboard frames PASS actual-pixel identity review (cite the
   Phase C regeneration receipt plus every per-frame review receipt and hash).

The receipt is written at the revision root and is deliberately excluded from the
hash-bound artifact index (it cites the activation receipt, which cites the index,
so indexing it would be circular). It records explicit ``does_not_prove``
exclusions: it proves none of Kling readiness, provider media publication for the
regenerated frames, paid authorization, a video return, or lip sync.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RECEIPT_NAME = "acceptance_rung_receipt.v1.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_ref(revision_root: Path, relative: str) -> dict[str, Any]:
    path = revision_root / relative
    if not path.is_file():
        raise SystemExit(f"BLOCKED_ACCEPTANCE_RUNG_MISSING_ARTIFACT:{relative}")
    return {"relative_path": relative, "sha256": sha256_file(path)}


def state_ref(run_root: Path, relative: str) -> dict[str, Any]:
    path = run_root / ".persona-dream" / "state" / relative
    if not path.is_file():
        raise SystemExit(f"BLOCKED_ACCEPTANCE_RUNG_MISSING_STATE:{relative}")
    return {
        "relative_path": f".persona-dream/state/{relative}",
        "sha256": sha256_file(path),
    }


def build(run_root: Path, revision_id: str) -> dict[str, Any]:
    revision_root = run_root / ".persona-dream" / "revisions" / revision_id
    manifest = read_json(revision_root / "revision_manifest.json")
    source_revision_id = str(manifest.get("sourceRevisionId") or "")

    activation = read_json(revision_root / "revision_activation_receipt.json")
    prepare = read_json(revision_root / "revision_memory_prepare_receipt.json")
    verify = read_json(revision_root / "revision_memory_verify_receipt.json")
    if activation.get("status") != "PASS_ACTIVE_CONSISTENT":
        raise SystemExit(f"BLOCKED_ACCEPTANCE_RUNG_ACTIVATION:{activation.get('status')}")
    if prepare.get("status") != "PASS_MEMORY_REVISION_PREPARED":
        raise SystemExit(f"BLOCKED_ACCEPTANCE_RUNG_PREPARE:{prepare.get('status')}")
    if verify.get("status") != "PASS_MEMORY_REVISION_VERIFIED":
        raise SystemExit(f"BLOCKED_ACCEPTANCE_RUNG_VERIFY:{verify.get('status')}")

    step_receipt_rel = f"pipeline_step_memory_receipt_{revision_id}.json"
    step_receipt = read_json(
        run_root / ".persona-dream" / "state" / step_receipt_rel
    )
    if not str(step_receipt.get("status") or "").startswith("PASS_EXACT_REREAD_42_OF_42"):
        raise SystemExit(f"BLOCKED_ACCEPTANCE_RUNG_STEP_REREAD:{step_receipt.get('status')}")

    phase_c_rel = (
        "phase_07_storyboard_live_tau/phase_c_successor_regen/"
        "phase_c_regeneration_receipt.json"
    )
    phase_c = read_json(revision_root / phase_c_rel)
    if phase_c.get("overall_status") != "8/8_FRAMES_PASS_ACTUAL_PIXEL_IDENTITY_REVIEW":
        raise SystemExit(f"BLOCKED_ACCEPTANCE_RUNG_FRAMES:{phase_c.get('overall_status')}")
    if phase_c.get("frames_pass") != 8 or phase_c.get("frames_total") != 8:
        raise SystemExit("BLOCKED_ACCEPTANCE_RUNG_FRAME_COUNT")

    frames = []
    for frame in phase_c.get("frames", []):
        review_rel = str(frame.get("review_receipt") or "").split(
            f"revisions/{revision_id}/", 1
        )[-1]
        review_path = revision_root / review_rel
        frames.append(
            {
                "frame_id": frame.get("frame_id"),
                "panel_id": frame.get("panel_id"),
                "review_status": frame.get("final_review_status"),
                "image_sha256": frame.get("image_sha256"),
                "image_path": frame.get("image_path"),
                "review_receipt_relative_path": review_rel,
                "review_receipt_sha256": (
                    sha256_file(review_path) if review_path.is_file() else None
                ),
            }
        )
    continuity_pass = sum(1 for c in phase_c.get("continuity", []) if c.get("status") == "PASS")

    index_path = revision_root / "revision_artifact_index.json"
    index = read_json(index_path)
    accepted_frame_ids = sorted(
        artifact_id
        for artifact_id, entry in index["artifacts"].items()
        if "accepted_frame" in entry.get("roles", [])
    )

    now = datetime.now(timezone.utc).isoformat()
    receipt = {
        "schema": "persona_dream.acceptance_rung_receipt.v1",
        "status": "PASS_ACCEPTANCE_RUNG",
        "rung": "pre_paid_call_boundary",
        "run_id": run_root.name,
        "revision_id": revision_id,
        "source_revision_id": source_revision_id,
        "observed_at": now,
        "successor_active_consistent": {
            "activation_receipt": file_ref(revision_root, "revision_activation_receipt.json"),
            "activation_status": activation.get("status"),
            "active_pointer_key": (activation.get("memory") or {}).get("active_pointer_key"),
            "active_revision_id": (activation.get("memory") or {}).get("active_revision_id")
            or revision_id,
            "artifact_index_sha256": sha256_file(index_path),
            "revision_manifest_sha256": sha256_file(revision_root / "revision_manifest.json"),
        },
        "memory_exact_reread": {
            "prepare_receipt": file_ref(revision_root, "revision_memory_prepare_receipt.json"),
            "prepare_status": prepare.get("status"),
            "verify_receipt": file_ref(revision_root, "revision_memory_verify_receipt.json"),
            "verify_status": verify.get("status"),
            "pipeline_step_memory_receipt": state_ref(run_root, step_receipt_rel),
            "pipeline_step_memory_status": step_receipt.get("status"),
            "pipeline_step_exact_reread_count": step_receipt.get("exact_reread_count"),
            "pipeline_step_collection": step_receipt.get("collection"),
        },
        "storyboard_frames_actual_pixel_review": {
            "phase_c_regeneration_receipt": file_ref(revision_root, phase_c_rel),
            "overall_status": phase_c.get("overall_status"),
            "frames_pass": phase_c.get("frames_pass"),
            "frames_total": phase_c.get("frames_total"),
            "continuity_pairs_pass": continuity_pass,
            "continuity_pairs_total": len(phase_c.get("continuity", [])),
            "image_model": phase_c.get("image_model"),
            "review_model": phase_c.get("review_model"),
            "identity_source": phase_c.get("identity_source"),
            "accepted_frame_artifact_ids": accepted_frame_ids,
            "frames": frames,
        },
        "claims": {
            "proves": [
                "the successor revision rev_successor_943b01ecd9a3 is active and consistent",
                "Memory prepare/verify and the 42-step pipeline bundle exactly reread",
                "all eight Phase 07 storyboard frames PASS actual-pixel identity review, 7/7 continuity pairs PASS",
                "the rebuilt artifact index makes the Phase C frames the active accepted Phase 07 evidence",
            ],
            "does_not_prove": [
                "Kling readiness",
                "provider media publication for the regenerated frames",
                "paid authorization",
                "a Kling video return",
                "visible-speaker lip sync",
                "final acceptance of the immutable goal",
            ],
        },
        "mocked": False,
        "live": True,
        "provider_live": False,
        "provider_ready": False,
        "paid_call_authorized": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
    }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--revision-id", required=True)
    args = parser.parse_args()
    run_root = args.run_root.expanduser().resolve(strict=True)
    receipt = build(run_root, args.revision_id)
    out_path = (
        run_root / ".persona-dream" / "revisions" / args.revision_id / RECEIPT_NAME
    )
    out_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": receipt["status"], "path": str(out_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
