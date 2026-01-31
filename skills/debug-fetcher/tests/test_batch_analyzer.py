"""Tests for batch analyzer."""

import pytest
from debug_fetcher.batch_analyzer import (
    analyze_batch,
    get_failure_summary,
)
from debug_fetcher.strategy_engine import StrategyResult, FetchAttempt


class TestAnalyzeBatch:
    """Tests for analyze_batch function."""

    def test_analyze_batch_groups_failures(self):
        """Test that failures are grouped by status, verdict, and domain."""
        results = [
            StrategyResult(
                url="https://nytimes.com/article1",
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url="https://nytimes.com/article1",
                    strategy="direct",
                    success=False,
                    status_code=403,
                    content_verdict="access_denied",
                ),
            ),
            StrategyResult(
                url="https://nytimes.com/article2",
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url="https://nytimes.com/article2",
                    strategy="direct",
                    success=False,
                    status_code=403,
                    content_verdict="access_denied",
                ),
            ),
            StrategyResult(
                url="https://example.com/page",
                success=True,
                winning_strategy="direct",
                final_attempt=FetchAttempt(
                    url="https://example.com/page",
                    strategy="direct",
                    success=True,
                    status_code=200,
                ),
            ),
        ]

        analysis = analyze_batch(results)

        assert analysis.total_urls == 3
        assert analysis.successful == 1
        assert analysis.failed == 2
        assert 403 in analysis.by_status
        assert len(analysis.by_status[403]) == 2
        assert "nytimes.com" in analysis.by_domain

    def test_analyze_batch_detects_patterns(self):
        """Test pattern detection for consistent domain failures."""
        # All 3 URLs from nytimes.com return 403
        results = [
            StrategyResult(
                url=f"https://nytimes.com/article{i}",
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url=f"https://nytimes.com/article{i}",
                    strategy="direct",
                    success=False,
                    status_code=403,
                ),
            )
            for i in range(3)
        ]

        analysis = analyze_batch(results)

        # Should detect "All X URLs from nytimes.com returned HTTP 403"
        assert any("nytimes.com" in p and "403" in p for p in analysis.patterns)

    def test_analyze_batch_empty_input(self):
        """Test with empty results list."""
        analysis = analyze_batch([])

        assert analysis.total_urls == 0
        assert analysis.successful == 0
        assert analysis.failed == 0
        assert analysis.patterns == []

    def test_analyze_batch_identifies_unrecoverable(self):
        """Test identification of truly unrecoverable URLs."""
        results = [
            StrategyResult(
                url="https://example.com/unrecoverable",
                success=False,
                winning_strategy="all_failed",  # Key indicator
                final_attempt=FetchAttempt(
                    url="https://example.com/unrecoverable",
                    strategy="wayback",
                    success=False,
                    error="All strategies exhausted",
                ),
            ),
        ]

        analysis = analyze_batch(results)

        assert "https://example.com/unrecoverable" in analysis.unrecoverable


class TestGetFailureSummary:
    """Tests for get_failure_summary function."""

    def test_failure_summary_includes_top_domains(self):
        """Test that summary includes top failing domains."""
        results = [
            StrategyResult(
                url=f"https://domain{i}.com/page",
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url=f"https://domain{i}.com/page",
                    strategy="direct",
                    success=False,
                    status_code=500,
                ),
            )
            for i in range(10)
        ]
        # Add multiple failures for domain0
        for _ in range(5):
            results.append(
                StrategyResult(
                    url="https://domain0.com/another",
                    success=False,
                    winning_strategy="all_failed",
                    final_attempt=FetchAttempt(
                        url="https://domain0.com/another",
                        strategy="direct",
                        success=False,
                        status_code=500,
                    ),
                )
            )

        summary = get_failure_summary(results)

        assert summary["failed"] == 15
        assert len(summary["top_failing_domains"]) > 0
        # domain0.com should be at top with 6 failures
        top_domain = summary["top_failing_domains"][0]
        assert top_domain["domain"] == "domain0.com"
        assert top_domain["count"] == 6

    def test_failure_summary_with_successes(self):
        """Test summary calculation with mixed results."""
        results = [
            StrategyResult(
                url="https://example.com/success",
                success=True,
                winning_strategy="direct",
                final_attempt=FetchAttempt(
                    url="https://example.com/success",
                    strategy="direct",
                    success=True,
                    status_code=200,
                ),
            ),
            StrategyResult(
                url="https://example.com/fail",
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url="https://example.com/fail",
                    strategy="direct",
                    success=False,
                    status_code=404,
                ),
            ),
        ]

        summary = get_failure_summary(results)

        assert summary["total"] == 2
        assert summary["success"] == 1
        assert summary["failed"] == 1
        assert summary["success_rate"] == "50.0%"
