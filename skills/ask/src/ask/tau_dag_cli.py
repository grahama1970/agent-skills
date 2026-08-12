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


def _emit_dag_chart(bundle: dict[str, Any], *, execute: bool) -> None:
    """Print an ASCII confirmation chart of the compiled DAG before any run.

    Deterministic and rendered from the same compiled nodes Tau executes;
    stderr so --json stdout stays parseable.
    """
    dag = bundle.get("dag") if isinstance(bundle, dict) else None
    nodes = (dag or {}).get("nodes") if isinstance(dag, dict) else None
    if not nodes:
        return
    by_id = {str(n.get("id")): n for n in nodes if isinstance(n, dict) and n.get("id")}
    # Edges live per-node (depends_on) or in the contract's top-level edges list.
    deps_by_node: dict[str, set[str]] = {nid: set() for nid in by_id}
    for nid, node in by_id.items():
        deps_by_node[nid].update(d for d in (node.get("depends_on") or []) if d in by_id)
    for edge in (dag or {}).get("edges") or []:
        if isinstance(edge, dict):
            src, dst = str(edge.get("from", "")), str(edge.get("to", ""))
        elif isinstance(edge, (list, tuple)) and len(edge) == 2:
            src, dst = str(edge[0]), str(edge[1])
        else:
            continue
        if src in by_id and dst in by_id:
            deps_by_node[dst].add(src)
    depths: dict[str, int] = {}

    def depth(nid: str) -> int:
        if nid not in depths:
            deps = deps_by_node[nid]
            depths[nid] = 0 if not deps else 1 + max(depth(d) for d in deps)
        return depths[nid]

    try:
        for nid in by_id:
            depth(nid)
    except RecursionError:
        return
    mode = "about to EXECUTE via Tau" if execute else "preview only; add --execute to run"
    lines = [f"DAG ({mode}):", ""]
    for level in range(max(depths.values()) + 1):
        for nid in sorted(n for n, d in depths.items() if d == level):
            node = by_id[nid]
            deps = sorted(deps_by_node[nid])
            arrow = f"  <- {', '.join(deps)}" if deps else ""
            lines.append(f"{'    ' * level}[{nid}] {node.get('agent', '')}{arrow}")
    typer.echo("\n".join(lines) + "\n", err=True)



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
        # Lane execution budgets come from the per-handler envelopes in
        # _roundtable_command_timeout; deriving them from --poll-timeout-seconds
        # (default 120) starved every browser lane to a 300s wall (observed:
        # webgpt/webgrok killed mid-generation at 120s effective submit).
        execution_timeout_seconds=0,
        attachments=attach_file,
    )
    bundle = compile_tau_dag_bundle(input_payload)
    _emit_dag_chart(bundle, execute=execute)
    lifecycle = {"status": "skipped", "mode": browser_tab_lifecycle}
    browser_availability = _skipped_browser_availability("not_executing" if not execute else "not_checked")
    if bundle.get("status") != "NEEDS_INTERVIEW" and execute and not _has_browser_handlers(input_payload):
        # Pure model-lane DAGs (scillm/subagent handlers only) must NEVER touch
        # the browser: probing availability opened webclaude tabs on every
        # claude-fable-low run (operator bug report, tab 837386031, 2026-08-12).
        browser_availability = _skipped_browser_availability("no_browser_handlers")
        _write_browser_availability(Path(str(bundle["run_dir"])), browser_availability)
    elif bundle.get("status") != "NEEDS_INTERVIEW" and execute:
        browser_availability = _probe_browser_provider_availability(
            input_payload,
            run_dir=Path(str(bundle["run_dir"])),
        )
        browser_availability = _annotate_browser_availability_cooldown(browser_availability)
        _write_browser_availability(Path(str(bundle["run_dir"])), browser_availability)
        browser_selection = _select_available_browser_handlers(input_payload, browser_availability)
        _write_browser_provider_selection(Path(str(bundle["run_dir"])), browser_selection)
        if browser_selection.get("status") == "ADJUSTED":
            input_payload = _apply_browser_provider_selection(input_payload, browser_selection)
            bundle = compile_tau_dag_bundle(input_payload)
            _write_browser_provider_selection(Path(str(bundle["run_dir"])), browser_selection)
        if not _browser_availability_blocks(browser_availability) and browser_selection.get("status") != "BLOCKED":
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
    browser_selection = browser_selection if "browser_selection" in locals() else _skipped_browser_provider_selection()
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
            elif browser_selection.get("status") == "BLOCKED":
                execution = browser_provider_selection_blocked_execution(browser_selection)
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
    if (
        isinstance(execution, dict)
        and execution.get("schema") == "ask.tau_dag_execution.v1"
        and "seam_validation" not in execution
    ):
        # Blocked-execution builders bypass run_tau_dag_bundle; enforce the
        # same typed seam contract on their output before it leaves the CLI.
        from .seam_models import enforce as _enforce_seam

        execution = _enforce_seam("ask.tau_dag_execution.v1", execution)
    # A panel that lost a requested seat must never read as a clean PASS.
    # best-practices-roundtable: a missing seat is NEEDS_ATTENTION, not silent
    # consensus (observed 2026-08-03: webgpt dropped by availability selection
    # and the run still reported PASS with four seats).
    _removed_seats = list((browser_selection or {}).get("removed_handlers") or [])
    _status = execution.get("status") if isinstance(execution, dict) else bundle.get("status")
    if _removed_seats and _status == "PASS":
        _status = "DEGRADED"
    output = {
        "schema": "ask.tau_dag_cli_result.v1",
        "removed_seats": _removed_seats or None,
        "status": _status,
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
        "browser_provider_selection": browser_selection,
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
    judge_handler: Annotated[
        str,
        typer.Option("--judge-handler", help="Independent judge seat (e.g. webgpt) reviewing all competitors."),
    ] = "",
    report_handler: Annotated[
        str,
        typer.Option("--report-handler", help="Report seat (profile/model or browser handler) writing up the winner after the join."),
    ] = "",
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
        judge_handler=judge_handler,
        report_handler=report_handler,
        handler_projects=handler_project,
        handler_workspaces=handler_workspace,
        ask_id=ask_id,
        output_root=output_root,
        local_fixture=False,
        scillm_base_url=scillm_base_url,
        scillm_api_key=scillm_api_key,
        tau_project_root=tau_project_root,
        browser_lock_timeout=browser_lock_timeout,
        # Lane execution budgets come from the per-handler envelopes in
        # _roundtable_command_timeout; deriving them from --poll-timeout-seconds
        # (default 120) starved every browser lane to a 300s wall (observed:
        # webgpt/webgrok killed mid-generation at 120s effective submit).
        execution_timeout_seconds=0,
        attachments=attach_file,
    )
    bundle = compile_tau_dag_bundle(input_payload)
    lifecycle = {"status": "skipped", "mode": browser_tab_lifecycle}
    browser_availability = _skipped_browser_availability("not_executing" if not execute else "not_checked")
    if bundle.get("status") != "NEEDS_INTERVIEW" and execute and not _has_browser_handlers(input_payload):
        # Pure model-lane DAGs (scillm/subagent handlers only) must NEVER touch
        # the browser: probing availability opened webclaude tabs on every
        # claude-fable-low run (operator bug report, tab 837386031, 2026-08-12).
        browser_availability = _skipped_browser_availability("no_browser_handlers")
        _write_browser_availability(Path(str(bundle["run_dir"])), browser_availability)
    elif bundle.get("status") != "NEEDS_INTERVIEW" and execute:
        browser_availability = _probe_browser_provider_availability(
            input_payload,
            run_dir=Path(str(bundle["run_dir"])),
        )
        browser_availability = _annotate_browser_availability_cooldown(browser_availability)
        _write_browser_availability(Path(str(bundle["run_dir"])), browser_availability)
        browser_selection = _select_available_browser_handlers(input_payload, browser_availability)
        _write_browser_provider_selection(Path(str(bundle["run_dir"])), browser_selection)
        if browser_selection.get("status") == "ADJUSTED":
            input_payload = _apply_browser_provider_selection(input_payload, browser_selection)
            bundle = compile_tau_dag_bundle(input_payload)
            _write_browser_provider_selection(Path(str(bundle["run_dir"])), browser_selection)
        if not _browser_availability_blocks(browser_availability) and browser_selection.get("status") != "BLOCKED":
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
    browser_selection = browser_selection if "browser_selection" in locals() else _skipped_browser_provider_selection()
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
            elif browser_selection.get("status") == "BLOCKED":
                execution = browser_provider_selection_blocked_execution(browser_selection)
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
    if (
        isinstance(execution, dict)
        and execution.get("schema") == "ask.tau_dag_execution.v1"
        and "seam_validation" not in execution
    ):
        # Blocked-execution builders bypass run_tau_dag_bundle; enforce the
        # same typed seam contract on their output before it leaves the CLI.
        from .seam_models import enforce as _enforce_seam

        execution = _enforce_seam("ask.tau_dag_execution.v1", execution)
    # A panel that lost a requested seat must never read as a clean PASS.
    # best-practices-roundtable: a missing seat is NEEDS_ATTENTION, not silent
    # consensus (observed 2026-08-03: webgpt dropped by availability selection
    # and the run still reported PASS with four seats).
    _removed_seats = list((browser_selection or {}).get("removed_handlers") or [])
    _status = execution.get("status") if isinstance(execution, dict) else bundle.get("status")
    if _removed_seats and _status == "PASS":
        _status = "DEGRADED"
    output = {
        "schema": "ask.tau_dag_cli_result.v1",
        "removed_seats": _removed_seats or None,
        "status": _status,
        "ok": exit_code == 0,
        "mocked": False,
        "live": bool(isinstance(execution, dict) and execution.get("live") is True)
        or bool(isinstance(browser_availability, dict) and browser_availability.get("live") is True),
        "provider_live": bool(isinstance(execution, dict) and execution.get("provider_live") is True),
        "bundle": bundle,
        "provider_gate": provider_gate,
        "execution": execution,
        "browser_provider_availability": browser_availability,
        "browser_provider_selection": browser_selection,
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


def _browser_providers_to_probe(input_payload: Any) -> list[str]:
    seen: set[str] = set()
    providers: list[str] = []
    for provider in [*_browser_handlers(input_payload), *_fallback_provider_order(str(getattr(input_payload, "request", "") or ""))]:
        if provider in BROWSER_FRESH_URLS and provider not in seen:
            seen.add(provider)
            providers.append(provider)
    return providers


def _skipped_browser_availability(reason: str) -> dict[str, Any]:
    return {
        "schema": "ask.browser_provider_availability.v1",
        "status": "skipped",
        "mocked": False,
        "live": False,
        "read_only": True,
        "reason": reason,
    }


def _skipped_browser_provider_selection() -> dict[str, Any]:
    return {
        "schema": "ask.browser_provider_selection.v1",
        "status": "skipped",
        "mocked": False,
        "live": False,
        "reason": "not_checked",
    }


def _has_browser_handlers(input_payload) -> bool:
    """True only when some seat is a browser provider (web*)."""
    from .tau_dag import ROUNDTABLE_HANDLERS

    browser = {h for h in ROUNDTABLE_HANDLERS if h.startswith("web")}
    return any(h in browser for h in getattr(input_payload, "handlers", ()) or ())


def _probe_browser_provider_availability(
    input_payload: Any,
    *,
    run_dir: Path,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    handlers = _browser_providers_to_probe(input_payload)
    if not handlers:
        report = _skipped_browser_availability("no_browser_handlers")
        _write_browser_availability(run_dir, report)
        return report

    script = Path(os.environ.get("ASK_BROWSER_AVAILABILITY_SCRIPT", str(DEFAULT_BROWSER_AVAILABILITY_SCRIPT)))
    output_path = run_dir / "browser-provider-availability.json"
    command = [sys.executable, str(script)]
    for handler in handlers:
        command.extend(["--provider", handler])
    binding_resolution = _resolve_explicit_browser_provider_tabs(input_payload, handlers)
    if binding_resolution.get("status") == "ERROR":
        report = {
            "schema": "ask.browser_provider_availability.v1",
            "status": "ERROR",
            "mocked": False,
            "live": False,
            "read_only": True,
            "error": "browser_provider_explicit_tab_resolve_failed",
            "requested_providers": handlers,
            "binding_resolution": binding_resolution,
            "path": str(output_path),
        }
        _write_browser_availability(run_dir, report)
        return report
    for item in binding_resolution.get("explicit_tab_args", []):
        command.extend(["--tab-id", str(item)])
    command.extend(["--output", str(output_path), "--max-tabs-per-provider", "2", "--json"])

    started = time.time()
    try:
        # #1307: the availability script spawns surf -> node grandchildren.
        # subprocess.run(timeout) kills only the direct child on timeout, so a
        # wedged surf/node grandchild keeps the stdout pipe open and
        # communicate() hangs PAST the timeout indefinitely (no artifact, no
        # timeout receipt). Run in a new session and hard-kill the whole
        # process group on timeout so the 180s bound actually terminates.
        proc = subprocess.Popen(
            command,
            cwd=str(ASK_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout_text, stderr_text = proc.communicate(timeout=timeout_seconds)
            command_receipt = {
                "command": command,
                "returncode": proc.returncode,
                "stdout": (stdout_text or "")[:20000],
                "stderr": (stderr_text or "")[:8000],
                "duration_seconds": round(time.time() - started, 3),
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                stdout_text, stderr_text = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                stdout_text, stderr_text = proc.communicate()
            command_receipt = {
                "command": command,
                "returncode": 124,
                "stdout": (stdout_text or "")[:20000],
                "stderr": ((stderr_text or "") + "\n[ask] browser availability probe timed out; killed process group\n")[:8000],
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
    if binding_resolution.get("explicit_tab_args"):
        report["binding_resolution"] = binding_resolution
    report["command_receipt"] = command_receipt
    if command_receipt["returncode"] != 0 and report.get("status") != "NEEDS_ATTENTION":
        report["status"] = "ERROR"
        report.setdefault("error", "browser_availability_probe_failed")
    _write_browser_availability(run_dir, report)
    return report


def _resolve_explicit_browser_provider_tabs(input_payload: Any, handlers: list[str]) -> dict[str, Any]:
    """Resolve caller-specified browser-oracle projects to exact tab ids.

    Availability probing is allowed to scan ambient tabs for default fresh
    browser lifecycle runs. It must not do that when the caller deliberately
    bound a handler to a project: an unrelated stale tab for the same provider
    must not poison the exact requested reviewer tab.
    """
    explicit_projects = _explicit_handler_projects(input_payload)
    if not explicit_projects:
        return {"schema": "ask.browser_provider_binding_resolution.v1", "status": "skipped", "explicit_tab_args": []}

    browser_oracle_run = Path(
        os.environ.get(
            "ASK_BROWSER_ORACLE_RUN",
            str(Path(__file__).resolve().parents[2].parent / "browser-oracle" / "run.sh"),
        )
    )
    explicit_tab_args: list[str] = []
    resolutions: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for handler in handlers:
        project = explicit_projects.get(handler)
        if not project:
            continue
        backend = BROWSER_BACKENDS.get(handler)
        if not backend:
            continue
        command = [
            str(browser_oracle_run),
            "resolve",
            "--backend",
            backend,
            "--project",
            project,
            "--json",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(browser_oracle_run.parent),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
            receipt = {
                "handler": handler,
                "project": project,
                "backend": backend,
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout[:4000],
                "stderr": completed.stderr[:2000],
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            receipt = {
                "handler": handler,
                "project": project,
                "backend": backend,
                "command": command,
                "returncode": 124 if isinstance(exc, subprocess.TimeoutExpired) else 127,
                "stdout": str(getattr(exc, "stdout", "") or "")[:4000],
                "stderr": str(getattr(exc, "stderr", "") or str(exc))[:2000],
            }
        tab_id = ""
        if receipt["returncode"] == 0:
            try:
                payload = json.loads(str(receipt.get("stdout") or "{}"))
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                tab_id = str(payload.get("tab_id") or payload.get("controlled_tab_id") or "").strip()
                receipt["resolved_tab_id"] = tab_id
                receipt["conversation_url"] = str(payload.get("conversation_url") or payload.get("url") or "")
        if not tab_id:
            errors.append(receipt)
        else:
            explicit_tab_args.append(f"{handler}={tab_id}")
            resolutions.append(receipt)

    return {
        "schema": "ask.browser_provider_binding_resolution.v1",
        "status": "ERROR" if errors else "READY",
        "explicit_tab_args": explicit_tab_args,
        "resolutions": resolutions,
        "errors": errors,
    }


def _explicit_handler_projects(input_payload: Any) -> dict[str, str]:
    projects: dict[str, str] = {}
    for item in list(getattr(input_payload, "handler_projects", ()) or ()):
        if "=" not in str(item):
            continue
        handler, project = str(item).split("=", 1)
        handler = handler.strip()
        project = project.strip()
        if handler in BROWSER_BACKENDS and project:
            projects[handler] = project
    return projects


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


def _select_available_browser_handlers(input_payload: Any, report: dict[str, Any]) -> dict[str, Any]:
    requested = list(getattr(input_payload, "handlers", ()) or ())
    if not any(handler in BROWSER_FRESH_URLS for handler in requested):
        return _skipped_browser_provider_selection()
    providers = report.get("providers") if isinstance(report, dict) else {}
    if not isinstance(providers, dict):
        providers = {}
    limited = {
        name
        for name, payload in providers.items()
        if isinstance(payload, dict) and payload.get("provider_limited") is True
    }
    active: list[str] = []
    removed: list[str] = []
    for handler in requested:
        if handler in BROWSER_FRESH_URLS and handler in limited:
            removed.append(handler)
        else:
            active.append(handler)

    min_handlers = _minimum_handlers_for_workflow(input_payload)
    desired_handlers = max(min_handlers, len(requested))
    fallback_added: list[str] = []
    if removed:
        for candidate in _fallback_provider_order(str(getattr(input_payload, "request", "") or "")):
            if candidate in active or candidate in requested or candidate in limited:
                continue
            payload = providers.get(candidate)
            if isinstance(payload, dict) and payload.get("probe_failed") is True:
                continue
            active.append(candidate)
            fallback_added.append(candidate)
            if len(active) >= desired_handlers:
                break

    if removed and len(active) < min_handlers:
        status = "BLOCKED"
    elif removed or fallback_added:
        status = "ADJUSTED"
    else:
        status = "READY"

    return {
        "schema": "ask.browser_provider_selection.v1",
        "status": status,
        "mocked": False,
        "live": bool(report.get("live") is True),
        "workflow_mode": str(getattr(input_payload, "workflow_mode", "") or ""),
        "minimum_handlers": min_handlers,
        "desired_handlers": desired_handlers,
        "original_handlers": requested,
        "active_handlers": active,
        "limited_providers": sorted(limited.intersection(set(requested))),
        "removed_handlers": removed,
        "fallback_handlers": fallback_added,
        "fallback_order": _fallback_provider_order(str(getattr(input_payload, "request", "") or "")),
        "failure_code": "browser_provider_rate_limited" if removed else None,
        "cooldown_seconds": 600 if removed else 0,
        "message": (
            "Provider cooldown/capacity is lane-local. Ask removed unavailable browser handlers "
            "and added available fallback handlers when the workflow still needed enough participants."
        )
        if status == "ADJUSTED"
        else "Browser provider selection did not require fallback."
        if status == "READY"
        else "Not enough available browser/API participants remain after provider cooldown filtering.",
        "next_command": (
            "Wait 600 seconds, rerun `skills/ask/run.sh browser-availability --provider <provider> --json`, "
            "then rerun only the missing provider lane or a new linked round if its contribution is still required."
        )
        if removed
        else "",
        "ticket_instruction": (
            "File a $ticket to $ask at agent-skills@main when a requested provider is unavailable and this packet "
            "does not already give enough local recovery evidence. Include browser-provider-availability.json, "
            "browser-provider-selection.json, provider name, tab id, visible text excerpt, failure_code, and the "
            "fallback handler Ask selected."
        )
        if removed
        else "",
        "ticket_command": (
            "skills/ticket/run.sh bug \"Ask browser provider unavailable during roundtable/competition\" "
            "--target skills/ask "
            "--observed \"Requested browser provider was unavailable; see browser-provider-availability.json and browser-provider-selection.json\" "
            "--expected \"Ask records the unavailable lane, selects an available fallback provider, and keeps the workflow moving\" "
            "--repro \"Run the same Ask command with the same immutable goal and provider set\" "
            "--proof \"provider availability receipt plus live Ask DAG receipt showing fallback selection\" "
            "--route backend_python_or_skill_runtime --agent coder --apply"
        )
        if removed
        else "",
    }


def _minimum_handlers_for_workflow(input_payload: Any) -> int:
    if str(getattr(input_payload, "workflow_mode", "") or "") == "compete":
        return 2
    template = str(getattr(input_payload, "dag_template", "") or "")
    if template == "roundtable":
        return 2
    return 1


def _fallback_provider_order(request: str) -> list[str]:
    configured = os.environ.get("ASK_BROWSER_FALLBACK_ORDER", "").strip()
    if configured:
        order = [item.strip() for item in configured.split(",") if item.strip()]
    else:
        lower = request.lower()
        if any(word in lower for word in ("code", "patch", "bug", "review", "diff", "implementation")):
            order = ["webclaude", "webgemini", "webkimi", "webgpt", "webgrok"]
        elif any(word in lower for word in ("current", "web", "source", "research", "search")):
            order = ["webgpt", "webgemini", "webclaude", "webkimi", "webgrok"]
        else:
            order = ["webclaude", "webgemini", "webkimi", "webgpt", "webgrok"]
    seen: set[str] = set()
    result: list[str] = []
    for handler in order:
        if handler in BROWSER_FRESH_URLS and handler not in seen:
            seen.add(handler)
            result.append(handler)
    return result


def _apply_browser_provider_selection(input_payload: Any, selection: dict[str, Any]) -> Any:
    active = tuple(str(handler) for handler in selection.get("active_handlers", []) if str(handler))
    original = list(getattr(input_payload, "handlers", ()) or ())
    original_hints = list(getattr(input_payload, "handler_provider_hints", ()) or ())
    hint_by_handler = {
        handler: original_hints[index] if index < len(original_hints) else ""
        for index, handler in enumerate(original)
    }
    return replace(
        input_payload,
        handlers=active,
        handler_provider_hints=tuple(hint_by_handler.get(handler, "") for handler in active),
    )


def _write_browser_provider_selection(run_dir: Path, selection: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "browser-provider-selection.json"
    payload = dict(selection)
    payload["path"] = str(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def browser_availability_blocked_execution(report: dict[str, Any]) -> dict[str, Any]:
    limited: list[str] = []
    providers = report.get("providers")
    if isinstance(providers, dict):
        limited = [
            name
            for name, payload in providers.items()
            if isinstance(payload, dict) and payload.get("provider_limited") is True
        ]
    failure_code = str(report.get("failure_code") or "")
    if not failure_code:
        failure_code = "browser_provider_rate_limited" if limited else "browser_provider_availability_probe_failed"
    next_command = str(report.get("next_command") or "")
    if not next_command:
        next_command = (
            "Wait for the named provider cooldown to clear, rerun `skills/ask/run.sh browser-availability "
            "--provider <provider> --json`, then rerun the Ask DAG with the same immutable goal."
        )
    message = (
        "Ask did not launch Tau or submit browser prompts because the read-only browser provider "
        "availability preflight found a visible cooldown/throttle state or could not complete."
    )
    if failure_code == "surf_browser_connection_unavailable":
        message = (
            "Ask did not launch Tau or submit browser prompts because Surf could not list Chrome tabs. "
            "This is local browser transport setup, not a provider cooldown."
        )
    ticket_instruction = str(report.get("ticket_instruction") or "")
    if not ticket_instruction:
        ticket_instruction = (
            "If this report is missing the provider, tab id, visible text excerpt, failure_code, or next_command, "
            "file a $ticket to $ask at agent-skills@main with the Ask run_dir and browser-provider-availability.json."
        )
    return {
        "schema": "ask.tau_dag_execution.v1",
        "status": "NEEDS_ATTENTION",
        "ok": False,
        "mocked": False,
        "live": bool(report.get("live") is True),
        "provider_live": False,
        "blocked_reason": "browser_provider_unavailable_preflight",
        "failure_code": failure_code,
        "recovery_kind": report.get("recovery_kind"),
        "human_action": report.get("human_action"),
        "limited_providers": limited,
        "no_tau_execution": True,
        "message": message,
        "browser_provider_availability": report,
        "next_command": next_command,
        "ticket_instruction": ticket_instruction,
    }


def browser_provider_selection_blocked_execution(selection: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "ask.tau_dag_execution.v1",
        "status": "NEEDS_ATTENTION",
        "ok": False,
        "mocked": False,
        "live": bool(selection.get("live") is True),
        "provider_live": False,
        "blocked_reason": "browser_provider_selection_insufficient_participants",
        "failure_code": selection.get("failure_code") or "browser_provider_unavailable",
        "limited_providers": selection.get("limited_providers", []),
        "active_handlers": selection.get("active_handlers", []),
        "minimum_handlers": selection.get("minimum_handlers"),
        "no_tau_execution": True,
        "message": selection.get("message"),
        "browser_provider_selection": selection,
        "next_command": selection.get("next_command"),
        "ticket_instruction": (
            "If Ask could not continue with available providers but the project has usable alternates, "
            "file a $ticket to $ask at agent-skills@main with browser-provider-availability.json and "
            "browser-provider-selection.json."
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
    # Reclaim abandoned windows before adding more. Doing this at
    # provisioning time keeps window count bounded by concurrent runs rather
    # than by total runs ever executed.
    window_reap = _reap_stale_ask_windows(surf_run)
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
    # One unfocused window per browser seat. Chrome reports
    # document.visibilityState "hidden" for every tab that is not the selected
    # tab of its window, and providers defer DOM updates while hidden - which
    # is why N seats sharing one window left exactly one seat unthrottled and
    # the rest timing out. Measured 2026-08-03: a tab alone in an unfocused
    # window reports visible/hidden=false, while a non-selected tab in a shared
    # window reports hidden=true.
    for handler in browser_handlers:
        project = f"{lifecycle_id}-{handler}"
        window_command = [
            str(surf_run),
            "window.new",
            BROWSER_FRESH_URLS[handler],
            "--json",
            "--unfocused",
            "--lock-timeout",
            str(lock_timeout_seconds),
        ]
        # Snapshot before creating: wmctrl output order is not creation order,
        # so the diff is the only reliable way to identify the window we made.
        pre_windows = _chrome_window_snapshot(browser_oracle_run)
        window = _lifecycle_command(
            window_command, cwd=surf_run.parent, timeout_seconds=command_timeout_seconds
        )
        commands.append(window)
        if window["returncode"] == 0:
            # Land seat windows on the reviewer desktop instead of scattering
            # them across whichever desktop the human is working on.
            placement = _place_seat_window(browser_oracle_run, pre_windows)
            if placement:
                commands.append(placement)
        if window["returncode"] != 0:
            # Provisioning can fail transiently while the host settles a
            # previous run's teardown; one bounded retry before failing closed.
            time.sleep(10)
            window = _lifecycle_command(
                window_command, cwd=surf_run.parent, timeout_seconds=command_timeout_seconds
            )
            commands.append(window)
        if window["returncode"] != 0:
            lifecycle = _lifecycle_blocked(
                mode, run_dir, f"{handler}_window_create_failed", commands, created_tabs
            )
            _write_lifecycle(run_dir, lifecycle)
            return lifecycle
        payload = _json_or_text(window["stdout"])
        seat_window_id = _extract_window_id(payload)
        seat_tab_id = _extract_tab_id(payload)
        if not seat_tab_id:
            lifecycle = _lifecycle_blocked(
                mode, run_dir, f"{handler}_window_missing_tab_id", commands, created_tabs
            )
            _write_lifecycle(run_dir, lifecycle)
            return lifecycle
        created_tabs.append(
            {
                "handler": handler,
                "project": project,
                "tab_id": seat_tab_id,
                "url": BROWSER_FRESH_URLS[handler],
                "window_id": seat_window_id,
            }
        )
        _replace_handler_project(handler_projects, handler, project)
    window_id = created_tabs[0].get("window_id") if created_tabs else None
    # Register before the identity guard and before any provider work: from
    # here on the run can be killed at any point, and an unregistered window
    # is one nothing will ever reclaim.
    _register_ask_windows({"created_tabs": created_tabs, "mode": mode, "run_dir": str(run_dir)})

    # Provisioning-to-gate identity guard (#1139): the handler gate resolves
    # these ids minutes later through tab.list; twice a run's freshly created
    # tabs were already gone by then, blocking pre-provider with no clue when
    # they vanished. Re-verify each id NOW through the same entrypoint; a
    # missing tab gets ONE recreate, then the run blocks with the mismatch
    # named at the moment it exists.
    identity_guard = _verify_created_tabs(
        surf_run,
        created_tabs,
        commands=commands,
        lock_timeout_seconds=lock_timeout_seconds,
        window_id=window_id,
    )
    if identity_guard.get("blocked"):
        lifecycle = _lifecycle_blocked(
            mode, run_dir, "tab_vanished_after_creation", commands, created_tabs, window_id=window_id
        )
        lifecycle["identity_guard"] = identity_guard
        _write_lifecycle(run_dir, lifecycle)
        return lifecycle
    verified_identity_guard = identity_guard

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
        "window_reap": window_reap,
        "window_id": window_id,
        "identity_guard": verified_identity_guard,
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


_RECOVERABLE_LANE_FAILURE_CODES = {
    "browser_handler_timeout",
    "missing_sentinel",
    "webgpt_missing_sentinel",
}


def _lanes_pending_recovery(run_dir: Path) -> list[dict[str, Any]]:
    """Lanes whose in-tab state may still hold the provider response.

    A lane pends recovery when its node receipt is absent or non-PASS and
    either its recovery packet names a recoverable failure class or its
    heartbeat proves the prompt was actually submitted. Closing the lane's
    tab in that state destroys the only copy of the response.
    """
    pending: list[dict[str, Any]] = []
    for lane_dir in sorted((run_dir / "node-artifacts").glob("handler-*")):
        receipt = _read_json_file(lane_dir / "node-receipt.json")
        if isinstance(receipt, dict) and str(receipt.get("status") or "") == "PASS":
            continue
        packet = _read_json_file(lane_dir / "browser-recovery-packet.json")
        heartbeat = _read_json_file(lane_dir / "webgpt_heartbeat.json")
        failure_code = str(packet.get("failure_code") or "") if isinstance(packet, dict) else ""
        submitted = bool(isinstance(heartbeat, dict) and heartbeat.get("submitted_at"))
        if failure_code in _RECOVERABLE_LANE_FAILURE_CODES or submitted:
            pending.append(
                {
                    "lane": lane_dir.name,
                    "failure_code": failure_code or None,
                    "heartbeat_submitted_at": (heartbeat or {}).get("submitted_at")
                    if isinstance(heartbeat, dict)
                    else None,
                    "next_command": (packet or {}).get("next_command")
                    if isinstance(packet, dict)
                    else None,
                }
            )
    return pending


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _verify_created_tabs(
    surf_run: Path,
    created_tabs: list[dict[str, Any]],
    *,
    commands: list[dict[str, Any]],
    lock_timeout_seconds: int,
    window_id: str | None,
) -> dict[str, Any]:
    """Verify every created tab id via tab.list; recreate a missing tab once."""

    def live_ids() -> set[str] | None:
        listing = _lifecycle_command(
            [str(surf_run), "tab.list", "--json"],
            cwd=surf_run.parent,
            timeout_seconds=60,
        )
        commands.append(listing)
        if listing["returncode"] != 0:
            return None
        payload = _json_or_text(listing["stdout"])
        if not isinstance(payload, list):
            return None
        return {str(t.get("id")) for t in payload if isinstance(t, dict)}

    ids = live_ids()
    if ids is None:
        # Cannot verify: do not block on the guard's own failure; the gate
        # will re-check later exactly as before.
        return {"status": "UNVERIFIED", "blocked": False}
    guard: dict[str, Any] = {"status": "PASS", "blocked": False, "checks": []}
    for tab in created_tabs:
        tab_id = str(tab.get("tab_id"))
        if tab_id in ids:
            guard["checks"].append({"tab_id": tab_id, "handler": tab.get("handler"), "present": True})
            continue
        recreate_cmd = [str(surf_run), "tab.new", str(tab.get("url")), "--json", "--background"]
        if window_id:
            recreate_cmd.extend(["--window-id", str(window_id)])
        recreate_cmd.extend(["--lock-timeout", str(lock_timeout_seconds)])
        recreated = _lifecycle_command(recreate_cmd, cwd=surf_run.parent, timeout_seconds=120)
        commands.append(recreated)
        new_id = _extract_tab_id(_json_or_text(recreated["stdout"])) if recreated["returncode"] == 0 else ""
        ids_after = live_ids() or set()
        if new_id and new_id in ids_after:
            guard["checks"].append(
                {
                    "tab_id": tab_id,
                    "handler": tab.get("handler"),
                    "present": False,
                    "action": "recreated",
                    "new_tab_id": new_id,
                }
            )
            tab["tab_id"] = new_id
            tab["recreated_from"] = tab_id
            guard["status"] = "SELF_HEALED"
            continue
        guard["checks"].append(
            {
                "tab_id": tab_id,
                "handler": tab.get("handler"),
                "present": False,
                "action": "recreate_failed",
                "recreate_returncode": recreated["returncode"],
            }
        )
        guard["status"] = "BLOCKED"
        guard["blocked"] = True
    return guard


# Windows Ask created but never got to close: the owning process was killed
# before its `finally` ran, or the run used fresh-keep and nobody came back.
# Eight provider windows were live on 2026-08-04, the oldest from a batch run
# on 2026-07-27 -- a permanent leak, because a skipped cleanup had no expiry
# and no second chance. The registry makes ownership durable so a later run
# can reclaim what an earlier one abandoned.
ASK_WINDOW_REGISTRY = Path.home() / ".ask" / "browser-windows.jsonl"
# fresh-keep exists so a human can inspect the tabs. Four hours is long past
# the end of any session that would have looked.
FRESH_KEEP_TTL_SECONDS = 4 * 3600
FRESH_TEMPORARY_TTL_SECONDS = 900


def _register_ask_windows(lifecycle: dict[str, Any]) -> None:
    """Record window ownership durably, before the run can be killed."""
    windows = [
        str(tab.get("window_id"))
        for tab in lifecycle.get("created_tabs", [])
        if isinstance(tab, dict) and tab.get("window_id")
    ]
    if not windows:
        return
    try:
        ASK_WINDOW_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        with ASK_WINDOW_REGISTRY.open("a", encoding="utf-8") as handle:
            for window_id in dict.fromkeys(windows):
                handle.write(
                    json.dumps(
                        {
                            "window_id": window_id,
                            "mode": str(lifecycle.get("mode") or ""),
                            "run_dir": str(lifecycle.get("run_dir") or ""),
                            "pid": os.getpid(),
                            "created_at": time.time(),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
    except OSError:
        # A registry write must never take the run down; the worst case is
        # the pre-existing leak, not a failed roundtable.
        pass


def _deregister_ask_windows(window_ids: set[str]) -> None:
    if not window_ids or not ASK_WINDOW_REGISTRY.is_file():
        return
    try:
        kept: list[str] = []
        for line in ASK_WINDOW_REGISTRY.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if str((entry or {}).get("window_id") or "") not in window_ids:
                kept.append(line)
        ASK_WINDOW_REGISTRY.write_text(
            "".join(line + "\n" for line in kept), encoding="utf-8"
        )
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _reap_stale_ask_windows(surf_run: Path, *, timeout_seconds: int = 60) -> dict[str, Any]:
    """Close Ask-created windows whose run is over, before opening more.

    Reaping runs at provisioning time rather than on a timer: that is the
    moment Ask is about to add windows, so it is exactly when reclaiming old
    ones matters and when the surf transport is known to be up.

    A window is reclaimed only when its owning process is gone AND its mode's
    TTL has passed, so a concurrent roundtable never has its seats closed out
    from under it.
    """
    receipt: dict[str, Any] = {"schema": "ask.window_reap.v1", "closed": [], "kept": []}
    if not ASK_WINDOW_REGISTRY.is_file():
        return receipt
    try:
        raw_lines = ASK_WINDOW_REGISTRY.read_text(encoding="utf-8").splitlines()
    except OSError:
        return receipt
    entries: list[dict[str, Any]] = []
    for line in raw_lines:
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except ValueError:
            continue
        if isinstance(loaded, dict):
            entries.append(loaded)

    now = time.time()
    reaped: set[str] = set()
    for entry in entries:
        window_id = str(entry.get("window_id") or "")
        if not window_id or window_id in reaped:
            continue
        pid = entry.get("pid")
        age = now - float(entry.get("created_at") or 0)
        ttl = (
            FRESH_KEEP_TTL_SECONDS
            if str(entry.get("mode") or "") == "fresh-keep"
            else FRESH_TEMPORARY_TTL_SECONDS
        )
        owner_alive = _pid_alive(int(pid)) if isinstance(pid, int) else False
        if owner_alive or age < ttl:
            receipt["kept"].append(
                {
                    "window_id": window_id,
                    "reason": "owner_alive" if owner_alive else "within_ttl",
                    "age_seconds": int(age),
                }
            )
            continue
        result = _lifecycle_command(
            [str(surf_run), "window.close", window_id],
            cwd=surf_run.parent,
            timeout_seconds=timeout_seconds,
        )
        reaped.add(window_id)
        receipt["closed"].append(
            {
                "window_id": window_id,
                "mode": entry.get("mode"),
                "age_seconds": int(age),
                "returncode": result.get("returncode"),
                "run_dir": entry.get("run_dir"),
            }
        )
    # A window that is already gone still deregisters: the registry tracks
    # outstanding obligations, and a failed close on a closed window is done.
    _deregister_ask_windows(reaped)
    return receipt


# Desktop 2 by default: Ask's browser seats are reviewer windows, not windows
# the human asked for, so they belong on the reviewer desktop rather than on
# top of whatever is being worked on. ASK_REVIEWER_DESKTOP overrides; empty
# disables placement entirely.
DEFAULT_REVIEWER_DESKTOP = "1"  # wmctrl index 1 == Desktop 2


def _reviewer_desktop() -> str:
    return os.environ.get("ASK_REVIEWER_DESKTOP", DEFAULT_REVIEWER_DESKTOP)


def _chrome_window_snapshot(browser_oracle_run: Path) -> list[str]:
    """Chrome windows before Ask creates one; empty list on any failure."""
    if not _reviewer_desktop():
        return []
    try:
        completed = subprocess.run(
            [str(browser_oracle_run), "window-snapshot", "--json"],
            capture_output=True, text=True, timeout=30, check=False,
            cwd=str(Path(browser_oracle_run).parent),
        )
        if completed.returncode != 0:
            return []
        payload = json.loads(completed.stdout)
        windows = payload.get("windows")
        return [str(w) for w in windows] if isinstance(windows, list) else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def _place_seat_window(browser_oracle_run: Path, before: list[str]) -> dict[str, Any] | None:
    """Move the seat window to the reviewer desktop.

    Placement is cosmetic: it must never fail a run, so every error path
    returns a recorded command entry rather than raising.
    """
    desktop = _reviewer_desktop()
    if not desktop:
        return None
    return _lifecycle_command(
        [
            str(browser_oracle_run), "place-window",
            "--before", ",".join(before),
            "--desktop", desktop,
            "--json",
        ],
        cwd=Path(browser_oracle_run).parent,
        timeout_seconds=60,
    )


def _cleanup_browser_lifecycle(lifecycle: dict[str, Any]) -> None:
    if lifecycle.get("cleanup_status") == "attempted":
        return
    if lifecycle.get("status") not in {"READY", "BLOCKED"} or lifecycle.get("mode") != "fresh-temporary":
        return
    run_dir = Path(str(lifecycle.get("run_dir") or ""))
    if run_dir.is_dir():
        pending = _lanes_pending_recovery(run_dir)
        if pending:
            lifecycle["cleanup"] = []
            lifecycle["cleanup_status"] = "skipped_pending_recovery"
            lifecycle["pending_recovery_lanes"] = pending
            lifecycle["cleanup_policy_note"] = (
                "Created window/tabs were kept open: one or more lanes failed in a "
                "state whose response may only exist in-tab. Run each lane's "
                "recovery next_command (or the provider extract) before closing."
            )
            _write_lifecycle(run_dir, lifecycle)
            return
    surf_run = Path(str(lifecycle.get("surf_run") or (Path(__file__).resolve().parents[2].parent / "surf" / "run.sh")))
    cleanup: list[dict[str, Any]] = []
    # Every seat now owns an unfocused window, so teardown closes each of them.
    # Closing only the first window would strand one live provider window per
    # seat per run - the sprawl that made the shared browser unusable.
    seat_windows = [
        str(tab.get("window_id"))
        for tab in lifecycle.get("created_tabs", [])
        if isinstance(tab, dict) and tab.get("window_id")
    ]
    seat_windows = list(dict.fromkeys(seat_windows))
    if seat_windows:
        lock_timeout_seconds = int(lifecycle.get("lock_timeout_seconds") or DEFAULT_BROWSER_SUBMIT_TIMEOUT_SECONDS)
        for seat_window in seat_windows:
            cleanup.append(
                _lifecycle_command(
                    [str(surf_run), "window.close", seat_window, "--lock-timeout", str(lock_timeout_seconds)],
                    cwd=surf_run.parent,
                    timeout_seconds=lock_timeout_seconds + BROWSER_COMMAND_GRACE_SECONDS,
                )
            )
        lifecycle["cleanup"] = cleanup
        lifecycle["cleanup_status"] = "attempted"
        _deregister_ask_windows(set(seat_windows))
        run_dir = Path(str(lifecycle.get("run_dir") or ""))
        if run_dir:
            _write_lifecycle(run_dir, lifecycle)
        return
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
    from .seam_models import enforce as _enforce_seam

    # Typed seam contract: a malformed lifecycle receipt raises at the
    # producer instead of feeding the handler gate garbage.
    lifecycle = _enforce_seam("ask.browser_tab_lifecycle.v1", lifecycle)
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
