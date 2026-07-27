"""CLI for /ask Tau DAG compilation and execution."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any

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

BROWSER_FRESH_URLS = {
    "webgpt": "https://chatgpt.com/",
    "webclaude": "https://claude.ai/new",
    "webkimi": "https://www.kimi.com/",
    "webgemini": "https://gemini.google.com/app",
    "webgrok": "https://grok.com/",
}
BROWSER_BACKENDS = {
    "webgpt": "webgpt",
    "webclaude": "webclaude",
    "webkimi": "webkimi",
    "webgemini": "webgemini",
    "webgrok": "webgrok",
}


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
    browser_tab_lifecycle: Annotated[
        str,
        typer.Option(
            "--browser-tab-lifecycle",
            help="Browser tab handling for Tau browser handlers: auto, reuse-bound, fresh-temporary, or fresh-keep.",
        ),
    ] = "auto",
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
    lifecycle = {"status": "skipped", "mode": browser_tab_lifecycle}
    if bundle.get("status") != "NEEDS_INTERVIEW" and execute:
        lifecycle = _provision_browser_lifecycle(
            input_payload,
            mode=browser_tab_lifecycle,
            run_dir=Path(str(bundle["run_dir"])),
        )
        if lifecycle.get("status") == "READY" and lifecycle.get("handler_projects"):
            input_payload = replace(
                input_payload,
                ask_id=Path(str(bundle["run_dir"])).name,
                handler_projects=tuple(lifecycle["handler_projects"]),
            )
            bundle = compile_tau_dag_bundle(input_payload)
            lifecycle["run_dir"] = str(bundle["run_dir"])
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
            if lifecycle.get("status") == "BLOCKED":
                execution = browser_lifecycle_blocked_execution(lifecycle)
                exit_code = 4
            elif input_payload.handlers and input_payload.workflow_mode == "compete":
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
                try:
                    execution = run_tau_dag_bundle(
                        bundle,
                        tau_project_root=tau_project_root,
                        poll=poll,
                        poll_interval_seconds=poll_interval_seconds,
                        poll_timeout_seconds=poll_timeout_seconds,
                        viewer_link=viewer_link,
                    )
                finally:
                    _cleanup_browser_lifecycle(lifecycle)
                if execution.get("ok") is not True:
                    exit_code = 4

    if execute:
        _cleanup_browser_lifecycle(lifecycle)

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
        "browser_tab_lifecycle": lifecycle,
        "execution": execution,
        "join_artifact_path": execution.get("join_artifact_path") if isinstance(execution, dict) else None,
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
    browser_tab_lifecycle: Annotated[
        str,
        typer.Option(
            "--browser-tab-lifecycle",
            help="Browser tab handling for Tau browser handlers: auto, reuse-bound, fresh-temporary, or fresh-keep.",
        ),
    ] = "auto",
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
    lifecycle = {"status": "skipped", "mode": browser_tab_lifecycle}
    if bundle.get("status") != "NEEDS_INTERVIEW" and execute:
        lifecycle = _provision_browser_lifecycle(
            input_payload,
            mode=browser_tab_lifecycle,
            run_dir=Path(str(bundle["run_dir"])),
        )
        if lifecycle.get("status") == "READY" and lifecycle.get("handler_projects"):
            input_payload = replace(
                input_payload,
                ask_id=Path(str(bundle["run_dir"])).name,
                handler_projects=tuple(lifecycle["handler_projects"]),
            )
            bundle = compile_tau_dag_bundle(input_payload)
            lifecycle["run_dir"] = str(bundle["run_dir"])
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
            if lifecycle.get("status") == "BLOCKED":
                execution = browser_lifecycle_blocked_execution(lifecycle)
                exit_code = 4
            else:
                browser_gate = probe_browser_compete_handler_gate(input_payload)
                if not browser_gate.get("skipped"):
                    provider_gate = browser_gate
                    gate_path.write_text(json.dumps(provider_gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    provider_gate["path"] = str(gate_path)
                if browser_gate.get("ok") is not True and not browser_gate.get("skipped"):
                    execution = browser_compete_blocked_execution(browser_gate)
                    exit_code = 4
                else:
                    try:
                        execution = run_tau_dag_bundle(
                            bundle,
                            tau_project_root=tau_project_root,
                            poll=poll,
                            poll_interval_seconds=poll_interval_seconds,
                            poll_timeout_seconds=poll_timeout_seconds,
                            viewer_link=viewer_link,
                        )
                    finally:
                        _cleanup_browser_lifecycle(lifecycle)
                    if execution.get("ok") is not True:
                        exit_code = 4

    if execute:
        _cleanup_browser_lifecycle(lifecycle)
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
        "browser_tab_lifecycle": lifecycle,
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2, sort_keys=True))
    else:
        _print_text(output)
    raise typer.Exit(exit_code)


def _provision_browser_lifecycle(
    input_payload: Any,
    *,
    mode: str,
    run_dir: Path,
    surf_run: Path | None = None,
    browser_oracle_run: Path | None = None,
) -> dict[str, Any]:
    mode = (mode or "auto").strip()
    browser_handlers = [handler for handler in input_payload.handlers if handler in BROWSER_FRESH_URLS]
    if mode == "auto":
        if browser_handlers and str(input_payload.workflow_mode or "") in {"roundtable", "compete"}:
            mode = "fresh-temporary"
        else:
            mode = "reuse-bound"
    if mode == "reuse-bound":
        lifecycle = {"schema": "ask.browser_tab_lifecycle.v1", "status": "skipped", "mode": mode}
        _write_lifecycle(run_dir, lifecycle)
        return lifecycle
    if mode not in {"fresh-temporary", "fresh-keep"}:
        lifecycle = {
            "schema": "ask.browser_tab_lifecycle.v1",
            "status": "BLOCKED",
            "mode": mode,
            "failure_code": "unsupported_browser_tab_lifecycle",
            "supported_modes": ["auto", "reuse-bound", "fresh-temporary", "fresh-keep"],
        }
        _write_lifecycle(run_dir, lifecycle)
        raise typer.BadParameter("browser_tab_lifecycle must be auto, reuse-bound, fresh-temporary, or fresh-keep")

    if not browser_handlers:
        lifecycle = {"schema": "ask.browser_tab_lifecycle.v1", "status": "skipped", "mode": mode, "reason": "no_browser_handlers"}
        _write_lifecycle(run_dir, lifecycle)
        return lifecycle

    surf_run = surf_run or (Path(__file__).resolve().parents[2].parent / "surf" / "run.sh")
    browser_oracle_run = browser_oracle_run or (Path(__file__).resolve().parents[2].parent / "browser-oracle" / "run.sh")
    created_tabs: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    handler_projects: list[str] = list(input_payload.handler_projects)
    lifecycle_id = run_dir.name
    first = browser_handlers[0]
    first_project = f"{lifecycle_id}-{first}"
    window = _lifecycle_command(
        [str(surf_run), "window.new", BROWSER_FRESH_URLS[first], "--json", "--unfocused"],
        cwd=surf_run.parent,
        timeout_seconds=60,
    )
    commands.append(window)
    if window["returncode"] != 0:
        lifecycle = _lifecycle_blocked(mode, run_dir, "browser_window_create_failed", commands, created_tabs)
        _write_lifecycle(run_dir, lifecycle)
        return lifecycle
    window_payload = _json_or_text(window["stdout"])
    window_id = _extract_window_id(window_payload)
    first_tab = _extract_tab_id(window_payload)
    if not first_tab:
        lifecycle = _lifecycle_blocked(mode, run_dir, "browser_window_missing_tab_id", commands, created_tabs)
        _write_lifecycle(run_dir, lifecycle)
        return lifecycle
    created_tabs.append({"handler": first, "project": first_project, "tab_id": first_tab, "url": BROWSER_FRESH_URLS[first], "window_id": window_id})
    _replace_handler_project(handler_projects, first, first_project)

    for handler in browser_handlers[1:]:
        project = f"{lifecycle_id}-{handler}"
        tab_command = [str(surf_run), "tab.new", BROWSER_FRESH_URLS[handler], "--json", "--background"]
        if window_id:
            tab_command.extend(["--window-id", window_id])
        opened = _lifecycle_command(tab_command, cwd=surf_run.parent, timeout_seconds=60)
        commands.append(opened)
        if opened["returncode"] != 0:
            lifecycle = _lifecycle_blocked(mode, run_dir, f"{handler}_tab_create_failed", commands, created_tabs, window_id=window_id)
            _write_lifecycle(run_dir, lifecycle)
            return lifecycle
        tab_id = _extract_tab_id(_json_or_text(opened["stdout"]))
        if not tab_id:
            lifecycle = _lifecycle_blocked(mode, run_dir, f"{handler}_tab_missing_tab_id", commands, created_tabs, window_id=window_id)
            _write_lifecycle(run_dir, lifecycle)
            return lifecycle
        created_tabs.append({"handler": handler, "project": project, "tab_id": tab_id, "url": BROWSER_FRESH_URLS[handler], "window_id": window_id})
        _replace_handler_project(handler_projects, handler, project)

    for tab in created_tabs:
        bound = _lifecycle_command(
            [
                str(browser_oracle_run),
                "bind",
                str(tab["project"]),
                "--backend",
                BROWSER_BACKENDS[str(tab["handler"])],
                "--tab-id",
                str(tab["tab_id"]),
                "--url",
                str(tab["url"]),
                "--auto",
                "--json",
            ],
            cwd=browser_oracle_run.parent,
            timeout_seconds=45,
        )
        commands.append(bound)
        tab["bind_returncode"] = bound["returncode"]
        if bound["returncode"] != 0:
            lifecycle = _lifecycle_blocked(mode, run_dir, f"{tab['handler']}_browser_oracle_bind_failed", commands, created_tabs, window_id=window_id)
            _write_lifecycle(run_dir, lifecycle)
            return lifecycle

    lifecycle = {
        "schema": "ask.browser_tab_lifecycle.v1",
        "status": "READY",
        "mode": mode,
        "run_dir": str(run_dir),
        "window_id": window_id,
        "created_tabs": created_tabs,
        "handler_projects": handler_projects,
        "cleanup_policy": "close_created_window_or_tabs_after_execution" if mode == "fresh-temporary" else "keep_created_tabs_for_inspection",
        "surf_run": str(surf_run),
        "browser_oracle_run": str(browser_oracle_run),
        "commands": commands,
    }
    _write_lifecycle(run_dir, lifecycle)
    return lifecycle


def _cleanup_browser_lifecycle(lifecycle: dict[str, Any]) -> None:
    if lifecycle.get("cleanup_status") == "attempted":
        return
    if lifecycle.get("status") not in {"READY", "BLOCKED"} or lifecycle.get("mode") != "fresh-temporary":
        return
    surf_run = Path(str(lifecycle.get("surf_run") or (Path(__file__).resolve().parents[2].parent / "surf" / "run.sh")))
    cleanup: list[dict[str, Any]] = []
    window_id = str(lifecycle.get("window_id") or "")
    if window_id:
        cleanup.append(_lifecycle_command([str(surf_run), "window.close", window_id], cwd=surf_run.parent, timeout_seconds=45))
    else:
        for tab in lifecycle.get("created_tabs", []):
            if isinstance(tab, dict) and tab.get("tab_id"):
                cleanup.append(_lifecycle_command([str(surf_run), "tab.close", str(tab["tab_id"])], cwd=surf_run.parent, timeout_seconds=45))
    lifecycle["cleanup"] = cleanup
    lifecycle["cleanup_status"] = "attempted"
    run_dir = Path(str(lifecycle.get("run_dir") or ""))
    if run_dir:
        _write_lifecycle(run_dir, lifecycle)


def browser_lifecycle_blocked_execution(lifecycle: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "ask.tau_dag_execution.v1",
        "status": "BLOCKED",
        "ok": False,
        "mocked": False,
        "live": False,
        "provider_live": False,
        "blocked_reason": "browser_tab_lifecycle_failed",
        "message": "Ask did not launch Tau because requested browser tab provisioning failed.",
        "no_tau_execution": True,
        "browser_tab_lifecycle": lifecycle,
    }


def _replace_handler_project(items: list[str], handler: str, project: str) -> None:
    prefix = f"{handler}="
    for index, item in enumerate(items):
        if item.startswith(prefix):
            items[index] = f"{handler}={project}"
            return
    items.append(f"{handler}={project}")


def _write_lifecycle(run_dir: Path, lifecycle: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "browser-tab-lifecycle.json").write_text(json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _lifecycle_blocked(
    mode: str,
    run_dir: Path,
    failure_code: str,
    commands: list[dict[str, Any]],
    created_tabs: list[dict[str, Any]],
    *,
    window_id: str = "",
) -> dict[str, Any]:
    return {
        "schema": "ask.browser_tab_lifecycle.v1",
        "status": "BLOCKED",
        "mode": mode,
        "run_dir": str(run_dir),
        "failure_code": failure_code,
        "window_id": window_id or None,
        "created_tabs": created_tabs,
        "commands": commands,
    }


def _lifecycle_command(command: list[str], *, cwd: Path, timeout_seconds: float) -> dict[str, Any]:
    started = time.time()
    try:
        completed = subprocess.run(command, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_seconds, check=False)
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[:20000],
            "stderr": completed.stderr[:8000],
            "duration_seconds": round(time.time() - started, 3),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": 124,
            "stdout": str(exc.stdout or "")[:20000],
            "stderr": str(exc.stderr or "command timed out")[:8000],
            "duration_seconds": round(time.time() - started, 3),
            "timed_out": True,
        }
    except OSError as exc:
        return {
            "command": command,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc)[:4000],
            "duration_seconds": round(time.time() - started, 3),
            "timed_out": False,
        }


def _json_or_text(text: str) -> Any:
    stripped = (text or "").strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def _extract_tab_id(payload: Any) -> str:
    if isinstance(payload, str):
        import re
        match = re.search(r"\b(?:tab|id)\D+(\d+)\b", payload, re.I)
        return match.group(1) if match else ""
    if isinstance(payload, dict):
        for key in ("tabId", "tab_id"):
            if payload.get(key):
                return str(payload[key])
        tabs = payload.get("tabs")
        if isinstance(tabs, list) and tabs:
            return _extract_tab_id(tabs[0])
        tab = payload.get("tab")
        if isinstance(tab, dict):
            return _extract_tab_id(tab)
        if payload.get("id") and not isinstance(payload.get("tabs"), list):
            return str(payload["id"])
    return ""


def _extract_window_id(payload: Any) -> str:
    if isinstance(payload, str):
        import re
        match = re.search(r"\bWindow\s+(\d+)\b", payload, re.I)
        return match.group(1) if match else ""
    if isinstance(payload, dict):
        for key in ("windowId", "window_id"):
            if payload.get(key):
                return str(payload[key])
        window = payload.get("window")
        if isinstance(window, dict):
            return _extract_window_id(window) or str(window.get("id") or "")
        tabs = payload.get("tabs")
        if isinstance(tabs, list) and tabs and isinstance(tabs[0], dict):
            for key in ("windowId", "window_id"):
                if tabs[0].get(key):
                    return str(tabs[0][key])
        if payload.get("id") and isinstance(payload.get("tabs"), list):
            return str(payload["id"])
    return ""


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
