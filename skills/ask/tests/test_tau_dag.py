from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ask.tau_dag import (
    browser_compete_blocked_execution,
    compile_tau_dag_bundle,
    infer_compile_input,
    probe_browser_compete_handler_gate,
    resolve_scillm_model_route,
)


TAU_ROOT = Path("/home/graham/workspace/experiments/tau")
ASK_ROOT = Path(__file__).resolve().parents[1]


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
    assert solver_policy["reasoning_effort"] == "high"
    assert solver_policy["requested_reasoning_effort"] == "xhigh"
    assert "xhigh is preserved" in solver_policy["reasoning_downgrade_reason"]
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
    assert {"from": "handler-webgemini", "to": "join"} in dag["edges"]
    join = dag["nodes"][-1]
    assert join["join"]["requires_completed"] == [
        "handler-webkimi",
        "handler-webclaude",
        "handler-webgpt",
        "handler-webgemini",
    ]
    kimi = dag["nodes"][0]
    assert kimi["agent"] == "handler-webkimi"
    assert kimi["context"]["handler"] == "webkimi"
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
if args[:1] == ["tab.new"]:
    print(json.dumps({"success": True, "tabId": 456, "url": args[1]}))
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
        command.get("recovery_attempt") == "webgpt_stale_binding_submit_after_rebind"
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
    assert request.handlers == ("deepseek-ai/deepseek-v3.2-tee",)
    assert request.handler_provider_hints == ("chutes",)
    dag = bundle["dag"]
    assert dag["context"]["handlers"] == ["deepseek-ai/deepseek-v3.2-tee"]
    node = dag["nodes"][0]
    assert node["context"]["provider_hint"] == "chutes"
    policy = node["context"]["handler_policy"]
    assert policy["transport_owner"] == "$tau"
    assert policy["transport"] == "scillm.chat"
    assert policy["provider_hint"] == "chutes"
    assert policy["model_policy"]["provider"] == "chutes"
    assert policy["model_policy"]["model"] == "deepseek-ai/deepseek-v3.2-tee"
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-deepseek-ai-deepseek-v3-2-tee", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--handler") + 1] == "deepseek-ai/deepseek-v3.2-tee"
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
    assert request.handlers == ("deepseek-ai/deepseek-v3.2-tee",)
    assert request.handler_provider_hints == ("chutes",)
    command_spec = json.loads(
        Path(bundle["command_spec_root"], "handler-deepseek-ai-deepseek-v3-2-tee", "tau-dispatch-command.json").read_text(
            encoding="utf-8"
        )
    )
    command = command_spec["command"]
    assert command[command.index("--handler") + 1] == "deepseek-ai/deepseek-v3.2-tee"
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
        "deepseek-ai/deepseek-v3.2-tee",
    )
    assert request.handler_provider_hints == ("", "", "", "chutes")
    dag = bundle["dag"]
    assert dag["context"]["handlers"] == [
        "webgpt",
        "webclaude",
        "webkimi",
        "deepseek-ai/deepseek-v3.2-tee",
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
    candidates = [node for node in dag["nodes"] if str(node["id"]).startswith("handler-")]
    assert candidates
    assert all(node["context"]["workflow_mode"] == "compete" for node in candidates)
    assert all(node["context"]["isolation_required"] is True for node in candidates)
    assert all(node["context"]["prompt_contract"]["isolation_required"] is True for node in candidates)
    assert all(node["context"]["prompt_contract"]["immutable_goal"] == request.immutable_goal for node in candidates)
    join = next(node for node in dag["nodes"] if node["id"] == "join")
    assert join["context"]["role"] == "compete_evaluator"
    assert "compete_scorecard" in join["required_evidence"]
    assert "winner_revision_request" in join["required_evidence"]
    assert join["join"]["fail_closed_on_tie"] is True
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
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 1, completed.stderr
    receipt = json.loads((join_dir / "node-receipt.json").read_text(encoding="utf-8"))
    scorecard = json.loads((join_dir / "compete-scorecard.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert scorecard["status"] == "NEEDS_ATTENTION"
    assert "winner_tie_requires_project_agent_review" in scorecard["blockers"]
    assert "no_explicit_verified_features_to_promote" in scorecard["blockers"]


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
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    scorecard = json.loads((join_dir / "compete-scorecard.json").read_text(encoding="utf-8"))
    revision_request = (join_dir / "winner-revision-request.md").read_text(encoding="utf-8")
    assert scorecard["status"] == "PASS"
    assert scorecard["winner_handler"] == "webclaude"
    assert scorecard["verified_features"] == [
        "keeps Ask as a Tau DAG compiler",
        "emits a bounded winner revision request",
    ]
    assert "Do not import unverified candidate claims." in revision_request


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
    assert command_spec["command"][command_spec["command"].index("--reasoning-effort") + 1] == "high"
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
    assert route.reasoning_effort == "high"
    assert route.requested_reasoning_effort == "xhigh"
    assert route.reasoning_downgrade_reason is not None


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
