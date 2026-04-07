#!/usr/bin/env python3
"""
Memory Recreation Queue.

Manages a queue of low-quality memories flagged by the quality scorer
for re-creation with better grounding, sensory detail, or taxonomy.

The nightly monitor-personas pipeline scores memories and enqueues those
that are ambiguous, have missing taxonomy, or lack contradiction reachability.
A separate nightly job (or manual run) drains the queue by:
  1. Recalling the original memory context
  2. Re-generating with enriched prompts
  3. Re-scoring and storing only if improved

Queue format: JSONL in data/memory_recreation_queue.jsonl

Usage:
    python recreation_queue.py enqueue --key <key> --scope <scope> --reason ambiguous
    python recreation_queue.py list [--scope <scope>]
    python recreation_queue.py drain [--scope <scope>] [--dry-run] [--max <n>]
    python recreation_queue.py stats
"""

import os
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILLS_DIR))
sys.path.insert(0, str(SKILLS_DIR / "common"))

PROJECT_ROOT = SKILLS_DIR.parent.parent
QUEUE_FILE = PROJECT_ROOT / "data" / "memory_recreation_queue.jsonl"
# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)


@dataclass
class QueueItem:
    """A memory flagged for re-creation."""
    key: str                          # ArangoDB _key
    scope: str                        # Memory scope
    reason: str                       # ambiguous | missing_taxonomy | no_contradiction | low_score
    deficits: list = field(default_factory=list)
    quality_score: float = 0.0
    original_text: str = ""           # First 200 chars of original
    enqueued_at: str = ""
    attempts: int = 0
    last_attempt: str = ""
    status: str = "pending"           # pending | in_progress | improved | failed | skipped


def load_queue() -> list[QueueItem]:
    """Load queue from JSONL file."""
    if not QUEUE_FILE.exists():
        return []
    items = []
    with open(QUEUE_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                items.append(QueueItem(**data))
    return items


def save_queue(items: list[QueueItem]):
    """Save queue to JSONL file (atomic write)."""
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        for item in items:
            f.write(json.dumps(asdict(item)) + "\n")
    tmp.rename(QUEUE_FILE)


def enqueue(
    key: str,
    scope: str,
    reason: str,
    deficits: list | None = None,
    quality_score: float = 0.0,
    original_text: str = "",
) -> QueueItem:
    """Add a memory to the re-creation queue.

    Deduplicates by key — if already queued, updates but doesn't duplicate.
    """
    items = load_queue()

    # Check for existing entry
    existing = next((i for i in items if i.key == key and i.scope == scope), None)
    if existing:
        existing.reason = reason
        existing.deficits = deficits or []
        existing.quality_score = quality_score
        existing.status = "pending"
        save_queue(items)
        return existing

    item = QueueItem(
        key=key,
        scope=scope,
        reason=reason,
        deficits=deficits or [],
        quality_score=quality_score,
        original_text=original_text[:200],
        enqueued_at=datetime.now(timezone.utc).isoformat(),
    )
    items.append(item)
    save_queue(items)
    return item


def list_queue(scope: str = "") -> list[QueueItem]:
    """List pending items, optionally filtered by scope."""
    items = load_queue()
    if scope:
        items = [i for i in items if i.scope == scope]
    return [i for i in items if i.status == "pending"]


def stats() -> dict:
    """Return queue statistics."""
    items = load_queue()
    by_status = {}
    by_reason = {}
    by_scope = {}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
        by_reason[item.reason] = by_reason.get(item.reason, 0) + 1
        by_scope[item.scope] = by_scope.get(item.scope, 0) + 1
    return {
        "total": len(items),
        "by_status": by_status,
        "by_reason": by_reason,
        "by_scope": by_scope,
    }


def drain(scope: str = "", max_items: int = 10, dry_run: bool = False) -> dict:
    """Process pending queue items by recalling and re-scoring.

    For each queued memory:
    1. Recall original from memory
    2. Re-score with contradiction check enabled
    3. If improved, update metadata; if still bad, increment attempts

    Returns summary of actions taken.
    """
    import subprocess

    items = load_queue()
    pending = [i for i in items if i.status == "pending"]
    if scope:
        pending = [i for i in pending if i.scope == scope]
    pending = pending[:max_items]

    results = {"processed": 0, "improved": 0, "still_bad": 0, "errors": 0}

    for item in pending:
        if dry_run:
            print(f"[DRY RUN] Would process: {item.key} ({item.scope}) reason={item.reason}")
            results["processed"] += 1
            continue

        item.status = "in_progress"
        item.attempts += 1
        item.last_attempt = datetime.now(timezone.utc).isoformat()

        try:
            # Recall the memory to get current text
            cmd = [
                "bash", str(MEMORY_RUN_SH),
                "recall", "--q", item.original_text[:80] or item.key,
                "--scope", item.scope, "--k", "1",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                cwd=str(MEMORY_RUN_SH.parent),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode != 0:
                item.status = "failed"
                results["errors"] += 1
                continue

            # Parse recalled memory
            recalled = None
            for line in result.stdout.strip().split("\n"):
                if line.strip().startswith("{"):
                    try:
                        recalled = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue

            if not recalled or not recalled.get("items"):
                item.status = "failed"
                results["errors"] += 1
                continue

            recalled_item = recalled["items"][0]
            text = f"{recalled_item.get('problem', '')} {recalled_item.get('solution', '')}".strip()
            bridges = recalled_item.get("bridge_attributes", [])

            # Re-score with contradiction check
            from memory_quality_scorer import score_memory
            qr = score_memory(
                text=text,
                scope=item.scope,
                bridges_stored=bridges,
                check_contradiction=True,
            )

            if qr.overall_score > item.quality_score + 0.1:
                # Improved (possibly due to new contradictions being reachable)
                item.status = "improved"
                item.quality_score = qr.overall_score
                results["improved"] += 1
            elif item.attempts >= 3:
                item.status = "failed"
                results["still_bad"] += 1
            else:
                item.status = "pending"  # Will retry next time
                results["still_bad"] += 1

            results["processed"] += 1

        except Exception as e:
            item.status = "pending" if item.attempts < 3 else "failed"
            results["errors"] += 1
            print(f"Error processing {item.key}: {e}", file=sys.stderr)

    save_queue(items)
    return results


import typer
import httpx

app = typer.Typer(help="Memory Recreation Queue")


@app.command()
def enqueue_cmd(
    key: str = typer.Option(..., help="ArangoDB _key"),
    scope: str = typer.Option(..., help="Memory scope"),
    reason: str = typer.Option(..., help="Reason: ambiguous | missing_taxonomy | no_contradiction | low_score"),
    deficits: Optional[list[str]] = typer.Option(None, help="Deficit labels"),
    score: float = typer.Option(0.0, help="Quality score"),
    text: str = typer.Option("", help="Original text"),
):
    item = enqueue(
        key=key, scope=scope, reason=reason,
        deficits=deficits or [], quality_score=score,
        original_text=text,
    )
    print(json.dumps(asdict(item), indent=2))


@app.command("list")
def list_cmd(
    scope: str = typer.Option("", help="Filter by scope"),
):
    items = list_queue(scope=scope)
    for item in items:
        print(json.dumps(asdict(item)))
    if not items:
        print("Queue empty")


@app.command()
def stats_cmd():
    print(json.dumps(stats(), indent=2))


@app.command()
def drain_cmd(
    scope: str = typer.Option("", help="Filter by scope"),
    max: int = typer.Option(10, "--max", help="Max items to process"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without processing"),
):
    result = drain(scope=scope, max_items=max, dry_run=dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
