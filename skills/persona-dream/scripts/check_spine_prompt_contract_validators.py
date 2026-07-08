#!/usr/bin/env python3
"""Aggregate Tau checker for Persona Dream spine prompt-contract validators."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
GOAL_HASH = "sha256:74d9bfb73afb36ef935f7b14975dc5d2fa0f751e0f8f756069ee609ec6434dfc"


CASES = [
    {
        "phase": "01",
        "label": "phase01_good",
        "validator": ROOT / "scripts/validate_phase01_memory_residue_contract.py",
        "fixture": ROOT / "tests/fixtures/phase01/good_memory_residue_contract.json",
        "expected_status": "PASS_MEMORY_RESIDUE_CONTRACT",
        "expected_exit": 0,
    },
    {
        "phase": "01",
        "label": "phase01_bad",
        "validator": ROOT / "scripts/validate_phase01_memory_residue_contract.py",
        "fixture": ROOT / "tests/fixtures/phase01/bad_memory_residue_serialized_json_text.json",
        "expected_status": "BLOCKED_SERIALIZED_MEMORY_TEXT",
        "expected_exit": 1,
        "expected_blocker": "serialized_json_blob_in_prompt_text:source_residue[0].text",
    },
    {
        "phase": "02",
        "label": "phase02_good",
        "validator": ROOT / "scripts/validate_phase02_story_contract_prompt.py",
        "fixture": ROOT / "tests/fixtures/phase02/good_story_contract_prompt.json",
        "expected_status": "PASS_STORY_CONTRACT",
        "expected_exit": 0,
    },
    {
        "phase": "02",
        "label": "phase02_bad",
        "validator": ROOT / "scripts/validate_phase02_story_contract_prompt.py",
        "fixture": ROOT / "tests/fixtures/phase02/bad_story_contract_serialized_memory_blob.json",
        "expected_status": "BLOCKED_STORY_CONTRACT",
        "expected_exit": 1,
        "expected_blocker": "serialized_json_blob_in_prompt_text:typed_source_context.source_context",
    },
    {
        "phase": "06",
        "label": "phase06_good",
        "validator": ROOT / "scripts/validate_phase06_script_prompt_contract.py",
        "fixture": ROOT / "tests/fixtures/phase06/good_script_prompt_contract.json",
        "expected_status": "PASS_SCRIPT_CONTRACT",
        "expected_exit": 0,
    },
    {
        "phase": "06",
        "label": "phase06_bad",
        "validator": ROOT / "scripts/validate_phase06_script_prompt_contract.py",
        "fixture": ROOT / "tests/fixtures/phase06/bad_script_contract_loose_asset_usage.json",
        "expected_status": "BLOCKED_SCRIPT_CONTRACT",
        "expected_exit": 1,
        "expected_blocker": "loose_asset_usage:Embry",
    },
    {
        "phase": "07",
        "label": "phase07_good",
        "validator": ROOT / "scripts/validate_phase07_prompt_contract.py",
        "fixture": ROOT / "tests/fixtures/phase07/good_panel_prompt_contract_sb004.json",
        "expected_status": "PASS_PROMPT_CONTRACT",
        "expected_exit": 0,
    },
    {
        "phase": "07",
        "label": "phase07_bad",
        "validator": ROOT / "scripts/validate_phase07_prompt_contract.py",
        "fixture": ROOT / "tests/fixtures/phase07/bad_prompt_contract_kai_spatially_implied.json",
        "expected_status": "BLOCKED_PROMPT_CONTRACT",
        "expected_exit": 1,
        "expected_blocker": "required_identity_spatially_implied:Kai",
    },
]


def _read_stdin_handoff() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {
            "github": {"repo": "grahama1970/agent-skills", "target": "skills/persona-dream"},
            "goal": {
                "goal_id": "persona-dream-spine-prompt-contract-validator",
                "goal_version": 1,
                "goal_hash": GOAL_HASH,
            },
            "context": {},
        }
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("stdin handoff must be a JSON object")
    return payload


def _goal(start_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    goal = start_payload.get("goal")
    if not isinstance(goal, Mapping):
        raise SystemExit("handoff missing goal")
    return goal


def _github(start_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    github = start_payload.get("github")
    if isinstance(github, Mapping) and "repo" in github and "target" in github:
        return github
    return {"repo": "grahama1970/agent-skills", "target": "skills/persona-dream"}


def _run_case(case: dict[str, Any], receipt_root: Path) -> dict[str, Any]:
    case_receipt_dir = receipt_root / case["label"]
    cmd = [
        "python3",
        str(case["validator"]),
        str(case["fixture"]),
        "--receipt-dir",
        str(case_receipt_dir),
    ]
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, timeout=30, check=False)
    receipt_paths = sorted(case_receipt_dir.glob("*.json"))
    receipt = json.loads(receipt_paths[0].read_text(encoding="utf-8")) if receipt_paths else {}
    blockers = receipt.get("blockers") if isinstance(receipt.get("blockers"), list) else []
    errors: list[str] = []
    status = str(receipt.get("status") or proc.stdout.strip())
    if proc.returncode != case["expected_exit"]:
        errors.append(f"exit_mismatch:{proc.returncode}:expected:{case['expected_exit']}")
    if status != case["expected_status"]:
        errors.append(f"status_mismatch:{status}:expected:{case['expected_status']}")
    expected_blocker = case.get("expected_blocker")
    if expected_blocker and expected_blocker not in blockers:
        errors.append(f"missing_expected_blocker:{expected_blocker}")
    return {
        "label": case["label"],
        "phase": case["phase"],
        "command": cmd,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "status": status,
        "receipt": str(receipt_paths[0]) if receipt_paths else None,
        "blockers": blockers,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-dir", type=Path)
    args = parser.parse_args()

    start_payload = _read_stdin_handoff()
    artifact_dir = Path(
        os.environ.get(
            "TAU_HANDOFF_COMMAND_ARTIFACT_DIR",
            str(args.receipt_dir or "/tmp/persona-dream-spine-prompt-contract-validator"),
        )
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    case_receipt_root = artifact_dir / "case-receipts"
    case_receipt_root.mkdir(parents=True, exist_ok=True)

    results = [_run_case(case, case_receipt_root) for case in CASES]
    blockers = [f"{result['label']}:{error}" for result in results for error in result["errors"]]
    status = "PASS_SPINE_CONTRACT_GATE" if not blockers else "BLOCKED_SPINE_CONTRACT_GATE"
    aggregate = {
        "schema": "persona_dream.spine_prompt_contract_validator_receipt.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "blockers": blockers,
        "live": True,
        "mocked": False,
        "provider_live": False,
        "live_image_call_started": False,
        "case_results": results,
        "does_prove": [
            "01/02/06/07 positive prompt-contract fixtures pass deterministic validators.",
            "01/02/06/07 negative prompt-contract fixtures fail closed with expected blockers.",
            "Local hashed fixture references are checked for SHA-256 match where fixture paths are present.",
        ],
        "does_not_prove": [
            "Live memory recall/write quality.",
            "Story or script creative quality.",
            "Provider reference attachment.",
            "Image generation or visual identity pass.",
            "Storyboard panel generation time.",
            "Final storyboard approval.",
        ],
    }
    aggregate_path = artifact_dir / "spine_prompt_contract_validator_receipt.json"
    aggregate_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    handoff = {
        "schema": "tau.agent_handoff.v1",
        "github": _github(start_payload),
        "goal": _goal(start_payload),
        "previous_subagent": "spine-prompt-contract-validator",
        "context": {
            "summary": status,
            "artifacts": [str(aggregate_path)] + [str(result["receipt"]) for result in results if result["receipt"]],
            "spine_prompt_contract_validator": aggregate,
        },
        "result": {
            "status": status,
            "summary": "Spine prompt-contract validators passed positive and negative fixture gate." if not blockers else "Spine prompt-contract validator gate blocked.",
            "evidence": [str(aggregate_path)],
        },
        "rationale": "Creator/reviewer prompt contracts must reject unsafe prompt inputs before downstream generation.",
        "next_agent": {"name": "human", "executor": "human", "reason": "Review deterministic prompt-contract gate receipt."},
        "required_evidence": ["spine_prompt_contract_validator_receipt.json"],
        "stop_condition": "All validator fixtures pass expected outcomes or concrete blockers emitted.",
    }
    print(json.dumps(handoff, indent=2, sort_keys=True))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
