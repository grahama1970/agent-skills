"""Integration tests for learn-fetcher.

Tests the full flow: fetch -> fail -> analyze -> interview -> recover -> learn
with mocked external dependencies for deterministic testing.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from debug_fetcher.strategy_engine import StrategyEngine, StrategyResult, FetchAttempt
from debug_fetcher.batch_analyzer import analyze_batch
from debug_fetcher.interview_generator import generate_interview
from debug_fetcher.interview_processor import process_response
from debug_fetcher.recovery_executor import execute_recovery
from debug_fetcher.memory_bridge import learn_strategy, recall_strategy
from debug_fetcher.memory_schema import FetchStrategy, RecoveryAction


class TestFullLearnFetchFlow:
    """Integration tests for the complete learn-fetch workflow."""

    @patch("debug_fetcher.strategy_engine.StrategyEngine._run_fetcher")
    @patch("debug_fetcher.memory_bridge.subprocess.run")
    def test_full_learn_fetch_flow(self, mock_subprocess, mock_fetcher):
        """Test the complete flow: fetch -> fail -> analyze -> interview -> recover -> learn."""
        # Step 1: Setup - URL that will fail all automated strategies
        test_url = "https://paywalled-site.com/article"

        # Mock memory recall (no prior knowledge)
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="[]",  # No prior strategies
            stderr="",
        )

        # Mock fetcher to always fail for this URL
        mock_fetcher.return_value = FetchAttempt(
            url=test_url,
            strategy="direct",
            success=False,
            status_code=403,
            content_verdict="paywall_detected",
            error="Paywall detected",
        )

        # Step 2: Fetch fails
        engine = StrategyEngine(
            strategies=["direct"],
            enable_memory=False,
            max_retries=1,
        )
        result = engine.exhaust_strategies(test_url)

        assert result.success is False
        assert result.winning_strategy == "all_failed"

        # Step 3: Analyze batch of failures
        batch_results = [result]
        analysis = analyze_batch(batch_results)

        assert analysis.failed == 1
        assert analysis.successful == 0
        assert len(analysis.unrecoverable) == 1
        assert test_url in analysis.unrecoverable

        # Step 4: Generate /interview questions
        interview_data = generate_interview(batch_results)

        assert "questions" in interview_data
        assert len(interview_data["questions"]) >= 1
        assert any("paywall" in str(q).lower() or "403" in str(q)
                   for q in interview_data["questions"])

        # Step 5: Simulate human response - provide a mirror URL
        human_response = {
            "completed": True,
            "responses": {
                interview_data["questions"][0]["id"]: {
                    "decision": "mirror",
                    "value": "Try this mirror",
                    "other_text": "https://archive.org/web/20230601/" + test_url,
                    "url": test_url,
                }
            },
        }

        # Step 6: Process interview response
        recovery_actions = process_response(human_response)

        assert len(recovery_actions) == 1
        action = recovery_actions[0]
        assert action.action_type == "mirror"
        assert action.mirror_url is not None

        # Step 7: Execute recovery (mock successful mirror fetch)
        with patch("debug_fetcher.recovery_executor.StrategyEngine") as mock_engine_class, \
             patch("debug_fetcher.recovery_executor.learn_strategy") as mock_learn:
            mock_recovery_engine = MagicMock()
            mock_engine_class.return_value = mock_recovery_engine
            mock_recovery_engine.exhaust_strategies.return_value = StrategyResult(
                url=action.mirror_url,
                success=True,
                winning_strategy="direct",
                final_attempt=FetchAttempt(
                    url=action.mirror_url,
                    strategy="direct",
                    success=True,
                    status_code=200,
                    content_length=10000,
                ),
            )
            mock_learn.return_value = True  # Mock successful learning

            recovery_results = execute_recovery(recovery_actions)

        assert len(recovery_results) == 1
        assert recovery_results[0].success is True
        assert recovery_results[0].winning_strategy == "mirror"

    @patch("debug_fetcher.strategy_engine.StrategyEngine._run_fetcher")
    @patch("debug_fetcher.strategy_engine.get_best_strategy_for_url")
    def test_memory_recall_improves_fetch(self, mock_get_best, mock_fetcher):
        """Test that fetching with prior memory knowledge improves success."""
        test_url = "https://attack.mitre.org/techniques/T1059"

        # Memory says playwright works for this domain
        mock_get_best.return_value = FetchStrategy(
            domain="attack.mitre.org",
            successful_strategy="playwright",
            success_rate=0.95,
        )

        # Playwright succeeds
        mock_fetcher.return_value = FetchAttempt(
            url=test_url,
            strategy="playwright",
            success=True,
            status_code=200,
            content_length=50000,
            content_verdict="ok",
        )

        engine = StrategyEngine(enable_memory=True)
        result = engine.exhaust_strategies(test_url)

        # Should succeed on first try with learned strategy
        assert result.success is True
        assert result.winning_strategy == "playwright"
        assert len(result.attempts) == 1  # Only needed one attempt

    def test_skip_actions_flow(self):
        """Test that skip actions are processed correctly in the workflow."""
        # Create failures
        failures = [
            StrategyResult(
                url="https://example.com/optional-page",
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url="https://example.com/optional-page",
                    strategy="wayback",
                    success=False,
                    error="Not found in any archive",
                ),
            ),
        ]

        # Generate interview
        interview = generate_interview(failures, group_by_domain=False)

        # Human decides to skip
        response = {
            "completed": True,
            "responses": {
                interview["questions"][0]["id"]: {
                    "decision": "skip",
                    "value": "Skip it",
                    "other_text": "Not important for my use case",
                    "url": "https://example.com/optional-page",
                }
            },
        }

        actions = process_response(response)
        assert len(actions) == 1
        assert actions[0].action_type == "skip"

        # Execute skip
        results = execute_recovery(actions)
        assert results[0].success is True  # Skip is "successful"
        assert results[0].winning_strategy == "skipped"

    @patch("debug_fetcher.recovery_executor.StrategyEngine")
    def test_custom_strategy_suggestion_flow(self, mock_engine_class):
        """Test that custom strategy suggestions are executed."""
        test_url = "https://geo-blocked.com/content"

        # Setup mock for custom strategy
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine
        mock_engine.exhaust_strategies.return_value = StrategyResult(
            url=test_url,
            success=True,
            winning_strategy="proxy",
            final_attempt=FetchAttempt(
                url=test_url,
                strategy="proxy",
                success=True,
                status_code=200,
            ),
        )

        # Simulate custom strategy response
        response = {
            "completed": True,
            "responses": {
                "domain_1234": {
                    "decision": "custom",
                    "value": "Try different strategy",
                    "other_text": "Use a proxy - site is geo-blocked",
                    "url": test_url,
                }
            },
        }

        actions = process_response(response)
        assert len(actions) == 1
        assert actions[0].action_type == "custom_strategy"

        results = execute_recovery(actions)

        # Custom strategy should have been attempted
        mock_engine_class.assert_called()
        call_kwargs = mock_engine_class.call_args.kwargs
        assert "proxy" in call_kwargs.get("strategies", [])


class TestBatchProcessingFlow:
    """Tests for batch processing scenarios."""

    @patch("debug_fetcher.strategy_engine.StrategyEngine._run_fetcher")
    @patch("debug_fetcher.strategy_engine.get_best_strategy_for_url")
    def test_batch_with_mixed_results(self, mock_memory, mock_fetcher):
        """Test processing a batch with mixed success/failure."""
        mock_memory.return_value = None

        # Setup: some URLs succeed, some fail
        def fetcher_side_effect(url, *args, **kwargs):
            if "success" in url:
                return FetchAttempt(
                    url=url,
                    strategy="direct",
                    success=True,
                    status_code=200,
                )
            else:
                return FetchAttempt(
                    url=url,
                    strategy="direct",
                    success=False,
                    status_code=403,
                    error="Forbidden",
                )

        mock_fetcher.side_effect = fetcher_side_effect

        urls = [
            "https://example.com/success1",
            "https://example.com/fail1",
            "https://example.com/success2",
            "https://example.com/fail2",
        ]

        engine = StrategyEngine(strategies=["direct"], enable_memory=False, max_retries=1)
        results = [engine.exhaust_strategies(url) for url in urls]

        # Analyze batch
        analysis = analyze_batch(results)

        assert analysis.total_urls == 4
        assert analysis.successful == 2
        assert analysis.failed == 2

        # Only generate interview for failures (don't group by domain)
        interview = generate_interview([r for r in results if not r.success], group_by_domain=False)

        assert len(interview["questions"]) == 2

    def test_domain_pattern_detection(self):
        """Test that batch analyzer detects domain patterns."""
        # All failures from same domain with same status
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
            for i in range(5)
        ]

        analysis = analyze_batch(results)

        # Should detect pattern
        assert any("nytimes.com" in p and "403" in p for p in analysis.patterns)

        # Interview should group by domain
        interview = generate_interview(results, group_by_domain=True)

        # Should have just 1 question for the domain
        assert len(interview["questions"]) == 1
        assert "5" in interview["questions"][0]["text"]  # "Failed 5 URLs"


class TestManualFileRecovery:
    """Tests for manual file recovery flow."""

    def test_manual_file_recovery_flow(self, tmp_path):
        """Test the complete flow for manual file recovery."""
        # Create a test file that simulates manual download
        manual_file = tmp_path / "downloaded_paper.pdf"
        manual_file.write_bytes(b"%PDF-1.4 fake pdf content")

        original_url = "https://academic-site.com/paper.pdf"

        # Create failure
        failures = [
            StrategyResult(
                url=original_url,
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url=original_url,
                    strategy="direct",
                    success=False,
                    error="Login required",
                ),
            ),
        ]

        # Generate interview
        interview = generate_interview(failures, group_by_domain=False)

        # Human provides manual file path
        response = {
            "completed": True,
            "responses": {
                interview["questions"][0]["id"]: {
                    "decision": "manual",
                    "value": "I'll download manually",
                    "other_text": str(manual_file),
                    "url": original_url,
                }
            },
        }

        actions = process_response(response)
        assert len(actions) == 1
        assert actions[0].action_type == "manual_file"
        assert actions[0].file_path == str(manual_file)

        # Execute recovery
        output_dir = tmp_path / "output"
        results = execute_recovery(actions, output_dir=output_dir)

        assert results[0].success is True
        assert results[0].winning_strategy == "manual"
        assert results[0].final_attempt.content_length > 0

        # File should be copied to output directory
        assert (output_dir / "downloaded_paper.pdf").exists()
