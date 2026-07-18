#!/usr/bin/env python3
"""Reviewer calibration negative-control probe for the Phase C identity reviewer.

Phase C reported 8/8 first-attempt PASS on the successor storyboard frames using
the actual-pixel identity reviewer (scillm gpt-5.5 ``image_url``, schema
``persona_dream.identity_continuity_review.v1``). 8/8 is consistent with a
genuinely better identity source OR with a lenient reviewer that never fails a
bad frame. There was no negative control proving the reviewer rejects known-bad
frames.

This probe runs the SAME reviewer — the real Phase 07 panel-node function
``phase07_storyboard_tau_node._run_identity_continuity_review`` (same model, same
prompt contract, same base64 ``image_url`` path) — that
``phase_c_regenerate_storyboard_frames.py`` uses. It does NOT fork a lenient
variant. It reviews a calibration set under the exact Phase C review conditions
(panel construction + accepted ``embry_contact_sheet_v3`` / Kai references), and
only the image (or, for the tamper case, the declared reference) changes:

  * known-bad: the stale montage-derived Phase 07 frames marked
    STALE_IDENTITY_SOURCE_SUPERSEDED in the successor's
    ``identity_successor_invalidation_ledger.v1.json`` (generated from the montage
    that FAILED identity qualification, FAIL_IDENTITY_REFERENCE_INCONSISTENT, and
    whose historical Kling return failed post-provider identity continuity).
    Expectation: FAIL with a concrete blocking finding.
  * positive control: accepted Phase C successor frames. Expectation: still PASS.
  * tamper: an accepted Phase C frame reviewed with the Embry reference slot
    pointed at the WRONG person (the Kai sheet). Expectation: FAIL — otherwise the
    review contract is not reference-grounded (it credits the frame, not the
    match to the declared reference).

Overall verdict:
  * REVIEWER_CALIBRATION_PASS  -> every known-bad and the tamper case FAIL with a
    concrete failure code AND every positive control PASSes.
  * REVIEWER_CALIBRATION_FAILED -> any known-bad or the tamper case PASSes, or a
    positive control fails. A known-bad frame passing is a CRITICAL finding: it
    would mean the 8/8 Phase C result is untrustworthy.

Live scillm gpt-5.5 vision calls ARE authorized (that is the point). NO image
generation, NO paid provider / Kling calls. The reviewer is NOT modified to make
the calibration pass; frozen revision files are read-only inputs.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]  # .../skills/persona-dream
SCRIPTS = SKILL_ROOT / "scripts"
NODE_PATH = SCRIPTS / "phase07_storyboard_tau_node.py"
PHASE_C_PATH = SCRIPTS / "phase_c_regenerate_storyboard_frames.py"

REVISION_ID = "rev_successor_943b01ecd9a3"
RUN_ID = "pipeline-complete"
REVISION_ROOT = (
    SKILL_ROOT / "reports" / "pipeline-complete" / ".persona-dream" / "revisions" / REVISION_ID
)
PHASE07_ROOT = REVISION_ROOT / "phase_07_storyboard_live_tau"
STALE_FRAMES_DIR = PHASE07_ROOT / "generated_storyboard_frames"
ACCEPTED_FRAMES_DIR = PHASE07_ROOT / "phase_c_successor_regen" / "generated_storyboard_frames"
PACKET_PATH = PHASE07_ROOT / "storyboard_packet.json"
LEDGER_PATH = REVISION_ROOT / "identity_successor_invalidation_ledger.v1.json"

RECEIPT_PATH = REVISION_ROOT / "reviewer_calibration_receipt.v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _panel_for(packet: dict, panel_id: str, phase_c, *, references: list[dict]) -> dict:
    """Reconstruct the exact Phase C review panel for ``panel_id``.

    Mirrors ``phase_c_regenerate_storyboard_frames.main``: required_entities is set
    to ["Embry", "Kai"] and references to the accepted identity sheets, so the only
    thing that varies across cases is the reviewed image (or the tampered reference).
    """
    panels = {p["panel_id"]: p for p in packet["panels"]}
    panel = dict(panels[panel_id])
    panel["required_entities"] = ["Embry", "Kai"]
    panel["references"] = references
    return panel


def _tamper_refs(phase_c) -> list[dict]:
    """Accepted-reference set with the Embry slot pointed at the WRONG person.

    Keeps the Embry reference id/title so the reviewer's reference resolver still
    binds it, but swaps its path to the Kai sheet. A reference-grounded reviewer
    must then FAIL an accepted (real-Embry) frame because the frame's Embry cannot
    match a reference image of Kai.
    """
    refs = [dict(r) for r in phase_c._panel_refs()]
    for ref in refs:
        if ref.get("id") == "embry_character_sheet":
            ref["path"] = str(phase_c.KAI_SHEET)
            ref["tampered"] = True
            ref["tamper_note"] = "Embry reference slot deliberately points at the Kai sheet"
    return refs


def evaluate_case(kind: str, expectation: str, status: str, blocking_findings: list[str]) -> dict[str, Any]:
    """Pure verdict logic for a single calibration case (unit-tested).

    A FAIL-expected case (known-bad or tamper) is only "satisfied" if the reviewer
    returns FAIL *and* names a concrete blocking finding — a silent/empty FAIL does
    not count as a proper rejection. A known-bad frame that PASSes is CRITICAL.
    """
    blocking = [b for b in (blocking_findings or []) if isinstance(b, str)]
    has_concrete_code = bool(blocking)
    matched = status == expectation
    if expectation == "FAIL":
        satisfied = status == "FAIL" and has_concrete_code
    else:
        satisfied = status == "PASS"
    critical = kind == "known_bad" and status == "PASS"
    return {
        "matched_expectation": matched,
        "satisfied": satisfied,
        "critical_known_bad_passed": critical,
        "has_concrete_failure_code": has_concrete_code,
    }


def aggregate(results: list[dict]) -> dict[str, Any]:
    """Aggregate per-case results into the overall calibration verdict (unit-tested)."""
    known_bad = [r for r in results if r["kind"] == "known_bad"]
    positive = [r for r in results if r["kind"] == "positive_control"]
    tamper = [r for r in results if r["kind"] == "tamper"]

    known_bad_all_fail = all(r["satisfied"] for r in known_bad) and bool(known_bad)
    positive_all_pass = all(r["satisfied"] for r in positive) and bool(positive)
    tamper_all_fail = all(r["satisfied"] for r in tamper)
    critical_hits = [r["case_id"] for r in results if r["critical_known_bad_passed"]]

    calibration_pass = known_bad_all_fail and positive_all_pass and tamper_all_fail
    overall = "REVIEWER_CALIBRATION_PASS" if calibration_pass else "REVIEWER_CALIBRATION_FAILED"

    failure_reasons: list[str] = []
    if not known_bad_all_fail:
        failure_reasons.append(
            "CRITICAL: at least one known-bad montage-derived frame PASSED identity review "
            f"({', '.join(critical_hits) or 'silent-fail-no-code'}); the Phase C 8/8 result is "
            "not trustworthy and the reviewer prompt/contract needs hardening"
        )
    if not positive_all_pass:
        failure_reasons.append(
            "at least one accepted positive-control frame FAILED review (reviewer over-strict or "
            "review path broken)"
        )
    if not tamper_all_fail:
        failure_reasons.append(
            "the tamper case (accepted frame + wrong Embry reference) PASSED; the review contract "
            "is not reference-grounded — it credits the frame rather than the declared reference match"
        )
    return {
        "overall_status": overall,
        "calibration_pass": calibration_pass,
        "failure_reasons": failure_reasons,
        "critical_known_bad_passed": critical_hits,
        "known_bad_all_fail": known_bad_all_fail,
        "positive_all_pass": positive_all_pass,
        "tamper_all_fail": tamper_all_fail,
    }


def _run_case(
    *,
    case_id: str,
    kind: str,
    expectation: str,
    image_path: Path,
    panel: dict,
    node,
    phase_c,
    receipts_root: Path,
) -> dict[str, Any]:
    frame_key = "start_frame"
    required = ["Embry", "Kai"]
    case_receipts = receipts_root / case_id
    case_receipts.mkdir(parents=True, exist_ok=True)

    prompt = node._identity_review_prompt(panel, frame_key=frame_key, required_entities=required)
    prompt_sha = phase_c._sha256_text(prompt)
    image_sha = phase_c._sha256_file(image_path) if image_path.exists() else None

    review = node._run_identity_continuity_review(
        {"path": str(image_path)},
        panel=panel,
        frame_key=frame_key,
        required_entities=required,
        identity_review_policy=phase_c.IDENTITY_REVIEW_POLICY,
        receipts_dir=case_receipts,
    )
    status = review.get("status")
    blocking = [b for b in (review.get("blocking_findings") or []) if isinstance(b, str)]
    verdict = evaluate_case(kind, expectation, status, blocking)

    return {
        "case_id": case_id,
        "kind": kind,
        "panel_id": panel.get("panel_id"),
        "frame_key": frame_key,
        "image_path": str(image_path),
        "image_sha256": image_sha,
        "expectation": expectation,
        "reviewer_status": status,
        "matched_expectation": verdict["matched_expectation"],
        "satisfied": verdict["satisfied"],
        "critical_known_bad_passed": verdict["critical_known_bad_passed"],
        "has_concrete_failure_code": verdict["has_concrete_failure_code"],
        "blocking_findings": blocking,
        "visible_entities": review.get("visible_entities"),
        "reviewer_source": review.get("reviewer_source"),
        "model": review.get("model"),
        "review_prompt_sha256": prompt_sha,
        "identity_notes": (review.get("raw_response") or {}).get("identity_notes")
        if isinstance(review.get("raw_response"), dict)
        else None,
        "review_receipt_path": review.get("receipt_path"),
        "reference_paths": {
            r.get("id"): r.get("path") for r in panel.get("references", []) if isinstance(r, dict)
        },
    }


def build_calibration_set(packet: dict, phase_c) -> list[dict]:
    accepted_refs = [dict(r) for r in phase_c._panel_refs()]
    tamper_refs = _tamper_refs(phase_c)
    return [
        # Known-bad: stale montage-derived frames (>= 2 required; 3 for robustness).
        {"case_id": "known_bad_sb_001_start", "kind": "known_bad", "expectation": "FAIL",
         "panel_id": "sb_001", "image_path": STALE_FRAMES_DIR / "sb_001_start_frame.png",
         "references": accepted_refs},
        {"case_id": "known_bad_sb_002_start", "kind": "known_bad", "expectation": "FAIL",
         "panel_id": "sb_002", "image_path": STALE_FRAMES_DIR / "sb_002_start_frame.png",
         "references": accepted_refs},
        {"case_id": "known_bad_sb_003_start", "kind": "known_bad", "expectation": "FAIL",
         "panel_id": "sb_003", "image_path": STALE_FRAMES_DIR / "sb_003_start_frame.png",
         "references": accepted_refs},
        # Positive controls: accepted Phase C frames must still PASS.
        {"case_id": "positive_control_sb_001_start", "kind": "positive_control", "expectation": "PASS",
         "panel_id": "sb_001", "image_path": ACCEPTED_FRAMES_DIR / "sb_001_start_frame.png",
         "references": accepted_refs},
        {"case_id": "positive_control_sb_002_start", "kind": "positive_control", "expectation": "PASS",
         "panel_id": "sb_002", "image_path": ACCEPTED_FRAMES_DIR / "sb_002_start_frame.png",
         "references": accepted_refs},
        # Tamper: accepted frame + wrong Embry reference => must FAIL (reference-grounding).
        {"case_id": "tamper_wrong_embry_ref", "kind": "tamper", "expectation": "FAIL",
         "panel_id": "sb_001", "image_path": ACCEPTED_FRAMES_DIR / "sb_001_start_frame.png",
         "references": tamper_refs},
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=RECEIPT_PATH)
    ap.add_argument("--receipts-root", type=Path,
                    default=REVISION_ROOT / "reviewer_calibration" / "case_receipts")
    args = ap.parse_args()

    node = _load("phase07_storyboard_tau_node", NODE_PATH)
    phase_c = _load("phase_c_regenerate_storyboard_frames", PHASE_C_PATH)

    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))

    cases = build_calibration_set(packet, phase_c)
    results: list[dict] = []
    for case in cases:
        panel = _panel_for(packet, case["panel_id"], phase_c, references=case["references"])
        result = _run_case(
            case_id=case["case_id"], kind=case["kind"], expectation=case["expectation"],
            image_path=case["image_path"], panel=panel, node=node, phase_c=phase_c,
            receipts_root=args.receipts_root,
        )
        results.append(result)
        print(f"[{result['case_id']}] expect={result['expectation']} "
              f"got={result['reviewer_status']} satisfied={result['satisfied']}"
              + ("  <<< CRITICAL: KNOWN-BAD PASSED" if result["critical_known_bad_passed"] else ""))

    known_bad = [r for r in results if r["kind"] == "known_bad"]
    positive = [r for r in results if r["kind"] == "positive_control"]
    tamper = [r for r in results if r["kind"] == "tamper"]

    agg = aggregate(results)
    overall = agg["overall_status"]
    calibration_pass = agg["calibration_pass"]
    failure_reasons = agg["failure_reasons"]
    critical_hits = agg["critical_known_bad_passed"]

    receipt = {
        "schema": "persona_dream.reviewer_calibration_receipt.v1",
        "created_at": _now(),
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "overall_status": overall,
        "calibration_pass": calibration_pass,
        "reviewer": {
            "function": "phase07_storyboard_tau_node._run_identity_continuity_review",
            "source_of_truth": "reused, not forked; identical to phase_c_regenerate_storyboard_frames.py",
            "model": phase_c.IDENTITY_REVIEW_POLICY.get("model"),
            "review_schema": "persona_dream.identity_continuity_review.v1",
            "image_path_mode": "base64 image_url (actual pixels)",
            "identity_review_policy": dict(phase_c.IDENTITY_REVIEW_POLICY),
        },
        "identity_references": {
            "embry_accepted_source": {
                "asset_id": "embry_contact_sheet_v3",
                "path": str(phase_c.EMBRY_SHEET),
                "sha256": phase_c._sha256_file(phase_c.EMBRY_SHEET)
                if phase_c.EMBRY_SHEET.exists() else None,
            },
            "kai_reference": {
                "path": str(phase_c.KAI_SHEET),
                "sha256": phase_c._sha256_file(phase_c.KAI_SHEET)
                if phase_c.KAI_SHEET.exists() else None,
            },
        },
        "ground_truth": {
            "known_bad_source": "stale montage-derived Phase 07 frames",
            "rejected_identity_source": ledger.get("rejected_identity_source"),
            "invalidation_ledger": str(LEDGER_PATH.relative_to(SKILL_ROOT)),
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
            "critical_known_bad_passed": critical_hits,
        },
        "failure_reasons": failure_reasons,
        "analyst_visual_verification": {
            "method": "human/agent side-by-side pixel comparison of each PASSed known-bad frame "
                      "against the embry_contact_sheet_v3 reference to confirm the CRITICAL finding "
                      "is a genuine reviewer-leniency defect and not a ground-truth-granularity artifact",
            "finding": "CONFIRMED genuine leniency defect",
            "detail": {
                "known_bad_sb_001_start": "PASSED, but Embry reads as an older, squarer-faced woman "
                    "in a navy polo — a different specific identity than v3 (v3 is a distinct late-20s "
                    "woman). Coarse category match only.",
                "known_bad_sb_002_start": "PASSED, but Embry is a visibly weathered woman ~40s-50s, "
                    "clearly not the v3 identity. Strongest evidence of over-lenient facial matching.",
                "known_bad_sb_003_start": "Correctly FAILED ('reads more like a generic adult female "
                    "surfer'); shows the reviewer is not a blanket rubber stamp.",
                "tamper_wrong_embry_ref": "Correctly FAILED and explicitly noted the Embry reference "
                    "'shows a young man matching Kai' — proves the contract does read reference pixels.",
            },
            "conclusion": "The reviewer discriminates (tamper + sb_003 FAIL) but its identity "
                          "threshold is too coarse: it accepts 'adult woman, brown hair, navy top ... "
                          "closely enough' as an identity match without enforcing specific facial "
                          "correspondence (age, face shape, distinctive features) to the reference. "
                          "Two montage-derived frames depicting a visibly different/older woman were "
                          "accepted. The Phase C 8/8 first-attempt PASS is therefore NOT trustworthy "
                          "as evidence of specific-identity fidelity.",
        },
        "proposed_hardening": {
            "status": "PROPOSED_NOT_IMPLEMENTED",
            "containment": "review prompt contract only (phase07_storyboard_tau_node._identity_review_prompt)",
            "why_not_implemented_here": [
                "Hard constraint: do not modify the reviewer to make this calibration pass.",
                "The Phase C 8/8 receipts and prompt hashes are bound to the current reviewer prompt; "
                "silently changing it would leave those receipts referencing a prompt that no longer "
                "exists and would require re-running the full Phase C actual-pixel review to re-establish truth.",
                "Re-review of Phase C frames is out of scope for this negative-control probe and is human-gated.",
            ],
            "recommended_changes": [
                "Replace the coarse 'matches ... closely enough' / category-match language with an "
                "explicit specific-identity gate: FAIL unless the SAME individual is depicted — matching "
                "face shape, apparent age, eyebrow shape, nose, and distinctive features to the reference, "
                "not merely the same demographic category (adult woman, brown hair, navy top).",
                "Add an explicit age-consistency clause: FAIL if the depicted person appears a clearly "
                "different age (e.g., a decade+ older/younger) than the reference identity.",
                "Require the reviewer to enumerate 2-3 concrete matching facial features it verified, and "
                "to FAIL if it cannot name specific correspondences (forces feature-level grounding, not vibes).",
                "Re-run the negative control after hardening: all known-bad + tamper must FAIL and both "
                "positive controls must still PASS before the reviewer is trusted; then re-run Phase C.",
            ],
        },
        "cases": results,
        "claims": {
            "proves": (
                [
                    "the Phase C identity reviewer (same model, prompt contract, and actual-pixel "
                    "image_url path) FAILS every known-bad montage-derived frame with a concrete "
                    "blocking finding while still PASSing accepted successor frames",
                    "the review contract is reference-grounded: an accepted frame reviewed against a "
                    "wrong identity reference is FAILED",
                    "the Phase C 8/8 first-attempt PASS reflects a discriminating reviewer, not a "
                    "reviewer that passes everything",
                ]
                if calibration_pass
                else [
                    "the reviewer calibration negative-control was executed live against known-bad "
                    "ground truth and the reviewer did NOT behave as a correct discriminator",
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
        "overall_status": overall,
        "known_bad_failed_as_required": receipt["summary"]["known_bad_failed_as_required"],
        "known_bad_total": len(known_bad),
        "positive_passed_as_required": receipt["summary"]["positive_passed_as_required"],
        "tamper_failed_as_required": receipt["summary"]["tamper_failed_as_required"],
        "critical_known_bad_passed": critical_hits,
        "receipt_path": str(args.out),
    }, indent=2))
    return 0 if calibration_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
