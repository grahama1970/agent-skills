"""Tests for Battle reactive Blue and independent Judge replay receipts."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from battle_skill.reactive_judge_round import (
    EventLedger,
    PhaseTransitionError,
    classify_judge2_outcome,
    run_reactive_judge_round,
    score_from_judges,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "reactive-judge"
AUTH = FIXTURE / "authorization.json"
SCHEMAS = ROOT / "schemas"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema(name: str) -> dict:
    return _load(SCHEMAS / name)


def test_event_ledger_rejects_invalid_phase_transition(tmp_path: Path) -> None:
    ledger = EventLedger(battle_id="test", out_dir=tmp_path)
    ledger.append("authorization_validated", actor="battle")
    ledger.append("judge1_started", actor="judge")
    with pytest.raises(PhaseTransitionError):
        ledger.append("red_started", actor="red")


def test_judge2_outcome_matrix_distinguishes_security_and_functionality() -> None:
    assert classify_judge2_outcome(
        exploit_exit_code=0,
        functionality_exit_code=0,
        expected_target_hash="a",
        actual_target_hash="a",
    ).verdict == "RED_SUCCESS"
    assert classify_judge2_outcome(
        exploit_exit_code=1,
        functionality_exit_code=0,
        expected_target_hash="a",
        actual_target_hash="a",
    ).verdict == "BLUE_SUCCESS"
    assert classify_judge2_outcome(
        exploit_exit_code=1,
        functionality_exit_code=1,
        expected_target_hash="a",
        actual_target_hash="a",
    ).verdict == "FAKE_DEFENSE"
    assert classify_judge2_outcome(
        exploit_exit_code=1,
        functionality_exit_code=0,
        expected_target_hash="a",
        actual_target_hash="b",
    ).verdict == "HASH_MISMATCH"
    assert classify_judge2_outcome(
        exploit_exit_code=1,
        functionality_exit_code=0,
        expected_target_hash="a",
        actual_target_hash="a",
        replay_error=True,
    ).verdict == "REPLAY_ERROR"


def test_scorekeeper_ignores_blue_advisory_fields() -> None:
    judge1 = {"verdict": "CONFIRMED"}
    judge2 = {"verdict": "RED_SUCCESS"}
    advisory_success = {
        "advisory_blue_success": True,
        "advisory_functionality_preserved": True,
    }
    advisory_failure = {
        "advisory_blue_success": False,
        "advisory_functionality_preserved": False,
    }

    score_a = score_from_judges(
        judge1=judge1,
        judge2=judge2,
        blue_patch_receipt=advisory_success,
    )
    score_b = score_from_judges(
        judge1=judge1,
        judge2=judge2,
        blue_patch_receipt=advisory_failure,
    )

    assert score_a["blue_score"] == score_b["blue_score"] == 0.0
    assert score_a["red_score"] == score_b["red_score"] == 1.5


def test_reactive_judge_round_writes_receipt_backed_docker_artifacts(tmp_path: Path) -> None:
    receipt = run_reactive_judge_round(
        authorization_manifest=AUTH,
        out_dir=tmp_path,
    )

    assert receipt["status"] == "PASS"
    assert receipt["mocked"] is False
    assert receipt["live"] == "local_docker_fixture"
    assert receipt["agentic"] is False
    jsonschema.validate(receipt, _schema("battle.round_receipt.v1.schema.json"))

    ledger = _load(tmp_path / "event-ledger.json")
    phases = [event["phase"] for event in ledger["events"]]
    assert phases.index("proactive_blue_started") < phases.index("red_observation_received")
    assert phases.index("judge1_terminal") < phases.index("reactive_blue_started")
    assert phases.index("candidate_patch_received") < phases.index("judge2_started")
    assert phases.index("judge2_terminal") < phases.index("scorekeeper_started")

    proactive = _load(tmp_path / "blue" / "proactive-blue-input.json")
    reactive = _load(tmp_path / "blue" / "reactive-blue-input.json")
    assert proactive["private_red_findings"] == []
    assert len(reactive["private_red_findings"]) == 1

    judge1 = _load(tmp_path / "judge-1" / "judge-1-receipt.json")
    judge2 = _load(tmp_path / "judge-2" / "judge-2-receipt.json")
    jsonschema.validate(judge1, _schema("battle.judge_receipt.v1.schema.json"))
    jsonschema.validate(judge2, _schema("battle.judge_receipt.v1.schema.json"))
    assert judge1["verdict"] == "CONFIRMED"
    assert judge1["hack_validation_receipt"]["confirms_exploit"] is True
    assert judge2["verdict"] == "BLUE_SUCCESS"
    assert judge2["exploit_blocked_after_patch"] is True
    assert judge2["functionality_preserved"] is True

    scorekeeper = _load(tmp_path / "scorekeeper-receipt.json")
    assert scorekeeper["score_authority"] == "judge_receipts_only"
    assert scorekeeper["blue_score"] > scorekeeper["red_score"]
