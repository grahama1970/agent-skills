from __future__ import annotations

import json
import os
import subprocess
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CLAUDE_SUBMIT = REPO_ROOT / "skills/surf/scripts/claude-submit.py"


def _load_claude_submit_module():
    spec = importlib.util.spec_from_file_location("claude_submit", CLAUDE_SUBMIT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_claude_submit_accepts_attach_file_and_records_upload_metadata(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    attachment = tmp_path / "prior-response.md"
    fake_run = tmp_path / "surf-run.sh"
    invocation_log = tmp_path / "surf-invocations.log"
    sentinel_file = tmp_path / "sentinel.txt"

    request.write_text("Review the attached prior handler response.\n", encoding="utf-8")
    attachment.write_text("Prior handler response.\n", encoding="utf-8")
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(invocation_log)!r}
case "${{1:-}}" in
  tab.list)
    printf '[{{"id":837360812,"url":"https://claude.ai/chat/example","title":"Claude"}}]\\n'
    ;;
  focus.state)
    printf '{{"focusedWindowId":1,"activeTabId":837360812}}\\n'
    ;;
  page.text)
    sentinel="$(cat {str(sentinel_file)!r} 2>/dev/null || true)"
    printf 'https://claude.ai/chat/example\\nprior-response.md\\nClaude responded:\\nAttached review complete\\n%s\\n' "$sentinel"
    ;;
  read)
    printf 'textbox "Write your prompt to Claude" [e1]\\n'
    printf 'button "Send message" [e2]\\n'
    printf 'button "Upload files" [e3] type="file"\\n'
    printf 'prior-response.md\\n'
    ;;
  js)
    printf '{{"ok":true}}\\n'
    ;;
  upload)
    printf 'uploaded\\n'
    ;;
  click|key)
    printf 'ok\\n'
    ;;
  type)
    python3 - "${{2:-}}" {str(sentinel_file)!r} <<'PY'
import pathlib
import re
import sys

match = re.search(r"<<<CLAUDE_DONE:[^>]+>>>", sys.argv[1], re.S)
if match:
    pathlib.Path(sys.argv[2]).write_text(match.group(0), encoding="utf-8")
PY
    printf 'typed\\n'
    ;;
  *)
    echo "unexpected surf command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)

    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(fake_run)
    proc = subprocess.run(
        [
            "python3",
            str(CLAUDE_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(response),
            "--meta-output",
            str(meta),
            "--tab-id",
            "837360812",
            "--url",
            "https://claude.ai/chat/example",
            "--attach-file",
            str(attachment),
            "--stable-polls",
            "0",
            "--timeout",
            "5",
            "--no-activate",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert response.read_text(encoding="utf-8").strip() == "Attached review complete"
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["attach_file"] == str(attachment.resolve())
    assert payload["attachment"] == {
        "path": str(attachment.resolve()),
        "filename": "prior-response.md",
        "upload_ref": "e3",
        "preview_visible": True,
    }
    assert payload["attachment_missing"] is False
    assert payload["attachment_preview_missing"] is False
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "upload --ref e3 --files" in invocations
    assert str(attachment.resolve()) in invocations
    assert "key ctrl+a --tab-id 837360812" in invocations
    assert "key Backspace --tab-id 837360812" in invocations


def test_claude_submit_accepts_new_tab_materialized_chat_url(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"
    sentinel_file = tmp_path / "sentinel.txt"

    request.write_text("Review this.\n", encoding="utf-8")
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  tab.list)
    printf '[{{"id":837360921,"url":"https://claude.ai/chat/live-url","title":"Claude"}}]\\n'
    ;;
  focus.state)
    printf '{{"focusedWindowId":1,"activeTabId":837360921}}\\n'
    ;;
  page.text)
    sentinel="$(cat {str(sentinel_file)!r} 2>/dev/null || true)"
    printf 'Claude responded:\\nTransition accepted\\n%s\\n' "$sentinel"
    ;;
  read)
    printf 'textbox "Write your prompt to Claude" [e1]\\n'
    printf 'button "Send message" [e2]\\n'
    ;;
  click|key)
    printf 'ok\\n'
    ;;
  type)
    python3 - "${{2:-}}" {str(sentinel_file)!r} <<'PY'
import pathlib
import re
import sys

match = re.search(r"<<<CLAUDE_DONE:[^>]+>>>", sys.argv[1], re.S)
if match:
    pathlib.Path(sys.argv[2]).write_text(match.group(0), encoding="utf-8")
PY
    printf 'typed\\n'
    ;;
  *)
    echo "unexpected surf command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)

    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(fake_run)
    proc = subprocess.run(
        [
            "python3",
            str(CLAUDE_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(response),
            "--meta-output",
            str(meta),
            "--tab-id",
            "837360921",
            "--url",
            "https://claude.ai/new",
            "--timeout",
            "5",
            "--stable-polls",
            "0",
            "--no-activate",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert response.read_text(encoding="utf-8").strip() == "Transition accepted"
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["current_url"] == "https://claude.ai/chat/live-url"
    assert payload["tab_identity_preflight"]["accepted_url_transition"] is True
    assert payload["tab_identity_preflight"]["reason"] == "claude_new_tab_materialized_chat"


def test_claude_submit_chat_url_mismatch_still_fails_closed(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"

    request.write_text("Review this.\n", encoding="utf-8")
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  tab.list)
    printf '[{"id":837360921,"url":"https://claude.ai/chat/live-url","title":"Claude"}]\\n'
    ;;
  focus.state)
    printf '{"focusedWindowId":1,"activeTabId":837360921}\\n'
    ;;
  *)
    echo "unexpected surf command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)

    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(fake_run)
    proc = subprocess.run(
        [
            "python3",
            str(CLAUDE_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(response),
            "--meta-output",
            str(meta),
            "--tab-id",
            "837360921",
            "--url",
            "https://claude.ai/chat/expected-url",
            "--timeout",
            "5",
            "--no-activate",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 4
    assert "URL mismatch: expected https://claude.ai/chat/expected-url, saw https://claude.ai/chat/live-url" in proc.stderr
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["failure"] == (
        "tab 837360921 URL mismatch: expected https://claude.ai/chat/expected-url, "
        "saw https://claude.ai/chat/live-url"
    )
    assert payload["tab_identity_preflight"]["error"] == "expected_url_mismatch"


def test_clean_response_collapses_single_line_accessibility_duplicate() -> None:
    module = _load_claude_submit_module()

    assert module._clean_response("Claude responded: claude smokeclaude smoke <<<CLAUDE_DONE:x>>>", "<<<CLAUDE_DONE:x>>>") == "claude smoke\n"
    assert module._clean_response("Claude responded: keep both\nkeep both <<<CLAUDE_DONE:x>>>", "<<<CLAUDE_DONE:x>>>") == "keep both\nkeep both\n"


def test_claude_submit_refreshes_materialized_chat_url_after_submit(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"
    sentinel_file = tmp_path / "sentinel.txt"
    submitted_marker = tmp_path / "submitted"

    request.write_text("Review this.\n", encoding="utf-8")
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  tab.list)
    if [ -f {str(submitted_marker)!r} ]; then
      printf '[{{"id":837360921,"url":"https://claude.ai/chat/materialized","title":"Claude"}}]\\n'
    else
      printf '[{{"id":837360921,"url":"https://claude.ai/new","title":"Claude"}}]\\n'
    fi
    ;;
  focus.state)
    printf '{{"focusedWindowId":1,"activeTabId":837360921}}\\n'
    ;;
  page.text)
    sentinel="$(cat {str(sentinel_file)!r} 2>/dev/null || true)"
    printf 'Claude responded:\\nTransition accepted\\n%s\\n' "$sentinel"
    ;;
  read)
    printf 'textbox "Write your prompt to Claude" [e1]\\n'
    printf 'button "Send message" [e2]\\n'
    ;;
  click|key)
    printf 'ok\\n'
    ;;
  type)
    touch {str(submitted_marker)!r}
    python3 - "${{2:-}}" {str(sentinel_file)!r} <<'PY'
import pathlib
import re
import sys

match = re.search(r"<<<CLAUDE_DONE:[^>]+>>>", sys.argv[1], re.S)
if match:
    pathlib.Path(sys.argv[2]).write_text(match.group(0), encoding="utf-8")
PY
    printf 'typed\\n'
    ;;
  *)
    echo "unexpected surf command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)

    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(fake_run)
    proc = subprocess.run(
        [
            "python3",
            str(CLAUDE_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(response),
            "--meta-output",
            str(meta),
            "--tab-id",
            "837360921",
            "--url",
            "https://claude.ai/new",
            "--timeout",
            "5",
            "--stable-polls",
            "0",
            "--no-activate",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["current_url"] == "https://claude.ai/chat/materialized"
    assert payload["tab_identity_preflight"]["accepted_url_transition"] is True
