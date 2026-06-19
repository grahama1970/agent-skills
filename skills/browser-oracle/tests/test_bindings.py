from pathlib import Path

import pytest

from browser_oracle.bindings import BindingError, DuplicateConversationUrlError
from browser_oracle.bindings import bind, load, open_tab_and_bind, reconcile_bindings, verify


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


def test_reconcile_reports_ready_live_binding(tmp_path: Path) -> None:
    surf = tmp_path / "surf"
    surf.write_text(
        "#!/usr/bin/env bash\n"
        "printf '12345\\tChatGPT - Demo\\thttps://chatgpt.com/c/demo\\n'\n"
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

    rows = reconcile_bindings("webgpt", surf_run=surf, root=tmp_path)

    assert len(rows) == 1
    assert rows[0].status == "ready"
    assert rows[0].live_found is True
    assert rows[0].live_url == "https://chatgpt.com/c/demo"


def test_reconcile_reports_duplicate_conversation_url(tmp_path: Path) -> None:
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

    rows = reconcile_bindings("webgpt", surf_run=surf, root=tmp_path)

    assert rows[0].status == "duplicate_conversation_url"
    assert rows[0].issues == ["duplicate_conversation_url"]
    assert rows[0].duplicate_url_tab_ids == ["67890"]


def test_reconcile_can_prune_missing_live_tab(tmp_path: Path) -> None:
    surf = tmp_path / "surf"
    surf.write_text("#!/usr/bin/env bash\nprintf ''\n")
    surf.chmod(0o755)
    bind(
        "demo-project",
        "webgpt",
        tab_id="12345",
        conversation_url="https://chatgpt.com/c/demo",
        manual=True,
        root=tmp_path,
    )

    rows = reconcile_bindings("webgpt", prune_missing=True, surf_run=surf, root=tmp_path)

    assert rows[0].status == "missing_live_tab"
    assert rows[0].pruned is True
    assert load("demo-project", "webgpt", root=tmp_path) is None


def test_reconcile_reports_url_mismatch_without_mutating(tmp_path: Path) -> None:
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

    rows = reconcile_bindings("webgpt", surf_run=surf, root=tmp_path)

    assert rows[0].status == "url_mismatch"
    assert rows[0].issues == ["url_mismatch"]
    assert load("demo-project", "webgpt", root=tmp_path) is not None


def test_open_tab_and_bind_parses_created_tab_id(tmp_path: Path) -> None:
    surf = tmp_path / "surf"
    surf.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == \"tab.new\" ]]; then\n"
        "  printf 'Created tab 67890: %s\\n' \"$2\"\n"
        "else\n"
        "  exit 2\n"
        "fi\n"
    )
    surf.chmod(0o755)

    state = open_tab_and_bind(
        "demo-project",
        "webgpt",
        url="https://chatgpt.com/",
        surf_run=surf,
        root=tmp_path,
    )

    assert state.tab_id == "67890"
    assert state.conversation_url == "https://chatgpt.com/"
    assert state.bound_manually is True
