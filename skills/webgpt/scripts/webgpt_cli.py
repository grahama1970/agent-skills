#!/usr/bin/env python3
"""Browser commands for WebGPT. Agent runs one-liners — background by default so it never hijacks the user."""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer()
BINDING_DIR = Path.home() / ".pi" / "webgpt-projects"
SURF = Path.home() / "workspace/experiments/agent-skills/skills/surf/run.sh"


GITHUB_REPO = "agent-skills"
GITHUB_ORG = "grahama1970"

EXECUTION_LOCK_HEADINGS = (
    "objective",
    "current phase",
    "critical path",
    "deferred work",
    "failure policy",
    "stop condition",
)

CODE_GATE_FIELDS = (
    "current_gate",
    "blocking_defect",
    "allowed_files",
    "required_live_proof",
    "stop_condition",
    "forbidden_adjacent_scope",
)

EXECUTION_LOCK_DIRECTIVES = (
    "max_identical_failures_per_family: 3",
    "systemic_failure_action: stop_family_mark_remaining_blocked_continue_independent_families",
    "reviewer_scope_authority: none",
)


def validate_execution_lock(text: str) -> list[str]:
    """Return missing execution-lock requirements for deadline-bound reviews."""
    lowered = text.lower()
    missing = [
        heading
        for heading in EXECUTION_LOCK_HEADINGS
        if f"## {heading}" not in lowered
    ]
    missing.extend(
        directive
        for directive in EXECUTION_LOCK_DIRECTIVES
        if directive not in lowered
    )
    return missing


def validate_code_gate(text: str) -> list[str]:
    """Return missing or duplicated fields in a code-deliverable gate."""
    errors: list[str] = []
    for field in CODE_GATE_FIELDS:
        matches = re.findall(
            rf"(?im)^\s*(?:[-*]\s*)?{re.escape(field)}\s*:\s*(\S.*)$",
            text,
        )
        if not matches:
            errors.append(f"missing_{field}")
        elif len(matches) > 1:
            errors.append(f"duplicate_{field}")
    return errors


def code_gate_values(text: str) -> dict[str, str]:
    """Parse canonical gate fields after validation succeeds."""
    values: dict[str, str] = {}
    for field in CODE_GATE_FIELDS:
        match = re.search(
            rf"(?im)^\s*(?:[-*]\s*)?{re.escape(field)}\s*:\s*(\S.*)$",
            text,
        )
        if match:
            values[field] = match.group(1).strip()
    return values


def _allowed_path(path: str, allowed: list[str]) -> bool:
    normalized = path.removeprefix("a/").removeprefix("b/").lstrip("./")
    return any(
        normalized == item.rstrip("/")
        or (item.endswith("/") and normalized.startswith(item))
        for item in allowed
    )


def code_deliverable_errors(
    response_text: str,
    zip_path: Path,
    gate_text: str,
    repo_root: Path | None = None,
) -> list[str]:
    """Validate that returned code is real and stays inside the declared boundary."""
    allowed = [
        item.strip().lstrip("./")
        for item in code_gate_values(gate_text).get("allowed_files", "").split(",")
        if item.strip()
    ]
    diff_paths = re.findall(r"(?m)^diff --git a/(\S+) b/(\S+)$", response_text)
    patch_paths = re.findall(
        r"(?m)^\*\*\* (?:Add|Update|Delete) File:\s*(\S.*)$", response_text
    )
    returned_paths = [path for pair in diff_paths for path in pair] + patch_paths
    if returned_paths:
        outside = sorted({path for path in returned_paths if not _allowed_path(path, allowed)})
        if outside:
            return [f"path_outside_allowed_files:{path}" for path in outside]
        if not diff_paths:
            return ["non_unified_patch_format"]
        if repo_root is not None:
            check = subprocess.run(
                ["git", "apply", "--check", "--whitespace=nowarn", "-"],
                cwd=repo_root,
                input=response_text,
                capture_output=True,
                text=True,
            )
            if check.returncode != 0:
                detail = (check.stderr or check.stdout).strip().splitlines()
                return ["unapplicable_unified_diff:" + (detail[0] if detail else "unknown")]
        return []
    if zip_path.is_file() and zipfile.is_zipfile(zip_path):
        with zipfile.ZipFile(zip_path) as archive:
            members = [
                member for member in archive.infolist() if not member.is_dir() and member.file_size > 0
            ]
        if not members:
            return ["empty_solution_zip"]
        outside = sorted(
            member.filename for member in members if not _allowed_path(member.filename, allowed)
        )
        return [f"path_outside_allowed_files:{path}" for path in outside]
    return ["code_deliverable_missing"]


def read_code_gate_text(bundle_path: Path) -> str:
    """Read the code gate from Markdown or a zipped execution-gate.md."""
    if bundle_path.suffix != ".zip":
        return bundle_path.read_text(encoding="utf-8")
    if not zipfile.is_zipfile(bundle_path):
        return ""
    with zipfile.ZipFile(bundle_path) as archive:
        matches = [
            member
            for member in archive.infolist()
            if not member.is_dir() and Path(member.filename).name == "execution-gate.md"
        ]
        if len(matches) != 1:
            return ""
        return archive.read(matches[0]).decode("utf-8")


def validate_explicit_tab(tab_id: str, expected_url: str, tabs: list[dict]) -> list[str]:
    """Verify an explicit human-selected tab without replacing it."""
    if not tab_id:
        return []
    if not expected_url:
        return ["explicit_tab_requires_expect_url"]
    match = next((tab for tab in tabs if str(tab.get("id", "")) == tab_id), None)
    if match is None:
        return ["explicit_tab_not_found"]
    actual_url = str(match.get("url", ""))
    if actual_url.rstrip("/") != expected_url.rstrip("/"):
        return ["explicit_tab_url_mismatch"]
    return []


def submission_target_args(tab_id: str, expected_url: str, binding: dict) -> list[str]:
    """Build Surf targeting args without replacing an explicit tab."""
    selected_tab = tab_id or str(binding.get("tab_id", ""))
    selected_url = expected_url or str(binding.get("conversation_url", ""))
    if not selected_tab:
        return ["--create-tab"]
    args = ["--tab-id", selected_tab]
    if selected_url:
        args += ["--expect-url", selected_url]
    if tab_id:
        args += ["--no-remember"]
    return args


def webgpt_download_args(
    tab_id: str, pattern: str, output_path: Path, timeout: int
) -> list[str]:
    """Build the supported Surf WebGPT download command."""
    return [
        "webgpt.download",
        "--match",
        pattern,
        "--tab-id",
        tab_id,
        "--output",
        str(output_path),
        "--timeout",
        str(timeout),
    ]


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _collect_context(command: str, error: str, stderr: str = "", binding: dict | None = None, **extra: str) -> str:
    """Collect debug context for a bug report."""
    parts = [
        f"## webgpt failure report ({_now()})",
        "",
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
    parts.append("\n---\nAuto-filed by `webgpt_cli.py`")
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


def _verify_desktop(binding: dict, background: bool, label: str = "") -> dict:
    """Verify tab identity and KDE desktop. Always called on every command.
    
    Auto-heals stale tabs: if the binding's tab is closed or points to the wrong
    URL, creates a new tab with the conversation URL and updates the binding.
    Returns the (possibly updated) binding.
    """
    tab_id = binding.get("tab_id", "")
    conv_url = binding.get("conversation_url", "")
    if not tab_id and not conv_url:
        return binding

    tag = f" [{label}]" if label else ""
    actual_desk = None
    actual_url = None

    if tab_id:
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

    # Desktop mismatch — informational only, CDP works across desktops
    target_desk = binding.get("kde_desktop_index", "")
    if target_desk and actual_desk is not None:
        human_actual = int(actual_desk) + 1
        if str(human_actual) != target_desk:
            print(f"NOTE_DESKTOP_MISMATCH: binding={target_desk} actual={human_actual}{tag}", file=sys.stderr)

    # Tab is stale (closed or wrong URL) — auto-heal by creating a new one
    needs_recreate = False
    if tab_id and actual_desk is None:
        print(f"TAB_REPLACE: {tab_id} not found{tag}", file=sys.stderr)
        needs_recreate = True
    elif conv_url and actual_url and conv_url.split("/")[-1] != actual_url.split("/")[-1]:
        print(f"TAB_REPLACE: {tab_id} has wrong conversation{tag}", file=sys.stderr)
        needs_recreate = True

    if needs_recreate and conv_url:
        # Create dedicated browser window on Desktop 2 with a single tab.
        # window.new --unfocused creates the window without stealing focus.
        cur_desk = subprocess.run(["qdbus", "org.kde.KWin", "/KWin", "currentDesktop"], capture_output=True, text=True, timeout=5).stdout.strip()
        subprocess.run(["wmctrl", "-s", "1"], capture_output=True, timeout=5)
        time.sleep(0.5)
        result = _surf("window.new", "--unfocused", conv_url)
        if cur_desk and cur_desk != "1":
            subprocess.run(["wmctrl", "-s", cur_desk], capture_output=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split()
            new_id = ""
            for i, p in enumerate(parts):
                if p == "(tab" and i + 1 < len(parts):
                    new_id = parts[i + 1].rstrip(")")
                    break
            if new_id:
                binding["tab_id"] = new_id
                binding["kde_desktop_index"] = "2"
                path = BINDING_DIR / f"{binding.get('name', 'sparta')}.json"
                if path.exists():
                    stored = json.loads(path.read_text())
                    stored.update(binding)
                    path.write_text(json.dumps(stored, indent=2) + "\n")
                print(f"TAB_REPLACED: {tab_id} -> {new_id} (new window on Desktop 2){tag}", file=sys.stderr)

    return binding


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
    """Download through Surf's tab-aware WebGPT artifact command."""
    del background
    suffix = Path(pattern).suffix or ".download"
    output_path = Path("/tmp") / f"webgpt-download-{os.getpid()}-{time.time_ns()}{suffix}"
    result = _surf(*webgpt_download_args(tab_id, pattern, output_path, timeout))
    if result.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0:
        return output_path
    return None


@app.command()
def submit(
    bundle: str | None = typer.Argument(None, help="Path to creation bundle (auto-finds latest)"),
    project: str = typer.Option("sparta", "-p"),
    timeout: int = typer.Option(900, "--timeout", "-t", help="WebGPT timeout (seconds)"),
    background: bool = typer.Option(True, "--background", help="Background: no KDE switch, no window focus"),
    execution_locked: bool = typer.Option(
        False,
        "--execution-locked",
        help="Require a shortest-path execution lock in the submitted bundle",
    ),
    output_contract: str = typer.Option(
        "code", "--output-contract", help="Required response deliverable: code or prose"
    ),
    tab_id: str = typer.Option("", "--tab-id", help="Exact human-selected WebGPT tab"),
    expect_url: str = typer.Option("", "--expect-url", help="Exact URL required for --tab-id"),
):
    """Submit a bundle, capture response, download solution zip. All complexity hidden."""
    bp = Path(bundle) if bundle else _latest_bundle()
    if not bp or not bp.exists():
        typer.echo("Bundle not found", err=True)
        raise typer.Exit(1)
    if execution_locked:
        missing = validate_execution_lock(bp.read_text(encoding="utf-8"))
        if missing:
            typer.echo(
                "Execution lock missing headings: " + ", ".join(missing), err=True
            )
            raise typer.Exit(2)

    if output_contract not in {"code", "prose"}:
        typer.echo("output contract must be code or prose", err=True)
        raise typer.Exit(2)
    bundle_text = read_code_gate_text(bp)
    if output_contract == "code":
        gate_errors = validate_code_gate(bundle_text)
        if gate_errors:
            typer.echo("BLOCKED_WEBGPT_CODE_GATE_INVALID: " + ", ".join(gate_errors), err=True)
            raise typer.Exit(2)

    b = _binding(project)
    if tab_id:
        tab_result = _surf("tab.list", "--json", "--with-kde")
        try:
            tab_payload = json.loads(tab_result.stdout) if tab_result.returncode == 0 else {}
            tabs = tab_payload.get("tabs", []) if isinstance(tab_payload, dict) else tab_payload
        except json.JSONDecodeError:
            tabs = []
        tab_errors = validate_explicit_tab(tab_id, expect_url, tabs if isinstance(tabs, list) else [])
        if tab_errors:
            typer.echo("BLOCKED_WEBGPT_EXPLICIT_TAB_INVALID: " + ", ".join(tab_errors), err=True)
            raise typer.Exit(2)
    else:
        b = _verify_desktop(b, background, "submit")

    resp_path = bp.with_name(f"{bp.stem}-response.md")
    zip_path = bp.with_name(f"{bp.stem}-solution.zip")

    typer.echo(f"Submitting {bp.name}...", err=True)
    cmd: list[str | int] = [
        "webgpt.submit", "--input", str(bp), "--output", str(resp_path),
        "--timeout", str(timeout),
    ]
    selected_tab = tab_id or str(b.get("tab_id", ""))
    cmd += submission_target_args(tab_id, expect_url, b)
    if background:
        cmd += ["--no-activate"]
    if bp.suffix == ".zip":
        cmd += ["--attach-file", str(bp)]
    result = _surf(*cmd)

    if result.returncode != 0:
        _report_failure("submit", result, binding=b, bundle=str(bp), timeout=str(timeout))
        typer.echo("Submit failed", err=True)
        raise typer.Exit(result.returncode)
    typer.echo(f"Response: {resp_path}")

    response_text = resp_path.read_text(encoding="utf-8") if resp_path.exists() else ""
    repo_root = Path(__file__).resolve().parents[3]
    if output_contract == "code" and not code_deliverable_errors(
        response_text, zip_path, bundle_text, repo_root
    ):
        typer.echo("PASS_CURRENT_GATE")
        return

    # Try to download solution zip from the new tab
    typer.echo("Looking for solution zip...", err=True)
    time.sleep(3)
    new_tab = selected_tab or _active_chatgpt_tab()
    if new_tab:
        found = _click_and_wait_download(new_tab, ".zip", timeout=120, background=background)
        if found:
            shutil.copy2(str(found), str(zip_path))
            typer.echo(f"Solution: {zip_path}")
    if output_contract == "code":
        errors = code_deliverable_errors(response_text, zip_path, bundle_text, repo_root)
        if errors:
            ruling = (
                "REJECTED_SCOPE_EXPANSION"
                if any(error.startswith("path_outside_allowed_files:") for error in errors)
                else "BLOCKED_WEBGPT_CODE_DELIVERABLE_MISSING"
            )
            typer.echo(ruling + ": " + ", ".join(errors), err=True)
            raise typer.Exit(3)
        typer.echo("PASS_CURRENT_GATE")
        return
    if not zip_path.exists():
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
def refresh(
    project: str = typer.Option("sparta", "-p"),
    background: bool = typer.Option(True, "--background"),
):
    """Refresh the project's WebGPT tab."""
    b = _binding(project)
    _verify_desktop(b, background, "refresh")
    tab_id = b.get("tab_id", "")
    if tab_id:
        _surf("tab.reload", *(["--no-activate"] if background else []), "--tab-id", tab_id)
        typer.echo(f"Tab {tab_id} refreshed")


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
