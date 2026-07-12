#!/usr/bin/env python3
"""Write the run-wide Phase 11 media requirements without publishing media."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(media_lock_path: Path, payload_path: Path, revision_id: str) -> dict[str, Any]:
    media_lock = read_object(media_lock_path)
    payload = read_object(payload_path)
    locked_assets = media_lock.get("assets") if isinstance(media_lock.get("assets"), list) else []
    panel_payloads = payload.get("panel_payloads") if isinstance(payload.get("panel_payloads"), list) else []
    referenced: dict[str, tuple[str, str]] = {}
    for panel in panel_payloads:
        if not isinstance(panel, dict):
            continue
        panel_id = str(panel.get("panel_id") or "")
        start_id = str(panel.get("source_start_image_asset_id") or "")
        end_id = str(panel.get("source_end_image_asset_id") or "")
        if start_id:
            referenced[start_id] = (panel_id, "input.start_image_url")
        if end_id:
            referenced[end_id] = (panel_id, "input.end_image_url")
    assets: list[dict[str, Any]] = []
    blockers: list[str] = []
    for item in locked_assets:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id") or "")
        panel_id, provider_field = referenced.get(asset_id, (str(item.get("panel_id") or ""), ""))
        provider_url = item.get("provider_accessible_url")
        role = "submission_required" if asset_id in referenced else "not_submitted"
        assets.append({
            "asset_id": asset_id,
            "panel_id": panel_id,
            "frame_role": item.get("frame_role"),
            "sha256": item.get("sha256"),
            "revision_id": revision_id,
            "provider_role": role,
            "provider_field": provider_field or None,
            "local_path": item.get("path"),
            "publication_status": "PUBLISHED" if provider_url else "NOT_RUN",
            "probe_status": "NOT_RUN",
            "teardown_status": "NOT_APPLICABLE",
            "public_url": provider_url,
            "public_fetch_proven": False,
            "provider_fetch_proven": False,
        })
        if not asset_id or not item.get("sha256"):
            blockers.append(f"BLOCKED_MEDIA_ID_OR_HASH_MISSING:{asset_id or 'unknown'}")
    locked_ids = {str(item.get("asset_id")) for item in locked_assets if isinstance(item, dict)}
    missing_refs = sorted(set(referenced) - locked_ids)
    blockers.extend(f"BLOCKED_REFERENCED_MEDIA_NOT_LOCKED:{asset_id}" for asset_id in missing_refs)
    if len(assets) != 8:
        blockers.append(f"BLOCKED_LOCKED_ASSET_CARDINALITY:{len(assets)}:expected:8")
    if any(asset["provider_role"] not in {"submission_required", "not_submitted"} for asset in assets):
        blockers.append("BLOCKED_MEDIA_ROLE_UNRESOLVED")
    return {
        "schema": "persona_dream.phase11_media_requirement_manifest.v1",
        "status": "PASS_PHASE11_MEDIA_REQUIREMENTS_DRY_RUN" if not blockers else "BLOCKED_PHASE11_MEDIA_REQUIREMENTS",
        "revision_id": revision_id,
        "media_lock_sha256": sha256_file(media_lock_path),
        "phase10_payload_sha256": sha256_file(payload_path),
        "all_locked_asset_count": len(assets),
        "submission_required_count": sum(asset["provider_role"] == "submission_required" for asset in assets),
        "assets": assets,
        "blockers": blockers,
        "publication_performed": False,
        "provider_accessible_url_created": False,
        "actual_provider_call_attempts": 0,
        "claims": {
            "proves": ["all locked assets have an explicit provider role and revision lineage"] if not blockers else [],
            "does_not_prove": ["media publication", "public fetch", "provider fetch", "provider readiness"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-lock", type=Path, required=True)
    parser.add_argument("--phase10-payload", type=Path, required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    manifest = build_manifest(args.media_lock, args.phase10_payload, args.revision_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True) if args.json else manifest["status"])
    return 0 if manifest["status"] == "PASS_PHASE11_MEDIA_REQUIREMENTS_DRY_RUN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
