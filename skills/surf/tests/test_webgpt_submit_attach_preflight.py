from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import zipfile
from pathlib import Path
import textwrap


REPO_ROOT = Path(__file__).resolve().parents[3]
WEBGPT_SUBMIT = REPO_ROOT / "skills/surf/scripts/webgpt-submit.sh"
WEBGPT_ROUNDTRIP = REPO_ROOT / "skills/surf/scripts/webgpt-roundtrip-preflight.sh"


def run_submit(
    tmp_path: Path,
    archive: Path,
    fake_run_body: str | None = None,
    extra_env: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
    target_args: list[str] | None = None,
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
    if extra_env:
        env.update(extra_env)
    if target_args is None:
        target_args = [
            "--tab-id",
            "837352334",
            "--expect-url",
            "https://chatgpt.com/c/example",
            "--no-activate",
        ]
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
            *target_args,
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


def test_assistant_snapshot_finds_sentinel_in_baseline_reused_turn(tmp_path: Path) -> None:
    script = tmp_path / "snapshot-baseline-reuse.cjs"
    client = REPO_ROOT / "skills/surf/vendor/surf-cli/native/chatgpt-client.cjs"
    script.write_text(
        textwrap.dedent(
            f"""
            const assert = require('assert');
            const {{ assistantSnapshotExpression }} = require({json.dumps(str(client))});
            class HTMLElement {{}}
            class Node extends HTMLElement {{
              constructor(text, attrs = {{}}) {{
                super();
                this.innerText = text;
                this.textContent = text;
                this.attrs = attrs;
              }}
              getAttribute(name) {{ return this.attrs[name] || null; }}
              querySelector(selector) {{
                if (selector.includes('[data-message-author-role="assistant"]')) return this;
                return null;
              }}
            }}
            const sentinel = '<<<WEBGPT_DONE:abc123>>>';
            const assistant = new Node('review text\\n' + sentinel, {{
              'data-message-author-role': 'assistant',
              'data-message-id': 'msg-1',
            }});
            global.HTMLElement = HTMLElement;
            global.document = {{
              hidden: false,
              visibilityState: 'visible',
              hasFocus: () => true,
              querySelector: () => null,
              querySelectorAll: (selector) => selector.includes('[data-message-author-role="assistant"]')
                ? [assistant]
                : [],
            }};
            const snapshot = eval(assistantSnapshotExpression(sentinel, 1));
            assert.equal(snapshot.source, 'assistant-dom-baseline-fallback');
            assert.equal(snapshot.pageTextContainsSentinel, true);
            assert.equal(snapshot.sentinelMatch, sentinel);
            assert.equal(snapshot.text.includes(sentinel), true);
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["node", str(script)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_type_prompt_replaces_existing_chatgpt_draft(tmp_path: Path) -> None:
    script = tmp_path / "type-prompt-replace.cjs"
    client = REPO_ROOT / "skills/surf/vendor/surf-cli/native/chatgpt-client.cjs"
    script.write_text(
        textwrap.dedent(
            f"""
            const assert = require('assert');
            const {{ typePrompt }} = require({json.dumps(str(client))});
            class EventTarget {{}}
            class HTMLElement extends EventTarget {{}}
            class MouseEvent {{}}
            class InputEvent {{}}
            class Node extends HTMLElement {{
              constructor(value) {{
                super();
                this.value = value;
                this.innerText = value;
                this.textContent = value;
                this.ownerDocument = global.document;
              }}
              focus() {{}}
              dispatchEvent() {{}}
            }}
            const composer = new Node('how many records');
            global.EventTarget = EventTarget;
            global.HTMLElement = HTMLElement;
            global.MouseEvent = MouseEvent;
            global.InputEvent = InputEvent;
            global.window = global;
            global.document = {{
              querySelector: () => composer,
              createRange: () => ({{
                selectNodeContents() {{}},
                collapse() {{}},
              }}),
              getSelection: () => ({{
                removeAllRanges() {{}},
                addRange() {{}},
              }}),
            }};
            composer.ownerDocument = global.document;
            let controlDown = false;
            let selectedAll = false;
            const cdp = async (expression) => {{
              const value = eval(expression);
              return {{ result: {{ value }} }};
            }};
            const inputCdp = async (method, params) => {{
              if (method === 'Input.dispatchKeyEvent') {{
                if (params.key === 'Control') controlDown = params.type === 'keyDown';
                if (params.key === 'a' && controlDown && params.type === 'keyDown') selectedAll = true;
                if (params.key === 'Backspace' && params.type === 'keyDown' && selectedAll) {{
                  composer.value = '';
                  composer.innerText = '';
                  composer.textContent = '';
                  selectedAll = false;
                }}
              }}
              if (method === 'Input.insertText') {{
                composer.value += params.text;
                composer.innerText = composer.value;
                composer.textContent = composer.value;
              }}
              return {{}};
            }};
            const prompt = 'new batch 2 request\\n<<<WEBGPT_DONE:test>>>';
            typePrompt(cdp, inputCdp, prompt).then(() => {{
              assert.equal(composer.value, prompt);
              assert.equal(composer.value.includes('how many records'), false);
            }}).catch((err) => {{
              console.error(err && err.stack || err);
              process.exit(1);
            }});
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["node", str(script)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_chatgpt_client_rejects_busy_page_before_submit(tmp_path: Path) -> None:
    script = tmp_path / "busy-page-preflight.cjs"
    client = REPO_ROOT / "skills/surf/vendor/surf-cli/native/chatgpt-client.cjs"
    script.write_text(
        textwrap.dedent(
            f"""
            const assert = require('assert');
            const {{ assertReadyForNewPrompt }} = require({json.dumps(str(client))});
            class HTMLElement {{}}
            const stop = new HTMLElement();
            const prompt = new HTMLElement();
            global.HTMLElement = HTMLElement;
            global.document = {{
              title: 'ChatGPT - busy',
              querySelector: (selector) => {{
                if (selector.includes('stop-button')) return stop;
                if (selector.includes('prompt-textarea')) return prompt;
                return null;
              }},
            }};
            global.location = {{ href: 'https://chatgpt.com/c/example' }};
            const cdp = async (expression) => ({{ result: {{ value: eval(expression) }} }});
            assertReadyForNewPrompt(cdp).then(() => {{
              console.error('busy page was accepted');
              process.exit(1);
            }}).catch((err) => {{
              assert.match(String(err.message), /page is busy before submit/);
              assert.equal(err.chatgptPageState.stopVisible, true);
            }});
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["node", str(script)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_chatgpt_client_rejects_prompt_left_unsent(tmp_path: Path) -> None:
    script = tmp_path / "prompt-unsent.cjs"
    client = REPO_ROOT / "skills/surf/vendor/surf-cli/native/chatgpt-client.cjs"
    script.write_text(
        textwrap.dedent(
            f"""
            const assert = require('assert');
            const {{ waitForSubmitAccepted }} = require({json.dumps(str(client))});
            class HTMLElement {{
              constructor(text = '') {{
                this.innerText = text;
                this.textContent = text;
                this.value = text;
              }}
            }}
            const promptText = 'review this\\n<<<WEBGPT_DONE:test>>>';
            const composer = new HTMLElement(promptText);
            global.HTMLElement = HTMLElement;
            global.document = {{
              querySelector: (selector) => {{
                if (selector.includes('prompt-textarea')) return composer;
                return null;
              }},
            }};
            const cdp = async (expression) => ({{ result: {{ value: eval(expression) }} }});
            waitForSubmitAccepted(cdp, promptText, 300).then(() => {{
              console.error('unsent prompt was accepted');
              process.exit(1);
            }}).catch((err) => {{
              assert.match(String(err.message), /did not accept submitted prompt/);
              assert.equal(err.chatgptSubmitState.composerStillContainsPrompt, true);
            }});
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["node", str(script)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_webgpt_submit_create_tab_closes_blank_tab_on_navigation_failure(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  tab.new)
    printf 'Created tab 9001: about:blank\\n'
    ;;
  tab.list)
    printf '9001\\tNew Tab\\tabout:blank\\n'
    ;;
  tab.close)
    printf '%s\\n' "${2:-}" > "$PWD/closed-tab.txt"
    ;;
  chatgpt)
    echo 'chatgpt should not run after failed create-tab navigation' >&2
    exit 99
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
        target_args=["--create-tab", "--no-activate"],
    )

    assert proc.returncode == 2
    assert "did not navigate to chatgpt.com; closed it" in proc.stderr
    assert (tmp_path / "closed-tab.txt").read_text(encoding="utf-8").strip() == "9001"
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "create_tab_navigation_failed"
    assert meta["requested_tab_id"] == "9001"


def test_webgpt_roundtrip_terminates_submit_child_on_parent_term(tmp_path: Path) -> None:
    fake_run = tmp_path / "surf-run.sh"
    output_dir = tmp_path / "roundtrip"
    fake_run.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  focus.state)
    printf '{"activeTabId":123,"focusedWindowId":456}\\n'
    ;;
  tab.list)
    printf '[]\\n'
    ;;
  webgpt.preflight)
    printf '{"status":"pass","failures":[]}\\n'
    ;;
  webgpt.submit)
    sleep 300 &
    printf '%s\\n' "$!" > "$PWD/sleeper.pid"
    wait "$!"
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env["SURF_DISPATCH_SH"] = str(fake_run)
    proc = subprocess.Popen(
        [
            "bash",
            str(WEBGPT_ROUNDTRIP),
            "--tab-id",
            "837352334",
            "--expect-url",
            "https://chatgpt.com/c/example",
            "--no-activate",
            "--timeout",
            "30",
            "--output-dir",
            str(output_dir),
            "--json",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    sleeper_pid_file = tmp_path / "sleeper.pid"
    deadline = time.time() + 5
    while time.time() < deadline and not sleeper_pid_file.exists():
        time.sleep(0.05)
    assert sleeper_pid_file.exists(), "fake webgpt.submit child did not start"
    sleeper_pid = sleeper_pid_file.read_text(encoding="utf-8").strip()

    proc.send_signal(signal.SIGTERM)
    stdout, stderr = proc.communicate(timeout=8)

    assert proc.returncode == 143, stderr or stdout
    time.sleep(0.5)
    ps = subprocess.run(
        ["ps", "-p", sleeper_pid, "-o", "stat="],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if ps.returncode == 0:
        subprocess.run(["kill", "-KILL", sleeper_pid], check=False)
    assert ps.returncode != 0, f"orphaned submit child still exists with stat {ps.stdout!r}"


def test_webgpt_submit_defaults_to_full_900_second_timeout(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    expected_timeout=0
    sentinel=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --timeout)
          if [[ "${2:-}" == "900" ]]; then expected_timeout=1; fi
          shift 2
          ;;
        --sentinel)
          sentinel="${2:-}"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done
    if [[ "$expected_timeout" != "1" ]]; then
      echo "missing default --timeout 900" >&2
      exit 88
    fi
    printf 'ok\\n%s\\n' "$sentinel"
    echo 'Tab ID: 837352334' >&2
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
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["requested_reasoning"] == "Pro"


def test_webgpt_submit_allows_reasoning_env_override(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    expected_reasoning=0
    sentinel=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --reasoning)
          if [[ "${2:-}" == "Heavy Reasoning" ]]; then expected_reasoning=1; fi
          shift 2
          ;;
        --sentinel)
          sentinel="${2:-}"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done
    if [[ "$expected_reasoning" != "1" ]]; then
      echo "missing overridden --reasoning Heavy Reasoning" >&2
      exit 88
    fi
    printf 'ok\\n%s\\n' "$sentinel"
    echo 'Tab ID: 837352334' >&2
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

    proc = run_submit(
        tmp_path,
        archive,
        fake_run,
        {"SURF_WEBGPT_REASONING": "Heavy Reasoning"},
    )

    assert proc.returncode == 0, proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["requested_reasoning"] == "Heavy Reasoning"


def test_webgpt_submit_writes_distinct_submit_receipt(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    host_log = tmp_path / "surf-host.log"
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    sentinel=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --sentinel)
          sentinel="${2:-}"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done
    printf '%s Prompt accepted: sentinel=%s stopVisible=true composerChars=0\\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$sentinel" >> "${SURF_WEBGPT_HOST_LOG:?}"
    printf 'ok\\n%s\\n' "$sentinel"
    echo 'Tab ID: 837352334' >&2
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

    proc = run_submit(
        tmp_path,
        archive,
        fake_run,
        {"SURF_WEBGPT_HOST_LOG": str(host_log)},
    )

    assert proc.returncode == 0, proc.stderr
    receipt = json.loads((tmp_path / "response.md.receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "submitted_to_chatgpt"
    assert receipt["submitted_to_chatgpt"] is True
    assert receipt["prepared_prompt_is_transport_proof"] is False
    assert receipt["requested_reasoning"] == "Pro"


def test_webgpt_submit_notification_assisted_wait_is_advisory_only(tmp_path: Path) -> None:
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
    printf 'notification may have fired, but sentinel proves completion\\n%s\\n' "$sentinel"
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

    proc = run_submit(tmp_path, archive, fake_run, extra_args=["--notification-assisted-wait"])

    assert proc.returncode == 0, proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["raw_contains_sentinel"] is True
    assert meta["notification_assisted_wait_requested"] is True
    assert meta["notification_assisted_wait_completion_proof"] is False
    assert meta["notification_assisted_wait_reason"] == "advisory_wake_only_sentinel_required"


FAKE_RUN_PREAMBLE = """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  tab.list)
    printf '837352334\\tAgentic Research - Boris Loop\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{"active_tab_id":"123","active_window_id":"456"}\\n'
    ;;
"""


FAKE_RUN_ACTIVE_PREAMBLE = """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  tab.list)
    printf '837352334\\tAgentic Research - Boris Loop\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{"focusedWindowId":456,"activeTabId":837352334}\\n'
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

    proc = run_submit(tmp_path, archive, fake_run, {"SURF_WEBGPT_ADVISORY_AFTER_SECONDS": "600"})

    assert proc.returncode == 7
    assert "simulated browser failure" in proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["exit_code"] == 7
    assert meta["requested_tab_id"] == "837352334"
    assert meta["tab_identity_preflight"]["ok"] is True


def test_webgpt_submit_no_activate_allows_already_active_controlled_tab(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_ACTIVE_PREAMBLE
        + """  chatgpt)
    sentinel=""
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${2:-}"
        break
      fi
      shift
    done
    printf 'same-tab observed response\\n%s\\n' "$sentinel"
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
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "same-tab observed response\n"
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["controlled_tab_id"] == "837352334"
    assert meta["focus_changed"] is False
    assert meta["active_tab_before"] == 837352334
    assert meta["active_tab_after"] == 837352334


def test_webgpt_submit_roundtrip_preflight_blocks_main_prompt(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_ACTIVE_PREAMBLE
        + """  chatgpt)
    prompt="${2:-}"
    if printf '%s' "$prompt" | grep -q 'WEBGPT_PREFLIGHT_DONE'; then
      echo 'hidden preflight stall'
      echo 'Tab ID: 837352334' >&2
      echo 'ResponseSource: assistant-dom' >&2
      echo 'ResponseTimedOut: true' >&2
      echo 'TimeoutError: Response timeout; hidden_polls=8; last_visibility=hidden; document_hidden=true' >&2
      exit 0
    fi
    echo 'MAIN_PROMPT_SHOULD_NOT_RUN' >> "$PWD/main-ran.txt"
    echo 'main response'
    exit 0
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""
    )

    proc = run_submit(tmp_path, archive, fake_run, extra_args=["--roundtrip-preflight", "--roundtrip-timeout", "5"])

    assert proc.returncode == 6
    assert not (tmp_path / "main-ran.txt").exists()
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "roundtrip_preflight_failed"
    assert meta["roundtrip_preflight_required"] is True
    assert "hidden_tab_stall" in meta["roundtrip_preflight"]["failures"]
    assert meta["roundtrip_preflight"]["diagnosis"]["hidden_tab_stall"] is True


def test_webgpt_submit_roundtrip_preflight_success_is_recorded(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_ACTIVE_PREAMBLE
        + """  chatgpt)
    sentinel=""
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${2:-}"
        break
      fi
      shift
    done
    printf 'ok\\n%s\\n' "$sentinel"
    echo 'Tab ID: 837352334' >&2
    echo 'Activated: false' >&2
    echo 'TabWasCreated: false' >&2
    echo 'ResponseSource: assistant-dom' >&2
    echo 'PageTextContainsSentinel: true' >&2
    echo 'DocumentHiddenAtCompletion: false' >&2
    echo 'VisibilityStateAtCompletion: visible' >&2
    echo 'BackgroundHiddenPolls: 0' >&2
    echo 'BackgroundPollCount: 2' >&2
    exit 0
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""
    )

    proc = run_submit(tmp_path, archive, fake_run, extra_args=["--roundtrip-preflight", "--roundtrip-timeout", "5"])

    assert proc.returncode == 0, proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["roundtrip_preflight_required"] is True
    assert meta["roundtrip_preflight"]["status"] == "pass"
    assert meta["roundtrip_preflight"]["diagnosis"]["raw_contains_sentinel"] is True


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


def test_webgpt_submit_failure_without_raw_extracts_available_tab_text(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    echo 'simulated sentinel wait failure with no stdout' >&2
    exit 124
    ;;
  chatgpt.extract)
    echo 'available same-tab assistant text after soft timeout'
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""
    )

    proc = run_submit(tmp_path, archive, fake_run, {"SURF_WEBGPT_ADVISORY_AFTER_SECONDS": "3"})

    assert proc.returncode == 124
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == (
        "available same-tab assistant text after soft timeout\n"
    )
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "submit_failed"
    assert meta["raw_response_advisory"] is True
    assert meta["extract_fallback_used"] is True
    assert meta["extract_fallback_reason"] == "submit_failed"
    assert meta["response_source"] == "webgpt-extract-fallback"


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
