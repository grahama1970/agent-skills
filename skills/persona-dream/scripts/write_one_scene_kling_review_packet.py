#!/usr/bin/env python3
"""Install a blocked one-scene Kling review packet for backward validation.

This writes canonical receipt paths for local validation only. It does not
upload media, probe public URLs, submit to Kling, or claim provider readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _rel_or_abs(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _resolve_artifact(path_value: str, *, base_dir: Path, run_root: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    for candidate in (base_dir / path, run_root / path):
        if candidate.exists():
            return candidate
    return run_root / path


def build_one_scene_kling_review_packet(
    *,
    run_root: Path,
    panel_source_receipt: Path,
    panel_repair_gate_receipt: Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    panel_source_receipt = panel_source_receipt.resolve()
    panel_repair_gate_receipt = panel_repair_gate_receipt.resolve()
    source_doc = _read_json(panel_source_receipt)
    if not isinstance(source_doc, dict):
        raise ValueError("panel source receipt must be a JSON object")
    repair_doc = _read_json(panel_repair_gate_receipt)
    if not isinstance(repair_doc, dict):
        raise ValueError("panel repair gate receipt must be a JSON object")

    image_value = source_doc.get("image_path")
    if not isinstance(image_value, str) or not image_value:
        raise ValueError("panel source receipt missing image_path")
    image_path = _resolve_artifact(image_value, base_dir=panel_source_receipt.parent, run_root=run_root)
    if not image_path.exists():
        raise ValueError(f"panel image does not exist: {image_path}")

    actual_hash = _sha256_file(image_path)
    expected_hash = source_doc.get("sha256")
    if expected_hash != actual_hash:
        raise ValueError(f"panel image hash mismatch: expected {expected_hash}, got {actual_hash}")

    panel_id = str(source_doc.get("panel_id") or "panel_01")
    run_id = str(source_doc.get("run_id") or run_root.name)
    local_image_path = _rel_or_abs(image_path, run_root)
    provider_urls = repair_doc.get("provider_media_urls")
    provider_url = provider_urls[0] if isinstance(provider_urls, list) and provider_urls else None
    provider_media_ready = (
        repair_doc.get("provider_eligibility") is True
        and repair_doc.get("provider_media_status") == "PASS"
        and isinstance(provider_url, str)
        and provider_url.startswith(("http://", "https://"))
    )
    provider_image_url = provider_url if provider_media_ready else "https://blocked.invalid/persona-dream/panel_01_not_uploaded.png"
    image_status = "PROVIDER_MEDIA_READY_PAID_CALL_BLOCKED" if provider_media_ready else "BLOCKED_PROVIDER_MEDIA_URLS"
    provider_text = (
        "Dry-run provider payload only. The image URL is provider-accessible and hash-probed; do not submit "
        "until explicit paid-call approval is granted."
        if provider_media_ready
        else "Blocked dry-run text only. The panel image is local and not provider-accessible; do not submit."
    )
    blocked_reason = (
        "Blocked one-scene review packet only: Panel 01 has provider-accessible media, "
        "but paid_call_authorized is false and no live Kling call is authorized."
        if provider_media_ready
        else (
            "Blocked one-scene review packet only: Panel 01 is not final-provider eligible, "
            "provider-accessible media is absent, paid_call_authorized is false, and no live Kling call is authorized."
        )
    )

    return {
        "schema": "kling.scene_packet.v1",
        "run_id": run_id,
        "status": "BLOCKED",
        "provider": "kling",
        "model": "kling-v3-omni",
        "mode": "std",
        "aspect_ratio": "16:9",
        "duration_s": 5.0,
        "paid_call_authorized": False,
        "cost_estimate": {
            "status": "DRY_RUN_ESTIMATE_ONLY_PROVIDER_PRICING_VALIDATION_REQUIRED",
            "currency": "credits",
            "duration_s": 5.0,
            "selected_mode": "std",
            "rate_credits_per_s": 9,
            "estimated_credits": 45,
            "formula": "duration_s * rate_credits_per_s",
            "docs_checked": [
                "skills/persona-dream/SKILL.md provider planning note; no current provider pricing proof in this transaction"
            ],
        },
        "callback_url": None,
        "polling_plan": "No live call. On future approval, persist provider task_id and poll with bounded backoff.",
        "storage_plan": {
            "download_output_to": f"provider_packet/{panel_id}_kling_output.mp4",
            "ffprobe_json": f"provider_packet/{panel_id}_ffprobe.json",
            "frame_contact_sheet": f"provider_packet/{panel_id}_frame_contact_sheet.jpg",
            "raw_response_json": f"provider_packet/{panel_id}_provider_response.json",
        },
        "retry_policy": "No retry is allowed before provider eligibility and explicit paid-call approval.",
        "audio_strategy": "silent/native ambient prompt only for this blocked one-scene review packet",
        "image_list": [
            {
                "token": "<<<image_1>>>",
                "path": local_image_path,
                "role": "panel_01_reference",
                "status": "LOCAL_MEDIA_LOCK_ONLY_NOT_PROVIDER_ACCESSIBLE",
                "hash": actual_hash,
            }
        ],
        "voice_list": [],
        "voice_examples": [],
        "multi_prompt": [
            {
                "index": 0,
                "duration_s": 5.0,
                "visual_anchor": local_image_path,
                "image_status": image_status,
                "voice_status": "NO_DIALOGUE",
                "prompt": (
                    "Panel 01 one-scene Kling review packet. Preserve the accepted photorealistic reference "
                    "image composition, character, desk evidence cards, laptop glow, tea steam, and quiet "
                    "cinematic mood. No dialogue, no text overlays, no live submission from this packet."
                ),
                "dialogue": [],
                "provider_text": provider_text,
                "cinematography": {
                    "shot_size": "medium",
                    "lens": "35mm_cinematic",
                    "camera_mount": "dolly",
                    "camera_movement": "slow_push_in",
                    "composition": "single_panel_reference",
                    "focus_behavior": "deep_focus",
                    "lighting": "preserve_panel_lighting",
                    "color_grade": "preserve_panel_grade",
                    "atmosphere": "preserve_panel_atmosphere",
                    "temporal_pacing": "slow",
                    "environment_lock": "preserve_panel_environment",
                    "director_note": "Review packet is blocked until panel/source/provider gates pass.",
                },
            }
        ],
        "negative_prompt": [
            "Nano Banana fallback final panel",
            "Gemini fallback final panel",
            "unreceipted image generation",
            "live Kling submission",
            "provider readiness by prose-only rewrite",
        ],
        "provider_dry_run_fields": {
            "model": "kling-v3-omni",
            "mode": "std",
            "aspect_ratio": "16:9",
            "sound": "off",
            "multi_shot": False,
            "shot_type": "customize",
            "image_list": [{"image": provider_image_url}],
            "voice_list": [],
            "multi_prompt": [
                {
                    "index": 0,
                    "duration": 5,
                    "prompt": "Blocked dry-run only. Do not submit until provider media URL and panel gates pass.",
                }
            ],
            "external_task_id": f"{run_id}-{panel_id}-blocked-review",
            "callback_url": None,
        },
        "source_artifacts": {
            "panel_source_receipt": _rel_or_abs(panel_source_receipt, run_root),
            "panel_repair_gate_receipt": _rel_or_abs(panel_repair_gate_receipt, run_root),
        },
        "live_call_block_reason": blocked_reason,
        "work_backwards_chain": [
            "kling.scene_packet.v1 blocked review packet",
            "local provider media lock receipt",
            "panel_source_receipt",
            "panel_repair_gate_receipt",
            "visual_review_receipt",
            "storyboard panel receipt",
            "story contract",
            "dream packet",
        ],
    }


def build_provider_media_lock_receipt(
    *,
    run_root: Path,
    panel_source_receipt: Path,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    source_doc = _read_json(panel_source_receipt)
    image_path = _resolve_artifact(str(source_doc["image_path"]), base_dir=panel_source_receipt.parent, run_root=run_root)
    image_hash = _sha256_file(image_path)
    local_path = _rel_or_abs(image_path, run_root)
    url_path = "/" + local_path.lstrip("/") if not Path(local_path).is_absolute() else "/external/panel_01.png"
    return {
        "schema": "persona_dream.provider_media_lock_receipt.v1",
        "run_id": str(source_doc.get("run_id") or run_root.name),
        "status": "LOCAL_MEDIA_LOCK_READY",
        "provider_accessible": False,
        "live_provider_call_made": False,
        "media": [
            {
                "id": str(source_doc.get("panel_id") or "panel_01"),
                "role": "panel_reference_local_only",
                "local_path": local_path,
                "url_path": url_path,
                "sha256": image_hash,
            }
        ],
    }


def install_one_scene_kling_review_packet(
    *,
    run_root: Path,
    panel_source_receipt: Path,
    panel_repair_gate_receipt: Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    receipts_dir = run_root / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    packet = build_one_scene_kling_review_packet(
        run_root=run_root,
        panel_source_receipt=panel_source_receipt,
        panel_repair_gate_receipt=panel_repair_gate_receipt,
        created_at=created_at,
    )
    media_lock = build_provider_media_lock_receipt(run_root=run_root, panel_source_receipt=panel_source_receipt)
    panel_source = _read_json(panel_source_receipt)
    panel_repair = _read_json(panel_repair_gate_receipt)

    outputs = {
        "kling_scene_packet": receipts_dir / "kling_scene_packet.json",
        "provider_media_lock_receipt": receipts_dir / "provider_media_lock_receipt.json",
        "panel_source_receipt": receipts_dir / "panel_source_receipt.json",
        "panel_repair_gate_receipt": receipts_dir / "panel_repair_gate_receipt.json",
    }
    _write_json(outputs["kling_scene_packet"], packet)
    _write_json(outputs["provider_media_lock_receipt"], media_lock)
    _write_json(outputs["panel_source_receipt"], panel_source)
    _write_json(outputs["panel_repair_gate_receipt"], panel_repair)

    return {
        "schema": "persona_dream.one_scene_kling_review_packet_install.v1",
        "status": "INSTALLED_BLOCKED_REVIEW_PACKET",
        "run_root": str(run_root),
        "outputs": {key: str(path) for key, path in outputs.items()},
        "mocked": "no",
        "live": "no",
        "exercised": "local receipt installation and image hash lock",
        "unverified": "provider media hosting, provider fetch, paid-call approval, Kling submission",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--panel-source-receipt", type=Path, required=True)
    parser.add_argument("--panel-repair-gate-receipt", type=Path, required=True)
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = install_one_scene_kling_review_packet(
            run_root=args.run_root,
            panel_source_receipt=args.panel_source_receipt,
            panel_repair_gate_receipt=args.panel_repair_gate_receipt,
            created_at=args.created_at,
        )
    except Exception as exc:
        result = {
            "schema": "persona_dream.one_scene_kling_review_packet_install.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "one_scene_kling_review_packet", "reason": str(exc)},
            "mocked": "unknown",
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["status"])
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
