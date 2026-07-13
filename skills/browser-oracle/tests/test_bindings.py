from pathlib import Path

import pytest

from browser_oracle.bindings import BindingError
from browser_oracle.bindings import bind, load, rebind_by_exact_url, verify


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


def _surf(tmp_path: Path, rows: list[tuple[str, str, str]]) -> Path:
    surf = tmp_path / "surf"
    body = "".join(f"printf '{tid}\\t{title}\\t{url}\\n'\n" for tid, title, url in rows)
    surf.write_text("#!/usr/bin/env bash\n" + body)
    surf.chmod(0o755)
    return surf


def test_rebind_by_exact_url_updates_stale_tab_and_preserves_previous_binding(tmp_path: Path) -> None:
    surf = _surf(
        tmp_path,
        [("999", "ChatGPT", "https://chatgpt.com/c/11111111-2222-3333-4444-555555555555")],
    )
    bind(
        "demo-project",
        "webgpt",
        tab_id="12345",
        conversation_url="https://chatgpt.com/c/11111111-2222-3333-4444-555555555555/",
        manual=False,
        root=tmp_path,
    )

    result = rebind_by_exact_url("demo-project", "webgpt", surf_run=surf, root=tmp_path)

    assert result["previous_binding"]["tab_id"] == "12345"
    assert result["binding"]["tab_id"] == "999"
    loaded = load("demo-project", "webgpt", root=tmp_path)
    assert loaded is not None
    assert loaded.tab_id == "999"


def test_rebind_by_exact_url_rejects_ambiguous_matches(tmp_path: Path) -> None:
    url = "https://chatgpt.com/c/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    surf = _surf(tmp_path, [("1", "A", url), ("2", "B", url + "/")])
    bind("demo-project", "webgpt", tab_id="old", conversation_url=url, root=tmp_path)

    with pytest.raises(BindingError, match="ambiguous"):
        rebind_by_exact_url("demo-project", "webgpt", surf_run=surf, root=tmp_path)

    assert load("demo-project", "webgpt", root=tmp_path).tab_id == "old"  # type: ignore[union-attr]


def test_rebind_by_exact_url_rejects_manual_without_maintenance_authorization(tmp_path: Path) -> None:
    url = "https://chatgpt.com/c/reviewer"
    surf = _surf(tmp_path, [("new", "ChatGPT", url)])
    bind("demo-project", "webgpt", tab_id="old", conversation_url=url, manual=True, root=tmp_path)

    with pytest.raises(BindingError, match="maintenance authorization"):
        rebind_by_exact_url("demo-project", "webgpt", surf_run=surf, root=tmp_path)

    result = rebind_by_exact_url(
        "demo-project",
        "webgpt",
        surf_run=surf,
        root=tmp_path,
        maintenance_authorized=True,
    )
    assert result["previous_binding"]["tab_id"] == "old"
    assert result["binding"]["tab_id"] == "new"


def test_rebind_by_exact_url_rejects_missing_stored_project_url(tmp_path: Path) -> None:
    surf = _surf(tmp_path, [("new", "ChatGPT", "https://chatgpt.com/c/reviewer")])
    bind("demo-project", "webgpt", tab_id="old", root=tmp_path)

    with pytest.raises(BindingError, match="stored project URL"):
        rebind_by_exact_url("demo-project", "webgpt", surf_run=surf, root=tmp_path)
