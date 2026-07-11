#!/usr/bin/env python3
"""Write a storyboard-panel generation/review work order.

The work order is a handoff artifact. It does not generate panel images, accept
visual semantics, call providers, or submit Kling tasks.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from validate_story_contract import validate_story_contract


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
DREAMER_AGENT = REPO / "agents/dreamer/AGENTS.md"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _first_existing(run_root: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        path = run_root / rel
        if path.exists():
            return path
    return None


def build_storyboard_panel_work_order(
    *,
    run_root: Path,
    story_contract: Path | None,
    blocker: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    if story_contract is None:
        story_contract = _first_existing(run_root, ["story_contract.json", "artifacts/story_contract.json"])
    if story_contract is None:
        raise ValueError("story_contract is required before storyboard panel work order")
    story_contract = story_contract.resolve()
    story = _read_json(story_contract)
    if not isinstance(story, dict):
        raise ValueError("story contract must be a JSON object")
    validation = validate_story_contract(story_contract, run_root=run_root)
    validation_blocker = validation.get("first_blocker")
    if validation_blocker:
        raise ValueError(f"story_contract_not_pass:{validation_blocker.get('reason')}")

    dream_packet = _first_existing(run_root, ["dream_packet.json", "artifacts/dream_packet.json"])
    first_blocker = blocker or {
        "phase": "storyboard_panel",
        "reason": "missing_artifact",
        "path": "receipts/storyboard_panel_receipt.json | artifacts/panel_001.json | panel_001.json | storyboard.json",
    }
    return {
        "schema": "persona_dream.storyboard_panel_work_order.v1",
        "created_at": created_at or _now_iso(),
        "created_by": "project_agent",
        "run_id": run_root.name,
        "status": "WORK_ORDER_READY_STORYBOARD_PANEL_REQUIRED",
        "owner_subagent": "dreamer",
        "purpose": "Create and review the first storyboard panel from the accepted story contract before any panel source, provider, or Kling claim.",
        "source_paths": {
            "run_root": str(run_root),
            "story_contract": str(story_contract),
            "dream_packet": str(dream_packet) if dream_packet is not None else "missing:dream_packet.json",
            "persona_dream_skill_contract": str(ROOT / "SKILL.md"),
            "project_knowledge": str(ROOT / "PROJECT_KNOWLEDGE.md"),
            "dreamer_agent_contract": str(DREAMER_AGENT),
        },
        "story_contract": {
            "schema": story.get("schema"),
            "artifact_id": story.get("artifact_id"),
            "status": story.get("status"),
            "target_duration_s": story.get("target_duration_s"),
            "speaking_characters": story.get("speaking_characters"),
            "story": story.get("story"),
        },
        "blocking_validation": {
            "command": "./run.sh validate-storyboard-panel <receipt> --run-root <run_root> --json",
            "status": "BLOCKED",
            "first_blocker": first_blocker,
        },
        "required_default_action": {
            "summary": "Generate a storyboard panel contract with continuity ledger and work-order artifacts from the accepted story.",
            "steps": [
                "Read dream_packet.json, story_contract.json, SKILL.md, and project knowledge.",
                "Write a panel work order with timing, beat, required visible entities, props, environment, and dynamic behaviors.",
                "Write a continuity ledger that explicitly checks story-to-panel continuity before image generation.",
                "Create or link the panel image only through the approved panel generation lane; do not use Nano Banana/Gemini final imagery.",
                "Run validate-storyboard-panel and pipeline-loop-status --direction forward, then report the next first blocker.",
            ],
        },
        "acceptance_criteria": [
            "receipts/storyboard_panel_receipt.json exists and validates",
            "continuity_ledger exists and records story-to-panel continuity checks",
            "work_order exists and names timing, beat, entities, props, environment, and dynamic behaviors",
            "validate-storyboard-panel returns PASS_STORYBOARD_PANEL",
            "pipeline-loop-status --direction forward advances to panel_repair_gate or a later blocker",
        ],
        "forbidden_actions": [
            "skip_continuity_ledger",
            "accept_panel_without_story_contract",
            "generate_final_panel_with_nano_banana_or_gemini",
            "rewrite_downstream_receipts_to_hide_missing_storyboard",
            "direct_kling_submit",
            "direct_paid_provider_call",
        ],
        "mocked": "no",
        "live": "no",
        "exercised": "local story contract validation, storyboard blocker packaging, continuity handoff policy",
        "unverified": "storyboard subagent execution, live panel generation, visual review, provider/Kling execution",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--story-contract", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        work_order = build_storyboard_panel_work_order(
            run_root=args.run_root,
            story_contract=args.story_contract,
            created_at=args.created_at,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = {"status": "WROTE", "output": str(args.output), "work_order": work_order}
    except Exception as exc:
        result = {
            "status": "BLOCKED",
            "first_blocker": {"phase": "storyboard_panel_work_order", "reason": str(exc)},
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} {result.get('output', '')}".strip())
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
