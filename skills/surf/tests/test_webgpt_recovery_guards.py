from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EXTRACT = REPO_ROOT / "skills/surf/scripts/webgpt-extract.sh"
RECOVER = REPO_ROOT / "skills/surf/scripts/webgpt-recover.sh"
SUBMIT = REPO_ROOT / "skills/surf/scripts/webgpt-submit.sh"
CLI = REPO_ROOT / "skills/surf/vendor/surf-cli/native/cli.cjs"
HOST = REPO_ROOT / "skills/surf/vendor/surf-cli/native/host.cjs"
CHATGPT_CLIENT = REPO_ROOT / "skills/surf/vendor/surf-cli/native/chatgpt-client.cjs"
KIMI_CLIENT = REPO_ROOT / "skills/surf/vendor/surf-cli/native/kimi-tab-client.cjs"
SERVICE_WORKER = REPO_ROOT / "skills/surf/vendor/surf-cli/src/service-worker/index.ts"


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


def test_chatgpt_reasoning_selector_unavailable_is_warning_not_abort() -> None:
    source = CHATGPT_CLIENT.read_text(encoding="utf-8")
    helper = source.split("async function attemptOptionalSelection", 1)[1].split(
        "async function typePrompt", 1
    )[0]

    assert "continuing with current setting" in helper
    assert 'status: "unavailable_using_current"' in helper
    assert "throw new Error" not in helper
    assert "reasoningSelectionStatus" in source
    assert "reasoningSelectionError" in source


def test_kimi_provider_capacity_busy_fails_fast() -> None:
    source = KIMI_CLIENT.read_text(encoding="utf-8")

    assert "providerBusy" in source
    assert "system is currently busy" in source
    assert "capacity is busy" in source
    assert "Kimi provider capacity busy" in source
    assert "promptNeedle" in source
    assert "providerBusyAfterPrompt" in source
    assert "busyMarkerIndex > promptSentinelIndex" in source
    assert "Kimi attachment upload failed: preview entered error state" in source
    assert "Kimi attachment upload did not become ready within 20s" in source
    assert "Kimi prompt submission was not accepted: composer still contains draft" in source
    assert "waitForSubmissionAcceptance" in source
    assert 'type: "keyDown"' in source
    assert 'key: "Enter"' in source


def test_kimi_formatter_emits_controlled_tab_metadata() -> None:
    source = CLI.read_text(encoding="utf-8")
    formatter = source.split('tool === "kimi_tab"', 1)[1].split('tool === "aistudio"', 1)[0]

    assert "Tab ID:" in formatter
    assert "controlledTabId" in formatter
    assert "Activated:" in formatter
    assert "TabWasCreated:" in formatter

def test_kimi_uses_dedicated_service_worker_cdp_messages() -> None:
    host_source = HOST.read_text(encoding="utf-8")
    worker_source = SERVICE_WORKER.read_text(encoding="utf-8")

    assert '"KIMI_EVALUATE"' in host_source
    assert '"KIMI_CDP_COMMAND"' in host_source
    assert 'case "KIMI_EVALUATE"' in worker_source
    assert 'case "KIMI_CDP_COMMAND"' in worker_source
    assert '"KIMI_EVALUATE", "KIMI_CDP_COMMAND"' in worker_source


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


def test_recover_finalize_does_not_overwrite_existing_raw_on_extract_timeout(tmp_path: Path) -> None:
    sentinel = "<<<WEBGPT_DONE:recover-timeout>>>"
    artifact_dir = tmp_path / "round"
    artifact_dir.mkdir()
    output = artifact_dir / "response.md"
    raw = artifact_dir / "response.raw.md"
    meta = artifact_dir / "response.meta.json"
    receipt = artifact_dir / "response.md.receipt.json"
    inflight = artifact_dir / "webgpt_inflight.json"
    calls = tmp_path / "calls.log"
    fake_run = tmp_path / "run.sh"
    output.write_text("previous clean response\n", encoding="utf-8")
    raw.write_text("previous raw response without current sentinel\n", encoding="utf-8")
    meta.write_text(
        json.dumps(
            {
                "status": "missing_sentinel",
                "failure": "missing_sentinel",
                "output": str(output),
                "raw_output": str(raw),
                "meta_output": str(meta),
                "sentinel": sentinel,
                "requested_tab_id": "837363742",
                "controlled_tab_id": "837363742",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    receipt.write_text(
        json.dumps(
            {
                "status": "submitted_to_chatgpt",
                "submitted_to_chatgpt": True,
                "requested_tab_id": "837363742",
                "sentinel": sentinel,
                "output": str(output),
                "raw_output": str(raw),
                "meta_output": str(meta),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    inflight.write_text(
        json.dumps(
            {
                "status": "submitted_to_chatgpt",
                "submitted_to_chatgpt": True,
                "requested_tab_id": "837363742",
                "sentinel": sentinel,
                "output": str(output),
                "raw_output": str(raw),
                "meta_output": str(meta),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fake_run.write_text(
        f'''#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> {str(calls)!r}
case "${{1:-}}" in
  chatgpt.extract)
    printf 'Response timeout while waiting for sentinel\\n' >&2
    exit 124
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
    env["SURF_RUN_SH"] = str(fake_run)

    proc = subprocess.run(
        ["bash", str(RECOVER), "--artifact-dir", str(artifact_dir), "--finalize", "--timeout", "1"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert proc.returncode == 124
    payload = json.loads(proc.stdout)
    assert payload["finalize_attempted"] is True
    assert payload["finalize_exit_code"] == 124
    assert payload["finalize_preserved_existing_outputs"] is True
    assert raw.read_text(encoding="utf-8") == "previous raw response without current sentinel\n"
    assert meta.read_text(encoding="utf-8").startswith('{"status": "missing_sentinel"')
    attempt = payload["finalize_attempt_artifacts"]
    assert Path(attempt["raw_output"]).exists()
    assert Path(attempt["meta_output"]).exists()
    assert "Response timeout" in Path(attempt["stderr_log"]).read_text(encoding="utf-8")
    invocation_text = calls.read_text(encoding="utf-8")
    assert "chatgpt.extract" in invocation_text
    assert "webgpt.submit" not in invocation_text
