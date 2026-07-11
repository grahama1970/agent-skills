#!/usr/bin/env python3
"""Validate a Persona Dream serial pipeline-loop run receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_STOP_REASONS = {
    "all_serial_loops_accepted",
    "external_action_required",
    "local_repair_blocked",
    "local_repair_handler_not_implemented",
    "missing_active_loop",
    "max_iterations_reached",
    "work_order_written",
}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _block(result: dict[str, Any], reason: str) -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": "pipeline_loop_run_receipt", "reason": reason}
    return result


def validate_pipeline_loop_run(path: Path) -> dict[str, Any]:
    path = path.resolve()
    receipt = _read_json(path)
    if not isinstance(receipt, dict):
        raise ValueError("pipeline loop run receipt must be a JSON object")

    result: dict[str, Any] = {
        "schema": "persona_dream.pipeline_loop_run_validation.v1",
        "status": "PASS_PIPELINE_LOOP_RUN_RECEIPT",
        "receipt": str(path),
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in path.parts else "no",
        "live": "no",
        "exercised": "pipeline-loop receipt schema, iteration list, active-loop consistency, fail-closed policy, stop-reason contract",
        "unverified": "actual repair execution, public media hosting, live panel subagent generation/review, paid Kling submission",
    }

    if receipt.get("schema") != "persona_dream.pipeline_loop_run.v1":
        return _block(result, f"wrong_schema:{receipt.get('schema')}")
    if receipt.get("status") not in {"BLOCKED", "ACCEPTED"}:
        return _block(result, f"wrong_status:{receipt.get('status')}")
    stop_reason = receipt.get("stop_reason")
    if stop_reason not in ALLOWED_STOP_REASONS:
        return _block(result, f"wrong_stop_reason:{stop_reason}")

    iterations = receipt.get("iterations")
    if not isinstance(iterations, list) or not iterations:
        return _block(result, "missing_iterations")
    for index, iteration in enumerate(iterations, start=1):
        if not isinstance(iteration, dict):
            return _block(result, f"iteration_not_object:{index}")
        if iteration.get("iteration") != index:
            return _block(result, f"iteration_index_mismatch:{index}")
        if not isinstance(iteration.get("phase_count"), int) or iteration["phase_count"] < 1:
            return _block(result, f"invalid_phase_count:{index}")

    active_loop = receipt.get("active_loop")
    if receipt.get("status") == "BLOCKED":
        if not isinstance(active_loop, dict):
            return _block(result, "blocked_receipt_missing_active_loop")
        for field in ("loop", "phase", "blocker", "default_repair", "validator"):
            if not isinstance(active_loop.get(field), str) or not active_loop[field]:
                return _block(result, f"active_loop_missing:{field}")
        last_loop = iterations[-1].get("active_loop")
        if not isinstance(last_loop, dict) or last_loop.get("phase") != active_loop.get("phase"):
            return _block(result, "active_loop_iteration_mismatch")
        if stop_reason == "external_action_required" and active_loop.get("external_action_required") is not True:
            return _block(result, "external_stop_without_external_action")

    policy = receipt.get("policy")
    if not isinstance(policy, dict):
        return _block(result, "missing_policy")
    for field in (
        "kling_call_allowed",
        "public_upload_allowed_without_explicit_authorization",
        "nano_banana_final_panel_allowed",
        "implicit_local_repair_allowed",
    ):
        if policy.get(field) is not False:
            return _block(result, f"policy_must_be_false:{field}")

    if receipt.get("live") != "no":
        return _block(result, f"live_must_be_no:{receipt.get('live')}")

    result["loop"] = active_loop.get("loop") if isinstance(active_loop, dict) else None
    result["phase"] = active_loop.get("phase") if isinstance(active_loop, dict) else None
    result["stop_reason"] = stop_reason
    result["iteration_count"] = len(iterations)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_pipeline_loop_run(args.receipt)
    except Exception as exc:
        result = {
            "schema": "persona_dream.pipeline_loop_run_validation.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc)},
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        print(f"{result['status']} {blocker['reason']}" if blocker else result["status"])
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
