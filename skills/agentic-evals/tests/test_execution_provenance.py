"""Regression tests for execution modes, immutable test/oracle hashes, and repair admission."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import provenance as prov  # noqa: E402
import runner  # noqa: E402


def _case(command: str = "exit 0", expected: dict | None = None, **extra: object) -> dict:
    case = {
        "name": "qid-regression",
        "type": "adversarial",
        "command": ["bash", "-c", command],
        "expected": expected or {"exit_code": 0},
        "evidence_class": "fault_injected_deterministic",
        "supports_claims": ["claim.qid"],
    }
    case.update(extra)
    return case


def _manifest(case: dict, admitted: list[dict] | None = None) -> dict:
    claim = {
        "id": "claim.qid",
        "description": "frozen selector regression",
        "criticality": "critical",
        "claim_semantics": "protocol",
        "evidence_required": {"fault_injected_deterministic": True},
    }
    if admitted is not None:
        claim["admitted_evidence"] = admitted
    return {
        "version": 2,
        "skill": "agentic-evals",
        "eval_kind": "runner_selftest",
        "trials": 2,
        "capability_claims": [claim],
        "cases": [case],
    }


def _write(tmp_path: Path, manifest: dict) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _run(tmp_path: Path, manifest: dict) -> dict:
    return runner.evaluate_manifest(_write(tmp_path, manifest), timeout_seconds=10)


def test_default_replay_records_mode_and_frozen_hashes(tmp_path: Path) -> None:
    case = _case()
    report = _run(tmp_path, _manifest(case))
    case_report = report["cases"][0]
    assert case_report["execution_mode"] == "regression_replay"
    assert case_report["test_source_sha256"] == prov.test_source_hash(case)
    assert case_report["oracle_sha256"] == prov.oracle_hash(case)
    assert case_report["evidence_eligibility"]["eligible"] is True
    trial_hashes = {
        (
            t["execution_provenance"]["test_source_sha256"],
            t["execution_provenance"]["oracle_sha256"],
        )
        for t in case_report["trials"]
    }
    assert trial_hashes == {(prov.test_source_hash(case), prov.oracle_hash(case))}


def test_trial_provenance_includes_generated_test_lineage(tmp_path: Path) -> None:
    lineage = {"generation_id": "gen-lineage-1", "origin": "live-discovery"}
    case = _case(generated_test_lineage=lineage)
    report = _run(tmp_path, _manifest(case))
    for trial in report["cases"][0]["trials"]:
        assert trial["execution_provenance"]["generated_test_lineage"] == lineage


def test_exploration_generated_test_is_candidate_not_claim_proof(tmp_path: Path) -> None:
    case = _case(execution_mode="exploration", generated_test_lineage={"generation_id": "draft-1"})
    report = _run(tmp_path, _manifest(case))
    assert report["cases"][0]["observed_outcome"] == "PASS"
    assert report["cases"][0]["evidence_eligibility"]["eligible"] is False
    assert "exploration_candidate_not_admitted" in report["cases"][0]["evidence_eligibility"]["reason_codes"]
    assert report["capability_readiness"]["claims"][0]["verdict"] == "NOT_ESTABLISHED"
    assert report["readiness"] != "READY"


def test_selector_repair_cannot_make_original_generation_pass(tmp_path: Path) -> None:
    original = _case(command="echo wrong; exit 1")
    repaired = _case(
        command="echo healed-control; exit 0",
        provenance={"prior_test_source_sha256": prov.test_source_hash(original)},
        mutation_provenance={"locator_healed": True},
    )
    report = _run(
        tmp_path,
        _manifest(
            repaired,
            admitted=[
                {
                    "case": "qid-regression",
                    "test_source_sha256": prov.test_source_hash(original),
                    "oracle_sha256": prov.oracle_hash(original),
                }
            ],
        ),
    )
    case_report = report["cases"][0]
    assert case_report["observed_outcome"] == "PASS"
    assert case_report["outcome"] == "FAIL"
    assert case_report["evidence_eligibility"]["eligible"] is False
    assert report["capability_readiness"]["claims"][0]["verdict"] == "NOT_ESTABLISHED"


def test_expected_output_change_cannot_satisfy_original_slot(tmp_path: Path) -> None:
    original = _case(command="printf broken", expected={"exit_code": 0, "stdout_contains": ["correct"]})
    edited_oracle = _case(command="printf broken", expected={"exit_code": 0, "stdout_contains": ["broken"]})
    report = _run(
        tmp_path,
        _manifest(
            edited_oracle,
            admitted=[
                {
                    "case": "qid-regression",
                    "test_source_sha256": prov.test_source_hash(original),
                    "oracle_sha256": prov.oracle_hash(original),
                }
            ],
        ),
    )
    assert report["cases"][0]["outcome"] == "PASS"
    claim = report["capability_readiness"]["claims"][0]
    assert claim["verdict"] == "NOT_ESTABLISHED"
    assert claim["ineligible_supporting_cases"][0]["admitted_for_claim"] is False
    assert report["readiness"] != "READY"


def test_declared_protected_surface_change_forces_fail_closed(tmp_path: Path) -> None:
    case = _case(mutation_provenance={"expected_output_changed": True})
    report = _run(tmp_path, _manifest(case))
    case_report = report["cases"][0]
    assert case_report["observed_outcome"] == "PASS"
    assert case_report["outcome"] == "FAIL"
    assert case_report["evidence_eligibility"]["eligible"] is False
    assert "protected_surface_changed" in case_report["evidence_eligibility"]["reason_codes"]
    assert report["capability_readiness"]["claims"][0]["verdict"] == "NOT_ESTABLISHED"


def test_external_healed_locator_pass_has_no_readiness_authority(tmp_path: Path) -> None:
    case = _case(
        external_result={
            "provider": "example-browser-agent",
            "status": "passed",
            "mutation_provenance": {"locator_healed": True},
        }
    )
    report = _run(tmp_path, _manifest(case))
    case_report = report["cases"][0]
    assert case_report["observed_outcome"] == "PASS"
    assert case_report["outcome"] == "FAIL"
    assert "external_pass_after_mutation_requires_requalification" in case_report["evidence_eligibility"]["reason_codes"]
    assert report["capability_readiness"]["claims"][0]["verdict"] == "NOT_ESTABLISHED"


def test_external_test_hash_change_without_mutation_declaration_fails_closed(tmp_path: Path) -> None:
    case = _case(external_result={"provider": "example-browser-agent", "test_source_sha256": "sha256:changed"})
    report = _run(tmp_path, _manifest(case))
    case_report = report["cases"][0]
    assert case_report["outcome"] == "FAIL"
    assert case_report["evidence_eligibility"]["integrity_errors"] == ["undeclared_test_mutation"]
    assert report["readiness"] != "READY"


def test_test_repair_candidate_carries_before_after_hashes(tmp_path: Path) -> None:
    original = _case(command="exit 1")
    repair = _case(
        command="exit 0",
        execution_mode="test_repair",
        repair={
            "prior_test_source_sha256": prov.test_source_hash(original),
            "prior_oracle_sha256": prov.oracle_hash(original),
        },
        mutation_provenance={"locator_changed": True},
    )
    report = _run(tmp_path, _manifest(repair))
    provenance = report["cases"][0]["execution_provenance"]
    assert report["cases"][0]["observed_outcome"] == "PASS"
    assert provenance["prior_test_source_sha256"] == prov.test_source_hash(original)
    assert provenance["test_source_sha256"] == prov.test_source_hash(repair)
    assert provenance["evidence_eligibility"]["requires_requalification"] is True
    assert report["readiness"] != "READY"


def test_repaired_generation_can_pass_only_after_explicit_admission(tmp_path: Path) -> None:
    repaired = _case(command="exit 0", generated_test_lineage={"generation_id": "gen-2"})
    admitted = [
        {
            "case": "qid-regression",
            "generation_id": "gen-2",
            "test_source_sha256": prov.test_source_hash(repaired),
            "oracle_sha256": prov.oracle_hash(repaired),
        }
    ]
    report = _run(tmp_path, _manifest(repaired, admitted=admitted))
    assert report["cases"][0]["outcome"] == "PASS"
    assert report["cases"][0]["evidence_eligibility"]["eligible"] is True
    assert report["capability_readiness"]["claims"][0]["verdict"] == "PROVEN"
    assert report["readiness"] == "READY"


def test_closed_execution_mode_validation(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="execution_mode"):
        _run(tmp_path, _manifest(_case(execution_mode="auto_heal")))


def test_non_vacuity_intentionally_broken_scorer_would_false_green(tmp_path: Path) -> None:
    case = _case(
        external_result={
            "provider": "example-browser-agent",
            "status": "passed",
            "mutation_provenance": {"locator_healed": True},
        }
    )
    report = _run(tmp_path, _manifest(case))
    broken_legacy_scorer = report["cases"][0]["observed_outcome"] == "PASS"
    assert broken_legacy_scorer is True
    assert report["readiness"] != "READY"
    assert report["capability_readiness"]["claims"][0]["verdict"] == "NOT_ESTABLISHED"
