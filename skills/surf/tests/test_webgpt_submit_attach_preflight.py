from __future__ import annotations

import json
import os
import subprocess
import time
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
WEBGPT_SUBMIT = REPO_ROOT / "skills/surf/scripts/webgpt-submit.sh"
WEBGPT_PROMPT_PREFLIGHT = REPO_ROOT / "skills/surf/scripts/lib/webgpt_prompt_preflight.py"


def run_submit(
    tmp_path: Path,
    archive: Path,
    fake_run_body: str | None = None,
    tab_id: str | None = "837352334",
    extra_args: list[str] | None = None,
    env_overrides: dict[str, str] | None = None,
    no_activate: bool = True,
    request_text: str = "review the attached bundle\n",
) -> subprocess.CompletedProcess[str]:
    request = tmp_path / "request.md"
    output = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    fake_run = tmp_path / "surf-run.sh"
    request.write_text(request_text, encoding="utf-8")
    fake_run.write_text(
        fake_run_body
        or "#!/usr/bin/env bash\necho unexpected surf invocation >&2\nexit 99\n",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(fake_run)
    env["SURF_WEBGPT_EXTRACT_FALLBACK_BUDGET"] = "0"
    env["SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS"] = "0"
    env["SURF_WEBGPT_HOST_LOG"] = str(tmp_path / "surf-host.log")
    env["TMPDIR"] = str(tmp_path)
    if env_overrides:
        env.update(env_overrides)
    command = [
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
    ]
    if tab_id is not None:
        command.extend(["--tab-id", tab_id, "--expect-url", "https://chatgpt.com/c/example"])
    if no_activate:
        command.append("--no-activate")
    command.extend(extra_args or [])
    return subprocess.run(
        command,
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


def test_prompt_preflight_does_not_treat_tilde_digit_approximation_as_path(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    request.write_text(
        "Please expand the stratified random sample to ~20 pages.\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            "python3",
            str(WEBGPT_PROMPT_PREFLIGHT),
            "--input",
            str(request),
            "--json",
            "--warn-only",
        ],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "pass"
    assert payload["local_paths"] == []
    assert payload["browser_submit_allowed"] is True


def test_webgpt_submit_allows_warn_preflight_and_records_metadata(tmp_path: Path) -> None:
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
    printf 'warning allowed response\\n%s\\n' "$sentinel"
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

    proc = run_submit(
        tmp_path,
        archive,
        fake_run,
        request_text="Review this prose mention of /tmp/nonexistent-webgpt-warning-only.\n",
    )

    assert proc.returncode == 0, proc.stderr
    assert "Proceeding because --warn-only was set" in proc.stderr
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "warning allowed response\n"
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["prompt_path_preflight"]["status"] == "warn"
    assert meta["prompt_path_preflight"]["browser_submit_allowed"] is True
    assert meta["prompt_path_preflight"]["local_paths"] == [
        {"path": "/tmp/nonexistent-webgpt-warning-only", "exists_locally": False}
    ]


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


def test_webgpt_submit_cdp_probe_lock_timeout_is_not_stale_cdp(tmp_path: Path) -> None:
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
    echo 'SURF_BROWSER_LOCK_BLOCKED {{"schema":"surf.browser_lock_blocker.v1","blocker":"surf_browser_lock_timeout","owner":{{"pid":3290346}}}}' >&2
    echo 'Error: Timed out waiting for browser lock after 2s. owner_pid=3290346 owner_socket=unix:/tmp/surf.sock lock_dir=/tmp/surf-lock-example.' >&2
    exit 1
    ;;
  extension.reload|extension.ping|tab.new|chatgpt)
    echo "forbidden fallback/submission command: $*" >&2
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
        env_overrides={"SURF_LOCK_TIMEOUT_MS": "2000"},
    )

    assert proc.returncode == 6
    assert "Surf browser lock blocked CDP probe" in proc.stderr
    log = invocation_log.read_text(encoding="utf-8")
    assert "--lock-timeout 2" in log
    assert "extension.reload" not in log
    assert "chatgpt" not in log
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "browser_cdp_lock_timeout"
    assert meta["proof_status"] == "not_submitted"
    assert meta["submitted_to_chatgpt"] is False
    assert meta["browser_lock_blocked"] is True
    assert meta["cdp_retry_attempted"] is False
    assert "SURF_BROWSER_LOCK_BLOCKED" in meta["cdp_probe_stderr"]
    assert meta["agent_diagnosis"] == (
        "Surf could not run the CDP pre-submit probe because the shared browser lock was held."
    )


def test_webgpt_submit_cdp_probe_timeout_writes_failure_meta(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  tab.list)
    printf '837352334\\tAgentic Research - Boris Loop\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{"active_tab_id":"123","active_window_id":"456"}\\n'
    ;;
  js)
    sleep 5
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

    proc = run_submit(
        tmp_path,
        archive,
        fake_run,
        env_overrides={"SURF_WEBGPT_CDP_PROBE_TIMEOUT_SECONDS": "1"},
    )

    assert proc.returncode == 6
    assert "same-tab extension reload retry" in proc.stderr
    meta_path = tmp_path / "response.meta.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "stale_cdp_on_explicit_tab"
    assert meta["proof_status"] == "not_submitted"
    assert meta["submitted_to_chatgpt"] is False
    assert meta["browser_lock_blocked"] is False
    assert meta["cdp_retry_attempted"] is True
    assert "SURF_CDP_PROBE_TIMEOUT after 1s" in meta["cdp_probe_stderr"]
    assert "SURF_CDP_PROBE_TIMEOUT after 1s" in meta["cdp_retry_stderr"]


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


def test_webgpt_submit_strips_chatgpt_feedback_chrome_after_sentinel(tmp_path: Path) -> None:
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
    printf 'clean response\\n%s\\n\\nIs this conversation helpful so far?\\n' "$sentinel"
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
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "clean response\n"
    raw = (tmp_path / "response.md.raw.md").read_text(encoding="utf-8")
    assert "Is this conversation helpful so far?" in raw
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


def test_webgpt_submit_exports_default_stable_stall_budget(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    env_log = tmp_path / "stable-stall-env.log"
    fake_run = (
        FAKE_RUN_PREAMBLE
        + f"""  chatgpt)
    printf '%s\\n' "${{SURF_WEBGPT_STABLE_STALL_MS:-unset}}" > {str(env_log)!r}
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${{2:-}}"
        break
      fi
      shift
    done
    printf 'finished answer\\n%s\\n' "$sentinel"
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
    assert env_log.read_text(encoding="utf-8").strip() == "30000"


def test_webgpt_submit_stable_stall_zero_disables_fast_stall(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    env_log = tmp_path / "stable-stall-env.log"
    fake_run = (
        FAKE_RUN_PREAMBLE
        + f"""  chatgpt)
    printf '%s\\n' "${{SURF_WEBGPT_STABLE_STALL_MS:-unset}}" > {str(env_log)!r}
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${{2:-}}"
        break
      fi
      shift
    done
    printf 'finished answer\\n%s\\n' "$sentinel"
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

    proc = run_submit(tmp_path, archive, fake_run, extra_args=["--stable-stall-ms", "0"])

    assert proc.returncode == 0, proc.stderr
    assert env_log.read_text(encoding="utf-8").strip() == "0"


def test_webgpt_submit_auto_open_binds_missing_browser_oracle_tab(
    tmp_path: Path, monkeypatch
) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    bo_log = tmp_path / "browser-oracle.log"
    fake_browser_oracle = tmp_path / "browser-oracle-run.sh"
    fake_browser_oracle.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(bo_log)!r}
case "${{1:-}}" in
  resolve)
    printf '{{"status":"ok","project":"demo","tab_id":"123","conversation_url":"https://chatgpt.com/c/demo"}}\\n'
    ;;
  reconcile)
    printf '{{"status":"needs_attention","rows":[{{"project":"demo","status":"missing_live_tab","stored_tab_id":"123","stored_url":"https://chatgpt.com/c/demo"}}]}}\\n'
    exit 1
    ;;
  open-bind)
    printf '{{"status":"open_bound","project":"demo","tab_id":"456","conversation_url":"https://chatgpt.com/c/demo","state_path":"/tmp/demo.json"}}\\n'
    ;;
  *)
    echo "unexpected browser-oracle command: $*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_browser_oracle.chmod(0o755)
    monkeypatch.setenv("BROWSER_ORACLE_RUN", str(fake_browser_oracle))
    fake_run = """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  tab.list)
    if [[ "${2:-}" == "--json" ]]; then
      printf '[{"id":456,"title":"ChatGPT demo","url":"https://chatgpt.com/c/demo"}]\n'
    else
      printf '456\tChatGPT demo\thttps://chatgpt.com/c/demo\n'
    fi
    ;;
  focus.state)
    printf '{"active_tab_id":"123","active_window_id":"456"}\n'
    ;;
  js)
    printf '"cdp-ok"\n'
    ;;
  chatgpt)
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${2:-}"
        break
      fi
      shift
    done
    printf 'Prompt accepted: sentinel=%s\n' "$sentinel" > "${SURF_WEBGPT_HOST_LOG:-/tmp/surf-host.log}"
    printf 'browser oracle rebound response\n%s\n' "$sentinel"
    echo 'Tab ID: 456' >&2
    echo 'ResponseSource: assistant-dom' >&2
    exit 0
    ;;
  *)
    echo "unexpected surf command: $*" >&2
    exit 99
    ;;
esac
"""

    proc = run_submit(tmp_path, archive, fake_run, tab_id=None, extra_args=["--project", "demo"])

    assert proc.returncode == 0, proc.stderr
    log = bo_log.read_text(encoding="utf-8")
    assert "resolve --from" in log
    assert "reconcile --backend webgpt --json --project demo" in log
    assert "open-bind demo --backend webgpt --url https://chatgpt.com/c/demo --manual --json" in log
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["requested_tab_id"] == "456"
    assert meta["controlled_tab_id"] == "456"
    assert meta["controlled_tab_id_mismatch"] is False


def test_webgpt_submit_cloudflare_challenge_fails_closed_without_extract_retry(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    invocation_log = tmp_path / "surf-invocations.log"
    fake_run = f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(invocation_log)!r}
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tCloudflare check\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  js)
    printf '"cdp-ok"\\n'
    ;;
  chatgpt)
    echo 'Error: Cloudflare challenge detected - complete in browser' >&2
    exit 1
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 1
    assert "Cloudflare challenge detected" in proc.stderr
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "cloudflare_challenge"
    assert meta["blocker"] == "BLOCKED_WEBGPT_CLOUDFLARE_CHALLENGE"
    assert meta["recommended_action"] == "complete_cloudflare_challenge_in_controlled_browser_tab"
    assert meta["proof_status"] == "browser_access_blocked"
    assert meta["submitted_to_chatgpt"] is False
    assert meta["browser_access_blocked"] is True
    assert meta["cloudflare_challenge_detected"] is True
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "chatgpt " in invocations


def test_webgpt_submit_visible_provider_limit_uses_bounded_cooldown_retry(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    invocation_log = tmp_path / "surf-invocations.log"
    chatgpt_count_file = tmp_path / "chatgpt-count"
    fake_run = f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(invocation_log)!r}
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tRate limited\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  js)
    if [[ "$*" == *"cdp-ok"* ]]; then
      printf '"cdp-ok"\\n'
    else
      echo "no visible Got it modal on hit-your-limit page" >&2
      exit 12
    fi
    ;;
  chatgpt)
    count="$(cat {str(chatgpt_count_file)!r} 2>/dev/null || printf '0')"
    count="$((count + 1))"
    printf '%s' "$count" > {str(chatgpt_count_file)!r}
    sentinel=""
    target_tab=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --sentinel) sentinel="${{2:-}}"; shift 2 ;;
        --target-tab-id) target_tab="${{2:-}}"; shift 2 ;;
        *) shift ;;
      esac
    done
    if [[ "$count" -eq 1 ]]; then
      echo "Error: ChatGPT is rate limited: too many requests; you've hit your limit. Please try again later." >&2
      exit 1
    fi
    if [[ "$target_tab" != "837352334" ]]; then
      echo "expected same-tab retry target 837352334, got $target_tab" >&2
      exit 43
    fi
    printf 'same tab response after hit-your-limit cooldown\\n%s\\n' "$sentinel"
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

    proc = run_submit(
        tmp_path,
        archive,
        fake_run,
        env_overrides={"SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS": "1"},
    )

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == (
        "same tab response after hit-your-limit cooldown\n"
    )
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["requested_tab_id"] == "837352334"
    assert meta["controlled_tab_id"] == "837352334"
    assert meta["chatgpt_too_many_requests_detected"] is True
    assert meta["chatgpt_rate_limit"]["wait_seconds"] == 0
    assert meta["chatgpt_rate_limit"]["retry_attempts"] == 1
    assert meta["chatgpt_rate_limit"]["dismiss_attempted"] is True
    assert meta["chatgpt_rate_limit"]["dismissed"] is False
    assert meta["chatgpt_rate_limit"]["retry_attempted"] is True
    assert meta["chatgpt_rate_limit"]["exhausted"] is False
    assert invocation_log.read_text(encoding="utf-8").count("chatgpt ") == 2


def test_webgpt_submit_provider_limit_without_sentinel_sets_rate_limit_blocker(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    chatgpt_count_file = tmp_path / "chatgpt-count"
    fake_run = f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tRate limited\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  js)
    printf '"cdp-ok"\\n'
    ;;
  chatgpt)
    count="$(cat {str(chatgpt_count_file)!r} 2>/dev/null || printf '0')"
    count="$((count + 1))"
    printf '%s' "$count" > {str(chatgpt_count_file)!r}
    if [[ "$count" -eq 1 ]]; then
      echo "Error: ChatGPT is rate limited: too many requests; you've hit your limit. Please try again later." >&2
      exit 1
    fi
    echo 'Error: ChatGPT is rate limited: too many requests; retry still blocked' >&2
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
        env_overrides={"SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS": "1"},
    )

    assert proc.returncode != 0
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "submit_failed"
    assert meta["blocker"] == "BLOCKED_WEBGPT_PROVIDER_RATE_LIMIT"
    assert meta["recommended_action"] == "wait_for_chatgpt_rate_limit_cooldown_before_retry"
    assert meta["proof_status"] == "rate_limited"
    assert meta["chatgpt_too_many_requests_detected"] is True
    assert meta["chatgpt_rate_limit"]["error"] == "retry_failed_exit_42"
    assert chatgpt_count_file.read_text(encoding="utf-8") == "2"


def test_webgpt_submit_clicks_start_new_chat_same_tab_on_conversation_max_length(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    invocation_log = tmp_path / "surf-invocations.log"
    chatgpt_count_file = tmp_path / "chatgpt-count"
    fake_run = f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(invocation_log)!r}
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tFull conversation\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  js)
    if [[ "$*" == *"start_new_chat_control_not_found"* || "$*" == *"Start new chat"* || "$*" == *"start new chat"* ]]; then
      printf '%s\n' '"{{\"clicked\":true,\"text\":\"Start new chat\",\"url\":\"https://chatgpt.com/c/example\"}}"'
    else
      printf '"cdp-ok"\\n'
    fi
    ;;
  tab.new)
    echo "fresh tab should not be created when same-tab Start new chat works" >&2
    exit 44
    ;;
  chatgpt)
    count="$(cat {str(chatgpt_count_file)!r} 2>/dev/null || printf '0')"
    count="$((count + 1))"
    printf '%s' "$count" > {str(chatgpt_count_file)!r}
    sentinel=""
    target_tab=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --sentinel) sentinel="${{2:-}}"; shift 2 ;;
        --target-tab-id) target_tab="${{2:-}}"; shift 2 ;;
        *) shift ;;
      esac
    done
    if [[ "$count" -eq 1 ]]; then
      echo 'Error: ChatGPT conversation reached maximum length; start a new chat is required' >&2
      exit 1
    fi
    if [[ "$target_tab" != "837352334" ]]; then
      echo "expected same-tab rollover target 837352334, got $target_tab" >&2
      exit 43
    fi
    printf 'same tab response after rollover\\n%s\\n' "$sentinel"
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

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "same tab response after rollover\n"
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["requested_tab_id"] == "837352334"
    assert meta["controlled_tab_id"] == "837352334"
    assert meta["conversation_max_length_detected"] is True
    assert meta["conversation_max_length_rollover"] == {
        "attempted": True,
        "from_tab_id": "837352334",
        "to_tab_id": "837352334",
        "action": "click_start_new_chat_same_tab_and_resubmit",
        "error": None,
    }
    receipt = json.loads((tmp_path / "response.md.receipt.json").read_text(encoding="utf-8"))
    assert receipt["submitted_to_chatgpt"] is True
    assert receipt["requested_tab_id"] == "837352334"
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "tab.new https://chatgpt.com/ --background" not in invocations
    assert "Start new chat" in invocations or "start new chat" in invocations
    assert invocations.count("chatgpt ") == 2


def test_webgpt_submit_cools_down_and_retries_same_tab_on_too_many_requests(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    invocation_log = tmp_path / "surf-invocations.log"
    chatgpt_count_file = tmp_path / "chatgpt-count"
    fake_run = f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(invocation_log)!r}
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tThrottled conversation\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  js)
    if [[ "$*" == *"got_it_control_not_found"* || "$*" == *"Got it"* || "$*" == *"got it"* ]]; then
      printf '%s\n' '"{{\"dismissed\":true,\"text\":\"Got it\",\"url\":\"https://chatgpt.com/c/example\"}}"'
    else
      printf '"cdp-ok"\\n'
    fi
    ;;
  tab.new)
    echo "fresh tab should not be created for rate-limit cooldown" >&2
    exit 44
    ;;
  chatgpt)
    count="$(cat {str(chatgpt_count_file)!r} 2>/dev/null || printf '0')"
    count="$((count + 1))"
    printf '%s' "$count" > {str(chatgpt_count_file)!r}
    sentinel=""
    target_tab=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --sentinel) sentinel="${{2:-}}"; shift 2 ;;
        --target-tab-id) target_tab="${{2:-}}"; shift 2 ;;
        *) shift ;;
      esac
    done
    if [[ "$count" -eq 1 ]]; then
      echo 'Error: ChatGPT is rate limited: too many requests; wait before retrying' >&2
      exit 1
    fi
    if [[ "$target_tab" != "837352334" ]]; then
      echo "expected same-tab retry target 837352334, got $target_tab" >&2
      exit 43
    fi
    printf 'same tab response after cooldown\\n%s\\n' "$sentinel"
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

    proc = run_submit(
        tmp_path,
        archive,
        fake_run,
        env_overrides={"SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS": "1"},
    )

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "same tab response after cooldown\n"
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["requested_tab_id"] == "837352334"
    assert meta["controlled_tab_id"] == "837352334"
    assert meta["chatgpt_too_many_requests_detected"] is True
    assert meta["chatgpt_rate_limit"]["wait_seconds"] == 0
    assert meta["chatgpt_rate_limit"]["retry_attempts"] == 1
    assert meta["chatgpt_rate_limit"]["dismiss_attempted"] is True
    assert meta["chatgpt_rate_limit"]["dismissed"] is True
    assert meta["chatgpt_rate_limit"]["retry_attempted"] is True
    assert meta["chatgpt_rate_limit"]["exhausted"] is False
    assert meta["chatgpt_rate_limit"]["action"] == "dismiss_got_it_cooldown_and_retry"
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "tab.new https://chatgpt.com/ --background" not in invocations
    assert "Got it" in invocations or "got it" in invocations
    assert invocations.count("chatgpt ") == 2


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


def test_webgpt_submit_stable_without_sentinel_is_reported_in_meta(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${2:-}"
        break
      fi
      shift
    done
    printf 'Prompt accepted: sentinel=%s\n' "$sentinel" > "${SURF_WEBGPT_HOST_LOG:-/tmp/surf-host.log}"
    echo 'complete stabilized reviewer answer without sentinel'
    echo 'Tab ID: 837352334' >&2
    echo 'ResponseSource: assistant-dom' >&2
    echo 'ResponseTimedOut: true' >&2
    echo 'StableResponseWithoutSentinel: true' >&2
    echo 'StableStallMs: 31000' >&2
    echo 'TimeoutError: Stable assistant response stalled without sentinel after 31000ms' >&2
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
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "missing_sentinel"
    assert meta["failure"] == "missing_sentinel"
    assert meta["stable_response_without_sentinel"] is True
    assert meta["stable_stall_ms"] == 31000
    assert meta["proof_status"] == "submitted_no_response_proof"
    assert "stabilized without the current completion sentinel" in meta["agent_diagnosis"]


def test_webgpt_submit_empty_timeout_has_distinct_fresh_conversation_failure(tmp_path: Path) -> None:
    archive = tmp_path / "five.zip"
    make_zip(archive, 5)
    fake_run = (
        FAKE_RUN_PREAMBLE
        + """  chatgpt)
    echo 'Tab ID: 837352334' >&2
    echo 'ResponseSource: assistant-dom' >&2
    echo 'ResponseTimedOut: true' >&2
    echo 'TimeoutError: Request timed out (12s)' >&2
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
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed"
    assert meta["failure"] == "chatgpt_empty_response_after_submit"
    assert meta["blocker"] == "BLOCKED_WEBGPT_EMPTY_RESPONSE_AFTER_SUBMIT"
    assert meta["recommended_action"] == "retry_with_fresh_chatgpt_conversation"
    assert meta["raw_chars"] == 0
    assert meta["proof_status"] in {"submitted_no_response_proof", "delivery_not_proven"}


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
    if (err.code !== 'stable_response_without_sentinel') {{
      console.error('unexpected error code', err.code);
      process.exit(4);
    }}
    if (err.partialResponse.stableResponseWithoutSentinel !== true) {{
      console.error('stable flag missing');
      process.exit(5);
    }}
    if (!Number.isFinite(err.partialResponse.stableStallMs)) {{
      console.error('stable stall ms missing');
      process.exit(6);
    }}
    if (Date.now() - started > 5000) {{
      console.error('waited too long');
      process.exit(7);
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


def test_chatgpt_client_detects_conversation_max_length_message(tmp_path: Path) -> None:
    node_script = tmp_path / "conversation-max-length.js"
    client_path = REPO_ROOT / "skills/surf/vendor/surf-cli/native/chatgpt-client.cjs"
    node_script.write_text(
        f"""
const client = require({json.dumps(str(client_path))});
if (!client.detectsConversationMaxLength("You've reached the maximum length for this conversation, but you can keep talking by starting a new chat.")) {{
  console.error('expected exact max-length message to be detected');
  process.exit(1);
}}
if (!client.detectsConversationMaxLength("You’ve reached the maximum length for this conversation. Keep talking by starting a new chat.")) {{
  console.error('expected curly apostrophe max-length message to be detected');
  process.exit(2);
}}
if (client.detectsConversationMaxLength("Start a new chat whenever you want.")) {{
  console.error('new-chat affordance alone must not trigger rollover');
  process.exit(3);
}}
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


def test_chatgpt_client_detects_too_many_requests_message(tmp_path: Path) -> None:
    node_script = tmp_path / "too-many-requests.js"
    client_path = REPO_ROOT / "skills/surf/vendor/surf-cli/native/chatgpt-client.cjs"
    node_script.write_text(
        f"""
const client = require({json.dumps(str(client_path))});
if (!client.detectsTooManyRequests("Too many requests\\n\\nYou're making requests too quickly. We've temporarily limited access to your conversations to protect your data.\\n\\nPlease wait a few minutes before trying again.")) {{
  console.error('expected exact rate-limit modal to be detected');
  process.exit(1);
}}
if (!client.detectsTooManyRequests("Too many requests\\n\\nYou’re making requests too quickly. We’ve temporarily limited access to your conversations to protect your data.")) {{
  console.error('expected curly apostrophe rate-limit modal to be detected');
  process.exit(2);
}}
if (!client.detectsTooManyRequests("You've hit your limit. Please try again later. Retry")) {{
  console.error('expected hit-your-limit retry copy to be detected');
  process.exit(3);
}}
if (client.detectsTooManyRequests("Please wait a few minutes before trying again.")) {{
  console.error('wait text alone must not trigger rate-limit handling');
  process.exit(4);
}}
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


def test_webgpt_submit_rate_limit_retries_are_opt_in() -> None:
    script = (REPO_ROOT / "skills/surf/scripts/webgpt-submit.sh").read_text(encoding="utf-8")

    assert 'rate_limit_retry_attempts="${SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS:-0}"' in script
    assert "ChatGPTTooManyRequestsDetected: true" in script
    assert "ChatGPTRateLimitRetryAttempted: false" in script


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
    assert meta["focus_drift_warning"] == "focus_stolen_despite_no_activate"
    assert meta["proof_status"] == "response_proven"
    assert meta["controlled_tab_id"] == "837352334"
    assert meta["controlled_tab_id_mismatch"] is False
    assert meta["raw_contains_sentinel"] is True
    assert meta["clean_contains_sentinel"] is False
    assert meta["focus_changed"] is True
    assert meta["focus_invariant_ok"] is False
    assert meta["transport_degraded"] is True
    assert meta["recovered_output"] is True


def test_webgpt_submit_recovers_focus_drift_when_tab_id_line_missing_but_preflight_verified(
    tmp_path: Path,
) -> None:
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

    proc = run_submit(tmp_path, archive, fake_run)

    assert proc.returncode == 0
    assert (tmp_path / "response.md").read_text(encoding="utf-8") == "external reviewer verdict\n"
    meta = json.loads((tmp_path / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "recovered_focus_changed"
    assert meta["failure"] == "focus_stolen_despite_no_activate"
    assert meta["proof_status"] == "response_proven"
    assert meta["response_proof_status"] == "response_proven"
    assert meta["controlled_tab_id"] == "837352334"
    assert meta["conversation_url"] == "https://chatgpt.com/c/example"
    assert meta["raw_contains_sentinel"] is True
    assert meta["clean_contains_sentinel"] is False
    assert meta["focus_invariant_ok"] is False
    assert meta["transport_degraded"] is True
