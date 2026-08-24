"""Tests for the Tau roundtable sanity eval runner."""

from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import subprocess
import sys
import time
from types import SimpleNamespace
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tau_roundtable_sanity_eval.py"
SPEC = importlib.util.spec_from_file_location("tau_roundtable_sanity_eval", SCRIPT_PATH)
assert SPEC and SPEC.loader
tau_roundtable_sanity_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tau_roundtable_sanity_eval
SPEC.loader.exec_module(tau_roundtable_sanity_eval)

WORKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tau_roundtable_worker.py"
WORKER_SPEC = importlib.util.spec_from_file_location("tau_roundtable_worker", WORKER_PATH)
assert WORKER_SPEC and WORKER_SPEC.loader
tau_roundtable_worker = importlib.util.module_from_spec(WORKER_SPEC)
sys.modules[WORKER_SPEC.name] = tau_roundtable_worker
WORKER_SPEC.loader.exec_module(tau_roundtable_worker)


def test_plan_lists_roundtable_eval_cases(tmp_path: Path) -> None:
    result = tau_roundtable_sanity_eval.build_plan(output_root=tmp_path, webgpt_project="tau")

    assert result["schema"] == "ask.tau_roundtable_sanity_eval.v1"
    assert result["status"] == "PLANNED"
    assert result["mocked"] is False
    assert result["live"] is False
    assert {case["id"] for case in result["cases"]} == {
        "browser_oracle_bindings",
        "compile_concurrent_all_handlers",
        "compile_compete_all_handlers",
        "live_four_handler_concurrent_roundtable",
        "live_four_handler_concurrent_compete",
    }
    assert result["min_active_handlers"] == 4
    assert result["browser_tab_lifecycle"] == "fresh-keep"
    assert "plan-only" in result["what_remains_unverified"][0]


def test_worker_declares_webgrok_browser_submit_transport() -> None:
    assert tau_roundtable_worker.HANDLER_BACKENDS["webgrok"] == "webgrok"
    assert tau_roundtable_worker.HANDLER_SUBMIT_COMMANDS["webgrok"] == "grok.submit"


def _browser_transport_lock_worker(
    command: list[str],
    cwd: str,
    lock_file: str,
    artifact_dir: str,
    result_path: str,
) -> None:
    os.environ["ASK_BROWSER_TRANSPORT_LOCK_FILE"] = lock_file
    # Serialization is opt-in since roundtable lanes went concurrent by default.
    os.environ["ASK_BROWSER_TRANSPORT_SERIAL"] = "1"
    result = tau_roundtable_worker._run_browser_transport_cmd(
        command,
        cwd=Path(cwd),
        timeout=10,
        handler="webgpt",
        artifact_dir=Path(artifact_dir),
        queue_path=Path(artifact_dir) / "browser-transport-queue.json",
        browser_lock_timeout=10,
    )
    Path(result_path).write_text(
        json.dumps({"returncode": result.returncode, "stderr": result.stderr, "duration": result.duration}),
        encoding="utf-8",
    )


def test_worker_serializes_browser_transport_commands(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "active").write_text("0\n", encoding="utf-8")
    (state_dir / "max_active").write_text("0\n", encoding="utf-8")
    command_script = tmp_path / "browser-command.sh"
    command_script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
state="{state_dir}"
(
  flock 200
  active="$(cat "$state/active")"
  active=$((active + 1))
  printf '%s\\n' "$active" > "$state/active"
  max_active="$(cat "$state/max_active")"
  if [[ "$active" -gt "$max_active" ]]; then
    printf '%s\\n' "$active" > "$state/max_active"
  fi
) 200>"$state/active.lock"
sleep 0.2
(
  flock 200
  active="$(cat "$state/active")"
  active=$((active - 1))
  printf '%s\\n' "$active" > "$state/active"
) 200>"$state/active.lock"
""",
        encoding="utf-8",
    )
    command_script.chmod(0o755)
    lock_file = str(tmp_path / "ask-browser.lock")
    procs = []
    for index in range(4):
        artifact_dir = tmp_path / f"lane-{index}"
        artifact_dir.mkdir()
        proc = multiprocessing.Process(
            target=_browser_transport_lock_worker,
            args=(
                [str(command_script)],
                str(tmp_path),
                lock_file,
                str(artifact_dir),
                str(artifact_dir / "result.json"),
            ),
        )
        proc.start()
        procs.append((proc, artifact_dir))
    for proc, _artifact_dir in procs:
        proc.join(10)
        assert proc.exitcode == 0

    assert (state_dir / "max_active").read_text(encoding="utf-8").strip() == "1"
    for _proc, artifact_dir in procs:
        result = json.loads((artifact_dir / "result.json").read_text(encoding="utf-8"))
        assert result["returncode"] == 0
        queue = json.loads((artifact_dir / "browser-transport-queue.json").read_text(encoding="utf-8"))
        assert queue["schema"] == "ask.browser_transport_queue.v1"
        assert queue["status"] == "ACQUIRED"


def _browser_transport_concurrent_worker(
    command: list[str],
    cwd: str,
    lock_file: str,
    artifact_dir: str,
    result_path: str,
) -> None:
    os.environ["ASK_BROWSER_TRANSPORT_LOCK_FILE"] = lock_file
    os.environ.pop("ASK_BROWSER_TRANSPORT_SERIAL", None)
    result = tau_roundtable_worker._run_browser_transport_cmd(
        command,
        cwd=Path(cwd),
        timeout=10,
        handler="webgpt",
        artifact_dir=Path(artifact_dir),
        queue_path=Path(artifact_dir) / "browser-transport-queue.json",
        browser_lock_timeout=10,
    )
    Path(result_path).write_text(
        json.dumps({"returncode": result.returncode, "stderr": result.stderr, "duration": result.duration}),
        encoding="utf-8",
    )


def test_worker_browser_transport_is_concurrent_by_default(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "active").write_text("0\n", encoding="utf-8")
    (state_dir / "max_active").write_text("0\n", encoding="utf-8")
    command_script = tmp_path / "browser-command.sh"
    command_script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
state="{state_dir}"
(
  flock 200
  active="$(cat "$state/active")"
  active=$((active + 1))
  printf '%s\\n' "$active" > "$state/active"
  max_active="$(cat "$state/max_active")"
  if [[ "$active" -gt "$max_active" ]]; then
    printf '%s\\n' "$active" > "$state/max_active"
  fi
) 200>"$state/active.lock"
sleep 0.5
(
  flock 200
  active="$(cat "$state/active")"
  active=$((active - 1))
  printf '%s\\n' "$active" > "$state/active"
) 200>"$state/active.lock"
""",
        encoding="utf-8",
    )
    command_script.chmod(0o755)
    lock_file = str(tmp_path / "ask-browser.lock")
    procs = []
    for index in range(4):
        artifact_dir = tmp_path / f"lane-{index}"
        artifact_dir.mkdir()
        proc = multiprocessing.Process(
            target=_browser_transport_concurrent_worker,
            args=(
                [str(command_script)],
                str(tmp_path),
                lock_file,
                str(artifact_dir),
                str(artifact_dir / "result.json"),
            ),
        )
        proc.start()
        procs.append((proc, artifact_dir))
    for proc, _artifact_dir in procs:
        proc.join(15)
        assert proc.exitcode == 0

    assert int((state_dir / "max_active").read_text(encoding="utf-8").strip()) > 1
    for _proc, artifact_dir in procs:
        result = json.loads((artifact_dir / "result.json").read_text(encoding="utf-8"))
        assert result["returncode"] == 0


def test_join_command_checker_rejects_empty_args(tmp_path: Path) -> None:
    spec_dir = tmp_path / "join"
    spec_dir.mkdir()
    spec_path = spec_dir / "tau-dispatch-command.json"
    spec_path.write_text(json.dumps({"command": ["python", "worker.py", ""]}), encoding="utf-8")

    assert tau_roundtable_sanity_eval._join_command_has_no_empty_args(tmp_path) is False

    spec_path.write_text(json.dumps({"command": ["python", "worker.py"]}), encoding="utf-8")
    assert tau_roundtable_sanity_eval._join_command_has_no_empty_args(tmp_path) is True


def test_sequential_chain_checker_requires_handler_order() -> None:
    dag = {
        "edges": [
            {"from": "handler-webclaude", "to": "handler-webkimi"},
            {"from": "handler-webkimi", "to": "handler-webgemini"},
            {"from": "handler-webgemini", "to": "handler-webgpt"},
            {"from": "handler-webgpt", "to": "join"},
            {"from": "join", "to": "human"},
        ]
    }

    assert tau_roundtable_sanity_eval._has_sequential_chain(dag) is True
    dag["edges"][0] = {"from": "handler-webkimi", "to": "handler-webclaude"}
    assert tau_roundtable_sanity_eval._has_sequential_chain(dag) is False


def test_node_receipts_collects_statuses(tmp_path: Path) -> None:
    receipt_dir = tmp_path / "node-artifacts" / "handler-webkimi"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "node-receipt.json").write_text(
        json.dumps({"status": "PASS", "ok": True, "provider_live": True}),
        encoding="utf-8",
    )

    receipts = tau_roundtable_sanity_eval._node_receipts(tmp_path)

    assert receipts["handler-webkimi"]["ok"] is True
    assert tau_roundtable_sanity_eval._receipt_statuses(receipts) == {
        "handler-webkimi": {"status": "PASS", "ok": True, "provider_live": True}
    }


def test_live_eval_attachment_checks_require_recorded_path_and_sentinel(tmp_path: Path) -> None:
    attachment = tmp_path / "evidence.md"
    attachment.write_text(
        "ASK_LIVE_ATTACHMENT_SENTINEL=attachment-visible-test\n",
        encoding="utf-8",
    )
    response_dir = tmp_path / "node-artifacts" / "handler-webkimi"
    response_dir.mkdir(parents=True)
    response = response_dir / "response.md"
    response.write_text("I can see attachment-visible-test.\n", encoding="utf-8")
    receipts = {
        "handler-webkimi": {
            "requested_attachment_paths": [str(attachment)],
            "browser_attachment_paths": [str(attachment)],
            "browser_local_path_preflight": {
                "attached_file_count": 1,
                "inlined_file_count": 0,
            },
            "response_path": str(response),
        }
    }

    checks = tau_roundtable_sanity_eval._attachment_checks(
        tmp_path,
        handlers=["webkimi"],
        node_receipts=receipts,
        attach_files=[str(attachment)],
        attachment_sentinel="attachment-visible-test",
    )

    assert [check["ok"] for check in checks] == [True, True, True]
    assert tau_roundtable_sanity_eval._infer_attachment_sentinel([str(attachment)]) == "attachment-visible-test"


def test_worker_prompt_includes_prior_receipts_and_verdict_contract(tmp_path: Path) -> None:
    prior_dir = tmp_path / "handler-webgpt"
    prior_dir.mkdir(parents=True)
    response_path = prior_dir / "response.md"
    response_path.write_text("WebGPT produced the implementation.", encoding="utf-8")
    receipt_path = prior_dir / "node-receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-webgpt",
                "handler": "webgpt",
                "status": "PASS",
                "ok": True,
                "response_path": str(response_path),
            }
        ),
        encoding="utf-8",
    )

    receipts = tau_roundtable_worker._load_prior_receipts(tmp_path, ["handler-webgpt"])
    prompt = tau_roundtable_worker._handler_prompt(
        "Ask webgpt to do the work, then ask webclaude to review it for pass/fail.",
        "webclaude",
        prior_receipts=receipts,
        requires_verdict=True,
    )

    assert "Prior handler receipts" in prompt
    assert "WebGPT produced the implementation." in prompt
    assert "Your first non-empty line must be exactly one review verdict" in prompt
    assert "VERDICT: PASS" in prompt
    assert "Do not omit the VERDICT line" in prompt
    assert tau_roundtable_worker._extract_verdict("VERDICT: FAIL\nReason") == "FAIL"
    assert tau_roundtable_worker._has_verdict("No clear verdict") is False


def test_project_watchdog_repair_prompt_requires_reviewer_verdict(tmp_path: Path) -> None:
    prior_dir = tmp_path / "handler-gpt-5-5-high"
    prior_dir.mkdir(parents=True)
    response_path = prior_dir / "response.md"
    response_path.write_text("Creator changed the registry and ran proof.", encoding="utf-8")
    (prior_dir / "node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-gpt-5-5-high",
                "handler": "gpt-5.5-high",
                "status": "PASS",
                "ok": True,
                "response_path": str(response_path),
            }
        ),
        encoding="utf-8",
    )
    request_text = (
        "The creator seat implements the fix and commits it. The reviewer seat "
        "checks it against the ticket's acceptance criterion and required proof, "
        "and answers VERDICT: PASS, VERDICT: FAIL, or VERDICT: NEEDS_ATTENTION."
    )

    receipts = tau_roundtable_worker._load_prior_receipts(tmp_path, ["handler-gpt-5-5-high"])
    assert tau_roundtable_worker._requires_verdict(request_text, receipts) is True
    prompt = tau_roundtable_worker._handler_prompt(
        request_text,
        "claude-opus-4-8-high",
        prior_receipts=receipts,
        requires_verdict=tau_roundtable_worker._requires_verdict(request_text, receipts),
    )

    assert "Your first non-empty line must be exactly one review verdict" in prompt
    assert "VERDICT: NEEDS_ATTENTION" in prompt


def test_worker_webclaude_submit_command_includes_prior_response_attachment(tmp_path: Path) -> None:
    node_root = tmp_path / "node-artifacts"
    prior_dir = node_root / "handler-webkimi"
    prior_dir.mkdir(parents=True)
    prior_response = prior_dir / "response.md"
    prior_response.write_text("WebKimi prior response.\n", encoding="utf-8")
    (prior_dir / "node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-webkimi",
                "handler": "webkimi",
                "status": "PASS",
                "ok": True,
                "response_path": str(prior_response),
            }
        ),
        encoding="utf-8",
    )
    request_file = tmp_path / "request.json"
    request_file.write_text(
        json.dumps({"request": "Ask webkimi, then ask webclaude to review for pass/fail."}),
        encoding="utf-8",
    )
    artifact_dir = node_root / "handler-webclaude"
    artifact_dir.mkdir(parents=True)
    args = SimpleNamespace(
        node_id="handler-webclaude",
        handler="webclaude",
        topology="sequential",
        request_file=str(request_file),
        browser_oracle_project="webclaude",
        next_agent="join",
        artifact_dir=str(artifact_dir),
        surf_run=str(tmp_path / "surf-run.sh"),
        browser_oracle_run=str(tmp_path / "browser-oracle-run.sh"),
        scillm_base_url="http://127.0.0.1:4001",
        scillm_api_key="",
        prior_node=["handler-webkimi"],
        timeout=300,
        stable_polls=2,
        no_activate=True,
        evidence=[],
        codex_workspace="",
        browser_model_preference="Opus 5 High",
    )
    seen_commands: list[list[str]] = []

    def fake_run_cmd(command: list[str], *, cwd: Path, timeout: int) -> tau_roundtable_worker.CmdResult:
        seen_commands.append(command)
        if "resolve" in command:
            return tau_roundtable_worker.CmdResult(
                command,
                0,
                json.dumps({"tab_id": "837360812", "conversation_url": "https://claude.ai/chat/example"}),
                "",
                0.01,
            )
        if "claude.submit" in command:
            response_path = Path(command[command.index("--output") + 1])
            raw_path = Path(command[command.index("--raw-output") + 1])
            meta_path = Path(command[command.index("--meta-output") + 1])
            response_path.write_text("VERDICT: PASS\nClaude reviewed the prior response.\n", encoding="utf-8")
            raw_path.write_text("VERDICT: PASS\nClaude reviewed the prior response.\n", encoding="utf-8")
            meta_path.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            return tau_roundtable_worker.CmdResult(command, 0, "", "", 0.01)
        return tau_roundtable_worker.CmdResult(command, 99, "", "unexpected command", 0.01)

    original_run_cmd = tau_roundtable_worker._run_cmd
    tau_roundtable_worker._run_cmd = fake_run_cmd
    try:
        result = tau_roundtable_worker._run_handler(args, {"goal": {"goal_hash": "sha256:test"}}, artifact_dir)
    finally:
        tau_roundtable_worker._run_cmd = original_run_cmd

    assert result["exit_code"] == 0
    submit_command = next(command for command in seen_commands if "claude.submit" in command)
    assert submit_command[submit_command.index("--attach-file") + 1] == str(prior_response)
    assert submit_command[submit_command.index("--model") + 1] == "Opus 5 High"
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["mocked"] is False
    assert receipt["live"] is True
    assert receipt["browser_model_preference"] == "Opus 5 High"
    assert receipt["provider_receipt"]["browser_model_preference"] == "Opus 5 High"


def test_worker_webclaude_refreshes_binding_after_new_url_materializes(tmp_path: Path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"request": "Ask webclaude to answer this."}), encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-webclaude"
    artifact_dir.mkdir(parents=True)
    args = SimpleNamespace(
        node_id="handler-webclaude",
        handler="webclaude",
        topology="concurrent",
        request_file=str(request_file),
        browser_oracle_project="webclaude",
        next_agent="join",
        artifact_dir=str(artifact_dir),
        surf_run=str(tmp_path / "surf-run.sh"),
        browser_oracle_run=str(tmp_path / "browser-oracle-run.sh"),
        scillm_base_url="http://127.0.0.1:4001",
        scillm_api_key="",
        prior_node=[],
        timeout=300,
        stable_polls=2,
        no_activate=True,
        evidence=[],
        codex_workspace="",
    )
    seen_commands: list[list[str]] = []

    def fake_run_cmd(command: list[str], *, cwd: Path, timeout: int) -> tau_roundtable_worker.CmdResult:
        seen_commands.append(command)
        if "resolve" in command:
            return tau_roundtable_worker.CmdResult(
                command,
                0,
                json.dumps({"tab_id": "837360921", "conversation_url": "https://claude.ai/new"}),
                "",
                0.01,
            )
        if "tab.list" in command:
            return tau_roundtable_worker.CmdResult(
                command,
                0,
                json.dumps(
                    [
                        {
                            "id": 837360921,
                            "url": "https://claude.ai/chat/9909bd8e-145d-4be5-8a21-2d3b69152e53",
                            "title": "Claude",
                        }
                    ]
                ),
                "",
                0.01,
            )
        if "bind" in command:
            return tau_roundtable_worker.CmdResult(
                command,
                0,
                json.dumps({"state_path": str(tmp_path / "webclaude.json")}),
                "",
                0.01,
            )
        if "claude.submit" in command:
            response_path = Path(command[command.index("--output") + 1])
            raw_path = Path(command[command.index("--raw-output") + 1])
            meta_path = Path(command[command.index("--meta-output") + 1])
            response_path.write_text("Claude answered.\n", encoding="utf-8")
            raw_path.write_text("Claude answered.\n<<<CLAUDE_DONE:test>>>\n", encoding="utf-8")
            meta_path.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "requested_tab_id": "837360921",
                        "controlled_tab_id": "837360921",
                        "raw_contains_sentinel": True,
                        "current_url": "https://claude.ai/chat/9909bd8e-145d-4be5-8a21-2d3b69152e53",
                    }
                ),
                encoding="utf-8",
            )
            return tau_roundtable_worker.CmdResult(command, 0, "", "", 0.01)
        return tau_roundtable_worker.CmdResult(command, 99, "", "unexpected command", 0.01)

    original_run_cmd = tau_roundtable_worker._run_cmd
    tau_roundtable_worker._run_cmd = fake_run_cmd
    try:
        result = tau_roundtable_worker._run_handler(args, {"goal": {"goal_hash": "sha256:test"}}, artifact_dir)
    finally:
        tau_roundtable_worker._run_cmd = original_run_cmd

    assert result["exit_code"] == 0
    submit_command = next(command for command in seen_commands if "claude.submit" in command)
    assert submit_command[submit_command.index("--url") + 1] == (
        "https://claude.ai/chat/9909bd8e-145d-4be5-8a21-2d3b69152e53"
    )
    bind_command = next(command for command in seen_commands if "bind" in command)
    assert bind_command == [
        str(args.browser_oracle_run),
        "bind",
        "webclaude",
        "--backend",
        "webclaude",
        "--tab-id",
        "837360921",
        "--url",
        "https://claude.ai/chat/9909bd8e-145d-4be5-8a21-2d3b69152e53",
        "--manual",
        "--json",
    ]
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["browser_oracle_binding_refresh"]["status"] == "updated"
    assert (
        receipt["browser_oracle_binding_refresh"]["current_url"]
        == "https://claude.ai/chat/9909bd8e-145d-4be5-8a21-2d3b69152e53"
    )


def test_worker_classifies_kimi_capacity_busy_as_provider_limited() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webkimi",
        failure="Kimi provider capacity busy: System is currently busy / Capacity is busy. Please try again later.",
        response_text="",
        raw_text="System is currently busy. Please try again later.",
        prompt_text="",
        submit_meta={
            "status": "failed",
            "failure": "kimi_provider_capacity_busy",
            "blocker": "BLOCKED_KIMI_PROVIDER_CAPACITY",
            "kimi_provider_capacity_busy": True,
        },
        commands=[],
    )

    assert failure_code == tau_roundtable_worker.BROWSER_PROVIDER_RATE_LIMITED


def test_worker_does_not_treat_false_busy_metadata_as_provider_limited() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webkimi",
        failure="Error: Response timeout",
        response_text="",
        raw_text="",
        prompt_text="Inspect the attached image.",
        submit_meta={
            "status": "failed",
            "kimi_provider_capacity_busy": False,
            "provider_busy_cooldown_count": 0,
        },
        commands=[],
    )

    assert failure_code == "prompt_too_large_or_stalled"


@pytest.mark.parametrize(
    "response_text",
    [
        "TESTER_STATUS: UNKNOWN\nThe attachment is inaccessible and is not mounted.",
        "The image file was not provided or rendered, so I cannot inspect the visual contents.",
        "The attached local image cannot be inspected. Local attachment is unreachable.",
    ],
)
def test_worker_rejects_explicit_attachment_access_denials(response_text: str) -> None:
    assert tau_roundtable_worker._response_denies_attachment_access(response_text) is True
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webgpt",
        failure="",
        response_text=response_text,
        raw_text=response_text,
        prompt_text="Inspect the attached visual evidence.",
        submit_meta={"status": "completed"},
        commands=[],
    )
    assert failure_code == tau_roundtable_worker.BROWSER_ATTACHMENT_UNAVAILABLE


def test_worker_does_not_reject_cautious_answer_without_attachment_denial() -> None:
    response_text = "TESTER_STATUS: UNKNOWN\nThe status label is too small to read confidently."

    assert tau_roundtable_worker._response_denies_attachment_access(response_text) is False


def test_worker_rejects_claude_missing_bundle_wording() -> None:
    response_text = "I checked the dispatch bundle before answering. There is no Battle bundle in it."

    assert tau_roundtable_worker._response_denies_attachment_access(response_text) is True


def test_direct_claude_cli_inlines_text_attachment_and_records_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = tmp_path / "bundle.md"
    evidence.write_text("ASK_ATTACHMENT_SENTINEL=direct-claude-visible\n", encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Read the attached bundle and echo the sentinel.", encoding="utf-8")
    response = tmp_path / "response.md"
    raw = tmp_path / "response.raw.md"
    meta = tmp_path / "response.meta.json"
    captured: dict[str, str] = {}

    def fake_run(command, *, input, capture_output, text, timeout, cwd):
        captured["input"] = input
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="I saw ASK_ATTACHMENT_SENTINEL=direct-claude-visible",
            stderr="",
        )

    monkeypatch.setattr(tau_roundtable_worker.subprocess, "run", fake_run)
    args = SimpleNamespace(
        handler="claude-opus-4-8-high",
        attach_files=[str(evidence)],
        timeout=60,
        codex_workspace=str(tmp_path),
    )

    text, submit_meta, commands = tau_roundtable_worker._run_claude_handler(
        args,
        prompt_path=prompt,
        response_path=response,
        raw_path=raw,
        meta_path=meta,
    )

    assert "ASK_ATTACHMENT_SENTINEL=direct-claude-visible" in captured["input"]
    assert "LOCAL_ATTACHMENT_1" in captured["input"]
    assert text == "I saw ASK_ATTACHMENT_SENTINEL=direct-claude-visible"
    assert commands[0]["returncode"] == 0
    assert tau_roundtable_worker._provider_transport_for_args(args, args.handler) == "$claude-cli"
    assert tau_roundtable_worker._transport_for_args(args, args.handler) == "claude.cli"
    assert submit_meta["requested_handler"] == "claude-opus-4-8-high"
    delivery = submit_meta["local_attachment_delivery"]
    assert delivery["schema"] == "ask.local_model_attachment_delivery.v1"
    assert delivery["delivered"] is True
    assert delivery["delivered_count"] == 1
    assert delivery["attachments"][0]["name"] == "bundle.md"
    assert json.loads(meta.read_text(encoding="utf-8"))["local_attachment_delivery"]["delivered"] is True


def test_worker_fails_closed_when_browser_response_denies_attached_evidence(tmp_path: Path) -> None:
    image_path = tmp_path / "visual-evidence.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    request_file = tmp_path / "request.json"
    request_file.write_text(
        json.dumps({"request": f"Inspect {image_path} and report the visible labels."}),
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgrok"
    artifact_dir.mkdir(parents=True)
    args = SimpleNamespace(
        node_id="handler-webgrok",
        handler="webgrok",
        topology="concurrent",
        workflow_mode="roundtable",
        request_file=str(request_file),
        browser_oracle_project="webgrok",
        provider_hint="",
        next_agent="join",
        artifact_dir=str(artifact_dir),
        surf_run=str(tmp_path / "surf-run.sh"),
        browser_oracle_run=str(tmp_path / "browser-oracle-run.sh"),
        scillm_base_url="http://127.0.0.1:4001",
        scillm_api_key="",
        prior_node=[],
        timeout=300,
        stable_polls=2,
        no_activate=True,
        evidence=[],
        codex_workspace="",
        browser_model_preference="",
    )

    def fake_run_cmd(command: list[str], *, cwd: Path, timeout: int) -> tau_roundtable_worker.CmdResult:
        if "resolve" in command:
            return tau_roundtable_worker.CmdResult(
                command,
                0,
                json.dumps({"tab_id": "837361318", "conversation_url": "https://grok.com/"}),
                "",
                0.01,
            )
        if "grok.submit" in command:
            response_path = Path(command[command.index("--output") + 1])
            raw_path = Path(command[command.index("--raw-output") + 1])
            meta_path = Path(command[command.index("--meta-output") + 1])
            response = "TESTER_STATUS: UNKNOWN\nThe attachment is inaccessible and is not mounted."
            response_path.write_text(response, encoding="utf-8")
            raw_path.write_text(response, encoding="utf-8")
            meta_path.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            return tau_roundtable_worker.CmdResult(command, 0, "", "", 0.01)
        return tau_roundtable_worker.CmdResult(command, 99, "", "unexpected command", 0.01)

    original_run_cmd = tau_roundtable_worker._run_cmd
    tau_roundtable_worker._run_cmd = fake_run_cmd
    try:
        result = tau_roundtable_worker._run_handler(args, {"goal": {"goal_hash": "sha256:test"}}, artifact_dir)
    finally:
        tau_roundtable_worker._run_cmd = original_run_cmd

    assert result["exit_code"] == 0
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["ok"] is False
    assert receipt["provider_live"] is False
    assert receipt["browser_attachment_paths"] == [str(image_path)]
    assert receipt["failure_code"] == tau_roundtable_worker.BROWSER_ATTACHMENT_UNAVAILABLE
    assert receipt["recovery_packet"]["auto_retry_allowed"] is False
    assert receipt["recovery_packet"]["next_command"] == []


def test_worker_webgpt_receipt_includes_transport_summary(tmp_path: Path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"request": "Ask webgpt to review the bundle."}), encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgpt"
    artifact_dir.mkdir(parents=True)
    args = SimpleNamespace(
        node_id="handler-webgpt",
        handler="webgpt",
        topology="concurrent",
        request_file=str(request_file),
        browser_oracle_project="tau",
        next_agent="join",
        artifact_dir=str(artifact_dir),
        surf_run=str(tmp_path / "surf-run.sh"),
        browser_oracle_run=str(tmp_path / "browser-oracle-run.sh"),
        scillm_base_url="http://127.0.0.1:4001",
        scillm_api_key="",
        prior_node=[],
        timeout=300,
        stable_polls=2,
        no_activate=True,
        evidence=[],
        codex_workspace="",
    )
    summary_payload = {
        "schema": "surf.webgpt_transport_summary.v1",
        "artifact_dir": str(artifact_dir),
        "requested_tab_id": "837360999",
        "requested_url": "https://chatgpt.com/c/example",
        "controlled_tab_id": "837360999",
        "submitted_to_chatgpt": True,
        "prepared_prompt_is_transport_proof": False,
        "response_raw_path": str(artifact_dir / "response.raw.md"),
        "response_meta_path": str(artifact_dir / "response.meta.json"),
        "sentinel": "<<<WEBGPT_DONE:test>>>",
        "raw_sentinel_present": True,
        "focus_changed": False,
        "final_transport_state": "completed",
        "next_command": f"surf webgpt.recover --artifact-dir {artifact_dir} --audit",
        "needs_attention": None,
    }
    seen_commands: list[list[str]] = []

    def fake_run_cmd(command: list[str], *, cwd: Path, timeout: int) -> tau_roundtable_worker.CmdResult:
        seen_commands.append(command)
        if "resolve" in command:
            return tau_roundtable_worker.CmdResult(
                command,
                0,
                json.dumps({"tab_id": "837360999", "conversation_url": "https://chatgpt.com/c/example"}),
                "",
                0.01,
            )
        if "webgpt.submit" in command:
            response_path = Path(command[command.index("--output") + 1])
            raw_path = Path(command[command.index("--raw-output") + 1])
            meta_path = Path(command[command.index("--meta-output") + 1])
            response_path.write_text("WebGPT reviewed the bundle.\n", encoding="utf-8")
            raw_path.write_text("WebGPT reviewed the bundle.\n<<<WEBGPT_DONE:test>>>\n", encoding="utf-8")
            meta_path.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "controlled_tab_id": "837360999",
                        "raw_contains_sentinel": True,
                        "focus_changed": False,
                    }
                ),
                encoding="utf-8",
            )
            (artifact_dir / "webgpt_transport_summary.json").write_text(
                json.dumps(summary_payload),
                encoding="utf-8",
            )
            return tau_roundtable_worker.CmdResult(command, 0, "", "", 0.01)
        return tau_roundtable_worker.CmdResult(command, 99, "", "unexpected command", 0.01)

    original_run_cmd = tau_roundtable_worker._run_cmd
    tau_roundtable_worker._run_cmd = fake_run_cmd
    try:
        result = tau_roundtable_worker._run_handler(args, {"goal": {"goal_hash": "sha256:test"}}, artifact_dir)
    finally:
        tau_roundtable_worker._run_cmd = original_run_cmd

    assert result["exit_code"] == 0
    submit_command = next(command for command in seen_commands if "webgpt.submit" in command)
    assert submit_command[submit_command.index("--expect-url") + 1] == "https://chatgpt.com/c/example"
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["transport_summary_path"] == str(artifact_dir / "webgpt_transport_summary.json")
    assert receipt["webgpt_transport_summary"]["final_transport_state"] == "completed"
    assert receipt["provider_receipt"]["transport_summary_path"] == str(
        artifact_dir / "webgpt_transport_summary.json"
    )
    handoff = result["handoff"]
    assert str(artifact_dir / "webgpt_transport_summary.json") in handoff["context"]["artifacts"]
    summary_evidence = [
        item for item in handoff["result"]["evidence"] if item.get("kind") == "webgpt_transport_summary"
    ]
    assert summary_evidence == [
        {
            "kind": "webgpt_transport_summary",
            "node_id": "handler-webgpt",
            "handler": "webgpt",
            "path": str(artifact_dir / "webgpt_transport_summary.json"),
            "final_transport_state": "completed",
            "next_command": summary_payload["next_command"],
            "goal_hash": "sha256:test",
        }
    ]


def test_worker_preserves_degraded_webgpt_sentinel_response_after_focus_drift(tmp_path: Path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"request": "Ask webgpt to review the bundle."}), encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgpt"
    artifact_dir.mkdir(parents=True)
    args = SimpleNamespace(
        node_id="handler-webgpt",
        handler="webgpt",
        topology="concurrent",
        request_file=str(request_file),
        browser_oracle_project="tau",
        next_agent="join",
        artifact_dir=str(artifact_dir),
        surf_run=str(tmp_path / "surf-run.sh"),
        browser_oracle_run=str(tmp_path / "browser-oracle-run.sh"),
        scillm_base_url="http://127.0.0.1:4001",
        scillm_api_key="",
        prior_node=[],
        timeout=300,
        stable_polls=2,
        no_activate=True,
        evidence=[],
        codex_workspace="",
        browser_model_preference="",
    )
    sentinel = "<<<WEBGPT_DONE:20260725T164452Z:8a6dc2c2>>>"

    def fake_run_cmd(command: list[str], *, cwd: Path, timeout: int) -> tau_roundtable_worker.CmdResult:
        if "resolve" in command:
            return tau_roundtable_worker.CmdResult(
                command,
                0,
                json.dumps({"tab_id": "837361097", "conversation_url": "https://chatgpt.com/c/example"}),
                "",
                0.01,
            )
        if "webgpt.submit" in command:
            response_path = Path(command[command.index("--output") + 1])
            raw_path = Path(command[command.index("--raw-output") + 1])
            meta_path = Path(command[command.index("--meta-output") + 1])
            response_path.write_text("WebGPT advisory response.\n", encoding="utf-8")
            raw_path.write_text(f"WebGPT advisory response.\n{sentinel}\n", encoding="utf-8")
            meta_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "failure": "focus_stolen_despite_no_activate",
                        "proof_status": "degraded_focus",
                        "response_proof_status": "response_unproven",
                        "sentinel": sentinel,
                        "requested_tab_id": "837361097",
                        "controlled_tab_id": None,
                        "raw_contains_sentinel": True,
                        "clean_contains_sentinel": False,
                        "clean_contamination_markers": [],
                        "focus_changed": True,
                        "focus_invariant_ok": False,
                        "submitted_to_chatgpt": True,
                        "tab_identity_preflight": {
                            "ok": True,
                            "tab_id": "837361097",
                            "tab": {
                                "id": "837361097",
                                "url": "https://chatgpt.com/c/example",
                                "title": "ChatGPT",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            return tau_roundtable_worker.CmdResult(command, 5, "", "focus stolen", 0.01)
        return tau_roundtable_worker.CmdResult(command, 99, "", "unexpected command", 0.01)

    original_run_cmd = tau_roundtable_worker._run_cmd
    tau_roundtable_worker._run_cmd = fake_run_cmd
    try:
        result = tau_roundtable_worker._run_handler(args, {"goal": {"goal_hash": "sha256:test"}}, artifact_dir)
    finally:
        tau_roundtable_worker._run_cmd = original_run_cmd

    assert result["exit_code"] == 0
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["ok"] is True
    assert receipt["failure"] is None
    assert receipt["response_chars"] == len("WebGPT advisory response.\n")
    assert receipt["submit_meta"]["status"] == "recovered_focus_changed"
    assert receipt["submit_meta"]["proof_status"] == "response_proven"
    assert receipt["submit_meta"]["response_proof_status"] == "response_proven"
    assert receipt["submit_meta"]["controlled_tab_id"] == "837361097"
    assert receipt["submit_meta"]["conversation_url"] == "https://chatgpt.com/c/example"
    assert receipt["submit_meta"]["transport_degraded"] is True
    assert receipt["recovery_packet"] is None


def test_worker_quarantines_unverified_webgpt_response_md(tmp_path: Path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"request": "Ask webgpt to review the bundle."}), encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgpt"
    artifact_dir.mkdir(parents=True)
    args = SimpleNamespace(
        node_id="handler-webgpt",
        handler="webgpt",
        topology="concurrent",
        workflow_mode="roundtable",
        request_file=str(request_file),
        browser_oracle_project="tau",
        next_agent="join",
        artifact_dir=str(artifact_dir),
        surf_run=str(tmp_path / "surf-run.sh"),
        browser_oracle_run=str(tmp_path / "browser-oracle-run.sh"),
        scillm_base_url="http://127.0.0.1:4001",
        scillm_api_key="",
        prior_node=[],
        timeout=300,
        stable_polls=2,
        no_activate=True,
        evidence=[],
        codex_workspace="",
        browser_model_preference="",
    )
    sentinel = "<<<WEBGPT_DONE:20260727T011747Z:6363a59e>>>"

    def fake_run_cmd(command: list[str], *, cwd: Path, timeout: int) -> tau_roundtable_worker.CmdResult:
        if "resolve" in command:
            return tau_roundtable_worker.CmdResult(
                command,
                0,
                json.dumps({"tab_id": "837362190", "conversation_url": "https://chatgpt.com/"}),
                "",
                0.01,
            )
        if "webgpt.submit" in command:
            response_path = Path(command[command.index("--output") + 1])
            raw_path = Path(command[command.index("--raw-output") + 1])
            meta_path = Path(command[command.index("--meta-output") + 1])
            response_path.write_text("Plausible but unverified WebGPT response.\n", encoding="utf-8")
            raw_path.write_text(f"Plausible but unverified WebGPT response.\n{sentinel}\n", encoding="utf-8")
            meta_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "failure": "missing_controlled_tab_id_or_contaminated_clean_output",
                        "proof_status": "unknown_failure",
                        "response_proof_status": "response_unproven",
                        "sentinel": sentinel,
                        "requested_tab_id": "837362190",
                        "controlled_tab_id": None,
                        "raw_contains_sentinel": True,
                        "clean_contains_sentinel": False,
                        "clean_contamination_markers": [],
                        "tab_identity_preflight": {
                            "ok": True,
                            "tab_id": "837362190",
                            "tab": {"id": "837362190", "url": "https://chatgpt.com/", "title": "ChatGPT"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            return tau_roundtable_worker.CmdResult(command, 1, "", "Terminated", 0.01)
        return tau_roundtable_worker.CmdResult(command, 99, "", "unexpected command", 0.01)

    original_run_cmd = tau_roundtable_worker._run_cmd
    tau_roundtable_worker._run_cmd = fake_run_cmd
    try:
        result = tau_roundtable_worker._run_handler(args, {"goal": {"goal_hash": "sha256:test"}}, artifact_dir)
    finally:
        tau_roundtable_worker._run_cmd = original_run_cmd

    assert result["exit_code"] == 0
    assert not (artifact_dir / "response.md").exists()
    quarantined = artifact_dir / "response.contaminated.md"
    assert quarantined.read_text(encoding="utf-8") == "Plausible but unverified WebGPT response.\n"
    quarantine_receipt = json.loads((artifact_dir / "response.quarantine.json").read_text(encoding="utf-8"))
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((artifact_dir / "browser-recovery-packet.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["ok"] is False
    assert receipt["provider_live"] is False
    assert receipt["failure_code"] == tau_roundtable_worker.WEBGPT_UNVERIFIED_CLEAN_OUTPUT
    assert receipt["response_path"] == str(quarantined)
    assert receipt["response_quarantine"]["quarantine_path"] == str(quarantined)
    assert quarantine_receipt["failure_code"] == tau_roundtable_worker.WEBGPT_UNVERIFIED_CLEAN_OUTPUT
    assert recovery["failure_code"] == tau_roundtable_worker.WEBGPT_UNVERIFIED_CLEAN_OUTPUT
    assert recovery["next_command"] == []


def test_browser_failure_classifier_keeps_tab_url_mismatch_distinct() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webclaude",
        failure="tab 837360921 URL mismatch: expected https://claude.ai/new, saw https://claude.ai/chat/live-url",
        response_text="",
        raw_text="",
        prompt_text="short prompt",
        submit_meta={
            "status": "failed",
            "failure": "tab 837360921 URL mismatch: expected https://claude.ai/new, saw https://claude.ai/chat/live-url",
        },
        commands=[
            {
                "returncode": 4,
                "stderr_excerpt": "tab 837360921 URL mismatch: expected https://claude.ai/new, saw https://claude.ai/chat/live-url",
            }
        ],
    )

    assert failure_code == tau_roundtable_worker.BROWSER_TAB_IDENTITY_MISMATCH


def test_browser_failure_classifier_marks_cloudflare_as_access_blocked() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webgpt",
        failure="cloudflare_challenge",
        response_text="",
        raw_text="",
        prompt_text="short prompt",
        submit_meta={
            "status": "failed",
            "failure": "cloudflare_challenge",
            "blocker": "BLOCKED_WEBGPT_CLOUDFLARE_CHALLENGE",
            "browser_access_blocked": True,
            "cloudflare_challenge_detected": True,
        },
        commands=[
            {
                "returncode": 1,
                "stderr_excerpt": "Error: Cloudflare challenge detected - complete in browser",
            }
        ],
    )

    assert failure_code == tau_roundtable_worker.BROWSER_ACCESS_BLOCKED
    assert (
        tau_roundtable_worker._auto_retry_blocked_reason(
            failure_code=failure_code,
            bundle_paths=["/tmp/review-bundle.md"],
            can_attach=True,
        )
        == "browser_access_challenge_requires_human_browser_recovery"
    )


def test_browser_failure_classifier_marks_provider_limit_distinct() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webgpt",
        failure="ChatGPT is rate limited: too many requests; wait before retrying",
        response_text="",
        raw_text="You've hit your limit. Please try again later.",
        prompt_text="short prompt",
        submit_meta={
            "status": "failed",
            "failure": "submit_failed",
            "chatgpt_too_many_requests_detected": True,
            "chatgpt_rate_limit": {"exhausted": True},
        },
        commands=[
            {
                "returncode": 1,
                "stderr_excerpt": "You've hit your limit. Please try again later.",
            }
        ],
    )

    assert failure_code == tau_roundtable_worker.BROWSER_PROVIDER_RATE_LIMITED
    assert (
        tau_roundtable_worker._auto_retry_blocked_reason(
            failure_code=failure_code,
            bundle_paths=["/tmp/review-bundle.md"],
            can_attach=True,
        )
        == "browser_provider_rate_limit_requires_backoff"
    )


def test_browser_failure_classifier_marks_terminal_sentinel_trailing_content_distinct() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webgemini",
        failure="assistant response contains text after terminal sentinel",
        response_text="",
        raw_text="stale unrelated content after the terminal sentinel",
        prompt_text="short prompt",
        submit_meta={"status": "failed"},
        commands=[{"returncode": 1, "stderr_excerpt": "assistant response contains text after terminal sentinel"}],
    )

    assert failure_code == tau_roundtable_worker.BROWSER_SENTINEL_TRAILING_CONTENT
    assert tau_roundtable_worker._requires_local_readable_bundle(failure_code) is False
    assert (
        tau_roundtable_worker._auto_retry_blocked_reason(
            failure_code=failure_code,
            bundle_paths=["/tmp/review-bundle.md"],
            can_attach=True,
        )
        == "browser_terminal_sentinel_parser_requires_repair_or_fresh_tab"
    )


def test_browser_failure_classifier_ignores_failure_names_in_prompt() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webgpt",
        failure="submit_failed",
        response_text="",
        raw_text="",
        prompt_text=(
            "Return no browser_access_blocked or transport blockers. "
            "The provider may report browser_provider_rate_limited."
        ),
        submit_meta={
            "status": "failed",
            "failure": "submit_failed",
            "blocker": "BLOCKED_WEBGPT_PROVIDER_RATE_LIMIT",
            "proof_status": "rate_limited",
            "browser_access_blocked": False,
            "chatgpt_too_many_requests_detected": True,
            "chatgpt_rate_limit": {"exhausted": True},
        },
        commands=[],
    )

    assert failure_code == tau_roundtable_worker.BROWSER_PROVIDER_RATE_LIMITED


@pytest.mark.parametrize(
    "failure",
    [
        "Error: Socket connect failed: Socket not found. Attempted socket: /tmp/surf.sock",
        "Error: Surf connection closed before response",
    ],
)
def test_browser_failure_classifier_keeps_socket_loss_distinct_from_provider_limit(
    failure: str,
) -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webgpt",
        failure=failure,
        response_text="",
        raw_text="",
        prompt_text=(
            "A sibling candidate may be browser_provider_rate_limited. "
            "Preserve that state in the scorecard."
        ),
        submit_meta={
            "status": "failed",
            "failure": failure,
            "chatgpt_too_many_requests_detected": True,
            "chatgpt_rate_limit": {"exhausted": True},
        },
        commands=[{"returncode": 1, "stderr_excerpt": failure}],
    )

    assert failure_code == tau_roundtable_worker.SURF_BROWSER_CONNECTION_UNAVAILABLE
    assert failure_code != tau_roundtable_worker.BROWSER_PROVIDER_RATE_LIMITED


def test_gemini_worker_timeout_covers_stall_retry_envelope(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SURF_LOCK_TIMEOUT_MS", "1800000")
    assert tau_roundtable_worker._browser_submit_timeout("webgpt", 900) == 3750
    assert tau_roundtable_worker._browser_submit_timeout("webgemini", 300) == 2670
    assert tau_roundtable_worker._browser_submit_timeout("webgemini", 900) == 3870
    assert tau_roundtable_worker._browser_submit_timeout("webkimi", 300) == 2145
    assert tau_roundtable_worker._browser_submit_timeout("webclaude", 300) == 2145
    assert tau_roundtable_worker._browser_submit_timeout("webgrok", 300) == 2145
    assert tau_roundtable_worker._browser_submit_timeout("webclaude", 1) == 3
    monkeypatch.setenv("SURF_LOCK_TIMEOUT_MS", "invalid")
    assert tau_roundtable_worker._browser_submit_timeout("webkimi", 300) == 405


def test_browser_failure_classifier_marks_worker_command_timeout_distinct() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webclaude",
        failure="[tau-worker] command timed out after 2s; killed process group rooted at pid 123",
        response_text="",
        raw_text="",
        prompt_text="short prompt",
        submit_meta={"status": "failed"},
        commands=[
            {
                "returncode": 124,
                "stderr_excerpt": "[tau-worker] command timed out after 2s; killed process group rooted at pid 123",
            }
        ],
    )

    assert failure_code == tau_roundtable_worker.BROWSER_HANDLER_TIMEOUT


def test_browser_failure_classifier_marks_unknown_tool_as_runtime_mismatch() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webgpt",
        failure="Error: Unknown tool: text",
        response_text="",
        raw_text="",
        prompt_text="short prompt",
        submit_meta={
            "status": "failed",
            "failure": "Error: Unknown tool: text",
        },
        commands=[
            {
                "returncode": 4,
                "stderr_excerpt": "Error: Unknown tool: text",
            }
        ],
    )

    assert failure_code == tau_roundtable_worker.BROWSER_TOOL_UNSUPPORTED
    assert (
        tau_roundtable_worker._auto_retry_blocked_reason(
            failure_code=failure_code,
            bundle_paths=["/tmp/review-bundle.md"],
            can_attach=True,
        )
        == "surf_runtime_command_mismatch_requires_repair"
    )


def test_browser_failure_classifier_marks_invalid_tab_id_as_identity_failure() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webgemini",
        failure="Error: Invalid tab ID: 837359725. Use 'surf tab.list' to see available tabs.",
        response_text="",
        raw_text="",
        prompt_text="short prompt",
        submit_meta={
            "status": "failed",
            "failure": "Error: Invalid tab ID: 837359725. Use 'surf tab.list' to see available tabs.",
        },
        commands=[
            {
                "returncode": 1,
                "stderr_excerpt": "Error: Invalid tab ID: 837359725. Use 'surf tab.list' to see available tabs.",
            }
        ],
    )

    assert failure_code == tau_roundtable_worker.BROWSER_TAB_IDENTITY_MISMATCH
    assert (
        tau_roundtable_worker._auto_retry_blocked_reason(
            failure_code=failure_code,
            bundle_paths=["/tmp/review-bundle.md"],
            can_attach=True,
        )
        == "browser_tab_identity_rebind_required"
    )


def test_worker_prior_receipts_marks_missing_upstream_not_ready(tmp_path: Path) -> None:
    receipts = tau_roundtable_worker._load_prior_receipts(tmp_path, ["handler-webgpt"])

    assert receipts == [
        {
            "node_id": "handler-webgpt",
            "status": "MISSING",
            "ok": False,
            "failure": f"missing prior receipt: {tmp_path / 'handler-webgpt' / 'node-receipt.json'}",
            "path": str(tmp_path / "handler-webgpt" / "node-receipt.json"),
        }
    ]


def test_worker_lane_recovers_in_run_and_keeps_response(tmp_path: Path, monkeypatch) -> None:
    """A lane whose submit misses its capture window heals itself in-run.

    Pins the composed path: the submit produces no verifiable response, the
    recovery ladder extracts the answer that was already rendered in the tab,
    and the recovered text stays at response.md instead of being quarantined
    as a failure the lane no longer has.
    """
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"request": "Ask webgpt."}), encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgpt"
    artifact_dir.mkdir(parents=True)
    surf = tmp_path / "surf-run.sh"
    surf.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    surf.chmod(0o755)
    args = SimpleNamespace(
        node_id="handler-webgpt", handler="webgpt", topology="concurrent",
        workflow_mode="roundtable", request_file=str(request_file),
        browser_oracle_project="tau", next_agent="join", artifact_dir=str(artifact_dir),
        surf_run=str(surf), browser_oracle_run=str(tmp_path / "browser-oracle-run.sh"),
        scillm_base_url="http://127.0.0.1:4001", scillm_api_key="", prior_node=[],
        timeout=300, stable_polls=2, no_activate=True, evidence=[], codex_workspace="",
        browser_model_preference="",
    )
    sentinel = "<<<WEBGPT_DONE:20260803T120000Z:abc123>>>"

    def fake_run_cmd(command, *, cwd, timeout):
        if "resolve" in command:
            return tau_roundtable_worker.CmdResult(
                command, 0,
                json.dumps({"tab_id": "837366839", "conversation_url": "https://chatgpt.com/"}),
                "", 0.01,
            )
        if "webgpt.submit" in command:
            # Capture window missed: no sentinel captured anywhere.
            for flag, text in (("--output", ""), ("--raw-output", "")):
                Path(command[command.index(flag) + 1]).write_text(text, encoding="utf-8")
            Path(command[command.index("--meta-output") + 1]).write_text(
                json.dumps({"status": "failed", "failure": "missing_sentinel",
                            "sentinel": sentinel, "requested_tab_id": "837366839",
                            "submitted_to_chatgpt": True}),
                encoding="utf-8",
            )
            return tau_roundtable_worker.CmdResult(command, 1, "", "timed out", 0.01)
        if "webgpt.extract" in command:
            # The answer was rendered in the tab all along.
            body = f"Recovered provider answer.\n{sentinel}\n"
            for flag in ("--output", "--raw-output"):
                Path(command[command.index(flag) + 1]).write_text(body, encoding="utf-8")
            Path(command[command.index("--meta-output") + 1]).write_text(
                json.dumps({"status": "completed", "raw_contains_sentinel": True,
                            "raw_chars": len(body)}),
                encoding="utf-8",
            )
            return tau_roundtable_worker.CmdResult(command, 0, "ok", "", 0.01)
        return tau_roundtable_worker.CmdResult(command, 0, "", "", 0.01)

    monkeypatch.setattr(tau_roundtable_worker, "_run_cmd", fake_run_cmd)
    monkeypatch.setattr(tau_roundtable_worker, "_run_browser_transport_cmd",
                        lambda command, **kw: fake_run_cmd(command, cwd=kw.get("cwd"), timeout=kw.get("timeout", 60)))

    result = tau_roundtable_worker._run_handler(
        args, {"goal": {"goal_hash": "sha256:test"}}, artifact_dir
    )

    recovery = json.loads((artifact_dir / "lane-recovery.json").read_text(encoding="utf-8"))
    assert recovery["recovered"] is True
    assert recovery["recovered_by"] == "provider_extract"
    assert result["handoff"]["result"]["status"] == "PASS"
    assert (artifact_dir / "response.md").is_file()
    assert sentinel in (artifact_dir / "response.md").read_text(encoding="utf-8")
    assert not (artifact_dir / "response.unverified.md").exists()


def test_worker_lane_recovery_never_retries_provider_refusal(tmp_path: Path) -> None:
    """A rate-limited provider gets zero recovery attempts, with the reason."""
    artifact_dir = tmp_path / "art"
    artifact_dir.mkdir()
    args = SimpleNamespace(handler="webgrok", node_id="handler-webgrok",
                           surf_run=str(tmp_path / "surf.sh"), timeout=120,
                           stable_polls=2, no_activate=True, evidence=[])
    receipt = tau_roundtable_worker._attempt_lane_recovery(
        args,
        recovery_packet={"failure_code": "grok_provider_rate_limited", "next_command": []},
        browser_oracle={}, submit_meta={"sentinel": "<<<X>>>"},
        response_path=artifact_dir / "response.md",
        raw_path=artifact_dir / "response.raw.md",
        meta_path=artifact_dir / "response.meta.json",
        artifact_dir=artifact_dir, deadline=time.time() + 300,
    )
    assert receipt["recovered"] is False
    assert receipt["attempts"] == []
    assert "provider-side" in receipt["skipped_reason"]


def test_codex_workspace_lane_accepts_committed_clean_worktree(tmp_path: Path, monkeypatch) -> None:
    """A Codex creator that commits its repair must not be rejected as no-op."""
    workspace = tmp_path / "workspace"
    (workspace / ".git").mkdir(parents=True)
    artifact_dir = tmp_path / "node-artifacts" / "handler-gpt-5-5-high"
    artifact_dir.mkdir(parents=True)
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"request": "Repair the issue and commit."}), encoding="utf-8")
    args = SimpleNamespace(
        node_id="handler-gpt-5-5-high",
        handler="gpt-5.5-high",
        topology="sequential",
        workflow_mode="roundtable",
        request_file=str(request_file),
        browser_oracle_project="",
        provider_hint="",
        next_agent="reviewer",
        artifact_dir=str(artifact_dir),
        surf_run=str(tmp_path / "surf-run.sh"),
        browser_oracle_run=str(tmp_path / "browser-oracle-run.sh"),
        scillm_base_url="http://127.0.0.1:4001",
        scillm_api_key="",
        prior_node=[],
        timeout=300,
        command_timeout_budget=0,
        browser_lock_timeout=0,
        stable_polls=2,
        no_activate=True,
        evidence=[],
        attach_files=[],
        codex_workspace=str(workspace),
        browser_model_preference="",
        subagent_runner="",
        subagent_model="gpt-5.5",
        subagent_reasoning_effort="high",
        subagent_requested_model="gpt-5.5-high",
    )
    before = "0" * 40
    after = "8" * 40
    codex_ran = False

    def fake_subprocess_run(command, **kwargs):  # noqa: ANN001, ANN003
        nonlocal codex_ran
        if command[0] == "codex":
            raw_path = Path(command[command.index("-o") + 1])
            raw_path.write_text(
                "VERDICT: PASS\n\nCommitted `88b7e98a`.\n"
                "Immutable Goal: ACHIEVED_WITH_RECEIPT:/tmp/receipt.json\n",
                encoding="utf-8",
            )
            codex_ran = True
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ["git", "-C", str(workspace)]:
            git_args = command[3:]
            if git_args == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, f"{after if codex_ran else before}\n", "")
            if git_args == ["status", "--short"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if git_args == ["diff"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if git_args[:3] == ["diff", "--stat", "--patch"]:
                return subprocess.CompletedProcess(command, 0, "diff --git a/proof.py b/proof.py\n+PASS\n", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(tau_roundtable_worker.subprocess, "run", fake_subprocess_run)

    result = tau_roundtable_worker._run_handler(args, {"goal": {"goal_hash": "sha256:test"}}, artifact_dir)

    assert result["exit_code"] == 0
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["ok"] is True
    assert receipt["response_chars"] > 0
    assert receipt["provider_receipt"]["transport"] == "codex.exec"
    meta = json.loads((artifact_dir / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["head_changed"] is True
    response = (artifact_dir / "response.md").read_text(encoding="utf-8")
    assert f"HEAD: {before} -> {after}" in response
    assert "diff --git" in response


def test_codex_workspace_lane_admits_no_diff_final_message_for_review(tmp_path: Path, monkeypatch) -> None:
    """A no-diff Codex response with evidence must reach the reviewer as a response."""
    workspace = tmp_path / "workspace"
    (workspace / ".git").mkdir(parents=True)
    artifact_dir = tmp_path / "node-artifacts" / "handler-gpt-5-5-high"
    artifact_dir.mkdir(parents=True)
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"request": "Check whether the ticket is already satisfied."}), encoding="utf-8")
    args = SimpleNamespace(
        node_id="handler-gpt-5-5-high",
        handler="gpt-5.5-high",
        topology="sequential",
        workflow_mode="roundtable",
        request_file=str(request_file),
        browser_oracle_project="",
        provider_hint="",
        next_agent="reviewer",
        artifact_dir=str(artifact_dir),
        surf_run=str(tmp_path / "surf-run.sh"),
        browser_oracle_run=str(tmp_path / "browser-oracle-run.sh"),
        scillm_base_url="http://127.0.0.1:4001",
        scillm_api_key="",
        prior_node=[],
        timeout=300,
        command_timeout_budget=0,
        browser_lock_timeout=0,
        stable_polls=2,
        no_activate=True,
        evidence=[],
        attach_files=[],
        codex_workspace=str(workspace),
        browser_model_preference="",
        subagent_runner="",
        subagent_model="gpt-5.5",
        subagent_reasoning_effort="high",
        subagent_requested_model="gpt-5.5-high",
    )
    head = "9" * 40

    def fake_subprocess_run(command, **kwargs):  # noqa: ANN001, ANN003
        if command[0] == "codex":
            raw_path = Path(command[command.index("-o") + 1])
            raw_path.write_text(
                "VERDICT: PASS\n\nExisting proof artifact reads as READY and live.\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ["git", "-C", str(workspace)]:
            git_args = command[3:]
            if git_args == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, f"{head}\n", "")
            if git_args in (["status", "--short"], ["diff"]):
                return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(tau_roundtable_worker.subprocess, "run", fake_subprocess_run)

    result = tau_roundtable_worker._run_handler(args, {"goal": {"goal_hash": "sha256:test"}}, artifact_dir)

    assert result["exit_code"] == 0
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["ok"] is True
    assert receipt["response_chars"] > 0
    meta = json.loads((artifact_dir / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["workspace_changed"] is False
    response = (artifact_dir / "response.md").read_text(encoding="utf-8")
    assert "Existing proof artifact reads as READY and live." in response
    assert "(no workspace diff)" in response


def test_worker_lane_recovery_skips_interrupted_submit(tmp_path: Path, monkeypatch) -> None:
    """A cancelled browser submit must not spawn a long in-run extractor."""
    artifact_dir = tmp_path / "art"
    artifact_dir.mkdir()
    args = SimpleNamespace(
        handler="webgpt",
        node_id="handler-webgpt",
        surf_run=str(tmp_path / "surf.sh"),
        timeout=2400,
        stable_polls=2,
        no_activate=True,
        evidence=[],
    )
    (tmp_path / "surf.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (tmp_path / "surf.sh").chmod(0o755)

    def fail_if_called(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("interrupted lane recovery must not execute commands")

    monkeypatch.setattr(tau_roundtable_worker, "_run_cmd", fail_if_called)

    receipt = tau_roundtable_worker._attempt_lane_recovery(
        args,
        recovery_packet={
            "failure_code": tau_roundtable_worker.BROWSER_HANDLER_INTERRUPTED,
            "next_command": [str(tmp_path / "surf.sh"), "webgpt.extract"],
        },
        browser_oracle={"tab_id": "837389526"},
        submit_meta={
            "exit_code": 143,
            "sentinel": "<<<WEBGPT_DONE:test>>>",
            "submitted_to_chatgpt": True,
        },
        response_path=artifact_dir / "response.md",
        raw_path=artifact_dir / "response.raw.md",
        meta_path=artifact_dir / "response.meta.json",
        artifact_dir=artifact_dir,
        deadline=time.time() + 300,
    )

    assert receipt["recovered"] is False
    assert receipt["attempts"] == []
    assert "interrupted" in receipt["skipped_reason"]
