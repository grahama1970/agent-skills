#!/usr/bin/env python3
"""Validate a one-panel repair work order for persona-dream-panel-repair-gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_FORBIDDEN_ACTIONS = {
    "direct_kling_submit",
    "direct_paid_provider_call",
    "direct_provider_image_api",
    "nano_banana_final_panel_generation",
    "gemini_final_panel_generation",
    "unreceipted_image_generation",
    "provider readiness by prose-only rewrite",
}
REQUIRED_DELEGATED_SUBAGENTS = ["panel-creator", "panel-reviewer"]


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
    if not isinstance(value, str) or not value.strip() or value.startswith("missing:"):
        return False
    return Path(value).exists()


def validate_panel_repair_work_order(work_order_path: Path) -> dict[str, Any]:
    work_order_path = work_order_path.resolve()
    work_order = _read_json(work_order_path)
    if not isinstance(work_order, dict):
        raise ValueError("panel repair work order must be a JSON object")

    result: dict[str, Any] = {
        "schema": "persona_dream.panel_repair_work_order_validation.v1",
        "work_order": str(work_order_path),
        "status": "PASS_PANEL_REPAIR_WORK_ORDER",
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in work_order_path.parts else "no",
        "live": "no",
        "exercised": "local work-order shape, owner/delegation contract, final-gate error capture, source path existence, forbidden action policy",
        "unverified": "subagent execution, image generation, independent visual rereview, provider media hosting, Kling submission",
    }

    if work_order.get("schema") != "persona_dream.panel_repair_work_order.v1":
        return _block(result, "panel_repair_work_order", f"wrong_schema:{work_order.get('schema')}", work_order_path)
    if work_order.get("status") != "WORK_ORDER_READY":
        return _block(result, "panel_repair_work_order", f"work_order_not_ready:{work_order.get('status')}", work_order_path)
    if work_order.get("owner_subagent") != "persona-dream-panel-repair-gate":
        return _block(result, "panel_repair_work_order", "wrong_owner_subagent", work_order_path)
    if work_order.get("delegated_subagents") != REQUIRED_DELEGATED_SUBAGENTS:
        return _block(result, "panel_repair_work_order", "wrong_delegated_subagents", work_order_path)
    if work_order.get("live") != "no":
        return _block(result, "panel_repair_work_order", "live_must_be_no", work_order_path)

    source_paths = work_order.get("source_paths")
    if not isinstance(source_paths, dict):
        return _block(result, "panel_repair_work_order", "missing_source_paths", work_order_path)
    for field in (
        "run_root",
        "persona_dream_skill_contract",
        "panel_repair_agent_contract",
        "panel_creator_agent_contract",
        "panel_reviewer_agent_contract",
    ):
        if not _existing_path(source_paths.get(field)):
            return _block(result, "panel_repair_work_order_source", f"missing_source_path:{field}", work_order_path)
    if not (
        _existing_path(source_paths.get("panel_repair_gate_receipt"))
        or _existing_path(source_paths.get("storyboard_panel_receipt"))
    ):
        return _block(
            result,
            "panel_repair_work_order_source",
            "missing_source_path:panel_repair_gate_receipt_or_storyboard_panel_receipt",
            work_order_path,
        )

    current_candidate = work_order.get("current_candidate")
    if not isinstance(current_candidate, dict):
        return _block(result, "panel_repair_work_order", "missing_current_candidate", work_order_path)
    if not _existing_path(current_candidate.get("image_path")):
        return _block(result, "panel_repair_work_order_candidate", "missing_candidate_image", work_order_path)
    if not isinstance(current_candidate.get("sha256"), str) or not current_candidate["sha256"].startswith("sha256:"):
        return _block(result, "panel_repair_work_order_candidate", "missing_candidate_sha256", work_order_path)

    final_gate = work_order.get("final_gate_validation")
    if not isinstance(final_gate, dict):
        return _block(result, "panel_repair_work_order", "missing_final_gate_validation", work_order_path)
    if final_gate.get("command") != "./run.sh validate-panel-repair-gate <panel_repair_gate_receipt> --require-provider-eligible":
        return _block(result, "panel_repair_work_order", "wrong_final_gate_command", work_order_path)
    if final_gate.get("status") not in {"PASS", "FAIL"}:
        return _block(result, "panel_repair_work_order", f"invalid_final_gate_status:{final_gate.get('status')}", work_order_path)
    if final_gate.get("status") == "FAIL" and not final_gate.get("errors"):
        return _block(result, "panel_repair_work_order", "missing_final_gate_errors", work_order_path)

    forbidden_actions = work_order.get("forbidden_actions")
    if not isinstance(forbidden_actions, list):
        return _block(result, "panel_repair_work_order", "missing_forbidden_actions", work_order_path)
    missing_forbidden = sorted(REQUIRED_FORBIDDEN_ACTIONS - set(forbidden_actions))
    if missing_forbidden:
        return _block(result, "panel_repair_work_order", "missing_forbidden_actions:" + ",".join(missing_forbidden), work_order_path)

    result["panel_id"] = work_order.get("panel_id")
    result["owner_subagent"] = work_order["owner_subagent"]
    result["final_gate_status"] = final_gate["status"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_order", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_panel_repair_work_order(args.work_order)
    except Exception as exc:
        result = {
            "schema": "persona_dream.panel_repair_work_order_validation.v1",
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
