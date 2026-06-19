from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
E2E_SANITY = REPO_ROOT / "skills/surf/scripts/webgpt-e2e-sanity.sh"


def run_sanity(tmp_path: Path, fake_run_body: str) -> subprocess.CompletedProcess[str]:
    fake_run = tmp_path / "surf-run.sh"
    fake_run.write_text(fake_run_body, encoding="utf-8")
    fake_run.chmod(0o755)
    out_dir = tmp_path / "sanity"
    env = os.environ.copy()
    env["SURF_DISPATCH_SH"] = str(fake_run)
    return subprocess.run(
        [
            "bash",
            str(E2E_SANITY),
            "--output-dir",
            str(out_dir),
            "--timeout",
            "10",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )


def fake_dispatch(roundtrip_payload: dict, fresh_status: str = "fresh") -> str:
    payload = json.dumps(roundtrip_payload)
    return f"""#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  extension.fresh)
    printf '{{"status":"{fresh_status}","extension_dist_fresh":true,"native_host_fresh":true}}\\n'
    ;;
  tab.list)
    printf '[{{"id":837352334,"title":"ChatGPT","url":"https://chatgpt.com/"}}]\\n'
    ;;
  focus.state)
    printf '{{"activeTabId":837352000,"activeTabUrl":"https://example.test/"}}\\n'
    ;;
  webgpt.roundtrip-preflight)
    out_dir=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --output-dir) out_dir="${{2:-}}"; shift 2 ;;
        *) shift ;;
      esac
    done
    mkdir -p "$out_dir"
    printf '%s\\n' {json.dumps(payload)}
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""


def fake_dispatch_stale_fails_if_roundtrip_called() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  extension.fresh)
    printf '{"status":"stale","extension_dist_fresh":true,"native_host_fresh":false}\\n'
    exit 1
    ;;
  tab.list)
    printf '[{"id":837352334,"title":"ChatGPT","url":"https://chatgpt.com/"}]\\n'
    ;;
  focus.state)
    printf '{"activeTabId":837352000,"activeTabUrl":"https://example.test/"}\\n'
    ;;
  webgpt.roundtrip-preflight)
    echo "roundtrip should not run after stale freshness" >&2
    exit 98
    ;;
  *)
    echo "unexpected command: $*" >&2
    exit 99
    ;;
esac
"""


def pass_payload() -> dict:
    return {
        "status": "pass",
        "failures": [],
        "meta": {
            "status": "completed",
            "proof_status": "response_proven",
            "submitted_to_chatgpt": True,
            "raw_contains_sentinel": True,
            "clean_contains_sentinel": False,
            "controlled_tab_id": "837352334",
            "controlled_tab_id_mismatch": False,
            "no_activate": True,
            "focus_invariant_ok": True,
            "conversation_url": "https://chatgpt.com/c/example",
            "requested_reasoning": "Pro",
            "observed_requested_reasoning": "Pro",
            "reasoning_selection_status": "selector_unavailable",
        },
        "diagnosis": {"raw_contains_sentinel": True},
    }


def test_webgpt_e2e_sanity_passes_with_sentinel_proof(tmp_path: Path) -> None:
    proc = run_sanity(tmp_path, fake_dispatch(pass_payload()))

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "pass"
    assert result["scenarios"][0]["warnings"] == ["warning_reasoning_selector_unavailable"]
    assert result["checks"][0]["name"] == "extension_native_fresh"


def test_webgpt_e2e_sanity_fails_stale_native_host(tmp_path: Path) -> None:
    proc = run_sanity(tmp_path, fake_dispatch(pass_payload(), fresh_status="stale"))

    assert proc.returncode == 7
    result = json.loads(proc.stdout)
    assert result["status"] == "fail"
    assert result["failure_code"] == "extension_native_fresh"
    assert "extension_native_fresh" in [check["name"] for check in result["checks"] if not check["ok"]]
    assert result["scenarios"] == []


def test_webgpt_e2e_sanity_does_not_submit_when_freshness_fails(tmp_path: Path) -> None:
    proc = run_sanity(tmp_path, fake_dispatch_stale_fails_if_roundtrip_called())

    assert proc.returncode == 7
    result = json.loads(proc.stdout)
    assert result["failure_code"] == "extension_native_fresh"
    assert result["scenarios"] == []
    assert "roundtrip should not run" not in proc.stderr


def test_webgpt_e2e_sanity_fails_missing_sentinel(tmp_path: Path) -> None:
    payload = pass_payload()
    payload["status"] = "fail"
    payload["failures"] = ["missing_sentinel"]
    payload["meta"]["proof_status"] = "submitted_no_response_proof"
    payload["meta"]["raw_contains_sentinel"] = False
    proc = run_sanity(tmp_path, fake_dispatch(payload))

    assert proc.returncode == 7
    result = json.loads(proc.stdout)
    scenario = result["scenarios"][0]
    assert result["status"] == "fail"
    assert scenario["failures"] == ["roundtrip_failed", "response_not_proven", "missing_sentinel"]


def test_webgpt_e2e_sanity_fails_focus_drift(tmp_path: Path) -> None:
    payload = pass_payload()
    payload["meta"]["focus_invariant_ok"] = False
    proc = run_sanity(tmp_path, fake_dispatch(payload))

    assert proc.returncode == 7
    scenario = json.loads(proc.stdout)["scenarios"][0]
    assert "focus_changed_despite_no_activate" in scenario["failures"]


def test_webgpt_e2e_sanity_fails_missing_controlled_tab_id(tmp_path: Path) -> None:
    payload = pass_payload()
    payload["meta"]["controlled_tab_id"] = None
    proc = run_sanity(tmp_path, fake_dispatch(payload))

    assert proc.returncode == 7
    scenario = json.loads(proc.stdout)["scenarios"][0]
    assert "missing_controlled_tab_id" in scenario["failures"]


def test_webgpt_e2e_sanity_fails_project_shell_without_conversation(tmp_path: Path) -> None:
    payload = pass_payload()
    payload["meta"]["conversation_url"] = "https://chatgpt.com/g/g-p-example/project"
    payload["meta"]["tab_identity_preflight"] = {
        "expected_url": "https://chatgpt.com/g/g-p-example/project",
        "tab": {"url": "https://chatgpt.com/g/g-p-example/project"},
    }
    proc = run_sanity(tmp_path, fake_dispatch(payload))

    assert proc.returncode == 7
    scenario = json.loads(proc.stdout)["scenarios"][0]
    assert "project_session_unproven" in scenario["failures"]


def test_webgpt_e2e_sanity_fails_missing_reasoning_status(tmp_path: Path) -> None:
    payload = pass_payload()
    payload["meta"]["reasoning_selection_status"] = None
    payload["meta"]["selected_reasoning"] = None
    proc = run_sanity(tmp_path, fake_dispatch(payload))

    assert proc.returncode == 7
    scenario = json.loads(proc.stdout)["scenarios"][0]
    assert "reasoning_status_missing" in scenario["failures"]
