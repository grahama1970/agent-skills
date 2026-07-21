from __future__ import annotations

import json
import os
import subprocess
import time
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
WEBGPT_SUBMIT = REPO_ROOT / "skills/surf/scripts/webgpt-submit.sh"


def run_submit(
    tmp_path: Path,
    archive: Path,
    fake_run_body: str | None = None,
    tab_id: str = "837352334",
    extra_args: list[str] | None = None,
    no_activate: bool = True,
) -> subprocess.CompletedProcess[str]:
    request = tmp_path / "request.md"
    output = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"
    request.write_text("review the attached bundle\n", encoding="utf-8")
    fake_run.write_text(
        fake_run_body
        or "#!/usr/bin/env bash\necho unexpected surf invocation >&2\nexit 99\n",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(fake_run)
    env["SURF_WEBGPT_EXTRACT_FALLBACK_BUDGET"] = "0"
    env["TMPDIR"] = str(tmp_path)
    return subprocess.run(
        [
            "bash",
            str(WEBGPT_SUBMIT),
            "--input",
            str(request),
            "--output",
            str(output),
            "--meta-output",
            str(meta),
            "--attach-file",
            str(archive),
            "--tab-id",
            tab_id,
            "--expect-url",
            "https://chatgpt.com/c/example",
            *(["--no-activate"] if no_activate else []),
            *(extra_args or []),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def make_zip(path: Path, count: int) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for idx in range(count):
            zf.writestr(f"file-{idx}.txt", f"payload {idx}\n")


FAKE_RUN_PREAMBLE = """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  tab.list)
    printf '837352334\\tAgentic Research - Boris Loop\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{"active_tab_id":"123","active_window_id":"456"}\\n'
    ;;
  js)
    printf '"cdp-ok"\\n'
    ;;
"""


def test_webgpt_submit_rejects_zip_attachment_with_more_than_five_files(tmp_path: Path) -> None:
    archive = tmp_path / "too-many.zip"
    make_zip(archive, 6)

    proc = run_submit(tmp_path, archive)

    assert proc.returncode == 2
    assert "zip contains 6 files; maximum is 5" in proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "attach_file_preflight_failed"
    assert meta["attach_file_preflight"]["file_count"] == 6
    assert meta["attach_file_preflight"]["max_files"] == 5


def test_webgpt_submit_accepts_zip_attachment_with_five_files_until_browser_preflight(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)

    proc = run_submit(tmp_path, archive)

    assert proc.returncode == 2
    assert "zip contains" not in proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "tab_identity_preflight_failed"


def test_webgpt_submit_browser_failure_writes_failed_meta(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    echo 'simulated browser failure' >&2
    exit 7
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""
    )

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 7
    assert "simulated browser failure" in proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["exit_code"] == 7
    assert meta["requested_tab_id"] == "837352334"
    assert meta["tab_identity_preflight"]["ok"] is True


def test_webgpt_submit_no_activate_stale_cdp_explicit_tab_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    invocation_log = tmp_path / "surf-invocations.log"
    fake_run = f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(invocation_log)!r}
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tAgentic Research - Boris Loop\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  js)
    echo 'Error: Failed to attach debugger: Another debugger is already attached to the tab with id: 837352334.' >&2
    exit 1
    ;;
  extension.reload|extension.ping)
    printf 'connected\\n'
    ;;
  tab.new|chatgpt)
    echo "forbidden fallback/submission command: $*" >&2
    exit 42
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 6
    assert "same-tab extension reload retry" in proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "stale_cdp_on_explicit_tab"
    assert meta["proof_status"] == "not_submitted"
    assert meta["submitted_to_chatgpt"] is False
    assert meta["requested_tab_id"] == "837352334"
    assert "Another debugger is already attached" in meta["cdp_probe_stderr"]
    assert meta["cdp_retry_attempted"] is True
    assert "Another debugger is already attached" in meta["cdp_retry_stderr"]
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "extension.reload" in invocations
    assert "tab.new" not in invocations
    assert "chatgpt" not in invocations
    assert not list(tmp_path.glob("surf-webgpt-cdp-*.log"))


def test_webgpt_submit_blocks_concurrent_submit_to_same_tab(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    locked_tab_id = "837399999"
    lock_path = Path(f"/tmp/surf-webgpt-tab-{locked_tab_id}.lock")
    holder = subprocess.Popen(["flock", "-n", str(lock_path), "sleep", "30"])
    try:
        time.sleep(0.2)
        fake_run = f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  tab.list)
    printf '{locked_tab_id}\\tAgentic Research - Boris Loop\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  chatgpt)
    echo "chatgpt should not be called while tab lock is held" >&2
    exit 42
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""

        proc = run_submit(tmp_path, archive, fake_run, tab_id=locked_tab_id)
    finally:
        holder.terminate()
        holder.wait(timeout=5)

    assert proc.returncode == 9
    assert f"already controlling tab {locked_tab_id}" in proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "concurrent_submit_same_tab"
    assert meta["proof_status"] == "not_submitted"
    assert meta["submitted_to_chatgpt"] is False
    assert meta["requested_tab_id"] == locked_tab_id
    assert meta["lock_path"] == str(lock_path)


def test_webgpt_submit_no_activate_stale_cdp_recovers_same_tab_after_extension_reload(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    invocation_log = tmp_path / "surf-invocations.log"
    js_count_file = tmp_path / "js-count"
    fake_run = f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(invocation_log)!r}
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tAgentic Research - Boris Loop\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  js)
    count="$(cat {str(js_count_file)!r} 2>/dev/null || printf '0')"
    count="$((count + 1))"
    printf '%s' "$count" > {str(js_count_file)!r}
    if [[ "$count" -eq 1 ]]; then
      echo 'Error: Failed to attach debugger: Another debugger is already attached to the tab with id: 837352334.' >&2
      exit 1
    fi
    printf '"cdp-ok"\\n'
    ;;
  extension.reload|extension.ping)
    printf 'connected\\n'
    ;;
  chatgpt)
    sentinel=""
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${{2:-}}"
        break
      fi
      shift
    done
    printf 'same tab response\\n%s\\n' "$sentinel"
    echo 'Tab ID: 837352334' >&2
    echo 'Activated: false' >&2
    echo 'TabWasCreated: false' >&2
    echo 'ConversationUrl: https://chatgpt.com/c/new-example' >&2
    echo 'CurrentUrl: https://chatgpt.com/c/new-example' >&2
    echo 'ResponseSource: assistant-dom' >&2
    exit 0
    ;;
  tab.new)
    echo "forbidden fallback command: $*" >&2
    exit 42
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 0
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "same tab response\n"
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["requested_tab_id"] == "837352334"
    assert meta["controlled_tab_id"] == "837352334"
    assert meta["conversation_url"] == "https://chatgpt.com/c/new-example"
    assert meta["current_url"] == "https://chatgpt.com/c/new-example"
    assert meta["tab_url"] == "https://chatgpt.com/c/new-example"
    assert meta["raw_contains_sentinel"] is True
    assert meta["clean_contains_sentinel"] is False
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "extension.reload" in invocations
    assert "chatgpt" in invocations
    assert "tab.new" not in invocations
    assert not list(tmp_path.glob("surf-webgpt-cdp-*.log"))


def test_webgpt_submit_allow_foreground_flag_does_not_activate_tab(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    invocation_log = tmp_path / "surf-invocations.log"
    js_count_file = tmp_path / "js-count"
    fake_run = f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(invocation_log)!r}
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tAgentic Research - Boris Loop\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"837352334","active_window_id":"456"}}\\n'
    ;;
  js)
    count="$(cat {str(js_count_file)!r} 2>/dev/null || printf '0')"
    count="$((count + 1))"
    printf '%s' "$count" > {str(js_count_file)!r}
    if [[ "$count" -eq 1 ]]; then
      echo 'Error: Failed to attach debugger: Another debugger is already attached to the tab with id: 837352334.' >&2
      exit 1
    fi
    printf '"cdp-ok"\\n'
    ;;
  extension.reload|extension.ping)
    printf 'connected\\n'
    ;;
  chatgpt)
    sentinel=""
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${{2:-}}"
        break
      fi
      shift
    done
    printf 'same tab visible response\\n%s\\n' "$sentinel"
    echo 'Tab ID: 837352334' >&2
    echo 'Activated: false' >&2
    echo 'TabWasCreated: false' >&2
    echo 'NoActivate: true' >&2
    echo 'ResponseSource: assistant-dom' >&2
    exit 0
    ;;
  tab.activate)
    echo "forbidden foreground activation: $*" >&2
    exit 42
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""

    proc = run_submit(
        tmp_path,
        archive,
        fake_run,
        extra_args=["--allow-foreground-controlled"],
        no_activate=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "same tab visible response\n"
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["no_activate"] is True
    assert meta["activated"] is False
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "extension.reload" in invocations
    assert "tab.activate" not in invocations


def test_webgpt_submit_strips_terminal_cursor_after_sentinel(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    sentinel=""
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${2:-}"
        break
      fi
      shift
    done
    printf 'cursor artifact response\\n%s_\\n' "$sentinel"
    echo 'Tab ID: 837352334' >&2
    echo 'Activated: false' >&2
    echo 'TabWasCreated: false' >&2
    echo 'ResponseSource: assistant-dom' >&2
    exit 0
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""
    )

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "cursor artifact response\n"
    raw = (tmp_path / "response.md.raw.md").read_text(encoding="utf-8")
    assert raw.rstrip().endswith("_")
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["raw_contains_sentinel"] is True
    assert meta["clean_contains_sentinel"] is False


def test_webgpt_submit_clean_failure_writes_meta_for_real_text_after_sentinel(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    sentinel=""
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${2:-}"
        break
      fi
      shift
    done
    printf 'bad terminal response\\n%s\\nextra text after marker\\n' "$sentinel"
    echo 'Tab ID: 837352334' >&2
    echo 'Activated: false' >&2
    echo 'TabWasCreated: false' >&2
    echo 'ResponseSource: assistant-dom' >&2
    exit 0
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""
    )

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 5
    assert "assistant response contains text after terminal sentinel" in proc.stderr
    assert not (tmp_path / "response.md").exists()
    raw = (tmp_path / "response.md.raw.md").read_text(encoding="utf-8")
    assert "extra text after marker" in raw
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "response_clean_failed"
    assert meta["proof_status"] == "delivery_not_proven"
    assert meta["submitted_to_chatgpt"] is False
    assert meta["raw_contains_sentinel"] is True
    assert meta["clean_contains_sentinel"] is False
    assert meta["controlled_tab_id"] == "837352334"


def test_webgpt_submit_failed_timeout_preserves_partial_raw_output(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    echo 'partial reviewer answer after timeout without sentinel'
    echo 'Tab ID: 837352334' >&2
    echo 'ResponseSource: assistant-dom' >&2
    echo 'ResponseTimedOut: true' >&2
    echo 'TimeoutError: Request timed out (600s)' >&2
    exit 124
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""
    )

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 124
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == (
        "partial reviewer answer after timeout without sentinel\n"
    )
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "submit_failed"
    assert meta["exit_code"] == 124
    assert meta["controlled_tab_id"] == "837352334"
    assert meta["response_source"] == "assistant-dom"
    assert meta["response_timed_out"] is True
    assert meta["timeout_error"] == "Request timed out (600s)"
    assert meta["raw_contains_sentinel"] is False
    assert meta["clean_contains_sentinel"] is False
    assert meta["raw_chars"] > 0
    assert meta["clean_chars"] > 0
    assert meta["raw_response_advisory"] is True


def test_webgpt_submit_classifies_conversation_full_without_timeout(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    echo 'BLOCKED_WEBGPT_CONVERSATION_FULL: You have reached the maximum length for this conversation, but you can keep talking by starting a new chat.' >&2
    exit 1
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""
    )

    started = time.monotonic()
    proc = run_submit(tmp_path, archive, fake_run, extra_args=["--timeout", "930"])
    elapsed = time.monotonic() - started

    assert proc.returncode == 1
    assert elapsed < 10
    assert "BLOCKED_WEBGPT_CONVERSATION_FULL" in proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "BLOCKED_WEBGPT_CONVERSATION_FULL"
    assert meta["blocker"] == "BLOCKED_WEBGPT_CONVERSATION_FULL"
    assert meta["recommended_action"] == "rebind_handler_project_to_fresh_chatgpt_conversation"
    assert meta["proof_status"] == "not_submitted"
    assert "fresh ChatGPT conversation" in meta["agent_action"]
    assert meta["exit_code"] == 1


def test_webgpt_submit_missing_sentinel_writes_advisory_raw_meta(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    echo 'partial reviewer answer without sentinel'
    echo 'Tab ID: 837352334' >&2
    echo 'ResponseSource: assistant-dom' >&2
    echo 'ResponseTimedOut: true' >&2
    echo 'TimeoutError: Request timed out (3s)' >&2
    exit 0
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""
    )

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 4
    assert "ChatGPT response did not contain sentinel" in proc.stderr
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "partial reviewer answer without sentinel\n"
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "missing_sentinel"
    assert meta["failure"] == "missing_sentinel"
    assert meta["controlled_tab_id"] == "837352334"
    assert meta["response_source"] == "assistant-dom"
    assert meta["response_timed_out"] is True
    assert meta["raw_response_advisory"] is True


def test_chatgpt_client_stable_stall_returns_partial_without_full_timeout(tmp_path: Path) -> None:
    node_script = tmp_path / "stable-stall.js"
    client_path = REPO_ROOT / "skills/surf/vendor/surf-cli/native/chatgpt-client.cjs"
    node_script.write_text(
        f"""
const client = require({json.dumps(str(client_path))});
process.env.SURF_WEBGPT_STABLE_STALL_MS = '5';
const started = Date.now();
const snapshot = {{
  text: 'I will prepare the bundle, but I never print the marker.',
  messageId: 'msg-stalled',
  turnIndex: 4,
  source: 'assistant-dom',
  pageTextContainsSentinel: false,
  documentHidden: false,
  visibilityState: 'visible',
  stopVisible: true,
  finished: false,
}};
async function cdpEvaluate(_expr) {{
  return {{result: {{value: snapshot}}}};
}}
(async () => {{
  try {{
    await client.waitForResponse(cdpEvaluate, 30000, {{
      sentinel: '<<<WEBGPT_DONE:test>>>',
      stablePolls: 3,
    }});
    console.error('expected stable stall error');
    process.exit(1);
  }} catch (err) {{
    if (!err.partialResponse || err.partialResponse.text !== snapshot.text) {{
      console.error('missing partial response', err);
      process.exit(2);
    }}
    if (!String(err.message).includes('Stable assistant response stalled without sentinel')) {{
      console.error('unexpected error', err.message);
      process.exit(3);
    }}
    if (Date.now() - started > 5000) {{
      console.error('waited too long');
      process.exit(4);
    }}
  }}
}})();
""",
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["node", str(node_script)],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr


def test_chatgpt_client_conversation_full_fails_fast(tmp_path: Path) -> None:
    node_script = tmp_path / "conversation-full.js"
    client_path = REPO_ROOT / "skills/surf/vendor/surf-cli/native/chatgpt-client.cjs"
    node_script.write_text(
        f"""
const client = require({json.dumps(str(client_path))});
const started = Date.now();
async function cdpEvaluate(_expr) {{
  return {{result: {{value: {{
    text: '',
    stopVisible: false,
    finished: false,
    source: 'awaiting-assistant-turn',
    pageTextContainsSentinel: false,
    conversationFull: true,
    conversationFullText: 'You have reached the maximum length for this conversation, but you can keep talking by starting a new chat.',
    documentHidden: false,
    visibilityState: 'visible',
    baselineAssistantCount: 0,
    newAssistantTurnCount: 0,
  }}}}}};
}}
(async () => {{
  try {{
    await client.waitForResponse(cdpEvaluate, 30000, {{
      sentinel: '<<<WEBGPT_DONE:test>>>',
      stablePolls: 3,
    }});
    console.error('expected conversation full block');
    process.exit(1);
  }} catch (err) {{
    if (!String(err.message).includes('BLOCKED_WEBGPT_CONVERSATION_FULL')) {{
      console.error('unexpected error', err.message);
      process.exit(2);
    }}
    if (Date.now() - started > 5000) {{
      console.error('waited too long');
      process.exit(3);
    }}
  }}
}})();
""",
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["node", str(node_script)],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr


def test_chatgpt_client_ready_allows_historical_stopped_thinking(tmp_path: Path) -> None:
    node_script = tmp_path / "ready-historical-stopped-thinking.js"
    client_path = REPO_ROOT / "skills/surf/vendor/surf-cli/native/chatgpt-client.cjs"
    node_script.write_text(
        f"""
const client = require({json.dumps(str(client_path))});
const state = {{
  stopVisible: false,
  activeStopLabel: null,
  stoppedThinkingCount: 1,
  sendPresent: true,
  sendDisabled: false,
  promptPresent: true,
  promptChars: 0,
  promptPreview: '',
  documentHidden: false,
  visibilityState: 'visible',
  documentHasFocus: true,
  tailContainsStoppedThinking: true,
  title: 'Gamified Interface Exploit Examples',
  url: 'https://chatgpt.com/c/example',
}};
async function cdpEvaluate(_expr) {{
  return {{result: {{value: state}}}};
}}
(async () => {{
  const ready = await client.assertReadyForNewPrompt(cdpEvaluate);
  if (ready !== state) {{
    console.error('unexpected ready state', ready);
    process.exit(1);
  }}
}})();
""",
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["node", str(node_script)],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr


def test_webgpt_submit_recovers_sentinel_output_when_focus_changed_after_completion(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  tab.list)
    printf '837352334\\tAgentic Research - Boris Loop\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    count_file="$PWD/focus-state-count"
    count="$(cat "$count_file" 2>/dev/null || printf '0')"
    count="$((count + 1))"
    printf '%s' "$count" > "$count_file"
    if [[ "$count" -eq 1 ]]; then
      printf '{"focusedWindowId":456,"activeTabId":123}\\n'
    else
      printf '{"focusedWindowId":999,"activeTabId":888}\\n'
    fi
    ;;
  js)
    printf '"cdp-ok"\\n'
    ;;
  chatgpt)
    sentinel=""
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${2:-}"
        break
      fi
      shift
    done
    printf 'external reviewer verdict\\n%s\\n' "$sentinel"
    echo 'Tab ID: 837352334' >&2
    echo 'Activated: false' >&2
    echo 'TabWasCreated: false' >&2
    echo 'ResponseSource: assistant-dom' >&2
    echo 'PageTextContainsSentinel: true' >&2
    echo 'DocumentHiddenAtCompletion: true' >&2
    echo 'VisibilityStateAtCompletion: hidden' >&2
    echo 'BackgroundHiddenPolls: 1' >&2
    echo 'BackgroundPollCount: 2' >&2
    exit 0
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 0
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "external reviewer verdict\n"
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "recovered_focus_changed"
    assert meta["failure"] == "focus_stolen_despite_no_activate"
    assert meta["controlled_tab_id"] == "837352334"
    assert meta["controlled_tab_id_mismatch"] is False
    assert meta["raw_contains_sentinel"] is True
    assert meta["clean_contains_sentinel"] is False
    assert meta["focus_changed"] is True
    assert meta["focus_invariant_ok"] is False
    assert meta["transport_degraded"] is True
    assert meta["recovered_output"] is True
