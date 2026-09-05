"""Bounded per-issue dispatch handlers.

Purpose
    Execute exactly one bounded unit of work for one leased GitHub issue, then
    hand back a receipt fragment. Handlers never loop, never retry, and never
    decide what to work on next — ``registry`` selects, ``commands`` sequences.

Inputs
    A run id, a receipt directory, the registered project entry, and the issue
    payload returned by ``gh issue list --json``.

Outputs
    A result dictionary appended to the tick receipt's ``handled_issues`` list,
    plus artifacts written under the receipt directory.

Failure modes
    - Malformed issue directives return ``status=BLOCKED`` without mutating
      GitHub.
    - A settled machine failure returns NEEDS_ATTENTION, retains scoped work,
      and releases only its owned native lease; it does not add human holds.
    - Every path is derived from the registered project worktree, so a handler
      cannot act on a repository it was not dispatched for.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from . import config, github, registry
from .core import iso_now, log_event, run_cmd, write_json
from .issue_fields import (
    parse_bool,
    parse_goal_hash,
    parse_issue_fields,
    parse_positive_int,
    repo_relative_existing_path,
)
from .registry import project_repo, project_worktree, worktree_readiness


def handle_issue(run_id: str, receipt_dir: Path, project: dict[str, Any], issue: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    routes = {"ticket_repair": handle_ticket_repair,
              "tau_handoff_dispatch": handle_tau_handoff_dispatch,
              "add_tau_coder_command_spec": handle_tau_coder_spec}
    handler = routes.get(issue.get("watchdog_action"))
    if handler is None:
        return {**_new_result(project, issue, str(issue.get("watchdog_action"))),
                "ok": False, "status": "BLOCKED", "summary": "unregistered watchdog action"}
    try:
        return handler(run_id, receipt_dir, project, issue, apply=apply)
    except (KeyError, RuntimeError, ValueError, OSError) as exc:
        from . import primary
        return primary.failure(project, issue, str(exc), human=getattr(exc, "human", False))


def _new_result(project: dict[str, Any], issue: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "project_id": project.get("project_id"),
        "repo": project_repo(project),
        "issue_number": int(issue["number"]),
        "issue_url": str(issue["url"]),
        "selected_agent": None,
        "action": action,
        "ok": False,
        "commands": [],
        "artifacts": [],
    }


def handle_tau_handoff_dispatch(run_id: str, receipt_dir: Path, project: dict[str, Any],
                                issue: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    """Existing approved Tau CLI, now under the shared primary/lease/review boundary."""
    from . import primary
    # Parse the original directive before dispatch, including containment and bounds.
    fields = parse_issue_fields(issue.get("body") or "")
    root = project_worktree(project)
    start = repo_relative_existing_path(fields["start"], worktree=root)
    parse_positive_int(fields.get("max_steps", "1"), field="max_steps")
    parse_goal_hash(fields.get("active_goal_hash", config.TAU_ACTIVE_GOAL_HASH))
    parse_bool(fields.get("apply_transport", "false"), field="apply_transport")
    routed = dict(issue, watchdog_action="tau_handoff_dispatch")
    targets = registry.issue_targets(issue)
    if targets == {registry.UNKNOWN_TARGET}:
        # This historical route already authorizes its command-spec overlay, not repo root.
        # A broader command's explicit write targets must still be supplied by the issue.
        targets = {"experiments/goal-locked-subagents/agent-command-specs"}
    routed["watchdog_targets"] = sorted(targets)
    return primary.dispatch(run_id, receipt_dir, project, routed, _handle_ticket_repair_primary, apply=apply)


def handle_tau_coder_spec(run_id: str, receipt_dir: Path, project: dict[str, Any],
                          issue: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    from . import primary
    root = project_worktree(project).resolve()
    routed = dict(issue, watchdog_action="add_tau_coder_command_spec",
                  watchdog_targets=[str(tau_coder_spec_path(root).relative_to(root))])
    return primary.dispatch(run_id, receipt_dir, project, routed, _handle_ticket_repair_primary, apply=apply)


def tau_coder_spec_path(worktree: Path) -> Path:
    return (
        worktree
        / "experiments/goal-locked-subagents/agent-command-specs/coder/tau-dispatch-command.json"
    )


def tau_coder_command_spec(uv_bin: str) -> dict[str, Any]:
    return {
        "command": [
            uv_bin,
            "run",
            "tau",
            "handoff-agent-adapter",
            "--result-status",
            "COMPLETED",
            "--result-summary",
            "Coder consumed the Tau handoff JSON contract through the Tau-owned "
            "command-spec overlay.",
            "--next-agent",
            "human",
            "--next-executor",
            "human",
            "--next-reason",
            "Human review is required after this bounded watchdog repair proof.",
            "--required-evidence",
            "Human reviews the watchdog receipt, Tau command-loop receipt, pushed commit, "
            "and issue comment.",
            "--stop-condition",
            "Human accepts, redirects, or requests another bounded subagent.",
        ],
        "cwd": ".",
        "timeout_s": 30,
    }


def tau_coder_start_handoff(
    repo: str,
    issue_number: int,
    issue_url: str,
    coder_spec: Path,
) -> dict[str, Any]:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": {
            "repo": repo,
            "target": f"issue#{issue_number}",
            "current_labels": [config.READY_LABEL, "next:coder", "executor:local"],
        },
        "goal": {
            "goal_id": "goal-project-watchdog-live-coder-spec",
            "goal_version": 1,
            "goal_hash": config.TAU_ACTIVE_GOAL_HASH,
        },
        "previous_subagent": "coder",
        "context": {
            "summary": (
                "Project watchdog found Tau allows coder routes but lacks a coder "
                "command-spec overlay."
            ),
            "artifacts": [issue_url, str(coder_spec)],
        },
        "result": {
            "status": "NEEDS_AGENT",
            "summary": (
                "Coder command-spec overlay is required for Tau cron to dispatch next:coder issues."
            ),
            "evidence": [f"Missing before repair: {coder_spec}"],
        },
        "rationale": (
            "Tau's command-loop cannot run a selected coder subagent without a "
            "command-spec overlay."
        ),
        "next_agent": {
            "name": "coder",
            "executor": "local",
            "reason": "Coder should consume the handoff and route to reviewer for validation.",
        },
        "required_evidence": [
            "Coder command-spec overlay exists.",
            "Tau command-loop selects coder and emits a schema-valid next handoff.",
        ],
        "stop_condition": "Coder routes to reviewer or Tau fails closed.",
    }


#: runner_kind values this generic handler knows how to drive.
#: Kept as the module-level default for tests; the live values come from
#: ``config.repair_creator``/``config.repair_reviewer`` so a project can name its
#: own seats (agent-skills#1086).
REPAIR_REVIEWER_HANDLER = config.DEFAULT_REPAIR_REVIEWER


def repair_immutable_goal(repo: str, issue_number: int) -> str:
    return (f"Repair {repo}#{issue_number} only in the registered PRIMARY checkout on main. "
            "Preserve existing work. No worktree or branch creation/removal, reset, stash, rebase, "
            "merge, force, push or issue closure. Modify only authorized target paths. "
            "Prove the actual acceptance criteria without weakening tests. Tau owns execution "
            "and proof; ticket owns verified integration and closure; watchdog only schedules.")


def _ticket_repair_execution_timeout(project: dict[str, Any]) -> int:
    """Ask/Tau per-node timeout for creator/reviewer repair lanes."""
    configured = int(
        project.get("ticket_repair_execution_timeout_s")
        or project.get("ticket_repair_node_timeout_s")
        or 0
    )
    if configured <= 0:
        configured = min(int(project.get("ticket_repair_timeout_s", 1800)), 3600)
    return max(300, min(configured, 3600))


def build_repair_task(
    *,
    repo: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    targets: list[str],
) -> str:
    """The prose task $ask compiles into the creator-reviewer DAG.

    The whole ticket body goes in: it carries the orientation block, required
    context files and proof command that a cron-dispatched agent with no prior
    session needs.
    """
    return (
        f"Repair {repo}#{issue_number}: {issue_title}\n\n"
        f"Allowed paths: {', '.join(targets) or '(as stated in the ticket)'}\n\n"
        f"Work only on primary main. Do not update local HEAD or the shared index. "
        f"Use the supplied scoped content-commit helper; do not publish or close.\n\n"
        f"The creator implements the scoped fix and records its content commit. The reviewer seat "
        f"checks whether the code works, whether the ticket's acceptance criterion "
        f"and required proof are satisfied, and whether the changed files comply "
        f"with the ticket's required best-practices-* skills. Nits are not a "
        f"blocking verdict unless they change correctness, proof, safety, or the "
        f"named best-practices contract. The reviewer answers VERDICT: PASS, "
        f"VERDICT: FAIL, or VERDICT: NEEDS_ATTENTION.\n\n"
        f"The verdict must be on a line of its own. VERDICT: PASS is review, not closure, "
        f"and is permitted only when the ticket's proof command has actually run "
        f"and its artifact reads as a completed pass -- name the artifact path in "
        f"the review. A proof that is still running, that failed, or that was not "
        f"run is VERDICT: NEEDS_ATTENTION.\n\n"
        f"--- ticket body ---\n{issue_body}"
    )


def acquire_lease(run_id: str, result: dict[str, Any], repo: str, issue_number: int) -> bool:
    """Apply the lease label, and report whether it actually took.

    The lease is the ONLY thing stopping a later tick from dispatching a second
    repair on the same ticket, so a lease that silently failed is worse than no
    lease attempt at all -- the guard reads the ticket as free.

    Observed 2026-07-28: neither ``agent-active`` nor ``agent-blocked`` existed
    as a label in grahama1970/agent-skills, so every ``gh issue edit
    --add-label`` exited nonzero, the lease comment posted regardless, and the
    dispatch went ahead unleased. Nothing checked the exit code.
    """
    lease = github.issue_edit(repo, issue_number, add=[config.LEASE_LABEL])
    result["commands"].append(lease)
    if lease.get("exit_code") == 0:
        return True
    result.update(
        {
            "ok": False,
            "status": "BLOCKED",
            "summary": (
                f"could not apply {config.LEASE_LABEL!r} to {repo}#{issue_number}: "
                f"{str(lease.get('stderr'))[:200]}. Not dispatching unleased -- nothing "
                f"would stop the next tick starting a second repair on the same ticket. "
                f"Run: skills/ticket/run.sh ensure-labels --repo {repo}"
            ),
        }
    )
    log_event(run_id, "lease_failed", issue=issue_number, stderr=lease.get("stderr"))
    return False


def issue_goal_hash(repo: str, issue_number: int) -> str:
    """Derive a stable per-issue goal hash.

    Tau requires ``goal.goal_hash`` to be identical across every node, receipt,
    and rerun for one workflow. Deriving it from repo and issue number makes it
    reproducible on resume without storing extra state.
    """
    digest = hashlib.sha256(f"{repo}#{issue_number}".encode()).hexdigest()
    return f"sha256:{digest}"


TAU_STREAM_TERMINAL_STATUSES = frozenset(
    {"PASS", "FAIL", "FAILED", "ERROR", "DEGRADED", "BLOCKED", "NEEDS_ATTENTION", "COMPLETED", "LANDED"}
)


def _json_from_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _jsonl_stats(path: Path) -> dict[str, Any]:
    stats: dict[str, Any] = {"path": str(path), "line_count": 0}
    latest: dict[str, Any] | None = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                stats["line_count"] += 1
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    latest = parsed
    except OSError as exc:
        stats["error"] = str(exc)
        return stats
    if latest is not None:
        stats["latest"] = latest
        for key in ("event_id", "id", "timestamp", "ts", "status", "stage", "node", "node_id"):
            if key in latest:
                stats[f"latest_{key}"] = latest[key]
    return stats


def _settled_semantic_refusal(plan_path: Path, expected: set[str]) -> dict[str, Any] | None:
    """A native semantic rejection stops before downstream nodes are launched.

    This admits failure settlement only, never success or cancelled/unknown
    execution. Missing downstream receipts are expected after this exact stop.
    """
    plan = _json_from_file(plan_path) or {}
    root = plan_path.parent
    native = _json_from_file(root / "tau-receipts/dag-receipt.json") or {}
    progress = _json_from_file(root / "tau-receipts/dag-progress.json") or {}
    execution = _json_from_file(root / "execution-status.json") or {}
    states = native.get("node_terminal_states") or {}
    dispatches = native.get("dispatches") or []
    events = native.get("scheduler_events") or []
    alerts = native.get("alerts") or []
    goal = plan.get("goal")
    if not isinstance(goal, dict) or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(goal.get("goal_hash", ""))):
        return None
    if not isinstance(states, dict) or not all(isinstance(v, str) for v in states.values()):
        return None
    if not all(isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
               for rows in (dispatches, events, alerts)):
        return None
    if not (
        plan.get("schema") == "tau.dag_contract.v1"
        and isinstance(plan.get("dag_id"), str) and bool(plan["dag_id"])
        and native.get("schema") == "tau.dag_receipt.v1"
        and progress.get("schema") == "tau.dag_progress.v1"
        and execution.get("schema") == "ask.tau_dag_execution.v1"
        and native.get("status") == execution.get("status") == progress.get("status") == "BLOCKED"
        and native.get("durable") is True
        and native.get("dag_id") == progress.get("dag_id") == plan.get("dag_id")
        and native.get("active_goal_hash") == (plan.get("goal") or {}).get("goal_hash")
        and native.get("contract_sha256") == "sha256:" + hashlib.sha256(plan_path.read_bytes()).hexdigest()
        and execution.get("receipt") == native
        and progress.get("active_subagents") == []
        and expected and set(states) == expected
        and set(states.values()) <= {"pending", "blocked", "completed"}
        and dispatches and all(d.get("status") == "COMPLETED" and d.get("stop_reason") == "response_consumed" for d in dispatches)
        and alerts and all(a.get("code") == "evidence_receipt_verdict_failed" for a in alerts)
        and events and events[-1].get("event") == "scheduler_finished"
    ):
        return None
    return {"path": str(root / "tau-receipts/dag-receipt.json"),
            "failure_code": "evidence_receipt_verdict_failed",
            "dag_error": native.get("dag_error")}


class _CompileStopObservation(BaseModel):
    """Strict watchdog observation of an Ask rejection before DAG emission."""
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["BLOCKED"]
    failure_code: Literal["ask_handler_binding_invalid"]
    exit_code: int
    process_running: bool
    timed_out: bool
    provider_live: bool
    execution: None

    @model_validator(mode="after")
    def stopped_without_execution(self) -> "_CompileStopObservation":
        if self.exit_code != 2 or self.process_running or self.timed_out or self.provider_live:
            raise ValueError("not a completed pre-dispatch refusal")
        return self


def _compile_stop(ask_run_dir: Path) -> dict[str, Any] | None:
    monitor = _json_from_file(ask_run_dir.parent / "tau-stream-monitor.json")
    output = _json_from_file(ask_run_dir.parent / "tau-stream-monitor.stdout.log")
    if not monitor or not output or output.get("schema") != "ask.tau_dag_cli_result.v1":
        return None
    bundle = output.get("bundle")
    if not isinstance(bundle, dict) or bundle.get("status") != "BLOCKED":
        return None
    try:
        _CompileStopObservation.model_validate({
            "status": output["status"], "failure_code": bundle["failure_code"],
            "exit_code": monitor["process_exit_code"], "process_running": monitor["process_running"],
            "timed_out": monitor["timed_out"], "provider_live": output["provider_live"],
            "execution": output["execution"],
        })
        root = Path(bundle["run_dir"]).resolve()
        request = Path(bundle["request_path"]).resolve()
        if (root.parent != ask_run_dir.resolve() or request != root / "request.json"
                or Path(monitor["ask_run_dir"]).resolve() != ask_run_dir.resolve()):
            return None
        if (root / "dag.json").exists() or (root / "node-artifacts").exists():
            return None
        if _json_from_file(root / "compile-status.json") != bundle:
            return None
        requested = _json_from_file(request) or {}
        goal = requested.get("goal")
        task = (ask_run_dir.parent / "repair-task.md").read_text(encoding="utf-8")
        if (requested.get("schema") != "ask.tau_dag_request.v1"
                or requested.get("request") != task or not task.strip()
                or not isinstance(goal, dict)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(goal.get("goal_hash", "")))):
            return None
    except (KeyError, TypeError, ValueError, ValidationError, OSError):
        return None
    return {"path": str(root / "compile-status.json"), "failure_code": bundle["failure_code"],
            "binding_errors": bundle.get("binding_errors", [])}


def inspect_tau_stream(ask_run_dir: Path) -> dict[str, Any]:
    """Read Ask/Tau stream artifacts into one watchdog status snapshot."""
    record: dict[str, Any] = {
        "schema": "agent_skills.project_watchdog.tau_stream_monitor.v1",
        "checked_at": iso_now(),
        "ask_run_dir": str(ask_run_dir),
        "stream_readable": False,
        "terminal": False,
        "terminal_status": None,
        "current_node": None,
        "current_status": None,
        "event_count": 0,
        "event_files": [],
        "progress_files": [],
        "node_receipts": [],
        "reason": "no Ask/Tau stream artifacts observed",
    }
    if not ask_run_dir.exists():
        return record
    if refusal := _compile_stop(ask_run_dir):
        record.update(terminal=True, terminal_status="BLOCKED", current_status="BLOCKED",
                      stream_readable=True, terminal_source=refusal["path"], compile_refusal=refusal,
                      reason="Ask rejected the binding before DAG emission; process exit verified")
        return record

    for event_path in sorted(ask_run_dir.glob("**/events.jsonl")):
        stats = _jsonl_stats(event_path)
        record["event_files"].append(stats)
        record["event_count"] += int(stats.get("line_count") or 0)
        latest = stats.get("latest")
        if isinstance(latest, dict):
            record["latest_event"] = latest

    for progress_path in sorted(ask_run_dir.glob("**/dag-progress.json")):
        progress = _json_from_file(progress_path)
        item: dict[str, Any] = {"path": str(progress_path), "readable": progress is not None}
        if progress:
            item["status"] = progress.get("status") or progress.get("verdict") or progress.get("state")
            item["current_node"] = (
                progress.get("current_node")
                or progress.get("active_node")
                or progress.get("node_id")
                or next((n.get("node_id") for n in progress.get("active_subagents", []) if isinstance(n, dict)), None)
            )
            if type(progress.get("event_count")) is int:
                record["event_count"] = max(record["event_count"], progress["event_count"])
            if isinstance(progress.get("last_event"), dict):
                record["latest_event"] = progress["last_event"]
        record["progress_files"].append(item)

    for receipt_path in sorted(ask_run_dir.glob("**/node-receipt.json")):
        receipt = _json_from_file(receipt_path)
        item: dict[str, Any] = {"path": str(receipt_path), "readable": receipt is not None}
        if receipt:
            item["status"] = receipt.get("status") or receipt.get("verdict") or receipt.get("state")
            item["node_id"] = receipt.get("node_id") or receipt_path.parent.name
            if receipt.get("failure_code"):
                item["failure_code"] = receipt["failure_code"]
            provider = receipt.get("provider_receipt")
            if isinstance(provider, dict):
                item["provider_transport"] = provider.get("provider_transport")
        record["node_receipts"].append(item)

    candidates: list[dict[str, Any]] = []
    candidates.extend(record["node_receipts"])
    candidates.extend(record["progress_files"])  # Run status outranks an individual node.
    for item in reversed(candidates):
        status = item.get("status")
        if status is not None:
            record["current_status"] = str(status)
            record["current_node"] = item.get("current_node") or item.get("node_id")
            break

    aggregate = [item for item in record["progress_files"] if item.get("readable")]
    statuses = {str(item.get("status", "")).upper() for item in aggregate}
    nodes = record["node_receipts"]
    nodes_settled = bool(nodes) and all(n.get("readable") and
        str(n.get("status", "")).upper() in (TAU_STREAM_TERMINAL_STATUSES | {"SKIPPED", "CANCELLED"}) for n in nodes)
    # Missing nodes are not terminal. Use the native DAG's declared node set,
    # not just whichever node receipt happened to arrive first.
    plans = sorted(ask_run_dir.glob("**/dag.json"))
    expected = set()
    if len(plans) == 1:
        plan = _json_from_file(plans[0]) or {}
        expected = {str(node["id"]) for node in plan.get("nodes", [])
                    if isinstance(node, dict) and node.get("id")}
    observed = [str(node.get("node_id")) for node in nodes]
    nodes_complete = bool(expected) and expected == set(observed) and len(observed) == len(set(observed))
    if aggregate and nodes_complete and nodes_settled and len(statuses) == 1 and statuses <= TAU_STREAM_TERMINAL_STATUSES:
        record["terminal"] = True
        record["terminal_status"] = next(iter(statuses))
        # Settlement and success are distinct. An aggregate PASS cannot erase
        # a declared node's FAIL/CANCELLED/SKIPPED result.
        if record["terminal_status"] in {"PASS", "COMPLETED"} and any(
                str(node.get("status", "")).upper() not in {"PASS", "COMPLETED"} for node in nodes):
            record["terminal_status"] = "NEEDS_ATTENTION"
            record["inconsistent_terminal"] = "aggregate success contradicts a required node"
        record["terminal_source"] = "run-level dag-progress.json"
    elif len(plans) == 1 and (refusal := _settled_semantic_refusal(plans[0], expected)):
        record.update(terminal=True, terminal_status="BLOCKED", current_status="BLOCKED",
                      terminal_source=refusal["path"], semantic_refusal=refusal)
    # Node receipts remain progress evidence only; they cannot settle a DAG.
    record["stream_readable"] = bool(
        record["event_count"] or any(p.get("readable") for p in record["progress_files"] + record["node_receipts"])
    )
    if record["terminal"]:
        record["reason"] = "terminal Ask/Tau stream state observed"
        failures = [n for n in nodes if n.get("failure_code")]
        if failures:
            codes = sorted({str(n["failure_code"]) for n in failures})
            record["upstream_failure"] = {"failure_codes": codes, "nodes": failures}
            if len(codes) == 1:
                record["upstream_failure"]["failure_code"] = codes[0]
    elif record["stream_readable"]:
        record["reason"] = "Ask/Tau stream readable but no terminal status observed"
    return record


def run_ask_tau_dag_with_stream_monitor(
    command: list[str], *, cwd: Path, timeout_s: int, ask_run_dir: Path,
    monitor_path: Path, poll_interval_s: float = 5.0,
) -> dict[str, Any]:
    """Spool continuously to disk; no unconsumed PIPE can deadlock Ask/Tau."""
    from . import primary
    started = time.monotonic()
    env = os.environ.copy()
    env["PATH"] = f"{Path(config.resolve_uv_bin()).parent}:{env.get('PATH', '')}"
    monitor_path.parent.mkdir(parents=True, exist_ok=True)
    out_path = monitor_path.with_suffix(".stdout.log")
    err_path = monitor_path.with_suffix(".stderr.log")
    timed_out, poll_count = False, 0
    with out_path.open("w") as out, err_path.open("w") as err:
        try:
            proc = subprocess.Popen(command, cwd=str(cwd), env=env, stdout=out, stderr=err,
                                    start_new_session=True, pass_fds=primary.inherited_fds())
        except OSError:
            if primary.inherited_fds():
                primary.checkpoint("leased", launch_failed_before_exec=True)
            raise
        if primary.inherited_fds():
            primary.checkpoint("running", ask_pid=proc.pid, ask_run_dir=str(ask_run_dir))
        while proc.poll() is None:
            poll_count += 1
            row = inspect_tau_stream(ask_run_dir)
            row.update(poll_count=poll_count, process_running=True, process_id=proc.pid,
                       elapsed_seconds=round(time.monotonic() - started, 3),
                       stdout_path=str(out_path), stderr_path=str(err_path),
                       stop_condition="process_exit_or_deadline")
            write_json(monitor_path, row)
            if time.monotonic() - started >= timeout_s:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=5)
                break
            time.sleep(min(poll_interval_s, max(0.05, timeout_s - (time.monotonic() - started))))
        proc.wait()
    final = inspect_tau_stream(ask_run_dir)
    final.update(poll_count=poll_count, process_running=False, process_id=proc.pid,
                 process_exit_code=proc.returncode,
                 elapsed_seconds=round(time.monotonic() - started, 3), timed_out=timed_out,
                 stop_condition="timeout_requires_tau_reconciliation" if timed_out else "process_exited",
                 stdout_path=str(out_path), stderr_path=str(err_path))
    write_json(monitor_path, final)
    if not final.get("terminal") and not timed_out:
        # Compile refusals require the now-persisted process-exit evidence.
        observed = inspect_tau_stream(ask_run_dir)
        if observed.get("terminal"):
            final.update(observed)
            write_json(monitor_path, final)
    return {"command": command, "cwd": str(cwd), "exit_code": 124 if timed_out else proc.returncode,
            "stdout": out_path.read_text(errors="replace"), "stderr": err_path.read_text(errors="replace"),
            "timed_out": timed_out, "duration_seconds": round(time.monotonic() - started, 3),
            "stream_monitor": str(monitor_path), "stdout_path": str(out_path), "stderr_path": str(err_path)}


def _land_repair_to_main(worktree: Path, run_id: str, issue_number: int) -> tuple[bool, list[dict[str, Any]]]:
    # Compatibility only. The active path uses private-index content publication
    # followed by native ticket proof/closure, never the historical rebase path.
    return False, [{"exit_code": 1, "stderr": "obsolete landing path; use target_content.publish and native_ticket.close"}]


def _cleanup_landed_repair_worktree(project_worktree: Path, repair_worktree: Path,
                                   run_id: str, issue_number: int) -> dict[str, Any]:
    return {"exit_code": 1, "receipt": None, "stderr": "primary-main-only: watchdog may not archive or remove any worktree"}


def _landed_repair_cleanup_ok(command_result: dict[str, Any]) -> bool:
    if command_result.get("exit_code") != 0:
        return False
    receipt = command_result.get("receipt")
    if not isinstance(receipt, dict):
        return False
    return receipt.get("outcome") in {"archived", "removed", "skipped"}


# --------------------------------------------------------------------------- #
# Repair proof gate — a DAG that exited 0 is not a repaired ticket
# --------------------------------------------------------------------------- #

#: The verdict vocabulary the repair task asks each seat for. A response that
#: declares nothing from this vocabulary has declared no verdict; the watchdog
#: reads what a seat states, it does not interpret prose into a verdict.
REPAIR_VERDICT_TOKENS = frozenset({"PASS", "FAIL", "NEEDS_ATTENTION", "BLOCKED"})

#: Verdicts that are an explicit refusal to claim the repair is done.
REPAIR_REFUSAL_TOKENS = frozenset({"FAIL", "NEEDS_ATTENTION", "BLOCKED"})

#: Values a machine-readable proof artifact may carry that mean "this run
#: finished and passed".
PROOF_PASS_VALUES = frozenset(
    {"PASS", "PASSED", "READY", "OK", "COMPLETED", "SUCCESS", "GREEN", "TRUE"}
)

#: Values that mean the proof did not finish, or finished badly. ``RUNNING``
#: and ``PENDING`` are failures here on purpose: agent-skills#1499 was closed
#: while its second proof attempt was still going.
PROOF_FAIL_VALUES = frozenset(
    {
        "FAIL", "FAILED", "BLOCKED", "ERROR", "ERRORED", "NOT_READY",
        "NEEDS_ATTENTION", "USABLE_WITH_GAPS", "NOT_TESTED", "RUNNING", "PENDING", "IN_PROGRESS", "TIMEOUT",
        "TIMED_OUT", "CANCELLED", "SKIPPED", "UNKNOWN", "FALSE",
    }
)

#: Keys whose value states the outcome of a run. Read at any depth so a
#: per-case ``status: FAIL`` inside an otherwise READY report still fails.
PROOF_RESULT_KEYS = frozenset(
    {"readiness", "status", "verdict", "result", "outcome", "overall",
     "overall_status", "state", "ok", "passed"}
)

#: How far into a proof artifact to read result keys. Deep enough for a
#: per-case eval report, bounded so a huge artifact cannot stall a tick.
PROOF_SCAN_DEPTH = 6

_POSITION_HEADING = re.compile(r"^#{1,6}\s*position\s*$", re.IGNORECASE)
_OUTPUT_FLAG = re.compile(r"--(?:output|out|output-file|report)[ =]+([^\s`'\"]+)")
_PROOF_PATH = re.compile(
    r"(?:^|[\s`'\"(=])((?:/|\./|~/)?[\w.@+-]+(?:/[\w.@+-]+)+\.(?:json|xml|txt|log|md|csv|html))"
)


def repair_node_id(handler: str) -> str:
    """The ``node-artifacts`` directory ``$ask`` writes for one handler seat."""
    return "handler-" + re.sub(r"[^a-z0-9]+", "-", handler.lower()).strip("-")


def declared_verdict(text: str) -> str | None:
    declarations = []
    for line in text.splitlines():
        match = re.fullmatch(r"\s*VERDICT:\s*(PASS|FAIL|BLOCKED|NEEDS_ATTENTION)\s*", line, re.I)
        if match:
            declarations.append(match.group(1).upper())
    if len(declarations) != 1:
        return None
    return declarations[0]


def seat_response_text(ask_run_dir: Path, handler: str) -> str | None:
    """Require one unambiguous response for this run/seat, not first-PASS wins."""
    node_id = repair_node_id(handler)
    candidates = list(ask_run_dir.glob(f"*/node-artifacts/{node_id}/response.md"))
    if len(candidates) != 1:
        return None
    try:
        return candidates[0].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def required_proof_artifacts(issue_body: str) -> list[str]:
    """The artifact paths the ticket's own proof section names.

    Only the ``Required proof`` section is read: paths elsewhere in a ticket
    body are context files and reproduction pointers, not things the repair is
    supposed to produce. When the section names an ``--output`` operand those
    win outright, because that is the artifact the proof command writes.
    """
    section: list[str] = []
    collecting = False
    for line in issue_body.splitlines():
        heading = re.match(r"^#{1,6}\s*(.+?)\s*$", line.strip())
        if heading:
            collecting = heading.group(1).strip().lower() == "required proof"
            continue
        if collecting:
            section.append(line)
    text = "\n".join(section)
    if not text.strip():
        return []
    outputs = [m.group(1) for m in _OUTPUT_FLAG.finditer(text)]
    if outputs:
        return sorted(dict.fromkeys(outputs))
    return sorted(dict.fromkeys(m.group(1) for m in _PROOF_PATH.finditer(text)))


def _result_values(payload: Any, depth: int = 0) -> list[str]:
    """Every outcome-key value in a parsed artifact, uppercased."""
    if depth > PROOF_SCAN_DEPTH:
        return ["UNKNOWN"] if isinstance(payload, (dict, list)) and payload else []
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in {"failed", "failures", "errored", "errors", "blocked", "skipped", "not_tested", "not_run"}:
                if (isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0) or (isinstance(value, list) and value):
                    found.append("FAIL")
            if str(key).lower() in PROOF_RESULT_KEYS and isinstance(value, (str, bool)):
                found.append(str(value).upper())
            else:
                found.extend(_result_values(value, depth + 1))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_result_values(item, depth + 1))
    return found


def inspect_proof_artifact(raw_path: str, *, not_before: float) -> dict[str, Any]:
    """Whether one named proof artifact is present, fresh, and a completed pass.

    Freshness is load-bearing: agent-skills#1499 had a passing receipt on disk
    from July, and accepting it would have closed the ticket on a proof no seat
    in this dispatch ever ran.
    """
    path = Path(raw_path).expanduser()
    record: dict[str, Any] = {
        "path": str(path), "exists": False, "fresh": False,
        "machine_readable": False, "passed": False, "reason": "",
    }
    if not path.is_file():
        record["reason"] = "not written"
        return record
    record["exists"] = True
    stat = path.stat()
    record["mtime"] = stat.st_mtime
    record["size"] = stat.st_size
    # File mtimes come from the kernel's coarse clock, which can lag
    # time.time() by a few milliseconds -- a file written microseconds AFTER
    # dispatch can carry an mtime microseconds BEFORE it (proven with a live
    # -0.34ms delta, 2026-09-05). One second of tolerance is noise against
    # real multi-minute dispatches and removes the false 'predates' refusal.
    if stat.st_mtime < not_before - 1.0:
        record["reason"] = "predates this dispatch"
        return record
    record["fresh"] = True
    if stat.st_size > 8 * 1024 * 1024:
        record["reason"] = "proof result exceeds bounded parser size"
        return record
    if stat.st_size == 0:
        record["reason"] = "empty"
        return record
    if path.suffix.lower() != ".json":
        record["reason"] = "non-JSON artifact is evidence to inspect, not a machine-verifiable pass"
        return record
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        record["reason"] = f"unreadable json: {exc}"
        return record
    values = _result_values(payload)
    record["machine_readable"] = bool(values)
    failing = sorted({v for v in values if v in PROOF_FAIL_VALUES})
    passing = sorted({v for v in values if v in PROOF_PASS_VALUES})
    record["failing_values"] = failing
    record["passing_values"] = passing
    if failing:
        record["reason"] = f"reports {', '.join(failing)}"
        return record
    unknown = sorted(set(values) - PROOF_PASS_VALUES - PROOF_FAIL_VALUES)
    if unknown:
        record["reason"] = "unrecognized result vocabulary: " + ", ".join(unknown)
        return record
    if not passing:
        record["reason"] = "no machine-readable result"
        return record
    record["passed"] = True
    record["reason"] = f"reports {', '.join(passing)}"
    return record


def repair_commits_ahead(worktree: Path) -> int | None:
    """Commits the repair branch has that ``origin/main`` does not.

    ``None`` means git could not answer, which the gate treats as unproven.
    """
    counted = run_cmd(
        ["git", "rev-list", "--count", "origin/main..HEAD"], cwd=worktree, timeout_s=60
    )
    if counted.get("exit_code") != 0:
        return None
    try:
        return int(str(counted.get("stdout", "")).strip())
    except ValueError:  # pragma: no cover - git printed something unexpected
        return None


def evaluate_repair_proof(
    *,
    ask_run_dir: Path,
    issue_body: str,
    creator: str,
    reviewer: str,
    repair_worktree: Path,
    not_before: float,
    base_sha: str | None = None,
    reviewed_commit: str | None = None,
) -> dict[str, Any]:
    """Decide whether repair evidence is ready for ticket-owned verification.

    ``$ask tau-dag`` exiting 0 means the DAG ran, not that the ticket was
    repaired: in agent-skills#1499 both seats reported ``status: PASS`` in
    their node receipts while the creator's response said it had no tools and
    the reviewer's said the live proof failed and a retry was still running.
    The issue was closed as completed with no proof and no commit.

    So closure requires positive evidence, and everything else fails closed:

    - the reviewer seat declares ``VERDICT: PASS`` in its response;
    - no seat declares FAIL, BLOCKED, or NEEDS_ATTENTION;
    - every required output and reviewer-declared JSON result is a fresh pass;
    - independently reviewed target bytes bind to an attributable content commit;
      local HEAD advancement and abandoned branch work are not attribution.
    """
    gate: dict[str, Any] = {
        "schema": "agent_skills.project_watchdog.repair_proof_gate.v1",
        "ok": False,
        "reasons": [],
        "seat_verdicts": {},
        "required_proof_artifacts": [],
        "artifact_results": [],
        "commits_ahead": None,
        "checked_at": iso_now(),
    }
    reasons: list[str] = []

    for role, handler in (("creator", creator), ("reviewer", reviewer)):
        response = seat_response_text(ask_run_dir, handler)
        verdict = declared_verdict(response) if response is not None else None
        gate["seat_verdicts"][role] = {
            "handler": handler,
            "node_id": repair_node_id(handler),
            "responded": response is not None,
            "verdict": verdict,
        }
        if response is None:
            reasons.append(f"{role} seat {handler} wrote no response artifact")
            continue
        if verdict in REPAIR_REFUSAL_TOKENS:
            reasons.append(f"{role} seat {handler} declared {verdict}")
        elif verdict is None and role == "reviewer":
            reasons.append(
                f"reviewer seat {handler} declared no VERDICT; the repair task "
                f"requires VERDICT: PASS, FAIL, or NEEDS_ATTENTION"
            )
        elif verdict != "PASS" and role == "reviewer":
            reasons.append(f"reviewer seat {handler} declared {verdict}, not PASS")

    review_text = seat_response_text(ask_run_dir, reviewer) or ""
    declared = [line.split(":", 1)[1].strip() for line in review_text.splitlines()
                if line.startswith("PROOF_ARTIFACT:")]
    # Ticket output operands remain mandatory; fixture/input JSON paths are not output proof.
    section = []
    collecting = False
    for line in issue_body.splitlines():
        heading = re.match(r"^#{1,6}\s*(.+?)\s*$", line.strip())
        if heading:
            collecting = heading.group(1).strip().lower() == "required proof"
        elif collecting:
            section.append(line)
    section_outputs = _OUTPUT_FLAG.findall("\n".join(section))
    artifacts = sorted(set(section_outputs + declared))
    if not artifacts:
        reasons.append("no explicit result artifacts: reviewer must emit PROOF_ARTIFACT lines")
    artifacts = [str((repair_worktree / a).resolve()) if not Path(a).expanduser().is_absolute()
                 else str(Path(a).expanduser().resolve()) for a in artifacts]
    gate["required_proof_artifacts"] = artifacts
    if artifacts:
        results = [inspect_proof_artifact(a, not_before=not_before) for a in artifacts]
        gate["artifact_results"] = results
        if not all(r["passed"] for r in results):
            detail = "; ".join(f"{r['path']}: {r['reason']}" for r in results)
            reasons.append(f"not every required proof artifact is a completed pass ({detail})")

    gate["reviewed_commit"] = reviewed_commit
    if not reviewed_commit:
        reasons.append("no independently reviewed content commit; local HEAD advancement is not attribution")

    gate["reasons"] = reasons
    gate["ok"] = not reasons
    return gate


def handle_ticket_repair(run_id: str, receipt_dir: Path, project: dict[str, Any],
                         issue: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    from . import primary
    return primary.dispatch(run_id, receipt_dir, project, issue, _handle_ticket_repair_primary, apply=apply)


def _handle_ticket_repair_primary(run_id: str, receipt_dir: Path, project: dict[str, Any],
                                  issue: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    from . import primary, native_ticket, target_content as content, models
    from .primary_models import OwnedTargets, encoded
    repo, number, root = project_repo(project), int(issue["number"]), project_worktree(project).resolve()
    targets = primary.safe_targets(issue.get("watchdog_targets") or registry.issue_targets(issue))
    result = _new_result(project, issue, str(issue.get("watchdog_action") or "ticket_repair"))
    result.update(requires_human_input=False, targets=targets)
    if registry.policy_held(repo, number):
        raise primary.Refusal("standing pitchdeck hold is immutable", human=True)
    result["worktree_readiness"] = primary.readonly_preflight(root, targets)
    primary.assert_repository(root, repo)
    if not apply:
        result.update(ok=True, status="DRY_RUN", summary="would reserve primary/main and use native Tau/ticket lifecycle")
        return result
    state = json.loads(config.state_path().read_text())
    models.validate_state(state)
    from .commands import _project_runtime_state
    if state["global"]["state"] != "active" or _project_runtime_state(project, state) != "active":
        raise primary.Refusal("runtime authorization changed", human=True)
    # Recheck foreign scopes at the actual reservation boundary, not only at scan time.
    foreign = registry.lane_busy_issues(run_id, project)
    if registry.targets_are_blocked(set(targets), registry.busy_targets(foreign)):
        raise primary.Refusal("known foreign lease overlaps this target; unrelated scopes remain eligible")
    pin = content.remote_pin(root)
    before = content.snapshot(root, targets, pin, receipt_dir / "primary-before-blobs")
    write_json(receipt_dir / "primary-before.json", encoded(before))
    ownership_path = primary._area(root) / "owned" / f"{number}.json"
    previous = OwnedTargets.model_validate(json.loads(ownership_path.read_text())) if ownership_path.exists() else None
    classification = content.classify(root, before, repo=repo, number=number,
                                      task_sha256=primary.current().task_sha256, owned=previous)
    result["target_ownership"] = classification
    write_json(receipt_dir / "target-ownership.json", classification)
    conflicts = {p: why for p, why in classification.items()
                 if why not in {"verified_remote_identical", "verified_current_task_owned"}}
    if conflicts:
        raise primary.Refusal(f"target ownership conflict (not checkout dirtiness): {conflicts}")
    legacy = primary.legacy_inventory(root, number)
    write_json(receipt_dir / "legacy-repair.json", legacy)
    native_ticket.acquire(primary.current(), result, primary.checkpoint)
    # Close the snapshot/lease race without rehashing the monorepo.
    current_pin = content.remote_pin(root)
    if content.remote_entries(root, current_pin, targets) != content.remote_entries(root, pin, targets):
        raise primary.Refusal("remote target changed while acquiring native lease")
    content.require_unchanged(before, content.snapshot(root, targets, current_pin))
    creator, reviewer = config.repair_seats(project)
    result["seats"] = {"creator": creator, "reviewer": reviewer}
    task = build_repair_task(repo=repo, issue_number=number, issue_title=str(issue.get("title", "")),
                             issue_body=str(issue.get("body") or ""), targets=targets)
    import shlex
    commit_tool = Path(__file__).with_name("scope_commit.py")
    commit_command = shlex.join([config.resolve_uv_bin(), "run", "--project", str(config.SKILL_DIR),
        "python", str(commit_tool), "--root", str(root), "--journal", primary.current().journal,
        "--before", str(receipt_dir / "primary-before.json"), "--output", str(receipt_dir / "authored-commit.json")])
    clauses = required_proof_clauses(str(issue.get("body") or "")) or ["legacy_native_route"]
    task += (f"\nPrimary checkout on MAIN only: {root}. Both seats use that exact path.\n"
             "Do not create/switch/remove branches or worktrees. No reset, stash, clean, rebase, merge, "
             "shared-index staging, local HEAD commit, amend, direct push, lease mutation or issue closure. "
             "Unrelated cron work is normal: do not inspect/hash/change all repository files. "
             "Inspect old repair refs with git show from primary only; preserve the old branch/worktree.\n"
             f"The starting shipped SHA is {pin}, NOT local HEAD {before.head}.\n"
             "After each meaningful scoped edit and before final review, creator MUST checkpoint with this private-index helper:\n"
             f"{commit_command}\n"
             "The helper creates an unreferenced content commit, never a branch or worktree. "
             "Reviewer must verify that exact commit and the on-disk target bytes, not an unrelated HEAD.\n"
             "Reviewer output must include one REVIEW_COMMIT: <full SHA> line, one VERDICT: PASS|FAIL|NEEDS_ATTENTION line, "
             "each PROOF_ARTIFACT: <absolute JSON RESULT path>, and one VERIFY_PLAN: <single-line JSON> line. "
             "VERIFY_PLAN has schema agent_skills.project_watchdog.verification_plan.v1, commands (nonempty list of "
             "deterministic commands suitable for ticket verify), artifacts (all result paths), and coverage "
             "(map from EVERY exact required clause below to the real command/artifact that proves it). "
             "Do not put model output, fabricated result JSON, fixture inputs, abbreviated comparisons, "
             "or a still-running background proof in place of an experiment. The watchdog reruns verification "
             "through ticket verify before native close. Report any inability as NEEDS_ATTENTION, not PASS.\n"
             f"Required coverage keys: {json.dumps(clauses)}\n")
    task += legacy_route_task(project, issue, receipt_dir)
    (receipt_dir / "repair-task.md").write_text(task)
    ask_dir = receipt_dir / "ask"
    command = [str(config.ask_run_sh()), "tau-dag", task, "--repo", repo, "--target", ",".join(targets),
               "--immutable-goal", repair_immutable_goal(repo, number), "--dag-template", "creator-reviewer",
               "--handler", creator, "--handler-workspace", f"{creator}={root}",
               "--handler", reviewer, "--handler-workspace", f"{reviewer}={root}",
               "--topology", "sequential", "--run-output-root", str(ask_dir), "--execute",
               "--execution-timeout-seconds", str(_ticket_repair_execution_timeout(project)),
               "--allow-provider-calls", "--json"]
    primary.checkpoint("launching", ask_run_dir=str(ask_dir), dispatched_at=time.time())
    execution = run_ask_tau_dag_with_stream_monitor(command, cwd=config.ask_run_sh().parent,
        timeout_s=int(project.get("ticket_repair_timeout_s", 1800)), ask_run_dir=ask_dir,
        monitor_path=receipt_dir / "tau-stream-monitor.json")
    result["commands"].append(execution)
    primary.checkpoint(primary.current().phase, result=result)
    stream = inspect_tau_stream(ask_dir)
    if not stream.get("terminal"):
        raise primary.Refusal("native Tau run is not settled; recover the same retained run")
    primary.checkpoint("settled", tau_settled=True)
    if execution.get("exit_code") != 0 or execution.get("timed_out"):
        raise primary.Refusal("Ask process failed or timed out despite terminal-looking stream; no closure")
    return finish_primary_operation(primary.current())


# --------------------------------------------------------------------------- #
# Closure audit — a closure is a claim, not evidence
# --------------------------------------------------------------------------- #

#: Marks an audit comment so a later tick can count prior reopens without
#: re-reading every comment body for meaning.
CLOSURE_AUDIT_MARKER = "project-watchdog:closure-audit"


#: Closure-evidence schema `/ticket close --results` submits. Its `unit` and
#: `e2e` blocks name the commands that ran and the artifact each wrote.
CLOSURE_EVIDENCE_SCHEMA = "agent_skills.ticket_closure_evidence.v1"

CLOSURE_AUDIT_NONZERO_NEEDS_ATTENTION_CODE = (
    "project_watchdog_closure_audit_nonzero_needs_attention"
)

#: Cap per artifact. The auditors read a prompt, not a filesystem; a 50MB log
#: would crowd out the ticket itself.
ARTIFACT_EXCERPT_CHARS = 4000

_LOCAL_PATH_IN_PROMPT = re.compile(r"(?<![\w.])(?:/home|/tmp)/[^\s`'\"),\]]+")


def sanitize_local_paths_for_browser_prompt(text: str) -> str:
    """Remove absolute local paths from prompts sent to browser-backed seats."""
    def replace(match: re.Match[str]) -> str:
        name = Path(match.group(0)).name or "path"
        return f"[local path omitted: {name}]"

    return _LOCAL_PATH_IN_PROMPT.sub(replace, text)


def collect_closure_artifacts(
    comments: list[dict[str, Any]], *, base_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Read the proof artifacts a closure claimed, so the audit can see them.

    Both audit seats reported they could not read local files, so they judged
    "was the proof actually run" from the ticket thread alone -- and a closing
    comment that summarises rather than pastes its output could never pass. The
    closer already submits artifact paths in the closure-evidence JSON; nothing
    read them.

    A path that no longer exists is reported as missing rather than omitted. An
    artifact that cannot be produced is itself a fact about the closure.
    """
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_artifact(path_value: str, *, tier: str, command: Any = None) -> None:
        path = path_value.strip().strip("`.,;)]")
        if not path or path in seen:
            return
        seen.add(path)
        record: dict[str, Any] = {"tier": tier, "path": path, "command": command}
        artifact_path = Path(path)
        if not artifact_path.is_absolute() and base_dir is not None:
            artifact_path = base_dir / artifact_path
        try:
            text = artifact_path.read_text(encoding="utf-8", errors="replace")
            record["content"] = text[:ARTIFACT_EXCERPT_CHARS]
            record["bytes"] = len(text)
        except OSError as exc:
            record["missing"] = str(exc)
        found.append(record)

    for comment in comments:
        body = str(comment.get("body", ""))
        for block in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.S):
            try:
                payload = json.loads(block)
            except ValueError:
                continue
            if payload.get("schema") != CLOSURE_EVIDENCE_SCHEMA:
                continue
            for tier in ("unit", "e2e"):
                entry = payload.get(tier)
                if isinstance(entry, dict):
                    add_artifact(str(entry.get("artifact") or ""), tier=tier, command=entry.get("command"))
        for match in re.findall(r"`?((?:docs|local|artifacts)/[^`\s]+?\.json)`?", body):
            add_artifact(match, tier="comment")
    return found


def render_closure_artifacts(artifacts: list[dict[str, Any]]) -> str:
    """Format collected artifacts for the audit prompt."""
    if not artifacts:
        return "(the closure cited no artifact paths)"
    chunks = []
    for a in artifacts:
        head = f"[{a['tier']}] {a['path']}"
        if a.get("command"):
            head += f"\n  command: {a['command']}"
        if "missing" in a:
            chunks.append(f"{head}\n  NOT READABLE: {a['missing']}")
        else:
            chunks.append(f"{head}\n  ({a['bytes']} chars)\n{a['content']}")
    return "\n\n".join(chunks)


def build_closure_audit_task(
    *,
    repo: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    evidence: str,
    artifacts: str = "(no artifacts collected)",
) -> str:
    """The prompt the auditor answers.

    It gets the ticket's own acceptance criterion and required proof, and the
    closing evidence, and nothing else. The question is narrow on purpose: not
    "is this good work" but "does the closure hold against what the ticket
    asked for".
    """
    task = (
        f"Audit the closure of {repo}#{issue_number}: {issue_title}\n\n"
        f"Decide one thing: does the evidence below actually establish the "
        f"acceptance criterion and the required proof the ticket names?\n\n"
        f"Answer VERDICT: PASS only if the named proof was actually run and its "
        f"result is shown. Answer VERDICT: FAIL if the criterion is unmet, the "
        f"proof was not run, the evidence is asserted rather than shown, or the "
        f"change demonstrably does something other than what was asked. Answer "
        f"VERDICT: NEEDS_ATTENTION if you cannot tell from what is here.\n\n"
        f"A closing comment claiming success is not evidence that the proof ran. "
        f"Deterministic tests over the closer's own new code are weak evidence "
        f"for a live defect. Say which specific criterion fails and why.\n\n"
        f"You are shown the proof artifacts the closure cited, read from disk. "
        f"Treat those as the actual output of the proof command. An artifact "
        f"marked NOT READABLE is a gap; an artifact whose contents show the proof "
        f"passing is the evidence you are looking for.\n\n"
        f"If the closure cites NO artifacts at all, it predates the evidence "
        f"contract and cannot produce them. That is not grounds for FAIL. Answer "
        f"NEEDS_ATTENTION unless the thread itself positively shows the criterion "
        f"is unmet. Reserve FAIL for evidence that the work is wrong, not for "
        f"evidence that is absent by design -- FAIL reopens the ticket and sends "
        f"a repair agent at work that may well be finished.\n\n"
        f"--- ticket ---\n{issue_body}\n\n"
        f"--- closing evidence ---\n{evidence}\n\n"
        f"--- proof artifacts read from disk ---\n{artifacts}"
    )
    return sanitize_local_paths_for_browser_prompt(task)


def _extract_verdict(text: str) -> str | None:
    """Same convention $ask's reviewer seats use."""
    upper = text.upper()
    for verdict in ("NEEDS_ATTENTION", "PASS", "FAIL"):
        if f"VERDICT: {verdict}" in upper or f"VERDICT {verdict}" in upper:
            return verdict
    return None


def read_seat_failures(run_root: Path) -> dict[str, str]:
    """Per-seat failure codes from an $ask run, for the summary.

    Without these a panel that could not reach a provider reported only "no
    usable panel verdict", and the operator had to dig through recovery packets
    to find `scillm_auth_invalid_api_key`. The cause belongs in the receipt.
    """
    failures: dict[str, str] = {}
    for receipt in sorted(run_root.glob("*/node-artifacts/*/node-receipt.json")):
        if receipt.parent.name == "join":
            continue
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.error("could not read node receipt {}: {}", receipt, exc)
            continue
        code = data.get("failure_code")
        if code:
            failures[receipt.parent.name] = str(code)
    return failures


def _read_ask_responses_by_node(run_root: Path) -> dict[str, str]:
    """Each handler seat's cleaned answer, keyed by node id.

    A panel needs per-seat verdicts: concatenating them would let one seat's
    "VERDICT: PASS" be read as the panel's answer.
    """
    responses: dict[str, str] = {}
    for node_dir in sorted(run_root.glob("*/node-artifacts/*")):
        if node_dir.name == "join":
            continue
        clean = node_dir / "response.md"
        raw = node_dir / "response.raw.md"
        path = clean if clean.is_file() else raw
        if not path.is_file():
            continue
        try:
            responses[node_dir.name] = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("could not read $ask response {}: {}", path, exc)
    return responses


def _read_ask_response(run_root: Path) -> str:
    """The handler's cleaned answer from an $ask run directory.

    `response.md` is the cleaned text; `response.raw.md` is the provider's whole
    chat-completion envelope. Globbing `response*.md` matched both, so the
    reviewer excerpt posted to GitHub was raw JSON with the reasoning buried in
    it. Only fall back to raw when a lane produced no cleaned response at all.
    """
    chunks: list[str] = []
    for node_dir in sorted(run_root.glob("*/node-artifacts/*")):
        clean = node_dir / "response.md"
        raw = node_dir / "response.raw.md"
        path = clean if clean.is_file() else raw
        if not path.is_file():
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.error("could not read $ask response {}: {}", path, exc)
    return "\n\n".join(chunks)


def handle_closure_audit(
    run_id: str,
    receipt_dir: Path,
    project: dict[str, Any],
    issue: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Review one closed ticket and reopen it if the closure does not hold.

    Closing a ticket is a claim that the work is done, and nothing checked it.
    The repair lane's reviewer judges a diff before it lands; this judges the
    closure afterwards, including closures no agent made.
    """
    repo = project_repo(project)
    issue_number = int(issue["number"])
    auditors = config.closure_auditors(project)
    result = _new_result(project, issue, "closure_audit")
    result["selected_agent"] = ",".join(auditors)
    result["auditors"] = auditors
    log_event(run_id, "closure_audit_start", issue=issue_number, repo=repo, auditors=auditors)

    if len(auditors) < 2 or len(set(auditors)) != len(auditors):
        result.update(
            {
                "ok": False,
                "status": "BLOCKED",
                "summary": (
                    f"closure audit needs at least two distinct seats, got {auditors}. "
                    f"One model that over-accepts would uphold its own bad closures."
                ),
            }
        )
        log_event(run_id, "closure_audit_panel_invalid", issue=issue_number, auditors=auditors)
        return result

    comments = github.issue_comments(repo, issue_number)
    reopens = sum(
        1
        for c in comments
        if CLOSURE_AUDIT_MARKER in str(c.get("body", "")) and "REOPENED" in str(c.get("body", ""))
    )
    result["prior_reopens"] = reopens

    evidence = "\n\n".join(
        f"[{c.get('author', {}).get('login', '?')} {str(c.get('createdAt', ''))[:19]}]\n"
        f"{str(c.get('body', ''))[:4000]}"
        for c in comments
    ) or "(no comments on this issue)"

    collected = collect_closure_artifacts(comments, base_dir=Path(project["worktree"]))
    result["closure_artifacts"] = [
        {k: v for k, v in a.items() if k != "content"} for a in collected
    ]
    task = build_closure_audit_task(
        repo=repo,
        issue_number=issue_number,
        issue_title=str(issue.get("title", "")),
        issue_body=str(issue.get("body", ""))[:8000],
        evidence=evidence,
        artifacts=render_closure_artifacts(collected),
    )
    if not apply:
        # Write nothing on a preview: creating the receipt directory is what
        # makes a tick leave a directory behind, and a previewed audit is not an
        # event. A per-minute cron would otherwise accumulate one per tick.
        result.update(
            {
                "ok": True,
                "status": "DRY_RUN",
                "summary": (
                    f"would audit the closure of {repo}#{issue_number} with {auditors}"
                ),
            }
        )
        return result

    task_path = receipt_dir / f"closure-audit-{issue_number}.md"
    task_path.write_text(task, encoding="utf-8")
    result["artifacts"].append(str(task_path))

    ask_run_dir = receipt_dir / f"closure-audit-{issue_number}"
    audit = run_cmd(
        [
            str(config.ask_run_sh()),
            "tau-dag",
            task,
            "--repo", repo,
            "--target", f"issue#{issue_number}",
            "--immutable-goal", (
                f"Decide whether the closure of {repo}#{issue_number} is supported by "
                f"evidence for the acceptance criterion and proof the ticket names. "
                f"Do not accept an assertion of success as evidence that a proof ran."
            ),
            "--dag-template", "roundtable",
            "--topology", "concurrent",
            *[arg for seat in auditors for arg in ("--handler", seat)],
            "--run-output-root", str(ask_run_dir),
            "--execute",
            "--allow-provider-calls",
            "--json",
        ],
        cwd=config.ask_run_sh().parent,
        timeout_s=int(project.get("closure_audit_timeout_s", 900)),
    )
    result["commands"].append(audit)
    result["artifacts"].append(str(ask_run_dir))

    by_node = _read_ask_responses_by_node(ask_run_dir)
    seat_failures = read_seat_failures(ask_run_dir)
    result["seat_failures"] = seat_failures
    seat_verdicts = {node: _extract_verdict(text) for node, text in by_node.items()}
    result["seat_verdicts"] = seat_verdicts
    answered = [v for v in seat_verdicts.values() if v]

    # A closure is upheld only if every seat that answered says so, and only if
    # the whole panel answered. Any FAIL reopens: one competent reviewer showing
    # the named proof was never run is decisive, and a closure is a claim that
    # has to be established rather than a default to fall back on.
    if any(v == "FAIL" for v in answered):
        verdict = "FAIL"
    elif answered and len(answered) == len(auditors) and all(v == "PASS" for v in answered):
        verdict = "PASS"
    elif any(v == "NEEDS_ATTENTION" for v in answered):
        verdict = "NEEDS_ATTENTION"
    else:
        verdict = None
    result["verdict"] = verdict
    response = "\n\n".join(
        f"### {node}\n{text.strip()}" for node, text in sorted(by_node.items())
    )

    if verdict is None or (audit.get("exit_code") != 0 and verdict == "PASS"):
        # No verdict is not a pass. A PASS from a nonzero Ask/Tau wrapper is
        # also not durable evidence. A semantic FAIL is different: Tau returns
        # nonzero when receipt evidence records a non-PASS verdict, and that
        # FAIL must still reach the reopen path or the same closure is audited
        # again after every cooldown window.
        result.update(
            {
                "ok": False,
                "status": "NEEDS_ATTENTION",
                "summary": (
                    f"closure audit of {repo}#{issue_number} produced no usable panel verdict "
                    f"(exit {audit.get('exit_code')}, seats {seat_verdicts}"
                    + (f", failures {seat_failures}" if seat_failures else "")
                    + "). The closure is unreviewed, not accepted."
                ),
            }
        )
        log_event(run_id, "closure_audit_no_verdict", issue=issue_number)
        return result

    if verdict == "PASS":
        result["commands"].append(
            github.issue_comment(
                repo,
                issue_number,
                github.watchdog_comment(
                    "Closure audit: PASS",
                    {
                        "schema": "agent_skills.project_watchdog.closure_audit.v1",
                        "marker": CLOSURE_AUDIT_MARKER,
                        "run_id": run_id,
                        "issue": f"issue#{issue_number}",
                        "repo": repo,
                        "auditors": auditors,
                        "seat_verdicts": seat_verdicts,
                        "verdict": verdict,
                        "outcome": "closure_upheld",
                    },
                ),
            )
        )
        # The label is what stops this closure being re-audited every tick, so a
        # failed edit is not cosmetic. Observed: `closure-verified` existed in no
        # repo and was absent from ensure-labels, so the first unanimous PASS
        # marked nothing.
        mark = github.issue_edit(
            repo,
            issue_number,
            add=[config.CLOSURE_VERIFIED_LABEL],
            remove=[config.CLOSURE_UNVERIFIED_LABEL],
        )
        result["commands"].append(mark)
        if mark.get("exit_code") != 0:
            result.update(
                {
                    "ok": False,
                    "status": "NEEDS_ATTENTION",
                    "summary": (
                        f"closure of {repo}#{issue_number} was upheld but "
                        f"{config.CLOSURE_VERIFIED_LABEL!r} could not be applied: "
                        f"{str(mark.get('stderr'))[:160]}. Without it the same closure is "
                        f"re-audited every tick. Run: skills/ticket/run.sh ensure-labels "
                        f"--repo {repo}"
                    ),
                }
            )
            log_event(run_id, "closure_verified_label_failed", issue=issue_number)
            return result
        result.update(
            {
                "ok": True,
                "status": "COMPLETED",
                "summary": (
                    f"closure of {repo}#{issue_number} upheld unanimously by {auditors}"
                ),
            }
        )
        log_event(run_id, "closure_audit_pass", issue=issue_number)
        return result

    if verdict == "NEEDS_ATTENTION":
        # "I cannot tell from what is here" is not a finding that the work is
        # wrong. Reopening on it would churn every ticket whose proof lives in
        # an artifact the auditor cannot read. Say so and leave it closed.
        audit_triage = None
        if audit.get("exit_code") != 0:
            audit_triage = {
                "code": CLOSURE_AUDIT_NONZERO_NEEDS_ATTENTION_CODE,
                "layer": "project-watchdog",
                "cause": (
                    "Ask/Tau exited nonzero while closure-audit seats declared "
                    "VERDICT: NEEDS_ATTENTION. The semantic verdict is usable; "
                    "the watchdog must make it durable with closure-unverified or cooldown."
                ),
                "next_command": (
                    f"Ensure {config.CLOSURE_UNVERIFIED_LABEL!r} exists for {repo}, "
                    "then re-run the project-watchdog closure-audit regression eval."
                ),
            }
            result["triage"] = audit_triage
        result["commands"].append(
            github.issue_comment(
                repo,
                issue_number,
                github.watchdog_comment(
                    "Closure audit: NEEDS_ATTENTION",
                    {
                        "schema": "agent_skills.project_watchdog.closure_audit.v1",
                        "marker": CLOSURE_AUDIT_MARKER,
                        "run_id": run_id,
                        "issue": f"issue#{issue_number}",
                        "repo": repo,
                        "auditors": auditors,
                        "seat_verdicts": seat_verdicts,
                        "seat_failures": seat_failures,
                        "verdict": verdict,
                        "wrapper_exit_code": audit.get("exit_code"),
                        "wrapper_stderr_excerpt": str(audit.get("stderr", ""))[:1000],
                        "triage": audit_triage,
                        "outcome": "left_closed_unverified",
                        "reviewer_excerpt": response.strip()[:2000],
                    },
                ),
            )
        )
        # Same durability rule as closure-verified for the current cooldown:
        # without a label/readable state the scan selects this closure again next
        # tick and the panel re-answers the identical question every minute
        # (observed as a window-flash loop). The persisted retry timestamp, not
        # this label, decides when a later tick may try again.
        mark = github.issue_edit(repo, issue_number, add=[config.CLOSURE_UNVERIFIED_LABEL])
        result["commands"].append(mark)
        if mark.get("exit_code") != 0:
            result.update(
                {
                    "ok": False,
                    "status": "NEEDS_ATTENTION",
                    "failure_code": (
                        audit_triage["code"] if audit_triage else "closure_unverified_label_failed"
                    ),
                    "summary": (
                        (f"[{audit_triage['code']}] " if audit_triage else "")
                        + f"closure of {repo}#{issue_number} was left unverified but "
                        f"{config.CLOSURE_UNVERIFIED_LABEL!r} could not be applied: "
                        f"{str(mark.get('stderr'))[:160]}. Without it the same closure is "
                        f"re-audited every tick. Run: skills/ticket/run.sh ensure-labels "
                        f"--repo {repo}"
                    ),
                }
            )
            log_event(run_id, "closure_unverified_label_failed", issue=issue_number)
            return result
        result.update(
            {
                "ok": True,
                "status": "NEEDS_ATTENTION",
                "failure_code": audit_triage["code"] if audit_triage else None,
                "summary": (
                    (f"[{audit_triage['code']}] " if audit_triage else "")
                    + f"closure of {repo}#{issue_number} could not be judged from the ticket "
                    f"thread; left closed and unverified rather than reopened "
                    f"(wrapper exit {audit.get('exit_code')}, seats {seat_verdicts}"
                    + (f", failures {seat_failures}" if seat_failures else "")
                    + ")"
                ),
            }
        )
        log_event(run_id, "closure_audit_inconclusive", issue=issue_number)
        return result

    # FAIL: a seat showed the closure does not hold.
    exhausted = reopens >= config.CLOSURE_AUDIT_MAX_REOPENS
    # Lead of the reviewer's reasoning, not the tail: taking the last N characters
    # started the excerpt mid-word and cut off the argument that justified it.
    excerpt = response.strip()[:2000]
    outcome = "reopen_budget_exhausted" if exhausted else "REOPENED"
    result["commands"].append(
        github.issue_comment(
            repo,
            issue_number,
            github.watchdog_comment(
                f"Closure audit: {verdict}",
                {
                    "schema": "agent_skills.project_watchdog.closure_audit.v1",
                    "marker": CLOSURE_AUDIT_MARKER,
                    "run_id": run_id,
                    "issue": f"issue#{issue_number}",
                    "repo": repo,
                    "auditors": auditors,
                    "seat_verdicts": seat_verdicts,
                    "verdict": verdict,
                    "outcome": outcome,
                    "prior_reopens": reopens,
                    "reviewer_excerpt": excerpt,
                },
            ),
        )
    )
    if exhausted:
        # Reopening again would loop. Hand it to a person instead.
        result["commands"].append(
            github.issue_edit(repo, issue_number, add=["needs-human"])
        )
        result.update(
            {
                "ok": False,
                "status": "NEEDS_ATTENTION",
                "summary": (
                    f"{repo}#{issue_number} failed closure audit {reopens + 1} times; "
                    f"not reopening again, needs a person."
                ),
            }
        )
        log_event(run_id, "closure_audit_reopen_budget_exhausted", issue=issue_number)
        return result

    result["commands"].append(github.issue_reopen(repo, issue_number))
    result["commands"].append(
        github.issue_edit(
            repo,
            issue_number,
            add=[config.READY_LABEL],
            remove=[config.CLOSURE_VERIFIED_LABEL, config.CLOSURE_UNVERIFIED_LABEL],
        )
    )
    result.update(
        {
            "ok": True,
            "status": "COMPLETED",
            "summary": (
                f"reopened {repo}#{issue_number}: closure did not survive review ({verdict})"
            ),
        }
    )
    log_event(run_id, "closure_audit_reopened", issue=issue_number, verdict=verdict)
    return result


# --------------------------------------------------------------------------- #
# Completion attestation — "everything is closed" is also a claim
# --------------------------------------------------------------------------- #


def build_completion_attestation_task(*, repo: str, recent: list[dict[str, Any]]) -> str:
    """Ask an independent seat whether this project is genuinely finished."""
    # Include each ticket's audit status. Shown only titles and statuses, the
    # attestor correctly refused to certify anything -- "this ticket list is a
    # set of titles and statuses with no underlying evidence" -- so the lane
    # could only ever answer NEEDS_ATTENTION. Whether a closure was
    # independently reviewed and upheld is the fact worth weighing here.
    rows = []
    for i in recent[:40]:
        labels = {str(lbl.get("name")) for lbl in i.get("labels", [])}
        audited = (
            "audited+upheld" if config.CLOSURE_VERIFIED_LABEL in labels
            else "closure NOT independently verified"
        )
        rows.append(
            f"- #{i['number']} [{i.get('stateReason') or 'CLOSED'}] [{audited}] "
            f"{str(i.get('title', ''))[:100]}"
        )
    listing = "\n".join(rows) or "(no recently closed tickets)"
    return (
        f"Every agent-routable ticket in {repo} is closed. Decide whether each one "
        f"is legitimately closed, and whether the set as a whole means the work is "
        f"actually done.\n\n"
        f"Answer VERDICT: PASS if these closures look legitimate and nothing "
        f"obvious is missing. Answer VERDICT: FAIL if any ticket was closed without "
        f"the work plausibly being done, if a closure contradicts another, or if the "
        f"pattern looks like scope was quietly abandoned rather than completed. "
        f"Answer VERDICT: NEEDS_ATTENTION only if you genuinely cannot tell.\n\n"
        f"If you answer FAIL, list the tickets to reopen on their own final line, "
        f"exactly:\n\n"
        f"REOPEN: #123, #456\n\n"
        f"Each ticket is marked with whether its closure was independently "
        f"reviewed and upheld by the closure audit. A repo where most closures "
        f"were never verified is weaker evidence of completion than the same "
        f"list where they were; say that rather than guess from titles.\n\n"
        f"List only tickets from the set below, and only ones you can say are "
        f"wrongly closed. Reopening is not free: each one goes back to a repair "
        f"agent. An empty queue is not evidence of a finished project -- it is "
        f"equally consistent with nobody filing the remaining work.\n\n"
        f"--- recently closed ---\n{listing}"
    )


def handle_completion_attestation(
    run_id: str,
    receipt_dir: Path,
    project: dict[str, Any],
    recent: list[dict[str, Any]],
    *,
    apply: bool,
) -> dict[str, Any]:
    """Independent check that a project with nothing open is genuinely done.

    Every judgement up to here came from the API-routed models that did and
    reviewed the work. This asks a different transport entirely, so "everything
    is done" is not self-certified by the system that did it.
    """
    repo = project_repo(project)
    attestor = config.completion_attestor(project)
    result = {
        "project_id": project.get("project_id"),
        "repo": repo,
        "action": "completion_attestation",
        "selected_agent": attestor,
        "ok": False,
        "commands": [],
        "artifacts": [],
    }
    log_event(run_id, "completion_attestation_start", repo=repo, attestor=attestor)

    task = build_completion_attestation_task(repo=repo, recent=recent)
    if not apply:
        result.update(
            {
                "ok": True,
                "status": "DRY_RUN",
                "summary": f"would ask {attestor} whether {repo} is genuinely finished",
            }
        )
        return result

    task_path = receipt_dir / "completion-attestation.md"
    task_path.write_text(task, encoding="utf-8")
    result["artifacts"].append(str(task_path))

    run_dir = receipt_dir / "completion-attestation"
    attest = run_cmd(
        [
            str(config.ask_run_sh()),
            "tau-dag",
            task,
            "--repo", repo,
            "--target", "project-completion",
            "--immutable-goal", (
                f"Decide whether {repo} is genuinely finished, or whether an empty "
                f"ticket queue is hiding unfiled work. Name the specific gap if there is one."
            ),
            "--dag-template", "single-call",
            "--handler", attestor,
            "--run-output-root", str(run_dir),
            "--execute",
            "--allow-provider-calls",
            "--json",
        ],
        cwd=config.ask_run_sh().parent,
        timeout_s=int(project.get("completion_attest_timeout_s", 1200)),
    )
    result["commands"].append(attest)
    result["artifacts"].append(str(run_dir))

    response = _read_ask_response(run_dir)
    verdict = _extract_verdict(response)
    result["verdict"] = verdict
    result["excerpt"] = response.strip()[:2000]

    if attest.get("exit_code") != 0 or verdict is None:
        result.update(
            {
                "ok": False,
                "status": "NEEDS_ATTENTION",
                "requires_human_input": False,
                "authorized_agent_next_steps": [
                    {
                        "kind": "inspect_and_repair_watchdog_attestation",
                        "reason": (
                            "The attestor transport or verdict parser failed before a "
                            "human decision was needed. The supervising agent is "
                            "authorized to inspect the retained artifacts, fix the "
                            "watchdog/attestation path, and rerun this tick."
                        ),
                        "commands": [
                            f"python -m json.tool {receipt_dir / 'receipt.json'}",
                            f"sed -n '1,220p' {task_path}",
                            f"find {run_dir} -maxdepth 3 -type f | sort | head -80",
                        ],
                    }
                ],
                "summary": (
                    f"completion attestation for {repo} produced no verdict "
                    f"(exit {attest.get('exit_code')}). Not attested; this is "
                    "agent-actionable, not a human-input blocker."
                ),
            }
        )
        log_event(run_id, "completion_attestation_no_verdict", repo=repo)
        return result

    if verdict == "PASS":
        result.update(
            {"ok": True, "status": "COMPLETED", "summary": f"{attestor} attests {repo} is finished"}
        )
        log_event(run_id, "completion_attestation_verdict", repo=repo, verdict="PASS")
        return result

    # FAIL: reopen exactly what it named, so the repair lane picks them up and
    # the cycle runs again. NEEDS_ATTENTION reopens nothing -- "cannot tell" is
    # not a finding.
    reopen = extract_reopen_list(response, allowed={int(i["number"]) for i in recent})
    result["reopen_requested"] = reopen
    reopened: list[int] = []
    if verdict == "FAIL":
        for number in reopen:
            r = github.issue_reopen(repo, number)
            result["commands"].append(r)
            if r.get("exit_code") != 0:
                continue
            result["commands"].append(
                github.issue_edit(
                    repo, number,
                    add=[config.READY_LABEL],
                    remove=[config.CLOSURE_VERIFIED_LABEL],
                )
            )
            result["commands"].append(
                github.issue_comment(
                    repo, number,
                    github.watchdog_comment(
                        "Reopened by completion attestation",
                        {
                            "schema": "agent_skills.project_watchdog.completion_attestation.v1",
                            "run_id": run_id,
                            "repo": repo,
                            "attestor": attestor,
                            "verdict": verdict,
                            "reason": "not legitimately closed",
                            "excerpt": response.strip()[:1500],
                        },
                    ),
                )
            )
            reopened.append(number)
    result["reopened"] = reopened
    result.update(
        {
            "ok": False,
            "status": "NEEDS_ATTENTION",
            "summary": (
                f"{attestor} does not attest {repo} is finished ({verdict}); "
                f"reopened {reopened or 'nothing'}"
            ),
        }
    )
    log_event(run_id, "completion_attestation_verdict", repo=repo, verdict=verdict,
              reopened=reopened)
    return result


_REOPEN_LINE = re.compile(r"^\s*REOPEN:\s*(.+)$", re.MULTILINE | re.IGNORECASE)


def extract_reopen_list(text: str, *, allowed: set[int]) -> list[int]:
    """Ticket numbers the attestor asked to reopen.

    Restricted to the set it was shown. A model naming a number outside that set
    is guessing, and reopening on a guess sends a repair agent at a ticket
    nobody reviewed.
    """
    numbers: list[int] = []
    for match in _REOPEN_LINE.finditer(text):
        for token in re.findall(r"#?(\d+)", match.group(1)):
            number = int(token)
            if number in allowed and number not in numbers:
                numbers.append(number)
    return numbers



def legacy_route_task(project: dict[str, Any], issue: dict[str, Any], receipt_dir: Path) -> str:
    """Executable compatibility instructions use the exact existing Tau interfaces.

    The original transport's unchecked raw-GitHub close is replaced by native
    ticket closure AFTER proof. Requested apply_transport remains explicit in the
    retained inputs; it is never silently run early or dropped.
    """
    import shlex
    root, uv = project_worktree(project).resolve(), config.resolve_uv_bin()
    action = issue.get("watchdog_action")
    if action not in {"tau_handoff_dispatch", "add_tau_coder_command_spec"}:
        return ""
    if action == "tau_handoff_dispatch":
        fields = parse_issue_fields(issue.get("body") or "")
        start = repo_relative_existing_path(fields["start"], worktree=root)
        steps = parse_positive_int(fields.get("max_steps", "1"), field="max_steps")
        goal = parse_goal_hash(fields.get("active_goal_hash", config.TAU_ACTIVE_GOAL_HASH))
        requested = parse_bool(fields.get("apply_transport", "false"), field="apply_transport")
        extra = ""
    else:
        start = receipt_dir / "tau-coder-start-handoff.json"
        spec = tau_coder_spec_path(root)
        write_json(start, tau_coder_start_handoff(project_repo(project), int(issue["number"]), str(issue["url"]), spec))
        steps, goal, requested = 2, config.TAU_ACTIVE_GOAL_HASH, False
        extra = (f"Write the exact scoped coder spec at {spec}:\n"
                 f"```json\n{json.dumps(tau_coder_command_spec(uv), indent=2)}\n```\n"
                 "Also run the existing deterministic tests: " + shlex.join([
                  uv, "run", "--project", str(root), "pytest", "-q",
                  "tests/test_cli.py::test_cli_handoff_agent_adapter_emits_tau_handoff",
                  "tests/test_subagent_receipt.py::test_headless_subagent_receipt_import_does_not_require_textual"]) + "\n")
    loop = receipt_dir / "tau-command-loop"
    command = [uv, "run", "tau", "handoff-command-loop", "--start", str(start),
               "--receipt-dir", str(loop), "--agents-root", str(config.agents_root()),
               "--command-spec-root", str(root / "experiments/goal-locked-subagents/agent-command-specs"),
               "--active-goal-hash", goal, "--max-steps", str(steps)]
    transport = [uv, "run", "tau", "handoff-command-loop-github-transport",
                 str(loop / "command-loop-receipt.json"), "--receipt", str(receipt_dir / "tau-github-transport.json")]
    write_json(receipt_dir / "legacy-route-inputs.json", {"action": action, "command": command,
               "transport_preview_command": transport, "requested_apply_transport": requested,
               "terminal_mutation_adapter": "native_ticket.close after independent review and deterministic proof"})
    return ("\nCompatibility route (do not replace with a generic implementation):\n" + extra +
            shlex.join(command) + "\n" + shlex.join(transport) + "\n"
            "Read back and validate the native command-loop and transport receipt. "
            "A NEEDS_AGENT or human continuation is bounded progress, not completed ticket proof. "
            "Do not apply raw GitHub transport; the watchdog applies the native ticket lifecycle "
            "only after all required proof, with the retained requested transport intent visible.\n")

def required_proof_clauses(body: str) -> list[str]:
    collecting, clauses = False, []
    for line in body.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+)$", line.strip())
        if heading:
            collecting = heading.group(1).strip().lower() == "required proof"
        elif collecting and line.strip() and not line.strip().startswith("```"):
            clauses.append(line.strip())
    if not clauses:
        clauses = [m.group(1).strip() for m in re.finditer(r"(?im)^proof:\s*(.+)$", body)]
    return clauses

def finish_primary_operation(record) -> dict[str, Any]:
    """Shared by normal execution and recovery; never re-dispatches the provider."""
    from . import primary, native_ticket, target_content as content, models
    from .primary_models import TargetSnapshot, OwnedTargets, VerificationPlan, NativeClosure, encoded
    root, receipt_dir = Path(record.root), Path(record.receipt_dir)
    project = json.loads((receipt_dir / "dispatch-project.json").read_text())
    issue = json.loads((receipt_dir / "dispatch-issue.json").read_text())
    models.validate_project_entry(project)
    models.validate_issue(issue)
    live = github.get_issue(record.repo, record.issue_number)
    if content.digest((live.get("body") or "").encode()) != record.task_sha256:
        raise primary.Refusal("ticket acceptance changed; retain edits and reauthorize a new attempt")
    native_ticket.assert_mutable(record)
    primary.readonly_preflight(root, record.targets)
    stream = inspect_tau_stream(Path(record.ask_run_dir))
    if not stream.get("terminal"):
        raise primary.Refusal("native Tau run is not settled; recover the same retained run")
    if stream.get("terminal_status") not in {"PASS", "COMPLETED"}:
        refused = stream.get("semantic_refusal") or stream.get("compile_refusal") or stream.get("upstream_failure") or {}
        result = primary.failure(project, issue,
            f"Tau stopped {stream.get('terminal_status')}: {refused.get('failure_code', 'non_passing_run')}; no verified closure")
        result["tau_stream_monitor"] = stream
        result["tau_failure"] = refused
        return result
    monitor = _json_from_file(receipt_dir / "tau-stream-monitor.json") or {}
    if monitor.get("timed_out") or monitor.get("process_exit_code") not in {None, 0}:
        raise primary.Refusal("retained Ask invocation failed/timed out; no automatic closure")
    creator, reviewer = config.repair_seats(project)
    text = seat_response_text(Path(record.ask_run_dir), reviewer) or ""
    declared = [line.partition(":")[2].strip() for line in text.splitlines() if line.startswith("REVIEW_COMMIT:")]
    if len(declared) != 1 or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", declared[0]):
        raise primary.Refusal("review must bind exactly one full content-commit SHA")
    review_commit = declared[0]
    plans = [line.partition(":")[2].strip() for line in text.splitlines() if line.startswith("VERIFY_PLAN:")]
    if len(plans) != 1:
        raise primary.Refusal("review must supply exactly one native verification plan")
    plan = VerificationPlan.model_validate(json.loads(plans[0]))
    clauses = required_proof_clauses(str(issue.get("body") or ""))
    if not clauses and record.action == "ticket_repair":
        raise primary.Refusal("ordinary ticket has no explicit required proof; do not invent acceptance")
    clauses = clauses or ["legacy_native_route"]
    if set(plan.coverage) != set(clauses) or any(not value.strip() for value in plan.coverage.values()):
        raise primary.Refusal("proof plan does not cover every exact required clause")
    before = TargetSnapshot.model_validate(json.loads((receipt_dir / "primary-before.json").read_text()))
    after = content.snapshot(root, record.targets, before.remote_sha, receipt_dir / "primary-after-blobs")
    if after.index_entries != before.index_entries:
        raise primary.Refusal("target's shared index intent changed; preserve it")
    if content.remote_entries(root, review_commit, record.targets) != content.versions(after):
        raise primary.Refusal("working target bytes do not match the independently reviewed commit")
    if review_commit != before.remote_sha:
        parent = content.git_bytes(root, "rev-parse", f"{review_commit}^").decode().strip()
        message = content.git_bytes(root, "show", "-s", "--format=%B", review_commit).decode()
        if parent != before.remote_sha or f"Watchdog-Run: {record.run_id}\n" not in message:
            raise primary.Refusal("commit is not this run's scoped authoring artifact; old repair work is not new proof")
        content.assert_scoped_commit(root, review_commit, record.targets)
    # Exact authored content may survive a failed proof and be retried by this same task.
    owned = OwnedTargets(repo=record.repo, issue_number=record.issue_number, task_sha256=record.task_sha256,
                         run_id=record.run_id, targets=record.targets, files=after.files, provenance="settled_attempt")
    write_json(primary._area(root) / "owned" / f"{record.issue_number}.json", encoded(owned))
    write_json(receipt_dir / "primary-after.json", encoded(after))
    initial_gate = evaluate_repair_proof(ask_run_dir=Path(record.ask_run_dir), issue_body=str(issue.get("body") or ""),
        creator=creator, reviewer=reviewer, repair_worktree=root, not_before=record.dispatched_at,
        reviewed_commit=review_commit)
    if not initial_gate["ok"]:
        raise primary.Refusal("independent proof gate failed: " + "; ".join(initial_gate["reasons"]))
    needed = {str(Path(p).expanduser().resolve() if Path(p).is_absolute() else (root / p).resolve())
              for p in initial_gate["required_proof_artifacts"]}
    provided = {str(Path(p).expanduser().resolve() if Path(p).is_absolute() else (root / p).resolve()) for p in plan.artifacts}
    if not needed <= provided:
        raise primary.Refusal("native verification plan omits a mandatory result artifact")
    prior_stamps = {p: (Path(p).stat().st_mtime_ns, Path(p).stat().st_size) if Path(p).exists() else None
                    for p in provided}
    verify_started = time.time()
    commands = native_ticket.verify(root, record.issue_number, plan,
        timeout_s=int(project.get("ticket_repair_timeout_s", 1800)))
    write_json(receipt_dir / "native-verification-commands.json", {"commands": commands})
    content.require_unchanged(after, content.snapshot(root, record.targets, before.remote_sha))
    artifacts = [inspect_proof_artifact(p, not_before=verify_started) for p in sorted(provided)]
    unchanged_results = [p for p in provided if Path(p).exists() and
                         prior_stamps[p] == (Path(p).stat().st_mtime_ns, Path(p).stat().st_size)]
    if unchanged_results:
        raise primary.Refusal("native verify did not rewrite required result files: " + str(unchanged_results))
    if not artifacts or not all(a["passed"] for a in artifacts):
        raise primary.Refusal("native ticket verification did not freshly pass every required result")
    gate_path = receipt_dir / "repair-proof-gate.json"
    gate = {**initial_gate, "native_verification": commands, "native_artifacts": artifacts,
            "coverage": plan.coverage, "reviewed_commit": review_commit}
    write_json(gate_path, gate)
    remote_required = bool(config.auto_land_main(project))
    commit = content.publish(root, before, after, receipt_dir, record.run_id, record.issue_number,
                             remote_required=remote_required)
    proof = receipt_dir / "native-ticket-proof.md"
    review = receipt_dir / "native-ticket-review.md"
    proof.write_text(f"<!-- watchdog-proof:{record.owner_token} -->\n"
        f"Verified {record.repo}#{record.issue_number}; content commit {commit}.\n"
        f"Remote publication required: {remote_required}. Local HEAD/index were not used as publication state.\n"
        f"Target scope: {', '.join(record.targets)}\n"
        "```json\n" + json.dumps(gate, indent=2) + "\n```\n")
    review.write_text(text)
    closure = NativeClosure(proof_path=str(proof), proof_sha256=content.digest(proof.read_bytes()),
        review_path=str(review), review_sha256=content.digest(review.read_bytes()), commit=commit,
        remote_required=remote_required, scope=record.targets, content=after)
    primary.checkpoint("closing", closure=encoded(closure))
    closed = native_ticket.close(primary.current())
    result = {**(record.result or _new_result(project, issue, record.action)), **closed,
              "requires_human_input": False, "proof_gate": str(gate_path),
              "artifacts": [str(proof), str(review), str(gate_path), str(receipt_dir / "tau-stream-monitor.json")],
              "preservation_scope": "target files and target index entries; unrelated cron changes are not attributed to this run"}
    primary.checkpoint("releasing", result=result)
    return result
