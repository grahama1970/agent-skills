#!/usr/bin/env python3
"""Diagram design gate: validate a typed diagram SPEC before it is rendered.

Reads a JSON diagram spec (view/nodes/edges/gates/terminal_states, plus an
optional `requirements` fragment), validates it through a Pydantic model with
`extra="forbid"` at the boundary, then runs deterministic rules in two
tiers:

1. Declaration rules (topology/legibility): is a gate declared, is a label
   short enough, is there a terminal state. These catch missing metadata.
2. Semantic-contract rules (control-flow only, ignore annotation/dependency
   edges): does the diagram actually preserve the process the `requirements`
   fragment demands -- can a required precondition be bypassed, is a
   required node unreachable, does a decision's rendered branch label match
   its declared outcome. These catch a diagram that *declares* the right
   things but draws the wrong process (e.g. a gated escalation ladder
   relabeled as a "fanout" while still carrying the escalation requirements).

`VIEW_TOPOLOGY_MISMATCH` (a crude "single source fans out to 3+ targets"
heuristic) has been removed. It rejected shape (a star), not meaning; a star
can correctly represent independent parallel options. It is subsumed by
`PRECONDITION_BYPASS` (the target is actually reachable without the required
gate) and `INTENT_VIEW_MISMATCH` (the chosen view cannot represent a required
ordering/gate at all).

Failure modes: malformed JSON or a spec that fails the Pydantic boundary
model produces a `SPEC_INVALID` error and, when `triage-error` is installed
alongside this skill, is additionally classified through it for a
`{code, cause, next_command}` triple. Exit code is non-zero iff any
error-level violation (spec-invalid or rule) is present.
"""
from __future__ import annotations

import json
import subprocess
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

import typer
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

app = typer.Typer(add_completion=False, help="Validate a diagram design spec before rendering.")


@app.callback()
def _main() -> None:
    """best-practices-diagram-design: diagram design gate CLI."""


ViewKind = Literal["decision_tree", "flowchart", "sequence", "structure", "fanout", "lifecycle"]
RoutingKind = Literal["orthogonal", "curved", "straight"]
NodeKind = Literal["action", "decision", "terminal", "handoff", "fork", "join"]
EdgeKind = Literal["control", "annotation", "dependency"]

PROCESS_VIEWS: set[str] = {"decision_tree", "flowchart", "sequence", "lifecycle"}
FLOW_VIEWS: set[str] = {"decision_tree", "flowchart"}

DEFAULT_LABEL_LIMIT = 60
FANOUT_SOURCE_LABEL_LIMIT = 80
FANOUT_TARGET_LABEL_LIMIT = 40
FANOUT_MAX_TARGETS = 4


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    # Node semantics live here, not in a separate conflicting declaration.
    # gates[]/terminal_states[] are still accepted for backward compat and
    # unioned with kind-derived sets.
    kind: NodeKind = "action"
    outcome_domain: list[str] | None = None  # finite outcome set for a decision, e.g. ["yes", "no"]


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    target: str
    branch_label: str | None = None  # what the rendered diagram shows the reader
    outcome: str | None = None  # canonical outcome value; defaults to branch_label if unset
    routing: RoutingKind = "orthogonal"
    kind: EdgeKind = "control"  # semantic rules only ever look at kind == "control"

    @property
    def effective_outcome(self) -> str | None:
        return self.outcome if self.outcome is not None else self.branch_label


class Precondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str
    gate: str
    outcome: str


class OutcomeTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gate: str
    outcome: str
    target: str


class Requirements(BaseModel):
    """The process the diagram is contractually required to preserve.

    Bound to the source spec. Layout/rendering steps MUST NOT modify this
    fragment -- it is the ground truth the semantic rules check the
    control-flow graph against, independent of how the diagram is drawn.
    """

    model_config = ConfigDict(extra="forbid")
    intent: str = Field(min_length=1)
    required_order: list[str] = Field(default_factory=list)
    required_preconditions: list[Precondition] = Field(default_factory=list)
    required_outcome_targets: list[OutcomeTarget] = Field(default_factory=list)


class DiagramSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    view: ViewKind
    nodes: list[Node] = Field(min_length=1)
    edges: list[Edge] = Field(default_factory=list)
    gates: list[str] = Field(default_factory=list)
    terminal_states: list[str] = Field(default_factory=list)
    label_limit: int = DEFAULT_LABEL_LIMIT
    requirements: Requirements | None = None


class Violation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    loc: str
    msg: str
    severity: Literal["error", "warning"]
    path: list[str] | None = None  # concrete node-id path, for bypass/reachability findings


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    errors: list[Violation]
    warnings: list[Violation]


def _triage_classify(raw_error: str) -> dict | None:
    """Best-effort classification of an unstructured failure via /triage-error.

    Advisory only: this script's own rule codes are already unambiguous and
    do not need triage. This is only invoked for spec-parse failures, which
    are exactly the "ambiguous raw signal" case /triage-error exists for.
    """
    triage_run = Path(__file__).resolve().parents[2] / "triage-error" / "run.sh"
    if not triage_run.exists():
        return None
    try:
        result = subprocess.run(
            [str(triage_run), "classify", "--text", raw_error, "--layer", "diagram-design", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("triage-error classify failed: {}", exc)
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error("triage-error returned non-JSON output: {}", exc)
        return None


def load_spec(path: Path) -> tuple[DiagramSpec | None, Violation | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        triage = _triage_classify(str(exc))
        msg = f"could not parse spec JSON: {exc}"
        if triage:
            msg += f" (triage: {triage.get('code', 'unclassified')})"
        return None, Violation(code="SPEC_INVALID", loc="$", msg=msg, severity="error")
    try:
        return DiagramSpec.model_validate(raw), None
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"]) or "$"
        return None, Violation(code="SPEC_INVALID", loc=loc, msg=first["msg"], severity="error")


class ControlGraph:
    """Control-flow-only view of the spec: annotation/dependency edges ignored."""

    def __init__(self, spec: DiagramSpec) -> None:
        self.spec = spec
        self.node_ids = {n.id for n in spec.nodes}
        self.out: dict[str, list[Edge]] = defaultdict(list)
        self.in_degree: dict[str, int] = defaultdict(int)
        for edge in spec.edges:
            if edge.kind != "control":
                continue
            self.out[edge.source].append(edge)
            self.in_degree[edge.target] += 1
        self.entries = sorted(nid for nid in self.node_ids if self.in_degree.get(nid, 0) == 0)
        self.gates = {g for g in spec.gates} | {n.id for n in spec.nodes if n.kind == "decision"}
        self.terminals = {t for t in spec.terminal_states} | {n.id for n in spec.nodes if n.kind == "terminal"}

    def bfs_path(self, starts: list[str], target: str, excluded_edges: set[tuple[str, str, str | None]]) -> list[str] | None:
        """Shortest control-flow path from any of `starts` to `target`, skipping excluded (source,target,outcome) edges."""
        if target in starts:
            return [target]
        visited = set(starts)
        queue: deque[str] = deque(starts)
        pred: dict[str, str] = {}
        while queue:
            node = queue.popleft()
            for edge in self.out.get(node, []):
                key = (edge.source, edge.target, edge.effective_outcome)
                if key in excluded_edges:
                    continue
                if edge.target in visited:
                    continue
                visited.add(edge.target)
                pred[edge.target] = node
                if edge.target == target:
                    path = [target]
                    cur = target
                    while cur in pred:
                        cur = pred[cur]
                        path.append(cur)
                    path.reverse()
                    return path
                queue.append(edge.target)
        return None

    def reachable(self, starts: list[str]) -> set[str]:
        visited = set(starts)
        queue: deque[str] = deque(starts)
        while queue:
            node = queue.popleft()
            for edge in self.out.get(node, []):
                if edge.target not in visited:
                    visited.add(edge.target)
                    queue.append(edge.target)
        return visited


def _check_declarations(spec: DiagramSpec, graph: ControlGraph, errors: list[Violation], warnings: list[Violation]) -> None:
    """Tier 1: metadata-presence rules (does the spec declare gates/labels/terminals)."""
    branching_nodes = [nid for nid, edges in graph.out.items() if len(edges) >= 2]

    if spec.view in FLOW_VIEWS and branching_nodes and not graph.gates:
        errors.append(Violation(
            code="MISSING_GATES",
            loc="gates",
            msg=(
                f"nodes {branching_nodes} branch (2+ outgoing control edges) but "
                "no gates declared (spec.gates or node.kind=='decision') -- mark decision points explicitly"
            ),
            severity="error",
        ))

    for gate in graph.gates:
        if gate not in graph.node_ids:
            errors.append(Violation(code="UNLABELED_BRANCH", loc=f"gates.{gate}", msg=f"gate '{gate}' is not a declared node id", severity="error"))
            continue
        for edge in graph.out.get(gate, []):
            if not edge.branch_label:
                errors.append(Violation(
                    code="UNLABELED_BRANCH",
                    loc=f"edges.{gate}->{edge.target}",
                    msg=f"gate '{gate}' has an outgoing edge to '{edge.target}' with no branch_label (e.g. yes/no)",
                    severity="error",
                ))

    if spec.view in PROCESS_VIEWS and not graph.terminals:
        errors.append(Violation(code="MISSING_TERMINAL_STATE", loc="terminal_states", msg=f"view={spec.view} declares no terminal_states -- readers can't tell where the flow ends", severity="error"))
    for terminal in graph.terminals:
        if terminal not in graph.node_ids:
            errors.append(Violation(code="MISSING_TERMINAL_STATE", loc=f"terminal_states.{terminal}", msg=f"terminal state '{terminal}' is not a declared node id", severity="error"))

    fanout_source_ids = set(graph.entries) if spec.view == "fanout" else set()
    for node in spec.nodes:
        if spec.view == "fanout" and node.id in fanout_source_ids:
            limit = FANOUT_SOURCE_LABEL_LIMIT
        elif spec.view == "fanout":
            limit = FANOUT_TARGET_LABEL_LIMIT
        else:
            limit = spec.label_limit
        if len(node.label) > limit:
            errors.append(Violation(code="LABEL_TOO_LONG", loc=f"nodes.{node.id}.label", msg=f"label is {len(node.label)} chars, limit is {limit}", severity="error"))

    if spec.view == "fanout":
        for source in graph.entries:
            targets = graph.out.get(source, [])
            if len(targets) > FANOUT_MAX_TARGETS:
                errors.append(Violation(code="FANOUT_TOO_MANY", loc=f"nodes.{source}", msg=f"fan-out from '{source}' has {len(targets)} targets, create-svg fan-out compiler ceiling is {FANOUT_MAX_TARGETS}", severity="error"))

    if spec.view in FLOW_VIEWS:
        for edge in spec.edges:
            if edge.kind == "control" and edge.routing == "straight":
                warnings.append(Violation(
                    code="CONNECTOR_ROUTING_STRAIGHT",
                    loc=f"edges.{edge.source}->{edge.target}",
                    msg="straight routing on a flow/decision edge risks crossing labels/boxes; prefer routing=orthogonal or curved (advisory, confirm at screenshot read-back). Note: a clean straight edge that does not measurably cross a label passes geometry -- see `geometry` subcommand.",
                    severity="warning",
                ))


def _check_semantics(spec: DiagramSpec, graph: ControlGraph, errors: list[Violation], warnings: list[Violation]) -> None:
    """Tier 2: does the control-flow graph actually preserve the required process."""
    req = spec.requirements

    # TERMINAL_HAS_CONTINUATION: a terminal must not have outgoing control-flow edges.
    for terminal in graph.terminals:
        if graph.out.get(terminal):
            targets = [e.target for e in graph.out[terminal]]
            errors.append(Violation(code="TERMINAL_HAS_CONTINUATION", loc=f"nodes.{terminal}", msg=f"terminal '{terminal}' has outgoing control-flow edges to {targets} -- a terminal must end the process", severity="error"))

    # DECISION_OUTCOMES_INVALID / CONDITION_COVERAGE_UNVERIFIED
    node_by_id = {n.id: n for n in spec.nodes}
    for gate in graph.gates:
        edges = graph.out.get(gate, [])
        if not edges:
            continue
        outcomes = [e.effective_outcome for e in edges]
        if any(o is None for o in outcomes):
            continue  # already flagged by UNLABELED_BRANCH
        dupes = {o for o in outcomes if outcomes.count(o) > 1}
        if dupes:
            errors.append(Violation(code="DECISION_OUTCOMES_INVALID", loc=f"nodes.{gate}", msg=f"decision '{gate}' has duplicate outgoing outcomes {sorted(dupes)} -- outcomes must partition the decision, not overlap", severity="error"))
            continue
        domain = node_by_id[gate].outcome_domain if gate in node_by_id else None
        if domain is not None:
            if set(outcomes) != set(domain):
                errors.append(Violation(code="DECISION_OUTCOMES_INVALID", loc=f"nodes.{gate}", msg=f"decision '{gate}' declares outcome_domain={domain} but outgoing edges cover {sorted(outcomes)} -- omitted or contradicted outcomes", severity="error"))
        else:
            warnings.append(Violation(code="CONDITION_COVERAGE_UNVERIFIED", loc=f"nodes.{gate}", msg=f"decision '{gate}' has free-text outcomes {sorted(outcomes)} and no declared outcome_domain -- coverage can't be proven, advisory only", severity="warning"))

    # BRANCH_LABEL_MISMATCH: rendered branch_label must match the canonical outcome.
    for edge in spec.edges:
        if edge.kind == "control" and edge.branch_label is not None and edge.outcome is not None and edge.branch_label != edge.outcome:
            errors.append(Violation(code="BRANCH_LABEL_MISMATCH", loc=f"edges.{edge.source}->{edge.target}", msg=f"edge shows branch_label='{edge.branch_label}' but its declared outcome is '{edge.outcome}' -- rendered text does not match outcome data", severity="error"))

    # TREE_TOPOLOGY_INVALID: strict decision_tree -- single root, no cycle, no multi-parent non-root.
    if spec.view == "decision_tree":
        roots = graph.entries
        if len(roots) > 1:
            errors.append(Violation(code="TREE_TOPOLOGY_INVALID", loc="nodes", msg=f"decision_tree has {len(roots)} roots {roots}, a tree has exactly one", severity="error"))
        multi_parent = [nid for nid in graph.node_ids if graph.in_degree.get(nid, 0) > 1]
        if multi_parent:
            errors.append(Violation(code="TREE_TOPOLOGY_INVALID", loc="edges", msg=f"nodes {multi_parent} have multiple incoming control edges -- not a tree (a diamond-merge belongs in flowchart, not decision_tree)", severity="error"))
        cycle = _find_cycle(graph)
        if cycle:
            errors.append(Violation(code="TREE_TOPOLOGY_INVALID", loc="edges", msg=f"decision_tree has a cycle: {' -> '.join(cycle)}", severity="error", path=cycle))

    if req is None:
        return

    # INTENT_VIEW_MISMATCH: fanout cannot represent an ordering/gating requirement.
    if spec.view == "fanout" and (req.required_order or req.required_preconditions):
        errors.append(Violation(code="INTENT_VIEW_MISMATCH", loc="view", msg=f"view=fanout cannot represent the required ordering/preconditions in requirements (intent: '{req.intent}') -- targets in a fan-out read as independent, choose decision_tree/flowchart", severity="error"))

    # UNREACHABLE_PROCESS_NODE
    required_nodes: set[str] = set(req.required_order)
    for pre in req.required_preconditions:
        required_nodes.add(pre.target)
        required_nodes.add(pre.gate)
    for tgt in req.required_outcome_targets:
        required_nodes.add(tgt.gate)
        required_nodes.add(tgt.target)
    required_nodes |= graph.terminals
    reachable = graph.reachable(graph.entries)
    for nid in sorted(required_nodes):
        if nid in graph.node_ids and nid not in reachable:
            errors.append(Violation(code="UNREACHABLE_PROCESS_NODE", loc=f"nodes.{nid}", msg=f"required node '{nid}' is not reachable from any entry node {graph.entries}", severity="error"))

    # REQUIRED_RELATION_MISSING
    for tgt in req.required_outcome_targets:
        matches = [e for e in graph.out.get(tgt.gate, []) if e.target == tgt.target and e.effective_outcome == tgt.outcome]
        if not matches:
            errors.append(Violation(code="REQUIRED_RELATION_MISSING", loc=f"requirements.required_outcome_targets", msg=f"no control edge '{tgt.gate}' --{tgt.outcome}--> '{tgt.target}' -- required transition is not represented", severity="error"))

    # REQUIRED_ORDER_VIOLATED: each consecutive pair must be reachable in the stated order.
    for a, b in zip(req.required_order, req.required_order[1:]):
        if a not in graph.node_ids or b not in graph.node_ids:
            continue
        forward = graph.reachable([a])
        if b not in forward:
            errors.append(Violation(code="REQUIRED_ORDER_VIOLATED", loc="requirements.required_order", msg=f"required order says '{a}' precedes '{b}', but '{b}' is not reachable from '{a}' on any control-flow path", severity="error"))
            continue
        backward = graph.reachable([b])
        if a in backward:
            errors.append(Violation(code="REQUIRED_ORDER_VIOLATED", loc="requirements.required_order", msg=f"required order says '{a}' precedes '{b}', but '{a}' is also reachable from '{b}' -- the order is not enforced (cycle)", severity="error"))

    # PRECONDITION_BYPASS: the real replacement for the star heuristic. Remove the
    # specific gate--outcome edge(s); if the target is still reachable, a bypass exists.
    for pre in req.required_preconditions:
        if pre.gate not in graph.node_ids or pre.target not in graph.node_ids:
            continue
        excluded = {(e.source, e.target, e.effective_outcome) for e in graph.out.get(pre.gate, []) if e.effective_outcome == pre.outcome}
        if not excluded:
            continue  # REQUIRED_RELATION_MISSING (if applicable) already covers "gate doesn't even have this outcome"
        bypass_path = graph.bfs_path(graph.entries, pre.target, excluded)
        if bypass_path is not None:
            errors.append(Violation(
                code="PRECONDITION_BYPASS",
                loc=f"requirements.required_preconditions",
                msg=(
                    f"'{pre.target}' is reachable without passing through '{pre.gate}' --{pre.outcome}--> "
                    f"(precondition bypassed). Bypass path: {' -> '.join(bypass_path)}"
                ),
                severity="error",
                path=bypass_path,
            ))


def _find_cycle(graph: ControlGraph) -> list[str] | None:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in graph.node_ids}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for edge in graph.out.get(node, []):
            nxt = edge.target
            if color.get(nxt, WHITE) == GRAY:
                idx = stack.index(nxt)
                return stack[idx:] + [nxt]
            if color.get(nxt, WHITE) == WHITE:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for nid in sorted(graph.node_ids):
        if color[nid] == WHITE:
            found = visit(nid)
            if found:
                return found
    return None


def check_spec(spec: DiagramSpec) -> Verdict:
    errors: list[Violation] = []
    warnings: list[Violation] = []
    graph = ControlGraph(spec)
    _check_declarations(spec, graph, errors, warnings)
    _check_semantics(spec, graph, errors, warnings)
    return Verdict(ok=not errors, errors=errors, warnings=warnings)


@app.command()
def check(
    spec_path: Path = typer.Argument(..., exists=True, readable=True, help="Path to diagram spec JSON"),
    json_output: bool = typer.Option(False, "--json", help="Print the verdict as JSON"),
) -> None:
    """Validate a diagram design spec and print the verdict."""
    spec, load_error = load_spec(spec_path)
    if load_error is not None:
        verdict = Verdict(ok=False, errors=[load_error], warnings=[])
    else:
        assert spec is not None
        verdict = check_spec(spec)

    if json_output:
        typer.echo(verdict.model_dump_json(indent=2))
    else:
        if verdict.ok:
            logger.info("PASS ({} warnings)", len(verdict.warnings))
        else:
            logger.error("FAIL: {} errors", len(verdict.errors))
        for violation in verdict.errors + verdict.warnings:
            typer.echo(f"[{violation.severity.upper()}] {violation.code} @ {violation.loc}: {violation.msg}")

    raise typer.Exit(code=0 if verdict.ok else 1)


@app.command()
def geometry(
    svg_path: Path = typer.Argument(..., exists=True, readable=True, help="Path to a rendered SVG (graphviz -Tsvg or mermaid svg)"),
    json_output: bool = typer.Option(False, "--json", help="Print the verdict as JSON"),
) -> None:
    """Validate the MEASURED geometry of a rendered SVG (delegates to diagram_geometry_check)."""
    from diagram_geometry_check import check_svg

    verdict = check_svg(svg_path)
    if json_output:
        typer.echo(verdict.model_dump_json(indent=2))
    else:
        if verdict.ok:
            logger.info("PASS ({} warnings)", len(verdict.warnings))
        else:
            logger.error("FAIL: {} errors", len(verdict.errors))
        for violation in verdict.errors + verdict.warnings:
            typer.echo(f"[{violation.severity.upper()}] {violation.code} @ {violation.loc}: {violation.msg}")
    raise typer.Exit(code=0 if verdict.ok else 1)


if __name__ == "__main__":
    app()
