from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from battle_skill.live_tau_child_dag_canary import (
    LIVE_TAU_CANARY_SCHEMA,
    _find_artifact,
    _missing_required_tau_artifacts,
    _pr3c_boundary_status,
    _top_receipt,
)


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_live_tau_canary_receipt_keeps_blocked_gap_non_success(tmp_path: Path) -> None:
    receipt = _top_receipt(
        battle_id="battle-004",
        status="BLOCKED",
        reason="missing_tau_child_artifacts",
        out_dir=tmp_path,
        spawn_architect_proof=tmp_path / "spawn-architect",
        preflight={"status": "PASS"},
        tau_receipt={"status": "BLOCKED", "verdict": "DAG_CONTRACT_INVALID"},
        events=[],
        missing_artifacts=["research_receipts.json", "battle_exploit_runner_handoff.json"],
        specimen_run_receipt=None,
        tau_command=["uv", "run", "tau", "dag-run", "child-exploit-dag.yaml"],
        tau_exit_code=1,
        tau_elapsed_seconds=0.1,
    )

    jsonschema.validate(receipt, _load_schema("battle.live_tau_child_dag_canary_receipt.v1.schema.json"))
    assert receipt["schema"] == LIVE_TAU_CANARY_SCHEMA
    assert receipt["status"] == "BLOCKED"
    assert receipt["mocked"] is False
    assert receipt["live"] == "tau_dag_runtime"
    assert receipt["agentic"] is True
    assert receipt["fixture_fallback_used"] is False
    assert receipt["tau_execution"] == "attempted"
    assert receipt["scoreboard"]["judge_verified_exploits"] == 0
    assert receipt["scoreboard"]["child_specimen_run"] is False
    proves = " ".join(receipt["claims"]["proves"]).lower()
    assert "exploit success" not in proves
    assert "any exploit succeeded." in " ".join(receipt["claims"]["does_not_prove"]).lower()


def test_live_tau_canary_follows_node_receipt_external_artifact_refs(tmp_path: Path) -> None:
    tau_run = tmp_path / "tau-dag-run"
    command_artifacts = tau_run / "command-loop" / "command-artifacts" / "command-loop-step-004"
    command_artifacts.mkdir(parents=True)
    provider_workspace = tmp_path / "provider-workspace"
    code_path = provider_workspace / "outputs" / "exploit_specimen.py"
    code_path.parent.mkdir(parents=True)
    code_path.write_text("print('provider artifact')\n", encoding="utf-8")
    (tau_run / "command-loop-step-002").mkdir(parents=True)
    (tau_run / "command-loop-step-002" / "research_receipts.json").write_text("{}", encoding="utf-8")
    (tau_run / "command-loop-step-003").mkdir(parents=True)
    (tau_run / "command-loop-step-003" / "exploit_genome.json").write_text("{}", encoding="utf-8")
    (command_artifacts / "exploit-code-author-node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "battle.child_dag_node_receipt.v1",
                "status": "BLOCKED",
                "evidence": [{"kind": "exploit_specimen.py", "path": str(code_path)}],
            }
        ),
        encoding="utf-8",
    )

    assert _find_artifact(tau_run, "exploit_specimen.py") == code_path
    missing = _missing_required_tau_artifacts(tau_run)
    assert "exploit_specimen.py" not in missing
    assert "specimen.json" in missing


def test_pr3c_boundary_status_passes_with_provider_authorship_receipts(tmp_path: Path) -> None:
    tau_run = tmp_path / "tau-dag-run"
    step = tau_run / "command-loop" / "command-artifacts" / "command-loop-step-004"
    step.mkdir(parents=True)
    provider = tmp_path / "provider-workspace" / "exploit-code-author"
    outputs = provider / "outputs"
    receipts = provider / "receipts"
    outputs.mkdir(parents=True)
    receipts.mkdir(parents=True)
    code_path = outputs / "exploit_specimen.py"
    code_path.write_text("print('provider-authored candidate')\n", encoding="utf-8")
    (tau_run / "command-loop-step-002").mkdir(parents=True)
    (tau_run / "command-loop-step-002" / "research_receipts.json").write_text("{}", encoding="utf-8")
    (tau_run / "command-loop-step-003").mkdir(parents=True)
    (tau_run / "command-loop-step-003" / "exploit_genome.json").write_text("{}", encoding="utf-8")
    (outputs / "specimen.json").write_text(
        json.dumps({"provider_live": True, "agentic": True, "code_sha256": "sha256:" + "1" * 64}),
        encoding="utf-8",
    )
    provider_fields = {
        "status": "PASS",
        "provider_live": True,
        "agentic": True,
        "fixture_fallback_used": False,
        "compile_status": "NOT_RUN",
        "runtime_status": "NOT_RUN",
        "judge_verified_exploits": 0,
    }
    (receipts / "provider-authorship-receipt.json").write_text(json.dumps(provider_fields), encoding="utf-8")
    (receipts / "provider-code-author-boundary-receipt.json").write_text(json.dumps(provider_fields), encoding="utf-8")
    evidence = [
        {"kind": "exploit_specimen.py", "path": str(code_path)},
        {"kind": "specimen.json", "path": str(outputs / "specimen.json")},
        {"kind": "provider-authorship-receipt.json", "path": str(receipts / "provider-authorship-receipt.json")},
        {"kind": "provider-code-author-boundary-receipt.json", "path": str(receipts / "provider-code-author-boundary-receipt.json")},
    ]
    (step / "exploit-code-author-node-receipt.json").write_text(
        json.dumps({"status": "PASS", "provider_live": True, "agentic": True, "fixture_fallback_used": False, "evidence": evidence}),
        encoding="utf-8",
    )

    status = _pr3c_boundary_status(tau_run)

    assert status["status"] == "PASS"
    assert status["provider_live"] is True
    assert status["agentic"] is True
    assert status["fixture_fallback_used"] is False
    assert status["compile_status"] == "NOT_RUN"
    assert status["runtime_status"] == "NOT_RUN"
    assert status["judge_verified_exploits"] == 0
