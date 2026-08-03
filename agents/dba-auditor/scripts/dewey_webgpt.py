#!/usr/bin/env python3
"""Typer CLI for Dewey's WebGPT interactions.

Encapsulates surf + clipboard ops for the dba-auditor agent:
- Tab activation, duplicate cleanup, KDE desktop switch
- Submit to WebGPT, download solution zip
- All target info from ~/.pi/webgpt-projects/<project>.json
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time
from pathlib import Path

import typer

app = typer.Typer()

PROJECT = "sparta"
BINDING_DIR = Path.home() / ".pi" / "webgpt-projects"
SURF = Path("/home/graham/workspace/experiments/agent-skills/skills/surf/run.sh")
CLI = SURF.parent / "vendor" / "surf-cli" / "native" / "cli.cjs"
DOWNLOADS = Path.home() / "Downloads"
DEFAULT_TIMEOUT = 900


def _binding() -> dict:
    path = BINDING_DIR / f"{PROJECT}.json"
    if not path.exists():
        typer.echo(f"Error: no project binding at {path}", err=True)
        typer.echo("Run: skills/ask/run.sh register --project sparta --backend webgpt", err=True)
        raise typer.Exit(1)
    return json.loads(path.read_text())


def _run(*cmd: str, timeout: int | None = None, capture: bool = True) -> subprocess.CompletedProcess:
    kwargs = dict(text=True)
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    if timeout:
        kwargs["timeout"] = timeout
    return subprocess.run([str(c) for c in cmd], **kwargs)


def _surf(*args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
    return _run(str(SURF), *args, timeout=timeout)


def _cli(*args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
    return _run(str(CLI), *args, timeout=timeout)


def _switch_kde_desktop(target: str) -> None:
    proc = _run("qdbus", "org.kde.KWin", "/KWin", "currentDesktop")
    current = proc.stdout.strip()
    if current and current != target:
        typer.echo(f"Switching to KDE desktop {target}", err=True)
        _run("wmctrl", "-s", target)
        time.sleep(1)


def _activate_tab(tab_id: str) -> None:
    typer.echo(f"Activating tab {tab_id}", err=True)
    _surf("tab.activate", tab_id, timeout=10)
    time.sleep(2)


def _clear_composer(tab_id: str) -> None:
    _surf(
        "js",
        r"""const ta = document.querySelector('#prompt-textarea') || document.querySelector('[contenteditable]');
if (typeof localStorage != 'undefined') {
  Object.keys(localStorage).filter(k => k.includes('draft') || k.includes('composer')).forEach(k => localStorage.removeItem(k));
}
if (ta) {
  if (ta.tagName === 'TEXTAREA' || ta.tagName === 'INPUT') ta.value = '';
  else { ta.innerHTML = '<p></p>'; ta.textContent = ''; }
  ta.dispatchEvent(new Event('input', {bubbles: true}));
}
return 'ok'""",
        "--tab-id", tab_id,
        timeout=10,
    )


def _close_duplicates(tab_id: str, target_url: str) -> None:
    proc = _surf("tab.list", "--json")
    if proc.returncode != 0:
        return
    try:
        tabs = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return
    for t in tabs:
        tid = str(t.get("id", ""))
        if tid != tab_id and t.get("url", "") == target_url:
            typer.echo(f"Closing duplicate tab {tid}", err=True)
            _cli("tab.close", tid, timeout=5)


def _download_zip(
    tab_id: str,
    output: Path | None = None,
    timeout: int = 30,
) -> Path | None:
    typer.echo(f"Looking for download button...", err=True)
    proc = _surf(
        "js",
        """return JSON.stringify(Array.from(document.querySelectorAll('button')).filter(e => (e.textContent || '').toLowerCase().includes('.zip')).map(e => ({text: e.textContent?.trim()})), null, 2)""",
        "--tab-id", tab_id,
        timeout=10,
    )
    if proc.returncode != 0 or not proc.stdout.strip() or proc.stdout.strip() == '"undefined"':
        typer.echo("No .zip button found", err=True)
        return None

    files_before = set(os.listdir(str(DOWNLOADS)))

    typer.echo("Clicking download button...", err=True)
    _surf("click", ".zip", "--tab-id", tab_id, timeout=5)

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        files_after = set(os.listdir(str(DOWNLOADS)))
        new = files_after - files_before
        for f in sorted(new):
            path = DOWNLOADS / f
            if path.is_file() and path.stat().st_size > 0:
                typer.echo(f"Downloaded: {path}", err=True)
                if output:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    import shutil
                    shutil.copy2(str(path), str(output))
                    typer.echo(f"Copied to: {output}", err=True)
                    return output
                return path
    typer.echo(f"Download timeout after {timeout}s", err=True)
    return None


@app.command()
def submit(
    bundle: str = typer.Argument(..., help="Path to creation bundle markdown"),
    output: str | None = typer.Option(None, "--output", "-o", help="Response output path"),
    project: str = typer.Option(PROJECT, "--project", "-p"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT, "--timeout", "-t"),
):
    """Submit a creation bundle to WebGPT.
    
    Hides all complexity: KDE desktop switch, tab activation, CDP cleanup,
    composer clear, duplicate tab close, submit, and solution zip download.
    Agent runs one command, everything else is automatic.
    """
    bundle_path = Path(bundle).resolve()
    resp_path = Path(output or f"{bundle_path.stem}-response.md").resolve()
    zip_path = Path(output or f"{bundle_path.stem}-solution.zip").resolve()

    binding = _binding()
    tab_id = binding.get("tab_id", "")
    conv_url = binding.get("conversation_url", "")
    kde = binding.get("kde_desktop_index", "2")

    if not tab_id:
        typer.echo("Error: no tab_id in project binding", err=True)
        raise typer.Exit(1)

    _switch_kde_desktop(kde)
    _activate_tab(tab_id)
    _clear_composer(tab_id)
    _close_duplicates(tab_id, conv_url)

    typer.echo(f"Submitting to WebGPT (timeout={timeout}s)...", err=True)
    result = _surf(
        "webgpt.submit",
        "--input", str(bundle_path),
        "--output", str(resp_path),
        "--create-tab",
        "--timeout", str(timeout),
    )
    if result.returncode != 0:
        typer.echo(f"Submit failed (rc={result.returncode})", err=True)
        if result.stderr:
            typer.echo(result.stderr[:2000], err=True)
        raise typer.Exit(result.returncode)

    typer.echo(f"Response written to {resp_path}", err=True)

    # Try to download solution zip
    new_tab_proc = _surf("tab.list", "--json")
    if new_tab_proc.returncode == 0:
        try:
            tabs = json.loads(new_tab_proc.stdout)
            if tabs:
                newest = max(tabs, key=lambda t: t.get("id", 0))
                new_id = str(newest.get("id", ""))
                if new_id:
                    time.sleep(2)
                    _download_zip(new_id, output=zip_path)
        except (json.JSONDecodeError, ValueError):
            pass


@app.command()
def download(
    project: str = typer.Option(PROJECT, "--project", "-p"),
    pattern: str = typer.Option(".zip", "--match", "-m"),
    output: str | None = typer.Option(None, "--output", "-o"),
    timeout: int = typer.Option(30, "--timeout", "-t"),
):
    """Download a file from the ChatGPT conversation."""
    binding = _binding()
    tab_id = binding.get("tab_id", "")
    kde = binding.get("kde_desktop_index", "2")

    _switch_kde_desktop(kde)
    _activate_tab(tab_id)

    result = _download_zip(
        tab_id,
        output=Path(output) if output else None,
        timeout=timeout,
    )
    if result:
        typer.echo(str(result))
    else:
        raise typer.Exit(1)


@app.command()
def activate(
    project: str = typer.Option(PROJECT, "--project", "-p"),
):
    """Activate the project's WebGPT tab (release stale CDP, switch desktop)."""
    binding = _binding()
    tab_id = binding.get("tab_id", "")
    kde = binding.get("kde_desktop_index", "2")
    conv_url = binding.get("conversation_url", "")

    _switch_kde_desktop(kde)
    _activate_tab(tab_id)
    _clear_composer(tab_id)
    _close_duplicates(tab_id, conv_url)
    typer.echo(f"Tab {tab_id} ready")


@app.command()
def cleanup(
    project: str = typer.Option(PROJECT, "--project", "-p"),
):
    """Close duplicate ChatGPT tabs with the same conversation URL."""
    binding = _binding()
    tab_id = binding.get("tab_id", "")
    conv_url = binding.get("conversation_url", "")
    _close_duplicates(tab_id, conv_url)


@app.command()
def requote(
    project: str = typer.Option(PROJECT, "--project", "-p"),
    timeout: int = typer.Option(DEFAULT_TIMEOUT, "--timeout", "-t"),
):
    """Re-submit the last bundle (re-engage WebGPT after porting fixes).
    
    Finds the most recent creation-bundle*.md in the webgpt-engagement dirs
    and submits it again. Agent runs one command after porting WebGPT's fixes.
    """
    agent_dir = Path(__file__).resolve().parent.parent
    engagement_root = agent_dir / "webgpt-engagement"
    if not engagement_root.exists():
        typer.echo("Error: no webgpt-engagement directory found", err=True)
        raise typer.Exit(1)

    bundles = sorted(engagement_root.rglob("creation-bundle*.md"))
    if not bundles:
        typer.echo("Error: no creation-bundle*.md found in webgpt-engagement/", err=True)
        raise typer.Exit(1)

    latest = bundles[-1]
    typer.echo(f"Re-submitting: {latest}", err=True)
    submit(str(latest), project=project, timeout=timeout)


if __name__ == "__main__":
    app()
