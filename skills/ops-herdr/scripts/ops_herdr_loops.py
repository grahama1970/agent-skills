#!/usr/bin/env python3
"""Bounded creator/reviewer loop helpers for Herdr workstations.

The loop controller uses Herdr only for live pane control. Work orders,
creator receipts, reviewer receipts, and final JSON files remain the canonical
source of truth for downstream project agents and monitors.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import shlex
import time
from pathlib import Path
from typing import Any

from ops_herdr_core import (
    create_tab,
    load_dotenv_once,
    create_workspace,
    ensure_dir,
    manifest_path_from_run_dir,
    read_json,
    run_herdr,
    save_manifest,
    slugify,
    utc_stamp,
    write_json,
)

# Idempotent: core loads .env on import; repeated here so importing this module
# alone still reads a populated environment.
load_dotenv_once()


@dataclasses.dataclass(slots=True)
class LoopTask:
    """Describe one bounded creator/reviewer task from JSON input."""

    task_id: str
    title: str
    prompt: str
    max_iterations: int = 3


def load_loop_tasks(path: Path) -> list[LoopTask]:
    """Load bounded loop task definitions from a JSON array."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Task file must contain a JSON array")
    tasks: list[LoopTask] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each task entry must be a JSON object")
        tasks.append(LoopTask(**item))
    return tasks


def receipt_ready(path: Path) -> dict[str, Any] | None:
    """Return parsed receipt JSON when a complete object exists."""
    if not path.exists():
        return None
    try:
        return read_json(path)
    except json.JSONDecodeError:
        return None


async def wait_for_receipt(path: Path, timeout_s: int, poll_s: float = 5.0) -> dict[str, Any]:
    """Wait for an agent receipt file to appear and parse cleanly."""
    start = time.monotonic()
    while time.monotonic() - start <= timeout_s:
        receipt = receipt_ready(path)
        if receipt is not None:
            return receipt
        await asyncio.sleep(poll_s)
    raise TimeoutError(f"Timed out waiting for receipt: {path}")


def build_creator_prompt(task: LoopTask, iteration: int, work_order: Path, receipt: Path, feedback: str) -> str:
    """Build the durable instruction sent to a creator pane."""
    return f"""
You are the CREATOR in a bounded Herdr-visible T'au loop.

Task: {task.title}
Task id: {task.task_id}
Iteration: {iteration}

Read the work order: {work_order}
Previous reviewer feedback: {feedback or 'none'}

Rules:
- Stay scoped to the work order.
- Prefer minimal, receipt-backed changes.
- Run relevant validation when possible.
- Do not fake success; write BLOCKED with a reason.

Write this JSON receipt exactly at:
{receipt}

Schema:
{{
  "role": "creator",
  "task_id": "{task.task_id}",
  "iteration": {iteration},
  "status": "DONE|BLOCKED",
  "summary": "what changed",
  "changed_files": ["repo-relative/path"],
  "validation": [{{"command": "...", "exit_code": 0, "summary": "..."}}],
  "blocked_reason": null,
  "handoff": "reviewer instructions and evidence"
}}

After writing the receipt, print:
TAU_CREATOR_RECEIPT_WRITTEN {receipt}
""".strip()


def build_reviewer_prompt(task: LoopTask, iteration: int, work_order: Path, creator_receipt: Path, receipt: Path) -> str:
    """Build the durable instruction sent to a reviewer pane."""
    return f"""
You are the REVIEWER in a bounded Herdr-visible T'au loop.

Task: {task.title}
Task id: {task.task_id}
Iteration: {iteration}

Read the work order: {work_order}
Read the creator receipt: {creator_receipt}

Rules:
- Review scope, evidence, diffs, and validation.
- Do not rubber-stamp.
- Write PASS only when complete.
- Write NEEDS_CHANGES for fixable issues.
- Write BLOCKED for missing evidence or unsafe ambiguity.

Write this JSON receipt exactly at:
{receipt}

Schema:
{{
  "role": "reviewer",
  "task_id": "{task.task_id}",
  "iteration": {iteration},
  "verdict": "PASS|NEEDS_CHANGES|BLOCKED",
  "summary": "review result",
  "feedback": "specific actionable feedback when not PASS",
  "evidence": [{{"kind": "file|command|receipt|diff", "reference": "...", "summary": "..."}}]
}}

After writing the receipt, print:
TAU_REVIEWER_RECEIPT_WRITTEN {receipt}
""".strip()


def write_work_order(run_dir: Path, task: LoopTask) -> Path:
    """Write the durable task work order and return its path."""
    work_order = run_dir / "work-orders" / "task.md"
    ensure_dir(work_order.parent)
    work_order.write_text(f"# {task.title}\n\nTask id: `{task.task_id}`\n\n{task.prompt}\n", encoding="utf-8")
    return work_order


def start_loop_agent(
    *,
    name: str,
    role: str,
    command: str,
    split: str | None,
    repo: Path,
    workspace_id: str,
    tab_id: str,
    run_dir: Path,
    work_order: Path,
    session: str | None,
    herdr_bin: str,
) -> None:
    """Start one loop agent in the requested Herdr workspace tab."""
    args = [
        "agent",
        "start",
        name,
        "--cwd",
        str(repo),
        "--workspace",
        workspace_id,
        "--tab",
        tab_id,
        "--env",
        f"TAU_ROLE={role}",
        "--env",
        f"TAU_RUN_DIR={run_dir}",
        "--env",
        f"TAU_WORK_ORDER={work_order}",
        "--no-focus",
    ]
    if split:
        args.extend(["--split", split])
    args.append("--")
    args.extend(shlex.split(command))
    run_herdr(args, herdr_bin=herdr_bin, session=session)


async def run_one_loop(
    *,
    task: LoopTask,
    repo: Path,
    run_root: Path,
    creator_cmd: str,
    reviewer_cmd: str,
    session: str | None,
    herdr_bin: str,
    receipt_timeout_s: int,
) -> dict[str, Any]:
    """Run one bounded creator/reviewer loop in a dedicated Herdr workstation."""
    label = f"tau-{slugify(task.task_id)}"
    run_id = f"{utc_stamp()}-{slugify(task.task_id)}"
    run_dir = ensure_dir(run_root / run_id)
    work_order = write_work_order(run_dir, task)
    workspace_id = create_workspace(label=label, cwd=repo, session=session, herdr_bin=herdr_bin, env_values=[], dry_run=False)
    agents_tab = create_tab(workspace_id=workspace_id, label="agents", cwd=repo, session=session, herdr_bin=herdr_bin, env_values=[], dry_run=False)
    logs_tab = create_tab(workspace_id=workspace_id, label="receipts-logs", cwd=repo, session=session, herdr_bin=herdr_bin, env_values=[], dry_run=False)
    manifest = {
        "schema_version": 1,
        "kind": "herdr-loop-workstation",
        "run_id": run_id,
        "created_at": utc_stamp(),
        "label": label,
        "session": session or os.environ.get("HERDR_SESSION") or "default",
        "repo": str(repo),
        "cwd": str(repo),
        "run_dir": str(run_dir),
        "workspace_id": workspace_id,
        "tabs": {"agents": agents_tab, "receipts-logs": logs_tab},
        "task": dataclasses.asdict(task),
        "events_jsonl": str(run_dir / "events.jsonl"),
    }
    save_manifest(manifest_path_from_run_dir(run_dir), manifest)
    creator_name = f"{slugify(task.task_id)}-creator"
    reviewer_name = f"{slugify(task.task_id)}-reviewer"
    start_loop_agent(name=creator_name, role="creator", command=creator_cmd, split=None, repo=repo, workspace_id=workspace_id, tab_id=agents_tab, run_dir=run_dir, work_order=work_order, session=session, herdr_bin=herdr_bin)
    start_loop_agent(name=reviewer_name, role="reviewer", command=reviewer_cmd, split="right", repo=repo, workspace_id=workspace_id, tab_id=agents_tab, run_dir=run_dir, work_order=work_order, session=session, herdr_bin=herdr_bin)
    feedback = "none"
    for iteration in range(1, task.max_iterations + 1):
        creator_receipt = run_dir / "receipts" / f"creator-{iteration}.json"
        reviewer_receipt = run_dir / "receipts" / f"reviewer-{iteration}.json"
        run_herdr(["agent", "send", creator_name, build_creator_prompt(task, iteration, work_order, creator_receipt, feedback) + "\n"], herdr_bin=herdr_bin, session=session)
        creator_data = await wait_for_receipt(creator_receipt, timeout_s=receipt_timeout_s)
        if creator_data.get("status") == "BLOCKED":
            return finish(run_dir, task.task_id, run_id, "BLOCKED", iteration, "creator")
        run_herdr(["agent", "send", reviewer_name, build_reviewer_prompt(task, iteration, work_order, creator_receipt, reviewer_receipt) + "\n"], herdr_bin=herdr_bin, session=session)
        reviewer_data = await wait_for_receipt(reviewer_receipt, timeout_s=receipt_timeout_s)
        verdict = reviewer_data.get("verdict")
        if verdict == "PASS":
            return finish(run_dir, task.task_id, run_id, "PASS", iteration, None)
        if verdict == "BLOCKED":
            return finish(run_dir, task.task_id, run_id, "BLOCKED", iteration, "reviewer")
        feedback = str(reviewer_data.get("feedback") or "Reviewer requested changes without details.")
    return finish(run_dir, task.task_id, run_id, "NEEDS_CHANGES", task.max_iterations, None, "max_iterations_exhausted")


def finish(run_dir: Path, task_id: str, run_id: str, status: str, iteration: int, blocked_by: str | None, reason: str | None = None) -> dict[str, Any]:
    """Write and return the final loop receipt."""
    final = {"task_id": task_id, "run_id": run_id, "status": status, "iteration": iteration, "run_dir": str(run_dir)}
    if blocked_by:
        final["blocked_by"] = blocked_by
    if reason:
        final["reason"] = reason
    write_json(run_dir / "final.json", final)
    return final
