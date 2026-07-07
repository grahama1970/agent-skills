#!/usr/bin/env python3
"""Tau node checker for Phase 07 prompt DAG review decisions.

This is a deterministic pre-implementation gate. It checks that the WebGPT
follow-up closed the prompt-DAG ambiguities with a narrow first proof rung.
It does not validate generated images or call providers.
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
    "chosen_slice_a": "Choose A: prompt contract JSON + deterministic validator only",
    "blocked_prompt_contract": "BLOCKED_PROMPT_CONTRACT",
    "attachment_unsupported": "BLOCKED_REFERENCE_ATTACHMENT_UNSUPPORTED",
    "dry_run_not_provider_eligible": "DRY_RUN_TEXT_ONLY_NOT_PROVIDER_ELIGIBLE",
    "parallel_policy": "generate start_frame and end_frame in parallel",
    "pass_prompt_contract": "PASS_PROMPT_CONTRACT",
    "validator_script": "validate_phase07_prompt_contract.py",
    "does_not_prove": "does not prove",
    "fresh_live_unverified": "remain explicitly unverified until a fresh live run",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_stdin_handoff() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {
            "github": {"repo": "grahama1970/agent-skills"},
            "goal": {
                "goal_id": "persona-dream-phase07-prompt-dag-review",
                "goal_version": 1,
                "goal_hash": "sha256:phase07-prompt-dag-review-20260707",
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
                    "target": target.get("target", "skills/persona-dream/local/phase07_storyboard_prompt_dag_webgpt_followup.md"),
                }
    return {
        "repo": "grahama1970/agent-skills",
        "target": "skills/persona-dream/local/phase07_storyboard_prompt_dag_webgpt_followup.md",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--response", required=True, type=Path)
    parser.add_argument("--meta", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()

    start_payload = _read_stdin_handoff()
    artifact_dir = Path(
        os.environ.get(
            "TAU_HANDOFF_COMMAND_ARTIFACT_DIR",
            "/tmp/persona-dream-phase07-prompt-dag-review-check",
        )
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    blockers: list[str] = []
    artifacts = [str(args.request), str(args.response), str(args.meta)]

    if not args.request.exists():
        blockers.append(f"missing_request:{args.request}")
    if not args.response.exists():
        blockers.append(f"missing_response:{args.response}")
    if not args.meta.exists():
        blockers.append(f"missing_meta:{args.meta}")

    response_text = args.response.read_text(encoding="utf-8") if args.response.exists() else ""
    meta = _read_json(args.meta) if args.meta.exists() else {}

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

    tab = meta.get("tab_identity_preflight", {}).get("tab") if isinstance(meta.get("tab_identity_preflight"), dict) else None
    if not isinstance(tab, dict) or tab.get("id") != EXPECTED_TAB_ID or tab.get("url") != EXPECTED_URL:
        blockers.append("tab_identity_not_verified")

    missing_markers = [
        marker_id
        for marker_id, marker in REQUIRED_RESPONSE_MARKERS.items()
        if marker not in response_text
    ]
    blockers.extend(f"missing_response_marker:{marker}" for marker in missing_markers)

    status = "PASS_REVIEW_AMBIGUITIES_CLOSED" if not blockers else "BLOCKED_REVIEW_AMBIGUITIES"
    receipt = {
        "schema": "persona_dream.phase07.prompt_dag_review_check_receipt.v1",
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
        "chosen_first_slice": "A_prompt_contract_json_plus_deterministic_validator_only",
        "first_tau_rung_to_check": "prompt_contract_preflight_blocks_bad_contracts_before_live_generation",
        "normal_text_only_generation_policy": "fail_closed_not_provider_eligible",
        "common_case_frame_policy": "start_and_end_parallel_after_prompt_validation",
        "blockers": blockers,
        "markers_checked": sorted(REQUIRED_RESPONSE_MARKERS),
        "artifacts": artifacts,
        "does_prove": [
            "WebGPT follow-up selected a narrow first proof rung.",
            "The exact requested ChatGPT tab returned sentinel output.",
            "The response names fail-closed statuses and deterministic proof expectations.",
        ],
        "does_not_prove": [
            "The prompt validator has been implemented.",
            "Any live image provider can attach reference images.",
            "Generated frames pass visual identity review.",
            "The five-minute per-panel common-case target holds in a fresh live run.",
        ],
    }
    receipt_path = artifact_dir / "phase07_prompt_dag_review_check_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    selected_agent = os.environ.get("TAU_HANDOFF_SELECTED_AGENT")
    if not selected_agent:
        context = start_payload.get("context")
        if isinstance(context, Mapping):
            selected_agent = str(context.get("dag_node_id") or "")
            tau_dag_node = context.get("tau_dag_node")
            if not selected_agent and isinstance(tau_dag_node, Mapping):
                selected_agent = str(tau_dag_node.get("node_id") or "")
    selected_agent = selected_agent or "review-checker"

    handoff = {
        "schema": "tau.agent_handoff.v1",
        "github": _github(start_payload),
        "goal": _goal(start_payload),
        "previous_subagent": selected_agent,
        "context": {
            "summary": status,
            "artifacts": artifacts + [str(receipt_path)],
            "phase07_prompt_dag_review_check": receipt,
        },
        "result": {
            "status": status,
            "summary": (
                "WebGPT follow-up closed prompt-DAG implementation ambiguities."
                if not blockers
                else "WebGPT follow-up did not satisfy the prompt-DAG ambiguity gate."
            ),
            "evidence": [str(receipt_path)],
        },
        "rationale": "Phase 07 prompt-DAG changes must be grounded in a closed review decision before implementation.",
        "next_agent": {
            "name": "human",
            "executor": "human",
            "reason": "Review the deterministic ambiguity-check receipt before implementing validator slice A.",
        },
        "required_evidence": ["phase07_prompt_dag_review_check_receipt.json"],
        "stop_condition": "Ambiguities closed or concrete blockers emitted.",
    }
    print(json.dumps(handoff, indent=2, sort_keys=True))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
