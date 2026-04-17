"""Arxiv benchmark distributions for empirically-grounded peer review.

Loads structural metrics from a corpus of arxiv papers and computes
percentile distributions (p25, p50, p75). These distributions replace
hardcoded thresholds in Tier 0 heuristics and exemplar comparison,
ensuring that scoring is calibrated against real venue norms.

The benchmark corpus lives at data/arxiv_benchmarks.json and grows
over time via /dogpile → /arxiv learn → benchmark ingestion.

Usage:
    benchmarks = ArxivBenchmarks.load()
    report = benchmarks.score_paper(paper_metrics)
    # report.percentile_ranks["refs_per_page"] = 0.45  (below median)
    # report.flags = ["refs_per_page below p25"]
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger


DATA_DIR = Path(__file__).parent.parent / "data"
BENCHMARKS_FILE = DATA_DIR / "arxiv_benchmarks.json"


@dataclass
class Distribution:
    """Percentile distribution for a single metric."""

    name: str
    values: list[float] = field(default_factory=list)
    p25: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    mean: float = 0.0
    std: float = 0.0
    n: int = 0

    def compute(self) -> None:
        if not self.values:
            return
        self.n = len(self.values)
        sorted_vals = sorted(self.values)
        self.p25 = _percentile(sorted_vals, 25)
        self.p50 = _percentile(sorted_vals, 50)
        self.p75 = _percentile(sorted_vals, 75)
        self.mean = statistics.mean(self.values)
        self.std = statistics.stdev(self.values) if len(self.values) > 1 else 0.0

    def percentile_rank(self, value: float) -> float:
        """Where does `value` fall in the distribution? Returns 0.0-1.0."""
        if not self.values:
            return 0.5
        below = sum(1 for v in self.values if v < value)
        equal = sum(1 for v in self.values if v == value)
        return (below + equal * 0.5) / len(self.values)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "n": self.n,
            "p25": round(self.p25, 3),
            "p50": round(self.p50, 3),
            "p75": round(self.p75, 3),
            "mean": round(self.mean, 3),
            "std": round(self.std, 3),
        }


@dataclass
class BenchmarkReport:
    """Scoring report for a paper against the benchmark corpus."""

    paper_id: str = ""
    corpus_size: int = 0
    percentile_ranks: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    distributions: dict[str, dict] = field(default_factory=dict)
    overall_structural_score: float = 0.0  # 0-10 composite

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "corpus_size": self.corpus_size,
            "percentile_ranks": {k: round(v, 3) for k, v in self.percentile_ranks.items()},
            "flags": self.flags,
            "distributions": self.distributions,
            "overall_structural_score": round(self.overall_structural_score, 2),
        }


class ArxivBenchmarks:
    """Empirical arxiv benchmark distributions.

    Loads a corpus of arxiv paper metrics and computes distributions
    for key structural features. Papers are scored by percentile rank
    against these distributions.
    """

    METRICS = [
        "words", "est_pages", "equations", "figures", "tables",
        "refs", "footnotes", "eq_per_pg", "fig_per_pg", "ref_per_pg",
    ]

    def __init__(self, corpus: list[dict]):
        self.corpus = corpus
        self.distributions: dict[str, Distribution] = {}
        self._compute_distributions()

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ArxivBenchmarks":
        """Load benchmarks from the corpus file."""
        benchmark_path = path or BENCHMARKS_FILE
        if not benchmark_path.exists():
            logger.warning(f"No benchmark corpus at {benchmark_path}")
            return cls([])

        corpus = json.loads(benchmark_path.read_text())
        logger.info(f"Loaded {len(corpus)} arxiv benchmarks from {benchmark_path}")
        return cls(corpus)

    def _compute_distributions(self) -> None:
        """Compute percentile distributions for all metrics."""
        for metric in self.METRICS:
            values = [p.get(metric, 0) for p in self.corpus if metric in p]
            dist = Distribution(name=metric, values=values)
            dist.compute()
            self.distributions[metric] = dist

    def score_paper(
        self,
        paper_metrics: dict,
        paper_id: str = "",
    ) -> BenchmarkReport:
        """Score a paper's structural metrics against the corpus.

        Args:
            paper_metrics: Dict with keys matching METRICS (words, figures, etc.)
            paper_id: Identifier for the paper being scored.

        Returns:
            BenchmarkReport with percentile ranks and flags.
        """
        report = BenchmarkReport(
            paper_id=paper_id,
            corpus_size=len(self.corpus),
        )

        if not self.corpus:
            report.flags.append("No benchmark corpus loaded — using defaults")
            report.overall_structural_score = 5.0
            return report

        # Compute percentile ranks for each metric
        scores = []
        for metric in self.METRICS:
            if metric not in paper_metrics:
                continue
            dist = self.distributions.get(metric)
            if not dist or dist.n == 0:
                continue

            value = paper_metrics[metric]
            rank = dist.percentile_rank(value)
            report.percentile_ranks[metric] = rank
            report.distributions[metric] = dist.to_dict()

            # Flag metrics below p25
            if rank < 0.25:
                report.flags.append(
                    f"{metric}={value:.2f} below p25 ({dist.p25:.2f}) — "
                    f"percentile rank {rank:.0%}"
                )

            # Flag metrics above p75 (positive signal)
            if rank > 0.75:
                report.flags.append(
                    f"{metric}={value:.2f} above p75 ({dist.p75:.2f}) — "
                    f"strong ({rank:.0%} percentile)"
                )

            # Use rank as a 0-10 score contribution for structural metrics
            if metric in ("eq_per_pg", "fig_per_pg", "ref_per_pg", "footnotes"):
                scores.append(rank * 10)

        # Overall structural score: average of per-page metric ranks
        if scores:
            report.overall_structural_score = sum(scores) / len(scores)
        else:
            report.overall_structural_score = 5.0

        return report

    def get_thresholds(self) -> dict[str, dict[str, float]]:
        """Return empirical thresholds for Tier 0 heuristics.

        Returns dict mapping metric names to {min, target, max} values
        derived from the corpus p25/p50/p75.
        """
        thresholds = {}
        for metric, dist in self.distributions.items():
            if dist.n == 0:
                continue
            thresholds[metric] = {
                "min": dist.p25,
                "target": dist.p50,
                "max": dist.p75,
                "n": dist.n,
            }
        return thresholds

    def comparison_table(self, paper_metrics: dict) -> list[dict]:
        """Generate a comparison table row for each metric.

        Returns list of dicts with: metric, paper_value, p25, p50, p75, rank.
        """
        rows = []
        for metric in self.METRICS:
            dist = self.distributions.get(metric)
            if not dist or dist.n == 0:
                continue
            value = paper_metrics.get(metric, 0)
            rank = dist.percentile_rank(value)
            rows.append({
                "metric": metric,
                "paper_value": value,
                "p25": round(dist.p25, 2),
                "p50": round(dist.p50, 2),
                "p75": round(dist.p75, 2),
                "rank": round(rank, 3),
                "status": "strong" if rank >= 0.75 else "ok" if rank >= 0.25 else "weak",
            })
        return rows

    def corpus_papers_table(self) -> list[dict]:
        """Return corpus papers with metadata for display."""
        rows = []
        for p in self.corpus:
            rows.append({
                "id": p.get("id", ""),
                "title": p.get("title", "Unknown"),
                "senior_author": p.get("senior_author", ""),
                "expertise": p.get("expertise", ""),
                "venue": p.get("venue", ""),
                "pages": p.get("est_pages", 0),
            })
        return rows

    def select_reviewer_authors(self, n: int = 3) -> list[dict]:
        """Select the n most prominent corpus authors as reviewer personas.

        Picks papers with senior_author and expertise fields, preferring
        top-venue papers (NeurIPS, ICML, ICLR, ACL) and diverse expertise.
        """
        candidates = [
            p for p in self.corpus
            if p.get("senior_author") and p.get("expertise")
        ]
        # Rank by venue prestige, then page count (larger = more thorough)
        venue_rank = {"NeurIPS": 5, "ICML": 5, "ICLR": 5, "ACL": 4, "arXiv": 2}
        candidates.sort(key=lambda p: (
            -max((v for k, v in venue_rank.items() if k in p.get("venue", "")), default=1),
            -p.get("est_pages", 0),
        ))
        # Deduplicate by expertise area (take first per unique expertise)
        seen_expertise: set[str] = set()
        selected: list[dict] = []
        for p in candidates:
            exp_key = p["expertise"].split(",")[0].strip()
            if exp_key not in seen_expertise:
                seen_expertise.add(exp_key)
                selected.append(p)
            if len(selected) >= n:
                break
        return selected

    def to_dict(self) -> dict:
        return {
            "corpus_size": len(self.corpus),
            "distributions": {k: v.to_dict() for k, v in self.distributions.items()},
        }


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute percentile using linear interpolation."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (n - 1) * pct / 100
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_values[-1]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])
