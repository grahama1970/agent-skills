"""Role-based project-team planning CLI for /ask (agent-skills#1220).

`ask team-plan "build a settings dashboard with a Python API, React UI, docs,
and tests" --team fullstack-premium` renders an editable ``ask.project_plan.v1``
and compiles it into a frozen ``tau.generic_dag_spec.v1`` preview. The user
thinks in deliverables and teams; roles map to SciLLM transport profiles via
team presets, and Tau owns execution. Planning is deterministic — no model
call — and a request whose workstreams cannot be inferred fails closed to
NEEDS_INTERVIEW with the missing fields named.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

import typer

from ask.project_plan import SCHEMA_ID, validate_project_plan
from ask.project_plan_to_tau import (
    TEAM_PRESETS,
    compile_plan_to_tau_spec,
    heterogeneous_profile_count,
    resolve_role_profiles,
    select_role_profiles_by_strength,
)

app = typer.Typer(help="Render role-based team plans and compile them into Tau DAG specs.")

# Deterministic keyword → role inference. Deliberately simple: anything the
# rules cannot infer becomes an /interview question instead of a model guess.
ROLE_PATTERNS: list[tuple[str, str, str]] = [
    (
        r"\bapi\b|\bbackend\b|\bpython\b|\bserver\b|\bendpoint|\bdatabase\b|\bschema\b"
        r"|\bmigrations?\b|\bpipeline\b|\bcli\b|\bdaemon\b|\bservice\b|\bworker\b"
        r"|\brust\b|\bgolang\b|\bgo\b|\bsql\b|\bgraphql\b|\bwebhooks?\b|\bauth(entication)?\b",
        "backend",
        "api",
    ),
    (
        r"\bui\b|\breact\b|\bfrontend\b|\bdashboard\b|\bscreen|\bcomponents?\b|\bcss\b"
        r"|\bdesign\b|\blayout\b|\bpage\b|\bmodal\b|\bform\b|\bchart\b|\bvisuali[sz]"
        r"|\bnext\.?js\b|\bvue\b|\bsvelte\b|\btypescript\b|\bwebsite\b|\bmobile\b|\bresponsive\b",
        "frontend",
        "ui",
    ),
    (
        r"\bdocs?\b|\bdocumentation\b|\breadme\b|\bguide\b|\btutorial\b|\bchangelog\b"
        r"|\bapi reference\b|\bwrite-?up\b|\bmanual\b|\bonboarding\b",
        "documentation",
        "docs",
    ),
    (
        r"\btests?\b|\btesting\b|\bcoverage\b|\bqa\b|\bregression\b|\be2e\b"
        r"|\bunit tests?\b|\bintegration tests?\b|\bbenchmarks?\b|\bvalidat",
        "testing",
        "tests",
    ),
]


def render_team_plan(request: str, *, repo: str, team: str) -> dict[str, Any]:
    """Deterministically render a request into ask.project_plan.v1."""
    low = request.lower()
    workstreams: list[dict[str, Any]] = [
        {"id": "coordinator", "role": "coordinator", "prompt": f"Plan and delegate: {request}"}
    ]
    worker_ids: list[str] = []
    for pattern, role, ws_id in ROLE_PATTERNS:
        if re.search(pattern, low):
            workstreams.append({"id": ws_id, "role": role, "depends_on": ["coordinator"]})
            worker_ids.append(ws_id)
    if worker_ids:
        workstreams.append(
            {"id": "review", "role": "independent_reviewer", "depends_on": list(worker_ids)}
        )
    return {
        "schema": SCHEMA_ID,
        "goal": request,
        "target": {"repo": repo},
        "deliverables": [
            {"name": ws["id"], "acceptance_criteria": [f"{ws['id']} workstream accepted by the independent reviewer"]}
            for ws in workstreams
            if ws["role"] not in ("coordinator", "independent_reviewer")
        ]
        or [{"name": "outcome", "acceptance_criteria": ["accepted by reviewer"]}],
        "workstreams": workstreams,
        "team": {"preset": team},
        "execution": {"topology": "hybrid", "max_concurrency": 3, "max_retries": 1},
        "unresolved": [] if worker_ids else ["workstreams"],
    }


def render_ascii_dag(spec: dict[str, Any], pricing: dict[str, Any] | None = None) -> str:
    """Deterministic ASCII chart of the compiled DAG for pre-run confirmation."""
    nodes = {n["node_id"]: n for n in spec["nodes"]}
    depths: dict[str, int] = {}

    def depth(nid: str) -> int:
        if nid not in depths:
            deps = nodes[nid]["depends_on"]
            depths[nid] = 0 if not deps else 1 + max(depth(d) for d in deps)
        return depths[nid]

    for nid in nodes:
        depth(nid)
    lines = ["DAG (confirm before --execute --live):", ""]
    for level in range(max(depths.values()) + 1):
        for nid in sorted(n for n, d in depths.items() if d == level):
            node = nodes[nid]
            profile = node["tau_agent"]["model"].removeprefix("profile:")
            price = ""
            if pricing and pricing.get(profile):
                pr = pricing[profile]
                price = f"  ${pr.get('input_per_mtok', '?')}/${pr.get('output_per_mtok', '?')}/Mtok"
            deps = node["depends_on"]
            arrow = "" if not deps else f"  <- {', '.join(deps)}"
            indent = "    " * level
            lines.append(f"{indent}[{nid}] {node['role']} :: {profile}{price}{arrow}")
    return "\n".join(lines)


@app.command("plan")
def plan(
    request: str = typer.Argument(..., help="Natural-language project request."),
    team: str = typer.Option("fullstack-premium", "--team", help=f"Team preset: {sorted(TEAM_PRESETS)}"),
    repo: str = typer.Option("grahama1970/agent-skills", "--repo", "-R"),
    out: Optional[Path] = typer.Option(None, "--out", help="Directory to write plan + spec."),
    as_json: bool = typer.Option(False, "--json"),
    execute: bool = typer.Option(False, "--execute", help="Submit the frozen spec to Tau for execution."),
    live: bool = typer.Option(False, "--live", help="Required with --execute: makes live provider calls."),
) -> None:
    """Render the plan, compile the frozen Tau spec, and print a preview."""
    strength_mode = None
    if team.startswith("strengths-"):
        strength_mode = team.removeprefix("strengths-")
        plan_payload = render_team_plan(request, repo=repo, team="fullstack-premium")
    else:
        plan_payload = render_team_plan(request, repo=repo, team=team)
    registry: list[dict[str, Any]] = []
    if strength_mode:
        from ask.tau_harness import fetch_profile_registry

        registry = fetch_profile_registry()
        roles = [str(ws["role"]) for ws in plan_payload["workstreams"]]
        selected = select_role_profiles_by_strength(registry, mode=strength_mode, roles=roles)
        plan_payload["team"] = {"preset": "fullstack-premium", "role_profiles": selected, "strength_mode": strength_mode}
    if plan_payload["unresolved"]:
        result = {
            "schema": "ask.team_plan_result.v1",
            "status": "NEEDS_INTERVIEW",
            "unresolved": plan_payload["unresolved"],
            "questions": [
                {
                    "field": "workstreams",
                    "question": "Which workstreams (backend/frontend/docs/tests) should this project include?",
                    "required": True,
                }
            ],
            "plan": plan_payload,
        }
        typer.echo(json.dumps(result, indent=2))
        raise typer.Exit(2)

    ok, errors = validate_project_plan(plan_payload)
    if not ok:
        typer.echo(json.dumps({"status": "INVALID_PLAN", "errors": errors}, indent=2))
        raise typer.Exit(2)

    run_dir = out or Path(tempfile.mkdtemp(prefix="ask-team-plan-"))
    spec = compile_plan_to_tau_spec(plan_payload, run_id="team-plan-preview", run_dir=run_dir)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "project-plan.json").write_text(json.dumps(plan_payload, indent=2), encoding="utf-8")
        (out / "dag-spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")

    pricing_by_profile = {
        p["id"]: p.get("pricing")
        for p in registry
        if f"profile:{p['id']}" in {n["tau_agent"]["model"] for n in spec["nodes"]}
    } if registry else None
    chart = render_ascii_dag(spec, pricing_by_profile)
    if not as_json:
        typer.echo(chart)
        typer.echo("")
    profiles = resolve_role_profiles(plan_payload)
    result = {
        "schema": "ask.team_plan_result.v1",
        "status": "READY",
        "goal": request,
        "team": team,
        "agents": [
            {
                "id": n["node_id"],
                "role": n["role"],
                "profile": n["tau_agent"]["model"],
                "depends_on": n["depends_on"],
            }
            for n in spec["nodes"]
        ],
        "heterogeneous_profiles": heterogeneous_profile_count(spec),
        "chart": chart,
        "pricing": pricing_by_profile,
        "spec_sha256": spec["extensions"]["spec_sha256"],
        "written": {"plan": str(out / "project-plan.json"), "spec": str(out / "dag-spec.json")} if out else None,
        "execution_note": (
            "Executing via Tau (Tau owns scheduling, receipts, settlement)."
            if execute
            else "Preview only; add --execute --live to submit to Tau."
        ),
    }
    _ = profiles

    if execute:
        if not live:
            typer.echo(json.dumps({**result, "status": "EXECUTE_REFUSED", "reason": "refusing to run: live provider calls; pass --live with --execute"}, indent=2))
            raise typer.Exit(2)
        from ask.tau_harness import run_plan_spec

        summary = run_plan_spec(spec, run_dir=run_dir)
        result["execution"] = summary
        result["status"] = "EXECUTED_PASS" if summary["scheduler_status"] == "PASS" else "EXECUTED_" + str(summary["scheduler_status"])
        typer.echo(json.dumps(result, indent=2))
        raise typer.Exit(0 if summary["scheduler_status"] == "PASS" else 1)

    typer.echo(json.dumps(result, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
