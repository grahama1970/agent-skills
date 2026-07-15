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
SURF = Path(os.path.expandvars("${HOME}/workspace/experiments/agent-skills/skills/surf/run.sh"))


GITHUB_REPO = "agent-skills"
GITHUB_ORG = "grahama1970"


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


def _exact_submission_target(
    binding: dict,
    tab_id_override: str = "",
    expected_url_override: str = "",
) -> tuple[str, str]:
    """Return the bound tab and URL or fail closed before browser mutation."""
    tab_id = tab_id_override.strip() or str(binding.get("tab_id", "")).strip()
    conversation_url = (
        expected_url_override.strip()
        or str(binding.get("conversation_url", "")).strip()
    )
    if not tab_id or not conversation_url:
        raise ValueError("exact tab_id and conversation_url are required for submit")
    return tab_id, conversation_url


def _routing_meta_is_exact(meta: dict, tab_id: str) -> bool:
    requested = str(meta.get("requested_tab_id", ""))
    controlled = str(meta.get("controlled_tab_id", ""))
    return (
        requested == tab_id
        and controlled == tab_id
        and meta.get("controlled_tab_id_mismatch") is False
        and meta.get("tab_was_created") is False
    )


def _has_code_deliverable(response_path: Path, solution_path: Path) -> bool:
    """A code request must yield a patch or a non-empty finished-file zip."""
    if solution_path.exists() and solution_path.stat().st_size > 0:
        return True
    if not response_path.exists():
        return False
    response = response_path.read_text(errors="replace")
    return (
        "diff --git " in response
        or "*** Begin Patch" in response
        or ("--- a/" in response and "+++ b/" in response)
    )


WEBGPT_MODES = {"assess", "plan", "code", "all", "none"}

_RESEARCH_CLAUSE = """## Research directive
Before answering, use your own web search to research current, authoritative
sources for this problem, and cite the source URLs you relied on. The bundle may
also include a "## Research context" section the project agent gathered via
brave-search; treat it as a starting point, not a limit."""

_MODE_CONTRACTS = {
    "assess": """## Output contract: ASSESS
Diagnose where the project agent is blocked or spiraling. Do NOT write code.
Return, in order:
- DIAGNOSIS: <root cause of the block or spiral>
- EVIDENCE: <what in the bundle/research supports it>
- CURRENT_GATE: <the one gate that must be closed next>
- NEXT_STEP: <single concrete action>
End with exactly one ruling line:
PASS_CURRENT_GATE | BLOCKED_CURRENT_GATE: <one concrete blocker> | REJECTED_SCOPE_EXPANSION""",
    "plan": """## Output contract: PLAN
Produce a bounded architectural task plan for the named current gate only.
Do NOT write code. Return:
- TASK_PLAN: numbered steps; each names allowed files/module boundary and required live proof
- FORBIDDEN_ADJACENT_SCOPE: <what must not be touched>
Stay within the current gate; do not expand scope.""",
    "code": """## Output contract: CODE
Return a unified diff (diff --git / *** Begin Patch) or a single finished-file zip.
Scope: the one current gate and allowed files only. A roadmap, staged architecture,
status analysis, or prose-only plan does NOT satisfy this contract.""",
    "none": "",
}


_GOAL_LOCK_TOP = """## GOAL LOCK - read first, obey throughout
Work on ONLY the single current gate / goal stated in this request. You are
FORBIDDEN from drifting into easier, adjacent, or tangential work - no unrelated
refactors, renames, new tooling, extra features, unrequested tests, or broader
architecture - none of which close the stated gate. If the stated gate is
unclear, out of scope, or blocked, say so and stop; do NOT substitute a
different, easier problem to look productive."""

_GOAL_LOCK_BOTTOM = """## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem."""


def _augment_bundle(bp: Path, mode: str) -> Path:
    """Wrap a text bundle with a goal lock (top + bottom), the research directive,
    and the mode output-contract.

    The goal lock is placed both first and last (LLMs weight the start and end of
    a prompt most) so WebGPT stays on the one stated gate and cannot devolve into
    easy, off-goal side quests. Zip bundles are attached as-is and cannot be
    augmented.
    """
    if bp.suffix == ".zip":
        return bp
    original = bp.read_text(errors="replace")
    contract = _MODE_CONTRACTS.get(mode, "")
    lock = mode != "none"
    top_blocks = [
        blk for blk in (_GOAL_LOCK_TOP if lock else "", _RESEARCH_CLAUSE, contract) if blk
    ]
    header = "\n\n".join(top_blocks) + "\n\n---\n\n"
    footer = ("\n\n---\n\n" + _GOAL_LOCK_BOTTOM) if lock else ""
    aug = bp.with_name(f"{bp.stem}.submitted-{mode}.md")
    aug.write_text(header + original + footer)
    return aug


def _has_assess_deliverable(response_path: Path) -> bool:
    """An assess request must return a diagnosis and a gate ruling."""
    if not response_path.exists():
        return False
    text = response_path.read_text(errors="replace")
    has_diagnosis = "DIAGNOSIS" in text
    has_ruling = any(
        token in text
        for token in ("PASS_CURRENT_GATE", "BLOCKED_CURRENT_GATE", "REJECTED_SCOPE_EXPANSION")
    )
    return has_diagnosis and has_ruling


def _has_plan_deliverable(response_path: Path) -> bool:
    """A plan request must return a bounded task plan."""
    if not response_path.exists():
        return False
    return "TASK_PLAN" in response_path.read_text(errors="replace")


def _deliverable_ok(mode: str, response_path: Path, solution_path: Path) -> bool:
    if mode == "code":
        return _has_code_deliverable(response_path, solution_path)
    if mode == "assess":
        return _has_assess_deliverable(response_path)
    if mode == "plan":
        return _has_plan_deliverable(response_path)
    return True


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
    output_contract: str = typer.Option("code", "--output-contract", help="Required response: assess, plan, code, all, or none"),
    architecture_authorized: bool = typer.Option(
        False,
        "--architecture-authorized",
        help="Human authorization required for plan or all",
    ),
    tab_id_override: str = typer.Option("", "--tab-id", help="Exact human-supplied tab id"),
    expected_url_override: str = typer.Option(
        "", "--expect-url", help="Exact expected ChatGPT conversation URL"
    ),
):
    """Submit a bundle, capture response, enforce the output contract. All complexity hidden.

    Single modes run one bounded submission. Human-authorized ``all`` composes
    assess, plan, and code; longer iteration remains a Tau DAG responsibility.
    """
    bp = Path(bundle) if bundle else _latest_bundle()
    if not bp or not bp.exists():
        typer.echo("Bundle not found", err=True)
        raise typer.Exit(1)

    if output_contract not in WEBGPT_MODES:
        typer.echo("--output-contract must be one of: assess, plan, code, all, none", err=True)
        raise typer.Exit(2)

    b = _binding(project)
    try:
        tab_id, conversation_url = _exact_submission_target(
            b, tab_id_override, expected_url_override
        )
    except ValueError as exc:
        typer.echo(f"BLOCKED_WEBGPT_EXACT_TAB_REQUIRED: {exc}", err=True)
        raise typer.Exit(2)

    if output_contract in {"plan", "all"} and not architecture_authorized:
        typer.echo(
            "REJECTED_SCOPE_EXPANSION: plan/all requires --architecture-authorized",
            err=True,
        )
        raise typer.Exit(2)

    modes = ("assess", "plan", "code") if output_contract == "all" else (output_contract,)
    for mode in modes:
        ok, _resp = _submit_stage(bp, mode, tab_id, conversation_url, b, timeout)
        if not ok:
            _raise_deliverable_missing(mode, bp, b)


def _raise_deliverable_missing(mode: str, bp: Path, binding: dict) -> None:
    """Report a missing stage deliverable and stop the composed run."""
    if mode == "code":
        failure = subprocess.CompletedProcess(
            args=[],
            returncode=4,
            stdout="",
            stderr="WebGPT returned no unified diff and no finished-file zip",
        )
        _report_failure(
            "submit-output-contract", failure, binding=binding, bundle=str(bp)
        )
    typer.echo(f"BLOCKED_WEBGPT_{mode.upper()}_DELIVERABLE_MISSING", err=True)
    raise typer.Exit(4)


def _submit_stage(
    bp: Path,
    mode: str,
    tab_id: str,
    conversation_url: str,
    b: dict,
    timeout: int,
) -> tuple[bool, Path]:
    """Run one WebGPT submission for `mode`.

    Hard-fails closed (typer.Exit) on preflight or routing-proof errors. Returns
    (deliverable_satisfied, response_path).
    """
    aug = _augment_bundle(bp, mode)
    preflight = _surf(
        "webgpt.preflight",
        "--tab-id", tab_id,
        "--expect-url", conversation_url,
        "--no-activate",
        "--json",
    )
    if preflight.returncode != 0:
        _report_failure("submit-preflight", preflight, binding=b, bundle=str(bp))
        typer.echo("BLOCKED_WEBGPT_TAB_IDENTITY_PREFLIGHT", err=True)
        raise typer.Exit(preflight.returncode)

    tag = "" if mode in {"code", "none"} else f"-{mode}"
    resp_path = bp.with_name(f"{bp.stem}{tag}-response.md")
    zip_path = bp.with_name(f"{bp.stem}{tag}-solution.zip")
    raw_path = bp.with_name(f"{bp.stem}{tag}-response.raw.md")
    meta_path = bp.with_name(f"{bp.stem}{tag}-response.meta.json")
    receipt_path = bp.with_name(f"{bp.stem}{tag}-response.receipt.json")

    typer.echo(f"Submitting {bp.name} [{mode}]...", err=True)
    cmd: list[str | int] = [
        "webgpt.submit",
        "--input", str(aug),
        "--output", str(resp_path),
        "--raw-output", str(raw_path),
        "--meta-output", str(meta_path),
        "--receipt-output", str(receipt_path),
        "--timeout", str(timeout),
        "--tab-id", tab_id,
        "--expect-url", conversation_url,
        "--no-activate",
        "--no-remember",
    ]
    if bp.suffix == ".zip":
        cmd += ["--attach-file", str(bp)]
    result = _surf(*cmd)

    if result.returncode != 0:
        _report_failure("submit", result, binding=b, bundle=str(bp), timeout=str(timeout))
        typer.echo("Submit failed", err=True)
        raise typer.Exit(result.returncode)

    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        typer.echo(f"BLOCKED_WEBGPT_ROUTING_PROOF_MISSING: {exc}", err=True)
        raise typer.Exit(3)
    if not _routing_meta_is_exact(meta, tab_id):
        typer.echo("BLOCKED_WEBGPT_ROUTING_PROOF_MISMATCH", err=True)
        raise typer.Exit(3)
    typer.echo(f"Response: {resp_path}")

    if mode == "code" and not _has_code_deliverable(resp_path, zip_path):
        typer.echo("Looking for solution zip...", err=True)
        time.sleep(3)
        found = _click_and_wait_download(tab_id, ".zip", timeout=120, background=True)
        if found:
            shutil.copy2(str(found), str(zip_path))
            typer.echo(f"Solution: {zip_path}")

    return _deliverable_ok(mode, resp_path, zip_path), resp_path


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
    tab_id_override: str = typer.Option("", "--tab-id", help="Exact human-supplied tab id"),
    expected_url_override: str = typer.Option(
        "", "--expect-url", help="Exact expected ChatGPT conversation URL"
    ),
):
    """Activate the project tab: KDE switch, close duplicates, release CDP, clear drafts."""
    b = _binding(project)
    try:
        tab_id, conversation_url = _exact_submission_target(
            b, tab_id_override, expected_url_override
        )
    except ValueError as exc:
        typer.echo(f"BLOCKED_WEBGPT_EXACT_TAB_REQUIRED: {exc}", err=True)
        raise typer.Exit(2)
    preflight = _surf(
        "webgpt.preflight",
        "--tab-id", tab_id,
        "--expect-url", conversation_url,
        "--no-activate",
        "--json",
    )
    if preflight.returncode != 0:
        typer.echo("BLOCKED_WEBGPT_TAB_IDENTITY_PREFLIGHT", err=True)
        raise typer.Exit(preflight.returncode)
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
