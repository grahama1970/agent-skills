"""Train a multi-view baseline, serialize safe JSON weights, certify a fixed threshold."""
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import Field, model_validator
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from a_detection.contracts import Sha256, Strict
from a_detection.dataset import Record, audit_splits
from a_detection.errors import Code, DetectionError
from a_detection.features import FEATURE_VERSION, FEATURE_WIDTH, extract
from a_detection.io import atomic_json, canonical, digest, read_json, utc_now
from a_detection.statistics import choose_threshold, rates, upper_binomial


class Calibration(Strict):
    threshold: float = Field(ge=0, le=1)
    target_fpr: float = Field(gt=0, lt=0.1)
    confidence: float = Field(gt=0.5, lt=1)
    human_sessions: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    fpr_upper: float | None = Field(ge=0, le=1)
    qualified: bool
    scores_sha256: Sha256

    @model_validator(mode="after")
    def check_math(self) -> "Calibration":
        expected = upper_binomial(self.false_positives, self.human_sessions, self.confidence)
        if (expected is None) != (self.fpr_upper is None):
            raise ValueError("Missing or fabricated FPR bound.")
        if expected is not None and abs(expected - float(self.fpr_upper)) > 1e-10:
            raise ValueError("FPR bound does not match the independent binomial calculation.")
        if self.qualified != (expected is not None and expected <= self.target_fpr):
            raise ValueError("Calibration qualification disagrees with the statistical bound.")
        return self

class ModelArtifact(Strict):
    schema_version: Literal["a_detection.linear_model.v1"] = "a_detection.linear_model.v1"
    feature_version: Literal["python-multiview-1"] = FEATURE_VERSION
    created_at: str
    weights: list[float] = Field(min_length=FEATURE_WIDTH, max_length=FEATURE_WIDTH)
    intercept: float
    mean: list[float] = Field(min_length=FEATURE_WIDTH, max_length=FEATURE_WIDTH)
    scale: list[float] = Field(min_length=FEATURE_WIDTH, max_length=FEATURE_WIDTH)
    calibration: Calibration
    corpus_sha256: Sha256
    synthetic_training: bool
    trained_families: list[str]
    heldout_families: list[str]
    provenance_status: Literal["DECLARED_NOT_INDEPENDENTLY_VERIFIED"] = "DECLARED_NOT_INDEPENDENTLY_VERIFIED"
    use_scope: Literal["research_review_only"] = "research_review_only"
    languages: Literal["python"] = "python"

    @model_validator(mode="after")
    def positive_scale(self) -> "ModelArtifact":
        if any(value <= 0 for value in self.scale):
            raise ValueError("All standardization scales must be positive.")
        if set(self.trained_families) & set(self.heldout_families):
            raise ValueError("Heldout family leakage in model metadata.")
        return self


def model_digest(model: ModelArtifact) -> str:
    return digest(canonical(model.model_dump(mode="json")))


def load_model(path: Path, expected_sha256: str | None = None) -> ModelArtifact:
    model = ModelArtifact.model_validate(read_json(path))
    if expected_sha256 is not None and model_digest(model) != expected_sha256:
        raise DetectionError(Code.INTEGRITY, "Model digest pin mismatch.")
    return model


def predict(model: ModelArtifact, source: str) -> float:
    vector = extract(source).vector
    standardized = (vector - np.array(model.mean)) / np.array(model.scale)
    value = float(expit(standardized @ np.array(model.weights) + model.intercept))
    if not np.isfinite(value):
        raise DetectionError(Code.MODEL, "Non-finite inference output.")
    return value


def session_scores(rows: list[Record], scores: list[float]) -> tuple[list[str], list[float]]:
    groups: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row, score in zip(rows, scores, strict=True):
        groups[row.session_id].append((row.label, score))
    labels, maxima = [], []
    for group in groups.values():
        if len({item[0] for item in group}) != 1:
            raise DetectionError(Code.INVALID_INPUT, "Mixed labels in a session.")
        labels.append(group[0][0])
        maxima.append(max(item[1] for item in group))
    return labels, maxima


def train(records: list[Record], target_fpr: float = 0.01,
          confidence: float = 0.95) -> tuple[ModelArtifact, dict]:
    audit = audit_splits(records)
    binary = [row for row in records if row.label in ("human", "machine")]
    groups = {split: [row for row in binary if row.split == split]
              for split in ("train", "tune", "calibration", "test")}
    if set(row.label for row in groups["train"]) != {"human", "machine"}:
        raise DetectionError(Code.INVALID_INPUT, "Training requires both binary classes.")
    x = np.stack([extract(row.source).vector for row in groups["train"]])
    y = np.array([int(row.label == "machine") for row in groups["train"]])
    scaler = StandardScaler().fit(x)
    learner = LogisticRegression(C=0.2, class_weight="balanced", solver="liblinear",
                                 random_state=0, max_iter=2000).fit(scaler.transform(x), y)
    if int(learner.n_iter_.max()) >= 2000:
        raise DetectionError(Code.MODEL, "Training did not converge within its iteration budget.")
    def score(rows: list[Record]) -> list[float]:
        if not rows:
            return []
        return learner.predict_proba(scaler.transform(
            np.stack([extract(row.source).vector for row in rows])))[:, 1].tolist()
    tune_labels, tune_scores = session_scores(groups["tune"], score(groups["tune"]))
    threshold = choose_threshold(tune_labels, tune_scores, target_fpr)
    cal_labels, cal_scores = session_scores(groups["calibration"], score(groups["calibration"]))
    cal = rates(cal_labels, cal_scores, threshold, confidence)
    calibration = Calibration(
        threshold=threshold, target_fpr=target_fpr, confidence=confidence,
        human_sessions=cal.human_sessions, false_positives=cal.false_positives,
        fpr_upper=cal.fpr_upper, qualified=cal.fpr_upper is not None and cal.fpr_upper <= target_fpr,
        scores_sha256=digest(canonical({"labels": cal_labels, "scores": cal_scores})),
    )
    model = ModelArtifact(
        created_at=utc_now(), weights=learner.coef_[0].tolist(),
        intercept=float(learner.intercept_[0]), mean=scaler.mean_.tolist(), scale=scaler.scale_.tolist(),
        calibration=calibration,
        corpus_sha256=digest(canonical([row.model_dump(mode="json") for row in records])),
        synthetic_training=any(row.origin == "synthetic" for row in records),
        trained_families=sorted({row.model_family for row in records
                                if row.split != "test" and row.model_family}),
        heldout_families=audit["heldout_families"],
    )
    report = evaluate(model, records)
    report["split_audit"] = audit
    report["calibration_readback"] = {"labels": cal_labels, "scores": cal_scores}
    return model, report


def evaluate(model: ModelArtifact, records: list[Record]) -> dict:
    audit_splits(records)
    if digest(canonical([row.model_dump(mode="json") for row in records])) != model.corpus_sha256:
        raise DetectionError(Code.INTEGRITY, "Evaluation corpus differs from the frozen training contract.")
    rows = [row for row in records if row.split == "test" and row.label in ("human", "machine")]
    scores = [predict(model, row.source) for row in rows]
    labels, maxima = session_scores(rows, scores)
    result = asdict(rates(labels, maxima, model.calibration.threshold, model.calibration.confidence))
    slices = {}
    for family in model.heldout_families:
        selected = [(row, value) for row, value in zip(rows, scores, strict=True)
                    if row.label == "human" or row.model_family == family]
        sl, ss = session_scores([row for row, _ in selected], [score for _, score in selected])
        slices[family] = asdict(rates(sl, ss, model.calibration.threshold, model.calibration.confidence))
    return {
        "schema_version": "a_detection.benchmark.v1", "model_sha256": model_digest(model),
        "corpus_sha256": model.corpus_sha256, "unit": "session_max_score", "test": result,
        "by_heldout_family": slices, "calibration": model.calibration.model_dump(mode="json"),
        "binary_test_records": len(rows),
        "unscored_hybrid_or_unknown": sum(row.split == "test" and row.label in ("hybrid", "unknown")
                                        for row in records),
        "empirical_efficacy": "NOT_ESTABLISHED" if model.synthetic_training else "MEASURED_ON_DECLARED_CORPUS_ONLY",
        "deployment_readiness": "NOT_ESTABLISHED",
        "limitations": ["Sample provenance is declared, not independently verified.",
                        "Binomial bounds assume independent representative sessions.",
                        "No population-level or all-provider guarantee.",
                        "No hybrid-code attribution; binary exclusions are counted."],
    }


def save_model(path: Path, model: ModelArtifact) -> None:
    atomic_json(path, model.model_dump(mode="json"))
