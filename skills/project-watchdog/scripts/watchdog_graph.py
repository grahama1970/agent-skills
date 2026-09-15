"""Validated, versioned graph source for the native Project Watchdog Pi workflow."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_GRAPH = ROOT / "workflows" / "watchdog-v2.json"
DRAFT_GRAPH = ROOT / "workflows" / "watchdog-v2.draft.json"
GRAPH_SCHEMA = "project_watchdog.dag.v1"
WORKFLOW_SCHEMA = "project_watchdog.v2.workflow"
NODE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
SHARED_CHECKOUT_SCOPE_GUIDANCE = (
    "This workflow runs in the operator's shared primary checkout. Unrelated dirty or "
    "untracked files may predate this ticket and are operator work: preserve them, do not "
    "revert them, and do not report them as scope drift. Judge scope from the files you "
    "personally changed for this ticket."
)


class GraphError(ValueError):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("; ".join(issues))


class RevisionConflict(GraphError):
    pass


def graph_path(source: str) -> Path:
    if source == "active":
        return ACTIVE_GRAPH
    if source == "draft":
        return DRAFT_GRAPH
    raise GraphError(["source must be active or draft"])


def validate_graph(graph: Any) -> list[dict[str, Any]]:
    issues: list[str] = []
    if not isinstance(graph, dict):
        raise GraphError(["graph must be an object"])
    if graph.get("schema") != GRAPH_SCHEMA:
        issues.append(f"schema must be {GRAPH_SCHEMA}")
    if set(graph) - {"schema", "nodes", "layout"}:
        issues.append("graph has unknown top-level fields")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not 2 <= len(nodes) <= 12:
        raise GraphError(issues + ["nodes must contain between 2 and 12 entries"])

    by_id: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            issues.append(f"nodes[{index}] must be an object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not NODE_ID.fullmatch(node_id):
            issues.append(f"nodes[{index}].id is invalid")
            continue
        if node_id in by_id:
            issues.append(f"duplicate node id: {node_id}")
            continue
        by_id[node_id] = node
        if set(node) - {"id", "agent", "access", "task", "depends_on"}:
            issues.append(f"{node_id} has unknown fields")
        if not isinstance(node.get("task"), str) or not 1 <= len(node["task"].strip()) <= 5000:
            issues.append(f"{node_id}.task must contain 1 to 5000 characters")
        deps = node.get("depends_on")
        if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
            issues.append(f"{node_id}.depends_on must be a list of node ids")
        elif len(deps) != len(set(deps)):
            issues.append(f"{node_id}.depends_on contains duplicates")
        if node_id == "fixer":
            if node.get("agent") != "worker" or node.get("access") != "write":
                issues.append("fixer must be the only writer and use the worker agent")
        elif node.get("agent") != "reviewer" or node.get("access") != "read":
            issues.append(f"{node_id} must be read-only and use the reviewer agent")

    if "fixer" not in by_id or "reviewer" not in by_id:
        issues.append("fixer and reviewer are required")
    layout = graph.get("layout")
    if not isinstance(layout, dict) or set(layout) != set(by_id):
        issues.append("layout must contain exactly one position for each node")
    else:
        for node_id, position in layout.items():
            if not isinstance(position, dict) or set(position) != {"x", "y"}:
                issues.append(f"{node_id} position must have x and y")
                continue
            if any(
                isinstance(position[axis], bool)
                or not isinstance(position[axis], (int, float))
                or not math.isfinite(position[axis])
                or abs(position[axis]) > 10000
                for axis in ("x", "y")
            ):
                issues.append(f"{node_id} position is invalid")

    for node_id, node in by_id.items():
        for dep in node.get("depends_on", []) if isinstance(node.get("depends_on"), list) else []:
            if dep not in by_id:
                issues.append(f"{node_id} depends on missing node {dep}")
            elif dep == node_id:
                issues.append(f"{node_id} cannot depend on itself")

    if issues:
        raise GraphError(issues)

    ordered: list[dict[str, Any]] = []
    pending = set(by_id)
    while pending:
        ready = sorted(node_id for node_id in pending if set(by_id[node_id]["depends_on"]) <= (set(by_id) - pending))
        if not ready:
            raise GraphError(["dependency cycle detected"])
        for node_id in ready:
            ordered.append(by_id[node_id])
            pending.remove(node_id)

    ancestors = {"reviewer"}
    frontier = ["reviewer"]
    while frontier:
        for dep in by_id[frontier.pop()]["depends_on"]:
            if dep not in ancestors:
                ancestors.add(dep)
                frontier.append(dep)
    if "fixer" not in ancestors:
        issues.append("reviewer must depend on fixer, directly or transitively")
    if ancestors != set(by_id):
        issues.append("every node must feed into reviewer")
    if issues:
        raise GraphError(issues)
    return ordered


def canonical_bytes(graph: dict[str, Any]) -> bytes:
    validate_graph(graph)
    return (json.dumps(graph, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")


def revision(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_graph(source: str = "draft") -> tuple[dict[str, Any], str]:
    raw = graph_path(source).read_bytes()
    graph = json.loads(raw)
    validate_graph(graph)
    return graph, revision(raw)


def save_graph(graph: dict[str, Any], expected_revision: str, source: str = "draft") -> str:
    if source != "draft":
        raise GraphError(["only the draft may be edited directly"])
    data = canonical_bytes(graph)
    path = graph_path(source)
    lock_root = Path(os.environ.get("PROJECT_WATCHDOG_STATE_ROOT", "~/.local/state/project-watchdog-v2")).expanduser()
    lock_root.mkdir(parents=True, exist_ok=True)
    with (lock_root / "workflow-graph.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = revision(path.read_bytes())
        if current != expected_revision:
            raise RevisionConflict(["draft changed since it was loaded"])
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    return revision(path.read_bytes())


def promote_graph(expected_draft_revision: str, expected_active_revision: str) -> str:
    lock_root = Path(os.environ.get("PROJECT_WATCHDOG_STATE_ROOT", "~/.local/state/project-watchdog-v2")).expanduser()
    lock_root.mkdir(parents=True, exist_ok=True)
    with (lock_root / "workflow-graph.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        draft_raw = DRAFT_GRAPH.read_bytes()
        active_raw = ACTIVE_GRAPH.read_bytes()
        if revision(draft_raw) != expected_draft_revision or revision(active_raw) != expected_active_revision:
            raise RevisionConflict(["draft or active graph changed before promotion"])
        draft = json.loads(draft_raw)
        data = canonical_bytes(draft)
        tmp = ACTIVE_GRAPH.with_suffix(ACTIVE_GRAPH.suffix + f".{os.getpid()}.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, ACTIVE_GRAPH)
        finally:
            tmp.unlink(missing_ok=True)
    return revision(ACTIVE_GRAPH.read_bytes())


def compile_script(graph: dict[str, Any], ticket: dict[str, Any], model: str) -> str:
    ordered = validate_graph(graph)
    required = {"key", "title", "body", "proof_command"}
    if set(ticket) != required or any(not isinstance(ticket[key], str) for key in required):
        raise GraphError(["ticket context must contain string key, title, body, and proof_command"])
    lines = ["const results = {};"]
    for node in ordered:
        node_id = node["id"]
        task = (
            node["task"].strip()
            + f"\n\n{SHARED_CHECKOUT_SCOPE_GUIDANCE}"
            + f"\n\nTicket {ticket['key']}: {ticket['title']}"
            + f"\nTicket body:\n{ticket['body']}"
            + f"\nTrusted proof command (controller-owned): {ticket['proof_command']}"
        )
        expression = json.dumps(task)
        for dep in node["depends_on"]:
            expression += " + " + json.dumps(f"\n\n{dep} result:\n") + f" + String(results[{json.dumps(dep)}].output ?? '')"
        lines.append(
            f"results[{json.dumps(node_id)}] = await runs.run({json.dumps(node_id)}, "
            + "{ agent: " + json.dumps(node["agent"])
            + ", model: " + json.dumps(model)
            + ", task: " + expression + " });"
        )
        lines.append(
            f"if (!results[{json.dumps(node_id)}].ok) return "
            + "{ schema: " + json.dumps(WORKFLOW_SCHEMA)
            + ", results, failed_role: " + json.dumps(node_id) + " };"
        )
    lines.append(
        "return { schema: " + json.dumps(WORKFLOW_SCHEMA)
        + ", results, fixer: results.fixer, reviewer: results.reviewer };"
    )
    return "\n".join(lines)
