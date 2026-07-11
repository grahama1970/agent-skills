"""Validation and repair receipts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_receipt(
    *,
    status: str,
    sprite_id: str,
    profile_id: str,
    source_path: Path,
    profile_path: Path,
    checks: list[dict[str, Any]],
    missing_frames: list[dict[str, Any]] | None = None,
    atlas_candidate: Path | None = None,
    manifest_candidate: Path | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "sprite_atlas.receipt.v1",
        "status": status,
        "sprite_id": sprite_id,
        "profile_id": profile_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_sha256": sha256_file(source_path),
        "profile_sha256": sha256_file(profile_path),
        "checks": checks,
    }
    if atlas_candidate and atlas_candidate.exists():
        payload["atlas_sha256"] = sha256_file(atlas_candidate)
    if manifest_candidate and manifest_candidate.exists():
        payload["manifest_sha256"] = sha256_file(manifest_candidate)
    if missing_frames:
        payload["missing_frames"] = missing_frames
    return payload


def build_regeneration_work_order(
    *,
    sprite_id: str,
    profile_id: str,
    missing_frames: list[dict[str, Any]],
    prompt_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": "sprite_atlas.work_order.v1",
        "kind": "regeneration",
        "sprite_id": sprite_id,
        "profile_id": profile_id,
        "missing_frames": missing_frames,
        "prompt_ref": prompt_ref,
        "instruction": "Image generation must supply only the missing or invalid frames/rows. Do not duplicate frames.",
    }
