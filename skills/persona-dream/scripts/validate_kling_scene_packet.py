#!/usr/bin/env python3
"""Validate a Persona Dream Kling dry-run scene packet.

This validator is intentionally local-only. It proves dry-run packet shape,
media locks, token binding, timing coverage, and live-submission blockers. It
does not call Kling, upload media, or prove current provider schema support.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_KLING_SCENE_PACKET_DRY_RUN"
BLOCKED_STATUS = "BLOCKED_KLING_SCENE_PACKET_DRY_RUN"
TOKEN_RE = re.compile(r"<<<(?:image_[0-9]+|element_[a-z0-9_]+|video_[0-9]+)>>>")
REQUIRED_ELEMENT_TOKENS = {
    "<<<element_embry>>>",
    "<<<element_kai>>>",
    "<<<element_kahaluu_lava_reef>>>",
}


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


def add_blocker(blockers: list[dict[str, Any]], status: str, field: str, detail: str = "") -> None:
    blockers.append({"status": status, "field": field, "detail": detail})


def resolve_sidecar(scene_path: Path, packet: dict[str, Any], key: str) -> Path | None:
    source_artifacts = packet.get("source_artifacts")
    if not isinstance(source_artifacts, dict):
        return None
    raw = source_artifacts.get(key)
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        return path
    return scene_path.parent / path


def load_sidecar(
    scene_path: Path,
    packet: dict[str, Any],
    key: str,
    blockers: list[dict[str, Any]],
    blocker_status: str,
) -> tuple[Path | None, dict[str, Any] | None]:
    path = resolve_sidecar(scene_path, packet, key)
    if path is None:
        add_blocker(blockers, blocker_status, f"source_artifacts.{key}", "missing sidecar path")
        return None, None
    if not path.exists():
        add_blocker(blockers, blocker_status, f"source_artifacts.{key}", f"missing sidecar file: {path}")
        return path, None
    try:
        return path, read_json(path)
    except json.JSONDecodeError as exc:
        add_blocker(blockers, blocker_status, f"source_artifacts.{key}", f"invalid JSON: {exc}")
        return path, None


def validate_schema_flags(packet: dict[str, Any], blockers: list[dict[str, Any]]) -> None:
    expected = {
        "schema": "kling.scene_packet.v1",
        "status": "GENERATED_UNREVIEWED",
        "provider": "kling",
        "model": "kling-v3-omni",
        "mode": "std",
        "aspect_ratio": "16:9",
        "duration_s": 10.0,
        "live_submit_status": "DRY_RUN_NOT_LIVE_SUBMITTABLE",
    }
    for field, expected_value in expected.items():
        if packet.get(field) != expected_value:
            add_blocker(
                blockers,
                "BLOCKED_KLING_SCENE_PACKET_SCHEMA",
                field,
                f"expected {expected_value!r}, observed {packet.get(field)!r}",
            )
    for field in ("cost_estimate", "storage_plan", "negative_prompt", "live_call_blockers"):
        if field not in packet:
            add_blocker(blockers, "BLOCKED_KLING_SCENE_PACKET_SCHEMA", field, "required field missing")
    claims = packet.get("claims")
    does_not_prove = claims.get("does_not_prove") if isinstance(claims, dict) else None
    if not isinstance(does_not_prove, list) or "live Kling generation" not in does_not_prove:
        add_blocker(
            blockers,
            "BLOCKED_KLING_SCENE_PACKET_SCHEMA",
            "claims.does_not_prove",
            "must include live Kling generation",
        )


def validate_dry_run_flags(packet: dict[str, Any], blockers: list[dict[str, Any]]) -> None:
    if packet.get("paid_call_authorized") is not False:
        add_blocker(
            blockers,
            "BLOCKED_PAID_CALL_AUTHORIZED_IN_DRY_RUN",
            "paid_call_authorized",
            "scene packet must keep paid_call_authorized=false",
        )
    if packet.get("submitted") is not False:
        add_blocker(
            blockers,
            "BLOCKED_PROVIDER_MAPPING_SUBMITTED_IN_DRY_RUN",
            "submitted",
            "scene packet must keep submitted=false",
        )
    if packet.get("external_task_id") is not None:
        add_blocker(
            blockers,
            "BLOCKED_PROVIDER_MAPPING_SUBMITTED_IN_DRY_RUN",
            "external_task_id",
            "dry-run packet must not have an external task id",
        )
    provider_fields = packet.get("provider_dry_run_fields")
    if not isinstance(provider_fields, dict):
        add_blocker(blockers, "BLOCKED_KLING_SCENE_PACKET_SCHEMA", "provider_dry_run_fields", "missing")
        return
    if provider_fields.get("paid_call_authorized") is not False:
        add_blocker(
            blockers,
            "BLOCKED_PAID_CALL_AUTHORIZED_IN_DRY_RUN",
            "provider_dry_run_fields.paid_call_authorized",
            "provider body must keep paid_call_authorized=false",
        )
    if provider_fields.get("submitted") is not False:
        add_blocker(
            blockers,
            "BLOCKED_PROVIDER_MAPPING_SUBMITTED_IN_DRY_RUN",
            "provider_dry_run_fields.submitted",
            "provider body must keep submitted=false",
        )
    if provider_fields.get("external_task_id") is not None:
        add_blocker(
            blockers,
            "BLOCKED_PROVIDER_MAPPING_SUBMITTED_IN_DRY_RUN",
            "provider_dry_run_fields.external_task_id",
            "provider body must not have an external task id",
        )


def validate_media_lock(media_lock: dict[str, Any] | None, blockers: list[dict[str, Any]]) -> dict[str, Any]:
    facts = {"accepted_frame_count": 0, "media_lock_status": None}
    if not isinstance(media_lock, dict):
        add_blocker(blockers, "BLOCKED_MEDIA_LOCK", "media_lock_manifest", "missing or invalid")
        return facts
    assets = media_lock.get("assets")
    facts["accepted_frame_count"] = int(media_lock.get("accepted_frame_count") or 0)
    facts["media_lock_status"] = media_lock.get("status")
    if media_lock.get("status") != "PASS_MEDIA_LOCK":
        add_blocker(blockers, "BLOCKED_MEDIA_LOCK", "media_lock_manifest.status", str(media_lock.get("status")))
    if media_lock.get("accepted_frame_count") != 8 or media_lock.get("required_asset_count") != 8:
        add_blocker(blockers, "BLOCKED_MEDIA_LOCK", "media_lock_manifest.accepted_frame_count", "expected 8")
    if not isinstance(assets, list) or len(assets) != 8:
        add_blocker(blockers, "BLOCKED_MEDIA_LOCK", "media_lock_manifest.assets", "expected 8 assets")
        return facts
    for index, asset in enumerate(assets):
        prefix = f"media_lock_manifest.assets[{index}]"
        if not isinstance(asset, dict):
            add_blocker(blockers, "BLOCKED_MEDIA_LOCK", prefix, "asset is not an object")
            continue
        if asset.get("role") != "accepted_storyboard_frame":
            add_blocker(blockers, "BLOCKED_MEDIA_LOCK", f"{prefix}.role", str(asset.get("role")))
        if not isinstance(asset.get("sha256"), str) or not asset["sha256"].startswith("sha256:"):
            add_blocker(blockers, "BLOCKED_MEDIA_LOCK", f"{prefix}.sha256", "missing sha256")
        if asset.get("width") != 1536 or asset.get("height") != 864:
            add_blocker(blockers, "BLOCKED_MEDIA_LOCK", f"{prefix}.dimensions", "expected 1536x864")
        if asset.get("status") != "LOCKED_LOCAL_ONLY":
            add_blocker(blockers, "BLOCKED_MEDIA_LOCK", f"{prefix}.status", str(asset.get("status")))
    return facts


def validate_tokens_and_timing(packet: dict[str, Any], media_lock: dict[str, Any] | None, blockers: list[dict[str, Any]]) -> dict[str, Any]:
    facts = {
        "provider_facing_image_count": 0,
        "element_count": 0,
        "multi_prompt_count": 0,
        "token_binding_status": "PASS",
    }
    image_list = packet.get("image_list")
    element_list = packet.get("element_list")
    multi_prompt = packet.get("multi_prompt")
    if not isinstance(image_list, list) or len(image_list) != 4:
        add_blocker(blockers, "BLOCKED_TOKEN_BINDING", "image_list", "expected four provider-facing storyboard anchors")
        image_list = image_list if isinstance(image_list, list) else []
    if not isinstance(element_list, list) or len(element_list) < 3:
        add_blocker(blockers, "BLOCKED_TOKEN_BINDING", "element_list", "expected Embry, Kai, and environment Elements")
        element_list = element_list if isinstance(element_list, list) else []
    if not isinstance(multi_prompt, list) or len(multi_prompt) != 4:
        add_blocker(blockers, "BLOCKED_MULTI_PROMPT_TIMING", "multi_prompt", "expected four timed prompts")
        multi_prompt = multi_prompt if isinstance(multi_prompt, list) else []
    facts["provider_facing_image_count"] = len(image_list)
    facts["element_count"] = len(element_list)
    facts["multi_prompt_count"] = len(multi_prompt)

    image_tokens = [item.get("token") for item in image_list if isinstance(item, dict)]
    element_tokens = [item.get("token") for item in element_list if isinstance(item, dict)]
    video_list = packet.get("video_list")
    video_list = video_list if isinstance(video_list, list) else []
    video_tokens = [item.get("token") for item in video_list if isinstance(item, dict)]
    facts["video_count"] = len(video_list)
    if len(video_tokens) != len(set(video_tokens)):
        add_blocker(blockers, "BLOCKED_TOKEN_BINDING", "video_list.token", "video tokens must be unique")
    declared_tokens = {
        token for token in image_tokens + element_tokens + video_tokens if isinstance(token, str)
    }
    if len(image_tokens) != len(set(image_tokens)):
        add_blocker(blockers, "BLOCKED_TOKEN_BINDING", "image_list.token", "image tokens must be unique")
    if len(element_tokens) != len(set(element_tokens)):
        add_blocker(blockers, "BLOCKED_TOKEN_BINDING", "element_list.token", "element tokens must be unique")
    missing_required = sorted(REQUIRED_ELEMENT_TOKENS - set(element_tokens))
    if missing_required:
        add_blocker(blockers, "BLOCKED_TOKEN_BINDING", "element_list", f"missing required Elements: {missing_required}")

    media_asset_ids = set()
    if isinstance(media_lock, dict) and isinstance(media_lock.get("assets"), list):
        media_asset_ids = {str(asset.get("asset_id")) for asset in media_lock["assets"] if isinstance(asset, dict)}
    for index, image in enumerate(image_list):
        if not isinstance(image, dict):
            continue
        asset_id = image.get("asset_id")
        if asset_id not in media_asset_ids:
            add_blocker(blockers, "BLOCKED_TOKEN_BINDING", f"image_list[{index}].asset_id", "not found in media lock")

    referenced_tokens = set(TOKEN_RE.findall(json.dumps(multi_prompt, sort_keys=True)))
    missing_tokens = sorted(referenced_tokens - declared_tokens)
    if missing_tokens:
        add_blocker(blockers, "BLOCKED_TOKEN_BINDING", "multi_prompt", f"missing referenced tokens: {missing_tokens}")

    current = 0.0
    ranges = []
    for index, prompt in enumerate(multi_prompt):
        if not isinstance(prompt, dict):
            add_blocker(blockers, "BLOCKED_MULTI_PROMPT_TIMING", f"multi_prompt[{index}]", "prompt is not an object")
            continue
        if isinstance(prompt.get("time_range_s"), list) and len(prompt["time_range_s"]) == 2:
            start = float(prompt["time_range_s"][0])
            end = float(prompt["time_range_s"][1])
            if abs(start - current) > 0.0001:
                add_blocker(blockers, "BLOCKED_MULTI_PROMPT_TIMING", f"multi_prompt[{index}].time_range_s", "gap or overlap")
            current = end
        else:
            duration = float(prompt.get("duration_s") or 0)
            start = current
            end = current + duration
            current = end
        if end <= start:
            add_blocker(blockers, "BLOCKED_MULTI_PROMPT_TIMING", f"multi_prompt[{index}]", "duration must be positive")
        ranges.append({"index": index, "start_s": start, "end_s": end})
    if abs(current - 10.0) > 0.0001 or abs(float(packet.get("duration_s") or 0) - 10.0) > 0.0001:
        add_blocker(blockers, "BLOCKED_MULTI_PROMPT_TIMING", "multi_prompt", "must cover exactly 0.0-10.0s")

    if any(blocker["status"] == "BLOCKED_TOKEN_BINDING" for blocker in blockers):
        facts["token_binding_status"] = "BLOCKED"
    facts["time_ranges"] = ranges
    return facts


def validate_video_list(packet: dict[str, Any], scene_path: Path, blockers: list[dict[str, Any]]) -> None:
    """Video references are optional; when declared they must be provable.

    Kling Omni supports <<<video_N>>> bound through video_list. A declared video
    reference is only meaningful if the file exists and its digest matches, so an
    unreadable or drifted reference blocks rather than passing as decoration.
    """
    video_list = packet.get("video_list")
    if video_list is None:
        return
    if not isinstance(video_list, list) or not video_list:
        add_blocker(blockers, "BLOCKED_TOKEN_BINDING", "video_list", "declared but empty or not a list")
        return
    for index, item in enumerate(video_list):
        prefix = f"video_list[{index}]"
        if not isinstance(item, dict):
            add_blocker(blockers, "BLOCKED_TOKEN_BINDING", prefix, "entry is not an object")
            continue
        token = item.get("token")
        if not isinstance(token, str) or not re.fullmatch(r"<<<video_[0-9]+>>>", token):
            add_blocker(blockers, "BLOCKED_TOKEN_BINDING", f"{prefix}.token", f"expected <<<video_N>>>, observed {token!r}")
        declared = item.get("sha256")
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            add_blocker(blockers, "BLOCKED_TOKEN_BINDING", f"{prefix}.path", "missing")
        else:
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = (scene_path.parent / candidate).resolve()
            if not candidate.is_file():
                add_blocker(blockers, "BLOCKED_TOKEN_BINDING", f"{prefix}.path", f"file not found: {candidate}")
            elif not isinstance(declared, str) or not declared.startswith("sha256:"):
                add_blocker(blockers, "BLOCKED_TOKEN_BINDING", f"{prefix}.sha256", "missing sha256")
            elif sha256_file(candidate) != declared:
                add_blocker(blockers, "BLOCKED_TOKEN_BINDING", f"{prefix}.sha256", "digest does not match file on disk")
        if item.get("provider_accessible_url"):
            add_blocker(
                blockers,
                "BLOCKED_PROVIDER_MAPPING_SUBMITTED_IN_DRY_RUN",
                f"{prefix}.provider_accessible_url",
                "dry run must not carry a provider-accessible video URL",
            )
        elif "BLOCKED_VIDEO_REFERENCE_NOT_PROVIDER_ACCESSIBLE_URL" not in (packet.get("live_call_blockers") or []):
            add_blocker(
                blockers,
                "BLOCKED_KLING_SCENE_PACKET_SCHEMA",
                "live_call_blockers",
                "video_list without a provider URL requires BLOCKED_VIDEO_REFERENCE_NOT_PROVIDER_ACCESSIBLE_URL",
            )


def validate_voice(packet: dict[str, Any], blockers: list[dict[str, Any]]) -> None:
    voice_status = packet.get("voice_status")
    if not isinstance(voice_status, dict):
        add_blocker(blockers, "BLOCKED_VOICE_STATUS_UNRESOLVED", "voice_status", "missing")
        return
    if voice_status.get("status") not in {"NO_DIALOGUE", "VOICE_TEXT_ONLY"}:
        add_blocker(
            blockers,
            "BLOCKED_VOICE_STATUS_UNRESOLVED",
            "voice_status.status",
            "expected NO_DIALOGUE or VOICE_TEXT_ONLY for dry run",
        )


def validate_provider_mapping(
    provider_mapping: dict[str, Any] | None,
    final_gate: dict[str, Any] | None,
    packet: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> None:
    if not isinstance(provider_mapping, dict):
        add_blocker(blockers, "BLOCKED_KLING_SCENE_PACKET_SCHEMA", "provider_payload_mapping", "missing")
    else:
        if provider_mapping.get("submitted") is not False:
            add_blocker(
                blockers,
                "BLOCKED_PROVIDER_MAPPING_SUBMITTED_IN_DRY_RUN",
                "provider_payload_mapping.submitted",
                "must be false",
            )
        if provider_mapping.get("paid_call_authorized") is not False:
            add_blocker(
                blockers,
                "BLOCKED_PAID_CALL_AUTHORIZED_IN_DRY_RUN",
                "provider_payload_mapping.paid_call_authorized",
                "must be false",
            )
        if provider_mapping.get("external_task_id") is not None:
            add_blocker(
                blockers,
                "BLOCKED_PROVIDER_MAPPING_SUBMITTED_IN_DRY_RUN",
                "provider_payload_mapping.external_task_id",
                "must be null",
            )
    if isinstance(final_gate, dict):
        packet_blockers = set(packet.get("live_call_blockers") or [])
        gate_blockers = set(final_gate.get("live_call_blockers") or final_gate.get("live_blockers") or [])
        if not packet_blockers.issubset(gate_blockers):
            add_blocker(
                blockers,
                "BLOCKED_KLING_SCENE_PACKET_SCHEMA",
                "provider_final_gate.live_call_blockers",
                "must include all scene_packet.live_call_blockers",
            )


def build_receipt(scene_path: Path) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    packet = read_json(scene_path)
    validate_schema_flags(packet, blockers)
    validate_dry_run_flags(packet, blockers)
    media_lock_path, media_lock = load_sidecar(scene_path, packet, "media_lock_manifest", blockers, "BLOCKED_MEDIA_LOCK")
    provider_mapping_path, provider_mapping = load_sidecar(
        scene_path,
        packet,
        "provider_payload_mapping_receipt",
        blockers,
        "BLOCKED_KLING_SCENE_PACKET_SCHEMA",
    )
    final_gate_path, final_gate = load_sidecar(
        scene_path,
        packet,
        "provider_final_gate",
        blockers,
        "BLOCKED_KLING_SCENE_PACKET_SCHEMA",
    )
    media_facts = validate_media_lock(media_lock, blockers)
    token_facts = validate_tokens_and_timing(packet, media_lock, blockers)
    validate_video_list(packet, scene_path, blockers)
    validate_voice(packet, blockers)
    validate_provider_mapping(provider_mapping, final_gate, packet, blockers)

    status = PASS_STATUS if not blockers else BLOCKED_STATUS
    return {
        "schema": "persona_dream.kling.scene_packet_validation_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "verdict": status,
        "scene_packet_path": str(scene_path),
        "scene_packet_sha256": sha256_file(scene_path),
        "media_lock_manifest_path": str(media_lock_path) if media_lock_path else None,
        "provider_payload_mapping_receipt_path": str(provider_mapping_path) if provider_mapping_path else None,
        "provider_final_gate_receipt_path": str(final_gate_path) if final_gate_path else None,
        "provider_live": False,
        "live_kling_call_started": False,
        "submitted": packet.get("submitted"),
        "paid_call_authorized": packet.get("paid_call_authorized"),
        "external_task_id": packet.get("external_task_id"),
        "accepted_frame_count": media_facts["accepted_frame_count"],
        "provider_facing_image_count": token_facts["provider_facing_image_count"],
        "element_count": token_facts["element_count"],
        "multi_prompt_count": token_facts["multi_prompt_count"],
        "token_binding_status": token_facts["token_binding_status"],
        "media_lock_status": media_facts["media_lock_status"],
        "live_submit_status": packet.get("live_submit_status"),
        "blockers": blockers,
        "claims": {
            "proves": [
                "local Kling dry-run scene packet passed fail-closed structural validation" if status == PASS_STATUS else "local Kling dry-run scene packet was checked and blocked",
                "no provider call was made by this validator",
                "paid_call_authorized and submitted dry-run flags were checked",
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
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene_packet", type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.scene_packet.resolve())
    write_json(args.receipt_out, receipt)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
