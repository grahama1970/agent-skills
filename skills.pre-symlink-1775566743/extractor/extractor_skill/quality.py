#!/usr/bin/env python3
"""
Quality module for extractor skill.

Provides quality gates and learning from extraction outcomes.

Usage:
    from extractor_skill.quality import ExtractionGate, LearningTracker, BATCH_GATE

    # Quality gate evaluation
    gate = ExtractionGate(name="batch")
    should_continue, reason = gate.check_batch_health(completed=10, failed=2)

    # Learning from outcomes
    tracker = LearningTracker(scope="documents")
    tracker.record_success("doc.pdf", preset="arxiv", retry_count=0)
    tracker.record_failure("fail.pdf", error="Timeout", retry_count=3)
    tracker.flush()
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Environment variable names
ENV_CONFIDENCE_MIN = "EXTRACTOR_GATE_CONFIDENCE_MIN"
ENV_SUCCESS_RATE_MIN = "EXTRACTOR_GATE_SUCCESS_RATE_MIN"
ENV_ERROR_RATE_MAX = "EXTRACTOR_GATE_ERROR_RATE_MAX"
ENV_CONSECUTIVE_ERRORS_MAX = "EXTRACTOR_GATE_CONSECUTIVE_ERRORS_MAX"
ENV_RETRY_MAX = "EXTRACTOR_RETRY_MAX"
ENV_RETRY_BASE_DELAY = "EXTRACTOR_RETRY_BASE_DELAY"

# Default thresholds
GATE_DEFAULTS = {
    "confidence_min": 8,
    "success_rate": 0.8,
    "error_rate_max": 0.1,
    "consecutive_errors_max": 5,
}


def _get_threshold(env_var: str, default: float) -> float:
    """Get threshold from env var or default."""
    val = os.getenv(env_var)
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return default


@dataclass
class ExtractionGate:
    """Quality gate for extraction operations.

    Thresholds can be set via:
    1. Constructor arguments (highest priority)
    2. Environment variables (EXTRACTOR_GATE_*)
    3. Defaults from GATE_DEFAULTS

    Args:
        name: Gate name for identification
        thresholds: Dict of metric -> threshold value
    """

    name: str
    thresholds: Dict[str, float] = field(default_factory=dict)
    _initialized: bool = field(default=False, repr=False)

    def __post_init__(self):
        """Load thresholds from env vars and defaults."""
        if self._initialized:
            return

        # Load defaults with env var override
        if "confidence_min" not in self.thresholds:
            self.thresholds["confidence_min"] = _get_threshold(
                ENV_CONFIDENCE_MIN, GATE_DEFAULTS["confidence_min"]
            )
        if "success_rate" not in self.thresholds:
            self.thresholds["success_rate"] = _get_threshold(
                ENV_SUCCESS_RATE_MIN, GATE_DEFAULTS["success_rate"]
            )
        if "error_rate_max" not in self.thresholds:
            self.thresholds["error_rate_max"] = _get_threshold(
                ENV_ERROR_RATE_MAX, GATE_DEFAULTS["error_rate_max"]
            )
        if "consecutive_errors_max" not in self.thresholds:
            self.thresholds["consecutive_errors_max"] = _get_threshold(
                ENV_CONSECUTIVE_ERRORS_MAX, GATE_DEFAULTS["consecutive_errors_max"]
            )

        self._initialized = True

    def check_confidence(self, confidence: int) -> Tuple[bool, str]:
        """Check if confidence meets threshold for auto-extraction.

        Args:
            confidence: Preset confidence score

        Returns:
            Tuple of (meets_threshold, reason)
        """
        min_confidence = int(self.thresholds.get("confidence_min", 8))
        if confidence >= min_confidence:
            return True, "ok"
        return False, f"confidence={confidence} < {min_confidence}"

    def check_batch_health(
        self,
        completed: int,
        failed: int,
        consecutive_errors: int = 0,
    ) -> Tuple[bool, str]:
        """Check if a batch operation should continue.

        Args:
            completed: Number of items completed
            failed: Number of items failed
            consecutive_errors: Number of consecutive errors

        Returns:
            Tuple of (should_continue, reason)
        """
        if completed == 0:
            return True, "ok"

        # Check error rate
        error_rate = failed / completed
        max_error_rate = self.thresholds.get("error_rate_max", 0.1)
        if error_rate > max_error_rate:
            return False, f"error_rate={error_rate:.2%} exceeds {max_error_rate:.2%}"

        # Check consecutive errors
        max_consecutive = int(self.thresholds.get("consecutive_errors_max", 5))
        if consecutive_errors >= max_consecutive:
            return False, f"consecutive_errors={consecutive_errors} >= {max_consecutive}"

        # Check success rate
        success_rate = 1 - error_rate
        min_success_rate = self.thresholds.get("success_rate", 0.8)
        if success_rate < min_success_rate:
            return False, f"success_rate={success_rate:.2%} below {min_success_rate:.2%}"

        return True, "ok"

    def evaluate(self, metrics: Dict[str, float]) -> Tuple[bool, Dict[str, Any]]:
        """Evaluate metrics against thresholds.

        Args:
            metrics: Dict of metric name -> actual value

        Returns:
            Tuple of (passed, details) where details contains per-metric results
        """
        results = {}
        all_passed = True

        for metric, threshold in self.thresholds.items():
            value = metrics.get(metric)
            if value is None:
                continue

            # For _max metrics, check if value is below threshold
            if metric.endswith("_max"):
                passed = value <= threshold
            else:
                passed = value >= threshold

            results[metric] = {
                "value": value,
                "threshold": threshold,
                "passed": passed,
            }

            if not passed:
                all_passed = False

        return all_passed, {
            "gate": self.name,
            "passed": all_passed,
            "metrics": results,
        }


@dataclass
class OutcomeRecord:
    """Record of a single extraction outcome."""

    item_id: str
    success: bool
    retry_count: int = 0
    error_context: Optional[str] = None
    preset: Optional[str] = None
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "item_id": self.item_id,
            "success": self.success,
            "retry_count": self.retry_count,
            "error_context": self.error_context[:200] if self.error_context else None,
            "preset": self.preset,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


class LearningTracker:
    """Track extraction outcomes for memory learning.

    Learns from:
    - Success patterns: which presets work for which documents
    - Error patterns: recurring failures and their causes
    - Retry complexity: documents that need many retries

    Args:
        scope: Scope for learning (default: "documents")
        batch_size: Flush to memory after this many outcomes (default: 50)
        auto_flush: Whether to auto-flush on batch size (default: True)
    """

    def __init__(
        self,
        scope: str = "documents",
        batch_size: int = 50,
        auto_flush: bool = True,
    ):
        self.scope = scope
        self.batch_size = batch_size
        self.auto_flush = auto_flush

        self._outcomes: List[OutcomeRecord] = []
        self._start_time = time.time()

    def record_success(
        self,
        item_id: str,
        preset: Optional[str] = None,
        retry_count: int = 0,
        duration_ms: int = 0,
        **metadata: Any,
    ) -> None:
        """Record a successful extraction.

        Args:
            item_id: Document identifier (filename)
            preset: Preset used for extraction
            retry_count: Number of retries needed
            duration_ms: Extraction duration
            **metadata: Additional metadata (sections, tables, etc.)
        """
        self._outcomes.append(
            OutcomeRecord(
                item_id=item_id,
                success=True,
                preset=preset,
                retry_count=retry_count,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        )

        if self.auto_flush and len(self._outcomes) >= self.batch_size:
            self.flush()

    def record_failure(
        self,
        item_id: str,
        error_context: str,
        preset: Optional[str] = None,
        retry_count: int = 0,
        duration_ms: int = 0,
        **metadata: Any,
    ) -> None:
        """Record a failed extraction.

        Args:
            item_id: Document identifier
            error_context: Error message or context
            preset: Preset attempted
            retry_count: Number of retries attempted
            duration_ms: Extraction duration
            **metadata: Additional metadata
        """
        self._outcomes.append(
            OutcomeRecord(
                item_id=item_id,
                success=False,
                error_context=error_context[:500],
                preset=preset,
                retry_count=retry_count,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        )

        if self.auto_flush and len(self._outcomes) >= self.batch_size:
            self.flush()

    def flush(self) -> Dict[str, Any]:
        """Persist outcomes to memory.

        Returns:
            Dict with flush statistics
        """
        if not self._outcomes:
            return {"learned": 0, "skipped": 0}

        learned = 0
        skipped = 0

        # Try to import memory integration
        try:
            from extractor_skill.memory_integration import (
                learn_to_memory,
                learn_failure_to_memory,
            )
            has_memory = True
        except ImportError:
            has_memory = False

        for outcome in self._outcomes:
            if not has_memory:
                skipped += 1
                continue

            try:
                if outcome.success:
                    # Build result dict for learn_to_memory
                    result = {
                        "success": True,
                        "preset": outcome.preset,
                        "counts": outcome.metadata,
                    }
                    from pathlib import Path
                    if learn_to_memory(Path(outcome.item_id), result, self.scope):
                        learned += 1
                    else:
                        skipped += 1
                else:
                    # Learn from failure
                    if learn_failure_to_memory(
                        Path(outcome.item_id),
                        outcome.error_context or "Unknown error",
                        outcome.retry_count,
                        self.scope,
                    ):
                        learned += 1
                    else:
                        skipped += 1
            except Exception:
                skipped += 1

        self._outcomes.clear()
        return {"learned": learned, "skipped": skipped}

    def get_stats(self) -> Dict[str, Any]:
        """Get accumulated stats without flushing."""
        successes = sum(1 for o in self._outcomes if o.success)
        failures = len(self._outcomes) - successes
        total_retries = sum(o.retry_count for o in self._outcomes)

        return {
            "pending": len(self._outcomes),
            "successes": successes,
            "failures": failures,
            "total_retries": total_retries,
            "avg_retries": total_retries / len(self._outcomes) if self._outcomes else 0,
            "scope": self.scope,
            "elapsed_ms": int((time.time() - self._start_time) * 1000),
        }

    def __enter__(self) -> "LearningTracker":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - flush remaining outcomes."""
        self.flush()


# Pre-configured gates
BATCH_GATE = ExtractionGate(
    name="batch",
    thresholds={
        "success_rate": 0.8,
        "error_rate_max": 0.1,
        "consecutive_errors_max": 5,
    },
)

CONFIDENCE_GATE = ExtractionGate(
    name="confidence",
    thresholds={
        "confidence_min": 8,
    },
)
