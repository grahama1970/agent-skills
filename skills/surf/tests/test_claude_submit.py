from __future__ import annotations

import json
import os
import subprocess
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CLAUDE_SUBMIT = REPO_ROOT / "skills/surf/scripts/claude-submit.py"
SURF_RUN = REPO_ROOT / "skills/surf/run.sh"


def _load_claude_submit_module():
    spec = importlib.util.spec_from_file_location("claude_submit_script", CLAUDE_SUBMIT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_surf_run_routes_claude_submit_help() -> None:
    proc = subprocess.run(
        [str(SURF_RUN), "claude.submit", "--help"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "usage: surf claude.submit" in proc.stdout
    assert "--attach-file" in proc.stdout


def test_claude_submit_accepts_attach_file_and_records_upload_metadata(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    attachment = tmp_path / "prior-response.md"
    fake_run = tmp_path / "surf-run.sh"
    invocation_log = tmp_path / "surf-invocations.log"
    sentinel_file = tmp_path / "sentinel.txt"
    prompt_file = tmp_path / "composer.txt"
    submitted_file = tmp_path / "submitted.flag"

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
    if [[ -f {str(submitted_file)!r} ]]; then
      printf 'https://claude.ai/chat/example\\nprior-response.md\\nClaude responded:\\nAttached review complete\\n%s\\n' "$sentinel"
    else
      printf 'https://claude.ai/chat/example\\nprior-response.md\\n%s\\n' "$(cat {str(prompt_file)!r} 2>/dev/null || true)"
    fi
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
  click)
    if [[ "${{2:-}}" == "e2" ]]; then
      printf 'submitted' > {str(submitted_file)!r}
    fi
    printf 'ok\\n'
    ;;
  key)
    printf 'submitted' > {str(submitted_file)!r}
    printf 'ok\\n'
    ;;
  type)
    python3 - "${{2:-}}" {str(sentinel_file)!r} {str(prompt_file)!r} <<'PY'
import pathlib
import re
import sys

pathlib.Path(sys.argv[3]).write_text(sys.argv[1], encoding="utf-8")
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
    submitted = (tmp_path / "response.md.submitted.md").read_text(encoding="utf-8")
    assert "Automation-only instruction" in submitted
    assert "Do not mention," in submitted
    assert "For transport verification" not in submitted


def test_claude_submit_recovery_preserves_attachment_metadata(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    attachment = tmp_path / "review-bundle.md"
    fake_run = tmp_path / "surf-run.sh"
    sentinel_file = tmp_path / "sentinel.txt"

    request.write_text("Review the attached bundle.\n", encoding="utf-8")
    attachment.write_text("# Bundle\n\nReadable local target.\n", encoding="utf-8")
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  tab.list)
    printf '[{{"id":837360812,"url":"https://claude.ai/chat/example","title":"Claude"}}]\\n'
    ;;
  focus.state)
    printf '{{"focusedWindowId":1,"activeTabId":837360812}}\\n'
    ;;
  page.text)
    sentinel="$(cat {str(sentinel_file)!r} 2>/dev/null || true)"
    printf 'https://claude.ai/chat/example\\nreview-bundle.md\\nClaude responded:\\nRecovered attached review complete\\n%s\\n' "$sentinel"
    ;;
  read)
    printf 'textbox "Write your prompt to Claude" [e1]\\n'
    printf 'button "Send message" [e2]\\n'
    printf 'button "Upload files" [e3] type="file"\\n'
    printf 'review-bundle.md\\n'
    ;;
  js)
    printf '{{"ok":true}}\\n'
    ;;
  upload)
    printf 'uploaded\\n'
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
  click)
    if [[ "${{2:-}}" == "e2" ]]; then
      echo "simulated post-submit transport failure" >&2
      exit 7
    fi
    printf 'ok\\n'
    ;;
  key)
    echo "simulated post-submit transport failure" >&2
    exit 7
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
    assert response.read_text(encoding="utf-8").strip() == "Recovered attached review complete"
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["recovered_after_failure"] is True
    assert payload["attachment_missing"] is False
    assert payload["attachment"]["source"] == "post_failure_sentinel_recovery_attach_file"
    assert payload["attachment"]["name"] == "review-bundle.md"


def test_claude_submit_recovers_missing_content_script_with_same_tab_reload(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"
    invocation_log = tmp_path / "surf-invocations.log"
    sentinel_file = tmp_path / "sentinel.txt"
    read_count_file = tmp_path / "read-count.txt"

    request.write_text("Review the generated records.\n", encoding="utf-8")
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
  tab.reload)
    printf '{{"success":true}}\\n'
    ;;
  page.text)
    sentinel="$(cat {str(sentinel_file)!r} 2>/dev/null || true)"
    printf 'https://claude.ai/chat/example\\nClaude responded:\\nRecovered review complete\\n%s\\n' "$sentinel"
    ;;
  read)
    count="$(cat {str(read_count_file)!r} 2>/dev/null || printf '0')"
    count="$((count + 1))"
    printf '%s' "$count" > {str(read_count_file)!r}
    if [[ "$count" -eq 1 ]]; then
      echo 'Error: Content script not loaded. Try refreshing the page.' >&2
      exit 1
    fi
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
            "837360812",
            "--url",
            "https://claude.ai/chat/example",
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
    assert response.read_text(encoding="utf-8").strip() == "Recovered review complete"
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert len(payload["content_script_recovery"]) == 1
    recovery = payload["content_script_recovery"][0]
    assert recovery["status"] == "recovered"
    assert recovery["tab_id"] == "837360812"
    assert recovery["probe_stderr"] == "Error: Content script not loaded. Try refreshing the page."
    assert recovery["probe_stdout"] == ""
    assert recovery["action"] == "tab.reload --hard"
    assert recovery["reload_returncode"] == 0
    assert recovery["reload_stdout"] == '{"success":true}'
    assert recovery["reload_stderr"] == ""
    assert recovery["ready_attempts"] == 1
    assert recovery["detected_at"]
    assert recovery["recovered_at"]
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "tab.reload --hard --tab-id 837360812" in invocations
    assert invocations.count("read --tab-id 837360812") >= 2


def test_claude_submit_finalizes_raw_sentinel_after_wait_failure(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    raw = tmp_path / "response.raw.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"
    invocation_log = tmp_path / "surf-invocations.log"
    sentinel_file = tmp_path / "sentinel.txt"
    text_count_file = tmp_path / "text-count.txt"
    prompt_file = tmp_path / "composer.txt"
    submitted_file = tmp_path / "submitted.flag"

    request.write_text("Review the generated records.\n", encoding="utf-8")
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
    if [[ ! -f {str(submitted_file)!r} ]]; then
      printf 'https://claude.ai/chat/example\\n%s\\n' "$(cat {str(prompt_file)!r} 2>/dev/null || true)"
    else
      count="$(cat {str(text_count_file)!r} 2>/dev/null || printf '0')"
      count="$((count + 1))"
      printf '%s' "$count" > {str(text_count_file)!r}
      if [[ "$count" -le 2 ]]; then
        printf 'https://claude.ai/chat/example\\nClaude is responding\\nClaude responded:\\nCompleted review\\n%s\\n' "$sentinel"
      else
        printf 'https://claude.ai/chat/example\\nClaude responded:\\nCompleted review\\n%s\\n' "$sentinel"
      fi
    fi
    ;;
  read)
    printf 'textbox "Write your prompt to Claude" [e1]\\n'
    printf 'button "Send message" [e2]\\n'
    ;;
  click)
    if [[ "${{2:-}}" == "e2" ]]; then
      printf 'submitted' > {str(submitted_file)!r}
    fi
    printf 'ok\\n'
    ;;
  key)
    printf 'submitted' > {str(submitted_file)!r}
    printf 'ok\\n'
    ;;
  type)
    python3 - "${{2:-}}" {str(sentinel_file)!r} {str(prompt_file)!r} <<'PY'
import pathlib
import re
import sys

pathlib.Path(sys.argv[3]).write_text(sys.argv[1], encoding="utf-8")
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
            "--raw-output",
            str(raw),
            "--meta-output",
            str(meta),
            "--tab-id",
            "837360812",
            "--url",
            "https://claude.ai/chat/example",
            "--stable-polls",
            "3",
            "--timeout",
            "1",
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
    assert response.read_text(encoding="utf-8").strip() == "Completed review"
    assert "<<<CLAUDE_DONE:" in raw.read_text(encoding="utf-8")
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["raw_contains_sentinel"] is True
    assert payload["clean_contains_sentinel"] is False
    assert payload["recovered_after_failure"] is True
    assert "timed out waiting for marker" in payload["recovery_failure"]
    assert payload["response_source"] == "post_failure_text_capture"


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


def test_claude_submit_does_not_recover_from_prompt_echo_sentinel(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    raw = tmp_path / "response.raw.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"
    prompt_file = tmp_path / "composer.txt"

    request.write_text("Review this.\n", encoding="utf-8")
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  tab.list)
    printf '[{{"id":837360921,"url":"https://claude.ai/new","title":"Claude"}}]\\n'
    ;;
  focus.state)
    printf '{{"focusedWindowId":1,"activeTabId":837360921}}\\n'
    ;;
  page.text)
    printf 'https://claude.ai/new\\n%s\\n' "$(cat {str(prompt_file)!r} 2>/dev/null || true)"
    ;;
  read)
    printf 'textbox "Write your prompt to Claude" [e1]\\n'
    printf 'button "Send message" [e2]\\n'
    ;;
  click|key)
    printf 'ok\\n'
    ;;
  type)
    python3 - "${{2:-}}" {str(prompt_file)!r} <<'PY'
import pathlib
import sys

pathlib.Path(sys.argv[2]).write_text(sys.argv[1], encoding="utf-8")
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
            "--raw-output",
            str(raw),
            "--meta-output",
            str(meta),
            "--sentinel",
            "<<<CLAUDE_DONE:prompt_echo>>>",
            "--tab-id",
            "837360921",
            "--url",
            "https://claude.ai/new",
            "--timeout",
            "1",
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

    assert proc.returncode == 4
    assert "Claude prompt was staged but not submitted" in proc.stderr
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["raw_contains_sentinel"] is True
    assert "recovered_after_failure" not in payload
    assert not response.exists()


def test_claude_submit_rejects_completed_page_prompt_echo(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    response = tmp_path / "response.md"
    raw = tmp_path / "response.raw.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"
    sentinel_file = tmp_path / "sentinel.txt"
    prompt_file = tmp_path / "composer.txt"
    submitted_file = tmp_path / "submitted.flag"
    acceptance_seen_file = tmp_path / "acceptance-seen.flag"

    request.write_text("You are one participant in a Tau-managed roundtable.\n", encoding="utf-8")
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  tab.list)
    printf '[{{"id":837360921,"url":"https://claude.ai/new","title":"New chat - Claude"}}]\\n'
    ;;
  focus.state)
    printf '{{"focusedWindowId":1,"activeTabId":837360921}}\\n'
    ;;
  page.text)
    sentinel="$(cat {str(sentinel_file)!r} 2>/dev/null || true)"
    if [[ -f {str(submitted_file)!r} ]]; then
      if [[ ! -f {str(acceptance_seen_file)!r} ]]; then
        printf 'accepted' > {str(acceptance_seen_file)!r}
        printf 'https://claude.ai/new\\nClaude is responding\\n'
      else
        printf 'Title: New chat - Claude\\n'
        printf 'URL: https://claude.ai/new\\n'
        printf '@keyframes look-around {{ from {{ opacity: 1; }} }}\\n'
        printf 'What can we tackle together?sparta-readme-roundtable-r2-bundle.mdmd'
        printf '%s\\n' "$(cat {str(prompt_file)!r} 2>/dev/null || true)"
      fi
    else
      printf 'https://claude.ai/new\\n%s\\n' "$(cat {str(prompt_file)!r} 2>/dev/null || true)"
    fi
    ;;
  read)
    printf 'textbox "Write your prompt to Claude" [e1]\\n'
    printf 'button "Send message" [e2]\\n'
    ;;
  click)
    if [[ "${{2:-}}" == "e2" ]]; then
      printf 'submitted' > {str(submitted_file)!r}
    fi
    printf 'ok\\n'
    ;;
  key)
    printf 'submitted' > {str(submitted_file)!r}
    printf 'ok\\n'
    ;;
  type)
    python3 - "${{2:-}}" {str(sentinel_file)!r} {str(prompt_file)!r} <<'PY'
import pathlib
import re
import sys

pathlib.Path(sys.argv[3]).write_text(sys.argv[1], encoding="utf-8")
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
            "--raw-output",
            str(raw),
            "--meta-output",
            str(meta),
            "--sentinel",
            "<<<CLAUDE_DONE:prompt_echo>>>",
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

    assert proc.returncode == 5, proc.stderr
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failure"] == "missing_sentinel_or_contaminated_clean_output"
    assert payload["raw_contains_sentinel"] is True
    assert payload["clean_contains_sentinel"] is False
    assert "What can we tackle together?" in payload["clean_contamination_markers"]
    assert "Automation-only instruction:" in payload["clean_contamination_markers"]


def test_claude_clean_contamination_allows_marker_discussion() -> None:
    claude_submit = _load_claude_submit_module()
    text = (
        "The prior detector matched @keyframes and What can we tackle together? "
        "as page-shell markers, but this answer is discussing them as evidence."
    )

    assert claude_submit._clean_contamination_markers(text) == []


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
