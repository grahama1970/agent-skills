#!/usr/bin/env python3
"""CLI for the interface research, mockup, and implementation tournament."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pipeline_common import (  # noqa: E402
    PHASES,
    REVIEW_SCHEMA,
    append_event,
    read_json,
    utc_now,
    validate_manifest,
    write_json,
)
from pipeline_planner import plan_pipeline  # noqa: E402
from research_phase import execute_research, update_status  # noqa: E402

def next_phase(phase: str) -> str:
    try:
        index = PHASES.index(phase)
    except ValueError:
        return phase
    return PHASES[min(index + 1, len(PHASES) - 1)]


def record_review(run_dir: Path, phase: str, receipt_path: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if phase not in PHASES:
        raise ValueError(f"unknown phase: {phase}")
    receipt = read_json(receipt_path.resolve())
    if receipt.get("schema") != REVIEW_SCHEMA:
        raise ValueError(f"review receipt schema must be {REVIEW_SCHEMA!r}")
    if receipt.get("phase") != phase:
        raise ValueError(f"review receipt phase must be {phase!r}")
    verdict = receipt.get("verdict")
    if verdict not in {"PASS", "NEEDS_CHANGES", "BLOCKED"}:
        raise ValueError("review receipt verdict must be PASS, NEEDS_CHANGES, or BLOCKED")
    findings = receipt.get("findings")
    if not isinstance(findings, list) or not all(isinstance(item, str) for item in findings):
        raise ValueError("review receipt findings must be a list of strings")
    destination = run_dir / "reviews" / f"{phase}.json"
    write_json(destination, receipt)
    if verdict == "PASS":
        current = next_phase(phase)
        pipeline_status = "NEEDS_REVIEW" if current != "human_promotion" else "AWAITING_HUMAN"
    elif verdict == "NEEDS_CHANGES":
        current = phase
        pipeline_status = "NEEDS_CHANGES"
    else:
        current = phase
        pipeline_status = "BLOCKED"
    update_status(run_dir, pipeline_status=pipeline_status, current_phase=current, phase=phase, phase_status=verdict)
    append_event(run_dir, "review_recorded", phase=phase, verdict=verdict, receipt=str(destination))
    return {
        "schema": "interface_design_pipeline.record_review_result.v1",
        "status": pipeline_status,
        "phase": phase,
        "verdict": verdict,
        "stored_receipt": str(destination),
        "current_phase": current,
    }


def command_validate(args: argparse.Namespace) -> int:
    manifest = read_json(Path(args.manifest).resolve())
    errors = validate_manifest(manifest)
    payload = {"valid": not errors, "errors": errors}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not errors else 1


def command_plan(args: argparse.Namespace) -> int:
    try:
        result = plan_pipeline(Path(args.manifest), Path(args.output) if args.output else None)
    except ValueError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def command_research(args: argparse.Namespace) -> int:
    try:
        result = execute_research(
            Path(args.run_dir),
            execute=args.execute,
            jobs=args.jobs,
            timeout=args.timeout,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] != "BLOCKED" else 1


def command_status(args: argparse.Namespace) -> int:
    status = read_json(Path(args.run_dir).resolve() / "status.json")
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


def command_record_review(args: argparse.Namespace) -> int:
    try:
        result = record_review(Path(args.run_dir), args.phase, Path(args.receipt))
    except ValueError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research -> mockup -> implementation interface design tournament.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a pipeline manifest.")
    validate.add_argument("--manifest", required=True)
    validate.set_defaults(func=command_validate)

    plan = subparsers.add_parser("plan", help="Compile phase plans, loop nodes, and receipts.")
    plan.add_argument("--manifest", required=True)
    plan.add_argument("--output", help="Exact run directory; default uses manifest output_root and timestamp.")
    plan.set_defaults(func=command_plan)

    research = subparsers.add_parser("research", help="Inspect or execute GitHub + Brave research lanes.")
    research.add_argument("--run-dir", required=True)
    research.add_argument("--execute", action="store_true", help="Actually call the existing search skills.")
    research.add_argument("--jobs", type=int, default=4)
    research.add_argument("--timeout", type=int, default=300)
    research.add_argument("--print-json", action="store_true", help=argparse.SUPPRESS)
    research.set_defaults(func=command_research)

    status = subparsers.add_parser("status", help="Print the durable pipeline status artifact.")
    status.add_argument("--run-dir", required=True)
    status.set_defaults(func=command_status)

    review = subparsers.add_parser("record-review", help="Validate and record a subagent review receipt.")
    review.add_argument("--run-dir", required=True)
    review.add_argument("--phase", required=True, choices=PHASES)
    review.add_argument("--receipt", required=True)
    review.set_defaults(func=command_record_review)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
