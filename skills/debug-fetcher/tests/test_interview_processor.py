"""Tests for interview processor."""

import pytest
from debug_fetcher.interview_processor import (
    process_response,
    group_actions_by_type,
    _parse_credentials,
    _extract_url,
)
from debug_fetcher.memory_schema import RecoveryAction


class TestProcessResponse:
    """Tests for process_response function."""

    def test_process_credentials_response(self):
        """Test processing a credentials response from /interview."""
        response = {
            "completed": True,
            "responses": {
                "url_1234": {
                    "decision": "option_1",
                    "value": "I have credentials",
                    "other_text": "username: testuser, password: secret123",
                    "url": "https://example.com/protected",
                }
            },
        }

        actions = process_response(response)

        assert len(actions) == 1
        action = actions[0]
        assert action.action_type == "credentials"
        assert action.url == "https://example.com/protected"
        assert action.credentials is not None
        assert action.credentials.get("username") == "testuser"
        assert action.credentials.get("password") == "secret123"

    def test_process_mirror_response(self):
        """Test processing a mirror URL response."""
        response = {
            "completed": True,
            "responses": {
                "url_abcd": {
                    "decision": "option_2",
                    "value": "Try this mirror",
                    "other_text": "https://archive.org/web/20230101/https://example.com/page",
                    "url": "https://example.com/page",
                }
            },
        }

        actions = process_response(response)

        assert len(actions) == 1
        action = actions[0]
        assert action.action_type == "mirror"
        assert action.mirror_url == "https://archive.org/web/20230101/https://example.com/page"

    def test_process_manual_download_response(self):
        """Test processing a manual download response."""
        response = {
            "completed": True,
            "responses": {
                "url_efgh": {
                    "decision": "option_3",
                    "value": "I'll download manually",
                    "other_text": "/home/user/downloads/paper.pdf",
                    "url": "https://example.com/paper.pdf",
                }
            },
        }

        actions = process_response(response)

        assert len(actions) == 1
        action = actions[0]
        assert action.action_type == "manual_file"
        assert action.file_path == "/home/user/downloads/paper.pdf"

    def test_process_skip_response(self):
        """Test processing a skip response."""
        response = {
            "completed": True,
            "responses": {
                "url_ijkl": {
                    "decision": "option_4",
                    "value": "Skip it",
                    "other_text": "Not critical for my use case",
                    "url": "https://example.com/optional",
                }
            },
        }

        actions = process_response(response)

        assert len(actions) == 1
        action = actions[0]
        assert action.action_type == "skip"
        assert "Not critical" in action.notes

    def test_process_retry_response(self):
        """Test processing a retry later response."""
        response = {
            "completed": True,
            "responses": {
                "url_mnop": {
                    "decision": "option_5",
                    "value": "Retry later",
                    "other_text": "Server is temporarily down",
                    "url": "https://example.com/temp-unavailable",
                }
            },
        }

        actions = process_response(response)

        assert len(actions) == 1
        action = actions[0]
        assert action.action_type == "retry"
        assert action.retry_after == 3600  # Default 1 hour

    def test_process_custom_strategy_response(self):
        """Test processing a custom strategy suggestion."""
        response = {
            "completed": True,
            "responses": {
                "domain_qrst": {
                    "decision": "option_2",
                    "value": "Try different strategy",
                    "other_text": "Use a proxy - the site is geo-blocked",
                    "url": "https://geo-blocked.com/content",
                }
            },
        }

        actions = process_response(response)

        assert len(actions) == 1
        action = actions[0]
        assert action.action_type == "custom_strategy"
        assert "proxy" in action.notes.lower()

    def test_process_incomplete_response(self):
        """Test that incomplete responses return empty list."""
        response = {
            "completed": False,
            "responses": {},
        }

        actions = process_response(response)

        assert len(actions) == 0

    def test_process_multiple_responses(self):
        """Test processing multiple responses at once."""
        response = {
            "completed": True,
            "responses": {
                "url_1": {
                    "decision": "opt1",
                    "value": "Skip it",
                    "url": "https://example.com/1",
                },
                "url_2": {
                    "decision": "opt2",
                    "value": "I have credentials",
                    "other_text": "user / pass",
                    "url": "https://example.com/2",
                },
            },
        }

        actions = process_response(response)

        assert len(actions) == 2
        action_types = {a.action_type for a in actions}
        assert "skip" in action_types
        assert "credentials" in action_types


class TestParseCredentials:
    """Tests for credential parsing."""

    def test_parse_credentials_colon_format(self):
        """Test parsing 'username: xxx, password: yyy' format."""
        creds = _parse_credentials("username: testuser, password: secret123")

        assert creds["username"] == "testuser"
        assert creds["password"] == "secret123"

    def test_parse_credentials_equals_format(self):
        """Test parsing 'user=xxx pass=yyy' format."""
        creds = _parse_credentials("user=admin pass=hunter2")

        assert creds["username"] == "admin"
        assert creds["password"] == "hunter2"

    def test_parse_credentials_slash_format(self):
        """Test parsing 'xxx / yyy' format."""
        creds = _parse_credentials("myuser / mypassword")

        assert creds["username"] == "myuser"
        assert creds["password"] == "mypassword"

    def test_parse_credentials_unparseable(self):
        """Test that unparseable text returns hint."""
        creds = _parse_credentials("just some random text about login")

        assert "hint" in creds
        assert "random text" in creds["hint"]

    def test_parse_credentials_empty(self):
        """Test empty input returns None."""
        assert _parse_credentials("") is None
        assert _parse_credentials(None) is None


class TestExtractUrl:
    """Tests for URL extraction."""

    def test_extract_url_from_text(self):
        """Test extracting URL from mixed text."""
        url = _extract_url("Try this: https://archive.org/page instead")

        assert url == "https://archive.org/page"

    def test_extract_url_plain(self):
        """Test extracting plain URL."""
        url = _extract_url("https://example.com/path/to/file.pdf")

        assert url == "https://example.com/path/to/file.pdf"

    def test_extract_url_www_prefix(self):
        """Test that www. prefix gets https:// added."""
        url = _extract_url("www.example.com/page")

        assert url == "https://www.example.com/page"

    def test_extract_url_empty(self):
        """Test empty input returns None."""
        assert _extract_url("") is None
        assert _extract_url(None) is None
        assert _extract_url("no urls here") is None


class TestGroupActionsByType:
    """Tests for grouping utility."""

    def test_group_actions_by_type(self):
        """Test grouping actions by their type."""
        actions = [
            RecoveryAction(url="https://a.com", action_type="skip"),
            RecoveryAction(url="https://b.com", action_type="skip"),
            RecoveryAction(url="https://c.com", action_type="mirror", mirror_url="https://x.com"),
            RecoveryAction(url="https://d.com", action_type="credentials"),
        ]

        grouped = group_actions_by_type(actions)

        assert len(grouped["skip"]) == 2
        assert len(grouped["mirror"]) == 1
        assert len(grouped["credentials"]) == 1
