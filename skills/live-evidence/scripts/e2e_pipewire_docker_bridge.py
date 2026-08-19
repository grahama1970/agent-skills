#!/usr/bin/env python3
"""Pipe PipeWire sink audio into Docker RealtimeSTT and Live Evidence.

This proof harness captures desktop audio with host PipeWire, streams raw PCM
into a CUDA RealtimeSTT container, and posts transcript events to a running Live
Evidence API. It stores the captured audio, container logs, state snapshot, and
receipt so the live path is inspectable after the run.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DOCKER_BRIDGE = r'''
import json
import os
import sys
import time
import urllib.error
import urllib.request

import numpy as np
from RealtimeSTT import AudioToTextRecorder

backend_url = os.environ["LIVE_EVIDENCE_BACKEND_URL"].rstrip("/")
model = os.environ.get("LIVE_EVIDENCE_STT_MODEL", "tiny.en")
realtime_model = os.environ.get("LIVE_EVIDENCE_REALTIME_STT_MODEL", "tiny.en")
device = os.environ.get("LIVE_EVIDENCE_STT_DEVICE", "cuda")
compute_type = os.environ.get("LIVE_EVIDENCE_STT_COMPUTE_TYPE", "int8")
sequence = 0
events = []


def post_json(path, payload):
    request = urllib.request.Request(
        backend_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def publish(kind, text):
    global sequence
    clean = " ".join(str(text or "").split())
    if not clean:
        return
    sequence += 1
    payload = {
        "schema": "live_evidence.transcript_event.v1",
        "speaker": "interviewer",
        "kind": kind,
        "source": "pipewire",
        "sequence": sequence,
        "text": clean,
    }
    post_json("/api/transcript", payload)
    event = {"kind": kind, "sequence": sequence, "text": clean, "t": time.time()}
    events.append(event)
    print(json.dumps(event, sort_keys=True), flush=True)


def on_realtime(text):
    publish("interim", text)


def on_stabilized(text):
    publish("stabilized", text)


def build_recorder(active_device):
    return AudioToTextRecorder(
        use_microphone=False,
        model=model,
        realtime_model_type=realtime_model,
        device=active_device,
        compute_type=compute_type,
        language="en",
        enable_realtime_transcription=True,
        realtime_processing_pause=0.12,
        min_length_of_recording=0,
        min_gap_between_recordings=0,
        post_speech_silence_duration=0.45,
        no_log_file=True,
        spinner=False,
        faster_whisper_vad_filter=True,
        on_realtime_transcription_update=on_realtime,
        on_realtime_transcription_stabilized=on_stabilized,
    )


# A busy GPU must degrade transcription latency, not kill the meeting:
# tiny.en runs realtime on CPU, so a CUDA init OOM falls back instead of dying.
try:
    recorder = build_recorder(device)
except Exception as exc:
    if device == "cpu" or "out of memory" not in str(exc).lower():
        raise
    print(
        json.dumps({"kind": "stt_device_fallback", "from": device, "to": "cpu", "error": str(exc)[:200]}),
        file=sys.stderr,
        flush=True,
    )
    device = "cpu"
    recorder = build_recorder("cpu")

chunks = 0
bytes_read = 0
started = time.time()
try:
    recorder.start()
    while True:
        chunk = sys.stdin.buffer.read(4096)
        if not chunk:
            break
        bytes_read += len(chunk)
        chunks += 1
        samples = np.frombuffer(chunk, dtype=np.int16)
        if samples.size:
            recorder.feed_audio(samples, original_sample_rate=16000)
    recorder.stop()
    time.sleep(1.2)
    try:
        final_text = recorder.text()
    except Exception as exc:
        print(json.dumps({"kind": "final_error", "error": str(exc)}), file=sys.stderr, flush=True)
    else:
        publish("final", final_text)
finally:
    recorder.shutdown()

summary = {
    "schema": "live_evidence.docker_realtimestt_bridge_summary.v1",
    "chunks": chunks,
    "bytes_read": bytes_read,
    "event_count": len(events),
    "model": model,
    "realtime_model": realtime_model,
    "device": device,
    "compute_type": compute_type,
    "elapsed_s": round(time.time() - started, 3),
}
print(json.dumps(summary, sort_keys=True), flush=True)
'''


def post_json(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def get_json(base_url: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=8) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def wav_duration_s(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())


def write_wav_from_raw(raw_path: Path, wav_path: Path, *, sample_rate: int = 16000) -> None:
    raw = raw_path.read_bytes()
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(raw)


def run_text(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def state_acceptance(state: dict[str, Any]) -> dict[str, int]:
    """Count evidence families from one Live Evidence state snapshot."""

    transcript = state.get("transcript") or []
    cards = state.get("cards") or []
    pipewire_events = [event for event in transcript if event.get("source") == "pipewire"]
    ask_cards = [
        card for card in cards
        if any(source.get("lane") == "ask" for source in card.get("sources") or [])
    ]
    ask_receipt_cards = [
        card for card in ask_cards
        if any(_ask_source_has_receipt(source) for source in card.get("sources") or [])
    ]
    source_cards = [
        card for card in cards
        if any(source.get("lane") in {"ripgrep", "code", "memory"} for source in card.get("sources") or [])
    ]
    return {
        "pipewire_transcript_events": len(pipewire_events),
        "evidence_cards": len(cards),
        "source_backed_cards": len(source_cards),
        "ask_backed_cards": len(ask_cards),
        "ask_receipt_backed_cards": len(ask_receipt_cards),
    }


def _ask_source_has_receipt(source: dict[str, Any]) -> bool:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    return (
        source.get("lane") == "ask"
        and bool(metadata.get("run_dir"))
        and bool(metadata.get("response_path"))
        and bool(metadata.get("response_sha256"))
    )


def wait_for_evidence_state(
    base_url: str,
    *,
    require_ask: bool,
    timeout_s: float = 75.0,
) -> dict[str, Any]:
    """Wait for async retrieval tasks to surface in the state snapshot."""

    deadline = time.monotonic() + timeout_s
    last_state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_state = get_json(base_url, "/api/state")
        counts = state_acceptance(last_state)
        if (
            counts["pipewire_transcript_events"] > 0
            and counts["evidence_cards"] > 0
            and counts["source_backed_cards"] > 0
            and (counts["ask_receipt_backed_cards"] > 0 if require_ask else True)
        ):
            return last_state
        time.sleep(2.0)
    return last_state or get_json(base_url, "/api/state")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8811")
    parser.add_argument(
        "--source-wav",
        help="Optional local WAV to play through PipeWire. Omit to capture an already-playing desktop source.",
    )
    # Sink NAME, not a numeric node id: PipeWire node ids are not stable
    # across boots. The previous default "59" pointed at a node that no
    # longer existed, so playback fell back elsewhere while capture
    # listened to this sink's monitor and recorded 107s of silence
    # (RMS 0.0003 vs 0.058 healthy). Names route deterministically.
    parser.add_argument("--playback-target", default="alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo")
    # Record the MICROPHONE SOURCE, never the sink. Binding a capture stream to
    # the sink (--capture-kind sink-monitor) wedged the Jabra SPEAK 510 on
    # 2026-08-17: the sink went to state suspended, the card needed a wpctl
    # profile cycle to recover, and every Chrome audio stream came back MUTED on
    # the new node ids - in the middle of a live meeting. The pattern proven in
    # the 2026-07-02 chatterbox rung-8 receipt plays through the sink and records
    # the mic source; on a speakerphone that one channel already carries both the
    # room and the far end.
    parser.add_argument(
        "--capture-target",
        default="alsa_input.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.mono-fallback",
    )
    parser.add_argument(
        "--capture-kind",
        choices=("source", "sink-monitor"),
        default="source",
        help="source records a microphone and is safe. sink-monitor binds a capture stream to the sink and "
             "can wedge a USB speakerphone mid-call; opt in only for a device you can afford to lose.",
    )
    parser.add_argument("--docker-image", default="live-evidence-realtimestt-gpu:local")
    parser.add_argument("--output-dir", default="/tmp/live-evidence-e2e-docker-pipewire")
    parser.add_argument("--max-seconds", type=float, default=75.0)
    parser.add_argument("--tail-seconds", type=float, default=2.0)
    parser.add_argument("--model", default="tiny.en")
    parser.add_argument("--realtime-model", default="tiny.en")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument(
        "--no-require-ask",
        action="store_true",
        help="Do not require an Ask-backed card before marking the receipt PASS.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_wav = Path(args.source_wav).expanduser().resolve() if args.source_wav else None
    if source_wav is not None and not source_wav.is_file():
        raise SystemExit(f"source wav not found: {source_wav}")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir).expanduser().resolve() / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    captured_raw = output_dir / "captured.raw"
    captured_wav = output_dir / "captured.wav"
    docker_stdout = output_dir / "docker.stdout.jsonl"
    docker_stderr = output_dir / "docker.stderr.log"
    record_stderr = output_dir / "pw-record.stderr.log"
    play_stderr = output_dir / "pw-play.stderr.log"
    receipt_path = output_dir / "receipt.json"
    state_path = Path("/tmp/live-evidence-e2e-interview-state.json")

    post_json(args.backend_url, "/api/session/start", {"consent_confirmed": True})
    docker_command = [
        "docker",
        "run",
        "-i",
        "--rm",
        "--gpus",
        "all",
        "--network",
        "host",
        "--entrypoint",
        "python3",
        "-e",
        f"LIVE_EVIDENCE_BACKEND_URL={args.backend_url}",
        "-e",
        f"LIVE_EVIDENCE_STT_MODEL={args.model}",
        "-e",
        f"LIVE_EVIDENCE_REALTIME_STT_MODEL={args.realtime_model}",
        "-e",
        f"LIVE_EVIDENCE_STT_DEVICE={args.device}",
        "-e",
        f"LIVE_EVIDENCE_STT_COMPUTE_TYPE={args.compute_type}",
        args.docker_image,
        "-c",
        DOCKER_BRIDGE,
    ]
    record_command = [
        "pw-record",
        *(("-P", "{ stream.capture.sink=true }") if args.capture_kind == "sink-monitor" else ()),
        "--target",
        args.capture_target,
        "--rate",
        "16000",
        "--channels",
        "1",
        "--format",
        "s16",
        "-",
    ]
    play_command = ["pw-play", "--target", args.playback_target, str(source_wav)] if source_wav else None
    started = time.monotonic()
    bytes_captured = 0
    chunks = 0
    receipt: dict[str, Any] = {
        "schema": "live_evidence.e2e_docker_pipewire_receipt.v1",
        "status": "FAIL",
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "run_id": run_id,
        "backend_url": args.backend_url,
        "source_wav": str(source_wav) if source_wav else None,
        "output_dir": str(output_dir),
        "docker_image": args.docker_image,
        "docker_command": docker_command,
        "record_command": record_command,
        "play_command": play_command,
    }
    docker_proc: subprocess.Popen[bytes] | None = None
    record_proc: subprocess.Popen[bytes] | None = None
    play_proc: subprocess.Popen[bytes] | None = None
    try:
        with docker_stdout.open("wb") as docker_out, docker_stderr.open("wb") as docker_err:
            docker_proc = subprocess.Popen(
                docker_command,
                stdin=subprocess.PIPE,
                stdout=docker_out,
                stderr=docker_err,
            )
            with record_stderr.open("wb") as rec_err:
                record_proc = subprocess.Popen(record_command, stdout=subprocess.PIPE, stderr=rec_err)
            time.sleep(0.8)
            if play_command:
                with play_stderr.open("wb") as play_err:
                    play_proc = subprocess.Popen(play_command, stderr=play_err)
                deadline = started + min(args.max_seconds, wav_duration_s(source_wav) + args.tail_seconds)
            else:
                play_stderr.write_text(
                    "No local playback command; capturing existing PipeWire sink audio.\n",
                    encoding="utf-8",
                )
                deadline = started + args.max_seconds
            with captured_raw.open("wb") as raw:
                while time.monotonic() < deadline:
                    if record_proc.stdout is None:
                        raise RuntimeError("pw-record stdout missing")
                    timeout = min(0.25, max(0.0, deadline - time.monotonic()))
                    ready, _, _ = select.select([record_proc.stdout], [], [], timeout)
                    if not ready:
                        continue
                    chunk = os.read(record_proc.stdout.fileno(), 4096)
                    if not chunk:
                        if record_proc.poll() is not None:
                            raise RuntimeError(f"pw-record exited {record_proc.returncode}")
                        time.sleep(0.02)
                        continue
                    raw.write(chunk)
                    bytes_captured += len(chunk)
                    chunks += 1
                    if docker_proc.stdin is not None:
                        docker_proc.stdin.write(chunk)
                        docker_proc.stdin.flush()
            if docker_proc.stdin is not None:
                docker_proc.stdin.close()
            docker_proc.wait(timeout=90)
        write_wav_from_raw(captured_raw, captured_wav)
        if record_proc and record_proc.poll() is None:
            record_proc.send_signal(signal.SIGINT)
            try:
                record_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                record_proc.kill()
                record_proc.wait(timeout=5)
        if play_proc and play_proc.poll() is None:
            play_proc.terminate()
            try:
                play_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                play_proc.kill()
                play_proc.wait(timeout=5)
        state = wait_for_evidence_state(args.backend_url, require_ask=not args.no_require_ask)
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        transcript = state.get("transcript") or []
        cards = state.get("cards") or []
        counts = state_acceptance(state)
        acceptance = {
            "pipewire_audio_captured": bytes_captured > 0 and captured_raw.stat().st_size > 0,
            "docker_realtimestt_process_ok": docker_proc.returncode == 0 if docker_proc else False,
            **counts,
        }
        acceptance["pass"] = (
            acceptance["pipewire_audio_captured"]
            and acceptance["docker_realtimestt_process_ok"]
            and acceptance["pipewire_transcript_events"] > 0
            and acceptance["evidence_cards"] > 0
            and acceptance["source_backed_cards"] > 0
            and (acceptance["ask_receipt_backed_cards"] > 0 if not args.no_require_ask else True)
        )
        receipt.update(
            {
                "status": "PASS" if acceptance["pass"] else "FAIL",
                "elapsed_s": round(time.monotonic() - started, 3),
                "bytes_captured": bytes_captured,
                "chunks_captured": chunks,
                "captured_raw": str(captured_raw),
                "captured_wav": str(captured_wav),
                "docker_stdout": str(docker_stdout),
                "docker_stderr": str(docker_stderr),
                "state_path": str(state_path),
                "transcript_count": len(transcript),
                "card_count": len(cards),
                "acceptance": acceptance,
            }
        )
    except Exception as exc:
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        for proc in (record_proc, play_proc):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
        if docker_proc and docker_proc.poll() is None:
            try:
                if docker_proc.stdin is not None:
                    docker_proc.stdin.close()
            except OSError:
                pass
            docker_proc.terminate()
            try:
                docker_proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                docker_proc.kill()
        receipt["record_returncode"] = record_proc.returncode if record_proc else None
        receipt["play_returncode"] = play_proc.returncode if play_proc else None
        receipt["docker_returncode"] = docker_proc.returncode if docker_proc else None
        receipt["record_stderr"] = str(record_stderr)
        receipt["play_stderr"] = str(play_stderr)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "status": receipt.get("status"), "acceptance": receipt.get("acceptance"), "error": receipt.get("error")}, indent=2))
    return 0 if receipt.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
