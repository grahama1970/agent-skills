"""One-shot, journal-bound PipeWire playback controller for Embry."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable
import wave

import httpx

from embry_voice_control.artifact_authority import resolve_audio_artifact
from embry_voice_control.event_journal import ack_event, append_event, claim_event, session_snapshot
from embry_voice_control.pipewire_graph import observe_route, resolve_sink


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_pw_dump(pw_dump: str = "/usr/bin/pw-dump") -> list[dict[str, Any]]:
    result = subprocess.run([pw_dump, "--no-colors"], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def sink_volume(object_id: int, wpctl: str = "/usr/bin/wpctl") -> tuple[float, bool]:
    result = subprocess.run([wpctl, "get-volume", str(object_id)], check=True, capture_output=True, text=True)
    match = re.search(r"Volume:\s+([0-9.]+)", result.stdout)
    if not match:
        raise RuntimeError("sink_volume_unreadable")
    return float(match.group(1)), "[MUTED]" in result.stdout


def wav_metadata(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        return {
            "channels": wav.getnchannels(),
            "sample_rate_hz": rate,
            "sample_width_bytes": wav.getsampwidth(),
            "frame_count": frames,
            "duration_ms": round(frames * 1000 / rate),
            "compression": wav.getcomptype(),
        }


def _event(
    *, event_type: str, suffix: str, session_id: str, turn_id: str,
    causation_id: str, correlation_id: str, artifact_hashes: dict[str, str], payload: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema": "embry.voice_event.v1",
        "event_id": f"{event_type}.{suffix}",
        "session_id": session_id,
        "turn_id": turn_id,
        "type": event_type,
        "created_at": utc_now(),
        "causation_id": causation_id,
        "correlation_id": correlation_id,
        "producer": "embry-voice-control.pipewire-playback",
        "mocked": False,
        "live": True,
        "artifact_hashes": artifact_hashes,
        "receipt_hash": "sha256:" + sha256_bytes(canonical_json(payload).encode()),
        "payload": payload,
    }


def authority_identity(
    *, session_id: str, turn_id: str, render_event_id: str,
    artifact_id: str, audio_sha256: str, sink_node_name: str
) -> dict[str, str]:
    material = {
        "schema": "embry.pipewire_playback_authority_seed.v1",
        "controller_revision": "v2-client-process-id",
        "session_id": session_id,
        "turn_id": turn_id,
        "render_event_id": render_event_id,
        "artifact_id": artifact_id,
        "audio_sha256": audio_sha256,
        "sink_node_name": sink_node_name,
    }
    digest = sha256_bytes(canonical_json(material).encode())
    return {
        "digest": digest,
        "authority_id": f"pipewire-playback:{digest[:24]}",
        "idempotency_key": f"sha256:{digest}",
        "stream_node_name": f"embry.playback.{digest[:16]}",
        "consumer_name": f"embry-pipewire-playback:{digest[:24]}",
    }


def run_playback(
    *, journal_db: Path, journal_url: str, session_id: str, turn_id: str,
    source_event_id: str, source_sequence: int, tau_plan_event_id: str,
    render_event_id: str, tau_plan_sha256: str, tts_text_sha256: str,
    audio_sha256: str, audio_bytes: int, sink_node_name: str,
    expected_current_node_id: int, expected_sink_description: str,
    expected_sink_volume: float, sink_volume_tolerance: float,
    output_dir: Path, pw_play: str = "/usr/bin/pw-play", pw_dump: str = "/usr/bin/pw-dump",
    graph_poll_ms: int = 20, start_timeout_ms: int = 1500, start_confirmations: int = 2,
    popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_sha256 = audio_sha256.removeprefix("sha256:")
    health = httpx.get(f"{journal_url.rstrip('/')}/health", timeout=5).json()
    if Path(health["db_path"]).resolve() != journal_db.resolve():
        raise RuntimeError("journal_db_mismatch")
    artifact_id = f"audio:{audio_sha256}"
    audio = resolve_audio_artifact(
        journal_db, session_id=session_id, turn_id=turn_id, audio_sha256=audio_sha256,
        render_event_id=render_event_id, artifact_id=artifact_id, audio_bytes=audio_bytes,
        tau_turn_plan_sha256=tau_plan_sha256,
    )
    render = audio["render_event"]
    if not render["live"] or render["mocked"] or render["causation_id"] != tau_plan_event_id:
        raise RuntimeError("render_lineage_invalid")
    if render["artifact_hashes"].get("tts_render_text_sha256") != tts_text_sha256:
        raise RuntimeError("tts_text_hash_mismatch")
    metadata = wav_metadata(audio["path"])
    if metadata["channels"] != 1 or metadata["sample_rate_hz"] != 24000 or metadata["compression"] != "NONE":
        raise RuntimeError("wav_metadata_invalid")
    identity = authority_identity(
        session_id=session_id, turn_id=turn_id, render_event_id=render_event_id,
        artifact_id=artifact_id, audio_sha256=audio_sha256, sink_node_name=sink_node_name,
    )
    prior = [
        event for event in session_snapshot(journal_db, session_id)["events"]
        if (
            event["payload"].get("playback_authority_id")
            or event["payload"].get("authority_id")
        ) == identity["authority_id"]
    ]
    prior_types = {event["type"] for event in prior}
    if {"playback.requested", "playback.started", "playback.ended"} <= prior_types:
        return _machine_receipt(identity, audio, metadata, prior, None, True, output_dir)
    if prior:
        raise RuntimeError("prior_playback_state_incomplete")
    dump = load_pw_dump(pw_dump)
    sink = resolve_sink(dump, node_name=sink_node_name, description=expected_sink_description)
    if sink["id"] != expected_current_node_id:
        raise RuntimeError("sink_current_node_id_mismatch")
    volume, muted = sink_volume(sink["id"])
    if muted or abs(volume - expected_sink_volume) > sink_volume_tolerance:
        raise RuntimeError("sink_volume_or_mute_invalid")
    claim_event(
        journal_db, identity["consumer_name"], render_event_id,
        expected_session_id=session_id, expected_turn_id=turn_id,
        expected_sequence=render["sequence"], expected_type="chatterbox.voice_render.completed",
        lease_seconds=60,
    )
    requested_ns = time.monotonic_ns()
    common_hashes = {
        "audio_sha256": "sha256:" + audio_sha256,
        "tau_turn_plan_sha256": tau_plan_sha256,
        "tts_render_text_sha256": "sha256:" + tts_text_sha256.removeprefix("sha256:"),
    }
    sink_props = sink["info"]["props"]
    properties = canonical_json({
        "application.id": "embry.voice.playback",
        "application.name": "Embry Voice Playback",
        "node.name": identity["stream_node_name"],
        "media.name": f"Embry {turn_id}",
        "media.role": "Communication",
        "node.dont-reconnect": "true",
    })
    argv = [pw_play, "--verbose", "--target", sink_node_name, "--latency", "100ms", "--volume", "1.0", "--properties", properties, str(audio["path"])]
    requested_payload = {
        "schema": "embry.playback_requested.v1", **identity,
        "render_event_id": render_event_id, "source_event_id": source_event_id,
        "source_sequence": source_sequence, "artifact_id": artifact_id,
        "audio_sha256": "sha256:" + audio_sha256, "artifact_path": str(audio["path"]),
        "audio_bytes": audio_bytes, **metadata,
        "sink": {"node_name": sink_node_name, "object_id": sink["id"], "object_serial": sink_props.get("object.serial"), "description": expected_sink_description, "volume": volume, "muted": muted, "device_id": sink_props.get("device.id")},
        "process": {"executable": pw_play, "argv": argv, "pid": None},
        "requested_monotonic_ns": requested_ns,
    }
    requested = append_event(journal_db, _event(
        event_type="playback.requested", suffix=identity["digest"][:16], session_id=session_id,
        turn_id=turn_id, causation_id=render_event_id, correlation_id=render["correlation_id"],
        artifact_hashes=common_hashes, payload=requested_payload,
    ))
    stdout_path, stderr_path = output_dir / "pw-play.stdout", output_dir / "pw-play.stderr"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = popen(argv, stdout=stdout, stderr=stderr, shell=False)
        observations: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
        deadline = time.monotonic() + start_timeout_ms / 1000
        while time.monotonic() < deadline and process.poll() is None:
            snapshot = load_pw_dump(pw_dump)
            route = observe_route(snapshot, stream_node_name=identity["stream_node_name"], child_pid=process.pid, sink_node_name=sink_node_name)
            if route:
                observations.append((time.monotonic_ns(), route, snapshot))
                if len(observations) >= start_confirmations:
                    break
            else:
                observations.clear()
            time.sleep(graph_poll_ms / 1000)
        if len(observations) < start_confirmations:
            process.terminate()
            process.wait(timeout=2)
            raise RuntimeError("playback_start_not_observed")
        snapshot_paths = []
        for index, (_, _, snapshot) in enumerate(observations[-start_confirmations:], 1):
            path = output_dir / f"start-snapshot-{index}.json"
            path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
            snapshot_paths.append(path)
        started_ns, route, _ = observations[-start_confirmations]
        started_payload = {
            "schema": "embry.playback_started.v1", **identity,
            "artifact_id": artifact_id, "audio_sha256": "sha256:" + audio_sha256,
            "render_event_id": render_event_id, "process": {"pid": process.pid, "alive_at_detection": process.poll() is None, "argv": argv},
            "sink": {"node_name": sink_node_name, "node_id_at_start": sink["id"], "description": expected_sink_description},
            "pipewire_graph": {**route, "qualifying_snapshot_count": start_confirmations, "snapshot_interval_ms": graph_poll_ms, "snapshots": [{"path": str(path), "sha256": "sha256:" + sha256_file(path)} for path in snapshot_paths]},
            "requested_monotonic_ns": requested_ns, "started_monotonic_ns": started_ns,
        }
        started = append_event(journal_db, _event(
            event_type="playback.started", suffix=identity["digest"][:16], session_id=session_id,
            turn_id=turn_id, causation_id=requested["event_id"], correlation_id=render["correlation_id"],
            artifact_hashes={**common_hashes, "pipewire_start_snapshot_sha256": "sha256:" + sha256_file(snapshot_paths[0])}, payload=started_payload,
        ))
        exit_code = process.wait(timeout=(metadata["duration_ms"] + 5000) / 1000)
    ended_ns = time.monotonic_ns()
    elapsed_ms = (ended_ns - requested_ns) / 1_000_000
    started_elapsed_ms = (ended_ns - started_ns) / 1_000_000
    post = load_pw_dump(pw_dump)
    post_path = output_dir / "post-exit-snapshot.json"
    post_path.write_text(json.dumps(post, indent=2), encoding="utf-8")
    post_route = observe_route(post, stream_node_name=identity["stream_node_name"], child_pid=process.pid, sink_node_name=sink_node_name)
    plausible = exit_code == 0 and metadata["duration_ms"] - 500 <= elapsed_ms <= metadata["duration_ms"] + 3000 and started_elapsed_ms >= max(250, metadata["duration_ms"] - 1000) and post_route is None
    if not plausible or sha256_file(audio["path"]) != audio_sha256:
        raise RuntimeError("playback_end_invalid")
    ended_payload = {
        "schema": "embry.playback_ended.v1", **identity,
        "artifact_id": artifact_id, "audio_sha256": "sha256:" + audio_sha256,
        "render_event_id": render_event_id, "process": {"pid": process.pid, "exit_code": exit_code, "stdout_path": str(stdout_path), "stderr_path": str(stderr_path)},
        "sink": {"node_name": sink_node_name, "description": expected_sink_description},
        "clock": {"requested_monotonic_ns": requested_ns, "started_monotonic_ns": started_ns, "ended_monotonic_ns": ended_ns, "requested_to_ended_ms": round(elapsed_ms, 3), "started_to_ended_ms": round(started_elapsed_ms, 3)},
        "timing_gate": {"expected_duration_ms": metadata["duration_ms"], "plausible": plausible},
        "post_exit_graph": {"stream_absent_or_not_running": post_route is None, "path": str(post_path), "sha256": "sha256:" + sha256_file(post_path)},
    }
    ended = append_event(journal_db, _event(
        event_type="playback.ended", suffix=identity["digest"][:16], session_id=session_id,
        turn_id=turn_id, causation_id=started["event_id"], correlation_id=render["correlation_id"],
        artifact_hashes={**common_hashes, "pipewire_end_snapshot_sha256": "sha256:" + sha256_file(post_path), "pw_play_stdout_sha256": "sha256:" + sha256_file(stdout_path), "pw_play_stderr_sha256": "sha256:" + sha256_file(stderr_path)}, payload=ended_payload,
    ))
    ack_event(journal_db, identity["consumer_name"], render_event_id)
    return _machine_receipt(identity, audio, metadata, [requested, started, ended], process.pid, False, output_dir)


def _machine_receipt(identity: dict[str, str], audio: dict[str, Any], metadata: dict[str, Any], events: list[dict[str, Any]], pid: int | None, idempotent: bool, output_dir: Path) -> dict[str, Any]:
    by_type = {event["type"]: event for event in events}
    plan_path = Path(audio["render_event"]["payload"]["tau_turn_plan"]["path"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    expected_text = str(plan["tts_render_text"])
    receipt = {
        "schema": "embry.voice.pipewire_playback_machine_receipt.v1",
        "status": "MACHINE_PASS_HUMAN_PENDING", "ok": True, "proof_complete": False,
        "live": True, "mocked": False, **identity,
        "artifact": {"artifact_id": audio["artifact_id"], "sha256": audio["sha256"], "bytes": audio["bytes"], **metadata},
        "events": {name.split(".")[1]: {"event_id": event["event_id"], "sequence": event["sequence"]} for name, event in by_type.items()},
        "process_pid": pid, "idempotent_replay": idempotent, "process_spawned": not idempotent,
        "machine_acceptance": {"requested_started_ended": set(by_type) >= {"playback.requested", "playback.started", "playback.ended"}, "journal_lineage_preserved": True, "browser_audio_not_used": True, "orb_events_emitted": False},
        "human_audible_witness": {
            "status": "pending",
            "expected_text": expected_text,
            "expected_text_sha256": "sha256:" + hashlib.sha256(expected_text.encode()).hexdigest(),
        },
        "failed_gates": [],
    }
    path = output_dir / "machine-receipt.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt
