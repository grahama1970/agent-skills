from __future__ import annotations

import json
import os
import subprocess
import zipfile
from pathlib import Path
import textwrap


REPO_ROOT = Path(__file__).resolve().parents[3]
WEBGPT_SUBMIT = REPO_ROOT / "skills/surf/scripts/webgpt-submit.sh"


def run_submit(
    tmp_path: Path,
    archive: Path,
    fake_run_body: str | None = None,
    extra_env: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
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
            "837352334",
            "--expect-url",
            "https://chatgpt.com/c/example",
            "--no-activate",
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
