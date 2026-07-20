from pathlib import Path

import pytest

from browser_oracle.bindings import BindingError
from browser_oracle.bindings import bind, load, verify
from browser_oracle.config import project_root


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


def test_webclaude_has_isolated_project_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    override = tmp_path / "claude-bindings"
    monkeypatch.setenv("BROWSER_ORACLE_WEBCLAUDE_PROJECT_ROOT", str(override))

    assert project_root("webclaude") == override


def test_webclaude_bind_and_verify_roundtrip(tmp_path: Path) -> None:
    claude_url = "https://claude.ai/chat/3cdf38d5-2c6c-4727-b5b9-eb7fd95f5146"
    surf = tmp_path / "surf"
    surf.write_text("#!/usr/bin/env bash\n" f"printf '837359291\\tPing test - Claude\\t{claude_url}\\n'\n")
    surf.chmod(0o755)

    state = bind(
        "webclaude",
        "webclaude",
        tab_id="837359291",
        conversation_url=claude_url,
        manual=True,
        root=tmp_path,
    )
    verified = verify("webclaude", "webclaude", surf_run=surf, root=tmp_path)

    assert state.backend == "webclaude"
    assert verified.tab_id == "837359291"
    assert verified.conversation_url == claude_url
    assert verified.last_verified_at is not None
