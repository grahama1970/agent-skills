"""Shared Three-Tier Validation Cascade runner.

Extracts the common escalation pattern used by /assistant, /monitor-sparta,
and /memory into a reusable runner. Each skill provides domain-specific tier
implementations; this module handles the escalation loop, shadow mode,
caching, and metrics logging.

Pattern:
    Tier 0: Heuristic (free, microseconds)
    Tier 0.5: Classifier (free, ~10ms)
    Tier 1.5: Trained GPT (free, ~200ms)
    Tier 2: scillm teacher (paid, 2-5s)

Usage:
    from common.cascade import CascadeRunner, TierResult, TierDef, ShadowEntry

    runner = CascadeRunner(
        tiers=[
            TierDef(tier=0, name="heuristic", fn=my_heuristic),
            TierDef(tier=0.5, name="classifier", fn=my_classifier, threshold=0.75),
            TierDef(tier=2, name="scillm", fn=my_scillm_call),
        ],
        shadow_file=Path("~/.pi/assistant/shadow.jsonl"),
    )

    result = runner.run(input_data, task="qra-assessor", scope="brandon_bailey")
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

import math


def wilson_score_lower(successes: int, total: int, confidence: float = 0.99) -> float:
    """Compute the lower bound of the Wilson score confidence interval.

    Uses the Wilson score interval formula for binomial proportions.
    Returns 0.0 if total is 0.

    Args:
        successes: Number of successful observations.
        total: Total number of observations.
        confidence: Confidence level (default 0.99 = 99% CI).

    Returns:
        Lower bound of the Wilson confidence interval.
    """
    if total == 0:
        return 0.0
    # z-scores for common confidence levels
    z_map = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_map.get(confidence, 2.576)
    p = successes / total
    denominator = 1 + z * z / total
    center = p + z * z / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (center - spread) / denominator


# Promotion gate constants
WILSON_PROMOTE_LOWER = 0.85    # Wilson lower bound must exceed this
WILSON_MIN_SAMPLES = 200       # Minimum shadow samples for promotion
WILSON_CONFIDENCE = 0.99       # 99% confidence interval
# Legacy constants for backward compatibility in tests
LEGACY_AGREEMENT_THRESHOLD = 0.90
LEGACY_MIN_SAMPLES = 50


__all__ = [
    "TierResult",
    "ShadowEntry",
    "TierDef",
    "CascadeRunner",
]

# ---------------------------------------------------------------------------
# Result dataclass — unified across all cascade consumers
# ---------------------------------------------------------------------------

@dataclass
class TierResult:
    """Result from any tier in the cascade.

    This is the common return type. Domain-specific consumers can extend
    or wrap it, but the cascade runner operates on this shape.
    """
    result: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    tier: float = -1          # 0, 0.5, 1.5, 2 etc.
    source: str = ""          # "heuristic", "classifier", "gpt", "scillm"
    latency_ms: float = 0.0
    cached: bool = False
    scope: str = ""
    task: str = ""

    # Classification-specific (optional)
    prediction: str = ""
    probabilities: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict, dropping empty optional fields."""
        d = asdict(self)
        if not d["prediction"]:
            del d["prediction"]
        if not d["probabilities"]:
            del d["probabilities"]
        return d


# ---------------------------------------------------------------------------
# Shadow log entry — standardized schema across all consumers
# ---------------------------------------------------------------------------

@dataclass
class ShadowEntry:
    """Standard shadow mode log entry.

    Written to shadow.jsonl when a local model (classifier or GPT) runs
    alongside the teacher (scillm). Used to measure agreement rate and
    decide when to promote the local model.
    """
    timestamp: str = ""
    task: str = ""
    scope: str = ""
    local_tier: float = -1
    local_source: str = ""
    local_grade: str = ""
    local_confidence: float = 0.0
    teacher_grade: str = ""
    teacher_confidence: float = 1.0
    agreed: bool = False
    input_hash: str = ""
    input_data: dict = field(default_factory=dict)
    teacher_result: dict = field(default_factory=dict)

    # Subgraph quality metrics (optional — populated when graph expansion is available)
    subgraph_qra_count: int = 0
    subgraph_avg_grounding: float = 0.0
    subgraph_vs_baseline_delta: float = 0.0

    # Citation metrics (semantic grading — Embry-OS global pattern)
    qra_citation_count: int = 0
    qra_citations_verified: int = 0
    qra_grounding_avg: float = 0.0
    student_model: str = ""
    teacher_model: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @staticmethod
    def _extract_grade(tier: "TierResult") -> str:
        """Extract a comparable grade string from a TierResult.

        LLM responses use many different keys. Check them all in priority
        order, falling back to stringifying the entire result dict.
        """
        r = tier.result if isinstance(tier.result, dict) else {}
        # Check common grade/label keys in priority order
        for key in ("grade", "teacher_grade", "prediction", "verdict",
                     "assessment", "label", "rating", "status",
                     "satisfied", "answer", "output",
                     "result", "raw", "overall_score", "score"):
            val = r.get(key)
            if val is None:
                continue
            # Handle numeric scores (e.g. overall_score: 7.0)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return str(val)
            # Handle boolean (e.g. satisfied: true)
            if isinstance(val, bool):
                return str(val).lower()
            if isinstance(val, str) and len(val.strip()) < 200:
                return val.strip()
        # Check TierResult.prediction field
        if tier.prediction:
            return tier.prediction
        # Fallback: stringify the whole result if small enough
        if r:
            flat = json.dumps(r, ensure_ascii=False)
            if len(flat) < 200:
                return flat
        return ""

    @classmethod
    def from_results(
        cls,
        task: str,
        scope: str,
        local: TierResult,
        teacher: TierResult,
        input_hash: str = "",
        input_data: dict | None = None,
        subgraph_qra_count: int = 0,
        subgraph_avg_grounding: float = 0.0,
        subgraph_vs_baseline_delta: float = 0.0,
    ) -> "ShadowEntry":
        local_grade = cls._extract_grade(local)
        teacher_grade = cls._extract_grade(teacher)
        agreed = (
            str(local_grade).upper() == str(teacher_grade).upper()
            if local_grade and teacher_grade
            else False
        )
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            task=task,
            scope=scope,
            local_tier=local.tier,
            local_source=local.source,
            local_grade=str(local_grade),
            local_confidence=local.confidence,
            teacher_grade=str(teacher_grade),
            teacher_confidence=teacher.confidence,
            agreed=agreed,
            input_hash=input_hash,
            input_data=input_data or {},
            teacher_result=teacher.result if isinstance(teacher.result, dict) else {},
            subgraph_qra_count=subgraph_qra_count,
            subgraph_avg_grounding=subgraph_avg_grounding,
            subgraph_vs_baseline_delta=subgraph_vs_baseline_delta,
        )


# ---------------------------------------------------------------------------
# Tier definition — what the consumer provides
# ---------------------------------------------------------------------------

@dataclass
class TierDef:
    """Definition of a single tier in the cascade.

    Args:
        tier: Numeric tier level (0, 0.5, 1.5, 2). Controls ordering.
        name: Human-readable name ("heuristic", "classifier", "gpt", "scillm").
        fn: Callable(input_data, **kwargs) → TierResult | None.
            Return TierResult to provide a result.
            Return None to skip this tier (e.g., model not loaded).
            Raise exception to skip with logging.
        threshold: Minimum confidence to accept this tier's result.
            If result.confidence < threshold, escalate to next tier.
            Default 0.0 means any non-None result is accepted.
        is_teacher: If True, this tier is the authoritative teacher.
            Shadow mode compares local results against this tier.
        shadow_mode: If True, this tier records its result but always
            escalates to the teacher for comparison.
    """
    tier: float
    name: str
    fn: Callable[..., Optional[TierResult]]
    threshold: float = 0.0
    is_teacher: bool = False
    shadow_mode: bool = False


# ---------------------------------------------------------------------------
# Cascade Runner — the shared escalation loop
# ---------------------------------------------------------------------------

class CascadeRunner:
    """Configurable multi-tier validation cascade.

    Runs tiers in order (lowest tier number first). Each tier either:
    - Returns a TierResult with confidence >= threshold → accepted, stop
    - Returns a TierResult with confidence < threshold → escalate
    - Returns None → skip this tier, escalate
    - Raises → log error, escalate

    Shadow mode: when a tier has shadow_mode=True, its result is recorded
    but execution continues to the teacher tier. The shadow entry is written
    to shadow_file for agreement tracking.
    """

    def __init__(
        self,
        tiers: List[TierDef],
        shadow_file: Optional[Path] = None,
        metrics_file: Optional[Path] = None,
        drift_sample_rate: float = 0.05,
    ):
        # Sort tiers by tier number (lowest first)
        self.tiers = sorted(tiers, key=lambda t: t.tier)
        self.shadow_file = shadow_file.expanduser() if shadow_file else None
        self.metrics_file = metrics_file.expanduser() if metrics_file else None
        # Post-promotion drift sampling: fraction of promoted-classifier
        # results that still get compared against the teacher (default 5%)
        self.drift_sample_rate = drift_sample_rate

        # Validate: at most one teacher
        teachers = [t for t in self.tiers if t.is_teacher]
        if len(teachers) > 1:
            raise ValueError(f"At most one tier can be is_teacher, got {len(teachers)}")

    def run(
        self,
        input_data: Any,
        task: str = "",
        scope: str = "",
        input_hash: str = "",
        **kwargs,
    ) -> TierResult:
        """Execute the cascade.

        Args:
            input_data: Domain-specific input passed to each tier function.
            task: Task name for logging and registry lookup.
            scope: Scope/persona for context injection.
            input_hash: Optional hash of input for shadow dedup.
            **kwargs: Additional kwargs passed to tier functions.

        Returns:
            TierResult from the first tier that accepts, or the last tier.
        """
        start = time.time()
        shadow_local: Optional[TierResult] = None  # Best local result for shadow
        best_below_threshold: Optional[TierResult] = None  # Best result that didn't meet threshold

        for tier_def in self.tiers:
            try:
                result = tier_def.fn(input_data, task=task, scope=scope, **kwargs)
            except Exception as e:
                logger.debug(f"Tier {tier_def.tier} ({tier_def.name}) failed: {e}")
                continue

            if result is None:
                continue

            # Fill in metadata
            result.task = task
            result.scope = scope
            result.tier = tier_def.tier
            result.source = result.source or tier_def.name
            result.latency_ms = (time.time() - start) * 1000

            # Shadow mode: record local result but keep escalating
            if tier_def.shadow_mode and result.confidence >= tier_def.threshold:
                shadow_local = result
                logger.debug(
                    f"[shadow] Tier {tier_def.tier} ({tier_def.name}) would return: "
                    f"confidence={result.confidence:.3f}"
                )
                continue

            # Check threshold
            if result.confidence >= tier_def.threshold:
                # Teacher tier + shadow comparison
                if tier_def.is_teacher and shadow_local is not None:
                    self._log_shadow(task, scope, shadow_local, result, input_hash, input_data)

                # Post-promotion drift sampling: even for promoted classifiers,
                # randomly sample a fraction of queries and continue to teacher
                # for ongoing agreement tracking. This enables drift detection
                # without impacting normal latency for most queries.
                if (
                    not tier_def.is_teacher
                    and not tier_def.shadow_mode
                    and self.drift_sample_rate > 0
                    and shadow_local is None
                    and random.random() < self.drift_sample_rate
                ):
                    shadow_local = result
                    logger.debug(
                        f"[drift-sample] Tier {tier_def.tier} ({tier_def.name}) "
                        f"sampled for drift check, continuing to teacher"
                    )
                    continue

                self._log_metric(result)
                return result

            # Below threshold — track best result and escalate
            if best_below_threshold is None or result.confidence > best_below_threshold.confidence:
                best_below_threshold = result
            logger.debug(
                f"Tier {tier_def.tier} ({tier_def.name}) confidence "
                f"{result.confidence:.3f} < {tier_def.threshold}, escalating"
            )

        # Exhausted all tiers. Return best available result in priority order:
        # 1. shadow_local (classifier that passed threshold in shadow mode)
        # 2. best_below_threshold (classifier with some confidence, better than nothing)
        # 3. empty fallback
        if shadow_local is not None:
            logger.debug(
                f"[shadow] Teacher unavailable for task={task}, "
                f"skipping shadow comparison (local_source={shadow_local.source})"
            )
            shadow_local.latency_ms = (time.time() - start) * 1000
            self._log_metric(shadow_local)
            return shadow_local

        if best_below_threshold is not None:
            logger.debug(
                f"All tiers exhausted for task={task}, returning best below-threshold "
                f"result: {best_below_threshold.source} confidence={best_below_threshold.confidence:.3f}"
            )
            best_below_threshold.latency_ms = (time.time() - start) * 1000
            self._log_metric(best_below_threshold)
            return best_below_threshold

        fallback = TierResult(
            task=task, scope=scope,
            latency_ms=(time.time() - start) * 1000,
            source="fallback",
        )
        self._log_metric(fallback)
        return fallback

    def _log_shadow(
        self,
        task: str,
        scope: str,
        local: TierResult,
        teacher: TierResult,
        input_hash: str,
        input_data: Any = None,
    ) -> None:
        """Write shadow mode comparison to shadow.jsonl."""
        if not self.shadow_file:
            return

        # Auto-compute subgraph metrics from input_data QRAs when available
        subgraph_qra_count = 0
        subgraph_avg_grounding = 0.0
        subgraph_vs_baseline_delta = 0.0
        if isinstance(input_data, dict) and "qras" in input_data:
            qras = input_data["qras"]
            if isinstance(qras, list):
                graph_qras = [q for q in qras if isinstance(q, dict) and q.get('_source') == 'subgraph_expansion']
                base_qras = [q for q in qras if isinstance(q, dict) and q.get('_source') != 'subgraph_expansion']
                if graph_qras:
                    subgraph_qra_count = len(graph_qras)
                    subgraph_avg_grounding = sum(q.get('grounding_score', 0) for q in graph_qras) / len(graph_qras)
                    base_avg = (
                        sum(q.get('grounding_score', 0) for q in base_qras) / len(base_qras)
                        if base_qras else 0.0
                    )
                    subgraph_vs_baseline_delta = subgraph_avg_grounding - base_avg

        entry = ShadowEntry.from_results(
            task=task, scope=scope,
            local=local, teacher=teacher,
            input_hash=input_hash,
            input_data=(
                input_data if isinstance(input_data, dict)
                else {"text": str(input_data)} if input_data
                else {}
            ),
            subgraph_qra_count=subgraph_qra_count,
            subgraph_avg_grounding=subgraph_avg_grounding,
            subgraph_vs_baseline_delta=subgraph_vs_baseline_delta,
        )

        try:
            self.shadow_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.shadow_file, "a") as f:
                f.write(entry.to_json() + "\n")

            if entry.agreed:
                logger.debug(
                    f"[shadow] AGREE on {task}: "
                    f"grade={entry.local_grade} (confidence={entry.local_confidence:.3f})"
                )
            else:
                logger.info(
                    f"[shadow] DISAGREE on {task}: "
                    f"local={entry.local_grade} vs teacher={entry.teacher_grade} "
                    f"(confidence={entry.local_confidence:.3f})"
                )
        except Exception as e:
            logger.debug(f"Failed to log shadow entry: {e}")

    def _log_metric(self, result: TierResult) -> None:
        """Append metric entry to metrics.jsonl."""
        if not self.metrics_file:
            return

        try:
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "task": result.task,
                "scope": result.scope,
                "tier": result.tier,
                "source": result.source,
                "confidence": result.confidence,
                "latency_ms": round(result.latency_ms, 2),
                "cached": result.cached,
            }
            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Shadow report utility
    # ------------------------------------------------------------------

    def shadow_report(
        self,
        task: str = "",
        hours: int = 24,
    ) -> Dict[str, Any]:
        """Compute shadow agreement stats from shadow.jsonl.

        Only counts entries that are real shadow comparisons (both local_grade
        and teacher_grade are non-empty).  Teacher-only priming entries
        (entry_type='teacher_label' or empty local_grade) are excluded — they
        are training data, not agreement evidence.

        Returns dict with total, agree, disagree, agreement_rate, status,
        plus teacher_labels (count of teacher-only entries available for
        training).
        """
        if not self.shadow_file or not self.shadow_file.exists():
            return {"total": 0, "agree": 0, "disagree": 0, "agreement_rate": 0.0,
                    "status": "no_data", "teacher_labels": 0, "skipped_incomplete": 0}

        cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
        agree = disagree = 0
        teacher_labels = 0
        skipped_incomplete = 0

        for line in self.shadow_file.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if task and entry.get("task") != task:
                    continue
                ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
                if ts < cutoff:
                    continue

                # Teacher-only priming entries are training data, not comparisons
                if entry.get("entry_type") == "teacher_label":
                    teacher_labels += 1
                    continue

                # Require both grades to be non-empty for a valid comparison
                local_grade = str(entry.get("local_grade", "")).strip()
                teacher_grade = str(entry.get("teacher_grade", "")).strip()
                if not local_grade or not teacher_grade:
                    skipped_incomplete += 1
                    teacher_labels += 1 if teacher_grade else 0
                    continue

                if entry.get("agreed"):
                    agree += 1
                else:
                    disagree += 1
            except (json.JSONDecodeError, KeyError):
                continue

        total = agree + disagree
        rate = agree / total if total > 0 else 0.0

        # Wilson score confidence interval for promotion decisions
        w_lower = wilson_score_lower(agree, total, WILSON_CONFIDENCE)
        w_upper = 1.0  # upper bound less critical for promotion gate
        if total > 0:
            z = 2.576  # 99% CI
            p = agree / total
            denom = 1 + z * z / total
            center = p + z * z / (2 * total)
            spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
            w_upper = min(1.0, (center + spread) / denom)

        # Promotion: use Wilson lower bound instead of raw agreement rate
        promotable = (w_lower >= WILSON_PROMOTE_LOWER and total >= WILSON_MIN_SAMPLES)
        status = "ready" if promotable else "learning" if rate >= 0.70 else "early"

        return {
            "total": total,
            "agree": agree,
            "disagree": disagree,
            "agreement_rate": round(rate, 4),
            "wilson_lower": round(w_lower, 4),
            "confidence_interval": (round(w_lower, 4), round(w_upper, 4)),
            "promotable": promotable,
            "status": status,
            "teacher_labels": teacher_labels,
            "skipped_incomplete": skipped_incomplete,
        }
