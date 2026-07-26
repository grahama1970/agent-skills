"""Tests for the Tau roundtable sanity eval runner."""

from __future__ import annotations

import importlib.util
import json
import sys
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
        "compile_sequential_all_handlers",
        "live_two_handler_smoke",
        "live_four_handler_sequential",
    }
    assert "plan-only" in result["what_remains_unverified"][0]


def test_worker_declares_webgrok_browser_submit_transport() -> None:
    assert tau_roundtable_worker.HANDLER_BACKENDS["webgrok"] == "webgrok"
    assert tau_roundtable_worker.HANDLER_SUBMIT_COMMANDS["webgrok"] == "grok.submit"


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
    assert "VERDICT: PASS" in prompt
    assert tau_roundtable_worker._extract_verdict("VERDICT: FAIL\nReason") == "FAIL"
    assert tau_roundtable_worker._has_verdict("No clear verdict") is False


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
        result = tau_roundtable_worker._run_handler(args, {}, artifact_dir)
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
        result = tau_roundtable_worker._run_handler(args, {}, artifact_dir)
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
        result = tau_roundtable_worker._run_handler(args, {}, artifact_dir)
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
        result = tau_roundtable_worker._run_handler(args, {}, artifact_dir)
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


def test_browser_failure_classifier_keeps_tab_url_mismatch_distinct() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
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


def test_browser_failure_classifier_ignores_failure_names_in_prompt() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
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
    assert tau_roundtable_worker._browser_submit_timeout("webkimi", 300) == 2190
    monkeypatch.setenv("SURF_LOCK_TIMEOUT_MS", "invalid")
    assert tau_roundtable_worker._browser_submit_timeout("webkimi", 300) == 450


def test_browser_failure_classifier_marks_unknown_tool_as_runtime_mismatch() -> None:
    failure_code = tau_roundtable_worker._classify_browser_failure(
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
