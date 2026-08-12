"""Tests for public-safe Memory and code evidence filtering."""

from live_evidence.config import InterviewProfile
from live_evidence.retrieval.memory import _code_item_allowed, _memory_item_allowed


def profile() -> InterviewProfile:
    return InterviewProfile(
        name="policy-test",
        repo_priorities=["tau", "agent-skills", "sparta"],
    )


def test_explicit_private_memory_is_rejected() -> None:
    assert _memory_item_allowed(
        {"problem": "client detail", "tags": ["private"], "_key": "x"},
        profile(),
    ) is False


def test_public_itar_summary_is_not_rejected_by_generic_topic_tag() -> None:
    assert _memory_item_allowed(
        {"problem": "Public ITAR experience summary", "tags": ["ITAR"], "_key": "x"},
        profile(),
    ) is True


def test_code_results_are_limited_to_declared_repositories() -> None:
    assert _code_item_allowed({"repository": "tau"}, profile()) is True
    assert _code_item_allowed({"repository": "unrelated-private-client"}, profile()) is False
