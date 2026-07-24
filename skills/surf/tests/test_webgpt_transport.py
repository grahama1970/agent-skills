from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TRANSPORT = REPO_ROOT / "skills/surf/scripts/lib/webgpt_transport.py"
WEBGPT_SUBMIT = REPO_ROOT / "skills/surf/scripts/webgpt-submit.sh"
WEBGPT_RECOVER = REPO_ROOT / "skills/surf/scripts/webgpt-recover.sh"
WEBGPT_ROUNDTRIP_PREFLIGHT = REPO_ROOT / "skills/surf/scripts/webgpt-roundtrip-preflight.sh"
TRANSPORT_FIXTURES = REPO_ROOT / "skills/surf/tests/fixtures/webgpt-transport"


def write_round(
    tmp_path: Path,
    *,
    meta: dict,
    receipt: dict | None = None,
    raw_text: str | None = None,
) -> Path:
    round_dir = tmp_path / "round-1"
    round_dir.mkdir(parents=True, exist_ok=True)
    meta_path = round_dir / "02_response.meta.json"
    raw_path = round_dir / "02_response.raw.md"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    if raw_text is not None:
        raw_path.write_text(raw_text, encoding="utf-8")
    if receipt is not None:
        (round_dir / "02_response.receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n",
            encoding="utf-8",
        )
    return round_dir


def run_recover(round_dir: Path) -> dict:
    proc = subprocess.run(
        ["bash", str(WEBGPT_RECOVER), "--artifact-dir", str(round_dir)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def write_summary(round_dir: Path) -> dict:
    proc = subprocess.run(
        [
            "python3",
            str(TRANSPORT),
            "write-summary",
            "--artifact-dir",
            str(round_dir),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    summary_path = round_dir / "webgpt_transport_summary.json"
    assert summary_path.exists()
    return json.loads(summary_path.read_text(encoding="utf-8"))


def test_transport_summary_submitted_only() -> None:
    tmp = Path("/tmp/surf-transport-test-submitted-only")
    tmp.mkdir(parents=True, exist_ok=True)
    round_dir = write_round(
        tmp,
        meta={
            "status": "failed",
            "failure": "submit_failed",
            "sentinel": "<<<WEBGPT_DONE:test>>>",
            "requested_tab_id": "837354098",
            "raw_contains_sentinel": False,
        },
        receipt={
            "status": "submitted_to_chatgpt",
            "submitted_to_chatgpt": True,
            "sentinel": "<<<WEBGPT_DONE:test>>>",
            "requested_tab_id": "837354098",
        },
    )
    summary = write_summary(round_dir)
    assert summary["final_transport_state"] == "submitted_only"
    assert summary["submitted_to_chatgpt"] is True
    assert summary["prepared_prompt_is_transport_proof"] is False
    assert "webgpt.extract" in summary["next_command"]
    recover = run_recover(round_dir)
    assert recover["state"] == "submitted_only"
    assert recover["next_command"] == summary["next_command"]


def test_transport_summary_completed_with_focus_drift() -> None:
    tmp = Path("/tmp/surf-transport-test-focus-drift")
    tmp.mkdir(parents=True, exist_ok=True)
    sentinel = "<<<WEBGPT_DONE:20260620T0523Z:abc>>>"
    round_dir = write_round(
        tmp,
        meta={
            "status": "recovered_focus_changed",
            "failure": "focus_stolen_despite_no_activate",
            "sentinel": sentinel,
            "requested_tab_id": "837354098",
            "controlled_tab_id": "837354098",
            "raw_contains_sentinel": True,
            "focus_changed": True,
            "transport_degraded": True,
            "agent_diagnosis": "Focus drift after completion.",
        },
        receipt={"status": "submitted_to_chatgpt", "submitted_to_chatgpt": True},
        raw_text=f"review verdict\n{sentinel}\n",
    )
    summary = write_summary(round_dir)
    assert summary["final_transport_state"] == "completed_with_focus_drift"
    assert summary["raw_sentinel_present"] is True
    assert summary["focus_changed"] is True
    assert "audit" in summary["next_command"]


def test_transport_summary_missing_sentinel() -> None:
    tmp = Path("/tmp/surf-transport-test-missing-sentinel")
    tmp.mkdir(parents=True, exist_ok=True)
    round_dir = write_round(
        tmp,
        meta={
            "status": "missing_sentinel",
            "failure": "missing_sentinel",
            "sentinel": "<<<WEBGPT_DONE:current>>>",
            "requested_tab_id": "837352352",
            "controlled_tab_id": "837352352",
            "raw_contains_sentinel": False,
            "raw_response_advisory": True,
            "agent_diagnosis": "Surf captured response text, but it did not contain the current completion sentinel in assistant output.",
        },
        receipt={"status": "submitted_to_chatgpt", "submitted_to_chatgpt": True},
        raw_text='{"verdict":"PASS"}\n<<<WEBGPT_DONE:old>>>\n',
    )
    summary = write_summary(round_dir)
    assert summary["final_transport_state"] == "missing_sentinel"
    assert summary["raw_response_advisory"] is True
    assert "webgpt.extract" in summary["next_command"]
    assert "do_not_accept_stale_sentinel_as_current_turn_proof" in summary["do_not_do"]


def test_transport_summary_missing_response_artifacts() -> None:
    tmp = Path("/tmp/surf-transport-test-missing-artifacts")
    tmp.mkdir(parents=True, exist_ok=True)
    round_dir = tmp / "round-empty"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "02_response.receipt.json").write_text(
        json.dumps(
            {
                "status": "submitted_to_chatgpt",
                "submitted_to_chatgpt": True,
                "sentinel": "<<<WEBGPT_DONE:test>>>",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    summary = write_summary(round_dir)
    assert summary["final_transport_state"] == "missing_response_artifacts"
    assert summary["needs_attention"] == "NEEDS_ATTENTION: missing_webgpt_transport_artifacts"
    assert summary["next_command"].startswith("NEEDS_ATTENTION:")


def test_recover_claims_ask_tau_submitted_no_raw_meta_fixture(tmp_path: Path) -> None:
    round_dir = tmp_path / "submitted_no_raw_meta"
    shutil.copytree(TRANSPORT_FIXTURES / "submitted_no_raw_meta", round_dir)

    summary = write_summary(round_dir)

    assert summary["final_transport_state"] == "missing_response_artifacts"
    assert summary["submitted_to_chatgpt"] is True
    assert summary["requested_tab_id"] == "837360896"
    assert summary["sentinel"] == "<<<WEBGPT_DONE:20260724T020405Z:e516d90f>>>"
    assert summary["needs_attention"] is None
    assert summary["claim"]["available"] is True
    assert summary["claim"]["output"] == str(round_dir / "response.md")
    assert summary["claim"]["raw_output"] == str(round_dir / "response.raw.md")
    assert summary["claim"]["meta_output"] == str(round_dir / "response.meta.json")
    assert "webgpt.extract --tab-id 837360896" in summary["next_command"]
    assert "--sentinel '<<<WEBGPT_DONE:20260724T020405Z:e516d90f>>>'" in summary["next_command"]
    assert summary["response_receipt_path"] == str(round_dir / "response.md.receipt.json")
    assert summary["submitted_path"] == str(round_dir / "response.md.submitted.md")

    recover = run_recover(round_dir)

    assert recover["state"] == "missing_response_artifacts"
    assert recover["needs_attention"] is None
    assert recover["claim"]["available"] is True
    assert recover["next_command"] == summary["next_command"]

    captured_before = json.loads(
        (TRANSPORT_FIXTURES / "submitted_no_raw_meta" / "captured-recover-before-fix.json").read_text(
            encoding="utf-8"
        )
    )
    assert captured_before["state"] == "unknown"
    assert captured_before["next_command"] == "NEEDS_ATTENTION: missing_webgpt_transport_artifacts"

    captured_extract = json.loads(
        (TRANSPORT_FIXTURES / "submitted_no_raw_meta" / "captured-extract-meta.json").read_text(
            encoding="utf-8"
        )
    )
    assert captured_extract["controlled_tab_id"] == "837360896"
    assert captured_extract["status"] == "completed"


def test_transport_summary_recognizes_ask_tau_manual_extract_paths(tmp_path: Path) -> None:
    round_dir = tmp_path / "round-manual-extract"
    round_dir.mkdir(parents=True)
    sentinel = "<<<WEBGPT_DONE:20260724T020405Z:e516d90f>>>"
    (round_dir / "response.md.receipt.json").write_text(
        json.dumps(
            {
                "schema": "surf.webgpt_submit_receipt.v1",
                "status": "submitted_to_chatgpt",
                "submitted_to_chatgpt": True,
                "sentinel": sentinel,
                "requested_tab_id": "837360896",
                "output": "response.md",
                "raw_output": "response.raw.md",
                "meta_output": "response.meta.json",
                "submitted_output": "response.md.submitted.md",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (round_dir / "response.md.raw.md").write_text(f"Recovered answer\n{sentinel}\n", encoding="utf-8")
    (round_dir / "response.md.meta.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "sentinel": None,
                "requested_tab_id": "837360896",
                "controlled_tab_id": "837360896",
                "raw_output": "response.md.raw.md",
                "raw_contains_sentinel": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = write_summary(round_dir)

    assert summary["final_transport_state"] == "completed"
    assert summary["raw_sentinel_present"] is True
    assert summary["sentinel"] == sentinel
    assert summary["response_raw_path"] == str(round_dir / "response.md.raw.md")
    assert summary["response_meta_path"] == str(round_dir / "response.md.meta.json")


def test_transport_summary_inflight_orphan_is_claimable(tmp_path: Path) -> None:
    round_dir = tmp_path / "round-inflight"
    round_dir.mkdir(parents=True)
    sentinel = "<<<WEBGPT_DONE:orphan>>>"
    (round_dir / "webgpt_inflight.json").write_text(
        json.dumps(
            {
                "schema": "surf.webgpt_inflight.v1",
                "status": "submitted_to_chatgpt",
                "submitted_to_chatgpt": True,
                "sentinel": sentinel,
                "requested_tab_id": "837360481",
                "output": str(round_dir / "02_response.md"),
                "raw_output": str(round_dir / "02_response.raw.md"),
                "meta_output": str(round_dir / "02_response.meta.json"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = write_summary(round_dir)

    assert summary["final_transport_state"] == "missing_response_artifacts"
    assert summary["needs_attention"] is None
    assert summary["claim"]["available"] is True
    assert summary["claim"]["tab_id"] == "837360481"
    assert "webgpt.extract --tab-id 837360481" in summary["next_command"]


def test_transport_summary_completed() -> None:
    tmp = Path("/tmp/surf-transport-test-completed")
    tmp.mkdir(parents=True, exist_ok=True)
    sentinel = "<<<WEBGPT_DONE:done>>>"
    round_dir = write_round(
        tmp,
        meta={
            "status": "completed",
            "sentinel": sentinel,
            "requested_tab_id": "123",
            "controlled_tab_id": "123",
            "raw_contains_sentinel": True,
            "focus_changed": False,
        },
        receipt={"status": "submitted_to_chatgpt", "submitted_to_chatgpt": True},
        raw_text=f"answer\n{sentinel}\n",
    )
    summary = write_summary(round_dir)
    assert summary["final_transport_state"] == "completed"
    assert summary["raw_sentinel_present"] is True


def test_roundtrip_preflight_bounds_rate_limit_wait_for_child_submit(tmp_path: Path) -> None:
    calls = tmp_path / "calls.log"
    env_log = tmp_path / "env.log"
    fake_run = tmp_path / "run.sh"
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(calls)!r}
case "${{1:-}}" in
  focus.state)
    printf '{{"active_tab_id":"123","active_window_id":"456"}}\\n'
    ;;
  tab.list)
    if printf '%s\\n' "$@" | grep -q -- '--json'; then
      printf '[{{"id":837352334,"title":"Reviewer","url":"https://chatgpt.com/c/example"}}]\\n'
    else
      printf '837352334\\tReviewer\\thttps://chatgpt.com/c/example\\n'
    fi
    ;;
  webgpt.preflight)
    printf '{{"status":"pass","tab_id":"837352334","url":"https://chatgpt.com/c/example"}}\\n'
    ;;
  js)
    if printf '%s\\n' "$*" | grep -q 'cdp-ok'; then
      printf 'cdp-ok\\n'
    else
      printf '"ok"\\n'
    fi
    ;;
  chatgpt)
    printf 'rate_wait=%s\\n' "${{SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS:-unset}}" >> {str(env_log)!r}
    sentinel=""
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--sentinel" ]]; then
        sentinel="${{2:-}}"
        break
      fi
      shift
    done
    printf 'pong %s\\n' "$sentinel"
    printf 'Tab ID: 837352334\\nActivated: false\\nTabWasCreated: false\\nResponseSource: assistant-dom\\n' >&2
    ;;
  *)
    printf 'unexpected command: %s\\n' "$*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)

    proc = subprocess.run(
        [
            "bash",
            str(WEBGPT_ROUNDTRIP_PREFLIGHT),
            "--tab-id",
            "837352334",
            "--expect-url",
            "https://chatgpt.com/c/example",
            "--no-activate",
            "--timeout",
            "5",
            "--output-dir",
            str(tmp_path / "roundtrip"),
            "--json",
        ],
        env={
            **__import__("os").environ,
            "SURF_RUN_SH": str(fake_run),
            "SURF_DISPATCH_SH": str(fake_run),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "pass"
    assert "rate_wait=5" in env_log.read_text(encoding="utf-8")

    env_log.write_text("", encoding="utf-8")
    proc_override = subprocess.run(
        [
            "bash",
            str(WEBGPT_ROUNDTRIP_PREFLIGHT),
            "--tab-id",
            "837352334",
            "--expect-url",
            "https://chatgpt.com/c/example",
            "--no-activate",
            "--timeout",
            "5",
            "--output-dir",
            str(tmp_path / "roundtrip-override"),
            "--json",
        ],
        env={
            **__import__("os").environ,
            "SURF_RUN_SH": str(fake_run),
            "SURF_DISPATCH_SH": str(fake_run),
            "SURF_WEBGPT_ROUNDTRIP_RATE_LIMIT_WAIT_SECONDS": "7",
            "SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS": "300",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc_override.returncode == 0, proc_override.stderr
    assert json.loads(proc_override.stdout)["status"] == "pass"
    assert "rate_wait=7" in env_log.read_text(encoding="utf-8")


def test_recover_finalize_claims_orphaned_submitted_receipt(tmp_path: Path) -> None:
    round_dir = tmp_path / "round-orphan"
    round_dir.mkdir(parents=True)
    sentinel = "<<<WEBGPT_DONE:finalize-orphan>>>"
    receipt = {
        "schema": "surf.webgpt_submit_receipt.v1",
        "status": "submitted_to_chatgpt",
        "submitted_to_chatgpt": True,
        "sentinel": sentinel,
        "requested_tab_id": "837360496",
        "output": str(round_dir / "02_response.md"),
        "raw_output": str(round_dir / "02_response.raw.md"),
        "meta_output": str(round_dir / "02_response.meta.json"),
    }
    (round_dir / "02_response.receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n",
        encoding="utf-8",
    )
    calls = tmp_path / "calls.log"
    fake_run = tmp_path / "run.sh"
    fake_run.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> {str(calls)!r}
case "${{1:-}}" in
  chatgpt.extract)
    printf 'recovered orphan answer\\n{sentinel}\\n'
    ;;
  *)
    printf 'unexpected command: %s\\n' "$*" >&2
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_run.chmod(0o755)

    proc = subprocess.run(
        [
            "bash",
            str(WEBGPT_RECOVER),
            "--artifact-dir",
            str(round_dir),
            "--finalize",
            "--timeout",
            "1",
        ],
        env={**__import__("os").environ, "SURF_RUN_SH": str(fake_run)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["finalize_attempted"] is True
    assert payload["finalize_exit_code"] == 0
    assert (round_dir / "02_response.md").read_text(encoding="utf-8") == "recovered orphan answer\n"
    assert sentinel in (round_dir / "02_response.raw.md").read_text(encoding="utf-8")
    assert "chatgpt.extract --tab-id 837360496" in calls.read_text(encoding="utf-8")
    summary = json.loads((round_dir / "webgpt_transport_summary.json").read_text(encoding="utf-8"))
    assert summary["final_transport_state"] == "completed"
