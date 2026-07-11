#!/usr/bin/env python3
"""Validate a storyboard-panel generation/review work order."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_FORBIDDEN_ACTIONS = {
    "skip_continuity_ledger",
    "accept_panel_without_story_contract",
    "generate_final_panel_with_nano_banana_or_gemini",
    "rewrite_downstream_receipts_to_hide_missing_storyboard",
    "direct_kling_submit",
    "direct_paid_provider_call",
}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _block(result: dict[str, Any], phase: str, reason: str, path: Path) -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": phase, "reason": reason, "path": str(path)}
    return result


def _existing_path(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and Path(value).exists()


def validate_storyboard_panel_work_order(work_order_path: Path) -> dict[str, Any]:
    work_order_path = work_order_path.resolve()
    work_order = _read_json(work_order_path)
    if not isinstance(work_order, dict):
        raise ValueError("storyboard panel work order must be a JSON object")

    result: dict[str, Any] = {
        "schema": "persona_dream.storyboard_panel_work_order_validation.v1",
        "work_order": str(work_order_path),
        "status": "PASS_STORYBOARD_PANEL_WORK_ORDER",
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in work_order_path.parts else "no",
        "live": "no",
        "exercised": "local work-order shape, story source path existence, continuity requirement policy, forbidden action policy",
        "unverified": "storyboard subagent execution, live panel generation, visual review, provider/Kling execution",
    }

    if work_order.get("schema") != "persona_dream.storyboard_panel_work_order.v1":
        return _block(result, "storyboard_panel_work_order", f"wrong_schema:{work_order.get('schema')}", work_order_path)
    if work_order.get("status") != "WORK_ORDER_READY_STORYBOARD_PANEL_REQUIRED":
        return _block(result, "storyboard_panel_work_order", f"work_order_not_ready:{work_order.get('status')}", work_order_path)
    if work_order.get("owner_subagent") != "dreamer":
        return _block(result, "storyboard_panel_work_order", "wrong_owner_subagent", work_order_path)
    if work_order.get("live") != "no":
        return _block(result, "storyboard_panel_work_order", "live_must_be_no", work_order_path)

    source_paths = work_order.get("source_paths")
    if not isinstance(source_paths, dict):
        return _block(result, "storyboard_panel_work_order", "missing_source_paths", work_order_path)
    for field in ("run_root", "story_contract", "persona_dream_skill_contract", "project_knowledge", "dreamer_agent_contract"):
        if not _existing_path(source_paths.get(field)):
            return _block(result, "storyboard_panel_work_order_source", f"missing_source_path:{field}", work_order_path)

    story = work_order.get("story_contract")
    if not isinstance(story, dict) or not isinstance(story.get("story"), str) or not story["story"].strip():
        return _block(result, "storyboard_panel_work_order", "missing_story_text", work_order_path)

    blocking_validation = work_order.get("blocking_validation")
    if not isinstance(blocking_validation, dict):
        return _block(result, "storyboard_panel_work_order", "missing_blocking_validation", work_order_path)
    if blocking_validation.get("first_blocker", {}).get("phase") != "storyboard_panel":
        return _block(result, "storyboard_panel_work_order", "first_blocker_must_be_storyboard_panel", work_order_path)

    required_default_action = work_order.get("required_default_action")
    steps = required_default_action.get("steps") if isinstance(required_default_action, dict) else None
    if not isinstance(steps, list) or not any("continuity" in str(step).lower() for step in steps):
        return _block(result, "storyboard_panel_work_order", "missing_continuity_step", work_order_path)

    forbidden_actions = work_order.get("forbidden_actions")
    if not isinstance(forbidden_actions, list):
        return _block(result, "storyboard_panel_work_order", "missing_forbidden_actions", work_order_path)
    missing_forbidden = sorted(REQUIRED_FORBIDDEN_ACTIONS - set(forbidden_actions))
    if missing_forbidden:
        return _block(result, "storyboard_panel_work_order", "missing_forbidden_actions:" + ",".join(missing_forbidden), work_order_path)

    result["owner_subagent"] = work_order["owner_subagent"]
    result["blocker"] = blocking_validation["first_blocker"].get("reason")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_order", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_storyboard_panel_work_order(args.work_order)
    except Exception as exc:
        result = {
            "schema": "persona_dream.storyboard_panel_work_order_validation.v1",
            "work_order": str(args.work_order),
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc), "path": str(args.work_order)},
            "mocked": "unknown",
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['phase']}: {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
