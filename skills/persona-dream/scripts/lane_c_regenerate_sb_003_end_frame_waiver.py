#!/usr/bin/env python3
"""LANE C (step 38 fix), WAIVER STANDARD: regenerate ONLY sb_003_end_frame under
the scoped anchored-identity waiver (scripts/anchored_identity_waiver.py), which
implements the resolution the step-38 composition delta itself already specified:
the end frame's face_required for Kai is FALSE, with Kai's identity anchored by the
UNCHANGED sb_003.start_frame plus non-facial start->end continuity.

Acceptance per attempt requires ALL of:
  (1) composition PASS: Kai's mouth is NOT camera-readable during 5.0-7.7s (and
      Embry stays readable; Kai present with matching build/wardrobe -- NON-facial);
  (2) Embry end-frame augmented identity PASS (full-frame VLM + ArcFace embedding
      subgate) -- Embry always gets the full check, never waived;
  (3) Kai anchored-identity waiver GRANTED: contract flag by hash (a) + start-frame
      full augmented identity PASS for Kai (b) + non-facial start->end continuity
      PASS (c) + waiver receipt emitted (d);
  (4) BOTH continuity pairs PASS: sb_003_start->sb_003_end(new) [non-facial for Kai]
      and sb_003_end(new)->sb_004_start [non-facial for Kai].

Fail closed: bounded loop, max 5 attempts; if exhausted, the frame stays FAILED, no
requalification is attempted, and a blocker receipt is written. No paid/Kling call.
Kai's END-frame face check is the ONLY thing waived; everything else stays strict.
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
WAIVED_CHARACTER = "Kai"
FULL_CHECK_CHARACTER = "Embry"


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
# Delta-composed prompt (waiver standard: Kai's face need NOT be groundable on the
# end frame -- occlusion OR a strong turn are both fine; the ONLY hard goals are
# mouth-not-readable + Embry readable + Kai present with matching build/wardrobe).
# --------------------------------------------------------------------------- #
def _lane_c_delta_block(delta: dict) -> str:
    d = delta["sb_003_end_frame_delta"]
    subject_after = d["prompt_sections.SUBJECT"]["after"]
    chars_add = d["prompt_sections.CHARACTERS_addendum"]
    camera_add = d["camera_contract_addendum"]
    lines = [
        "",
        "=== STEP 38 LANE C COMPOSITION DELTA -- ANCHORED-IDENTITY WAIVER STANDARD ===",
        "This is the sb_003 END frame at the close of Kai's spoken cue (dialogue window",
        "5.0-7.7s). Kai's identity on THIS frame is anchored by the unchanged sb_003 START",
        "frame plus wardrobe/build/hair continuity; his full frontal face is NOT required",
        "here. Apply the following composition delta EXACTLY:",
        f"SUBJECT: {subject_after}",
        f"CHARACTERS: {chars_add}",
        f"CAMERA: {camera_add}",
        "",
        "HARD RULES FOR THIS FRAME (the ONLY strict goals):",
        "  1. KAI'S MOUTH IS NOT CAMERA-READABLE. Achieve this by having Kai turn his head",
        "     OUT toward the lineup/reef he is reading (three-quarter-away or over-the-",
        "     shoulder) AND/OR bring a forearm and spray across his lower face on a paddle",
        "     stroke. A viewer must NOT be able to see his lip shape or lip-read him.",
        "  2. KAI STILL READS AS THE SAME PERSON by NON-FACIAL cues: dark curly wet hair,",
        "     tan skin, athletic surfer build, BLACK rashguard, same board -- continuous with",
        "     the sb_003 start frame. He is a clear, large foreground figure, NOT a tiny",
        "     distant person and NOT omitted.",
        "  3. EMBRY STAYS FULLY READABLE, near-frontal, foreground, face clearly toward the",
        "     camera/decision, strongly matching her reference (adult woman, brown hair,",
        "     navy top). Her mouth may be visible; she is not speaking in this window.",
        "  4. Wardrobe, reef boundary, lineup geometry and lighting stay continuous with the",
        "     sb_003 start frame.",
        "Because Kai's face need not be frontally groundable here, hiding his mouth by a",
        "turn OR by arm/spray occlusion are BOTH acceptable -- pick whichever renders the",
        "mouth clearly unreadable while keeping his hair/build/wardrobe/board recognizable.",
        "=== END STEP 38 LANE C COMPOSITION DELTA ===",
    ]
    return "\n".join(lines)


def _compose_prompt(phase_c, panel: dict, delta: dict) -> str:
    base = phase_c._base_prompt(panel, "end_frame")
    return base + "\n" + _lane_c_delta_block(delta)


def _repair_addendum(attempt: int, failures: list[str]) -> str:
    blob = " ".join(failures).lower()
    lines = [
        "",
        f"SURGICAL REPAIR DELTA (attempt {attempt}) -- the previous render FAILED one or",
        "more Lane C waiver-standard acceptance checks. Fix ALL of these without breaking",
        "the others:",
    ]
    lines += [f"  - {f}" for f in failures]
    lines.append("TARGETED CORRECTION:")
    if "mouth" in blob and "readable" in blob:
        lines += [
            "  Kai's mouth was still camera-readable. Turn his head FURTHER out toward the",
            "  lineup (over-the-shoulder / three-quarter-away) so the lips are angled away and",
            "  unreadable, OR bring his forearm + spray across his lower face on a paddle",
            "  stroke. His face need NOT be frontally visible -- only the mouth must be hidden.",
        ]
    if any(k in blob for k in ("embry", "readable=false")):
        lines += [
            "  Embry must be foreground, near-frontal, face clearly toward camera and matching",
            "  her reference (adult woman, brown hair, navy top). Do NOT turn or occlude Embry.",
        ]
    if any(k in blob for k in ("continuity", "wardrobe", "build", "hair", "board", "kai present", "missing kai", "same person")):
        lines += [
            "  Keep Kai clearly the SAME surfer by NON-facial cues: dark curly wet hair, tan",
            "  skin, athletic build, BLACK rashguard, same board, continuous with the start",
            "  frame. Keep him a large foreground figure (not tiny, not omitted).",
        ]
    lines.append("Preserve wardrobe/reef/lighting continuity with the sb_003 start frame.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Waiver-aware composition check: Kai mouth NOT camera-readable + Embry readable +
# Kai present with matching build/wardrobe (NON-facial). The end-frame frontal
# face-recognizability requirement is intentionally dropped -- that is exactly what
# the anchored-identity waiver relaxes; re-imposing it would recreate the gate
# contradiction the delta already resolved.
# --------------------------------------------------------------------------- #
COMPOSITION_PROMPT = """You are a strict storyboard COMPOSITION reviewer for a lip-sync-avoidance requirement operating under an ANCHORED-IDENTITY WAIVER.
You are given ONE generated storyboard end-frame (the sb_003 END frame, at the close of Kai's ~2.7s spoken cue, dialogue window 5.0-7.7s), plus the Embry and Kai identity reference sheets. Judge the actual pixels only.

Context: Kai's frontal-face identity on THIS end frame is NOT required -- it is anchored by a separate start frame and by non-facial continuity. So DO NOT fail this frame merely because Kai's face is turned away or his lower face is occluded. What matters here:
- Kai (young tan man, dark curly wet hair, black rashguard) has just delivered a restrained cue while looking OUT toward the lineup/reef, so his lips are NOT camera-readable (a turn-away and/or forearm+spray across the lower face are both acceptable).
- Kai must still be PRESENT as a clear, large foreground figure and read as the same surfer by NON-facial cues (dark curly wet hair, tan skin, athletic build, black rashguard) -- NOT a tiny distant person, NOT omitted, NOT identity-swapped for a different build/wardrobe.
- Embry (adult woman, brown hair, navy top) stays camera-readable and is NOT required to hide her mouth.

Answer the SPECIFIC question: is KAI'S MOUTH camera-readable in this frame -- i.e., could a viewer clearly see his mouth/lip shape or lip-read him?

Return strict JSON with EXACTLY these keys:
{"kai_mouth_camera_readable": true|false,
 "kai_present_matching_build": true|false,
 "embry_face_readable": true|false,
 "verdict": "PASS|FAIL",
 "reasons": ["..."]}

Set verdict = PASS if and ONLY if kai_mouth_camera_readable == false AND kai_present_matching_build == true AND embry_face_readable == true. Otherwise verdict = FAIL. Judge pixels, not captions or metadata."""


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
        kai_present = bool(parsed.get("kai_present_matching_build"))
        embry_ok = bool(parsed.get("embry_face_readable"))
        reasons = [str(x) for x in parsed.get("reasons", []) if isinstance(x, str)]
        if parsed.get("verdict") == "PASS" and (not mouth) and kai_present and embry_ok:
            status = "PASS"
        else:
            if mouth:
                reasons.insert(0, "kai_mouth_camera_readable=true (mouth is readable; requirement violated)")
            if not kai_present:
                reasons.insert(0, "kai_present_matching_build=false (Kai absent/tiny/wrong build)")
            if not embry_ok:
                reasons.insert(0, "embry_face_readable=false (Embry not readable)")
    except Exception as exc:  # noqa: BLE001 -- fail closed
        reasons = [f"composition check call failed: {exc}"]
    receipt = {
        "schema": "persona_dream.lane_c.composition_check.waiver.v1",
        "created_at": _now(),
        "question": "Is Kai's mouth camera-readable during the sb_003 dialogue window (5.0-7.7s)?",
        "criteria": {
            "pass_requires": "kai_mouth_camera_readable == false AND kai_present_matching_build == true AND embry_face_readable == true",
            "note": "frontal face-recognizability for Kai is intentionally NOT required here; it is carried by the anchored-identity waiver (start-frame anchor + non-facial continuity).",
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
# NON-FACIAL continuity review for the waived character (condition c). Embry gets
# full identity continuity; Kai gets wardrobe/build/hair/board/position continuity
# WITHOUT requiring a frontal facial match (his head may be turned/occluded).
# --------------------------------------------------------------------------- #
NON_FACIAL_CONTINUITY_PROMPT = """You are a strict visual storyboard CONTINUITY reviewer operating under an ANCHORED-IDENTITY WAIVER for KAI. You are given two generated storyboard frames (Frame A first, then Frame B) plus the Embry and Kai identity reference sheets. Judge the actual pixels only.

In one of these frames Kai's face may be turned away from camera or his lower face occluded (that is intentional and MUST NOT by itself be a failure). For Kai, verify NON-FACIAL identity continuity ONLY. For Embry, verify full identity continuity as usual.

Return strict JSON with EXACTLY these keys:
{"verdict":"PASS|FAIL",
 "embry_same_person": true|false,
 "kai_wardrobe_consistent": true|false,
 "kai_build_consistent": true|false,
 "kai_hair_consistent": true|false,
 "kai_board_consistent": true|false,
 "kai_position_logic_consistent": true|false,
 "blocking_findings": ["..."],
 "notes": "..."}

PASS only if ALL are true across Frame A and Frame B:
1. Embry is the SAME person in both frames and matches the Embry reference (full facial identity).
2. Kai WARDROBE continuity holds (black rashguard consistent).
3. Kai BUILD continuity holds (same athletic surfer build/proportions).
4. Kai HAIR continuity holds (dark curly wet hair consistent).
5. Kai BOARD/equipment continuity holds (same board).
6. Kai POSITION/action logic is plausible from Frame A to Frame B ({transition}).
7. Lighting/time-of-day and the visible lava reef boundary stay consistent.
Do NOT fail merely because Kai's face is turned away or his lower face is occluded in one frame -- that is the point of this frame. Fail if Embry's identity flips, if Kai's wardrobe/build/hair/board break (a different-looking surfer), if lighting/reef break, or if the frames are unrelated.
Transition context: {transition}
"""


def _non_facial_continuity_review(phase_c, frame_a: Path, frame_b: Path, transition: str,
                                  out_path: Path, pair_id: str) -> dict:
    prompt = NON_FACIAL_CONTINUITY_PROMPT.replace("{transition}", transition)
    content = [
        {"type": "text", "text": prompt},
        {"type": "text", "text": "Frame A:"}, phase_c._image_part(frame_a, "frame_a"),
        {"type": "text", "text": "Frame B:"}, phase_c._image_part(frame_b, "frame_b"),
        {"type": "text", "text": "Embry reference:"}, phase_c._image_part(phase_c.EMBRY_SHEET, "embry_ref"),
        {"type": "text", "text": "Kai reference:"}, phase_c._image_part(phase_c.KAI_SHEET, "kai_ref"),
    ]
    payload = {
        "model": "gpt-5.5",
        "messages": [
            {"role": "system", "content": "You are a strict continuity reviewer. Return JSON only. Judge pixels, not metadata."},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }
    status = "FAIL"
    parsed: Any = None
    blocking: list[str] = []
    axes_ok: dict[str, bool] = {}
    try:
        raw = phase_c._post_scillm(payload)
        parsed = json.loads(raw["choices"][0]["message"]["content"])
        blocking = [str(x) for x in parsed.get("blocking_findings", []) if isinstance(x, str)]
        axes_ok = {
            "wardrobe": bool(parsed.get("kai_wardrobe_consistent")),
            "build": bool(parsed.get("kai_build_consistent")),
            "hair": bool(parsed.get("kai_hair_consistent")),
            "board": bool(parsed.get("kai_board_consistent")),
            "position": bool(parsed.get("kai_position_logic_consistent")),
        }
        embry_ok = bool(parsed.get("embry_same_person"))
        all_axes = all(axes_ok.values())
        if parsed.get("verdict") == "PASS" and embry_ok and all_axes and not blocking:
            status = "PASS"
        else:
            if not embry_ok:
                blocking.insert(0, "embry_same_person=false (Embry identity continuity broken)")
            for axis, ok in axes_ok.items():
                if not ok:
                    blocking.append(f"kai_{axis}_consistent=false (non-facial continuity broken)")
            if parsed.get("verdict") != "PASS" and not blocking:
                blocking = [f"continuity verdict was {parsed.get('verdict')}"]
    except Exception as exc:  # noqa: BLE001
        blocking = [f"continuity review call failed: {exc}"]
    receipt = {
        "schema": "persona_dream.lane_c.non_facial_continuity_review.v1",
        "created_at": _now(),
        "pair_id": pair_id,
        "transition": transition,
        "non_facial_identity_continuity_for": [WAIVED_CHARACTER],
        "non_facial_checks": ["wardrobe", "build", "hair", "board", "position"],
        "non_facial_axis_results": axes_ok,
        "frame_a": str(frame_a), "frame_a_sha256": _sha256_file(frame_a) if frame_a.exists() else None,
        "frame_b": str(frame_b), "frame_b_sha256": _sha256_file(frame_b) if frame_b.exists() else None,
        "reviewer_source": "scillm:gpt-5.5:image_url",
        "review_prompt_sha256": _sha256_text(prompt),
        "status": status,
        "blocking_findings": blocking,
        "raw_response": parsed,
        "mocked": False, "live": True,
    }
    _write_json(out_path, receipt)
    return receipt


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-attempts", type=int, default=5)
    ap.add_argument("--out-root", type=Path,
                    default=PHASE07 / "lane_c_step38_sb_003_end_regen_waiver")
    args = ap.parse_args()

    node = _load("phase07_storyboard_tau_node", SCRIPTS / "phase07_storyboard_tau_node.py")
    phase_c = _load("phase_c_regenerate_storyboard_frames", SCRIPTS / "phase_c_regenerate_storyboard_frames.py")
    waiver_mod = _load("anchored_identity_waiver", SCRIPTS / "anchored_identity_waiver.py")

    delta = json.loads(DELTA_PATH.read_text(encoding="utf-8"))
    contract_sha = _sha256_file(CONTRACT_PATH)
    expected_contract_sha = delta["targets"]["sb_003_end_frame_contract"]["sha256"]
    if contract_sha != expected_contract_sha:
        print(json.dumps({"status": "BLOCKED_CONTRACT_SHA_DRIFT",
                          "expected": expected_contract_sha, "observed": contract_sha}))
        return 2

    packet = json.loads((PHASE07 / "storyboard_packet.json").read_text(encoding="utf-8"))
    panels = {p["panel_id"]: p for p in packet["panels"]}
    panel = dict(panels["sb_003"])
    panel["references"] = phase_c._panel_refs()

    out_root: Path = args.out_root
    frames_dir = out_root / "generated_storyboard_frames"
    gen_dir = out_root / "receipts" / "storyboard_frame_generation"
    review_dir = out_root / "receipts" / "storyboard_identity_review"
    comp_dir = out_root / "receipts" / "composition_check"
    cont_dir = out_root / "receipts" / "continuity_review"
    waiver_dir = out_root / "receipts" / "anchored_identity_waiver"
    for d in (frames_dir, gen_dir, review_dir, comp_dir, cont_dir, waiver_dir):
        d.mkdir(parents=True, exist_ok=True)

    frame_id = "sb_003_end_frame"
    out_png = frames_dir / f"{frame_id}.png"

    anchor_start = SUCCESSOR_FRAMES / "sb_003_start_frame.png"
    next_start = SUCCESSOR_FRAMES / "sb_004_start_frame.png"
    for anchor in (anchor_start, next_start):
        if not anchor.exists():
            print(json.dumps({"status": "BLOCKED_ANCHOR_MISSING", "path": str(anchor)}))
            return 2

    # ---- Condition (b): start-frame FULL augmented identity review (Embry+Kai), once.
    anchor_panel = dict(panel)
    anchor_panel["required_entities"] = [FULL_CHECK_CHARACTER, WAIVED_CHARACTER]
    anchor_review = node._run_identity_continuity_review(
        {"path": str(anchor_start)}, panel=anchor_panel, frame_key="start_frame",
        required_entities=[FULL_CHECK_CHARACTER, WAIVED_CHARACTER],
        identity_review_policy=phase_c.IDENTITY_REVIEW_POLICY, receipts_dir=review_dir,
    )
    _write_json(review_dir / "sb_003_start_frame.anchor_augmented_identity_review.json", anchor_review)
    anchor_kai_cosine = next(
        (er.get("best_cosine") for er in anchor_review.get("face_embedding_subgate", {}).get("entity_results", [])
         if er.get("entity") == WAIVED_CHARACTER), None)
    print(f"anchor start-frame review: status={anchor_review.get('status')} "
          f"Kai_cosine={anchor_kai_cosine}")

    base_prompt = _compose_prompt(phase_c, {**panel, "required_entities": [FULL_CHECK_CHARACTER, WAIVED_CHARACTER]}, delta)

    attempts: list[dict] = []
    accepted = False
    accepted_bundle: dict[str, Any] = {}

    for attempt in range(1, args.max_attempts + 1):
        failures_prev = attempts[-1]["failures"] if attempts else []
        prompt = base_prompt if attempt == 1 else base_prompt + "\n" + _repair_addendum(attempt, failures_prev)

        gen = phase_c._generate(prompt, out_png, gen_dir, frame_id, attempt)
        row: dict[str, Any] = {
            "attempt": attempt, "generation_ok": bool(gen.get("ok")),
            "image_sha256": gen.get("image_sha256"), "prompt_sha256": gen.get("prompt_sha256"),
            "composition_status": None, "embry_identity_status": None,
            "embry_embedding_cosine": None, "kai_anchor_cosine": anchor_kai_cosine,
            "kai_waiver_granted": None, "continuity": None, "failures": [],
        }
        if not gen.get("ok"):
            row["failures"] = [f"generation failed rc={gen.get('returncode')}: {gen.get('stderr_tail')}"]
            attempts.append(row)
            _write_json(out_root / "lane_c_regeneration_receipt.partial.json",
                        {"attempts": attempts, "updated_at": _now()})
            continue

        failures: list[str] = []

        # (1) composition check (waiver-aware): Kai mouth not readable.
        comp = _composition_check(
            phase_c, out_png, comp_dir / f"{frame_id}.attempt_{attempt:02d}_composition_check.json")
        row["composition_status"] = comp.get("status")
        row["composition_findings"] = comp.get("blocking_findings")
        if comp.get("status") != "PASS":
            failures.extend(str(b) for b in (comp.get("blocking_findings") or []))

        # (2) Embry end-frame FULL augmented identity (never waived).
        embry_panel = dict(panel)
        embry_panel["required_entities"] = [FULL_CHECK_CHARACTER]
        embry_review = node._run_identity_continuity_review(
            {"path": str(out_png)}, panel=embry_panel, frame_key="end_frame",
            required_entities=[FULL_CHECK_CHARACTER],
            identity_review_policy=phase_c.IDENTITY_REVIEW_POLICY, receipts_dir=review_dir,
        )
        _write_json(review_dir / f"{frame_id}.attempt_{attempt:02d}_embry_identity_review.json", embry_review)
        embry_emb = embry_review.get("face_embedding_subgate", {})
        embry_cos = next((er.get("best_cosine") for er in embry_emb.get("entity_results", [])
                          if er.get("entity") == FULL_CHECK_CHARACTER), None)
        row["embry_identity_status"] = embry_review.get("status")
        row["embry_embedding_cosine"] = embry_cos
        if embry_review.get("status") != "PASS":
            failures.extend(f"embry_identity: {b}" for b in (embry_review.get("blocking_findings") or ["FAIL"]))

        # (4) continuity re-review (non-facial for Kai) for BOTH affected pairs.
        cont_results = []
        pair_specs = [
            ("sb_003_start__to__sb_003_end", anchor_start, out_png,
             "start->end within the same panel (sb_003): Kai turns out / occludes his mouth"),
            ("sb_003_end__to__sb_004_start", out_png, next_start,
             "end->next-start across adjacent panels (sb_003 end -> sb_004 start)"),
        ]
        start_end_cont = None
        for pair_id, fa, fb, transition in pair_specs:
            rec = _non_facial_continuity_review(
                phase_c, fa, fb, transition,
                cont_dir / f"{frame_id}.attempt_{attempt:02d}.{pair_id}_continuity.json", pair_id)
            cont_results.append({"pair": pair_id, "status": rec["status"],
                                 "blocking_findings": rec["blocking_findings"],
                                 "receipt": str(cont_dir / f"{frame_id}.attempt_{attempt:02d}.{pair_id}_continuity.json")})
            if pair_id == "sb_003_start__to__sb_003_end":
                start_end_cont = rec
            if rec["status"] != "PASS":
                failures.extend(f"continuity[{pair_id}]: {b}" for b in (rec["blocking_findings"] or [f"verdict {rec['status']}"]))
        row["continuity"] = cont_results

        # (3) evaluate the anchored-identity waiver for Kai (condition d = emit receipt).
        cont_receipt_path = str(cont_dir / f"{frame_id}.attempt_{attempt:02d}.sb_003_start__to__sb_003_end_continuity.json")
        waiver = waiver_mod.evaluate_anchored_identity_waiver(
            character=WAIVED_CHARACTER, frame_key="end_frame", panel_id="sb_003",
            delta=delta, delta_block_key="sb_003_end_frame_delta",
            contract_target_key="sb_003_end_frame_contract",
            observed_contract_sha256=contract_sha,
            start_frame_review=anchor_review,
            continuity_review=start_end_cont or {},
            anchor_frame_path=str(anchor_start),
            continuity_receipt_path=cont_receipt_path,
        )
        waiver_mod.write_waiver_receipt(
            waiver_dir / f"{frame_id}.attempt_{attempt:02d}_kai_anchored_identity_waiver.json", waiver)
        row["kai_waiver_granted"] = waiver.get("granted")
        if not waiver.get("granted"):
            failures.extend(f"kai_waiver: {r}" for r in (waiver.get("denied_reasons") or ["denied"]))

        row["failures"] = failures
        attempts.append(row)
        _write_json(out_root / "lane_c_regeneration_receipt.partial.json",
                    {"attempts": attempts, "updated_at": _now()})

        comp_pass = comp.get("status") == "PASS"
        embry_pass = embry_review.get("status") == "PASS"
        waiver_pass = bool(waiver.get("granted"))
        cont_pass = all(r["status"] == "PASS" for r in cont_results)
        print(f"attempt {attempt}: composition={comp.get('status')} "
              f"embry_identity={embry_review.get('status')}(cos={embry_cos}) "
              f"kai_waiver={'GRANTED' if waiver_pass else 'DENIED'} "
              f"continuity={[r['status'] for r in cont_results]}")
        if comp_pass and embry_pass and waiver_pass and cont_pass:
            accepted = True
            accepted_bundle = {
                "composition": comp, "embry_review": embry_review,
                "waiver": waiver, "continuity": cont_results,
                "waiver_receipt": str(waiver_dir / f"{frame_id}.attempt_{attempt:02d}_kai_anchored_identity_waiver.json"),
            }
            break

    final_status = "PASS_LANE_C_SB_003_END_REGENERATED_WAIVER" if accepted else "FAILED_LANE_C_ATTEMPTS_EXHAUSTED"
    summary = {
        "schema": "persona_dream.lane_c.sb_003_end_regeneration_receipt.waiver.v1",
        "status": final_status, "created_at": _now(),
        "run_id": RUN_ID, "revision_id": REVISION_ID, "frame_id": "sb_003.end_frame",
        "standard": "anchored_identity_waiver",
        "waiver_module": "scripts/anchored_identity_waiver.py",
        "waived_character": WAIVED_CHARACTER, "full_check_character": FULL_CHECK_CHARACTER,
        "step38_delta": {
            "path": str(DELTA_PATH.relative_to(SKILL_ROOT)),
            "contract_path": str(CONTRACT_PATH.relative_to(SKILL_ROOT)),
            "contract_sha256": contract_sha,
        },
        "identity_source": {"asset_id": "embry_contact_sheet_v3", "path": str(phase_c.EMBRY_SHEET),
                            "sha256": _sha256_file(phase_c.EMBRY_SHEET)},
        "kai_reference": {"path": str(phase_c.KAI_SHEET), "sha256": _sha256_file(phase_c.KAI_SHEET)},
        "identity_anchor_start_frame": {
            "path": str(anchor_start), "sha256": _sha256_file(anchor_start),
            "augmented_review_status": anchor_review.get("status"),
            "kai_embedding_cosine": anchor_kai_cosine},
        "image_model": phase_c.IMAGE_MODEL, "image_auth": phase_c.IMAGE_AUTH,
        "review_model": "gpt-5.5", "review_auth": "codex-oauth",
        "max_attempts": args.max_attempts, "attempts_used": len(attempts), "accepted": accepted,
        "new_frame_path": str(out_png) if accepted else None,
        "new_frame_sha256": _sha256_file(out_png) if accepted and out_png.exists() else None,
        "superseded_frame": {
            "index_key": "sb_003.end_frame",
            "path": str(SUCCESSOR_FRAMES / "sb_003_end_frame.png"),
            "sha256": _sha256_file(SUCCESSOR_FRAMES / "sb_003_end_frame.png"),
            "disposition": "retained_as_superseded_evidence"},
        "acceptance_contract": {
            "per_attempt_requires_all_of": [
                "(1) composition PASS: Kai mouth NOT camera-readable + Embry readable + Kai present matching build (non-facial)",
                "(2) Embry end-frame augmented identity PASS (full-frame VLM + embedding subgate) -- never waived",
                "(3) Kai anchored-identity waiver GRANTED (contract flag by hash + start-frame Kai full augmented PASS + non-facial start->end continuity PASS + waiver receipt)",
                "(4) BOTH continuity pairs PASS (non-facial for Kai)",
            ],
            "max_attempts": args.max_attempts,
            "waiver_is_scoped": "only Kai's END-frame face check is waived; Embry keeps the full check; default fail-closed elsewhere",
        },
        "acceptance": accepted_bundle if accepted else None,
        "attempts": attempts,
        "claims": {
            "proves": [
                "sb_003_end_frame was regenerated via the Phase C GPT Image 2 lane under the scoped "
                "anchored-identity waiver and (only if accepted) passes: a composition check proving "
                "Kai's mouth is not camera-readable, Embry's full augmented identity review, the Kai "
                "anchored-identity waiver (start-frame anchor + non-facial continuity), and both "
                "continuity pairs -- the delta's own recorded design, not a gate weakening",
            ] if accepted else [
                "the Lane C waiver-standard bounded regeneration loop was executed live; no attempt "
                "satisfied all acceptance checks within the budget, so the frame is left FAILED and no "
                "requalification is attempted (fail closed)",
            ],
            "does_not_prove": [
                "Kling readiness", "provider media publication", "publication authorization",
                "paid authorization", "provider return", "lip-sync-on-return",
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
