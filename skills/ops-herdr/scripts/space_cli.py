#!/usr/bin/env python3
"""Typer sub-app for planning and launching grids of agents in a Herdr space.

Split out of cli.py to keep every module under the 800-line repo limit. The pure
planning logic lives in ops_herdr_topology; this module is the operator surface
over it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ops_herdr_core import (  # noqa: E402
    AGENT_KINDS,
    create_tab,
    create_workspace,
    ensure_dir,
    load_dotenv_once,
    manifest_path_from_run_dir,
    require_protocol,
    run_herdr,
    save_manifest,
    slugify,
    utc_stamp,
)
from ops_herdr_topology import (  # noqa: E402
    GridPlan,
    cells_row_major,
    grid_for_count,
    materialize_grid,
    parse_grid,
    plan_grid,
)

# Idempotent: core loads .env on import; repeated so importing this module alone
# still reads a populated environment before any os.environ lookup below.
load_dotenv_once()

space_app = typer.Typer(help="Plan and launch grids of agents in a Herdr space.")


def print_json(value: Any) -> None:
    """Print deterministic JSON for scripts and receipts."""
    import json

    typer.echo(json.dumps(value, indent=2, sort_keys=True))


def resolve_plan(grid: Optional[str], count: Optional[int]) -> GridPlan:
    """Turn --grid or --count into a validated plan, rejecting both or neither."""
    if bool(grid) == bool(count):
        raise typer.BadParameter("supply exactly one of --grid ROWSxCOLS or --count N")
    try:
        rows, columns = parse_grid(grid) if grid else grid_for_count(int(count or 0))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    return plan_grid(rows, columns)


def parse_agent_specs(specs: list[str] | None) -> list[tuple[str, str]]:
    """Parse repeated --agent name=kind options into ordered (name, kind) pairs."""
    parsed: list[tuple[str, str]] = []
    for spec in specs or []:
        name, sep, kind = spec.partition("=")
        if not sep or not name.strip() or not kind.strip():
            raise typer.BadParameter(f"--agent must look like name=kind, got {spec!r}")
        if kind.strip() not in AGENT_KINDS:
            raise typer.BadParameter(f"unknown kind {kind.strip()!r}; Herdr accepts {', '.join(sorted(AGENT_KINDS))}")
        parsed.append((name.strip(), kind.strip()))
    return parsed


@space_app.command("plan")
def space_plan(
    grid: Annotated[Optional[str], typer.Option(help="Explicit rectangle, e.g. 2x2 or 3x4.")] = None,
    count: Annotated[Optional[int], typer.Option(help="Agent count; the most balanced rectangle is chosen.")] = None,
) -> None:
    """Print the split plan for a grid without touching Herdr.

    Deterministic and offline, so the layout algorithm can be asserted without a
    running server.
    """
    print_json(resolve_plan(grid, count).to_dict())


@space_app.command("launch")
def space_launch(
    repo: Annotated[Path, typer.Option(help="Repository or project cwd for the space.")],
    label: Annotated[str, typer.Option(help="Herdr workspace label.")],
    grid: Annotated[Optional[str], typer.Option(help="Explicit rectangle, e.g. 2x2.")] = None,
    count: Annotated[Optional[int], typer.Option(help="Agent count; picks the most balanced rectangle.")] = None,
    agent: Annotated[Optional[list[str]], typer.Option("--agent", help="Agent to start, as name=kind. Repeatable, assigned row-major.")] = None,
    tab_label: Annotated[str, typer.Option(help="Label for the tab holding the grid.")] = "agents",
    run_root: Annotated[Path, typer.Option(help="Directory for manifests and receipts.")] = Path(".herdr-workstations"),
    timeout_ms: Annotated[int, typer.Option(help="Agent readiness timeout in ms.")] = 30000,
    focus: Annotated[bool, typer.Option("--focus/--no-focus", help="Focus the new space.")] = False,
    dry_run: Annotated[bool, typer.Option(help="Print the plan and stop before mutating Herdr.")] = False,
    herdr_bin: Annotated[str, typer.Option(help="Herdr binary path.")] = "herdr",
    session: Annotated[Optional[str], typer.Option(help="Named Herdr session.")] = None,
) -> None:
    """Build a grid of panes in one new space and optionally attach agents to cells.

    The whole topology is built and verified against Herdr's own layout before any
    agent starts, because `agent start` attaches to an existing idle pane and
    splitting underneath a live agent is not safe.
    """
    plan = resolve_plan(grid, count)
    agents = parse_agent_specs(agent)
    if len(agents) > plan.cell_count:
        raise typer.BadParameter(f"{len(agents)} agents do not fit a {plan.rows}x{plan.columns} grid")
    if dry_run:
        print_json({"plan": plan.to_dict(), "agents": [{"name": n, "kind": k} for n, k in agents]})
        return

    repo = repo.expanduser().resolve()
    if not repo.exists():
        raise typer.BadParameter(f"repo does not exist: {repo}")
    require_protocol(herdr_bin=herdr_bin, session=session)

    run_id = f"{utc_stamp()}-{slugify(label)}"
    run_dir = ensure_dir(run_root.expanduser().resolve() / run_id)
    topology = create_workspace(
        label=label, cwd=repo, session=session, herdr_bin=herdr_bin, env_values=[], dry_run=False,
    )
    tab = create_tab(
        workspace_id=topology.workspace_id, label=tab_label, cwd=repo, session=session,
        herdr_bin=herdr_bin, env_values=[f"TAU_RUN_DIR={run_dir}"], dry_run=False,
    )
    order = cells_row_major(plan)
    cell_env = {
        cell: [f"TAU_RUN_DIR={run_dir}", f"TAU_AGENT_NAME={agents[i][0]}", f"TAU_CELL={cell[0]},{cell[1]}"]
        for i, cell in enumerate(order)
        if i < len(agents)
    }
    panes = materialize_grid(
        tab=tab, plan=plan, cwd=repo, cell_env=cell_env, session=session, herdr_bin=herdr_bin,
    )

    started: dict[str, Any] = {}
    for index, (name, kind) in enumerate(agents):
        cell = order[index]
        pane_id = panes[cell]
        run_herdr(
            ["agent", "start", name, "--kind", kind, "--pane", pane_id, "--timeout", str(timeout_ms)],
            herdr_bin=herdr_bin, session=session,
        )
        started[name] = {"kind": kind, "cell": list(cell), "pane_id": pane_id, "previous_pane_ids": []}

    manifest = {
        "schema_version": 2,
        "kind": "herdr-workstation",
        "run_id": run_id,
        "created_at": utc_stamp(),
        "updated_at": utc_stamp(),
        "label": label,
        "session": session or os.environ.get("HERDR_SESSION") or "default",
        "repo": str(repo),
        "cwd": str(repo),
        "run_dir": str(run_dir),
        "events_jsonl": str(run_dir / "events.jsonl"),
        "workspace_id": topology.workspace_id,
        "root_tab_id": topology.root_tab_id,
        "root_pane_id": topology.root_pane_id,
        "grid": plan.to_dict(),
        "tabs": {
            tab_label: {
                "tab_id": tab.tab_id,
                "root_pane_id": tab.root_pane_id,
                "panes": [panes[cell] for cell in order],
                "occupied": [panes[order[i]] for i in range(len(agents))],
                "cells": {f"{r},{c}": panes[(r, c)] for (r, c) in order},
            }
        },
        "agents": {name: {"role": name, "tab": tab_label, "started_at": utc_stamp(), **info} for name, info in started.items()},
        "worktree": {"enabled": False, "branch": None, "base": None, "path": None, "raw": None},
    }
    save_manifest(manifest_path_from_run_dir(run_dir), manifest)
    if focus:
        run_herdr(["workspace", "focus", topology.workspace_id], herdr_bin=herdr_bin, session=session, check=False)
    print_json(manifest)
