#!/usr/bin/env python3
"""Convergence tracking via /memory queries.

Replaces counter-based convergence tracking with score-trajectory queries
against lessons stored by inline_reviewer.py. Uses ONLY the authorized
/memory APIs (MemoryClient.recall()) — never get_db() directly.

recall() provides BM25 + semantic + multi-hop graph traversal.
Neither BM25 nor semantic returns chronological order, so we always
fetch 4x the window, sort by updated_at timestamp, and take the most
recent window_size entries.

Usage:
    from convergence_tracker import get_convergence_status
    status = get_convergence_status(corpus_root)
    print(status["trend"])  # "improving" | "plateau" | "degrading"
"""
from __future__ import annotations

import json
import os
from loguru import logger
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# sys.path setup
# ---------------------------------------------------------------------------
import sys

_THIS_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _THIS_DIR.parent  # pi-mono/.pi/skills
_MEMORY_SRC = Path(
    os.environ.get("MEMORY_ROOT", str(Path.home() / "workspace" / "experiments" / "memory"))
) / "src"

for _p in [str(_THIS_DIR), str(_SKILLS_DIR), str(_MEMORY_SRC)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# RULE: NEVER use get_db() directly. Only MemoryClient.recall() for queries.
# recall() provides BM25 + semantic + multi-hop graph traversal via /taxonomy.
try:
    from graph_memory.api import MemoryClient
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False

# Subprocess fallback when graph_memory isn't importable (e.g. supervisor uv env
# lacks python-arango). Shells out to memory skill's ./run.sh recall which uses
# its own uv environment with all dependencies.
import subprocess as _subprocess

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)


class _HttpxMemoryClient:
    """Memory client using httpx to embry-memory Unix socket."""

    def __init__(self, scope: str = ""):
        self.scope = scope

    def recall(self, query: str, k: int = 10) -> Dict[str, Any]:
        try:
            import httpx
            transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
            with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                body: dict = {"q": query, "k": k}
                if self.scope:
                    body["scope"] = self.scope
                resp = client.post("/recall", json=body)
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"convergence_tracker httpx recall HTTP {resp.status_code}")
                return {"found": False, "items": []}
        except Exception as exc:
            logger.warning(f"convergence_tracker httpx recall error: {exc}")
            return {"found": False, "items": []}


if not HAS_MEMORY:
    MemoryClient = _HttpxMemoryClient  # type: ignore[misc]
    HAS_MEMORY = True
    logger.info("Using httpx MemoryClient (Unix socket)")

try:
    from annealing import ANNEALING_SCHEDULE
    HAS_ANNEALING = True
except ImportError:
    HAS_ANNEALING = False

# logger provided by loguru import above

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SCORE_RE = re.compile(r"score=(\d+\.\d+)")
_GRADE_RE = re.compile(r"grade=(\S+)")
_VERDICT_RE = re.compile(r"verdict=(\S+)")
_SECTOR_RE = re.compile(r"pdf_assessment\s+\w+\s+(\S+)\s+score=")

# Trend detection thresholds
_IMPROVING_SLOPE_THRESHOLD = 0.005   # Slope > 0.5% per review = improving
_DEGRADING_SLOPE_THRESHOLD = -0.005  # Slope < -0.5% per review = degrading
_MIN_REVIEWS_FOR_TREND = 5           # Need at least 5 reviews to compute trend


def _parse_assessment(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse a search result item into structured assessment data.

    Extracts score, grade, verdict, sector from the problem text,
    and full dimension data from the JSON solution field.
    """
    problem = item.get("problem", "")
    if not problem.startswith("pdf_assessment"):
        return None

    score_m = _SCORE_RE.search(problem)
    grade_m = _GRADE_RE.search(problem)
    verdict_m = _VERDICT_RE.search(problem)
    sector_m = _SECTOR_RE.search(problem)

    if not score_m:
        return None

    result = {
        "_key": item.get("_key", ""),
        "score": float(score_m.group(1)),
        "grade": grade_m.group(1) if grade_m else "?",
        "verdict": verdict_m.group(1) if verdict_m else "?",
        "sector": sector_m.group(1) if sector_m else "unknown",
        "updated_at": int(item.get("updated_at", 0)),
        "tags": item.get("tags", []),
    }

    # Try to extract dimension scores from JSON solution
    solution = item.get("solution", "")
    if solution and solution.startswith("{"):
        try:
            sol_data = json.loads(solution)
            if "dimensions" in sol_data:
                result["dimensions"] = {
                    name: d.get("score", 0.0)
                    for name, d in sol_data["dimensions"].items()
                }
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    return result


def _compute_slope(scores: List[float]) -> float:
    """Compute linear regression slope over a list of scores.

    Uses simple least-squares: slope = Σ((x-x̄)(y-ȳ)) / Σ((x-x̄)²)
    where x is the index (0, 1, 2, ...) and y is the score.
    """
    n = len(scores)
    if n < 2:
        return 0.0

    x_mean = (n - 1) / 2.0
    y_mean = sum(scores) / n

    numerator = sum((i - x_mean) * (s - y_mean) for i, s in enumerate(scores))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 0.0

    return numerator / denominator


def _mann_kendall(scores: List[float]) -> Dict[str, Any]:
    """Mann-Kendall trend test for monotonic trends.

    More robust than linear regression for non-normal data.
    Returns S statistic, normalized tau, and p-value approximation.
    """
    import math

    n = len(scores)
    if n < 4:
        return {"S": 0, "tau": 0.0, "p_value": 1.0, "significant": False}

    # Compute S statistic: sum of sign(x_j - x_i) for all j > i
    s_stat = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = scores[j] - scores[i]
            if diff > 0:
                s_stat += 1
            elif diff < 0:
                s_stat -= 1

    # Kendall's tau
    n_pairs = n * (n - 1) / 2
    tau = s_stat / n_pairs if n_pairs > 0 else 0.0

    # Variance of S (accounting for ties)
    var_s = n * (n - 1) * (2 * n + 5) / 18.0

    # Tie correction
    from collections import Counter
    tie_groups = Counter(scores)
    for count in tie_groups.values():
        if count > 1:
            var_s -= count * (count - 1) * (2 * count + 5) / 18.0

    # Z-score and p-value approximation
    if var_s <= 0:
        return {"S": s_stat, "tau": tau, "p_value": 1.0, "significant": False}

    std_s = math.sqrt(var_s)
    if s_stat > 0:
        z = (s_stat - 1) / std_s
    elif s_stat < 0:
        z = (s_stat + 1) / std_s
    else:
        z = 0.0

    # Two-tailed p-value using normal approximation
    p_value = 2.0 * (1.0 - _norm_cdf(abs(z)))

    return {
        "S": s_stat,
        "tau": round(tau, 4),
        "p_value": round(p_value, 4),
        "z": round(z, 4),
        "significant": p_value < 0.05,
    }


def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    import math
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _confidence_interval(scores: List[float]) -> Dict[str, float]:
    """Compute 95% confidence interval for the mean score."""
    import math

    n = len(scores)
    if n < 2:
        mean = scores[0] if scores else 0.0
        return {"mean": mean, "ci_lower": mean, "ci_upper": mean, "std": 0.0}

    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / (n - 1)
    std = math.sqrt(variance)
    # t-distribution approximation: use 1.96 for large samples, 2.0 for small
    t_val = 2.0 if n < 30 else 1.96
    margin = t_val * std / math.sqrt(n)

    return {
        "mean": round(mean, 4),
        "ci_lower": round(max(0.0, mean - margin), 4),
        "ci_upper": round(min(1.0, mean + margin), 4),
        "std": round(std, 4),
    }


def _classify_trend(slope: float, n_reviews: int) -> str:
    """Classify trend based on slope and sample size."""
    if n_reviews < _MIN_REVIEWS_FOR_TREND:
        return "insufficient_data"
    if slope > _IMPROVING_SLOPE_THRESHOLD:
        return "improving"
    elif slope < _DEGRADING_SLOPE_THRESHOLD:
        return "degrading"
    else:
        return "plateau"


def _get_phase(coverage_pct: float) -> str:
    """Get the current annealing phase name from coverage percentage."""
    if not HAS_ANNEALING:
        if coverage_pct >= 95:
            return "Certification"
        elif coverage_pct >= 90:
            return "Refinement"
        elif coverage_pct >= 75:
            return "Late Growth"
        elif coverage_pct >= 50:
            return "Mid Growth"
        elif coverage_pct >= 20:
            return "Early Growth"
        return "Bootstrap"

    for (lo, hi), config in ANNEALING_SCHEDULE.items():
        if lo <= coverage_pct < hi:
            return config.get("phase_name", f"{lo}-{hi}%")
    # Above all ranges = Certification
    return "Certification"


def _estimate_coverage(corpus_root: Path) -> float:
    """Estimate corpus coverage from disk (profile.json count / total PDFs).

    This is a lightweight disk scan — no ArangoDB needed.
    """
    results_dir = corpus_root / "results"
    if not results_dir.exists():
        return 0.0

    # Count profiles (extracted PDFs)
    profile_count = 0
    for profile_dir in results_dir.iterdir():
        if profile_dir.is_dir():
            profile_json = profile_dir / "00_profile_detector" / "profile.json"
            if profile_json.exists():
                profile_count += 1

    # Count total PDFs in corpus
    pdf_count = 0
    for ext in ("*.pdf", "*.PDF"):
        pdf_count += len(list(corpus_root.rglob(ext)))

    if pdf_count == 0:
        return 0.0

    return min(100.0, (profile_count / pdf_count) * 100.0)


def get_convergence_status(
    corpus_root: Path,
    window_size: int = 50,
) -> Dict[str, Any]:
    """Query /memory for convergence status based on score trajectory.

    Uses search() to find recent PDF assessments stored by inline_reviewer,
    computes trend from score trajectory, and breaks down by sector/dimension.

    Args:
        corpus_root: Root of the corpus directory (for coverage estimation)
        window_size: Number of recent reviews to analyze (default: 50)

    Returns:
        {
            "trend": "improving"|"plateau"|"degrading"|"insufficient_data",
            "avg_score": float,
            "score_trajectory": list[float],  # oldest to newest
            "phase": str,
            "coverage_pct": float,
            "reviews_total": int,
            "slope": float,
            "sectors": dict[str, {"trend": str, "avg_score": float, "count": int}],
            "dimensions": dict[str, {"trend": str, "avg_score": float}],
            "verdict_distribution": dict[str, int],
            "grade_distribution": dict[str, int],
        }
    """
    empty = {
        "trend": "insufficient_data",
        "avg_score": 0.0,
        "score_trajectory": [],
        "phase": "Bootstrap",
        "coverage_pct": 0.0,
        "reviews_total": 0,
        "slope": 0.0,
        "sectors": {},
        "dimensions": {},
        "verdict_distribution": {},
        "grade_distribution": {},
    }

    if not HAS_MEMORY:
        logger.warning("graph_memory not available — cannot query convergence")
        return empty

    # Fetch assessments from /memory via recall() — BM25 + semantic + multi-hop
    # Neither BM25 nor semantic ranking returns chronological order.
    # Request 4x the window to get a broader pool, then sort by timestamp
    # and take the most recent window_size for trend computation.
    # NOTE: memory service /recall endpoint caps k at ~50-99.  k>=100 returns
    # 422 Unprocessable Entity.  Cap at 50 to stay within service limits.
    fetch_k = min(window_size * 4, 50)
    try:
        client = MemoryClient(scope="extractor")
        search_result = client.recall(
            "pdf_assessment extractor extraction quality review scores",
            k=fetch_k,
        )
    except Exception as e:
        logger.error(f"recall() failed: {e}")
        return empty

    items = search_result.get("items", [])
    if not items:
        return empty

    # Parse assessments
    assessments = []
    for item in items:
        parsed = _parse_assessment(item)
        if parsed:
            assessments.append(parsed)

    if not assessments:
        return empty

    # Deduplicate by PDF hash: when a FAIL-tagged doc gets re-assessed,
    # both old and new assessments exist in /memory.  Keep only the most
    # recent assessment per PDF hash prefix (8-char tag).
    _seen_hashes: Dict[str, Dict[str, Any]] = {}
    for a in assessments:
        hash_prefix = next(
            (t for t in a.get("tags", [])
             if len(t) == 8 and t not in ("pdf_assessment", a.get("grade", ""), a.get("verdict", ""), a.get("sector", ""))),
            None,
        )
        key = hash_prefix if hash_prefix else a["_key"]
        existing = _seen_hashes.get(key)
        if existing is None or a["updated_at"] > existing["updated_at"]:
            _seen_hashes[key] = a
    assessments = list(_seen_hashes.values())

    # Sort by updated_at (newest first) to select the most recent reviews
    assessments.sort(key=lambda a: a["updated_at"], reverse=True)
    total_available = len(assessments)
    # Take only the window_size most recent, then reverse to oldest-first
    # for trajectory computation (linear regression expects chronological order)
    assessments = assessments[:window_size]
    if total_available > window_size:
        logger.info(
            f"convergence window truncated: {total_available} assessments available, "
            f"using most recent {window_size} for trend computation"
        )
    assessments.reverse()

    # Compute coverage
    coverage_pct = _estimate_coverage(corpus_root)
    phase = _get_phase(coverage_pct)

    # Overall score trajectory and trend
    scores = [a["score"] for a in assessments]
    slope = _compute_slope(scores)
    trend = _classify_trend(slope, len(scores))
    avg_score = sum(scores) / len(scores) if scores else 0.0

    # Per-sector analysis
    sectors: Dict[str, List[float]] = {}
    for a in assessments:
        sector = a["sector"]
        if sector not in sectors:
            sectors[sector] = []
        sectors[sector].append(a["score"])

    sector_stats = {}
    for sector, sector_scores in sectors.items():
        s_slope = _compute_slope(sector_scores)
        sector_stats[sector] = {
            "trend": _classify_trend(s_slope, len(sector_scores)),
            "avg_score": sum(sector_scores) / len(sector_scores),
            "count": len(sector_scores),
        }

    # Per-dimension analysis (from assessments that have dimension data)
    dim_scores: Dict[str, List[float]] = {}
    for a in assessments:
        if "dimensions" in a:
            for dim_name, dim_score in a["dimensions"].items():
                if dim_name not in dim_scores:
                    dim_scores[dim_name] = []
                dim_scores[dim_name].append(dim_score)

    dim_stats = {}
    for dim_name, d_scores in dim_scores.items():
        d_slope = _compute_slope(d_scores)
        dim_stats[dim_name] = {
            "trend": _classify_trend(d_slope, len(d_scores)),
            "avg_score": sum(d_scores) / len(d_scores),
        }

    # Verdict and grade distributions
    verdict_dist: Dict[str, int] = {}
    grade_dist: Dict[str, int] = {}
    for a in assessments:
        v = a["verdict"]
        verdict_dist[v] = verdict_dist.get(v, 0) + 1
        g = a["grade"]
        grade_dist[g] = grade_dist.get(g, 0) + 1

    # Mann-Kendall trend test (more robust than linear regression for non-normal data)
    mk_result = _mann_kendall(scores)

    # 95% confidence interval for mean score
    ci_result = _confidence_interval(scores)

    return {
        "trend": trend,
        "avg_score": round(avg_score, 4),
        "score_trajectory": [round(s, 4) for s in scores],
        "phase": phase,
        "coverage_pct": round(coverage_pct, 2),
        "reviews_total": len(assessments),
        "slope": round(slope, 6),
        "mann_kendall": mk_result,
        "confidence_interval": ci_result,
        "sectors": sector_stats,
        "dimensions": dim_stats,
        "verdict_distribution": verdict_dist,
        "grade_distribution": grade_dist,
    }


def get_sector_convergence(
    sector: str,
    window_size: int = 20,
) -> Dict[str, Any]:
    """Get convergence status for a specific sector.

    Args:
        sector: Sector name (e.g., "arxiv", "defense", "inbox")
        window_size: Number of recent reviews to analyze

    Returns:
        {
            "sector": str,
            "trend": str,
            "avg_score": float,
            "score_trajectory": list[float],
            "count": int,
            "slope": float,
        }
    """
    empty = {"sector": sector, "trend": "insufficient_data", "avg_score": 0.0,
             "score_trajectory": [], "count": 0, "slope": 0.0}

    if not HAS_MEMORY:
        return empty

    # Use recall() for BM25 + semantic + multi-hop graph traversal.
    # Fetch 4x window to compensate for non-chronological ranking.
    # NOTE: memory service /recall endpoint caps k at ~50-99.  k>=100 returns
    # 422 Unprocessable Entity.  Cap at 50 to stay within service limits.
    fetch_k = min(window_size * 4, 50)
    try:
        client = MemoryClient(scope="extractor")
        search_result = client.recall(
            f"pdf_assessment {sector} extractor extraction quality",
            k=fetch_k,
        )
    except Exception as e:
        logger.error(f"recall() failed: {e}")
        return empty

    assessments = []
    for item in search_result.get("items", []):
        parsed = _parse_assessment(item)
        if parsed and parsed["sector"] == sector:
            assessments.append(parsed)

    # Sort by timestamp (newest first), take window, reverse to oldest-first
    assessments.sort(key=lambda a: a["updated_at"], reverse=True)
    assessments = assessments[:window_size]
    assessments.reverse()

    scores = [a["score"] for a in assessments]
    slope = _compute_slope(scores)

    return {
        "sector": sector,
        "trend": _classify_trend(slope, len(scores)),
        "avg_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "score_trajectory": [round(s, 4) for s in scores],
        "count": len(assessments),
        "slope": round(slope, 6),
    }


def get_dimension_convergence(
    dimension: str,
    window_size: int = 20,
) -> Dict[str, Any]:
    """Get convergence status for a specific quality dimension.

    Args:
        dimension: Dimension name (e.g., "table_fidelity", "section_alignment")
        window_size: Number of recent reviews to analyze

    Returns:
        {
            "dimension": str,
            "trend": str,
            "avg_score": float,
            "score_trajectory": list[float],
            "count": int,
            "slope": float,
        }
    """
    empty = {"dimension": dimension, "trend": "insufficient_data", "avg_score": 0.0,
             "score_trajectory": [], "count": 0, "slope": 0.0}

    if not HAS_MEMORY:
        return empty

    # Use recall() for BM25 + semantic + multi-hop graph traversal.
    # Fetch 4x window to compensate for non-chronological ranking.
    # NOTE: memory service /recall endpoint caps k at ~50-99.  k>=100 returns
    # 422 Unprocessable Entity.  Cap at 50 to stay within service limits.
    fetch_k = min(window_size * 4, 50)
    try:
        client = MemoryClient(scope="extractor")
        search_result = client.recall(
            f"pdf_assessment extractor {dimension} quality dimension score",
            k=fetch_k,
        )
    except Exception as e:
        logger.error(f"recall() failed: {e}")
        return empty

    # Extract dimension-specific scores from solution JSON
    dim_scores = []
    for item in search_result.get("items", []):
        parsed = _parse_assessment(item)
        if parsed and "dimensions" in parsed and dimension in parsed["dimensions"]:
            dim_scores.append({
                "score": parsed["dimensions"][dimension],
                "updated_at": parsed["updated_at"],
            })

    # Sort by timestamp (newest first), take window, reverse to oldest-first
    dim_scores.sort(key=lambda d: d["updated_at"], reverse=True)
    dim_scores = dim_scores[:window_size]
    dim_scores.reverse()

    scores = [d["score"] for d in dim_scores]
    slope = _compute_slope(scores)

    return {
        "dimension": dimension,
        "trend": _classify_trend(slope, len(scores)),
        "avg_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "score_trajectory": [round(s, 4) for s in scores],
        "count": len(dim_scores),
        "slope": round(slope, 6),
    }


if __name__ == "__main__":
    import typer
import httpx

    def _cli(
        corpus_root: Path = typer.Option(Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "extractor_corpus", help="Corpus root directory"),
        window_size: int = typer.Option(50, help="Number of recent reviews to analyze"),
        sector: str = typer.Option("", help="Per-sector convergence"),
        dimension: str = typer.Option("", help="Per-dimension convergence"),
        output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Convergence tracker."""
        if sector:
            result = get_sector_convergence(sector, window_size)
        elif dimension:
            result = get_dimension_convergence(dimension, window_size)
        else:
            result = get_convergence_status(corpus_root, window_size)

        if output_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"Trend: {result['trend']}")
            print(f"Avg Score: {result.get('avg_score', 0.0):.4f}")
            print(f"Slope: {result.get('slope', 0.0):.6f}")
            if "phase" in result:
                print(f"Phase: {result['phase']}")
                print(f"Coverage: {result.get('coverage_pct', 0.0):.1f}%")
            print(f"Reviews: {result.get('reviews_total', result.get('count', 0))}")
            if result.get("score_trajectory"):
                trajectory = result["score_trajectory"]
                print(f"Trajectory: [{trajectory[0]:.3f} ... {trajectory[-1]:.3f}] ({len(trajectory)} points)")
            if result.get("sectors"):
                print("\nSectors:")
                for sec, stats in sorted(result["sectors"].items()):
                    print(f"  {sec}: trend={stats['trend']} avg={stats['avg_score']:.3f} n={stats['count']}")
            if result.get("dimensions"):
                print("\nDimensions:")
                for dim, stats in sorted(result["dimensions"].items()):
                    print(f"  {dim}: trend={stats['trend']} avg={stats['avg_score']:.3f}")
            if result.get("verdict_distribution"):
                print(f"\nVerdicts: {result['verdict_distribution']}")
            if result.get("grade_distribution"):
                print(f"Grades: {result['grade_distribution']}")

    typer.run(_cli)
