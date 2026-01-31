"""Tests for interview generator."""

import pytest
import json
from debug_fetcher.interview_generator import (
    generate_interview,
    generate_interview_file,
)
from debug_fetcher.strategy_engine import StrategyResult, FetchAttempt


class TestGenerateInterview:
    """Tests for generate_interview function."""

    def test_generate_interview_valid_json(self):
        """Test that generated interview is valid /interview JSON."""
        failures = [
            StrategyResult(
                url="https://paywall.com/article",
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url="https://paywall.com/article",
                    strategy="wayback",
                    success=False,
                    status_code=403,
                    content_verdict="access_denied",
                    error="Paywall detected",
                ),
                attempts=[
                    FetchAttempt(
                        url="https://paywall.com/article",
                        strategy="direct",
                        success=False,
                        status_code=403,
                    ),
                    FetchAttempt(
                        url="https://paywall.com/article",
                        strategy="playwright",
                        success=False,
                        status_code=403,
                    ),
                ],
            ),
        ]

        interview = generate_interview(failures)

        # Validate structure
        assert "title" in interview
        assert "context" in interview
        assert "questions" in interview
        assert isinstance(interview["questions"], list)

        # Should have at least one question for the failure
        assert len(interview["questions"]) >= 1

        # Each question should have required fields
        for q in interview["questions"]:
            assert "id" in q
            assert "header" in q
            assert "text" in q
            assert "options" in q
            assert len(q["header"]) <= 12  # Max header length

            # Options should have label and description
            for opt in q["options"]:
                assert "label" in opt
                assert "description" in opt

    def test_generate_interview_empty_when_no_failures(self):
        """Test that no questions generated for empty failures list."""
        interview = generate_interview([])

        assert "questions" in interview
        assert len(interview["questions"]) == 0
        assert "No Failures" in interview["title"]

    def test_generate_interview_groups_by_domain(self):
        """Test domain grouping reduces question count."""
        # 5 failures from same domain
        failures = [
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

        interview_grouped = generate_interview(failures, group_by_domain=True)
        interview_ungrouped = generate_interview(failures, group_by_domain=False)

        # Grouped should have 1 question (for the domain)
        assert len(interview_grouped["questions"]) == 1
        # Ungrouped should have 5 questions (one per URL)
        assert len(interview_ungrouped["questions"]) == 5

    def test_generate_interview_respects_max_questions(self):
        """Test max_questions limit is respected."""
        failures = [
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
            for i in range(50)  # 50 different domains
        ]

        interview = generate_interview(failures, max_questions=10, group_by_domain=True)

        assert len(interview["questions"]) <= 10

    def test_generate_interview_includes_error_info(self):
        """Test that error information is included in questions."""
        failures = [
            StrategyResult(
                url="https://example.com/protected",
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url="https://example.com/protected",
                    strategy="direct",
                    success=False,
                    status_code=401,
                    error="Authentication required",
                ),
            ),
        ]

        interview = generate_interview(failures, group_by_domain=False)

        # Question text should contain error info
        assert len(interview["questions"]) == 1
        question_text = interview["questions"][0]["text"]
        assert "401" in question_text or "Authentication" in question_text

    def test_generate_interview_options_for_recovery(self):
        """Test that recovery options are present."""
        failures = [
            StrategyResult(
                url="https://example.com/page",
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url="https://example.com/page",
                    strategy="direct",
                    success=False,
                ),
            ),
        ]

        interview = generate_interview(failures, group_by_domain=False)

        options = interview["questions"][0]["options"]
        option_labels = [o["label"].lower() for o in options]

        # Should have common recovery options
        assert any("credential" in l for l in option_labels)
        assert any("skip" in l for l in option_labels)


class TestGenerateInterviewFile:
    """Tests for generate_interview_file function."""

    def test_generate_interview_file_creates_json(self, tmp_path):
        """Test that interview file is created with valid JSON."""
        failures = [
            StrategyResult(
                url="https://example.com/page",
                success=False,
                winning_strategy="all_failed",
                final_attempt=FetchAttempt(
                    url="https://example.com/page",
                    strategy="direct",
                    success=False,
                    status_code=500,
                ),
            ),
        ]

        output_path = tmp_path / "interview.json"
        result_path = generate_interview_file(failures, str(output_path))

        assert result_path == str(output_path)
        assert output_path.exists()

        # Verify valid JSON
        with open(output_path) as f:
            data = json.load(f)

        assert "title" in data
        assert "questions" in data
