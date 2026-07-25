from pathlib import Path

import pytest

from browser_oracle.bindings import BindingError
from browser_oracle.bindings import bind, load, verify
from browser_oracle.config import SUPPORTED_BACKENDS, project_root


def test_bind_and_load_roundtrip(tmp_path: Path) -> None:
    state = bind(
        "demo-project",
        "webgpt",
        tab_id="12345",
        conversation_url="https://chatgpt.com/c/demo",
        manual=True,
        root=tmp_path,
    )
    loaded = load("demo-project", "webgpt", root=tmp_path)
    assert loaded is not None
    assert loaded.tab_id == state.tab_id
    assert loaded.conversation_url == state.conversation_url
    assert loaded.bound_manually is True


def test_webclaude_backend_uses_claude_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSER_ORACLE_WEBCLAUDE_PROJECT_ROOT", str(tmp_path))

    assert "webclaude" in SUPPORTED_BACKENDS
    assert project_root("webclaude") == tmp_path

    bind(
        "claude-review",
        "webclaude",
        tab_id="837360812",
        conversation_url="https://claude.ai/chat/example",
        manual=True,
    )
    loaded = load("claude-review", "webclaude")
    assert loaded is not None
    assert loaded.backend == "webclaude"
    assert loaded.tab_id == "837360812"


def test_webgrok_backend_uses_grok_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSER_ORACLE_WEBGROK_PROJECT_ROOT", str(tmp_path))

    assert "webgrok" in SUPPORTED_BACKENDS
    assert project_root("webgrok") == tmp_path

    bind(
        "grok-review",
        "webgrok",
        tab_id="837361111",
        conversation_url="https://grok.com/",
        manual=True,
    )
    loaded = load("grok-review", "webgrok")
    assert loaded is not None
    assert loaded.backend == "webgrok"
    assert loaded.tab_id == "837361111"


def test_verify_manual_binding_fails_on_url_mismatch_without_mutating(tmp_path: Path) -> None:
    surf = tmp_path / "surf"
    surf.write_text(
        "#!/usr/bin/env bash\n"
        "printf '12345\\tChatGPT - Wrong\\thttps://chatgpt.com/c/wrong\\n'\n"
    )
    surf.chmod(0o755)
    bind(
        "demo-project",
        "webgpt",
        tab_id="12345",
        conversation_url="https://chatgpt.com/c/right",
        manual=True,
        root=tmp_path,
    )

    with pytest.raises(BindingError, match="different URL"):
        verify("demo-project", "webgpt", surf_run=surf, root=tmp_path)

    loaded = load("demo-project", "webgpt", root=tmp_path)
    assert loaded is not None
    assert loaded.conversation_url == "https://chatgpt.com/c/right"
