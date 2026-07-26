import json
from pathlib import Path

from typer.testing import CliRunner

from browser_oracle.bindings import bind, load
from browser_oracle.cli import app


runner = CliRunner()


def _fake_surf(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_reconcile_reports_missing_live_tab_with_url_match(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_ORACLE_WEBGPT_PROJECT_ROOT", str(tmp_path / "bindings"))
    surf = _fake_surf(
        tmp_path / "surf-run.sh",
        """
case "$*" in
  "tab.list --json")
    printf '[{"id":456,"title":"ChatGPT","url":"https://chatgpt.com/c/demo"}]\\n'
    ;;
  *)
    echo "unexpected surf command: $*" >&2
    exit 99
    ;;
esac
""",
    )
    monkeypatch.setenv("BROWSER_ORACLE_SURF_RUN", str(surf))
    bind(
        "demo",
        "webgpt",
        tab_id="123",
        conversation_url="https://chatgpt.com/c/demo",
        manual=True,
    )

    result = runner.invoke(app, ["reconcile", "--backend", "webgpt", "--project", "demo", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    row = payload["rows"][0]
    assert row["status"] == "missing_live_tab"
    assert row["stored_tab_id"] == "123"
    assert row["url_matches"][0]["tab_id"] == "456"
    assert load("demo", "webgpt").tab_id == "123"


def test_open_bind_opens_window_and_persists_new_tab(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_ORACLE_WEBGPT_PROJECT_ROOT", str(tmp_path / "bindings"))
    calls = tmp_path / "calls.log"
    surf = _fake_surf(
        tmp_path / "surf-run.sh",
        f"""
printf '%s\\n' "$*" >> {str(calls)!r}
case "$*" in
  "window.new https://chatgpt.com/c/demo --json --unfocused")
    printf '{{"success":true,"windowId":99,"tabId":456}}\\n'
    ;;
  *)
    echo "unexpected surf command: $*" >&2
    exit 99
    ;;
esac
""",
    )
    monkeypatch.setenv("BROWSER_ORACLE_SURF_RUN", str(surf))

    result = runner.invoke(
        app,
        ["open-bind", "demo", "--backend", "webgpt", "--url", "https://chatgpt.com/c/demo", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "open_bound"
    assert payload["tab_id"] == "456"
    assert payload["conversation_url"] == "https://chatgpt.com/c/demo"
    assert load("demo", "webgpt").tab_id == "456"
    assert "window.new https://chatgpt.com/c/demo --json --unfocused" in calls.read_text(encoding="utf-8")


def test_open_bind_accepts_live_surf_window_string_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_ORACLE_WEBGPT_PROJECT_ROOT", str(tmp_path / "bindings"))
    surf = _fake_surf(
        tmp_path / "surf-run.sh",
        """
printf '%s\\n' '"Window 837361281 (tab 837361282)\\nUse --window-id 837361281 to target this window"'
""",
    )
    monkeypatch.setenv("BROWSER_ORACLE_SURF_RUN", str(surf))

    result = runner.invoke(
        app,
        ["open-bind", "demo", "--backend", "webgpt", "--url", "https://chatgpt.com/", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["tab_id"] == "837361282"


def test_open_bind_accepts_live_surf_tab_string_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_ORACLE_WEBGPT_PROJECT_ROOT", str(tmp_path / "bindings"))
    surf = _fake_surf(
        tmp_path / "surf-run.sh",
        """
printf '"Created tab 837361275: https://claude.ai/new"\\n'
""",
    )
    monkeypatch.setenv("BROWSER_ORACLE_SURF_RUN", str(surf))

    result = runner.invoke(
        app,
        [
            "open-bind",
            "demo",
            "--backend",
            "webclaude",
            "--url",
            "https://claude.ai/new",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["tab_id"] == "837361275"
