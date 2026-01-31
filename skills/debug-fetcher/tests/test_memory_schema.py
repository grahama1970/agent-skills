"""Tests for memory schema."""

import json
import pytest
from debug_fetcher.memory_schema import FetchStrategy, BatchAnalysis, RecoveryAction


class TestFetchStrategy:
    """Tests for FetchStrategy dataclass."""

    def test_fetch_strategy_serialization(self):
        """Test serialization to/from memory format."""
        strategy = FetchStrategy(
            domain="attack.mitre.org",
            path_pattern="/techniques/*",
            successful_strategy="playwright",
            headers={"Accept": "text/html"},
            timing_ms=1500,
            success_rate=0.95,
            tags=["security", "spa"],
        )

        # Convert to memory format
        memory_format = strategy.to_memory_format()
        assert "problem" in memory_format
        assert "solution" in memory_format
        assert "attack.mitre.org" in memory_format["problem"]
        assert "playwright" in memory_format["tags"]

        # Parse solution JSON
        solution_data = json.loads(memory_format["solution"])
        assert solution_data["domain"] == "attack.mitre.org"
        assert solution_data["successful_strategy"] == "playwright"

    def test_fetch_strategy_from_memory_format(self):
        """Test parsing from memory recall result."""
        memory_item = {
            "problem": "Fetch strategy for attack.mitre.org/techniques/*",
            "solution": json.dumps({
                "domain": "attack.mitre.org",
                "path_pattern": "/techniques/*",
                "successful_strategy": "playwright",
                "timing_ms": 1500,
            }),
        }

        strategy = FetchStrategy.from_memory_format(memory_item)
        assert strategy is not None
        assert strategy.domain == "attack.mitre.org"
        assert strategy.successful_strategy == "playwright"
        assert strategy.timing_ms == 1500

    def test_fetch_strategy_from_invalid_format(self):
        """Test graceful handling of invalid memory format."""
        # Missing solution
        assert FetchStrategy.from_memory_format({}) is None

        # Invalid JSON
        assert FetchStrategy.from_memory_format({"solution": "not-json"}) is None

    def test_update_stats_success(self):
        """Test updating stats after successful fetch."""
        strategy = FetchStrategy(domain="example.com")
        initial_count = strategy.success_count

        strategy.update_stats(success=True, timing_ms=500)

        assert strategy.success_count == initial_count + 1
        assert strategy.success_rate == 1.0  # Still perfect

    def test_update_stats_failure(self):
        """Test updating stats after failed fetch."""
        strategy = FetchStrategy(domain="example.com", success_count=3, failure_count=1)

        strategy.update_stats(success=False)

        assert strategy.failure_count == 2
        assert strategy.success_rate == 0.6  # 3 / (3+2)

    def test_matches_url_domain(self):
        """Test URL matching by domain."""
        strategy = FetchStrategy(domain="example.com")

        assert strategy.matches_url("https://example.com/page")
        assert strategy.matches_url("https://www.example.com/page")
        assert not strategy.matches_url("https://other.com/page")

    def test_matches_url_path_pattern(self):
        """Test URL matching by path pattern."""
        strategy = FetchStrategy(domain="example.com", path_pattern="/article/*")

        assert strategy.matches_url("https://example.com/article/123")
        assert not strategy.matches_url("https://example.com/page/123")

    def test_matches_url_wildcard(self):
        """Test wildcard pattern matches all paths."""
        strategy = FetchStrategy(domain="example.com", path_pattern="*")

        assert strategy.matches_url("https://example.com/any/path")
        assert strategy.matches_url("https://example.com/")


class TestBatchAnalysis:
    """Tests for BatchAnalysis dataclass."""

    def test_batch_analysis_defaults(self):
        """Test default values."""
        analysis = BatchAnalysis()

        assert analysis.total_urls == 0
        assert analysis.successful == 0
        assert analysis.failed == 0
        assert analysis.by_status == {}
        assert analysis.by_verdict == {}
        assert analysis.unrecoverable == []


class TestRecoveryAction:
    """Tests for RecoveryAction dataclass."""

    def test_recovery_action_mirror(self):
        """Test mirror URL recovery action."""
        action = RecoveryAction(
            url="https://example.com/page",
            action_type="mirror",
            mirror_url="https://archive.org/web/example.com/page",
        )

        assert action.action_type == "mirror"
        assert action.mirror_url is not None

    def test_recovery_action_skip(self):
        """Test skip recovery action."""
        action = RecoveryAction(
            url="https://example.com/page",
            action_type="skip",
            notes="Not critical for this batch",
        )

        assert action.action_type == "skip"
