from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

import ask.tau_dag as tau_dag
import ask.tau_dag_cli as tau_dag_cli
from ask.tau_dag import (
    browser_compete_blocked_execution,
    compile_tau_dag_bundle,
    infer_compile_input,
    probe_browser_compete_handler_gate,
    resolve_scillm_model_route,
    run_tau_dag_bundle,
)


TAU_ROOT = Path("/home/graham/workspace/experiments/tau")
ASK_ROOT = Path(__file__).resolve().parents[1]
WORKER_SPEC = importlib.util.spec_from_file_location(
    "tau_roundtable_worker",
    ASK_ROOT / "scripts" / "tau_roundtable_worker.py",
)
assert WORKER_SPEC and WORKER_SPEC.loader
tau_roundtable_worker = importlib.util.module_from_spec(WORKER_SPEC)
sys.modules[WORKER_SPEC.name] = tau_roundtable_worker
WORKER_SPEC.loader.exec_module(tau_roundtable_worker)


def test_default_scillm_api_key_prefers_ambient_proxy_key_over_deployment_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / "scillm.env"
    env_file.write_text("SCILLM_MASTER_KEY=stale-deployment-key\n", encoding="utf-8")
    monkeypatch.setenv("SCILLM_ENV_FILE", str(env_file))
    monkeypatch.setenv("SCILLM_PROXY_KEY", "running-proxy-key")
    monkeypatch.setattr(tau_dag, "_running_scillm_proxy_key", lambda: None)
    for var in ("SCILLM_MASTER_KEY", "LITELLM_MASTER_KEY", "SCILLM_API_KEY", "SCILLM_PROXY_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    assert tau_dag.default_scillm_api_key() == "running-proxy-key"


def test_default_scillm_api_key_prefers_running_proxy_over_stale_deployment_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / "scillm.env"
    env_file.write_text("SCILLM_MASTER_KEY=stale-deployment-key\n", encoding="utf-8")
    monkeypatch.setenv("SCILLM_ENV_FILE", str(env_file))
    for var in (
        "SCILLM_PROXY_KEY",
        "SCILLM_MASTER_KEY",
        "LITELLM_MASTER_KEY",
        "SCILLM_API_KEY",
        "SCILLM_PROXY_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="SCILLM_MASTER_KEY=running-container-key\nLITELLM_MASTER_KEY=running-litellm-key\n",
            stderr="",
        )

    monkeypatch.setattr(tau_dag.subprocess, "run", fake_run)

    assert tau_dag.default_scillm_api_key() == "running-container-key"


def test_incomplete_tau_dag_request_routes_to_interview(tmp_path: Path) -> None:
    request = infer_compile_input(
        "ask 2 gpt 5.6 xhigh subagents to solve X concurrently",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "NEEDS_INTERVIEW"
    assert bundle["interview_skill"] == "$interview"
    assert {"repo", "target", "reviewer_model", "criteria"} <= set(bundle["missing_fields"])
    interview_path = Path(bundle["run_dir"]) / "interview-required.json"
    assert interview_path.is_file()


def test_complete_tau_dag_bundle_emits_strict_tau_contract(tmp_path: Path) -> None:
    request = infer_compile_input(
        "ask 2 gpt 5.6 xhigh subagents to solve X concurrently, then launch a claude fable subagent to review both solutions",
        repo="local/tau",
        target="issue-ask-tau-dag",
        criteria=["correctness", "maintainability"],
        output_root=tmp_path,
        local_fixture=True,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    assert bundle["final_dag_emitted_before_execution"] is True
    dag = bundle["dag"]
    assert dag["schema"] == "tau.dag_contract.v1"
    assert dag["provider_sensitive"] is True
    assert dag["requires_provider_route"] is True
    assert dag["context"]["execution_owner"] == "$tau"
    assert dag["context"]["provider_transport"] == "$scillm"
    assert dag["context"]["provider_route"] == "tau_local_scillm_adapter"
    assert [node["id"] for node in dag["nodes"]] == ["solver-1", "solver-2", "reviewer"]
    assert all(node["model_policy"]["execution_owner"] == "$tau" for node in dag["nodes"])
    assert all(node["model_policy"]["provider_transport"] == "$scillm" for node in dag["nodes"])
    assert all("prompt_contract" in node for node in dag["nodes"])
    solver_policy = dag["nodes"][0]["model_policy"]
    assert solver_policy["requested_model"] == "gpt-5.6-xhigh"
    assert solver_policy["model"] == "gpt-5.5"
    assert solver_policy["reasoning_effort"] == "xhigh"
    assert solver_policy["requested_reasoning_effort"] == "xhigh"
    assert "reasoning_downgrade_reason" not in solver_policy
    reviewer_policy = dag["nodes"][-1]["model_policy"]
    assert reviewer_policy["requested_model"] == "claude-fable"
    assert reviewer_policy["model"] == "claude-fable-5"
    assert Path(bundle["dag_path"]).is_file()
    assert Path(bundle["command_spec_root"], "solver-1", "tau-dispatch-command.json").is_file()

    validate = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(TAU_ROOT),
            "python",
            "-c",
            (
                "from pathlib import Path;"
                "from tau_coding.project_dag import load_dag_contract_payload, validate_dag_contract;"
                "validate_dag_contract(load_dag_contract_payload(Path(__import__('sys').argv[1])));"
                "print('ok')"
            ),
            str(bundle["dag_path"]),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert validate.returncode == 0, validate.stderr
    assert validate.stdout.strip() == "ok"


def test_roundtable_prompt_compiles_to_handler_neutral_tau_dag(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Roundtable webkimi, webclaude, webgpt, and webgemini concurrently, then join the answers.",
        repo="local/agent-skills",
        target="roundtable-web-handlers",
        immutable_goal="All handlers answer the same orchestration question and the join preserves dissent.",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    dag = bundle["dag"]
    assert dag["schema"] == "tau.dag_contract.v1"
    assert dag["context"]["execution_owner"] == "$tau"
    assert dag["context"]["transport_adapter"] == "handler_neutral_adapter"
    assert dag["context"]["roundtable_topology"] == "concurrent"
    assert dag["context"]["handlers"] == ["webkimi", "webclaude", "webgpt", "webgemini"]
    assert dag["goal"]["immutable_goal"] == request.immutable_goal
    assert dag["context"]["immutable_goal"] == request.immutable_goal
    assert dag["entry_node"] == "handler-webkimi"
    assert [node["id"] for node in dag["nodes"]] == [
        "handler-webkimi",
        "handler-webclaude",
        "handler-webgpt",
        "handler-webgemini",
        "join",
    ]
    assert {"from": "handler-webkimi", "to": "join"} in dag["edges"]
    assert {"from": "handler-webclaude", "to": "join"} in dag["edges"]
    assert {"from": "handler-webgpt", "to": "join"} in dag["edges"]
    assert {"from": "handler-webgemini", "to": "join"} in dag["edges"]
    assert dag["context"]["browser_transport_serialized"] is False
    assert dag["context"]["browser_transport_lock_queued"] is False
    assert dag["context"]["browser_transport_chain"] == [
        "handler-webkimi",
        "handler-webclaude",
        "handler-webgpt",
        "handler-webgemini",
    ]
    join = dag["nodes"][-1]
    assert "join" not in join
    assert join["context"]["join_semantics"]["requires_completed"] == [
        "handler-webkimi",
        "handler-webclaude",
        "handler-webgpt",
        "handler-webgemini",
    ]
    kimi = dag["nodes"][0]
    assert kimi["agent"] == "handler-webkimi"
    assert kimi["context"]["handler"] == "webkimi"
    assert kimi["context"]["prior_nodes"] == []
    assert kimi["context"]["scheduler_dependencies"] == []
    assert dag["nodes"][1]["context"]["prior_nodes"] == []
    assert dag["nodes"][1]["context"]["scheduler_dependencies"] == []
    assert dag["nodes"][1]["context"]["requires_prior_receipts"] is False
    assert kimi["context"]["immutable_goal"] == request.immutable_goal
    assert kimi["context"]["prompt_contract"]["immutable_goal"] == request.immutable_goal
    assert f"Immutable goal / acceptance bar: {request.immutable_goal}" in kimi["context"]["prompt_contract"]["user_template"]
    assert kimi["context"]["handler_policy"]["transport_owner"] == "$surf"
    assert kimi["context"]["handler_policy"]["transport"] == "kimi.submit"
    assert Path(bundle["command_spec_root"], "handler-webkimi", "tau-dispatch-command.json").is_file()
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-webkimi", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    assert command_spec["compile_only"] is False
    assert command_spec["requires_network"] is True
    assert "kimi.submit" not in command_spec["command"]
    assert "--browser-oracle-project" in command_spec["command"]

    validate = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(TAU_ROOT),
            "python",
            "-c",
            (
                "from pathlib import Path;"
                "from tau_coding.project_dag import load_dag_contract_payload, validate_dag_contract;"
                "validate_dag_contract(load_dag_contract_payload(Path(__import__('sys').argv[1])));"
                "print('ok')"
            ),
            str(bundle["dag_path"]),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert validate.returncode == 0, validate.stderr
    assert validate.stdout.strip() == "ok"


def test_dag_template_roundtable_defaults_to_concurrent_handler_dag(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Evaluate the implementation plan.",
        repo="local/agent-skills",
        target="template-roundtable",
        immutable_goal="All handlers review the same plan and preserve dissent.",
        handlers=["webgpt", "webclaude"],
        dag_template="roundtable",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    dag = bundle["dag"]
    assert request.dag_template == "roundtable"
    assert request.topology == "concurrent"
    assert request.workflow_mode == "roundtable"
    assert dag["context"]["dag_template"] == "roundtable"
    assert dag["context"]["roundtable_topology"] == "concurrent"
    assert dag["edges"] == [
        {"from": "handler-webgpt", "to": "join"},
        {"from": "handler-webclaude", "to": "join"},
        {"from": "join", "to": "human"},
    ]
    assert dag["nodes"][0]["context"]["dag_template"] == "roundtable"


def test_dag_template_creator_reviewer_defaults_to_sequential_receipt_chain(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Ask webgpt to do the work, then ask webclaude to review the work for pass/fail.",
        repo="local/agent-skills",
        target="template-creator-reviewer",
        immutable_goal="Creator produces the work and reviewer returns PASS, FAIL, or NEEDS_ATTENTION.",
        handlers=["webgpt", "webclaude"],
        dag_template="creator-reviewer",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    assert request.topology == "sequential"
    assert request.workflow_mode == "roundtable"
    dag = bundle["dag"]
    assert dag["context"]["dag_template"] == "creator-reviewer"
    assert dag["edges"] == [
        {"from": "handler-webgpt", "to": "handler-webclaude"},
        {"from": "handler-webclaude", "to": "join"},
        {"from": "join", "to": "human"},
    ]
    reviewer = next(node for node in dag["nodes"] if node["id"] == "handler-webclaude")
    assert reviewer["context"]["requires_prior_receipts"] is True
    assert reviewer["context"]["prompt_contract"]["requires_verdict"] is True


def test_dag_template_compete_sets_compete_mode_and_concurrent(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Compare implementation approaches.",
        repo="local/agent-skills",
        target="template-compete",
        immutable_goal="Choose a winner only from locally verifiable features.",
        handlers=["webgpt", "webclaude"],
        dag_template="bakeoff",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    assert request.dag_template == "compete"
    assert request.workflow_mode == "compete"
    assert request.topology == "concurrent"
    assert bundle["dag"]["context"]["dag_template"] == "compete"
    join = next(node for node in bundle["dag"]["nodes"] if node["id"] == "join")
    assert join["context"]["role"] == "compete_evaluator"


def test_dag_template_unknown_routes_to_interview_options(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Run the work.",
        repo="local/agent-skills",
        target="template-unknown",
        immutable_goal="Do not dispatch unknown templates.",
        handlers=["webgpt"],
        dag_template="mystery-template",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "NEEDS_INTERVIEW"
    assert "dag_template" in bundle["missing_fields"]
    question = next(item for item in bundle["questions"] if item["field"] == "dag_template")
    assert question["recovery_packet"]["failure_code"] == "unknown_dag_template"
    assert any(option["value"] == "roundtable" for option in question["options"])


def test_dag_template_tau_native_request_fails_closed_with_tau_ticket(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Review retrieved evidence.",
        repo="local/agent-skills",
        target="template-rag-review",
        immutable_goal="Do not fake retrieval gates.",
        handlers=["webgpt", "webclaude"],
        dag_template="rag",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "NEEDS_INTERVIEW"
    question = next(item for item in bundle["questions"] if item["field"] == "dag_template")
    assert question["recovery_packet"]["failure_code"] == "tau_native_template_required"
    assert question["recovery_packet"]["tau_ticket"] == "https://github.com/grahama1970/tau/issues/131"


def test_dag_template_missing_handlers_uses_interview_recovery_packet(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Evaluate the implementation plan.",
        repo="local/agent-skills",
        target="template-missing-handlers",
        immutable_goal="The selected template must not dispatch without handlers.",
        dag_template="roundtable",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "NEEDS_INTERVIEW"
    question = next(item for item in bundle["questions"] if item["field"] == "handlers")
    assert question["recovery_packet"]["failure_code"] == "template_missing_handlers"
    assert "webgpt" in question["options"]


def test_webgrok_handler_compiles_to_surf_grok_submit(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Ask webgrok to identify one browser orchestration risk.",
        repo="local/agent-skills",
        target="single-webgrok",
        output_root=tmp_path,
        immutable_goal="Return one browser orchestration risk with evidence.",
        handlers=("webgrok",),
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    node = bundle["dag"]["nodes"][0]
    assert node["context"]["handler"] == "webgrok"
    assert node["context"]["handler_policy"]["transport"] == "grok.submit"
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-webgrok", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    assert "--handler" in command_spec["command"]
    assert command_spec["command"][command_spec["command"].index("--handler") + 1] == "webgrok"


def test_webgpt_worker_rebinds_stale_tab_before_retry(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"request": "What is 2+2?"}) + "\n", encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgpt"
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
log = Path(__file__).with_suffix(".log")
log.write_text(log.read_text() + json.dumps(args) + "\\n" if log.exists() else json.dumps(args) + "\\n")
if args[:1] == ["tab.new"] or args[:1] == ["window.new"]:
    print(json.dumps({"success": True, "tabId": 456, "windowId": 900, "url": args[1]}))
    raise SystemExit(0)
if args[:1] == ["webgpt.submit"]:
    meta = Path(args[args.index("--meta-output") + 1])
    output = Path(args[args.index("--output") + 1])
    raw = Path(args[args.index("--raw-output") + 1])
    tab = args[args.index("--tab-id") + 1]
    if tab == "123":
        meta.write_text(json.dumps({"failure": "tab_identity_preflight_failed"}) + "\\n")
        print("tab_not_open_chatgpt", file=sys.stderr)
        raise SystemExit(1)
    output.write_text("2 + 2 = 4.\\n")
    raw.write_text("2 + 2 = 4.\\n")
    meta.write_text(json.dumps({
        "status": "completed",
        "response_proof_status": "response_proven",
        "controlled_tab_id": tab,
        "requested_tab_id": tab,
        "current_url": "https://chatgpt.com/c/stale",
    }) + "\\n")
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
if args[:1] == ["resolve"]:
    print(json.dumps({
        "backend": "webgpt",
        "project": "webgpt",
        "tab_id": "123",
        "conversation_url": "https://chatgpt.com/c/stale",
        "status": "ok",
    }))
    raise SystemExit(0)
if args[:1] == ["bind"]:
    print(json.dumps({
        "backend": "webgpt",
        "project": args[1],
        "tab_id": args[args.index("--tab-id") + 1],
        "conversation_url": args[args.index("--url") + 1],
        "state_path": "/tmp/webgpt.json",
        "status": "ok",
    }))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "handler-webgpt",
            "--handler",
            "webgpt",
            "--topology",
            "concurrent",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--surf-run",
            str(surf),
            "--browser-oracle-run",
            str(browser_oracle),
            "--timeout",
            "5",
            "--stable-polls",
            "1",
            "--no-activate",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["ok"] is True
    assert receipt["browser_oracle_binding_refresh"]["status"] == "updated"
    assert receipt["browser_oracle_binding_refresh"]["tab_id"] == "456"
    assert any(
        command.get("recovery_attempt") == "webgpt_stale_binding_open_url"
        for command in receipt["commands"]
    )
    assert any(
        command.get("recovery_attempt") == "webgpt_stale_binding_submit_after_new_tab_rebind"
        for command in receipt["commands"]
    )


def test_roundtable_handlers_can_be_explicit_and_sequential(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Roundtable the implementation plan.",
        repo="local/agent-skills",
        target="roundtable-sequential",
        immutable_goal="Produce a receipt-backed implementation plan review.",
        handlers=["webkimi", "webgemini"],
        topology="sequential",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    dag = bundle["dag"]
    assert dag["context"]["roundtable_topology"] == "sequential"
    assert dag["entry_node"] == "handler-webkimi"
    assert dag["edges"] == [
        {"from": "handler-webkimi", "to": "handler-webgemini"},
        {"from": "handler-webgemini", "to": "join"},
        {"from": "join", "to": "human"},
    ]
    join_spec = json.loads(
        Path(bundle["command_spec_root"], "join", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    assert "" not in join_spec["command"]
    assert "--browser-oracle-project" not in join_spec["command"]


def test_sequential_webgpt_webclaude_review_receives_prior_receipt_contract(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Ask webgpt to do the work, then ask webclaude to review the work for pass/fail.",
        repo="local/agent-skills",
        target="webgpt-webclaude-review",
        immutable_goal="WebGPT creates the requested work and WebClaude returns a pass/fail review.",
        handlers=["webgpt", "webclaude"],
        handler_projects=["webgpt=tau"],
        topology="sequential",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    dag = bundle["dag"]
    assert dag["edges"] == [
        {"from": "handler-webgpt", "to": "handler-webclaude"},
        {"from": "handler-webclaude", "to": "join"},
        {"from": "join", "to": "human"},
    ]
    claude = next(node for node in dag["nodes"] if node["id"] == "handler-webclaude")
    assert claude["depends_on"] == ["handler-webgpt"]
    assert claude["context"]["prior_nodes"] == ["handler-webgpt"]
    assert claude["context"]["requires_prior_receipts"] is True
    assert claude["context"]["requires_verdict"] is True
    assert claude["context"]["prompt_contract"]["requires_verdict"] is True
    assert claude["context"]["prompt_contract"]["verdict_schema"] == "PASS|FAIL|NEEDS_ATTENTION"
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-webclaude", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--prior-node") + 1] == "handler-webgpt"


def test_roundtable_api_model_handler_routes_to_scillm_adapter(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Ask a local API model and webclaude to review this sequentially.",
        repo="local/agent-skills",
        target="api-web-review",
        immutable_goal="API and browser handlers complete the sequential review with receipts.",
        handlers=["gpt-5.5", "webclaude"],
        topology="sequential",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    dag = bundle["dag"]
    assert dag["context"]["handlers"] == ["gpt-5.5", "webclaude"]
    assert dag["entry_node"] == "handler-gpt-5-5"
    api_node = next(node for node in dag["nodes"] if node["id"] == "handler-gpt-5-5")
    assert api_node["context"]["handler"] == "gpt-5.5"
    assert api_node["context"]["handler_policy"]["transport_owner"] == "$tau"
    assert api_node["context"]["handler_policy"]["transport"] == "scillm.chat"
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-gpt-5-5", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--handler") + 1] == "gpt-5.5"
    assert command[command.index("--next-agent") + 1] == "handler-webclaude"
    assert "--browser-oracle-project" not in command
    assert "--scillm-base-url" in command


def test_natural_chutes_exact_model_prompt_compiles_to_single_scillm_handler(tmp_path: Path) -> None:
    request = infer_compile_input(
        "chutes deepseek-ai/DeepSeek-V3.2-TEE: what is 2+2?",
        repo="local/ask",
        target="chutes-natural-ping",
        immutable_goal="The handler answers the arithmetic ping.",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    assert request.request == "what is 2+2?"
    assert request.handlers == ("deepseek-ai/DeepSeek-V3.2-TEE",)
    assert request.handler_provider_hints == ("chutes",)
    dag = bundle["dag"]
    assert dag["context"]["handlers"] == ["deepseek-ai/DeepSeek-V3.2-TEE"]
    node = dag["nodes"][0]
    assert node["context"]["provider_hint"] == "chutes"
    policy = node["context"]["handler_policy"]
    assert policy["transport_owner"] == "$tau"
    assert policy["transport"] == "scillm.chat"
    assert policy["provider_hint"] == "chutes"
    assert policy["model_policy"]["provider"] == "chutes"
    assert policy["model_policy"]["model"] == "deepseek-ai/DeepSeek-V3.2-TEE"
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-deepseek-ai-deepseek-v3-2-tee", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--handler") + 1] == "deepseek-ai/DeepSeek-V3.2-TEE"
    assert command[command.index("--provider-hint") + 1] == "chutes"


def test_chutes_prefixed_handler_is_canonicalized_before_scillm_dispatch(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Answer the ping.",
        repo="local/ask",
        target="chutes-prefixed-handler",
        immutable_goal="The handler answers the ping through the Chutes provider route.",
        handlers=["chutes/deepseek-ai/DeepSeek-V3.2-TEE"],
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    assert request.handlers == ("deepseek-ai/DeepSeek-V3.2-TEE",)
    assert request.handler_provider_hints == ("chutes",)
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-deepseek-ai-deepseek-v3-2-tee", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--handler") + 1] == "deepseek-ai/DeepSeek-V3.2-TEE"
    assert command[command.index("--provider-hint") + 1] == "chutes"


def test_xhigh_handler_compiles_to_tau_subagent_transport(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Ask gpt-5.5-xhigh to review this project-agent bundle.",
        repo="local/ask",
        target="subagent-handler-route",
        immutable_goal="The requested handler route is emitted as a Tau subagent node.",
        handlers=["gpt-5.5-xhigh"],
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    node = bundle["dag"]["nodes"][0]
    policy = node["context"]["handler_policy"]
    assert policy["transport_owner"] == "$tau"
    assert policy["transport"] == "subagent-runner.codex_exec"
    assert policy["runtime"] == "local_subagent"
    assert policy["model_policy"]["provider_transport"] == "$subagent-runner"
    assert policy["model_policy"]["requested_model"] == "gpt-5.5-xhigh"
    assert policy["model_policy"]["model"] == "gpt-5.5"
    assert policy["model_policy"]["reasoning_effort"] == "xhigh"
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-gpt-5-5-xhigh", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--handler") + 1] == "gpt-5.5-xhigh"
    assert command[command.index("--subagent-model") + 1] == "gpt-5.5"
    assert command[command.index("--subagent-reasoning-effort") + 1] == "xhigh"
    assert command[command.index("--subagent-requested-model") + 1] == "gpt-5.5-xhigh"
    assert command_spec["mutates"] is False
    assert command_spec["timeout_s"] == 1800


def test_supported_high_api_handler_still_compiles_to_scillm(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Ask gpt-5.5-high to answer the ping.",
        repo="local/ask",
        target="scillm-handler-route",
        immutable_goal="The SciLLM-compatible handler answers the ping.",
        handlers=["gpt-5.5-high"],
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-gpt-5-5-high", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--handler") + 1] == "gpt-5.5-high"
    assert "--codex-workspace" not in command


def test_high_handler_with_workspace_compiles_to_codex_exec_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "repair-worktree"
    workspace.mkdir()
    request = infer_compile_input(
        "Ask gpt-5.5-high to repair the scoped files.",
        repo="local/ask",
        target="workspace-handler-route",
        immutable_goal="The requested handler route can edit the bound repair worktree.",
        handlers=["gpt-5.5-high"],
        handler_workspaces=[f"gpt-5.5-high={workspace}"],
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-gpt-5-5-high", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--handler") + 1] == "gpt-5.5-high"
    assert command[command.index("--codex-workspace") + 1] == str(workspace)
    assert command[command.index("--subagent-model") + 1] == "gpt-5.5"
    assert command[command.index("--subagent-reasoning-effort") + 1] == "high"
    assert command[command.index("--subagent-requested-model") + 1] == "gpt-5.5-high"


def test_non_browser_handler_timeout_uses_explicit_execution_budget(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Ask gpt-5.5-high to draft, then claude-opus-5-medium reviews.",
        repo="local/ask",
        target="non-browser-timeout-budget",
        immutable_goal="Non-browser handler DAGs honor the requested execution budget.",
        handlers=["gpt-5.5-high", "claude-opus-5-medium"],
        topology="sequential",
        dag_template="creator-reviewer",
        output_root=tmp_path,
        execution_timeout_seconds=1800,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["dag"]["limits"]["default_timeout_seconds"] == 1800 + tau_dag.BROWSER_COMMAND_GRACE_SECONDS
    for node in ("handler-gpt-5-5-high", "handler-claude-opus-5-medium"):
        spec = json.loads(
            Path(bundle["command_spec_root"], node, "tau-dispatch-command.json").read_text(encoding="utf-8")
        )
        command = spec["command"]
        assert spec["timeout_s"] == 1800 + tau_dag.BROWSER_COMMAND_GRACE_SECONDS
        assert command[command.index("--timeout") + 1] == "1800"


def test_tau_dag_cli_passes_explicit_execution_timeout_to_compiler(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        tau_dag_cli.app,
        [
            "run",
            "Ask gpt-5.5-high to draft, then claude-opus-5-medium reviews.",
            "--repo",
            "local/ask",
            "--target",
            "non-browser-timeout-cli",
            "--immutable-goal",
            "Non-browser handler DAGs honor the requested execution budget.",
            "--handler",
            "gpt-5.5-high",
            "--handler",
            "claude-opus-5-medium",
            "--topology",
            "sequential",
            "--dag-template",
            "creator-reviewer",
            "--execution-timeout-seconds",
            "1800",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["bundle"]["dag"]["limits"]["default_timeout_seconds"] == 1800 + tau_dag.BROWSER_COMMAND_GRACE_SECONDS


def test_tau_worker_dispatches_xhigh_handler_through_subagent_runner(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"request": "What is 2+2?"}) + "\n", encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-gpt-5-5-xhigh"
    fake_runner = tmp_path / "subagent-runner"
    fake_runner.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

if sys.argv[1:2] != ["start"]:
    raise SystemExit(2)
spec = json.loads(Path(sys.argv[2]).read_text())
session = Path(spec["output_dir"]) / "session-1"
session.mkdir(parents=True, exist_ok=True)
(session / "status.json").write_text(json.dumps({
    "status": "completed",
    "status_reason": "fixture completed",
}) + "\\n")
(session / "result.json").write_text(json.dumps({
    "final_message": "2 + 2 = 4.",
    "final_message_status": "ok",
    "duration_seconds": 0.01,
}) + "\\n")
(session / "transcript.log").write_text("2 + 2 = 4.\\n")
print(json.dumps({"artifact_dir": str(session), "status": "starting"}))
raise SystemExit(0)
""",
        encoding="utf-8",
    )
    fake_runner.chmod(0o755)

    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "handler-gpt-5-5-xhigh",
            "--handler",
            "gpt-5.5-xhigh",
            "--topology",
            "concurrent",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--surf-run",
            "/bin/false",
            "--browser-oracle-run",
            "/bin/false",
            "--subagent-runner",
            str(fake_runner),
            "--subagent-model",
            "gpt-5.5",
            "--subagent-reasoning-effort",
            "xhigh",
            "--subagent-requested-model",
            "gpt-5.5-xhigh",
            "--timeout",
            "5",
            "--stable-polls",
            "1",
            "--no-activate",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["ok"] is True
    assert receipt["provider_receipt"]["provider_transport"] == "$subagent-runner"
    assert receipt["provider_receipt"]["transport"] == "subagent-runner.codex_exec"
    assert receipt["provider_receipt"]["model"] == "gpt-5.5"
    assert receipt["provider_receipt"]["requested_model"] == "gpt-5.5-xhigh"
    meta = json.loads((artifact_dir / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["transport"] == "subagent-runner.codex_exec"
    assert meta["reasoning_effort"] == "xhigh"


def test_tau_worker_dispatches_workspace_bound_gpt55_high_through_codex_exec(
    tmp_path: Path,
    monkeypatch,
) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"request": "Edit the workspace."}) + "\n", encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-gpt-5-5-high"
    workspace = tmp_path / "repair-worktree"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    (workspace / "README.md").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(workspace), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(workspace), "commit", "-q", "-m", "init"],
        check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
             "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com"},
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        """#!/usr/bin/env python3
import pathlib
import sys
args = sys.argv[1:]
out = pathlib.Path(args[args.index("-o") + 1])
(pathlib.Path.cwd() / "README.md").write_text("after\\n", encoding="utf-8")
out.write_text("changed README\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ.get('PATH', '')}")

    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "handler-gpt-5-5-high",
            "--handler",
            "gpt-5.5-high",
            "--topology",
            "sequential",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--surf-run",
            "/bin/false",
            "--browser-oracle-run",
            "/bin/false",
            "--subagent-model",
            "gpt-5.5",
            "--subagent-reasoning-effort",
            "high",
            "--subagent-requested-model",
            "gpt-5.5-high",
            "--codex-workspace",
            str(workspace),
            "--timeout",
            "5",
            "--stable-polls",
            "1",
            "--no-activate",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["provider_receipt"]["provider_transport"] == "$codex-cli"
    assert receipt["provider_receipt"]["transport"] == "codex.exec"
    assert receipt["provider_receipt"]["model"] == "gpt-5.5"
    assert receipt["provider_receipt"]["requested_model"] == "gpt-5.5-high"
    meta = json.loads((artifact_dir / "response.meta.json").read_text(encoding="utf-8"))
    assert meta["transport"] == "codex.exec"
    assert meta["workspace"] == str(workspace)
    assert "after" in subprocess.check_output(["git", "-C", str(workspace), "diff"], text=True)


def test_natural_mixed_concurrent_web_and_chutes_prompt_compiles_to_tau_dag(tmp_path: Path) -> None:
    request = infer_compile_input(
        "$ask concurrently webgpt, webclaude, webkimi and chutes deepseek-ai/DeepSeek-V3.2-TEE   What is  2+2?",
        repo="local/ask",
        target="mixed-web-chutes-concurrent",
        immutable_goal="All requested browser and API handlers answer 2+2 from identical context.",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    assert request.request == "What is  2+2?"
    assert request.topology == "concurrent"
    assert request.handlers == (
        "webgpt",
        "webclaude",
        "webkimi",
        "deepseek-ai/DeepSeek-V3.2-TEE",
    )
    assert request.handler_provider_hints == ("", "", "", "chutes")
    dag = bundle["dag"]
    assert dag["context"]["handlers"] == [
        "webgpt",
        "webclaude",
        "webkimi",
        "deepseek-ai/DeepSeek-V3.2-TEE",
    ]
    assert dag["edges"] == [
        {"from": "handler-webgpt", "to": "join"},
        {"from": "handler-webclaude", "to": "join"},
        {"from": "handler-webkimi", "to": "join"},
        {"from": "handler-deepseek-ai-deepseek-v3-2-tee", "to": "join"},
        {"from": "join", "to": "human"},
    ]
    chutes_node = next(node for node in dag["nodes"] if node["id"] == "handler-deepseek-ai-deepseek-v3-2-tee")
    assert chutes_node["context"]["provider_hint"] == "chutes"
    assert chutes_node["context"]["handler_policy"]["provider_hint"] == "chutes"
    assert chutes_node["context"]["handler_policy"]["model_policy"]["provider"] == "chutes"


def test_browser_command_specs_use_long_provider_timeout_envelope(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Roundtable webgpt, webclaude, webkimi, webgrok, and webgemini on timeout budgets.",
        repo="local/ask",
        target="browser-timeout-budgets",
        immutable_goal="Browser command specs enforce handler-specific timeout budgets.",
        handlers=["webgpt", "webclaude", "webkimi", "webgrok", "webgemini"],
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)
    specs = {}
    for node in ("handler-webgpt", "handler-webclaude", "handler-webkimi", "handler-webgrok", "handler-webgemini"):
        specs[node] = json.loads(
            Path(bundle["command_spec_root"], node, "tau-dispatch-command.json").read_text(encoding="utf-8")
        )

    assert specs["handler-webgpt"]["timeout_s"] == 4680
    assert specs["handler-webgemini"]["timeout_s"] == 4680
    assert specs["handler-webclaude"]["timeout_s"] == 4680
    assert specs["handler-webkimi"]["timeout_s"] == 4680
    assert specs["handler-webgrok"]["timeout_s"] == 4680
    for node in ("handler-webclaude", "handler-webkimi", "handler-webgrok", "handler-webgemini"):
        command = specs[node]["command"]
        # 900s was the LOW end of a normal browser-model call (webgpt Pro runs
        # 15-20 min), so it killed longer answers mid-generation. The envelope
        # now matches surf webgpt.submit's own 2400s default. Asserted via the
        # constant so the test tracks the policy instead of a stale literal.
        assert command[command.index("--timeout") + 1] == str(
            tau_dag.DEFAULT_BROWSER_WORKER_TIMEOUT_SECONDS
        )
        assert command[command.index("--browser-lock-timeout") + 1] == "3600"


def test_browser_command_specs_cap_executed_browser_workers_to_requested_budget(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Compete webgpt, webclaude, webkimi, webgrok, and webgemini on timeout budgets.",
        repo="local/ask",
        target="issue-1032-timeout-budgets",
        immutable_goal="Every browser worker is bounded by the requested execution budget.",
        handlers=["webgpt", "webclaude", "webkimi", "webgrok", "webgemini"],
        workflow_mode="compete",
        output_root=tmp_path,
        execution_timeout_seconds=900,
    )

    bundle = compile_tau_dag_bundle(request)

    for node in ("handler-webgpt", "handler-webclaude", "handler-webkimi", "handler-webgrok", "handler-webgemini"):
        spec = json.loads(
            Path(bundle["command_spec_root"], node, "tau-dispatch-command.json").read_text(encoding="utf-8")
        )
        command = spec["command"]
        assert spec["timeout_s"] == 900 + tau_dag.BROWSER_COMMAND_GRACE_SECONDS
        assert command[command.index("--timeout") + 1] == "900"
        assert command[command.index("--command-timeout-budget") + 1] == "900"


def test_browser_submit_timeout_budget_caps_nested_surf_watchdog(monkeypatch) -> None:
    monkeypatch.setenv("SURF_LOCK_TIMEOUT_MS", str(3600 * 1000))

    assert tau_roundtable_worker._browser_submit_timeout("webkimi", 900, command_timeout_budget=900) == 900
    assert tau_roundtable_worker._browser_submit_timeout("webgrok", 900, command_timeout_budget=900) == 900
    assert tau_roundtable_worker._browser_submit_timeout("webclaude", 900, command_timeout_budget=900) == 900
    assert tau_roundtable_worker._browser_submit_timeout("webgpt", 900, command_timeout_budget=900) == 900
    assert tau_roundtable_worker._browser_submit_timeout("webgemini", 900, command_timeout_budget=900) == 900


def test_compete_cli_execute_passes_poll_timeout_to_browser_worker_budget(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        tau_dag_cli,
        "_probe_browser_provider_availability",
        lambda *args, **kwargs: {
            "schema": "ask.browser_provider_availability.v1",
            "status": "AVAILABLE_PREFLIGHT",
            "mocked": False,
            "live": True,
            "read_only": True,
            "providers": {},
        },
    )
    monkeypatch.setattr(
        tau_dag_cli,
        "_provision_browser_lifecycle",
        lambda *args, **kwargs: {"schema": "ask.browser_tab_lifecycle.v1", "status": "skipped", "mode": "auto"},
    )
    monkeypatch.setattr(
        tau_dag_cli,
        "probe_browser_compete_handler_gate",
        lambda *args, **kwargs: {"schema": "ask.browser_compete_handler_gate.v1", "skipped": True},
    )

    def fake_run_tau_dag_bundle(bundle: dict[str, Any], **kwargs) -> dict[str, Any]:
        captured["bundle"] = bundle
        return {
            "schema": "ask.tau_dag_execution.v1",
            "status": "NEEDS_ATTENTION",
            "ok": False,
            "mocked": False,
            "live": True,
            "provider_live": False,
        }

    monkeypatch.setattr(tau_dag_cli, "run_tau_dag_bundle", fake_run_tau_dag_bundle)

    result = CliRunner().invoke(
        tau_dag_cli.app,
        [
            "compete",
            "Each candidate must answer PING_RESULT: 4.",
            "--repo",
            "local/agent-skills",
            "--target",
            "issue-1032-cli-budget",
            "--immutable-goal",
            "Every browser worker is bounded by the requested poll timeout.",
            "--handler",
            "webgpt",
            "--handler",
            "webclaude",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--execute",
            "--poll-timeout-seconds",
            "900",
            "--no-poll",
            "--json",
        ],
    )

    assert result.exit_code == 4
    bundle = captured["bundle"]
    for node in ("handler-webgpt", "handler-webclaude"):
        spec = json.loads(
            Path(bundle["command_spec_root"], node, "tau-dispatch-command.json").read_text(encoding="utf-8")
        )
        command = spec["command"]
        # Lane budgets come from per-handler envelopes, NOT --poll-timeout
        # (98b021d2e: deriving them from poll timeout starved browser lanes;
        # execution_timeout_seconds=0 means no --command-timeout-budget cap).
        # The worker envelope tracks the lock budget by design: a lane that may
        # wait out a full turn for the socket must outlive that wait, or it is
        # killed mid-submit. Raising the concurrent lock floor to the worker
        # timeout (2026-08-16) therefore lifts webclaude 3000 -> 3480. webgpt is
        # unchanged because its 3900 floor already exceeded the new envelope.
        expected = {"handler-webgpt": 3900, "handler-webclaude": 3480}[node]
        assert spec["timeout_s"] == expected
        assert "--command-timeout-budget" not in command


def test_browser_compete_gate_timeout_kills_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "gate-child-survived.txt"
    child_code = (
        "import pathlib, time; "
        "time.sleep(2); "
        f"pathlib.Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(10)"
    )

    result = tau_dag._run_gate_command([sys.executable, "-c", parent_code], cwd=tmp_path, timeout_seconds=1)

    assert result["returncode"] == 124
    assert result["timed_out"] is True
    assert "killed process group" in result["stderr"]
    time.sleep(2.5)
    assert not marker.exists()


def test_browser_lifecycle_timeout_kills_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "lifecycle-child-survived.txt"
    child_code = (
        "import pathlib, time; "
        "time.sleep(2); "
        f"pathlib.Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(10)"
    )

    result = tau_dag_cli._lifecycle_command([sys.executable, "-c", parent_code], cwd=tmp_path, timeout_seconds=1)

    assert result["returncode"] == 124
    assert result["timed_out"] is True
    assert "killed process group" in result["stderr"]
    time.sleep(2.5)
    assert not marker.exists()


def test_roundtable_handler_project_overrides_are_written_to_command_specs(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Roundtable webgpt and webkimi.",
        repo="local/agent-skills",
        target="roundtable-projects",
        immutable_goal="Both handlers receive the same project-binding check.",
        handler_projects=["webgpt=tau", "webkimi=webkimi"],
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    dag = bundle["dag"]
    assert dag["context"]["handler_projects"] == {"webgpt": "tau", "webkimi": "webkimi"}
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-webgpt", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--browser-oracle-project") + 1] == "tau"


def test_compete_mixed_handlers_compile_to_isolated_candidate_dag(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Compete webgpt, webclaude, and gpt-5.5-high on this focused implementation.",
        repo="local/agent-skills",
        target="ask-compete",
        immutable_goal="Select a winner only after locally checking reusable implementation features.",
        handlers=["webgpt", "webclaude", "gpt-5.5-high"],
        handler_projects=["webgpt=tau"],
        criteria=["skill-contract", "deterministic-proof"],
        topology="concurrent",
        workflow_mode="compete",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    dag = bundle["dag"]
    assert dag["schema"] == "tau.dag_contract.v1"
    assert dag["context"]["workflow_mode"] == "compete"
    assert dag["goal"]["immutable_goal"] == request.immutable_goal
    assert dag["context"]["immutable_goal"] == request.immutable_goal
    assert dag["context"]["transport_adapter"] == "handler_neutral_adapter"
    assert dag["context"]["handlers"] == ["webgpt", "webclaude", "gpt-5.5-high"]
    assert dag["edges"] == [
        {"from": "handler-webgpt", "to": "join"},
        {"from": "handler-webclaude", "to": "join"},
        {"from": "handler-gpt-5-5-high", "to": "join"},
        {"from": "join", "to": "human"},
    ]
    assert dag["context"]["browser_transport_serialized"] is False
    assert dag["context"]["browser_transport_lock_queued"] is False
    candidates = [node for node in dag["nodes"] if str(node["id"]).startswith("handler-")]
    assert candidates
    assert all(node["context"]["workflow_mode"] == "compete" for node in candidates)
    assert all(node["context"]["isolation_required"] is True for node in candidates)
    assert all(node["context"]["prompt_contract"]["isolation_required"] is True for node in candidates)
    assert all(node["context"]["prompt_contract"]["immutable_goal"] == request.immutable_goal for node in candidates)
    claude = next(node for node in candidates if node["id"] == "handler-webclaude")
    api = next(node for node in candidates if node["id"] == "handler-gpt-5-5-high")
    assert claude["depends_on"] == []
    assert claude["context"]["prior_nodes"] == []
    assert claude["context"]["requires_prior_receipts"] is False
    assert api["depends_on"] == []
    join = next(node for node in dag["nodes"] if node["id"] == "join")
    assert join["context"]["role"] == "compete_evaluator"
    assert "compete_scorecard" in join["required_evidence"]
    assert "winner_continuation_request" in join["required_evidence"]
    assert "join" not in join
    assert join["context"]["join_semantics"]["fail_closed_on_tie"] is True
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-webgpt", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--workflow-mode") + 1] == "compete"
    assert command[command.index("--browser-oracle-project") + 1] == "tau"
    claude_command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-webclaude", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    claude_command = claude_command_spec["command"]
    assert claude_command[claude_command.index("--browser-model-preference") + 1] == "Opus 5 High"


def test_compete_requires_two_concurrent_handlers(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Compete webgpt on this focused implementation.",
        repo="local/agent-skills",
        target="ask-compete",
        immutable_goal="One competitor cannot form a valid competition.",
        handlers=["webgpt"],
        topology="sequential",
        workflow_mode="compete",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "NEEDS_INTERVIEW"
    assert {"handlers", "topology"} <= set(bundle["missing_fields"])


def test_roundtable_requires_immutable_goal_preflight(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Roundtable webgpt and webclaude on this issue.",
        repo="local/agent-skills",
        target="roundtable-missing-goal",
        handlers=["webgpt", "webclaude"],
        topology="concurrent",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "NEEDS_INTERVIEW"
    assert "immutable_goal" in bundle["missing_fields"]
    assert not (Path(bundle["run_dir"]) / "dag.json").exists()


def test_compete_infers_labeled_acceptance_bar(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Acceptance bar: choose a winner only from locally verified features.\n\nCompete webgpt and webclaude on this focused patch.",
        repo="local/agent-skills",
        target="compete-labeled-goal",
        handlers=["webgpt", "webclaude"],
        topology="concurrent",
        workflow_mode="compete",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    assert request.immutable_goal == "choose a winner only from locally verified features."
    dag = bundle["dag"]
    assert dag["goal"]["immutable_goal"] == request.immutable_goal
    assert all(
        node["context"]["prompt_contract"]["immutable_goal"] == request.immutable_goal
        for node in dag["nodes"]
        if str(node["id"]).startswith("handler-")
    )


def test_all_browser_compete_gate_blocks_unavailable_surf_socket(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Compete webgpt, webclaude, webgrok, and webkimi on this focused patch.",
        repo="local/agent-skills",
        target="browser-compete-preflight",
        immutable_goal="Do not launch browser candidates unless browser transport is available.",
        handlers=["webgpt", "webclaude", "webgrok", "webkimi"],
        topology="concurrent",
        workflow_mode="compete",
        output_root=tmp_path,
    )
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import sys
if sys.argv[1:3] == ["tab.list", "--json"]:
    print("Error: Socket connect failed: Socket not found.", file=sys.stderr)
    print("Attempted socket: /tmp/surf.sock", file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text("#!/usr/bin/env python3\nraise SystemExit(2)\n", encoding="utf-8")
    browser_oracle.chmod(0o755)

    gate = probe_browser_compete_handler_gate(
        request,
        surf_run=surf,
        browser_oracle_run=browser_oracle,
        timeout_seconds=2,
    )
    execution = browser_compete_blocked_execution(gate)

    assert gate["status"] == "BLOCKED"
    assert gate["ok"] is False
    assert gate["blocked_handler_count"] == 4
    assert {check["failure_code"] for check in gate["handler_checks"]} == {"surf_transport_unavailable"}
    assert all(check["status"] == "BLOCKED" for check in gate["handler_checks"])
    assert execution["status"] == "BLOCKED"
    assert execution["no_tau_execution"] is True
    assert [node["status"] for node in execution["node_statuses"]] == ["BLOCKED"] * 5
    assert execution["node_statuses"][-1]["node_id"] == "join"
    assert execution["node_statuses"][-1]["failure_code"] == "candidate_preflight_failed"


def test_all_browser_compete_gate_blocks_missing_surf_entrypoint(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Compete webgpt and webclaude on this focused patch.",
        repo="local/agent-skills",
        target="browser-compete-missing-surf",
        immutable_goal="Do not launch Tau when the Surf entrypoint is missing.",
        handlers=["webgpt", "webclaude"],
        topology="concurrent",
        workflow_mode="compete",
        output_root=tmp_path,
    )

    gate = probe_browser_compete_handler_gate(
        request,
        surf_run=tmp_path / "missing-surf-run.sh",
        browser_oracle_run=tmp_path / "missing-browser-oracle-run.sh",
        timeout_seconds=1,
    )
    execution = browser_compete_blocked_execution(gate)

    assert gate["status"] == "BLOCKED"
    assert gate["ok"] is False
    assert gate["blocked_handler_count"] == 2
    assert {check["failure_code"] for check in gate["handler_checks"]} == {"surf_transport_unavailable"}
    assert all(check["command"]["returncode"] == 127 for check in gate["handler_checks"])
    assert execution["status"] == "BLOCKED"
    assert execution["no_tau_execution"] is True


def test_all_browser_compete_gate_accepts_top_level_tab_array(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Compete webgpt and webclaude on this focused patch.",
        repo="local/agent-skills",
        target="browser-compete-tab-array",
        immutable_goal="Launch only when both browser bindings resolve to live tabs.",
        handlers=["webgpt", "webclaude"],
        handler_projects=["webgpt=tau"],
        topology="concurrent",
        workflow_mode="compete",
        output_root=tmp_path,
    )
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
if sys.argv[1:3] == ["tab.list", "--json"]:
    print(json.dumps([
        {"id": 101, "url": "https://chatgpt.com/c/live", "title": "ChatGPT"},
        {"id": 202, "url": "https://claude.ai/chat/live", "title": "Claude"}
    ]))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys
args = sys.argv[1:]
if args[:1] == ["resolve"]:
    backend = args[args.index("--backend") + 1]
    if backend == "webgpt":
        print(json.dumps({"status": "ok", "backend": backend, "project": "tau", "tab_id": "101"}))
    elif backend == "webclaude":
        print(json.dumps({"status": "ok", "backend": backend, "project": "webclaude", "tab_id": "202"}))
    else:
        raise SystemExit(3)
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    gate = probe_browser_compete_handler_gate(
        request,
        surf_run=surf,
        browser_oracle_run=browser_oracle,
        timeout_seconds=2,
    )

    assert gate["status"] == "READY"
    assert gate["ok"] is True
    assert gate["blocked_handler_count"] == 0
    assert [check["live_tab"]["id"] for check in gate["handler_checks"]] == [101, 202]


def test_all_browser_compete_gate_accepts_json_after_tooling_chatter(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Compete webgpt and webclaude on this focused patch.",
        repo="local/agent-skills",
        target="browser-compete-contaminated-json",
        immutable_goal="Launch only when both browser bindings resolve to live tabs.",
        handlers=["webgpt", "webclaude"],
        handler_projects=["webgpt=tau"],
        topology="concurrent",
        workflow_mode="compete",
        output_root=tmp_path,
    )
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
if sys.argv[1:3] == ["tab.list", "--json"]:
    print("Building vendored surf-cli at /tmp/example...")
    print("added 317 packages, and audited 318 packages in 3s")
    print(json.dumps([
        {"id": 101, "url": "https://chatgpt.com/c/live", "title": "ChatGPT"},
        {"id": 202, "url": "https://claude.ai/chat/live", "title": "Claude"}
    ]))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys
args = sys.argv[1:]
if args[:1] == ["resolve"]:
    backend = args[args.index("--backend") + 1]
    print("Resolved 16 packages in 0.90ms")
    print("Audited 14 packages in 0.22ms")
    if backend == "webgpt":
        print(json.dumps({"status": "ok", "backend": backend, "project": "tau", "tab_id": "101"}))
    elif backend == "webclaude":
        print(json.dumps({"status": "ok", "backend": backend, "project": "webclaude", "tab_id": "202"}))
    else:
        raise SystemExit(3)
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    gate = probe_browser_compete_handler_gate(
        request,
        surf_run=surf,
        browser_oracle_run=browser_oracle,
        timeout_seconds=2,
    )

    assert gate["status"] == "READY"
    assert gate["ok"] is True
    assert gate["blocked_handler_count"] == 0
    assert [check["live_tab"]["id"] for check in gate["handler_checks"]] == [101, 202]


def test_all_browser_compete_gate_keeps_large_tab_list_before_matching_bindings(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Compete webgpt and webclaude on this focused patch.",
        repo="local/agent-skills",
        target="browser-compete-large-tab-list",
        immutable_goal="Do not lose live bindings when many unrelated Chrome tabs exist.",
        handlers=["webgpt", "webclaude"],
        handler_projects=["webgpt=tau"],
        topology="concurrent",
        workflow_mode="compete",
        output_root=tmp_path,
    )
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
if sys.argv[1:3] == ["tab.list", "--json"]:
    tabs = [
        {"id": index, "url": "https://example.com/" + ("x" * 220), "title": "unrelated"}
        for index in range(40)
    ]
    tabs.extend([
        {"id": 101, "url": "https://chatgpt.com/c/live", "title": "ChatGPT"},
        {"id": 202, "url": "https://claude.ai/chat/live", "title": "Claude"},
    ])
    print(json.dumps(tabs))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys
args = sys.argv[1:]
if args[:1] == ["resolve"]:
    backend = args[args.index("--backend") + 1]
    if backend == "webgpt":
        print(json.dumps({"status": "ok", "backend": backend, "project": "tau", "tab_id": "101"}))
    elif backend == "webclaude":
        print(json.dumps({"status": "ok", "backend": backend, "project": "webclaude", "tab_id": "202"}))
    else:
        raise SystemExit(3)
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    gate = probe_browser_compete_handler_gate(
        request,
        surf_run=surf,
        browser_oracle_run=browser_oracle,
        timeout_seconds=2,
    )

    assert gate["status"] == "READY"
    assert gate["ok"] is True
    assert gate["blocked_handler_count"] == 0
    assert [check["live_tab"]["id"] for check in gate["handler_checks"]] == [101, 202]


def test_compete_join_fails_closed_without_explicit_verified_features(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": "Implement the feature in isolation."}) + "\n",
        encoding="utf-8",
    )
    artifacts = tmp_path / "node-artifacts"
    for node_id, handler in (("handler-webgpt", "webgpt"), ("handler-webclaude", "webclaude")):
        node_dir = artifacts / node_id
        node_dir.mkdir(parents=True)
        response_path = node_dir / "response.md"
        response_path.write_text("## Position\nCandidate answer without explicit feature markers.\n", encoding="utf-8")
        (node_dir / "node-receipt.json").write_text(
            json.dumps(
                {
                    "schema": "ask.tau_dag_handler_receipt.v1",
                    "node_id": node_id,
                    "handler": handler,
                    "status": "PASS",
                    "ok": True,
                    "mocked": False,
                    "live": True,
                    "provider_live": True,
                    "response_path": str(response_path),
                }
            )
            + "\n",
            encoding="utf-8",
        )

    join_dir = artifacts / "join"
    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "join",
            "--handler",
            "join",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "compete",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(join_dir),
            "--surf-run",
            "/bin/false",
            "--browser-oracle-run",
            "/bin/false",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((join_dir / "node-receipt.json").read_text(encoding="utf-8"))
    scorecard = json.loads((join_dir / "compete-scorecard.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert scorecard["status"] == "NEEDS_ATTENTION"
    assert "no_clear_winner_from_receipts" in scorecard["blockers"]
    assert "no_explicit_verified_features_to_promote" in scorecard["blockers"]


def test_compete_browser_lane_error_records_needs_attention_without_failed_process(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": "Implement the feature in isolation."}) + "\n",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgpt"
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
if args[:1] == ["webgpt.submit"]:
    raw = Path(args[args.index("--raw-output") + 1])
    meta = Path(args[args.index("--meta-output") + 1])
    raw.write_text("browser_tab_read_timeout: no stable assistant response\\n")
    meta.write_text(json.dumps({
        "status": "failed",
        "failure": "browser_tab_read_timeout",
    }) + "\\n")
    print("browser_tab_read_timeout", file=sys.stderr)
    raise SystemExit(5)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
if args[:1] == ["resolve"]:
    print(json.dumps({
        "backend": "webgpt",
        "project": "webgpt",
        "tab_id": "837361011",
        "conversation_url": "https://chatgpt.com/c/compete-lane",
        "status": "ok",
    }))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "handler-webgpt",
            "--handler",
            "webgpt",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "compete",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--surf-run",
            str(surf),
            "--browser-oracle-run",
            str(browser_oracle),
            "--timeout",
            "5",
            "--stable-polls",
            "1",
            "--no-activate",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((artifact_dir / "browser-recovery-packet.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["ok"] is False
    assert receipt["competition_lane_exit_ok"] is True
    assert receipt["failure_code"] in {
        "browser_tab_read_timeout",
        "prompt_too_large_or_stalled",
    }
    assert receipt["recovery_packet_path"] == str(artifact_dir / "browser-recovery-packet.json")
    assert recovery["status"] == "NEEDS_ATTENTION"
    assert recovery["next_command"]


def test_webgpt_identity_failure_recovery_resubmits_with_expected_url(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": "Compete with a fresh WebGPT tab while many ChatGPT tabs are open."}) + "\n",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgpt"
    surf_log = tmp_path / "surf-commands.jsonl"
    surf = tmp_path / "surf"
    surf.write_text(
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
with Path({str(surf_log)!r}).open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(args) + "\\n")
if args[:1] == ["webgpt.submit"]:
    raw = Path(args[args.index("--raw-output") + 1])
    meta = Path(args[args.index("--meta-output") + 1])
    raw.write_text("")
    meta.write_text(json.dumps({{
        "status": "failed",
        "failure": "tab_identity_preflight_failed",
        "submitted_to_chatgpt": False,
        "requested_tab_id": "837362433",
        "requested_url": None,
        "tab_identity_preflight": {{
            "ok": False,
            "error": "unverified_tab_id_with_multiple_chatgpt_tabs",
            "expected_url": None,
            "tab": {{"id": "837362433", "url": "https://chatgpt.com/", "title": "ChatGPT"}},
            "chatgpt_tabs_count": 23,
        }},
    }}) + "\\n")
    print("unverified_tab_id_with_multiple_chatgpt_tabs", file=sys.stderr)
    raise SystemExit(2)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
if args[:1] == ["resolve"]:
    print(json.dumps({
        "backend": "webgpt",
        "project": "pdf-oxide-mvp-retry-20260727T1315Z-webgpt",
        "tab_id": "837362433",
        "conversation_url": "https://chatgpt.com/",
        "status": "ok",
    }))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "handler-webgpt",
            "--handler",
            "webgpt",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "compete",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--surf-run",
            str(surf),
            "--browser-oracle-run",
            str(browser_oracle),
            "--browser-oracle-project",
            "pdf-oxide-mvp-retry-20260727T1315Z-webgpt",
            "--timeout",
            "5",
            "--stable-polls",
            "1",
            "--no-activate",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    submitted = [json.loads(line) for line in surf_log.read_text(encoding="utf-8").splitlines()]
    webgpt_submit = next(item for item in submitted if item[:1] == ["webgpt.submit"])
    assert webgpt_submit[0] == "webgpt.submit"
    assert webgpt_submit[webgpt_submit.index("--tab-id") + 1] == "837362433"
    assert webgpt_submit[webgpt_submit.index("--expect-url") + 1] == "https://chatgpt.com/"

    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((artifact_dir / "browser-recovery-packet.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["failure_code"] == "browser_submit_not_accepted"
    assert recovery["failure_code"] == "browser_submit_not_accepted"
    assert recovery["next_command"][1] == "webgpt.submit"
    assert "open-bind" not in recovery["next_command"]
    assert recovery["next_command"][recovery["next_command"].index("--tab-id") + 1] == "837362433"
    assert recovery["next_command"][recovery["next_command"].index("--expect-url") + 1] == "https://chatgpt.com/"


def test_browser_lane_sanitizes_local_paths_and_attaches_bundle_before_submit(tmp_path: Path) -> None:
    evidence = tmp_path / "review-target.md"
    evidence.write_text("# Evidence\n\nThe answer should be 4.\n", encoding="utf-8")
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": f"Review this URL https://example.com/review and local evidence file: {evidence}"})
        + "\n",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgpt"
    surf = tmp_path / "surf"
    surf.write_text(
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
if args[:1] == ["webgpt.submit"]:
    input_path = Path(args[args.index("--input") + 1])
    prompt = input_path.read_text()
    if {str(evidence)!r} in prompt:
        print("bare local path reached browser prompt", file=sys.stderr)
        raise SystemExit(9)
    if "https://example.com/review" not in prompt:
        print("non-local URL was incorrectly sanitized", file=sys.stderr)
        raise SystemExit(7)
    attachments = [
        args[index + 1]
        for index, item in enumerate(args)
        if item == "--attach-file" and index + 1 < len(args)
    ]
    if {str(evidence.resolve())!r} not in attachments:
        print("missing local evidence attachment", file=sys.stderr)
        raise SystemExit(8)
    Path(args[args.index("--output") + 1]).write_text("## Position\\n2 + 2 = 4.\\n")
    Path(args[args.index("--raw-output") + 1]).write_text("## Position\\n2 + 2 = 4.\\n")
    Path(args[args.index("--meta-output") + 1]).write_text(json.dumps({{"status": "ok"}}) + "\\n")
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
if args[:1] == ["resolve"]:
    print(json.dumps({
        "backend": "webgpt",
        "project": "webgpt",
        "tab_id": "837361013",
        "conversation_url": "https://chatgpt.com/c/local-path-preflight",
        "status": "ok",
    }))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "handler-webgpt",
            "--handler",
            "webgpt",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "compete",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--surf-run",
            str(surf),
            "--browser-oracle-run",
            str(browser_oracle),
            "--timeout",
            "5",
            "--stable-polls",
            "1",
            "--no-activate",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    browser_prompt = Path(receipt["browser_prompt_path"])
    assert receipt["status"] == "PASS"
    assert str(evidence.resolve()) in receipt["browser_attachment_paths"]
    assert receipt["browser_local_path_preflight"]["local_path_count"] >= 1
    assert receipt["browser_local_path_preflight"]["attached_file_count"] == 1
    assert str(evidence) in Path(receipt["prompt_path"]).read_text(encoding="utf-8")
    assert str(evidence) not in browser_prompt.read_text(encoding="utf-8")


def test_browser_lane_attaches_readable_image_path_before_submit(tmp_path: Path) -> None:
    evidence = tmp_path / "page-overlay.webp"
    evidence.write_bytes(b"RIFF-test-webp")
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": f"Inspect the image at {evidence}."}) + "\n",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "node-artifacts" / "handler-webkimi"
    surf = tmp_path / "surf"
    surf.write_text(
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
if args[:1] == ["kimi.submit"]:
    attachment = args[args.index("--attach-file") + 1]
    if attachment != {str(evidence.resolve())!r}:
        print("missing image attachment", file=sys.stderr)
        raise SystemExit(8)
    Path(args[args.index("--output") + 1]).write_text("## Position\\nImage inspected.\\n")
    Path(args[args.index("--raw-output") + 1]).write_text("## Position\\nImage inspected.\\n")
    Path(args[args.index("--meta-output") + 1]).write_text(json.dumps({{"status": "ok"}}) + "\\n")
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys

if sys.argv[1:2] == ["resolve"]:
    print(json.dumps({
        "backend": "webkimi",
        "project": "webkimi",
        "tab_id": "837361015",
        "conversation_url": "https://www.kimi.ai/chat/image-proof",
        "status": "ok",
    }))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "handler-webkimi",
            "--handler",
            "webkimi",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "roundtable",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--surf-run",
            str(surf),
            "--browser-oracle-run",
            str(browser_oracle),
            "--timeout",
            "5",
            "--stable-polls",
            "1",
            "--no-activate",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["browser_attachment_paths"] == [str(evidence.resolve())]
    assert receipt["browser_local_path_preflight"]["attached_file_count"] == 1


def test_roundtable_browser_lane_error_records_needs_attention_without_failed_process(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": "Roundtable the browser handlers."}) + "\n",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "node-artifacts" / "handler-webclaude"
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
if args[:1] == ["tab.list"]:
    print(json.dumps([{"id": 837361234, "url": "https://claude.ai/new"}]))
    raise SystemExit(0)
if args[:1] == ["claude.submit"]:
    raw = Path(args[args.index("--raw-output") + 1])
    meta = Path(args[args.index("--meta-output") + 1])
    raw.write_text("")
    meta.write_text(json.dumps({
        "status": "failed",
        "failure": "browser_tab_read_timeout",
    }) + "\\n")
    print("browser_tab_read_timeout", file=sys.stderr)
    raise SystemExit(4)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
if args[:1] == ["resolve"]:
    print(json.dumps({
        "backend": "webclaude",
        "project": "webclaude",
        "tab_id": "837361234",
        "conversation_url": "https://claude.ai/new",
        "status": "ok",
    }))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "handler-webclaude",
            "--handler",
            "webclaude",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "roundtable",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--surf-run",
            str(surf),
            "--browser-oracle-run",
            str(browser_oracle),
            "--timeout",
            "5",
            "--stable-polls",
            "1",
            "--no-activate",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((artifact_dir / "browser-recovery-packet.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["ok"] is False
    assert receipt["competition_lane_exit_ok"] is True
    assert receipt["failure_code"] == "browser_tab_read_timeout"
    assert recovery["status"] == "NEEDS_ATTENTION"
    assert recovery["failure_code"] == "browser_tab_read_timeout"


def test_roundtable_browser_worker_timeout_emits_terminal_receipt(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": "Roundtable the browser handlers."}) + "\n",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "node-artifacts" / "handler-webclaude"
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
import time

args = sys.argv[1:]
if args[:1] == ["tab.list"]:
    print(json.dumps([{"id": 837361234, "url": "https://claude.ai/new"}]))
    raise SystemExit(0)
if args[:1] == ["claude.submit"]:
    time.sleep(10)
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
if args[:1] == ["resolve"]:
    print(json.dumps({
        "backend": "webclaude",
        "project": "webclaude",
        "tab_id": "837361234",
        "conversation_url": "https://claude.ai/new",
        "status": "ok",
    }))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    started = time.time()
    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "handler-webclaude",
            "--handler",
            "webclaude",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "roundtable",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--surf-run",
            str(surf),
            "--browser-oracle-run",
            str(browser_oracle),
            "--timeout",
            "1",
            "--stable-polls",
            "1",
            "--no-activate",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    elapsed = time.time() - started

    assert completed.returncode == 0, completed.stderr
    assert elapsed < 5
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((artifact_dir / "browser-recovery-packet.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["ok"] is False
    assert receipt["competition_lane_exit_ok"] is True
    assert receipt["failure_code"] == "browser_handler_timeout"
    assert receipt["commands"][-1]["returncode"] == 124
    assert recovery["failure_code"] == "browser_handler_timeout"
    assert recovery["auto_retry_blocked_reason"] == "browser_handler_timeout_expired"


def test_roundtable_scillm_auth_error_records_recovery_packet_without_failed_process(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": "Roundtable the API handlers."}) + "\n",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "node-artifacts" / "handler-gpt-5-5"

    class AuthFailureHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(401)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                b'{"error":{"message":"Invalid API key","type":"authentication_error","code":401}}'
            )

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), AuthFailureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
                "--node-id",
                "handler-gpt-5-5",
                "--handler",
                "gpt-5.5",
                "--topology",
                "concurrent",
                "--workflow-mode",
                "roundtable",
                "--request-file",
                str(request_path),
                "--artifact-dir",
                str(artifact_dir),
                "--surf-run",
                "/bin/false",
                "--browser-oracle-run",
                "/bin/false",
                "--scillm-base-url",
                base_url,
                "--scillm-api-key",
                "stale-default-key",
                "--timeout",
                "3",
            ],
            input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((artifact_dir / "handler-recovery-packet.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["ok"] is False
    assert receipt["competition_lane_exit_ok"] is True
    assert receipt["failure_code"] == "scillm_auth_invalid_api_key"
    assert receipt["recovery_packet_path"] == str(artifact_dir / "handler-recovery-packet.json")
    assert recovery["status"] == "NEEDS_ATTENTION"
    assert "SCILLM_PROXY_KEY=<configured proxy key>" in recovery["next_command"]
    assert "--handler gpt-5.5" in recovery["next_command"]
    assert "--execute --allow-provider-calls --json" in recovery["next_command"]


def test_roundtable_unknown_scillm_model_records_suggestions_in_recovery_packet(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "request": "Roundtable the API handlers.",
                "repo": "local/agent-skills",
                "target": "issue-1010-model-suggestions",
                "immutable_goal": "Invalid SciLLM model names produce actionable recovery packets.",
                "handlers": ["kimi-k2.6", "gpt-5.5"],
                "topology": "concurrent",
                "workflow_mode": "roundtable",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "node-artifacts" / "handler-kimi-k2-6"

    class UnknownModelHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.end_headers()
            payload = {
                "error": {
                    "message": (
                        "Unknown model 'kimi-k2.6'. Did you mean: oc-kimi? "
                        "Available: claude, gpt-5.5, oc-kimi, gemini-flash."
                    ),
                    "type": "invalid_request_error",
                    "code": 400,
                }
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), UnknownModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
                "--node-id",
                "handler-kimi-k2-6",
                "--handler",
                "kimi-k2.6",
                "--topology",
                "concurrent",
                "--workflow-mode",
                "roundtable",
                "--request-file",
                str(request_path),
                "--artifact-dir",
                str(artifact_dir),
                "--surf-run",
                "/bin/false",
                "--browser-oracle-run",
                "/bin/false",
                "--scillm-base-url",
                base_url,
                "--scillm-api-key",
                "sk-dev-proxy-123",
                "--timeout",
                "3",
            ],
            input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((artifact_dir / "handler-recovery-packet.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["competition_lane_exit_ok"] is True
    assert receipt["failure_code"] == "scillm_model_not_found"
    assert recovery["failure_code"] == "scillm_model_not_found"
    assert recovery["provider_diagnosis"]["http_status"] == 400
    assert recovery["provider_diagnosis"]["suggested_models"] == ["oc-kimi"]
    assert "oc-kimi" in recovery["provider_diagnosis"]["available_models_sample"]
    assert "--execute --allow-provider-calls --json" in recovery["next_command"]
    assert "available model id" in recovery["fallback_instruction"]


def test_roundtable_scillm_valid_api_key_message_classifies_as_auth_failure(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"request": "Roundtable the API handlers."}) + "\n", encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-gemini-flash"

    class ValidApiKeyHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.end_headers()
            payload = {
                "error": {
                    "message": (
                        "All groups exhausted for model='gemini-flash' "
                        "(chain=['gemini-flash','gemini-flash-free2']): Please pass a valid API key"
                    ),
                    "type": "router_error",
                    "code": 400,
                }
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), ValidApiKeyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
                "--node-id",
                "handler-gemini-flash",
                "--handler",
                "gemini-flash",
                "--topology",
                "concurrent",
                "--workflow-mode",
                "roundtable",
                "--request-file",
                str(request_path),
                "--artifact-dir",
                str(artifact_dir),
                "--surf-run",
                "/bin/false",
                "--browser-oracle-run",
                "/bin/false",
                "--scillm-base-url",
                base_url,
                "--scillm-api-key",
                "sk-dev-proxy-123",
                "--timeout",
                "3",
            ],
            input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((artifact_dir / "handler-recovery-packet.json").read_text(encoding="utf-8"))
    assert receipt["failure_code"] == "scillm_auth_invalid_api_key"
    assert recovery["failure_code"] == "scillm_auth_invalid_api_key"
    assert recovery["provider_diagnosis"]["http_status"] == 400
    assert recovery["provider_diagnosis"]["routed_model"] == "gemini-flash"
    assert recovery["provider_diagnosis"]["provider_chain"] == ["gemini-flash", "gemini-flash-free2"]
    assert recovery["auto_retry_blocked_reason"] == "auth_requires_configured_scillm_proxy_key"
    assert recovery["ticket_target"] == "$ask at agent-skills@main"
    assert "$ticket to $ask at agent-skills@main" in recovery["ticket_instruction"]


def test_roundtable_scillm_model_unsupported_401_classifies_as_model_route_failure(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"request": "Run the oc-deepseek repair lane."}) + "\n", encoding="utf-8")
    artifact_dir = tmp_path / "node-artifacts" / "handler-oc-deepseek"

    class UnsupportedModelHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(401)
            self.send_header("content-type", "application/json")
            self.end_headers()
            payload = {
                "error": {
                    "message": (
                        "All groups exhausted for model='oc-deepseek' "
                        "(chain=['opencode-go/deepseek-v4-flash']): Error code: 401 - "
                        "{'type': 'error', 'error': {'type': 'ModelError', "
                        "'message': 'Model  is not supported'}}"
                    ),
                    "type": "router_error",
                    "code": 401,
                }
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), UnsupportedModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
                "--node-id",
                "handler-oc-deepseek",
                "--handler",
                "oc-deepseek",
                "--topology",
                "concurrent",
                "--workflow-mode",
                "roundtable",
                "--request-file",
                str(request_path),
                "--artifact-dir",
                str(artifact_dir),
                "--surf-run",
                "/bin/false",
                "--browser-oracle-run",
                "/bin/false",
                "--scillm-base-url",
                base_url,
                "--scillm-api-key",
                "sk-dev-proxy-123",
                "--timeout",
                "3",
            ],
            input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((artifact_dir / "handler-recovery-packet.json").read_text(encoding="utf-8"))
    assert receipt["failure_code"] == "scillm_model_not_found"
    assert recovery["failure_code"] == "scillm_model_not_found"
    assert recovery["provider_diagnosis"]["http_status"] == 401
    assert recovery["provider_diagnosis"]["routed_model"] == "oc-deepseek"
    assert recovery["provider_diagnosis"]["provider_chain"] == ["opencode-go/deepseek-v4-flash"]
    assert recovery["auto_retry_blocked_reason"] == "provider_route_requires_model_or_provider_repair"
    assert "available model id" in recovery["fallback_instruction"]
    assert "SCILLM_PROXY_KEY=<configured proxy key>" not in recovery["next_command"]


def test_roundtable_join_emits_degraded_receipt_with_failed_seat_recovery_packet(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": "Roundtable the partial receipts."}) + "\n",
        encoding="utf-8",
    )
    artifacts = tmp_path / "node-artifacts"
    pass_dir = artifacts / "handler-webkimi"
    pass_dir.mkdir(parents=True)
    pass_response = pass_dir / "response.md"
    pass_response.write_text("## Position\nUsable WebKimi response.\n", encoding="utf-8")
    (pass_dir / "node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-webkimi",
                "handler": "webkimi",
                "status": "PASS",
                "ok": True,
                "mocked": False,
                "live": True,
                "provider_live": True,
                "response_path": str(pass_response),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    fail_dir = artifacts / "handler-gpt-5-5"
    fail_dir.mkdir(parents=True)
    fail_response = fail_dir / "response.md"
    fail_response.write_text("DO NOT IMPORT: failed lane prose.\n", encoding="utf-8")
    recovery_path = fail_dir / "handler-recovery-packet.json"
    recovery_path.write_text(
        json.dumps(
            {
                "schema": "ask.handler_failure_recovery_packet.v1",
                "status": "NEEDS_ATTENTION",
                "handler": "gpt-5.5",
                "node_id": "handler-gpt-5-5",
                "failure_code": "scillm_auth_invalid_api_key",
                "next_command": "export SCILLM_PROXY_KEY=<configured proxy key>; cd skills/ask && ./run.sh tau-dag ...",
                "ticket_target": "$ask at agent-skills@main",
                "ticket_instruction": "If this handler-recovery-packet is still blocking, file a $ticket to $ask at agent-skills@main.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (fail_dir / "node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-gpt-5-5",
                "handler": "gpt-5.5",
                "status": "NEEDS_ATTENTION",
                "ok": False,
                "mocked": False,
                "live": True,
                "provider_live": False,
                "response_path": str(fail_response),
                "failure": "scillm.chat failed HTTP 401: Invalid API key",
                "failure_code": "scillm_auth_invalid_api_key",
                "recovery_packet_path": str(recovery_path),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    join_dir = artifacts / "join"
    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "join",
            "--handler",
            "join",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "roundtable",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(join_dir),
            "--surf-run",
            "/bin/false",
            "--browser-oracle-run",
            "/bin/false",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((join_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "DEGRADED"
    assert receipt["ok"] is False
    assert receipt["usable_response_count"] == 1
    assert receipt["failed_seat_count"] == 1
    indexed = {item["handler"]: item for item in receipt["handler_response_index"]}
    assert indexed["webkimi"]["response_path"] == str(pass_response)
    assert indexed["gpt-5.5"]["failure_code"] == "scillm_auth_invalid_api_key"
    assert indexed["gpt-5.5"]["recovery_packet_path"] == str(recovery_path)
    assert receipt["unresolved_gaps"][0]["failure_code"] == "scillm_auth_invalid_api_key"
    analysis = receipt["degradation_analysis"]
    assert analysis["status"] == "DEGRADED"
    assert "1 of 2 handler seat(s) produced usable responses" in analysis["why"]
    assert analysis["failure_codes"] == {"scillm_auth_invalid_api_key": 1}
    assert analysis["failed_seats"][0]["next_command"].startswith("export SCILLM_PROXY_KEY")
    assert analysis["failed_seats"][0]["ticket_target"] == "$ask at agent-skills@main"
    assert "$ticket to $ask at agent-skills@main" in analysis["failed_seats"][0]["ticket_instruction"]
    summary = (join_dir / "roundtable-summary.md").read_text(encoding="utf-8")
    assert "## Degradation Analysis" in summary
    assert "scillm_auth_invalid_api_key" in summary
    assert "$ticket to $ask at agent-skills@main" in summary
    assert "DO NOT IMPORT" not in summary


def test_run_tau_dag_bundle_synthesizes_degraded_join_when_tau_skips_join(monkeypatch, tmp_path: Path) -> None:
    request = infer_compile_input(
        "Roundtable webkimi and gpt-5.5 about the partial failure.",
        repo="local/agent-skills",
        target="issue-1015-fixture",
        immutable_goal="Emit a degraded join when one terminal seat fails and another has a response.",
        handlers=["webkimi", "gpt-5.5"],
        output_root=tmp_path,
    )
    bundle = compile_tau_dag_bundle(request)
    run_dir = Path(bundle["run_dir"])
    artifacts = run_dir / "node-artifacts"
    pass_dir = artifacts / "handler-webkimi"
    pass_dir.mkdir(parents=True, exist_ok=True)
    pass_response = pass_dir / "response.md"
    pass_response.write_text("## Position\nFixture response from WebKimi.\n", encoding="utf-8")
    (pass_dir / "node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-webkimi",
                "handler": "webkimi",
                "status": "PASS",
                "ok": True,
                "mocked": False,
                "live": True,
                "provider_live": True,
                "response_path": str(pass_response),
                "provider_receipt": {"schema": "ask.tau_dag_provider_route_receipt.v1", "status": "PASS", "ok": True, "live": True, "provider_live": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fail_dir = artifacts / "handler-gpt-5-5"
    fail_dir.mkdir(parents=True, exist_ok=True)
    fail_response = fail_dir / "response.md"
    fail_response.write_text("", encoding="utf-8")
    recovery_path = fail_dir / "handler-recovery-packet.json"
    recovery_path.write_text(
        json.dumps({"schema": "ask.handler_failure_recovery_packet.v1", "failure_code": "scillm_auth_invalid_api_key", "next_command": "export SCILLM_PROXY_KEY=<configured proxy key>"})
        + "\n",
        encoding="utf-8",
    )
    (fail_dir / "node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-gpt-5-5",
                "handler": "gpt-5.5",
                "status": "NEEDS_ATTENTION",
                "ok": False,
                "mocked": False,
                "live": True,
                "provider_live": False,
                "response_path": str(fail_response),
                "failure": "scillm.chat failed HTTP 401: Invalid API key",
                "failure_code": "scillm_auth_invalid_api_key",
                "recovery_packet_path": str(recovery_path),
                "provider_receipt": {"schema": "ask.tau_dag_provider_route_receipt.v1", "status": "NEEDS_ATTENTION", "ok": False, "live": True, "provider_live": False},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    real_run_command = tau_dag._run_command

    def fake_run_command(command: list[str], *, cwd: Path) -> dict[str, object]:
        if "dag-run" in command:
            return {"returncode": 1, "stdout": "join skipped after upstream failure", "stderr": ""}
        return real_run_command(command, cwd=cwd)

    monkeypatch.setattr(tau_dag, "_run_command", fake_run_command)

    execution = run_tau_dag_bundle(bundle, tau_project_root=tmp_path, poll=False)

    join_path = run_dir / "node-artifacts" / "join" / "node-receipt.json"
    assert execution["status"] == "DEGRADED"
    assert execution["join_artifact_path"] == str(join_path)
    assert execution["degraded_join"]["status"] == "emitted"
    assert join_path.is_file()
    join = json.loads(join_path.read_text(encoding="utf-8"))
    assert join["status"] == "DEGRADED"
    failed = next(item for item in join["handler_response_index"] if item["handler"] == "gpt-5.5")
    assert failed["failure_code"] == "scillm_auth_invalid_api_key"
    assert failed["recovery_packet_path"] == str(recovery_path)
    assert join["degradation_analysis"]["failure_codes"] == {"scillm_auth_invalid_api_key": 1}


def test_run_tau_dag_bundle_synthesizes_missing_browser_timeout_receipt_and_join(
    monkeypatch, tmp_path: Path
) -> None:
    request = infer_compile_input(
        "Roundtable webgpt and webclaude about timeout recovery.",
        repo="local/agent-skills",
        target="issue-1027-fixture",
        immutable_goal="Emit a degraded join when a browser lane times out after submit artifacts but before a receipt.",
        handlers=["webgpt", "webclaude"],
        output_root=tmp_path,
    )
    bundle = compile_tau_dag_bundle(request)
    run_dir = Path(bundle["run_dir"])
    artifacts = run_dir / "node-artifacts"

    pass_dir = artifacts / "handler-webgpt"
    pass_dir.mkdir(parents=True, exist_ok=True)
    pass_response = pass_dir / "response.md"
    pass_response.write_text("## Position\nUsable WebGPT response.\n", encoding="utf-8")
    (pass_dir / "node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-webgpt",
                "handler": "webgpt",
                "status": "PASS",
                "ok": True,
                "mocked": False,
                "live": True,
                "provider_live": True,
                "response_path": str(pass_response),
                "provider_receipt": {"schema": "ask.tau_dag_provider_route_receipt.v1", "status": "PASS", "ok": True, "live": True, "provider_live": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    missing_dir = artifacts / "handler-webclaude"
    missing_dir.mkdir(parents=True, exist_ok=True)
    (missing_dir / "prompt.md").write_text("Prompt submitted to Claude.\n", encoding="utf-8")
    (missing_dir / "response.md.submitted.md").write_text("Prompt submitted to Claude.\n", encoding="utf-8")
    (missing_dir / "response.md").write_text("DO NOT IMPORT: unreceipted Claude prose.\n", encoding="utf-8")
    (missing_dir / "response.raw.md").write_text("raw Claude browser text\n", encoding="utf-8")
    (missing_dir / "response.meta.json").write_text(
        json.dumps({"status": "failed", "proof_status": "failed", "requested_tab_id": "837361234"}) + "\n",
        encoding="utf-8",
    )

    real_run_command = tau_dag._run_command

    def fake_run_command(command: list[str], *, cwd: Path) -> dict[str, object]:
        if "dag-run" in command:
            return {"returncode": 1, "stdout": "join skipped after missing browser receipt", "stderr": ""}
        return real_run_command(command, cwd=cwd)

    monkeypatch.setattr(tau_dag, "_run_command", fake_run_command)

    execution = run_tau_dag_bundle(bundle, tau_project_root=tmp_path, poll=False)

    synthesized_path = missing_dir / "node-receipt.json"
    join_path = artifacts / "join" / "node-receipt.json"
    assert execution["status"] == "DEGRADED"
    assert execution["degraded_join"]["status"] == "emitted"
    assert synthesized_path.is_file()
    synthesized = json.loads(synthesized_path.read_text(encoding="utf-8"))
    assert synthesized["status"] == "NEEDS_ATTENTION"
    assert synthesized["failure_code"] == "browser_handler_timeout"
    assert synthesized["synthesized_missing_receipt"] is True
    assert not (missing_dir / "response.md").exists()
    assert (missing_dir / "response.unverified.md").is_file()
    join = json.loads(join_path.read_text(encoding="utf-8"))
    assert join["status"] == "DEGRADED"
    failed = next(item for item in join["handler_response_index"] if item["handler"] == "webclaude")
    assert failed["failure_code"] == "browser_handler_timeout"
    summary = (artifacts / "join" / "roundtable-summary.md").read_text(encoding="utf-8")
    assert "DO NOT IMPORT" not in summary


def test_run_tau_dag_bundle_synthesizes_webgpt_recovery_from_orphaned_submit_artifacts(
    monkeypatch, tmp_path: Path
) -> None:
    request = infer_compile_input(
        "Ask webgpt for a tiny attached-bundle review.",
        repo="local/agent-skills",
        target="issue-1094-orphaned-webgpt",
        immutable_goal="WebGPT lane emits terminal artifacts when submit was accepted but no receipt was written.",
        handlers=["webgpt"],
        dag_template="single-call",
        output_root=tmp_path,
    )
    bundle = compile_tau_dag_bundle(request)
    run_dir = Path(bundle["run_dir"])
    artifacts = run_dir / "node-artifacts"
    node_dir = artifacts / "handler-webgpt"
    node_dir.mkdir(parents=True, exist_ok=True)
    (node_dir / "prompt.md").write_text("Prompt submitted to WebGPT.\n", encoding="utf-8")
    (node_dir / "response.md.submitted.md").write_text("Prompt submitted to WebGPT.\n", encoding="utf-8")
    sentinel = "<<<WEBGPT_DONE:20260729T121500Z:1094>>>>"
    (node_dir / "response.md.receipt.json").write_text(
        json.dumps(
            {
                "schema": "surf.webgpt_submit_receipt.v1",
                "status": "submitted_to_chatgpt",
                "submitted_to_chatgpt": True,
                "sentinel": sentinel,
                "requested_tab_id": "837363669",
                "output": str(node_dir / "response.md"),
                "raw_output": str(node_dir / "response.raw.md"),
                "meta_output": str(node_dir / "response.meta.json"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (node_dir / "webgpt_inflight.json").write_text(
        json.dumps(
            {
                "schema": "surf.webgpt_inflight.v1",
                "status": "submitted_to_chatgpt",
                "submitted_to_chatgpt": True,
                "sentinel": sentinel,
                "requested_tab_id": "837363669",
                "recovery_command": f"surf webgpt.recover --artifact-dir {node_dir} --finalize",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (node_dir / "webgpt_heartbeat.json").write_text(
        json.dumps(
            {
                "schema": "surf.webgpt_heartbeat.v1",
                "phase": "generating",
                "page_state": "waiting_for_sentinel",
                "next_expected_artifact": str(node_dir / "response.raw.md"),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    real_run_command = tau_dag._run_command

    def fake_run_command(command: list[str], *, cwd: Path) -> dict[str, object]:
        if "dag-run" in command:
            return {"returncode": 1, "stdout": "handler died before receipt", "stderr": ""}
        return real_run_command(command, cwd=cwd)

    monkeypatch.setattr(tau_dag, "_run_command", fake_run_command)

    execution = run_tau_dag_bundle(bundle, tau_project_root=tmp_path, poll=False)

    receipt = json.loads((node_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((node_dir / "browser-recovery-packet.json").read_text(encoding="utf-8"))
    assert execution["status"] == "NEEDS_ATTENTION"
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["synthesized_missing_receipt"] is True
    assert receipt["failure_code"] == "browser_handler_timeout"
    assert recovery["failure_code"] == "browser_handler_timeout"
    assert recovery["auto_retry_blocked_reason"] == "browser_submitted_no_response_proof_requires_recover"
    assert recovery["evidence"]["submit_receipt_path"] == str(node_dir / "response.md.receipt.json")
    assert recovery["evidence"]["inflight_path"] == str(node_dir / "webgpt_inflight.json")
    assert recovery["evidence"]["heartbeat_path"] == str(node_dir / "webgpt_heartbeat.json")
    assert recovery["evidence"]["inflight_submitted_to_chatgpt"] is True
    assert recovery["next_command"] == [
        "surf",
        "webgpt.recover",
        "--artifact-dir",
        str(node_dir),
        "--finalize",
    ]
    assert "$ticket to $ask at agent-skills@main" in recovery["ticket_instruction"]
    join = json.loads((artifacts / "join" / "node-receipt.json").read_text(encoding="utf-8"))
    assert join["status"] == "NEEDS_ATTENTION"
    failed = next(item for item in join["handler_response_index"] if item["handler"] == "webgpt")
    assert failed["recovery_packet_path"] == str(node_dir / "browser-recovery-packet.json")


def test_run_tau_dag_bundle_preserves_attachment_for_prepared_webgpt_orphan(
    monkeypatch, tmp_path: Path
) -> None:
    attached_bundle = tmp_path / "compact evidence bundle.zip"
    attached_bundle.write_text("bundle bytes", encoding="utf-8")
    request = infer_compile_input(
        "Ask webgpt for a tiny attached-bundle review.",
        repo="local/agent-skills",
        target="issue-1093-prepared-webgpt-attachment",
        immutable_goal="Prepared WebGPT prompt recovery preserves the original local attachment path.",
        handlers=["webgpt"],
        dag_template="single-call",
        output_root=tmp_path,
    )
    bundle = compile_tau_dag_bundle(request)
    run_dir = Path(bundle["run_dir"])
    spec_path = run_dir / "command-specs" / "handler-webgpt" / "tau-dispatch-command.json"
    command_spec = json.loads(spec_path.read_text(encoding="utf-8"))
    command_spec["command"].extend(["--attach-file", str(attached_bundle)])
    spec_path.write_text(json.dumps(command_spec, indent=2) + "\n", encoding="utf-8")

    artifacts = run_dir / "node-artifacts"
    node_dir = artifacts / "handler-webgpt"
    node_dir.mkdir(parents=True, exist_ok=True)
    (node_dir / "prompt.md").write_text("Prompt prepared for WebGPT.\n", encoding="utf-8")
    (node_dir / "response.md.submitted.md").write_text("Prompt prepared for WebGPT.\n", encoding="utf-8")
    sentinel = "<<<WEBGPT_DONE:20260729T131500Z:1093>>>>"
    (node_dir / "response.md.receipt.json").write_text(
        json.dumps(
            {
                "schema": "surf.webgpt_submit_receipt.v1",
                "status": "prepared_prompt",
                "submitted_to_chatgpt": False,
                "sentinel": sentinel,
                "requested_tab_id": "837363305",
                "output": str(node_dir / "response.md"),
                "raw_output": str(node_dir / "response.raw.md"),
                "meta_output": str(node_dir / "response.meta.json"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (node_dir / "webgpt_inflight.json").write_text(
        json.dumps(
            {
                "schema": "surf.webgpt_inflight.v1",
                "status": "prepared_prompt",
                "submitted_to_chatgpt": False,
                "sentinel": sentinel,
                "requested_tab_id": "837363305",
                "recovery_command": f"surf webgpt.recover --artifact-dir {node_dir} --finalize",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (node_dir / "webgpt_heartbeat.json").write_text(
        json.dumps(
            {
                "schema": "surf.webgpt_heartbeat.v1",
                "phase": "prompt_prepared",
                "page_state": "waiting_for_submit",
                "next_expected_artifact": str(node_dir / "response.raw.md"),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    real_run_command = tau_dag._run_command

    def fake_run_command(command: list[str], *, cwd: Path) -> dict[str, object]:
        if "dag-run" in command:
            return {"returncode": 1, "stdout": "worker exited after prompt preparation", "stderr": ""}
        return real_run_command(command, cwd=cwd)

    monkeypatch.setattr(tau_dag, "_run_command", fake_run_command)

    execution = run_tau_dag_bundle(bundle, tau_project_root=tmp_path, poll=False)

    receipt = json.loads((node_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((node_dir / "browser-recovery-packet.json").read_text(encoding="utf-8"))
    assert execution["status"] == "NEEDS_ATTENTION"
    assert receipt["failure_code"] == "browser_submit_not_accepted"
    assert recovery["failure_code"] == "browser_submit_not_accepted"
    assert recovery["auto_retry_blocked_reason"] == "browser_prepared_prompt_requires_attachment_preserving_resubmit"
    assert recovery["evidence"]["requested_attachment_paths"] == [str(attached_bundle)]
    assert recovery["requested_attachment_paths"] == [str(attached_bundle)]
    assert recovery["next_command"][1] == "webgpt.submit"
    assert "--attach-file" in recovery["next_command"]
    attach_index = recovery["next_command"].index("--attach-file")
    assert recovery["next_command"][attach_index + 1] == str(attached_bundle)
    assert "--tab-id" in recovery["next_command"]
    assert recovery["next_command"][recovery["next_command"].index("--tab-id") + 1] == "837363305"


def test_run_tau_dag_bundle_reclassifies_orphaned_webgpt_rate_limit_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    request = infer_compile_input(
        "Ask webgpt while ChatGPT is rate limited.",
        repo="local/agent-skills",
        target="issue-1094-rate-limited-webgpt",
        immutable_goal="WebGPT provider throttling is terminal lane-local evidence.",
        handlers=["webgpt"],
        dag_template="single-call",
        output_root=tmp_path,
    )
    bundle = compile_tau_dag_bundle(request)
    run_dir = Path(bundle["run_dir"])
    node_dir = run_dir / "node-artifacts" / "handler-webgpt"
    node_dir.mkdir(parents=True, exist_ok=True)
    (node_dir / "prompt.md").write_text("Prompt submitted to WebGPT.\n", encoding="utf-8")
    (node_dir / "response.md.submitted.md").write_text("Prompt submitted to WebGPT.\n", encoding="utf-8")
    (node_dir / "response.meta.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "proof_status": "rate_limited",
                "submitted_to_chatgpt": False,
                "chatgpt_too_many_requests_detected": True,
                "chatgpt_rate_limit": {"exhausted": True, "wait_seconds": 300},
                "blocker": "BLOCKED_WEBGPT_PROVIDER_RATE_LIMIT",
                "requested_tab_id": "837363698",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    real_run_command = tau_dag._run_command

    def fake_run_command(command: list[str], *, cwd: Path) -> dict[str, object]:
        if "dag-run" in command:
            return {"returncode": 1, "stdout": "provider throttle before receipt", "stderr": ""}
        return real_run_command(command, cwd=cwd)

    monkeypatch.setattr(tau_dag, "_run_command", fake_run_command)

    run_tau_dag_bundle(bundle, tau_project_root=tmp_path, poll=False)

    receipt = json.loads((node_dir / "node-receipt.json").read_text(encoding="utf-8"))
    recovery = json.loads((node_dir / "browser-recovery-packet.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["failure_code"] == "browser_provider_rate_limited"
    assert recovery["failure_code"] == "browser_provider_rate_limited"
    assert recovery["auto_retry_blocked_reason"] == "browser_provider_rate_limit_requires_backoff"
    assert recovery["evidence"]["provider_throttle"] is True
    assert recovery["fallback_instruction"].startswith("Treat only this browser lane as provider-rate-limited")


def test_run_tau_dag_bundle_synthesizes_compete_join_when_all_browser_lanes_need_attention(
    monkeypatch, tmp_path: Path
) -> None:
    request = infer_compile_input(
        "Compete webgpt and webkimi on a browser-readable evidence bundle.",
        repo="local/agent-skills",
        target="issue-1013-fixture",
        immutable_goal="Emit a compete scorecard even when every browser candidate needs attention.",
        handlers=["webgpt", "webkimi"],
        workflow_mode="compete",
        output_root=tmp_path,
    )
    bundle = compile_tau_dag_bundle(request)
    run_dir = Path(bundle["run_dir"])
    artifacts = run_dir / "node-artifacts"

    cases = [
        (
            "handler-webgpt",
            "webgpt",
            "repo_access_blocked",
            "skills/surf/run.sh webgpt.submit --input retry-with-local-bundle.md --attach-file evidence.zip",
        ),
        (
            "handler-webkimi",
            "webkimi",
            "browser_provider_rate_limited",
            "skills/surf/run.sh kimi.submit --input retry-with-local-bundle.md --attach-file evidence.zip",
        ),
    ]
    for node_id, handler, failure_code, next_command in cases:
        node_dir = artifacts / node_id
        node_dir.mkdir(parents=True, exist_ok=True)
        response_path = node_dir / "response.md"
        response_path.write_text("", encoding="utf-8")
        recovery_path = node_dir / "browser-recovery-packet.json"
        recovery_path.write_text(
            json.dumps(
                {
                    "schema": "ask.browser_failure_recovery_packet.v1",
                    "status": "NEEDS_ATTENTION",
                    "handler": handler,
                    "node_id": node_id,
                    "failure_code": failure_code,
                    "next_command": next_command,
                    "auto_retry_allowed": False,
                    "auto_retry_blocked_reason": "fixture_blocker",
                    "ticket_target": "$ask at agent-skills@main",
                    "ticket_instruction": "If this browser-recovery-packet is still blocking, file a $ticket to $ask at agent-skills@main.",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (node_dir / "node-receipt.json").write_text(
            json.dumps(
                {
                    "schema": "ask.tau_dag_handler_receipt.v1",
                    "node_id": node_id,
                    "handler": handler,
                    "status": "NEEDS_ATTENTION",
                    "ok": False,
                    "mocked": False,
                    "live": True,
                    "provider_live": False,
                    "response_path": str(response_path),
                    "failure": failure_code,
                    "failure_code": failure_code,
                    "recovery_packet_path": str(recovery_path),
                    "provider_receipt": {
                        "schema": "ask.tau_dag_provider_route_receipt.v1",
                        "status": "NEEDS_ATTENTION",
                        "ok": False,
                        "live": True,
                        "provider_live": False,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    real_run_command = tau_dag._run_command

    def fake_run_command(command: list[str], *, cwd: Path) -> dict[str, object]:
        if "dag-run" in command:
            return {"returncode": 1, "stdout": "join skipped after upstream failure", "stderr": ""}
        return real_run_command(command, cwd=cwd)

    monkeypatch.setattr(tau_dag, "_run_command", fake_run_command)

    execution = run_tau_dag_bundle(bundle, tau_project_root=tmp_path, poll=False)

    join_path = run_dir / "node-artifacts" / "join" / "node-receipt.json"
    scorecard_path = run_dir / "node-artifacts" / "join" / "compete-scorecard.json"
    assert execution["status"] == "NEEDS_ATTENTION"
    assert execution["join_artifact_path"] == str(join_path)
    assert execution["degraded_join"]["status"] == "emitted"
    assert execution["join_receipt"]["schema"] == "ask.tau_dag_compete_join_receipt.v1"
    assert join_path.is_file()
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    assert scorecard["status"] == "NEEDS_ATTENTION"
    assert len(scorecard["candidates"]) == 2
    assert all(candidate["ok"] is False for candidate in scorecard["candidates"])
    assert scorecard["degradation_analysis"]["candidate_count"] == 2
    assert scorecard["degradation_analysis"]["verified_feature_count"] == 0
    assert scorecard["degradation_analysis"]["failure_codes"] == {
        "browser_provider_rate_limited": 1,
        "repo_access_blocked": 1,
    }
    assert "competition_transport_blocked" in scorecard["blockers"]
    assert len(scorecard["degradation_analysis"]["recovery_commands"]) == 2


def test_execute_no_poll_forces_tau_stream_monitoring(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run_tau_dag_bundle(bundle, **kwargs):  # noqa: ANN001, ANN003
        captured["poll"] = kwargs.get("poll")
        return {
            "schema": "ask.tau_dag_execution.v1",
            "status": "PASS",
            "ok": True,
            "mocked": False,
            "live": True,
            "provider_live": False,
            "receipt_dir": str(tmp_path / "receipts"),
            "receipt_path": str(tmp_path / "receipts" / "dag-receipt.json"),
            "polls": [{"status": "PASS"}],
        }

    monkeypatch.setattr(tau_dag_cli, "run_tau_dag_bundle", fake_run_tau_dag_bundle)

    result = CliRunner().invoke(
        tau_dag_cli.app,
        [
            "run",
            "Ask gpt-5.5 for a short answer.",
            "--repo",
            "local/agent-skills",
            "--target",
            "stream-monitoring-policy",
            "--immutable-goal",
            "Executed Ask/Tau DAGs are monitored until terminal JSON status.",
            "--handler",
            "gpt-5.5",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--execute",
            "--no-poll",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    policy = payload["tau_stream_monitoring_policy"]
    assert captured["poll"] is True
    assert policy["status"] == "ENFORCED"
    assert policy["requested_poll"] is False
    assert policy["effective_poll"] is True
    assert policy["must_monitor_until_terminal"] is True


def test_tau_dag_cli_json_reports_degraded_join_path(monkeypatch, tmp_path: Path) -> None:
    join_path = tmp_path / "node-artifacts" / "join" / "node-receipt.json"
    join_path.parent.mkdir(parents=True)
    join_path.write_text("{}\n", encoding="utf-8")

    def fake_run_tau_dag_bundle(*args, **kwargs):
        return {
            "schema": "ask.tau_dag_execution.v1",
            "status": "DEGRADED",
            "ok": False,
            "mocked": False,
            "live": True,
            "provider_live": True,
            "join_artifact_path": str(join_path),
        }

    monkeypatch.setattr(
        tau_dag_cli,
        "_probe_browser_provider_availability",
        lambda *args, **kwargs: {
            "schema": "ask.browser_provider_availability.v1",
            "status": "AVAILABLE_PREFLIGHT",
            "mocked": False,
            "live": True,
            "read_only": True,
            "providers": {},
        },
    )
    monkeypatch.setattr(
        tau_dag_cli,
        "_provision_browser_lifecycle",
        lambda *args, **kwargs: {"schema": "ask.browser_tab_lifecycle.v1", "status": "skipped", "mode": "auto"},
    )
    monkeypatch.setattr(tau_dag_cli, "run_tau_dag_bundle", fake_run_tau_dag_bundle)
    result = CliRunner().invoke(
        tau_dag_cli.app,
        [
            "run",
            "Roundtable webkimi and gpt-5.5.",
            "--repo",
            "local/agent-skills",
            "--target",
            "issue-1015-cli",
            "--immutable-goal",
            "Report degraded join path.",
            "--handler",
            "webkimi",
            "--handler",
            "gpt-5.5",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--execute",
            "--no-poll",
            "--json",
        ],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["status"] == "DEGRADED"
    assert payload["join_artifact_path"] == str(join_path)


def test_browser_tab_lifecycle_auto_creates_one_owned_window_and_provider_tabs(tmp_path: Path) -> None:
    log_path = tmp_path / "commands.jsonl"
    tab_counter = tmp_path / "tab-counter.txt"
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

log = Path(sys.argv[0]).with_name("commands.jsonl")
counter = Path(sys.argv[0]).with_name("tab-counter.txt")
args = sys.argv[1:]
with log.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(args) + "\\n")
if args[:1] == ["window.new"]:
    value = int(counter.read_text(encoding="utf-8").strip() or "100") + 1 if counter.exists() else 101
    counter.write_text(str(value), encoding="utf-8")
    print(json.dumps({"id": 800 + value, "tabs": [{"id": value, "windowId": 800 + value, "url": args[1]}]}))
elif args[:1] == ["tab.new"]:
    value = int(counter.read_text(encoding="utf-8").strip() or "101") + 1 if counter.exists() else 102
    counter.write_text(str(value), encoding="utf-8")
    print(json.dumps({"id": value, "windowId": int(args[args.index("--window-id") + 1]) if "--window-id" in args else None}))
else:
    print(json.dumps({"ok": True}))
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

log = Path(sys.argv[0]).with_name("commands.jsonl")
with log.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({"ok": True, "args": sys.argv[1:]}))
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)
    request = infer_compile_input(
        "Roundtable webgpt, webclaude, and webkimi.",
        repo="local/agent-skills",
        target="fresh-browser-lifecycle",
        immutable_goal="Each browser handler gets an owned fresh tab.",
        handlers=["webgpt", "webclaude", "webkimi"],
        output_root=tmp_path / "runs",
        ask_id="fresh-browser-lifecycle",
    )
    bundle = compile_tau_dag_bundle(request)

    lifecycle = tau_dag_cli._provision_browser_lifecycle(
        request,
        mode="auto",
        run_dir=Path(str(bundle["run_dir"])),
        surf_run=surf,
        browser_oracle_run=browser_oracle,
    )

    assert lifecycle["status"] == "READY"
    assert lifecycle["mode"] == "fresh-temporary"
    # One unfocused window per seat: a tab that is not the selected tab of its
    # window reports document.hidden, and providers defer DOM updates while
    # hidden, so seats must not share a window.
    assert [tab["handler"] for tab in lifecycle["created_tabs"]] == ["webgpt", "webclaude", "webkimi"]
    assert [tab["tab_id"] for tab in lifecycle["created_tabs"]] == ["101", "102", "103"]
    seat_windows = [tab["window_id"] for tab in lifecycle["created_tabs"]]
    assert len(set(seat_windows)) == 3, f"each seat needs its own window, got {seat_windows}"
    assert lifecycle["handler_projects"] == [
        "webgpt=fresh-browser-lifecycle-webgpt",
        "webclaude=fresh-browser-lifecycle-webclaude",
        "webkimi=fresh-browser-lifecycle-webkimi",
    ]
    logged = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    # Seat windows are now snapshotted and placed on the reviewer desktop, so
    # window.new is no longer the first logged command; select it by name.
    window_new = [cmd for cmd in logged if cmd and cmd[0] == "window.new"]
    assert window_new[0] == [
        "window.new",
        "https://chatgpt.com/",
        "--json",
        "--unfocused",
        "--lock-timeout",
        "1800",
    ]
    assert [
        "window.new",
        "https://claude.ai/new",
        "--json",
        "--unfocused",
        "--lock-timeout",
        "1800",
    ] in logged
    assert [
        "window.new",
        "https://www.kimi.ai/",
        "--json",
        "--unfocused",
        "--lock-timeout",
        "1800",
    ] in logged
    assert sum(1 for c in logged if c[:1] == ["window.new"]) == 3
    assert not any(c[:1] == ["tab.new"] for c in logged), "seats must not share a window"
    assert ["bind", "fresh-browser-lifecycle-webgpt", "--backend", "webgpt", "--tab-id", "101", "--url", "https://chatgpt.com/", "--auto", "--json"] in logged
    assert ["bind", "fresh-browser-lifecycle-webclaude", "--backend", "webclaude", "--tab-id", "102", "--url", "https://claude.ai/new", "--auto", "--json"] in logged
    assert ["bind", "fresh-browser-lifecycle-webkimi", "--backend", "webkimi", "--tab-id", "103", "--url", "https://www.kimi.ai/", "--auto", "--json"] in logged
    assert (Path(str(bundle["run_dir"])) / "browser-tab-lifecycle.json").is_file()

    log_path.write_text("", encoding="utf-8")
    tab_counter.write_text("201", encoding="utf-8")
    capped_lifecycle = tau_dag_cli._provision_browser_lifecycle(
        request,
        mode="auto",
        run_dir=Path(str(bundle["run_dir"])),
        timeout_budget_seconds=900,
        surf_run=surf,
        browser_oracle_run=browser_oracle,
    )

    capped_logged = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    capped_window_new = [cmd for cmd in capped_logged if cmd and cmd[0] == "window.new"]
    assert capped_lifecycle["status"] == "READY"
    assert capped_lifecycle["lock_timeout_seconds"] == 900
    assert capped_lifecycle["command_timeout_seconds"] == 900 + tau_dag.BROWSER_COMMAND_GRACE_SECONDS
    assert capped_window_new[0] == [
        "window.new",
        "https://chatgpt.com/",
        "--json",
        "--unfocused",
        "--lock-timeout",
        "900",
    ]


def test_browser_tab_lifecycle_shared_mode_creates_one_window_with_provider_tabs(tmp_path: Path) -> None:
    log_path = tmp_path / "commands.jsonl"
    tab_counter = tmp_path / "tab-counter.txt"
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

log = Path(sys.argv[0]).with_name("commands.jsonl")
counter = Path(sys.argv[0]).with_name("tab-counter.txt")
args = sys.argv[1:]
with log.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(args) + "\\n")
if args[:1] == ["window.new"]:
    value = int(counter.read_text(encoding="utf-8").strip() or "100") + 1 if counter.exists() else 101
    counter.write_text(str(value), encoding="utf-8")
    print(json.dumps({"id": 900, "tabs": [{"id": value, "windowId": 900, "url": args[1]}]}))
elif args[:1] == ["tab.new"]:
    value = int(counter.read_text(encoding="utf-8").strip() or "101") + 1 if counter.exists() else 102
    counter.write_text(str(value), encoding="utf-8")
    print(json.dumps({"id": value}))
else:
    print(json.dumps({"ok": True}))
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

log = Path(sys.argv[0]).with_name("commands.jsonl")
with log.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({"ok": True, "args": sys.argv[1:]}))
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)
    request = infer_compile_input(
        "Roundtable webgpt, webclaude, and webkimi.",
        repo="local/agent-skills",
        target="shared-browser-lifecycle",
        immutable_goal="Browser review seats live in one self-contained window.",
        handlers=["webgpt", "webclaude", "webkimi"],
        output_root=tmp_path / "runs",
        ask_id="shared-browser-lifecycle",
    )
    bundle = compile_tau_dag_bundle(request)

    lifecycle = tau_dag_cli._provision_browser_lifecycle(
        request,
        mode="fresh-shared-keep",
        run_dir=Path(str(bundle["run_dir"])),
        surf_run=surf,
        browser_oracle_run=browser_oracle,
    )

    assert lifecycle["status"] == "READY"
    assert lifecycle["mode"] == "fresh-shared-keep"
    assert lifecycle["shared_window"] is True
    assert [tab["handler"] for tab in lifecycle["created_tabs"]] == ["webgpt", "webclaude", "webkimi"]
    assert [tab["tab_id"] for tab in lifecycle["created_tabs"]] == ["101", "102", "103"]
    assert {tab["window_id"] for tab in lifecycle["created_tabs"]} == {"900"}
    logged = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert sum(1 for c in logged if c[:1] == ["window.new"]) == 1
    assert [
        "window.new",
        "https://chatgpt.com/",
        "--json",
        "--unfocused",
        "--lock-timeout",
        "1800",
    ] in logged
    assert [
        "tab.new",
        "https://claude.ai/new",
        "--json",
        "--window-id",
        "900",
        "--background",
        "--lock-timeout",
        "1800",
    ] in logged
    assert [
        "tab.new",
        "https://www.kimi.ai/",
        "--json",
        "--window-id",
        "900",
        "--background",
        "--lock-timeout",
        "1800",
    ] in logged
    assert lifecycle["handler_projects"] == [
        "webgpt=shared-browser-lifecycle-webgpt",
        "webclaude=shared-browser-lifecycle-webclaude",
        "webkimi=shared-browser-lifecycle-webkimi",
    ]


def test_browser_tab_lifecycle_auto_skips_non_browser_dag(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Ask gpt-5.5-high to answer.",
        repo="local/agent-skills",
        target="api-only-lifecycle",
        immutable_goal="API-only handlers do not need browser tabs.",
        handlers=["gpt-5.5-high"],
        output_root=tmp_path / "runs",
        ask_id="api-only-lifecycle",
    )
    bundle = compile_tau_dag_bundle(request)

    lifecycle = tau_dag_cli._provision_browser_lifecycle(
        request,
        mode="auto",
        run_dir=Path(str(bundle["run_dir"])),
        surf_run=tmp_path / "missing-surf",
        browser_oracle_run=tmp_path / "missing-browser-oracle",
    )

    assert lifecycle == {
        "schema": "ask.browser_tab_lifecycle.v1",
        "status": "skipped",
        "mode": "reuse-bound",
        "seam_validation": {"kind": "ask.browser_tab_lifecycle.v1", "status": "PASS"},
    }


def test_browser_tab_lifecycle_fresh_temporary_closes_only_owned_window(tmp_path: Path) -> None:
    log_path = tmp_path / "commands.jsonl"
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

log = Path(sys.argv[0]).with_name("commands.jsonl")
args = sys.argv[1:]
with log.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(args) + "\\n")
print(json.dumps({"ok": True}))
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    lifecycle = {
        "schema": "ask.browser_tab_lifecycle.v1",
        "status": "READY",
        "mode": "fresh-temporary",
        "run_dir": str(tmp_path / "run"),
        "window_id": "900",
        "created_tabs": [{"handler": "webgpt", "tab_id": "101", "url": "u"}, {"handler": "webclaude", "tab_id": "102", "url": "u"}],
        "surf_run": str(surf),
    }

    tau_dag_cli._cleanup_browser_lifecycle(lifecycle)
    tau_dag_cli._cleanup_browser_lifecycle(lifecycle)

    logged = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert logged == [["window.close", "900", "--lock-timeout", "900"]]
    assert lifecycle["cleanup_status"] == "attempted"
    assert (tmp_path / "run" / "browser-tab-lifecycle.json").is_file()


def test_browser_tab_lifecycle_keeps_window_for_recoverable_failed_lane(tmp_path: Path) -> None:
    log_path = tmp_path / "commands.jsonl"
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json, sys
from pathlib import Path
log = Path(sys.argv[0]).with_name("commands.jsonl")
with log.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({"ok": True}))
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    run_dir = tmp_path / "run"
    lane = run_dir / "node-artifacts" / "handler-webgpt"
    lane.mkdir(parents=True)
    (lane / "browser-recovery-packet.json").write_text(
        json.dumps({"failure_code": "browser_handler_timeout", "next_command": []}),
        encoding="utf-8",
    )
    lifecycle = {
        "schema": "ask.browser_tab_lifecycle.v1",
        "status": "READY",
        "mode": "fresh-temporary",
        "run_dir": str(run_dir),
        "window_id": "900",
        "created_tabs": [{"handler": "webgpt", "tab_id": "101", "url": "u"}],
        "surf_run": str(surf),
    }

    tau_dag_cli._cleanup_browser_lifecycle(lifecycle)

    assert not log_path.exists()
    assert lifecycle["cleanup_status"] == "skipped_pending_recovery"
    assert lifecycle["pending_recovery_lanes"][0]["lane"] == "handler-webgpt"
    receipt = json.loads((run_dir / "browser-tab-lifecycle.json").read_text(encoding="utf-8"))
    assert receipt["cleanup_status"] == "skipped_pending_recovery"


def test_browser_tab_lifecycle_extracts_surf_window_text_output() -> None:
    output = "Window 837362456 (tab 837362457)\nUse --window-id 837362456 to target this window"

    assert tau_dag_cli._extract_window_id(output) == "837362456"
    assert tau_dag_cli._extract_tab_id(output) == "837362457"


def test_browser_tab_lifecycle_failure_blocks_tau_execution(monkeypatch, tmp_path: Path) -> None:
    def fake_provision(*args, **kwargs):
        return {
            "schema": "ask.browser_tab_lifecycle.v1",
            "status": "BLOCKED",
            "mode": "fresh-temporary",
            "run_dir": str(tmp_path / "runs" / "blocked-lifecycle"),
            "failure_code": "browser_window_create_failed",
            "commands": [],
            "created_tabs": [],
        }

    def unexpected_tau_execution(*args, **kwargs):
        raise AssertionError("Tau execution should not start when fresh browser lifecycle is blocked")

    monkeypatch.setattr(
        tau_dag_cli,
        "_probe_browser_provider_availability",
        lambda *args, **kwargs: {
            "schema": "ask.browser_provider_availability.v1",
            "status": "AVAILABLE_PREFLIGHT",
            "mocked": False,
            "live": True,
            "read_only": True,
            "providers": {},
        },
    )
    monkeypatch.setattr(tau_dag_cli, "_provision_browser_lifecycle", fake_provision)
    monkeypatch.setattr(tau_dag_cli, "run_tau_dag_bundle", unexpected_tau_execution)

    result = CliRunner().invoke(
        tau_dag_cli.app,
        [
            "run",
            "Roundtable webgpt and webclaude.",
            "--repo",
            "local/agent-skills",
            "--target",
            "blocked-browser-lifecycle",
            "--immutable-goal",
            "Do not run Tau when fresh browser tabs cannot be created.",
            "--handler",
            "webgpt",
            "--handler",
            "webclaude",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--browser-tab-lifecycle",
            "fresh-temporary",
            "--execute",
            "--no-poll",
            "--json",
        ],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["execution"]["status"] == "BLOCKED"
    assert payload["execution"]["blocked_reason"] == "browser_tab_lifecycle_failed"
    assert payload["execution"]["no_tau_execution"] is True


def test_browser_availability_uses_bound_handler_project_tab(monkeypatch, tmp_path: Path) -> None:
    browser_oracle = tmp_path / "browser-oracle-run.py"
    browser_oracle.write_text(
        """#!/usr/bin/env python3
import json
import sys

assert sys.argv[1:6] == ["resolve", "--backend", "webgpt", "--project", "battle-1199-final-review-retry"]
print(json.dumps({"project": "battle-1199-final-review-retry", "tab_id": "837367444", "conversation_url": "https://chatgpt.com/c/current"}))
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)
    availability = tmp_path / "availability.py"
    availability.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

output = Path(sys.argv[sys.argv.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
payload = {
    "schema": "ask.browser_provider_availability.v1",
    "status": "AVAILABLE_PREFLIGHT",
    "mocked": False,
    "live": True,
    "read_only": True,
    "argv": sys.argv[1:],
    "providers": {"webgpt": {"provider_limited": False, "checked_tabs": [{"tab_id": "837367444"}]}},
}
output.write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASK_BROWSER_ORACLE_RUN", str(browser_oracle))
    monkeypatch.setenv("ASK_BROWSER_AVAILABILITY_SCRIPT", str(availability))

    input_payload = tau_dag.TauDagCompileInput(
        request="Ask WebGPT to review the Battle backend proof.",
        repo="local/agent-skills",
        target="battle-1199",
        immutable_goal="Use the explicitly bound WebGPT tab for backend review.",
        solver_models=(),
        reviewer_model="",
        criteria=(),
        handlers=("webgpt",),
        topology="concurrent",
        workflow_mode="roundtable",
        dag_template="single-call",
        handler_projects=("webgpt=battle-1199-final-review-retry",),
    )

    report = tau_dag_cli._probe_browser_provider_availability(
        input_payload,
        run_dir=tmp_path / "runs",
        timeout_seconds=20,
    )

    command = report["command_receipt"]["command"]
    assert report["status"] == "AVAILABLE_PREFLIGHT"
    assert report["binding_resolution"]["explicit_tab_args"] == ["webgpt=837367444"]
    assert "--tab-id" in command
    assert command[command.index("--tab-id") + 1] == "webgpt=837367444"
    assert report["providers"]["webgpt"]["provider_limited"] is False


def test_roundtable_browser_availability_rate_limit_continues_to_tau(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_availability(*args, **kwargs):
        return {
            "schema": "ask.browser_provider_availability.v1",
            "status": "NEEDS_ATTENTION",
            "mocked": False,
            "live": True,
            "read_only": True,
            "requested_providers": ["webgpt", "webclaude"],
            "providers": {
                "webgpt": {"provider_limited": True, "checked_tabs": [{"tab_id": "837362610"}]},
                "webclaude": {"provider_limited": False, "checked_tabs": []},
            },
            "path": str(tmp_path / "runs" / "browser-provider-availability.json"),
        }

    def fake_lifecycle(input_payload, *args, **kwargs):
        captured["lifecycle_started"] = True
        captured["lifecycle_handlers"] = list(input_payload.handlers)
        return {"schema": "ask.browser_tab_lifecycle.v1", "status": "skipped", "mode": "auto"}

    def fake_tau_execution(bundle: dict[str, Any], **kwargs):
        captured["bundle"] = bundle
        dag = json.loads(Path(bundle["dag_path"]).read_text(encoding="utf-8"))
        captured["dag_handlers"] = dag["context"]["handlers"]
        claude = next(node for node in dag["nodes"] if node["context"].get("handler") == "webclaude")
        captured["claude_model_preference"] = claude["context"]["handler_policy"].get("model_preference")
        return {
            "schema": "ask.tau_dag_execution.v1",
            "status": "PASS",
            "ok": True,
            "mocked": False,
            "live": True,
            "provider_live": True,
        }

    monkeypatch.setattr(tau_dag_cli, "_probe_browser_provider_availability", fake_availability)
    monkeypatch.setattr(tau_dag_cli, "_provision_browser_lifecycle", fake_lifecycle)
    monkeypatch.setattr(
        tau_dag_cli,
        "probe_browser_compete_handler_gate",
        lambda *args, **kwargs: {"schema": "ask.browser_compete_handler_gate.v1", "skipped": True},
    )
    monkeypatch.setattr(tau_dag_cli, "run_tau_dag_bundle", fake_tau_execution)

    result = CliRunner().invoke(
        tau_dag_cli.app,
        [
            "run",
            "Roundtable webgpt and webclaude.",
            "--repo",
            "local/agent-skills",
            "--target",
            "blocked-browser-availability",
            "--immutable-goal",
            "Do not submit browser prompts while a requested provider is rate limited.",
            "--handler",
            "webgpt",
            "--handler",
            "webclaude",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--execute",
            "--no-poll",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    # The run still continues to Tau with the remaining seats, but a panel that
    # lost a requested provider must report DEGRADED and name the lost seat -
    # a four-seat result must never read as a clean five-seat PASS.
    assert payload["status"] == "DEGRADED"
    assert payload["removed_seats"], "a dropped seat must be surfaced, not silent"
    assert payload["live"] is True
    assert captured["lifecycle_started"] is True
    assert captured["bundle"]["status"] == "READY"
    assert captured["lifecycle_handlers"] == ["webclaude", "webgemini"]
    assert captured["dag_handlers"] == ["webclaude", "webgemini"]
    assert captured["claude_model_preference"] == "Opus 5 High"
    assert payload["browser_provider_availability"]["status"] == "NEEDS_ATTENTION"
    assert payload["browser_provider_availability"]["limited_providers"] == ["webgpt"]
    assert payload["browser_provider_availability"]["cooldown_policy"]["status"] == "LANE_LOCAL_RETRY"
    assert payload["browser_provider_availability"]["cooldown_policy"]["retry_after_seconds"] == 300
    assert payload["browser_provider_availability"]["cooldown_policy"]["surf_env"] == {
        "SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS": "1",
        "SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS": "300",
    }
    selection = payload["browser_provider_selection"]
    assert selection["status"] == "ADJUSTED"
    assert selection["limited_providers"] == ["webgpt"]
    assert selection["removed_handlers"] == ["webgpt"]
    assert selection["fallback_handlers"] == ["webgemini"]
    assert selection["active_handlers"] == ["webclaude", "webgemini"]
    assert selection["cooldown_seconds"] == 600
    assert "skills/ticket/run.sh bug" in selection["ticket_command"]
    assert payload["execution"]["status"] == "PASS"
    assert "no_tau_execution" not in payload["execution"]


def test_single_fresh_webgpt_rate_limit_keeps_requested_seat(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_availability(*args, **kwargs):
        return {
            "schema": "ask.browser_provider_availability.v1",
            "status": "NEEDS_ATTENTION",
            "mocked": False,
            "live": True,
            "read_only": True,
            "requested_providers": ["webgpt"],
            "providers": {
                "webgpt": {"provider_limited": True, "checked_tabs": [{"tab_id": "old-tab"}]},
            },
        }

    def fake_lifecycle(input_payload, *args, **kwargs):
        captured["lifecycle_started"] = True
        captured["lifecycle_handlers"] = list(input_payload.handlers)
        return {
            "schema": "ask.browser_tab_lifecycle.v1",
            "status": "READY",
            "mode": "fresh-keep",
            "handler_projects": ["webgpt=fresh-webgpt-project"],
        }

    def fake_tau_execution(bundle: dict[str, Any], **kwargs):
        captured["bundle"] = bundle
        dag = json.loads(Path(bundle["dag_path"]).read_text(encoding="utf-8"))
        captured["dag_handlers"] = dag["context"]["handlers"]
        return {
            "schema": "ask.tau_dag_execution.v1",
            "status": "PASS",
            "ok": True,
            "mocked": False,
            "live": True,
            "provider_live": True,
        }

    monkeypatch.setattr(tau_dag_cli, "_probe_browser_provider_availability", fake_availability)
    monkeypatch.setattr(tau_dag_cli, "_provision_browser_lifecycle", fake_lifecycle)
    monkeypatch.setattr(tau_dag_cli, "run_tau_dag_bundle", fake_tau_execution)

    result = CliRunner().invoke(
        tau_dag_cli.app,
        [
            "run",
            "Ask WebGPT for a single fresh-tab review.",
            "--repo",
            "local/agent-skills",
            "--target",
            "single-fresh-webgpt",
            "--immutable-goal",
            "A fresh requested WebGPT seat is created even when stale ambient tabs show cooldown.",
            "--dag-template",
            "single-call",
            "--handler",
            "webgpt",
            "--browser-tab-lifecycle",
            "fresh-keep",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--execute",
            "--no-poll",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    selection = payload["browser_provider_selection"]
    assert selection["status"] == "READY"
    assert selection["limited_providers"] == ["webgpt"]
    assert selection["removed_handlers"] == []
    assert selection["fresh_lifecycle_kept_handlers"] == ["webgpt"]
    assert selection["active_handlers"] == ["webgpt"]
    assert captured["lifecycle_started"] is True
    assert captured["lifecycle_handlers"] == ["webgpt"]
    assert captured["dag_handlers"] == ["webgpt"]
    assert payload["execution"]["status"] == "PASS"


def test_single_reuse_bound_webgpt_rate_limit_blocks_before_dispatch(monkeypatch, tmp_path: Path) -> None:
    def fake_availability(*args, **kwargs):
        return {
            "schema": "ask.browser_provider_availability.v1",
            "status": "NEEDS_ATTENTION",
            "mocked": False,
            "live": True,
            "read_only": True,
            "requested_providers": ["webgpt"],
            "providers": {
                "webgpt": {"provider_limited": True, "checked_tabs": [{"tab_id": "bound-tab"}]},
            },
        }

    def unexpected_lifecycle(*args, **kwargs):
        raise AssertionError("reuse-bound rate-limited WebGPT should block before lifecycle provisioning")

    def unexpected_tau_execution(*args, **kwargs):
        raise AssertionError("reuse-bound rate-limited WebGPT should not dispatch Tau")

    monkeypatch.setattr(tau_dag_cli, "_probe_browser_provider_availability", fake_availability)
    monkeypatch.setattr(tau_dag_cli, "_provision_browser_lifecycle", unexpected_lifecycle)
    monkeypatch.setattr(tau_dag_cli, "run_tau_dag_bundle", unexpected_tau_execution)

    result = CliRunner().invoke(
        tau_dag_cli.app,
        [
            "run",
            "Ask WebGPT on the bound tab.",
            "--repo",
            "local/agent-skills",
            "--target",
            "single-bound-webgpt",
            "--immutable-goal",
            "A reused WebGPT tab with visible cooldown blocks before dispatch.",
            "--dag-template",
            "single-call",
            "--handler",
            "webgpt",
            "--browser-tab-lifecycle",
            "reuse-bound",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--execute",
            "--no-poll",
            "--json",
        ],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    selection = payload["browser_provider_selection"]
    assert selection["status"] == "BLOCKED"
    assert selection["removed_handlers"] == ["webgpt"]
    assert selection["fresh_lifecycle_kept_handlers"] == []
    assert payload["execution"]["blocked_reason"] == "browser_provider_selection_insufficient_participants"


def test_browser_availability_blocked_execution_preserves_surf_socket_recovery() -> None:
    report = {
        "schema": "ask.browser_provider_availability.v1",
        "status": "ERROR",
        "mocked": False,
        "live": True,
        "error": "surf_tab_list_failed",
        "failure_code": "surf_browser_connection_unavailable",
        "recovery_kind": "surf_extension_socket_missing",
        "human_action": "Open Chrome chrome://extensions and Load unpacked Surf.",
        "next_command": "cd skills/surf && ./run.sh tab.list --json",
        "ticket_instruction": "If reload fails, file a $ticket to $surf.",
        "providers": {},
    }

    execution = tau_dag_cli.browser_availability_blocked_execution(report)

    assert execution["status"] == "NEEDS_ATTENTION"
    assert execution["failure_code"] == "surf_browser_connection_unavailable"
    assert execution["recovery_kind"] == "surf_extension_socket_missing"
    assert execution["human_action"] == "Open Chrome chrome://extensions and Load unpacked Surf."
    assert execution["next_command"] == "cd skills/surf && ./run.sh tab.list --json"
    assert "not a provider cooldown" in execution["message"]
    assert execution["ticket_instruction"] == "If reload fails, file a $ticket to $surf."


def test_compete_browser_availability_rate_limit_continues_to_tau(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_availability(*args, **kwargs):
        return {
            "schema": "ask.browser_provider_availability.v1",
            "status": "NEEDS_ATTENTION",
            "mocked": False,
            "live": True,
            "read_only": True,
            "requested_providers": ["webgpt", "webkimi"],
            "providers": {
                "webgpt": {"provider_limited": True, "checked_tabs": [{"tab_id": "837362610"}]},
                "webkimi": {"provider_limited": False, "checked_tabs": []},
            },
        }

    def fake_lifecycle(input_payload, *args, **kwargs):
        captured["lifecycle_started"] = True
        captured["lifecycle_handlers"] = list(input_payload.handlers)
        return {"schema": "ask.browser_tab_lifecycle.v1", "status": "skipped", "mode": "auto"}

    def fake_tau_execution(bundle: dict[str, Any], **kwargs):
        captured["bundle"] = bundle
        dag = json.loads(Path(bundle["dag_path"]).read_text(encoding="utf-8"))
        captured["dag_handlers"] = dag["context"]["handlers"]
        claude = next(node for node in dag["nodes"] if node["context"].get("handler") == "webclaude")
        captured["claude_model_preference"] = claude["context"]["handler_policy"].get("model_preference")
        return {
            "schema": "ask.tau_dag_execution.v1",
            "status": "PASS",
            "ok": True,
            "mocked": False,
            "live": True,
            "provider_live": True,
        }

    monkeypatch.setattr(tau_dag_cli, "_probe_browser_provider_availability", fake_availability)
    monkeypatch.setattr(tau_dag_cli, "_provision_browser_lifecycle", fake_lifecycle)
    monkeypatch.setattr(
        tau_dag_cli,
        "probe_browser_compete_handler_gate",
        lambda *args, **kwargs: {"schema": "ask.browser_compete_handler_gate.v1", "skipped": True},
    )
    monkeypatch.setattr(tau_dag_cli, "run_tau_dag_bundle", fake_tau_execution)

    result = CliRunner().invoke(
        tau_dag_cli.app,
        [
            "compete",
            "Each candidate must answer PING_RESULT: 4.",
            "--repo",
            "local/agent-skills",
            "--target",
            "blocked-compete-browser-availability",
            "--immutable-goal",
            "Do not submit competition browser prompts while a requested provider is rate limited.",
            "--handler",
            "webgpt",
            "--handler",
            "webkimi",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--execute",
            "--no-poll",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "DEGRADED"
    assert payload["removed_seats"] == ["webgpt"]
    assert captured["lifecycle_started"] is True
    assert captured["bundle"]["status"] == "READY"
    assert captured["lifecycle_handlers"] == ["webkimi", "webclaude"]
    assert captured["dag_handlers"] == ["webkimi", "webclaude"]
    assert captured["claude_model_preference"] == "Opus 5 High"
    assert payload["browser_provider_availability"]["status"] == "NEEDS_ATTENTION"
    assert payload["browser_provider_availability"]["limited_providers"] == ["webgpt"]
    assert payload["browser_provider_availability"]["cooldown_policy"]["retry_after_seconds"] == 300
    selection = payload["browser_provider_selection"]
    assert selection["status"] == "ADJUSTED"
    assert selection["limited_providers"] == ["webgpt"]
    assert selection["active_handlers"] == ["webkimi", "webclaude"]
    assert selection["fallback_handlers"] == ["webclaude"]
    assert "skills/ticket/run.sh bug" in selection["ticket_command"]
    assert payload["execution"]["status"] == "PASS"
    assert "no_tau_execution" not in payload["execution"]


def test_browser_availability_blocks_when_not_enough_available_participants(monkeypatch, tmp_path: Path) -> None:
    def fake_availability(*args, **kwargs):
        return {
            "schema": "ask.browser_provider_availability.v1",
            "status": "NEEDS_ATTENTION",
            "mocked": False,
            "live": True,
            "read_only": True,
            "requested_providers": ["webgpt", "webkimi"],
            "providers": {
                "webgpt": {"provider_limited": True, "checked_tabs": [{"tab_id": "837362610"}]},
                "webkimi": {"provider_limited": True, "checked_tabs": [{"tab_id": "837362611"}]},
            },
        }

    def unexpected_lifecycle(*args, **kwargs):
        raise AssertionError("Browser lifecycle should not start without enough available participants")

    def unexpected_tau_execution(*args, **kwargs):
        raise AssertionError("Tau execution should not start without enough available participants")

    monkeypatch.setattr(tau_dag_cli, "_probe_browser_provider_availability", fake_availability)
    monkeypatch.setattr(tau_dag_cli, "_fallback_provider_order", lambda request: [])
    monkeypatch.setattr(tau_dag_cli, "_provision_browser_lifecycle", unexpected_lifecycle)
    monkeypatch.setattr(tau_dag_cli, "run_tau_dag_bundle", unexpected_tau_execution)

    result = CliRunner().invoke(
        tau_dag_cli.app,
        [
            "compete",
            "Each candidate must answer PING_RESULT: 4.",
            "--repo",
            "local/agent-skills",
            "--target",
            "blocked-compete-no-available-provider",
            "--immutable-goal",
            "Block only when no sufficient provider set remains.",
            "--handler",
            "webgpt",
            "--handler",
            "webkimi",
            "--run-output-root",
            str(tmp_path / "runs"),
            "--execute",
            "--no-poll",
            "--json",
        ],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["status"] == "NEEDS_ATTENTION"
    assert payload["browser_provider_selection"]["status"] == "BLOCKED"
    assert payload["execution"]["blocked_reason"] == "browser_provider_selection_insufficient_participants"
    assert payload["execution"]["limited_providers"] == ["webgpt", "webkimi"]
    assert payload["execution"]["no_tau_execution"] is True


def test_roundtable_webgrok_stale_binding_retries_existing_provider_tab_before_blocking(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": "Live browser-backed Grok smoke. Return PING_RESULT: 4."}) + "\n",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "node-artifacts" / "handler-webgrok"
    bind_log = tmp_path / "bind-log.jsonl"
    surf = tmp_path / "surf"
    surf.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
if args[:2] == ["tab.list", "--json"]:
    print(json.dumps([
        {"id": 111, "title": "Grok old", "url": "https://grok.com/", "active": False},
        {"id": 222, "title": "Grok current", "url": "https://grok.com/", "active": True},
    ]))
    raise SystemExit(0)
if args[:1] == ["grok.submit"]:
    tab_id = args[args.index("--tab-id") + 1]
    output = Path(args[args.index("--output") + 1])
    raw = Path(args[args.index("--raw-output") + 1])
    meta = Path(args[args.index("--meta-output") + 1])
    if tab_id == "111":
        raw.write_text("")
        meta.write_text(json.dumps({
            "status": "failed",
            "failure": "grok_auth_required",
            "blocker": "BLOCKED_GROK_AUTH_REQUIRED",
            "tab_identity_preflight": {
                "ok": True,
                "provider_ok": True,
                "expected_tab_id": "111",
                "live_url": "https://grok.com/",
            },
        }) + "\\n")
        print("Not authenticated - log in to x.com first", file=sys.stderr)
        raise SystemExit(1)
    if tab_id == "222":
        output.write_text("PING_RESULT: 4\\n")
        raw.write_text("PING_RESULT: 4\\n<<<GROK_DONE:TEST>>>\\n")
        meta.write_text(json.dumps({
            "status": "completed",
            "proof_status": "response_proven",
            "requested_tab_id": "222",
            "resolved_url": "https://grok.com/",
        }) + "\\n")
        raise SystemExit(0)
    raise SystemExit(9)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    surf.chmod(0o755)
    browser_oracle = tmp_path / "browser-oracle"
    browser_oracle.write_text(
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

args = sys.argv[1:]
if args[:1] == ["resolve"]:
    print(json.dumps({{
        "backend": "webgrok",
        "project": "webgrok-project",
        "tab_id": "111",
        "conversation_url": "https://grok.com/",
        "status": "ok",
    }}))
    raise SystemExit(0)
if args[:1] == ["bind"]:
    Path({str(bind_log)!r}).write_text(json.dumps({{
        "args": args,
    }}) + "\\n")
    print(json.dumps({{
        "name": args[1],
        "backend": "webgrok",
        "tab_id": args[args.index("--tab-id") + 1],
        "conversation_url": args[args.index("--url") + 1],
        "state_path": "/tmp/webgrok-project.json",
    }}))
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    browser_oracle.chmod(0o755)

    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "handler-webgrok",
            "--handler",
            "webgrok",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "roundtable",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(artifact_dir),
            "--surf-run",
            str(surf),
            "--browser-oracle-run",
            str(browser_oracle),
            "--timeout",
            "5",
            "--stable-polls",
            "1",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((artifact_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["ok"] is True
    assert receipt["browser_oracle"]["tab_id"] == "222"
    assert receipt["browser_oracle_binding_refresh"]["status"] == "updated"
    commands = receipt["commands"]
    assert any(item.get("recovery_attempt") == "webgrok_stale_binding_scan_live_tabs" for item in commands)
    assert any(
        item.get("recovery_attempt") == "webgrok_stale_binding_submit_existing_tab"
        and item.get("candidate_tab_id") == "222"
        for item in commands
    )
    bound = json.loads(bind_log.read_text(encoding="utf-8"))
    assert bound["args"][bound["args"].index("--tab-id") + 1] == "222"


def test_compete_join_preserves_partial_results_and_browser_recovery_packets(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps({"request": "Implement the feature in isolation."}) + "\n",
        encoding="utf-8",
    )
    artifacts = tmp_path / "node-artifacts"
    pass_dir = artifacts / "handler-webkimi"
    pass_dir.mkdir(parents=True)
    pass_response = pass_dir / "response.md"
    pass_response.write_text("WebKimi candidate response with useful prose but no local proof marker.\n", encoding="utf-8")
    (pass_dir / "node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-webkimi",
                "handler": "webkimi",
                "status": "PASS",
                "ok": True,
                "mocked": False,
                "live": True,
                "provider_live": True,
                "response_path": str(pass_response),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    blocked_cases = [
        (
            "handler-webgpt",
            "webgpt",
            "prompt_too_large_or_stalled",
            "skills/surf/run.sh webgpt.submit --input prompt.md --attach-file bundle.zip",
        ),
        (
            "handler-webclaude",
            "webclaude",
            "browser_tab_read_timeout",
            "skills/surf/run.sh claude.submit --input prompt.md",
        ),
    ]
    for node_id, handler, failure_code, next_command in blocked_cases:
        node_dir = artifacts / node_id
        node_dir.mkdir(parents=True)
        response_path = node_dir / "response.md"
        response_path.write_text("", encoding="utf-8")
        recovery_path = node_dir / "browser-recovery-packet.json"
        recovery_packet = {
            "schema": "ask.browser_failure_recovery_packet.v1",
            "status": "NEEDS_ATTENTION",
            "handler": handler,
            "node_id": node_id,
            "failure_code": failure_code,
            "next_command": next_command,
            "auto_retry_allowed": False,
            "auto_retry_blocked_reason": "fixture_blocker",
            "evidence": {"failure_excerpt": failure_code},
            "ticket_target": "$ask at agent-skills@main",
            "ticket_instruction": "If this browser-recovery-packet is still blocking, file a $ticket to $ask at agent-skills@main.",
        }
        recovery_path.write_text(json.dumps(recovery_packet) + "\n", encoding="utf-8")
        (node_dir / "node-receipt.json").write_text(
            json.dumps(
                {
                    "schema": "ask.tau_dag_handler_receipt.v1",
                    "node_id": node_id,
                    "handler": handler,
                    "status": "NEEDS_ATTENTION",
                    "ok": False,
                    "mocked": False,
                    "live": True,
                    "provider_live": False,
                    "response_path": str(response_path),
                    "failure": failure_code,
                    "failure_code": failure_code,
                    "recovery_packet_path": str(recovery_path),
                    "recovery_packet": recovery_packet,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    join_dir = artifacts / "join"
    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "join",
            "--handler",
            "join",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "compete",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(join_dir),
            "--surf-run",
            "/bin/false",
            "--browser-oracle-run",
            "/bin/false",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    scorecard = json.loads((join_dir / "compete-scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["status"] == "NEEDS_ATTENTION"
    assert scorecard["winner_handler"] == ""
    assert len(scorecard["candidates"]) == 3
    kimi = next(candidate for candidate in scorecard["candidates"] if candidate["handler"] == "webkimi")
    assert kimi["ok"] is True
    assert kimi["response_path"] == str(pass_response)
    blockers = {item["handler"]: item for item in scorecard["transport_blockers"]}
    assert blockers["webgpt"]["next_command"] == "skills/surf/run.sh webgpt.submit --input prompt.md --attach-file bundle.zip"
    assert blockers["webclaude"]["failure_code"] == "browser_tab_read_timeout"
    assert "competition_transport_degraded" in scorecard["blockers"]
    assert "competition_transport_blocked" not in scorecard["blockers"]
    assert "no_explicit_verified_features_to_promote" in scorecard["blockers"]
    analysis = scorecard["degradation_analysis"]
    assert analysis["status"] == "NEEDS_ATTENTION"
    assert "2 of 3 candidate lane(s) failed or need attention" in analysis["why"]
    assert analysis["failure_codes"] == {
        "browser_tab_read_timeout": 1,
        "prompt_too_large_or_stalled": 1,
    }
    assert {item["handler"] for item in analysis["failed_candidates"]} == {"webgpt", "webclaude"}
    assert all(item["ticket_target"] == "$ask at agent-skills@main" for item in analysis["failed_candidates"])
    assert all("$ticket to $ask at agent-skills@main" in item["ticket_instruction"] for item in analysis["failed_candidates"])
    assert any("webgpt.submit" in item["next_command"] for item in analysis["recovery_commands"])
    receipt = json.loads((join_dir / "node-receipt.json").read_text(encoding="utf-8"))
    assert receipt["degradation_analysis"]["transport_blocker_count"] == 2
    summary = (join_dir / "compete-summary.md").read_text(encoding="utf-8")
    assert "## Degradation Analysis" in summary
    assert "prompt_too_large_or_stalled" in summary
    assert "$ticket to $ask at agent-skills@main" in summary


def test_compete_join_selects_clear_winner_when_peer_transport_degraded(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"request": "Implement the feature."}) + "\n", encoding="utf-8")
    artifacts = tmp_path / "node-artifacts"

    pass_dir = artifacts / "handler-gpt-5-5"
    pass_dir.mkdir(parents=True)
    pass_response = pass_dir / "response.md"
    pass_response.write_text("RESULT: 4\nVERIFIED_FEATURE: deterministic arithmetic\n", encoding="utf-8")
    (pass_dir / "node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-gpt-5-5",
                "handler": "gpt-5.5",
                "status": "PASS",
                "ok": True,
                "mocked": False,
                "live": True,
                "provider_live": True,
                "response_path": str(pass_response),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    blocked_dir = artifacts / "handler-webkimi"
    blocked_dir.mkdir(parents=True)
    blocked_response = blocked_dir / "response.md"
    blocked_response.write_text("", encoding="utf-8")
    recovery = {
        "failure_code": "browser_provider_rate_limited",
        "next_command": "retry later",
        "auto_retry_blocked_reason": "browser_provider_rate_limit_requires_backoff",
        "evidence": {},
    }
    (blocked_dir / "node-receipt.json").write_text(
        json.dumps(
            {
                "schema": "ask.tau_dag_handler_receipt.v1",
                "node_id": "handler-webkimi",
                "handler": "webkimi",
                "status": "NEEDS_ATTENTION",
                "ok": False,
                "mocked": False,
                "live": True,
                "provider_live": False,
                "response_path": str(blocked_response),
                "failure_code": "browser_provider_rate_limited",
                "recovery_packet": recovery,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    join_dir = artifacts / "join"
    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "join",
            "--handler",
            "join",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "compete",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(join_dir),
            "--surf-run",
            "/bin/false",
            "--browser-oracle-run",
            "/bin/false",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    scorecard = json.loads((join_dir / "compete-scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["status"] == "NEEDS_ATTENTION"
    assert scorecard["ok"] is False
    assert scorecard["winner_handler"] == ""
    assert scorecard["winner_node_id"] == ""
    assert "competition_transport_degraded" in scorecard["blockers"]
    assert "competition_transport_blocked" not in scorecard["blockers"]
    assert scorecard["failure_kind"] == "transport"
    assert scorecard["provider_live"] is False
    assert scorecard["transport_blockers"][0]["handler"] == "webkimi"
    assert "selection failed closed" in scorecard["degradation_analysis"]["why"]
    summary = (join_dir / "compete-summary.md").read_text(encoding="utf-8")
    assert "- winner: `NEEDS_ATTENTION`" in summary
    assert "browser_provider_rate_limited" in summary


def test_compete_join_promotes_only_explicit_verified_features(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"request": "Implement the feature in isolation."}) + "\n", encoding="utf-8")
    artifacts = tmp_path / "node-artifacts"
    cases = [
        ("handler-webgpt", "webgpt", ["VERIFIED_FEATURE: keeps Ask as a Tau DAG compiler"]),
        (
            "handler-webclaude",
            "webclaude",
            [
                "VERIFIED_FEATURE: keeps Ask as a Tau DAG compiler",
                "VERIFIED_FEATURE: emits a bounded winner revision request",
            ],
        ),
    ]
    for node_id, handler, lines in cases:
        node_dir = artifacts / node_id
        node_dir.mkdir(parents=True)
        response_path = node_dir / "response.md"
        response_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        (node_dir / "node-receipt.json").write_text(
            json.dumps(
                {
                    "schema": "ask.tau_dag_handler_receipt.v1",
                    "node_id": node_id,
                    "handler": handler,
                    "status": "PASS",
                    "ok": True,
                    "mocked": False,
                    "live": True,
                    "provider_live": True,
                    "response_path": str(response_path),
                }
            )
            + "\n",
            encoding="utf-8",
        )

    join_dir = artifacts / "join"
    completed = subprocess.run(
        [
            sys.executable,
            str(ASK_ROOT / "scripts" / "tau_roundtable_worker.py"),
            "--node-id",
            "join",
            "--handler",
            "join",
            "--topology",
            "concurrent",
            "--workflow-mode",
            "compete",
            "--request-file",
            str(request_path),
            "--artifact-dir",
            str(join_dir),
            "--surf-run",
            "/bin/false",
            "--browser-oracle-run",
            "/bin/false",
        ],
        input=json.dumps({"goal": {"goal_hash": "sha256:test"}}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    scorecard = json.loads((join_dir / "compete-scorecard.json").read_text(encoding="utf-8"))
    revision_request = (join_dir / "winner-continuation-request.md").read_text(encoding="utf-8")
    assert scorecard["status"] == "PASS"
    assert scorecard["winner_handler"] == "webclaude"
    assert scorecard["verified_features"] == [
        "keeps Ask as a Tau DAG compiler",
        "emits a bounded winner revision request",
    ]
    assert "Do not import unverified candidate claims." in revision_request


def test_extract_verified_features_recovers_collapsed_browser_markers() -> None:
    text = (
        "Position Competitor label is webclaude, so the public tiebreaker requires exactly four distinct "
        "VERIFIED_FEATURE: lines, and the ping answer is 4. "
        "VERIFIED_FEATURE: response.md contains exactly one line matching PING_RESULT. "
        "VERIFIED_FEATURE: response.md contains exactly four lines beginning with VERIFIED_FEATURE: "
        "and all four are byte-distinct. "
        "VERIFIED_FEATURE: response.md contains the required headings. "
        "VERIFIED_FEATURE: response.md states the competitor label. Evidence done."
    )

    assert tau_roundtable_worker._extract_verified_features(text) == [
        "response.md contains exactly one line matching PING_RESULT.",
        "response.md contains exactly four lines beginning with",
        "response.md contains the required headings.",
        "response.md states the competitor label.",
    ]


def test_kimi_clean_output_contamination_is_not_tab_identity_mismatch() -> None:
    meta = {
        "status": "failed",
        "failure": "missing_controlled_tab_id_or_contaminated_clean_output",
        "raw_contains_sentinel": True,
        "clean_contains_sentinel": True,
        "requested_tab_id": "837362804",
        "controlled_tab_id": "837362804",
        "controlled_tab_id_mismatch": False,
        "output": "/tmp/response.md",
        "raw_output": "/tmp/response.raw.md",
        "stderr_log": "/tmp/surf-kimi-submit-stderr.log",
    }

    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webkimi",
        failure=json.dumps(meta),
        response_text="",
        raw_text="PING_RESULT: 4\n<<<KIMI_DONE:test>>>",
        prompt_text="PING_RESULT: 4",
        submit_meta=meta,
        commands=[],
    )
    summary = tau_roundtable_worker._browser_transport_failure_summary(
        failure_code=failure_code,
        submit_meta=meta,
        commands=[],
        surf_lock_blocker={},
    )

    assert failure_code == tau_roundtable_worker.BROWSER_CLEAN_OUTPUT_CONTAMINATED
    assert summary["transport_failure_kind"] == "browser_clean_output_contaminated"
    assert summary["raw_contains_sentinel"] is True
    assert summary["clean_contains_sentinel"] is True


def test_claude_page_prompt_echo_is_clean_output_contamination() -> None:
    meta = {
        "status": "failed",
        "failure": "missing_sentinel_or_contaminated_clean_output",
        "raw_contains_sentinel": True,
        "clean_contains_sentinel": False,
        "requested_tab_id": "837364427",
        "controlled_tab_id": "837364427",
        "controlled_tab_id_mismatch": False,
        "output": "/tmp/response.md",
        "raw_output": "/tmp/response.raw.md",
    }
    response_text = (
        "Title: New chat - Claude\n"
        "URL: https://claude.ai/new\n"
        "@keyframes look-around { 0%, 16.6%, 100% { transform: translateX(-1.5px); } }\n"
        "What can we tackle together?"
        "Automation-only instruction: answer the user's request normally.\n"
    )

    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webclaude",
        failure=json.dumps(meta),
        response_text=response_text,
        raw_text=response_text + "\n<<<CLAUDE_DONE:test>>>",
        prompt_text="Roundtable request",
        submit_meta=meta,
        commands=[],
    )

    assert failure_code == tau_roundtable_worker.BROWSER_CLEAN_OUTPUT_CONTAMINATED


def test_browser_oracle_existing_venv_setup_failure_is_not_missing_sentinel() -> None:
    failure = """Using CPython 3.14.3
Creating virtual environment at: .venv
error: Failed to create virtual environment
  Caused by: A virtual environment already exists at `/tmp/askmain/skills/browser-oracle/.venv`. Use `--clear` to replace it
"""
    commands = [
        {
            "command": ["skills/browser-oracle/run.sh", "resolve", "--backend", "webkimi", "--project", "webkimi", "--json"],
            "returncode": 2,
            "stderr_excerpt": failure,
            "stdout_excerpt": "",
        }
    ]

    failure_code = tau_roundtable_worker._classify_browser_failure(
        handler="webkimi",
        failure=failure,
        response_text="",
        raw_text="",
        prompt_text="Roundtable request",
        submit_meta={},
        commands=commands,
    )

    assert failure_code == tau_roundtable_worker.ENVIRONMENT_DEPENDENCY_INSTALL_FAILED


def test_command_spec_blocks_provider_execution_without_opt_in(tmp_path: Path) -> None:
    request = infer_compile_input(
        "solve X",
        repo="local/tau",
        target="issue-ask-tau-dag",
        solver_models=["gpt-5.6-xhigh", "gpt-5.6-xhigh"],
        reviewer_model="claude-fable",
        criteria=["correctness", "maintainability"],
        output_root=tmp_path,
        local_fixture=False,
    )

    bundle = compile_tau_dag_bundle(request)
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "solver-1", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )

    assert "--mode" in command_spec["command"]
    assert "scillm" in command_spec["command"]
    assert command_spec["command"][command_spec["command"].index("--model") + 1] == "gpt-5.5"
    assert command_spec["command"][command_spec["command"].index("--requested-model") + 1] == "gpt-5.6-xhigh"
    assert command_spec["command"][command_spec["command"].index("--reasoning-effort") + 1] == "xhigh"
    assert command_spec["command"][command_spec["command"].index("--requested-reasoning-effort") + 1] == "xhigh"
    assert command_spec["requires_network"] is True
    assert command_spec["timeout_s"] == 900
    worker_source = Path(bundle["worker_path"]).read_text(encoding="utf-8")
    assert "max_tokens" not in worker_source
    compile(worker_source, str(bundle["worker_path"]), "exec")


def test_scillm_route_preserves_requested_gpt_56_xhigh_selector() -> None:
    route = resolve_scillm_model_route("gpt-5.6-xhigh")

    assert route.requested_model == "gpt-5.6-xhigh"
    assert route.model == "gpt-5.5"
    assert route.provider == "openai"
    assert route.reasoning_effort == "xhigh"
    assert route.requested_reasoning_effort == "xhigh"
    assert route.reasoning_downgrade_reason is None


def test_scillm_route_maps_claude_fable_alias_to_live_catalog_name() -> None:
    route = resolve_scillm_model_route("claude-fable")

    assert route.requested_model == "claude-fable"
    assert route.model == "claude-fable-5"
    assert route.provider == "anthropic"
    assert route.auth == "scillm_claude_code_credentials"


def test_webgpt_model_routes_to_interview_until_native_tau_skill_node_exists(tmp_path: Path) -> None:
    request = infer_compile_input(
        "ask webgpt to review X after a solver finishes",
        repo="local/tau",
        target="issue-ask-tau-dag",
        solver_models=["gpt-5.6-xhigh"],
        reviewer_model="webgpt",
        criteria=["correctness"],
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "NEEDS_INTERVIEW"
    assert "model_routes" in bundle["missing_fields"]
    assert "native Tau skill nodes" in bundle["questions"][-1]["question"]


def _handler_lock_timeout(bundle: dict, node_id: str) -> str:
    spec = json.loads(
        Path(bundle["command_spec_root"], node_id, "tau-dispatch-command.json").read_text(encoding="utf-8")
    )
    command = spec["command"]
    if "--browser-lock-timeout" not in command:
        return ""
    return command[command.index("--browser-lock-timeout") + 1]


# agent-skills#1033: the lock wait was only derivable from handler count and
# topology, so a caller facing a busy browser had no way to widen it and
# `--browser-lock-timeout` failed with "No such option" on both subcommands.
def test_browser_lock_timeout_override_reaches_every_browser_handler(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Roundtable webgpt and webclaude concurrently.",
        repo="local/agent-skills",
        target="lock-timeout-override",
        immutable_goal="Every seat answers the same shared prompt.",
        handlers=["webgpt", "webclaude"],
        topology="concurrent",
        output_root=tmp_path,
        browser_lock_timeout=2700,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    assert _handler_lock_timeout(bundle, "handler-webgpt") == "2700"
    assert _handler_lock_timeout(bundle, "handler-webclaude") == "2700"
    assert _handler_lock_timeout(bundle, "join") == ""


def test_browser_lock_timeout_default_is_kept_without_an_override(tmp_path: Path) -> None:
    def compile_with(**kwargs) -> dict:
        return compile_tau_dag_bundle(
            infer_compile_input(
                "Roundtable webgpt and webclaude concurrently.",
                repo="local/agent-skills",
                target="lock-timeout-default",
                immutable_goal="Every seat answers the same shared prompt.",
                handlers=["webgpt", "webclaude"],
                topology="concurrent",
                output_root=tmp_path / kwargs.pop("slug"),
                **kwargs,
            )
        )

    derived = compile_with(slug="derived")
    zeroed = compile_with(slug="zeroed", browser_lock_timeout=0)

    derived_timeout = _handler_lock_timeout(derived, "handler-webgpt")
    assert derived_timeout != ""
    assert derived_timeout != "0"
    assert _handler_lock_timeout(zeroed, "handler-webgpt") == derived_timeout


def test_attachments_reach_every_browser_handler_dispatch_command(tmp_path: Path) -> None:
    evidence = tmp_path / "rendered-page.png"
    evidence.write_bytes(b"\x89PNG\r\n\x1a\n")
    request = infer_compile_input(
        "Review the attached rendered page.",
        repo="local/agent-skills",
        target="attachment-forwarding",
        immutable_goal="The browser seat receives the attached evidence.",
        handlers=["webgpt", "webclaude"],
        topology="concurrent",
        output_root=tmp_path / "runs",
        attachments=[str(evidence)],
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"
    for node in ("handler-webgpt", "handler-webclaude"):
        command = json.loads(
            Path(bundle["command_spec_root"], node, "tau-dispatch-command.json").read_text(encoding="utf-8")
        )["command"]
        assert "--attach-file" in command
        assert command[command.index("--attach-file") + 1] == str(evidence)
    join_command = json.loads(
        Path(bundle["command_spec_root"], "join", "tau-dispatch-command.json").read_text(encoding="utf-8")
    )["command"]
    assert "--attach-file" not in join_command


def test_multiple_attachments_fail_preflight_before_tau_runs(tmp_path: Path) -> None:
    first = tmp_path / "metrics.md"
    second = tmp_path / "samples.md"
    for path in (first, second):
        path.write_text("evidence\n", encoding="utf-8")
    request = infer_compile_input(
        "Review the attached statistical-design bundle.",
        repo="local/agent-skills",
        target="attachment-contract",
        immutable_goal="The reviewer sees the evidence it is asked to judge.",
        handlers=["webgpt"],
        output_root=tmp_path / "runs",
        attachments=[str(first), str(second)],
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "BLOCKED"
    assert bundle["failure_code"] == "browser_attachment_argument_contract_failed"
    assert bundle["handlers"] == ["webgpt"]
    assert bundle["attachment_count"] == 2
    assert "one local bundle or zip" in bundle["remedy"]
    assert Path(bundle["run_dir"], "attachment-contract-blocked.json").is_file()
    assert not Path(bundle["run_dir"], "dag.json").exists()


def test_a_single_attachment_still_compiles_for_a_single_attachment_handler(tmp_path: Path) -> None:
    evidence = tmp_path / "bundle.md"
    evidence.write_text("evidence\n", encoding="utf-8")
    request = infer_compile_input(
        "Review the attached bundle.",
        repo="local/agent-skills",
        target="attachment-contract-ok",
        immutable_goal="The reviewer sees the evidence it is asked to judge.",
        handlers=["webgpt"],
        output_root=tmp_path / "runs",
        attachments=[str(evidence)],
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"


def test_multi_attachment_handlers_are_not_blocked(tmp_path: Path) -> None:
    first = tmp_path / "a.md"
    second = tmp_path / "b.md"
    for path in (first, second):
        path.write_text("evidence\n", encoding="utf-8")
    request = infer_compile_input(
        "Review the attached files.",
        repo="local/agent-skills",
        target="attachment-contract-grok",
        immutable_goal="The reviewer sees the evidence it is asked to judge.",
        handlers=["webgrok"],
        output_root=tmp_path / "runs",
        attachments=[str(first), str(second)],
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "READY"


def test_claude_handler_is_agentic_scillm_not_webclaude():
    """#1387: 'claude' means the agentic model on the scillm Claude Code OAuth
    lane; webclaude (a claude.ai chat tab) is reachable only by explicit name."""
    from ask.tau_dag import _normalize_handler, resolve_scillm_model_route

    assert _normalize_handler("claude") == "claude-fable-5"
    assert _normalize_handler("claude fable") == "claude-fable-5"
    assert _normalize_handler("webclaude") == "webclaude"

    route = resolve_scillm_model_route(_normalize_handler("claude"))
    assert route.provider == "anthropic"
    assert route.auth == "scillm_claude_code_credentials"

    low = resolve_scillm_model_route("claude-fable-low")
    assert low.model == "claude-fable-5"
    assert low.reasoning_effort == "low"
    xhigh = resolve_scillm_model_route("claude-fable-xhigh")
    assert xhigh.reasoning_effort == "xhigh"
    assert xhigh.requested_reasoning_effort == "xhigh"
    assert xhigh.reasoning_downgrade_reason is None
    sonnet = resolve_scillm_model_route("claude-sonnet-4-6")
    assert sonnet.model == "claude-sonnet-4-6" and sonnet.provider == "anthropic"


def test_claude_fable_low_worker_uses_scillm_not_direct_claude_cli() -> None:
    """Fable is a Tau/SciLLM lane, not a bare Claude CLI model.

    Regression guard for a live failure where the worker dispatched
    `claude-fable-low` through `claude -p --model claude-fable`, which Claude
    Code rejected before provider execution.
    """
    assert tau_roundtable_worker._is_direct_claude_cli_handler("claude-fable-low") is False
    assert tau_roundtable_worker._is_direct_claude_cli_handler("claude-fable-5") is False
    assert tau_roundtable_worker._is_direct_claude_cli_handler("claude-sonnet-4-6-medium") is False
    assert tau_roundtable_worker._is_direct_claude_cli_handler("claude-opus-5-medium") is True
    assert tau_roundtable_worker._is_direct_claude_cli_handler("opus-5-medium") is True
