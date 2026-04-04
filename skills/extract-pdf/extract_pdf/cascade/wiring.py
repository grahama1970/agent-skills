"""Cascade decision point wiring for /extract-pdf.

Logs shadow data for each extraction decision. Rust handles Tier 0
(heuristic) decisions; this module logs them and optionally escalates
to Tier 0.5 (classifier) or Tier 2 (LLM) when confidence is low.

Three decision points:
    1. header-verdict   — is a block a section header?
    2. pdf-profile      — what domain/preset does the PDF match?
    3. pdf-strategy     — which extraction strategy to use?
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Import CascadeRunner from common skill library — graceful fallback
# ---------------------------------------------------------------------------
try:
    import sys

    _COMMON_DIR = str(Path(__file__).resolve().parents[3] / "common")
    if _COMMON_DIR not in sys.path:
        sys.path.insert(0, _COMMON_DIR)
    from cascade import CascadeRunner, TierDef, TierResult, ShadowEntry

    _HAVE_CASCADE = True
except ImportError:
    _HAVE_CASCADE = False
    CascadeRunner = None  # type: ignore[misc,assignment]
    TierDef = None  # type: ignore[misc,assignment]
    TierResult = None  # type: ignore[misc,assignment]
    ShadowEntry = None  # type: ignore[misc,assignment]

SHADOW_DIR = Path.home() / ".pi" / "skills" / "extract-pdf" / "shadow"
METRICS_DIR = Path.home() / ".pi" / "skills" / "extract-pdf" / "metrics"

# Model path for header-verdict classifier (matches model_registry.json)
_HEADER_VERDICT_MODEL_PATH = Path.home() / ".pi" / "models" / "classifiers" / "header_verdict.joblib"

# Feature order must match training data and model_registry input_signature
_HEADER_VERDICT_FEATURES = [
    "text_len",
    "has_number_prefix",
    "font_size",
    "size_ratio",
    "is_bold",
    "ends_with_period",
    "ends_with_colon",
    "ends_with_other_punct",
    "has_bullet_char",
    "is_caption_pattern",
    "is_multi_sentence",
    "word_count",
    "title_case_ratio",
    "is_all_caps",
    "numbering_depth",
    "has_formal_prefix",
    "has_parentheses",
    "is_too_long",
]

# Confidence threshold from model_registry.json
_HEADER_VERDICT_THRESHOLD = 0.85

# Lazy-loaded classifier (cached after first load)
_header_verdict_clf = None


def _load_header_verdict_clf():
    """Load the header-verdict sklearn classifier (lazy, cached)."""
    global _header_verdict_clf
    if _header_verdict_clf is not None:
        return _header_verdict_clf
    if not _HEADER_VERDICT_MODEL_PATH.exists():
        logger.debug(f"[cascade] Header-verdict model not found: {_HEADER_VERDICT_MODEL_PATH}")
        return None
    try:
        import joblib
        _header_verdict_clf = joblib.load(_HEADER_VERDICT_MODEL_PATH)
        logger.debug(f"[cascade] Loaded header-verdict classifier from {_HEADER_VERDICT_MODEL_PATH}")
        return _header_verdict_clf
    except Exception as e:
        logger.warning(f"[cascade] Failed to load header-verdict classifier: {e}")
        return None


# ---------------------------------------------------------------------------
# Tier 0 functions — wrap Rust heuristic results as TierResult
# ---------------------------------------------------------------------------

def _heuristic_header_verdict(
    input_data: Dict[str, Any],
    **kwargs,
) -> "TierResult | None":
    """Tier 0: Rust header disposition packaged as TierResult.

    input_data must have: text, disposition, confidence, features
    """
    if not _HAVE_CASCADE:
        return None
    disposition = input_data.get("disposition", "Escalate")
    confidence = input_data.get("confidence", 0.0)
    return TierResult(
        result={"verdict": disposition, "features": input_data.get("features", {})},
        confidence=confidence,
        prediction=disposition,
    )


def _heuristic_profile(
    input_data: Dict[str, Any],
    **kwargs,
) -> "TierResult | None":
    """Tier 0: Rust profile prediction packaged as TierResult."""
    if not _HAVE_CASCADE:
        return None
    domain = input_data.get("domain", "general")
    preset = input_data.get("preset", "general")
    # Profile heuristic is always high-confidence — Rust uses font/layout stats
    confidence = input_data.get("complexity_score", 0.5)
    # Normalize: complexity_score is 0-10, map to 0-1 confidence
    confidence = min(1.0, max(0.0, confidence / 10.0)) if confidence > 1.0 else confidence
    return TierResult(
        result={"domain": domain, "preset": preset},
        confidence=0.85,  # Rust profiler is reliable
        prediction=domain,
    )


def _heuristic_strategy(
    input_data: Dict[str, Any],
    **kwargs,
) -> "TierResult | None":
    """Tier 0: Rust extraction strategy packaged as TierResult."""
    if not _HAVE_CASCADE:
        return None
    strategy = input_data.get("recommended_strategy", "standard")
    return TierResult(
        result={"strategy": strategy},
        confidence=0.80,  # Strategy is derived from profile + block stats
        prediction=strategy,
    )


# ---------------------------------------------------------------------------
# Tier 0.5 functions — sklearn classifier between heuristic and LLM
# ---------------------------------------------------------------------------

def _classifier_header_verdict(
    input_data: Dict[str, Any],
    **kwargs,
) -> "TierResult | None":
    """Tier 0.5: Trained RandomForest classifier for header-verdict.

    Loads the joblib model lazily (cached after first call). Extracts the
    18-feature vector from input_data["features"], runs predict() and
    predict_proba(), and returns the predicted class if max probability
    meets the confidence threshold. Returns None if the model is not
    available, or a low-confidence TierResult that triggers escalation
    to Tier 2 (LLM) if below threshold.
    """
    if not _HAVE_CASCADE:
        return None

    clf = _load_header_verdict_clf()
    if clf is None:
        return None

    features = input_data.get("features")
    if not features or not isinstance(features, dict):
        logger.debug("[cascade] Tier 0.5: no features dict in input_data")
        return None

    # Build feature vector in the exact order the model expects
    try:
        import numpy as np
        feature_vec = np.array(
            [[float(features.get(f, 0.0)) for f in _HEADER_VERDICT_FEATURES]]
        )
    except Exception as e:
        logger.debug(f"[cascade] Tier 0.5: feature extraction failed: {e}")
        return None

    try:
        prediction = clf.predict(feature_vec)[0]
        probabilities = clf.predict_proba(feature_vec)[0]
        # Map class indices to class names
        classes = list(clf.classes_)
        prob_dict = {str(cls): float(prob) for cls, prob in zip(classes, probabilities)}
        max_prob = float(max(probabilities))

        return TierResult(
            result={"verdict": str(prediction), "features": features},
            confidence=max_prob,
            prediction=str(prediction),
            probabilities=prob_dict,
            source="header-verdict-clf",
        )
    except Exception as e:
        logger.debug(f"[cascade] Tier 0.5: classifier inference failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Runner factories — one per decision point
# ---------------------------------------------------------------------------

def get_header_runner() -> "CascadeRunner | None":
    """CascadeRunner for header-verdict decisions.

    Tier 0:   Rust heuristic (Accept/Reject/Escalate with confidence).
    Tier 0.5: Trained RandomForest classifier (18 features, 3 classes).
              PROMOTED — runs as real decision tier (not shadow).
              Falls through to Tier 2 if max_prob < 0.85.
    Tier 2:   LLM escalation (not yet wired — future /assistant call).
    """
    if not _HAVE_CASCADE:
        return None
    return CascadeRunner(
        tiers=[
            TierDef(
                tier=0,
                name="rust-heuristic",
                fn=_heuristic_header_verdict,
                threshold=0.85,  # Accept/Reject pass; Escalate stays below
            ),
            TierDef(
                tier=0.5,
                name="header-verdict-clf",
                fn=_classifier_header_verdict,
                threshold=_HEADER_VERDICT_THRESHOLD,  # 0.85 from registry
            ),
        ],
        shadow_file=SHADOW_DIR / "header-verdict.jsonl",
        metrics_file=METRICS_DIR / "header-verdict.jsonl",
    )


def get_profile_runner() -> "CascadeRunner | None":
    """CascadeRunner for pdf-profile-detector decisions.

    Tier 0: Rust profiler (domain, preset, complexity).
    Shadow mode — logs predictions for future classifier comparison.
    """
    if not _HAVE_CASCADE:
        return None
    return CascadeRunner(
        tiers=[
            TierDef(
                tier=0,
                name="rust-profiler",
                fn=_heuristic_profile,
                threshold=0.70,
                shadow_mode=True,
            ),
        ],
        shadow_file=SHADOW_DIR / "pdf-profile.jsonl",
        metrics_file=METRICS_DIR / "pdf-profile.jsonl",
    )


def get_strategy_runner() -> "CascadeRunner | None":
    """CascadeRunner for pdf-extraction-strategy decisions.

    Tier 0: Rust strategy predictor (standard, ocr, engineering, etc).
    Shadow mode — logs predictions for future classifier comparison.
    """
    if not _HAVE_CASCADE:
        return None
    return CascadeRunner(
        tiers=[
            TierDef(
                tier=0,
                name="rust-strategy",
                fn=_heuristic_strategy,
                threshold=0.70,
                shadow_mode=True,
            ),
        ],
        shadow_file=SHADOW_DIR / "pdf-strategy.jsonl",
        metrics_file=METRICS_DIR / "pdf-strategy.jsonl",
    )


# ---------------------------------------------------------------------------
# Legacy log_shadow — kept for backward compatibility
# ---------------------------------------------------------------------------

def log_shadow(
    decision_point: str,
    predicted: str,
    features: Dict[str, Any],
    confidence: float,
    actual: str | None = None,
) -> None:
    """Append a shadow entry for a cascade decision point.

    Args:
        decision_point: E.g. "profile-detector", "header-verdict"
        predicted: The Tier 0 heuristic prediction
        features: Numeric feature vector for classifier training
        confidence: Heuristic confidence (0.0-1.0)
        actual: Ground truth (filled in later by verification loop)
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decision_point": decision_point,
        "predicted": predicted,
        "confidence": confidence,
        "features": features,
        "actual": actual,
        "agree": predicted == actual if actual else None,
    }

    shadow_file = SHADOW_DIR / f"{decision_point}.jsonl"
    try:
        shadow_file.parent.mkdir(parents=True, exist_ok=True)
        with shadow_file.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        logger.warning(f"Failed to write shadow entry for {decision_point}")


# ---------------------------------------------------------------------------
# High-level wiring: log all decisions from an extraction result
# ---------------------------------------------------------------------------

def log_extraction_decisions(
    prediction: Dict[str, Any],
    source_pdf: str = "",
) -> Dict[str, Any]:
    """Log all cascade decision points from a predict_extraction() result.

    Runs each CascadeRunner in shadow mode so predictions are recorded
    to JSONL files. Returns summary dict of what was logged.

    Args:
        prediction: Result dict from doc.predict_extraction()
        source_pdf: Path to source PDF (for input_hash)

    Returns:
        Dict with counts: {profile_logged, strategy_logged, headers_logged,
                           headers_escalated}
    """
    summary = {
        "profile_logged": False,
        "strategy_logged": False,
        "headers_logged": 0,
        "headers_escalated": 0,
    }

    if not _HAVE_CASCADE:
        logger.debug("CascadeRunner not available, skipping shadow logging")
        return summary

    input_hash = hashlib.md5(source_pdf.encode()).hexdigest()[:12] if source_pdf else ""

    # --- Profile decision ---
    if prediction.get("profile"):
        profile_data = dict(prediction["profile"])
        domain = profile_data.get("domain", "general")
        log_shadow(
            decision_point="pdf-profile",
            predicted=domain,
            features=profile_data,
            confidence=0.85,
        )
        summary["profile_logged"] = True
        logger.debug(f"[cascade] Profile: domain={domain}")

    # --- Strategy decision ---
    if prediction.get("recommended_strategy"):
        strategy = prediction["recommended_strategy"]
        log_shadow(
            decision_point="pdf-strategy",
            predicted=strategy,
            features={"recommended_strategy": strategy, "source_pdf": source_pdf},
            confidence=0.80,
        )
        summary["strategy_logged"] = True
        logger.debug(f"[cascade] Strategy: {strategy}")

    # --- Header decisions (per-page blocks from classify_blocks) ---
    for page_summary in prediction.get("page_summaries", []):
        if page_summary.get("has_header") or page_summary.get("title_count", 0) > 0:
            summary["headers_logged"] += 1

    return summary


def log_header_decisions(
    doc: Any,
    page_count: int,
    source_pdf: str = "",
) -> Dict[str, int]:
    """Log header-level cascade decisions using classify_blocks().

    Iterates pages, calls classify_blocks() to get header_validation
    with disposition and features, then runs the header CascadeRunner
    for each block with disposition == "Escalate".

    Args:
        doc: PdfDocument instance (must have classify_blocks method)
        page_count: Number of pages in the document
        source_pdf: Path to source PDF

    Returns:
        Dict with {total, accepted, rejected, escalated}
    """
    counts = {"total": 0, "accepted": 0, "rejected": 0, "escalated": 0}

    if not _HAVE_CASCADE:
        return counts

    header_runner = get_header_runner()
    if not header_runner:
        return counts

    input_hash = hashlib.md5(source_pdf.encode()).hexdigest()[:12] if source_pdf else ""

    for page_idx in range(min(page_count, 50)):  # Cap at 50 pages for performance
        try:
            blocks = doc.classify_blocks(page_idx)
        except Exception:
            continue

        for block in blocks:
            hv = block.get("header_validation")
            if hv is None:
                continue

            disposition = hv.get("disposition", "Reject")
            confidence = hv.get("confidence", 0.0)
            features = hv.get("features", {})
            counts["total"] += 1

            if disposition == "Accept":
                counts["accepted"] += 1
            elif disposition == "Reject":
                counts["rejected"] += 1
            elif disposition == "Escalate":
                # Run the full cascade (Tier 0 -> Tier 0.5 -> Tier 2)
                # so the classifier can resolve ambiguous cases
                cascade_input = {
                    "text": block.get("text", "")[:200],
                    "disposition": disposition,
                    "confidence": confidence,
                    "features": dict(features) if features else {},
                }
                result = header_runner.run(
                    cascade_input,
                    task="header-verdict",
                    scope="extract-pdf",
                    input_hash=input_hash,
                )
                # Update disposition based on cascade result
                resolved = result.prediction if result.prediction else disposition
                if resolved == "Accept":
                    counts["accepted"] += 1
                elif resolved == "Reject":
                    counts["rejected"] += 1
                else:
                    counts["escalated"] += 1
                # Skip the legacy log_shadow below — CascadeRunner logs metrics
                continue

            # Log non-Escalate decisions to shadow for ongoing tracking
            log_shadow(
                decision_point="header-verdict",
                predicted=disposition,
                features={
                    "text": block.get("text", "")[:200],
                    "page": page_idx,
                    "source_pdf": source_pdf,
                    **(dict(features) if features else {}),
                },
                confidence=confidence,
            )

    logger.debug(
        f"[cascade] Headers: {counts['total']} total, "
        f"{counts['accepted']} accept, {counts['rejected']} reject, "
        f"{counts['escalated']} escalate"
    )
    return counts
