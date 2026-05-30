"""Sanity coverage for documented human `$ask` chat examples."""

import json
import shlex
from pathlib import Path

from typer.testing import CliRunner

import ask.ask as ask_module
import ask.model_aliases as aliases


ASK_DIR = Path(__file__).resolve().parents[1]
OPENCODE_MODELS = [
    {"id": "opencode-go/kimi-k2.6", "supported": True, "key_configured": True, "input": {"text": True, "image": True, "pdf": False}},
    {"id": "opencode-go/qwen3.6-plus", "supported": True, "key_configured": True, "input": {"text": True, "image": False, "pdf": False}},
]


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


def test_documented_spaced_opencode_model_shorthand_uses_latest_live_model(monkeypatch):
    monkeypatch.setattr(aliases, "fetch_opencode_go_models", lambda *_args, **_kwargs: OPENCODE_MODELS)

    result, captured = _invoke_chat_prompt(
        "$ask oc kimi explain this design tradeoff",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "explain this design tradeoff"
    assert captured["oracle_model"] == "opencode-go/kimi-k2.6"
    assert captured["oracle_backend"] == "scillm"
    assert captured["oracle_model_alias"]["provider_hint"] == "opencode"
    assert captured["oracle_model_alias"]["source"] == "live-opencode-go-models"
    assert captured["oracle_model_alias"]["input_capabilities"]["image"] is True


def test_documented_hyphenated_opencode_model_shorthand_uses_latest_live_model(monkeypatch):
    monkeypatch.setattr(aliases, "fetch_opencode_go_models", lambda *_args, **_kwargs: OPENCODE_MODELS)

    result, captured = _invoke_chat_prompt(
        "$ask oc-qwen compare these options",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "compare these options"
    assert captured["oracle_model"] == "opencode-go/qwen3.6-plus"
    assert captured["oracle_backend"] == "scillm"


def test_documented_chutes_model_shorthand_uses_configured_alias(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask chutes kimi explain this design tradeoff",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "explain this design tradeoff"
    assert captured["oracle_model"] == "chutes-kimi"
    assert captured["oracle_backend"] == "scillm"
    assert captured["oracle_model_alias"]["provider_hint"] == "chutes"


def test_documented_hyphenated_chutes_model_shorthand_uses_configured_alias(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask chutes-kimi explain this design tradeoff",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "explain this design tradeoff"
    assert captured["oracle_model"] == "chutes-kimi"
    assert captured["oracle_backend"] == "scillm"


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


def test_missing_lowercase_roundtable_personas_clarify_before_memory(monkeypatch, tmp_path):
    ask_module = _load_ask_module()

    def fail_ask(**_kwargs):
        raise AssertionError("missing persona clarification should not call memory/oracle ask")

    monkeypatch.setattr(ask_module, "ask", fail_ask)
    result = CliRunner().invoke(
        ask_module.app,
        [
            "Have",
            "the",
            "tester",
            "and",
            "maintainer",
            "roundtable",
            "the",
            "cache",
            "invalidation",
            "migration",
            "risk",
            "for",
            "cross-region",
            "writes.",
            "--ask-id",
            "missing-personas",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    attention = payload["needs_attention"]
    assert attention["reason"] == "missing_roundtable_personas"
    assert attention["safe_default"] == "clarify_before_roundtable"
    assert attention["missing_personas"] == ["tester", "maintainer"]
    assert "/interview" in attention["suggested_skills"]
    assert "/create-persona" in attention["suggested_skills"]


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


def test_documented_argue_prompt_maps_to_scillm_argue(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask argue whether we should ship this change",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["question"] == "we should ship this change"
    assert captured["argue"] is True
    assert captured["oracle_model"] == "gpt-5.5"
    assert captured["oracle_backend"] == "scillm"


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
    assert captured["oracle_backend"] == "scillm"




def test_documented_webgpt_prompt_maps_to_webgpt_oracle(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask webgpt review /tmp/review-bundle.md",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["oracle_backend"] == "webgpt"
    assert captured["oracle_model"] == "webgpt"
    assert "review-bundle" in captured["question"]


def test_documented_webgemini_prompt_maps_to_webgemini_oracle(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask webgemini review /tmp/review-bundle.md",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["oracle_backend"] == "webgemini"
    assert captured["oracle_model"] == "webgemini"


def test_documented_webperplexity_prompt_maps_to_webperplexity_oracle(monkeypatch):
    result, captured = _invoke_chat_prompt(
        "$ask webperplexity summarize the current state of space-based cybersecurity in 2026",
        monkeypatch,
    )

    assert result.exit_code == 0
    assert captured["oracle_backend"] == "webperplexity"
    assert captured["oracle_model"] == "webperplexity"


def test_documented_chat_examples_file_keeps_required_categories():
    examples = (ASK_DIR / "docs" / "HUMAN_CHAT_EXAMPLES.md").read_text()
    for required in [
        "$ask what do we know about the release checklist?",
        "$ask Brandon persona about whether this retry design fails closed",
        "$ask Brandon, Margaret, and Jennifer personas to roundtable about the topic: Should this service use retries or queues?",
        "$ask run 3 parallel adversarial reviewers on this implementation",
        "$ask argue whether we should ship this change",
        "$ask deep review this implementation --deep-review-target src/ask/ask.py",
        "$ask oracle with a 10 minute timeout on this architecture decision",
        "$ask oc kimi explain this design tradeoff",
        "$ask oc-qwen compare these options",
        "$ask chutes kimi explain this design tradeoff",
        "$ask chutes-kimi explain this design tradeoff",
        "Wrong: $ask run oracle for these 100 questions",
        "sparta_preflight",
        "mustard",
        "CM0001",
        "needs_attention",
        "$ask webgpt review /tmp/review-bundle.md",
        "$ask webgemini review /tmp/review-bundle.md",
        "$ask webperplexity summarize the current state of space-based cybersecurity in 2026",
        "Wrong: $ask webgpt review /tmp/bundle/REVIEW_REQUEST.md",
    ]:
        assert required in examples
