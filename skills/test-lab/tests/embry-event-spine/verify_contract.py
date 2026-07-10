#!/usr/bin/env python3
"""Hidden semantic checks for the Embry event-spine hardening plan."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor


def fail(category: str, hint: str) -> None:
    print(json.dumps({"category": category, "public_hint": hint}))
    raise SystemExit(1)


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("hidden_target", path)
    if spec is None or spec.loader is None:
        fail("contract_load", "Target module could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def journal(target: Path) -> None:
    skill = target / "skills/embry-voice-control" if (target / "skills").exists() else target
    src = skill / "src/embry_voice_control/event_journal.py"
    module = load_module(src)
    required = ("append_event", "claim_events", "ack_event", "consumer_offset")
    if any(not hasattr(module, name) for name in required):
        fail("consumer_contract", "Durable claim, acknowledgement, and cursor APIs are incomplete.")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "events.sqlite3"

        def append(index: int):
            return module.append_event(db, {
                "schema": module.EVENT_SCHEMA,
                "event_id": f"evt-{index}", "session_id": "session-a", "turn_id": "turn-a",
                "type": "listener.final_transcript", "created_at": f"2026-07-10T00:00:{index:02d}Z",
                "causation_id": "wake-1", "correlation_id": "session-a", "producer": "realtimestt",
                "mocked": False, "live": True, "artifact_hashes": {}, "receipt_hash": "a" * 64,
                "payload": {"index": index},
            })

        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(append, range(1, 33)))
        sequences = sorted(int(row["sequence"]) for row in rows)
        if sequences != list(range(1, 33)):
            fail("sequence_allocation", "Concurrent server allocation produced a gap or duplicate.")
        replay = append(1)
        if int(replay["sequence"]) != int(rows[0]["sequence"]):
            fail("event_idempotency", "Exact event replay did not preserve canonical identity.")
        claims = module.claim_events(db, "consumer-a", "session-a", limit=2, lease_seconds=30)
        if len(claims) != 2:
            fail("consumer_claim", "Exclusive consumer claim did not return the requested events.")
        event_id = claims[0]["event_id"]
        module.ack_event(db, "consumer-a", event_id)
        module.ack_event(db, "consumer-a", event_id)
        if module.consumer_offset(db, "consumer-a", "session-a") < 1:
            fail("consumer_restart", "Acknowledged cursor was not durably persisted.")
    print(json.dumps({"category": "journal_semantics", "public_hint": "Journal semantic contract passed."}))


def publisher(target: Path) -> None:
    path = target / "proofs/embry_pipewire_ingress/run_pipewire_realtimestt_ingress.py"
    text = path.read_text()
    if "--sequence-start" in text or '"sequence": sequence' in text:
        fail("publisher_sequence", "RealtimeSTT still controls the canonical journal sequence.")
    if "assigned_sequence" not in text and 'response_json.get("sequence")' not in text:
        fail("publisher_receipt", "Publisher does not preserve the journal-assigned sequence.")
    print(json.dumps({"category": "publisher_semantics", "public_hint": "Publisher contract passed."}))


def runner(target: Path) -> None:
    skill = target / "skills/embry-voice-control" if (target / "skills").exists() else target
    path = skill / "scripts/sanity_event_spine_hardening.py"
    if not path.is_file():
        fail("receipt_runner", "Focused journal hardening receipt runner is missing.")
    text = path.read_text()
    for token in ("receipt.json", "run-manifest.json", "physical_hot_mic", "claim", "ack"):
        if token not in text:
            fail("receipt_runner", "Runner omits required receipt or restart/consumer evidence.")
    print(json.dumps({"category": "receipt_runner", "public_hint": "Receipt runner contract passed."}))


def audit(target: Path) -> None:
    path = target / "scripts/audit_horus_live_loop_gates.py"
    text = path.read_text()
    if "unix_listener_authority" not in text:
        fail("listener_authority", "Canonical audit lacks the Unix listener authority gate.")
    if 'required_receipt("browser_webrtc")' in text or 'required_receipt("browser_realtimestt")' in text:
        fail("browser_diagnostic", "Browser evidence still controls suite readiness.")
    for token in ("interruption_id", "old_turn_id", "new_turn_id"):
        if token not in text:
            fail("interruption_lineage", "Interruption old-turn/new-turn lineage is incomplete.")
    print(json.dumps({"category": "audit_semantics", "public_hint": "Audit semantic contract passed."}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", choices=("journal", "runner", "publisher", "audit"))
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    try:
        {"journal": journal, "runner": runner, "publisher": publisher, "audit": audit}[args.contract](args.target.resolve())
    except SystemExit:
        raise
    except Exception as exc:
        fail(f"{args.contract}_runtime", f"Semantic contract raised {type(exc).__name__}.")


if __name__ == "__main__":
    main()
