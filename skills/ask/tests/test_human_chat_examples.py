"""Sanity coverage for documented human `$ask` chat examples."""

import shlex
from pathlib import Path

from typer.testing import CliRunner

import ask.ask as ask_module


ASK_DIR = Path(__file__).resolve().parents[1]


def _load_ask_module():
    return ask_module


def _invoke_chat_prompt(prompt: str, monkeypatch):
    ask_module = _load_ask_module()
    captured = {}

    def fake_ask(**kwargs):
        captured.update(kwargs)
        return {"items": [{"solution": "ok"}], "answer": "ok", "bridges_found": []}

    monkeypatch.setattr(ask_module, "ask", fake_ask)
    normalized = prompt.strip()
    if normalized.startswith("$ask "):
        normalized = normalized[len("$ask "):]
    elif normalized.startswith("ask "):
        normalized = normalized[len("ask "):]
    result = CliRunner().invoke(ask_module.app, shlex.split(normalized))
    return result, captured


def test_documented_memory_prompt_stays_non_oracle(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask what do we know about the release checklist?",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "what do we know about the release checklist?"
    assert captured["oracle_model"] is None
    assert captured["roundtable"] is False
    assert captured["parallel_review"] is False


def test_documented_broad_current_prompt_uses_auto_persona_oracle(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask What is the state of Python packaging in 2026?",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "What is the state of Python packaging in 2026?"
    assert captured["oracle_model"] == "gpt-5.5"
    assert captured["oracle_reasoning"] == "high"
    assert captured["oracle_backend"] == "subagent-runner"
    assert captured["oracle_consult_personas"] == []
    assert captured["dogpile_mode"] == "auto"


def test_documented_persona_prompt_maps_to_subagent_oracle(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask Brandon what is the best way to review this API boundary?",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "what is the best way to review this API boundary?"
    assert captured["oracle_persona"] == "Brandon"
    assert captured["oracle_model"] == "gpt-5.5"
    assert captured["oracle_backend"] == "subagent-runner"


def test_documented_persona_about_prompt_maps_to_persona_oracle(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask Brandon persona about whether this retry design fails closed",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "whether this retry design fails closed"
    assert captured["oracle_persona"] == "Brandon"
    assert captured["oracle_model"] == "gpt-5.5"
    assert captured["oracle_backend"] == "subagent-runner"


def test_documented_peer_prompt_maps_to_two_turn_deliberation(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask Brandon ask Margaret where are we weak?",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "where are we weak?"
    assert captured["oracle_persona"] == "Brandon"
    assert captured["oracle_peer"] == "Margaret"
    assert captured["oracle_iterations"] == 2
    assert captured["oracle_backend"] == "subagent-runner"


def test_documented_roundtable_prompt_maps_to_protocol(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask Brandon, Margaret, and Jennifer personas to roundtable about the topic: Should this service use retries or queues?",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "Should this service use retries or queues?"
    assert captured["roundtable"] is True
    assert captured["roundtable_personas"] == "Brandon,Margaret,Jennifer"
    assert captured["oracle_model"] == "gpt-5.5"
    assert captured["oracle_backend"] == "subagent-runner"
    assert captured["dogpile_mode"] == "auto"


def test_documented_role_roundtable_prompt_maps_to_protocol(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask roundtable with Brandon:failure_mode, Margaret:evidence_auditor, Jennifer:complexity_minimizer on this architecture",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "this architecture"
    assert captured["roundtable"] is True
    assert captured["roundtable_personas"] == "Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer"
    assert captured["oracle_backend"] == "subagent-runner"


def test_documented_parallel_review_prompt_maps_to_parallel_review(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask run 3 parallel adversarial reviewers on this implementation",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "this implementation"
    assert captured["parallel_review"] is True
    assert captured["parallel_reviewers"] == 3
    assert captured["oracle_model"] == "gpt-5.5"
    assert captured["oracle_backend"] == "subagent-runner"


def test_documented_parallel_focus_prompt_maps_focus_labels(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask launch 5 parallel reviewers for correctness, tests, security, maintainability, and UX",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["parallel_review"] is True
    assert captured["parallel_reviewers"] == 5
    assert captured["parallel_review_focus"] == "correctness,tests,security,maintainability,UX"


def test_documented_deep_review_prompt_maps_to_deep_review(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask deep review this implementation --deep-review-target src/ask/ask.py",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["deep_review"] is True
    assert captured["deep_review_target"] == "src/ask/ask.py"
    assert captured["oracle_reasoning"] == "xhigh"
    assert captured["oracle_backend"] == "subagent-runner"


def test_documented_chat_examples_file_keeps_required_categories():
    examples = (ASK_DIR / "docs" / "HUMAN_CHAT_EXAMPLES.md").read_text()
    for required in [
        "$ask what do we know about the release checklist?",
        "$ask Brandon persona about whether this retry design fails closed",
        "$ask Brandon, Margaret, and Jennifer personas to roundtable about the topic: Should this service use retries or queues?",
        "$ask run 3 parallel adversarial reviewers on this implementation",
        "$ask deep review this implementation --deep-review-target src/ask/ask.py",
        "$ask oracle with a 10 minute timeout on this architecture decision",
        "Wrong: $ask run oracle for these 100 questions",
    ]:
        assert required in examples
