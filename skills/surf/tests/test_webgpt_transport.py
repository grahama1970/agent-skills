from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TRANSPORT = REPO_ROOT / "skills/surf/scripts/lib/webgpt_transport.py"
WEBGPT_SUBMIT = REPO_ROOT / "skills/surf/scripts/webgpt-submit.sh"
WEBGPT_RECOVER = REPO_ROOT / "skills/surf/scripts/webgpt-recover.sh"


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
