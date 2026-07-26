"""CLI for /ask Tau DAG compilation and execution."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from .env import load_dotenv_once
from .tau_dag import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SCILLM_API_KEY,
    DEFAULT_SCILLM_BASE_URL,
    DEFAULT_TAU_PROJECT_ROOT,
    browser_compete_blocked_execution,
    compile_tau_dag_bundle,
    default_scillm_api_key,
    infer_compile_input,
    probe_browser_compete_handler_gate,
    probe_scillm_provider_gate,
    run_tau_dag_bundle,
)

load_dotenv_once()

app = typer.Typer(help="Compile /ask requests into strict Tau DAGs.")


@app.command("run")
def run(
    request: Annotated[
        str,
        typer.Argument(help="Human request to compile into a Tau DAG."),
    ] = "",
    repo: Annotated[str, typer.Option("--repo", help="Repository/project binding.")] = "",
    target: Annotated[str, typer.Option("--target", help="Issue, task, path, or work target.")] = "",
    immutable_goal: Annotated[
        str,
        typer.Option(
            "--immutable-goal",
            help="Immutable goal or acceptance bar shared with every roundtable/compete participant.",
        ),
    ] = "",
    solver_model: Annotated[
        list[str] | None,
        typer.Option("--solver-model", help="Solver model to run. Repeat for parallel solvers."),
    ] = None,
    reviewer_model: Annotated[str, typer.Option("--reviewer-model", help="Reviewer model.")] = "",
    handler: Annotated[
        list[str] | None,
        typer.Option("--handler", help="Roundtable handler to route through Tau. Repeat for multiple handlers."),
    ] = None,
    topology: Annotated[
        str,
        typer.Option("--topology", help="Roundtable topology: concurrent or sequential."),
    ] = "",
    workflow_mode: Annotated[
        str,
        typer.Option("--workflow-mode", help="Workflow mode: roundtable or compete."),
    ] = "roundtable",
    dag_template: Annotated[
        str,
        typer.Option(
            "--dag-template",
            "--pattern",
            help=(
                "Named DAG template/pattern: single-call, prompt-chain, creator-reviewer, "
                "reflection-loop, roundtable, compete."
            ),
        ),
    ] = "",
    join_handler: Annotated[
        str,
        typer.Option("--join-handler", help="Roundtable join/adjudicator handler label."),
    ] = "join",
    handler_project: Annotated[
        list[str] | None,
        typer.Option(
            "--handler-project",
            help="Browser-oracle project override as handler=project. Repeat for multiple handlers.",
        ),
    ] = None,
    handler_workspace: Annotated[
        list[str] | None,
        typer.Option(
            "--handler-workspace",
            help="Workspace binding for local-CLI handlers as handler=/path (e.g. codex=/path/to/worktree).",
        ),
    ] = None,
    criterion: Annotated[
        list[str] | None,
        typer.Option("--criterion", help="Reviewer criterion. Repeat for multiple criteria."),
    ] = None,
    ask_id: Annotated[str | None, typer.Option("--ask-id", help="Stable artifact id.")] = None,
    output_root: Annotated[
        Path,
        typer.Option("--run-output-root", help="Directory for ask Tau DAG artifacts."),
    ] = DEFAULT_OUTPUT_ROOT,
    execute: Annotated[bool, typer.Option("--execute", help="Execute the emitted DAG with Tau.")] = False,
    poll: Annotated[bool, typer.Option("--poll/--no-poll", help="Poll Tau run-status after execution.")] = True,
    viewer_link: Annotated[
        bool,
        typer.Option("--viewer-link", help="Ask Tau for a React Flow DAG viewer link."),
    ] = False,
    local_fixture: Annotated[
        bool,
        typer.Option(
            "--local-fixture",
            help="Use local command workers instead of provider calls for scheduler sanity proof.",
        ),
    ] = False,
    allow_provider_calls: Annotated[
        bool,
        typer.Option("--allow-provider-calls", help="Permit real provider calls through SciLLM."),
    ] = False,
    require_provider_calls: Annotated[
        bool,
        typer.Option("--require-provider-calls", help="Fail if SciLLM/provider calls are unavailable."),
    ] = False,
    scillm_base_url: Annotated[
        str,
        typer.Option("--scillm-base-url", help="SciLLM container service base URL."),
    ] = os.environ.get("SCILLM_BASE_URL", DEFAULT_SCILLM_BASE_URL),
    scillm_api_key: Annotated[
        str,
        typer.Option("--scillm-api-key", help="SciLLM bearer token."),
    ] = default_scillm_api_key(),
    tau_project_root: Annotated[
        Path,
        typer.Option("--tau-project-root", help="Tau project root used for uv run tau."),
    ] = DEFAULT_TAU_PROJECT_ROOT,
    poll_timeout_seconds: Annotated[
        float,
        typer.Option("--poll-timeout-seconds", help="Maximum status polling time."),
    ] = 120.0,
    poll_interval_seconds: Annotated[
        float,
        typer.Option("--poll-interval-seconds", help="Polling interval."),
    ] = 1.0,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    input_payload = infer_compile_input(
        request.strip(),
        repo=repo,
        target=target,
        immutable_goal=immutable_goal,
        solver_models=solver_model,
        reviewer_model=reviewer_model,
        criteria=criterion,
        handlers=handler,
        topology=topology,
        workflow_mode=workflow_mode,
        dag_template=dag_template,
        join_handler=join_handler,
        handler_projects=handler_project,
        handler_workspaces=handler_workspace,
        ask_id=ask_id,
        output_root=output_root,
        local_fixture=local_fixture,
        scillm_base_url=scillm_base_url,
        scillm_api_key=scillm_api_key,
        tau_project_root=tau_project_root,
    )
    bundle = compile_tau_dag_bundle(input_payload)
    provider_gate = None
    execution = None
    exit_code = 0

    if bundle.get("status") == "NEEDS_INTERVIEW":
        exit_code = 2
    else:
        if input_payload.handlers:
            provider_gate = {
                "schema": "ask.tau_dag_roundtable_handler_gate.v1",
                "status": "READY",
                "ok": True,
                "mocked": False,
                "live": False,
                "provider_live": False,
                "handlers": list(input_payload.handlers),
                "topology": input_payload.topology,
                "workflow_mode": input_payload.workflow_mode,
                "handler_projects": list(input_payload.handler_projects),
                "message": "Handler DAG emitted; live Surf/browser execution happens when Tau executes the DAG.",
            }
        else:
            provider_gate = probe_scillm_provider_gate(
                models=[*input_payload.solver_models, input_payload.reviewer_model],
                base_url=scillm_base_url,
                api_key=scillm_api_key,
                allow_provider_calls=allow_provider_calls,
            )
        gate_path = Path(str(bundle["run_dir"])) / "provider-gate.json"
        gate_path.write_text(json.dumps(provider_gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        provider_gate["path"] = str(gate_path)
        if require_provider_calls and provider_gate.get("ok") is not True:
            exit_code = 3
        elif execute:
            if input_payload.handlers and input_payload.workflow_mode == "compete":
                browser_gate = probe_browser_compete_handler_gate(input_payload)
                if not browser_gate.get("skipped"):
                    provider_gate = browser_gate
                    gate_path.write_text(json.dumps(provider_gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    provider_gate["path"] = str(gate_path)
                if browser_gate.get("ok") is not True and not browser_gate.get("skipped"):
                    execution = browser_compete_blocked_execution(browser_gate)
                    exit_code = 4
            if execution is not None:
                pass
            elif not input_payload.handlers and not local_fixture and not allow_provider_calls:
                execution = {
                    "schema": "ask.tau_dag_execution.v1",
                    "status": "BLOCKED",
                    "ok": False,
                    "mocked": False,
                    "live": False,
                    "provider_live": False,
                    "blocked_reason": "provider_execution_requires_allow_provider_calls",
                    "message": "Re-run with --allow-provider-calls or --local-fixture.",
                }
                exit_code = 3
            else:
                execution = run_tau_dag_bundle(
                    bundle,
                    tau_project_root=tau_project_root,
                    poll=poll,
                    poll_interval_seconds=poll_interval_seconds,
                    poll_timeout_seconds=poll_timeout_seconds,
                    viewer_link=viewer_link,
                )
                if execution.get("ok") is not True:
                    exit_code = 4

    output_live = bool(
        (isinstance(execution, dict) and execution.get("live") is True)
        or (isinstance(provider_gate, dict) and provider_gate.get("live") is True)
    )
    output = {
        "schema": "ask.tau_dag_cli_result.v1",
        "status": execution.get("status") if isinstance(execution, dict) else bundle.get("status"),
        "ok": exit_code == 0,
        "mocked": False,
        "live": output_live,
        "provider_live": bool(
            isinstance(provider_gate, dict) and provider_gate.get("provider_live") is True
        )
        or bool(isinstance(execution, dict) and execution.get("provider_live") is True),
        "bundle": bundle,
        "provider_gate": provider_gate,
        "execution": execution,
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2, sort_keys=True))
    else:
        _print_text(output)
    raise typer.Exit(exit_code)


@app.command("compete")
def compete(
    request: Annotated[
        str,
        typer.Argument(help="Task to give to isolated competitors."),
    ],
    repo: Annotated[str, typer.Option("--repo", help="Repository/project binding.")] = "",
    target: Annotated[str, typer.Option("--target", help="Issue, task, path, or work target.")] = "",
    immutable_goal: Annotated[
        str,
        typer.Option(
            "--immutable-goal",
            help="Immutable goal or acceptance bar shared with every isolated competitor.",
        ),
    ] = "",
    handler: Annotated[
        list[str] | None,
        typer.Option("--handler", help="Competitor handler/model. Repeat for multiple competitors."),
    ] = None,
    handler_project: Annotated[
        list[str] | None,
        typer.Option("--handler-project", help="Browser-oracle project override as handler=project."),
    ] = None,
    handler_workspace: Annotated[
        list[str] | None,
        typer.Option("--handler-workspace", help="Workspace binding for local-CLI handlers as handler=/path."),
    ] = None,
    criterion: Annotated[
        list[str] | None,
        typer.Option("--criterion", help="Evaluation criterion. Repeat for multiple criteria."),
    ] = None,
    ask_id: Annotated[str | None, typer.Option("--ask-id", help="Stable artifact id.")] = None,
    output_root: Annotated[
        Path,
        typer.Option("--run-output-root", help="Directory for ask Tau DAG artifacts."),
    ] = DEFAULT_OUTPUT_ROOT,
    execute: Annotated[bool, typer.Option("--execute", help="Execute the emitted compete DAG with Tau.")] = False,
    poll: Annotated[bool, typer.Option("--poll/--no-poll", help="Poll Tau run-status after execution.")] = True,
    viewer_link: Annotated[
        bool,
        typer.Option("--viewer-link", help="Ask Tau for a React Flow DAG viewer link."),
    ] = False,
    scillm_base_url: Annotated[
        str,
        typer.Option("--scillm-base-url", help="SciLLM container service base URL."),
    ] = os.environ.get("SCILLM_BASE_URL", DEFAULT_SCILLM_BASE_URL),
    scillm_api_key: Annotated[
        str,
        typer.Option("--scillm-api-key", help="SciLLM bearer token."),
    ] = default_scillm_api_key(),
    tau_project_root: Annotated[
        Path,
        typer.Option("--tau-project-root", help="Tau project root used for uv run tau."),
    ] = DEFAULT_TAU_PROJECT_ROOT,
    poll_timeout_seconds: Annotated[
        float,
        typer.Option("--poll-timeout-seconds", help="Maximum status polling time."),
    ] = 120.0,
    poll_interval_seconds: Annotated[
        float,
        typer.Option("--poll-interval-seconds", help="Polling interval."),
    ] = 1.0,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    input_payload = infer_compile_input(
        request.strip(),
        repo=repo,
        target=target,
        immutable_goal=immutable_goal,
        criteria=criterion,
        handlers=handler,
        topology="concurrent",
        workflow_mode="compete",
        dag_template="compete",
        join_handler="join",
        handler_projects=handler_project,
        handler_workspaces=handler_workspace,
        ask_id=ask_id,
        output_root=output_root,
        local_fixture=False,
        scillm_base_url=scillm_base_url,
        scillm_api_key=scillm_api_key,
        tau_project_root=tau_project_root,
    )
    bundle = compile_tau_dag_bundle(input_payload)
    provider_gate = None
    execution = None
    exit_code = 0
    if bundle.get("status") == "NEEDS_INTERVIEW":
        exit_code = 2
    else:
        provider_gate = {
            "schema": "ask.tau_dag_compete_handler_gate.v1",
            "status": "READY",
            "ok": True,
            "mocked": False,
            "live": False,
            "provider_live": False,
            "handlers": list(input_payload.handlers),
            "topology": input_payload.topology,
            "workflow_mode": input_payload.workflow_mode,
            "handler_projects": list(input_payload.handler_projects),
            "message": "Compete DAG emitted; live handler execution happens when Tau executes the DAG.",
        }
        gate_path = Path(str(bundle["run_dir"])) / "provider-gate.json"
        gate_path.write_text(json.dumps(provider_gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        provider_gate["path"] = str(gate_path)
        if execute:
            browser_gate = probe_browser_compete_handler_gate(input_payload)
            if not browser_gate.get("skipped"):
                provider_gate = browser_gate
                gate_path.write_text(json.dumps(provider_gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                provider_gate["path"] = str(gate_path)
            if browser_gate.get("ok") is not True and not browser_gate.get("skipped"):
                execution = browser_compete_blocked_execution(browser_gate)
                exit_code = 4
            else:
                execution = run_tau_dag_bundle(
                    bundle,
                    tau_project_root=tau_project_root,
                    poll=poll,
                    poll_interval_seconds=poll_interval_seconds,
                    poll_timeout_seconds=poll_timeout_seconds,
                    viewer_link=viewer_link,
                )
                if execution.get("ok") is not True:
                    exit_code = 4
    output = {
        "schema": "ask.tau_dag_cli_result.v1",
        "status": execution.get("status") if isinstance(execution, dict) else bundle.get("status"),
        "ok": exit_code == 0,
        "mocked": False,
        "live": bool(isinstance(execution, dict) and execution.get("live") is True),
        "provider_live": bool(isinstance(execution, dict) and execution.get("provider_live") is True),
        "bundle": bundle,
        "provider_gate": provider_gate,
        "execution": execution,
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2, sort_keys=True))
    else:
        _print_text(output)
    raise typer.Exit(exit_code)


@app.command("probe-scillm")
def probe_scillm(
    model: Annotated[
        list[str] | None,
        typer.Option("--model", help="Model to probe with a live chat call."),
    ] = None,
    allow_provider_calls: Annotated[
        bool,
        typer.Option("--allow-provider-calls", help="Permit real provider chat completions."),
    ] = False,
    scillm_base_url: Annotated[
        str,
        typer.Option("--scillm-base-url", help="SciLLM container service base URL."),
    ] = os.environ.get("SCILLM_BASE_URL", DEFAULT_SCILLM_BASE_URL),
    scillm_api_key: Annotated[
        str,
        typer.Option("--scillm-api-key", help="SciLLM bearer token."),
    ] = default_scillm_api_key(),
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    result = probe_scillm_provider_gate(
        models=model or [],
        base_url=scillm_base_url,
        api_key=scillm_api_key,
        allow_provider_calls=allow_provider_calls,
    )
    if json_output:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
    else:
        typer.echo(f"status: {result['status']}")
        typer.echo(f"live: {result['live']}")
        typer.echo(f"provider_live: {result['provider_live']}")
    raise typer.Exit(0 if result.get("ok") is True or not allow_provider_calls else 3)


def _print_text(output: dict[str, object]) -> None:
    bundle = output.get("bundle") if isinstance(output.get("bundle"), dict) else {}
    typer.echo(f"status: {output.get('status')}")
    typer.echo(f"run_dir: {bundle.get('run_dir')}")
    typer.echo(f"dag_path: {bundle.get('dag_path')}")
    typer.echo(f"dag_sha256: {bundle.get('dag_sha256')}")
    if bundle.get("status") == "NEEDS_INTERVIEW":
        typer.echo(f"interview_required: {bundle.get('missing_fields')}")
        typer.echo(f"interview_packet: {bundle.get('run_dir')}/interview-required.json")
    provider_gate = output.get("provider_gate")
    if isinstance(provider_gate, dict):
        typer.echo(f"provider_gate: {provider_gate.get('status')}")
    execution = output.get("execution")
    if isinstance(execution, dict):
        typer.echo(f"execution_status: {execution.get('status')}")
        typer.echo(f"receipt_path: {execution.get('receipt_path')}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
