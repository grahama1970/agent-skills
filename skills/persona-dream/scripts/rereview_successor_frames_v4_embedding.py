#!/usr/bin/env python3
"""Part 3 — re-run the 8 accepted successor frames through the augmented reviewer.

Augmented reviewer = hardened full-frame VLM gate (scene/wardrobe/composition +
face visibility) with the deterministic ArcFace embedding subgate as the IDENTITY
verdict authority (calibration v4). Writes fresh per-frame receipts and an
aggregate v4 re-review receipt with the embedding cosine scores recorded.

No image generation and no paid provider calls; the accepted frames are read-only
inputs. gpt-5.5 full-frame vision calls via scillm are authorized. If a frame
FAILs identity, the bounded GPT Image 2 repair loop is the follow-up (not run here
unless a failure appears — all 8 already PASS the embedding subgate in
reviewer_calibration_receipt.v4.json).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
REVISION_ID = "rev_successor_943b01ecd9a3"
RUN_ID = "pipeline-complete"
REV_ROOT = SKILL_ROOT / "reports" / RUN_ID / ".persona-dream" / "revisions" / REVISION_ID
SUCCESSOR_DIR = REV_ROOT / "phase_07_storyboard_live_tau" / "phase_c_successor_regen" / "generated_storyboard_frames"
DEFAULT_OUT = REV_ROOT / "reviewer_calibration_v4" / "successor_rereview"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--panels", default="sb_001,sb_002,sb_003,sb_004")
    args = ap.parse_args()

    node = _load("phase07_storyboard_tau_node", SCRIPTS / "phase07_storyboard_tau_node.py")
    phase_c = _load("phase_c_regenerate_storyboard_frames", SCRIPTS / "phase_c_regenerate_storyboard_frames.py")
    packet = json.loads((SKILL_ROOT / "reports/pipeline-complete/.persona-dream/revisions" / REVISION_ID
                         / "phase_07_storyboard_live_tau" / "storyboard_packet.json").read_text())
    panels = {p["panel_id"]: p for p in packet["panels"]}
    required = ["Embry", "Kai"]
    refs = phase_c._panel_refs()
    args.out.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    all_pass = True
    for panel_id in args.panels.split(","):
        panel = dict(panels[panel_id])
        panel["required_entities"] = required
        panel["references"] = refs
        for frame_key in ("start_frame", "end_frame"):
            fp = SUCCESSOR_DIR / f"{panel_id}_{frame_key}.png"
            if not fp.exists():
                continue
            review = node._run_identity_continuity_review(
                {"path": str(fp)}, panel=panel, frame_key=frame_key,
                required_entities=required, identity_review_policy=phase_c.IDENTITY_REVIEW_POLICY,
                receipts_dir=args.out,
            )
            emb = review.get("face_embedding_subgate", {})
            scores = {er["entity"]: er.get("best_cosine") for er in emb.get("entity_results", [])}
            status = review.get("status")
            if status != "PASS":
                all_pass = False
            rows.append({
                "frame_id": f"{panel_id}_{frame_key}",
                "status": status,
                "full_frame_status": review.get("full_frame_status"),
                "identity_authority": review.get("identity_authority"),
                "embedding_status": emb.get("status"),
                "embedding_scores": scores,
                "embedding_threshold": emb.get("threshold"),
                "advisory_face_crop_status": (review.get("face_crop_subgate_advisory") or {}).get("status"),
                "gate_fired": review.get("gate_fired"),
                "blocking_findings": review.get("blocking_findings"),
                "review_receipt_path": review.get("receipt_path"),
            })
            print(f"{panel_id}_{frame_key}: {status} full_frame={review.get('full_frame_status')} "
                  f"emb={emb.get('status')} {scores}")

    receipt = {
        "schema": "persona_dream.successor_rereview_v4.v1",
        "overall_status": "SUCCESSOR_REREVIEW_PASS" if all_pass and len(rows) == 8 else "SUCCESSOR_REREVIEW_INCOMPLETE_OR_FAILED",
        "created_at": _now(),
        "revision_id": REVISION_ID,
        "run_id": RUN_ID,
        "identity_authority": "insightface_buffalo_l_cosine",
        "calibration_receipt": "reviewer_calibration_receipt.v4.json",
        "frames_total": len(rows),
        "frames_pass": sum(1 for r in rows if r["status"] == "PASS"),
        "all_pass": all_pass,
        "frames": rows,
        "repair_needed": [r["frame_id"] for r in rows if r["status"] != "PASS"],
        "live": True, "mocked": False, "paid_call_authorized": False, "provider_live": False,
    }
    out_receipt = args.out / "successor_rereview_v4_receipt.json"
    out_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nWROTE {out_receipt}  status={receipt['overall_status']} "
          f"{receipt['frames_pass']}/{receipt['frames_total']} PASS")
    return 0 if receipt["overall_status"] == "SUCCESSOR_REREVIEW_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
