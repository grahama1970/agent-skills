#!/usr/bin/env python3
"""Migrate monitor state across Herdr pane moves.

Inputs: `herdr.space_operation_receipt.v1` receipts written by `ops-herdr agent
move`, plus the monitor state file.
Outputs: a JSON report on stdout; with --apply, a rewritten state file.
Failure modes: exits 1 when a receipt is malformed, 2 when the state file is
unreadable.

Monitor state is keyed by pane id, but a cross-workspace move changes that id
while the terminal and the agent survive. Without this migration a moved agent
looks brand new: its stopped-since timestamp is lost, its cooldown resets, and it
can be re-prompted immediately after a move it never noticed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from loguru import logger

RECEIPT_SCHEMA = "herdr.space_operation_receipt.v1"
DEFAULT_STATE_PATH = Path.home() / ".local" / "state" / "monitor-herdr" / "state.json"

app = typer.Typer(help="Reconcile monitor-herdr pane state after ops-herdr moves.")


def load_receipts(sources: list[Path]) -> list[dict[str, Any]]:
    """Collect move receipts from files and directories, oldest first."""
    found: list[dict[str, Any]] = []
    for source in sources:
        source = source.expanduser()
        paths = sorted(source.rglob("*.json")) if source.is_dir() else [source]
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"unreadable receipt {path}: {exc}") from exc
            if not isinstance(payload, dict) or payload.get("schema") != RECEIPT_SCHEMA:
                continue
            if not isinstance(payload.get("id_map"), dict) or not payload["id_map"]:
                raise ValueError(f"receipt {path} has no usable id_map")
            payload["_path"] = str(path)
            found.append(payload)
    found.sort(key=lambda r: str(r.get("created_at", "")))
    return found


def resolve_chain(receipts: list[dict[str, Any]]) -> dict[str, str]:
    """Collapse chained moves so an id moved twice maps to its final location."""
    resolved: dict[str, str] = {}
    for receipt in receipts:
        for old, new in receipt["id_map"].items():
            for start, current in list(resolved.items()):
                if current == old:
                    resolved[start] = new
            resolved.setdefault(old, new)
    return {old: new for old, new in resolved.items() if old != new}


def migrate_prompts(state: dict[str, Any], id_map: dict[str, str]) -> dict[str, Any]:
    """Move per-pane prompt state onto new pane ids without losing a cooldown."""
    prompts = state.get("prompts")
    if not isinstance(prompts, dict):
        raise ValueError("state has no 'prompts' object")
    actions: list[dict[str, Any]] = []
    for old, new in id_map.items():
        if old not in prompts:
            actions.append({"from": old, "to": new, "action": "skipped_no_state"})
            continue
        if new in prompts:
            # Both ids carry state: keep whichever was prompted most recently, so a
            # migration can never shorten an active cooldown.
            old_epoch = int(prompts[old].get("last_prompt_epoch", 0) or 0)
            new_epoch = int(prompts[new].get("last_prompt_epoch", 0) or 0)
            if old_epoch > new_epoch:
                prompts[new] = prompts.pop(old)
                actions.append({"from": old, "to": new, "action": "migrated_over_older_entry"})
            else:
                prompts.pop(old)
                actions.append({"from": old, "to": new, "action": "kept_newer_destination"})
            continue
        prompts[new] = prompts.pop(old)
        actions.append({"from": old, "to": new, "action": "migrated"})
    return {"prompts": prompts, "actions": actions}


@app.command("reconcile-moves")
def reconcile_moves(
    receipts: Annotated[Optional[list[Path]], typer.Option("--receipts", help="Receipt file or directory. Repeatable.")] = None,
    state_path: Annotated[Path, typer.Option("--state", help="Monitor state file.")] = DEFAULT_STATE_PATH,
    apply: Annotated[bool, typer.Option("--apply/--dry-run", help="Write the migrated state. Dry run by default.")] = False,
) -> None:
    """Migrate monitor pane state onto the new ids reported by move receipts."""
    if not receipts:
        raise typer.BadParameter("--receipts is required")
    try:
        collected = load_receipts(list(receipts))
    except ValueError as exc:
        logger.error("{}", exc)
        raise typer.Exit(code=1) from exc

    id_map = resolve_chain(collected)
    if not state_path.expanduser().exists():
        state: dict[str, Any] = {"schema": "agent_skills.monitor_herdr.state.v1", "prompts": {}}
    else:
        try:
            state = json.loads(state_path.expanduser().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("state unreadable at {}: {}", state_path, exc)
            raise typer.Exit(code=2) from exc
    if not isinstance(state, dict):
        logger.error("state at {} is not an object", state_path)
        raise typer.Exit(code=2)
    state.setdefault("prompts", {})

    try:
        outcome = migrate_prompts(state, id_map)
    except ValueError as exc:
        logger.error("{}", exc)
        raise typer.Exit(code=2) from exc

    if apply:
        target = state_path.expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(target)

    report = {
        "schema": "agent_skills.monitor_herdr.move_reconciliation.v1",
        "receipts_read": [r["_path"] for r in collected],
        "id_map": id_map,
        "actions": outcome["actions"],
        "migrated": sum(1 for a in outcome["actions"] if a["action"].startswith("migrated")),
        "applied": apply,
        "state_path": str(state_path),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


def main() -> int:
    """Entry point for run.sh routing."""
    app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
