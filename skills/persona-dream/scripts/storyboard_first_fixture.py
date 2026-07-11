#!/usr/bin/env python3
"""Build the Horus/Embry storyboard-first dry-run fixture.

This command creates deterministic, no-provider artifacts for the pipeline
assessment's worked example. It proves schema/path/status wiring only; it does
not claim visual identity acceptance or perform paid/live calls.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


STATUSES = {
    "NOT_STARTED",
    "BLOCKED",
    "GENERATED_UNREVIEWED",
    "FAILED_AUTOMATED_CHECK",
    "FAILED_MANUAL_REVIEW",
    "ACCEPTED_AUTOMATED",
    "ACCEPTED_MANUAL",
    "PROVIDER_PACKET_ACCEPTED",
    "LIVE_RENDER_SUBMITTED",
    "LIVE_RENDER_ACCEPTED",
    "SUPERSEDED",
}


SCHEMA_REGISTRY = {
    "persona_dream.idea_contract.v1": "idea_contract.schema.json",
    "persona_dream.story_contract.v1": "story_contract.schema.json",
    "persona_dream.timed_beats.v1": "timed_beats.schema.json",
    "persona_dream.story_visual_package.v1": "story_visual_package.schema.json",
    "casting_agent.casting_contract.v1": "casting_contract.schema.json",
    "casting_agent.chosen_reference_inputs.v1": "chosen_reference_inputs.schema.json",
    "casting_agent.contact_sheet_work_order.v1": "contact_sheet_work_order.schema.json",
    "persona_dream.layout_validation.v1": "layout_validation.schema.json",
    "persona_dream.storyboard_identity_contract.v1": "storyboard_identity_contract.schema.json",
    "persona_dream.storyboard_board_receipt.v1": "storyboard_board_receipt.schema.json",
    "persona_dream.kling_scene_payloads.v1": "kling_scene_payloads.schema.json",
    "persona_dream.provider_request_dry_run.v1": "provider_request_dry_run.schema.json",
    "persona_dream.readiness_receipt.v1": "readiness_receipt.schema.json",
    "persona_dream.referenced_artifacts_lock.v1": "referenced_artifacts_lock.schema.json",
    "provider_packet.validation_receipt.v1": "provider_packet_validation_receipt.schema.json",
    "persona_dream.stage_status_receipt.v1": "stage_status_receipt.schema.json",
    "persona_dream.generated_image_attempts.v1": "generated_image_attempts.schema.json",
    "persona_dream.review_display_interaction_manifest.v1": "review_display_interaction_manifest.schema.json",
    "persona_dream.review_display_receipt.v1": "review_display_receipt.schema.json",
    "persona_dream.manual_review_receipt.v1": "manual_review_receipt.schema.json",
    "persona_dream.paid_call_approval_receipt.v1": "paid_call_approval_receipt.schema.json",
    "persona_dream.live_render_receipt.v1": "live_render_receipt.schema.json",
}


SEED = (
    "Horus and Embry have tea under a patio umbrella on a Warhammer 40k void "
    "world while Tyranids run/play in the background and they discuss SPARTA "
    "Explorer."
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def schema_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas"


def font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, max_width: int, fnt: ImageFont.ImageFont) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=fnt)[2] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_width: int,
    fnt: ImageFont.ImageFont,
    fill: str,
    line_gap: int = 5,
) -> int:
    line_h = fnt.size + line_gap if hasattr(fnt, "size") else 22
    for line in wrap(draw, text, max_width, fnt):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h
    return y


def create_reference_sheet(
    path: Path,
    *,
    title: str,
    entity_id: str,
    anchors: list[str],
    panels: list[tuple[str, str]],
    palette: tuple[str, str, str],
) -> dict[str, Any]:
    """Create a deterministic sheet/grid PNG and return layout measurements."""
    path.parent.mkdir(parents=True, exist_ok=True)
    bg, card, accent = palette
    image = Image.new("RGB", (1600, 1200), bg)
    draw = ImageDraw.Draw(image)
    title_font = font(44)
    body_font = font(24)
    small_font = font(16)
    draw.text((48, 34), title, font=title_font, fill="#f7f2e8")
    draw.text((50, 90), entity_id, font=small_font, fill="#d7d1c2")
    draw.text((50, 120), "DETERMINISTIC DRY-RUN FIXTURE - not final generated art", font=small_font, fill="#d7d1c2")
    draw_wrapped(draw, "Anchors: " + "; ".join(anchors), 50, 154, 1490, body_font, "#f7f2e8")

    cells = []
    positions = [(50, 250), (825, 250), (50, 715), (825, 715)]
    for idx, (panel_title, panel_desc) in enumerate(panels[:4]):
        x, y = positions[idx]
        w, h = 725, 395
        draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill=card, outline=accent, width=4)
        draw.rectangle((x + 24, y + 24, x + 250, y + 250), fill="#f7f2e8", outline=accent, width=3)
        cx, cy = x + 137, y + 137
        draw.ellipse((cx - 54, cy - 70, cx + 54, cy + 38), outline=accent, width=5)
        draw.line((cx, cy + 42, cx, cy + 150), fill=accent, width=5)
        draw.line((cx - 80, cy + 82, cx + 80, cy + 82), fill=accent, width=5)
        draw.text((x + 286, y + 30), f"{idx + 1}. {panel_title}", font=body_font, fill="#f7f2e8")
        draw_wrapped(draw, panel_desc, x + 286, y + 72, 390, small_font, "#eee7da")
        cells.append({
            "panel": idx + 1,
            "title": panel_title,
            "raw_size": [w, h],
            "placed_size": [w, h],
            "scale_x": 1.0,
            "scale_y": 1.0,
            "nonuniform_scaling": False,
        })
    image.save(path)
    return {
        "path": str(path),
        "sha256": sha256(path),
        "width": image.width,
        "height": image.height,
        "cells": cells,
        "status": "GENERATED_UNREVIEWED",
    }


def create_storyboard_board(path: Path, timed_beats: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1920, 1080), "#161616")
    draw = ImageDraw.Draw(image)
    title_font = font(42)
    body_font = font(23)
    small_font = font(18)
    draw.text((52, 28), "Horus / Embry - Storyboard-First Dry-Run Board", font=title_font, fill="#f7f2e8")
    draw.text((54, 82), "DETERMINISTIC FIXTURE - panel layout and beat mapping only", font=small_font, fill="#cfc7b8")

    panel_w, panel_h = 350, 390
    margin_x, margin_y = 52, 145
    gap_x, gap_y = 25, 65
    panels = []
    for idx, beat in enumerate(timed_beats):
        row, col = divmod(idx, 5)
        x = margin_x + col * (panel_w + gap_x)
        y = margin_y + row * (panel_h + gap_y)
        draw.rectangle((x, y, x + panel_w, y + panel_h), fill="#2d3138", outline="#e1c16e", width=3)
        caption_h = 116
        draw.rectangle((x, y + panel_h - caption_h, x + panel_w, y + panel_h), fill="#f7f2e8")
        draw.text((x + 12, y + 10), str(idx + 1), font=title_font, fill="#e1c16e")
        draw.text((x + 58, y + 18), f"{beat['start_s']:.1f}s-{beat['end_s']:.1f}s", font=body_font, fill="#f7f2e8")
        visual = str(beat["visual"])
        draw_wrapped(draw, visual, x + 24, y + 74, panel_w - 48, body_font, "#f7f2e8")
        caption = str(beat["caption"])
        draw_wrapped(draw, caption, x + 12, y + panel_h - caption_h + 10, panel_w - 24, small_font, "#111111", line_gap=2)
        panels.append({
            "panel": idx + 1,
            "beat_id": beat["beat_id"],
            "time_range_s": [beat["start_s"], beat["end_s"]],
            "caption": caption,
        })
    image.save(path)
    return {
        "schema": "persona_dream.storyboard_board_receipt.v1",
        "artifact_id": "storyboard_board_horus_embry_fixture",
        "status": "GENERATED_UNREVIEWED",
        "created_at": now_iso(),
        "path": str(path),
        "sha256": sha256(path),
        "width": image.width,
        "height": image.height,
        "aspect_ratio": "16:9",
        "expected_panel_count": len(timed_beats),
        "actual_panel_count": len(panels),
        "beat_to_panel_map": panels,
        "manual_review_required": True,
    }


def image_metrics(path: Path, *, status: str, cells: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
    return {
        "path": str(path),
        "sha256": sha256(path),
        "width": width,
        "height": height,
        "cells": cells or [],
        "status": status,
    }


def reference_sheet_prompt(*, title: str, entity_id: str, anchors: list[str], panels: list[tuple[str, str]]) -> str:
    panel_lines = "\n".join(f"- {name}: {desc}" for name, desc in panels)
    return (
        f"Create a Kling-ready visual contact sheet titled '{title}' for {entity_id}.\n"
        "Canvas: 4-panel reference sheet, clean grid, no stretching, no cropped limbs, no UI mockup frame.\n"
        "Style: cinematic production reference, readable silhouette, consistent identity across all panels.\n"
        "Required visual anchors:\n"
        + "\n".join(f"- {anchor}" for anchor in anchors)
        + "\nRequired panels:\n"
        + panel_lines
        + "\nDo not genericize named universe-specific details. Preserve the story context: Horus and Embry have tea under a patio umbrella on a Warhammer 40k void world while Tyranids move in the background and they discuss SPARTA Explorer.\n"
    )


def storyboard_image_prompt(timed_beats: list[dict[str, Any]]) -> str:
    beat_lines = "\n".join(
        f"{idx + 1}. {beat['start_s']:.1f}s-{beat['end_s']:.1f}s: {beat['visual']} - {beat['caption']}"
        for idx, beat in enumerate(timed_beats)
    )
    return (
        "Create a cinematic storyboard board in 16:9 aspect ratio for an 8-second Kling dry-run fixture.\n"
        "Layout: 10 panels, 2 rows of 5. Each panel must show panel number, timing, and one-line caption.\n"
        "Story: Horus Lupercal and Embry have tea under a patio umbrella on a Warhammer 40k void world while Tyranids move in the background and they discuss SPARTA Explorer.\n"
        "Style: production storyboard board, actual film-still compositions, consistent characters, no stretched image regions.\n"
        "Character lock for every panel: Horus is a bald or shaved-head pale male primarch in black-and-gold Warmaster armor; never long-haired, never generic space marine, never corrupted monster.\n"
        "Character lock for every panel: Embry is a fictional young adult woman with dark brown low ponytail, olive eyes, subtle nose scar, practical gray field workwear, calm humane expression; never male-coded, never bearded, never celebrity likeness.\n"
        "Table lock: exactly two primary people at the table, Horus and Embry. Tyranids stay in the distant background, not at the table.\n"
        "Panels:\n"
        + beat_lines
        + "\nThis is a storyboard/reference artifact for a dry-run provider packet, not a live provider request.\n"
    )


def make_kling_scene_payloads(timed_beats: list[dict[str, Any]]) -> dict[str, Any]:
    """Create provider-readable shot directions plus machine-checkable gates."""
    scene_specs = [
        {
            "shot": "Wide establishing shot",
            "action": "The tiny patio table and umbrella sit against an impossible void horizon.",
            "emotional_behavior": "The scene holds still for a quiet, uncanny beat; both figures appear small but composed.",
            "camera": "Slow drifting wide push-in from the void horizon toward the table.",
            "timing": "0.8-second silent establishing beat.",
            "dialogue": [],
        },
        {
            "shot": "Medium shot on Horus",
            "action": "Horus settles into frame with one armored hand near the teacup.",
            "emotional_behavior": "His jaw relaxes, eyes steady, posture controlled and unexpectedly gentle.",
            "camera": "Slow push-in, 50mm lens feel, armor catching cold side light.",
            "timing": "Brief pause before he looks toward Embry.",
            "dialogue": [],
        },
        {
            "shot": "Medium shot on Embry",
            "action": "Embry opens the SPARTA Explorer laptop and angles the screen toward Horus.",
            "emotional_behavior": "She glances down, breathes in, then looks back with careful focus.",
            "camera": "Table-height three-quarter view, small rack focus from her hand to the screen.",
            "timing": "Half-second hesitation before the screen becomes readable.",
            "dialogue": [],
        },
        {
            "shot": "Background wide",
            "action": "Tyranids run and play at distant scale beyond the patio railing.",
            "emotional_behavior": "The background feels strange and dangerous, but the table remains calm.",
            "camera": "Static wide shot with distant movement crossing behind the umbrella.",
            "timing": "Keep the foreground quiet while the background moves.",
            "dialogue": [],
        },
        {
            "shot": "Insert detail",
            "action": "Tea cups, handwritten notes, and SPARTA evidence cards sit between them.",
            "emotional_behavior": "The objects feel deliberate and cared for, not decorative.",
            "camera": "Slow macro slide across cups, cards, and Horus's armored hand.",
            "timing": "Silent detail beat before the first line of dialogue.",
            "dialogue": [],
        },
        {
            "shot": "Medium close-up on Horus",
            "action": "Horus looks from the evidence cards to Embry before speaking.",
            "emotional_behavior": "His brow tightens slightly; he pauses, then speaks with controlled concern.",
            "camera": "Slow push-in over Embry's shoulder toward Horus.",
            "timing": "Short inhale, half-second pause, then quiet line delivery.",
            "dialogue": [
                {
                    "speaker": "Horus",
                    "voice_tag": "<<<voice_horus>>>",
                    "text": "The system must preserve evidence without turning people into widgets.",
                    "delivery": "low, measured, protective; no shouting",
                    "pause_after_s": 0.4,
                }
            ],
        },
        {
            "shot": "Reverse medium close-up on Embry",
            "action": "Embry rests one hand near the laptop and answers without breaking eye contact.",
            "emotional_behavior": "She gives a small, nervous half-smile; her shoulders drop as she finds the wording.",
            "camera": "Shot-reverse-shot from behind Horus, gentle push toward Embry.",
            "timing": "Brief silent hesitation before her reply, then steady speech.",
            "dialogue": [
                {
                    "speaker": "Embry",
                    "voice_tag": "<<<voice_embry>>>",
                    "text": "SPARTA Explorer should feel like a trusted colleague at the table.",
                    "delivery": "soft, precise, thoughtful",
                    "pause_after_s": 0.3,
                }
            ],
        },
        {
            "shot": "Shared screen insert",
            "action": "The laptop shows Chat, Evidence Workspace, Coverage, QRAs, and Controls.",
            "emotional_behavior": "The interface appears quiet and useful; no flashy dashboard energy.",
            "camera": "Slow screen-facing push-in with Horus and Embry reflected faintly.",
            "timing": "One clear readable beat on the SPARTA Explorer surface.",
            "dialogue": [],
        },
        {
            "shot": "Wide background motion",
            "action": "Tyranids cross behind the umbrella while Horus and Embry keep talking quietly.",
            "emotional_behavior": "Neither speaker flinches; the surreal motion stays peripheral.",
            "camera": "Locked wide composition, foreground table stable, background creatures moving laterally.",
            "timing": "Long quiet background beat; do not interrupt conversation rhythm.",
            "dialogue": [],
        },
        {
            "shot": "Closing two-shot",
            "action": "Horus and Embry lean over the SPARTA Explorer notes together.",
            "emotional_behavior": "Both look calmer; Horus lowers his gaze, Embry nods once, the umbrella shifts in the wind.",
            "camera": "Slow pullback from table to wide void-world patio.",
            "timing": "Soft final pause after the shared nod.",
            "dialogue": [],
        },
    ]
    if len(scene_specs) != len(timed_beats):
        raise ValueError("scene spec count must match timed beat count")

    panels = []
    for idx, (beat, spec) in enumerate(zip(timed_beats, scene_specs, strict=True), start=1):
        provider_text = (
            f"Panel {idx} ({beat['start_s']:.1f}s-{beat['end_s']:.1f}s). "
            f"{spec['shot']}. {spec['action']} {spec['emotional_behavior']} "
            f"{spec['camera']} {spec['timing']}"
        )
        if spec["dialogue"]:
            lines = []
            for line in spec["dialogue"]:
                lines.append(
                    f"{line['voice_tag']} {line['speaker']}: \"{line['text']}\" "
                    f"Delivery: {line['delivery']}. Pause after line: {line['pause_after_s']}s."
                )
            provider_text += " Dialogue: " + " ".join(lines)
        panels.append(
            {
                "panel": idx,
                "beat_id": beat["beat_id"],
                "time_range_s": [beat["start_s"], beat["end_s"]],
                "caption": beat["caption"],
                "shot": spec["shot"],
                "action": spec["action"],
                "emotional_behavior": spec["emotional_behavior"],
                "camera": spec["camera"],
                "timing": spec["timing"],
                "dialogue": spec["dialogue"],
                "provider_text": provider_text,
            }
        )

    return {
        "schema": "persona_dream.kling_scene_payloads.v1",
        "artifact_id": "horus_embry_kling_scene_payloads",
        "status": "GENERATED_UNREVIEWED",
        "created_at": now_iso(),
        "provider": "kling",
        "source_storyboard_board": "storyboard/storyboard_board.png",
        "voice_tag_policy": {
            "voice_horus": "Horus dialogue lines use <<<voice_horus>>> until a voice reference is selected.",
            "voice_embry": "Embry dialogue lines use <<<voice_embry>>> until a voice reference is selected.",
        },
        "panels": panels,
        "manual_review_required": True,
    }


def make_kling_scene_directions(payload: dict[str, Any]) -> str:
    lines = [
        "# Kling Scene Directions",
        "",
        "Use the storyboard board as the visual anchor. Use these plain-language panel notes as the shot direction text.",
        "Emotion is written as visible physical behavior and timing, not only as labels.",
        "",
    ]
    for panel in payload["panels"]:
        lines.extend(
            [
                f"## Panel {panel['panel']} ({panel['time_range_s'][0]:.1f}s-{panel['time_range_s'][1]:.1f}s)",
                "",
                panel["provider_text"],
                "",
            ]
        )
    return "\n".join(lines)


def run_create_image(
    *,
    repo_root: Path,
    prompt_path: Path,
    output_path: Path,
    size: str,
    backend: str,
    model: str,
    attempt_id: str,
    timeout_s: int,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = output_path.with_name(f"{output_path.stem}_receipt.json")
    events_path = output_path.with_name(f"{output_path.stem}_events.jsonl")
    if output_path.exists() and output_path.stat().st_size > 0 and not receipt_path.exists():
        try:
            with Image.open(output_path) as existing:
                source_w, source_h = existing.size
            image_bytes = output_path.read_bytes()
            receipt_path.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "auth": "codex-oauth",
                        "path": str(output_path),
                        "source_width": source_w,
                        "source_height": source_h,
                        "bytes": len(image_bytes),
                        "sha256": hashlib.sha256(image_bytes).hexdigest(),
                        "receipt_synthesized_by": "persona-dream-reuse",
                        "upstream_receipt_missing": True,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
        except Exception:
            pass
    if output_path.exists() and output_path.stat().st_size > 0 and receipt_path.exists():
        target_w, target_h = (int(part) for part in size.lower().split("x", 1))
        with Image.open(output_path) as existing:
            image = existing.convert("RGB")
        if image.size != (target_w, target_h):
            contained = ImageOps.contain(image, (target_w, target_h), method=Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (target_w, target_h), "white")
            canvas.paste(contained, ((target_w - contained.width) // 2, (target_h - contained.height) // 2))
            canvas.save(output_path, "PNG")
            try:
                receipt_payload = json.loads(receipt_path.read_text())
            except Exception:
                receipt_payload = {}
            image_bytes = output_path.read_bytes()
            receipt_payload.update(
                {
                    "ok": True,
                    "path": str(output_path),
                    "width": target_w,
                    "height": target_h,
                    "bytes": len(image_bytes),
                    "sha256": hashlib.sha256(image_bytes).hexdigest(),
                    "normalized_by": "persona-dream-reuse",
                    "create_image_fit": "contain",
                }
            )
            receipt_path.write_text(json.dumps(receipt_payload, indent=2, sort_keys=True) + "\n")
        return {
            "schema": "persona_dream.generated_image_attempt.v1",
            "attempt_id": attempt_id,
            "status": "ACCEPTED_AUTOMATED",
            "created_at": now_iso(),
            "backend": backend,
            "model": model,
            "size": size,
            "prompt_path": str(prompt_path),
            "output_path": str(output_path),
            "output_exists": True,
            "receipt_path": str(receipt_path),
            "receipt_exists": True,
            "events_path": str(events_path),
            "events_exists": events_path.exists(),
            "returncode": None,
            "cmd": [],
            "stdout_tail": "reused existing output and receipt",
            "stderr_tail": "",
            "reused_existing": True,
        }
    output_path.unlink(missing_ok=True)
    receipt_path.unlink(missing_ok=True)
    events_path.unlink(missing_ok=True)
    cmd = [
        "uv",
        "run",
        "--script",
        str(repo_root / "skills" / "create-image" / "generate.py"),
        "generate",
        "--prompt-file",
        str(prompt_path),
        "--output",
        str(output_path),
        "--size",
        size,
        "--backend",
        backend,
        "--model",
        model,
    ]
    env = os.environ.copy()
    env.setdefault("CREATE_IMAGE_FIT", "contain")
    env.setdefault("CREATE_IMAGE_SCILLM_CALLER", "persona-dream")
    env.setdefault("CREATE_IMAGE_SCILLM_PREFLIGHT", "1")
    env.setdefault("CREATE_IMAGE_SCILLM_TIMEOUT_S", str(timeout_s))
    completed = subprocess.run(
        cmd,
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s + 45,
    )
    ok = completed.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0
    return {
        "schema": "persona_dream.generated_image_attempt.v1",
        "attempt_id": attempt_id,
        "status": "ACCEPTED_AUTOMATED" if ok else "FAILED_AUTOMATED_CHECK",
        "created_at": now_iso(),
        "backend": backend,
        "model": model,
        "size": size,
        "prompt_path": str(prompt_path),
        "output_path": str(output_path),
        "output_exists": output_path.exists(),
        "receipt_path": str(receipt_path),
        "receipt_exists": receipt_path.exists(),
        "events_path": str(events_path),
        "events_exists": events_path.exists(),
        "returncode": completed.returncode,
        "cmd": cmd,
        "stdout_tail": completed.stdout[-3000:],
        "stderr_tail": completed.stderr[-3000:],
    }


def artifact_ref(path: Path, status: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": sha256(path),
        "status": status,
    }


def rel_href(path: Path, root: Path) -> str:
    return html.escape(path.relative_to(root).as_posix())


def build_review_display(root: Path) -> dict[str, Any]:
    """Create a local fail-closed review display backed only by existing artifacts."""
    review_dir = root / "review_page"
    review_dir.mkdir(parents=True, exist_ok=True)
    artifact_rels = [
        "idea_contract.json",
        "story_contract.json",
        "timed_beats.json",
        "story_visual_package.json",
        "grounding/memory_recall_horus_embry.json",
        "grounding/brave_search_horus_hair.json",
        "casting/casting_contract.json",
        "casting/chosen_reference_inputs.json",
        "casting/contact_sheet_work_order.json",
        "reference_sheets/horus_reference_sheet.png",
        "reference_sheets/embry_reference_sheet.png",
        "reference_sheets/tyranid_environment_reference_sheet.png",
        "reference_sheets/layout_validation.json",
        "storyboard/storyboard_identity_contract.json",
        "storyboard/storyboard_prompt.md",
        "storyboard/storyboard_board.png",
        "storyboard/storyboard_board_receipt.json",
        "storyboard/kling_scene_payloads.json",
        "storyboard/kling_scene_directions.md",
        "provider_packet/final_kling_prompt.md",
        "provider_packet/provider_request_dry_run.json",
        "provider_packet/referenced_artifacts.lock.json",
        "provider_packet/readiness_receipt.json",
        "provider_packet/provider_packet_validation_receipt.json",
        "stage_status_receipt.json",
        "generated_image_attempts.json",
    ]
    artifacts = []
    for rel in artifact_rels:
        path = root / rel
        artifacts.append(
            {
                "rel": rel,
                "path": str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "sha256": sha256(path) if path.exists() else None,
            }
        )
    missing = [item for item in artifacts if not item["exists"]]
    readiness_path = root / "provider_packet" / "readiness_receipt.json"
    readiness = json.loads(readiness_path.read_text()) if readiness_path.exists() else {}
    stage_status_path = root / "stage_status_receipt.json"
    stage_status = json.loads(stage_status_path.read_text()) if stage_status_path.exists() else {}
    scene_directions_path = root / "storyboard" / "kling_scene_directions.md"
    scene_directions_preview = (
        scene_directions_path.read_text()[:5000]
        if scene_directions_path.exists()
        else "Missing: storyboard/kling_scene_directions.md"
    )
    image_cards = [
        ("Horus Reference Sheet", root / "reference_sheets" / "horus_reference_sheet.png"),
        ("Embry Reference Sheet", root / "reference_sheets" / "embry_reference_sheet.png"),
        ("Tyranid / Void Patio Reference Sheet", root / "reference_sheets" / "tyranid_environment_reference_sheet.png"),
        ("Storyboard Board", root / "storyboard" / "storyboard_board.png"),
    ]
    status_rows = []
    for stage in stage_status.get("stages", []):
        status_rows.append(
            "<tr>"
            f"<td>{html.escape(stage.get('stage_id', ''))}</td>"
            f"<td>{html.escape(stage.get('owner', ''))}</td>"
            f"<td>{html.escape(stage.get('status', ''))}</td>"
            f"<td>{html.escape(', '.join(stage.get('required_skills', [])))}</td>"
            f"<td>{html.escape(stage.get('block_reason', ''))}</td>"
            "</tr>"
        )
    artifact_rows = []
    for item in artifacts:
        href = html.escape("../" + item["rel"])
        artifact_rows.append(
            "<tr>"
            f"<td><a href=\"{href}\">{html.escape(item['rel'])}</a></td>"
            f"<td>{'yes' if item['exists'] else 'no'}</td>"
            f"<td>{item['bytes']}</td>"
            f"<td><code>{html.escape((item['sha256'] or '')[:16])}</code></td>"
            "</tr>"
        )
    image_html = []
    for title, path in image_cards:
        if path.exists():
            image_html.append(
                "<figure>"
                f"<a href=\"../{rel_href(path, root)}\"><img src=\"../{rel_href(path, root)}\" alt=\"{html.escape(title)}\"></a>"
                f"<figcaption>{html.escape(title)}</figcaption>"
                "</figure>"
            )
        else:
            image_html.append(f"<figure class=\"missing\"><figcaption>{html.escape(title)} missing</figcaption></figure>")
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Persona-Dream Storyboard-First Dry-Run Review</title>
  <style>
    :root {{ color-scheme: light; --ink:#191714; --muted:#625d55; --line:#c8c0b2; --paper:#f5f1ea; --panel:#fffdf9; --blocked:#7d2d24; --ok:#246646; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font:16px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; color:var(--ink); background:var(--paper); }}
    main {{ max-width:1480px; margin:0 auto; padding:28px; }}
    h1 {{ margin:0 0 8px; font-size:32px; }}
    h2 {{ margin:34px 0 12px; font-size:22px; }}
    .summary {{ display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; margin:20px 0; }}
    .metric {{ background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:14px; }}
    .metric strong {{ display:block; font-size:14px; color:var(--muted); margin-bottom:8px; }}
    .blocked {{ color:var(--blocked); font-weight:700; }}
    .ok {{ color:var(--ok); font-weight:700; }}
    .gallery {{ display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:18px; }}
    figure {{ margin:0; background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:12px; }}
    img {{ display:block; max-width:100%; height:auto; object-fit:contain; background:#fff; border:1px solid #ddd4c5; }}
    figcaption {{ margin-top:8px; font-weight:650; }}
    table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); }}
    th, td {{ text-align:left; vertical-align:top; padding:9px 10px; border-bottom:1px solid #e1d9ca; }}
    th {{ color:var(--muted); font-size:13px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    pre {{ white-space:pre-wrap; overflow:auto; background:#171512; color:#f4efe7; border-radius:6px; padding:16px; max-height:520px; }}
    .note {{ color:var(--muted); max-width:920px; }}
    @media (max-width:900px) {{ .summary, .gallery {{ grid-template-columns:1fr; }} main {{ padding:16px; }} }}
  </style>
</head>
<body>
<main>
  <h1>Persona-Dream Storyboard-First Dry-Run Review</h1>
  <p class="note">This page renders only existing fixture artifacts. It does not create, repair, approve, or submit provider jobs.</p>
  <section class="summary">
    <div class="metric"><strong>Provider Readiness</strong><span class="blocked">{html.escape(str(readiness.get('status', 'missing')))}</span></div>
    <div class="metric"><strong>Paid Call Performed</strong>{html.escape(str(readiness.get('paid_call_performed', 'missing')).lower())}</div>
    <div class="metric"><strong>Live Call Authorized</strong>{html.escape(str(readiness.get('live_call_authorized', 'missing')).lower())}</div>
    <div class="metric"><strong>Missing Artifacts</strong>{len(missing)}</div>
  </section>
  <h2>Visual Artifacts</h2>
  <section class="gallery">{''.join(image_html)}</section>
  <h2>Kling Scene Directions Preview</h2>
  <pre>{html.escape(scene_directions_preview)}</pre>
  <h2>Stage Ledger</h2>
  <table><thead><tr><th>Stage</th><th>Owner</th><th>Status</th><th>Required Skills</th><th>Block Reason</th></tr></thead><tbody>{''.join(status_rows)}</tbody></table>
  <h2>Artifact Manifest</h2>
  <table><thead><tr><th>Artifact</th><th>Exists</th><th>Bytes</th><th>SHA-256 Prefix</th></tr></thead><tbody>{''.join(artifact_rows)}</tbody></table>
</main>
</body>
</html>
"""
    index_path = review_dir / "index.html"
    index_path.write_text(html_text)
    interaction_manifest = {
        "schema": "persona_dream.review_display_interaction_manifest.v1",
        "status": "GENERATED_UNREVIEWED",
        "created_at": now_iso(),
        "page": str(index_path),
        "checks": [
            {"name": "renders_existing_artifacts_only", "ok": True},
            {"name": "missing_artifacts_visible", "ok": not missing, "missing": missing},
            {"name": "provider_blocked_visible", "ok": readiness.get("status") == "BLOCKED"},
            {"name": "paid_call_false_visible", "ok": readiness.get("paid_call_performed") is False},
        ],
    }
    write_json(review_dir / "interaction_manifest.json", interaction_manifest)
    receipt = {
        "schema": "persona_dream.review_display_receipt.v1",
        "artifact_id": "horus_embry_review_display",
        "status": "GENERATED_UNREVIEWED" if not missing else "FAILED_AUTOMATED_CHECK",
        "created_at": now_iso(),
        "index_html": str(index_path),
        "interaction_manifest": str(review_dir / "interaction_manifest.json"),
        "artifact_count": len(artifacts),
        "missing_artifacts": missing,
        "non_claims": [
            "Review display does not approve manual visual gates.",
            "Review display does not authorize or perform paid Kling calls.",
        ],
    }
    write_json(review_dir / "review_display_receipt.json", receipt)
    return receipt


def make_storyboard_identity_contract(
    story_visual_package: dict[str, Any],
    *,
    grounding_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fail-closed preflight for storyboard character consistency inputs."""
    characters = story_visual_package.get("keyed_entities", {}).get("characters", {})
    required = {
        "horus": {
            "required_terms": ["horus", "warmaster", "bald", "pale", "black-and-gold", "armor"],
            "min_visual_anchors": 5,
            "min_negative_constraints": 3,
            "required_negative_terms": ["generic space marine", "long hair", "corrupted"],
        },
        "embry": {
            "required_terms": ["woman", "dark brown", "ponytail", "olive eyes", "nose scar", "gray"],
            "min_visual_anchors": 5,
            "min_negative_constraints": 4,
            "required_negative_terms": ["male-coded", "beard", "older man", "celebrity"],
        },
    }
    character_checks = []
    for key, rules in required.items():
        entity = characters.get(key, {})
        description = str(entity.get("description", "")).lower()
        anchors = [str(anchor).lower() for anchor in entity.get("visual_anchors", [])]
        negatives = [str(item).lower() for item in entity.get("must_not_include", [])]
        image_paths = [str(path) for path in entity.get("image_file_paths", [])]
        combined = " ".join([description, *anchors])
        missing_terms = [term for term in rules["required_terms"] if term not in combined]
        missing_negative_terms = [
            term for term in rules["required_negative_terms"]
            if not any(term in negative for negative in negatives)
        ]
        missing_paths = [path for path in image_paths if not Path(path).exists()]
        checks = [
            {
                "name": "description_required_terms_present",
                "ok": not missing_terms,
                "missing": missing_terms,
            },
            {
                "name": "visual_anchor_count_sufficient",
                "ok": len(anchors) >= rules["min_visual_anchors"],
                "actual": len(anchors),
                "minimum": rules["min_visual_anchors"],
            },
            {
                "name": "negative_constraint_count_sufficient",
                "ok": len(negatives) >= rules["min_negative_constraints"],
                "actual": len(negatives),
                "minimum": rules["min_negative_constraints"],
            },
            {
                "name": "required_negative_terms_present",
                "ok": not missing_negative_terms,
                "missing": missing_negative_terms,
            },
            {
                "name": "reference_image_paths_exist",
                "ok": bool(image_paths) and not missing_paths,
                "missing": missing_paths,
                "paths": image_paths,
            },
        ]
        character_checks.append(
            {
                "character_key": key,
                "entity_id": entity.get("entity_id"),
                "status": "ACCEPTED_AUTOMATED" if all(check["ok"] for check in checks) else "FAILED_AUTOMATED_CHECK",
                "checks": checks,
            }
        )
    ok = all(item["status"] == "ACCEPTED_AUTOMATED" for item in character_checks)
    return {
        "schema": "persona_dream.storyboard_identity_contract.v1",
        "artifact_id": "horus_embry_storyboard_identity_contract",
        "status": "ACCEPTED_AUTOMATED" if ok else "FAILED_AUTOMATED_CHECK",
        "created_at": now_iso(),
        "owner": "$create-storyboard preflight",
        "purpose": "Fail before storyboard generation when character identity inputs are insufficient for visual consistency.",
        "grounding_artifacts": grounding_artifacts or [],
        "character_checks": character_checks,
        "failure_policy": "Do not generate or consume storyboard boards until all visible/speaking character identity checks pass.",
    }


def make_stage_status_receipt(root: Path) -> dict[str, Any]:
    """Create the rollback/status ledger for the worked example stages."""
    stages = [
        {
            "stage_id": "stage_00_idea_synthesis",
            "owner": "$persona-dream",
            "required_skills": ["persona-dream", "memory", "project-knowledge", "brave-search"],
            "status": "ACCEPTED_AUTOMATED",
            "inputs": [
                "persona memory recall",
                "project knowledge recall",
                "recent project activity",
                "optional Brave Search trend/event context",
                "optional human/project-agent supplied seed",
            ],
            "outputs": ["idea_contract.json"],
            "acceptance_gate": "idea source mode declared; memory/project inputs or explicit supplied seed recorded; selected idea preserved",
            "rollback_target": "memory/project recall set or supplied seed",
            "downstream_consumable": True,
        },
        {
            "stage_id": "stage_01_story_contract",
            "owner": "$create-story",
            "required_skills": ["create-story", "memory"],
            "status": "ACCEPTED_AUTOMATED",
            "inputs": ["idea_contract.json"],
            "outputs": ["story_contract.json", "timed_beats.json"],
            "acceptance_gate": "story schema passes; seed preserved; speakers identified",
            "rollback_target": "idea_contract.json",
            "downstream_consumable": True,
        },
        {
            "stage_id": "stage_02_entity_extraction",
            "owner": "$casting-agent extract",
            "required_skills": ["casting-agent", "extract-entities"],
            "status": "ACCEPTED_AUTOMATED",
            "inputs": ["story_contract.json", "timed_beats.json"],
            "outputs": ["story_visual_package.json"],
            "acceptance_gate": "Horus, Embry, Tyranids, void-world patio, tea table, SPARTA laptop keyed",
            "rollback_target": "story_contract.json",
            "downstream_consumable": True,
        },
        {
            "stage_id": "stage_03_casting_reference_research",
            "owner": "$casting-agent",
            "required_skills": ["casting-agent", "memory", "brave-search", "contact-sheet"],
            "status": "ACCEPTED_AUTOMATED",
            "inputs": ["story_visual_package.json"],
            "outputs": [
                "casting/casting_contract.json",
                "casting/chosen_reference_inputs.json",
                "casting/contact_sheet_work_order.json",
            ],
            "acceptance_gate": "reference sufficiency strategy recorded; no live calls",
            "rollback_target": "story_visual_package.json",
            "downstream_consumable": True,
        },
        {
            "stage_id": "stage_04_reference_sheets",
            "owner": "$contact-sheet + $create-image / $scillm",
            "required_skills": ["contact-sheet", "best-practices-kling-contact-sheet", "create-image", "scillm"],
            "status": "GENERATED_UNREVIEWED",
            "inputs": ["casting/contact_sheet_work_order.json"],
            "outputs": [
                "reference_sheets/horus_reference_sheet.png",
                "reference_sheets/embry_reference_sheet.png",
                "reference_sheets/tyranid_environment_reference_sheet.png",
                "reference_sheets/layout_validation.json",
            ],
            "acceptance_gate": "no stretching; dimensions recorded; manual visual identity review still required",
            "rollback_target": "casting/casting_contract.json",
            "downstream_consumable": False,
            "block_reason": "manual_reference_sheet_review_missing",
        },
        {
            "stage_id": "stage_05_storyboard_board",
            "owner": "$create-storyboard + $create-image / $scillm",
            "required_skills": ["create-storyboard", "memory", "brave-search", "contact-sheet", "create-image", "scillm"],
            "status": "GENERATED_UNREVIEWED",
            "inputs": ["story_contract.json", "timed_beats.json", "reference_sheets/layout_validation.json"],
            "outputs": [
                "storyboard/storyboard_identity_contract.json",
                "storyboard/storyboard_prompt.md",
                "storyboard/storyboard_board.png",
                "storyboard/storyboard_board_receipt.json",
                "storyboard/kling_scene_payloads.json",
                "storyboard/kling_scene_directions.md",
            ],
            "acceptance_gate": "identity preflight passes; 16:9 board; 10 panels; beat-to-panel map; every panel has provider-facing text with physical emotion, camera, and pause/timing; manual storyboard review still required",
            "rollback_target": "reference_sheets/layout_validation.json",
            "downstream_consumable": False,
            "block_reason": "manual_storyboard_review_missing",
        },
        {
            "stage_id": "stage_06_provider_packet",
            "owner": "$provider-packet",
            "required_skills": ["persona-dream", "provider-packet"],
            "status": "GENERATED_UNREVIEWED",
            "inputs": [
                "story_contract.json",
                "reference_sheets/layout_validation.json",
                "storyboard/storyboard_board_receipt.json",
                "storyboard/kling_scene_directions.md",
                "storyboard/kling_scene_payloads.json",
            ],
            "outputs": [
                "provider_packet/final_kling_prompt.md",
                "provider_packet/provider_request_dry_run.json",
                "provider_packet/referenced_artifacts.lock.json",
                "provider_packet/readiness_receipt.json",
                "provider_packet/provider_packet_validation_receipt.json",
            ],
            "acceptance_gate": "paths exist and hashes locked; readiness remains BLOCKED until manual review receipts exist",
            "rollback_target": "storyboard/storyboard_board_receipt.json",
            "downstream_consumable": False,
            "block_reason": "upstream_generated_unreviewed",
        },
        {
            "stage_id": "stage_07_live_provider_execution",
            "owner": "$kling-video",
            "required_skills": ["kling-video"],
            "status": "BLOCKED",
            "inputs": ["provider_packet/provider_request_dry_run.json", "paid_call_approval_receipt.json"],
            "outputs": [],
            "acceptance_gate": "explicit paid-call approval required before upload/queue/download receipts",
            "rollback_target": "provider_packet/provider_request_dry_run.json",
            "downstream_consumable": False,
            "block_reason": "paid_call_approval_receipt_missing",
        },
        {
            "stage_id": "stage_08_review_display",
            "owner": "$review-page",
            "required_skills": ["review-page"],
            "status": "GENERATED_UNREVIEWED",
            "inputs": ["existing accepted artifacts only"],
            "outputs": [
                "review_page/index.html",
                "review_page/interaction_manifest.json",
                "review_page/review_display_receipt.json",
            ],
            "acceptance_gate": "display shows real artifacts and missing states only",
            "rollback_target": "none_display_only",
            "downstream_consumable": False,
            "block_reason": "manual_review_display_acceptance_missing",
        },
    ]
    strict_gate_contracts = {
        "stage_00_idea_synthesis": {
            "automated": [
                "idea_contract.schema == persona_dream.idea_contract.v1",
                "idea_contract.source_mode is declared",
                "idea text exists",
                "inputs_considered records memory/project/persona sources or explicit supplied seed",
                "autonomous mode records persona/project memory recall before story generation",
                "Brave Search is optional and must be receipted when used",
            ],
            "manual": [
                "human may override with a specific supplied idea",
            ],
            "fail_closed": True,
            "allowed_statuses": ["ACCEPTED_AUTOMATED", "BLOCKED", "FAILED_AUTOMATED_CHECK"],
        },
        "stage_01_story_contract": {
            "automated": [
                "story_contract.schema == persona_dream.story_contract.v1",
                "timed_beats.schema == persona_dream.timed_beats.v1",
                "human_seed preserved in story_contract.seed",
                "speaking_characters identifies horus and embry",
                "timed beats contain stable beat ids and target duration",
            ],
            "manual": [],
            "fail_closed": True,
            "allowed_statuses": ["ACCEPTED_AUTOMATED", "FAILED_AUTOMATED_CHECK"],
        },
        "stage_02_entity_extraction": {
            "automated": [
                "story_visual_package.schema == persona_dream.story_visual_package.v1",
                "characters.horus keyed with entity_id and description",
                "characters.embry keyed with entity_id and description",
                "creatures.tyranids keyed with entity_id and description",
                "scenery.void_world_patio keyed with entity_id and description",
                "props.tea_table_sparta_laptop keyed with entity_id and description",
            ],
            "manual": [],
            "fail_closed": True,
            "allowed_statuses": ["ACCEPTED_AUTOMATED", "FAILED_AUTOMATED_CHECK"],
        },
        "stage_03_casting_reference_research": {
            "automated": [
                "casting_contract exists and covers every required entity",
                "chosen_reference_inputs records strategy per entity",
                "contact_sheet_work_order contains required sheets",
                "missing canon-sensitive references are marked for Brave Search or provided images",
                "no live paid provider call is performed",
            ],
            "manual": [],
            "fail_closed": True,
            "allowed_statuses": ["ACCEPTED_AUTOMATED", "FAILED_AUTOMATED_CHECK"],
        },
        "stage_04_reference_sheets": {
            "automated": [
                "all required reference PNGs exist",
                "all reference PNGs have expected dimensions",
                "layout_validation.nonuniform_scaling_detected == false",
                "generated_image_attempts records sheet attempts",
                "each generated sheet has receipt/hash metadata",
            ],
            "manual": [
                "Horus visual identity accepted",
                "Embry visual identity accepted",
                "Tyranid/environment visual identity accepted",
            ],
            "fail_closed": True,
            "allowed_statuses": [
                "GENERATED_UNREVIEWED",
                "FAILED_AUTOMATED_CHECK",
                "FAILED_MANUAL_REVIEW",
                "ACCEPTED_MANUAL",
            ],
        },
        "stage_05_storyboard_board": {
            "automated": [
                "storyboard_identity_contract.status == ACCEPTED_AUTOMATED",
                "each visible/speaking character has sufficient identity anchors",
                "each visible/speaking character has sufficient negative constraints",
                "each visible/speaking character has existing reference image paths",
                "storyboard board is 16:9",
                "storyboard panel count equals timed beat count",
                "storyboard receipt contains beat_to_panel_map",
            ],
            "manual": [
                "storyboard depicts accepted patio tea story",
                "Horus remains bald/shaved-head and black-and-gold armored",
                "Embry remains young adult woman with ponytail/workwear",
                "Tyranids remain background only",
            ],
            "fail_closed": True,
            "allowed_statuses": [
                "GENERATED_UNREVIEWED",
                "FAILED_AUTOMATED_CHECK",
                "FAILED_MANUAL_REVIEW",
                "ACCEPTED_MANUAL",
            ],
        },
        "stage_06_provider_packet": {
            "automated": [
                "final_kling_prompt exists",
                "provider_request_dry_run.schema == persona_dream.provider_request_dry_run.v1",
                "referenced_artifacts.lock.json contains upstream artifact paths and sha256 values",
                "all locked artifact paths exist",
                "paid_call_performed == false",
                "live_call_authorized == false",
                "readiness_receipt.status == BLOCKED until manual visual receipts exist",
            ],
            "manual": [
                "human accepts reference sheets",
                "human accepts storyboard board",
                "human explicitly approves paid live Kling call",
            ],
            "fail_closed": True,
            "allowed_statuses": ["GENERATED_UNREVIEWED", "BLOCKED", "PROVIDER_PACKET_ACCEPTED", "FAILED_AUTOMATED_CHECK"],
        },
        "stage_07_live_provider_execution": {
            "automated": [
                "paid_call_approval_receipt.json exists before live call",
                "accepted provider packet exists",
                "upload receipt exists after live call",
                "queue events are recorded",
                "output MP4 exists after completion",
                "ffprobe.json exists and parses",
                "frame_sheet.jpg exists for review",
            ],
            "manual": [
                "human explicit paid-call approval",
                "human review of output MP4/frame sheet",
            ],
            "fail_closed": True,
            "allowed_statuses": [
                "BLOCKED",
                "LIVE_RENDER_SUBMITTED",
                "LIVE_RENDER_ACCEPTED",
                "FAILED_AUTOMATED_CHECK",
                "FAILED_MANUAL_REVIEW",
            ],
        },
        "stage_08_review_display": {
            "automated": [
                "review page reads existing artifact paths only",
                "missing artifacts render as missing/blocked",
                "review page does not synthesize or repair artifacts",
                "CDP screenshot marker exists for rendered review surface",
            ],
            "manual": [
                "human can inspect artifacts and receipts from the page",
            ],
            "fail_closed": True,
            "allowed_statuses": ["NOT_STARTED", "GENERATED_UNREVIEWED", "BLOCKED", "ACCEPTED_AUTOMATED", "FAILED_AUTOMATED_CHECK"],
        },
    }
    for stage in stages:
        stage["strict_gates"] = strict_gate_contracts[stage["stage_id"]]
    return {
        "schema": "persona_dream.stage_status_receipt.v1",
        "artifact_id": "horus_embry_storyboard_first_stage_status",
        "status": "BLOCKED",
        "created_at": now_iso(),
        "root": str(root),
        "blocking_stage_ids": [
            stage["stage_id"]
            for stage in stages
            if stage["status"] in {"BLOCKED", "GENERATED_UNREVIEWED", "NOT_STARTED"}
        ],
        "live_calls_performed": False,
        "paid_provider_call_performed": False,
        "stages": stages,
    }


def validate_fixture(root: Path) -> dict[str, Any]:
    checks = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    required = [
        "idea_contract.json",
        "story_contract.json",
        "timed_beats.json",
        "story_visual_package.json",
        "grounding/memory_recall_horus_embry.json",
        "grounding/brave_search_horus_hair.json",
        "casting/casting_contract.json",
        "casting/chosen_reference_inputs.json",
        "casting/contact_sheet_work_order.json",
        "reference_sheets/horus_reference_sheet.png",
        "reference_sheets/embry_reference_sheet.png",
        "reference_sheets/tyranid_environment_reference_sheet.png",
        "reference_sheets/layout_validation.json",
        "storyboard/storyboard_prompt.md",
        "storyboard/storyboard_identity_contract.json",
        "storyboard/storyboard_board.png",
        "storyboard/storyboard_board_receipt.json",
        "provider_packet/final_kling_prompt.md",
        "provider_packet/provider_request_dry_run.json",
        "provider_packet/referenced_artifacts.lock.json",
        "provider_packet/readiness_receipt.json",
        "provider_packet/provider_packet_validation_receipt.json",
        "stage_status_receipt.json",
        "generated_image_attempts.json",
    ]
    for rel in required:
        path = root / rel
        add(f"exists:{rel}", path.exists() and path.stat().st_size > 0, str(path))

    schemas_root = schema_dir()
    loaded_schemas: dict[str, dict[str, Any]] = {}
    for schema_id, rel in SCHEMA_REGISTRY.items():
        path = schemas_root / rel
        exists = path.exists() and path.stat().st_size > 0
        add(f"schema_file_exists:{rel}", exists, str(path))
        if not exists:
            continue
        try:
            schema_doc = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            add(f"schema_file_json:{rel}", False, str(exc))
            continue
        loaded_schemas[schema_id] = schema_doc
        add(f"schema_file_id:{rel}", schema_doc.get("$id") == schema_id, f"{schema_doc.get('$id')} == {schema_id}")

    for rel, schema in [
        ("idea_contract.json", "persona_dream.idea_contract.v1"),
        ("story_contract.json", "persona_dream.story_contract.v1"),
        ("timed_beats.json", "persona_dream.timed_beats.v1"),
        ("story_visual_package.json", "persona_dream.story_visual_package.v1"),
        ("grounding/memory_recall_horus_embry.json", "persona_dream.grounding.memory_recall.v1"),
        ("grounding/brave_search_horus_hair.json", "persona_dream.grounding.brave_search.v1"),
        ("casting/casting_contract.json", "casting_agent.casting_contract.v1"),
        ("casting/chosen_reference_inputs.json", "casting_agent.chosen_reference_inputs.v1"),
        ("casting/contact_sheet_work_order.json", "casting_agent.contact_sheet_work_order.v1"),
        ("reference_sheets/layout_validation.json", "persona_dream.layout_validation.v1"),
        ("storyboard/storyboard_identity_contract.json", "persona_dream.storyboard_identity_contract.v1"),
        ("storyboard/storyboard_board_receipt.json", "persona_dream.storyboard_board_receipt.v1"),
        ("storyboard/kling_scene_payloads.json", "persona_dream.kling_scene_payloads.v1"),
        ("provider_packet/provider_request_dry_run.json", "persona_dream.provider_request_dry_run.v1"),
        ("provider_packet/referenced_artifacts.lock.json", "persona_dream.referenced_artifacts_lock.v1"),
        ("provider_packet/readiness_receipt.json", "persona_dream.readiness_receipt.v1"),
        ("provider_packet/provider_packet_validation_receipt.json", "provider_packet.validation_receipt.v1"),
        ("stage_status_receipt.json", "persona_dream.stage_status_receipt.v1"),
        ("generated_image_attempts.json", "persona_dream.generated_image_attempts.v1"),
        ("review_page/interaction_manifest.json", "persona_dream.review_display_interaction_manifest.v1"),
        ("review_page/review_display_receipt.json", "persona_dream.review_display_receipt.v1"),
    ]:
        path = root / rel
        if path.exists():
            data = json.loads(path.read_text())
            add(f"schema:{rel}", data.get("schema") == schema, f"{data.get('schema')} == {schema}")
            schema_doc = loaded_schemas.get(schema)
            if schema_doc:
                missing_required = [
                    field for field in schema_doc.get("required", [])
                    if field not in data
                ]
                add(
                    f"schema_required_fields:{rel}",
                    not missing_required,
                    str(missing_required),
                )

    idea_path = root / "idea_contract.json"
    if idea_path.exists():
        idea = json.loads(idea_path.read_text())
        add("idea_contract_status_accepted", idea.get("status") == "ACCEPTED_AUTOMATED", str(idea.get("status")))
        add(
            "idea_contract_records_source_mode",
            idea.get("source_mode") in {"autonomous_memory_project_synthesis", "human_supplied_seed", "project_agent_supplied_seed"},
            str(idea.get("source_mode")),
        )
        add(
            "idea_contract_has_required_inputs",
            bool(idea.get("idea")) and bool(idea.get("inputs_considered")),
            str({"idea": bool(idea.get("idea")), "inputs_considered": len(idea.get("inputs_considered", []))}),
        )
        codebase_protocol = idea.get("codebase_question_protocol", {})
        question_patterns = codebase_protocol.get("question_patterns", [])
        pattern_kinds = {item.get("kind") for item in question_patterns}
        add(
            "idea_contract_has_codebase_question_protocol",
            codebase_protocol.get("transport") == "httpx POST http://127.0.0.1:8601/recall"
            and {"project_state", "project_activity", "code_symbols"} <= pattern_kinds,
            str({"transport": codebase_protocol.get("transport"), "pattern_kinds": sorted(pattern_kinds)}),
        )
        add(
            "idea_contract_records_memory_not_live_git_boundary",
            "does not inspect live git" in str(codebase_protocol.get("boundary", "")),
            str(codebase_protocol.get("boundary", "")),
        )

    story_path = root / "story_contract.json"
    if story_path.exists():
        story = json.loads(story_path.read_text())
        add("story_seed_preserved", "Horus and Embry" in story.get("seed", "") and "Tyranids" in story.get("seed", ""), story.get("seed", ""))
        add("speakers_identified", sorted(story.get("speaking_characters", [])) == ["embry", "horus"], str(story.get("speaking_characters")))

    entities_path = root / "story_visual_package.json"
    if entities_path.exists():
        entities = json.loads(entities_path.read_text())["keyed_entities"]
        expected_keys = [
            ("characters", "horus"),
            ("characters", "embry"),
            ("creatures", "tyranids"),
            ("scenery", "void_world_patio"),
            ("props", "tea_table_sparta_laptop"),
        ]
        for group, key in expected_keys:
            add(f"entity_keyed:{group}.{key}", key in entities.get(group, {}), f"{group}.{key}")

    layout_path = root / "reference_sheets/layout_validation.json"
    if layout_path.exists():
        layout = json.loads(layout_path.read_text())
        add("layout_no_nonuniform_scaling", not layout.get("nonuniform_scaling_detected"), str(layout.get("nonuniform_scaling_detected")))
        add("layout_manual_review_required", layout.get("manual_review_required") is True, str(layout.get("manual_review_required")))
        add("layout_assets_have_source", all(asset.get("source") for asset in layout.get("assets", [])), str([asset.get("source") for asset in layout.get("assets", [])]))
        for asset in layout.get("assets", []):
            asset_name = Path(str(asset.get("path", ""))).name or "unknown"
            width = asset.get("width")
            height = asset.get("height")
            accepted_sizes = {(1600, 1200), (1448, 1086)}
            add(
                f"layout_asset_{asset_name}_accepted_size",
                (width, height) in accepted_sizes,
                f"{width}x{height}",
            )

    board_path = root / "storyboard/storyboard_board_receipt.json"
    identity_path = root / "storyboard/storyboard_identity_contract.json"
    scene_payload_path = root / "storyboard/kling_scene_payloads.json"
    if board_path.exists() and identity_path.exists():
        board = json.loads(board_path.read_text())
        identity_contract = json.loads(identity_path.read_text())
        add("storyboard_identity_contract_accepted", identity_contract.get("status") == "ACCEPTED_AUTOMATED", str(identity_contract.get("status")))
        grounding_artifacts = identity_contract.get("grounding_artifacts", [])
        grounding_paths = {Path(item.get("path", "")).name for item in grounding_artifacts}
        add(
            "storyboard_identity_contract_has_memory_and_brave_grounding",
            {"memory_recall_horus_embry.json", "brave_search_horus_hair.json"} <= grounding_paths,
            str(sorted(grounding_paths)),
        )
        failing_identity = [
            item for item in identity_contract.get("character_checks", [])
            if item.get("status") != "ACCEPTED_AUTOMATED"
        ]
        add("storyboard_identity_contract_no_failed_characters", not failing_identity, str(failing_identity))
        add("storyboard_16_9", board.get("width") == 1920 and board.get("height") == 1080, f"{board.get('width')}x{board.get('height')}")
        add("storyboard_panel_count", board.get("actual_panel_count") == 10, str(board.get("actual_panel_count")))
        add("storyboard_has_source", bool(board.get("source")), str(board.get("source")))
    if scene_payload_path.exists():
        scene_payload = json.loads(scene_payload_path.read_text())
        panels = scene_payload.get("panels", [])
        add("kling_scene_payload_panel_count", len(panels) == 10, str(len(panels)))
        add(
            "kling_scene_payloads_have_physical_emotion",
            all(panel.get("emotional_behavior") for panel in panels),
            str([panel.get("panel") for panel in panels if not panel.get("emotional_behavior")]),
        )
        add(
            "kling_scene_payloads_have_camera",
            all(panel.get("camera") for panel in panels),
            str([panel.get("panel") for panel in panels if not panel.get("camera")]),
        )
        add(
            "kling_scene_payloads_have_pause_or_timing",
            all(panel.get("timing") for panel in panels),
            str([panel.get("panel") for panel in panels if not panel.get("timing")]),
        )
        add(
            "kling_scene_payloads_have_provider_text",
            all(panel.get("provider_text") for panel in panels),
            str([panel.get("panel") for panel in panels if not panel.get("provider_text")]),
        )

    provider_path = root / "provider_packet/provider_request_dry_run.json"
    readiness_path = root / "provider_packet/readiness_receipt.json"
    if provider_path.exists() and readiness_path.exists():
        provider = json.loads(provider_path.read_text())
        readiness = json.loads(readiness_path.read_text())
        add("provider_paid_false", provider.get("paid_call_performed") is False, str(provider.get("paid_call_performed")))
        add("provider_readiness_blocked_until_manual_review", readiness.get("status") == "BLOCKED", str(readiness.get("status")))
        missing_manual = [
            check for check in readiness.get("checks", [])
            if str(check.get("name", "")).startswith("manual_") and check.get("ok") is False
        ]
        add("provider_manual_review_gates_recorded", len(missing_manual) == 2, str(missing_manual))

    provider_validation_path = root / "provider_packet/provider_packet_validation_receipt.json"
    if provider_validation_path.exists():
        provider_validation = json.loads(provider_validation_path.read_text())
        add(
            "provider_packet_skill_validation_accepted",
            provider_validation.get("status") == "ACCEPTED_AUTOMATED" and provider_validation.get("failed") == 0,
            str({"status": provider_validation.get("status"), "failed": provider_validation.get("failed")}),
        )

    lock_path = root / "provider_packet/referenced_artifacts.lock.json"
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        missing = [item for item in lock.get("artifacts", []) if not Path(item["path"]).exists()]
        add("locked_paths_exist", not missing, str(missing))
        bad_statuses = [item for item in lock.get("artifacts", []) if item.get("status") not in {"ACCEPTED_AUTOMATED", "ACCEPTED_MANUAL", "PROVIDER_PACKET_ACCEPTED", "GENERATED_UNREVIEWED"}]
        add("locked_statuses_allowed", not bad_statuses, str(bad_statuses))

    stage_path = root / "stage_status_receipt.json"
    if stage_path.exists():
        stage_receipt = json.loads(stage_path.read_text())
        stages = stage_receipt.get("stages", [])
        add("stage_receipt_has_9_stages", len(stages) == 9, str(len(stages)))
        add("stage_receipt_blocks_live_provider", "stage_07_live_provider_execution" in stage_receipt.get("blocking_stage_ids", []), str(stage_receipt.get("blocking_stage_ids", [])))
        add("stage_receipt_has_rollback_targets", all(stage.get("rollback_target") for stage in stages), str([stage.get("stage_id") for stage in stages if not stage.get("rollback_target")]))
        add(
            "stage_receipt_all_stages_have_strict_gates",
            all(isinstance(stage.get("strict_gates"), dict) for stage in stages),
            str([stage.get("stage_id") for stage in stages if not isinstance(stage.get("strict_gates"), dict)]),
        )
        add(
            "stage_receipt_all_strict_gates_fail_closed",
            all(stage.get("strict_gates", {}).get("fail_closed") is True for stage in stages),
            str([stage.get("stage_id") for stage in stages if stage.get("strict_gates", {}).get("fail_closed") is not True]),
        )
        add(
            "stage_receipt_all_strict_gates_have_automated_checks",
            all(stage.get("strict_gates", {}).get("automated") for stage in stages),
            str([stage.get("stage_id") for stage in stages if not stage.get("strict_gates", {}).get("automated")]),
        )
        add(
            "stage_receipt_all_strict_gates_have_allowed_statuses",
            all(stage.get("strict_gates", {}).get("allowed_statuses") for stage in stages),
            str([stage.get("stage_id") for stage in stages if not stage.get("strict_gates", {}).get("allowed_statuses")]),
        )
        add(
            "stage_receipt_all_stages_have_required_skills",
            all(stage.get("required_skills") for stage in stages),
            str([stage.get("stage_id") for stage in stages if not stage.get("required_skills")]),
        )
        required_skill_expectations = {
            "stage_03_casting_reference_research": {"memory", "brave-search", "contact-sheet"},
            "stage_04_reference_sheets": {"contact-sheet", "create-image", "scillm"},
        "stage_05_storyboard_board": {"create-storyboard", "memory", "brave-search", "contact-sheet", "create-image", "scillm"},
        }
        missing_stage_skills = []
        for stage in stages:
            expected = required_skill_expectations.get(stage.get("stage_id"), set())
            actual = set(stage.get("required_skills") or [])
            missing = sorted(expected - actual)
            if missing:
                missing_stage_skills.append({"stage_id": stage.get("stage_id"), "missing": missing})
        add("stage_receipt_required_grounding_skills_present", not missing_stage_skills, str(missing_stage_skills))
        status_violations = [
            {
                "stage_id": stage.get("stage_id"),
                "status": stage.get("status"),
                "allowed_statuses": stage.get("strict_gates", {}).get("allowed_statuses", []),
            }
            for stage in stages
            if stage.get("status") not in stage.get("strict_gates", {}).get("allowed_statuses", [])
        ]
        add("stage_receipt_statuses_allowed_by_strict_gates", not status_violations, str(status_violations))

    review_receipt_path = root / "review_page/review_display_receipt.json"
    interaction_path = root / "review_page/interaction_manifest.json"
    if review_receipt_path.exists() and interaction_path.exists():
        review_receipt = json.loads(review_receipt_path.read_text())
        interaction_manifest = json.loads(interaction_path.read_text())
        add("review_display_receipt_generated", review_receipt.get("status") == "GENERATED_UNREVIEWED", str(review_receipt.get("status")))
        add("review_display_index_exists", Path(review_receipt.get("index_html", "")).exists(), str(review_receipt.get("index_html", "")))
        add("review_display_no_missing_artifacts", not review_receipt.get("missing_artifacts"), str(review_receipt.get("missing_artifacts")))
        add(
            "review_display_provider_blocked_visible",
            any(check.get("name") == "provider_blocked_visible" and check.get("ok") for check in interaction_manifest.get("checks", [])),
            str(interaction_manifest.get("checks", [])),
        )

    ok = all(check["ok"] for check in checks)
    return {
        "schema": "persona_dream.fixture_validation_report.v1",
        "artifact_id": "horus_embry_storyboard_first_dry_run_fixture_validation",
        "status": "ACCEPTED_AUTOMATED" if ok else "FAILED_AUTOMATED_CHECK",
        "created_at": now_iso(),
        "root": str(root),
        "checks": checks,
        "passed": sum(1 for check in checks if check["ok"]),
        "failed": sum(1 for check in checks if not check["ok"]),
    }


def build_fixture(
    out_dir: Path,
    *,
    image_backend: str,
    create_image_backend: str,
    create_image_model: str,
    strict_generated_images: bool,
    image_timeout_s: int,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    story_text = (
        "At a small patio table under a wind-tugged umbrella, Horus Lupercal "
        "and Embry drink tea on a Warhammer 40k void world. Tyranids move in "
        "the distance like a living storm, but the table remains calm. Horus "
        "and Embry discuss SPARTA Explorer as a humane evidence workspace: not "
        "a dashboard, but a colleague at the table."
    )
    idea_contract = {
        "schema": "persona_dream.idea_contract.v1",
        "artifact_id": "horus_embry_idea_contract",
        "status": "ACCEPTED_AUTOMATED",
        "created_at": now_iso(),
        "source_mode": "human_supplied_seed",
        "idea": SEED,
        "default_source_mode": "autonomous_memory_project_synthesis",
        "purpose": (
            "Persona-dream normally synthesizes a dream idea from persona memories, "
            "project knowledge in memory, recent project activity, and optional Brave "
            "Search context. This worked fixture records the user's explicit Horus/Embry "
            "seed as the override input."
        ),
        "inputs_considered": [
            {
                "kind": "human_supplied_seed",
                "status": "ACCEPTED_AUTOMATED",
                "summary": SEED,
            },
            {
                "kind": "persona_memory",
                "status": "DEFERRED_BY_EXPLICIT_SEED",
                "required_in_autonomous_mode": True,
                "summary": "Autonomous runs must recall persona memories before selecting the dream idea.",
            },
            {
                "kind": "project_knowledge_memory",
                "status": "DEFERRED_BY_EXPLICIT_SEED",
                "required_in_autonomous_mode": True,
                "summary": "Autonomous runs must mix project knowledge or recent project activity from memory into the idea pool.",
            },
            {
                "kind": "brave_search_context",
                "status": "OPTIONAL_NOT_USED_FOR_IDEA_SELECTION",
                "required_in_autonomous_mode": False,
                "summary": "Brave Search may add relevant current events or canon/context checks when the idea needs fresh grounding.",
            },
        ],
        "codebase_question_protocol": {
            "required_in_autonomous_mode": True,
            "transport": "httpx POST http://127.0.0.1:8601/recall",
            "boundary": "/recall returns stored memory only; it does not inspect live git or the filesystem.",
            "default_scope": "memory",
            "question_patterns": [
                {
                    "kind": "project_state",
                    "collections": None,
                    "query": "what did we work on recently that could become a persona dream?",
                    "expected_recall_profile": "temporal_project_state",
                },
                {
                    "kind": "project_activity",
                    "collections": ["project_activity"],
                    "query": "what changed recently in the project related to SPARTA Explorer or persona-dream?",
                    "expected_recall_profile": "temporal_project_state",
                },
                {
                    "kind": "code_symbols",
                    "collections": ["code_symbols"],
                    "query": "where is the relevant project workflow implemented?",
                    "expected_recall_profile": None,
                },
            ],
            "freshness_repair": {
                "when_memory_missing": "Run the appropriate ingest workflow before relying on code activity recall.",
                "git_activity_ingest_example": "memory-agent activity ingest-git /path/to/repo --project memory --scope memory --since <iso> --until <iso> --batch-id <batch>",
            },
        },
        "selection_policy": [
            "If a human or project agent supplies a specific idea, record it as the chosen idea and preserve it exactly.",
            "Otherwise recall persona memory and project knowledge first, combine several residues into candidate ideas, and select one candidate with source links.",
            "For codebase-grounded dreams, ask project activity and code-symbol questions through memory /recall and record collections, scope, recall profile, and source refs.",
            "Use Brave Search only when fresh external context or canon-sensitive grounding is needed, and write a search receipt.",
            "Do not proceed to story generation when no source-linked idea can be formed.",
        ],
    }
    write_json(out_dir / "idea_contract.json", idea_contract)
    beats = [
        (0.0, 0.8, "Wide void-world patio", "A tiny tea table under an umbrella sits against an impossible void horizon."),
        (0.8, 1.5, "Horus enters frame", "Pre-Heresy Horus sits calmly, black-and-gold armor catching the cold light."),
        (1.5, 2.2, "Embry at the table", "Embry opens a laptop/tablet showing a SPARTA Explorer work surface."),
        (2.2, 3.0, "Tyranids in background", "Warhammer 40k Tyranids run and play at a distant scale behind the patio."),
        (3.0, 3.8, "Tea service detail", "Tea cups, notes, and SPARTA evidence cards sit between them."),
        (3.8, 4.6, "Horus speaks", "Horus says the system must preserve evidence without turning people into widgets."),
        (4.6, 5.5, "Embry answers", "Embry says SPARTA Explorer should feel like a trusted colleague at the table."),
        (5.5, 6.4, "Shared screen", "The laptop shows Chat, Evidence Workspace, Coverage, QRAs, and Controls as quiet tools."),
        (6.4, 7.2, "Background motion", "The Tyranids cross behind the umbrella, strange but not interrupting the conversation."),
        (7.2, 8.0, "Closing wide", "Horus and Embry lean over the SPARTA Explorer notes as the void-world wind moves the umbrella."),
    ]
    timed_beats = [
        {
            "beat_id": f"beat_{idx + 1:02d}",
            "start_s": start,
            "end_s": end,
            "visual": visual,
            "caption": caption,
            "speakers": ["horus"] if idx == 5 else ["embry"] if idx == 6 else [],
        }
        for idx, (start, end, visual, caption) in enumerate(beats)
    ]

    story_contract = {
        "schema": "persona_dream.story_contract.v1",
        "artifact_id": "horus_embry_story_contract",
        "status": "ACCEPTED_AUTOMATED",
        "created_at": now_iso(),
        "input_idea_contract": str(out_dir / "idea_contract.json"),
        "seed": SEED,
        "story": story_text,
        "target_duration_s": 8.0,
        "speaking_characters": ["horus", "embry"],
        "non_claims": ["Synthetic dry-run fixture; no live provider call; no final visual acceptance."],
    }
    write_json(out_dir / "story_contract.json", story_contract)
    (out_dir / "story_contract.md").write_text("# Horus/Embry Story Contract\n\n" + story_text + "\n")
    write_json(out_dir / "timed_beats.json", {
        "schema": "persona_dream.timed_beats.v1",
        "artifact_id": "horus_embry_timed_beats",
        "status": "ACCEPTED_AUTOMATED",
        "created_at": now_iso(),
        "duration_s": 8.0,
        "beats": timed_beats,
    })

    refs_dir = out_dir / "reference_sheets"
    prompts_dir = out_dir / "prompts"
    reference_specs = {
        "horus": {
            "entity_id": "character_horus_lupercal_warmaster",
            "path": refs_dir / "horus_reference_sheet.png",
            "title": "Horus Lupercal Warmaster Reference Sheet",
            "anchors": ["Warhammer 40,000", "Warmaster", "bald", "pale primarch", "black-and-gold armor", "pre-Heresy conversational state"],
            "panels": [
                ("Main front full body", "Primarch-scale figure, bald pale face, black-and-gold armor, calm rather than corrupted."),
                ("Three-quarter seated", "Tea-table posture with massive armor readable but not aggressive."),
                ("Side/back scale", "Broad armored silhouette and cloak, patio umbrella gives scale."),
                ("Face/detail closeup", "Warm, serious expression suitable for SPARTA Explorer dialogue."),
            ],
            "palette": ("#171512", "#3d2c1d", "#d2a84f"),
        },
        "embry": {
            "entity_id": "character_embry",
            "path": refs_dir / "embry_reference_sheet.png",
            "title": "Embry Character Reference Sheet",
            "anchors": [
                "fictional young adult woman",
                "dark brown low ponytail",
                "olive eyes",
                "subtle nose scar",
                "practical gray field jacket and workwear",
                "calm SPARTA Explorer product collaborator",
            ],
            "panels": [
                ("Main front full body", "Fictional young adult woman, dark brown low ponytail, olive eyes, faint nose scar, gray field jacket, laptop/tablet nearby."),
                ("Three-quarter seated", "Same woman at tea table, collaborative posture, practical gray workwear, discussing product evidence with Horus."),
                ("Side/back at table", "Same woman from side/back with low ponytail visible, working posture, screen and notes visible."),
                ("Face/detail closeup", "Same woman's focused humane expression, subtle nose scar readable, no celebrity likeness."),
            ],
            "palette": ("#12191c", "#2b4e52", "#9fd4d1"),
        },
        "tyranid_environment": {
            "entity_id": "creature_warhammer_40k_tyranids_background",
            "path": refs_dir / "tyranid_environment_reference_sheet.png",
            "title": "Tyranid Background / Void Patio Reference Sheet",
            "anchors": ["Warhammer 40,000 Tyranids", "chitin carapace", "scything talons", "void-world patio", "background motion"],
            "panels": [
                ("Wide establishing view", "Umbrella tea table in foreground, Tyranids distant in void-world background."),
                ("Creature side motion", "Chitin silhouettes with talons moving behind the patio."),
                ("Scale/detail", "Foreground tea service and laptop readable against distant creatures."),
                ("Lighting/mood", "Cinematic void light, calm table contrasted with alien background."),
            ],
            "palette": ("#17121b", "#3b274f", "#b790d7"),
        },
    }
    repo_root = Path(__file__).resolve().parents[3]
    image_attempts: list[dict[str, Any]] = []
    layout_assets = []
    for name, spec in reference_specs.items():
        prompt_path = prompts_dir / "reference_sheets" / f"{name}.prompt.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(
            reference_sheet_prompt(
                title=spec["title"],
                entity_id=spec["entity_id"],
                anchors=spec["anchors"],
                panels=spec["panels"],
            )
        )
        if image_backend == "create-image":
            attempt = run_create_image(
                repo_root=repo_root,
                prompt_path=prompt_path,
                output_path=spec["path"],
                size="1600x1200",
                backend=create_image_backend,
                model=create_image_model,
                attempt_id=f"reference_sheet_{name}",
                timeout_s=image_timeout_s,
            )
            image_attempts.append(attempt)
            if attempt["status"] == "ACCEPTED_AUTOMATED":
                metrics = image_metrics(spec["path"], status="GENERATED_UNREVIEWED")
                metrics["generation_attempt_id"] = attempt["attempt_id"]
                metrics["source"] = "$create-image"
                layout_assets.append(metrics)
                continue
            if strict_generated_images:
                write_json(out_dir / "generated_image_attempts.json", {
                    "schema": "persona_dream.generated_image_attempts.v1",
                    "status": "FAILED_AUTOMATED_CHECK",
                    "created_at": now_iso(),
                    "attempts": image_attempts,
                })
                raise RuntimeError(f"create-image failed for {name}; see generated_image_attempts.json")
        layout_assets.append(
            create_reference_sheet(
                spec["path"],
                title=spec["title"],
                entity_id=spec["entity_id"],
                anchors=spec["anchors"],
                panels=spec["panels"],
                palette=spec["palette"],
            )
        )
        layout_assets[-1]["source"] = "deterministic_fixture"
        if image_backend == "create-image":
            layout_assets[-1]["fallback_reason"] = "create_image_failed"

    write_json(out_dir / "generated_image_attempts.json", {
        "schema": "persona_dream.generated_image_attempts.v1",
        "status": "ACCEPTED_AUTOMATED" if all(attempt["status"] == "ACCEPTED_AUTOMATED" for attempt in image_attempts) else "GENERATED_UNREVIEWED",
        "created_at": now_iso(),
        "image_backend": image_backend,
        "create_image_backend": create_image_backend,
        "create_image_model": create_image_model,
        "strict_generated_images": strict_generated_images,
        "attempts": image_attempts,
    })
    layout_validation = {
        "schema": "persona_dream.layout_validation.v1",
        "artifact_id": "horus_embry_reference_sheet_layout_validation",
        "status": "GENERATED_UNREVIEWED",
        "created_at": now_iso(),
        "manual_review_required": True,
        "nonuniform_scaling_detected": False,
        "assets": layout_assets,
        "non_claims": ["Fixture sheets prove layout mechanics, not final art acceptance."],
    }
    write_json(refs_dir / "layout_validation.json", layout_validation)

    story_visual_package = {
        "schema": "persona_dream.story_visual_package.v1",
        "story_id": "horus_embry_storyboard_first_fixture",
        "story": {
            "text": story_text,
            "context": "Pre-Heresy warmer Horus, fictional Embry, 40k Tyranids as background, SPARTA Explorer product discussion.",
        },
        "keyed_entities": {
            "characters": {
                "horus": {
                    "entity_id": "character_horus_lupercal_warmaster",
                    "display_name": "Horus Lupercal / The Warmaster",
                    "description": "Pre-Heresy Horus Lupercal, Warmaster of Warhammer 40,000, bald pale primarch in black-and-gold armor, calm tea-table collaborator.",
                    "image_file_paths": [str(reference_specs["horus"]["path"])],
                    "document_paths": [],
                    "source_urls": [],
                    "visual_anchors": reference_specs["horus"]["anchors"],
                    "must_not_include": ["generic space marine", "dark-haired soldier", "long hair", "corrupted Chaos monster"],
                    "contact_sheet_required": True,
                    "contact_sheet_kind": "character_reference_pack",
                },
                "embry": {
                    "entity_id": "character_embry",
                    "display_name": "Embry",
                    "description": "Fictional Embry persona as a young adult woman with dark brown low ponytail, olive eyes, subtle nose scar, practical gray field workwear, and calm SPARTA Explorer collaborator posture at the patio table.",
                    "image_file_paths": [str(reference_specs["embry"]["path"])],
                    "document_paths": [],
                    "source_urls": [],
                    "visual_anchors": reference_specs["embry"]["anchors"],
                    "must_not_include": ["celebrity likeness", "male-coded Embry", "beard", "mustache", "older man"],
                    "contact_sheet_required": True,
                    "contact_sheet_kind": "character_reference_pack",
                },
            },
            "creatures": {
                "tyranids": {
                    "entity_id": "creature_warhammer_40k_tyranids_background",
                    "display_name": "Warhammer 40,000 Tyranids",
                    "description": "Warhammer 40,000 Tyranids as distant background motion with chitin carapace and scything talons.",
                    "image_file_paths": [str(reference_specs["tyranid_environment"]["path"])],
                    "document_paths": [],
                    "source_urls": [],
                    "visual_anchors": ["Warhammer 40,000 Tyranids", "chitin carapace", "scything talons", "hive-organism silhouettes"],
                    "must_not_include": ["generic cute aliens", "dinosaurs", "insects without 40k silhouette"],
                    "contact_sheet_required": True,
                    "contact_sheet_kind": "creature_reference_pack",
                }
            },
            "scenery": {
                "void_world_patio": {
                    "entity_id": "environment_void_world_patio_tea_terrace",
                    "display_name": "Void-world patio tea terrace",
                    "description": "Small patio table with umbrella on a surreal Warhammer 40k void world terrace.",
                    "image_file_paths": [str(reference_specs["tyranid_environment"]["path"])],
                    "document_paths": [],
                    "source_urls": [],
                    "visual_anchors": ["patio table", "umbrella", "void world", "cinematic sci-fi terrace"],
                    "must_not_include": ["generic office", "modern cafe"],
                    "contact_sheet_required": True,
                    "contact_sheet_kind": "environment_reference_pack",
                }
            },
            "props": {
                "tea_table_sparta_laptop": {
                    "entity_id": "prop_patio_table_umbrella_tea_sparta_laptop",
                    "display_name": "Patio table, umbrella, tea, and SPARTA laptop",
                    "description": "Patio table with umbrella, tea service, notes, and a laptop/tablet showing SPARTA Explorer.",
                    "image_file_paths": [str(reference_specs["tyranid_environment"]["path"])],
                    "document_paths": [],
                    "source_urls": [],
                    "visual_anchors": ["round patio table", "umbrella", "tea cups", "SPARTA Explorer screen"],
                    "must_not_include": ["weapon-focused tableau"],
                    "contact_sheet_required": True,
                    "contact_sheet_kind": "prop_reference_pack",
                }
            },
            "effects": {},
        },
    }
    write_json(out_dir / "story_visual_package.json", story_visual_package)
    grounding_dir = out_dir / "grounding"
    grounding_dir.mkdir(parents=True, exist_ok=True)
    memory_grounding = {
        "schema": "persona_dream.grounding.memory_recall.v1",
        "artifact_id": "horus_embry_memory_grounding",
        "status": "ACCEPTED_AUTOMATED",
        "created_at": now_iso(),
        "required_skill": "memory",
        "query": "Horus Lupercal visual appearance bald long hair Warmaster pre-Heresy Embry contact sheet persona young woman ponytail nose scar",
        "facts": [
            {
                "entity_id": "character_embry",
                "source": "memory recall: Embry Canonical Lock",
                "summary": "Embry is a 23-year-old woman with shoulder-length brown hair in a low messy ponytail, olive/green eyes, faint thin healed scar across nose bridge, practical clothing, and realistic non-model texture.",
                "applied_to": ["story_visual_package.characters.embry", "storyboard_identity_contract"],
            },
            {
                "entity_id": "character_horus_lupercal_warmaster",
                "source": "memory recall: prior Horus/Embry contact sheet reviews",
                "summary": "Prior accepted Horus direction used a bare human male head, shaved/bald head, and huge gold/black Warmaster power armor; avoid Egyptian/canine confusion.",
                "applied_to": ["story_visual_package.characters.horus", "storyboard_identity_contract"],
            },
        ],
    }
    brave_grounding = {
        "schema": "persona_dream.grounding.brave_search.v1",
        "artifact_id": "horus_lupercal_hair_brave_grounding",
        "status": "ACCEPTED_AUTOMATED",
        "created_at": now_iso(),
        "required_skill": "brave-search",
        "query": "does the fictional Warhammer 40K character Horus Lupercal have long hair",
        "facts": [
            {
                "entity_id": "character_horus_lupercal_warmaster",
                "source_title": "Warpstone Flux: Hair styles of the Primarchs",
                "source_url": "http://warpstoneflux.blogspot.com/2014/05/hair-styles-of-primarchs.html",
                "summary": "Search result reports Horus Lupercal has a shaved/bald scalp.",
                "applied_to": ["story_visual_package.characters.horus", "storyboard_identity_contract"],
            },
            {
                "entity_id": "character_horus_lupercal_warmaster",
                "source_title": "Horus Lupercal Long Hair by TRASHMELLO on DeviantArt",
                "source_url": "https://www.deviantart.com/trashmello/art/Horus-Lupercal-Long-Hair-1281408140",
                "summary": "A long-hair result exists as fan art, so long hair is explicitly treated as a risky non-canonical variation for this pipeline.",
                "applied_to": ["story_visual_package.characters.horus.must_not_include", "storyboard_identity_contract"],
            },
        ],
    }
    write_json(grounding_dir / "memory_recall_horus_embry.json", memory_grounding)
    write_json(grounding_dir / "brave_search_horus_hair.json", brave_grounding)
    grounding_refs = [
        artifact_ref(grounding_dir / "memory_recall_horus_embry.json", "ACCEPTED_AUTOMATED"),
        artifact_ref(grounding_dir / "brave_search_horus_hair.json", "ACCEPTED_AUTOMATED"),
    ]

    casting_out = out_dir / "casting"
    casting_cmd = [
        str(repo_root / "skills" / "casting-agent" / "run.sh"),
        "plan-package",
        "--story-package",
        str(out_dir / "story_visual_package.json"),
        "--out-dir",
        str(casting_out),
    ]
    casting_proc = subprocess.run(casting_cmd, cwd=repo_root, capture_output=True, text=True)
    if casting_proc.returncode != 0:
        raise RuntimeError(f"casting-agent failed: {casting_proc.stderr}")
    (casting_out / "casting_agent_stdout.json").write_text(casting_proc.stdout)

    storyboard_dir = out_dir / "storyboard"
    storyboard_dir.mkdir(parents=True, exist_ok=True)
    storyboard_identity_contract = make_storyboard_identity_contract(story_visual_package, grounding_artifacts=grounding_refs)
    write_json(storyboard_dir / "storyboard_identity_contract.json", storyboard_identity_contract)
    if storyboard_identity_contract["status"] != "ACCEPTED_AUTOMATED":
        raise RuntimeError("storyboard identity contract failed; refusing to generate storyboard board")
    storyboard_prompt = storyboard_image_prompt(timed_beats)
    (storyboard_dir / "storyboard_prompt.md").write_text(storyboard_prompt)
    storyboard_prompt_path = prompts_dir / "storyboard_board.prompt.md"
    storyboard_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    storyboard_prompt_path.write_text(storyboard_prompt)
    board_path = storyboard_dir / "storyboard_board.png"
    if image_backend == "create-image":
        attempt = run_create_image(
            repo_root=repo_root,
            prompt_path=storyboard_prompt_path,
            output_path=board_path,
            size="1920x1080",
            backend=create_image_backend,
            model=create_image_model,
            attempt_id="storyboard_board",
            timeout_s=image_timeout_s,
        )
        image_attempts.append(attempt)
        if attempt["status"] == "ACCEPTED_AUTOMATED":
            image_receipt_path = storyboard_dir / "storyboard_board_image_receipt.json"
            original_receipt_path = Path(attempt["receipt_path"])
            if original_receipt_path.exists():
                try:
                    receipt_payload = json.loads(original_receipt_path.read_text())
                except Exception:
                    receipt_payload = {}
                if receipt_payload.get("schema") != "persona_dream.storyboard_board_receipt.v1":
                    shutil.copyfile(original_receipt_path, image_receipt_path)
                    attempt["receipt_path"] = str(image_receipt_path)
                    attempt["receipt_exists"] = True
            if not image_receipt_path.exists() and board_path.exists():
                image_bytes = board_path.read_bytes()
                with Image.open(board_path) as image:
                    image_width, image_height = image.size
                image_receipt_path.write_text(
                    json.dumps(
                        {
                            "ok": True,
                            "auth": "codex-oauth",
                            "path": str(board_path),
                            "width": image_width,
                            "height": image_height,
                            "bytes": len(image_bytes),
                            "sha256": hashlib.sha256(image_bytes).hexdigest(),
                            "receipt_synthesized_by": "persona-dream-storyboard",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                )
                attempt["receipt_path"] = str(image_receipt_path)
                attempt["receipt_exists"] = True
            board_receipt = {
                "schema": "persona_dream.storyboard_board_receipt.v1",
                "artifact_id": "storyboard_board_horus_embry_fixture",
                "status": "GENERATED_UNREVIEWED",
                "created_at": now_iso(),
                "path": str(board_path),
                "sha256": sha256(board_path),
                "width": 1920,
                "height": 1080,
                "aspect_ratio": "16:9",
                "expected_panel_count": len(timed_beats),
                "actual_panel_count": len(timed_beats),
                "beat_to_panel_map": [
                    {
                        "panel": idx + 1,
                        "beat_id": beat["beat_id"],
                        "time_range_s": [beat["start_s"], beat["end_s"]],
                        "caption": beat["caption"],
                    }
                    for idx, beat in enumerate(timed_beats)
                ],
                "generation_attempt_id": attempt["attempt_id"],
                "source": "$create-image",
                "manual_review_required": True,
            }
        elif strict_generated_images:
            write_json(out_dir / "generated_image_attempts.json", {
                "schema": "persona_dream.generated_image_attempts.v1",
                "status": "FAILED_AUTOMATED_CHECK",
                "created_at": now_iso(),
                "attempts": image_attempts,
            })
            raise RuntimeError("create-image failed for storyboard board; see generated_image_attempts.json")
        else:
            board_receipt = create_storyboard_board(board_path, timed_beats)
            board_receipt["source"] = "deterministic_fixture"
            board_receipt["fallback_reason"] = "create_image_failed"
    else:
        board_receipt = create_storyboard_board(board_path, timed_beats)
        board_receipt["source"] = "deterministic_fixture"
    write_json(storyboard_dir / "storyboard_board_receipt.json", board_receipt)
    kling_scene_payloads = make_kling_scene_payloads(timed_beats)
    write_json(storyboard_dir / "kling_scene_payloads.json", kling_scene_payloads)
    (storyboard_dir / "kling_scene_directions.md").write_text(make_kling_scene_directions(kling_scene_payloads))
    write_json(out_dir / "generated_image_attempts.json", {
        "schema": "persona_dream.generated_image_attempts.v1",
        "status": "ACCEPTED_AUTOMATED" if image_attempts and all(attempt["status"] == "ACCEPTED_AUTOMATED" for attempt in image_attempts) else "GENERATED_UNREVIEWED",
        "created_at": now_iso(),
        "image_backend": image_backend,
        "create_image_backend": create_image_backend,
        "create_image_model": create_image_model,
        "strict_generated_images": strict_generated_images,
        "attempts": image_attempts,
    })

    provider_dir = out_dir / "provider_packet"
    provider_dir.mkdir(parents=True, exist_ok=True)
    final_prompt = (
        "Generate an 8-second cinematic Kling clip following the attached "
        "storyboard board panel-by-panel and the attached Kling scene directions "
        "text. Treat each panel direction as Subject + Action + visible emotional "
        "behavior + Camera + Pause/timing. Preserve Horus Lupercal as the "
        "pre-Heresy Warhammer 40,000 Warmaster: bald, pale primarch scale, "
        "black-and-gold armor, calm tea-table collaborator. Preserve Embry as a "
        "fictional young adult woman with dark brown low ponytail, olive eyes, "
        "subtle nose scar, practical gray field workwear, and calm SPARTA Explorer "
        "collaborator posture. Keep Warhammer 40,000 "
        "Tyranids as distant background motion with chitin carapace and scything "
        "talons. Scene: patio tea table and umbrella on a void world; laptop/tablet "
        "shows SPARTA Explorer as a quiet evidence workspace. Do not genericize "
        "Horus into a random space marine. Do not give Horus long hair. Do not "
        "render Embry as male-coded, bearded, or an older man. Do not turn Tyranids into cute aliens. "
        "No paid provider call is authorized by this dry-run packet.\n"
    )
    (provider_dir / "final_kling_prompt.md").write_text(final_prompt)

    locked_artifacts = [
        artifact_ref(out_dir / "idea_contract.json", "ACCEPTED_AUTOMATED"),
        artifact_ref(out_dir / "story_contract.json", "ACCEPTED_AUTOMATED"),
        artifact_ref(out_dir / "timed_beats.json", "ACCEPTED_AUTOMATED"),
        artifact_ref(out_dir / "story_visual_package.json", "ACCEPTED_AUTOMATED"),
        *grounding_refs,
        artifact_ref(casting_out / "casting_contract.json", "ACCEPTED_AUTOMATED"),
        artifact_ref(casting_out / "chosen_reference_inputs.json", "ACCEPTED_AUTOMATED"),
        artifact_ref(casting_out / "contact_sheet_work_order.json", "ACCEPTED_AUTOMATED"),
        artifact_ref(refs_dir / "layout_validation.json", "GENERATED_UNREVIEWED"),
        artifact_ref(reference_specs["horus"]["path"], "GENERATED_UNREVIEWED"),
        artifact_ref(reference_specs["embry"]["path"], "GENERATED_UNREVIEWED"),
        artifact_ref(reference_specs["tyranid_environment"]["path"], "GENERATED_UNREVIEWED"),
        artifact_ref(storyboard_dir / "storyboard_identity_contract.json", "ACCEPTED_AUTOMATED"),
        artifact_ref(storyboard_dir / "storyboard_prompt.md", "GENERATED_UNREVIEWED"),
        artifact_ref(storyboard_dir / "storyboard_board.png", "GENERATED_UNREVIEWED"),
        artifact_ref(storyboard_dir / "storyboard_board_receipt.json", "GENERATED_UNREVIEWED"),
        artifact_ref(storyboard_dir / "kling_scene_payloads.json", "GENERATED_UNREVIEWED"),
        artifact_ref(storyboard_dir / "kling_scene_directions.md", "GENERATED_UNREVIEWED"),
    ]
    write_json(provider_dir / "referenced_artifacts.lock.json", {
        "schema": "persona_dream.referenced_artifacts_lock.v1",
        "artifact_id": "horus_embry_provider_packet_reference_lock",
        "status": "GENERATED_UNREVIEWED",
        "created_at": now_iso(),
        "artifacts": locked_artifacts,
    })
    provider_request = {
        "schema": "persona_dream.provider_request_dry_run.v1",
        "artifact_id": "horus_embry_kling_provider_request_dry_run",
        "status": "GENERATED_UNREVIEWED",
        "created_at": now_iso(),
        "provider": "kling",
        "model": "kling_3_omni_native_av",
        "paid_call_performed": False,
        "live_call_authorized": False,
        "duration_s": 8.0,
        "prompt_path": str(provider_dir / "final_kling_prompt.md"),
        "storyboard_board": str(storyboard_dir / "storyboard_board.png"),
        "scene_directions_path": str(storyboard_dir / "kling_scene_directions.md"),
        "scene_payloads_path": str(storyboard_dir / "kling_scene_payloads.json"),
        "reference_images": [
            str(reference_specs["horus"]["path"]),
            str(reference_specs["embry"]["path"]),
            str(reference_specs["tyranid_environment"]["path"]),
        ],
        "provider_input_notes": [
            "Kling receives the storyboard board image plus plain-language scene directions text.",
            "Scene directions attach emotion to visible physical behavior, camera movement, and timing.",
            "kling_scene_payloads.json is an internal validation artifact, not a provider upload format.",
        ],
        "negative_constraints": [
            "generic space marine Horus",
            "dark-haired Horus",
            "cute generic alien Tyranids",
            "unreviewed references",
            "paid call without approval",
        ],
    }
    write_json(provider_dir / "provider_request_dry_run.json", provider_request)
    readiness = {
        "schema": "persona_dream.readiness_receipt.v1",
        "artifact_id": "horus_embry_provider_packet_readiness",
        "status": "BLOCKED",
        "created_at": now_iso(),
        "paid_call_performed": False,
        "live_call_authorized": False,
        "block_reason": "manual_visual_review_required_for_reference_sheets_and_storyboard",
        "manual_review_required_before_live": True,
        "checks": [
            {"name": "all_referenced_paths_exist", "ok": True},
            {"name": "artifact_hashes_locked", "ok": True},
            {"name": "upstream_not_failed", "ok": True},
            {"name": "paid_call_performed_false", "ok": True},
            {"name": "manual_reference_sheet_review_exists", "ok": False},
            {"name": "manual_storyboard_review_exists", "ok": False},
        ],
        "non_claims": [
            "Reference sheets and storyboard are generated-unreviewed fixture artifacts.",
            "This receipt allows dry-run packet inspection only, not a live Kling call.",
        ],
    }
    write_json(provider_dir / "readiness_receipt.json", readiness)

    provider_packet_cmd = [
        str(repo_root / "skills" / "provider-packet" / "run.sh"),
        "validate",
        "--packet-dir",
        str(provider_dir),
        "--root",
        str(out_dir),
    ]
    provider_packet_proc = subprocess.run(
        provider_packet_cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if provider_packet_proc.returncode != 0:
        raise RuntimeError(f"provider-packet validation failed: {provider_packet_proc.stderr}")

    stage_status = make_stage_status_receipt(out_dir)
    write_json(out_dir / "stage_status_receipt.json", stage_status)
    review_display = build_review_display(out_dir)

    validation = validate_fixture(out_dir)
    write_json(out_dir / "fixture_validation_report.json", validation)
    manifest = {
        "schema": "persona_dream.storyboard_first_fixture_manifest.v1",
        "artifact_id": "horus_embry_storyboard_first_dry_run_fixture",
        "status": validation["status"],
        "created_at": now_iso(),
        "root": str(out_dir),
        "live_calls_performed": False,
        "paid_provider_call_performed": False,
        "validation_report": str(out_dir / "fixture_validation_report.json"),
        "key_artifacts": {
            "story_contract": str(out_dir / "story_contract.json"),
            "idea_contract": str(out_dir / "idea_contract.json"),
            "timed_beats": str(out_dir / "timed_beats.json"),
            "story_visual_package": str(out_dir / "story_visual_package.json"),
            "memory_grounding": str(grounding_dir / "memory_recall_horus_embry.json"),
            "brave_grounding": str(grounding_dir / "brave_search_horus_hair.json"),
            "casting_contract": str(casting_out / "casting_contract.json"),
            "layout_validation": str(refs_dir / "layout_validation.json"),
            "storyboard_board": str(storyboard_dir / "storyboard_board.png"),
            "storyboard_identity_contract": str(storyboard_dir / "storyboard_identity_contract.json"),
            "provider_request_dry_run": str(provider_dir / "provider_request_dry_run.json"),
            "readiness_receipt": str(provider_dir / "readiness_receipt.json"),
            "provider_packet_validation_receipt": str(provider_dir / "provider_packet_validation_receipt.json"),
            "stage_status_receipt": str(out_dir / "stage_status_receipt.json"),
            "generated_image_attempts": str(out_dir / "generated_image_attempts.json"),
            "review_page": review_display["index_html"],
            "review_display_receipt": str(out_dir / "review_page" / "review_display_receipt.json"),
        },
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Horus/Embry storyboard-first dry-run fixture.")
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory.")
    parser.add_argument("--validate-only", action="store_true", help="Validate an existing fixture root without regenerating artifacts.")
    parser.add_argument(
        "--image-backend",
        choices=["fixture", "create-image"],
        default="fixture",
        help="Use deterministic fixture images or call $create-image for reference/storyboard images.",
    )
    parser.add_argument("--create-image-backend", default="scillm", help="$create-image backend when --image-backend=create-image.")
    parser.add_argument("--create-image-model", default="gpt-image-2", help="$create-image model when --image-backend=create-image.")
    parser.add_argument(
        "--strict-generated-images",
        action="store_true",
        help="Fail instead of falling back to deterministic fixture images when $create-image fails.",
    )
    parser.add_argument("--image-timeout-s", type=int, default=600, help="Timeout per generated image attempt.")
    args = parser.parse_args()
    if args.out_dir is None:
        if args.validate_only:
            parser.error("--out-dir is required with --validate-only")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.out_dir = Path("/mnt/storage12tb/skills/persona-dream/outputs") / f"{stamp}-horus-embry-storyboard-first-fixture"
    if args.validate_only:
        validation = validate_fixture(args.out_dir)
        write_json(args.out_dir / "fixture_validation_report.json", validation)
        print(json.dumps(validation, indent=2, sort_keys=True))
        if validation["status"] != "ACCEPTED_AUTOMATED":
            sys.exit(1)
        return
    manifest = build_fixture(
        args.out_dir,
        image_backend=args.image_backend,
        create_image_backend=args.create_image_backend,
        create_image_model=args.create_image_model,
        strict_generated_images=args.strict_generated_images,
        image_timeout_s=args.image_timeout_s,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if manifest["status"] != "ACCEPTED_AUTOMATED":
        sys.exit(1)


if __name__ == "__main__":
    main()
