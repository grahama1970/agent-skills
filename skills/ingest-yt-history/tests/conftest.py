"""
Pytest configuration for ingest-yt-history tests.
"""
import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: requires external services (ArangoDB, APIs)")
    config.addinivalue_line("markers", "llm: requires LLM API calls")
