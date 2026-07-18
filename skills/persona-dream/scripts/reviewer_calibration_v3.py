#!/usr/bin/env python3
"""Reviewer calibration v3 — negative control through the face-crop-augmented reviewer.

Re-runs the exact 6-case negative-control suite from
``reviewer_negative_control_probe.py`` (3 known-bad, 2 positive controls, 1
tamper) through ``phase07_storyboard_tau_node._run_identity_continuity_review``,
which now enforces the mandatory face-crop identity subgate on top of the
hardened full-frame review. This runner REUSES the probe's calibration-set
construction, per-case verdict logic, and aggregation — it does not fork them —
and additionally records, per case, which gate fired (full_frame vs
face_crop_subgate) so the v2 -> v3 movement is auditable.

PASS bar (unchanged from the probe): every known-bad and the tamper case FAIL
with a concrete blocking finding AND both positive controls PASS.

Live gpt-5.5 vision calls are authorized. NO image generation, NO paid provider
calls. Frozen revision frames are read-only calibration inputs; the reviewer is
NOT weakened to make calibration pass (the subgate only adds strictness).
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
NODE_PATH = SCRIPTS / "phase07_storyboard_tau_node.py"
PHASE_C_PATH = SCRIPTS / "phase_c_regenerate_storyboard_frames.py"
PROBE_PATH = SCRIPTS / "reviewer_negative_control_probe.py"

REVISION_ID = "rev_successor_943b01ecd9a3"
RUN_ID = "pipeline-complete"
REVISION_ROOT = SKILL_ROOT / "reports" / "pipeline-complete" / ".persona-dream" / "revisions" / REVISION_ID
V2_RECEIPT = REVISION_ROOT / "reviewer_calibration_receipt.v2.json"
DEFAULT_OUT = REVISION_ROOT / "reviewer_calibration_receipt.v3.json"
DEFAULT_RECEIPTS = REVISION_ROOT / "reviewer_calibration_v3" / "case_receipts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _v2_verdicts() -> dict[str, str]:
    if not V2_RECEIPT.exists():
        return {}
    data = json.loads(V2_RECEIPT.read_text(encoding="utf-8"))
    return {c["case_id"]: c.get("reviewer_status") for c in data.get("cases", [])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--receipts-root", type=Path, default=DEFAULT_RECEIPTS)
    args = ap.parse_args()

    node = _load("phase07_storyboard_tau_node", NODE_PATH)
    phase_c = _load("phase_c_regenerate_storyboard_frames", PHASE_C_PATH)
    probe = _load("reviewer_negative_control_probe", PROBE_PATH)

    packet = json.loads(probe.PACKET_PATH.read_text(encoding="utf-8"))
    ledger = json.loads(probe.LEDGER_PATH.read_text(encoding="utf-8"))
    v2 = _v2_verdicts()

    cases = probe.build_calibration_set(packet, phase_c)
    results: list[dict[str, Any]] = []
    for case in cases:
        panel = probe._panel_for(packet, case["panel_id"], phase_c, references=case["references"])
        result = probe._run_case(
            case_id=case["case_id"], kind=case["kind"], expectation=case["expectation"],
            image_path=case["image_path"], panel=panel, node=node, phase_c=phase_c,
            receipts_root=args.receipts_root,
        )
        # Pull the augmented-reviewer detail from the written case receipt.
        gate_detail = {}
        rc_path = result.get("review_receipt_path")
        if rc_path and Path(rc_path).exists():
            rc = json.loads(Path(rc_path).read_text(encoding="utf-8"))
            subgate = rc.get("face_crop_subgate") or {}
            gate_detail = {
                "full_frame_status": rc.get("full_frame_status"),
                "face_crop_subgate_status": subgate.get("status"),
                "gate_fired": rc.get("gate_fired"),
                "subgate_blocking_findings": subgate.get("blocking_findings") or [],
                "subgate_entity_results": [
                    {k: er.get(k) for k in ("entity", "status", "verdict", "confidence", "reason", "divergences")}
                    for er in (subgate.get("entity_results") or [])
                ],
            }
        result.update(gate_detail)
        result["v2_reviewer_status"] = v2.get(case["case_id"])
        results.append(result)
        print(f"[{result['case_id']}] v2={result.get('v2_reviewer_status')} -> v3={result['reviewer_status']} "
              f"(full_frame={result.get('full_frame_status')} subgate={result.get('face_crop_subgate_status')} "
              f"fired={result.get('gate_fired')}) satisfied={result['satisfied']}"
              + ("  <<< CRITICAL: KNOWN-BAD PASSED" if result["critical_known_bad_passed"] else ""))

    agg = probe.aggregate(results)
    known_bad = [r for r in results if r["kind"] == "known_bad"]
    positive = [r for r in results if r["kind"] == "positive_control"]
    tamper = [r for r in results if r["kind"] == "tamper"]

    receipt = {
        "schema": "persona_dream.reviewer_calibration_receipt.v3",
        "created_at": _now(),
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "overall_status": agg["overall_status"],
        "calibration_pass": agg["calibration_pass"],
        "reviewer": {
            "function": "phase07_storyboard_tau_node._run_identity_continuity_review",
            "augmentation": "hardened full-frame review AND mandatory face-crop identity subgate "
                            "(identity_face_crop_subgate.run_face_crop_subgate)",
            "subgate_failure_code": "FAIL_FACE_CROP_IDENTITY_MISMATCH",
            "source_of_truth": "reused, not forked; same node function phase_c uses",
            "model": phase_c.IDENTITY_REVIEW_POLICY.get("model"),
            "review_schema": "persona_dream.identity_continuity_review.v1",
            "subgate_schema": "persona_dream.identity_face_crop_subgate.v1",
            "image_path_mode": "base64 image_url (actual pixels), full-frame + zoomed face crops",
            "identity_review_policy": dict(phase_c.IDENTITY_REVIEW_POLICY),
        },
        "identity_references": {
            "embry_accepted_source": {
                "asset_id": "embry_contact_sheet_v3",
                "path": str(phase_c.EMBRY_SHEET),
                "sha256": phase_c._sha256_file(phase_c.EMBRY_SHEET) if phase_c.EMBRY_SHEET.exists() else None,
            },
            "kai_reference": {
                "path": str(phase_c.KAI_SHEET),
                "sha256": phase_c._sha256_file(phase_c.KAI_SHEET) if phase_c.KAI_SHEET.exists() else None,
            },
        },
        "ground_truth": {
            "known_bad_source": "stale montage-derived Phase 07 frames",
            "rejected_identity_source": ledger.get("rejected_identity_source"),
            "invalidation_ledger": str(probe.LEDGER_PATH.relative_to(SKILL_ROOT)),
            "stale_disposition": "STALE_IDENTITY_SOURCE_SUPERSEDED",
        },
        "summary": {
            "cases_total": len(results),
            "known_bad_total": len(known_bad),
            "known_bad_failed_as_required": sum(1 for r in known_bad if r["satisfied"]),
            "positive_total": len(positive),
            "positive_passed_as_required": sum(1 for r in positive if r["satisfied"]),
            "tamper_total": len(tamper),
            "tamper_failed_as_required": sum(1 for r in tamper if r["satisfied"]),
            "critical_known_bad_passed": agg["critical_known_bad_passed"],
        },
        "v2_to_v3_movement": [
            {
                "case_id": r["case_id"],
                "kind": r["kind"],
                "expectation": r["expectation"],
                "v2_status": r.get("v2_reviewer_status"),
                "v3_status": r["reviewer_status"],
                "full_frame_status": r.get("full_frame_status"),
                "face_crop_subgate_status": r.get("face_crop_subgate_status"),
                "gate_fired": r.get("gate_fired"),
                "satisfied": r["satisfied"],
            }
            for r in results
        ],
        "failure_reasons": agg["failure_reasons"],
        "cases": results,
        "claims": {
            "proves": (
                [
                    "the face-crop-augmented Phase 07 identity reviewer FAILS every known-bad "
                    "montage-derived frame (including the residual sb_001) with a concrete blocking "
                    "finding while still PASSing accepted successor frames",
                    "the review contract remains reference-grounded: the tamper case (wrong Embry "
                    "reference) FAILs",
                    "the face-crop subgate closed the full-frame dilution blind spot that left "
                    "known_bad_sb_001 passing under v2",
                ]
                if agg["calibration_pass"]
                else [
                    "the face-crop-augmented reviewer was executed live against known-bad ground "
                    "truth; calibration did not fully pass (see failure_reasons and v2_to_v3_movement)",
                ]
            ),
            "does_not_prove": [
                "any provider readiness, publication, payment, or Kling submission",
                "identity correctness of any frame beyond the reviewer's own verdict",
                "that the accepted Phase C frames are provider-grade for post-provider continuity",
            ],
        },
        "mocked": False,
        "live": True,
        "provider_live": False,
        "paid_call_authorized": False,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "overall_status": agg["overall_status"],
        "known_bad_failed_as_required": receipt["summary"]["known_bad_failed_as_required"],
        "known_bad_total": len(known_bad),
        "positive_passed_as_required": receipt["summary"]["positive_passed_as_required"],
        "tamper_failed_as_required": receipt["summary"]["tamper_failed_as_required"],
        "critical_known_bad_passed": agg["critical_known_bad_passed"],
        "receipt_path": str(args.out),
    }, indent=2))
    return 0 if agg["calibration_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
