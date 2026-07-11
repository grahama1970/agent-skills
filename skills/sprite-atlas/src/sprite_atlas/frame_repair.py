"""Plan, extract, and apply exact runtime-atlas frame repairs.

Inputs are an existing fixed-grid runtime atlas and a project-owned profile.
Outputs are named frame files, machine-readable repair plans, and staged atlas
candidates. Missing artwork is never synthesized or duplicated here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from sprite_atlas.contracts import Profile
from sprite_atlas.generate_manifest import write_manifest
from sprite_atlas.receipts import sha256_file, write_json
from sprite_atlas.validate_atlas import summarize_checks, validate_atlas_png, validate_manifest


MIN_OPAQUE_PIXELS = 80


def frame_path(animation: str, frame: int) -> Path:
    """Return the stable relative path for one authored frame."""
    return Path(animation) / f"{frame:03d}.png"


def analyze_required_frames(image: Image.Image, profile: Profile) -> list[dict[str, Any]]:
    """Describe every required profile cell without inferring missing artwork."""
    rgba = np.array(image.convert("RGBA"))
    fw = profile.atlas.frame_width
    fh = profile.atlas.frame_height
    frames: list[dict[str, Any]] = []
    for animation in profile.animations:
        for column in range(animation.frames):
            cell = rgba[
                animation.row * fh : (animation.row + 1) * fh,
                column * fw : (column + 1) * fw,
            ]
            alpha = cell[:, :, 3]
            opaque_pixels = int((alpha > 0).sum())
            ys, xs = np.nonzero(alpha > 0)
            touches_edge = bool(
                opaque_pixels
                and (
                    int(xs.min()) == 0
                    or int(ys.min()) == 0
                    or int(xs.max()) == fw - 1
                    or int(ys.max()) == fh - 1
                )
            )
            if opaque_pixels == 0:
                state = "missing"
            elif opaque_pixels < MIN_OPAQUE_PIXELS:
                state = "invalid_sparse"
            else:
                state = "present"
            frames.append(
                {
                    "animation": animation.name,
                    "frame": column,
                    "row": animation.row,
                    "column": column,
                    "path": frame_path(animation.name, column).as_posix(),
                    "opaque_pixels": opaque_pixels,
                    "state": state,
                    "touches_cell_edge": touches_edge,
                }
            )
    return frames


def build_repair_plan(
    *, image: Image.Image, atlas_path: Path, profile: Profile, profile_path: Path, sprite_id: str
) -> dict[str, Any]:
    """Build an exact generation plan for missing and structurally invalid cells."""
    frames = analyze_required_frames(image, profile)
    required = [frame for frame in frames if frame["state"] != "present"]
    by_animation: dict[str, list[dict[str, Any]]] = {}
    for frame in frames:
        by_animation.setdefault(str(frame["animation"]), []).append(frame)
    for frame in required:
        neighbors = by_animation[str(frame["animation"])]
        index = int(frame["frame"])
        frame["reference_frames"] = [
            candidate["path"]
            for candidate in neighbors
            if candidate["state"] == "present" and abs(int(candidate["frame"]) - index) <= 1
        ]
    edge_warnings = [frame["path"] for frame in frames if frame["touches_cell_edge"]]
    return {
        "schema": "sprite_atlas.frame_repair_plan.v1",
        "sprite_id": sprite_id,
        "profile_id": profile.profile_id,
        "source_atlas_sha256": sha256_file(atlas_path),
        "profile_sha256": sha256_file(profile_path),
        "authoring_model": "named_frames",
        "runtime_output": {
            "width": profile.atlas.width,
            "height": profile.atlas.height,
            "frame_width": profile.atlas.frame_width,
            "frame_height": profile.atlas.frame_height,
        },
        "required_frame_count": len(frames),
        "repair_required": bool(required),
        "repair_frame_count": len(required),
        "repair_frames": required,
        "edge_touch_warnings": edge_warnings,
        "claim_boundary": {
            "proves": ["profile-derived missing and sparse frame inventory"],
            "does_not_prove": ["art quality", "identity consistency", "animation continuity", "promotion eligibility"],
        },
    }


def extract_named_frames(*, image: Image.Image, profile: Profile, output_dir: Path) -> dict[str, Any]:
    """Extract required fixed-grid cells into stable animation/frame paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fw = profile.atlas.frame_width
    fh = profile.atlas.frame_height
    index: list[dict[str, Any]] = []
    for frame in analyze_required_frames(image, profile):
        target = output_dir / frame["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        row = int(frame["row"])
        column = int(frame["column"])
        image.crop((column * fw, row * fh, (column + 1) * fw, (row + 1) * fh)).convert("RGBA").save(target)
        index.append(frame)
    payload = {
        "schema": "sprite_atlas.named_frame_index.v1",
        "profile_id": profile.profile_id,
        "frame_count": len(index),
        "frames": index,
    }
    write_json(output_dir / "frame-index.json", payload)
    return payload


def validate_named_frames(*, frames_dir: Path, profile: Profile) -> dict[str, Any]:
    """Validate every required named frame before runtime packing."""
    checks: list[dict[str, Any]] = []
    for animation in profile.animations:
        for index in range(animation.frames):
            relative = frame_path(animation.name, index)
            source = frames_dir / relative
            check: dict[str, Any] = {"path": relative.as_posix(), "passed": False}
            if not source.is_file():
                check["reason"] = "missing_frame"
                checks.append(check)
                continue
            image = Image.open(source).convert("RGBA")
            expected = (profile.atlas.frame_width, profile.atlas.frame_height)
            if image.size != expected:
                check.update(reason="invalid_dimensions", found=list(image.size), expected=list(expected))
                checks.append(check)
                continue
            alpha = np.array(image.getchannel("A"))
            opaque_pixels = int((alpha > 0).sum())
            check["opaque_pixels"] = opaque_pixels
            if opaque_pixels < MIN_OPAQUE_PIXELS:
                check["reason"] = "insufficient_opaque_pixels"
                checks.append(check)
                continue
            guard = profile.normalization.edge_guard_px
            if guard > 0 and (
                np.any(alpha[:guard, :] > 0)
                or np.any(alpha[-guard:, :] > 0)
                or np.any(alpha[:, :guard] > 0)
                or np.any(alpha[:, -guard:] > 0)
            ):
                check.update(reason="edge_guard_violated", edge_guard_px=guard)
                checks.append(check)
                continue
            check.update(passed=True, sha256=sha256_file(source))
            checks.append(check)
    failed = [check for check in checks if not check["passed"]]
    return {
        "schema": "sprite_atlas.named_frame_validation.v1",
        "passed": not failed,
        "required_frame_count": len(checks),
        "passed_frame_count": len(checks) - len(failed),
        "failed_frame_count": len(failed),
        "checks": checks,
    }


def pack_named_frames(*, frames_dir: Path, profile: Profile) -> Image.Image:
    """Pack a complete validated named-frame tree into the profile grid."""
    validation = validate_named_frames(frames_dir=frames_dir, profile=profile)
    if not validation["passed"]:
        raise ValueError("named frame validation failed; refusing to pack")
    atlas = Image.new("RGBA", (profile.atlas.width, profile.atlas.height), (0, 0, 0, 0))
    for animation in profile.animations:
        for index in range(animation.frames):
            frame = Image.open(frames_dir / frame_path(animation.name, index)).convert("RGBA")
            atlas.paste(frame, (index * profile.atlas.frame_width, animation.row * profile.atlas.frame_height))
    return atlas


def apply_frame_patches(
    *,
    source_atlas: Path,
    profile: Profile,
    profile_path: Path,
    sprite_id: str,
    repair_plan: dict[str, Any],
    patch_dir: Path,
    job_dir: Path,
) -> dict[str, Any]:
    """Apply every planned patch and stage a fully revalidated atlas candidate."""
    if repair_plan.get("source_atlas_sha256") != sha256_file(source_atlas):
        raise ValueError("repair plan source_atlas_sha256 does not match the supplied atlas")
    if repair_plan.get("profile_sha256") != sha256_file(profile_path):
        raise ValueError("repair plan profile_sha256 does not match the supplied profile")

    source_image = Image.open(source_atlas).convert("RGBA")
    named_frames_dir = job_dir / "frames"
    extract_named_frames(image=source_image, profile=profile, output_dir=named_frames_dir)
    applied: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for frame in repair_plan.get("repair_frames", []):
        relative = Path(str(frame["path"]))
        patch_path = patch_dir / relative
        if not patch_path.is_file():
            errors.append({"path": relative.as_posix(), "reason": "missing_patch_file"})
            continue
        patch = Image.open(patch_path).convert("RGBA")
        expected_size = (profile.atlas.frame_width, profile.atlas.frame_height)
        if patch.size != expected_size:
            errors.append(
                {"path": relative.as_posix(), "reason": "invalid_dimensions", "found": list(patch.size), "expected": list(expected_size)}
            )
            continue
        alpha = np.array(patch.getchannel("A"))
        opaque_pixels = int((alpha > 0).sum())
        if opaque_pixels < MIN_OPAQUE_PIXELS:
            errors.append({"path": relative.as_posix(), "reason": "insufficient_opaque_pixels", "opaque_pixels": opaque_pixels})
            continue
        guard = profile.normalization.edge_guard_px
        if guard > 0 and (
            np.any(alpha[:guard, :] > 0)
            or np.any(alpha[-guard:, :] > 0)
            or np.any(alpha[:, :guard] > 0)
            or np.any(alpha[:, -guard:] > 0)
        ):
            errors.append(
                {
                    "path": relative.as_posix(),
                    "reason": "edge_guard_violated",
                    "edge_guard_px": guard,
                }
            )
            continue
        patch.save(named_frames_dir / relative)
        applied.append({"path": relative.as_posix(), "sha256": sha256_file(patch_path), "opaque_pixels": opaque_pixels})

    if errors:
        return {"status": "BLOCKED_FRAME_PATCH_INVALID", "applied": applied, "errors": errors}

    job_dir.mkdir(parents=True, exist_ok=True)
    named_validation = validate_named_frames(frames_dir=named_frames_dir, profile=profile)
    write_json(job_dir / "frame-validation-index.json", named_validation)
    if not named_validation["passed"]:
        return {
            "status": "BLOCKED_NAMED_FRAME_VALIDATION",
            "applied": applied,
            "errors": [check for check in named_validation["checks"] if not check["passed"]],
        }
    candidate = pack_named_frames(frames_dir=named_frames_dir, profile=profile)
    candidate_png = job_dir / "atlas.candidate.png"
    candidate_json = job_dir / "atlas.candidate.json"
    candidate.save(candidate_png)
    write_manifest(candidate_json, sprite_id=sprite_id, image_name=f"{sprite_id}.png", profile=profile)
    manifest = json.loads(candidate_json.read_text(encoding="utf-8"))
    validation = summarize_checks(validate_atlas_png(candidate, profile) + validate_manifest(manifest, profile, sprite_id=sprite_id))
    write_json(job_dir / "validation.json", validation)
    status = "PASS_FRAME_PATCH" if validation["passed"] else "FAIL_RUNTIME_VALIDATION"
    receipt = {
        "schema": "sprite_atlas.frame_patch_receipt.v1",
        "status": status,
        "sprite_id": sprite_id,
        "source_atlas_sha256": sha256_file(source_atlas),
        "candidate_atlas_sha256": sha256_file(candidate_png),
        "repair_plan_sha256": sha256_file(job_dir / "frame-repair-plan.json") if (job_dir / "frame-repair-plan.json").is_file() else None,
        "applied": applied,
        "validation_passed": validation["passed"],
    }
    write_json(job_dir / "frame-patch-receipt.json", receipt)
    return receipt
