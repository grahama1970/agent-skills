#!/usr/bin/env python3
"""Core helpers for Herdr workstation orchestration.

This module wraps Herdr CLI calls, normalizes JSON output, persists workstation
manifests, and writes JSONL coordination events. It has no Typer dependency so
project agents can import the primitives directly when a shell CLI is awkward.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Iterable

from loguru import logger


@dataclasses.dataclass(slots=True)
class CommandResult:
    """Store one Herdr command result with parsed and raw output."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    parsed: Any | None


def utc_stamp() -> str:
    """Return a compact UTC timestamp safe for run identifiers."""
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str, *, limit: int = 80) -> str:
    """Convert a label into a stable filesystem and Herdr-safe slug."""
    lowered = value.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return (slug or "workstation")[:limit]


def parse_key_value(raw: str) -> tuple[str, str]:
    """Parse KEY=VALUE strings and reject malformed environment pairs."""
    if "=" not in raw:
        raise ValueError(f"Expected KEY=VALUE, got {raw!r}")
    key, value = raw.split("=", 1)
    if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        raise ValueError(f"Invalid environment key: {key!r}")
    return key, value


def parse_env_options(values: Iterable[str] | None) -> list[str]:
    """Normalize repeated KEY=VALUE options for Herdr --env arguments."""
    normalized: list[str] = []
    for value in values or []:
        key, env_value = parse_key_value(value)
        normalized.append(f"{key}={env_value}")
    return normalized


def ensure_dir(path: Path) -> Path:
    """Create a directory and return its resolved path."""
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def write_json(path: Path, value: dict[str, Any]) -> None:
    """Write a formatted JSON object to disk via a temporary file."""
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk and reject non-object payloads."""
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return parsed


def append_event(path: Path, event: dict[str, Any]) -> None:
    """Append one JSONL event for durable pane-to-pane coordination."""
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def parse_output(stdout: str) -> Any | None:
    """Parse JSON stdout when Herdr returns JSON and preserve raw text otherwise."""
    stripped = stdout.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def herdr_env(session: str | None) -> dict[str, str]:
    """Build environment variables for Herdr CLI subprocesses."""
    env = os.environ.copy()
    if session:
        env["HERDR_SESSION"] = session
    return env


def run_herdr(
    args: list[str],
    *,
    herdr_bin: str = "herdr",
    session: str | None = None,
    cwd: Path | None = None,
    check: bool = True,
    dry_run: bool = False,
) -> CommandResult:
    """Run a Herdr CLI command with JSON parsing and rich errors."""
    argv = [herdr_bin, *args]
    if dry_run:
        logger.info("DRY RUN: {}", shlex.join(argv))
        return CommandResult(argv=argv, returncode=0, stdout="", stderr="", parsed=None)
    proc = subprocess.run(
        argv,
        text=True,
        capture_output=True,
        cwd=str(cwd) if cwd else None,
        env=herdr_env(session),
    )
    result = CommandResult(
        argv=argv,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        parsed=parse_output(proc.stdout),
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            "Herdr command failed\n"
            f"command: {shlex.join(argv)}\n"
            f"exit: {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n"
        )
    return result


def find_id(value: Any, keys: tuple[str, ...]) -> str | None:
    """Recursively find the first plausible identifier in Herdr JSON."""
    if isinstance(value, dict):
        for key in keys:
            if key == "id":
                continue
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for nested in value.values():
            found = find_id(nested, keys)
            if found:
                return found
        if "id" in keys:
            candidate = value.get("id")
            if isinstance(candidate, str) and candidate:
                return candidate
    if isinstance(value, list):
        for item in value:
            found = find_id(item, keys)
            if found:
                return found
    return None


def require_id(label: str, value: Any, keys: tuple[str, ...]) -> str:
    """Return a required identifier or raise with the full Herdr payload."""
    found = find_id(value, keys)
    if not found:
        raise RuntimeError(f"Could not find {label} id in Herdr response: {value!r}")
    return found


def manifest_path_from_run_dir(run_dir: Path) -> Path:
    """Return the canonical workstation manifest path for a run directory."""
    return run_dir / "workstation.json"


def load_manifest(manifest: Path) -> dict[str, Any]:
    """Load a workstation manifest from a file or run directory."""
    path = manifest_path_from_run_dir(manifest) if manifest.is_dir() else manifest
    if not path.exists():
        raise FileNotFoundError(f"Missing workstation manifest: {path}")
    return read_json(path)


def save_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    """Persist a workstation manifest after lifecycle changes."""
    manifest["updated_at"] = utc_stamp()
    write_json(manifest_path, manifest)


def status_object(result: CommandResult) -> dict[str, Any]:
    """Convert a command result into a JSON-friendly status object."""
    return {
        "argv": result.argv,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "parsed": result.parsed,
    }


def create_workspace(
    *,
    label: str,
    cwd: Path,
    session: str | None,
    herdr_bin: str,
    env_values: list[str],
    dry_run: bool,
) -> str:
    """Create one Herdr workspace and return its identifier."""
    args = ["workspace", "create", "--cwd", str(cwd), "--label", label, "--no-focus"]
    for env_value in env_values:
        args.extend(["--env", env_value])
    result = run_herdr(args, herdr_bin=herdr_bin, session=session, dry_run=dry_run)
    if dry_run:
        return f"dry-workspace-{slugify(label)}"
    return require_id("workspace", result.parsed, ("workspace_id", "id"))


def create_tab(
    *,
    workspace_id: str,
    label: str,
    cwd: Path,
    session: str | None,
    herdr_bin: str,
    env_values: list[str],
    dry_run: bool,
) -> str:
    """Create one Herdr tab and return its identifier."""
    args = ["tab", "create", "--workspace", workspace_id, "--cwd", str(cwd), "--label", label, "--no-focus"]
    for env_value in env_values:
        args.extend(["--env", env_value])
    result = run_herdr(args, herdr_bin=herdr_bin, session=session, dry_run=dry_run)
    if dry_run:
        return f"dry-tab-{slugify(label)}"
    return require_id("tab", result.parsed, ("tab_id", "id"))


def create_worktree_workspace(
    *,
    label: str,
    repo: Path,
    branch: str,
    base: str | None,
    path: Path | None,
    session: str | None,
    herdr_bin: str,
    dry_run: bool,
) -> tuple[str, Path | None, Any]:
    """Create a Herdr Git worktree workspace and return id, path, and raw output."""
    args = ["worktree", "create", "--cwd", str(repo), "--branch", branch, "--label", label, "--no-focus", "--json"]
    if base:
        args.extend(["--base", base])
    if path:
        args.extend(["--path", str(path)])
    result = run_herdr(args, herdr_bin=herdr_bin, session=session, dry_run=dry_run)
    if dry_run:
        return f"dry-worktree-{slugify(label)}", path, None
    workspace_id = require_id("worktree workspace", result.parsed, ("workspace_id", "id"))
    worktree_path = find_id(result.parsed, ("path", "worktree_path", "cwd"))
    return workspace_id, Path(worktree_path).expanduser().resolve() if worktree_path else None, result.parsed
