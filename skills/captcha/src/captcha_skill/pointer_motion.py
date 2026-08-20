"""Deterministic pointer-motion planning for authorized synthetic CAPTCHA tests.

The planner converts screenshot pixel coordinates into Chrome viewport CSS
coordinates and emits CDP-style pointer samples. It never dispatches browser
input; Surf or another authorized transport must consume the receipt after the
captcha policy gate has already passed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from .constants import POINTER_MOTION_REFERENCE
from .models import (
    AuthorizationManifest,
    AuthorizationReceipt,
    PointerMotionAction,
    PointerMotionPlan,
    PointerMotionRequest,
    PointerPoint,
    PointerSample,
    PointerSourcePackage,
    PointerDispatchPlan,
    SurfPointerDispatchBinding,
    SeamValidation,
)
from .policy import sha256_file, utc_now


@dataclass(frozen=True, slots=True)
class _Point:
    x: float
    y: float


def _clamp(value: float, *, low: float, high: float) -> float:
    return min(high, max(low, value))


def _smoothstep(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def _clamped_knots(control_count: int, degree: int) -> list[float]:
    interior = control_count - degree - 1
    return (
        [0.0] * (degree + 1)
        + [index / (interior + 1) for index in range(1, interior + 1)]
        + [1.0] * (degree + 1)
    )


def _basis(index: int, degree: int, t_value: float, knots: list[float]) -> float:
    if degree == 0:
        if knots[index] <= t_value < knots[index + 1]:
            return 1.0
        if t_value == 1.0 and knots[index + 1] == 1.0:
            return 1.0
        return 0.0

    left_denominator = knots[index + degree] - knots[index]
    right_denominator = knots[index + degree + 1] - knots[index + 1]
    left = 0.0
    right = 0.0
    if left_denominator:
        left = (
            (t_value - knots[index])
            / left_denominator
            * _basis(index, degree - 1, t_value, knots)
        )
    if right_denominator:
        right = (
            (knots[index + degree + 1] - t_value)
            / right_denominator
            * _basis(index + 1, degree - 1, t_value, knots)
        )
    return left + right


def _evaluate_b_spline(control_points: list[_Point], t_value: float) -> _Point:
    degree = 3
    if t_value >= 1.0:
        return control_points[-1]
    knots = _clamped_knots(len(control_points), degree)
    x_value = 0.0
    y_value = 0.0
    for index, point in enumerate(control_points):
        weight = _basis(index, degree, t_value, knots)
        x_value += point.x * weight
        y_value += point.y * weight
    return _Point(x=x_value, y=y_value)


def _control_points(
    start: PointerPoint,
    end: PointerPoint,
    request: PointerMotionRequest,
) -> list[_Point]:
    rng = random.Random(request.seed)
    dx = end.x - start.x
    dy = end.y - start.y
    distance = math.hypot(dx, dy) or 1.0
    perpendicular_x = -dy / distance
    perpendicular_y = dx / distance
    max_offset = min(request.control_offset_css_px, max(8.0, distance * 0.45))
    offset_one = rng.uniform(-max_offset, max_offset)
    offset_two = rng.uniform(-max_offset, max_offset)
    parallel_one = rng.uniform(-distance * 0.08, distance * 0.08)
    parallel_two = rng.uniform(-distance * 0.08, distance * 0.08)
    unit_x = dx / distance
    unit_y = dy / distance
    width = request.mapping.viewport_width_css
    height = request.mapping.viewport_height_css

    c1 = _Point(
        x=_clamp(
            start.x + dx * 0.28 + unit_x * parallel_one + perpendicular_x * offset_one,
            low=0.0,
            high=float(width),
        ),
        y=_clamp(
            start.y + dy * 0.28 + unit_y * parallel_one + perpendicular_y * offset_one,
            low=0.0,
            high=float(height),
        ),
    )
    c2 = _Point(
        x=_clamp(
            start.x + dx * 0.72 + unit_x * parallel_two + perpendicular_x * offset_two,
            low=0.0,
            high=float(width),
        ),
        y=_clamp(
            start.y + dy * 0.72 + unit_y * parallel_two + perpendicular_y * offset_two,
            low=0.0,
            high=float(height),
        ),
    )
    return [
        _Point(start.x, start.y),
        _Point(start.x, start.y),
        c1,
        c2,
        _Point(end.x, end.y),
        _Point(end.x, end.y),
    ]


def _rounded(value: float) -> float:
    return round(value, 3)


def _path_samples(request: PointerMotionRequest) -> tuple[PointerPoint, PointerPoint, list[PointerSample]]:
    start = request.mapping.image_to_viewport(request.start_image_px)
    end = request.mapping.image_to_viewport(request.end_image_px)
    control_points = _control_points(start, end, request)
    rng = random.Random(request.seed + 1)
    samples: list[PointerSample] = [
        PointerSample(
            event="mouseMoved",
            time_ms=0,
            x_css=_rounded(start.x),
            y_css=_rounded(start.y),
            button_down=False,
        )
    ]

    if request.action is PointerMotionAction.CLICK:
        samples.append(
            PointerSample(
                event="mousePressed",
                time_ms=request.hold_ms,
                x_css=_rounded(start.x),
                y_css=_rounded(start.y),
                button_down=True,
            )
        )
        samples.append(
            PointerSample(
                event="mouseReleased",
                time_ms=request.hold_ms + max(20, request.duration_ms // 8),
                x_css=_rounded(start.x),
                y_css=_rounded(start.y),
                button_down=False,
            )
        )
        return start, end, samples

    for index in range(request.sample_count):
        fraction = index / max(1, request.sample_count - 1)
        curve_t = _smoothstep(fraction)
        point = _evaluate_b_spline(control_points, curve_t)
        endpoint_weight = math.sin(math.pi * fraction)
        jitter = request.jitter_css_px * endpoint_weight
        x_value = point.x + rng.uniform(-jitter, jitter)
        y_value = point.y + rng.uniform(-jitter, jitter)
        samples.append(
            PointerSample(
                event="mouseMoved",
                time_ms=request.hold_ms
                + round(request.duration_ms * fraction),
                x_css=_rounded(
                    _clamp(x_value, low=0.0, high=float(request.mapping.viewport_width_css))
                ),
                y_css=_rounded(
                    _clamp(y_value, low=0.0, high=float(request.mapping.viewport_height_css))
                ),
                button_down=True,
            )
        )
    samples.insert(
        1,
        PointerSample(
            event="mousePressed",
            time_ms=request.hold_ms,
            x_css=_rounded(start.x),
            y_css=_rounded(start.y),
            button_down=True,
        ),
    )
    samples.append(
        PointerSample(
            event="mouseReleased",
            time_ms=request.hold_ms + request.duration_ms + request.hold_ms,
            x_css=_rounded(end.x),
            y_css=_rounded(end.y),
            button_down=False,
        )
    )
    return start, end, samples


def build_pointer_motion_plan(
    manifest: AuthorizationManifest,
    authorization: AuthorizationReceipt,
    request: PointerMotionRequest,
) -> PointerMotionPlan:
    """Build a receipt-backed pointer path for an authorized local challenge."""

    start, end, samples = _path_samples(request)
    return PointerMotionPlan(
        schema_version="captcha.pointer_motion_plan.v1",
        created_at=utc_now(),
        authorization_id=authorization.authorization_id,
        manifest_sha256=authorization.manifest_sha256,
        target_url=str(manifest.target_url),
        team_mode=manifest.team_mode,
        source_package=PointerSourcePackage.model_validate(POINTER_MOTION_REFERENCE),
        algorithm="clamped_cubic_b_spline_with_seeded_jitter.v1",
        action=request.action,
        start_viewport_css=PointerPoint(x=_rounded(start.x), y=_rounded(start.y)),
        end_viewport_css=PointerPoint(x=_rounded(end.x), y=_rounded(end.y)),
        mapping=request.mapping,
        samples=samples,
        limitations=[
            "Pointer plan is for authorized loopback synthetic CAPTCHA evaluation only.",
            "This artifact does not dispatch input and is not a third-party bypass tool.",
            "Coordinates are valid only for the screenshot and viewport metrics recorded here.",
            "Surf/CDP consumers must re-observe the target before and after dispatch.",
        ],
        seam_validation=SeamValidation(kind="captcha.pointer_motion_plan"),
    )


def build_pointer_dispatch_plan(
    manifest: AuthorizationManifest,
    authorization: AuthorizationReceipt,
    pointer_plan: PointerMotionPlan,
    pointer_plan_path: Path,
) -> PointerDispatchPlan:
    """Build the Surf dispatch command for an authorized pointer plan."""

    pointer_plan_sha256 = sha256_file(pointer_plan_path)
    surf_run = (
        Path(__file__).resolve().parents[4]
        / "skills"
        / "surf"
        / "run.sh"
    )
    return PointerDispatchPlan(
        schema_version="captcha.pointer_dispatch_plan.v1",
        created_at=utc_now(),
        authorization_id=authorization.authorization_id,
        manifest_sha256=authorization.manifest_sha256,
        pointer_plan_sha256=pointer_plan_sha256,
        target_url=str(manifest.target_url),
        team_mode=manifest.team_mode,
        pointer_action=pointer_plan.action,
        sample_count=len(pointer_plan.samples),
        surf=SurfPointerDispatchBinding(
            command=[
                str(surf_run),
                "pointer.dispatch",
                "--plan",
                str(pointer_plan_path.expanduser().resolve()),
                "--json",
            ]
        ),
        limitations=[
            "This dispatch plan is authorized only for the loopback synthetic target in the manifest.",
            "Captcha does not dispatch browser input; Surf owns the transport command and receipt.",
            "Surf pointer dispatch is input-delivery proof only and requires post-dispatch observation.",
            "This artifact does not prove that any CAPTCHA challenge was solved.",
        ],
        seam_validation=SeamValidation(kind="captcha.pointer_dispatch_plan"),
    )
