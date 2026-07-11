#!/usr/bin/env python3
"""Validate a story-contract review work order."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_FORBIDDEN_ACTIONS = {
    "mark_story_accepted_without_review",
    "rewrite_status_only_to_bypass_gate",
    "rewrite_panel_or_provider_receipts_to_hide_story_staleness",
    "accept_downstream_panels_from_stale_story",
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


def _missing_marker(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("missing:")


def validate_story_contract_work_order(work_order_path: Path) -> dict[str, Any]:
    work_order_path = work_order_path.resolve()
    work_order = _read_json(work_order_path)
    if not isinstance(work_order, dict):
        raise ValueError("story contract work order must be a JSON object")

    result: dict[str, Any] = {
        "schema": "persona_dream.story_contract_work_order_validation.v1",
        "work_order": str(work_order_path),
        "status": "PASS_STORY_CONTRACT_WORK_ORDER",
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in work_order_path.parts else "no",
        "live": "no",
        "exercised": "local work-order shape, owner contract, source path existence, forbidden action policy, validation blocker capture",
        "unverified": "semantic story acceptance, live memory grounding, dreamer subagent execution, downstream regeneration, provider/Kling execution",
    }

    if work_order.get("schema") != "persona_dream.story_contract_work_order.v1":
        return _block(result, "story_contract_work_order", f"wrong_schema:{work_order.get('schema')}", work_order_path)
    if work_order.get("status") != "WORK_ORDER_READY_STORY_REVIEW_REQUIRED":
        return _block(result, "story_contract_work_order", f"work_order_not_ready:{work_order.get('status')}", work_order_path)
    if work_order.get("owner_subagent") != "dreamer":
        return _block(result, "story_contract_work_order", "wrong_owner_subagent", work_order_path)
    if work_order.get("live") != "no":
        return _block(result, "story_contract_work_order", "live_must_be_no", work_order_path)

    source_paths = work_order.get("source_paths")
    if not isinstance(source_paths, dict):
        return _block(result, "story_contract_work_order", "missing_source_paths", work_order_path)
    for field in ("run_root", "persona_dream_skill_contract", "project_knowledge", "dreamer_agent_contract"):
        if not _existing_path(source_paths.get(field)):
            return _block(result, "story_contract_work_order_source", f"missing_source_path:{field}", work_order_path)
    story_contract_source = source_paths.get("story_contract")
    current_contract = work_order.get("current_contract")
    missing_story_contract = _missing_marker(story_contract_source)
    if not missing_story_contract and not _existing_path(story_contract_source):
        return _block(result, "story_contract_work_order_source", "missing_source_path:story_contract", work_order_path)
    if missing_story_contract and not _existing_path(source_paths.get("dream_packet")):
        return _block(result, "story_contract_work_order_source", "missing_source_path:dream_packet", work_order_path)

    if not isinstance(current_contract, dict):
        return _block(result, "story_contract_work_order", "missing_current_contract", work_order_path)
    if not isinstance(current_contract.get("status"), str) or not current_contract["status"]:
        return _block(result, "story_contract_work_order", "missing_current_contract_status", work_order_path)
    if missing_story_contract and current_contract.get("exists") is not False:
        return _block(result, "story_contract_work_order", "missing_story_contract_must_record_exists_false", work_order_path)

    blocking_validation = work_order.get("blocking_validation")
    if not isinstance(blocking_validation, dict):
        return _block(result, "story_contract_work_order", "missing_blocking_validation", work_order_path)
    if blocking_validation.get("command") != "./run.sh validate-story-contract <story_contract> --run-root <run_root> --json":
        return _block(result, "story_contract_work_order", "wrong_validation_command", work_order_path)
    if not isinstance(blocking_validation.get("first_blocker"), dict):
        return _block(result, "story_contract_work_order", "missing_first_blocker", work_order_path)

    required_default_action = work_order.get("required_default_action")
    if not isinstance(required_default_action, dict) or not isinstance(required_default_action.get("steps"), list):
        return _block(result, "story_contract_work_order", "missing_required_default_action_steps", work_order_path)
    if len(required_default_action["steps"]) < 3:
        return _block(result, "story_contract_work_order", "insufficient_required_default_action_steps", work_order_path)

    forbidden_actions = work_order.get("forbidden_actions")
    if not isinstance(forbidden_actions, list):
        return _block(result, "story_contract_work_order", "missing_forbidden_actions", work_order_path)
    missing_forbidden = sorted(REQUIRED_FORBIDDEN_ACTIONS - set(forbidden_actions))
    if missing_forbidden:
        return _block(result, "story_contract_work_order", "missing_forbidden_actions:" + ",".join(missing_forbidden), work_order_path)

    result["owner_subagent"] = work_order["owner_subagent"]
    result["current_status"] = current_contract["status"]
    result["blocker"] = blocking_validation["first_blocker"].get("reason")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_order", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_story_contract_work_order(args.work_order)
    except Exception as exc:
        result = {
            "schema": "persona_dream.story_contract_work_order_validation.v1",
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
