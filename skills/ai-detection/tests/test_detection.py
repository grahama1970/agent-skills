"""Detector training, split audits, abstention, and low-FPR math; no real-human accuracy claims."""
import numpy as np
import pytest
from pydantic import ValidationError

from ai_detection.analysis import analyze
from ai_detection.contracts import Policy
from ai_detection.dataset import audit_splits, load_records
from ai_detection.errors import DetectionError
from ai_detection.features import extract
from ai_detection.model import (
    Calibration,
    evaluate,
    load_model,
    model_digest,
    predict,
    save_model,
    train,
)
from ai_detection.statistics import rates, upper_binomial
from tests.helpers import corpus


def test_features_do_not_execute_code(tmp_path):
    sentinel = tmp_path / "must-not-exist"
    source = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('no')\n"
    features = extract(source)
    assert np.isfinite(features.vector).all()
    assert not sentinel.exists()


def test_normalized_view_removes_superficial_renaming():
    left = extract("def x(a):\n    return a + 1\n")
    right = extract("def alternate(value):\n    return value + 9\n")
    assert left.normalized_sha256 == right.normalized_sha256


@pytest.mark.parametrize("source,language", [("x=1", "python"), ("function x() {}", "javascript"),
    ("def broken(:", "python"), ("# comment\n" * 20, "python")])
def test_missing_model_and_unsupported_always_abstain(source, language):
    outcome = analyze(source, language, Policy())
    assert outcome.disposition == "INSUFFICIENT_EVIDENCE"
    assert outcome.authorship_established is False
    assert outcome.automatic_penalty is False
    assert outcome.raw_classifier_score is None


def test_activity_not_an_authorship_verdict():
    source = "def solve(items):\n    return [item for item in items if item is not None]\n" * 2
    first = analyze(source, "python", Policy(), observations={"reported_pastes": 0})
    second = analyze(source, "python", Policy(), observations={"reported_pastes": 1000})
    assert first.disposition == second.disposition == "INSUFFICIENT_EVIDENCE"


def test_independent_low_false_positive_confidence_bound():
    assert upper_binomial(0, 10, 0.95) > 0.25
    assert upper_binomial(0, 300, 0.95) < 0.01
    assert upper_binomial(0, 0, 0.95) is None
    with pytest.raises((ValueError, DetectionError)):
        upper_binomial(11, 10, 0.95)
    with pytest.raises(ValidationError):
        Calibration(threshold=0.8, target_fpr=0.01, confidence=0.95, human_sessions=10,
                    false_positives=0, fpr_upper=0.0, qualified=True, scores_sha256="0" * 64)


@pytest.mark.parametrize("group", ["session_id", "task_id", "author_id", "repository_id", "source", "model_family"])
def test_cross_split_leakage_rejected(group):
    rows = corpus()
    original = next(item for item in rows if item.split == "train" and item.label == "machine")
    index = next(i for i, item in enumerate(rows) if item.split == "test" and item.label == "machine")
    rows[index] = rows[index].model_copy(update={group: getattr(original, group)})
    with pytest.raises(DetectionError):
        audit_splits(rows)


def test_synthetic_requires_explicit_permission(tmp_path):
    path = tmp_path / "synthetic.jsonl"
    path.write_text("\n".join(item.model_dump_json() for item in corpus()))
    with pytest.raises(DetectionError):
        load_records(path)
    assert len(load_records(path, allow_synthetic=True)) == 48


def test_train_safe_serialization_and_frozen_test_protocol(tmp_path):
    rows = corpus()
    model, report = train(rows)
    path = tmp_path / "model.json"
    save_model(path, model)
    reread = load_model(path, model_digest(model))
    assert predict(reread, rows[0].source) == predict(model, rows[0].source)
    assert model.synthetic_training is True
    assert model.calibration.qualified is False
    result = analyze(rows[0].source, "python", Policy(), model)
    assert result.disposition == "INSUFFICIENT_EVIDENCE"
    assert result.raw_classifier_score is not None
    assert report["deployment_readiness"] == "NOT_ESTABLISHED"
    replayed = evaluate(model, rows)
    assert all(report[key] == value for key, value in replayed.items())
    assert report["split_audit"]["status"] == "PASS"
    assert len(report["calibration_readback"]["labels"]) == 12
    with pytest.raises(DetectionError):
        load_model(path, "f" * 64)
    changed = list(rows)
    changed[0] = changed[0].model_copy(update={"provenance_ref": "changed after model was frozen"})
    with pytest.raises(DetectionError):
        evaluate(model, changed)


def test_rates_count_sessions_not_fragments():
    result = rates(["human", "human", "machine"], [0.1, 0.9, 0.95], 0.8, 0.95)
    assert result.false_positives == 1
