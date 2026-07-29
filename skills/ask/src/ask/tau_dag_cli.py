"""CLI for /ask Tau DAG compilation and execution."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any

import typer

from .env import load_dotenv_once
from .tau_dag import (
    BROWSER_COMMAND_GRACE_SECONDS,
    DEFAULT_BROWSER_SUBMIT_TIMEOUT_SECONDS,
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

ASK_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BROWSER_AVAILABILITY_SCRIPT = ASK_ROOT / "scripts" / "probe_browser_provider_availability.py"

BROWSER_FRESH_URLS = {
    "webgpt": "https://chatgpt.com/",
    "webclaude": "https://claude.ai/new",
    "webkimi": "https://www.kimi.com/",
    "webgemini": "https://gemini.google.com/app",
    "webgrok": "https://grok.com/",
    "webdeepseek": "https://chat.deepseek.com/",
}
BROWSER_BACKENDS = {
    "webgpt": "webgpt",
    "webclaude": "webclaude",
    "webkimi": "webkimi",
    "webgemini": "webgemini",
    "webgrok": "webgrok",
    "webdeepseek": "webdeepseek",
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
    browser_lock_timeout: Annotated[
        int,
        typer.Option(
            "--browser-lock-timeout",
            help="Seconds a browser handler waits for the shared Surf browser lock. 0 keeps the derived default.",
        ),
    ] = 0,
    attach_file: Annotated[
        list[str] | None,
        typer.Option(
            "--attach-file",
            help="Local file forwarded to browser handlers as Surf --attach-file evidence. Repeat for multiple files.",
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
        browser_lock_timeout=browser_lock_timeout,
        execution_timeout_seconds=int(poll_timeout_seconds) if execute else 0,
        attachments=attach_file,
    )
    bundle = compile_tau_dag_bundle(input_payload)
    lifecycle = {"status": "skipped", "mode": browser_tab_lifecycle}
    browser_availability = _skipped_browser_availability("not_executing" if not execute else "not_checked")
    if bundle.get("status") != "NEEDS_INTERVIEW" and execute:
        browser_availability = _probe_browser_provider_availability(
            input_payload,
            run_dir=Path(str(bundle["run_dir"])),
        )
        browser_availability = _annotate_browser_availability_cooldown(browser_availability)
        _write_browser_availability(Path(str(bundle["run_dir"])), browser_availability)
        if not _browser_availability_blocks(browser_availability):
            lifecycle = _provision_browser_lifecycle(
                input_payload,
                mode=browser_tab_lifecycle,
                run_dir=Path(str(bundle["run_dir"])),
                timeout_budget_seconds=int(poll_timeout_seconds) if execute else 0,
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
            if _browser_availability_blocks(browser_availability):
                execution = browser_availability_blocked_execution(browser_availability)
                exit_code = 4
            elif lifecycle.get("status") == "BLOCKED":
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
        or (isinstance(browser_availability, dict) and browser_availability.get("live") is True)
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
        "browser_provider_availability": browser_availability,
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
    browser_lock_timeout: Annotated[
        int,
        typer.Option(
            "--browser-lock-timeout",
            help="Seconds a browser handler waits for the shared Surf browser lock. 0 keeps the derived default.",
        ),
    ] = 0,
    attach_file: Annotated[
        list[str] | None,
        typer.Option(
            "--attach-file",
            help="Local file forwarded to browser handlers as Surf --attach-file evidence. Repeat for multiple files.",
        ),
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
        browser_lock_timeout=browser_lock_timeout,
        execution_timeout_seconds=int(poll_timeout_seconds) if execute else 0,
        attachments=attach_file,
    )
    bundle = compile_tau_dag_bundle(input_payload)
    lifecycle = {"status": "skipped", "mode": browser_tab_lifecycle}
    browser_availability = _skipped_browser_availability("not_executing" if not execute else "not_checked")
    if bundle.get("status") != "NEEDS_INTERVIEW" and execute:
        browser_availability = _probe_browser_provider_availability(
            input_payload,
            run_dir=Path(str(bundle["run_dir"])),
        )
        browser_availability = _annotate_browser_availability_cooldown(browser_availability)
        _write_browser_availability(Path(str(bundle["run_dir"])), browser_availability)
        if not _browser_availability_blocks(browser_availability):
            lifecycle = _provision_browser_lifecycle(
                input_payload,
                mode=browser_tab_lifecycle,
                run_dir=Path(str(bundle["run_dir"])),
                timeout_budget_seconds=int(poll_timeout_seconds) if execute else 0,
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
            if _browser_availability_blocks(browser_availability):
                execution = browser_availability_blocked_execution(browser_availability)
                exit_code = 4
            elif lifecycle.get("status") == "BLOCKED":
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
        "live": bool(isinstance(execution, dict) and execution.get("live") is True)
        or bool(isinstance(browser_availability, dict) and browser_availability.get("live") is True),
        "provider_live": bool(isinstance(execution, dict) and execution.get("provider_live") is True),
        "bundle": bundle,
        "provider_gate": provider_gate,
        "execution": execution,
        "browser_provider_availability": browser_availability,
        "browser_tab_lifecycle": lifecycle,
    }
    if json_output:
        typer.echo(json.dumps(output, indent=2, sort_keys=True))
    else:
        _print_text(output)
    raise typer.Exit(exit_code)


def _browser_handlers(input_payload: Any) -> list[str]:
    seen: set[str] = set()
    handlers: list[str] = []
    for handler in getattr(input_payload, "handlers", ()) or ():
        if handler in BROWSER_FRESH_URLS and handler not in seen:
            seen.add(handler)
            handlers.append(handler)
    return handlers


def _skipped_browser_availability(reason: str) -> dict[str, Any]:
    return {
        "schema": "ask.browser_provider_availability.v1",
        "status": "skipped",
        "mocked": False,
        "live": False,
        "read_only": True,
        "reason": reason,
    }


def _probe_browser_provider_availability(
    input_payload: Any,
    *,
    run_dir: Path,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    handlers = _browser_handlers(input_payload)
    if not handlers:
        report = _skipped_browser_availability("no_browser_handlers")
        _write_browser_availability(run_dir, report)
        return report

    script = Path(os.environ.get("ASK_BROWSER_AVAILABILITY_SCRIPT", str(DEFAULT_BROWSER_AVAILABILITY_SCRIPT)))
    output_path = run_dir / "browser-provider-availability.json"
    command = [sys.executable, str(script)]
    for handler in handlers:
        command.extend(["--provider", handler])
    command.extend(["--output", str(output_path), "--max-tabs-per-provider", "2", "--json"])

    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(ASK_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        command_receipt = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[:20000],
            "stderr": completed.stderr[:8000],
            "duration_seconds": round(time.time() - started, 3),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        command_receipt = {
            "command": command,
            "returncode": 124,
            "stdout": str(exc.stdout or "")[:20000],
            "stderr": str(exc.stderr or "browser availability probe timed out")[:8000],
            "duration_seconds": round(time.time() - started, 3),
            "timed_out": True,
        }
    except OSError as exc:
        command_receipt = {
            "command": command,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc)[:4000],
            "duration_seconds": round(time.time() - started, 3),
            "timed_out": False,
        }

    report: dict[str, Any]
    if output_path.is_file():
        try:
            report = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report = {
                "schema": "ask.browser_provider_availability.v1",
                "status": "ERROR",
                "mocked": False,
                "live": True,
                "read_only": True,
                "error": f"browser_availability_report_invalid_json: {exc}",
            }
    else:
        report = {
            "schema": "ask.browser_provider_availability.v1",
            "status": "ERROR",
            "mocked": False,
            "live": False,
            "read_only": True,
            "error": "browser_availability_report_missing",
        }

    report["path"] = str(output_path)
    report["requested_providers"] = handlers
    report["command_receipt"] = command_receipt
    if command_receipt["returncode"] != 0 and report.get("status") != "NEEDS_ATTENTION":
        report["status"] = "ERROR"
        report.setdefault("error", "browser_availability_probe_failed")
    _write_browser_availability(run_dir, report)
    return report


def _browser_availability_blocks(report: dict[str, Any]) -> bool:
    if report.get("status") == "ERROR":
        return True
    if report.get("status") == "NEEDS_ATTENTION" and not _browser_availability_limited_providers(report):
        return True
    return False


def _browser_availability_limited_providers(report: dict[str, Any]) -> list[str]:
    providers = report.get("providers")
    if isinstance(providers, dict):
        return [
            name
            for name, payload in providers.items()
            if isinstance(payload, dict) and payload.get("provider_limited") is True
        ]
    return []


def _annotate_browser_availability_cooldown(report: dict[str, Any]) -> dict[str, Any]:
    limited = _browser_availability_limited_providers(report)
    if not limited:
        return report
    annotated = dict(report)
    annotated["limited_providers"] = limited
    annotated["cooldown_policy"] = {
        "schema": "ask.browser_provider_cooldown_policy.v1",
        "status": "LANE_LOCAL_RETRY",
        "limited_providers": limited,
        "retry_after_seconds": 300,
        "retry_attempts": 1,
        "continues_with_available_providers": True,
        "surf_env": {
            "SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS": "300",
            "SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS": "1",
        }
        if "webgpt" in limited
        else {},
        "message": (
            "Ask treats provider cooldowns as lane-local. Executed handler DAGs continue with peer "
            "providers, and cooled-down WebGPT lanes opt into Surf's bounded 300-second retry."
        ),
    }
    return annotated


def browser_availability_blocked_execution(report: dict[str, Any]) -> dict[str, Any]:
    limited: list[str] = []
    providers = report.get("providers")
    if isinstance(providers, dict):
        limited = [
            name
            for name, payload in providers.items()
            if isinstance(payload, dict) and payload.get("provider_limited") is True
        ]
    failure_code = "browser_provider_rate_limited" if limited else "browser_provider_availability_probe_failed"
    return {
        "schema": "ask.tau_dag_execution.v1",
        "status": "NEEDS_ATTENTION",
        "ok": False,
        "mocked": False,
        "live": bool(report.get("live") is True),
        "provider_live": False,
        "blocked_reason": "browser_provider_unavailable_preflight",
        "failure_code": failure_code,
        "limited_providers": limited,
        "no_tau_execution": True,
        "message": (
            "Ask did not launch Tau or submit browser prompts because the read-only browser provider "
            "availability preflight found a visible cooldown/throttle state or could not complete."
        ),
        "browser_provider_availability": report,
        "next_command": (
            "Wait for the named provider cooldown to clear, rerun `skills/ask/run.sh browser-availability "
            "--provider <provider> --json`, then rerun the Ask DAG with the same immutable goal."
        ),
        "ticket_instruction": (
            "If this report is missing the provider, tab id, visible text excerpt, failure_code, or next_command, "
            "file a $ticket to $ask at agent-skills@main with the Ask run_dir and browser-provider-availability.json."
        ),
    }


def _write_browser_availability(run_dir: Path, report: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "browser-provider-availability.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _provision_browser_lifecycle(
    input_payload: Any,
    *,
    mode: str,
    run_dir: Path,
    timeout_budget_seconds: int = 0,
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
    lock_timeout_seconds = DEFAULT_BROWSER_SUBMIT_TIMEOUT_SECONDS * max(len(browser_handlers) - 1, 1)
    if timeout_budget_seconds > 0:
        lock_timeout_seconds = min(lock_timeout_seconds, max(1, int(timeout_budget_seconds)))
    command_timeout_seconds = (
        DEFAULT_BROWSER_SUBMIT_TIMEOUT_SECONDS
        + lock_timeout_seconds
        + BROWSER_COMMAND_GRACE_SECONDS
    )
    if timeout_budget_seconds > 0:
        command_timeout_seconds = min(
            command_timeout_seconds,
            max(1, int(timeout_budget_seconds)) + BROWSER_COMMAND_GRACE_SECONDS,
        )
    first = browser_handlers[0]
    first_project = f"{lifecycle_id}-{first}"
    window = _lifecycle_command(
        [
            str(surf_run),
            "window.new",
            BROWSER_FRESH_URLS[first],
            "--json",
            "--unfocused",
            "--lock-timeout",
            str(lock_timeout_seconds),
        ],
        cwd=surf_run.parent,
        timeout_seconds=command_timeout_seconds,
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
        tab_command.extend(["--lock-timeout", str(lock_timeout_seconds)])
        opened = _lifecycle_command(tab_command, cwd=surf_run.parent, timeout_seconds=command_timeout_seconds)
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
        "lock_timeout_seconds": lock_timeout_seconds,
        "command_timeout_seconds": command_timeout_seconds,
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
        lock_timeout_seconds = int(lifecycle.get("lock_timeout_seconds") or DEFAULT_BROWSER_SUBMIT_TIMEOUT_SECONDS)
        cleanup.append(
            _lifecycle_command(
                [str(surf_run), "window.close", window_id, "--lock-timeout", str(lock_timeout_seconds)],
                cwd=surf_run.parent,
                timeout_seconds=lock_timeout_seconds + BROWSER_COMMAND_GRACE_SECONDS,
            )
        )
    else:
        lock_timeout_seconds = int(lifecycle.get("lock_timeout_seconds") or DEFAULT_BROWSER_SUBMIT_TIMEOUT_SECONDS)
        for tab in lifecycle.get("created_tabs", []):
            if isinstance(tab, dict) and tab.get("tab_id"):
                cleanup.append(
                    _lifecycle_command(
                        [str(surf_run), "tab.close", str(tab["tab_id"]), "--lock-timeout", str(lock_timeout_seconds)],
                        cwd=surf_run.parent,
                        timeout_seconds=lock_timeout_seconds + BROWSER_COMMAND_GRACE_SECONDS,
                    )
                )
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
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        return {
            "command": command,
            "returncode": proc.returncode,
            "stdout": stdout[:20000],
            "stderr": stderr[:8000],
            "duration_seconds": round(time.time() - started, 3),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        if proc is not None:
            _terminate_process_group(proc.pid)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_process_group(proc.pid)
                stdout, stderr = proc.communicate()
        else:
            stdout = str(exc.stdout or "")
            stderr = str(exc.stderr or "")
        return {
            "command": command,
            "returncode": 124,
            "stdout": (stdout or "")[:20000],
            "stderr": ((stderr or "") + "\n[ask-lifecycle] command timed out; killed process group\n")[:8000],
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


def _terminate_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


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
    browser_availability = output.get("browser_provider_availability")
    if isinstance(browser_availability, dict):
        typer.echo(f"browser_provider_availability: {browser_availability.get('status')}")
    execution = output.get("execution")
    if isinstance(execution, dict):
        typer.echo(f"execution_status: {execution.get('status')}")
        typer.echo(f"receipt_path: {execution.get('receipt_path')}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
