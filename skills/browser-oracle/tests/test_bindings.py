from pathlib import Path

import pytest

from browser_oracle.bindings import BindingError
from browser_oracle.bindings import bind, load, verify


def test_bind_and_load_roundtrip(tmp_path: Path) -> None:
    state = bind(
        "demo-project",
        "webgpt",
        human_name="Demo Project",
        tab_id="12345",
        conversation_url="https://chatgpt.com/c/demo",
        kde_desktop_index="2",
        manual=True,
        root=tmp_path,
    )
    loaded = load("demo-project", "webgpt", root=tmp_path)
    assert loaded is not None
    assert loaded.human_name == "Demo Project"
    assert loaded.tab_id == state.tab_id
    assert loaded.conversation_url == state.conversation_url
    assert loaded.kde_desktop_index == "2"
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
