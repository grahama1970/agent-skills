#!/usr/bin/env python3
"""Convert an accepted Persona Dream storyboard packet into Kling dry-run artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

try:
    import jsonschema
except ModuleNotFoundError:
    jsonschema = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/kling_scene_packet.schema.json"
TOKEN_RE = re.compile(r"<<<(?:image_[0-9]+|element_[a-z0-9_]+)>>>")


def validate_scene_packet(scene_packet: dict[str, Any]) -> str:
    if jsonschema is not None and SCHEMA_PATH.exists():
        jsonschema.Draft202012Validator(read_json(SCHEMA_PATH)).validate(scene_packet)
        return "jsonschema"
    blockers: list[str] = []
    expected_values = {
        "schema": "kling.scene_packet.v1",
        "status": "GENERATED_UNREVIEWED",
        "provider": "kling",
        "model": "kling-v3-omni",
        "mode": "std",
        "aspect_ratio": "16:9",
        "duration_s": 10.0,
        "paid_call_authorized": False,
    }
    for field, expected in expected_values.items():
        if scene_packet.get(field) != expected:
            blockers.append(f"BLOCKED_KLING_SCENE_PACKET_FIELD_{field.upper()}")
    required_fields = [
        "cost_estimate",
        "image_list",
        "multi_prompt",
        "negative_prompt",
        "provider_dry_run_fields",
        "storage_plan",
        "work_backwards_chain",
    ]
    for field in required_fields:
        if field not in scene_packet:
            blockers.append(f"BLOCKED_KLING_SCENE_PACKET_MISSING_{field.upper()}")
    provider_fields = scene_packet.get("provider_dry_run_fields", {})
    if provider_fields.get("submitted") is not False:
        blockers.append("BLOCKED_PROVIDER_DRY_RUN_SUBMITTED_NOT_FALSE")
    if provider_fields.get("external_task_id") is not None:
        blockers.append("BLOCKED_PROVIDER_DRY_RUN_EXTERNAL_TASK_ID_PRESENT")
    if len(scene_packet.get("image_list", [])) != 4:
        blockers.append("BLOCKED_KLING_SCENE_PACKET_IMAGE_LIST_COUNT")
    if len(scene_packet.get("multi_prompt", [])) != 4:
        blockers.append("BLOCKED_KLING_SCENE_PACKET_MULTI_PROMPT_COUNT")
    if blockers:
        raise ValueError(";".join(blockers))
    return "structural_fallback"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"not a PNG file: {path}")
    return struct.unpack(">II", header[16:24])


def accepted_frame(panel: dict[str, Any], role: str) -> dict[str, Any]:
    frame = panel.get(role, {}).get("accepted_frame")
    if not isinstance(frame, dict):
        raise ValueError(f"{panel.get('panel_id')} missing {role}.accepted_frame")
    return frame


def status_for_role(role: str) -> str:
    return "ACCEPTED_START_FRAME" if role == "start_frame" else "ACCEPTED_END_FRAME"


def build_media_lock(packet: dict[str, Any], storyboard_path: Path) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    blockers: list[str] = []
    for panel in packet["panels"]:
        panel_id = panel["panel_id"]
        for role in ("start_frame", "end_frame"):
            frame = accepted_frame(panel, role)
            path = Path(frame["path"])
            declared_sha = frame.get("sha256")
            observed_sha = sha256_file(path) if path.exists() else None
            width = height = None
            byte_size = None
            if path.exists():
                width, height = png_dimensions(path)
                byte_size = path.stat().st_size
            expected_status = status_for_role(role)
            identity = frame.get("identity_continuity_review") or {}
            frame_blockers = []
            if not path.exists():
                frame_blockers.append("BLOCKED_ACCEPTED_FRAME_MISSING")
            if not declared_sha:
                frame_blockers.append("BLOCKED_ACCEPTED_FRAME_HASH_MISSING")
            if observed_sha and declared_sha != observed_sha:
                frame_blockers.append("BLOCKED_ACCEPTED_FRAME_HASH_MISMATCH")
            if (width, height) != (1536, 864):
                frame_blockers.append("BLOCKED_ACCEPTED_FRAME_DIMENSIONS_INVALID")
            if frame.get("status") != expected_status:
                frame_blockers.append("BLOCKED_ACCEPTED_FRAME_STATUS_INVALID")
            if identity.get("status") != "PASS":
                frame_blockers.append("BLOCKED_ACCEPTED_FRAME_IDENTITY_NOT_PASS")
            blockers.extend(frame_blockers)
            time_s = panel["time_range"]["start_s"] if role == "start_frame" else panel["time_range"]["end_s"]
            assets.append(
                {
                    "asset_id": f"{panel_id}.{role}",
                    "panel_id": panel_id,
                    "frame_role": role,
                    "time_s": float(time_s),
                    "role": "accepted_storyboard_frame",
                    "path": str(path),
                    "provider_accessible_url": None,
                    "sha256": declared_sha,
                    "observed_sha256": observed_sha,
                    "width": width,
                    "height": height,
                    "mime": "image/png",
                    "byte_size": byte_size,
                    "identity_continuity_status": identity.get("status"),
                    "status": "LOCKED_LOCAL_ONLY" if not frame_blockers else "BLOCKED",
                    "blockers": frame_blockers,
                }
            )
    return {
        "schema": "persona_dream.kling.media_lock_manifest.v1",
        "status": "PASS_MEDIA_LOCK" if not blockers and len(assets) == 8 else "BLOCKED_MEDIA_LOCK",
        "storyboard_packet": str(storyboard_path),
        "accepted_frame_count": len(assets),
        "required_asset_count": 8,
        "assets": assets,
        "blockers": sorted(set(blockers)),
        "notes": [
            "All eight accepted start/end frames are locked here.",
            "Only the four start frames are provider-facing image_list anchors by default.",
        ],
    }


def build_reference_pack_audit(packet: dict[str, Any]) -> dict[str, Any]:
    refs = packet.get("identity_reference_assets", {})
    elements = [
        {
            "element_id": "element_embry_v1",
            "token": "<<<element_embry>>>",
            "type": "character_reference",
            "source_asset_ids": ["embry_character_sheet"],
            "reference_pack_status": "DRAFT_CONTACT_SHEET_SOURCE_ONLY",
            "description": "Embry, adult woman surfer, brown hair, navy rashguard/polo continuity, controlled under heat and glare.",
            "do_not_change": [
                "do not change Embry into a male surfer",
                "do not change brown hair",
                "do not change navy rashguard/polo continuity",
                "do not remove or hide Embry",
            ],
            "allowed_variation": ["wet hair movement", "subtle expression changes", "natural salt spray"],
            "ignore": ["contact sheet grid", "labels", "borders", "reference layout artifacts"],
            "live_blockers": ["BLOCKED_CHARACTER_ELEMENT_PACK_NOT_SPLIT_INTO_2_TO_4_IMAGES"],
            "source_assets": refs.get("Embry", []),
        },
        {
            "element_id": "element_kai_v1",
            "token": "<<<element_kai>>>",
            "type": "character_reference",
            "source_asset_ids": ["kai_character_sheet"],
            "reference_pack_status": "DRAFT_CONTACT_SHEET_SOURCE_ONLY",
            "description": "Kai Akana, young Hawaiian male surfer, curly dark hair, black rashguard, calm and lineup-aware.",
            "do_not_change": [
                "do not replace Kai with a generic surfer",
                "do not remove Kai where required",
                "do not change black rashguard continuity",
            ],
            "allowed_variation": ["wet hair movement", "subtle stance changes", "natural surf posture"],
            "ignore": ["contact sheet grid", "labels", "borders", "reference layout artifacts"],
            "live_blockers": ["BLOCKED_CHARACTER_ELEMENT_PACK_NOT_SPLIT_INTO_2_TO_4_IMAGES"],
            "source_assets": refs.get("Kai", []),
        },
        {
            "element_id": "element_kahaluu_lava_reef_v1",
            "token": "<<<element_kahaluu_lava_reef>>>",
            "type": "scene_environment",
            "source_asset_ids": [],
            "reference_pack_status": "BLOCKED_ENVIRONMENT_ELEMENT_REFERENCES_MISSING",
            "description": "Kahaluu Bay / Kona Coast public reef break, clear shallow water over dark lava reef, hot glare, public lineup pressure.",
            "do_not_change": [
                "do not turn into a private empty beach",
                "do not remove the lava reef boundary",
                "do not turn into a generic tropical postcard",
                "do not turn the water into a pool or sandbar",
            ],
            "allowed_variation": ["water shimmer", "small swell movement", "spray", "glare"],
            "ignore": [],
            "live_blockers": ["BLOCKED_ENVIRONMENT_ELEMENT_REFERENCES_MISSING"],
            "source_assets": [],
        },
    ]
    return {
        "schema": "persona_dream.kling.reference_pack_audit.v1",
        "status": "GENERATED_WITH_LIVE_BLOCKERS",
        "elements": elements,
        "dry_run_blockers": [],
        "live_blockers": sorted({blocker for element in elements for blocker in element["live_blockers"]}),
    }


def provider_text(panel: dict[str, Any], image_token: str) -> str:
    prompt = (
        f"{panel['panel_id']} {panel['time_range']['start_s']:.1f}-{panel['time_range']['end_s']:.1f}s. "
        f"Use storyboard anchor {image_token} with <<<element_embry>>>, <<<element_kai>>>, and "
        "<<<element_kahaluu_lava_reef>>>. "
        f"{panel['action']} "
        f"Camera stays {panel['camera']['height']}, {panel['camera']['movement']}; "
        f"composition: {panel['camera']['composition']} "
        f"Acting beats: {' '.join(panel.get('acting_beats') or [])} "
        "Keep faces identity-readable and preserve public reef lineup etiquette. "
        "Native ambience and foley only unless voice status is later accepted."
    )
    if panel.get("dialogue"):
        prompt += f" Text-only cue, not live voiced audio: {panel['dialogue']}"
    return prompt


def build_scene_packet(
    packet: dict[str, Any],
    media_lock: dict[str, Any],
    reference_audit: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    panels = packet["panels"]
    image_list = []
    for index, panel in enumerate(panels, start=1):
        frame = accepted_frame(panel, "start_frame")
        panel_id = panel["panel_id"]
        image_list.append(
            {
                "token": f"<<<image_{index}>>>",
                "asset_id": f"{panel_id}.start_frame",
                "panel_id": panel_id,
                "path": frame["path"],
                "role": "storyboard_visual_anchor",
                "status": "LOCKED_LOCAL_ONLY",
                "hash": frame["sha256"],
                "sha256": frame["sha256"],
            }
        )
    multi_prompt = []
    for index, panel in enumerate(panels):
        token = f"<<<image_{index + 1}>>>"
        dialogue = []
        if panel.get("dialogue"):
            dialogue = [{"speaker": "Kai", "status": "VOICE_TEXT_ONLY", "text": panel["dialogue"]}]
        multi_prompt.append(
            {
                "index": index,
                "duration_s": float(panel["time_range"]["end_s"] - panel["time_range"]["start_s"]),
                "visual_anchor": token,
                "image_status": "LOCKED_LOCAL_ONLY",
                "voice_status": "VOICE_TEXT_ONLY" if dialogue else "NO_DIALOGUE",
                "prompt": provider_text(panel, token),
                "dialogue": dialogue,
                "provider_text": provider_text(panel, token),
                "cinematography": {
                    "shot_size": panel["camera"].get("shot_code", "MWS"),
                    "lens": panel["camera"].get("lens", "28-35mm waterline"),
                    "camera_mount": panel["camera"].get("camera_equipment", "water housing"),
                    "camera_movement": panel["camera"].get("movement", "stable waterline drift"),
                    "composition": panel["camera"].get("composition", "identity-readable surf composition"),
                    "focus_behavior": "identity-readable faces, no spray/glare occlusion",
                    "lighting": panel.get("lighting", {}).get("quality", "hot daylight glare"),
                    "color_grade": "realistic coastal daylight, clear water, dark lava reef",
                    "atmosphere": "hot humid Kona surf glare, salt spray, public lineup pressure",
                    "temporal_pacing": "four restrained 2.5 second beats within a 10 second dry run",
                    "environment_lock": "Kahaluu Bay / Kona Coast public lava reef break",
                    "director_note": "Embry keeps agency; Kai remains restrained, not a rescuer.",
                },
            }
        )
    provider_body = {
        "model": "kling-v3-omni",
        "mode": "std",
        "aspect_ratio": "16:9",
        "duration": 10,
        "sound": "on",
        "multi_shot": True,
        "shot_type": "customize",
        "paid_call_authorized": False,
        "submitted": False,
        "image_list": [{"image": None, "token": item["token"], "source_path": item["path"]} for item in image_list],
        "element_list": [
            {
                "token": element["token"],
                "type": element["type"],
                "description": element["description"],
                "source_assets": element["source_asset_ids"],
            }
            for element in reference_audit["elements"]
        ],
        "multi_prompt": [
            {"index": item["index"], "duration": item["duration_s"], "prompt": item["provider_text"]}
            for item in multi_prompt
        ],
        "negative_prompt": [
            "no generic replacement surfers",
            "do not change Embry into a male surfer",
            "do not remove Embry",
            "do not remove Kai",
            "do not hide faces with spray, glare, board, or camera angle",
            "no contact sheet, grid, collage, reference board, UI screenshot, captions, labels, arrows, or name tags",
            "no private empty beach",
            "no reckless heroic takeoff",
            "do not violate public lineup etiquette",
            "do not turn lava reef into sandbar or pool",
            "do not drift into a generic tropical surf postcard",
        ],
        "callback_url": None,
        "external_task_id": None,
    }
    voice_status = {
        "status": "VOICE_TEXT_ONLY" if any(item.get("dialogue") for item in multi_prompt) else "NO_DIALOGUE",
        "ambience_and_foley": "ON",
        "spoken_dialogue_live_ready": False,
        "provider_voice_ids_locked": False,
        "provider_voice_ids": [],
        "live_blockers": ["BLOCKED_PROVIDER_VOICE_IDS_MISSING"],
    }
    live_call_blockers = [
        "BLOCKED_MANUAL_VISUAL_ACCEPTANCE_MISSING",
        "BLOCKED_PROVIDER_SCHEMA_UNVERIFIED",
        "BLOCKED_PROVIDER_ACCESSIBLE_URLS_MISSING",
        "BLOCKED_CHARACTER_ELEMENT_PACK_NOT_SPLIT_INTO_2_TO_4_IMAGES",
        "BLOCKED_ENVIRONMENT_ELEMENT_REFERENCES_MISSING",
        "BLOCKED_PROVIDER_VOICE_IDS_MISSING",
        "BLOCKED_COST_ESTIMATE_UNVERIFIED",
        "BLOCKED_PAID_CALL_NOT_AUTHORIZED",
    ]
    return {
        "schema": "kling.scene_packet.v1",
        "run_id": "persona-dream-kahaluu-10s-dryrun-001",
        "status": "GENERATED_UNREVIEWED",
        "provider": "kling",
        "model": "kling-v3-omni",
        "mode": "std",
        "aspect_ratio": "16:9",
        "duration_s": 10.0,
        "paid_call_authorized": False,
        "submitted": False,
        "external_task_id": None,
        "live_submit_status": "DRY_RUN_NOT_LIVE_SUBMITTABLE",
        "cost_estimate": {
            "status": "DRY_RUN_ESTIMATE_UNVERIFIED",
            "currency": "credits",
            "duration_s": 10.0,
            "selected_mode": "std",
            "rate_credits_per_s": 9,
            "estimated_credits": 90,
            "formula": "duration_s * rate_credits_per_s; provider pricing requires current-account verification",
            "docs_checked": ["pending_current_provider_pricing_schema"],
        },
        "callback_url": None,
        "polling_plan": "Dry run only. If later approved, poll provider task endpoint every 15s for at most 80 attempts and persist terminal raw response.",
        "storage_plan": {
            "download_output_to": str(output_root / "outputs/kling_output.mp4"),
            "ffprobe_json": str(output_root / "outputs/ffprobe.json"),
            "frame_contact_sheet": str(output_root / "outputs/frame_contact_sheet.jpg"),
            "raw_response_json": str(output_root / "outputs/provider_response.json"),
        },
        "retry_policy": "No live provider attempts in this round. Allow at most two dry-run packet revisions after review.",
        "audio_strategy": "Ambience and foley are on. Kai cue is VOICE_TEXT_ONLY because no provider voice IDs are locked.",
        "voice_status": voice_status,
        "element_list": reference_audit["elements"],
        "image_list": image_list,
        "voice_list": [],
        "voice_examples": [
            {
                "speaker": "Kai",
                "status": "VOICE_TEXT_ONLY",
                "source": "Storyboard text cue exists; no provider voice_id exists for this dry-run packet.",
            }
        ],
        "multi_prompt": multi_prompt,
        "negative_prompt": provider_body["negative_prompt"],
        "provider_dry_run_fields": provider_body,
        "source_artifacts": {
            "storyboard_packet": media_lock["storyboard_packet"],
            "media_lock_manifest": "storyboard_media_lock_manifest.json",
            "reference_pack_audit": "kling_reference_pack_audit.json",
            "token_binding_linter": "token_binding_linter_receipt.json",
            "provider_payload_mapping_receipt": "provider_payload_mapping_receipt.json",
            "provider_final_gate": "provider_final_gate_receipt.json",
        },
        "live_call_blockers": live_call_blockers,
        "claims": {
            "proves": [
                "accepted storyboard evidence was distilled into a local dry-run Kling scene packet",
                "all provider prompt tokens are declared",
                "paid_call_authorized is false",
                "submitted is false",
                "no provider request was submitted",
            ],
            "does_not_prove": [
                "current Kling provider schema compatibility",
                "provider-accessible media URLs",
                "reference upload readiness",
                "voice readiness",
                "cost approval",
                "manual acceptance",
                "live Kling generation",
            ],
        },
        "live_call_block_reason": (
            "GENERATED_UNREVIEWED dry-run only: manual review missing, provider schema unverified, "
            "provider-accessible URLs missing, reference packs not split into clean Element images, "
            "environment references missing, provider voice IDs missing, cost estimate unverified, "
            "and paid-call authorization is false."
        ),
        "work_backwards_chain": [
            "accepted_storyboard_packet",
            "storyboard_media_lock_manifest",
            "kling_reference_pack_audit",
            "kling_context_distiller",
            "token_binding_linter",
            "kling_scene_packet_dry_run",
            "provider_payload_mapping_receipt",
            "provider_final_gate",
        ],
    }


def token_lint(scene_packet: dict[str, Any], reference_audit: dict[str, Any]) -> dict[str, Any]:
    declared = {item["token"] for item in scene_packet["image_list"]}
    declared.update(element["token"] for element in reference_audit["elements"])
    text_blob = json.dumps(
        {
            "multi_prompt": scene_packet["multi_prompt"],
            "provider_dry_run_fields": scene_packet["provider_dry_run_fields"],
        },
        sort_keys=True,
    )
    referenced = set(TOKEN_RE.findall(text_blob))
    missing = sorted(referenced - declared)
    unused = sorted(declared - referenced)
    ranges = []
    current = 0.0
    timing_blockers = []
    for prompt in scene_packet["multi_prompt"]:
        duration = float(prompt["duration_s"])
        start = current
        end = current + duration
        ranges.append({"index": prompt["index"], "start_s": start, "end_s": end, "duration_s": duration})
        current = end
    if abs(current - scene_packet["duration_s"]) > 0.0001:
        timing_blockers.append("BLOCKED_MULTI_PROMPT_TIMING")
    blockers = []
    if missing:
        blockers.append("BLOCKED_TOKEN_BINDING")
    blockers.extend(timing_blockers)
    return {
        "schema": "persona_dream.kling.token_binding_linter_receipt.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "declared_tokens": sorted(declared),
        "referenced_tokens": sorted(referenced),
        "missing_tokens": missing,
        "unused_tokens": unused,
        "time_ranges": ranges,
        "total_duration_s": current,
        "expected_duration_s": scene_packet["duration_s"],
        "blockers": blockers,
    }


def build_distiller_receipt(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "persona_dream.kling.context_distiller_receipt.v1",
        "status": "PASS_DISTILLED",
        "distill_into_kling": {
            "who": "Embry and Kai",
            "where": "Kahaluu Bay / Kona Coast / lava reef / public lineup",
            "when": "10 seconds, four timed 2.5 second beats",
            "what_moves": "characters, boards, water, swell, background lineup, glare, spray",
            "camera": "waterline, identity-readable, continuity-preserving",
            "what_not_to_change": "identity, wardrobe, surf etiquette, lava reef, public lineup, no generic surfers",
            "audio_state": "ambience/foley on; dialogue/voice explicit as VOICE_TEXT_ONLY",
            "provider_state": "dry run only; no paid or live call",
        },
        "omitted_from_provider_prompt": [
            "raw memory residue",
            "serialized story/script contract JSON",
            "interaction matrices",
            "Tau receipts",
            "reviewer prose",
            "failed/rejected attempts",
            "UI screenshots",
            "internal filesystem paths except dry-run traceability fields",
        ],
        "source_panel_count": packet.get("panel_count"),
    }


def write_ksml(path: Path, scene_packet: dict[str, Any], reference_audit: dict[str, Any]) -> None:
    doc = {
        "schema": "ksml.v0.1",
        "project_id": scene_packet["run_id"],
        "provider": scene_packet["provider"],
        "model": scene_packet["model"],
        "status": scene_packet["status"],
        "duration_s": scene_packet["duration_s"],
        "aspect_ratio": scene_packet["aspect_ratio"],
        "paid_call_authorized": scene_packet["paid_call_authorized"],
        "elements": reference_audit["elements"],
        "images": scene_packet["image_list"],
        "shots": [
            {
                "index": item["index"],
                "duration_s": item["duration_s"],
                "visual_anchor": item["visual_anchor"],
                "prompt": item["provider_text"],
                "voice_status": item["voice_status"],
                "cinematography": item["cinematography"],
            }
            for item in scene_packet["multi_prompt"]
        ],
        "negative_prompt": scene_packet["negative_prompt"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storyboard-packet", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    storyboard_path = args.storyboard_packet.resolve()
    output_root = args.output_root.resolve()
    packet = read_json(storyboard_path)
    if packet.get("accepted") is not True or packet.get("panel_count") != 4:
        raise SystemExit("storyboard packet must be accepted with panel_count=4")

    media_lock = build_media_lock(packet, storyboard_path)
    reference_audit = build_reference_pack_audit(packet)
    distiller = build_distiller_receipt(packet)
    scene_packet = build_scene_packet(packet, media_lock, reference_audit, output_root)
    token_receipt = token_lint(scene_packet, reference_audit)

    scene_packet_validation = validate_scene_packet(scene_packet)
    provider_mapping = {
        "schema": "persona_dream.kling.provider_payload_mapping_receipt.v1",
        "status": "DRY_RUN_NOT_LIVE_SUBMITTABLE",
        "submitted": False,
        "paid_call_authorized": False,
        "external_task_id": None,
        "provider_schema_verified": False,
        "request_body_path": "provider_payload_mapping/kling_request_body.dry_run.json",
        "live_blockers": [
            "BLOCKED_PROVIDER_SCHEMA_UNVERIFIED",
            "BLOCKED_PROVIDER_ACCESSIBLE_URLS_MISSING",
            "BLOCKED_PAID_CALL_NOT_AUTHORIZED",
        ],
        "claims": {
            "proves": [
                "provider-facing request body was mapped from kling.scene_packet.v1",
                "submitted is false",
                "paid_call_authorized is false",
            ],
            "does_not_prove": [
                "current Kling provider schema compatibility",
                "provider-accessible media URLs",
                "live Kling generation",
            ],
        },
    }
    final_gate_live_blockers = sorted(set(scene_packet["live_call_blockers"]))
    final_gate = {
        "schema": "persona_dream.kling.provider_final_gate_receipt.v1",
        "status": "DRY_RUN_NOT_LIVE_SUBMITTABLE",
        "submitted": False,
        "paid_call_authorized": False,
        "manual_acceptance_status": "BLOCKED_MANUAL_REVIEW_MISSING",
        "live_call_blockers": final_gate_live_blockers,
        "live_blockers": final_gate_live_blockers,
    }

    paths = {
        "media_lock_manifest": output_root / "storyboard_media_lock_manifest.json",
        "reference_pack_audit": output_root / "kling_reference_pack_audit.json",
        "context_distiller": output_root / "kling_context_distiller_receipt.json",
        "scene_packet": output_root / "kling_scene_packet.json",
        "token_binding_linter": output_root / "token_binding_linter_receipt.json",
        "provider_request_body": output_root / "provider_payload_mapping/kling_request_body.dry_run.json",
        "provider_mapping_receipt": output_root / "provider_payload_mapping_receipt.json",
        "provider_final_gate": output_root / "provider_final_gate_receipt.json",
        "ksml": output_root / "project.ksml",
        "summary": output_root / "phase08_kling_conversion_summary.json",
    }
    write_json(paths["media_lock_manifest"], media_lock)
    write_json(paths["reference_pack_audit"], reference_audit)
    write_json(paths["context_distiller"], distiller)
    write_json(paths["scene_packet"], scene_packet)
    write_json(paths["token_binding_linter"], token_receipt)
    write_json(paths["provider_request_body"], scene_packet["provider_dry_run_fields"])
    write_json(paths["provider_mapping_receipt"], provider_mapping)
    write_json(paths["provider_final_gate"], final_gate)
    write_ksml(paths["ksml"], scene_packet, reference_audit)

    status = "GENERATED_UNREVIEWED" if (
        media_lock["status"] == "PASS_MEDIA_LOCK" and token_receipt["status"] == "PASS"
    ) else "BLOCKED"
    summary = {
        "schema": "persona_dream.kling.phase08_conversion_summary.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "phase_boundary": scene_packet["work_backwards_chain"],
        "mocked": False,
        "live": False,
        "storyboard_source_live": True,
        "submitted": False,
        "paid_call_authorized": False,
        "accepted_frame_count": media_lock["accepted_frame_count"],
        "provider_facing_image_count": len(scene_packet["image_list"]),
        "element_count": len(reference_audit["elements"]),
        "multi_prompt_count": len(scene_packet["multi_prompt"]),
        "token_linter_status": token_receipt["status"],
        "media_lock_status": media_lock["status"],
        "scene_packet_schema_valid": True,
        "scene_packet_schema_validation": scene_packet_validation,
        "artifacts": {key: str(path) for key, path in paths.items() if key != "summary"},
        "claims": {
            "proves": [
                "accepted storyboard was converted into local dry-run Kling artifacts",
                "all eight accepted frames are represented in the media lock manifest",
                "four start frames are selected as provider-facing storyboard anchors",
                "scene packet passed the available Kling scene packet validation gate",
                "token binding and timing linter passed",
                "no live provider submission was performed",
            ],
            "does_not_prove": [
                "manual acceptance",
                "current Kling provider schema compatibility",
                "provider-accessible URLs",
                "live reference upload readiness",
                "voice readiness",
                "cost approval",
                "live Kling generation",
            ],
        },
    }
    write_json(paths["summary"], summary)
    print(json.dumps(summary if args.json else {"status": status, "summary": str(paths["summary"])}, indent=2, sort_keys=True))
    return 0 if status == "GENERATED_UNREVIEWED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
