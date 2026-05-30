"""CLI for managing per-project Cursor Browser tab bindings.

  cursor-browser-project bind NAME --view-id ID [--url URL]
  cursor-browser-project list [--json]
  cursor-browser-project show NAME [--json]
  cursor-browser-project unbind NAME
  cursor-browser-project gc [--days N]
  cursor-browser-project verify NAME
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from . import cursor_browser_project
from .ask_config import SURF_RUN

app = typer.Typer(help="Manage per-project Cursor Browser tab bindings for /ask cursor-browser.")


@app.command("bind")
def bind_cmd(
    name: str = typer.Argument(..., help="Project name (e.g. code-runner-review, pr-1234)."),
    view_id: str = typer.Option(..., "--view-id", help="Cursor Browser viewId to bind. Use the browser_tabs list (viewId) to copy from a live tab."),
    url: str = typer.Option("", "--url", help="Optional ChatGPT conversation URL for the bound tab (informational; auto-refreshes on next call)."),
    manual: bool = typer.Option(True, "--manual/--auto", help="Mark this as a human-curated binding. Manual bindings are never auto-replaced; auto bindings get re-created silently if the tab is closed."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Bind a project name to a specific Cursor Browser viewId."""
    try:
        state = cursor_browser_project.bind(name, view_id, conversation_url=url, manual=manual)
    except ValueError as exc:
        typer.echo(f"bind failed: {exc}", err=True)
        raise typer.Exit(2)
    out = state.to_dict()
    out["state_path"] = str(cursor_browser_project.project_state_path(state.name))
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"bound project '{state.name}' → viewId {state.view_id}")
        print(f"  manual:      {state.bound_manually}")
        if state.conversation_url:
            print(f"  url:         {state.conversation_url}")
        print(f"  state_path:  {out['state_path']}")


@app.command("unbind")
def unbind_cmd(
    name: str = typer.Argument(..., help="Project name to unbind."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Remove a project's binding (does not close the Cursor Browser tab)."""
    removed = cursor_browser_project.unbind(name)
    result = {"name": name, "removed": removed}
    if as_json:
        print(json.dumps(result, indent=2))
    elif removed:
        print(f"unbound project '{name}'")
    else:
        print(f"no binding found for project '{name}'")
        raise typer.Exit(1)


@app.command("list")
def list_cmd(
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
    verify: bool = typer.Option(False, "--verify", help="Verify each viewId still exists in Cursor Browser via surf cursor-browser.tab.list (slower)."),
) -> None:
    """List all bound projects."""
    projects = cursor_browser_project.list_projects()
    rows = []
    for state in projects:
        row = state.to_dict()
        if verify:
            try:
                verified = cursor_browser_project.verify(state.name, surf_run=Path(SURF_RUN))
                row["tab_still_open"] = verified is not None
            except cursor_browser_project.ProjectBindingError:
                row["tab_still_open"] = False
        rows.append(row)
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print("no bound projects")
        return
    headers = ["name", "view_id", "manual", "last_used_at"]
    if verify:
        headers.append("tab_still_open")
    widths = {h: max(len(h), *(len(str(r.get(h, ""))) for r in rows)) for h in headers}
    print("  ".join(h.ljust(widths[h]) for h in headers))
    print("  ".join("-" * widths[h] for h in headers))
    for row in rows:
        print("  ".join(str(row.get(h, "")).ljust(widths[h]) for h in headers))


@app.command("show")
def show_cmd(
    name: str = typer.Argument(..., help="Project name to show."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Show the full state for one project."""
    state = cursor_browser_project.load(name)
    if not state:
        print(f"no binding found for project '{name}'", file=sys.stderr)
        raise typer.Exit(1)
    out = state.to_dict()
    out["state_path"] = str(cursor_browser_project.project_state_path(state.name))
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        for key in ["name", "view_id", "conversation_url", "bound_manually", "created_at", "last_used_at", "last_verified_at", "state_path"]:
            print(f"{key}: {out.get(key, '')}")


@app.command("verify")
def verify_cmd(
    name: str = typer.Argument(..., help="Project name to verify."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Check whether the bound tab is still open in Chrome."""
    try:
        state = cursor_browser_project.verify(name, surf_run=Path(SURF_RUN))
    except cursor_browser_project.ProjectBindingError as exc:
        result = {"name": name, "status": "manual_bind_tab_missing", "error": str(exc)}
        if as_json:
            print(json.dumps(result, indent=2))
        else:
            print(str(exc), file=sys.stderr)
        raise typer.Exit(2)
    if state is None:
        result = {"name": name, "status": "missing_or_tab_closed"}
        if as_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"project '{name}' has no valid binding (no state file, or tab is closed)")
        raise typer.Exit(1)
    result = {"name": state.name, "status": "ok", "view_id": state.view_id, "conversation_url": state.conversation_url, "last_verified_at": state.last_verified_at}
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"project '{state.name}' OK — tab {state.view_id} still open")


@app.command("gc")
def gc_cmd(
    days: int = typer.Option(30, "--days", help="Garbage-collect auto-bound projects unused for more than N days. Manually-bound projects are never collected."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Remove stale auto-bound project state files."""
    removed = cursor_browser_project.gc_stale(days=days)
    result = {"days": days, "removed": removed, "count": len(removed)}
    if as_json:
        print(json.dumps(result, indent=2))
    elif removed:
        print(f"removed {len(removed)} stale auto-bindings (>{days}d):")
        for name in removed:
            print(f"  - {name}")
    else:
        print(f"no stale auto-bindings older than {days}d")


if __name__ == "__main__":
    app()
