"""Runtime atlas validation gates."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from sprite_atlas.contracts import Profile
from sprite_atlas.generate_manifest import build_manifest


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def _grid_scars(cell: np.ndarray, *, threshold: int = 85) -> bool:
    rgb = cell[:, :, :3]
    alpha = cell[:, :, 3]
    opaque = alpha > 0
    if not opaque.any():
        return False
    mx = rgb[:, :, 0].astype(int)
    for axis in (0, 1):
        for idx in (0, -1):
            line = (mx[idx, :] if axis == 0 else mx[:, idx])
            alpha_line = alpha[idx, :] if axis == 0 else alpha[:, idx]
            if np.any((line <= threshold) & (alpha_line > 0)):
                if (line <= threshold).sum() > len(line) * 0.4:
                    return True
    return False


def validate_atlas_png(image: Image.Image, profile: Profile) -> list[CheckResult]:
    checks: list[CheckResult] = []
    arr = np.array(image.convert("RGBA"))
    h, w = arr.shape[:2]
    alpha = arr[:, :, 3]

    checks.append(CheckResult("png_dimensions", (w, h) == (profile.atlas.width, profile.atlas.height), f"found {w}x{h}"))
    checks.append(CheckResult("png_mode_rgba", arr.shape[2] == 4, image.mode))
    transparent_fraction = float((alpha == 0).mean())
    checks.append(CheckResult("actual_transparency", transparent_fraction > 0.1, f"alpha0={transparent_fraction:.2%}"))
    corners = [tuple(arr[y, x]) for y, x in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1))]
    checks.append(
        CheckResult(
            "corner_alpha_zero",
            all(px[3] == 0 for px in corners),
            str(corners),
        )
    )

    fw = profile.atlas.frame_width
    fh = profile.atlas.frame_height
    occupied: dict[str, int] = {}
    empty_violations = 0
    scar_rows = 0
    clipped = 0

    for animation in profile.animations:
        count = 0
        for col in range(profile.atlas.columns):
            cell = arr[animation.row * fh : (animation.row + 1) * fh, col * fw : (col + 1) * fw]
            n = int((cell[:, :, 3] > 0).sum())
            should_occupy = col < animation.frames
            if should_occupy and n < 80:
                clipped += 1
            if not should_occupy and n > 0:
                empty_violations += 1
            if should_occupy and n >= 80:
                count += 1
            if should_occupy and _grid_scars(cell):
                scar_rows += 1
        occupied[animation.name] = count
        checks.append(
            CheckResult(
                f"row_{animation.name}_occupied",
                count == animation.frames,
                f"expected {animation.frames}, found {count}",
            )
        )

    checks.append(CheckResult("unused_cells_alpha_zero", empty_violations == 0, f"violations={empty_violations}"))
    checks.append(CheckResult("no_grid_scars", scar_rows == 0, f"cells_with_scars={scar_rows}"))
    checks.append(CheckResult("no_clipped_required_frames", clipped == 0, f"clipped={clipped}"))
    return checks


def validate_manifest(manifest: dict[str, object], profile: Profile, *, sprite_id: str) -> list[CheckResult]:
    checks: list[CheckResult] = []
    expected = build_manifest(sprite_id=sprite_id, image_name="candidate.png", profile=profile)
    checks.append(
        CheckResult(
            "animation_arrays_match_profile",
            manifest.get("animations") == expected.get("animations"),
            "animation names/order/count",
        )
    )
    exp_frames = expected["frames"]
    act_frames = manifest.get("frames", {})
    rects_ok = True
    for name, spec in exp_frames.items():
        if act_frames.get(name, {}).get("frame") != spec["frame"]:
            rects_ok = False
            break
    checks.append(CheckResult("pixi_frame_rectangles", rects_ok, "frame rectangles"))
    return checks


def summarize_checks(checks: list[CheckResult]) -> dict[str, object]:
    return {
        "passed": all(check.passed for check in checks),
        "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
    }
