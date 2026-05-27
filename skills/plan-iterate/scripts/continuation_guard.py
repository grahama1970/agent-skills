#!/usr/bin/env python3
"""Fail-closed final-response guard for plan-iterate ledgers."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from phase_status import load_status, validate_status


SCHEMA = "plan_iterate.continuation_guard.v1"
TERMINAL_PHASE_STATES = {"accepted", "superseded", "abandoned"}
FIXABLE_STATES = {"planned", "implementing", "ready_for_review", "external_review_passed"}
BLOCKING_STATES = {"local_validation_failed", "external_review_blocked"}
COMPLETED_NODE_STATES = {"accepted", "complete", "completed"}
RESERVED_LEDGER_DIRS = {"plans"}
PROJECT_KNOWLEDGE_AGENT_EXECUTABLE_MARKERS = (
    "next agent-executable candidate",
    "next agent executable candidate",
    "next agent-executable phase",
    "next agent executable phase",
    "next action:",
)

PROJECT_KNOWLEDGE_UNMET_GOAL_MARKERS = (
    "current blocker",
    "still blocked",
    "remaining blocker",
    "remaining issue",
    "do not claim full",
    "missing_source",
    "completeness_gate.passing=false",
    "project still blocked",
    "not complete",
)

PROJECT_KNOWLEDGE_PROOF_MARKERS = (
    "browser proof",
    "browser visual proof",
    "browser visual rendering",
    "cdp proof",
    "screenshot proof",
    "public browser",
)

PROJECT_KNOWLEDGE_MISSING_PROOF_QUALIFIERS = (
    "missing",
    "needs",
    "need ",
    "required",
    "require ",
    "lacks",
    "lack ",
    "without",
    "must add",
    "must capture",
    "must provide",
    "unproven",
    "not proven",
    "not verified",
    "no ",
)

CLOSURE_CLAIM_RE = re.compile(
    r"""(
        \bdone\b|\bcomplete(?:d)?\b|\bfinished\b|\bfixed\b|\bgreen\b|\bpass(?:ed)?\b|
        \bverified\b|\bclosed\b|\bready\b|all\s+(?:set|good|clear)|no\s+blockers|
        overall\s+complete|project\s+complete|work\s+complete
    )""",
    re.IGNORECASE | re.VERBOSE,
)

EXPLICIT_STOP_RE = re.compile(
    r"""(
        \bBLOCKED\b|\bHUMAN_REQUIRED\b|\bMAX_ITERATIONS_REACHED\b|
        \bblocked\b|\bblocker\b|\bnon[- ]terminal\b|\bremaining\s+phase\b|
        \bremaining\s+blocker\b|\bnot\s+complete\b|\bcannot\s+claim\b|
        \bneeds\s+human\b|\bhuman\s+required\b|\bvalidation\s+failed\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)

HARD_STOP_RE = re.compile(
    r"""(
        \bHUMAN_REQUIRED\b|\bMAX_ITERATIONS_REACHED\b|
        \bneeds\s+human\b|\bhuman\s+required\b|\bmax\s+iterations\b|
        repeated\s+blocker|dogpile\s+(?:completed|evaluated|exhausted)|
        cannot\s+continue\s+without\s+human|requires\s+credential|requires\s+admin
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def phase_sort_key(phase_id: str) -> list[Any]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", phase_id)]


def _blockers(status: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = status.get("blockers")
    if not isinstance(blockers, list):
        return []
    active: list[dict[str, Any]] = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            active.append({"description": str(blocker), "status": "unknown"})
            continue
        blocker_status = str(blocker.get("status") or blocker.get("state") or "open").lower()
        if blocker_status in {"resolved", "closed", "fixed", "accepted"}:
            continue
        active.append(blocker)
    return active


def _blocker_occurrences(blocker: dict[str, Any]) -> int:
    try:
        return int(blocker.get("occurrences") or 1)
    except (TypeError, ValueError):
        return 1


def _is_escalated(blocker: dict[str, Any]) -> bool:
    return bool(blocker.get("escalated"))


def _has_dogpile_stop_proof(blocker: dict[str, Any]) -> bool:
    return bool(
        blocker.get("dogpile_evaluated")
        or blocker.get("dogpile_not_applicable_rationale")
        or blocker.get("dogpile_report_artifact")
    )


def _has_human_dependency(blocker: dict[str, Any]) -> bool:
    return bool(
        str(blocker.get("human_dependency_type") or "").strip()
        and str(blocker.get("human_dependency_detail") or "").strip()
    )


def _has_hard_stop_proof(blocker: dict[str, Any]) -> bool:
    return (
        _blocker_occurrences(blocker) >= 2
        and _is_escalated(blocker)
        and _has_dogpile_stop_proof(blocker)
        and _has_human_dependency(blocker)
    )


def _is_actionable_blocking_row(row: dict[str, Any]) -> bool:
    if row["state"] not in BLOCKING_STATES:
        return False
    blockers = row["active_blockers"]
    if not blockers:
        return True
    return any(not _has_hard_stop_proof(blocker) for blocker in blockers)


def _node_completion_state(node: dict[str, Any], status: dict[str, Any]) -> str:
    completed_nodes = status.get("completed_plan_nodes")
    completed_ids = {str(node_id) for node_id in completed_nodes} if isinstance(completed_nodes, list) else set()
    node_id = str(node.get("id") or "")
    if node_id and node_id in completed_ids:
        return "completed"
    state = str(node.get("state") or node.get("status") or "").lower()
    if state in COMPLETED_NODE_STATES:
        return "completed"
    active_phase_id = str(status.get("phase_id") or "")
    if node_id and node_id == active_phase_id and str(status.get("status")) in TERMINAL_PHASE_STATES:
        return "completed"
    return "pending"


def _plan_graph_nodes(graph: Any) -> list[dict[str, Any]]:
    if not isinstance(graph, dict):
        return []
    nodes = graph.get("nodes")
    if isinstance(nodes, list):
        return [node for node in nodes if isinstance(node, dict)]
    layers = graph.get("layers")
    if not isinstance(layers, list):
        return []
    graph_nodes: list[dict[str, Any]] = []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        layer_nodes = layer.get("nodes")
        if isinstance(layer_nodes, list):
            graph_nodes.extend(node for node in layer_nodes if isinstance(node, dict))
    return graph_nodes


def _accepted_row_has_remaining_graph_work(row: dict[str, Any]) -> bool:
    if row["state"] != "accepted":
        return False
    status = row.get("status") if isinstance(row.get("status"), dict) else {}
    active_artifact = status.get("active_plan_graph_artifact") if isinstance(status, dict) else None
    if not active_artifact:
        return False
    graph_path = Path(row["phase_dir"]) / str(active_artifact)
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    for node in _plan_graph_nodes(graph):
        if _node_completion_state(node, status) != "completed":
            return True
    return False


def _project_knowledge_continuation(repo_root: Path) -> dict[str, Any] | None:
    knowledge_path = repo_root / "PROJECT_KNOWLEDGE.md"
    if not knowledge_path.exists():
        return None
    try:
        lines = knowledge_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    matches: list[dict[str, Any]] = []
    agent_executable = False
    for line_number, line in enumerate(lines, 1):
        normalized = line.lower()
        executable_match = any(marker in normalized for marker in PROJECT_KNOWLEDGE_AGENT_EXECUTABLE_MARKERS)
        unmet_match = any(marker in normalized for marker in PROJECT_KNOWLEDGE_UNMET_GOAL_MARKERS)
        proof_marker_match = any(marker in normalized for marker in PROJECT_KNOWLEDGE_PROOF_MARKERS)
        missing_proof_match = proof_marker_match and any(
            qualifier in normalized for qualifier in PROJECT_KNOWLEDGE_MISSING_PROOF_QUALIFIERS
        )
        unmet_match = unmet_match or missing_proof_match
        if not executable_match and not unmet_match:
            continue
        if executable_match:
            agent_executable = True
        matches.append(
            {
                "path": str(knowledge_path),
                "line": line_number,
                "text": line.strip(),
                "agent_executable": executable_match,
            }
        )
    if not matches:
        return None
    return {
        "path": str(knowledge_path),
        "agent_executable": agent_executable,
        "matches": matches[:12],
    }


def load_ledger(repo_root: Path, root: Path) -> list[dict[str, Any]]:
    ledger_root = root if root.is_absolute() else repo_root / root
    rows: list[dict[str, Any]] = []
    if not ledger_root.exists():
        return rows

    phase_dirs: list[Path] = []
    for candidate in sorted(path for path in ledger_root.iterdir() if path.is_dir()):
        if candidate.name in RESERVED_LEDGER_DIRS:
            continue
        if (candidate / "PHASE_STATUS.json").exists():
            phase_dirs.append(candidate)
            continue
        nested_phase_dirs = sorted(
            path
            for path in candidate.iterdir()
            if path.is_dir() and ((path / "PHASE_STATUS.json").exists() or (path / "PHASE_REVIEW_REQUEST.md").exists())
        )
        if nested_phase_dirs:
            phase_dirs.extend(nested_phase_dirs)
        else:
            phase_dirs.append(candidate)

    for phase_dir in phase_dirs:
        status_file = phase_dir / "PHASE_STATUS.json"
        if not status_file.exists():
            rows.append(
                {
                    "phase_id": phase_dir.name,
                    "phase_dir": str(phase_dir),
                    "state": "missing_status",
                    "status": {},
                    "valid": False,
                    "errors": ["missing_status: PHASE_STATUS.json"],
                    "active_blockers": [],
                    "sort_key": phase_sort_key(phase_dir.name),
                }
            )
            continue
        try:
            status = load_status(status_file)
        except Exception as exc:
            rows.append(
                {
                    "phase_id": phase_dir.name,
                    "phase_dir": str(phase_dir),
                    "state": "unreadable",
                    "status": {},
                    "valid": False,
                    "errors": [f"unreadable_status: {exc}"],
                    "active_blockers": [],
                    "sort_key": phase_sort_key(phase_dir.name),
                }
            )
            continue
        phase_id = str(status.get("phase_id") or phase_dir.name)
        errors = validate_status(status, phase_dir, repo_root)
        rows.append(
            {
                "phase_id": phase_id,
                "phase_dir": str(phase_dir),
                "state": str(status.get("status") or "unknown"),
                "status": status,
                "valid": not errors,
                "errors": errors,
                "active_blockers": _blockers(status),
                "sort_key": phase_sort_key(phase_id),
            }
        )
    rows.sort(key=lambda row: row["sort_key"])
    return rows


def evaluate(repo_root: Path, root: Path, message: str = "") -> dict[str, Any]:
    rows = load_ledger(repo_root, root)
    active_rows = [row for row in rows if row["state"] not in TERMINAL_PHASE_STATES]
    fixable_rows = [row for row in active_rows if row["state"] in FIXABLE_STATES]
    blocking_rows = [row for row in active_rows if row["state"] in BLOCKING_STATES or row["active_blockers"]]
    actionable_blocking_rows = [row for row in blocking_rows if _is_actionable_blocking_row(row)]
    accepted_graph_rows = [row for row in rows if _accepted_row_has_remaining_graph_work(row)]
    invalid_rows = [row for row in rows if not row["valid"]]
    project_knowledge = _project_knowledge_continuation(repo_root)
    project_knowledge_agent_executable = bool(project_knowledge and project_knowledge["agent_executable"])

    has_closure_claim = bool(CLOSURE_CLAIM_RE.search(message or ""))
    reports_stop_state = bool(EXPLICIT_STOP_RE.search(message or ""))
    reports_hard_stop = bool(HARD_STOP_RE.search(message or ""))
    should_continue = bool(
        fixable_rows
        or actionable_blocking_rows
        or invalid_rows
        or accepted_graph_rows
        or project_knowledge_agent_executable
    )
    has_unresolved_work = bool(active_rows or invalid_rows or accepted_graph_rows or project_knowledge)
    block_final = bool(
        has_unresolved_work
        and (
            should_continue
            or invalid_rows
            or (has_closure_claim and not reports_hard_stop)
            or (reports_stop_state and not reports_hard_stop)
        )
    )

    if fixable_rows:
        terminal_state = "PASS"
        decision = "CONTINUE"
        reason = "fixable non-terminal phase work remains"
    elif actionable_blocking_rows:
        terminal_state = "PASS"
        decision = "CONTINUE"
        reason = "blocking phase status still has agent-actionable recovery work"
    elif accepted_graph_rows:
        terminal_state = "PASS"
        decision = "CONTINUE"
        reason = "accepted phase active plan graph still has uncompleted work"
    elif project_knowledge_agent_executable:
        terminal_state = "PASS"
        decision = "PROJECT_GOALS_REMAIN"
        reason = "PROJECT_KNOWLEDGE.md names agent-executable remaining work"
    elif invalid_rows:
        terminal_state = "PASS"
        decision = "CONTINUE"
        reason = "invalid phase ledger work is agent-actionable and must be repaired"
    elif blocking_rows or invalid_rows:
        terminal_state = "BLOCKED"
        decision = "BLOCKED"
        reason = "ledger has blocking or invalid non-terminal phase work"
    elif active_rows:
        terminal_state = "HUMAN_REQUIRED"
        decision = "HUMAN_REQUIRED"
        reason = "ledger has non-terminal phase work with ambiguous status"
    else:
        terminal_state = "PASS"
        decision = "OVERALL_COMPLETE" if rows else "NO_LEDGER"
        reason = "no active plan-iterate phase work found"

    return {
        "schema": SCHEMA,
        "repo_root": str(repo_root),
        "ledger_root": str((root if root.is_absolute() else repo_root / root)),
        "decision": decision,
        "controller_terminal_state": terminal_state,
        "should_continue": should_continue,
        "block_final": block_final,
        "reason": reason,
        "has_closure_claim": has_closure_claim,
        "reports_stop_state": reports_stop_state,
        "reports_hard_stop": reports_hard_stop,
        "phase_count": len(rows),
        "active_phase_count": len(active_rows),
        "fixable_phase_count": len(fixable_rows),
        "blocking_phase_count": len(blocking_rows),
        "actionable_blocking_phase_count": len(actionable_blocking_rows),
        "accepted_graph_remaining_phase_count": len(accepted_graph_rows),
        "invalid_phase_count": len(invalid_rows),
        "project_knowledge_continuation": project_knowledge,
        "active_phases": [
            {
                "phase_id": row["phase_id"],
                "state": row["state"],
                "valid": row["valid"],
                "error_count": len(row["errors"]),
                "errors": row["errors"],
                "active_blocker_count": len(row["active_blockers"]),
            }
            for row in active_rows
        ],
        "accepted_graph_remaining_phases": [
            {
                "phase_id": row["phase_id"],
                "state": row["state"],
                "valid": row["valid"],
            }
            for row in accepted_graph_rows
        ],
    }


def _read_message(args: argparse.Namespace) -> str:
    if args.message_file:
        return Path(args.message_file).read_text(encoding="utf-8")
    return args.message or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard plan-iterate final responses against premature closure")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--root", default=".plan-iterate")
    parser.add_argument("--message", default="")
    parser.add_argument("--message-file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = evaluate(Path(args.repo_root).resolve(), Path(args.root), _read_message(args))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["block_final"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
