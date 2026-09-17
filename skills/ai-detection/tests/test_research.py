"""Independent contrastive-score numerical controls; not live transformer qualification."""
import numpy as np
import pytest

from ai_detection.errors import DetectionError
from ai_detection.research import contrastive_math, weights_manifest


def test_uniform_reference_score_is_one():
    logits = np.zeros((4, 5))
    score, nll, cross = contrastive_math(logits, logits, np.array([0, 1, 2, 3]))
    assert score == pytest.approx(1.0)


def test_reference_score_matches_independent_manual_math():
    left = np.array([[0.0, 1.0], [2.0, -1.0]])
    right = np.array([[0.5, -0.5], [-1.0, 1.0]])
    targets = np.array([1, 0])
    p = np.exp(left) / np.exp(left).sum(axis=1, keepdims=True)
    q = np.exp(right) / np.exp(right).sum(axis=1, keepdims=True)
    expected = -np.log(p[np.arange(2), targets]).mean() / -(p * np.log(q)).sum(axis=1).mean()
    score, nll, cross = contrastive_math(left, right, targets)
    assert score == pytest.approx(expected)
    assert nll > 0 and cross > 0


def test_untrusted_weights_are_not_deserialized(tmp_path):
    (tmp_path / "model.bin").write_bytes(b"not even a real pickle")
    with pytest.raises(DetectionError):
        weights_manifest(tmp_path)
