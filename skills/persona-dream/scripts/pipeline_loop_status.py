#!/usr/bin/env python3
"""Report the active serial while-loop for a Persona Dream run root.

This is a transparent controller receipt, not a provider executor. It validates
the run root, identifies the first blocked phase, maps that phase to the
serial while-loop that owns repair, and stops before external side effects.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from validate_run_root_pipeline import validate_run_root


LOOP_BY_PHASE: dict[str, dict[str, Any]] = {
    "kling_scene_packet": {
        "loop": "kling_packet_loop",
        "validator": "validate-run-root --direction backward",
        "default_repair": "Regenerate the blocked one-scene Kling review packet with paid_call_authorized=false and stable source_artifacts.",
        "external_action_required": False,
    },
    "local_provider_media_lock": {
        "loop": "provider_media_loop",
        "validator": "validate-local-media-lock",
        "default_repair": "Rebuild the local provider media lock from the exact panel source bytes and record provider_accessible=false.",
        "external_action_required": False,
    },
    "provider_media_publication_work_order": {
        "loop": "provider_media_loop",
        "validator": "validate-provider-media-publication-work-order",
        "default_repair": "Write a publication work order that names the exact locked media, required public-upload authorization, forbidden actions, rollback path, and verification commands.",
        "external_action_required": False,
    },
    "provider_media_local_staging": {
        "loop": "provider_media_loop",
        "validator": "validate-provider-media-local-staging",
        "default_repair": "Stage the locked media bytes to the proposed repo path and validate local path/hash parity without claiming public availability.",
        "external_action_required": False,
    },
    "provider_media_publication_authorization": {
        "loop": "provider_media_loop",
        "validator": "validate-provider-media-publication-authorization",
        "default_repair": "Supply an explicit authorization receipt for the exact staged asset, locked SHA-256, target repo path, and proposed public URL before any public upload or git push.",
        "external_action_required": True,
        "requires_authorization": ["public_upload_of_panel_image", "git_commit_and_push_or_equivalent_public_asset_publish"],
    },
    "provider_media_public_probe": {
        "loop": "provider_media_loop",
        "validator": "validate-provider-media-url",
        "default_repair": "Publish the exact staged PNG to the approved stable public URL, rerun validate-provider-media-url, then apply the passing probe.",
        "external_action_required": True,
        "requires_authorization": ["public_upload_of_panel_image", "git_commit_and_push_or_equivalent_public_asset_publish"],
    },
    "panel_source_receipt": {
        "loop": "panel_source_loop",
        "validator": "validate-panel-source",
        "default_repair": "Regenerate panel_source_receipt.json from a provider-eligible panel repair gate receipt.",
        "external_action_required": False,
    },
    "panel_repair_gate": {
        "loop": "panel_review_loop",
        "validator": "validate-panel-repair-gate --require-provider-eligible",
        "default_repair": "Run the panel subagent repair loop; reject Nano Banana/Gemini final imagery, repair the exact visual/text blocker, and write a provider-eligible receipt.",
        "external_action_required": False,
    },
    "visual_review_receipt": {
        "loop": "panel_review_loop",
        "validator": "validate-visual-review",
        "default_repair": "Run the visual review subagent against the real panel image and write the eight-check visual review receipt.",
        "external_action_required": False,
    },
    "storyboard_panel": {
        "loop": "storyboard_loop",
        "validator": "validate-storyboard-panel",
        "default_repair": "Write or regenerate the storyboard panel receipt linking image, timing, continuity ledger, and panel work order.",
        "external_action_required": False,
    },
    "story_contract": {
        "loop": "story_loop",
        "validator": "validate-story-contract",
        "default_repair": "Repair or regenerate the story contract from the current upstream idea/memory revision and mark downstream artifacts stale as needed.",
        "external_action_required": False,
    },
    "dream_packet": {
        "loop": "dream_packet_loop",
        "validator": "validate-dream-packet",
        "default_repair": "Generate or repair the dream packet from current memory residue, contact sheet, frame prompts, and reflection receipts.",
        "external_action_required": False,
    },
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _active_loop(first_blocker: dict[str, Any] | None) -> dict[str, Any] | None:
    if first_blocker is None:
        return None
    phase = first_blocker.get("phase")
    if not isinstance(phase, str):
        return {
            "loop": "unknown_loop",
            "phase": phase,
            "validator": "validate-run-root --direction backward",
            "default_repair": "Inspect first_blocker and add an explicit phase mapping before repairing.",
            "external_action_required": False,
        }
    mapped = dict(LOOP_BY_PHASE.get(phase, {}))
    if not mapped:
        mapped = {
            "loop": "unknown_loop",
            "validator": "validate-run-root --direction backward",
            "default_repair": "Inspect first_blocker and add an explicit phase mapping before repairing.",
            "external_action_required": False,
        }
    mapped["phase"] = phase
    mapped["blocker"] = first_blocker.get("reason")
    mapped["path"] = first_blocker.get("path")
    return mapped


def _loop_backlog(validation: dict[str, Any]) -> list[dict[str, Any]]:
    phases = validation.get("phases")
    if not isinstance(phases, list):
        return []

    backlog: list[dict[str, Any]] = []
    for item in phases:
        if not isinstance(item, dict) or item.get("status") != "BLOCKED":
            continue
        loop = _active_loop(
            {
                "phase": item.get("phase"),
                "reason": item.get("blocker"),
                "path": item.get("path"),
            }
        )
        if loop is None:
            continue
        loop["sequence"] = len(backlog) + 1
        backlog.append(loop)
    return backlog


def build_pipeline_loop_status(
    *,
    run_root: Path,
    direction: str = "backward",
    generated_at: str | None = None,
) -> dict[str, Any]:
    validation = validate_run_root(run_root, direction=direction)
    first_blocker = validation.get("first_blocker")
    active_loop = _active_loop(first_blocker if isinstance(first_blocker, dict) else None)
    loop_backlog = _loop_backlog(validation)
    status = "BLOCKED" if first_blocker else "ALL_SERIAL_LOOPS_ACCEPTED"
    stop_condition = (
        "No external action performed; repair the active_loop.default_repair, write/refresh receipts, then rerun this command."
        if first_blocker
        else "All local serial loop validators accepted for this validation direction; provider execution still requires separate approval."
    )
    if active_loop and active_loop.get("external_action_required"):
        stop_condition = "External authorization is required before this loop can repair the blocker. Do not publish, push, or call Kling without approval."

    return {
        "schema": "persona_dream.pipeline_loop_status.v1",
        "generated_at": generated_at or _now_iso(),
        "run_root": str(run_root),
        "direction": direction,
        "status": status,
        "active_loop": active_loop,
        "loop_backlog": loop_backlog,
        "validation": validation,
        "loop_model": {
            "shape": "serial_pipeline_of_fail_closed_while_loops",
            "rule": "validate phase, repair first blocker, write receipt, rebuild report, repeat; convert to DAG only after serial loops are proven.",
        },
        "policy": {
            "kling_call_allowed": False,
            "public_upload_allowed_without_explicit_authorization": False,
            "nano_banana_final_panel_allowed": False,
        },
        "stop_condition": stop_condition,
        "mocked": validation.get("mocked"),
        "live": "no",
        "exercised": "local run-root validation, first-blocker to serial-loop mapping, fail-closed repair action selection",
        "unverified": "actual repair execution, public media hosting if blocked there, live panel subagent generation/review, paid Kling submission",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--direction", choices=["forward", "backward"], default="backward")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--generated-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = build_pipeline_loop_status(
            run_root=args.run_root,
            direction=args.direction,
            generated_at=args.generated_at,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        result = {
            "schema": "persona_dream.pipeline_loop_status.v1",
            "status": "BLOCKED",
            "active_loop": {
                "loop": "pipeline_loop_status",
                "phase": "schema_or_parse",
                "blocker": str(exc),
                "default_repair": "Fix pipeline-loop-status input/schema error, then rerun.",
                "external_action_required": False,
            },
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        loop = result.get("active_loop") or {}
        print(f"{result['status']} {loop.get('loop', 'no_active_loop')} {loop.get('phase', '')}".strip())
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
