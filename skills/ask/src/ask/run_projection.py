"""One normalized operator read model for every Ask run (#1401).

Purpose
    Ask status is artifact-shape dependent: a roundtable, a compete run, a
    browser lane and a scillm-only DAG each answer "what happened?" from a
    different set of files, so every consumer -- humans, ``--json``, cron, the
    Tau timeline -- reimplements the same inspection and drifts.

    ``ask.run_projection.v1`` derives one shape from the authoritative
    artifacts. It is read-only and deterministic: the same artifact set always
    yields the same projection, so it is safe to call on a live run, in a
    watch loop, or from another host.

    The contract's load-bearing rule is that **absence is reported, never
    silently dropped**. Every node in the frozen DAG appears even when it
    never created a worker directory or a receipt, because the failure this
    projection exists to surface is precisely the node that produced nothing
    (see #1397 and #1399: a lane that stalls with no artifacts, and a join
    that dies after the handler already answered). A node omitted for lack of
    evidence is indistinguishable from a node that never existed.

    Completion authority is equally strict. A provider response, pane text,
    browser text, or a zero exit code is never on its own evidence that a node
    settled; the projection reports what the artifacts assert and marks
    everything else as unproven.

Inputs
    A run directory containing any subset of ``request.json``, ``dag.json``,
    ``compile-status.json``, ``execution-status.json``,
    ``interview-required.json``, browser provider artifacts, and
    ``node-artifacts/<node>/node-receipt.json``.

Outputs
    ``project_run(run_dir)`` returns an ``ask.run_projection.v1`` dict.

Failure modes
    A missing or unreadable artifact becomes a recorded entry in
    ``limitations`` and degrades the affected field, never an exception. A run
    directory that does not exist yields a projection whose lifecycle is
    ``UNKNOWN`` with the reason stated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "ask.run_projection.v1"

# Named explicitly rather than imported: the projection must stay read-only and
# dependency-light so it can run against an archived run directory.
BROWSER_HANDLERS = ("webgpt", "webclaude", "webkimi", "webgemini", "webgrok", "webdeepseek")

# Run lifecycle, ordered from least to most settled. Kept explicit rather than
# derived so a new artifact status cannot silently invent a state.
RUN_LIFECYCLE = (
    "PLANNED",
    "RUNNING",
    "WAITING",
    "NEEDS_ATTENTION",
    "DEGRADED",
    "PASS",
    "FAILED",
    "CANCELLED",
    "UNKNOWN",
)

# Node progress is a ladder, not a boolean. The distinctions matter because
# each names a different real failure: dispatched-but-no-receipt is #1397,
# candidate-output-but-not-admitted is a provider answer nobody accepted.
NODE_STAGES = (
    "COMPILED",       # in the frozen DAG, nothing else observed
    "DISPATCHED",     # a worker directory exists
    "ACKNOWLEDGED",   # transport accepted the request
    "CANDIDATE",      # output exists but is not admitted evidence
    "ADMITTED",       # evidence accepted
    "SETTLED",        # node reached a terminal receipt
)

_TERMINAL_RUN_STATES = {"PASS", "FAILED", "CANCELLED"}


@dataclass
class _Limitation:
    """Something the projection could not determine, and why."""

    scope: str
    reason: str
    path: str = ""

    def as_dict(self) -> dict[str, str]:
        payload = {"scope": self.scope, "reason": self.reason}
        if self.path:
            payload["path"] = self.path
        return payload


@dataclass
class _Reader:
    """Reads run artifacts, recording every gap instead of raising."""

    run_dir: Path
    limitations: list[_Limitation] = field(default_factory=list)

    def json(self, name: str, *, scope: str) -> dict[str, Any] | None:
        path = self.run_dir / name
        if not path.is_file():
            self.limitations.append(_Limitation(scope, f"{name} is absent", str(path)))
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.limitations.append(
                _Limitation(scope, f"{name} is unreadable: {exc}", str(path))
            )
            return None
        if not isinstance(loaded, dict):
            self.limitations.append(
                _Limitation(scope, f"{name} is not a JSON object", str(path))
            )
            return None
        return loaded


def _node_ids_in_dag_order(dag: dict[str, Any] | None) -> list[str]:
    """Node ids in the DAG's own order, which is the operator's mental order."""
    if not isinstance(dag, dict):
        return []
    nodes = dag.get("nodes")
    if not isinstance(nodes, list):
        return []
    ordered: list[str] = []
    for node in nodes:
        if isinstance(node, dict):
            node_id = str(node.get("id") or node.get("node_id") or "").strip()
            if node_id and node_id not in ordered:
                ordered.append(node_id)
    return ordered


def _classify_target(node_id: str, node: dict[str, Any]) -> dict[str, str]:
    """Name what kind of thing this node talks to.

    Operators reason in targets (a browser seat, a model, a join), so the
    projection classifies rather than leaving callers to parse node ids.
    """
    handler = str(node.get("handler") or node.get("agent") or "").strip()
    lowered = (handler or node_id).lower()
    # Real DAG nodes carry `agent: "handler-webgpt"` with no separate handler
    # field, so the provider name is embedded rather than leading. Matching on
    # a prefix classified every browser seat as a plain model.
    if any(name in lowered for name in BROWSER_HANDLERS) or "browser" in lowered:
        kind = "browser_seat"
    elif node_id.startswith("join") or handler == "join":
        kind = "join"
    elif "human" in lowered:
        kind = "human"
    elif "review" in lowered:
        kind = "reviewer"
    elif "solver" in lowered or "handler" in node_id:
        kind = "model"
    else:
        kind = "local"
    return {"target_kind": kind, "target_selector": handler or node_id}


def _project_node(
    node_id: str,
    node: dict[str, Any],
    reader: _Reader,
) -> dict[str, Any]:
    """Project one node, including one that produced nothing at all."""
    artifact_dir = reader.run_dir / "node-artifacts" / node_id
    projected: dict[str, Any] = {
        "node_id": node_id,
        "stage": "COMPILED",
        "ok": None,
        "status": None,
        "failure_code": None,
        "artifact_dir": str(artifact_dir) if artifact_dir.is_dir() else None,
        "evidence_admitted": False,
        "provider_live": None,
        **_classify_target(node_id, node),
    }

    if not artifact_dir.is_dir():
        # Rule 1: a compiled node that never ran is still reported, with the
        # absence named. Dropping it would hide the #1397 failure entirely.
        projected["limitation"] = "node never created a worker directory"
        return projected

    projected["stage"] = "DISPATCHED"
    receipt_path = artifact_dir / "node-receipt.json"
    if not receipt_path.is_file():
        # Dispatched with no terminal receipt: the caller is left waiting.
        projected["limitation"] = "dispatched with no node-receipt.json"
        candidates = [p.name for p in artifact_dir.glob("response*") if p.is_file()]
        if candidates:
            # Output exists but nothing admitted it. Explicitly NOT settled:
            # a provider response is not completion authority.
            projected["stage"] = "CANDIDATE"
            projected["candidate_outputs"] = sorted(candidates)
        return projected

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        reader.limitations.append(
            _Limitation(f"node:{node_id}", f"node-receipt.json unreadable: {exc}", str(receipt_path))
        )
        projected["limitation"] = "node-receipt.json unreadable"
        return projected

    if not isinstance(receipt, dict):
        projected["limitation"] = "node-receipt.json is not a JSON object"
        return projected

    projected["stage"] = "SETTLED"
    projected["ok"] = receipt.get("ok")
    projected["status"] = receipt.get("status")
    projected["failure_code"] = receipt.get("failure_code") or None
    projected["provider_live"] = receipt.get("provider_live")
    projected["evidence_admitted"] = receipt.get("ok") is True
    if receipt.get("ok") is not True and projected["failure_code"]:
        projected["stage"] = "ACKNOWLEDGED"
    return projected


def _run_lifecycle(
    compile_status: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    interview: dict[str, Any] | None,
) -> tuple[str, str]:
    """Derive the run lifecycle and say which artifact decided it."""
    if interview is not None:
        return "WAITING", "interview-required.json"
    if execution is None:
        if compile_status is None:
            return "UNKNOWN", "no compile-status.json"
        return "PLANNED", "compile-status.json (no execution-status.json)"

    status = str(execution.get("status") or "").upper()
    if status in RUN_LIFECYCLE:
        return status, "execution-status.json"
    if execution.get("ok") is True:
        return "PASS", "execution-status.json ok"
    if status:
        return "NEEDS_ATTENTION", f"execution-status.json status={status!r}"
    return "UNKNOWN", "execution-status.json has no usable status"


def project_run(run_dir: Path | str) -> dict[str, Any]:
    """Build ``ask.run_projection.v1`` for one run directory."""
    path = Path(run_dir)
    reader = _Reader(path)

    if not path.is_dir():
        return {
            "schema": SCHEMA,
            "run_dir": str(path),
            "lifecycle": "UNKNOWN",
            "lifecycle_source": "run directory does not exist",
            "nodes": [],
            "limitations": [_Limitation("run", "run directory does not exist", str(path)).as_dict()],
        }

    request = reader.json("request.json", scope="request")
    dag = reader.json("dag.json", scope="dag")
    compile_status = reader.json("compile-status.json", scope="compile")
    execution = reader.json("execution-status.json", scope="execution")
    interview = None
    if (path / "interview-required.json").is_file():
        interview = reader.json("interview-required.json", scope="interview")

    goal = (request or {}).get("goal") if isinstance(request, dict) else None
    if not isinstance(goal, dict):
        goal = (dag or {}).get("goal") if isinstance(dag, dict) else None
    goal = goal if isinstance(goal, dict) else {}

    node_index: dict[str, dict[str, Any]] = {}
    if isinstance(dag, dict) and isinstance(dag.get("nodes"), list):
        for node in dag["nodes"]:
            if isinstance(node, dict):
                node_id = str(node.get("id") or node.get("node_id") or "").strip()
                if node_id:
                    node_index[node_id] = node

    ordered = _node_ids_in_dag_order(dag)
    nodes = [_project_node(node_id, node_index.get(node_id, {}), reader) for node_id in ordered]

    lifecycle, lifecycle_source = _run_lifecycle(compile_status, execution, interview)

    settled = [n for n in nodes if n["stage"] == "SETTLED"]
    admitted = [n for n in nodes if n["evidence_admitted"]]
    unsettled = [n for n in nodes if n["stage"] != "SETTLED"]

    projection: dict[str, Any] = {
        "schema": SCHEMA,
        "run_dir": str(path),
        "run_id": path.name,
        "request": (request or {}).get("request") if isinstance(request, dict) else None,
        "repo": (request or {}).get("repo") if isinstance(request, dict) else None,
        "target": (request or {}).get("target") if isinstance(request, dict) else None,
        "immutable_goal": goal.get("immutable_goal")
        or ((request or {}).get("immutable_goal") if isinstance(request, dict) else None),
        "goal_hash": goal.get("goal_hash"),
        "mode": (request or {}).get("workflow_mode") or (request or {}).get("dag_template")
        if isinstance(request, dict)
        else None,
        "topology": (request or {}).get("topology") if isinstance(request, dict) else None,
        "lifecycle": lifecycle,
        "lifecycle_source": lifecycle_source,
        "terminal": lifecycle in _TERMINAL_RUN_STATES,
        "mocked": (execution or {}).get("mocked"),
        "live": (execution or {}).get("live"),
        "provider_live": (execution or {}).get("provider_live"),
        "failure_code": (execution or {}).get("failure_code"),
        "removed_seats": (execution or {}).get("removed_seats"),
        "node_count": len(nodes),
        "settled_node_count": len(settled),
        "admitted_node_count": len(admitted),
        "unsettled_nodes": [n["node_id"] for n in unsettled],
        "nodes": nodes,
        "next_action": None,
        "limitations": [limitation.as_dict() for limitation in reader.limitations],
    }

    projection["next_action"] = _next_action(projection, execution, interview)
    return projection


def _next_action(
    projection: dict[str, Any],
    execution: dict[str, Any] | None,
    interview: dict[str, Any] | None,
) -> str | None:
    """One safe next step, or None when nothing is actionable.

    Only actions the artifacts actually justify: inventing a recovery command
    for a state nobody observed is how an operator gets sent to the wrong
    layer.
    """
    if interview is not None:
        return "answer the interview packet: interview-required.json"
    if isinstance(execution, dict):
        command = execution.get("next_command")
        if isinstance(command, list) and command:
            return " ".join(str(part) for part in command)
        if isinstance(command, str) and command.strip():
            return command.strip()
    if projection["lifecycle"] == "PLANNED":
        return "compiled but never executed; re-run with --execute"
    unsettled = projection["unsettled_nodes"]
    if unsettled and projection["lifecycle"] not in {"RUNNING", "WAITING"}:
        return f"inspect nodes with no terminal receipt: {', '.join(unsettled[:5])}"
    return None
