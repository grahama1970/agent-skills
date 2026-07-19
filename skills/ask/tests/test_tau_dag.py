from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ask.tau_dag import compile_tau_dag_bundle, infer_compile_input, resolve_scillm_model_route


TAU_ROOT = Path("/home/graham/workspace/experiments/tau")


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
