#!/usr/bin/env python3
"""Aggregate checker for the Persona Dream spine chain manifest gate."""
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
VALIDATOR = ROOT / "scripts/validate_persona_dream_spine_chain.py"
GOOD_MANIFEST = ROOT / "tests/fixtures/spine_chain/good/spine_chain_manifest.v1.json"
NEGATIVE_ROOT = ROOT / "tests/fixtures/spine_chain/negative"
GOAL_HASH = "sha256:3df4d7875d50b0b81c30ac57b55eaf18800d97e6c15add11f040ea69da975147"


EXPECTED_NEGATIVE_BLOCKERS = {
    "bad_chain_phase02_phase01_hash_mismatch.json": {"BLOCKED_INTER_CONTRACT_HASH_MISMATCH"},
    "bad_chain_phase06_missing_phase02_contract.json": {"BLOCKED_MISSING_UPSTREAM_CONTRACT"},
    "bad_chain_phase07_wrong_phase06_hash.json": {"BLOCKED_INTER_CONTRACT_HASH_MISMATCH"},
    "bad_chain_compiled_prompt_hash_missing.json": {"BLOCKED_COMPILED_PROMPT_HASH_MISSING"},
    "bad_chain_compiled_prompt_hash_mismatch.json": {"BLOCKED_COMPILED_PROMPT_HASH_MISMATCH"},
    "bad_chain_compiled_prompt_contract_hash_mismatch.json": {"BLOCKED_COMPILED_PROMPT_CONTRACT_HASH_MISMATCH"},
    "bad_chain_compiled_prompt_contract_path_mismatch.json": {"BLOCKED_COMPILED_PROMPT_CONTRACT_PATH_MISMATCH"},
    "bad_chain_compiled_prompt_embedded_in_contract.json": {"BLOCKED_COMPILED_PROMPT_PROOF_EMBEDDED_IN_CONTRACT"},
    "bad_chain_downstream_raw_source_text_used.json": {
        "BLOCKED_DOWNSTREAM_USED_RAW_SOURCE_TEXT",
        "BLOCKED_SERIALIZED_JSON_PROMPT_TEXT",
    },
    "bad_chain_reviewer_pass_without_validator_receipt.json": {"BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT"},
    "bad_chain_reviewer_pass_with_blocked_validator.json": {"BLOCKED_REVIEWER_PASS_WITH_INVALID_CONTRACT"},
    "bad_chain_provider_live_true.json": {
        "BLOCKED_PROVIDER_LIVE_IN_LOCAL_CHAIN_GATE",
        "BLOCKED_LIVE_CALL_STARTED_IN_LOCAL_CHAIN_GATE",
    },
}


def _read_stdin_handoff() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {
            "github": {"repo": "grahama1970/agent-skills", "target": "skills/persona-dream"},
            "goal": {
                "goal_id": "persona-dream-spine-chain-contract-validator",
                "goal_version": 1,
                "goal_hash": GOAL_HASH,
            },
            "context": {},
        }
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("stdin handoff must be a JSON object")
    return payload


def _github(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    github = payload.get("github")
    if isinstance(github, Mapping) and "repo" in github and "target" in github:
        return github
    return {"repo": "grahama1970/agent-skills", "target": "skills/persona-dream"}


def _goal(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    goal = payload.get("goal")
    if isinstance(goal, Mapping):
        return goal
    return {
        "goal_id": "persona-dream-spine-chain-contract-validator",
        "goal_version": 1,
        "goal_hash": GOAL_HASH,
    }


def _run_manifest(manifest: Path, receipt: Path, expected_exit: int) -> dict[str, Any]:
    cmd = [
        "python3",
        str(VALIDATOR),
        "--manifest",
        str(manifest),
        "--receipt-out",
        str(receipt),
    ]
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, timeout=60, check=False)
    loaded = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
    blockers = loaded.get("blockers") if isinstance(loaded.get("blockers"), list) else []
    blocker_statuses = [str(item.get("status")) for item in blockers if isinstance(item, dict)]
    errors: list[str] = []
    if proc.returncode != expected_exit:
        errors.append(f"exit_mismatch:{proc.returncode}:expected:{expected_exit}")
    return {
        "manifest": str(manifest),
        "command": cmd,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "receipt": str(receipt),
        "status": loaded.get("status"),
        "blocker_statuses": blocker_statuses,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-dir", type=Path)
    args = parser.parse_args()

    start_payload = _read_stdin_handoff()
    context = start_payload.get("context") if isinstance(start_payload.get("context"), Mapping) else {}
    current_node = str(context.get("dag_node_id") or context.get("dag_agent_role") or "")
    if current_node == "review-checker":
        manifest_path = ROOT / "tests/fixtures/spine_chain/good/spine_chain_manifest.v1.json"
        handoff = {
            "schema": "tau.agent_handoff.v1",
            "github": _github(start_payload),
            "goal": _goal(start_payload),
            "previous_subagent": "review-checker",
            "context": {
                "summary": "Review checker routed the manifest gate to the spine-chain-contract-validator node.",
                "artifacts": [
                    str(ROOT / "local/spine_chain_contract_validator_tau_dag.json"),
                    str(manifest_path),
                ],
            },
            "result": {
                "status": "DAG_NODE_READY",
                "summary": "Dependencies are satisfied for DAG node spine-chain-contract-validator.",
                "evidence": [
                    str(ROOT / "local/spine_chain_contract_validator_tau_dag.json"),
                    str(manifest_path),
                ],
            },
            "rationale": "The DAG route requires a review-checker hop before the local chain validator.",
            "next_agent": {
                "name": "spine-chain-contract-validator",
                "executor": "local",
                "reason": "Run the single-manifest spine chain validator.",
            },
            "required_evidence": ["spine_chain_validator_receipt.v1.json"],
            "stop_condition": "Stop at a terminal DAG node or any fail-closed invariant violation.",
        }
        print(json.dumps(handoff, indent=2, sort_keys=True))
        return 0
    artifact_dir = Path(
        os.environ.get(
            "TAU_HANDOFF_COMMAND_ARTIFACT_DIR",
            str(args.receipt_dir or "/tmp/persona-dream-spine-chain-contract-validator"),
        )
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    receipt_root = artifact_dir / "manifest-receipts"
    receipt_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    good_result = _run_manifest(GOOD_MANIFEST, receipt_root / "good.receipt.json", 0)
    if good_result["status"] != "PASS_SPINE_CHAIN_CONTRACT_GATE":
        good_result["errors"].append(f"status_mismatch:{good_result['status']}:expected:PASS_SPINE_CHAIN_CONTRACT_GATE")
    results.append(good_result)

    for manifest in sorted(NEGATIVE_ROOT.glob("*.json")):
        result = _run_manifest(manifest, receipt_root / f"{manifest.stem}.receipt.json", 1)
        if result["status"] != "BLOCKED_SPINE_CHAIN_CONTRACT":
            result["errors"].append(f"status_mismatch:{result['status']}:expected:BLOCKED_SPINE_CHAIN_CONTRACT")
        expected = EXPECTED_NEGATIVE_BLOCKERS.get(manifest.name, set())
        missing = sorted(expected.difference(result["blocker_statuses"]))
        if missing:
            result["errors"].append(f"missing_expected_blockers:{','.join(missing)}")
        results.append(result)

    blockers = [f"{Path(result['manifest']).name}:{error}" for result in results for error in result["errors"]]
    status = "PASS_SPINE_CHAIN_CONTRACT_GATE" if not blockers else "BLOCKED_SPINE_CHAIN_CONTRACT"
    aggregate = {
        "schema": "persona_dream.spine.chain_contract_validator_receipt.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "verdict": "PASS" if status == "PASS_SPINE_CHAIN_CONTRACT_GATE" else "FAIL_CLOSED",
        "provider_live": False,
        "mocked": False,
        "live_image_call_started": False,
        "blockers": blockers,
        "manifest_results": results,
        "claims": {
            "proves": [
                "positive single-manifest chain fixture passes path/SHA and receipt binding",
                "mandatory negative chain fixtures fail closed with expected normalized blockers",
                "Phase 07 compiled prompt proofs are manifest-level raw-byte hash bindings",
            ],
            "does_not_prove": [
                "provider reference attachment",
                "image generation",
                "visual identity pass",
                "story/script creative quality",
                "runtime performance",
            ],
        },
    }
    aggregate_path = artifact_dir / "spine_chain_validator_receipt.v1.json"
    aggregate_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    handoff = {
        "schema": "tau.agent_handoff.v1",
        "github": _github(start_payload),
        "goal": _goal(start_payload),
        "previous_subagent": "spine-chain-contract-validator",
        "context": {
            "summary": status,
            "artifacts": [str(aggregate_path)] + [str(result["receipt"]) for result in results],
            "spine_chain_validator": aggregate,
        },
        "result": {
            "status": status,
            "summary": "Persona Dream spine chain manifest gate passed positive and negative fixtures." if not blockers else "Persona Dream spine chain manifest gate blocked.",
            "evidence": [str(aggregate_path)],
        },
        "rationale": "Creator/reviewer prompt contracts must be chained by typed-contract path/SHA and compiled prompt hashes before downstream generation.",
        "next_agent": {"name": "human", "executor": "human", "reason": "Review deterministic spine chain gate receipt."},
        "required_evidence": ["spine_chain_validator_receipt.v1.json"],
        "stop_condition": "All chain fixtures pass expected outcomes or concrete blockers emitted.",
    }
    print(json.dumps(handoff, indent=2, sort_keys=True))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
