"""Bind reviewer-only recovery to its native lease, result and admitted outputs.

Historical DAGs remain evidence, never candidates for current settlement.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any

from .core import load_json, write_json

FENCE = "watchdog-resume-generation.json"


def file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def begin(record, run_dir: Path) -> Path:
    receipts = run_dir / "tau-receipts"
    path = receipts / FENCE
    history = receipts / f"watchdog-resume-prior-{record.lease_event.id}"
    history.mkdir(parents=True, exist_ok=False)
    prior_command = run_dir.parent.parent / "watchdog-reattach-resume-command.json"
    if prior_command.is_file():
        shutil.copyfile(prior_command, history / "command.json")
    for node in load_json(run_dir / "dag.json").get("nodes", []):
        for name in ("node-receipt.json", "response.meta.json", "response.md"):
            source = run_dir / "node-artifacts" / node["id"] / name
            if source.is_file():
                target = history / node["id"] / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    if path.exists():
        previous = load_json(path)
        write_json(receipts / f"watchdog-resume-generation-{previous['lease_event_id']}.json", previous)
    write_json(path, {
        "schema": "agent_skills.project_watchdog.resume_generation.v1",
        "run_dir": str(run_dir.resolve()), "run_id": run_dir.name,
        "journal": record.journal, "lease_event_id": record.lease_event.id,
        "lease_agent": record.lease_agent, "started_at": time.time(),
        "source_sha256": file_hash(run_dir / "dag.json"),
        "prior_result_sha256": file_hash(receipts / "command-spec-resume-result.json"),
        "prior_prep_sha256": file_hash(receipts / "command-spec-resume-prep.json"),
        "prior_store_sha256": file_hash(receipts / "dag-run.sqlite3"),
        "command_receipt": None,
    })
    return path


def complete(path: Path, row: dict[str, Any]) -> None:
    fence = load_json(path)
    fence["command_receipt"] = row
    write_json(path, fence)


def _admitted(store: Path, run_id: str) -> dict[str, tuple[str, dict[str, Any]]]:
    with sqlite3.connect(store.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute(
            "SELECT node_id,attempt_id,committed_json FROM dag_node_attempts "
            "JOIN dag_attempt_outputs USING(attempt_id) "
            "WHERE run_id=? AND state='SETTLED' AND committed_json IS NOT NULL ORDER BY attempt_no",
            (run_id,),
        )
        return {node: (attempt, json.loads(output)) for node, attempt, output in rows}


def observe(ask_root: Path) -> dict[str, Any] | None:
    # Only direct project-run children are authoritative. Never recurse into
    # archived source DAGs, copied workers, or generated command-spec plans.
    roots = [ask_root] if (ask_root / "dag.json").is_file() else [
        child for child in ask_root.iterdir() if child.is_dir() and (child / "dag.json").is_file()
    ]
    fences = [root / "tau-receipts" / FENCE for root in roots if (root / "tau-receipts" / FENCE).exists()]
    if not fences:
        return None
    observation: dict[str, Any] = {
        "terminal": False, "terminal_status": None, "stream_readable": True,
        "reason": "waiting for current resume generation", "current_status": "RUNNING",
    }
    try:
        if len(fences) != 1:
            raise ValueError("ambiguous current resume generation")
        path = fences[0]
        receipts, run_dir = path.parent, path.parent.parent
        fence = load_json(path)
        if (fence.get("schema") != "agent_skills.project_watchdog.resume_generation.v1"
                or Path(fence["run_dir"]).resolve() != run_dir.resolve()
                or fence["source_sha256"] != file_hash(run_dir / "dag.json")):
            raise ValueError("resume generation source identity mismatch")
        observation["resume_generation"] = fence["lease_event_id"]
        observation["terminal_source"] = str(path)
        command = fence.get("command_receipt")
        control = None
        if command is not None:
            try:
                control = json.loads(command.get("stdout") or "{}")
            except (ValueError, TypeError):
                control = {}
            valid_control = (isinstance(control, dict)
                and control.get("schema") == "ask.run_control.v1"
                and control.get("action") == "resume" and control.get("run_id") == fence["run_id"])
            observation["resume_control"] = control
            observation["command_receipt"] = command
            if not valid_control:
                control = {}
        result_path = receipts / "command-spec-resume-result.json"
        fresh_result = file_hash(result_path) not in {None, fence["prior_result_sha256"]}
        if not fresh_result:
            if command is not None:
                unchanged = (
                    file_hash(receipts / "command-spec-resume-prep.json") == fence["prior_prep_sha256"]
                    and file_hash(receipts / "dag-run.sqlite3") == fence["prior_store_sha256"]
                )
                failed = (command.get("exit_code") != 0 or not control
                          or control.get("outcome") == "failed" or control.get("returncode") not in {None, 0})
                observation.update(
                    invocation_failed=bool(unchanged and failed),
                    reason="resume invocation failed before native state changed" if unchanged and failed
                    else "resume result absent; current execution not settled",
                )
            return observation
        result = load_json(result_path)
        plan_path = receipts / "command-spec-resume/dag.json"
        native_path = receipts / "dag-receipt.json"
        native = load_json(native_path)
        source = load_json(run_dir / "dag.json")
        journal = result.get("watchdog_journal") or {}
        archive = Path(result.get("archive_path") or "")
        if (result.get("schema") != "tau.project_dag_command_spec_resume.v1"
                or result.get("dag_id") != source.get("dag_id")
                or Path(result["contract_path"]).resolve() != (run_dir / "dag.json").resolve()
                or Path(result["resume_contract_path"]).resolve() != plan_path.resolve()
                or Path(result["receipt_dir"]).resolve() != receipts.resolve()
                or journal.get("path") != fence["journal"]
                or journal.get("lease_event_id") != fence["lease_event_id"]
                or journal.get("lease_agent") != fence["lease_agent"]
                or archive.parent.resolve() != receipts.resolve()
                or file_hash(archive) != fence["prior_store_sha256"]
                or native.get("schema") != "tau.dag_receipt.v1"
                or native.get("dag_id") != source.get("dag_id")
                or native.get("active_goal_hash") != source.get("goal", {}).get("goal_hash")
                or native.get("contract_sha256") != "sha256:" + str(file_hash(plan_path))
                or result.get("execution") != native
                or result.get("status") != native.get("status")):
            raise ValueError("resume result does not bind current lease/source/native receipt")
        preserved = result.get("preserved_nodes") or []
        if native.get("durable") is True:
            before = _admitted(archive, source["dag_id"])
            after = _admitted(receipts / "dag-run.sqlite3", source["dag_id"])
            for node in preserved:
                old_id, old = before[node]
                _, new = after[node]
                if (old_id not in result["preserved_attempt_ids"]
                        or old.get("status") != "PASS" or new.get("status") != "PASS"
                        or old.get("accepted_output") != new.get("accepted_output")):
                    raise ValueError("preserved node admission changed: " + node)
        elif native.get("command_executed") is not False:
            raise ValueError("resume has neither durable settlement nor pre-dispatch refusal")
        status = str(native.get("status"))
        observation.update(
            terminal=status in {"PASS", "FAIL", "FAILED", "ERROR", "BLOCKED", "NEEDS_ATTENTION", "COMPLETED"},
            terminal_status=status, current_status=status, reason="current native resume result verified",
            terminal_source=str(result_path), authoritative_plan=str(plan_path),
            resume_result=result, node_receipts=[],
        )
        for node in source.get("nodes", []):
            node_path = run_dir / "node-artifacts" / node["id"] / "node-receipt.json"
            if node_path.is_file():
                observed = load_json(node_path)
                observation["node_receipts"].append({"path": str(node_path), "readable": True,
                    "node_id": node["id"], "status": observed.get("status")})
        if status not in {"PASS", "COMPLETED"}:
            observation["upstream_failure"] = {"failure_code": native.get("verdict"),
                                               "alerts": native.get("alerts", [])}
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        observation.update(terminal=False, terminal_status=None, reason=str(exc),
                           resume_integrity_error=str(exc))
    return observation
