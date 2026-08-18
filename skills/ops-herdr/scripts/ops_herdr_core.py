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
import sys
from pathlib import Path
from typing import Any, Iterable

from loguru import logger

SKILLS_DIR = Path(__file__).resolve().parents[2]

# Verified against Herdr 0.8.0 / protocol 19. `herdr api schema --json` reports the
# protocol; `herdr <group> --help` reports flags. Both outrank this file.
PROTOCOL_MIN = 19

# `herdr agent start --kind` enum, from `herdr agent start --help` on 0.8.0.
AGENT_KINDS = frozenset(
    {
        "pi", "claude", "codex", "gemini", "cursor", "devin", "agy", "cline", "omp",
        "mastracode", "opencode", "copilot", "kimi", "kiro", "droid", "amp", "grok",
        "hermes", "kilo", "qodercli", "maki",
    }
)


def load_dotenv_once() -> None:
    """Load .env before any HERDR_* lookup, without clobbering the live pane env.

    Herdr exports HERDR_ENV, HERDR_SESSION, and HERDR_PANE_ID into the panes it
    manages. Those must win over any .env on disk, so both the shared helper and
    the fallback load with override=False.
    """
    if str(SKILLS_DIR) not in sys.path:
        sys.path.append(str(SKILLS_DIR))
    try:
        from dotenv_helper import load_env

        load_env()
        return
    except Exception as exc:  # noqa: BLE001 - dotenv is optional, never fatal.
        logger.debug("shared dotenv helper unavailable: {}", exc)
    try:
        from dotenv import find_dotenv, load_dotenv

        load_dotenv(find_dotenv(usecwd=True) or None, override=False)
    except Exception as exc:  # noqa: BLE001 - dotenv is optional, never fatal.
        logger.debug("dotenv unavailable: {}", exc)


load_dotenv_once()


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


class HerdrContractError(RuntimeError):
    """Raised when Herdr's response or protocol does not match this skill's contract."""


def result_body(parsed: Any, *, context: str) -> dict[str, Any]:
    """Return the `result` object of a Herdr response or fail loudly.

    Herdr replies are {"id": ..., "result": {...}}. Reaching into `result` by an
    exact path is required for move responses, where a recursive id search would
    happily return `previous_pane_id` instead of the new `pane.pane_id`.
    """
    if not isinstance(parsed, dict):
        raise HerdrContractError(f"{context}: expected a JSON object, got {parsed!r}")
    body = parsed.get("result")
    if not isinstance(body, dict):
        raise HerdrContractError(f"{context}: response has no 'result' object: {parsed!r}")
    return body


def exact_str(body: dict[str, Any], path: tuple[str, ...], *, context: str) -> str:
    """Read a required string from an exact response path."""
    node: Any = body
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise HerdrContractError(f"{context}: missing {'.'.join(path)} in {body!r}")
        node = node[key]
    if not isinstance(node, str) or not node:
        raise HerdrContractError(f"{context}: {'.'.join(path)} is not a non-empty string: {node!r}")
    return node


@dataclasses.dataclass(frozen=True, slots=True)
class WorkspaceTopology:
    """Identifiers Herdr returns when it creates a workspace."""

    workspace_id: str
    root_tab_id: str
    root_pane_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class TabTopology:
    """Identifiers Herdr returns when it creates a tab."""

    tab_id: str
    root_pane_id: str


def check_protocol(
    *,
    herdr_bin: str = "herdr",
    session: str | None = None,
    minimum: int = PROTOCOL_MIN,
) -> dict[str, Any]:
    """Assert the installed Herdr speaks a protocol this skill was built against.

    Herdr changes CLI flags between releases; `herdr api schema --json` carries the
    protocol number and is the cheapest machine-readable compatibility signal.
    """
    result = run_herdr(["api", "schema", "--json"], herdr_bin=herdr_bin, session=session, check=False)
    if result.returncode != 0:
        return {"ok": False, "protocol": None, "minimum": minimum, "reason": "api_schema_unavailable"}
    parsed = result.parsed
    protocol = parsed.get("protocol") if isinstance(parsed, dict) else None
    if not isinstance(protocol, int):
        return {"ok": False, "protocol": None, "minimum": minimum, "reason": "protocol_missing"}
    ok = protocol >= minimum
    return {
        "ok": ok,
        "protocol": protocol,
        "minimum": minimum,
        "reason": "ok" if ok else "protocol_below_minimum",
    }


def require_protocol(*, herdr_bin: str = "herdr", session: str | None = None) -> dict[str, Any]:
    """Fail closed before any topology mutation when the protocol is unsupported."""
    status = check_protocol(herdr_bin=herdr_bin, session=session)
    if not status["ok"]:
        raise HerdrContractError(
            f"Herdr protocol check failed ({status['reason']}); "
            f"found {status['protocol']}, need >= {status['minimum']}. "
            "Compare `herdr api schema --json` and `herdr <group> --help` with this skill's contract."
        )
    return status


def create_workspace(
    *,
    label: str,
    cwd: Path,
    session: str | None,
    herdr_bin: str,
    env_values: list[str],
    dry_run: bool,
) -> WorkspaceTopology:
    """Create one Herdr workspace and return its workspace, root tab, and root pane."""
    args = ["workspace", "create", "--cwd", str(cwd), "--label", label, "--no-focus"]
    for env_value in env_values:
        args.extend(["--env", env_value])
    result = run_herdr(args, herdr_bin=herdr_bin, session=session, dry_run=dry_run)
    if dry_run:
        slug = slugify(label)
        return WorkspaceTopology(f"dry-workspace-{slug}", f"dry-tab-{slug}", f"dry-pane-{slug}")
    body = result_body(result.parsed, context="workspace create")
    return WorkspaceTopology(
        workspace_id=exact_str(body, ("workspace", "workspace_id"), context="workspace create"),
        root_tab_id=exact_str(body, ("tab", "tab_id"), context="workspace create"),
        root_pane_id=exact_str(body, ("root_pane", "pane_id"), context="workspace create"),
    )


def create_tab(
    *,
    workspace_id: str,
    label: str,
    cwd: Path,
    session: str | None,
    herdr_bin: str,
    env_values: list[str],
    dry_run: bool,
) -> TabTopology:
    """Create one Herdr tab and return its tab id and root pane id."""
    args = ["tab", "create", "--workspace", workspace_id, "--cwd", str(cwd), "--label", label, "--no-focus"]
    for env_value in env_values:
        args.extend(["--env", env_value])
    result = run_herdr(args, herdr_bin=herdr_bin, session=session, dry_run=dry_run)
    if dry_run:
        slug = slugify(label)
        return TabTopology(f"dry-tab-{slug}", f"dry-pane-{slug}")
    body = result_body(result.parsed, context="tab create")
    return TabTopology(
        tab_id=exact_str(body, ("tab", "tab_id"), context="tab create"),
        root_pane_id=exact_str(body, ("root_pane", "pane_id"), context="tab create"),
    )


def split_pane(
    *,
    pane_id: str,
    direction: str,
    cwd: Path | None = None,
    env_values: list[str] | None = None,
    ratio: float | None = None,
    session: str | None = None,
    herdr_bin: str = "herdr",
    dry_run: bool = False,
) -> str:
    """Split a pane and return the new pane id from the exact response path."""
    if direction not in {"right", "down"}:
        raise ValueError(f"direction must be 'right' or 'down', got {direction!r}")
    args = ["pane", "split", pane_id, "--direction", direction, "--no-focus"]
    if ratio is not None:
        args.extend(["--ratio", str(ratio)])
    if cwd:
        args.extend(["--cwd", str(cwd)])
    for env_value in env_values or []:
        args.extend(["--env", env_value])
    result = run_herdr(args, herdr_bin=herdr_bin, session=session, dry_run=dry_run)
    if dry_run:
        return f"dry-pane-{slugify(pane_id + direction)}"
    body = result_body(result.parsed, context="pane split")
    return exact_str(body, ("pane", "pane_id"), context="pane split")


def pane_layout(
    *,
    pane_id: str,
    session: str | None = None,
    herdr_bin: str = "herdr",
) -> dict[str, Any]:
    """Read the layout of the tab containing a pane.

    Herdr 0.8.0 takes `--pane <ID>` (not a positional, and not a tab id) and returns
    a flat `layout` with a `panes` list of leaves plus a `splits` list -- not a
    nested tree.
    """
    result = run_herdr(["pane", "layout", "--pane", pane_id], herdr_bin=herdr_bin, session=session)
    body = result_body(result.parsed, context="pane layout")
    layout = body.get("layout")
    if not isinstance(layout, dict):
        raise HerdrContractError(f"pane layout: response has no layout object: {body!r}")
    return layout


def layout_pane_ids(layout: dict[str, Any]) -> list[str]:
    """Return the leaf pane ids of a layout, in Herdr's own order."""
    panes = layout.get("panes")
    if not isinstance(panes, list):
        raise HerdrContractError(f"pane layout: 'panes' is not a list: {layout!r}")
    ids = [p.get("pane_id") for p in panes if isinstance(p, dict)]
    if not all(isinstance(i, str) and i for i in ids):
        raise HerdrContractError(f"pane layout: a pane entry has no pane_id: {panes!r}")
    return ids


@dataclasses.dataclass(frozen=True, slots=True)
class PaneMove:
    """Typed view of Herdr's PaneMoveResult.

    Herdr keeps the terminal alive across a cross-workspace move and retains the
    old pane id as an alias, so `terminal_id` is the durable identity and
    `pane_id` is only the current location.
    """

    pane_id: str
    previous_pane_id: str
    terminal_id: str
    workspace_id: str
    tab_id: str
    previous_workspace_id: str | None
    previous_tab_id: str | None
    created_workspace_id: str | None
    created_tab_id: str | None
    closed_workspace_id: str | None
    closed_tab_id: str | None
    changed: bool

    def id_map(self) -> dict[str, str]:
        """Return the old-to-new pane id mapping monitors need after a move."""
        return {self.previous_pane_id: self.pane_id}


def _opt_str(body: dict[str, Any], *path: str) -> str | None:
    """Read an optional string from an exact path, tolerating nulls."""
    node: Any = body
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) and node else None


def move_pane(
    *,
    pane_id: str,
    new_workspace: bool = False,
    workspace_id: str | None = None,
    new_tab: bool = False,
    tab_id: str | None = None,
    target_pane: str | None = None,
    split: str | None = None,
    ratio: float | None = None,
    label: str | None = None,
    tab_label: str | None = None,
    focus: bool = False,
    session: str | None = None,
    herdr_bin: str = "herdr",
    dry_run: bool = False,
) -> PaneMove:
    """Move a pane and return the typed move result.

    Exactly one destination must be supplied; Herdr rejects the rest. The response
    is parsed by exact path because it carries `previous_pane_id`,
    `previous_tab_id`, and `previous_workspace_id` alongside the new ids.
    """
    destinations = [bool(new_workspace), bool(new_tab), bool(tab_id)]
    if sum(destinations) != 1:
        raise ValueError("supply exactly one of new_workspace, new_tab, or tab_id")
    args = ["pane", "move", pane_id]
    if new_workspace:
        args.append("--new-workspace")
        if label:
            args.extend(["--label", label])
        if tab_label:
            args.extend(["--tab-label", tab_label])
    elif new_tab:
        args.append("--new-tab")
        if workspace_id:
            args.extend(["--workspace", workspace_id])
        if label:
            args.extend(["--label", label])
    else:
        args.extend(["--tab", str(tab_id)])
        if target_pane:
            args.extend(["--target-pane", target_pane])
        if split:
            args.extend(["--split", split])
        if ratio is not None:
            args.extend(["--ratio", str(ratio)])
    args.append("--focus" if focus else "--no-focus")
    result = run_herdr(args, herdr_bin=herdr_bin, session=session, dry_run=dry_run)
    if dry_run:
        return PaneMove(
            pane_id=f"dry-moved-{slugify(pane_id)}", previous_pane_id=pane_id,
            terminal_id="dry-terminal", workspace_id="dry-workspace", tab_id="dry-tab",
            previous_workspace_id=None, previous_tab_id=None, created_workspace_id=None,
            created_tab_id=None, closed_workspace_id=None, closed_tab_id=None, changed=True,
        )
    body = result_body(result.parsed, context="pane move")
    move = body.get("move_result")
    if not isinstance(move, dict):
        raise HerdrContractError(f"pane move: response has no move_result object: {body!r}")
    return PaneMove(
        pane_id=exact_str(move, ("pane", "pane_id"), context="pane move"),
        previous_pane_id=exact_str(move, ("previous_pane_id",), context="pane move"),
        terminal_id=exact_str(move, ("pane", "terminal_id"), context="pane move"),
        workspace_id=exact_str(move, ("pane", "workspace_id"), context="pane move"),
        tab_id=exact_str(move, ("pane", "tab_id"), context="pane move"),
        previous_workspace_id=_opt_str(move, "previous_workspace_id"),
        previous_tab_id=_opt_str(move, "previous_tab_id"),
        created_workspace_id=_opt_str(move, "created_workspace", "workspace_id"),
        created_tab_id=_opt_str(move, "created_tab", "tab_id"),
        closed_workspace_id=_opt_str(move, "closed_workspace_id"),
        closed_tab_id=_opt_str(move, "closed_tab_id"),
        changed=bool(move.get("changed")),
    )


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
