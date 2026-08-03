from __future__ import annotations

import pytest

from battle_skill.patch_writer import _classify_functional_assertions
from battle_skill.scoring import Scorer
from battle_skill.state import (
    AttackType,
    BattleState,
    DefenseType,
    Finding,
    FunctionalEvidenceStatus,
    Patch,
    RoundResult,
)


def _finding(identifier: str) -> Finding:
    return Finding(
        id=identifier,
        type=AttackType.EXPLOIT,
        severity="high",
        description="fixture finding",
        exploit_proof="judge-receipt",
    )


def _patch(identifier: str, status: FunctionalEvidenceStatus) -> Patch:
    return Patch(
        id=identifier,
        finding_id=identifier.replace("patch", "finding"),
        type=DefenseType.PATCH,
        diff="diff --git a/app.py b/app.py",
        verified=True,
        functional_evidence_status=status,
        functional_test_command="python -m pytest -q",
        functional_exit_code=0 if status is FunctionalEvidenceStatus.PASS else 1,
        functional_receipt_ref=f"receipt:{identifier}",
        functional_artifact_sha256=identifier * 8,
    )


def test_patch_defaults_to_insufficient_without_coercing_false() -> None:
    patch = Patch(
        id="patch-default",
        finding_id="finding-default",
        type=DefenseType.PATCH,
        diff="",
    )

    assert patch.functional_evidence_status is FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert patch.functionality_preserved is None


def test_legacy_false_migrates_to_insufficient_but_true_retains_pass() -> None:
    legacy_false = Patch(
        id="patch-legacy-false",
        finding_id="finding-legacy-false",
        type=DefenseType.PATCH,
        diff="",
        functionality_preserved=False,
    )
    legacy_true = Patch(
        id="patch-legacy-true",
        finding_id="finding-legacy-true",
        type=DefenseType.PATCH,
        diff="",
        functionality_preserved=True,
    )
    explicit_fail = Patch(
        id="patch-explicit-fail",
        finding_id="finding-explicit-fail",
        type=DefenseType.PATCH,
        diff="",
        functional_evidence_status=FunctionalEvidenceStatus.FAIL,
    )

    assert legacy_false.functional_evidence_status is FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert legacy_false.functionality_preserved is None
    assert legacy_true.functional_evidence_status is FunctionalEvidenceStatus.PASS
    assert legacy_true.functionality_preserved is True
    assert explicit_fail.functional_evidence_status is FunctionalEvidenceStatus.FAIL
    assert explicit_fail.functionality_preserved is False


def test_state_round_trip_preserves_functional_evidence_metadata() -> None:
    finding = _finding("finding-1")
    patch = _patch("patch-1", FunctionalEvidenceStatus.PASS)
    state = BattleState(
        battle_id="battle-functional-evidence",
        target_path="/tmp/target",
        max_rounds=1,
        current_round=1,
        status="completed",
        all_findings=[finding],
        all_patches=[patch],
        rounds=[RoundResult(round_number=1, red_findings=[finding], blue_patches=[patch])],
    )

    restored = BattleState.from_dict(state.to_dict())
    restored_patch = restored.all_patches[0]

    assert restored_patch.functional_evidence_status is FunctionalEvidenceStatus.PASS
    assert restored_patch.functionality_preserved is True
    assert restored_patch.functional_test_command == "python -m pytest -q"
    assert restored_patch.functional_receipt_ref == "receipt:patch-1"
    assert restored.rounds[0].blue_patches[0].functional_artifact_sha256 == "patch-1" * 8


def test_metrics_count_pass_fail_and_insufficient_separately() -> None:
    findings = [_finding(f"finding-{index}") for index in range(1, 4)]
    patches = [
        _patch("patch-1", FunctionalEvidenceStatus.PASS),
        _patch("patch-2", FunctionalEvidenceStatus.FAIL),
        _patch("patch-3", FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE),
    ]
    state = BattleState(
        battle_id="battle-metrics",
        target_path="/tmp/target",
        max_rounds=1,
        all_findings=findings,
        all_patches=patches,
    )

    metrics = Scorer.calculate_metrics(state)

    assert metrics["tdsr"] == pytest.approx(1 / 3)
    assert metrics["fdsr"] == pytest.approx(1 / 3)
    assert metrics["functional_evidence_insufficient"] == 1


def test_only_explicit_pass_receives_functionality_bonus() -> None:
    finding = _finding("finding-1")
    passed = _patch("patch-1", FunctionalEvidenceStatus.PASS)
    failed = _patch("patch-1", FunctionalEvidenceStatus.FAIL)
    unknown = _patch("patch-1", FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE)

    pass_score = Scorer.score_patch(passed, finding, round_number=1)
    fail_score = Scorer.score_patch(failed, finding, round_number=1)
    unknown_score = Scorer.score_patch(unknown, finding, round_number=1)

    assert fail_score == pytest.approx(unknown_score)
    assert pass_score == pytest.approx(unknown_score * 1.2)


def test_patch_writer_classifies_only_explicit_behavioral_assertions() -> None:
    assert _classify_functional_assertions(
        [True, {"status": "PASS"}], "python -m pytest -q"
    ) == ("PASS", True)
    assert _classify_functional_assertions(
        [True, {"passed": False}], "python -m pytest -q"
    ) == ("FAIL", False)
    assert _classify_functional_assertions(
        [], "python -m pytest -q"
    ) == ("INSUFFICIENT_EVIDENCE", None)
    assert _classify_functional_assertions(
        [True], "python -m py_compile app.py"
    ) == ("INSUFFICIENT_EVIDENCE", None)
    assert _classify_functional_assertions(
        [{"detail": "no machine-readable result"}], "make test"
    ) == ("INSUFFICIENT_EVIDENCE", None)
