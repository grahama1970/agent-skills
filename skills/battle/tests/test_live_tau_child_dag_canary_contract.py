from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from battle_skill.live_tau_child_dag_canary import (
    LIVE_TAU_CANARY_SCHEMA,
    _find_artifact,
    _missing_required_tau_artifacts,
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
    assert "compile_receipt.json" in missing
