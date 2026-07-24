from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ask.tau_dag import compile_tau_dag_bundle, infer_compile_input, resolve_scillm_model_route


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


def test_roundtable_handlers_can_be_explicit_and_sequential(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Roundtable the implementation plan.",
        repo="local/agent-skills",
        target="roundtable-sequential",
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


def test_roundtable_handler_project_overrides_are_written_to_command_specs(tmp_path: Path) -> None:
    request = infer_compile_input(
        "Roundtable webgpt and webkimi.",
        repo="local/agent-skills",
        target="roundtable-projects",
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
    claude = next(node for node in candidates if node["context"]["handler"] == "webclaude")
    assert claude["context"]["handler_policy"]["model_preference"] == "Opus 5 High"
    assert claude["context"]["handler_policy"]["model_preference_scope"] == "ask_compete_default"
    assert claude["context"]["prompt_contract"]["model_preference"] == "Opus 5 High"
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
        handlers=["webgpt"],
        topology="sequential",
        workflow_mode="compete",
        output_root=tmp_path,
    )

    bundle = compile_tau_dag_bundle(request)

    assert bundle["status"] == "NEEDS_INTERVIEW"
    assert {"handlers", "topology"} <= set(bundle["missing_fields"])


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
