#!/usr/bin/env python3
"""Backfill evidence metadata on all 218K+ QRAs in sparta_qra.

Thin client that calls the memory daemon's /sparta/qra/validate-batch endpoint.
ALL business logic (entity extraction, gates, AQL, stamping) runs SERVER-SIDE
in the memory project's FastAPI service.

This script only:
  1. Calls /sparta/qra/validate-batch in a loop
  2. Tracks progress and prints stats
  3. Saves state for resume
  4. Reports to /task-monitor

Usage:
    python backfill_qra_evidence.py [--batch 500] [--resume]

No special venv or uv required — just needs httpx.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# -- Config -------------------------------------------------------------------

BATCH_SIZE = 100  # Reduced from 500 — keeps batch processing well within daemon timeout
STATE_FILE = Path(__file__).parent / "state" / "backfill_state.json"

MEMORY_SOCKET = os.environ.get(
    "EMBRY_MEMORY_SOCKET",
    f"/run/user/{os.getuid()}/embry/memory.sock",
)

# -- Stats --------------------------------------------------------------------

_stats = {
    "processed": 0,
    "stamped": 0,
    "errors": 0,
    "flagged": 0,
    "batches": 0,
    "start_time": 0.0,
}
_shutdown = False


# -- Task monitor integration ------------------------------------------------

SKILLS_DIR = Path(__file__).resolve().parent.parent
TM_RUN = SKILLS_DIR / "task-monitor" / "run.sh"


def _tm(args: list[str]) -> bool:
    if not TM_RUN.exists():
        return False
    try:
        return subprocess.run(
            [str(TM_RUN), *args],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        ).returncode == 0
    except Exception:
        return False


# -- State persistence --------------------------------------------------------

def save_state():
    """Save progress for resume."""
    state = {
        **_stats,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, STATE_FILE)


def load_state() -> dict | None:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return None


# -- Main loop ----------------------------------------------------------------

def p(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def main():
    global _shutdown

    batch_size = BATCH_SIZE
    resume = False

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--batch" and i < len(sys.argv) - 1:
            batch_size = int(sys.argv[i + 1])
        elif arg == "--resume":
            resume = True

    # Resume from saved state
    if resume:
        state = load_state()
        if state:
            _stats["processed"] = state.get("processed", 0)
            _stats["stamped"] = state.get("stamped", 0)
            _stats["errors"] = state.get("errors", 0)
            _stats["flagged"] = state.get("flagged", 0)
            _stats["batches"] = state.get("batches", 0)
            p(f"Resuming: processed={_stats['processed']}, stamped={_stats['stamped']}")

    _stats["start_time"] = time.monotonic()

    # Register with task-monitor
    _tm(["start-session", "--project", "evidence-case-lab-backfill"])

    # Handle graceful shutdown
    def _signal_handler(signum, frame):
        global _shutdown
        p("Shutdown signal received, finishing current batch...")
        _shutdown = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    p(f"Starting QRA evidence backfill: batch={batch_size}")

    # Single httpx client — daemon handles all parallelism server-side
    client = httpx.Client(
        transport=httpx.HTTPTransport(uds=MEMORY_SOCKET),
        base_url="http://localhost",
        timeout=300.0,  # Large timeout — server does entity extraction per QRA
    )

    empty_batches = 0

    while not _shutdown:
        # Call server-side validate-batch — it fetches, extracts, gates, stamps
        try:
            resp = client.post("/sparta/qra/validate-batch", json={
                "limit": batch_size,
            })
            if resp.status_code != 200:
                p(f"ERROR: /sparta/qra/validate-batch returned {resp.status_code}: {resp.text[:200]}")
                time.sleep(5)
                continue
            data = resp.json()
        except Exception as exc:
            p(f"ERROR calling validate-batch: {exc}")
            time.sleep(5)
            continue

        processed = data.get("processed", 0)
        stamped = data.get("stamped", 0)
        remaining = data.get("remaining", -1)
        results = data.get("results", [])

        if processed == 0:
            empty_batches += 1
            if empty_batches >= 3:
                p("No more unvalidated QRAs. Done!")
                break
            p("Empty batch, retrying...")
            time.sleep(2)
            continue
        empty_batches = 0

        # Update stats
        _stats["processed"] += processed
        _stats["stamped"] += stamped
        _stats["batches"] += 1

        batch_flagged = sum(1 for r in results if r.get("verdict") == "flagged")
        batch_errors = sum(1 for r in results if "error" in r)
        _stats["flagged"] += batch_flagged
        _stats["errors"] += batch_errors

        elapsed = time.monotonic() - _stats["start_time"]
        rate = _stats["processed"] / max(elapsed, 1)

        p(f"Batch {_stats['batches']}: {processed} processed, {stamped} stamped, "
          f"{batch_flagged} flagged, {batch_errors} errors | "
          f"rate: {rate:.1f} QRA/s | elapsed: {elapsed/60:.1f}min")

        # Log flagged QRAs
        for r in results:
            if r.get("verdict") == "flagged":
                p(f"  FLAGGED: {r['key']} — gate_failed={r.get('gate_failed', '?')}")
            if "error" in r:
                p(f"  ERROR: {r['key']} — {r['error']}")

        # Progress
        if remaining >= 0:
            total_est = _stats["processed"] + remaining
            pct = (_stats["processed"] / max(total_est, 1)) * 100
            eta_min = remaining / max(rate, 0.1) / 60
            p(f"  Progress: {_stats['processed']}/{total_est} ({pct:.1f}%) | "
              f"remaining: {remaining} | ETA: {eta_min:.0f}min")

        # Save state and report to task-monitor
        save_state()
        _tm(["add-accomplishment", "--text",
             f"Batch {_stats['batches']}: {_stats['processed']} total, "
             f"{batch_flagged} flagged this batch"])

        if "stamp_error" in data:
            p(f"  STAMP ERROR: {data['stamp_error']}")

    # Final report
    elapsed = time.monotonic() - _stats["start_time"]
    p("")
    p("=" * 60)
    p("BACKFILL COMPLETE")
    p(f"  Processed:  {_stats['processed']}")
    p(f"  Stamped:    {_stats['stamped']}")
    p(f"  Errors:     {_stats['errors']}")
    p(f"  Flagged:    {_stats['flagged']}")
    p(f"  Batches:    {_stats['batches']}")
    p(f"  Elapsed:    {elapsed/60:.1f} minutes ({elapsed/3600:.1f} hours)")
    p(f"  Rate:       {_stats['processed']/max(elapsed,1):.1f} QRA/s")
    p("=" * 60)

    save_state()
    _tm(["end-session", "--notes",
         f"Backfill complete: {_stats['processed']} processed, "
         f"{_stats['stamped']} stamped, {_stats['errors']} errors"])


if __name__ == "__main__":
    main()
