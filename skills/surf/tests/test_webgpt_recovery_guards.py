from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EXTRACT = REPO_ROOT / "skills/surf/scripts/webgpt-extract.sh"
SUBMIT = REPO_ROOT / "skills/surf/scripts/webgpt-submit.sh"
CLI = REPO_ROOT / "skills/surf/vendor/surf-cli/native/cli.cjs"
KIMI_CLIENT = REPO_ROOT / "skills/surf/vendor/surf-cli/native/kimi-tab-client.cjs"


def test_extract_rejects_malformed_tab_id_before_browser_call(tmp_path: Path) -> None:
    called = tmp_path / "called"
    fake_run = tmp_path / "run.sh"
    fake_run.write_text(f"#!/usr/bin/env bash\ntouch {called!s}\n", encoding="utf-8")
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env["SURF_RUN_SH"] = str(fake_run)

    proc = subprocess.run(
        ["bash", str(EXTRACT), "--tab-id", "83x7", "--output", str(tmp_path / "out.md")],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "Invalid --tab-id" in proc.stderr
    assert not called.exists()


def test_submit_finalizer_has_no_implicit_followup_submission() -> None:
    source = SUBMIT.read_text(encoding="utf-8")
    auto_download = source.split("# ── --auto-download", 1)[1].split("# ── --verify-cmd", 1)[0]

    assert "document.execCommand" not in auto_download
    assert 'key Enter' not in auto_download
    assert "No follow-up was submitted" in auto_download


def test_submit_never_deletes_or_clears_existing_drafts() -> None:
    source = SUBMIT.read_text(encoding="utf-8")

    assert "localStorage.removeItem" not in source
    assert "keys.forEach" not in source
    assert "ta.innerHTML = '<p></p>'" not in source


def test_submit_passes_prompt_using_native_cli_positional_contract() -> None:
    source = SUBMIT.read_text(encoding="utf-8")

    assert 'args=(chatgpt "$submitted_query"' in source
    assert "--query-file" not in source


def test_native_reconnect_waits_on_same_tab_without_activation() -> None:
    source = CLI.read_text(encoding="utf-8")
    recovery = source.split("async function attemptChatgptRecovery()", 1)[1].split("const performAutoCapture", 1)[0]

    assert '"tab-id": tabId' in recovery
    assert "sentinel" in recovery
    assert "wait: true" in recovery
    assert '"no-activate": true' in recovery
    assert '"stable-polls"' in recovery


def test_kimi_provider_capacity_busy_fails_fast() -> None:
    source = KIMI_CLIENT.read_text(encoding="utf-8")

    assert "providerBusy" in source
    assert "system is currently busy" in source
    assert "capacity is busy" in source
    assert "Kimi provider capacity busy" in source


def test_kimi_formatter_emits_controlled_tab_metadata() -> None:
    source = CLI.read_text(encoding="utf-8")
    formatter = source.split('tool === "kimi_tab"', 1)[1].split('tool === "aistudio"', 1)[0]

    assert "Tab ID:" in formatter
    assert "controlledTabId" in formatter
    assert "Activated:" in formatter
    assert "TabWasCreated:" in formatter


def test_nonzero_submit_with_exact_sentinel_recovery_reaches_finalization(tmp_path: Path) -> None:
    sentinel = "<<<WEBGPT_DONE:recovery-guard>>>"
    request = tmp_path / "request.md"
    output = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    host_log = tmp_path / "host.log"
    calls = tmp_path / "calls.log"
    fake_run = tmp_path / "run.sh"
    request.write_text("recover this turn\n", encoding="utf-8")
    host_log.write_text(f"Prompt accepted: sentinel={sentinel}\n", encoding="utf-8")
    fake_run.write_text(
        f'''#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> {str(calls)!r}
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tRecovery Test\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  js)
    printf 'cdp-ok\\n'
    ;;
  chatgpt)
    printf 'partial response\\n'
    printf 'Tab ID: 837352334\\nResponseSource: assistant-dom\\n' >&2
    exit 7
    ;;
  chatgpt.extract)
    printf 'recovered response\\n{sentinel}\\n'
    ;;
  *)
    printf 'unexpected command: %s\\n' "$*" >&2
    exit 99
    ;;
esac
''',
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "SURF_RUN_SH": str(fake_run),
        "SURF_WEBGPT_HOST_LOG": str(host_log),
        "SURF_WEBGPT_EXTRACT_FALLBACK_BUDGET": "5",
    })

    proc = subprocess.run(
        [
            "bash", str(SUBMIT), "--input", str(request), "--output", str(output),
            "--meta-output", str(meta), "--sentinel", sentinel, "--tab-id", "837352334",
            "--expect-url", "https://chatgpt.com/c/example", "--no-activate", "--timeout", "5",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = __import__("json").loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] in {"completed", "recovered_focus_changed"}
    assert payload["response_proof_status"] == "response_proven"
    assert payload["extract_fallback_used"] is True
    assert payload["extract_fallback_reason"] == "submit_failed"
    assert sentinel in output.with_suffix(".md.raw.md").read_text(encoding="utf-8")
    assert sentinel not in output.read_text(encoding="utf-8")
    invocation_text = calls.read_text(encoding="utf-8")
    assert "chatgpt.extract" in invocation_text
    assert "tab.new" not in invocation_text
    assert "key Enter" not in invocation_text


def test_tiny_missing_sentinel_fragment_is_still_generating_not_finalized(tmp_path: Path) -> None:
    sentinel = "<<<WEBGPT_DONE:slow-generation-fragment>>>"
    request = tmp_path / "request.md"
    output = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    host_log = tmp_path / "host.log"
    calls = tmp_path / "calls.log"
    fake_run = tmp_path / "run.sh"
    request.write_text("produce a slow long JSON answer\n", encoding="utf-8")
    host_log.write_text(f"Prompt accepted: sentinel={sentinel}\n", encoding="utf-8")
    fake_run.write_text(
        f'''#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> {str(calls)!r}
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tSlow Test\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  js)
    printf 'cdp-ok\\n'
    ;;
  chatgpt)
    printf 'Position\\n\\n[\\n{{\\n'
    printf 'Tab ID: 837352334\\nResponseSource: assistant-dom\\n' >&2
    exit 0
    ;;
  chatgpt.extract)
    printf 'Position\\n\\n[\\n{{\\n'
    ;;
  *)
    printf 'unexpected command: %s\\n' "$*" >&2
    exit 99
    ;;
esac
''',
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "SURF_RUN_SH": str(fake_run),
        "SURF_WEBGPT_EXTRACT_FALLBACK_BUDGET": "2",
        "SURF_WEBGPT_EXTRACT_FALLBACK_INTERVAL": "0",
        "SURF_WEBGPT_EXTRACT_FALLBACK_TIMEOUT": "1",
        "SURF_WEBGPT_MIN_FINAL_RAW_CHARS": "32",
        "SURF_WEBGPT_HOST_LOG": str(host_log),
    })

    proc = subprocess.run(
        [
            "bash", str(SUBMIT), "--input", str(request), "--output", str(output),
            "--meta-output", str(meta), "--sentinel", sentinel, "--tab-id", "837352334",
            "--expect-url", "https://chatgpt.com/c/example", "--no-activate", "--timeout", "5",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert proc.returncode == 4
    assert output.read_text(encoding="utf-8") == ""
    payload = __import__("json").loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failure"] == "partial_response_still_generating"
    assert payload["blocker"] == "BLOCKED_WEBGPT_PARTIAL_RESPONSE_STILL_GENERATING"
    assert payload["partial_response_still_generating"] is True
    assert payload["raw_chars"] < payload["min_final_raw_chars"]
    assert payload["proof_status"] == "submitted_response_still_generating"
    assert payload["raw_response_advisory"] is True


def test_missing_sentinel_submit_uses_extract_fallback_before_final_failure(tmp_path: Path) -> None:
    sentinel = "<<<WEBGPT_DONE:missing-sentinel-recovery>>>"
    request = tmp_path / "request.md"
    output = tmp_path / "response.md"
    meta = tmp_path / "response.meta.json"
    calls = tmp_path / "calls.log"
    fake_run = tmp_path / "run.sh"
    request.write_text("recover completed same-tab response\n", encoding="utf-8")
    fake_run.write_text(
        f'''#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> {str(calls)!r}
case "${{1:-}}" in
  tab.list)
    printf '837352334\\tRecovery Test\\thttps://chatgpt.com/c/example\\n'
    ;;
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  js)
    printf 'cdp-ok\\n'
    ;;
  tab.activate)
    exit 0
    ;;
  chatgpt)
    printf 'Position\\n\\n[\\n'
    printf 'Tab ID: 837352334\\nResponseSource: assistant-dom\\n' >&2
    exit 0
    ;;
  chatgpt.extract)
    printf 'recovered completed response\\n{sentinel}\\n'
    ;;
  *)
    printf 'unexpected command: %s\\n' "$*" >&2
    exit 99
    ;;
esac
''',
        encoding="utf-8",
    )
    fake_run.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "SURF_RUN_SH": str(fake_run),
        "SURF_WEBGPT_EXTRACT_FALLBACK_BUDGET": "5",
    })

    proc = subprocess.run(
        [
            "bash", str(SUBMIT), "--input", str(request), "--output", str(output),
            "--meta-output", str(meta), "--sentinel", sentinel, "--tab-id", "837352334",
            "--expect-url", "https://chatgpt.com/c/example", "--no-activate", "--timeout", "5",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert output.read_text(encoding="utf-8") == "recovered completed response\n"
    payload = __import__("json").loads(meta.read_text(encoding="utf-8"))
    assert payload["status"] in {"completed", "recovered_focus_changed"}
    assert payload["response_proof_status"] == "response_proven"
    assert payload["extract_fallback_used"] is True
    assert payload["extract_fallback_reason"] == "missing_sentinel"
    assert payload["raw_contains_sentinel"] is True
    assert payload["clean_contains_sentinel"] is False
    invocation_text = calls.read_text(encoding="utf-8")
    assert "chatgpt.extract" in invocation_text
    assert "tab.new" not in invocation_text
    assert "key Enter" not in invocation_text
