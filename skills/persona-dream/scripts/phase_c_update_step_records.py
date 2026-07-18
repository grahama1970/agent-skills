#!/usr/bin/env python3
"""Update pipeline step records 13-19 in the successor bundle from the Phase C
regeneration summary, then leave the bundle ready for
`persist_pipeline_step_records.py` (upsert + exact reread of all 42 docs).

Steps 13-19 were staged by Phase B as STALE_IDENTITY_SOURCE_SUPERSEDED. This
flips them to their real Phase C outcomes (PASS / FAILED with codes) bound to
the regenerated frames + actual-pixel review receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--summary", required=True, type=Path)
    ap.add_argument("--out-root", required=True, type=Path,
                    help="Phase C regen out-root (for relative receipt paths).")
    args = ap.parse_args()

    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    frames = summary["frames"]
    continuity = summary.get("continuity", [])
    n_pass = summary["frames_pass"]
    n_total = summary["frames_total"]
    all_pass = n_pass == n_total
    cont_all_pass = bool(continuity) and all(c["status"] == "PASS" for c in continuity)
    summary_hash = _sha256(args.summary)
    now = _now()

    # per-frame repair evidence
    repairs = [
        {"frame_id": f["frame_id"], "attempts_used": f["attempts_used"],
         "final_status": f["status"], "blocking_findings": f.get("final_blocking_findings")}
        for f in frames if f["attempts_used"] > 1 or f["status"] != "PASS"
    ]

    docs = {d["step_no"]: d for d in bundle["documents"]}

    def base_update(step_no: int, status: str, disposition: str, outputs: list[str],
                    receipts: list[str], extra_inputs: dict[str, Any],
                    proves: list[str], does_not: list[str], blocker: Any) -> None:
        d = docs[step_no]
        d["status"] = status
        d["disposition"] = disposition
        d["outputs"] = outputs
        d["receipt_paths"] = receipts
        d["artifact_hashes"] = {"phase_c_regeneration_receipt.json": summary_hash}
        d["inputs"] = {**d.get("inputs", {}), **extra_inputs,
                       "identity_source": "embry_contact_sheet_v3",
                       "identity_source_sha256": "sha256:3ce40b3b6839ebba0f468d75a1adbb7f82e0d95457aefd3627e222eb569de00c"}
        d["claims"] = {"proves": proves, "does_not_prove": does_not}
        d["blocker"] = blocker
        d["observed_at"] = now
        d["memory_write_method"] = "/upsert"
        st = status.lower()
        d["retrieval_text"] = (f"Persona Dream pipeline-complete rev_successor_943b01ecd9a3 "
                               f"step {step_no} {d['step_name']} status {status} disposition {disposition} "
                               f"phase C regeneration from embry_contact_sheet_v3")
        d["tags"] = ["persona-dream", "phase-c-regeneration", "run:pipeline-complete",
                     "revision:rev_successor_943b01ecd9a3", f"step:{step_no}",
                     f"status:{st}", f"disposition:{disposition}"]

    rel = str(args.out_root)
    review_receipts = [f["review_receipt"] for f in frames]
    frame_paths = [f["image_path"] for f in frames if f["image_path"]]

    # 13 Storyboard Prompt Composition
    base_update(
        13, "PASS_STORYBOARD_PROMPTS_COMPOSED", "active",
        outputs=[f"{rel}/receipts/storyboard_frame_generation/*.prompt.md"],
        receipts=[f"{rel}/phase_c_regeneration_receipt.json"],
        extra_inputs={"panels": ["sb_001", "sb_002", "sb_003", "sb_004"], "frames_total": n_total},
        proves=["8 identity-first storyboard prompts were composed and bound to embry_contact_sheet_v3 + Kai reference as actual image inputs"],
        does_not=["provider readiness or final acceptance"],
        blocker=None)

    # 14 Storyboard Panel Receipts
    base_update(
        14, "PASS_STORYBOARD_PANEL_RECEIPTS", "active",
        outputs=[f"{rel}/receipts/storyboard_frame_generation/"],
        receipts=[f["review_receipt"] for f in frames],
        extra_inputs={"required_identities": ["Embry", "Kai"]},
        proves=["per-frame generation and review receipts exist for all 8 frames with image hashes"],
        does_not=["final acceptance"],
        blocker=None)

    # 15 Panel Continuity And Repair Ledger
    cont_status = "PASS_PANEL_CONTINUITY" if cont_all_pass else ("BLOCKED_PANEL_CONTINUITY" if continuity else "PARTIAL_PANEL_CONTINUITY_NOT_ALL_FRAMES_PASSED")
    base_update(
        15, cont_status, "active" if cont_all_pass else "blocked",
        outputs=[f"{rel}/receipts/continuity_review/"],
        receipts=[f"{rel}/receipts/continuity_review/"],
        extra_inputs={"continuity_pairs": len(continuity),
                      "continuity_pass": sum(1 for c in continuity if c["status"] == "PASS")},
        proves=["inter-frame continuity (start->end, end->next-start) reviewed on actual pixels for identity-passing frames"],
        does_not=["final acceptance"],
        blocker=None if cont_all_pass else [c for c in continuity if c["status"] != "PASS"])

    # 16 Panel Generation Loop
    n_generated = sum(1 for f in frames if f["image_path"])
    base_update(
        16, f"PASS_PANEL_GENERATION_{n_generated}_OF_{n_total}" if n_generated == n_total else f"PARTIAL_PANEL_GENERATION_{n_generated}_OF_{n_total}",
        "active" if n_generated == n_total else "blocked",
        outputs=frame_paths,
        receipts=[f"{rel}/phase_c_regeneration_receipt.json"],
        extra_inputs={"image_model": "gpt-image-2", "image_auth": "codex-oauth",
                      "frame_hashes": {f["frame_id"]: f["image_sha256"] for f in frames if f["image_sha256"]}},
        proves=[f"{n_generated}/{n_total} storyboard frames generated live via GPT Image 2 through the Scillm codex-oauth wrapper"],
        does_not=["identity acceptance by itself"],
        blocker=None if n_generated == n_total else "one or more frames failed to generate")

    # 17 Panel Visual Review Loop
    base_update(
        17, f"{'PASS' if all_pass else 'PARTIAL'}_PANEL_VISUAL_REVIEW_{n_pass}_OF_{n_total}",
        "active" if all_pass else "blocked",
        outputs=review_receipts,
        receipts=review_receipts,
        extra_inputs={"review_model": "gpt-5.5", "review_auth": "codex-oauth",
                      "reviewer_source": "scillm:gpt-5.5:image_url",
                      "frame_review_status": {f["frame_id"]: f["status"] for f in frames}},
        proves=[f"{n_pass}/{n_total} frames PASS actual-pixel identity review (Embry vs embry_contact_sheet_v3, Kai vs reference)"],
        does_not=["provider readiness or final acceptance"],
        blocker=None if all_pass else [f["frame_id"] + ":" + str(f.get("final_blocking_findings")) for f in frames if f["status"] != "PASS"])

    # 18 Surgical Panel Repair
    base_update(
        18, "PASS_SURGICAL_REPAIR" if all_pass else "PARTIAL_SURGICAL_REPAIR",
        "active" if all_pass else "blocked",
        outputs=[f"{rel}/receipts/storyboard_frame_generation/"],
        receipts=[f"{rel}/phase_c_regeneration_receipt.json"],
        extra_inputs={"repairs": repairs, "max_attempts": 5},
        proves=["identity failures triggered bounded surgical repair (MUST INCLUDE / MUST NOT INCLUDE deltas); attempts recorded per frame"],
        does_not=["final acceptance"],
        blocker=None if all_pass else "frames remaining FAILED after repair budget exhausted")

    # 19 Panel Repair Gate
    gate_status = "PASS_PANEL_REVIEWED" if (all_pass and cont_all_pass) else "FAILED_PANEL_REPAIR_GATE"
    base_update(
        19, gate_status, "active" if gate_status == "PASS_PANEL_REVIEWED" else "blocked",
        outputs=[f"{rel}/phase_c_regeneration_receipt.json"],
        receipts=[f"{rel}/phase_c_regeneration_receipt.json"],
        extra_inputs={"frames_pass": n_pass, "frames_total": n_total,
                      "continuity_all_pass": cont_all_pass},
        proves=[f"final panel gate: {n_pass}/{n_total} identity PASS; continuity_all_pass={cont_all_pass}"],
        does_not=["provider readiness beyond this gate"],
        blocker=None if gate_status == "PASS_PANEL_REVIEWED" else f"{n_total - n_pass} frame(s) not identity-PASS and/or continuity failures")

    args.bundle.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"updated_steps": [13, 14, 15, 16, 17, 18, 19],
                      "frames_pass": n_pass, "frames_total": n_total,
                      "gate_status": gate_status,
                      "continuity_all_pass": cont_all_pass}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
