#!/usr/bin/env python3
"""Re-review all 8 Phase C successor frames under the HARDENED identity reviewer.

Step 3 of the reviewer-leniency remediation. The Phase C 8/8 first-attempt PASS
was produced under the pre-hardening ``_identity_review_prompt`` (prompt hash
b09a50.../e9b670...). After hardening the reviewer prompt (specific-identity
gate + age clause + feature grounding + complexion/adversarial-divergence check),
the accepted successor frames must be re-reviewed on actual pixels to see which
still pass. This does NOT reuse cached receipts (unlike the phase_c resume path);
every frame gets a fresh review with the new prompt hash.

Live scillm gpt-5.5 vision only. NO image generation, NO paid provider calls.
Writes per-frame v2 receipts and a roll-up.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
NODE_PATH = SCRIPTS / "phase07_storyboard_tau_node.py"
PHASE_C_PATH = SCRIPTS / "phase_c_regenerate_storyboard_frames.py"

REVISION_ID = "rev_successor_943b01ecd9a3"
RUN_ID = "pipeline-complete"
REVISION_ROOT = SKILL_ROOT / "reports" / "pipeline-complete" / ".persona-dream" / "revisions" / REVISION_ID
PHASE07_ROOT = REVISION_ROOT / "phase_07_storyboard_live_tau"
ACCEPTED_FRAMES_DIR = PHASE07_ROOT / "phase_c_successor_regen" / "generated_storyboard_frames"
PACKET_PATH = PHASE07_ROOT / "storyboard_packet.json"

OUT_RECEIPTS = REVISION_ROOT / "hardened_rereview" / "case_receipts"
OUT_SUMMARY = REVISION_ROOT / "hardened_rereview" / "hardened_rereview_summary.v2.json"

PANELS = ["sb_001", "sb_002", "sb_003", "sb_004"]
FRAME_KEYS = ["start_frame", "end_frame"]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    node = _load("phase07_storyboard_tau_node", NODE_PATH)
    phase_c = _load("phase_c_regenerate_storyboard_frames", PHASE_C_PATH)
    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    panels = {p["panel_id"]: p for p in packet["panels"]}
    refs = [dict(r) for r in phase_c._panel_refs()]
    required = ["Embry", "Kai"]

    OUT_RECEIPTS.mkdir(parents=True, exist_ok=True)
    results = []
    for panel_id in PANELS:
        for frame_key in FRAME_KEYS:
            frame_id = f"{panel_id}_{frame_key}"
            img = ACCEPTED_FRAMES_DIR / f"{frame_id}.png"
            panel = dict(panels[panel_id])
            panel["required_entities"] = required
            panel["references"] = refs
            prompt = node._identity_review_prompt(panel, frame_key=frame_key, required_entities=required)
            prompt_sha = phase_c._sha256_text(prompt)
            case_dir = OUT_RECEIPTS / frame_id
            case_dir.mkdir(parents=True, exist_ok=True)
            review = node._run_identity_continuity_review(
                {"path": str(img)}, panel=panel, frame_key=frame_key,
                required_entities=required, identity_review_policy=phase_c.IDENTITY_REVIEW_POLICY,
                receipts_dir=case_dir,
            )
            raw = review.get("raw_response") if isinstance(review.get("raw_response"), dict) else {}
            row = {
                "frame_id": frame_id,
                "panel_id": panel_id,
                "frame_key": frame_key,
                "image_path": str(img),
                "image_sha256": phase_c._sha256_file(img) if img.exists() else None,
                "hardened_status": review.get("status"),
                "blocking_findings": review.get("blocking_findings"),
                "visible_entities": review.get("visible_entities"),
                "observed_divergences": raw.get("observed_divergences"),
                "verified_facial_features": raw.get("verified_facial_features"),
                "review_prompt_sha256": prompt_sha,
                "review_receipt_path": review.get("receipt_path"),
            }
            results.append(row)
            print(f"[{frame_id}] hardened={row['hardened_status']} "
                  f"blocking={len(row['blocking_findings'] or [])}")

    n_pass = sum(1 for r in results if r["hardened_status"] == "PASS")
    summary = {
        "schema": "persona_dream.hardened_rereview_summary.v2",
        "created_at": _now(),
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "reviewer": {
            "function": "phase07_storyboard_tau_node._run_identity_continuity_review",
            "model": "gpt-5.5",
            "review_schema": "persona_dream.identity_continuity_review.v1",
            "hardened_prompt_sha256": results[0]["review_prompt_sha256"] if results else None,
        },
        "prior_result": "Phase C reported 8/8 first-attempt PASS under the pre-hardening reviewer prompt",
        "frames_total": len(results),
        "frames_pass_hardened": n_pass,
        "frames_fail_hardened": [r["frame_id"] for r in results if r["hardened_status"] != "PASS"],
        "overall_status": f"{n_pass}/{len(results)}_FRAMES_PASS_HARDENED_IDENTITY_REVIEW",
        "frames": results,
        "mocked": False,
        "live": True,
        "provider_live": False,
        "paid_call_authorized": False,
    }
    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall_status": summary["overall_status"],
                      "frames_fail_hardened": summary["frames_fail_hardened"],
                      "summary_path": str(OUT_SUMMARY)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
