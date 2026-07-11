#!/usr/bin/env python3
"""Tau adapter that persists persona-dream phase artifacts through $memory."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import os


ROOT = Path("/home/graham/workspace/experiments/agent-skills")
BRIDGE = ROOT / "skills/persona-dream/scripts/persona_dream_memory_bridge.py"


ARTIFACTS = [
    {
        "phase": "02_story",
        "artifact_type": "story_contract",
        "artifact": Path(
            "/home/graham/workspace/experiments/tau/experiments/goal-locked-subagents/proofs/"
            "persona-dream-story-ui-dispatch/story-ui-20260702T125257Z/run/story_contract.json"
        ),
        "run_root": Path(
            "/home/graham/workspace/experiments/tau/experiments/goal-locked-subagents/proofs/"
            "persona-dream-story-ui-dispatch/story-ui-20260702T125257Z/run"
        ),
        "receipt_name": "story_memory_bridge_receipt.json",
    },
    {
        "phase": "06_script",
        "artifact_type": "script_contract",
        "artifact": Path(
            "/home/graham/workspace/experiments/tau/experiments/goal-locked-subagents/proofs/"
            "persona-dream-script-ui-dispatch/script-ui-20260703T230932Z/run/script_contract.json"
        ),
        "run_root": Path(
            "/home/graham/workspace/experiments/tau/experiments/goal-locked-subagents/proofs/"
            "persona-dream-script-ui-dispatch/script-ui-20260703T230932Z/run"
        ),
        "receipt_name": "script_memory_bridge_receipt.json",
    },
    {
        "phase": "04_contact_sheets",
        "artifact_type": "contact_sheet_build_receipt",
        "artifact": ROOT
        / "skills/persona-dream/reports/pipeline-complete/phase_04_contact_sheets/contact_sheet_build_receipt.json",
        "run_root": ROOT / "skills/persona-dream/reports/pipeline-complete",
        "receipt_name": "contact_sheet_memory_bridge_receipt.json",
    },
]


def main() -> int:
    artifact_dir = Path(
        os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR", "/tmp/persona-dream-memory-tau")
    ).expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        handoff = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        _write_json(artifact_dir / "persona-dream-memory-tau-receipt.json", _receipt("BLOCKED", [str(exc)], []))
        return 2

    bridge_receipts: list[dict[str, Any]] = []
    errors: list[str] = []
    commands: list[dict[str, Any]] = []
    for spec in ARTIFACTS:
        artifact = Path(spec["artifact"])
        if not artifact.is_file():
            errors.append(f"missing_artifact:{artifact}")
            continue
        receipt_path = artifact_dir / str(spec["receipt_name"])
        cmd = [
            "python3",
            str(BRIDGE),
            "--phase",
            str(spec["phase"]),
            "--artifact-type",
            str(spec["artifact_type"]),
            "--artifact",
            str(artifact),
            "--run-root",
            str(spec["run_root"]),
            "--receipt",
            str(receipt_path),
        ]
        completed = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=False)
        commands.append(
            {
                "command": cmd,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-2000:],
            }
        )
        if completed.returncode != 0:
            errors.append(f"memory_bridge_failed:{spec['phase']}:{completed.returncode}")
            continue
        bridge_receipt = _read_json(receipt_path)
        bridge_receipt["_adapter_phase"] = str(spec["phase"])
        bridge_receipts.append(bridge_receipt)

    audit = _audit(bridge_receipts, errors)
    audit_path = artifact_dir / "persona-dream-memory-tau-audit.json"
    receipt_path = artifact_dir / "persona-dream-memory-tau-receipt.json"
    _write_json(audit_path, audit)
    _write_json(receipt_path, _receipt(audit["status"], errors, commands, bridge_receipts, audit_path))
    print(json.dumps(_handoff_response(handoff, audit, receipt_path, audit_path), sort_keys=True))
    return 0 if audit["status"] == "PASS" else 2


def _audit(bridge_receipts: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    expected = {"02_story", "06_script", "04_contact_sheets"}
    phases = {str(receipt.get("_adapter_phase")) for receipt in bridge_receipts}
    media_edges = sum(len(receipt.get("media_edges_written") or []) for receipt in bridge_receipts)
    media_assets = sum(len(receipt.get("media_assets_written") or []) for receipt in bridge_receipts)
    score_counts = {"bm25": 0, "dense": 0, "graph": 0}
    for receipt in bridge_receipts:
        recall_probe = receipt.get("recall_probe") if isinstance(receipt.get("recall_probe"), dict) else {}
        for key, value in dict(recall_probe.get("score_counts") or {}).items():
            if key in score_counts:
                score_counts[key] += int(value or 0)
    missing = sorted(expected - phases)
    status = "PASS"
    if errors or missing or media_edges < 1 or score_counts["bm25"] < 1 or score_counts["dense"] < 1:
        status = "BLOCKED"
    return {
        "schema": "persona_dream.memory_tau_audit.v1",
        "status": status,
        "mocked": False,
        "live": True,
        "expected_phases": sorted(expected),
        "observed_phases": sorted(phases),
        "missing_phases": missing,
        "bridge_receipt_count": len(bridge_receipts),
        "media_assets_written_count": media_assets,
        "media_edges_written_count": media_edges,
        "recall_score_counts": score_counts,
        "errors": errors,
        "timestamp": _now(),
    }


def _handoff_response(handoff: dict[str, Any], audit: dict[str, Any], receipt_path: Path, audit_path: Path) -> dict[str, Any]:
    status = "COMPLETED" if audit["status"] == "PASS" else "BLOCKED"
    evidence = [
        {
            "kind": "persona_dream_memory_tau_receipt",
            "path": str(receipt_path),
        },
        {
            "kind": "persona_dream_memory_tau_audit",
            "path": str(audit_path),
        },
    ]
    for label in [
        "story memory_bridge_receipt mocked=false live=true",
        "script memory_bridge_receipt mocked=false live=true",
        "contact-sheet memory_bridge_receipt mocked=false live=true",
        "media asset vertices written through memory /upsert",
        "TOM/media grounding edges written through memory /upsert",
        "entity_context.json for story/script/contact-sheet artifacts",
        "no direct ArangoDB or Qdrant writes",
    ]:
        evidence.append({"kind": "required_evidence", "label": label})
    return {
        "schema": "tau.agent_handoff.v1",
        "github": handoff.get("github", {}),
        "goal": handoff.get("goal", {}),
        "previous_subagent": "memory",
        "context": {
            "summary": "persona-dream memory integration bridge executed through Tau memory node.",
            "artifacts": [str(receipt_path), str(audit_path)],
        },
        "result": {
            "status": status,
            "summary": "Memory bridge receipts written and recall modes checked."
            if status == "COMPLETED"
            else "Memory bridge receipts did not satisfy required evidence.",
            "evidence": evidence,
        },
        "rationale": "The memory node is responsible for durable /upsert writes through the memory daemon.",
        "next_agent": {
            "name": "project-or-harness-verifier",
            "executor": "local",
            "reason": "Review memory receipts before returning to human.",
        },
        "required_evidence": [
            "persona-dream-memory-tau-audit.json status PASS",
            "memory bridge receipts mocked=false live=true",
        ],
        "stop_condition": "Stop at verifier or human after receipt review.",
    }


def _receipt(
    status: str,
    errors: list[str],
    commands: list[dict[str, Any]],
    bridge_receipts: list[dict[str, Any]] | None = None,
    audit_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema": "persona_dream.memory_tau_receipt.v1",
        "status": status,
        "mocked": False,
        "live": True,
        "bridge_receipts": bridge_receipts or [],
        "audit_path": str(audit_path) if audit_path else None,
        "commands": commands,
        "errors": errors,
        "timestamp": _now(),
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
