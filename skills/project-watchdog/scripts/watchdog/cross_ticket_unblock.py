"""Same-cycle cross-ticket unblock (#1646).

Ticket A serialized behind ticket B's owned bytes stayed conflicted until A's
own next cron tick re-diffed (#1617/#1620 waited whole cycles behind
#1618/#1619). This records a wait edge when A serializes behind B, and -- when
B lands on primary main within the same scan -- re-diffs every waiting A against
the NEW main bytes: if A's intended bytes are now remote-identical to main, the
conflict is cleared and A can dispatch in that cycle.

Release is decided on ACTUAL main bytes (sha per path), never on a CLOSED label:
a ticket can be labeled closed while its bytes never landed, and unlanded foreign
bytes must keep serializing. At most one dependency-release per waiting issue per
scan.

A wait edge stores, per waiting issue:
  blocking      the issue whose owned bytes serialized this one
  path_shas     {path: sha the waiter intends to land} (the "remote-identical"
                target -- when main[path] == this sha, the waiter is a no-op)
  baseline      {path: blocker baseline sha at record time} for diagnostics
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load(journal_path: Path) -> dict[str, dict[str, Any]]:
    try:
        return json.loads(journal_path.read_text())
    except (OSError, ValueError):
        return {}


def _save(journal_path: Path, edges: dict[str, dict[str, Any]]) -> None:
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text(json.dumps(edges, indent=2, sort_keys=True) + "\n")


def record_wait_edge(journal_path: Path, *, waiting: int, blocking: int,
                     path_shas: dict[str, str], baseline: dict[str, str] | None = None) -> None:
    """Upsert exactly one wait edge for the waiting issue."""
    edges = _load(journal_path)
    edges[str(waiting)] = {
        "waiting": int(waiting),
        "blocking": int(blocking),
        "path_shas": dict(path_shas),
        "baseline": dict(baseline or {}),
    }
    _save(journal_path, edges)


def releasable(journal_path: Path, main_shas: dict[str, str]) -> list[dict[str, Any]]:
    """Waiting issues whose intended bytes are now remote-identical to main.

    ``main_shas`` maps path -> the sha currently on primary main (actual bytes,
    resolved by the caller). A waiter is releasable only when EVERY path in its
    set matches main exactly. At most one release per waiting issue.
    """
    out: list[dict[str, Any]] = []
    for edge in sorted(_load(journal_path).values(), key=lambda e: e["waiting"]):
        paths = edge["path_shas"]
        if paths and all(main_shas.get(p) == sha for p, sha in paths.items()):
            out.append({"waiting": edge["waiting"], "blocking": edge["blocking"],
                        "paths": sorted(paths)})
    return out


def clear_edge(journal_path: Path, waiting: int) -> None:
    edges = _load(journal_path)
    if edges.pop(str(waiting), None) is not None:
        _save(journal_path, edges)
