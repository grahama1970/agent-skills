"""Tests for recovery executor."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from debug_fetcher.recovery_executor import (
    execute_recovery,
    _execute_single_action,
    _try_mirror_url,
    _process_manual_file,
    _try_with_credentials,
    _schedule_retry,
    _try_custom_strategy,
)
from debug_fetcher.memory_schema import RecoveryAction
from debug_fetcher.strategy_engine import StrategyResult, FetchAttempt


class TestExecuteRecovery:
    """Tests for execute_recovery function."""

    def test_execute_skip_action(self):
        """Test executing a skip action."""
        actions = [
            RecoveryAction(
                url="https://example.com/skip-me",
                action_type="skip",
                notes="Not needed",
            ),
        ]

        results = execute_recovery(actions)

        assert len(results) == 1
        result = results[0]
        assert result.success is True  # Skip is "successful"
        assert result.winning_strategy == "skipped"
        assert result.final_attempt.metadata.get("skipped") is True

    def test_execute_multiple_actions(self):
        """Test executing multiple actions."""
        actions = [
            RecoveryAction(url="https://a.com", action_type="skip"),
            RecoveryAction(url="https://b.com", action_type="retry"),
        ]

        results = execute_recovery(actions)

        assert len(results) == 2
        assert results[0].winning_strategy == "skipped"
        assert results[1].winning_strategy == "retry_scheduled"


class TestTryMirrorUrl:
    """Tests for mirror URL recovery."""

    @patch("debug_fetcher.recovery_executor.StrategyEngine")
    def test_execute_mirror_url_recovery(self, mock_engine_class):
        """Test successful mirror URL fetch."""
        # Setup mock
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine
        mock_engine.exhaust_strategies.return_value = StrategyResult(
            url="https://archive.org/page",
            success=True,
            winning_strategy="direct",
            final_attempt=FetchAttempt(
                url="https://archive.org/page",
                strategy="direct",
                success=True,
                status_code=200,
                content_length=5000,
            ),
        )

        action = RecoveryAction(
            url="https://example.com/original",
            action_type="mirror",
            mirror_url="https://archive.org/page",
        )

        result = _try_mirror_url(action)

        assert result.success is True
        assert result.winning_strategy == "mirror"
        assert result.url == "https://example.com/original"  # Original URL preserved
        assert result.final_attempt.metadata.get("mirror_url") == "https://archive.org/page"

    def test_mirror_url_missing(self):
        """Test error when mirror URL not provided."""
        action = RecoveryAction(
            url="https://example.com/page",
            action_type="mirror",
            mirror_url=None,  # Missing!
        )

        result = _try_mirror_url(action)

        assert result.success is False
        assert "No mirror URL" in result.final_attempt.error


class TestProcessManualFile:
    """Tests for manual file processing."""

    def test_process_manual_file_exists(self, tmp_path):
        """Test processing existing manual file."""
        # Create a test file
        test_file = tmp_path / "manual_download.pdf"
        test_file.write_bytes(b"PDF content here")

        action = RecoveryAction(
            url="https://example.com/paper.pdf",
            action_type="manual_file",
            file_path=str(test_file),
        )

        result = _process_manual_file(action)

        assert result.success is True
        assert result.winning_strategy == "manual"
        assert result.final_attempt.content_length == len(b"PDF content here")
        assert result.final_attempt.metadata.get("source") == "manual_download"

    def test_process_manual_file_not_found(self):
        """Test error when manual file doesn't exist."""
        action = RecoveryAction(
            url="https://example.com/paper.pdf",
            action_type="manual_file",
            file_path="/nonexistent/path/file.pdf",
        )

        result = _process_manual_file(action)

        assert result.success is False
        assert "not found" in result.final_attempt.error.lower()

    def test_process_manual_file_copies_to_output_dir(self, tmp_path):
        """Test that file is copied to output directory."""
        # Create source file
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        source_file = source_dir / "original.pdf"
        source_file.write_bytes(b"Original content")

        # Output directory
        output_dir = tmp_path / "output"

        action = RecoveryAction(
            url="https://example.com/doc.pdf",
            action_type="manual_file",
            file_path=str(source_file),
        )

        result = _process_manual_file(action, output_dir=output_dir)

        assert result.success is True
        assert output_dir.exists()
        assert (output_dir / "original.pdf").exists()
        assert (output_dir / "original.pdf").read_bytes() == b"Original content"

    def test_process_manual_file_no_path(self):
        """Test error when file path not provided."""
        action = RecoveryAction(
            url="https://example.com/doc.pdf",
            action_type="manual_file",
            file_path=None,
        )

        result = _process_manual_file(action)

        assert result.success is False
        assert "No file path" in result.final_attempt.error


class TestTryWithCredentials:
    """Tests for credential-based recovery."""

    def test_credentials_returns_pending(self):
        """Test that credentials action returns pending status."""
        action = RecoveryAction(
            url="https://example.com/protected",
            action_type="credentials",
            credentials={"username": "user", "password": "pass"},
        )

        result = _try_with_credentials(action)

        # Currently returns pending (not implemented)
        assert result.success is False
        assert result.winning_strategy == "credentials_pending"
        assert result.final_attempt.metadata.get("credentials_provided") is True


class TestScheduleRetry:
    """Tests for retry scheduling."""

    def test_schedule_retry_default_delay(self):
        """Test scheduling retry with default delay."""
        action = RecoveryAction(
            url="https://example.com/temp-down",
            action_type="retry",
            notes="Server maintenance",
        )

        result = _schedule_retry(action)

        assert result.success is False  # Not yet successful
        assert result.winning_strategy == "retry_scheduled"
        assert result.final_attempt.metadata.get("retry_after_seconds") == 3600

    def test_schedule_retry_custom_delay(self):
        """Test scheduling retry with custom delay."""
        action = RecoveryAction(
            url="https://example.com/temp-down",
            action_type="retry",
            retry_after=7200,  # 2 hours
        )

        result = _schedule_retry(action)

        assert result.final_attempt.metadata.get("retry_after_seconds") == 7200


class TestTryCustomStrategy:
    """Tests for custom strategy execution."""

    @patch("debug_fetcher.recovery_executor.StrategyEngine")
    def test_custom_strategy_parses_proxy(self, mock_engine_class):
        """Test custom strategy parses proxy suggestion."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine
        mock_engine.exhaust_strategies.return_value = StrategyResult(
            url="https://geo-blocked.com/content",
            success=True,
            winning_strategy="proxy",
            final_attempt=FetchAttempt(
                url="https://geo-blocked.com/content",
                strategy="proxy",
                success=True,
            ),
        )

        action = RecoveryAction(
            url="https://geo-blocked.com/content",
            action_type="custom_strategy",
            notes="Try using a proxy, site is geo-blocked",
        )

        result = _try_custom_strategy(action)

        # Should have tried proxy strategy
        mock_engine_class.assert_called_once()
        call_kwargs = mock_engine_class.call_args.kwargs
        assert "proxy" in call_kwargs.get("strategies", [])

    @patch("debug_fetcher.recovery_executor.StrategyEngine")
    def test_custom_strategy_parses_playwright(self, mock_engine_class):
        """Test custom strategy parses browser/JS suggestion."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine
        mock_engine.exhaust_strategies.return_value = StrategyResult(
            url="https://spa.com/page",
            success=True,
            winning_strategy="playwright",
            final_attempt=FetchAttempt(
                url="https://spa.com/page",
                strategy="playwright",
                success=True,
            ),
        )

        action = RecoveryAction(
            url="https://spa.com/page",
            action_type="custom_strategy",
            notes="Need browser/JS rendering",
        )

        result = _try_custom_strategy(action)

        call_kwargs = mock_engine_class.call_args.kwargs
        assert "playwright" in call_kwargs.get("strategies", [])

    def test_custom_strategy_unparseable(self):
        """Test custom strategy with unparseable notes."""
        action = RecoveryAction(
            url="https://example.com/page",
            action_type="custom_strategy",
            notes="some random suggestion that doesn't match any strategy",
        )

        result = _try_custom_strategy(action)

        assert result.success is False
        assert "Could not parse strategy" in result.final_attempt.error


class TestUnknownActionType:
    """Tests for unknown action types."""

    def test_unknown_action_type(self):
        """Test handling of unknown action type."""
        action = RecoveryAction(
            url="https://example.com/page",
            action_type="unknown_type",
        )

        result = _execute_single_action(action)

        assert result.success is False
        assert "Unknown action type" in result.final_attempt.error
