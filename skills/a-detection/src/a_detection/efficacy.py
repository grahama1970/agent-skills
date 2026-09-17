"""A real-corpus numeric gate with frozen thresholds and simultaneous conservative bounds.

This checks declared independent study evidence, not whether provenance statements
are truthful. Passing numerical criteria never replaces independent human review.
"""
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import Field
from scipy.stats import beta

from a_detection.contracts import Policy, Sha256, Strict
from a_detection.dataset import audit_splits, load_records
from a_detection.errors import Code, DetectionError
from a_detection.model import evaluate, load_model, predict, session_scores
from a_detection.statistics import rates


class EfficacyRequest(Strict):
    schema_version: Literal["a_detection.efficacy_request.v1"] = "a_detection.efficacy_request.v1"
    corpus: str
    model: str
    model_sha256: Sha256
    study_id: str = Field(min_length=1, max_length=200)
    min_tpr: float = Field(gt=0, lt=1)
    minimum_heldout_families: int = Field(ge=1, le=100)
    minimum_test_human_sessions: int = Field(ge=1)
    require_temporal_holdout: bool = True


class FamilyBound(Strict):
    machine_sessions: int
    true_positives: int
    tpr_lower: float


class EfficacyReport(Strict):
    schema_version: Literal["a_detection.efficacy_numeric_gate.v1"] = "a_detection.efficacy_numeric_gate.v1"
    status: Literal["PASS", "FAIL"]
    study_id: str
    model_sha256: Sha256
    corpus_sha256: Sha256
    target_fpr: float
    minimum_tpr: float
    simultaneous_confidence: float
    per_comparison_confidence: float
    test_human_sessions: int
    test_fpr_upper: float | None
    by_heldout_family: dict[str, FamilyBound]
    problems: list[str]
    proves: Literal["Only numerical criteria on the frozen, declared study corpus."] = "Only numerical criteria on the frozen, declared study corpus."
    provenance: Literal["DECLARED_NOT_INDEPENDENTLY_VERIFIED"] = "DECLARED_NOT_INDEPENDENTLY_VERIFIED"
    independent_human_review: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"
    all_provider_claim: Literal[False] = False
    release_readiness: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"


def qualify(request: EfficacyRequest, policy: Policy) -> EfficacyReport:
    records = load_records(Path(request.corpus), allow_synthetic=False)
    model = load_model(Path(request.model), request.model_sha256)
    if model.synthetic_training:
        raise DetectionError(Code.INVALID_INPUT, "Synthetic-trained models cannot enter the efficacy gate.")
    audit = audit_splits(records)
    benchmark = evaluate(model, records)  # rechecks exact frozen corpus binding, not supplied summary prose
    families = audit["heldout_families"]
    confidence = 1 - (1 - policy.confidence) / (len(families) + 1)
    test = [row for row in records if row.split == "test" and row.label in ("human", "machine")]
    scores = [predict(model, row.source) for row in test]
    labels, maxima = session_scores(test, scores)
    measured = rates(labels, maxima, model.calibration.threshold, confidence)
    problems = []
    if (not model.calibration.qualified or model.calibration.target_fpr > policy.target_fpr
            or model.calibration.confidence < policy.confidence):
        problems.append("Independent calibration does not satisfy the active policy.")
    if request.require_temporal_holdout and not audit["temporal_holdout"]:
        problems.append("The requested chronological holdout is missing.")
    if len(families) < request.minimum_heldout_families:
        problems.append("Too few unseen generator families.")
    if measured.human_sessions < request.minimum_test_human_sessions:
        problems.append("Too few independent human test sessions.")
    # Repeated authors across sessions would make a naive session-binomial bound overconfident.
    for split in ("calibration", "test"):
        authors: dict[str, set[str]] = defaultdict(set)
        for row in records:
            if row.split == split and row.label == "human":
                authors[row.author_id].add(row.session_id)
        if any(len(sessions) > 1 for sessions in authors.values()):
            problems.append(f"Repeated human authors across {split} sessions violate this gate's independence protocol.")
    if measured.fpr_upper is None or measured.fpr_upper > policy.target_fpr:
        problems.append("Held-out human FPR confidence bound exceeds the policy limit.")
    family_bounds = {}
    for family in families:
        selected = [(row, score) for row, score in zip(test, scores, strict=True)
                    if row.label == "machine" and row.model_family == family]
        _, per_session = session_scores([row for row, _ in selected], [score for _, score in selected])
        n = len(per_session)
        hits = sum(score >= model.calibration.threshold for score in per_session)
        lower = float(beta.ppf(1 - confidence, hits, n - hits + 1)) if hits else 0.0
        family_bounds[family] = FamilyBound(machine_sessions=n, true_positives=hits, tpr_lower=lower)
        if lower < request.min_tpr:
            problems.append(f"Family {family}: TPR lower confidence bound is below the study requirement.")
    return EfficacyReport(status="FAIL" if problems else "PASS", study_id=request.study_id,
        model_sha256=benchmark["model_sha256"], corpus_sha256=model.corpus_sha256,
        target_fpr=policy.target_fpr, minimum_tpr=request.min_tpr,
        simultaneous_confidence=policy.confidence, per_comparison_confidence=confidence,
        test_human_sessions=measured.human_sessions, test_fpr_upper=measured.fpr_upper,
        by_heldout_family=family_bounds, problems=problems)
