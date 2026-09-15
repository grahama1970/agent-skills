#!/usr/bin/env python3
"""Backfill ask_call_log from historical run dirs on disk.

Memory should already know what doesn't work; runs executed before the call
log existed left their receipts on disk only. Walk a outputs root, ingest one
ask.call_log.v1 doc per node receipt. Idempotent: deterministic _key per
(run_dir, node) upserts in place, so re-running never duplicates.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ask import call_log, tau_dag  # noqa: E402


def _run_ts(run_dir: Path, receipt: Path | None = None) -> str | None:
    """Best-effort run timestamp: dir name first, node-receipt mtime fallback."""
    match = re.search(r"(20\d{6}T\d{6,8}(?:Z|\.\d+Z?)?)", run_dir.name)
    if match:
        raw = match.group(1).replace("Z", "")
        for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M%S%f", "%Y%m%dT%H%M"):
            try:
                return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.strptime(raw, fmt))
            except ValueError:
                continue
    source = receipt or (run_dir / "node-receipt.json")
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(source.stat().st_mtime))
    except OSError:
        return None


def backfill(root: Path, *, batch_size: int = 50, dry_run: bool = False) -> dict:
    import httpx

    stats = {"runs": 0, "docs": 0, "stored": 0, "errors": 0}
    pending: list[dict] = []
    for artifacts in sorted(root.rglob("node-artifacts")):
        run_dir = artifacts.parent
        receipts = tau_dag._collect_node_provider_receipts(artifacts)
        if not receipts:
            continue
        stats["runs"] += 1
        status = ""
        execution_status = run_dir / "execution-status.json"
        if execution_status.is_file():
            try:
                import json

                status = str(json.loads(execution_status.read_text(encoding="utf-8")).get("status") or "")
            except (OSError, ValueError):
                status = ""
        for item in receipts:
            doc = call_log.document_for(item, run_dir=str(run_dir), status=status)
            receipt_path = Path(str(item.get("path"))) if item.get("path") else None
            ts = _run_ts(run_dir, receipt_path)
            if ts:
                doc["ts"] = ts  # historical truth: when the run happened
                doc["backfilled"] = True
                doc["retrieval_text"] = f"{doc['retrieval_text']} (backfilled)"
            pending.append(doc)
            stats["docs"] += 1
        if len(pending) >= batch_size:
            stats["stored"] += _flush(pending, dry_run)
            pending = []
    stats["stored"] += _flush(pending, dry_run)
    return stats


def _flush(docs: list[dict], dry_run: bool) -> int:
    import httpx

    if not docs or dry_run:
        return 0
    try:
        response = httpx.post(
            f"{call_log.MEMORY_URL}/upsert",
            json={"collection": call_log.COLLECTION, "documents": docs},
            timeout=30.0,
            headers={"x-caller-skill": "ask"},
        )
        response.raise_for_status()
        return len(docs)
    except (httpx.HTTPError, OSError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="/mnt/storage12tb/skills/ask/outputs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = backfill(Path(args.root), dry_run=args.dry_run)
    import json

    print(json.dumps({**stats, "dry_run": args.dry_run}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
