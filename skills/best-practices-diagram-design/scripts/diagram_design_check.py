#!/usr/bin/env python3
"""Diagram design gate: validate a typed diagram SPEC before it is rendered.

Reads a JSON diagram spec (view/nodes/edges/gates/terminal_states), validates
it through a Pydantic model with `extra="forbid"` at the boundary, then runs
deterministic topology/legibility rules (see SKILL.md rule table). Emits a
machine-readable verdict: `errors[]` (blocking) and `warnings[]` (advisory,
e.g. connector routing) with `code`/`loc`/`msg` on each.

Failure modes: malformed JSON or a spec that fails the Pydantic boundary
model produces a `SPEC_INVALID` error and, when `triage-error` is installed
alongside this skill, is additionally classified through it for a
`{code, cause, next_command}` triple. Exit code is non-zero iff any
error-level violation (spec-invalid or rule) is present.
"""
from __future__ import annotations

import json
import subprocess
from collections import defaultdict
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

PROCESS_VIEWS: set[str] = {"decision_tree", "flowchart", "sequence", "lifecycle"}
FLOW_VIEWS: set[str] = {"decision_tree", "flowchart"}

DEFAULT_LABEL_LIMIT = 60
FANOUT_SOURCE_LABEL_LIMIT = 80
FANOUT_TARGET_LABEL_LIMIT = 40
FANOUT_MAX_TARGETS = 4
FANOUT_MIN_SOURCE_OUT_DEGREE = 3  # a source with >=3 unconditional edges reads as a star


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    target: str
    branch_label: str | None = None
    routing: RoutingKind = "orthogonal"


class DiagramSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    view: ViewKind
    nodes: list[Node] = Field(min_length=1)
    edges: list[Edge] = Field(default_factory=list)
    gates: list[str] = Field(default_factory=list)
    terminal_states: list[str] = Field(default_factory=list)
    label_limit: int = DEFAULT_LABEL_LIMIT


class Violation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    loc: str
    msg: str
    severity: Literal["error", "warning"]


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


def check_spec(spec: DiagramSpec) -> Verdict:
    errors: list[Violation] = []
    warnings: list[Violation] = []

    node_ids = {n.id for n in spec.nodes}
    out_edges: dict[str, list[Edge]] = defaultdict(list)
    in_degree: dict[str, int] = defaultdict(int)
    for edge in spec.edges:
        out_edges[edge.source].append(edge)
        in_degree[edge.target] += 1

    sources = [nid for nid in node_ids if in_degree.get(nid, 0) == 0]
    branching_nodes = [nid for nid, edges in out_edges.items() if len(edges) >= 2]

    # VIEW_TOPOLOGY_MISMATCH: single source fanning to many targets, no gates,
    # in a flow/decision view -- the star-for-sequence bug.
    if spec.view in FLOW_VIEWS and not spec.gates and len(sources) == 1:
        source = sources[0]
        if len(out_edges.get(source, [])) >= FANOUT_MIN_SOURCE_OUT_DEGREE:
            errors.append(Violation(
                code="VIEW_TOPOLOGY_MISMATCH",
                loc=f"nodes.{source}",
                msg=(
                    f"view={spec.view} but node '{source}' fans out to "
                    f"{len(out_edges[source])} targets with zero gates declared "
                    "-- this is a fan-out star, not a sequence/decision flow"
                ),
                severity="error",
            ))

    # MISSING_GATES: branching without any declared gate.
    if spec.view in FLOW_VIEWS and branching_nodes and not spec.gates:
        errors.append(Violation(
            code="MISSING_GATES",
            loc="gates",
            msg=(
                f"nodes {branching_nodes} branch (2+ outgoing edges) but "
                "gates=[] -- mark decision points explicitly"
            ),
            severity="error",
        ))

    # UNLABELED_BRANCH: a gate's outgoing edges must all carry branch_label.
    for gate in spec.gates:
        if gate not in node_ids:
            errors.append(Violation(
                code="UNLABELED_BRANCH",
                loc=f"gates.{gate}",
                msg=f"gate '{gate}' is not a declared node id",
                severity="error",
            ))
            continue
        for edge in out_edges.get(gate, []):
            if not edge.branch_label:
                errors.append(Violation(
                    code="UNLABELED_BRANCH",
                    loc=f"edges.{gate}->{edge.target}",
                    msg=f"gate '{gate}' has an outgoing edge to '{edge.target}' with no branch_label (e.g. yes/no)",
                    severity="error",
                ))

    # MISSING_TERMINAL_STATE: process views need at least one terminal state.
    if spec.view in PROCESS_VIEWS and not spec.terminal_states:
        errors.append(Violation(
            code="MISSING_TERMINAL_STATE",
            loc="terminal_states",
            msg=f"view={spec.view} declares no terminal_states -- readers can't tell where the flow ends",
            severity="error",
        ))
    for terminal in spec.terminal_states:
        if terminal not in node_ids:
            errors.append(Violation(
                code="MISSING_TERMINAL_STATE",
                loc=f"terminal_states.{terminal}",
                msg=f"terminal state '{terminal}' is not a declared node id",
                severity="error",
            ))

    # LABEL_TOO_LONG: fan-out uses tighter source/target limits per Excalidraw sizing.
    fanout_source_ids = set(sources) if spec.view == "fanout" else set()
    for node in spec.nodes:
        if spec.view == "fanout" and node.id in fanout_source_ids:
            limit = FANOUT_SOURCE_LABEL_LIMIT
        elif spec.view == "fanout":
            limit = FANOUT_TARGET_LABEL_LIMIT
        else:
            limit = spec.label_limit
        if len(node.label) > limit:
            errors.append(Violation(
                code="LABEL_TOO_LONG",
                loc=f"nodes.{node.id}.label",
                msg=f"label is {len(node.label)} chars, limit is {limit}",
                severity="error",
            ))

    # FANOUT_TOO_MANY: create-svg fan-out compiler ceiling is 4 targets.
    if spec.view == "fanout":
        for source in sources:
            targets = out_edges.get(source, [])
            if len(targets) > FANOUT_MAX_TARGETS:
                errors.append(Violation(
                    code="FANOUT_TOO_MANY",
                    loc=f"nodes.{source}",
                    msg=(
                        f"fan-out from '{source}' has {len(targets)} targets, "
                        f"create-svg fan-out compiler ceiling is {FANOUT_MAX_TARGETS}"
                    ),
                    severity="error",
                ))

    # CONNECTOR_ROUTING_STRAIGHT: advisory -- prefer orthogonal/curved for flows.
    if spec.view in FLOW_VIEWS:
        for edge in spec.edges:
            if edge.routing == "straight":
                warnings.append(Violation(
                    code="CONNECTOR_ROUTING_STRAIGHT",
                    loc=f"edges.{edge.source}->{edge.target}",
                    msg=(
                        "straight routing on a flow/decision edge risks crossing labels/boxes; "
                        "prefer routing=orthogonal or curved (advisory, confirm at screenshot read-back)"
                    ),
                    severity="warning",
                ))

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


if __name__ == "__main__":
    app()
