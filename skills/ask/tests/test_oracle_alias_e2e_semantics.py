"""Regression tests for alias oracle end-to-end semantics."""

from typer.testing import CliRunner

import ask.ask as ask_module
import ask.ask_oracle as ask_oracle
import ask.model_aliases as aliases
from ask.run_state import AskRunState


def test_cli_exits_success_when_oracle_answers_without_memory_items(monkeypatch, tmp_path):
    monkeypatch.setattr(
        aliases,
        "fetch_opencode_go_models",
        lambda *_args, **_kwargs: [{"id": "opencode-go/kimi-k2.6", "supported": True, "key_configured": True}],
    )

    def fake_ask(**kwargs):
        return {
            "question": kwargs["question"],
            "scope": kwargs["scope"],
            "items": [],
            "bridges_found": [],
            "answer": "ASK_E2E_OK",
            "oracle": {
                "model": kwargs["oracle_model"],
                "backend": kwargs["oracle_backend"],
            },
        }

    monkeypatch.setattr(ask_module, "ask", fake_ask)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "oc",
            "kimi",
            "Reply",
            "with",
            "ASK_E2E_OK",
            "only.",
            "--ask-id",
            "oracle-answer-no-memory",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0


def test_oracle_synthesis_preserves_model_alias_metadata(monkeypatch):
    alias = {
        "provider_hint": "opencode",
        "family": "kimi",
        "resolved_model": "opencode-go/kimi-k2.6",
        "source": "live-opencode-go-models",
    }
    result = {
        "question": "Reply with ASK_E2E_OK only.",
        "scope": "ask-e2e",
        "items": [],
        "answer": "fallback",
        "oracle": {
            "model_alias": alias,
            "dogpile_mode": "auto",
            "dogpile_recommended": False,
        },
    }

    monkeypatch.setattr(ask_oracle, "_load_oracle_persona_profiles", lambda **_kwargs: {})
    monkeypatch.setattr(
        ask_oracle,
        "_run_oracle_iterations",
        lambda **_kwargs: ("ASK_E2E_OK", "moonshotai/kimi-k2.6-20260420", [{}]),
    )

    ask_oracle._apply_oracle_synthesis(
        result,
        k=1,
        model="opencode-go/kimi-k2.6",
        reasoning_effort="high",
        timeout=30,
        idle_timeout=300,
        heartbeat_interval=30,
        persona=None,
        consult_personas=[],
        peer=None,
        iterations=1,
        backend="scillm",
        persona_model=None,
        peer_model=None,
        persona_scope="personas",
    )

    assert result["answer"] == "ASK_E2E_OK"
    assert result["oracle"]["model_alias"] == alias


def test_runtime_finish_treats_oracle_answer_as_answered(tmp_path):
    run_state = AskRunState("oracle-answer-runtime", output_root=tmp_path)
    result = {
        "question": "Reply with ASK_E2E_OK only.",
        "scope": "ask-e2e",
        "items": [],
        "answer": "ASK_E2E_OK",
        "oracle": {
            "model": "opencode-go/kimi-k2.6",
            "model_served": "moonshotai/kimi-k2.6-20260420",
            "model_alias": {"provider_hint": "opencode", "family": "kimi"},
        },
        "auto_learned": False,
    }

    run_state.finish(result)

    status = run_state._read_current_status()
    assert status["state"] == "answered"
    assert status["result_summary"]["items_count"] == 0
    assert status["result_summary"]["answer_chars"] == len("ASK_E2E_OK")
    assert status["result_summary"]["oracle_model"] == "opencode-go/kimi-k2.6"
    assert status["result_summary"]["oracle_model_alias"]["family"] == "kimi"
