from pathlib import Path

import pytest

from browser_oracle.bindings import BindingError, DuplicateConversationUrlError
from browser_oracle.bindings import bind, load, verify


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


def test_verify_fails_on_duplicate_conversation_url_without_mutating(tmp_path: Path) -> None:
    surf = tmp_path / "surf"
    surf.write_text(
        "#!/usr/bin/env bash\n"
        "printf '12345\\tChatGPT - Demo\\thttps://chatgpt.com/c/demo\\n'\n"
        "printf '67890\\tChatGPT - Duplicate\\thttps://chatgpt.com/c/demo\\n'\n"
    )
    surf.chmod(0o755)
    bind(
        "demo-project",
        "webgpt",
        tab_id="12345",
        conversation_url="https://chatgpt.com/c/demo",
        manual=True,
        root=tmp_path,
    )

    with pytest.raises(DuplicateConversationUrlError, match="same conversation URL"):
        verify("demo-project", "webgpt", surf_run=surf, root=tmp_path)

    loaded = load("demo-project", "webgpt", root=tmp_path)
    assert loaded is not None
    assert loaded.conversation_url == "https://chatgpt.com/c/demo"
