"""Typer CLI for browser-oracle bind, resolve, register, and doctor."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from .bindings import BindingError, bind, list_bindings, load, rebind_by_exact_url, unbind, verify
from .bindings import BindingError, bind, list_bindings, load, unbind, verify
from .config import SUPPORTED_BACKENDS, project_root, surf_run_path
from .registry import register_mapping, resolve_project
from .walkup import find_all_registries, find_registry

def _default_from() -> str:
    return os.environ.get("BROWSER_ORACLE_CALLER_CWD", ".")



app = typer.Typer(
    help="Persistent browser-oracle tab bindings and directory walk-up registry.",
    no_args_is_help=True,
)


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, indent=2, default=str))
    else:
        for key, value in payload.items():
            typer.echo(f"{key}: {value}")


@app.command("resolve")
def resolve_cmd(
    from_path: str = typer.Option(_default_from, "--from", help="Directory or file to resolve from."),
    backend: str = typer.Option("webgpt", "--backend", help="Browser oracle backend."),
    project: str = typer.Option("", "--project", help="Explicit project name override."),
    lane: str = typer.Option("", "--lane", help="Named lane from registry lanes map."),
    as_json: bool = typer.Option(False, "--json", help="JSON output."),
) -> None:
    """Resolve project name via walk-up registry; load ~/.pi binding if present."""
    if backend not in SUPPORTED_BACKENDS:
        typer.echo(f"unsupported backend {backend!r}", err=True)
        raise typer.Exit(2)
    result = resolve_project(
        start=from_path,
        backend=backend,
        project_override=project,
        lane=lane,
    )
    payload = {
        "backend": result.backend,
        "project": result.project,
        "source": result.source,
        "relative_path": result.relative_path,
        "registry_path": str(result.registry_path) if result.registry_path else None,
        "registry_root": str(result.registry_root) if result.registry_root else None,
        "binding_path": str(result.binding_path) if result.binding_path else None,
        "human_name": result.binding.human_name if result.binding else None,
        "tab_id": result.binding.tab_id if result.binding else None,
        "view_id": result.binding.view_id if result.binding else None,
        "conversation_url": result.binding.conversation_url if result.binding else None,
        "kde_desktop_index": result.binding.kde_desktop_index if result.binding else None,
        "bound_manually": result.binding.bound_manually if result.binding else None,
        "status": "ok" if result.project else "needs_attention",
    }
    if not result.project:
        payload["reason"] = "no_project_resolved"
        payload["resume_hint"] = (
            "browser-oracle register --at <dir> --project <name> "
            "&& browser-oracle bind <name> --tab-id <id> --url <url> --manual"
        )
    elif not result.binding:
        payload["reason"] = "binding_missing"
        payload["resume_hint"] = (
            f"browser-oracle bind {result.project} --backend {backend} "
            "--tab-id <id> --url <url> --manual"
        )
    _emit(payload, as_json)
    if not result.project:
        raise typer.Exit(2)


@app.command("bind")
def bind_cmd(
    name: str = typer.Argument(..., help="Project name (e.g. oc-subagent-personas)."),
    backend: str = typer.Option("webgpt", "--backend"),
    human_name: str = typer.Option("", "--human-name", "--display-name", help="Human-facing name for this browser oracle binding."),
    tab_id: str = typer.Option("", "--tab-id", help="Chrome tab id (WebGPT/Gemini/Kimi)."),
    view_id: str = typer.Option("", "--view-id", help="Cursor Browser viewId."),
    url: str = typer.Option("", "--url", help="Conversation URL for identity checks."),
    kde_desktop_index: str = typer.Option("", "--kde-desktop", "--desktop", help="Human KDE desktop number, 1-indexed."),
    manual: bool = typer.Option(True, "--manual/--auto", help="Manual bindings are not auto-replaced."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Store tab id / viewId + URL under ~/.pi/*-projects/."""
    try:
        state = bind(
            name,
            backend,
            human_name=human_name,
            tab_id=tab_id,
            view_id=view_id,
            conversation_url=url,
            kde_desktop_index=kde_desktop_index,
            manual=manual,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)
    payload = {**state.to_dict(), "state_path": str(project_root(backend) / f"{state.name}.json")}
    _emit(payload, as_json)
    if not as_json:
        typer.echo(f"bound {state.name} ({backend})")


@app.command("verify")
def verify_cmd(
    name: str = typer.Argument(...),
    backend: str = typer.Option("webgpt", "--backend"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Verify a project's tab is still open (Chrome backends via surf tab.list)."""
    try:
        state = verify(name, backend, surf_run=surf_run_path())
    except BindingError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)
    if state is None:
        typer.echo(f"no binding or tab missing for {name!r}", err=True)
        raise typer.Exit(1)
    payload = {**state.to_dict(), "verified": True}
    _emit(payload, as_json)


@app.command("list")
def list_cmd(
    backend: Optional[str] = typer.Option(None, "--backend"),
    verify_tabs: bool = typer.Option(False, "--verify", help="Check tabs via surf."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List machine-local browser-oracle project bindings."""
    rows = []
    for state in list_bindings(backend):
        row = state.to_dict()
        row["state_path"] = str(project_root(state.backend) / f"{state.name}.json")
        if verify_tabs and state.backend != "cursor-browser":
            try:
                verified = verify(state.name, state.backend, surf_run=surf_run_path())
                row["tab_open"] = verified is not None
            except BindingError:
                row["tab_open"] = False
        rows.append(row)
    if as_json:
        typer.echo(json.dumps(rows, indent=2))
@app.command("rebind-by-exact-url")
def rebind_by_exact_url_cmd(
    name: str = typer.Argument(...),
    backend: str = typer.Option("webgpt", "--backend"),
    maintenance_authorized: bool = typer.Option(False, "--maintenance-authorized", help="Allow maintenance rebind of manually pinned bindings."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Atomically rebind a stale tab id by exactly one live stored-URL match."""
    try:
        payload = rebind_by_exact_url(
            name,
            backend,
            surf_run=surf_run_path(),
            maintenance_authorized=maintenance_authorized,
        )
    except BindingError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)
    _emit(payload, as_json)


@app.command("list")
        for row in rows:
            typer.echo(
                f"{row['name']}\t{row['backend']}\ttab={row.get('tab_id') or row.get('view_id')}\t{row['state_path']}"
            )


@app.command("unbind")
def unbind_cmd(
    name: str = typer.Argument(...),
    backend: str = typer.Option("webgpt", "--backend"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Remove a binding file (does not close the browser tab)."""
    removed = unbind(name, backend)
    payload = {"name": name, "backend": backend, "removed": removed}
    _emit(payload, as_json)
    if not removed:
        raise typer.Exit(1)


@app.command("register")
def register_cmd(
    at: str = typer.Option(".", "--at", help="Directory that will own the registry (creates .ask/)."),
    backend: str = typer.Option("webgpt", "--backend"),
    project: str = typer.Argument(..., help="Project name to map."),
    relative_path: str = typer.Option("", "--relative-path", help="Path under --at for by_relative_path map."),
    default: bool = typer.Option(False, "--default", help="Set backend default project for this registry root."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Write or update .ask/browser-oracles.yaml at the registry root."""
    root = Path(at).expanduser().resolve()
    if not root.is_dir():
        typer.echo(f"--at must be a directory: {root}", err=True)
        raise typer.Exit(2)
    path = register_mapping(
        registry_root=root,
        backend=backend,
        project=project,
        relative_path=relative_path,
        as_default=default or not relative_path.strip(),
    )
    payload = {
        "registry_path": str(path),
        "registry_root": str(root),
        "backend": backend,
        "project": project,
        "relative_path": relative_path or None,
        "default": default or not relative_path.strip(),
    }
    _emit(payload, as_json)


@app.command("show-registry")
def show_registry_cmd(
    from_path: str = typer.Option(_default_from, "--from"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show nearest registry file discovered by walk-up."""
    hit = find_registry(from_path)
    if hit is None:
        typer.echo("no registry found on walk-up chain", err=True)
        raise typer.Exit(1)
    payload = {
        "registry_path": str(hit.registry_path),
        "registry_root": str(hit.registry_root),
    }
    _emit(payload, as_json)


@app.command("walk-up")
def walk_up_cmd(
    from_path: str = typer.Option(_default_from, "--from"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List all registry files on the walk-up chain (child-nearest first)."""
    hits = find_all_registries(from_path)
    rows = [
        {"registry_path": str(h.registry_path), "registry_root": str(h.registry_root)} for h in hits
    ]
    if as_json:
        typer.echo(json.dumps(rows, indent=2))
    else:
        for row in rows:
            typer.echo(f"{row['registry_root']}\t{row['registry_path']}")
    if not rows:
        raise typer.Exit(1)


@app.command("doctor")
def doctor_cmd(
    from_path: str = typer.Option(_default_from, "--from"),
    backend: str = typer.Option("webgpt", "--backend"),
    project: str = typer.Option("", "--project"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Resolve project from directory, verify binding, report readiness."""
    result = resolve_project(
        start=from_path,
        backend=backend,
        project_override=project,
    )
    issues: list[str] = []
    if not result.project:
        issues.append("no_project_resolved")
    if result.project and not result.binding:
        issues.append("binding_missing")
    verified = None
    if result.project and result.binding:
        try:
            verified = verify(result.project, backend, surf_run=surf_run_path())
        except BindingError:
            issues.append("tab_stale_manual_binding")
            verified = None
        if verified is None and "tab_stale_manual_binding" not in issues:
            issues.append("tab_not_open")
    surf = surf_run_path()
    if not surf.exists():
        issues.append("surf_missing")
    readiness = "ready" if not issues else "needs_attention"
    payload = {
        "readiness": readiness,
        "backend": backend,
        "project": result.project,
        "source": result.source,
        "registry_path": str(result.registry_path) if result.registry_path else None,
        "binding_path": str(result.binding_path) if result.binding_path else None,
        "human_name": result.binding.human_name if result.binding else None,
        "tab_id": result.binding.tab_id if result.binding else None,
        "conversation_url": result.binding.conversation_url if result.binding else None,
        "kde_desktop_index": result.binding.kde_desktop_index if result.binding else None,
        "issues": issues,
        "surf_run": str(surf),
    }
    if issues:
        payload["resume_hint"] = (
            "browser-oracle register --at <dir> --project <name> --default && "
            "browser-oracle bind <name> --tab-id <id> --url <url> --manual"
        )
    _emit(payload, as_json)
    if issues:
        raise typer.Exit(2)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
