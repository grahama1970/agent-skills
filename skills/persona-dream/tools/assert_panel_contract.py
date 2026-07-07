#!/usr/bin/env python3
"""
Validate the Phase 07 panel payload invariant:
a candidate image cannot become accepted unless reviewer identity review passes.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def get(d: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def assert_reference(root: Path, payload: dict[str, Any], identity: str) -> None:
    assets = get(payload, f"identity_reference_assets.{identity}", [])
    if not assets:
        fail(f"missing identity_reference_assets for {identity}")
    for asset in assets:
        bundle_path = asset.get("bundle_path")
        if not bundle_path:
            fail(f"{identity} reference missing bundle_path")
        p = root / bundle_path
        if not p.exists():
            fail(f"{identity} reference bundle_path does not exist: {bundle_path}")
        expected = str(asset.get("sha256", "")).removeprefix("sha256:")
        if expected:
            actual = hashlib.sha256(p.read_bytes()).hexdigest()
            if actual != expected:
                fail(f"{identity} reference sha mismatch: {bundle_path}")
        for flag in ("pane_visible", "sent_to_generator_required", "sent_to_reviewer_required"):
            if asset.get(flag) is not True:
                fail(f"{identity} reference {bundle_path} missing true {flag}")


def accepted_status_is_claimed(value: Any) -> bool:
    return isinstance(value, str) and value.upper().startswith("ACCEPTED")


def scan_for_bad_acceptance(obj: Any, path: str = "$") -> None:
    if isinstance(obj, dict):
        status = obj.get("status")
        review = (
            get(obj, "identity_continuity_review.status")
            or get(obj, "identity_review.status")
            or get(obj, "panel_review.identity_review.status")
        )
        if accepted_status_is_claimed(status) and str(review).upper() == "FAIL":
            fail(f"accepted status with failed identity review at {path}")
        for k, v in obj.items():
            scan_for_bad_acceptance(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            scan_for_bad_acceptance(v, f"{path}[{i}]")


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: assert_panel_contract.py <panel_payload.json>")

    payload_path = Path(sys.argv[1]).resolve()
    root = payload_path.parent
    payload = json.loads(payload_path.read_text())

    required = payload.get("required_identities")
    if not isinstance(required, list) or not {"Embry", "Kai"}.issubset(set(required)):
        fail("required_identities must include Embry and Kai")

    if not get(payload, "model_policy.image_generation.provider_route"):
        fail("missing model_policy.image_generation.provider_route")
    if get(payload, "model_policy.image_generation.provider_route") != "codex_oauth":
        fail("image generation route must be codex_oauth")
    if get(payload, "model_policy.image_generation.model") != "gpt-2":
        fail("image model must be gpt-2")
    if get(payload, "model_policy.image_generation.fallbacks") != []:
        fail("fallbacks must be empty")
    if "flux" not in get(payload, "model_policy.image_generation.disallowed_fallbacks", []):
        fail("flux must be explicitly disallowed")

    if not payload.get("generation_scope"):
        fail("missing generation_scope")

    for identity in ("Embry", "Kai"):
        assert_reference(root, payload, identity)

    scan_for_bad_acceptance(payload)

    forbidden = get(payload, "terminal_truth_rule.creator_must_not_write", [])
    if "accepted_frame" not in forbidden:
        fail("terminal_truth_rule must forbid creator writing accepted_frame")

    writer = get(payload, "terminal_truth_rule.accepted_frame_writer")
    if writer != "panel-reviewer":
        fail("accepted_frame_writer must be panel-reviewer")

    print("PASS: panel contract invariants hold")


if __name__ == "__main__":
    main()
