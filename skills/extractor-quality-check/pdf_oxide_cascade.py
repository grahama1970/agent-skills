"""PDF Oxide Cascade Decision Points.

Wires CascadeRunner instances for pdf_oxide engine decisions:
- pdf-profile-detector: domain/preset classification
- pdf-extraction-strategy: OCR vs native vs hybrid routing

These run alongside the existing extraction-quality-assessor and
table-strategy-selector cascades, sharing the same shadow/metrics
infrastructure.

Usage:
    from pdf_oxide_cascade import get_profile_runner, get_strategy_runner

    result = get_profile_runner().run(
        {"page_count": 10, "file_size_mb": 2.5, "first_page_text": "..."},
        task="pdf-profile-detector",
    )
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

try:
    from common.cascade import CascadeRunner, TierDef, TierResult
except ImportError:
    # Fallback for standalone testing
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
    from cascade import CascadeRunner, TierDef, TierResult

# Shadow and metrics directories (under extractor-quality-check)
_SKILL_DIR = Path(__file__).resolve().parent
_SHADOW_DIR = _SKILL_DIR / "shadow"
_METRICS_DIR = _SKILL_DIR / "metrics"


# ---------------------------------------------------------------------------
# Tier 0: Heuristic functions
# ---------------------------------------------------------------------------

def _profile_heuristic(
    input_data: Any,
    task: str = "",
    scope: str = "",
    **kwargs,
) -> Optional[TierResult]:
    """Heuristic domain/preset detection from text features.

    Mirrors the logic in s00_profile_detector.infer_domain() and match_preset().
    """
    if not isinstance(input_data, dict):
        return None

    text = input_data.get("first_page_text", "")
    filename = input_data.get("filename", "")
    page_count = input_data.get("page_count", 0)
    fname = filename.lower()

    # Domain heuristics
    if any(t in fname for t in ["arxiv", "paper", "journal", "proceedings"]):
        domain = "scientific"
    elif any(t in fname for t in ["spec", "requirement", "bht", "boeing", "std"]):
        domain = "engineering"
    elif any(t in fname for t in ["contract", "agreement", "legal"]):
        domain = "legal"
    elif re.search(r"\\frac|\\sum|\\int|\\partial", text):
        domain = "scientific"
    elif re.search(r"shall\b.*\b(comply|meet|provide)", text, re.IGNORECASE):
        domain = "engineering"
    else:
        domain = "general"

    # Confidence based on signal strength
    confidence = 0.6 if domain == "general" else 0.8

    return TierResult(
        result={"domain": domain, "page_count": page_count},
        prediction=domain,
        confidence=confidence,
        source="heuristic",
    )


def _strategy_heuristic(
    input_data: Any,
    task: str = "",
    scope: str = "",
    **kwargs,
) -> Optional[TierResult]:
    """Heuristic extraction strategy selection.

    Routes: scanned -> OCR, simple -> native, complex -> accurate.
    """
    if not isinstance(input_data, dict):
        return None

    profile = input_data.get("profile", {})
    is_scanned = profile.get("is_scanned", False)
    page_count = profile.get("page_count", 0)
    has_tables = profile.get("has_tables", False)
    has_formulas = profile.get("has_formulas", False)
    complexity = profile.get("complexity_score", 0)

    if is_scanned:
        strategy = "ocr"
        confidence = 0.9
    elif complexity >= 3 or (has_tables and has_formulas):
        strategy = "accurate"
        confidence = 0.7
    elif page_count > 100:
        strategy = "accurate"
        confidence = 0.65
    else:
        strategy = "fast"
        confidence = 0.85

    return TierResult(
        result={"strategy": strategy, "complexity": complexity},
        prediction=strategy,
        confidence=confidence,
        source="heuristic",
    )


# ---------------------------------------------------------------------------
# Tier 0.5: Classifier stubs (activated when models are trained)
# ---------------------------------------------------------------------------

def _profile_classifier(
    input_data: Any,
    task: str = "",
    scope: str = "",
    **kwargs,
) -> Optional[TierResult]:
    """Classifier-based preset detection.

    Loads from model_registry.json -> pdf-profile-detector.
    Returns None if model not available (graceful skip).
    """
    # Check if model is available
    registry_path = _SKILL_DIR.parent / "assistant" / "model_registry.json"
    if not registry_path.exists():
        return None

    try:
        registry = json.loads(registry_path.read_text())
        classifier_cfg = registry.get("classifiers", {}).get("pdf-profile-detector")
        if not classifier_cfg:
            return None

        model_path = Path(classifier_cfg.get("model_path", "")).expanduser()
        if not model_path.exists():
            logger.debug("pdf-profile-detector model not yet trained")
            return None

        # Future work: Load sklearn model and predict
        # For now, return None to skip to next tier
        return None
    except Exception as e:
        logger.debug(f"Profile classifier failed: {e}")
        return None


def _strategy_classifier(
    input_data: Any,
    task: str = "",
    scope: str = "",
    **kwargs,
) -> Optional[TierResult]:
    """Classifier-based extraction strategy selection.

    Uses extraction-error-classifier from model_registry.json.
    Returns None if model not available.
    """
    registry_path = _SKILL_DIR.parent / "assistant" / "model_registry.json"
    if not registry_path.exists():
        return None

    try:
        registry = json.loads(registry_path.read_text())
        classifier_cfg = registry.get("classifiers", {}).get("extraction-error-classifier")
        if not classifier_cfg:
            return None

        model_path = Path(classifier_cfg.get("model_path", "")).expanduser()
        if not model_path.exists():
            logger.debug("extraction-error-classifier model not yet trained")
            return None

        # Future work: Load distilbert model and predict
        return None
    except Exception as e:
        logger.debug(f"Strategy classifier failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Runner factories
# ---------------------------------------------------------------------------

_profile_runner: Optional[CascadeRunner] = None
_strategy_runner: Optional[CascadeRunner] = None


def get_profile_runner() -> CascadeRunner:
    """Get or create the pdf-profile-detector cascade runner."""
    global _profile_runner
    if _profile_runner is None:
        _profile_runner = CascadeRunner(
            tiers=[
                TierDef(tier=0, name="heuristic", fn=_profile_heuristic),
                TierDef(
                    tier=0.5, name="classifier", fn=_profile_classifier,
                    threshold=0.85, shadow_mode=True,
                ),
            ],
            shadow_file=_SHADOW_DIR / "pdf-profile-detector.jsonl",
            metrics_file=_METRICS_DIR / "pdf-profile-detector.jsonl",
        )
    return _profile_runner


def get_strategy_runner() -> CascadeRunner:
    """Get or create the pdf-extraction-strategy cascade runner."""
    global _strategy_runner
    if _strategy_runner is None:
        _strategy_runner = CascadeRunner(
            tiers=[
                TierDef(tier=0, name="heuristic", fn=_strategy_heuristic),
                TierDef(
                    tier=0.5, name="classifier", fn=_strategy_classifier,
                    threshold=0.80, shadow_mode=True,
                ),
            ],
            shadow_file=_SHADOW_DIR / "pdf-extraction-strategy.jsonl",
            metrics_file=_METRICS_DIR / "pdf-extraction-strategy.jsonl",
        )
    return _strategy_runner


def run_profile_cascade(
    page_count: int,
    file_size_mb: float,
    first_page_text: str,
    filename: str = "",
) -> Dict[str, Any]:
    """Convenience wrapper for profile detection cascade.

    Returns dict with domain, confidence, source, and cascade metadata.
    """
    input_data = {
        "page_count": page_count,
        "file_size_mb": file_size_mb,
        "first_page_text": first_page_text[:2000],
        "filename": filename,
    }
    input_hash = hashlib.sha256(
        json.dumps(input_data, sort_keys=True).encode()
    ).hexdigest()[:16]

    result = get_profile_runner().run(
        input_data,
        task="pdf-profile-detector",
        input_hash=input_hash,
    )
    return {
        "domain": result.prediction or result.result.get("domain", "general"),
        "confidence": result.confidence,
        "source": result.source,
        "tier": result.tier,
        "latency_ms": result.latency_ms,
    }


def run_strategy_cascade(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience wrapper for extraction strategy cascade.

    Returns dict with strategy, confidence, source, and cascade metadata.
    """
    input_data = {"profile": profile}
    input_hash = hashlib.sha256(
        json.dumps(input_data, sort_keys=True).encode()
    ).hexdigest()[:16]

    result = get_strategy_runner().run(
        input_data,
        task="pdf-extraction-strategy",
        input_hash=input_hash,
    )
    return {
        "strategy": result.prediction or result.result.get("strategy", "fast"),
        "confidence": result.confidence,
        "source": result.source,
        "tier": result.tier,
        "latency_ms": result.latency_ms,
    }
