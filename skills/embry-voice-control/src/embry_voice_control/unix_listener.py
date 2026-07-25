"""Unix/PipeWire listener sanity runner for Embry voice control.

This module wraps the local RealtimeSTT PipeWire proof runner and adds an
Embry-control receipt over the resulting transcript. Inputs are PipeWire target
IDs and an expected spoken phrase. Outputs are an underlying RealtimeSTT receipt,
listener event JSONL, and an Embry voice-control receipt. Failure modes are
explicit: missing runner, failed subprocess, missing transcript, no wake word,
or failed local audio capture all produce failed receipts.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Any
from uuid import uuid4

from loguru import logger


DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/embry-voice-control/outputs/e2e/unix-listener")
DEFAULT_REALTIMESTT_REPO = Path("/home/graham/workspace/experiments/RealtimeSTT")
DEFAULT_REALTIMESTT_PYTHON = DEFAULT_REALTIMESTT_REPO / ".venv-fastapi/bin/python"
DEFAULT_PROOF_SCRIPT = DEFAULT_REALTIMESTT_REPO / "proofs/embry_pipewire_ingress/run_pipewire_realtimestt_ingress.py"
DEFAULT_EXPECTED_PHRASE = "embry the capital of france is paris"
WAKE_WORD = "embry"
WAKE_INITIALISM_ALIASES = (("k", "m", "b"),)


def now_iso() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def new_wrapper_run_id() -> str:
    """Return a run id for the Embry control wrapper receipt."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-unix-listener-" + uuid4().hex[:8]


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write formatted JSON to a path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def append_jsonl(path: Path, event: dict[str, Any]) -> None:
    """Append one JSON object to a JSONL event file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def normalize_text(text: str) -> str:
    """Normalize transcript text for wake-word and phrase checks."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def wake_phrase_detected(text: str) -> bool:
    """Return true when ASR text contains the Embry wake phrase."""
    tokens = normalize_text(text).split()
    if WAKE_WORD in tokens:
        return True
    return any(tokens[: len(alias)] == list(alias) for alias in WAKE_INITIALISM_ALIASES)


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from a path."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def parse_receipt_path(stdout: str) -> Path | None:
    """Return the first printed receipt path from the proof runner output."""
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.endswith("/receipt.json") or stripped.endswith("receipt.json"):
            candidate = Path(stripped)
            if candidate.exists():
                return candidate
    return None


def build_realtimestt_command(
    *,
    python_executable: Path,
    proof_script: Path,
    expected_phrase: str,
    playback_target: str,
    capture_target: str,
    output_root: Path,
    capture_seconds: float,
    model: str,
    realtime_model: str,
    max_wer: float,
    skip_speaker_gate: bool,
    source_wav: Path | None,
) -> list[str]:
    """Build the RealtimeSTT PipeWire proof command."""
    command = [
        str(python_executable),
        str(proof_script),
        "--expected-phrase",
        expected_phrase,
        "--playback-target",
        playback_target,
        "--capture-target",
        capture_target,
        "--output-root",
        str(output_root),
        "--capture-seconds",
        str(capture_seconds),
        "--model",
        model,
        "--realtime-model",
        realtime_model,
        "--max-wer",
        str(max_wer),
    ]
    if skip_speaker_gate:
        command.append("--skip-speaker-gate")
    if source_wav is not None:
        command.extend(["--source-wav", str(source_wav)])
    return command


def emit_listener_events(
    *,
    events_path: Path,
    wrapper_run_id: str,
    underlying_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Write listener state events from the underlying RealtimeSTT receipt."""
    transcript = underlying_receipt.get("transcript", {})
    final_text = str(transcript.get("final") or "")
    normalized_final = normalize_text(final_text)
    realtime_events = underlying_receipt.get("realtimestt", {}).get("realtime_transcript_events", [])
    wake_detected = wake_phrase_detected(final_text)

    append_jsonl(events_path, {
        "type": "listener.state",
        "state": "idle",
        "run_id": wrapper_run_id,
        "created_at": now_iso(),
    })
    append_jsonl(events_path, {
        "type": "listener.state",
        "state": "listening",
        "run_id": wrapper_run_id,
        "created_at": now_iso(),
    })
    for event in realtime_events:
        text = str(event.get("text", "")).strip()
        if not text:
            continue
        partial_norm = normalize_text(text)
        if wake_phrase_detected(text):
            wake_detected = True
            append_jsonl(events_path, {
                "type": "listener.wake_detected",
                "source": "realtimestt_realtime",
                "text": text,
                "run_id": wrapper_run_id,
                "created_at": now_iso(),
            })
        append_jsonl(events_path, {
            "type": "listener.partial_transcript",
            "text": text,
            "realtimestt_t_ms": event.get("t_ms"),
            "run_id": wrapper_run_id,
            "created_at": now_iso(),
        })
    if wake_detected:
        append_jsonl(events_path, {
            "type": "listener.wake_detected",
            "source": "realtimestt_final",
            "text": final_text,
            "run_id": wrapper_run_id,
            "created_at": now_iso(),
        })
    append_jsonl(events_path, {
        "type": "listener.final_transcript",
        "text": final_text,
        "normalized_text": normalized_final,
        "run_id": wrapper_run_id,
        "created_at": now_iso(),
    })
    append_jsonl(events_path, {
        "type": "listener.state",
        "state": "transcribing_complete" if final_text.strip() else "error",
        "run_id": wrapper_run_id,
        "created_at": now_iso(),
    })
    append_jsonl(events_path, {
        "type": "listener.receipt_written",
        "underlying_receipt_path": str(underlying_receipt.get("receipt_path", "")),
        "run_id": wrapper_run_id,
        "created_at": now_iso(),
    })
    return {
        "events_path": str(events_path),
        "wake_word": WAKE_WORD,
        "wake_detected": wake_detected,
        "final_transcript": final_text,
        "normalized_final_transcript": normalized_final,
        "realtime_event_count": len(realtime_events),
    }


def build_acceptance(
    *,
    process_returncode: int,
    underlying_receipt: dict[str, Any] | None,
    listener_events: dict[str, Any] | None,
) -> dict[str, bool]:
    """Build deterministic acceptance flags for the Unix listener rung."""
    underlying_acceptance = (underlying_receipt or {}).get("acceptance", {})
    transcript = (underlying_receipt or {}).get("transcript", {})
    checks = {
        "proof_runner_exited_zero": process_returncode == 0,
        "used_ui": False,
        "used_browser_mic": False,
        "used_mock_transcript": False,
        "unix_pipewire_capture_exercised": bool(underlying_acceptance.get("audio_was_captured_from_local_audio_graph")),
        "audio_was_played_through_local_audio_graph": bool(underlying_acceptance.get("audio_was_played_through_local_audio_graph")),
        "captured_audio_non_silent": bool(underlying_acceptance.get("captured_audio_non_silent")),
        "captured_audio_fed_to_realtimestt": bool(underlying_acceptance.get("captured_audio_fed_to_realtimestt")),
        "realtimestt_realtime_events_seen": bool(underlying_acceptance.get("realtimestt_realtime_events_seen")),
        "realtimestt_final_transcript_seen": bool(underlying_acceptance.get("realtimestt_final_transcript_seen")),
        "final_transcript_matches_expected_phrase": bool(transcript.get("matches_expected")),
        "wake_word_detected": bool((listener_events or {}).get("wake_detected")),
    }
    checks["pass"] = all(
        value for key, value in checks.items()
        if key not in {"used_ui", "used_browser_mic", "used_mock_transcript"}
    )
    return checks


def run_unix_listener_sanity(
    *,
    realtimestt_repo: Path = DEFAULT_REALTIMESTT_REPO,
    python_executable: Path = DEFAULT_REALTIMESTT_PYTHON,
    proof_script: Path = DEFAULT_PROOF_SCRIPT,
    expected_phrase: str = DEFAULT_EXPECTED_PHRASE,
    playback_target: str = "64",
    capture_target: str = "67",
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    capture_seconds: float = 6.0,
    model: str = "tiny.en",
    realtime_model: str = "tiny.en",
    max_wer: float = 0.5,
    timeout: float = 180.0,
    skip_speaker_gate: bool = True,
    source_wav: Path | None = None,
) -> dict[str, Any]:
    """Run the Unix/PipeWire RealtimeSTT listener sanity proof."""
    wrapper_run_id = new_wrapper_run_id()
    wrapper_dir = output_root / "voice-control-wrapper" / wrapper_run_id
    wrapper_dir.mkdir(parents=True, exist_ok=False)
    stdout_path = wrapper_dir / "realtimestt_runner.stdout.log"
    stderr_path = wrapper_dir / "realtimestt_runner.stderr.log"
    listener_events_path = wrapper_dir / "listener_events.jsonl"
    receipt_path = wrapper_dir / "embry_voice_control_unix_listener_receipt.json"

    if not realtimestt_repo.exists():
        raise FileNotFoundError(f"RealtimeSTT repo not found: {realtimestt_repo}")
    if not python_executable.exists():
        raise FileNotFoundError(f"RealtimeSTT python not found: {python_executable}")
    if not proof_script.exists():
        raise FileNotFoundError(f"RealtimeSTT proof script not found: {proof_script}")

    command = build_realtimestt_command(
        python_executable=python_executable,
        proof_script=proof_script,
        expected_phrase=expected_phrase,
        playback_target=playback_target,
        capture_target=capture_target,
        output_root=output_root,
        capture_seconds=capture_seconds,
        model=model,
        realtime_model=realtime_model,
        max_wer=max_wer,
        skip_speaker_gate=skip_speaker_gate,
        source_wav=source_wav,
    )
    logger.info("running Unix listener sanity: {}", " ".join(command))
    started_at = now_iso()
    completed = subprocess.run(
        command,
        cwd=str(realtimestt_repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")

    underlying_receipt_path = parse_receipt_path(completed.stdout)
    underlying_receipt: dict[str, Any] | None = None
    listener_events: dict[str, Any] | None = None
    error: str | None = None
    if underlying_receipt_path is None:
        error = "proof runner did not print a readable receipt.json path"
    else:
        underlying_receipt = read_json(underlying_receipt_path)
        underlying_receipt["receipt_path"] = str(underlying_receipt_path)
        listener_events = emit_listener_events(
            events_path=listener_events_path,
            wrapper_run_id=wrapper_run_id,
            underlying_receipt=underlying_receipt,
        )

    acceptance = build_acceptance(
        process_returncode=completed.returncode,
        underlying_receipt=underlying_receipt,
        listener_events=listener_events,
    )
    receipt = {
        "schema": "embry_voice_control.unix_pipewire_realtimestt_listener_receipt.v1",
        "run_id": wrapper_run_id,
        "created_at": started_at,
        "completed_at": now_iso(),
        "mocked": False,
        "live": True,
        "used_ui": False,
        "used_browser_mic": False,
        "used_mock_transcript": False,
        "proof_rung": "unix_pipewire_audio_capture_to_realtimestt_listener",
        "command": command,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "process_returncode": completed.returncode,
        "realtimestt_repo": str(realtimestt_repo),
        "underlying_receipt_path": str(underlying_receipt_path) if underlying_receipt_path else None,
        "source_wav": str(source_wav) if source_wav else None,
        "listener_events": listener_events or {"events_path": str(listener_events_path), "wake_detected": False},
        "underlying_summary": {
            "status": (underlying_receipt or {}).get("status"),
            "source_audio": (underlying_receipt or {}).get("source_audio"),
            "captured_audio": (underlying_receipt or {}).get("captured_audio"),
            "transcript": (underlying_receipt or {}).get("transcript"),
            "acceptance": (underlying_receipt or {}).get("acceptance"),
        },
        "acceptance": acceptance,
        "error": error,
        "receipt_path": str(receipt_path),
        "claims": {
            "proves": [
                "Real local PipeWire audio was played and captured as PCM.",
                "Captured PCM was fed to RealtimeSTT with use_microphone=false.",
                "RealtimeSTT emitted realtime and final transcript callbacks.",
                "The final or realtime transcript included the Embry wake word.",
            ] if acceptance["pass"] else [],
            "does_not_prove": [
                "Browser microphone or WebRTC capture.",
                "Speaker identity or diarization acceptance.",
                "Tau or memory routing.",
                "Chatterbox response generated from live STT.",
                "Shared Chat UX sync.",
                "Orb sync.",
                "Replay.",
                "Interruption or barge-in.",
            ],
        },
    }
    write_json(receipt_path, receipt)
    write_json(
        output_root / "latest_unix_listener.json",
        {
            "run_id": wrapper_run_id,
            "pass": acceptance["pass"],
            "receipt_path": str(receipt_path),
            "underlying_receipt_path": str(underlying_receipt_path) if underlying_receipt_path else None,
            "final_transcript": (listener_events or {}).get("final_transcript"),
            "wake_detected": (listener_events or {}).get("wake_detected", False),
        },
    )
    return receipt
