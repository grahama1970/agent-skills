#!/usr/bin/env python3
"""Tau node checker for Persona Dream spine creator/reviewer prompt review.

This is a deterministic review gate around a WebGPT architecture response. It
does not implement prompt validators or call image providers.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


EXPECTED_TAB_ID = "837358015"
EXPECTED_URL = "https://chatgpt.com/c/6a4c25f5-1460-83ea-83cc-e63ce7a497d9"


REQUIRED_RESPONSE_MARKERS = {
    "implementation_order": "07 integration rerun using upstream typed contracts",
    "do_not_full_rewrite_first": "Do not begin with a full 01 -> 02 -> 06 -> 07 rewrite.",
    "phase07_schema": "persona_dream.phase07.panel_prompt_contract.v2",
    "phase01_schema": "persona_dream.phase01.memory_residue_contract.v1",
    "phase02_schema": "persona_dream.phase02.story_contract_prompt.v1",
    "phase06_schema": "persona_dream.phase06.script_prompt_contract.v1",
    "phase07_validator": "validate_phase07_prompt_contract.py",
    "phase01_validator": "validate_phase01_memory_residue_contract.py",
    "phase02_validator": "validate_phase02_story_contract_prompt.py",
    "phase06_validator": "validate_phase06_script_prompt_contract.py",
    "phase07_bad_fixture": "bad_prompt_contract_kai_spatially_implied.json",
    "phase01_bad_fixture": "bad_memory_residue_serialized_json_text.json",
    "phase02_bad_fixture": "bad_story_contract_serialized_memory_blob.json",
    "phase06_bad_fixture": "bad_script_contract_loose_asset_usage.json",
    "shared_pass_spine": "PASS_SPINE_CONTRACT_GATE",
    "blocked_serialized_memory": "BLOCKED_SERIALIZED_MEMORY_TEXT",
    "blocked_prompt_contract": "BLOCKED_PROMPT_CONTRACT",
    "first_tau_dag": "Run a local-only Phase 07 prompt-contract validator gate first.",
    "tau_route": "review-checker\n  -> prompt-contract-validator-positive\n  -> prompt-contract-validator-negative\n  -> spine-decision-finalizer\n  -> human",
    "non_claims": "This contract-hardening plan does not claim:",
    "first_proof_claim": "The pipeline spine can deterministically reject structurally unsafe creator prompt inputs before downstream stages or live provider calls consume them.",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_stdin_handoff() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {
            "github": {"repo": "grahama1970/agent-skills"},
            "goal": {
                "goal_id": "persona-dream-spine-creator-reviewer-webgpt",
                "goal_version": 1,
                "goal_hash": "sha256:579bdb18760122f5c6072345ee251908ecbfd6706da70ae3371ccfaa00d6fb98",
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
    context = start_payload.get("context")
    if isinstance(context, Mapping):
        tau_dag_node = context.get("tau_dag_node")
        if isinstance(tau_dag_node, Mapping):
            target = tau_dag_node.get("target")
            if isinstance(target, Mapping):
                return {
                    "repo": target.get("repo", "grahama1970/agent-skills"),
                    "target": target.get("target", "skills/persona-dream/local/spine_creator_reviewer_webgpt_request.md"),
                }
    return {
        "repo": "grahama1970/agent-skills",
        "target": "skills/persona-dream/local/spine_creator_reviewer_webgpt_request.md",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    parser.add_argument("--meta", required=True, type=Path)
    args = parser.parse_args()

    start_payload = _read_stdin_handoff()
    artifact_dir = Path(
        os.environ.get(
            "TAU_HANDOFF_COMMAND_ARTIFACT_DIR",
            "/tmp/persona-dream-spine-creator-reviewer-webgpt-check",
        )
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    blockers: list[str] = []
    artifacts = [str(args.request), str(args.response), str(args.meta)]

    for label, path in (("request", args.request), ("response", args.response), ("meta", args.meta)):
        if not path.exists():
            blockers.append(f"missing_{label}:{path}")

    response_text = args.response.read_text(encoding="utf-8") if args.response.exists() else ""
    request_text = args.request.read_text(encoding="utf-8") if args.request.exists() else ""
    meta = _read_json(args.meta) if args.meta.exists() else {}

    if "01 Idea / Memory Residue" not in request_text:
        blockers.append("request_missing_phase01_scope")
    if "02 Story" not in request_text:
        blockers.append("request_missing_phase02_scope")
    if "06 Script" not in request_text:
        blockers.append("request_missing_phase06_scope")
    if "07 Storyboard" not in request_text:
        blockers.append("request_missing_phase07_scope")

    if meta.get("requested_tab_id") != EXPECTED_TAB_ID:
        blockers.append("requested_tab_id_mismatch")
    if meta.get("controlled_tab_id") != EXPECTED_TAB_ID:
        blockers.append("controlled_tab_id_mismatch")
    if meta.get("controlled_tab_id_mismatch") is not False:
        blockers.append("controlled_tab_id_mismatch_not_false")
    if meta.get("tab_was_created") is not False:
        blockers.append("tab_was_created_not_false")
    if meta.get("submitted_to_chatgpt") is not True:
        blockers.append("submitted_to_chatgpt_not_true")
    if meta.get("raw_contains_sentinel") is not True:
        blockers.append("raw_missing_sentinel")

    tab_preflight = meta.get("tab_identity_preflight")
    tab = tab_preflight.get("tab") if isinstance(tab_preflight, dict) else None
    if not isinstance(tab, dict) or tab.get("id") != EXPECTED_TAB_ID or tab.get("url") != EXPECTED_URL:
        blockers.append("tab_identity_not_verified")

    missing_markers = [
        marker_id
        for marker_id, marker in REQUIRED_RESPONSE_MARKERS.items()
        if marker not in response_text
    ]
    blockers.extend(f"missing_response_marker:{marker}" for marker in missing_markers)

    status = "PASS_SPINE_WEBGPT_REVIEW_GATE" if not blockers else "BLOCKED_SPINE_WEBGPT_REVIEW_GATE"
    receipt = {
        "schema": "persona_dream.spine_creator_reviewer_webgpt_check_receipt.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mocked": False,
        "live": True,
        "provider_live": False,
        "webgpt_transport_degraded": bool(meta.get("transport_degraded")),
        "webgpt_proof_status": meta.get("proof_status"),
        "requested_tab_id": meta.get("requested_tab_id"),
        "controlled_tab_id": meta.get("controlled_tab_id"),
        "controlled_tab_id_mismatch": meta.get("controlled_tab_id_mismatch"),
        "tab_was_created": meta.get("tab_was_created"),
        "submitted_to_chatgpt": meta.get("submitted_to_chatgpt"),
        "recommended_order": [
            "07_phase07_prompt_contract_validator_first",
            "01_memory_residue_contract",
            "02_story_contract_prompt",
            "06_script_prompt_contract",
            "07_integration_rerun",
        ],
        "first_tau_rung": "phase07_prompt_contract_validator_local_only",
        "first_tau_route": [
            "review-checker",
            "prompt-contract-validator-positive",
            "prompt-contract-validator-negative",
            "spine-decision-finalizer",
            "human",
        ],
        "phase_schemas": {
            "01": "persona_dream.phase01.memory_residue_contract.v1",
            "02": "persona_dream.phase02.story_contract_prompt.v1",
            "06": "persona_dream.phase06.script_prompt_contract.v1",
            "07": "persona_dream.phase07.panel_prompt_contract.v2",
        },
        "blockers": blockers,
        "markers_checked": sorted(REQUIRED_RESPONSE_MARKERS),
        "artifacts": artifacts,
        "does_prove": [
            "A live WebGPT reviewer response on the requested tab selected the first reusable prompt-contract hardening rung.",
            "The response names per-stage schema contracts, validators, invalid fixtures, pass/blocked vocabulary, and non-claims.",
            "The response recommends a local-only Phase 07 Tau validator gate before broad spine rewrites.",
        ],
        "does_not_prove": [
            "The Phase 07 prompt-contract validator or fixtures exist in this repository.",
            "Any prompt validator passes or fails fixtures.",
            "Storyboard panels generate in under five minutes.",
            "Image provider reference attachments work.",
            "A final storyboard is accepted by a reviewer.",
        ],
    }
    receipt_path = artifact_dir / "spine_creator_reviewer_webgpt_check_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    selected_agent = os.environ.get("TAU_HANDOFF_SELECTED_AGENT")
    if not selected_agent:
        context = start_payload.get("context")
        if isinstance(context, Mapping):
            selected_agent = str(context.get("dag_node_id") or "")
            tau_dag_node = context.get("tau_dag_node")
            if not selected_agent and isinstance(tau_dag_node, Mapping):
                selected_agent = str(tau_dag_node.get("node_id") or "")
    selected_agent = selected_agent or "spine-webgpt-review-checker"

    handoff = {
        "schema": "tau.agent_handoff.v1",
        "github": _github(start_payload),
        "goal": _goal(start_payload),
        "previous_subagent": selected_agent,
        "context": {
            "summary": status,
            "artifacts": artifacts + [str(receipt_path)],
            "spine_creator_reviewer_webgpt_check": receipt,
        },
        "result": {
            "status": status,
            "summary": (
                "WebGPT spine creator/reviewer prompt review is specific enough for the first local Tau validator rung."
                if not blockers
                else "WebGPT spine creator/reviewer prompt review failed deterministic gate checks."
            ),
            "evidence": [str(receipt_path)],
        },
        "rationale": "Reusable creator/reviewer prompt contracts must be closed by external review before implementation expands across the spine.",
        "next_agent": {
            "name": "human",
            "executor": "human",
            "reason": "Review the deterministic WebGPT decision gate before implementing the Phase 07 validator slice.",
        },
        "required_evidence": ["spine_creator_reviewer_webgpt_check_receipt.json"],
        "stop_condition": "WebGPT review gate passed or concrete blockers emitted.",
    }
    print(json.dumps(handoff, indent=2, sort_keys=True))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
