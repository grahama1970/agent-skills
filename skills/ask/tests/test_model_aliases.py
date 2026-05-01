"""Tests for `$ask` provider-family model shorthand."""

import pytest

from ask.model_aliases import (
    resolve_chutes_model,
    resolve_model_alias_route,
    select_opencode_model,
)


OPENCODE_MODELS = [
    {"id": "opencode-go/kimi-k2.5", "supported": True, "key_configured": True},
    {"id": "opencode-go/kimi-k2.6", "supported": True, "key_configured": True},
    {"id": "opencode-go/qwen3.5-plus", "supported": True, "key_configured": True},
    {"id": "opencode-go/qwen3.6-plus", "supported": True, "key_configured": True},
    {"id": "opencode-go/deepseek-v4-flash", "supported": True, "key_configured": True},
    {"id": "opencode-go/deepseek-v4-pro", "supported": True, "key_configured": True},
]


def test_select_opencode_model_prefers_latest_supported_family_model():
    assert select_opencode_model("kimi", OPENCODE_MODELS) == "opencode-go/kimi-k2.6"
    assert select_opencode_model("qwen", OPENCODE_MODELS) == "opencode-go/qwen3.6-plus"
    assert select_opencode_model("deepseek", OPENCODE_MODELS) == "opencode-go/deepseek-v4-pro"


def test_select_opencode_model_ignores_unconfigured_models():
    models = [
        {"id": "opencode-go/kimi-k2.6", "supported": True, "key_configured": False},
        {"id": "opencode-go/kimi-k2.5", "supported": True, "key_configured": True},
    ]

    assert select_opencode_model("kimi", models) == "opencode-go/kimi-k2.5"


def test_resolve_model_alias_route_accepts_spaced_opencode_alias(monkeypatch):
    import ask.model_aliases as aliases

    monkeypatch.setattr(aliases, "fetch_opencode_go_models", lambda *_args, **_kwargs: OPENCODE_MODELS)

    route = resolve_model_alias_route(
        ["oc", "kimi", "explain", "this"],
        scillm_base_url="http://scillm.test",
        scillm_api_key="test",
    )

    assert route is not None
    assert route.provider_hint == "opencode"
    assert route.resolved_model == "opencode-go/kimi-k2.6"
    assert route.question == "explain this"
    assert route.source == "live-opencode-go-models"


def test_resolve_model_alias_route_accepts_hyphenated_alias(monkeypatch):
    import ask.model_aliases as aliases

    monkeypatch.setattr(aliases, "fetch_opencode_go_models", lambda *_args, **_kwargs: OPENCODE_MODELS)

    route = resolve_model_alias_route(
        ["oc-qwen", "compare", "options"],
        scillm_base_url="http://scillm.test",
        scillm_api_key="test",
    )

    assert route is not None
    assert route.resolved_model == "opencode-go/qwen3.6-plus"
    assert route.question == "compare options"


def test_resolve_model_alias_route_accepts_chutes_aliases():
    spaced = resolve_model_alias_route(
        ["chutes", "kimi", "summarize", "this"],
        scillm_base_url="http://scillm.test",
        scillm_api_key="test",
    )
    hyphenated = resolve_model_alias_route(
        ["chutes-kimi", "summarize", "this"],
        scillm_base_url="http://scillm.test",
        scillm_api_key="test",
    )

    assert spaced is not None
    assert hyphenated is not None
    assert spaced.resolved_model == "text-kimi"
    assert hyphenated.resolved_model == "text-kimi"


def test_resolve_chutes_model_accepts_exact_catalog_model():
    assert resolve_chutes_model("qwen", exact_model="Qwen/Qwen3-30B-A3B") == "Qwen/Qwen3-30B-A3B"


def test_model_alias_requires_question_after_shorthand(monkeypatch):
    import ask.model_aliases as aliases

    monkeypatch.setattr(aliases, "fetch_opencode_go_models", lambda *_args, **_kwargs: OPENCODE_MODELS)

    with pytest.raises(ValueError, match="requires a question"):
        resolve_model_alias_route(["oc", "kimi"], scillm_base_url="http://scillm.test", scillm_api_key="test")
