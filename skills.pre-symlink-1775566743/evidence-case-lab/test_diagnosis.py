"""Tests for diagnosis.py — classification of batch results."""
from __future__ import annotations

from diagnosis import DiagnosisResult, diagnose_results


def _result(
    *,
    expected: str = "satisfied",
    actual: str = "satisfied",
    qid: str = "Q1",
    grounding: dict | None = None,
    gate_trace: list | None = None,
) -> dict:
    return {
        "id": qid,
        "question": f"Test question {qid}",
        "expected": expected,
        "actual_verdict": actual,
        "grounding_evidence": grounding or {},
        "gate_trace": gate_trace or [],
    }


class TestDiagnosisResult:
    def test_empty_result(self):
        d = DiagnosisResult()
        assert d.total == 0
        assert d.error_count == 0
        assert d.needs_human_review == 0

    def test_summary_keys(self):
        d = DiagnosisResult()
        s = d.summary()
        assert "total" in s
        assert "fp_rate" in s
        assert "fn_rate" in s

    def test_error_count_excludes_grounding_warnings(self):
        d = DiagnosisResult()
        d.grounding_warnings.append({"id": "W1"})
        d.false_positives.append({"id": "FP1"})
        assert d.error_count == 1
        assert d.needs_human_review == 2


class TestCorrectClassification:
    def test_exact_match_satisfied(self):
        diag = diagnose_results([_result(expected="satisfied", actual="satisfied")])
        assert len(diag.correct) == 1
        assert diag.error_count == 0

    def test_exact_match_not_satisfied(self):
        diag = diagnose_results([_result(expected="not_satisfied", actual="not_satisfied")])
        assert len(diag.correct) == 1

    def test_inconclusive_for_adversarial_is_correct(self):
        diag = diagnose_results([_result(expected="not_satisfied", actual="inconclusive")])
        assert len(diag.correct) == 1
        assert diag.error_count == 0


class TestFalsePositive:
    def test_satisfied_when_expected_not_satisfied(self):
        diag = diagnose_results([_result(expected="not_satisfied", actual="satisfied")])
        assert len(diag.false_positives) == 1
        assert diag.false_positives[0]["root_cause"] == "false_positive"

    def test_grounding_failure_with_fabricated_id(self):
        grounding = {
            "unresolved_id_like": 1,
            "ratio": 0.5,
            "unresolved_terms": [{"term": "X23-MUSTARD", "type": "id_like"}],
        }
        diag = diagnose_results([
            _result(expected="not_satisfied", actual="satisfied", grounding=grounding),
        ])
        assert len(diag.grounding_failures) == 1
        assert len(diag.false_positives) == 0
        assert diag.grounding_failures[0]["root_cause"] == "grounding_failure"
        assert "X23-MUSTARD" in diag.grounding_failures[0]["detail"]


class TestFalseNegative:
    def test_not_satisfied_when_expected_satisfied(self):
        diag = diagnose_results([_result(expected="satisfied", actual="not_satisfied")])
        assert len(diag.false_negatives) == 1

    def test_inconclusive_when_expected_satisfied(self):
        diag = diagnose_results([_result(expected="satisfied", actual="inconclusive")])
        assert len(diag.false_negatives) == 1


class TestGroundingWarning:
    def test_satisfied_with_unresolved_id_triggers_warning(self):
        grounding = {
            "unresolved_id_like": 1,
            "ratio": 0.5,
            "unresolved_terms": [{"term": "ZZ-PHANTOM", "type": "id_like"}],
        }
        diag = diagnose_results([
            _result(expected="satisfied", actual="satisfied", grounding=grounding),
        ])
        assert len(diag.grounding_warnings) == 1
        assert diag.error_count == 0

    def test_satisfied_with_misspelling_triggers_warning(self):
        grounding = {
            "misspellings": 1,
            "unresolved_terms": [{"term": "CM028", "type": "misspelling", "suggestion": "CM0028"}],
        }
        diag = diagnose_results([
            _result(expected="satisfied", actual="satisfied", grounding=grounding),
        ])
        assert len(diag.grounding_warnings) == 1

    def test_satisfied_with_low_ratio_triggers_warning(self):
        grounding = {"ratio": 0.5, "resolved": 1}
        diag = diagnose_results([
            _result(expected="satisfied", actual="satisfied", grounding=grounding),
        ])
        assert len(diag.grounding_warnings) == 1


class TestWarningsFallback:
    """Test that names are extracted from warnings list when unresolved_terms is missing."""

    def test_fabricated_id_names_from_warnings(self):
        grounding = {
            "unresolved_id_like": 1,
            "ratio": 0.5,
            "warnings": [{"category": "fabricated_id", "term": "X23-MUSTARD", "detail": "No match"}],
            # NO unresolved_terms key — simulates runner.py before fix
        }
        diag = diagnose_results([
            _result(expected="not_satisfied", actual="satisfied", grounding=grounding),
        ])
        assert len(diag.grounding_failures) == 1
        assert "X23-MUSTARD" in diag.grounding_failures[0]["detail"]
        assert "X23-MUSTARD" in diag.grounding_failures[0]["unresolved_names"]

    def test_misspelling_names_from_warnings(self):
        grounding = {
            "misspellings": 1,
            "warnings": [{"category": "misspelling", "term": "CM028", "detail": "CM0028"}],
        }
        diag = diagnose_results([
            _result(expected="satisfied", actual="satisfied", grounding=grounding),
        ])
        assert len(diag.grounding_warnings) == 1
        assert any("CM028" in n for n in diag.grounding_warnings[0]["misspelling_names"])


class TestTechniqueScatter:
    def test_unrecognized_mismatch_with_failed_technique_gate(self):
        gate_trace = [{"gate": "step_3_technique_bridge", "passed": False, "detail": "too scattered"}]
        diag = diagnose_results([
            _result(expected="satisfied", actual="error", gate_trace=gate_trace),
        ])
        assert len(diag.technique_scatter) == 1


class TestMixedBatch:
    def test_realistic_batch(self):
        results = [
            _result(qid="R1", expected="satisfied", actual="satisfied"),
            _result(qid="R2", expected="satisfied", actual="satisfied"),
            _result(qid="R3", expected="satisfied", actual="not_satisfied"),
            _result(
                qid="A1", expected="not_satisfied", actual="satisfied",
                grounding={"unresolved_id_like": 1, "unresolved_terms": [{"term": "FAKE-1", "type": "id_like"}]},
            ),
            _result(qid="A2", expected="not_satisfied", actual="inconclusive"),
        ]
        diag = diagnose_results(results)
        s = diag.summary()
        assert s["total"] == 5
        assert len(diag.correct) == 3
        assert len(diag.false_negatives) == 1
        assert len(diag.grounding_failures) == 1
        assert s["fp_rate"] == 1 / 5
