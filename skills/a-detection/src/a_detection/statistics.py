"""Fixed-threshold binomial uncertainty and session-level metrics; no tuning on test data."""
from dataclasses import dataclass

import numpy as np
from scipy.stats import beta

from a_detection.errors import Code, DetectionError


@dataclass(frozen=True, slots=True)
class Rates:
    human_sessions: int
    machine_sessions: int
    false_positives: int
    true_positives: int
    fpr: float | None
    tpr: float | None
    fpr_upper: float | None


def upper_binomial(errors: int, total: int, confidence: float = 0.95) -> float | None:
    if total < 0 or errors < 0 or errors > total or not 0 < confidence < 1:
        raise DetectionError(Code.INVALID_INPUT, "Invalid binomial inputs.")
    if total == 0:
        return None
    if errors == total:
        return 1.0
    return float(beta.ppf(confidence, errors + 1, total - errors))


def rates(labels: list[str], scores: list[float], threshold: float,
          confidence: float = 0.95) -> Rates:
    if len(labels) != len(scores) or not np.isfinite(threshold):
        raise DetectionError(Code.INVALID_INPUT, "Invalid score dimensions or threshold.")
    if any(label not in ("human", "machine") for label in labels):
        raise DetectionError(Code.INVALID_INPUT, "Binary rates require explicit binary labels.")
    if any(not np.isfinite(score) or not 0 <= score <= 1 for score in scores):
        raise DetectionError(Code.INVALID_INPUT, "Scores must be finite and bounded.")
    human = sum(label == "human" for label in labels)
    machine = len(labels) - human
    fp = sum(label == "human" and score >= threshold for label, score in zip(labels, scores, strict=True))
    tp = sum(label == "machine" and score >= threshold for label, score in zip(labels, scores, strict=True))
    return Rates(human, machine, fp, tp, fp / human if human else None,
                 tp / machine if machine else None, upper_binomial(fp, human, confidence))


def choose_threshold(labels: list[str], scores: list[float], target_fpr: float) -> float:
    if set(labels) != {"human", "machine"} or not 0 < target_fpr < 1:
        raise DetectionError(Code.INVALID_INPUT, "Tuning needs both classes and a valid target FPR.")
    # 1.0 is retained as a bounded fallback. Saturated scores may leave no usable threshold.
    candidates = sorted(set([0.0, 1.0] + [float(np.nextafter(x, 1.0)) for x in scores]))
    viable = [(rates(labels, scores, threshold), threshold) for threshold in candidates]
    viable = [(metric, threshold) for metric, threshold in viable
              if metric.fpr is not None and metric.fpr <= target_fpr]
    if not viable:
        raise DetectionError(Code.MODEL, "No threshold meets even the empirical tuning FPR.")
    return max(viable, key=lambda pair: (pair[0].tpr or 0.0, pair[1]))[1]
