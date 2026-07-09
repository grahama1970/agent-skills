from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from battle_skill.live_tau_child_dag_canary import LIVE_TAU_CANARY_SCHEMA, _top_receipt


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
