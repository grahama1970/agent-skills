#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def get(obj: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def assert_file_sha(root: Path, bundle_path: str, expected_sha: str) -> None:
    p = root / bundle_path
    if not p.exists():
        fail(f"missing bundle path: {bundle_path}")
    expected = expected_sha.removeprefix("sha256:")
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    if actual != expected:
        fail(f"sha mismatch for {bundle_path}: {actual} != {expected}")


def accepted_claim(value: Any) -> bool:
    return isinstance(value, str) and value.upper().startswith("ACCEPTED")


def scan_bad_acceptance(obj: Any, path: str = "$") -> None:
    if isinstance(obj, dict):
        status = obj.get("status")
        identity_status = (
            get(obj, "identity_review.status")
            or get(obj, "identity_continuity_review.status")
            or get(obj, "panel_review.identity_review.status")
        )
        if accepted_claim(status) and str(identity_status).upper() == "FAIL":
            fail(f"accepted status with failed identity review at {path}")
        for key, value in obj.items():
            scan_bad_acceptance(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            scan_bad_acceptance(value, f"{path}[{index}]")


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_optimum_payload.py <sb_001.optimum_prompt_payload.v1.json>")
    payload_path = Path(sys.argv[1]).resolve()
    payload = json.loads(payload_path.read_text())
    root = payload_path.parent

    if payload.get("schema") != "persona_dream.phase07.optimum_prompt_payload.v1":
        fail("wrong schema")
    if payload.get("panel_id") != "sb_001":
        fail("panel_id must be sb_001")
    if set(payload.get("required_identities", [])) != {"Embry", "Kai"}:
        fail("required_identities must be exactly Embry and Kai")

    for identity in ("Embry", "Kai"):
        assets = get(payload, f"identity_reference_assets.{identity}", [])
        if not isinstance(assets, list) or not assets:
            fail(f"missing identity_reference_assets for {identity}")
        for asset in assets:
            bundle_path = asset.get("bundle_path")
            if not isinstance(bundle_path, str) or not bundle_path.startswith("references/"):
                fail(f"{identity} reference must use references/ bundle_path")
            assert_file_sha(root, bundle_path, str(asset.get("sha256", "")))
            for flag in (
                "pane_visible_required",
                "generator_attachment_required",
                "reviewer_attachment_required",
                "reference_only_not_output",
            ):
                if asset.get(flag) is not True:
                    fail(f"{identity} reference missing true {flag}")

    if get(payload, "model_policy.image_generation.provider_route") != "codex_oauth":
        fail("image_generation provider_route must be codex_oauth")
    if get(payload, "model_policy.image_generation.model") != "gpt-2":
        fail("image_generation model must be gpt-2")
    if get(payload, "model_policy.image_generation.fallbacks") != []:
        fail("image_generation fallbacks must be empty")
    if "flux" not in get(payload, "model_policy.image_generation.disallowed_fallbacks", []):
        fail("flux must be explicitly disallowed")

    if get(payload, "model_policy.identity_review.provider_route") != "codex_oauth":
        fail("identity_review provider_route must be codex_oauth")
    if get(payload, "model_policy.identity_review.model") != "gpt-2":
        fail("identity_review model must be gpt-2")

    if get(payload, "generation_scope.mode") not in {"failed_unlocked_only", "initial_all"}:
        fail("generation_scope.mode must be failed_unlocked_only or initial_all")

    if payload.get("accepted_frame") is not None:
        fail("optimum payload must not start with accepted_frame")
    if payload.get("candidate_frame") is not None:
        fail("optimum payload fixture must start without candidate_frame")

    if "accepted_frame" not in get(payload, "state_truth_rule.creator_must_not_write", []):
        fail("creator_must_not_write must include accepted_frame")
    if get(payload, "state_truth_rule.accepted_frame_writer") != "panel-reviewer":
        fail("accepted_frame_writer must be panel-reviewer")
    if "identity_review.status == PASS" not in get(payload, "state_truth_rule.accepted_frame_requires", []):
        fail("accepted_frame must require identity_review PASS")

    if get(payload, "composition_contract.shot_type") != "identity-readable medium-wide waterline two-shot":
        fail("shot type must be identity-readable medium-wide waterline two-shot")
    forbidden = set(get(payload, "composition_contract.forbidden_shot_types", []))
    if "wide establishing shot" not in forbidden or "back-facing two-shot" not in forbidden:
        fail("identity-hostile shot types must be forbidden")

    for prompt_key in ("start_frame_prompt_path", "end_frame_prompt_path", "reviewer_prompt_path"):
        prompt_path = root / str(get(payload, f"prompts.{prompt_key}", ""))
        if not prompt_path.exists():
            fail(f"missing prompt file for {prompt_key}")

    scan_bad_acceptance(payload)
    print("PASS")


if __name__ == "__main__":
    main()
