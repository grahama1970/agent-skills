"""Unit tests for Surf CDP geometry and pointer primitives."""

from __future__ import annotations

import sys
from pathlib import Path


SURF_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SURF_ROOT))

from cdp_client import CDPController  # noqa: E402


class FakeCDP(CDPController):
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    def send(self, method: str, params: dict | None = None) -> dict:
        params = params or {}
        self.sent.append((method, params))
        if method == "Page.getLayoutMetrics":
            return {"cssLayoutViewport": {"clientWidth": 800, "clientHeight": 600}}
        if method == "DOM.getDocument":
            return {"root": {"nodeId": 1}}
        if method == "DOM.querySelector":
            return {"nodeId": 7}
        if method == "DOM.getContentQuads":
            return {"quads": [[10, 20, 110, 20, 110, 70, 10, 70]]}
        if method == "DOM.getNodeForLocation":
            return {"backendNodeId": 44, "frameId": "frame-1"}
        if method == "DOM.describeNode":
            return {"node": {"nodeName": "BUTTON", "backendNodeId": 44}}
        if method == "Input.dispatchMouseEvent":
            return {}
        return {"ok": True}

    def evaluate(self, expression: str, return_by_value: bool = True) -> dict:
        return {
            "url": "http://127.0.0.1:8000/",
            "title": "Synthetic",
            "viewport_width_css": 800,
            "viewport_height_css": 600,
            "device_scale_factor": 1,
            "scroll_x_css": 0,
            "scroll_y_css": 0,
            "document_width_css": 800,
            "document_height_css": 1200,
        }


def test_raw_command_wraps_cdp_result() -> None:
    cdp = FakeCDP()

    receipt = cdp.raw_command("Page.getLayoutMetrics", {"probe": True})

    assert receipt["schema_version"] == "surf.cdp_raw_result.v1"
    assert receipt["success"] is True
    assert receipt["method"] == "Page.getLayoutMetrics"
    assert receipt["params"] == {"probe": True}
    assert receipt["result"]["cssLayoutViewport"]["clientWidth"] == 800


def test_layout_metrics_emits_viewport_and_cdp_payload() -> None:
    cdp = FakeCDP()

    receipt = cdp.layout_metrics()

    assert receipt["schema_version"] == "surf.layout_metrics.v1"
    assert receipt["viewport"]["viewport_width_css"] == 800
    assert receipt["cdp"]["cssLayoutViewport"]["clientHeight"] == 600


def test_content_quads_resolves_selector_center() -> None:
    cdp = FakeCDP()

    receipt = cdp.content_quads("button.submit")

    assert receipt["schema_version"] == "surf.content_quads.v1"
    assert receipt["node_id"] == 7
    assert receipt["primary_center"] == {"x": 60.0, "y": 45.0}
    assert ("DOM.querySelector", {"nodeId": 1, "selector": "button.submit"}) in cdp.sent


def test_hit_test_uses_viewport_coordinates_and_describes_node() -> None:
    cdp = FakeCDP()

    receipt = cdp.hit_test(60.5, 45.25)

    assert receipt["schema_version"] == "surf.hit_test.v1"
    assert receipt["hit"]["backendNodeId"] == 44
    assert receipt["node"]["nodeName"] == "BUTTON"
    assert (
        "DOM.getNodeForLocation",
        {
            "x": 60,
            "y": 45,
            "includeUserAgentShadowDOM": True,
            "ignorePointerEventsNone": False,
        },
    ) in cdp.sent


def test_dispatch_pointer_samples_emits_dispatch_only_receipt() -> None:
    cdp = FakeCDP()

    receipt = cdp.dispatch_pointer_samples(
        [
            {"event": "mouseMoved", "time_ms": 0, "x_css": 10, "y_css": 20},
            {"event": "mousePressed", "time_ms": 0, "x_css": 10, "y_css": 20},
            {"event": "mouseReleased", "time_ms": 0, "x_css": 10, "y_css": 20},
        ],
        source_path="/tmp/pointer-plan.json",
    )

    assert receipt["schema_version"] == "surf.pointer_dispatch_receipt.v1"
    assert receipt["sample_count"] == 3
    assert receipt["proof_boundary"]["dispatch_only"] is True
    assert receipt["proof_boundary"]["does_not_prove_challenge_solved"] is True
    assert [method for method, _ in cdp.sent] == [
        "Input.dispatchMouseEvent",
        "Input.dispatchMouseEvent",
        "Input.dispatchMouseEvent",
    ]
