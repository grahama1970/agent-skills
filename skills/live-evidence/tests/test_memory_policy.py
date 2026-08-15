"""Tests for public-safe Memory and code evidence filtering."""

import asyncio
from pathlib import Path

import pytest

from live_evidence.config import AppSettings
from live_evidence.config import InterviewProfile
from live_evidence.models import EvidenceSource, Freshness, RetrievalLane
from live_evidence.retrieval import memory as memory_retrieval
from live_evidence.retrieval.memory import MemoryEvidenceClient
from live_evidence.retrieval.memory import _code_item_allowed, _memory_item_allowed
from live_evidence.retrieval.memory import _code_queries
from live_evidence.retrieval.memory import _dedupe_sources
from live_evidence.retrieval.memory import _filtered_code_repositories
from live_evidence.retrieval.memory import _memory_items_to_sources
from live_evidence.retrieval.memory import _select_code_items
from live_evidence.retrieval.memory import _subprocess_env


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


def test_code_queries_keep_exact_identifier_before_profile_phrases() -> None:
    interview_profile = InterviewProfile(
        name="youtube-eval",
        watch_terms=["invalid parentheses", "remove"],
        project_aliases={"youtube-eval": ["invalid parentheses", "stack solution"]},
        repo_priorities=["youtube-eval"],
    )

    queries = _code_queries(
        "removeInvalidParentheses invalid parentheses minimum removals",
        interview_profile,
    )

    assert queries == ["removeInvalidParentheses", "invalid", "parentheses"]


def test_current_code_source_suppresses_legacy_duplicate() -> None:
    current = EvidenceSource(
        lane=RetrievalLane.CODE,
        label="removeInvalidParentheses",
        excerpt="export function removeInvalidParentheses(input) { return input; }",
        score=0.94,
        freshness=Freshness.CURRENT,
        repository="youtube-eval",
        path="remove_invalid_parentheses.js",
        metadata={"symbol_id": "canonical"},
    )
    legacy = EvidenceSource(
        lane=RetrievalLane.CODE,
        label="removeInvalidParentheses",
        excerpt="Indexed symbol removeInvalidParentheses in remove_invalid_parentheses.js",
        score=0.74,
        freshness=Freshness.UNKNOWN,
        repository="youtube-eval",
        path="remove_invalid_parentheses.js",
        metadata={"symbol_id": "legacy"},
    )

    assert _dedupe_sources([legacy, current]) == [current]


def test_code_item_selection_prefers_canonical_rows_before_legacy_budget() -> None:
    canonical = {
        "repository": "youtube-eval",
        "path": "newly_written_solution.js",
        "qualified_name": "liveEvidenceNewlyWrittenRemoveInvalidParentheses",
        "symbol_id": "canonical-main",
        "code_index_id": "ci_current",
        "file_id": "cf_current",
        "coverage_complete": True,
        "branch": "main",
    }
    legacy = {
        **canonical,
        "symbol_id": "legacy",
        "code_index_id": None,
        "file_id": None,
        "coverage_complete": None,
        "branch": "unknown",
    }
    helper = {
        "repository": "youtube-eval",
        "path": "newly_written_solution.js",
        "qualified_name": "countMinimumInvalidParentheses",
        "symbol_id": "helper",
        "code_index_id": "ci_current",
        "file_id": "cf_current",
        "coverage_complete": True,
        "branch": "main",
    }

    selected = _select_code_items(
        [legacy, canonical, helper],
        InterviewProfile(name="youtube-eval", repo_priorities=["youtube-eval"]),
        limit=2,
    )

    assert [item["symbol_id"] for item in selected] == ["canonical-main", "helper"]


def test_memory_http_clients_ignore_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bool | None] = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"found": True, "items": [], "recall_profile": "procedural_memory"}

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            seen.append(kwargs.get("trust_env"))

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(memory_retrieval.httpx, "AsyncClient", FakeAsyncClient)
    settings = AppSettings(
        skill_root=Path("/tmp/live-evidence"),
        data_dir=Path("/tmp/live-evidence-data"),
        profile_path=Path("/tmp/live-evidence-profile.yaml"),
        memory_url="http://127.0.0.1:8601",
    )
    client = MemoryEvidenceClient(settings, profile())

    assert asyncio.run(client._intent_profile("What is dependency confusion?")) == "procedural_memory"
    assert asyncio.run(client._post_recall("What is dependency confusion?", "procedural_memory")) == {
        "found": True,
        "items": [],
        "recall_profile": "procedural_memory",
    }
    assert seen == [False, False]


def test_memory_intent_oserror_degrades_to_indexed_code(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise FileNotFoundError("/missing/ca-bundle.pem")

    monkeypatch.setattr(memory_retrieval.httpx, "AsyncClient", BrokenAsyncClient)
    settings = AppSettings(
        skill_root=Path("/tmp/live-evidence"),
        data_dir=Path("/tmp/live-evidence-data"),
        profile_path=Path("/tmp/live-evidence-profile.yaml"),
        memory_url="http://127.0.0.1:8601",
    )
    client = MemoryEvidenceClient(settings, profile())
    source = EvidenceSource(
        lane=RetrievalLane.CODE,
        label="dependency_confusion_guard",
        excerpt="Indexed source fallback remains available",
        score=0.74,
        freshness=Freshness.UNKNOWN,
        repository="agent-skills",
        path="skills/live-evidence/example.py",
    )

    async def fake_code_search(query: str) -> tuple[list[EvidenceSource], str]:
        return [source], "Indexed code 1 across 1 term(s)"

    monkeypatch.setattr(client, "_code_search", fake_code_search)

    assert asyncio.run(client._intent_profile("What is dependency confusion?")) is None
    result = asyncio.run(client.retrieve("What is dependency confusion?"))

    assert result.ok is True
    assert result.sources == [source]
    assert "intent=degraded" in result.detail
    assert "Indexed code 1" in result.detail


def test_memory_subprocess_env_does_not_inherit_live_evidence_venv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/live-evidence-venv")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/tmp/live-evidence-uv-env")
    monkeypatch.setenv("PYTHONPATH", "/tmp/live-evidence-src")

    env = _subprocess_env()

    assert "VIRTUAL_ENV" not in env
    assert "UV_PROJECT_ENVIRONMENT" not in env
    assert "PYTHONPATH" not in env
    assert env["UV_LINK_MODE"] == "copy"


def test_memory_recall_found_false_is_optional_no_evidence() -> None:
    sources = _memory_items_to_sources(
        {
            "found": False,
            "should_scan": True,
            "confidence": 0.0,
            "items": [
                {
                    "_key": "lesson-unrelated",
                    "problem": "Unrelated result",
                    "solution": "This should not become a visible evidence source.",
                    "score": 1.0,
                }
            ],
        },
        "procedural_memory",
        profile(),
    )

    assert sources == []


def test_memory_recall_low_confidence_is_optional_no_evidence() -> None:
    sources = _memory_items_to_sources(
        {
            "found": True,
            "should_scan": True,
            "confidence": 0.21,
            "items": [
                {
                    "_key": "lesson-weak",
                    "problem": "Weak result",
                    "solution": "Low-confidence Memory is optional context, not support.",
                    "score": 0.9,
                }
            ],
        },
        "procedural_memory",
        profile(),
    )

    assert sources == []


def test_memory_recall_confident_hit_can_be_evidence() -> None:
    sources = _memory_items_to_sources(
        {
            "found": True,
            "should_scan": False,
            "confidence": 0.83,
            "items": [
                {
                    "_key": "lesson-live-evidence-memory-optional",
                    "problem": "Live Evidence Memory fallback",
                    "solution": "Treat Memory recall as deterministic optional context.",
                    "score": 0.83,
                    "tags": ["live-evidence"],
                }
            ],
        },
        "procedural_memory",
        profile(),
    )

    assert len(sources) == 1
    assert sources[0].metadata["_key"] == "lesson-live-evidence-memory-optional"


def test_memory_code_symbol_items_become_code_sources_when_repo_allowed() -> None:
    sources = _memory_items_to_sources(
        {
            "found": True,
            "should_scan": False,
            "confidence": 0.91,
            "items": [
                {
                    "_key": "cs-remove-invalid-parens",
                    "type": "code_context",
                    "symbol_id": "cs-remove-invalid-parens",
                    "qualified_name": "removeInvalidParentheses",
                    "symbol_kind": "function",
                    "repo": "youtube-eval",
                    "branch": "main",
                    "path": "remove_invalid_parentheses.js",
                    "start_line": 1,
                    "end_line": 11,
                    "retrieval_text": "Repository: youtube-eval\nQualified name: removeInvalidParentheses",
                }
            ],
        },
        "temporal_project_state",
        InterviewProfile(name="youtube-eval", repo_priorities=["youtube-eval"]),
    )

    assert len(sources) == 1
    assert sources[0].lane is RetrievalLane.CODE
    assert sources[0].repository == "youtube-eval"
    assert sources[0].label == "removeInvalidParentheses"
    assert "Repository: youtube-eval" in sources[0].excerpt


def test_filtered_code_repositories_reports_profile_mismatch() -> None:
    rejected = _filtered_code_repositories(
        [
            {"repository": "youtube-eval", "qualified_name": "removeInvalidParentheses"},
            {"repository": "agent-skills", "qualified_name": "LiveEvidence"},
        ],
        InterviewProfile(name="youtube-live", repo_priorities=["youtube-live", "agent-skills"]),
    )

    assert rejected == {"youtube-eval"}
