#!/usr/bin/env python3
"""Open a workspace file in the Herdr file-viewer plugin.

Inputs: an exact path, a `path:line` reference, or a fuzzy `--query`.
Outputs: a plan and a receipt describing which pane the file was opened in.
Failure modes: returns a plan with `status` set when the plugin is absent or the
path escapes the workspace root.

Split out of monitor_herdr.py to keep every module under the 800-line repo limit;
this is a self-contained feature reached only by the `open-file` command.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from goal_discovery import path_is_relative_to
from herdr_terminal_control import herdr_bin_path
from monitor_common import (
    FILE_VIEWER_PLUGIN_ID,
    LOG_DIR,
    RECEIPT_ROOT,
    append_jsonl,
    log_event,
    now_iso,
    timestamp,
    write_json,
)


def open_file_viewer(
    *,
    target: str | None,
    query: str | None,
    root: Path | None,
    focus: bool,
    dry_run: bool,
) -> tuple[int, dict[str, Any]]:
    run_id = f"monitor-herdr-open-file-{timestamp()}"
    receipt_dir = RECEIPT_ROOT / run_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    events_path = receipt_dir / "events.jsonl"
    receipt: dict[str, Any] = {
        "schema": "agent_skills.monitor_herdr.file_viewer_open_receipt.v1",
        "run_id": run_id,
        "mocked": False,
        "live": not dry_run,
        "dry_run": dry_run,
        "target": target,
        "query": query,
        "requested_root": str(root) if root else None,
        "focus": focus,
        "receipt_dir": str(receipt_dir),
        "events_path": str(events_path),
        "log_file": str(LOG_DIR / "monitor-herdr.log"),
        "errors": [],
        "commands": [],
    }
    append_jsonl(events_path, {"event": "open_file_start", "ts": now_iso(), "target": target, "query": query})
    try:
        plan = build_file_viewer_open_plan(target=target, query=query, root=root)
    except ValueError as exc:
        receipt.update({"ok": False, "status": "BLOCKED", "errors": [str(exc)]})
        return finish_file_viewer_open(receipt, 2)

    receipt.update(plan)
    if dry_run:
        receipt.update({"ok": True, "status": "DRY_RUN"})
        return finish_file_viewer_open(receipt, 0)

    plugin = find_file_viewer_plugin()
    if not plugin.get("ok"):
        receipt.update({"ok": False, "status": "BLOCKED", "errors": [plugin.get("error", "herdr-file-viewer plugin not available")]})
        return finish_file_viewer_open(receipt, 2)
    receipt["plugin"] = plugin
    viewer_bin = Path(str(plugin["plugin_root"])) / "target" / "release" / "herdr-file-viewer"
    if not viewer_bin.exists():
        receipt.update({"ok": False, "status": "BLOCKED", "errors": [f"viewer binary not found: {viewer_bin}"]})
        return finish_file_viewer_open(receipt, 2)

    herdr_bin = herdr_bin_path()
    split_command = [
        herdr_bin,
        "pane",
        "split",
        "--current",
        "--direction",
        "right",
        "--ratio",
        "0.35",
        "--cwd",
        str(plan["root"]),
        "--env",
        f"HERDR_FILE_VIEWER_OPEN={plan['open_ref']}",
        "--focus" if focus else "--no-focus",
    ]
    split_result = run_cli(split_command, timeout_s=5)
    receipt["commands"].append(split_result)
    if not split_result.get("ok"):
        receipt.update({"ok": False, "status": "NEEDS_ATTENTION", "errors": ["herdr pane split failed"]})
        return finish_file_viewer_open(receipt, 1)
    pane_id = pane_id_from_cli_result(split_result.get("stdout", ""))
    if not pane_id:
        receipt.update({"ok": False, "status": "NEEDS_ATTENTION", "errors": ["herdr pane split did not return a pane_id"]})
        return finish_file_viewer_open(receipt, 1)
    receipt["pane_id"] = pane_id

    run_text = f"{shlex.quote(str(viewer_bin))} --open {shlex.quote(str(plan['open_ref']))}"
    run_command = [herdr_bin, "pane", "run", pane_id, run_text]
    run_result = run_cli(run_command, timeout_s=5)
    receipt["commands"].append(run_result)
    if not run_result.get("ok"):
        receipt.update({"ok": False, "status": "NEEDS_ATTENTION", "errors": ["herdr pane run failed"]})
        return finish_file_viewer_open(receipt, 1)

    read_command = [herdr_bin, "pane", "read", pane_id, "--source", "recent", "--lines", "100", "--format", "text"]
    read_result: dict[str, Any] = {"ok": False, "stdout": ""}
    visible = ""
    last_nonempty_visible = ""
    last_nonempty_read: dict[str, Any] | None = None
    for attempt in range(1, 21):
        time.sleep(0.75)
        current_read = run_cli(read_command, timeout_s=5)
        read_result = current_read
        read_result["poll_attempt"] = attempt
        receipt["commands"].append(read_result)
        visible = str(read_result.get("stdout") or "")
        if visible.strip():
            last_nonempty_visible = visible
            last_nonempty_read = read_result
        if (
            read_result.get("ok")
            and file_viewer_visible(visible)
            and open_target_visible(visible, str(plan["open_ref"]), str(plan["resolved_path"]))
        ):
            break
    if last_nonempty_visible and not file_viewer_visible(visible):
        visible = last_nonempty_visible
        if last_nonempty_read is not None:
            read_result = last_nonempty_read
    receipt["visible_excerpt"] = visible[-2000:]
    receipt["visible_viewer_frame"] = file_viewer_visible(visible)
    receipt["visible_open_target"] = open_target_visible(visible, str(plan["open_ref"]), str(plan["resolved_path"]))
    receipt["ok"] = bool(read_result.get("ok") and receipt["visible_viewer_frame"] and receipt["visible_open_target"])
    receipt["status"] = "OPENED" if receipt["ok"] else "NEEDS_ATTENTION"
    if not receipt["ok"]:
        receipt["errors"].append("opened pane did not visibly confirm the expected root and file")
    return finish_file_viewer_open(receipt, 0 if receipt["ok"] else 1)
def finish_file_viewer_open(receipt: dict[str, Any], exit_code: int) -> tuple[int, dict[str, Any]]:
    receipt_path = Path(receipt["receipt_dir"]) / "receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    append_jsonl(Path(receipt["events_path"]), {
        "event": "open_file_finish",
        "ts": now_iso(),
        "status": receipt.get("status"),
        "ok": receipt.get("ok"),
        "receipt_path": str(receipt_path),
    })
    write_json(receipt_path, receipt)
    log_event(
        str(receipt["run_id"]),
        "open_file_finish",
        status=receipt.get("status"),
        ok=receipt.get("ok"),
        receipt_path=str(receipt_path),
        exit_code=exit_code,
    )
    return exit_code, receipt
def build_file_viewer_open_plan(*, target: str | None, query: str | None, root: Path | None) -> dict[str, Any]:
    raw_target = (target or "").strip()
    raw_query = (query or "").strip()
    if not raw_target and not raw_query:
        raise ValueError("open-file requires a path target or --query")
    parsed_target = split_line_reference(raw_target) if raw_target else {"path": "", "line_suffix": ""}
    workspace_root = resolve_workspace_root(root, parsed_target["path"] if raw_target and not raw_query else None)

    fuzzy_matches: list[dict[str, Any]] = []
    mode = "exact"
    resolved_path: Path | None = None
    line_suffix = parsed_target["line_suffix"]
    exact_error: str | None = None
    if raw_target and not raw_query:
        try:
            resolved_path = resolve_exact_file(parsed_target["path"], workspace_root)
        except ValueError as exc:
            exact_error = str(exc)

    if resolved_path is None:
        mode = "fuzzy"
        fuzzy_query = raw_query or raw_target
        fuzzy_matches = fuzzy_find_files(workspace_root, fuzzy_query)
        if not fuzzy_matches:
            detail = f"; exact error: {exact_error}" if exact_error else ""
            raise ValueError(f"no file matched fuzzy query {fuzzy_query!r} under {workspace_root}{detail}")
        if len(fuzzy_matches) > 1 and int(fuzzy_matches[0]["score"]) == int(fuzzy_matches[1]["score"]):
            choices = ", ".join(item["path"] for item in fuzzy_matches[:5])
            raise ValueError(f"ambiguous fuzzy query {fuzzy_query!r}; top matches: {choices}")
        resolved_path = workspace_root / str(fuzzy_matches[0]["path"])
        if not line_suffix:
            line_suffix = split_line_reference(raw_query)["line_suffix"] if raw_query else ""

    resolved_real = resolved_path.resolve(strict=True)
    root_real = workspace_root.resolve(strict=True)
    if not resolved_real.is_file():
        raise ValueError(f"target is not a file: {resolved_real}")
    if not path_is_relative_to(str(resolved_real), str(root_real)):
        raise ValueError(f"target escapes workspace root: {resolved_real} not under {root_real}")
    rel_path = resolved_real.relative_to(root_real).as_posix()
    open_ref = f"{rel_path}{line_suffix}"
    return {
        "mode": mode,
        "root": str(root_real),
        "resolved_path": str(resolved_real),
        "open_ref": open_ref,
        "fuzzy_matches": fuzzy_matches[:10],
    }
def split_line_reference(raw: str) -> dict[str, str]:
    text = raw.strip()
    match = re.match(r"^(?P<path>.+):(?P<line>[1-9][0-9]*)(?:-(?P<end>[1-9][0-9]*))?$", text)
    if not match:
        return {"path": text, "line_suffix": ""}
    suffix = f":{match.group('line')}"
    if match.group("end"):
        suffix += f"-{match.group('end')}"
    return {"path": match.group("path"), "line_suffix": suffix}
def resolve_workspace_root(root: Path | None, target_path: str | None = None) -> Path:
    if root:
        candidate = root.expanduser().resolve()
        if not candidate.is_dir():
            raise ValueError(f"--root is not a directory: {candidate}")
        return git_root_for(candidate) or candidate
    if target_path:
        path = Path(target_path).expanduser()
        if path.is_absolute() and path.exists():
            start = path if path.is_dir() else path.parent
            return git_root_for(start) or start.resolve()
    cwd = Path.cwd().resolve()
    return git_root_for(cwd) or cwd
def git_root_for(path: Path) -> Path | None:
    result = run_cli(["git", "-C", str(path), "rev-parse", "--show-toplevel"], timeout_s=3)
    if not result.get("ok"):
        return None
    root = str(result.get("stdout") or "").strip().splitlines()[-1:]
    return Path(root[0]).resolve() if root else None
def resolve_exact_file(target_path: str, root: Path) -> Path:
    if not target_path:
        raise ValueError("empty file target")
    path = Path(target_path).expanduser()
    candidate = path if path.is_absolute() else root / path
    if not candidate.exists():
        raise ValueError(f"file does not exist: {candidate}")
    if not candidate.is_file():
        raise ValueError(f"target is not a file: {candidate}")
    return candidate
def workspace_files(root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    if proc is not None and proc.returncode == 0:
        files = [item for item in proc.stdout.split("\0") if item]
        if files:
            return sorted(set(files))
    ignored_dirs = {".git", ".hg", ".svn", ".venv", "node_modules", "__pycache__"}
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in ignored_dirs]
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                found.append(path.relative_to(root).as_posix())
            except ValueError:
                continue
    return sorted(set(found))
def fuzzy_find_files(root: Path, query: str) -> list[dict[str, Any]]:
    query_ref = split_line_reference(query)
    query_text = query_ref["path"].strip()
    if not query_text:
        raise ValueError("empty fuzzy query")
    matches: list[dict[str, Any]] = []
    for rel in workspace_files(root):
        score = fuzzy_score(query_text, rel)
        if score > 0:
            matches.append({"path": rel, "score": score})
    matches.sort(key=lambda item: (-int(item["score"]), len(str(item["path"])), str(item["path"])))
    return matches
def fuzzy_score(query: str, path: str) -> int:
    q = query.lower().replace("\\", "/").strip()
    p = path.lower()
    base = Path(p).name
    q_compact = re.sub(r"[^a-z0-9]+", "", q)
    p_compact = re.sub(r"[^a-z0-9]+", "", p)
    base_compact = re.sub(r"[^a-z0-9]+", "", base)
    if not q_compact:
        return 0
    score = 0
    if p == q:
        score += 2000
    if base == q:
        score += 1500
    if p.endswith(q):
        score += 900
    if q in p:
        score += 700
    if base.startswith(q):
        score += 500
    if q_compact in base_compact:
        score += 450
    elif q_compact in p_compact:
        score += 300
    tokens = [token for token in re.split(r"[^a-z0-9]+", q) if token]
    if tokens:
        hits = sum(1 for token in tokens if token in p)
        if hits == len(tokens):
            score += 250 + 50 * hits
        else:
            score += 25 * hits
    subseq = subsequence_score(q_compact, p_compact)
    if subseq:
        score += subseq
    return score
def subsequence_score(query: str, candidate: str) -> int:
    pos = -1
    gaps = 0
    for char in query:
        next_pos = candidate.find(char, pos + 1)
        if next_pos < 0:
            return 0
        if pos >= 0:
            gaps += max(0, next_pos - pos - 1)
        pos = next_pos
    return max(1, 120 + len(query) * 8 - gaps)
def find_file_viewer_plugin() -> dict[str, Any]:
    result = run_cli([herdr_bin_path(), "plugin", "list", "--plugin", FILE_VIEWER_PLUGIN_ID, "--json"], timeout_s=5)
    if not result.get("ok"):
        return {"ok": False, "error": "herdr plugin list failed", "command": result}
    try:
        payload = json.loads(str(result.get("stdout") or ""))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"could not parse herdr plugin list JSON: {exc}", "command": result}
    plugins = payload.get("result", {}).get("plugins", [])
    if not plugins:
        return {"ok": False, "error": f"{FILE_VIEWER_PLUGIN_ID} is not installed", "command": result}
    plugin = plugins[0]
    return {
        "ok": True,
        "plugin_id": plugin.get("plugin_id"),
        "version": plugin.get("version"),
        "plugin_root": plugin.get("plugin_root"),
        "resolved_commit": plugin.get("source", {}).get("resolved_commit") if isinstance(plugin.get("source"), dict) else None,
    }
def run_cli(command: list[str], *, timeout_s: float) -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "ok": False, "error": str(exc)}
    return {
        "command": command,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
    }
def pane_id_from_cli_result(stdout: str) -> str | None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    pane = payload.get("result", {}).get("pane")
    if isinstance(pane, dict) and pane.get("pane_id"):
        return str(pane["pane_id"])
    plugin_pane = payload.get("result", {}).get("plugin_pane")
    if isinstance(plugin_pane, dict):
        pane = plugin_pane.get("pane")
        if isinstance(pane, dict) and pane.get("pane_id"):
            return str(pane["pane_id"])
    return None
def file_viewer_visible(text: str) -> bool:
    return "┌" in text and "│" in text and "└" in text
def open_target_visible(text: str, open_ref: str, resolved_path: str) -> bool:
    return f"Opened {open_ref}" in text
