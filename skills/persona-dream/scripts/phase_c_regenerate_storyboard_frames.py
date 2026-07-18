#!/usr/bin/env python3
"""Phase C: regenerate the 8 Phase 07 storyboard frames from the accepted
successor identity source (embry_contact_sheet_v3) and run actual-pixel
creator/reviewer review through the same Tau/Scillm engine the panel node uses.

This driver reuses the real Phase 07 panel-node reviewer
(`_run_identity_continuity_review`) so identity review is done on actual pixels
(base64 image_url of the generated frame plus the Embry and Kai reference sheets)
via Scillm gpt-5.5 — not on filenames or metadata. Frames are generated with GPT
Image 2 through the Scillm `generate-image` codex-oauth wrapper (the same command
the node emits). Every generation and review writes a machine-readable receipt
with hashes. Identity FAIL triggers a bounded surgical repair loop with
MUST INCLUDE / MUST NOT INCLUDE deltas; a frame that exhausts attempts is left
FAILED with a blocker receipt. No paid video/Kling call is made.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import subprocess
import sys
import urllib.request as urllib_request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_SKILL = Path(__file__).resolve().parent.parent  # .../skills/persona-dream
NODE_PATH = REPO_SKILL / "scripts" / "phase07_storyboard_tau_node.py"
SCILLM_RUN = Path("/home/graham/workspace/experiments/agent-skills-main/skills/scillm/run.sh")
SCILLM_CHAT_URL = "http://localhost:4001/v1/chat/completions"

EMBRY_SHEET = Path(
    "/mnt/storage12tb/media/personas/embry/assets/contact_sheets/"
    "embry-gpt-image-2-v3/images/embry_contact_sheet_v3.png"
)
KAI_SHEET = Path(
    "/mnt/storage12tb/media/personas/kai_akana/assets/contact_sheets/"
    "kai_akana_character_sheet.png"
)

IDENTITY_REVIEW_POLICY = {
    "schema": "persona_dream.identity_review_policy.v1",
    "provider": "codex",
    "auth": "codex-oauth",
    "model": "gpt-5.5",
    "source": "dag_identity_review_model_policy",
    "supported": True,
    "fallback_performed": False,
    "error": None,
}

IMAGE_MODEL = "gpt-image-2"
IMAGE_AUTH = "codex-oauth"
IMAGE_SIZE = "1536x864"


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


def _load_node():
    spec = importlib.util.spec_from_file_location("phase07_storyboard_tau_node", NODE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #
IDENTITY_HEADER = """Create a single cinematic storyboard frame for Kling planning. This must be a real storyboard frame, not a contact sheet, not a collage, not a UI mockup.
MANDATORY CHARACTER IDENTITY REQUIREMENT (HIGHEST PRIORITY):
Embry and Kai must both be clearly visible, foreground, and strongly matched to the attached character reference images. The attached Embry reference image and attached Kai reference image are mandatory identity references passed as ACTUAL IMAGE INPUTS, not loose inspiration. Do not invent new faces or substitute generic surfers. Required character identity match is the highest priority, above faces-visible, character-readable composition, and above location/reef/cinematic detail.

CHARACTERS:
Embry is on the left/mid-foreground. She must match the attached Embry contact sheet v3: adult woman, brown hair tied back or wet and pulled back, recognizable face in three-quarter view, navy rashguard or navy polo-style surf top. She must read clearly as the same woman from the reference. Do not depict her as male, teenage, blond, short-haired, generic, back-facing, or too distant to identify.
Kai is on the right foreground. He must match the attached Kai character sheet: young adult man, tan skin, dark curly wet hair, athletic surfer build, black rashguard, recognizable face in three-quarter view. He must read clearly as the same person from the reference. Do not make him generic, back-facing only, hidden, or too distant to identify.

COMPOSITION:
Medium-wide waterline foreground two-shot, not a distant wide establishing shot. Embry and Kai are the only large foreground people, chest-up or waist-up above the waterline, faces clearly visible and not blocked by surfboards, spray, glare, other surfers, hair, shadows, or water.
"""

STYLE_BLOCK = """STYLE:
Realistic cinematic storyboard frame, natural daylight, believable surf photography, low waterline camera, subtle humidity and ocean glare, emotionally grounded, not glossy tourism advertising. Hot, humid daylight at Kahalu'u Bay; clear shallow water reveals dark lava reef shapes below the surface; a public surf lineup is visible in the background with local surfers holding priority (background surfers stay smaller and secondary).

NEGATIVE CONSTRAINTS:
No missing Embry. No missing Kai. No generic surfer substituted for Embry or Kai. No swapped identities. No back-facing-only characters. No tiny distant faces. No occluded faces. No extra foreground surfers. No crowd blocking the main characters. No empty tropical postcard. No contact sheet. No collage. No character-sheet layout.
"""

REFERENCE_LINE = (
    "Reference assets attached as mandatory identity/reference inputs (ACTUAL IMAGE INPUTS), not loose inspiration: "
    f"Embry accepted contact sheet v3 (identity_reference): {EMBRY_SHEET}; "
    f"Kai Akana character sheet (identity_reference): {KAI_SHEET}"
)


def _base_prompt(panel: dict, frame_key: str) -> str:
    frame_word = "Start frame" if frame_key == "start_frame" else "End frame"
    frame_desc = panel.get(frame_key, {})
    if isinstance(frame_desc, dict):
        frame_desc = frame_desc.get("description") or frame_desc.get("summary") or ""
    dialogue = panel.get("dialogue")
    beats = "; ".join(str(b) for b in (panel.get("acting_beats") or []))
    lines = [
        IDENTITY_HEADER,
        f"PANEL {panel.get('panel_id')} ({panel.get('time_range')}): {panel.get('shot','')}",
        f"ACTION: {panel.get('action','')}",
        f"{frame_word}: {frame_desc}" if frame_desc else f"{frame_word} of this panel's action.",
    ]
    if dialogue:
        lines.append(f"DIALOGUE INTENT (do not render text): {dialogue}")
    if beats:
        lines.append(f"ACTING BEATS: {beats}")
    lines.append(f"CAMERA: {json.dumps(panel.get('camera', {}))}")
    lines.append(f"LIGHTING: {json.dumps(panel.get('lighting', {}))}")
    lines.append(STYLE_BLOCK)
    lines.append("OUTPUT: one 16:9 photorealistic storyboard frame, 1536x864.")
    lines.append(REFERENCE_LINE)
    return "\n".join(lines)


def _repair_prompt(base: str, blocking_findings: list[str], attempt: int) -> str:
    must_include = [
        "Embry's face clearly visible in three-quarter view and matching the attached Embry contact sheet v3.",
        "Kai's face clearly visible in three-quarter view and matching the attached Kai character sheet.",
        "Both characters large in the foreground, reference-verifiable, not generic.",
    ]
    must_not = [
        "Do NOT render either character as generic, back-facing-only, distant, or occluded.",
        "Do NOT substitute a different person for Embry or Kai.",
        "Do NOT let the frame become a location establishing shot without readable faces.",
    ]
    delta = [
        "",
        f"SURGICAL REPAIR DELTA (attempt {attempt}) — the previous render FAILED identity review.",
        "Reviewer blocking findings to fix:",
    ]
    delta += [f"  - {f}" for f in blocking_findings] or ["  - (identity not reference-verifiable)"]
    delta.append("MUST INCLUDE:")
    delta += [f"  - {m}" for m in must_include]
    delta.append("MUST NOT INCLUDE:")
    delta += [f"  - {m}" for m in must_not]
    return base + "\n" + "\n".join(delta)


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def _generate(prompt: str, out_png: Path, gen_dir: Path, frame_id: str, attempt: int) -> dict:
    prompt_path = gen_dir / f"{frame_id}.attempt_{attempt:02d}.prompt.md"
    receipt_path = gen_dir / f"{frame_id}.attempt_{attempt:02d}_scillm_image_generation_receipt.json"
    events_path = gen_dir / f"{frame_id}.attempt_{attempt:02d}_scillm_image_generation_events.jsonl"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    cmd = [
        "bash", str(SCILLM_RUN), "generate-image",
        "--auth", IMAGE_AUTH,
        "--prompt-file", str(prompt_path),
        "--out", str(out_png),
        "--receipt", str(receipt_path),
        "--events-out", str(events_path),
        "--model", IMAGE_MODEL,
        "--size", IMAGE_SIZE,
        "--quality", "high",
        "--caller-skill", "persona-dream-phase07-panel-creator",
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    ok = out_png.exists()
    sha = _sha256_file(out_png) if ok else None
    receipt = {
        "schema": "persona_dream.phase_c.frame_generation_receipt.v1",
        "frame_id": frame_id,
        "attempt": attempt,
        "created_at": _now(),
        "model": IMAGE_MODEL,
        "auth": IMAGE_AUTH,
        "provider": "codex",
        "size": IMAGE_SIZE,
        "command": cmd,
        "prompt_file": str(prompt_path),
        "prompt_sha256": _sha256_text(prompt),
        "scillm_receipt": str(receipt_path) if receipt_path.exists() else None,
        "events": str(events_path) if events_path.exists() else None,
        "output_path": str(out_png),
        "image_sha256": sha,
        "returncode": proc.returncode,
        "ok": ok,
        "stdout_tail": proc.stdout[-800:],
        "stderr_tail": proc.stderr[-800:],
        "mocked": False,
        "live": True,
    }
    _write_json(gen_dir / f"{frame_id}.attempt_{attempt:02d}_generation_receipt.json", receipt)
    return receipt


# --------------------------------------------------------------------------- #
# Continuity review (two-frame pixel comparison via gpt-5.5)
# --------------------------------------------------------------------------- #
def _scillm_keys() -> list[str]:
    keys = ["sk-dev-proxy-123"]
    env = Path("/home/graham/workspace/experiments/scillm/.env")
    if env.exists():
        for line in env.read_text(errors="ignore").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                n, v = line.split("=", 1)
                if n.strip() in {"SCILLM_PROXY_KEY", "SCILLM_MASTER_KEY", "LITELLM_MASTER_KEY"}:
                    v = v.strip().strip("\"'")
                    if v:
                        keys.insert(0, v)
    return keys


def _image_part(path: Path, label: str) -> dict:
    mt = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    enc = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mt};base64,{enc}", "detail": "high"}, "label": label}


def _post_scillm(payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    last = None
    for key in _scillm_keys():
        req = urllib_request.Request(
            SCILLM_CHAT_URL, data=data,
            headers={"Authorization": f"Bearer {key}",
                     "X-Caller-Skill": "persona-dream-phase07-continuity-reviewer",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=240) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
    raise RuntimeError(f"scillm continuity call failed: {last}")


CONTINUITY_PROMPT = """You are a strict visual storyboard CONTINUITY reviewer. You are given two generated storyboard frames (Frame A first, then Frame B) plus the Embry and Kai identity reference sheets. Judge the actual pixels only.
Return strict JSON with keys: {"verdict":"PASS|FAIL","blocking_findings":["..."],"notes":"..."}.
PASS only if ALL are true across Frame A and Frame B:
1. Embry is the SAME person in both frames and matches the Embry reference.
2. Kai is the SAME person in both frames and matches the Kai reference.
3. Wardrobe/equipment continuity holds (Embry navy rashguard, Kai black rashguard, boards consistent).
4. Lighting/time-of-day and the visible lava reef boundary stay consistent.
5. The action progresses plausibly from Frame A to Frame B ({transition}).
Fail if any identity flips, wardrobe/board/lighting/reef breaks, or the frames are unrelated.
Transition context: {transition}
"""


def _continuity_review(frame_a: Path, frame_b: Path, transition: str, out_path: Path,
                       pair_id: str) -> dict:
    prompt = CONTINUITY_PROMPT.replace("{transition}", transition)
    content = [
        {"type": "text", "text": prompt},
        {"type": "text", "text": "Frame A:"}, _image_part(frame_a, "frame_a"),
        {"type": "text", "text": "Frame B:"}, _image_part(frame_b, "frame_b"),
        {"type": "text", "text": "Embry reference:"}, _image_part(EMBRY_SHEET, "embry_ref"),
        {"type": "text", "text": "Kai reference:"}, _image_part(KAI_SHEET, "kai_ref"),
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
    try:
        raw = _post_scillm(payload)
        parsed = json.loads(raw["choices"][0]["message"]["content"])
        blocking = [str(x) for x in parsed.get("blocking_findings", []) if isinstance(x, str)]
        if parsed.get("verdict") == "PASS" and not blocking:
            status = "PASS"
        elif parsed.get("verdict") != "PASS" and not blocking:
            blocking = [f"continuity verdict was {parsed.get('verdict')}"]
    except Exception as exc:  # noqa: BLE001
        blocking = [f"continuity review call failed: {exc}"]
    receipt = {
        "schema": "persona_dream.phase_c.continuity_review.v1",
        "created_at": _now(),
        "pair_id": pair_id,
        "transition": transition,
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
# Main driver
# --------------------------------------------------------------------------- #
def _panel_refs() -> list[dict]:
    return [
        {"id": "embry_character_sheet", "title": "Embry accepted contact sheet v3",
         "role": "identity_reference", "media_type": "image", "path": str(EMBRY_SHEET)},
        {"id": "kai_character_sheet", "title": "Kai Akana character sheet",
         "role": "identity_reference", "media_type": "image", "path": str(KAI_SHEET)},
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--packet", required=True, type=Path)
    ap.add_argument("--out-root", required=True, type=Path)
    ap.add_argument("--max-attempts", type=int, default=5)
    ap.add_argument("--panels", default="sb_001,sb_002,sb_003,sb_004")
    ap.add_argument("--seed-frame", type=Path, default=None,
                    help="Pre-generated frame to reuse for the first frame (skip its generation).")
    ap.add_argument("--seed-frame-id", default=None)
    args = ap.parse_args()

    node = _load_node()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    panels = {p["panel_id"]: p for p in packet["panels"]}
    wanted = args.panels.split(",")

    out_root = args.out_root
    frames_dir = out_root / "generated_storyboard_frames"
    gen_dir = out_root / "receipts" / "storyboard_frame_generation"
    review_dir = out_root / "receipts" / "storyboard_identity_review"
    cont_dir = out_root / "receipts" / "continuity_review"
    for d in (frames_dir, gen_dir, review_dir, cont_dir):
        d.mkdir(parents=True, exist_ok=True)

    required = ["Embry", "Kai"]
    results: list[dict] = []
    ordered_frames: list[tuple[str, str, Path]] = []  # (frame_id, panel_id, png)

    for panel_id in wanted:
        panel = dict(panels[panel_id])
        panel["required_entities"] = required
        panel["references"] = _panel_refs()
        for frame_key in ("start_frame", "end_frame"):
            frame_id = f"{panel_id}_{frame_key}"
            out_png = frames_dir / f"{frame_id}.png"
            base = _base_prompt(panel, frame_key)
            attempts: list[dict] = []
            final_status = "FAILED"
            review = None
            # Resume: reuse an already-accepted frame (do not regenerate PASSed frames).
            existing_review = review_dir / f"{frame_id}_identity_continuity_review.json"
            if out_png.exists() and existing_review.exists():
                try:
                    prev = json.loads(existing_review.read_text(encoding="utf-8"))
                except Exception:
                    prev = {}
                if prev.get("status") == "PASS":
                    review = prev
                    final_status = "PASS"
                    attempts.append({"attempt": 0, "resumed": True,
                                     "generation_sha256": _sha256_file(out_png),
                                     "review_status": "PASS"})
            for attempt in range(1, args.max_attempts + 1):
                if final_status == "PASS":
                    break
                if attempt == 1 and args.seed_frame and args.seed_frame_id == frame_id and args.seed_frame.exists():
                    import shutil
                    shutil.copyfile(args.seed_frame, out_png)
                    gen = {"schema": "persona_dream.phase_c.frame_generation_receipt.v1",
                           "frame_id": frame_id, "attempt": attempt, "created_at": _now(),
                           "model": IMAGE_MODEL, "auth": IMAGE_AUTH, "provider": "codex",
                           "seeded_from": str(args.seed_frame), "output_path": str(out_png),
                           "image_sha256": _sha256_file(out_png), "ok": True, "mocked": False, "live": True}
                    _write_json(gen_dir / f"{frame_id}.attempt_{attempt:02d}_generation_receipt.json", gen)
                else:
                    prompt = base if attempt == 1 else _repair_prompt(
                        base, review.get("blocking_findings", []) if review else [], attempt)
                    gen = _generate(prompt, out_png, gen_dir, frame_id, attempt)
                if not gen.get("ok"):
                    attempts.append({"attempt": attempt, "generation": gen, "review": None,
                                     "status": "GENERATION_FAILED"})
                    continue
                review = node._run_identity_continuity_review(
                    {"path": str(out_png)},
                    panel=panel, frame_key=frame_key, required_entities=required,
                    identity_review_policy=IDENTITY_REVIEW_POLICY, receipts_dir=review_dir,
                )
                review["review_prompt_sha256"] = _sha256_text(
                    node._identity_review_prompt(panel, frame_key=frame_key, required_entities=required))
                _write_json(review_dir / f"{frame_id}_identity_continuity_review.json", review)
                attempts.append({"attempt": attempt, "generation_sha256": gen.get("image_sha256"),
                                 "review_status": review.get("status"),
                                 "blocking_findings": review.get("blocking_findings")})
                if review.get("status") == "PASS":
                    final_status = "PASS"
                    break
            frame_result = {
                "frame_id": frame_id, "panel_id": panel_id, "frame_key": frame_key,
                "status": final_status,
                "image_path": str(out_png) if out_png.exists() else None,
                "image_sha256": _sha256_file(out_png) if out_png.exists() else None,
                "attempts_used": len(attempts),
                "attempts": attempts,
                "final_review_status": review.get("status") if review else None,
                "final_blocking_findings": review.get("blocking_findings") if review else None,
                "review_receipt": str(review_dir / f"{frame_id}_identity_continuity_review.json"),
            }
            results.append(frame_result)
            if out_png.exists():
                ordered_frames.append((frame_id, panel_id, out_png))
            _write_json(out_root / "phase_c_regeneration_receipt.partial.json",
                        {"frames": results, "updated_at": _now()})

    # Inter-frame continuity (only over identity-PASS frames)
    passed = {r["frame_id"] for r in results if r["status"] == "PASS"}
    continuity: list[dict] = []
    seq = [f"{p}_{k}" for p in wanted for k in ("start_frame", "end_frame")]
    for i in range(len(seq) - 1):
        a_id, b_id = seq[i], seq[i + 1]
        if a_id not in passed or b_id not in passed:
            continue
        a_png = frames_dir / f"{a_id}.png"
        b_png = frames_dir / f"{b_id}.png"
        same_panel = a_id.rsplit("_", 2)[0] == b_id.rsplit("_", 2)[0]
        transition = ("start->end within the same panel" if same_panel
                      else "end->next-start across adjacent panels")
        rec = _continuity_review(a_png, b_png, transition,
                                 cont_dir / f"{a_id}__to__{b_id}_continuity.json",
                                 f"{a_id}__to__{b_id}")
        continuity.append({"pair": f"{a_id}->{b_id}", "same_panel": same_panel,
                           "status": rec["status"], "blocking_findings": rec["blocking_findings"]})

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    summary = {
        "schema": "persona_dream.phase_c.regeneration_summary.v1",
        "created_at": _now(),
        "identity_source": {"asset_id": "embry_contact_sheet_v3", "path": str(EMBRY_SHEET),
                            "sha256": _sha256_file(EMBRY_SHEET)},
        "kai_reference": {"path": str(KAI_SHEET), "sha256": _sha256_file(KAI_SHEET)},
        "image_model": IMAGE_MODEL, "image_auth": IMAGE_AUTH,
        "review_model": "gpt-5.5", "review_auth": "codex-oauth",
        "frames_total": len(results),
        "frames_pass": n_pass,
        "overall_status": f"{n_pass}/{len(results)}_FRAMES_PASS_ACTUAL_PIXEL_IDENTITY_REVIEW",
        "frames": results,
        "continuity": continuity,
        "mocked": False, "live": True,
    }
    _write_json(out_root / "phase_c_regeneration_receipt.json", summary)
    print(json.dumps({"overall_status": summary["overall_status"],
                      "frames_pass": n_pass, "frames_total": len(results),
                      "continuity_pairs": len(continuity)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
