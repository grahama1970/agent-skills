#!/usr/bin/env python3
"""Write a one-panel repair work order for the panel-repair subagent.

The work order is a handoff artifact only. It does not generate images, call
providers, or claim provider readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from validate_panel_repair_gate import validate_receipt as validate_panel_repair_gate_receipt
from validate_storyboard_panel_receipt import validate_storyboard_panel_receipt


ROOT = Path(__file__).resolve().parents[1]
PANEL_REPAIR_AGENT = ROOT / "agents/persona-dream-panel-repair-gate/AGENTS.md"
PANEL_CREATOR_AGENT = ROOT / "agents/panel-creator/AGENTS.md"
PANEL_REVIEWER_AGENT = ROOT / "agents/panel-reviewer/AGENTS.md"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _maybe_existing_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or value.startswith("missing:"):
        return None
    return value


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base / path


def _first_existing(run_root: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        path = run_root / rel
        if path.exists():
            return path
    return None


def build_panel_repair_work_order(
    *,
    run_root: Path,
    panel_id: str,
    panel_repair_gate_receipt: Path | None = None,
    storyboard_panel_receipt: Path | None = None,
    source_work_order: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    receipt: dict[str, Any] | None = None
    receipt_path: Path | None = None
    final_gate_errors: list[str] = []
    generated_image: str | None = None
    storyboard_validation: dict[str, Any] | None = None

    if panel_repair_gate_receipt is not None:
        receipt_path = panel_repair_gate_receipt.resolve()
        loaded = _read_json(receipt_path)
        if not isinstance(loaded, dict):
            raise ValueError("panel repair gate receipt must be a JSON object")
        receipt = loaded
        final_gate_errors = validate_panel_repair_gate_receipt(
            receipt,
            require_provider_eligible=True,
            base_dir=receipt_path.parent,
        )
        generated_image = _maybe_existing_path(receipt.get("generated_image_path"))
    else:
        if storyboard_panel_receipt is None:
            storyboard_panel_receipt = _first_existing(
                run_root,
                ["receipts/storyboard_panel_receipt.json", "storyboard_panel_receipt.json"],
            )
        if storyboard_panel_receipt is None:
            raise ValueError("storyboard_panel_receipt is required when panel_repair_gate_receipt is missing")
        storyboard_panel_receipt = storyboard_panel_receipt.resolve()
        storyboard_validation = validate_storyboard_panel_receipt(storyboard_panel_receipt, run_root=run_root)
        storyboard_blocker = storyboard_validation.get("first_blocker")
        if storyboard_blocker:
            raise ValueError(f"storyboard_panel_receipt_not_pass:{storyboard_blocker.get('reason')}")
        storyboard = _read_json(storyboard_panel_receipt)
        if not isinstance(storyboard, dict):
            raise ValueError("storyboard panel receipt must be a JSON object")
        image_info = storyboard.get("image")
        if not isinstance(image_info, dict) or not isinstance(image_info.get("path"), str):
            raise ValueError("storyboard panel receipt missing image.path")
        generated_image = str(_resolve_path(run_root, image_info["path"]))
        final_gate_errors = [
            "panel_repair_gate_receipt_missing",
            "real_panel_generation_and_visual_review_required",
            "provider_eligibility_not_yet_established",
        ]

    image_hash = None
    if generated_image:
        image_path = Path(generated_image)
        if image_path.exists():
            image_hash = _sha256_file(image_path)

    source_paths: dict[str, str] = {
        "run_root": str(run_root),
        "persona_dream_skill_contract": str(ROOT / "SKILL.md"),
        "panel_repair_agent_contract": str(PANEL_REPAIR_AGENT),
        "panel_creator_agent_contract": str(PANEL_CREATOR_AGENT),
        "panel_reviewer_agent_contract": str(PANEL_REVIEWER_AGENT),
    }
    if receipt_path is not None:
        source_paths["panel_repair_gate_receipt"] = str(receipt_path)
    if storyboard_panel_receipt is not None:
        source_paths["storyboard_panel_receipt"] = str(storyboard_panel_receipt.resolve())
    if source_work_order is not None:
        source_paths["previous_work_order"] = str(source_work_order.resolve())

    if receipt is not None:
        for field in (
            "requirement_matrix",
            "script_coverage_receipt",
            "post_generation_script_coverage_receipt",
            "reference_receipt",
            "generation_receipt",
            "visual_review_receipt",
            "no_overlay_receipt",
            "callback_or_polling_plan",
            "cost_estimate",
            "status_transition_log",
        ):
            path = _maybe_existing_path(receipt.get(field))
            if path:
                source_paths[field] = path

    work_order = {
        "schema": "persona_dream.panel_repair_work_order.v1",
        "created_at": created_at or _now_iso(),
        "created_by": "project_agent",
        "run_id": str((receipt or {}).get("run_id") or run_root.name),
        "panel_id": panel_id,
        "owner_subagent": "persona-dream-panel-repair-gate",
        "delegated_subagents": ["panel-creator", "panel-reviewer"],
        "status": "WORK_ORDER_READY",
        "purpose": "Run the real panel creator/reviewer repair loop for one storyboard panel and produce a panel repair gate receipt without live Kling submission.",
        "source_paths": source_paths,
        "current_candidate": {
            "image_path": generated_image,
            "sha256": image_hash,
            "visual_style_status": (receipt or {}).get("visual_style_status") or "STORYBOARD_CONTRACT_ONLY",
            "visual_review_status": (receipt or {}).get("visual_review_status") or "MISSING_REAL_PANEL_VISUAL_REVIEW",
            "provider_eligibility": (receipt or {}).get("provider_eligibility", False),
            "provider_packet_status": (receipt or {}).get("provider_packet_status") or "BLOCKED_PROVIDER_GATE",
            "remaining_blockers": (receipt or {}).get("remaining_blockers", final_gate_errors),
        },
        "storyboard_panel_validation": storyboard_validation,
        "final_gate_validation": {
            "command": "./run.sh validate-panel-repair-gate <panel_repair_gate_receipt> --require-provider-eligible",
            "status": "PASS" if not final_gate_errors else "FAIL",
            "errors": final_gate_errors,
        },
        "required_default_action": {
            "summary": "Run panel-creator, panel-reviewer, then persona-dream-panel-repair-gate on this one storyboard panel.",
            "steps": [
                "Read storyboard_panel_receipt.json, the continuity ledger, panel work order, SKILL.md, and project knowledge.",
                "Create the real panel image through the approved Scillm/GPT image lane; do not use Nano Banana or Gemini final imagery.",
                "Run independent read-only visual review through panel-reviewer for the generated image.",
                "Write the requirement matrix, generation receipt, script coverage receipts, visual review receipt, no-overlay receipt, and provider-media readiness fields.",
                "Emit request.json, response.json, panel_repair_gate_receipt.json, and status_transition_log.jsonl.",
            ],
        },
        "acceptance_criteria": [
            "panel_repair_gate_receipt.status == PASS_PANEL_REVIEWED",
            "all panel repair subgates are PASS",
            "provider_eligibility == true",
            "provider_packet_status == PROVIDER_READY",
            "remaining_blockers is empty",
            "nano_banana_fallback_used is absent or false; Gemini/Nano Banana final panel generation is not accepted",
            "live_call_performed == false and paid_call_performed == false unless explicitly authorized later",
        ],
        "forbidden_actions": [
            "direct_kling_submit",
            "direct_paid_provider_call",
            "direct_provider_image_api",
            "nano_banana_final_panel_generation",
            "gemini_final_panel_generation",
            "unreceipted_image_generation",
            "provider readiness by prose-only rewrite",
        ],
        "mocked": "no",
        "live": "no",
        "exercised": "local receipt parse, final panel repair gate validation, source path packaging",
        "unverified": "subagent execution, live image generation, independent visual rereview, provider media hosting, Kling submission",
    }
    return work_order


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--panel-id", required=True)
    parser.add_argument("--panel-repair-gate-receipt", type=Path)
    parser.add_argument("--storyboard-panel-receipt", type=Path)
    parser.add_argument("--source-work-order", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        work_order = build_panel_repair_work_order(
            run_root=args.run_root,
            panel_id=args.panel_id,
            panel_repair_gate_receipt=args.panel_repair_gate_receipt,
            storyboard_panel_receipt=args.storyboard_panel_receipt,
            source_work_order=args.source_work_order,
            created_at=args.created_at,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = {"status": "WROTE", "output": str(args.output), "work_order": work_order}
    except Exception as exc:
        result = {
            "status": "BLOCKED",
            "first_blocker": {"phase": "panel_repair_work_order", "reason": str(exc)},
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} {result.get('output', '')}".strip())
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
