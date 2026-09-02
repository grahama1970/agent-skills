#!/usr/bin/env python3
"""Validate the canonical executable Persona Dream spine contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts" / "dream_spine.v1.yaml"
ACTIVE_CONTRACT_DIR = ROOT / "contracts"
ARCHIVE_CONTRACT_DIR = ACTIVE_CONTRACT_DIR / "archive"
REQUIRED_STEP_FIELDS = (
    "id",
    "name",
    "command",
    "args",
    "produces",
    "proves",
    "does_not_prove",
)
PASS_STATUS = "PASS_PERSONA_DREAM_PIPELINE_CONTRACT"
BLOCKED_STATUS = "BLOCKED_PERSONA_DREAM_PIPELINE_CONTRACT"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pipeline contract must be a YAML mapping")
    return data


def _run_sh_commands() -> set[str]:
    run_sh = (ROOT / "run.sh").read_text(encoding="utf-8")
    commands: set[str] = set()
    for raw in run_sh.splitlines():
        stripped = raw.strip()
        if stripped.endswith(")") and " " not in stripped:
            commands.update(part for part in stripped[:-1].split("|") if part)
    return commands


def _active_competing_contracts(canonical_path: Path) -> list[str]:
    competing: list[str] = []
    for path in sorted(ACTIVE_CONTRACT_DIR.glob("*.yaml")):
        if path.resolve() == canonical_path:
            continue
        try:
            data = _load_yaml(path)
        except Exception:
            continue
        schema = str(data.get("schema") or "")
        status = str(data.get("status") or "")
        if status == "RETIRED_REFERENCE_NOT_CANONICAL":
            continue
        if schema.startswith("persona_dream.pipeline") or status == PASS_STATUS:
            competing.append(str(path))
    return competing


def _retired_references() -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    if not ARCHIVE_CONTRACT_DIR.is_dir():
        return references
    for path in sorted(ARCHIVE_CONTRACT_DIR.glob("*.yaml")):
        try:
            data = _load_yaml(path)
        except Exception:
            continue
        if str(data.get("status") or "") == "RETIRED_REFERENCE_NOT_CANONICAL":
            references.append({
                "path": str(path.resolve()),
                "superseded_by": str(data.get("superseded_by") or ""),
            })
    for path in sorted(ACTIVE_CONTRACT_DIR.glob("*.yaml")):
        try:
            data = _load_yaml(path)
        except Exception:
            continue
        if str(data.get("status") or "") == "RETIRED_REFERENCE_NOT_CANONICAL":
            references.append({
                "path": str(path.resolve()),
                "superseded_by": str(data.get("superseded_by") or ""),
            })
    return references


def check_pipeline_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    path = path.resolve()
    blockers: list[str] = []
    data = _load_yaml(path)

    if data.get("schema") != "persona_dream.dream_spine.v1":
        blockers.append("BLOCKED_SCHEMA_NOT_DREAM_SPINE_V1")

    if data.get("terminates_at") != "chatterbox_conversation":
        blockers.append("BLOCKED_TERMINAL_NODE_NOT_CHATTERBOX_CONVERSATION")

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        blockers.append("BLOCKED_STEPS_NOT_NONEMPTY_LIST")
        steps = []

    commands = _run_sh_commands()
    step_ids: list[str] = []
    produced_artifacts: list[str] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            blockers.append(f"BLOCKED_STEP_{index}_NOT_MAPPING")
            continue
        step_id = str(step.get("id") or "")
        step_ids.append(step_id)
        for field in REQUIRED_STEP_FIELDS:
            if field not in step:
                blockers.append(f"BLOCKED_STEP_{step_id or index}_MISSING_{field.upper()}")
        command = str(step.get("command") or "")
        if command and command not in commands:
            blockers.append(f"BLOCKED_STEP_{step_id or index}_UNKNOWN_COMMAND:{command}")
        produces = step.get("produces")
        if not isinstance(produces, list) or not produces:
            blockers.append(f"BLOCKED_STEP_{step_id or index}_NO_PRODUCES")
        else:
            produced_artifacts.extend(str(item) for item in produces)

    if len(step_ids) != len(set(step_ids)):
        blockers.append("BLOCKED_DUPLICATE_STEP_IDS")
    if step_ids and step_ids[-1] != data.get("terminates_at"):
        blockers.append("BLOCKED_LAST_STEP_DOES_NOT_MATCH_TERMINATES_AT")
    if "dream_journal.md" not in produced_artifacts:
        blockers.append("BLOCKED_JOURNAL_MARKDOWN_NOT_DECLARED")
    if "journal.wav" not in produced_artifacts:
        blockers.append("BLOCKED_JOURNAL_AUDIO_NOT_DECLARED")
    if "conversation.jsonl" not in produced_artifacts:
        blockers.append("BLOCKED_CONVERSATION_JSONL_NOT_DECLARED")
    if "dynamic_conversation_receipt.v1.json" not in produced_artifacts:
        blockers.append("BLOCKED_DYNAMIC_CONVERSATION_RECEIPT_NOT_DECLARED")

    competing_contracts = _active_competing_contracts(path)
    if competing_contracts:
        blockers.append("BLOCKED_COMPETING_ACTIVE_PIPELINE_CONTRACT")

    return {
        "schema": "persona_dream.pipeline_contract_check_receipt.v1",
        "created_at": _now_iso(),
        "contract_path": str(path),
        "contract_sha256": _sha256(path),
        "canonical_contract_schema": data.get("schema"),
        "status": PASS_STATUS if not blockers else BLOCKED_STATUS,
        "step_count": len(step_ids),
        "terminal_step": data.get("terminates_at"),
        "node_set": step_ids,
        "produced_artifacts": sorted(set(produced_artifacts)),
        "active_competing_contracts": competing_contracts,
        "retired_references": _retired_references(),
        "mocked": "no",
        "live": "no",
        "actual_provider_call_attempts": 0,
        "blockers": blockers,
        "claims": {
            "proves": [
                "the executable Persona Dream DAG node set is derived from one committed spine contract",
                "no active competing persona_dream.pipeline contract is present in contracts/",
                "the spine declares its terminal journal and Chatterbox conversation artifacts",
            ] if not blockers else [],
            "does_not_prove": [
                "runtime spine execution",
                "dream quality",
                "voice synthesis quality",
                "optional video branch completion",
                "provider readiness",
                "provider submit",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = check_pipeline_contract(args.contract)
    except Exception as exc:  # noqa: BLE001 - fail-closed receipt.
        receipt = {
            "schema": "persona_dream.pipeline_contract_check_receipt.v1",
            "created_at": _now_iso(),
            "contract_path": str(args.contract),
            "status": BLOCKED_STATUS,
            "blockers": [f"BLOCKED_SCHEMA_OR_PARSE:{exc}"],
            "mocked": "no",
            "live": "no",
            "actual_provider_call_attempts": 0,
        }

    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
