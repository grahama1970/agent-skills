"""Co-evolutionary feedback logging for Shadow-LEGO.

Tracks which classifier seeds produce the richest subgraphs when
expanded through LEGO-GraphRAG. This drives classifier promotion:
classifiers that produce richer subgraphs (more QRAs, higher grounding)
get promoted, not just those with higher entity-level accuracy.

Schema per JSONL line (SubgraphFeedbackEntry):
    timestamp           : ISO-8601 UTC timestamp
    classifier_name     : Registry key of the classifier that produced seeds
    seeds               : List of entity/seed strings sent to graph expansion
    classifier_confidence : Confidence score from the classifier (0.0-1.0)
    subgraph_qra_count  : Number of QRAs retrieved via classifier seeds
    avg_grounding       : Mean grounding score of classifier-seeded QRAs
    baseline_qra_count  : Number of QRAs retrieved via keyword baseline
    baseline_grounding  : Mean grounding score of keyword-baseline QRAs
    quality_delta       : subgraph avg_grounding - baseline_grounding
    count_delta         : subgraph qra_count - baseline qra_count
    richer              : True if classifier seeds outperformed baseline
    scope               : Optional scope tag (e.g. "brandon_bailey")
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .paths import SUBGRAPH_FEEDBACK_FILE

__all__ = [
    "SubgraphFeedbackEntry",
    "log_subgraph_feedback",
    "summarize_subgraph_feedback",
]


@dataclass
class SubgraphFeedbackEntry:
    """One co-evolutionary feedback observation.

    Records how well a classifier's entity seeds performed when expanded
    through LEGO-GraphRAG (k-hop BFS) compared to a keyword baseline.
    """

    timestamp: str = ""
    classifier_name: str = ""
    seeds: List[str] = field(default_factory=list)
    classifier_confidence: float = 0.0
    subgraph_qra_count: int = 0
    avg_grounding: float = 0.0
    baseline_qra_count: int = 0
    baseline_grounding: float = 0.0
    quality_delta: float = 0.0
    count_delta: int = 0
    richer: bool = False
    scope: str = ""


def log_subgraph_feedback(
    classifier_name: str,
    seeds: List[str],
    subgraph_qra_count: int,
    avg_grounding: float,
    baseline_qra_count: int,
    baseline_grounding: float,
    confidence: float,
    *,
    scope: str = "",
    feedback_file: Path | None = None,
) -> SubgraphFeedbackEntry:
    """Append a co-evolutionary feedback observation.

    Call this after every shadow-mode query where both classifier-seeded and
    keyword-baseline subgraph expansions were performed.

    Args:
        classifier_name: Registry key of the classifier.
        seeds: Entity/seed strings produced by the classifier.
        subgraph_qra_count: QRAs retrieved using classifier seeds.
        avg_grounding: Mean grounding score of classifier-seeded QRAs.
        baseline_qra_count: QRAs retrieved using keyword baseline.
        baseline_grounding: Mean grounding score of keyword-baseline QRAs.
        confidence: Classifier confidence score (0.0-1.0).
        scope: Optional domain scope tag.
        feedback_file: Override default feedback file path.

    Returns:
        The SubgraphFeedbackEntry that was logged.
    """
    out_file = feedback_file or SUBGRAPH_FEEDBACK_FILE
    quality_delta = avg_grounding - baseline_grounding
    count_delta = subgraph_qra_count - baseline_qra_count

    entry = SubgraphFeedbackEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        classifier_name=classifier_name,
        seeds=list(seeds),
        classifier_confidence=confidence,
        subgraph_qra_count=subgraph_qra_count,
        avg_grounding=avg_grounding,
        baseline_qra_count=baseline_qra_count,
        baseline_grounding=baseline_grounding,
        quality_delta=quality_delta,
        count_delta=count_delta,
        richer=(quality_delta > 0 or (quality_delta == 0 and count_delta > 0)),
        scope=scope,
    )

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "a") as f:
        f.write(json.dumps(asdict(entry), default=str) + "\n")

    return entry


def summarize_subgraph_feedback(
    min_samples: int = 10,
    feedback_file: Path | None = None,
) -> Dict[str, Any]:
    """Summarize co-evolutionary feedback per classifier.

    Reads the feedback JSONL and computes per-classifier stats:
    - Total observations, win rate, mean quality/count deltas
    - Confidence-quality correlation (high vs low confidence bins)
    - Promotion recommendation based on win rate

    Thresholds:
        win_rate >= 0.70  ->  "promote"
        win_rate >= 0.50  ->  "shadow"
        win_rate <  0.50  ->  "retrain"

    Args:
        min_samples: Minimum observations before making a recommendation.
        feedback_file: Override default feedback file path.

    Returns:
        Dict keyed by classifier_name with stats and recommendation.
    """
    src = feedback_file or SUBGRAPH_FEEDBACK_FILE
    if not src.exists():
        return {}

    buckets: Dict[str, List[Dict[str, Any]]] = {}
    with open(src) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = entry.get("classifier_name", "unknown")
            buckets.setdefault(name, []).append(entry)

    summaries: Dict[str, Any] = {}
    for name, entries in buckets.items():
        n = len(entries)
        wins = sum(1 for e in entries if e.get("richer", False))
        win_rate = wins / max(1, n)
        mean_quality_delta = (
            sum(e.get("quality_delta", 0.0) for e in entries) / max(1, n)
        )
        mean_count_delta = sum(e.get("count_delta", 0) for e in entries) / max(1, n)
        mean_confidence = (
            sum(e.get("classifier_confidence", 0.0) for e in entries) / max(1, n)
        )

        high_conf = [e for e in entries if e.get("classifier_confidence", 0) >= 0.8]
        low_conf = [e for e in entries if e.get("classifier_confidence", 0) < 0.8]
        high_conf_delta = (
            sum(e.get("quality_delta", 0.0) for e in high_conf) / max(1, len(high_conf))
            if high_conf
            else 0.0
        )
        low_conf_delta = (
            sum(e.get("quality_delta", 0.0) for e in low_conf) / max(1, len(low_conf))
            if low_conf
            else 0.0
        )

        if n < min_samples:
            recommendation = "insufficient_data"
        elif win_rate >= 0.70:
            recommendation = "promote"
        elif win_rate >= 0.50:
            recommendation = "shadow"
        else:
            recommendation = "retrain"

        summaries[name] = {
            "total_observations": n,
            "wins": wins,
            "win_rate": round(win_rate, 4),
            "mean_quality_delta": round(mean_quality_delta, 4),
            "mean_count_delta": round(mean_count_delta, 2),
            "mean_confidence": round(mean_confidence, 4),
            "high_confidence_quality_delta": round(high_conf_delta, 4),
            "low_confidence_quality_delta": round(low_conf_delta, 4),
            "confidence_quality_correlation": round(high_conf_delta - low_conf_delta, 4),
            "recommendation": recommendation,
        }

    return summaries
