"""Unit tests for Surf OS-level pointer dispatch receipts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


SURF_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SURF_ROOT))

from pointer_os_dispatch import (  # noqa: E402
    PointerDispatchError,
    WindowContext,
    dispatch_os_pointer_plan,
    map_samples_to_screen,
    select_backend,
)


SAMPLES = [
    {"event": "mouseMoved", "time_ms": 0, "x_css": 10, "y_css": 20},
    {"event": "mousePressed", "time_ms": 20, "x_css": 10, "y_css": 20},
    {"event": "mouseReleased", "time_ms": 40, "x_css": 10, "y_css": 20},
]


def test_maps_viewport_css_samples_to_screen_pixels() -> None:
    context = WindowContext(origin_x=100, origin_y=200, device_pixel_ratio=2, source="explicit")

    mapped = map_samples_to_screen(SAMPLES, context)

    assert mapped[0]["screen_x"] == 120
    assert mapped[0]["screen_y"] == 240
    assert mapped[1]["delay_ms"] == 20
    assert mapped[2]["event"] == "mouseReleased"


def test_os_dispatch_dry_run_receipt_records_mapping_and_boundaries() -> None:
    receipt = dispatch_os_pointer_plan(
        {"samples": SAMPLES},
        backend="xdotool",
        dry_run=True,
        window_origin_x=100,
        window_origin_y=200,
        device_pixel_ratio=2,
        source_path=None,
    )

    assert receipt["schema_version"] == "surf.pointer_dispatch_receipt.v1"
    assert receipt["success"] is True
    assert receipt["transport_selected"] == "os"
    assert receipt["backend"] == "xdotool"
    assert receipt["dry_run"] is True
    assert receipt["sample_count"] == 3
    assert receipt["coordinate_mapping"]["window_origin_screen_px"] == {"x": 100, "y": 200}
    assert receipt["coordinate_mapping"]["device_pixel_ratio"] == 2
    assert receipt["events"][0]["screen_x"] == 120
    assert receipt["proof_boundary"]["post_observation_required"] is True
    assert receipt["proof_boundary"]["does_not_choose_target_coordinates"] is True


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(PointerDispatchError, match="unsupported pointer dispatch backend"):
        select_backend("nope", dry_run=True)


def test_dry_run_requires_explicit_window_origin() -> None:
    with pytest.raises(PointerDispatchError, match="requires explicit --window-origin-x"):
        dispatch_os_pointer_plan({"samples": SAMPLES}, backend="xdotool", dry_run=True)
