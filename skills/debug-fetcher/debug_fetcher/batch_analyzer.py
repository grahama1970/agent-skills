"""Batch analyzer for identifying failure patterns.

Analyzes results from batch fetch operations to identify
patterns and group failures for human review.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List
from urllib.parse import urlparse

from .memory_schema import BatchAnalysis
from .strategy_engine import StrategyResult


def analyze_batch(results: List[StrategyResult]) -> BatchAnalysis:
    """Analyze a batch of fetch results to identify patterns.

    Groups failures by:
    - HTTP status code
    - Content verdict
    - Domain

    Identifies patterns like "all nytimes.com URLs returned 403".

    Args:
        results: List of StrategyResult from batch fetch

    Returns:
        BatchAnalysis with grouped failures and detected patterns
    """
    analysis = BatchAnalysis(total_urls=len(results))

    # Count successes and failures
    for result in results:
        if result.success:
            analysis.successful += 1
        else:
            analysis.failed += 1

    # Group failures
    by_status: Dict[int, List[str]] = defaultdict(list)
    by_verdict: Dict[str, List[str]] = defaultdict(list)
    by_domain: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for result in results:
        if result.success:
            continue

        url = result.url

        # Extract domain
        try:
            domain = urlparse(url).hostname or "unknown"
        except Exception:
            domain = "unknown"

        # Get status and verdict from final attempt
        status = 0
        verdict = "unknown"
        if result.final_attempt:
            status = result.final_attempt.status_code
            verdict = result.final_attempt.content_verdict or result.final_attempt.error or "failed"

        # Group
        if status > 0:
            by_status[status].append(url)
        by_verdict[verdict].append(url)
        by_domain[domain]["total"] += 1
        if status > 0:
            by_domain[domain][f"status_{status}"] += 1

    analysis.by_status = dict(by_status)
    analysis.by_verdict = dict(by_verdict)
    analysis.by_domain = dict(by_domain)

    # Detect patterns
    patterns = _detect_patterns(analysis)
    analysis.patterns = patterns

    # Identify unrecoverable URLs (failed all strategies)
    for result in results:
        if not result.success and result.winning_strategy == "all_failed":
            analysis.unrecoverable.append(result.url)

    return analysis


def _detect_patterns(analysis: BatchAnalysis) -> List[str]:
    """Detect human-readable patterns in failure data.

    Args:
        analysis: BatchAnalysis with grouped failures

    Returns:
        List of pattern descriptions
    """
    patterns = []

    # Pattern: Domain with high failure rate
    for domain, stats in analysis.by_domain.items():
        total = stats.get("total", 0)
        if total >= 3:  # Meaningful sample
            # Check for consistent status
            for key, count in stats.items():
                if key.startswith("status_") and count == total:
                    status = key.replace("status_", "")
                    patterns.append(f"All {total} URLs from {domain} returned HTTP {status}")

    # Pattern: Common verdict
    for verdict, urls in analysis.by_verdict.items():
        if len(urls) >= 5:
            pct = (len(urls) / analysis.failed) * 100 if analysis.failed > 0 else 0
            if pct >= 30:
                patterns.append(f"{len(urls)} URLs ({pct:.0f}%) failed with: {verdict}")

    # Pattern: High failure rate
    if analysis.failed > 0 and analysis.total_urls > 0:
        fail_rate = (analysis.failed / analysis.total_urls) * 100
        if fail_rate >= 50:
            patterns.append(f"High failure rate: {fail_rate:.0f}% ({analysis.failed}/{analysis.total_urls})")

    # Pattern: Single domain dominates failures
    if analysis.by_domain:
        total_failed = sum(d.get("total", 0) for d in analysis.by_domain.values())
        for domain, stats in analysis.by_domain.items():
            domain_total = stats.get("total", 0)
            if domain_total >= 5 and total_failed > 0:
                pct = (domain_total / total_failed) * 100
                if pct >= 40:
                    patterns.append(f"{domain} accounts for {pct:.0f}% of failures ({domain_total} URLs)")

    return patterns


def get_failure_summary(results: List[StrategyResult]) -> Dict[str, Any]:
    """Get a concise summary of batch failures.

    Useful for quick diagnosis or logging.

    Args:
        results: List of StrategyResult

    Returns:
        Dict with failure summary
    """
    analysis = analyze_batch(results)

    # Top failing domains
    top_domains = sorted(
        [(d, s.get("total", 0)) for d, s in analysis.by_domain.items()],
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    return {
        "total": analysis.total_urls,
        "success": analysis.successful,
        "failed": analysis.failed,
        "success_rate": f"{(analysis.successful / analysis.total_urls * 100):.1f}%" if analysis.total_urls > 0 else "N/A",
        "top_failing_domains": [{"domain": d, "count": c} for d, c in top_domains],
        "patterns": analysis.patterns,
        "unrecoverable_count": len(analysis.unrecoverable),
    }
