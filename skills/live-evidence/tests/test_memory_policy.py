"""Tests for public-safe Memory and code evidence filtering."""

from pathlib import Path

import pytest

from live_evidence.config import AppSettings
from live_evidence.config import InterviewProfile
from live_evidence.retrieval import memory as memory_retrieval
from live_evidence.retrieval.memory import MemoryEvidenceClient
from live_evidence.retrieval.memory import _code_item_allowed, _memory_item_allowed
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


@pytest.mark.asyncio
async def test_memory_http_clients_ignore_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
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

    assert await client._intent_profile("What is dependency confusion?") == "procedural_memory"
    assert await client._post_recall("What is dependency confusion?", "procedural_memory") == {
        "found": True,
        "items": [],
        "recall_profile": "procedural_memory",
    }
    assert seen == [False, False]


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
