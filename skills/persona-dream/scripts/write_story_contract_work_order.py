#!/usr/bin/env python3
"""Write a story-contract review work order.

The work order is a handoff artifact. It does not mark a story accepted,
regenerate content, touch downstream panels, or call a provider.
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


def build_story_contract_work_order(
    *,
    run_root: Path,
    story_contract: Path | None = None,
    blocker: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    story_contract = story_contract.resolve() if story_contract is not None else None
    dream_packet = next(
        (
            candidate
            for candidate in (run_root / "dream_packet.json", run_root / "artifacts/dream_packet.json")
            if candidate.exists()
        ),
        None,
    )

    if story_contract is not None:
        contract = _read_json(story_contract)
        if not isinstance(contract, dict):
            raise ValueError("story contract must be a JSON object")
        validation = validate_story_contract(story_contract, run_root=run_root)
        validation_blocker = validation.get("first_blocker")
        current_contract = {
            "exists": True,
            "schema": contract.get("schema"),
            "artifact_id": contract.get("artifact_id"),
            "status": contract.get("status"),
            "target_duration_s": contract.get("target_duration_s"),
            "speaking_characters": contract.get("speaking_characters"),
            "story_chars": len(str(contract.get("story", ""))),
        }
        story_contract_value = str(story_contract)
    else:
        validation_blocker = blocker or {
            "phase": "story_contract",
            "reason": "missing_artifact",
            "path": "story_contract.json | artifacts/story_contract.json",
        }
        validation = {
            "status": "BLOCKED",
            "first_blocker": validation_blocker,
        }
        current_contract = {
            "exists": False,
            "schema": None,
            "artifact_id": None,
            "status": "MISSING",
            "target_duration_s": None,
            "speaking_characters": [],
            "story_chars": 0,
        }
        story_contract_value = "missing:story_contract.json | artifacts/story_contract.json"

    return {
        "schema": "persona_dream.story_contract_work_order.v1",
        "created_at": created_at or _now_iso(),
        "created_by": "project_agent",
        "run_id": run_root.name,
        "status": "WORK_ORDER_READY_STORY_REVIEW_REQUIRED",
        "owner_subagent": "dreamer",
        "purpose": "Review or regenerate the story contract from the current upstream idea/memory revision before any downstream storyboard, panel, provider, or Kling claim.",
        "source_paths": {
            "run_root": str(run_root),
            "story_contract": story_contract_value,
            "dream_packet": str(dream_packet) if dream_packet is not None else "missing:dream_packet.json",
            "persona_dream_skill_contract": str(ROOT / "SKILL.md"),
            "project_knowledge": str(ROOT / "PROJECT_KNOWLEDGE.md"),
            "dreamer_agent_contract": str(DREAMER_AGENT),
        },
        "current_contract": current_contract,
        "blocking_validation": {
            "command": "./run.sh validate-story-contract <story_contract> --run-root <run_root> --json",
            "status": validation.get("status"),
            "first_blocker": validation_blocker,
        },
        "required_default_action": {
            "summary": "Run a bounded story review/regeneration pass before any storyboard or panel acceptance.",
            "steps": [
                "Re-read the current idea, memory residue, story contract, SKILL.md, and PROJECT_KNOWLEDGE.md.",
                "If the current story is semantically acceptable, write a reviewed accepted story contract plus review receipt; do not edit only the status field without review evidence.",
                "If the story is not acceptable or upstream revisions are stale, regenerate the story contract from the current upstream idea/memory revision.",
                "Mark downstream storyboard, panel, provider packet, panel source, and report artifacts stale unless a migration receipt proves they still derive from the accepted story.",
                "Run validate-story-contract, then validate-run-root --direction backward, and report the next first blocker.",
            ],
        },
        "acceptance_criteria": [
            "story_contract.status is one of ACCEPTED_AUTOMATED, ACCEPTED_MANUAL, PASS_STORY_CONTRACT, or STORY_READY",
            "story contract has review/regeneration evidence tied to the current upstream idea/memory revision",
            "downstream artifacts are either regenerated from the accepted story or explicitly marked stale",
            "validate-story-contract returns PASS_STORY_CONTRACT",
            "validate-run-root --direction backward advances to the next blocker",
        ],
        "forbidden_actions": [
            "mark_story_accepted_without_review",
            "rewrite_status_only_to_bypass_gate",
            "rewrite_panel_or_provider_receipts_to_hide_story_staleness",
            "accept_downstream_panels_from_stale_story",
            "direct_kling_submit",
            "direct_paid_provider_call",
        ],
        "mocked": "no",
        "live": "no",
        "exercised": "local story contract parse, story contract validator execution, source path packaging, review handoff policy",
        "unverified": "semantic story acceptance, live memory grounding, dreamer subagent execution, downstream regeneration, panel review, provider/Kling execution",
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
        work_order = build_story_contract_work_order(
            run_root=args.run_root,
            story_contract=args.story_contract,
            blocker=None,
            created_at=args.created_at,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = {"status": "WROTE", "output": str(args.output), "work_order": work_order}
    except Exception as exc:
        result = {
            "status": "BLOCKED",
            "first_blocker": {"phase": "story_contract_work_order", "reason": str(exc)},
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} {result.get('output', '')}".strip())
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
