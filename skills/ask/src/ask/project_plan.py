"""ask.project_plan.v1 — editable plan contract for role-based project-team UX.

Defined by agent-skills#1220. The plan is editable proposal data produced by
/ask from a natural-language request; it is NOT an accepted Tau DAG and NOT
completion proof. Compilation into tau.dag_contract.v1 agent nodes happens
downstream (blocked on tau#308/310 and scillm#27/28 shipping their contracts).

``validate_project_plan`` is a deterministic validator: no I/O, no model
calls. It returns (ok, errors) so callers can render every violation at once.
"""

from __future__ import annotations

from typing import Any

SCHEMA_ID = "ask.project_plan.v1"

SEMANTIC_ROLES = frozenset({
    "coordinator",
    "backend",
    "frontend",
    "documentation",
    "testing",
    "independent_reviewer",
})

HARNESS_MODES = frozenset({"tau_native_agent_loop", "opaque_agent_compat"})
DEFAULT_HARNESS_MODE = "tau_native_agent_loop"

_TOPOLOGIES = frozenset({"sequential", "concurrent", "hybrid"})


def _err(errors: list[str], msg: str) -> None:
    errors.append(msg)


def validate_project_plan(plan: Any) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return False, ["plan must be a mapping"]

    if plan.get("schema") != SCHEMA_ID:
        _err(errors, f"schema must be {SCHEMA_ID!r}, got {plan.get('schema')!r}")

    goal = plan.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        _err(errors, "goal must be a non-empty string (immutable)")

    target = plan.get("target")
    if not isinstance(target, dict) or not str(target.get("repo", "")).strip():
        _err(errors, "target.repo must name the target repository/project")

    deliverables = plan.get("deliverables")
    if not isinstance(deliverables, list) or not deliverables:
        _err(errors, "deliverables must be a non-empty list")
    else:
        for i, d in enumerate(deliverables):
            if not isinstance(d, dict) or not str(d.get("name", "")).strip():
                _err(errors, f"deliverables[{i}].name is required")
                continue
            criteria = d.get("acceptance_criteria")
            if not isinstance(criteria, list) or not criteria or not all(isinstance(c, str) and c.strip() for c in criteria):
                _err(errors, f"deliverables[{i}].acceptance_criteria must be a non-empty list of strings")

    workstreams = plan.get("workstreams")
    ws_ids: set[str] = set()
    if not isinstance(workstreams, list) or not workstreams:
        _err(errors, "workstreams must be a non-empty list")
    else:
        for i, ws in enumerate(workstreams):
            if not isinstance(ws, dict):
                _err(errors, f"workstreams[{i}] must be a mapping")
                continue
            ws_id = str(ws.get("id", "")).strip()
            if not ws_id:
                _err(errors, f"workstreams[{i}].id is required")
            elif ws_id in ws_ids:
                _err(errors, f"workstreams[{i}].id {ws_id!r} is duplicated")
            else:
                ws_ids.add(ws_id)
            role = ws.get("role")
            if role not in SEMANTIC_ROLES:
                _err(errors, f"workstreams[{i}].role {role!r} not in {sorted(SEMANTIC_ROLES)}")
            mode = ws.get("harness_mode", DEFAULT_HARNESS_MODE)
            if mode not in HARNESS_MODES:
                _err(errors, f"workstreams[{i}].harness_mode {mode!r} not in {sorted(HARNESS_MODES)}")
            elif mode == "opaque_agent_compat" and not str(ws.get("compat_justification", "")).strip():
                _err(errors, f"workstreams[{i}]: opaque_agent_compat requires compat_justification")
        for i, ws in enumerate(workstreams):
            if not isinstance(ws, dict):
                continue
            for dep in ws.get("depends_on", []) or []:
                if dep not in ws_ids:
                    _err(errors, f"workstreams[{i}].depends_on references unknown workstream {dep!r}")
                elif dep == ws.get("id"):
                    _err(errors, f"workstreams[{i}] depends on itself")

        # Reject dependency cycles (#1260): a cycle compiles to an
        # unschedulable Tau DAG that deadlocks/fails deep instead of failing
        # closed here. Only edges between known workstreams are considered.
        graph = {
            str(ws["id"]): [str(d) for d in (ws.get("depends_on") or []) if d in ws_ids]
            for ws in workstreams
            if isinstance(ws, dict) and str(ws.get("id", "")).strip()
        }
        WHITE, GREY, BLACK = 0, 1, 2
        color = {node: WHITE for node in graph}

        def _find_cycle(node: str, stack: list[str]) -> list[str] | None:
            color[node] = GREY
            stack.append(node)
            for nxt in graph.get(node, []):
                if color.get(nxt) == GREY:
                    return stack[stack.index(nxt):] + [nxt]
                if color.get(nxt) == WHITE:
                    found = _find_cycle(nxt, stack)
                    if found:
                        return found
            color[node] = BLACK
            stack.pop()
            return None

        for node in graph:
            if color[node] == WHITE:
                cycle = _find_cycle(node, [])
                if cycle:
                    _err(errors, f"workstreams form a dependency cycle: {' -> '.join(cycle)}")
                    break

    team = plan.get("team")
    if team is not None:
        if not isinstance(team, dict):
            _err(errors, "team must be a mapping when present")
        elif not str(team.get("preset", "")).strip() and not team.get("profile_ids"):
            _err(errors, "team must set preset or profile_ids (SciLLM transport profile ids)")

    execution = plan.get("execution", {})
    if not isinstance(execution, dict):
        _err(errors, "execution must be a mapping")
    else:
        topology = execution.get("topology", "concurrent")
        if topology not in _TOPOLOGIES:
            _err(errors, f"execution.topology {topology!r} not in {sorted(_TOPOLOGIES)}")
        concurrency = execution.get("max_concurrency", 1)
        if not isinstance(concurrency, int) or concurrency < 1:
            _err(errors, "execution.max_concurrency must be an integer >= 1")
        retries = execution.get("max_retries", 0)
        if not isinstance(retries, int) or retries < 0:
            _err(errors, "execution.max_retries must be an integer >= 0")

    unresolved = plan.get("unresolved", [])
    if not isinstance(unresolved, list) or not all(isinstance(u, str) for u in unresolved):
        _err(errors, "unresolved must be a list of strings (fields requiring /interview)")

    return (not errors), errors
