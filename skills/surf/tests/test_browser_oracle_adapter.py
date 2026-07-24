import json
import os
import shlex
import subprocess
from pathlib import Path


SURF_DIR = Path(__file__).resolve().parents[1]
ADAPTER = SURF_DIR / "scripts" / "lib" / "browser_oracle_resolve.sh"
SUBMIT = SURF_DIR / "scripts" / "webgpt-submit.sh"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _legacy_browser_oracle(path: Path, *, verified: bool) -> None:
    _write_executable(
        path,
        f"""#!/usr/bin/env bash
set -u
case "$1" in
  resolve)
    printf '%s\n' '{{"project":"surf","tab_id":"837356906","conversation_url":"https://chatgpt.com/c/stale"}}'
    ;;
  reconcile)
    echo "No such command 'reconcile'" >&2
    exit 2
    ;;
  verify)
    printf '%s\n' '{{"name":"surf","backend":"webgpt","tab_id":"837356906","conversation_url":"https://chatgpt.com/c/stale","verified":{str(verified).lower()}}}'
    ;;
  open-bind)
    printf '%s\n' '{{"name":"surf","backend":"webgpt","tab_id":"837358677","conversation_url":"https://chatgpt.com/c/fresh"}}'
    ;;
  *) exit 9 ;;
esac
""",
    )


def test_reconcile_adapter_normalizes_legacy_verify(tmp_path: Path) -> None:
    browser_oracle = tmp_path / "browser-oracle"
    _legacy_browser_oracle(browser_oracle, verified=True)
    command = (
        f"source {shlex.quote(str(ADAPTER))}; "
        "browser_oracle_reconcile_json webgpt surf 0"
    )
    env = {**os.environ, "BROWSER_ORACLE_RUN": str(browser_oracle)}

    completed = subprocess.run(
        ["bash", "-c", command],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["project"] == "surf"
    assert payload["rows"][0]["status"] == "ready"
    assert payload["rows"][0]["tab_id"] == "837356906"


def test_open_bind_adapter_delegates_to_browser_oracle(tmp_path: Path) -> None:
    browser_oracle = tmp_path / "browser-oracle"
    _legacy_browser_oracle(browser_oracle, verified=True)
    command = (
        f"source {shlex.quote(str(ADAPTER))}; "
        "browser_oracle_open_bind_json surf webgpt https://chatgpt.com/c/fresh"
    )
    env = {**os.environ, "BROWSER_ORACLE_RUN": str(browser_oracle)}

    completed = subprocess.run(
        ["bash", "-c", command],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["tab_id"] == "837358677"


def test_submit_does_not_fall_back_to_remembered_tab_when_binding_is_stale(
    tmp_path: Path,
) -> None:
    browser_oracle = tmp_path / "browser-oracle"
    _legacy_browser_oracle(browser_oracle, verified=False)

    surf_calls = tmp_path / "surf-calls.log"
    fake_surf = tmp_path / "surf"
    _write_executable(fake_surf, f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> {shlex.quote(str(surf_calls))}\n')

    remembered = tmp_path / "remembered-tab"
    remembered.write_text("837356906\n", encoding="utf-8")
    request = tmp_path / "request.md"
    request.write_text("diagnose the current issue\n", encoding="utf-8")

    env = {
        **os.environ,
        "BROWSER_ORACLE_RUN": str(browser_oracle),
        "SURF_RUN_SH": str(fake_surf),
        "SURF_WEBGPT_TAB_STATE": str(remembered),
    }
    completed = subprocess.run(
        [
            "bash",
            str(SUBMIT),
            "--input",
            str(request),
            "--output",
            str(tmp_path / "response.md"),
            "--browser-oracle-from",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 3
    assert "browser-oracle binding for project surf is missing_live_tab" in completed.stderr
    assert not surf_calls.exists()
