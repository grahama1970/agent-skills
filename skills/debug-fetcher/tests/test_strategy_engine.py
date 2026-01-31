"""Tests for strategy engine."""

import pytest
from unittest.mock import patch, MagicMock
from debug_fetcher.strategy_engine import (
    StrategyEngine,
    FetchAttempt,
    StrategyResult,
    exhaust_strategies,
)
from debug_fetcher.memory_schema import FetchStrategy


class TestStrategyEngine:
    """Tests for StrategyEngine class."""

    def test_engine_initialization(self):
        """Test engine initializes with default strategies."""
        engine = StrategyEngine()

        assert "direct" in engine.strategies
        assert "playwright" in engine.strategies
        assert engine.enable_memory is True

    def test_engine_custom_strategies(self):
        """Test engine with custom strategy list."""
        engine = StrategyEngine(strategies=["direct", "playwright"])

        assert engine.strategies == ["direct", "playwright"]

    def test_is_youtube_url(self):
        """Test YouTube URL detection."""
        engine = StrategyEngine()

        assert engine._is_youtube_url("https://www.youtube.com/watch?v=abc123")
        assert engine._is_youtube_url("https://youtube.com/watch?v=abc123")
        assert engine._is_youtube_url("https://youtu.be/abc123")
        assert not engine._is_youtube_url("https://example.com/video")

    @patch("debug_fetcher.strategy_engine.StrategyEngine._run_fetcher")
    @patch("debug_fetcher.strategy_engine.get_best_strategy_for_url")
    def test_exhaust_strategies_finds_winner(self, mock_memory, mock_fetcher):
        """Test finding a winning strategy."""
        mock_memory.return_value = None  # No learned strategy

        # First strategy fails (with non-transient error to skip retries), second succeeds
        mock_fetcher.side_effect = [
            FetchAttempt(url="https://example.com", strategy="direct", success=False, error="404 Not Found"),
            FetchAttempt(url="https://example.com", strategy="playwright", success=True, content_verdict="ok"),
        ]

        engine = StrategyEngine(strategies=["direct", "playwright"], max_retries=1, enable_memory=False)
        result = engine.exhaust_strategies("https://example.com")

        assert result.success is True
        assert result.winning_strategy == "playwright"

    @patch("debug_fetcher.strategy_engine.StrategyEngine._run_fetcher")
    @patch("debug_fetcher.strategy_engine.get_best_strategy_for_url")
    def test_exhaust_strategies_all_fail(self, mock_memory, mock_fetcher):
        """Test when all strategies fail."""
        mock_memory.return_value = None

        mock_fetcher.return_value = FetchAttempt(
            url="https://example.com",
            strategy="direct",
            success=False,
            error="Connection refused",
        )

        engine = StrategyEngine(strategies=["direct"], max_retries=1, enable_memory=False)
        result = engine.exhaust_strategies("https://example.com")

        assert result.success is False
        assert result.winning_strategy == "all_failed"

    @patch("debug_fetcher.strategy_engine.StrategyEngine._run_fetcher")
    @patch("debug_fetcher.strategy_engine.get_best_strategy_for_url")
    def test_prefetch_uses_learned_strategy(self, mock_memory, mock_fetcher):
        """Test that learned strategy is tried first."""
        # Memory says playwright works for this domain
        mock_memory.return_value = FetchStrategy(
            domain="attack.mitre.org",
            successful_strategy="playwright",
        )

        mock_fetcher.return_value = FetchAttempt(
            url="https://attack.mitre.org/techniques/T1059",
            strategy="playwright",
            success=True,
        )

        engine = StrategyEngine(enable_memory=False)  # Memory mock is separate

        # Manually inject the learned strategy check
        engine.enable_memory = True
        result = engine.exhaust_strategies("https://attack.mitre.org/techniques/T1059")

        # First attempt should be playwright (the learned strategy)
        assert result.attempts[0].strategy == "playwright"
        assert result.success is True

    @patch("debug_fetcher.strategy_engine.StrategyEngine._run_youtube_skill")
    def test_youtube_url_uses_youtube_skill(self, mock_youtube):
        """Test that YouTube URLs use the YouTube skill first."""
        mock_youtube.return_value = FetchAttempt(
            url="https://www.youtube.com/watch?v=abc123",
            strategy="youtube",
            success=True,
            content_length=5000,
        )

        engine = StrategyEngine(enable_memory=False)
        result = engine.exhaust_strategies("https://www.youtube.com/watch?v=abc123")

        assert result.success is True
        assert result.winning_strategy == "youtube"
        mock_youtube.assert_called_once()


class TestExhaustStrategiesFunction:
    """Tests for convenience function."""

    @patch("debug_fetcher.strategy_engine.StrategyEngine.exhaust_strategies")
    def test_exhaust_strategies_returns_tuple(self, mock_exhaust):
        """Test convenience function returns expected tuple."""
        mock_exhaust.return_value = StrategyResult(
            url="https://example.com",
            success=True,
            winning_strategy="direct",
            final_attempt=FetchAttempt(
                url="https://example.com",
                strategy="direct",
                success=True,
                status_code=200,
                content_verdict="ok",
                timing_ms=500,
            ),
            attempts=[],
        )

        success, strategy, metadata = exhaust_strategies("https://example.com")

        assert success is True
        assert strategy == "direct"
        assert metadata["status_code"] == 200
