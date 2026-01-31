"""Tests for memory bridge."""

import pytest
from unittest.mock import patch, MagicMock
from debug_fetcher.memory_bridge import (
    recall_strategy,
    learn_strategy,
    get_best_strategy_for_url,
    recall_strategies_for_domain,
)
from debug_fetcher.memory_schema import FetchStrategy


class TestRecallStrategy:
    """Tests for recall_strategy function."""

    @patch("debug_fetcher.memory_bridge._run_memory_command")
    def test_recall_strategy_found(self, mock_cmd):
        """Test finding a strategy in memory."""
        mock_cmd.return_value = {
            "found": True,
            "items": [
                {
                    "problem": "Fetch strategy for attack.mitre.org/*",
                    "solution": '{"domain": "attack.mitre.org", "successful_strategy": "playwright"}',
                }
            ],
        }

        strategy = recall_strategy("attack.mitre.org", "/techniques/T1059")

        assert strategy is not None
        assert strategy.domain == "attack.mitre.org"
        assert strategy.successful_strategy == "playwright"

    @patch("debug_fetcher.memory_bridge._run_memory_command")
    def test_recall_strategy_not_found(self, mock_cmd):
        """Test when no strategy exists in memory."""
        mock_cmd.return_value = {"found": False, "items": []}

        strategy = recall_strategy("unknown.com", "/")

        assert strategy is None

    @patch("debug_fetcher.memory_bridge._run_memory_command")
    def test_recall_strategy_invalid_json(self, mock_cmd):
        """Test handling of invalid JSON in memory."""
        mock_cmd.return_value = {
            "found": True,
            "items": [{"problem": "test", "solution": "not-json"}],
        }

        strategy = recall_strategy("example.com", "/")

        assert strategy is None


class TestLearnStrategy:
    """Tests for learn_strategy function."""

    @patch("debug_fetcher.memory_bridge._run_memory_command")
    def test_learn_strategy_stores_to_memory(self, mock_cmd):
        """Test that learning stores strategy in memory."""
        mock_cmd.return_value = {"ok": True}

        result = learn_strategy(
            url="https://attack.mitre.org/techniques/T1059",
            strategy_used="playwright",
            timing_ms=1500,
        )

        assert result is True
        mock_cmd.assert_called_once()
        call_args = mock_cmd.call_args[0][0]
        assert "learn" in call_args
        assert "--problem" in call_args
        assert "--solution" in call_args

    @patch("debug_fetcher.memory_bridge._run_memory_command")
    def test_learn_strategy_with_path_generalization(self, mock_cmd):
        """Test that numeric paths are generalized."""
        mock_cmd.return_value = {"ok": True}

        # URL with numeric ID should generalize
        result = learn_strategy(
            url="https://example.com/article/12345",
            strategy_used="direct",
        )

        assert result is True

    def test_learn_strategy_invalid_url(self):
        """Test handling of invalid URLs."""
        result = learn_strategy(
            url="not-a-url",
            strategy_used="direct",
        )

        assert result is False


class TestGetBestStrategyForUrl:
    """Tests for get_best_strategy_for_url function."""

    @patch("debug_fetcher.memory_bridge.recall_strategies_for_domain")
    def test_get_best_strategy_matches_path(self, mock_recall):
        """Test finding best strategy based on path match."""
        mock_recall.return_value = [
            FetchStrategy(domain="example.com", path_pattern="/article/*", successful_strategy="playwright"),
            FetchStrategy(domain="example.com", path_pattern="*", successful_strategy="direct"),
        ]

        strategy = get_best_strategy_for_url("https://example.com/article/123")

        assert strategy is not None
        # More specific path pattern should win
        assert strategy.successful_strategy == "playwright"

    @patch("debug_fetcher.memory_bridge.recall_strategies_for_domain")
    def test_get_best_strategy_no_match(self, mock_recall):
        """Test when no strategies exist for domain."""
        mock_recall.return_value = []

        strategy = get_best_strategy_for_url("https://unknown.com/page")

        assert strategy is None
