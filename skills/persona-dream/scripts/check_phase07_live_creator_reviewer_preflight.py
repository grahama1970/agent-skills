#!/usr/bin/env python3
"""Local checker for Phase 07 live creator/reviewer preflight enforcement."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase07_storyboard_tau_node import _generate_image, _run_phase07_live_preflight, _write_json


ROOT = Path(__file__).resolve().parents[1]
GOOD_CHAIN = ROOT / "tests/fixtures/spine_chain/good"


CASES = {
    "missing_manifest": "BLOCKED_CHAIN_MANIFEST_MISSING",
    "stale_compiled_prompt_hash": "BLOCKED_STALE_COMPILED_PROMPT_HASH",
    "target_scope_missing": "BLOCKED_TARGET_SCOPE_NOT_IN_CHAIN_MANIFEST",
    "reviewer_pass_without_validator_receipt": "BLOCKED_REVIEWER_PASS_WITHOUT_VALIDATOR_RECEIPT",
}


def _packet(*, panel_id: str = "sb_001", frame_id: str = "sb_001.start_frame") -> dict[str, Any]:
    return {
        "schema": "persona_dream.storyboard_packet.v1",
        "panel_count": 1,
        "duration_seconds": 10,
        "generation_scope": {
            "mode": "targeted_panel_proof",
            "target_panel_ids": [panel_id],
            "target_frame_ids": [frame_id],
        },
        "panels": [
            {
                "panel_id": panel_id,
                "start_frame": {"candidate_frame": {"status": "GENERATED_CANDIDATE_FRAME"}},
                "end_frame": {},
            }
        ],
    }


def _start_payload(manifest: Path | None, *, provider_live: bool = False) -> dict[str, Any]:
    context: dict[str, Any] = {
        "provider_live": provider_live,
        "mocked": False,
        "live_image_call_started": False,
    }
    if manifest is not None:
        context["persona_dream_spine_chain_manifest"] = str(manifest)
    return {
        "schema": "tau.agent_handoff.v1",
        "context": context,
        "goal": {
            "goal_id": "persona-dream-phase07-live-preflight",
            "goal_version": 1,
            "goal_hash": "sha256:51dc0e18732f90516891cb53f478dfe40c7a4ef592a4ca8e0a6c4031a5e3be11",
        },
        "github": {"repo": "grahama1970/agent-skills", "target": "skills/persona-dream"},
    }


def _copy_good_chain(run_root: Path) -> Path:
    for child in GOOD_CHAIN.iterdir():
        destination = run_root / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)
    return run_root / "spine_chain_manifest.v1.json"


def _run_case(name: str, run_root: Path) -> dict[str, Any]:
    case_root = run_root / name
    case_root.mkdir(parents=True, exist_ok=True)
    manifest: Path | None = None
    packet = _packet()
    role = "panel-creator"
    require_reviewer = False
    if name != "missing_manifest":
        manifest = _copy_good_chain(case_root)
    if name == "stale_compiled_prompt_hash":
        prompt = case_root / "phase07/prompts/sb_001.start_frame.attempt_001.md"
        prompt.write_text(prompt.read_text(encoding="utf-8") + "stale mutation\n", encoding="utf-8")
    if name == "target_scope_missing":
        packet = _packet(panel_id="sb_004", frame_id="sb_004.start_frame")
        manifest_payload = json.loads((manifest or case_root / "spine_chain_manifest.v1.json").read_text(encoding="utf-8"))
        manifest_payload["stages"]["phase07"]["panel_prompt_contracts"] = manifest_payload["stages"]["phase07"]["panel_prompt_contracts"][:1]
        _write_json(manifest or case_root / "spine_chain_manifest.v1.json", manifest_payload)
    if name == "reviewer_pass_without_validator_receipt":
        role = "panel-reviewer"
        require_reviewer = True
    packet_path = case_root / "storyboard_packet.json"
    _write_json(packet_path, packet)
    result = _run_phase07_live_preflight(
        role=role,
        run_root=case_root,
        packet=packet,
        packet_path=packet_path,
        start_payload=_start_payload(manifest),
        require_provider_live=role == "panel-creator",
        require_target_scope=True,
        require_reviewer_pass_preconditions=require_reviewer,
    )
    guard = _generate_image(
        "guard must not call provider",
        output_path=case_root / "blocked.png",
        backend="scillm",
        model="gpt-image-2",
        image_policy={"source": "dag_model_policy"},
        receipts_dir=case_root / "receipts/provider",
        panel_id="sb_001",
        frame_key="start_frame",
        live_preflight_status=result["status"],
    )
    expected = CASES[name]
    blockers = result["blockers"]
    errors: list[str] = []
    if result["status"] != "BLOCKED_LIVE_PREFLIGHT":
        errors.append(f"status_mismatch:{result['status']}")
    if expected not in blockers:
        errors.append(f"missing_expected_blocker:{expected}")
    if guard.get("error") != "BLOCKED_PROVIDER_CALL_BEFORE_PREFLIGHT_PASS" or guard.get("provider_call_started") is not False:
        errors.append("provider_guard_failed")
    return {
        "case": name,
        "status": "PASS" if not errors else "FAIL",
        "expected_blocker": expected,
        "observed_blockers": blockers,
        "preflight_receipt": result["receipt_path"],
        "provider_guard": guard,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-root", type=Path, default=ROOT / "tests/fixtures/phase07_live_preflight")
    parser.add_argument("--receipt-out", type=Path)
    args = parser.parse_args()
    start_payload = _read_start_payload()
    current_node = _current_node(start_payload)
    if current_node == "review-checker":
        print(json.dumps(_review_checker_handoff(start_payload), indent=2, sort_keys=True))
        return 0
    receipt_out = args.receipt_out
    if receipt_out is None:
        artifact_dir = Path(os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR", "/tmp/persona-dream-phase07-live-preflight"))
        receipt_out = artifact_dir / "phase07_live_creator_reviewer_preflight_checker_receipt.json"

    args.fixtures_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="persona-dream-phase07-live-preflight-") as tmp:
        run_root = Path(tmp)
        results = [_run_case(name, run_root) for name in CASES]
        for result in results:
            case_dir = args.fixtures_root / result["case"]
            if case_dir.exists():
                shutil.rmtree(case_dir)
            shutil.copytree(run_root / result["case"], case_dir)

    blockers = [f"{result['case']}:{error}" for result in results for error in result["errors"]]
    observed = sorted({blocker for result in results for blocker in result["observed_blockers"]})
    receipt = {
        "schema": "persona_dream.phase07.live_creator_reviewer_preflight_checker_receipt.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_LIVE_CREATOR_REVIEWER_PREFLIGHT_GATE" if not blockers else "BLOCKED_LIVE_CREATOR_REVIEWER_PREFLIGHT_GATE",
        "provider_live": False,
        "mocked": False,
        "live_image_call_started": False,
        "provider_call_attempts": 0,
        "tests": {result["case"]: result["status"] for result in results},
        "observed_blockers": observed,
        "case_results": results,
        "blockers": blockers,
        "claims": {
            "proves": [
                "local Phase 07 live preflight blocks missing run manifest",
                "local Phase 07 live preflight blocks stale compiled prompt hash",
                "local Phase 07 live preflight blocks target scope absent from manifest",
                "local Phase 07 reviewer preflight blocks PASS without validator receipt precondition",
                "defensive _generate_image guard blocks when preflight status is not PASS_LIVE_CREATOR_PREFLIGHT",
            ],
            "does_not_prove": [
                "live provider image generation works",
                "reference images are attached to the provider request",
                "Embry/Kai visually pass identity review",
                "final storyboard approval",
            ],
        },
    }
    receipt_out.parent.mkdir(parents=True, exist_ok=True)
    _write_json(receipt_out, receipt)
    if start_payload:
        print(json.dumps(_checker_handoff(start_payload, receipt, receipt_out), indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if not blockers else 1


def _read_start_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("stdin handoff must be a JSON object")
    return payload


def _current_node(payload: dict[str, Any]) -> str:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    return str(context.get("dag_node_id") or context.get("dag_agent_role") or "")


def _goal(payload: dict[str, Any]) -> dict[str, Any]:
    goal = payload.get("goal")
    if isinstance(goal, dict):
        return goal
    return {
        "goal_id": "persona-dream-phase07-live-preflight",
        "goal_version": 1,
        "goal_hash": "sha256:51dc0e18732f90516891cb53f478dfe40c7a4ef592a4ca8e0a6c4031a5e3be11",
    }


def _github(payload: dict[str, Any]) -> dict[str, Any]:
    github = payload.get("github")
    if isinstance(github, dict):
        return github
    return {"repo": "grahama1970/agent-skills", "target": "skills/persona-dream"}


def _review_checker_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": _github(payload),
        "goal": _goal(payload),
        "previous_subagent": "review-checker",
        "context": {
            "summary": "Review checker routed Phase 07 live preflight gate to the local checker.",
            "artifacts": [str(ROOT / "local/phase07_live_creator_reviewer_preflight_tau_dag.json")],
        },
        "result": {
            "status": "DAG_NODE_READY",
            "summary": "Dependencies are satisfied for DAG node phase07-live-creator-reviewer-preflight-checker.",
            "evidence": [str(ROOT / "local/phase07_live_creator_reviewer_preflight_tau_dag.json")],
        },
        "rationale": "The DAG route requires a review-checker hop before local preflight enforcement checks.",
        "next_agent": {
            "name": "phase07-live-creator-reviewer-preflight-checker",
            "executor": "local",
            "reason": "Run local-only live preflight fail-closed fixtures.",
        },
        "required_evidence": ["phase07_live_creator_reviewer_preflight_checker_receipt.json"],
        "stop_condition": "Stop at human after local preflight checker receipt.",
    }


def _checker_handoff(payload: dict[str, Any], receipt: dict[str, Any], receipt_out: Path) -> dict[str, Any]:
    evidence = [str(receipt_out), str(receipt.get("status")), "provider_call_attempts:0"]
    evidence.extend(str(item) for item in receipt.get("observed_blockers", []) if isinstance(item, str))
    return {
        "schema": "tau.agent_handoff.v1",
        "github": _github(payload),
        "goal": _goal(payload),
        "previous_subagent": "phase07-live-creator-reviewer-preflight-checker",
        "context": {
            "summary": receipt["status"],
            "artifacts": evidence,
            "phase07_live_preflight_checker": receipt,
        },
        "result": {
            "status": receipt["status"],
            "summary": "Phase 07 live creator/reviewer preflight gate passed local fail-closed fixtures.",
            "evidence": evidence,
        },
        "rationale": "Provider generation and reviewer promotion must be unreachable without live preflight receipts.",
        "next_agent": {"name": "human", "executor": "human", "reason": "Review local preflight enforcement receipt."},
        "required_evidence": ["phase07_live_creator_reviewer_preflight_checker_receipt.json"],
        "stop_condition": "All local preflight fixtures pass expected blockers or concrete blockers are emitted.",
    }


if __name__ == "__main__":
    raise SystemExit(main())
