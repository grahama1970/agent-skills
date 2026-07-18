#!/usr/bin/env python3
"""LANE C (step 38 fix): regenerate ONLY sb_003_end_frame with the composition
delta from step38_sb_003_composition_delta_proposal.v1.json so Kai's mouth is NOT
camera-readable during the dialogue window (5.0-7.7s), while keeping Kai
identity-recognizable and Embry fully readable. sb_003_start remains the identity
anchor and is NOT regenerated.

Generation lane = the same Phase C GPT Image 2 lane (codex-oauth via scillm
generate-image, embry_contact_sheet_v3 + Kai character sheet as reference inputs).
The prompt is composed from the existing sb_003.end_frame panel contract PLUS the
composition delta.

Acceptance per attempt requires ALL of:
  (a) augmented identity review PASS (full-frame VLM + deterministic ArcFace
      embedding subgate for BOTH visible characters; embedding cosines recorded)
      -- run through the real Phase 07 node reviewer, unchanged and unweakened.
  (b) composition check PASS: a VLM check answering the specific question whether
      Kai's mouth is camera-readable, applying the delta's own criteria. PASS iff
      kai_mouth_camera_readable == false AND kai_identity_recognizable == true AND
      embry_face_readable == true.
  (c) continuity re-review PASS for the affected pairs:
      sb_003_start -> sb_003_end(new)  and  sb_003_end(new) -> sb_004_start,
      via the existing Phase C continuity lane.

Fail closed: bounded loop, max 5 attempts. If 5 attempts exhaust without a single
attempt passing a AND b AND c, the frame is left FAILED with a blocker receipt and
NO requalification is attempted. No paid provider / Kling call is made.
"""
from __future__ import annotations

import argparse
import hashlib
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
PHASE07 = REV_ROOT / "phase_07_storyboard_live_tau"
SUCCESSOR_FRAMES = PHASE07 / "phase_c_successor_regen" / "generated_storyboard_frames"
DELTA_PATH = REV_ROOT / "step38_sb_003_composition_delta_proposal.v1.json"
CONTRACT_PATH = (
    PHASE07 / "tau_loop_preflight_proof" / "spine_chain" / "phase07"
    / "prompt_contracts" / "sb_003.end_frame.attempt_001.json"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Delta-composed prompt
# --------------------------------------------------------------------------- #
def _lane_c_delta_block(delta: dict) -> str:
    d = delta["sb_003_end_frame_delta"]
    subject_after = d["prompt_sections.SUBJECT"]["after"]
    chars_add = d["prompt_sections.CHARACTERS_addendum"]
    camera_add = delta["sb_003_end_frame_delta"]["camera_contract_addendum"]
    lines = [
        "",
        "=== STEP 38 LANE C COMPOSITION DELTA (authoritative for THIS end frame) ===",
        "This is the sb_003 END frame at the close of Kai's spoken cue "
        "(dialogue window 5.0-7.7s). Apply the following composition delta EXACTLY:",
        f"SUBJECT: {subject_after}",
        f"CHARACTERS: {chars_add}",
        f"CAMERA: {camera_add}",
        "",
        "HARD COMPOSITION RULES FOR THIS FRAME (READ CAREFULLY -- these two goals must",
        "BOTH hold at once; the target is a MODERATE THREE-QUARTER turn, NOT an occlusion",
        "and NOT a profile):",
        "  - KAI IS IN A MODERATE THREE-QUARTER VIEW, ~45-60 DEGREES turned toward the",
        "    lineup/reef he is reading. At this angle ONE full eye, the eyebrow, the nose,",
        "    the near cheekbone, and the near jawline are ALL clearly visible to camera and",
        "    sharply match the attached Kai reference (dark curly wet hair, tan skin,",
        "    athletic build, black rashguard). His whole face is lit and visible -- this is",
        "    the identity anchor for the frame. A reviewer MUST be able to name matching eye,",
        "    brow, nose, cheek and jaw features.",
        "  - HIS MOUTH IS NOT CAMERA-READABLE because of that turn: at ~45-60 degrees his",
        "    lips are foreshortened and angled away from the lens, so their exact shape and",
        "    any lip movement CANNOT be read. Do NOT show a clean frontal mouth. Do NOT let a",
        "    viewer lip-read him.",
        "  - DO NOT COVER HIS FACE WITH HIS ARM, HAND, HAIR, OR SPRAY. The face must stay",
        "    fully visible; only the camera ANGLE (the three-quarter turn), not occlusion,",
        "    makes the mouth unreadable. Do NOT turn him past a three-quarter (no side-",
        "    profile, no back-facing, no tiny distant figure).",
        "  - EMBRY STAYS FULLY READABLE, near-frontal. Embry is nearer the decision point,",
        "    foreground, face clearly toward the camera/decision and strongly matching her",
        "    reference; her mouth may be visible (she is not speaking in this window).",
        "  - Only Kai's lip camera-readability is removed (by the turn); everything else",
        "    (wardrobe, reef boundary, lineup geometry, lighting) is continuous with the",
        "    sb_003 start frame.",
        "=== END STEP 38 LANE C COMPOSITION DELTA ===",
    ]
    return "\n".join(lines)


def _compose_prompt(phase_c, panel: dict, delta: dict) -> str:
    base = phase_c._base_prompt(panel, "end_frame")
    return base + "\n" + _lane_c_delta_block(delta)


def _repair_addendum(attempt: int, failures: list[str]) -> str:
    lines = [
        "",
        f"SURGICAL REPAIR DELTA (attempt {attempt}) -- the previous render FAILED one or",
        "more Lane C acceptance checks. Fix ALL of the following without breaking the others:",
    ]
    lines += [f"  - {f}" for f in failures]
    blob = " ".join(failures).lower()
    id_failed = any(k in blob for k in ("identity", "features_not_grounded", "verify", "occlud", "hidden", "obscur", "back-facing", "back facing", "profile", "arm"))
    mouth_readable = "mouth" in blob and ("readable" in blob or "readable=true" in blob or "lip-read" in blob)
    lines.append("TARGETED CORRECTION:")
    if id_failed and not mouth_readable:
        lines += [
            "  Kai's identity could not be verified -- his face was occluded or turned too far.",
            "  Do NOT cover his face with arm/hand/hair/spray and do NOT go to profile/back-facing.",
            "  Put him in a clean MODERATE three-quarter (~45-55 degrees): show his full near-side",
            "  face -- eye, brow, nose, cheekbone, jawline -- clearly lit and matching the reference,",
            "  so 2-3 facial features are groundable. The mouth becomes unreadable purely from the",
            "  turn angle (lips foreshortened away), NOT from any covering.",
        ]
    elif mouth_readable and not id_failed:
        lines += [
            "  Kai's mouth was still camera-readable. Turn his head a little FURTHER toward the",
            "  lineup (toward ~55-60 degrees) so the lips foreshorten away and cannot be read --",
            "  but keep his near eye, brow, nose, cheek and jaw visible and reference-matching. Do",
            "  NOT cover the face and do NOT go past a three-quarter into profile.",
        ]
    else:
        lines += [
            "  Hit the narrow target: a MODERATE three-quarter turn (~50 degrees) where Kai's near-",
            "  side face (eye, brow, nose, cheek, jaw) is fully visible and reference-matching AND",
            "  his lips are foreshortened away so they are not camera-readable. No arm/hair/spray",
            "  occlusion; no profile/back-facing; no clean frontal mouth.",
        ]
    lines.append("Embry stays foreground, near-frontal, camera-readable, reference-matching (adult "
                 "woman, navy top). Preserve wardrobe/reef/lighting continuity with sb_003 start.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Composition check (Kai mouth not camera-readable) via gpt-5.5 vision
# --------------------------------------------------------------------------- #
COMPOSITION_PROMPT = """You are a strict storyboard COMPOSITION reviewer for a lip-sync-avoidance requirement.
You are given ONE generated storyboard end-frame (the sb_003 END frame, at the close of Kai's ~2.7s spoken cue, dialogue window 5.0-7.7s), plus the Embry and Kai identity reference sheets. Judge the actual pixels only.

The requirement for THIS frame (step 38 composition delta): Kai (the young tan man with dark curly wet hair, black rashguard) has just delivered a restrained spoken cue while looking OUT toward the lineup/reef, so his head is three-quarter turned away and his lips are NOT camera-readable (optionally a paddle stroke brings his forearm/spray across his lower face). Embry (adult woman, brown hair, navy top) stays camera-readable and is NOT required to hide her mouth.

Answer the SPECIFIC question: is KAI'S MOUTH camera-readable in this frame -- i.e., could a viewer clearly see his mouth/lip shape or lip-read him?

Return strict JSON with EXACTLY these keys:
{"kai_mouth_camera_readable": true|false,
 "kai_identity_recognizable": true|false,
 "embry_face_readable": true|false,
 "verdict": "PASS|FAIL",
 "reasons": ["..."]}

Set verdict = PASS if and ONLY if kai_mouth_camera_readable == false AND kai_identity_recognizable == true AND embry_face_readable == true. Otherwise verdict = FAIL. Judge pixels, not captions or metadata."""


def _composition_check(phase_c, frame: Path, out_path: Path) -> dict:
    content = [
        {"type": "text", "text": COMPOSITION_PROMPT},
        {"type": "text", "text": "sb_003 END frame under review:"},
        phase_c._image_part(frame, "end_frame"),
        {"type": "text", "text": "Embry reference:"},
        phase_c._image_part(phase_c.EMBRY_SHEET, "embry_ref"),
        {"type": "text", "text": "Kai reference:"},
        phase_c._image_part(phase_c.KAI_SHEET, "kai_ref"),
    ]
    payload = {
        "model": "gpt-5.5",
        "messages": [
            {"role": "system", "content": "You are a strict composition reviewer. Return JSON only. Judge pixels, not metadata."},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }
    status = "FAIL"
    parsed: Any = None
    reasons: list[str] = []
    try:
        raw = phase_c._post_scillm(payload)
        parsed = json.loads(raw["choices"][0]["message"]["content"])
        mouth = bool(parsed.get("kai_mouth_camera_readable"))
        kai_ok = bool(parsed.get("kai_identity_recognizable"))
        embry_ok = bool(parsed.get("embry_face_readable"))
        reasons = [str(x) for x in parsed.get("reasons", []) if isinstance(x, str)]
        if parsed.get("verdict") == "PASS" and (not mouth) and kai_ok and embry_ok:
            status = "PASS"
        else:
            if mouth:
                reasons.insert(0, "kai_mouth_camera_readable=true (mouth is readable; requirement violated)")
            if not kai_ok:
                reasons.insert(0, "kai_identity_recognizable=false (Kai not reference-verifiable)")
            if not embry_ok:
                reasons.insert(0, "embry_face_readable=false (Embry not readable)")
    except Exception as exc:  # noqa: BLE001 -- fail closed
        reasons = [f"composition check call failed: {exc}"]
    receipt = {
        "schema": "persona_dream.lane_c.composition_check.v1",
        "created_at": _now(),
        "question": "Is Kai's mouth camera-readable during the sb_003 dialogue window (5.0-7.7s)?",
        "criteria": {
            "pass_requires": "kai_mouth_camera_readable == false AND kai_identity_recognizable == true AND embry_face_readable == true",
            "source_delta": "step38_sb_003_composition_delta_proposal.v1.json",
        },
        "frame": str(frame),
        "frame_sha256": _sha256_file(frame) if frame.exists() else None,
        "reviewer_source": "scillm:gpt-5.5:image_url",
        "review_prompt_sha256": _sha256_text(COMPOSITION_PROMPT),
        "status": status,
        "blocking_findings": [] if status == "PASS" else reasons,
        "raw_response": parsed,
        "mocked": False,
        "live": True,
    }
    _write_json(out_path, receipt)
    return receipt


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-attempts", type=int, default=5)
    ap.add_argument(
        "--out-root",
        type=Path,
        default=PHASE07 / "lane_c_step38_sb_003_end_regen",
    )
    args = ap.parse_args()

    node = _load("phase07_storyboard_tau_node", SCRIPTS / "phase07_storyboard_tau_node.py")
    phase_c = _load("phase_c_regenerate_storyboard_frames", SCRIPTS / "phase_c_regenerate_storyboard_frames.py")

    delta = json.loads(DELTA_PATH.read_text(encoding="utf-8"))
    # Bind the exact contract + delta we are executing against (fail closed on drift).
    contract_sha = _sha256_file(CONTRACT_PATH)
    expected_contract_sha = delta["targets"]["sb_003_end_frame_contract"]["sha256"]
    if contract_sha != expected_contract_sha:
        print(json.dumps({"status": "BLOCKED_CONTRACT_SHA_DRIFT",
                          "expected": expected_contract_sha, "observed": contract_sha}))
        return 2

    packet = json.loads((PHASE07 / "storyboard_packet.json").read_text(encoding="utf-8"))
    panels = {p["panel_id"]: p for p in packet["panels"]}
    required = ["Embry", "Kai"]
    panel = dict(panels["sb_003"])
    panel["required_entities"] = required
    panel["references"] = phase_c._panel_refs()

    out_root: Path = args.out_root
    frames_dir = out_root / "generated_storyboard_frames"
    gen_dir = out_root / "receipts" / "storyboard_frame_generation"
    review_dir = out_root / "receipts" / "storyboard_identity_review"
    comp_dir = out_root / "receipts" / "composition_check"
    cont_dir = out_root / "receipts" / "continuity_review"
    for d in (frames_dir, gen_dir, review_dir, comp_dir, cont_dir):
        d.mkdir(parents=True, exist_ok=True)

    frame_id = "sb_003_end_frame"
    out_png = frames_dir / f"{frame_id}.png"
    base_prompt = _compose_prompt(phase_c, panel, delta)

    anchor_start = SUCCESSOR_FRAMES / "sb_003_start_frame.png"
    next_start = SUCCESSOR_FRAMES / "sb_004_start_frame.png"
    for anchor in (anchor_start, next_start):
        if not anchor.exists():
            print(json.dumps({"status": "BLOCKED_ANCHOR_MISSING", "path": str(anchor)}))
            return 2

    attempts: list[dict] = []
    accepted = False
    accepted_review = None
    accepted_comp = None
    accepted_cont: list[dict] = []

    for attempt in range(1, args.max_attempts + 1):
        failures_prev = attempts[-1]["failures"] if attempts else []
        prompt = base_prompt if attempt == 1 else base_prompt + "\n" + _repair_addendum(attempt, failures_prev)

        gen = phase_c._generate(prompt, out_png, gen_dir, frame_id, attempt)
        row: dict[str, Any] = {
            "attempt": attempt,
            "generation_ok": bool(gen.get("ok")),
            "image_sha256": gen.get("image_sha256"),
            "prompt_sha256": gen.get("prompt_sha256"),
            "review_status": None,
            "embedding_scores": None,
            "composition_status": None,
            "continuity": None,
            "failures": [],
        }
        if not gen.get("ok"):
            row["failures"] = [f"generation failed rc={gen.get('returncode')}: {gen.get('stderr_tail')}"]
            attempts.append(row)
            _write_json(out_root / "lane_c_regeneration_receipt.partial.json",
                        {"attempts": attempts, "updated_at": _now()})
            continue

        # (a) augmented identity review (full-frame VLM + embedding subgate) -- unweakened node reviewer.
        review = node._run_identity_continuity_review(
            {"path": str(out_png)}, panel=panel, frame_key="end_frame",
            required_entities=required, identity_review_policy=phase_c.IDENTITY_REVIEW_POLICY,
            receipts_dir=review_dir,
        )
        review["review_prompt_sha256"] = _sha256_text(
            node._identity_review_prompt(panel, frame_key="end_frame", required_entities=required))
        _write_json(review_dir / f"{frame_id}.attempt_{attempt:02d}_identity_continuity_review.json", review)
        emb = review.get("face_embedding_subgate", {})
        scores = {er["entity"]: er.get("best_cosine") for er in emb.get("entity_results", [])}
        row["review_status"] = review.get("status")
        row["full_frame_status"] = review.get("full_frame_status")
        row["embedding_status"] = emb.get("status")
        row["embedding_scores"] = scores
        row["embedding_threshold"] = emb.get("threshold")
        failures: list[str] = []
        if review.get("status") != "PASS":
            failures.extend(str(b) for b in (review.get("blocking_findings") or []))

        # (b) composition check -- Kai mouth not camera-readable (only if identity passed;
        # otherwise we still record it for the attempt table but it cannot accept).
        comp = _composition_check(
            phase_c, out_png, comp_dir / f"{frame_id}.attempt_{attempt:02d}_composition_check.json")
        row["composition_status"] = comp.get("status")
        row["composition_findings"] = comp.get("blocking_findings")
        if comp.get("status") != "PASS":
            failures.extend(str(b) for b in (comp.get("blocking_findings") or []))

        # (c) continuity re-review for both affected pairs.
        cont_results = []
        pair_specs = [
            ("sb_003_start__to__sb_003_end", anchor_start, out_png,
             "start->end within the same panel (sb_003)"),
            ("sb_003_end__to__sb_004_start", out_png, next_start,
             "end->next-start across adjacent panels (sb_003 end -> sb_004 start)"),
        ]
        for pair_id, fa, fb, transition in pair_specs:
            rec = phase_c._continuity_review(
                fa, fb, transition,
                cont_dir / f"{frame_id}.attempt_{attempt:02d}.{pair_id}_continuity.json",
                pair_id)
            cont_results.append({"pair": pair_id, "status": rec["status"],
                                 "blocking_findings": rec["blocking_findings"]})
            if rec["status"] != "PASS":
                failures.extend(f"continuity[{pair_id}]: {b}" for b in (rec["blocking_findings"] or [f"verdict {rec['status']}"]))
        row["continuity"] = cont_results
        row["failures"] = failures

        attempts.append(row)
        _write_json(out_root / "lane_c_regeneration_receipt.partial.json",
                    {"attempts": attempts, "updated_at": _now()})

        a_pass = review.get("status") == "PASS"
        b_pass = comp.get("status") == "PASS"
        c_pass = all(r["status"] == "PASS" for r in cont_results)
        print(f"attempt {attempt}: identity={review.get('status')} scores={scores} "
              f"composition={comp.get('status')} continuity={[r['status'] for r in cont_results]}")
        if a_pass and b_pass and c_pass:
            accepted = True
            accepted_review = review
            accepted_comp = comp
            accepted_cont = cont_results
            break

    final_status = "PASS_LANE_C_SB_003_END_REGENERATED" if accepted else "FAILED_LANE_C_ATTEMPTS_EXHAUSTED"
    summary = {
        "schema": "persona_dream.lane_c.sb_003_end_regeneration_receipt.v1",
        "status": final_status,
        "created_at": _now(),
        "run_id": RUN_ID,
        "revision_id": REVISION_ID,
        "frame_id": "sb_003.end_frame",
        "step38_delta": {
            "path": str(DELTA_PATH.relative_to(SKILL_ROOT)),
            "contract_path": str(CONTRACT_PATH.relative_to(SKILL_ROOT)),
            "contract_sha256": contract_sha,
        },
        "identity_source": {
            "asset_id": "embry_contact_sheet_v3", "path": str(phase_c.EMBRY_SHEET),
            "sha256": _sha256_file(phase_c.EMBRY_SHEET)},
        "kai_reference": {"path": str(phase_c.KAI_SHEET), "sha256": _sha256_file(phase_c.KAI_SHEET)},
        "identity_anchor_start_frame": {
            "path": str(anchor_start), "sha256": _sha256_file(anchor_start)},
        "image_model": phase_c.IMAGE_MODEL, "image_auth": phase_c.IMAGE_AUTH,
        "review_model": "gpt-5.5", "review_auth": "codex-oauth",
        "max_attempts": args.max_attempts,
        "attempts_used": len(attempts),
        "accepted": accepted,
        "new_frame_path": str(out_png) if accepted else None,
        "new_frame_sha256": _sha256_file(out_png) if accepted and out_png.exists() else None,
        "superseded_frame": {
            "index_key": "sb_003.end_frame",
            "path": str(SUCCESSOR_FRAMES / "sb_003_end_frame.png"),
            "sha256": _sha256_file(SUCCESSOR_FRAMES / "sb_003_end_frame.png"),
            "disposition": "retained_as_superseded_evidence",
        },
        "acceptance": {
            "identity_review": accepted_review.get("status") if accepted_review else None,
            "identity_authority": "face_embedding_subgate",
            "embedding_scores": (
                {er["entity"]: er.get("best_cosine")
                 for er in accepted_review.get("face_embedding_subgate", {}).get("entity_results", [])}
                if accepted_review else None),
            "embedding_threshold": 0.421,
            "composition_status": accepted_comp.get("status") if accepted_comp else None,
            "composition_receipt": (
                str(comp_dir / f"sb_003_end_frame.attempt_{len(attempts):02d}_composition_check.json")
                if accepted else None),
            "continuity": accepted_cont if accepted else None,
        },
        "attempts": attempts,
        "claims": {
            "proves": [
                "sb_003_end_frame was regenerated via the Phase C GPT Image 2 lane with the step 38 "
                "composition delta applied, and (only if accepted) passes the unweakened augmented identity "
                "review, a composition check proving Kai's mouth is not camera-readable, and continuity "
                "re-review for both affected pairs",
            ] if accepted else [
                "the Lane C bounded regeneration loop was executed live; no attempt satisfied all three "
                "acceptance checks within the attempt budget, so the frame is left FAILED and no "
                "requalification is attempted (fail closed)",
            ],
            "does_not_prove": [
                "Kling readiness", "provider media publication", "publication authorization",
                "paid authorization", "provider return",
                "lip-sync-on-return (Lane C removes the known cause of the prior step 38 failure by "
                "construction, but proof requires a real return)",
            ],
        },
        "mocked": False, "live": True, "paid_call_authorized": False, "provider_live": False,
    }
    _write_json(out_root / "lane_c_regeneration_receipt.json", summary)
    print(json.dumps({"status": final_status, "accepted": accepted,
                      "attempts_used": len(attempts),
                      "receipt": str(out_root / "lane_c_regeneration_receipt.json")}, indent=2))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
