#!/usr/bin/env python3
"""Execute one pilot F-arm run (protocol v3): full loop with storyboard frames.

Faithful-standard lane, per producer contract F and the frozen render
boundary (no non-paid video renderer exists at run time, so the storyboard
frames ARE the visual artifact — recorded as a scope note):

  1. Producer-blinding receipt over {contract F, root_set_reading.md}.
  2. Manifest verify (drift aborts).
  3. Dream idea + 4-panel storyboard composed by the Tau text node, grounded
     ONLY in the assigned root set.
  4. Each panel rendered with the SAME engine the standard phase-07 lane uses
     (scillm generate-image, gpt-image-2, via phase_c_regenerate_storyboard_
     frames._generate) — <= 2 attempts per panel.
  5. Identity gate per frame: the ArcFace face-embedding subgate (buffalo_l,
     threshold 0.421) against Embry's accepted contact sheet v3 — the SOLE
     identity authority, fail-closed. Persons without reference sheets
     (e.g. Brandon, Marketa) render uncertified; disclosed in the receipt.
  6. Independent re-perception: Tau VLM montage review of the accepted frames
     (advisory content observation, never an identity decision).
  7. Observation packet over the frames (frame_evidence + step-36-shaped
     identity hook + declared coverage gaps; media identity = sha256 of the
     composed 2x2 contact sheet).
  8. phase13/14 live through the unmodified gates; certified transactional
     persist (kind synthetic_dream_memory, evidence_class synthetic_dream,
     origin storyboard_frames — explicit, never a silent conversion).
  9. Arm receipt with per-call receipts, scope notes, image-call count.

A failed gate after the per-panel retry ends the run as failed (protocol:
run invalid, not patched).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8601"
PERSONA = "embry"
RUN_ID = "pilot-c-vs-f"
REVISION_ID = "pilot_c_vs_f"
EMBRY_SHEET = Path(
    "/mnt/storage12tb/media/personas/embry/assets/contact_sheets/"
    "embry-gpt-image-2-v3/images/embry_contact_sheet_v3.png"
)
MAX_ATTEMPTS = 2
PANEL_COUNT = 4


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose_prompt(panel: dict, other_person: str) -> str:
    header = (
        "Create a single cinematic storyboard frame. Real storyboard frame — "
        "not a contact sheet, not a collage, not a UI mockup, no rendered text.\n"
        "MANDATORY CHARACTER IDENTITY REQUIREMENT (HIGHEST PRIORITY):\n"
        "Embry must be clearly visible in the foreground with her face readable "
        "in three-quarter view, strongly matched to her reference identity: "
        "adult woman, brown hair (tied back or loose), recognizable consistent "
        "face. Do not depict her as male, teenage, blond, generic, back-facing, "
        "or too distant to identify.\n"
        f"{other_person} appears as described in the panel action; no identity "
        "reference exists for this person — render consistently with the "
        "description, secondary to Embry in prominence.\n"
    )
    style = (
        "STYLE: realistic cinematic storyboard frame, natural light, "
        "emotionally grounded, believable everyday detail, not glossy "
        "advertising.\nNEGATIVE CONSTRAINTS: no missing Embry, no generic "
        "woman substituted for Embry, no back-facing-only Embry, no tiny "
        "distant faces, no occluded faces, no contact sheet, no collage, no "
        "character-sheet layout, no text overlays.\n"
    )
    lines = [
        header,
        f"PANEL {panel['panel_id']} ({panel.get('time_range', '')}): {panel.get('shot', '')}",
        f"SETTING: {panel.get('setting', '')}",
        f"ACTION: {panel.get('action', '')}",
        f"FRAME: {panel.get('start_frame_description', '')}",
        f"MOOD: {panel.get('mood', '')}",
        style,
        "OUTPUT: one 16:9 photorealistic storyboard frame, 1536x864.",
    ]
    return "\n".join(lines)


def repair_delta(base: str, findings: list[str], attempt: int) -> str:
    return base + (
        f"\nSURGICAL REPAIR DELTA (attempt {attempt}) — previous render FAILED "
        "the face-embedding identity gate.\nBlocking findings:\n"
        + "\n".join(f"  - {f}" for f in findings)
        + "\nMUST: Embry's face large, sharp, three-quarter view, foreground, "
        "unoccluded, matching her established identity.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", required=True, choices=["r1", "r2"])
    parser.add_argument("--inputs-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    run_name = f"{args.set.upper()}-F"
    dream_id = f"pilot_{args.set}_f"
    other_person = {"r1": "Brandon", "r2": "Marketa Lawson"}[args.set]

    # 1. blinding
    contract = ROOT / "contracts/pilot_producer_contract_F.v1.md"
    blinding_out = out / f"blinding_{run_name}.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/pilot_producer_blinding.py"),
         "--producer-role", run_name,
         "--shown-file", str(contract),
         "--shown-file", str(args.inputs_dir / "root_set_reading.md"),
         "--out", str(blinding_out)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"BLOCKED_PILOT_F_BLINDING: {proc.stderr[-400:]}", file=sys.stderr)
        return 2

    # 2. manifest verify
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/pilot_run_manifest.py"), "--verify"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"BLOCKED_PILOT_F_MANIFEST_DRIFT: {proc.stderr[-400:]}", file=sys.stderr)
        return 2

    adapter = _load("tau_text_reasoning_adapter")
    phase_c = _load("phase_c_regenerate_storyboard_frames")
    subgate = _load("identity_face_embedding_subgate")
    p13 = _load("phase13_self_interpretation")
    p14 = _load("phase14_tom_validation")
    p15 = _load("phase15_dream_persistence")

    # 3. storyboard composition via Tau text, grounded ONLY in the root set
    reading = (args.inputs_dir / "root_set_reading.md").read_text()
    prompt = (
        "You are composing Embry's synthetic dream as a 4-panel storyboard. "
        "Ground the dream ONLY in these root memories of hers (the dream "
        "recombines and heightens them; it is synthetic, never literal "
        "history):\n" + reading + "\n\n"
        "Compose a dream synopsis (2-3 sentences) and EXACTLY 4 storyboard "
        "panels. Embry must appear foreground with her face visible in every "
        f"panel; {other_person} appears in at least 2 panels. Return strict "
        'JSON: {"dream_synopsis": "...", "panels": [{"panel_id": "sb_001", '
        '"time_range": "0.0-2.5s", "shot": "...", "setting": "...", '
        '"action": "...", "start_frame_description": "...", "mood": "..."}, '
        "... 4 panels total]}"
    )
    parsed, tau_receipt = adapter.dispatch_text_reasoning(
        prompt, f"embry-pilot-{args.set}-f-storyboard",
        output_contract={"dream_synopsis": "string", "panels": ["4 panel objects"]},
    )
    if parsed is None or len(parsed.get("panels", [])) != PANEL_COUNT:
        print(f"BLOCKED_PILOT_F_STORYBOARD_COMPOSE: {json.dumps(tau_receipt)[:200]}",
              file=sys.stderr)
        return 1
    (out / "storyboard_plan.json").write_text(json.dumps(
        {"plan": parsed, "tau_receipt": {k: tau_receipt.get(k) for k in
                                         ("route", "model", "live", "http_status")}},
        indent=2) + "\n")

    # 4+5. generate frames with the standard engine; ArcFace-gate each frame
    embedder = subgate.InsightFaceEmbedder()
    frames_dir = out / "frames"
    frames_dir.mkdir(exist_ok=True)
    accepted_frames = []
    image_calls = 0
    for i, panel in enumerate(parsed["panels"]):
        panel_id = panel.get("panel_id") or f"sb_{i+1:03d}"
        base_prompt = compose_prompt(panel, other_person)
        findings: list[str] = []
        accepted = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            frame_png = frames_dir / f"{panel_id}.attempt_{attempt:02d}.png"
            gen_prompt = base_prompt if attempt == 1 else repair_delta(base_prompt, findings, attempt)
            gen = phase_c._generate(gen_prompt, frame_png, frames_dir, panel_id, attempt)
            image_calls += 1
            if not gen.get("ok"):
                findings = [f"image generation failed rc={gen.get('returncode')}"]
                continue
            verdict = subgate.run_face_embedding_subgate(
                frame_path=frame_png,
                references={"Embry": EMBRY_SHEET},
                required_entities=["Embry"],
                embedder=embedder,
            )
            (frames_dir / f"{panel_id}.attempt_{attempt:02d}_arcface.json").write_text(
                json.dumps(verdict, indent=2, default=str) + "\n")
            if verdict.get("verdict") == "PASS":
                accepted = {"panel_id": panel_id, "frame": str(frame_png),
                            "frame_sha256": sha256_file(frame_png),
                            "attempt": attempt,
                            "arcface": {"verdict": "PASS",
                                        "entities": verdict.get("entities")}}
                break
            findings = [str(f) for f in (verdict.get("blocking_findings") or
                                         ["Embry not reference-verifiable"])]
        if accepted is None:
            print(f"BLOCKED_PILOT_F_IDENTITY_GATE: panel {panel_id} failed "
                  f"{MAX_ATTEMPTS} attempts: {findings}", file=sys.stderr)
            (out / "run_invalid.json").write_text(json.dumps(
                {"run": run_name, "invalid": True, "panel": panel_id,
                 "findings": findings, "image_calls": image_calls}, indent=2) + "\n")
            return 1
        accepted_frames.append(accepted)

    # contact sheet = the dream's media identity (one dream event per media hash)
    sheet_png = out / "storyboard_contact_sheet.png"
    from PIL import Image
    imgs = [Image.open(f["frame"]) for f in accepted_frames]
    w, h = imgs[0].size
    sheet = Image.new("RGB", (w * 2, h * 2))
    for i, im in enumerate(imgs):
        sheet.paste(im.resize((w, h)), ((i % 2) * w, (i // 2) * h))
    sheet.save(sheet_png)
    media_sha = sha256_file(sheet_png)

    # 6. independent re-perception: advisory VLM montage observation via Tau
    composite = _load("tau_vlm_composite_review")
    obs_prompt = (
        "Describe what is actually visible in each of the 4 storyboard frames "
        "(2x2 grid, reading order): people present, their apparent activity, "
        "setting, and emotional tone. Judge pixels only; do not speculate "
        "beyond what is visible. Return strict JSON: "
        '{"frames": [{"index": 1, "people": ["..."], "activity": "...", '
        '"setting": "...", "tone": "..."}, ... 4 entries]}'
    )
    payload = {
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": obs_prompt},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," +
                           __import__("base64").b64encode(sheet_png.read_bytes()).decode(),
                           "detail": "high"},
             "label": "storyboard 2x2 contact sheet"},
        ]}],
    }
    vlm_dir = out / "vlm_observation"
    vlm_dir.mkdir(exist_ok=True)
    vlm_resp = composite.post_openai_vlm_via_tau(
        payload, artifact_dir=str(vlm_dir),
        caller_skill="persona-dream-pilot-f-observer",
        purpose="storyboard_content_observation",
    )
    vlm_text = (vlm_resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
    try:
        vlm_frames = json.loads(vlm_text[vlm_text.index("{"):vlm_text.rindex("}") + 1]).get("frames", [])
    except Exception:
        vlm_frames = []
    (out / "vlm_observation.json").write_text(json.dumps(
        {"raw": vlm_text[:4000], "frames": vlm_frames}, indent=2) + "\n")

    # 7. observation packet over the frames
    packet = {
        "schema": "persona_dream.pilot_storyboard_observation_packet.v1",
        "status": "ACCEPTED_STORYBOARD_OBSERVATION",
        "evidence_origin": "storyboard_frames",
        "evidence_class": "synthetic_dream",
        "source_video_sha256": f"sha256:{media_sha}",
        "source_revision_id": REVISION_ID,
        "frame_evidence": [
            {"index": i + 1,
             "timestamp_seconds": round(i * 2.5, 2),
             "in_identity_window": True,
             "in_speaker_window": False,
             "observed_entities": (vlm_frames[i].get("people")
                                   if i < len(vlm_frames) else None)}
            for i in range(len(accepted_frames))
        ],
        "transcript_facts": [],
        "step_hooks": {
            "step_36_identity_temporal_continuity": {
                "identity_window_seconds": [0.0, 10.0],
                "vision_review": {
                    "model": "insightface:buffalo_l (authority) + gpt-5.5 montage (advisory)",
                    "verdict": "PASS",
                    "raw_output_tail": "all 4 frames passed the ArcFace subgate vs embry_contact_sheet_v3",
                },
            },
        },
        "coverage_gaps": [
            "no audio track: visual artifact is storyboard frames (render boundary scope note)",
            "no inter-frame motion: temporal continuity is panel-to-panel only",
            f"{other_person} has no identity reference sheet: presence advisory, uncertified",
        ],
    }
    packet_path = out / "observation_packet.json"
    packet_path.write_text(json.dumps(packet, indent=2) + "\n")

    # 8. phases 13/14 + certified persist
    residue_path = args.inputs_dir / "residue_links.json"
    interp = p13.run_phase13(packet_path, residue_path, None, None,
                             dream_id, REVISION_ID, RUN_ID, PERSONA, live=True)
    p13.write_json(out / "phase13_interpretation.json", interp)
    if not interp["status"].startswith("PASS") or not interp["accepted_interpretations"]:
        print(f"BLOCKED_PILOT_F_PHASE13: {interp['status']}", file=sys.stderr)
        return 1
    tom = p14.run_phase14(interp, dream_id, REVISION_ID, RUN_ID, live=True)
    p13.write_json(out / "phase14_tom.json", tom)
    if not tom["status"].startswith("PASS") or not tom["accepted_tom_candidates"]:
        print(f"BLOCKED_PILOT_F_PHASE14: {tom['status']}", file=sys.stderr)
        return 1

    root_ids = sorted({b.get("source_id") for b in interp.get("source_memory_bindings", [])
                       if b.get("source_id")})
    causal = p15.build_causal_family_fields(PERSONA, dream_id, root_ids, None)
    causal["pilot_run"] = run_name
    dream_doc = p15.build_dream_memory_document(
        dream_id, REVISION_ID, RUN_ID, PERSONA, packet, interp, tom,
        causal_fields=causal)
    dream_doc["evidence_class"] = "synthetic_dream"
    dream_doc["tags"] = [f"persona:{PERSONA}", "synthetic_dream",
                         "persona_dream", "pilot_c_vs_f"]
    interp_vertices = p15.build_interpretation_vertices(
        interp, PERSONA, dream_id, causal_fields=causal)
    return_id = f"storyboard_{media_sha[:32]}"
    allowed, blockers = p15.canonical_write_decision(packet, True, return_id)
    if not allowed:
        print(f"BLOCKED_PILOT_F_WRITE_DECISION: {blockers}", file=sys.stderr)
        return 1
    proof = p15.persist_canonical(
        dream_doc, interp, tom, [], BASE,
        dream_id=dream_id, return_id=return_id, packet=packet,
        phase13_sha=p15.canonical_sha(interp), phase14_sha=p15.canonical_sha(tom),
        interpretation_vertices=interp_vertices, causal_fields=causal,
        include_dream_node=True,
        justification=f"pilot v3 arm {run_name}: storyboard dream loop",
    )
    p13.write_json(out / "persist_proof.json", proof)
    manifest = proof.get("commit_manifest") or {}
    written = bool(proof.get("all_exact_reread_match") and manifest.get("exact_reread_match")
                   and manifest.get("active"))
    if not written:
        print("BLOCKED_PILOT_F_PERSIST", file=sys.stderr)
        return 1

    receipt = {
        "schema": "persona_dream.pilot_arm_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run": run_name,
        "arm": "F",
        "set": args.set,
        "dream_id": dream_id,
        "evidence_class": "synthetic_dream",
        "produced_record_key": dream_doc["_key"],
        "commit_manifest_key": manifest.get("key"),
        "root_ids": root_ids,
        "media_sha256": media_sha,
        "frames": accepted_frames,
        "image_generation_calls": image_calls,
        "phase13_status": interp["status"],
        "phase14_status": tom["status"],
        "accepted_interpretations": len(interp["accepted_interpretations"]),
        "accepted_tom_candidates": len(tom["accepted_tom_candidates"]),
        "blinding_receipt": str(blinding_out),
        "scope_notes": [
            "render boundary: no non-paid video renderer exists at run time; "
            "the storyboard frames are the visual artifact (protocol v3 F clause)",
            f"{other_person} presence is advisory (no identity reference sheet); "
            "ArcFace certifies Embry only",
        ],
    }
    p13.write_json(out / f"arm_receipt_{run_name}.json", receipt)
    print(json.dumps({"run": run_name, "produced": dream_doc["_key"],
                      "manifest": manifest.get("key"), "media_sha": media_sha[:16],
                      "image_calls": image_calls,
                      "p13": interp["status"], "p14": tom["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
