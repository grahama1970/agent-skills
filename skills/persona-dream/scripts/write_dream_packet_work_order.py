#!/usr/bin/env python3
"""Write a dream-packet generation/repair work order.

The work order is a handoff artifact. It does not recall memory, fabricate
residue, create a packet, write memory, generate panels, or call providers.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from validate_dream_packet import validate_dream_packet


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
DREAMER_AGENT = REPO / "agents/dreamer/AGENTS.md"
MEMORY_AGENT = REPO / "agents/memory/AGENTS.md"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _maybe_read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _validate_existing_packet(path: Path, *, run_root: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return validate_dream_packet(path, run_root=run_root)


def build_dream_packet_work_order(
    *,
    run_root: Path,
    dream_packet: Path | None = None,
    blocker: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    packet_path = (dream_packet or (run_root / "dream_packet.json")).resolve()
    packet = _maybe_read_json(packet_path)
    validation = _validate_existing_packet(packet_path, run_root=run_root)
    validation_blocker = validation.get("first_blocker") if isinstance(validation, dict) else None
    first_blocker = validation_blocker or blocker or {
        "phase": "dream_packet",
        "reason": "missing_artifact",
        "path": "dream_packet.json | artifacts/dream_packet.json",
    }

    current_packet: dict[str, Any] = {
        "exists": packet is not None,
        "path": str(packet_path),
    }
    if isinstance(packet, dict):
        current_packet.update(
            {
                "schema": packet.get("schema"),
                "run_id": packet.get("run_id"),
                "mode": packet.get("mode"),
                "persona_id": packet.get("persona", {}).get("id")
                if isinstance(packet.get("persona"), dict)
                else None,
                "residue_item_count": len(packet.get("residue_items", []))
                if isinstance(packet.get("residue_items"), list)
                else None,
                "frame_prompt_count": len(packet.get("frame_prompts", []))
                if isinstance(packet.get("frame_prompts"), list)
                else None,
                "contact_sheet": packet.get("contact_sheet"),
            }
        )

    return {
        "schema": "persona_dream.dream_packet_work_order.v1",
        "created_at": created_at or _now_iso(),
        "created_by": "project_agent",
        "run_id": run_root.name,
        "status": "WORK_ORDER_READY_DREAM_PACKET_REQUIRED",
        "owner_subagent": "dreamer",
        "delegated_subagents": ["memory"],
        "purpose": "Generate or repair the beginning-of-pipeline dream packet from real recalled residue and local receipt-backed artifacts before story, storyboard, panel, provider, or Kling claims.",
        "source_paths": {
            "run_root": str(run_root),
            "dream_packet_candidate": str(packet_path),
            "persona_dream_skill_contract": str(ROOT / "SKILL.md"),
            "project_knowledge": str(ROOT / "PROJECT_KNOWLEDGE.md"),
            "dreamer_agent_contract": str(DREAMER_AGENT),
            "memory_agent_contract": str(MEMORY_AGENT),
        },
        "current_packet": current_packet,
        "blocking_validation": {
            "command": "./run.sh validate-dream-packet <dream_packet> --run-root <run_root> --json",
            "status": validation.get("status") if isinstance(validation, dict) else "BLOCKED",
            "first_blocker": first_blocker,
        },
        "required_default_action": {
            "summary": "Create a receipt-backed dream packet from current persona memory residue and local contact-sheet evidence.",
            "steps": [
                "Recall or load real persona residue; if no residue exists, block with no_dream instead of fabricating source ids.",
                "Write residue_links.json and contradiction_report.json preserving source_id, scope, and recall metadata.",
                "Create dream_prompt.txt, frame_prompts.json, contact_sheet.png, and dream_reflection.md as local artifacts.",
                "Write dream_packet.json with schema persona_dream.packet.v1, mode, persona id, residue_items, dream_prompt, frame_prompts, contact_sheet, and reflection.",
                "Keep memory_write_receipt.json skipped unless explicit write-memory authorization is present.",
                "Run validate-dream-packet, then validate-run-root --direction backward, and report the next first blocker.",
            ],
        },
        "acceptance_criteria": [
            "dream_packet.json exists at run root or declared artifact path",
            "validate-dream-packet returns PASS_DREAM_PACKET",
            "residue_items are nonempty and each item has a nonempty source_id",
            "contact_sheet points to an existing PNG with a PNG signature",
            "memory_write_receipt is skipped unless write-memory was explicitly requested",
            "validate-run-root --direction backward advances to story_contract or a later concrete blocker",
        ],
        "forbidden_actions": [
            "fabricate_residue_source_ids",
            "treat_about_text_as_residue_without_memory_source",
            "write_memory_without_explicit_authorization",
            "mark_dream_packet_pass_without_contact_sheet_png",
            "rewrite_downstream_story_or_panel_receipts_to_hide_missing_packet",
            "direct_kling_submit",
            "direct_paid_provider_call",
        ],
        "mocked": "no",
        "live": "no",
        "exercised": "local run-root packaging, optional dream packet validator execution, missing-packet blocker capture, repair handoff policy",
        "unverified": "live memory recall, residue semantic grounding, dreamer subagent execution, contact sheet generation quality, story/panel/provider/Kling execution",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--dream-packet", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        work_order = build_dream_packet_work_order(
            run_root=args.run_root,
            dream_packet=args.dream_packet,
            created_at=args.created_at,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = {"status": "WROTE", "output": str(args.output), "work_order": work_order}
    except Exception as exc:
        result = {
            "status": "BLOCKED",
            "first_blocker": {"phase": "dream_packet_work_order", "reason": str(exc)},
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} {result.get('output', '')}".strip())
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
