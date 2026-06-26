#!/usr/bin/env python3
"""Browser commands for WebGPT. Agent runs one-liners — background by default so it never hijacks the user."""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import typer

app = typer.Typer()
BINDING_DIR = Path.home() / ".pi" / "webgpt-projects"
SURF = Path("/home/graham/workspace/experiments/agent-skills/skills/surf/run.sh")


GITHUB_REPO = "agent-skills"
GITHUB_ORG = "grahama1970"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _collect_context(command: str, error: str, stderr: str = "", binding: dict | None = None, **extra: str) -> str:
    """Collect debug context for a bug report."""
    parts = [
        f"## webgpt failure report ({_now()})",
        f"",
        f"**Command:** `{command}`",
        f"**Error:** {error[:500]}",
    ]
    if stderr:
        parts.append(f"**Stderr:**\n```\n{stderr[:2000]}\n```")
    # Desktop state
    parts.append(f"**Current desktop:** {_current_desktop()}")
    parts.append(f"**Desktop list:**\n```\n{_desktop_state()}\n```")
    # Tab list
    try:
        tl = subprocess.run([str(SURF), "tab.list", "--json"], capture_output=True, text=True, timeout=10)
        if tl.returncode == 0 and tl.stdout.strip():
            parts.append(f"**Tabs:**\n```json\n{tl.stdout[:2000]}\n```")
    except Exception:
        pass
    # Binding
    for proj in ["sparta"]:
        p = BINDING_DIR / f"{proj}.json"
        if p.exists():
            parts.append(f"**Binding ({proj}):**\n```json\n{p.read_text().strip()[:1000]}\n```")
    # Surf version
    try:
        ver = subprocess.run([str(SURF.parent / "vendor" / "surf-cli" / "native" / "cli.cjs"), "--version"], capture_output=True, text=True, timeout=5)
        if ver.returncode == 0:
            parts.append(f"**Surf CLI:** {ver.stdout.strip()}")
    except Exception:
        pass
    # Env
    env_keys = ["DISPLAY", "KDE_FULL_SESSION", "XDG_CURRENT_DESKTOP", "DESKTOP_SESSION", "VIRTUAL_ENV"]
    env_info = {k: os.environ.get(k, "") for k in env_keys}
    parts.append(f"**Env:** {json.dumps(env_info)}")
    # Extra
    for k, v in extra.items():
        if v:
            parts.append(f"**{k}:** {v[:500]}")
    parts.append(f"\n---\nAuto-filed by `webgpt_cli.py`")
    return "\n".join(parts)


def _file_issue(title: str, body: str) -> bool:
    """File a GitHub issue on the agent-skills repo. Returns True on success."""
    try:
        result = subprocess.run(
            ["gh", "issue", "create", "--repo", f"{GITHUB_ORG}/{GITHUB_REPO}", "--title", title, "--body", body, "--label", "bug", "--label", "webgpt"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"  [filed] {result.stdout.strip()}", file=sys.stderr)
            return True
        else:
            print(f"  [issue failed] {result.stderr[:500]}", file=sys.stderr)
            return False
    except Exception as exc:
        print(f"  [issue exception] {exc}", file=sys.stderr)
        return False


def _report_failure(command: str, result: subprocess.CompletedProcess, binding: dict | None = None, **extra: str) -> None:
    """Collect context and file a GitHub issue for a webgpt failure."""
    error = (result.stderr or "")[:500]
    title = f"webgpt: {command} failed — {error[:80]}"
    body = _collect_context(command, error, result.stderr or "", binding=binding, **extra)
    _file_issue(title, body)


def _binding(project: str) -> dict:
    path = BINDING_DIR / f"{project}.json"
    if not path.exists():
        return {}
    b = json.loads(path.read_text())
    if not b.get("kde_desktop_index"):
        info = _surf("tab.list", "--json", "--with-kde")
        if info.returncode == 0 and info.stdout.strip():
            try:
                data = json.loads(info.stdout)
                tabs = data.get("tabs", []) if isinstance(data, dict) else data
                for t in tabs if isinstance(tabs, list) else []:
                    kde = t.get("kde", {}) or {}
                    di = kde.get("desktop_index")
                    if di is not None:
                        b["kde_desktop_index"] = str(di + 1)
                        path.write_text(json.dumps(b, indent=2) + "\n")
                        break
            except (json.JSONDecodeError, KeyError, TypeError, IndexError):
                pass
    return b


def _current_desktop() -> str | None:
    """Return current KDE desktop number (1-indexed, human-readable)."""
    qdbus = subprocess.run(["qdbus", "org.kde.KWin", "/KWin", "currentDesktop"], capture_output=True, text=True, timeout=5)
    return qdbus.stdout.strip() or None


def _desktop_state() -> str:
    """Return wmctrl desktop list for debugging."""
    r = subprocess.run(["wmctrl", "-d"], capture_output=True, text=True, timeout=5)
    return r.stdout.strip() if r.returncode == 0 else "wmctrl unavailable"


def _verify_desktop(binding: dict, background: bool, label: str = "") -> None:
    """Verify tab identity and KDE desktop. Always called on every command.
    
    Files a GitHub issue for any unexpected result: desktop mismatch, URL
    mismatch, tab not found, etc. Forces the agent to acknowledge problems.
    """
    tab_id = binding.get("tab_id", "")
    target_desk = binding.get("kde_desktop_index", "")
    conv_url = binding.get("conversation_url", "")
    if not tab_id and not target_desk:
        return

    tag = f" [{label}]" if label else ""
    findings: list[str] = []

    actual_desk = None
    actual_url = None
    tab_info = _surf("tab.list", "--json", "--with-kde")
    if tab_info.returncode == 0 and tab_info.stdout.strip():
        try:
            data = json.loads(tab_info.stdout)
            tabs = data.get("tabs", []) if isinstance(data, dict) else data
            for t in tabs if isinstance(tabs, list) else []:
                if str(t.get("id", "")) == tab_id:
                    kde = t.get("kde", {}) or {}
                    actual_desk = kde.get("desktop_index")
                    actual_url = t.get("url", "")
                    break
        except (json.JSONDecodeError, KeyError, TypeError, IndexError):
            pass

    # Desktop mismatch
    if target_desk and actual_desk is not None:
        human_actual = int(actual_desk) + 1
        if str(human_actual) != target_desk:
            msg = f"DESKTOP_MISMATCH: binding={target_desk} actual={human_actual}{tag}"
            print(f"ERROR_{msg}", file=sys.stderr)
            print(f"  fix: wmctrl -s {str(int(target_desk)-1)}  # switch desktop", file=sys.stderr)
            print(f"  fix: config --kde-desktop {human_actual}  # update binding", file=sys.stderr)
            findings.append(msg)
            if not background:
                subprocess.run(["wmctrl", "-s", str(int(target_desk)-1)], timeout=5)
                time.sleep(1)

    # URL mismatch
    if conv_url and actual_url and conv_url.split("/")[-1] != actual_url.split("/")[-1]:
        msg = f"URL_MISMATCH: binding={conv_url[-60:]} actual={actual_url[-60:]}{tag}"
        print(f"ERROR_{msg}", file=sys.stderr)
        print(f"  fix: config --url {actual_url}", file=sys.stderr)
        findings.append(msg)

    # Tab not found
    if tab_id and actual_desk is None:
        msg = f"TAB_NOT_FOUND: tab_id={tab_id}{tag}"
        print(f"ERROR_{msg}", file=sys.stderr)
        findings.append(msg)

    # File issue for every finding
    for f in findings:
        result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr=f"webgpt verification: {f}",
        )
        _report_failure(f"verify", result, binding=binding)


def _surf(*args: str | int, capture: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    kwargs: dict = {"capture_output": capture, "text": True} if capture else {}
    if timeout:
        kwargs["timeout"] = timeout
    return subprocess.run([str(SURF)] + [str(a) for a in args], **kwargs)


def _active_chatgpt_tab() -> str:
    """Return the most recent ChatGPT tab id from the surf controlled-tab file, or empty."""
    f = Path("/tmp/surf-webgpt-controlled-tab-id")
    return f.read_text().strip() if f.exists() else ""


def _click_and_wait_download(tab_id: str, pattern: str, timeout: int = 60, background: bool = False) -> Path | None:
    """Click a download button by text match, poll ~/Downloads."""
    before = set((Path.home() / "Downloads").iterdir()) if (Path.home() / "Downloads").exists() else set()
    _surf("click", pattern, *(["--no-activate"] if background else []), "--tab-id", tab_id, capture=False)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        after = set((Path.home() / "Downloads").iterdir())
        new = [f for f in (after - before) if pattern in f.name and f.stat().st_size > 0]
        if new:
            return new[0]
    return None


@app.command()
def submit(
    bundle: str | None = typer.Argument(None, help="Path to creation bundle (auto-finds latest)"),
    project: str = typer.Option("sparta", "-p"),
    timeout: int = typer.Option(900, "--timeout", "-t", help="WebGPT timeout (seconds)"),
    background: bool = typer.Option(True, "--background", help="Background: no KDE switch, no window focus"),
):
    """Submit a bundle, capture response, download solution zip. All complexity hidden."""
    bp = Path(bundle) if bundle else _latest_bundle()
    if not bp or not bp.exists():
        typer.echo("Bundle not found", err=True)
        raise typer.Exit(1)

    b = _binding(project)
    _verify_desktop(b, background, "submit")

    resp_path = bp.with_name(f"{bp.stem}-response.md")
    zip_path = bp.with_name(f"{bp.stem}-solution.zip")

    typer.echo(f"Submitting {bp.name}...", err=True)
    cmd: list[str | int] = ["webgpt.submit", "--input", str(bp), "--output", str(resp_path), "--timeout", str(timeout), "--create-tab"]
    if background:
        cmd += ["--no-activate"]
    if bp.suffix == ".zip":
        cmd += ["--attach-file", str(bp)]
    result = _surf(*cmd)

    if result.returncode != 0:
        _report_failure("submit", result, binding=b, bundle=str(bp), timeout=str(timeout))
        typer.echo(f"Submit failed", err=True)
        raise typer.Exit(result.returncode)
    typer.echo(f"Response: {resp_path}")

    # Try to download solution zip from the new tab
    typer.echo("Looking for solution zip...", err=True)
    time.sleep(3)
    new_tab = _active_chatgpt_tab()
    if new_tab:
        found = _click_and_wait_download(new_tab, ".zip", timeout=120, background=background)
        if found:
            shutil.copy2(str(found), str(zip_path))
            typer.echo(f"Solution: {zip_path}")
            return
    typer.echo("No zip detected (check Downloads)", err=True)


def _latest_bundle() -> Path | None:
    for root in [Path(__file__).resolve().parent.parent.parent / "webgpt-engagement"]:
        candidates = sorted(root.rglob("creation-bundle*.md"))
        if candidates:
            return candidates[-1]
    return None


@app.command()
def download(
    project: str = typer.Option("sparta", "-p"),
    match: str = typer.Option(".zip", "--match", "-m"),
    timeout: int = typer.Option(60, "--timeout", "-t"),
    output: str | None = typer.Option(None, "-o"),
    background: bool = typer.Option(True, "--background"),
):
    """Click the download button in the ChatGPT tab, wait for the file in ~/Downloads."""
    _verify_desktop(_binding(project), background, "download")
    tab_id = _active_chatgpt_tab()
    if not tab_id:
        tab_id = _binding(project).get("tab_id", "")
    if not tab_id:
        _report_failure("download", subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="no tab id"), binding=_binding(project), project=project)
        typer.echo("No active ChatGPT tab found", err=True)
        raise typer.Exit(1)
    found = _click_and_wait_download(tab_id, match, timeout, background=background)
    if found:
        out = Path(output) if output else found
        if output:
            shutil.copy2(str(found), str(out))
        typer.echo(str(out))
    else:
        typer.echo(f"No file matched '{match}'", err=True)
        raise typer.Exit(1)


@app.command()
def listen(
    project: str = typer.Option("sparta", "-p"),
    timeout: int = typer.Option(900, "--timeout", "-t"),
    output: str = typer.Option("response.md", "-o"),
    background: bool = typer.Option(True, "--background"),
):
    """Wait for WebGPT to finish generating and capture the response."""
    b = _binding(project)
    _verify_desktop(b, background, "listen")
    tab_id = _active_chatgpt_tab() or b.get("tab_id", "")
    if not tab_id:
        _report_failure("listen", subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="no tab id"), binding=_binding(project), project=project)
        typer.echo("No tab id available", err=True)
        raise typer.Exit(1)
    typer.echo(f"Listening (tab {tab_id}, timeout={timeout}s)...", err=True)
    cmd: list[str | int] = ["webgpt.extract", "--tab-id", tab_id, "--timeout", str(timeout), "--sentinel", "auto"]
    if background:
        cmd += ["--no-activate"]
    result = _surf(*cmd)
    if result.returncode == 0 and result.stdout.strip():
        Path(output).write_text(result.stdout)
        typer.echo(f"Response: {output}")
    else:
        typer.echo("No response captured", err=True)
        raise typer.Exit(1)


@app.command()
def activate(
    project: str = typer.Option("sparta", "-p"),
    background: bool = typer.Option(True, "--background"),
):
    """Activate the project tab: KDE switch, close duplicates, release CDP, clear drafts."""
    b = _binding(project)
    _verify_desktop(b, background, "activate")
    tab_id = b.get("tab_id", "")
    if not tab_id:
        typer.echo("No tab_id in binding. Run `config` first or use `submit` which auto-creates.", err=True)
        return
    _surf("tab.activate", tab_id, capture=False)
    time.sleep(2)
    if not background:
        typer.echo(f"Tab {tab_id} ready")


@app.command()
def navigate(
    url: str = typer.Argument(..., help="URL"),
    project: str = typer.Option("sparta", "-p"),
    background: bool = typer.Option(True, "--background"),
):
    """Navigate the project tab to a URL."""
    b = _binding(project)
    _verify_desktop(b, background, "navigate")
    tab_id = b.get("tab_id", "")
    if not tab_id:
        typer.echo("No tab_id in binding", err=True)
        raise typer.Exit(1)
    _surf("go", url, *(["--no-activate"] if background else []), "--tab-id", tab_id)


@app.command()
def close(tab_id: str = typer.Argument(..., help="Tab id to close")):
    """Close a browser tab."""
    _surf("tab.close", tab_id, capture=False)


@app.command()
def config(
    project: str = typer.Option("sparta", "-p"),
    tab_id: str = typer.Option("", "--tab-id"),
    url: str = typer.Option("", "--url"),
    kde: str = typer.Option("2", "--kde-desktop", help="Desktop number (1=Desktop1, 2=Desktop2)"),
):
    """Create or update a project binding."""
    path = BINDING_DIR / f"{project}.json"
    binding = json.loads(path.read_text()) if path.exists() else {"name": project, "backend": "webgpt"}
    if tab_id:
        binding["tab_id"] = tab_id
    if url:
        binding["conversation_url"] = url
    if kde:
        binding["kde_desktop_index"] = kde
    path.write_text(json.dumps(binding, indent=2) + "\n")
    typer.echo(f"Wrote {path}")


if __name__ == "__main__":
    app()
