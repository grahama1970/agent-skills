"""Reclaim finished Ask DAG output trees.

Purpose
    `run_state.prune_runs` only removes directories carrying a terminal
    `status.json`, which is the runtime-run shape. The DAG output tree has a
    different shape -- `<outputs>/<label>/<ask-tau-...>/` holding `dag.json`,
    `compile-status.json`, node artifacts and provider transcripts -- so
    `prune_runs` never saw it. Measured 2026-08-16: it would have removed 1 of
    325 entries under a 2.2 GB tree, leaving 332 DAG runs in place.

    This is the pruner for that shape. It is deliberately separate rather than
    folded into `prune_runs`: the two identify a run by different markers, and
    conflating them is how one of them ends up deleting the other's directories.

Safety
    Everything here is a refusal by default.

    - A directory is a candidate only if it *looks* like an Ask DAG run, by
      carrying `dag.json` or `compile-status.json`. A directory that merely
      lives under the output root is never touched.
    - `webgpt_inflight.json` is NOT a liveness signal. 1,226 of them exist under
      the tree because a completed submit leaves its marker behind; treating
      presence as "in flight" would protect everything forever, and treating it
      as garbage would delete a live run. Liveness comes from mtime and from a
      non-terminal execution status instead.
    - A non-terminal `execution-status.json` pins the run regardless of age: a
      BLOCKED run is the evidence for why it blocked.
    - Age is measured from the NEWEST file in the tree, not the directory
      mtime, which does not change when a nested artifact is written.

Failure modes
    Dry-run is the default at every layer. The receipt names each kept run and
    why, so "nothing was pruned" is explainable rather than mysterious.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

#: What makes a directory an Ask DAG run rather than a grouping label.
RUN_MARKERS = ("dag.json", "compile-status.json")

#: Execution states that mean the run is over. Anything else -- RUNNING, or a
#: status this version does not recognise -- pins the directory.
TERMINAL_EXECUTION_STATES = {"PASS", "FAIL", "NEEDS_ATTENTION", "BLOCKED", "COMPLETED"}

DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/ask/outputs")
DEFAULT_OLDER_THAN_DAYS = 14
#: Nothing this young is ever pruned, whatever its status says. A run that
#: finished minutes ago may still be being read by the agent that launched it.
MINIMUM_AGE_HOURS = 6


def is_run_dir(path: Path) -> bool:
    return path.is_dir() and any((path / marker).is_file() for marker in RUN_MARKERS)


def newest_mtime(path: Path) -> float:
    """Newest mtime anywhere in the tree.

    A directory's own mtime does not move when a nested node artifact is
    written, so using it would age a busy run out from under itself.
    """
    newest = 0.0
    try:
        newest = path.stat().st_mtime
    except OSError:
        return 0.0
    for child in path.rglob("*"):
        try:
            newest = max(newest, child.stat().st_mtime)
        except OSError:
            continue
    return newest


def execution_state(path: Path) -> str | None:
    status_path = path / "execution-status.json"
    if not status_path.is_file():
        return None
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Unreadable status is not permission to delete.
        return "unreadable"
    return str(payload.get("status") or payload.get("state") or "unknown")


def find_run_dirs(root: Path, *, max_depth: int = 3) -> list[Path]:
    """Every DAG run directory under the output root.

    Bounded depth because node artifacts nest arbitrarily deep and a run inside
    a run is not a thing Ask produces; an unbounded walk would just be slower.
    """
    found: list[Path] = []

    def _walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = sorted(p for p in current.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            return
        for child in children:
            if is_run_dir(child):
                found.append(child)
                continue  # do not descend into a run we already claimed
            _walk(child, depth + 1)

    if is_run_dir(root):
        return [root]
    _walk(root, 1)
    return found


def plan(
    root: Path | str | None = None,
    *,
    older_than_days: int = DEFAULT_OLDER_THAN_DAYS,
    now: float | None = None,
) -> dict[str, Any]:
    """Decide what would be removed, without removing anything."""
    output_root = Path(root).expanduser() if root else DEFAULT_OUTPUT_ROOT
    moment = time.time() if now is None else now
    cutoff = moment - max(older_than_days * 86400, MINIMUM_AGE_HOURS * 3600)

    removable: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    if not output_root.is_dir():
        return {
            "schema": "ask.prune_outputs_plan.v1",
            "output_root": str(output_root),
            "older_than_days": older_than_days,
            "removable": [],
            "kept": [],
            "missing_root": True,
        }

    for run_dir in find_run_dirs(output_root):
        age_days = (moment - newest_mtime(run_dir)) / 86400
        record = {"path": str(run_dir), "age_days": round(age_days, 2)}
        state = execution_state(run_dir)
        if state is not None and state not in TERMINAL_EXECUTION_STATES:
            kept.append({**record, "reason": f"execution_state:{state}"})
            continue
        if newest_mtime(run_dir) >= cutoff:
            kept.append({**record, "reason": "too_recent"})
            continue
        removable.append({**record, "execution_state": state})

    return {
        "schema": "ask.prune_outputs_plan.v1",
        "output_root": str(output_root),
        "older_than_days": older_than_days,
        "removable": removable,
        "kept": kept,
    }


def prune(
    root: Path | str | None = None,
    *,
    older_than_days: int = DEFAULT_OLDER_THAN_DAYS,
    apply: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    """Remove finished DAG runs older than the threshold. Dry-run by default."""
    decided = plan(root, older_than_days=older_than_days, now=now)
    removed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    freed_bytes = 0

    for entry in decided["removable"]:
        path = Path(entry["path"])
        size = _tree_size(path)
        if apply:
            try:
                shutil.rmtree(path)
            except OSError as exc:
                errors.append({**entry, "error": str(exc)[:200]})
                continue
        freed_bytes += size
        removed.append({**entry, "bytes": size})

    return {
        "schema": "ask.prune_outputs_receipt.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now or time.time())),
        "applied": apply,
        "output_root": decided["output_root"],
        "older_than_days": older_than_days,
        "removed_count": len(removed),
        "kept_count": len(decided["kept"]),
        "freed_bytes": freed_bytes,
        "removed": removed,
        "kept": decided["kept"],
        "errors": errors,
    }


def _tree_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file() and not child.is_symlink():
                total += child.stat().st_size
        except OSError:
            continue
    return total
