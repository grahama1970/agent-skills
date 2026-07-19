"""Focused regressions for SciLLM authentication and fail-closed rendering."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import typer

import evidence_case
import runner
import storage
from candidate_qra import EvidenceCaseStore2
from runner import EvidenceCaseRunner, ScillmRenderError, resolve_scillm_api_key


def test_scillm_key_resolves_deployment_master_before_stale_proxy_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SCILLM_MASTER_KEY=active-master\n", encoding="utf-8")
    for name in ("SCILLM_API_KEY", "SCILLM_MASTER_KEY", "LITELLM_MASTER_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SCILLM_PROXY_KEY", "stale-proxy")
    monkeypatch.setenv("SCILLM_ENV_FILE", str(env_file))

    assert resolve_scillm_api_key() == "active-master"


def test_scillm_render_raises_infrastructure_error_instead_of_false_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCILLM_API_KEY", "test-key")

    def unauthorized(*_args: object, **_kwargs: object) -> None:
        request = httpx.Request("POST", "http://localhost:4001/v1/chat/completions")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("401 Unauthorized", request=request, response=response)

    monkeypatch.setattr(runner.httpx, "post", unauthorized)
    evidence_runner = EvidenceCaseRunner()

    with pytest.raises(ScillmRenderError, match="failed after 2 attempts"):
        evidence_runner._scillm_render(
            "Does CM0002 satisfy this requirement?",
            "satisfied",
            [{"canonical_id": "CM0002", "canonical_name": "Example"}],
            [],
            [],
            [],
            [{"control_id": "CM0002", "answer": "grounded"}],
            [],
        )


def test_scillm_render_returns_clarifying_question_instead_of_json_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCILLM_API_KEY", "test-key")
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "http://localhost:4001/v1/chat/completions"),
        json={
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"decision":"clarify","answer":"",'
                            '"clarifying_question":"Which interface is in scope?",'
                            '"suggested_rewrite":"","citations":[]}'
                        )
                    }
                }
            ]
        },
    )
    monkeypatch.setattr(runner.httpx, "post", lambda *_args, **_kwargs: response)

    def unexpected_collect(_answer: str) -> None:
        raise AssertionError("clarification text does not require citation extraction")

    monkeypatch.setattr(runner, "collect_entities", unexpected_collect)

    answer = EvidenceCaseRunner()._scillm_render(
        "Does CM0002 satisfy this requirement?",
        "not_satisfied",
        [{"canonical_id": "CM0002", "canonical_name": "COMSEC"}],
        [],
        [],
        [],
        [{"control_id": "CM0002", "answer": "grounded"}],
        [],
    )

    assert answer == "Which interface is in scope?"


def test_scillm_render_rejects_invalid_content_after_retry_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCILLM_API_KEY", "test-key")
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "http://localhost:4001/v1/chat/completions"),
        json={
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"decision":"answer","answer":"Unsupported",'
                            '"clarifying_question":"","suggested_rewrite":"",'
                            '"citations":["NOT-IN-EVIDENCE"]}'
                        )
                    }
                }
            ]
        },
    )
    monkeypatch.setattr(runner.httpx, "post", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(
        runner,
        "collect_entities",
        lambda _answer: {"resolved_entities": []},
    )

    with pytest.raises(ScillmRenderError, match="failed validation after 2 attempts"):
        EvidenceCaseRunner()._scillm_render(
            "Does CM0002 satisfy this requirement?",
            "satisfied",
            [{"canonical_id": "CM0002", "canonical_name": "COMSEC"}],
            [],
            [],
            [],
            [{"control_id": "CM0002", "answer": "grounded"}],
            [],
        )


def test_persist_case_returns_supplied_decomposition_without_name_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage, "_upsert_evidence_case", lambda _case: True)
    decomposition = {"question": "q", "given_components": [], "then_components": []}

    result = EvidenceCaseStore2().persist_case(
        question="q",
        category="compliance",
        verdict_state="satisfied",
        grade="A",
        score=1.0,
        gates=[{"gate": "scillm_synthesize", "passed": True}],
        evidence_items=[],
        answer="grounded",
        decomposition=decomposition,
    )

    assert result["decomposition"] == decomposition
    assert result["persisted"] is True


def test_cli_reports_scillm_failure_as_error_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise ScillmRenderError("SciLLM HTTP 401: Unauthorized")

    monkeypatch.setattr(EvidenceCaseRunner, "run", fail_run)

    with pytest.raises(typer.Exit) as exc_info:
        evidence_case.create(
            claim="Does CM0002 satisfy the requirement?",
            category="auto",
            strategies=0,
            quiet=True,
            json_output=True,
            test_only=False,
        )

    payload = capsys.readouterr().out
    assert exc_info.value.exit_code == 1
    assert '"state": "error"' in payload
    assert '"infrastructure_error": true' in payload
    assert '"state": "not_satisfied"' not in payload
