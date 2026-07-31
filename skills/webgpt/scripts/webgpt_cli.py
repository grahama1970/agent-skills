#!/usr/bin/env python3
"""Browser commands for WebGPT. Agent runs one-liners — background by default so it never hijacks the user."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import typer

app = typer.Typer()
BINDING_DIR = Path.home() / ".pi" / "webgpt-projects"
SURF = Path(
    os.path.expandvars(
        os.environ.get("SURF_RUN_SH", "${HOME}/workspace/experiments/agent-skills/skills/surf/run.sh")
    )
).expanduser()
BROWSER_ORACLE = Path(__file__).resolve().parents[2] / "browser-oracle" / "run.sh"
DEFAULT_WEBGPT_TIMEOUT_SECONDS = 2400

EXECUTION_LOCK_HEADINGS = (
    "current phase",
    "critical path",
    "deferred work",
    "failure policy",
    "stop condition",
)
EXECUTION_LOCK_DIRECTIVES = (
    "max_identical_failures_per_family: 3",
    "systemic_failure_action: stop_family_mark_remaining_blocked_continue_independent_families",
    "reviewer_scope_authority: none",
)

CODE_GATE_FIELDS = (
    "current_gate",
    "blocking_defect",
    "allowed_files",
    "required_live_proof",
    "stop_condition",
    "forbidden_adjacent_scope",
)


GITHUB_REPO = "agent-skills"
GITHUB_ORG = "grahama1970"
DEFAULT_ISSUE_COOLDOWN_SECONDS = 3600


def validate_execution_lock(text: str) -> list[str]:
    lowered = text.lower()
    missing = [
        heading
        for heading in EXECUTION_LOCK_HEADINGS
        if f"## {heading}" not in lowered
    ]
    missing.extend(
        directive for directive in EXECUTION_LOCK_DIRECTIVES if directive not in text
    )
    return missing


def validate_code_gate(text: str) -> list[str]:
    counts = {field: 0 for field in CODE_GATE_FIELDS}
    for raw_line in text.splitlines():
        key, sep, _value = raw_line.partition(":")
        if sep and key.strip() in counts:
            counts[key.strip()] += 1
    errors = [f"duplicate_{field}" for field, count in counts.items() if count > 1]
    errors.extend(f"missing_{field}" for field, count in counts.items() if count == 0)
    return errors


def _allowed_code_gate_files(gate_text: str) -> set[str]:
    for raw_line in gate_text.splitlines():
        key, sep, value = raw_line.partition(":")
        if sep and key.strip() == "allowed_files":
            return {
                part.strip()
                for part in re.split(r"[, ]+", value.strip())
                if part.strip()
            }
    return set()


def read_code_gate_text(path: Path) -> str:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            try:
                return archive.read("execution-gate.md").decode("utf-8")
            except KeyError as exc:
                raise ValueError("execution-gate.md missing from zip bundle") from exc
    return path.read_text(errors="replace")


def _diff_paths(response_text: str) -> list[str]:
    paths: list[str] = []
    for match in re.finditer(r"^diff --git a/(.*?) b/(.*?)$", response_text, re.MULTILINE):
        paths.append(match.group(2))
    return paths


def code_deliverable_errors(
    response_text: str,
    solution_zip: Path,
    gate_text: str,
    repo: Path | None = None,
) -> list[str]:
    if solution_zip.exists() and solution_zip.stat().st_size > 0:
        return []
    has_diff = (
        "diff --git " in response_text
        or "*** Begin Patch" in response_text
        or ("--- a/" in response_text and "+++ b/" in response_text)
    )
    if not has_diff:
        return ["code_deliverable_missing"]

    allowed = _allowed_code_gate_files(gate_text)
    for path in _diff_paths(response_text):
        if allowed and path not in allowed:
            return [f"path_outside_allowed_files:{path}"]

    if repo is not None and "diff --git " in response_text:
        check = subprocess.run(
            ["git", "apply", "--check", "-"],
            input=response_text,
            cwd=repo,
            text=True,
            capture_output=True,
        )
        if check.returncode != 0:
            detail = (check.stderr or check.stdout or "git apply --check failed").strip()
            return [f"unapplicable_unified_diff:{detail}"]
    return []


def validate_explicit_tab(tab_id: str, expect_url: str, tabs: list[dict]) -> list[str]:
    if not expect_url:
        return ["explicit_tab_requires_expect_url"]
    matches = [tab for tab in tabs if str(tab.get("id", "")) == str(tab_id)]
    if len(matches) != 1:
        return ["explicit_tab_missing"]
    if not _same_url(str(matches[0].get("url", "")), expect_url):
        return ["explicit_tab_url_mismatch"]
    return []


def submission_target_args(tab_id: str, expect_url: str, _binding: dict) -> list[str]:
    return ["--tab-id", tab_id, "--expect-url", expect_url, "--no-remember"]


def webgpt_download_args(tab_id: str, match: str, output: Path, timeout: int) -> list[str]:
    return [
        "webgpt.download",
        "--match",
        match,
        "--tab-id",
        tab_id,
        "--output",
        str(output),
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
    if not _auto_file_issues_enabled():
        print("  [issue suppressed] WEBGPT_AUTO_FILE_ISSUES disabled", file=sys.stderr)
        return False
    recent = _recent_issue_marker(title)
    if recent:
        print(f"  [issue suppressed] recent duplicate: {recent}", file=sys.stderr)
        return False
    existing = _find_existing_open_issue(title)
    if existing:
        _write_issue_marker(title, existing)
        print(f"  [issue suppressed] open duplicate: {existing}", file=sys.stderr)
        return False
    try:
        result = subprocess.run(
            ["gh", "issue", "create", "--repo", f"{GITHUB_ORG}/{GITHUB_REPO}", "--title", title, "--body", body, "--label", "bug", "--label", "webgpt"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            _write_issue_marker(title, url)
            print(f"  [filed] {url}", file=sys.stderr)
            return True
        else:
            print(f"  [issue failed] {result.stderr[:500]}", file=sys.stderr)
            return False
    except Exception as exc:
        print(f"  [issue exception] {exc}", file=sys.stderr)
        return False


def _auto_file_issues_enabled() -> bool:
    value = os.environ.get("WEBGPT_AUTO_FILE_ISSUES", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _issue_state_dir() -> Path:
    override = os.environ.get("WEBGPT_ISSUE_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".cache" / "webgpt" / "issue-autofile"


def _issue_cooldown_seconds() -> int:
    raw = os.environ.get("WEBGPT_ISSUE_COOLDOWN_SECONDS", str(DEFAULT_ISSUE_COOLDOWN_SECONDS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_ISSUE_COOLDOWN_SECONDS
    return max(0, value)


def _issue_marker_path(title: str) -> Path:
    key = hashlib.sha256(title.encode("utf-8", errors="replace")).hexdigest()
    return _issue_state_dir() / f"{key}.json"


def _recent_issue_marker(title: str) -> str | None:
    cooldown = _issue_cooldown_seconds()
    if cooldown <= 0:
        return None
    path = _issue_marker_path(title)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        marked_at = float(payload.get("marked_at_epoch") or 0)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if path.exists():
            print(f"  [issue marker unreadable] {path}: {exc}", file=sys.stderr)
        return None
    if time.time() - marked_at <= cooldown:
        return str(payload.get("url") or payload.get("title") or "duplicate")
    return None


def _write_issue_marker(title: str, url: str) -> None:
    path = _issue_marker_path(title)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema": "webgpt.issue_autofile_marker.v1",
                    "title": title,
                    "url": url,
                    "marked_at": _now(),
                    "marked_at_epoch": time.time(),
                    "cooldown_seconds": _issue_cooldown_seconds(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"  [issue marker failed] {exc}", file=sys.stderr)


def _find_existing_open_issue(title: str) -> str | None:
    query = f'is:issue is:open in:title "{title}"'
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                f"{GITHUB_ORG}/{GITHUB_REPO}",
                "--state",
                "open",
                "--search",
                query,
                "--json",
                "number,title,url",
                "--limit",
                "20",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:
        print(f"  [issue duplicate lookup exception] {exc}", file=sys.stderr)
        return None
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if detail:
            print(f"  [issue duplicate lookup failed] {detail[:500]}", file=sys.stderr)
        return None
    try:
        issues = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        print(f"  [issue duplicate lookup invalid json] {exc}", file=sys.stderr)
        return None
    if not isinstance(issues, list):
        return None
    for issue in issues:
        if isinstance(issue, dict) and str(issue.get("title") or "") == title:
            return str(issue.get("url") or "")
    return None


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


class SourceProvenanceError(RuntimeError):
    """A repository-backed WebGPT request is not reproducible from its upstream."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


class TargetResolutionError(RuntimeError):
    """The exact tab cannot be mapped to one supported, Oracle-bound provider."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


def _git(repo: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _cloneable_remote_url(url: str) -> str:
    """Return a credential-free network clone URL suitable for an external reviewer."""
    value = url.strip()
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value) and not value.startswith(
        ("http://", "https://", "ssh://")
    ):
        raise SourceProvenanceError(
            "SOURCE_REMOTE_UNAVAILABLE", "local or unsupported upstream URL scheme"
        )
    scp_match = re.fullmatch(r"(?:[^@/]+@)?([^:/]+):(.+)", value)
    if scp_match and not value.startswith(("http://", "https://", "ssh://")):
        return f"https://{scp_match.group(1)}/{scp_match.group(2)}"
    if value.startswith("ssh://"):
        parsed = urlsplit(value)
        if not parsed.hostname or not parsed.path:
            raise SourceProvenanceError("SOURCE_REMOTE_UNAVAILABLE", "invalid SSH upstream URL")
        return f"https://{parsed.hostname}{parsed.path}"
    if value.startswith(("http://", "https://")):
        parsed = urlsplit(value)
        if not parsed.hostname:
            raise SourceProvenanceError("SOURCE_REMOTE_UNAVAILABLE", "invalid HTTP upstream URL")
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    raise SourceProvenanceError(
        "SOURCE_REMOTE_UNAVAILABLE",
        "upstream must use an HTTP(S) or SSH network URL; local paths are not reviewable",
    )


def _source_provenance(repo_root: str, source_paths: list[str]) -> dict:
    """Prove declared paths are clean at a commit reachable from the live upstream."""
    if not source_paths:
        raise SourceProvenanceError(
            "SOURCE_PATH_REQUIRED", "at least one --source-path is required"
        )

    requested_root = Path(repo_root).expanduser().resolve()
    root_result = _git(requested_root, "rev-parse", "--show-toplevel")
    if root_result.returncode != 0:
        raise SourceProvenanceError("SOURCE_REPO_REQUIRED", "--repo-root is not in a Git repository")
    root = Path(root_result.stdout.strip()).resolve()

    normalized: list[str] = []
    for raw in source_paths:
        value = raw.strip()
        candidate = Path(value)
        if not value:
            raise SourceProvenanceError("SOURCE_PATH_REQUIRED", "--source-path cannot be empty")
        if candidate.is_absolute():
            raise SourceProvenanceError(
                "SOURCE_PATH_ABSOLUTE", f"source path must be repository-relative: {value}"
            )
        if ".." in candidate.parts:
            raise SourceProvenanceError(
                "SOURCE_PATH_OUTSIDE_REPO", f"source path escapes repository: {value}"
            )
        canonical = candidate.as_posix().removeprefix("./")
        if canonical in {"", "."}:
            raise SourceProvenanceError("SOURCE_PATH_REQUIRED", "source path must name a file or directory")
        tracked = _git(root, "cat-file", "-e", f"HEAD:{canonical}")
        if tracked.returncode != 0:
            raise SourceProvenanceError(
                "SOURCE_PATH_NOT_COMMITTED", f"source path is not present in HEAD: {canonical}"
            )
        dirty = _git(
            root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            canonical,
        )
        if dirty.returncode != 0 or dirty.stdout.strip():
            raise SourceProvenanceError(
                "SOURCE_PATH_UNCOMMITTED", f"source path has uncommitted changes: {canonical}"
            )
        normalized.append(canonical)

    branch_result = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch_result.returncode != 0:
        raise SourceProvenanceError("SOURCE_UPSTREAM_MISSING", "detached HEAD has no configured upstream")
    branch = branch_result.stdout.strip()
    upstream_result = _git(
        root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    if upstream_result.returncode != 0:
        raise SourceProvenanceError(
            "SOURCE_UPSTREAM_MISSING", f"branch {branch!r} has no configured upstream"
        )
    upstream = upstream_result.stdout.strip()
    remote = _git(root, "config", "--get", f"branch.{branch}.remote").stdout.strip()
    merge_ref = _git(root, "config", "--get", f"branch.{branch}.merge").stdout.strip()
    if not remote or not merge_ref or remote == ".":
        raise SourceProvenanceError(
            "SOURCE_UPSTREAM_MISSING", f"branch {branch!r} has no network upstream"
        )

    remote_url_result = _git(root, "config", "--get", f"remote.{remote}.url")
    if remote_url_result.returncode != 0:
        raise SourceProvenanceError("SOURCE_REMOTE_UNAVAILABLE", f"cannot resolve remote {remote!r}")
    clone_url = _cloneable_remote_url(remote_url_result.stdout)

    try:
        fetch_result = _git(
            root, "fetch", "--quiet", "--no-tags", remote, merge_ref, timeout=120
        )
    except subprocess.TimeoutExpired as exc:
        raise SourceProvenanceError(
            "SOURCE_REMOTE_UNAVAILABLE", f"upstream fetch timed out after {exc.timeout}s"
        ) from exc
    if fetch_result.returncode != 0:
        detail = fetch_result.stderr.strip() or f"failed to fetch {remote}/{merge_ref}"
        raise SourceProvenanceError("SOURCE_REMOTE_UNAVAILABLE", detail)
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    pushed = _git(root, "merge-base", "--is-ancestor", head, "FETCH_HEAD")
    if pushed.returncode != 0:
        raise SourceProvenanceError(
            "SOURCE_COMMIT_UNPUSHED", f"HEAD {head} is not reachable from {upstream}"
        )

    try:
        proof_cwd = Path.cwd().resolve().relative_to(root).as_posix() or "."
    except ValueError:
        proof_cwd = "."
    return {
        "schema": "webgpt.source_provenance.v1",
        "repository_url": clone_url,
        "branch": branch,
        "upstream": upstream,
        "commit_sha": head,
        "source_paths": normalized,
        "proof_cwd": proof_cwd,
    }


def _source_provenance_block(provenance: dict) -> str:
    url = provenance["repository_url"]
    sha = provenance["commit_sha"]
    return (
        "## Authoritative source provenance\n"
        "Use the pushed repository state below as the only source of truth. Clone it and "
        "check out the exact detached commit before inspecting the declared paths.\n\n"
        "```bash\n"
        f"git clone --filter=blob:none {shlex.quote(url)} webgpt-source\n"
        f"git -C webgpt-source checkout --detach {sha}\n"
        "```\n\n"
        "```json\n"
        f"{json.dumps(provenance, indent=2)}\n"
        "```"
    )


def _run_browser_oracle(*args: str) -> subprocess.CompletedProcess:
    if not BROWSER_ORACLE.exists():
        raise TargetResolutionError("BROWSER_ORACLE_UNAVAILABLE", "runtime missing")
    try:
        return subprocess.run(
            [str(BROWSER_ORACLE), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TargetResolutionError("BROWSER_ORACLE_UNAVAILABLE", str(exc)) from exc


def _browser_oracle_doctor(project: str, from_path: str, backend: str) -> dict:
    """Require Browser Oracle readiness before any Surf/browser operation."""
    result = _run_browser_oracle(
        "doctor",
        "--from",
        str(Path(from_path).expanduser().resolve()),
        "--backend",
        backend,
        "--project",
        project,
        "--json",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TargetResolutionError("BROWSER_ORACLE_PROOF_MISSING", str(exc)) from exc
    if result.returncode != 0 or payload.get("readiness") != "ready":
        issues = ",".join(payload.get("issues", [])) or result.stderr.strip() or "not_ready"
        raise TargetResolutionError("BROWSER_ORACLE_NOT_READY", issues)
    if str(payload.get("project", "")) != project:
        raise TargetResolutionError(
            "BROWSER_ORACLE_IDENTITY_MISMATCH", "project mismatch"
        )
    if not payload.get("tab_id") or not payload.get("conversation_url"):
        raise TargetResolutionError(
            "BROWSER_ORACLE_IDENTITY_MISMATCH", "tab id or URL missing"
        )
    return payload


def _provider_for_url(url: str) -> tuple[str, str]:
    """Map an authoritative tab URL to (Browser Oracle backend, Surf transport)."""
    host = (urlsplit(url).hostname or "").lower()
    if host == "chatgpt.com" or host.endswith(".chatgpt.com"):
        return "webgpt", "webgpt"
    if host == "kimi.com" or host.endswith(".kimi.com"):
        return "webkimi", "kimi"
    raise TargetResolutionError(
        "PROVIDER_UNSUPPORTED", f"no WebGPT transport is registered for host {host or '<missing>'}"
    )


def _same_url(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def _tab_identity(tab_id: str) -> dict:
    """Resolve one exact Chrome tab without selecting or activating another tab."""
    result = _surf("tab.list", "--json")
    if result.returncode != 0:
        raise TargetResolutionError(
            "TAB_INVENTORY_UNAVAILABLE", result.stderr.strip() or "surf tab.list failed"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TargetResolutionError("TAB_INVENTORY_INVALID", str(exc)) from exc
    tabs = payload.get("tabs", []) if isinstance(payload, dict) else payload
    matches = [tab for tab in tabs if str(tab.get("id", "")) == tab_id]
    if len(matches) != 1:
        raise TargetResolutionError(
            "TAB_IDENTITY_MISSING", f"expected one open tab {tab_id}, found {len(matches)}"
        )
    url = str(matches[0].get("url", "")).strip()
    if not url:
        raise TargetResolutionError("TAB_IDENTITY_MISSING", f"tab {tab_id} has no URL")
    return matches[0]


def _browser_oracle_binding_for_tab(backend: str, tab_id: str, url: str) -> dict:
    """Find the ready Browser Oracle binding that owns an explicit tab identity."""
    result = _run_browser_oracle("list", "--backend", backend, "--verify", "--json")
    if result.returncode != 0:
        raise TargetResolutionError(
            "BROWSER_ORACLE_NOT_READY", result.stderr.strip() or f"{backend} list failed"
        )
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TargetResolutionError("BROWSER_ORACLE_PROOF_MISSING", str(exc)) from exc
    matches = [row for row in rows if str(row.get("tab_id", "")) == tab_id]
    if len(matches) != 1:
        raise TargetResolutionError(
            "BROWSER_ORACLE_NOT_READY",
            f"expected one {backend} binding for tab {tab_id}, found {len(matches)}",
        )
    binding = matches[0]
    if binding.get("tab_open") is not True:
        raise TargetResolutionError(
            "BROWSER_ORACLE_NOT_READY", f"{backend} binding for tab {tab_id} is not open"
        )
    if not _same_url(str(binding.get("conversation_url", "")), url):
        raise TargetResolutionError(
            "BROWSER_ORACLE_IDENTITY_MISMATCH", "bound URL does not match the live tab URL"
        )
    return binding


def _resolve_submission_target(
    project: str,
    from_path: str,
    tab_id_override: str,
    expected_url_override: str,
) -> tuple[dict, str, str, str]:
    """Resolve (binding, provider transport, tab id, URL) fail-closed."""
    explicit_tab = tab_id_override.strip()
    if explicit_tab:
        if not explicit_tab.isdigit():
            raise TargetResolutionError("TAB_IDENTITY_INVALID", "--tab-id must be numeric")
        tab = _tab_identity(explicit_tab)
        live_url = str(tab["url"]).strip()
        if expected_url_override and not _same_url(expected_url_override.strip(), live_url):
            raise TargetResolutionError(
                "TAB_IDENTITY_MISMATCH", "--expect-url does not match the live tab URL"
            )
        backend, transport = _provider_for_url(live_url)
        binding = _browser_oracle_binding_for_tab(backend, explicit_tab, live_url)
        return binding, transport, explicit_tab, live_url

    binding = _browser_oracle_doctor(project, from_path, "webgpt")
    tab_id, url = _exact_submission_target(binding, "", expected_url_override)
    _backend, transport = _provider_for_url(url)
    return binding, transport, tab_id, url


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
    if not response_path.exists():
        return solution_path.exists() and solution_path.stat().st_size > 0
    return not code_deliverable_errors(response_path.read_text(errors="replace"), solution_path, "")


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


def _augment_bundle(bp: Path, mode: str, provenance: dict | None = None) -> Path:
    """Wrap a text bundle with a goal lock (top + bottom), the research directive,
    and the mode output-contract.

    The goal lock is placed both first and last (LLMs weight the start and end of
    a prompt most) so WebGPT stays on the one stated gate and cannot devolve into
    easy, off-goal side quests. Zip bundles are attached as-is while a generated
    text prompt carries the contract and source provenance.
    """
    original = (
        f"The request bundle is attached as `{bp.name}`.\n"
        if bp.suffix == ".zip"
        else bp.read_text(errors="replace")
    )
    contract = _MODE_CONTRACTS.get(mode, "")
    lock = mode != "none"
    top_blocks = [
        blk
        for blk in (
            _GOAL_LOCK_TOP if lock else "",
            _source_provenance_block(provenance) if provenance else "",
            _RESEARCH_CLAUSE,
            contract,
        )
        if blk
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
    """Download a generated artifact through Surf's tab-aware WebGPT helper."""
    suffix = pattern if pattern.startswith(".") and "/" not in pattern else ""
    fd, tmp_name = tempfile.mkstemp(prefix="webgpt-download-", suffix=suffix)
    os.close(fd)
    output = Path(tmp_name)
    output.unlink(missing_ok=True)
    result = _surf(*webgpt_download_args(tab_id, pattern, output, timeout))
    if result.returncode == 0 and output.exists() and output.stat().st_size > 0:
        return output
    manual = (
        f"Manual resume: {SURF} webgpt.download --match {shlex.quote(pattern)} "
        f"--tab-id {shlex.quote(str(tab_id))} --output /tmp/webgpt-download{suffix or '.artifact'} "
        f"--timeout {timeout}"
    )
    detail = (result.stderr or result.stdout or "").strip()
    if detail:
        typer.echo(detail, err=True)
    typer.echo(manual, err=True)
    return None


@app.command()
def submit(
    bundle: str | None = typer.Argument(None, help="Path to creation bundle (auto-finds latest)"),
    project: str = typer.Option("sparta", "-p"),
    timeout: int = typer.Option(DEFAULT_WEBGPT_TIMEOUT_SECONDS, "--timeout", "-t", help="WebGPT timeout (seconds)"),
    background: bool = typer.Option(True, "--background", help="Background: no KDE switch, no window focus"),
    output_contract: str = typer.Option("code", "--output-contract", help="Required response: assess, plan, code, all, or none"),
    architecture_authorized: bool = typer.Option(
        False,
        "--architecture-authorized",
        help="Human authorization required for plan or all",
    ),
    tab_id_override: str = typer.Option("", "--tab-id", help="Exact human-supplied tab id"),
    expected_url_override: str = typer.Option(
        "", "--expect-url", help="Optional assertion for the exact provider conversation URL"
    ),
    repo_root: str = typer.Option(
        ".", "--repo-root", help="Project Git repository root"
    ),
    source_paths: list[str] = typer.Option(
        [],
        "--source-path",
        help="Repository-relative committed source path (repeatable; required except for none)",
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

    if output_contract in {"plan", "all"} and not architecture_authorized:
        typer.echo(
            "REJECTED_SCOPE_EXPANSION: plan/all requires --architecture-authorized",
            err=True,
        )
        raise typer.Exit(2)

    try:
        b, transport, tab_id, conversation_url = _resolve_submission_target(
            project, repo_root, tab_id_override, expected_url_override
        )
    except (TargetResolutionError, ValueError) as exc:
        code = exc.code if isinstance(exc, TargetResolutionError) else "EXACT_TAB_REQUIRED"
        typer.echo(f"BLOCKED_WEBGPT_{code}: {exc}", err=True)
        raise typer.Exit(2)

    provenance = None
    if output_contract != "none":
        try:
            provenance = _source_provenance(repo_root, source_paths)
        except SourceProvenanceError as exc:
            typer.echo(f"BLOCKED_WEBGPT_{exc.code}: {exc}", err=True)
            raise typer.Exit(2)
        provenance_path = bp.with_name(f"{bp.stem}.source-provenance.json")
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")

    modes = ("assess", "plan", "code") if output_contract == "all" else (output_contract,)
    for mode in modes:
        ok, _resp = _submit_stage(
            bp, mode, transport, tab_id, conversation_url, b, timeout, provenance
        )
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


def _emit_submit_failure_summary(meta_path: Path) -> None:
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError):
        typer.echo("Submit failed", err=True)
        return

    failure = str(meta.get("failure") or "unknown")
    typer.echo(f"BLOCKED_WEBGPT_{failure.upper()}", err=True)
    diagnosis = str(meta.get("agent_diagnosis") or "").strip()
    action = str(meta.get("agent_action") or "").strip()
    if diagnosis:
        typer.echo(f"Diagnosis: {diagnosis}", err=True)
    if action:
        typer.echo(f"Recovery: {action}", err=True)
    if meta.get("browser_lock_blocked") is True:
        for key in ("cdp_probe_stderr", "cdp_retry_stderr", "stderr_log"):
            value = str(meta.get(key) or "")
            if "SURF_BROWSER_LOCK_BLOCKED" in value:
                typer.echo("Transport: SURF_BROWSER_LOCK_BLOCKED", err=True)
                break


def _submit_stage(
    bp: Path,
    mode: str,
    transport: str,
    tab_id: str,
    conversation_url: str,
    b: dict,
    timeout: int,
    provenance: dict | None,
) -> tuple[bool, Path]:
    """Run one WebGPT submission for `mode`.

    Hard-fails closed (typer.Exit) on preflight or routing-proof errors. Returns
    (deliverable_satisfied, response_path).
    """
    aug = _augment_bundle(bp, mode, provenance)
    if transport == "webgpt":
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
    elif transport == "kimi":
        try:
            live_tab = _tab_identity(tab_id)
        except TargetResolutionError as exc:
            typer.echo(f"BLOCKED_WEBGPT_{exc.code}: {exc}", err=True)
            raise typer.Exit(2)
        if not _same_url(str(live_tab.get("url", "")), conversation_url):
            typer.echo("BLOCKED_WEBGPT_TAB_IDENTITY_MISMATCH", err=True)
            raise typer.Exit(2)
    else:
        typer.echo(f"BLOCKED_WEBGPT_PROVIDER_UNSUPPORTED: {transport}", err=True)
        raise typer.Exit(2)

    tag = "" if mode in {"code", "none"} else f"-{mode}"
    resp_path = bp.with_name(f"{bp.stem}{tag}-response.md")
    zip_path = bp.with_name(f"{bp.stem}{tag}-solution.zip")
    raw_path = bp.with_name(f"{bp.stem}{tag}-response.raw.md")
    meta_path = bp.with_name(f"{bp.stem}{tag}-response.meta.json")
    receipt_path = bp.with_name(f"{bp.stem}{tag}-response.receipt.json")

    typer.echo(f"Submitting {bp.name} [{mode}]...", err=True)
    if transport == "webgpt":
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
    else:
        cmd = [
            "kimi.submit",
            "--input", str(aug),
            "--output", str(resp_path),
            "--raw-output", str(raw_path),
            "--meta-output", str(meta_path),
            "--timeout", str(timeout),
            "--tab-id", tab_id,
            "--url", conversation_url,
            "--no-activate",
        ]
    if bp.suffix == ".zip":
        cmd += ["--attach-file", str(bp)]
    result = _surf(*cmd)

    if result.returncode != 0:
        _report_failure(
            f"submit-{transport}", result, binding=b, bundle=str(bp), timeout=str(timeout)
        )
        _emit_submit_failure_summary(meta_path)
        raise typer.Exit(result.returncode)

    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        typer.echo(f"BLOCKED_WEBGPT_ROUTING_PROOF_MISSING: {exc}", err=True)
        raise typer.Exit(3)
    if not _routing_meta_is_exact(meta, tab_id):
        typer.echo("BLOCKED_WEBGPT_ROUTING_PROOF_MISMATCH", err=True)
        raise typer.Exit(3)
    if transport == "kimi":
        receipt_path.write_text(
            json.dumps(
                {
                    "schema": "webgpt.provider_route_receipt.v1",
                    "transport": transport,
                    "browser_oracle_backend": str(b.get("backend", "")),
                    "browser_oracle_project": str(b.get("name", b.get("project", ""))),
                    "requested_tab_id": tab_id,
                    "conversation_url": conversation_url,
                    "meta_output": str(meta_path),
                    "source_provenance": provenance,
                },
                indent=2,
            )
            + "\n"
        )
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
    binding = _verify_desktop(_binding(project), background, "download")
    tab_id = str(binding.get("tab_id", "")).strip() or _active_chatgpt_tab()
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
    timeout: int = typer.Option(DEFAULT_WEBGPT_TIMEOUT_SECONDS, "--timeout", "-t"),
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
