"""Deterministic regression referee (pdf_lab.regression_verdict.v1).

A repair is promotable only when no blocking defect dimension worsened and
the targeted dimension strictly decreased. This is the verification
command tau's reviewer runs; PASS must never depend on model output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.regression import evaluate_regression, run_regression_check  # noqa: E402


def _comparison(**vector):
    defaults = {
        "matched_expected": 9,
        "missing_expected": 0,
        "ambiguous_expected": 0,
        "unwaived_extras": 0,
        "waived_extras": 3,
        "type_mismatches": 0,
    }
    defaults.update(vector)
    return {"schema_version": "pdf-lab.comparison.v2", "defect_vector": defaults}


def test_identical_vectors_pass_without_target():
    verdict = evaluate_regression(_comparison(), _comparison())
    assert verdict["verdict"] == "PASS"
    assert verdict["failures"] == []
    assert verdict["semantic_truth"] == "NOT_CLAIMED"


def test_targeted_dimension_must_strictly_decrease():
    baseline = _comparison(unwaived_extras=5)
    same = _comparison(unwaived_extras=5)
    better = _comparison(unwaived_extras=3)

    stalled = evaluate_regression(baseline, same, target_class="unwaived_extras")
    assert stalled["verdict"] == "FAIL"
    assert any("did not strictly decrease" in failure for failure in stalled["failures"])

    fixed = evaluate_regression(baseline, better, target_class="unwaived_extras")
    assert fixed["verdict"] == "PASS"
    assert fixed["target"]["strictly_decreased"] is True


def test_any_blocking_dimension_increase_fails_even_if_target_improves():
    baseline = _comparison(unwaived_extras=5, missing_expected=0)
    candidate = _comparison(unwaived_extras=0, missing_expected=1)
    verdict = evaluate_regression(baseline, candidate, target_class="unwaived_extras")
    assert verdict["verdict"] == "FAIL"
    assert any("missing_expected increased" in failure for failure in verdict["failures"])


def test_matched_expected_decrease_fails():
    verdict = evaluate_regression(
        _comparison(matched_expected=9), _comparison(matched_expected=8)
    )
    assert verdict["verdict"] == "FAIL"
    assert any("matched_expected decreased" in failure for failure in verdict["failures"])


def test_unknown_target_class_fails_closed():
    verdict = evaluate_regression(
        _comparison(), _comparison(), target_class="not_a_dimension"
    )
    assert verdict["verdict"] == "FAIL"


def test_legacy_v1_comparison_payloads_are_supported():
    legacy = {
        "schema_version": "pdf-lab.comparison.v1",
        "matched_expected_elements": 6,
        "unmatched_expected_elements": 3,
        "unmatched_actual_elements": 13,
    }
    improved = _comparison(matched_expected=9, missing_expected=0, unwaived_extras=5)
    verdict = evaluate_regression(legacy, improved, target_class="missing_expected")
    assert verdict["verdict"] == "PASS"
    assert verdict["baseline_defect_vector"]["missing_expected"] == 3


def test_run_regression_check_writes_verdict(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(json.dumps(_comparison(unwaived_extras=2)), encoding="utf-8")
    candidate_path.write_text(json.dumps(_comparison(unwaived_extras=0)), encoding="utf-8")
    output_path = tmp_path / "verdict.json"
    verdict = run_regression_check(
        baseline_path,
        candidate_path,
        target_class="unwaived_extras",
        output_path=output_path,
    )
    assert verdict["verdict"] == "PASS"
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["schema_version"] == "pdf_lab.regression_verdict.v1"
    assert written["baseline_path"] == str(baseline_path)
