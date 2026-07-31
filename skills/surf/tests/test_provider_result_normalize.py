from __future__ import annotations

import json
import subprocess
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
NORMALIZE = SKILL_DIR / "scripts" / "surf_meta_normalize.py"
RUN_SH = SKILL_DIR / "run.sh"


def write_success_fixture(tmp_path: Path) -> Path:
    input_path = tmp_path / "request.md"
    submitted_path = tmp_path / "submitted.md"
    output_path = tmp_path / "response.md"
    raw_path = tmp_path / "response.raw.md"
    stderr_path = tmp_path / "stderr.log"
    input_path.write_text("Please answer with the sentinel.\n")
    submitted_path.write_text("Please answer with the sentinel.\nSENTINEL: surf-test-123\n")
    output_path.write_text("Answer body.\n")
    raw_path.write_text("Answer body.\nSENTINEL: surf-test-123\n")
    stderr_path.write_text("")
    meta = {
        "status": "completed",
        "proof_status": "response_proven",
        "submitted_to_chatgpt": True,
        "requested_tab_id": 837360001,
        "controlled_tab_id": 837360001,
        "requested_url": "https://chatgpt.com/c/example",
        "actual_url": "https://chatgpt.com/c/example",
        "model": "gpt-5.5",
        "reasoning": "high",
        "sentinel": "surf-test-123",
        "raw_contains_sentinel": True,
        "input": str(input_path),
        "submitted_output": str(submitted_path),
        "output": str(output_path),
        "raw_output": str(raw_path),
        "stderr_log": str(stderr_path),
    }
    meta_path = tmp_path / "response.meta.json"
    meta_path.write_text(json.dumps(meta))
    return meta_path


def test_normalize_webgpt_success_strict_snapshot(tmp_path: Path) -> None:
    meta_path = write_success_fixture(tmp_path)
    proc = subprocess.run(
        ["python3", str(NORMALIZE), "--meta", str(meta_path), "--json", "--strict"],
        cwd=SKILL_DIR,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "surf.provider_result.v1"
    assert payload["provider"] == "webgpt"
    assert payload["proof_status"] == "response_proven"
    assert payload["success"] is True
    assert payload["target"]["requested_tab_id"] == 837360001
    assert payload["target"]["controlled_tab_id"] == 837360001
    assert payload["delivery"]["delivery_proven"] is True
    assert payload["immutable_request_snapshot"]["present"] is True
    assert payload["immutable_request_snapshot"]["input_sha256"]
    assert payload["immutable_request_snapshot"]["submitted_sha256"]
    assert payload["retryability"] == {"retryable": False, "reason": "successful_result"}
    assert payload["strict_ok"] is True
    assert payload["strict_errors"] == []


def test_run_sh_routes_meta_normalize(tmp_path: Path) -> None:
    meta_path = write_success_fixture(tmp_path)
    proc = subprocess.run(
        [str(RUN_SH), "meta.normalize", "--meta", str(meta_path), "--json", "--strict"],
        cwd=SKILL_DIR,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["schema"] == "surf.provider_result.v1"


def test_strict_mode_fails_when_immutable_snapshot_missing(tmp_path: Path) -> None:
    raw_path = tmp_path / "response.raw.md"
    raw_path.write_text("provider capacity reached\n")
    meta_path = tmp_path / "kimi.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "status": "failed",
                "submitted_to_kimi": False,
                "proof_status": "provider_capacity",
                "failure": "provider_capacity",
                "controlled_tab_id": 837360002,
                "raw_output": str(raw_path),
            }
        )
    )

    proc = subprocess.run(
        ["python3", str(NORMALIZE), "--meta", str(meta_path), "--json", "--strict"],
        cwd=SKILL_DIR,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["provider"] == "kimi"
    assert payload["retryability"] == {"retryable": True, "reason": "retryable_failure_class"}
    assert payload["strict_ok"] is False
    assert "missing_immutable_request_snapshot" in payload["strict_errors"]


def test_killed_running_kimi_meta_normalizes_to_terminal_provider_result(tmp_path: Path) -> None:
    input_path = tmp_path / "request.md"
    submitted_path = tmp_path / "submitted.md"
    stderr_path = tmp_path / "submit.stderr.txt"
    attachment = tmp_path / "bundle.md"
    input_path.write_text("Use ATTACHMENT_1 and answer with the sentinel.\n")
    submitted_path.write_text("Use ATTACHMENT_1.\n<<<KIMI_DONE:test>>>\n")
    stderr_path.write_text("[tau-worker] command timed out after 300s; killed process group rooted at pid 123\n")
    attachment.write_text("# Evidence\n")
    meta_path = tmp_path / "kimi.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "status": "running",
                "proof_status": "pending",
                "submitted_to_kimi": False,
                "requested_tab_id": "837364343",
                "controlled_tab_id": None,
                "input": str(input_path),
                "submitted_output": str(submitted_path),
                "output": str(tmp_path / "response.md"),
                "raw_output": str(tmp_path / "response.raw.md"),
                "stderr_log": str(stderr_path),
                "sentinel": "<<<KIMI_DONE:test>>>",
                "raw_contains_sentinel": None,
                "attach_file": str(attachment),
                "attachment_delivery_proven": False,
            }
        )
    )

    proc = subprocess.run(
        [
            "python3",
            str(NORMALIZE),
            "--meta",
            str(meta_path),
            "--provider",
            "kimi",
            "--json",
            "--return-code",
            "-9",
            "--duration-seconds",
            "387.53",
            "--command-stderr-file",
            str(stderr_path),
        ],
        cwd=SKILL_DIR,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "surf.provider_result.v1"
    assert payload["provider"] == "kimi"
    assert payload["status"] == "timeout"
    assert payload["proof_status"] == "delivery_not_proven"
    assert payload["success"] is False
    assert payload["target"]["requested_tab_id"] == "837364343"
    assert payload["target"]["controlled_tab_id"] is None
    assert payload["delivery"]["submitted"] is False
    assert payload["attachments"]["requested"] is True
    assert payload["attachments"]["delivery_proven"] is False
    assert payload["bounded_error"]["code"] == "browser_handler_timeout"
    assert payload["bounded_error"]["exit_code"] == -9


def test_webgpt_prepared_prompt_is_not_submitted_when_killed(tmp_path: Path) -> None:
    input_path = tmp_path / "request.md"
    submitted_path = tmp_path / "submitted.md"
    input_path.write_text("Answer with sentinel.\n")
    submitted_path.write_text("Answer with sentinel.\n<<<WEBGPT_DONE:test>>>\n")
    meta_path = tmp_path / "webgpt.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "status": "prepared_prompt",
                "proof_status": "delivery_pending",
                "submitted_to_chatgpt": False,
                "requested_tab_id": "837364340",
                "input": str(input_path),
                "submitted_output": str(submitted_path),
                "output": str(tmp_path / "response.md"),
                "raw_output": str(tmp_path / "response.raw.md"),
                "sentinel": "<<<WEBGPT_DONE:test>>>",
                "raw_contains_sentinel": False,
            }
        )
    )

    proc = subprocess.run(
        [
            "python3",
            str(NORMALIZE),
            "--meta",
            str(meta_path),
            "--provider",
            "webgpt",
            "--json",
            "--return-code",
            "-9",
            "--command-stderr",
            "process killed before ChatGPT accepted the prompt",
        ],
        cwd=SKILL_DIR,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "failed"
    assert payload["proof_status"] == "not_submitted"
    assert payload["delivery"]["submitted"] is False
    assert payload["bounded_error"]["code"] == "not_submitted"
    assert payload["success"] is False


def test_gemini_attachment_missing_metadata_stays_terminal(tmp_path: Path) -> None:
    attachment = tmp_path / "review-bundle.md"
    attachment.write_text("# Bundle\n")
    meta_path = tmp_path / "gemini.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "status": "failed",
                "failure": "attachment_metadata_missing",
                "proof_status": "file_upload_unavailable",
                "submitted_to_gemini": False,
                "requested_tab_id": "837364346",
                "controlled_tab_id": "837364346",
                "attach_file": str(attachment),
                "attachment": {"missing_native_metadata": True, "attached": False},
                "attachment_missing": True,
                "attachment_delivery_proven": False,
            }
        )
    )

    proc = subprocess.run(
        ["python3", str(NORMALIZE), "--meta", str(meta_path), "--provider", "gemini", "--json"],
        cwd=SKILL_DIR,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "failed"
    assert payload["proof_status"] == "file_upload_unavailable"
    assert payload["attachments"]["requested"] is True
    assert payload["attachments"]["missing"] is True
    assert payload["attachments"]["delivery_proven"] is False
    assert payload["bounded_error"]["code"] == "attachment_metadata_missing"
