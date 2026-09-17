"""Evidence-aware inference; missing coverage abstains and behavior never becomes authorship."""
from loguru import logger

from a_detection.contracts import Analysis, Policy
from a_detection.errors import DetectionError
from a_detection.io import text_digest
from a_detection.model import ModelArtifact, model_digest, predict

LIMITATIONS = [
    "A classifier score is not a percentage of AI authorship or proof of misconduct.",
    "Client events are untrusted reports; receipt hashes do not prove a human typed the code.",
    "Paste, input method, typing speed, or missing events are not evidence of AI use.",
    "No automatic penalties; reviewers must consider authorized tools and accessibility needs.",
    "Provider-agnostic interface does not establish performance on all providers.",
]


def analyze(source: str, language: str, policy: Policy, model: ModelArtifact | None = None,
            observations: dict[str, int | float | str | bool] | None = None) -> Analysis:
    common = {"source_sha256": text_digest(source), "limitations": LIMITATIONS,
              "observations": observations or {}, "reasons": []}
    reason = None
    if language != "python":
        reason = "Unsupported language for the supplied detector; evidence capture remains available."
    elif len(source.strip()) < policy.min_code_chars:
        reason = "Insufficient source length for this detector."
    elif model is None:
        reason = "No trained and calibrated model has been supplied."
    if reason:
        return Analysis(disposition="INSUFFICIENT_EVIDENCE", **{**common, "reasons": [reason]})
    if model is None:  # keeps the type boundary explicit, not a runtime assertion
        raise ValueError("Unreachable missing-model state.")
    try:
        score = predict(model, source)
    except DetectionError:
        logger.error("classified_failure module=analysis")
        return Analysis(disposition="INSUFFICIENT_EVIDENCE",
                        **{**common, "reasons": ["Source is not supported by the bounded parser."]})
    eligible = (model.calibration.qualified and not model.synthetic_training
                and model.calibration.target_fpr <= policy.target_fpr
                and model.calibration.confidence >= policy.confidence)
    disposition = ("REVIEW_SUGGESTED" if score >= model.calibration.threshold else "NO_ELEVATED_SIGNAL")
    if not eligible:
        disposition = "INSUFFICIENT_EVIDENCE"
    return Analysis(
        disposition=disposition, raw_classifier_score=score, model_sha256=model_digest(model),
        calibration_qualified=eligible,
        **{**common, "reasons": [
            "Research-only score; independent real-world provenance and transportability remain unproven."
            if eligible else "Synthetic training, inadequate calibration, or a weaker-than-policy FPR bound."
        ]},
    )
