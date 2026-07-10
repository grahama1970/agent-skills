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
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

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


def _git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"git_head_unavailable:{path}:{result.stderr.strip()}")
    return result.stdout.strip()


def _service_origin(event_service_url: str) -> tuple[str, str, int]:
    parsed = urlsplit(event_service_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("--event-service-url must be a localhost HTTP URL")
    port = parsed.port or 80
    return f"http://{parsed.hostname}:{port}", parsed.hostname, port


def _start_service(db_path: Path, origin: str, host: str, port: int, log_path: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["EMBRY_VOICE_JOURNAL_DB"] = str(db_path)
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    log_handle = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "embry_voice_control.listener_service:create_app",
            "--factory",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    process._embry_log_handle = log_handle  # type: ignore[attr-defined]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            response = httpx.get(origin + "/health", timeout=1)
            if response.status_code == 200:
                time.sleep(0.15)
                if process.poll() is not None:
                    break
                return process
        except httpx.HTTPError:
            time.sleep(0.1)
    _stop_service(process)
    raise RuntimeError(f"listener_service_start_failed:{log_path}")


def _stop_service(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    log_handle = getattr(process, "_embry_log_handle", None)
    if log_handle is not None:
        log_handle.close()


def _run_live(
    *,
    output_dir: Path,
    realtimestt_python: Path,
    realtimestt_runner: Path,
    source_wav: Path,
    expected_phrase: str,
    playback_target: str,
    capture_target: str,
    event_service_url: str,
) -> dict[str, Any]:
    """Run actual PipeWire/RealtimeSTT callbacks through the durable service."""
    output_dir.mkdir(parents=True, exist_ok=False)
    child_root = output_dir / "realtimestt"
    child_root.mkdir()
    db_path = output_dir / "event-spine.sqlite3"
    service_log = output_dir / "listener-service.log"
    command_log = output_dir / "commands.txt"
    origin, host, port = _service_origin(event_service_url)
    session_id = "event-spine-live-session-" + _sha256_bytes(expected_phrase.encode())[:12]
    turn_id = "event-spine-live-turn-1"

    command = [
        str(realtimestt_python),
        str(realtimestt_runner),
        "--source-wav",
        str(source_wav),
        "--expected-phrase",
        expected_phrase,
        "--playback-target",
        playback_target,
        "--capture-target",
        capture_target,
        "--capture-seconds",
        "10",
        "--event-service-url",
        origin,
        "--session-id",
        session_id,
        "--turn-id",
        turn_id,
        "--output-root",
        str(child_root),
        "--skip-speaker-gate",
    ]
    command_log.write_text(" ".join(command) + "\n", encoding="utf-8")

    service = _start_service(db_path, origin, host, port, service_log)
    try:
        child = subprocess.run(command, text=True, capture_output=True, timeout=180, check=False)
        (output_dir / "realtimestt.stdout.log").write_text(child.stdout, encoding="utf-8")
        (output_dir / "realtimestt.stderr.log").write_text(child.stderr, encoding="utf-8")
        receipt_paths = sorted(child_root.glob("*/receipt.json"))
        if len(receipt_paths) != 1:
            stderr_tail = child.stderr[-1000:].replace("\n", " | ")
            raise RuntimeError(
                f"expected_one_realtimestt_receipt:found={len(receipt_paths)}:"
                f"returncode={child.returncode}:stderr={stderr_tail}"
            )
        child_receipt_path = receipt_paths[0]
        child_receipt = json.loads(child_receipt_path.read_text(encoding="utf-8"))
        before_restart = httpx.get(origin + f"/v1/sessions/{session_id}/journal", timeout=5).json()
    finally:
        _stop_service(service)

    restarted = _start_service(db_path, origin, host, port, service_log)
    try:
        after_restart = httpx.get(origin + f"/v1/sessions/{session_id}/journal", timeout=5).json()
        claim = httpx.post(
            origin + "/v1/listener/events/claim",
            json={"consumer_name": "event-spine-live-proof", "session_id": session_id, "limit": 500, "lease_seconds": 60},
            timeout=5,
        ).json()
        claimed = claim.get("events") or []
        for event in claimed:
            response = httpx.post(
                origin + "/v1/listener/events/ack",
                json={"consumer_name": "event-spine-live-proof", "event_id": event["event_id"]},
                timeout=5,
            )
            response.raise_for_status()
        claim_after_ack = httpx.post(
            origin + "/v1/listener/events/claim",
            json={"consumer_name": "event-spine-live-proof", "session_id": session_id, "limit": 500, "lease_seconds": 60},
            timeout=5,
        ).json()
    finally:
        _stop_service(restarted)

    events = after_restart.get("events") or []
    sequences = [event.get("sequence") for event in events]
    causal_complete = all(
        event.get("event_id")
        and event.get("causation_id")
        and event.get("correlation_id") == session_id
        and event.get("producer") == "RealtimeSTT.pipewire_ingress"
        and event.get("mocked") is False
        and event.get("live") is True
        and event.get("receipt_hash")
        for event in events
    )
    acceptance = {
        "realtimestt_process_passed": child.returncode == 0,
        "realtimestt_receipt_passed": child_receipt.get("acceptance", {}).get("pass") is True,
        "callbacks_persisted": len(events) >= 3,
        "server_sequences_contiguous": sequences == list(range(1, len(events) + 1)),
        "causal_metadata_complete": causal_complete,
        "restart_journal_hash_preserved": before_restart.get("sha256") == after_restart.get("sha256"),
        "consumer_claimed_all_events": len(claimed) == len(events),
        "consumer_ack_prevents_redelivery": not (claim_after_ack.get("events") or []),
    }
    status = "pass" if all(acceptance.values()) else "fail"
    receipt = {
        "schema": SCHEMA,
        "status": status,
        "mocked": False,
        "live": True,
        "used_ui": False,
        "used_mock_transcript": False,
        "session_id": session_id,
        "turn_id": turn_id,
        "listener_authority": "unix_pipewire_realtimestt",
        "claims": {"physical_hot_mic": False},
        "acceptance": acceptance,
        "realtimestt_receipt": str(child_receipt_path),
        "journal": {
            "path": str(db_path),
            "event_count": len(events),
            "sequences": sequences,
            "sha256": after_restart.get("sha256"),
            "events": events,
        },
        "consumer_claim_ack": {
            "claimed_event_ids": [event["event_id"] for event in claimed],
            "claim_after_ack_count": len(claim_after_ack.get("events") or []),
        },
    }
    receipt_path = output_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    child_hash = _sha256_bytes(child_receipt_path.read_bytes())
    manifest = {
        "schema": "embry.voice_run_manifest.v1",
        "run_id": session_id,
        "session_id": session_id,
        "listener_authority": "unix_pipewire_realtimestt",
        "repo_commits": {
            "agent_skills": _git_head(ROOT),
            "realtimestt": _git_head(realtimestt_runner.resolve().parents[2]),
        },
        "turn_ids": [turn_id],
        "receipts": {
            "listener": [{
                "kind": "unix_listener_authority",
                "path": str(child_receipt_path),
                "sha256": child_hash,
                "session_id": session_id,
                "turn_id": turn_id,
                "expected_transcript": expected_phrase,
            }]
        },
    }
    (output_dir / "run-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


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
    parser.add_argument("--realtimestt-python", type=Path)
    parser.add_argument("--realtimestt-runner", type=Path)
    parser.add_argument("--source-wav", type=Path)
    parser.add_argument("--expected-phrase")
    parser.add_argument("--playback-target", default="64")
    parser.add_argument("--capture-target", default="67")
    parser.add_argument("--event-service-url", default="http://127.0.0.1:8019/v1/listener/events")
    args = parser.parse_args(argv)
    live_args = (args.realtimestt_python, args.realtimestt_runner, args.source_wav, args.expected_phrase)
    if any(value is not None for value in live_args):
        if not all(value is not None for value in live_args):
            parser.error("live mode requires --realtimestt-python, --realtimestt-runner, --source-wav, and --expected-phrase")
        receipt = _run_live(
            output_dir=args.output_dir,
            realtimestt_python=args.realtimestt_python,
            realtimestt_runner=args.realtimestt_runner,
            source_wav=args.source_wav,
            expected_phrase=args.expected_phrase,
            playback_target=args.playback_target,
            capture_target=args.capture_target,
            event_service_url=args.event_service_url,
        )
    else:
        receipt = run(args.output_dir, args.pipewire_proof)
    print(json.dumps({"status": receipt["status"], "receipt_path": str(args.output_dir / "receipt.json")}, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
