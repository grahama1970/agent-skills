"""Durable ownership ledger for browser windows Ask caused to exist.

Purpose
    A window Ask opened and did not record is a window nothing will ever
    reclaim. Both existing reapers -- the one that runs at provisioning time
    (`_reap_stale_ask_windows`) and the binding-based `close_stale_ask_tabs` --
    can only close what some ledger claims. Ownership, not closing, was the
    gap: `_provision_browser_lifecycle` registered its seat windows, but the
    roundtable worker's recovery paths (`--create-tab`, `open-bind`) create
    windows below that layer and registered nothing. Measured on 2026-08-14: 9
    provider windows open, 0 of them named by any of 351 lifecycle receipts,
    and `~/.ask/browser-windows.jsonl` empty at 0 bytes.

    So registration has to happen wherever a window is *caused*, not only where
    a lifecycle is *compiled*. This module is that single point.

Design
    Append-only JSONL, one entry per window. Append-only because the writer may
    be killed at any moment: a torn append loses one entry, whereas a
    read-modify-write loses the whole ledger. Every entry carries the owning
    pid and a creation time, which is what lets a reaper distinguish "a run is
    still using this" from "nobody is coming back for it".

Failure modes
    Every function here swallows OSError. A ledger write must never take a
    provider run down -- the worst case of a failed write is the pre-existing
    leak, not a failed roundtable.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

REGISTRY = Path.home() / ".ask" / "browser-windows.jsonl"

#: Tests must never write into the real ledger. Before this override the
#: tau_dag suite appended fake window ids (901, 902, 1002...) to the user's own
#: file on every run -- harmless while no window carries those ids, and exactly
#: the kind of thing a reaper should never be handed.
REGISTRY_ENV = "ASK_BROWSER_WINDOW_REGISTRY"


def registry_path() -> Path:
    """The ledger to read and write, honouring the test override."""
    override = os.environ.get(REGISTRY_ENV, "").strip()
    return Path(override) if override else REGISTRY

#: fresh-keep exists so a human can inspect the tabs. Four hours is long past
#: the end of any session that would have looked.
FRESH_KEEP_TTL_SECONDS = 4 * 3600
FRESH_TEMPORARY_TTL_SECONDS = 900
#: A window kept back for recovery is still an obligation, not an exemption.
#: 28 of 351 receipts sat at `skipped_pending_recovery`, whose windows were
#: kept for a recovery nobody ever performed. They get a long TTL, not none.
PENDING_RECOVERY_TTL_SECONDS = 12 * 3600

TTL_BY_MODE = {
    "fresh-keep": FRESH_KEEP_TTL_SECONDS,
    "fresh-temporary": FRESH_TEMPORARY_TTL_SECONDS,
    "pending-recovery": PENDING_RECOVERY_TTL_SECONDS,
}


def ttl_for_mode(mode: str) -> int:
    """Seconds a window of this mode may outlive its owning process."""
    return TTL_BY_MODE.get(str(mode or ""), FRESH_TEMPORARY_TTL_SECONDS)


def register(
    window_ids: list[str],
    *,
    mode: str,
    run_dir: str = "",
    source: str = "",
    pid: int | None = None,
) -> list[str]:
    """Record ownership of windows, before the run can be killed.

    Returns the ids actually written, so a caller can log what it now owns.
    """
    unique = [str(w) for w in dict.fromkeys(window_ids) if str(w or "").strip()]
    if not unique:
        return []
    entry_pid = os.getpid() if pid is None else int(pid)
    try:
        registry = registry_path()
        registry.parent.mkdir(parents=True, exist_ok=True)
        # A writer killed mid-append leaves a line with no terminator. Without
        # this the NEXT append concatenates onto it and loses two entries
        # instead of one, which defeats the point of an append-only ledger.
        if registry.is_file() and registry.stat().st_size:
            with registry.open("rb") as probe:
                probe.seek(-1, os.SEEK_END)
                if probe.read(1) != b"\n":
                    with registry.open("a", encoding="utf-8") as repair:
                        repair.write("\n")
        with registry.open("a", encoding="utf-8") as handle:
            for window_id in unique:
                handle.write(
                    json.dumps(
                        {
                            "window_id": window_id,
                            "mode": str(mode or ""),
                            "run_dir": str(run_dir or ""),
                            "source": str(source or ""),
                            "pid": entry_pid,
                            "created_at": time.time(),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
    except OSError:
        return []
    return unique


def load() -> list[dict[str, Any]]:
    """Every registry entry, skipping lines a torn append left unreadable."""
    registry = registry_path()
    if not registry.is_file():
        return []
    try:
        raw = registry.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in raw:
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except ValueError:
            continue
        if isinstance(loaded, dict) and loaded.get("window_id"):
            entries.append(loaded)
    return entries


def deregister(window_ids: set[str]) -> None:
    """Drop entries for windows that are no longer an obligation."""
    registry = registry_path()
    if not window_ids or not registry.is_file():
        return
    try:
        kept = [
            line
            for line in registry.read_text(encoding="utf-8").splitlines()
            if line.strip() and _window_of(line) not in window_ids
        ]
        registry.write_text("".join(line + "\n" for line in kept), encoding="utf-8")
    except OSError:
        pass


def _window_of(line: str) -> str:
    try:
        entry = json.loads(line)
    except ValueError:
        return ""
    return str((entry or {}).get("window_id") or "")


def pid_alive(pid: Any) -> bool:
    """Whether the owning process still exists.

    PermissionError means the pid exists and belongs to somebody else, so it
    counts as alive: guessing otherwise would close a live run's window.
    """
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError, TypeError):
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def reclaimable(entries: list[dict[str, Any]] | None = None, *, now: float | None = None) -> list[dict[str, Any]]:
    """Entries whose owner is gone AND whose mode TTL has passed.

    Both conditions, never either: a live owner means a run is still using the
    window, and a young entry means a run may have died mid-flight with output
    that only exists in-tab.
    """
    moment = time.time() if now is None else now
    out: list[dict[str, Any]] = []
    for entry in load() if entries is None else entries:
        if pid_alive(entry.get("pid")):
            continue
        age = moment - float(entry.get("created_at") or 0)
        if age < ttl_for_mode(str(entry.get("mode") or "")):
            continue
        out.append(entry)
    return out


def window_ids_for_tabs(tab_ids: list[str], *, surf_run: Path, timeout_seconds: int = 60) -> dict[str, str]:
    """Resolve {tab_id: window_id} through surf, the way the rest of Ask does.

    The worker learns a tab id from provider submit metadata and never a window
    id, so ownership of a worker-created window can only be recorded by asking
    the browser which window holds that tab.
    """
    wanted = {str(t) for t in tab_ids if str(t or "").strip()}
    if not wanted:
        return {}
    try:
        proc = subprocess.run(
            [str(surf_run), "tab.list", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(Path(surf_run).parent),
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0:
        return {}
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return {}
    tabs = data if isinstance(data, list) else data.get("tabs", data.get("result", []))
    resolved: dict[str, str] = {}
    for tab in tabs if isinstance(tabs, list) else []:
        if not isinstance(tab, dict):
            continue
        tab_id = str(tab.get("id") or tab.get("tab_id") or "")
        window_id = str(tab.get("windowId") or tab.get("window_id") or "")
        if tab_id in wanted and window_id:
            resolved[tab_id] = window_id
    return resolved


def register_tabs(
    tab_ids: list[str],
    *,
    surf_run: Path,
    mode: str = "fresh-temporary",
    run_dir: str = "",
    source: str = "",
) -> list[str]:
    """Claim ownership of whatever windows hold these tabs.

    This is the call the worker recovery paths need: they know the tab they
    caused to exist, and nothing else in Ask will ever claim it.
    """
    resolved = window_ids_for_tabs(tab_ids, surf_run=surf_run)
    return register(list(resolved.values()), mode=mode, run_dir=run_dir, source=source)
