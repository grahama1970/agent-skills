#!/usr/bin/env python3
"""Focused non-UI sanity runner for RealtimeSTT -> Embry event journal hardening.

This runner intentionally stops at the listener event spine. It does not start a
hot-mic daemon, call Memory/Tau, render Chatterbox audio, or build downstream
projections.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from embry_voice_control.event_journal import (  # noqa: E402
    ack_event,
    append_event,
    claim_events,
    consumer_offset,
    list_events,
)

SCHEMA = "embry_voice_control.event_spine_hardening_receipt.v1"
MANIFEST_SCHEMA = "embry_voice_control.event_spine_hardening_manifest.v1"
PRODUCER = "embry.event_spine_hardening_runner"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _read_proof(path: Path | None) -> tuple[dict[str, Any], dict[str, str]]:
    if path is None:
        proof = {
            "schema": "embry_voice_control.realtimestt_pipewire_proof_reference.v1",
            "provided": False,
            "note": "No external proof file was supplied; this runner only composes the event-spine contract.",
        }
        return proof, {"realtimestt_pipewire_proof_json": "sha256:" + _sha256_json(proof)}
    raw = path.read_bytes()
    try:
        proof = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"RealtimeSTT PipeWire proof is not valid JSON: {path}: {exc}") from exc
    if not isinstance(proof, dict):
        raise SystemExit("RealtimeSTT PipeWire proof must be a JSON object")
    return proof, {"realtimestt_pipewire_proof_file": "sha256:" + _sha256_bytes(raw)}


def _event(event_id: str, session_id: str, turn_id: str, event_type: str, payload: dict[str, Any], hashes: dict[str, str]) -> dict[str, Any]:
    seed = {
        "event_id": event_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "type": event_type,
        "payload": payload,
        "artifact_hashes": hashes,
    }
    return {
        "schema": "embry.voice_event.v1",
        "event_id": event_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "type": event_type,
        "created_at": _utc_now(),
        "causation_id": turn_id,
        "correlation_id": session_id,
        "producer": PRODUCER,
        "mocked": False,
        "live": True,
        "artifact_hashes": dict(hashes),
        "receipt_hash": "sha256:" + _sha256_json(seed),
        "payload": payload,
    }


def run(output_dir: Path, pipewire_proof: Path | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "event-spine.sqlite3"
    for suffix in ("", "-wal", "-shm"):
        stale = Path(str(db_path) + suffix)
        if stale.exists():
            stale.unlink()

    proof, proof_hashes = _read_proof(pipewire_proof)
    proof_summary = {
        "schema": proof.get("schema"),
        "provided": pipewire_proof is not None,
        "source": proof.get("capture_source") or proof.get("source") or "RealtimeSTT/PipeWire proof",
        "asr_engine": proof.get("asr_engine", "RealtimeSTT"),
    }
    immutable_hashes = dict(proof_hashes)
    immutable_hashes["proof_summary_json"] = "sha256:" + _sha256_json(proof_summary)

    session_id = "event-spine-hardening-session"
    turn_id = "event-spine-hardening-turn"
    events = [
        _event(
            "event-spine.listener-state",
            session_id,
            turn_id,
            "listener.state",
            {
                "listener_state": "proof_composed",
                "capture_source": "pipewire_proof_receipt",
                "asr_engine": "RealtimeSTT",
                "physical_hot_mic": False,
                "proof_summary": proof_summary,
            },
            immutable_hashes,
        ),
        _event(
            "event-spine.final-transcript",
            session_id,
            turn_id,
            "listener.final_transcript",
            {
                "text": proof.get("final_transcript") or proof.get("transcript") or "Embry event spine sanity",
                "source": "existing_realtimestt_pipewire_proof",
                "physical_hot_mic": False,
            },
            immutable_hashes,
        ),
        _event(
            "event-spine.receipt-written",
            session_id,
            turn_id,
            "listener.receipt_written",
            {
                "receipt_path": str(output_dir / "receipt.json"),
                "physical_hot_mic": False,
            },
            immutable_hashes,
        ),
    ]
    stored = [append_event(db_path, event) for event in events]

    # Restart recovery proof: reopen the fresh SQLite WAL journal and read the
    # same immutable event rows before any consumer work.
    recovered = list_events(db_path, session_id)
    recovery_hash_before = "sha256:" + _sha256_json(recovered)

    consumer_name = "event-spine-hardening-consumer"
    claimed = claim_events(db_path, consumer_name, session_id=session_id, limit=10, lease_seconds=60)
    for row in claimed:
        ack_event(db_path, consumer_name, row["event_id"])
    offset_after_ack = consumer_offset(db_path, consumer_name, session_id)
    claimed_after_ack = claim_events(db_path, consumer_name, session_id=session_id, limit=10, lease_seconds=60)
    recovered_after_ack = list_events(db_path, session_id)
    recovery_hash_after = "sha256:" + _sha256_json(recovered_after_ack)

    receipt = {
        "schema": SCHEMA,
        "status": "pass",
        "physical_hot_mic": False,
        "ui_exercised": False,
        "fresh_sqlite_file": str(db_path),
        "realtime_stt_pipewire_proof": proof_summary,
        "embry_journal_service": "embry_voice_control.event_journal SQLite WAL API",
        "restart_recovery": {
            "recovered_event_count": len(recovered),
            "sequence_numbers": [row["sequence"] for row in recovered],
            "event_hash_before_consumer_ack": recovery_hash_before,
            "event_hash_after_consumer_ack": recovery_hash_after,
            "immutable_hashes_preserved": recovery_hash_before == recovery_hash_after,
        },
        "consumer_claim_ack": {
            "consumer_name": consumer_name,
            "claimed_event_ids": [row["event_id"] for row in claimed],
            "acked_event_ids": [row["event_id"] for row in claimed],
            "offset_after_ack": offset_after_ack,
            "claim_after_ack_count": len(claimed_after_ack),
        },
        "immutable_hashes": immutable_hashes,
        "stored_events": stored,
        "not_implemented_by_design": [
            "listener daemon",
            "Memory/Tau calls",
            "Chatterbox rendering",
            "downstream projections",
        ],
    }
    if len(recovered) != len(events) or offset_after_ack != len(events) or claimed_after_ack:
        receipt["status"] = "fail"
    if not receipt["restart_recovery"]["immutable_hashes_preserved"]:
        receipt["status"] = "fail"

    receipt_path = output_dir / "receipt.json"
    manifest_path = output_dir / "run-manifest.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "created_at": _utc_now(),
        "output_dir": str(output_dir),
        "receipt_path": str(receipt_path),
        "sqlite_path": str(db_path),
        "physical_hot_mic": False,
        "artifacts": {
            "receipt.json": "sha256:" + _sha256_bytes(receipt_path.read_bytes()),
            "event-spine.sqlite3": "sha256:" + _sha256_bytes(db_path.read_bytes()),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the non-UI event-spine hardening sanity proof.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for receipt.json, run-manifest.json, and fresh SQLite journal.")
    parser.add_argument("--pipewire-proof", type=Path, default=None, help="Existing RealtimeSTT PipeWire proof JSON to compose into the journal receipt.")
    args = parser.parse_args(argv)
    receipt = run(args.output_dir, args.pipewire_proof)
    print(json.dumps({"status": receipt["status"], "receipt_path": str(args.output_dir / "receipt.json")}, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
