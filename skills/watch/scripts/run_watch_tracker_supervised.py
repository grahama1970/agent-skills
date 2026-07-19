#!/usr/bin/env python3
"""Supervise the Watch tracker producer with session-chained restarts (P0C).

Runs ``track_yolo_bytetrack.py`` against a source (file or live stream) with
journaling. If the producer dies (crash, kill, stream drop), a NEW session is
started that chains to the previous session's journal via
``previous_session_id``. Track ids never carry identity across the chain
boundary — a restart is a new source session by contract, because tracker
state is only valid for consecutive frames of one stream.

Produces one journal file per session plus a chain receipt listing every
session, its exit cause, and its chain linkage.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from watch_source_session_journal import read_journal_lenient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Video file or live stream URI")
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--max-sessions", type=int, default=3)
    parser.add_argument("--max-events-per-session", type=int, default=120)
    parser.add_argument("--sample-fps", type=float, default=5.0)
    parser.add_argument("--segment-id", default="live_supervised")
    parser.add_argument("--asset-uid", default="watch_live_supervised_canary")
    parser.add_argument("--stream-id", default="watch_stream_live_supervised")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--restart-delay-seconds", type=float, default=1.0,
        help="Delay before chaining a new session after a producer death",
    )
    args = parser.parse_args()

    args.session_dir.mkdir(parents=True, exist_ok=True)
    sessions: list[dict[str, object]] = []
    previous_journal: Path | None = None

    for session_index in range(1, args.max_sessions + 1):
        journal_path = args.session_dir / f"session_{session_index:04d}.journal.jsonl"
        # Isolate the tracker's event-log out-dir per session so supervised
        # runs can never clobber committed fixture logs at the default path.
        out_dir = args.session_dir / f"session_{session_index:04d}_out"
        command = [
            args.python,
            str(SCRIPTS_DIR / "track_yolo_bytetrack.py"),
            "--source", args.source,
            "--out-dir", str(out_dir),
            "--start-seconds", "0",
            "--segment-id", args.segment_id,
            "--asset-uid", args.asset_uid,
            "--stream-id", args.stream_id,
            "--sample-fps", str(args.sample_fps),
            "--max-events", str(args.max_events_per_session),
            "--journal", str(journal_path),
        ]
        if previous_journal is not None:
            command += [
                "--previous-journal", str(previous_journal),
                "--chain-reason", "producer_death_supervised_restart",
            ]

        started_at = datetime.now(timezone.utc).isoformat()
        process = subprocess.run(command, capture_output=True, text=True)
        session: dict[str, object] = {
            "session_index": session_index,
            "journal": str(journal_path),
            "started_at": started_at,
            "exit_code": process.returncode,
            "signalled": process.returncode < 0,
            "stderr_tail": (process.stderr or "")[-400:],
        }
        if journal_path.exists():
            try:
                header, events, salvage = read_journal_lenient(journal_path)
                session["source_session_id"] = header["source_session_id"]
                session["previous_session_id"] = header.get("previous_session_id")
                session["finalized"] = salvage["finalized"]
                session["salvaged_event_count"] = salvage["salvaged_event_count"]
            except Exception as exc:  # pragma: no cover - diagnostic only
                session["journal_error"] = str(exc)
        sessions.append(session)

        if process.returncode == 0:
            break
        previous_journal = journal_path if journal_path.exists() else previous_journal
        time.sleep(args.restart_delay_seconds)

    receipt = {
        "schema_version": "watch.supervised_tracker_chain_receipt.v1",
        "source": args.source,
        "session_count": len(sessions),
        "sessions": sessions,
        "chain_valid": all(
            sessions[i].get("previous_session_id") == sessions[i - 1].get("source_session_id")
            for i in range(1, len(sessions))
        ),
        "identity_policy": (
            "Each session is a distinct source session; observation ids are "
            "session-scoped and track ids never carry identity across the chain."
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = args.session_dir / "supervised_chain_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"sessions={len(sessions)} chain_valid={receipt['chain_valid']} receipt={receipt_path}")
    return 0 if sessions and sessions[-1]["exit_code"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
