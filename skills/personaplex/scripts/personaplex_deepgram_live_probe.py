#!/usr/bin/env python3
"""Live Deepgram ASR/VAD probe for the PersonaPlex golden-state wrapper."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any


ROOT = Path("/home/graham/workspace/experiments/agent-skills")
PERSONAPLEX_PYTHON = Path("/home/graham/workspace/experiments/personaplex/.venv/bin/python")
OUTPUT_ROOT = Path("/mnt/storage12tb/skills/personaplex/outputs/deepgram-live-probe/embry")
DEFAULT_QUESTION = (
    "Embry, what is the weather like in Hawaii today, "
    "and how would that make you feel about surfing with Kai?"
)


def ensure_runtime_python() -> None:
    if PERSONAPLEX_PYTHON.exists() and Path(sys.executable).resolve() != PERSONAPLEX_PYTHON.resolve():
        os.execv(str(PERSONAPLEX_PYTHON), [str(PERSONAPLEX_PYTHON), __file__, *sys.argv[1:]])


def utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def synthesize_question_wav(text: str, output_dir: Path) -> Path:
    raw = output_dir / "user-question-raw.wav"
    wav = output_dir / "user-question-24khz-mono.wav"
    espeak = subprocess.run(
        ["bash", "-lc", "command -v espeak-ng || command -v espeak"],
        capture_output=True,
        text=True,
        check=True,
    )
    espeak_path = espeak.stdout.strip().splitlines()[0]
    subprocess.run([espeak_path, "-w", str(raw), text], check=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw),
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ],
        check=True,
    )
    return wav


def wav_metrics(path: Path) -> dict[str, Any]:
    import soundfile as sf

    data, sample_rate = sf.read(str(path), always_2d=True)
    info = sf.info(str(path))
    return {
        "path": str(path),
        "sha256": sha256_path(path),
        "size_bytes": path.stat().st_size,
        "sample_rate": int(sample_rate),
        "channels": int(data.shape[1]),
        "frames": int(data.shape[0]),
        "duration_s": round(float(info.duration), 3),
        "peak": float(abs(data).max()) if data.size else 0.0,
        "rms": float((data * data).mean() ** 0.5) if data.size else 0.0,
    }


async def live_probe(
    url_base: str,
    wav_path: Path,
    output_dir: Path,
    *,
    trailing_silence_s: float,
    wait_after_audio_s: float,
) -> dict[str, Any]:
    import aiohttp
    import numpy as np
    import soundfile as sf
    import sphn

    audio, sample_rate = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if audio.ndim != 1:
        audio = audio[:, 0]
    if sample_rate != 24000:
        raise ValueError(f"expected 24kHz input WAV, got {sample_rate}")

    params = {"deepgram": "1"}
    url = f"{url_base}/api/chat?{urllib.parse.urlencode(params)}"
    event_path = output_dir / "deepgram-live-events.jsonl"
    server_audio_path = output_dir / "server-audio.opus-pages.bin"

    def append_event(payload: dict[str, Any]) -> None:
        with event_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": dt.datetime.now(dt.UTC).isoformat(), **payload}, sort_keys=True) + "\n")

    writer = sphn.OpusStreamWriter(24000)
    server_audio_chunks: list[bytes] = []
    control_events: list[dict[str, Any]] = []
    start = time.monotonic()
    timings: dict[str, float] = {}
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession() as session:
        append_event({"event": "connect_start", "url": url})
        async with session.ws_connect(url, ssl=ssl_ctx, timeout=90, receive_timeout=90) as ws:
            timings["connected_ms"] = round((time.monotonic() - start) * 1000, 2)
            while True:
                msg = await asyncio.wait_for(ws.receive(), timeout=90)
                if msg.type == aiohttp.WSMsgType.BINARY and msg.data and msg.data[0] == 0:
                    timings["handshake_ms"] = round((time.monotonic() - start) * 1000, 2)
                    append_event({"event": "handshake_marker", "elapsed_ms": timings["handshake_ms"]})
                    break
                if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    raise RuntimeError(f"socket closed before handshake: {msg.type} {msg.data!r}")

            async def receive_loop() -> None:
                while True:
                    msg = await ws.receive()
                    if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        append_event({"event": "socket_closed", "type": str(msg.type)})
                        return
                    if msg.type != aiohttp.WSMsgType.BINARY or not msg.data:
                        continue
                    kind = msg.data[0]
                    payload = bytes(msg.data[1:])
                    now_ms = round((time.monotonic() - start) * 1000, 2)
                    if kind == 1:
                        server_audio_chunks.append(payload)
                        if "first_audio_ms" not in timings:
                            timings["first_audio_ms"] = now_ms
                            append_event({"event": "first_audio", "elapsed_ms": now_ms, "bytes": len(payload)})
                    elif kind == 2:
                        if "first_text_ms" not in timings:
                            timings["first_text_ms"] = now_ms
                            append_event({"event": "first_text", "elapsed_ms": now_ms})
                    elif kind == 4:
                        decoded = json.loads(payload.decode("utf-8", errors="replace"))
                        decoded["elapsed_ms"] = now_ms
                        control_events.append(decoded)
                        append_event({"event": "control", **decoded})

            recv_task = asyncio.create_task(receive_loop())
            frame = 1920
            sent_pages = 0
            for offset in range(0, len(audio), frame):
                chunk = audio[offset : offset + frame]
                if len(chunk) < frame:
                    chunk = np.pad(chunk, (0, frame - len(chunk)))
                writer.append_pcm(chunk.astype("float32"))
                pages = writer.read_bytes()
                if pages:
                    await ws.send_bytes(b"\x01" + pages)
                    sent_pages += 1
                await asyncio.sleep(0.08)
            silence_frames = int((trailing_silence_s * 24000) // frame)
            for _ in range(silence_frames):
                writer.append_pcm(np.zeros(frame, dtype="float32"))
                pages = writer.read_bytes()
                if pages:
                    await ws.send_bytes(b"\x01" + pages)
                    sent_pages += 1
                await asyncio.sleep(0.08)
            timings["input_sent_ms"] = round((time.monotonic() - start) * 1000, 2)
            append_event(
                {
                    "event": "input_sent",
                    "elapsed_ms": timings["input_sent_ms"],
                    "sent_pages": sent_pages,
                    "trailing_silence_s": trailing_silence_s,
                }
            )
            await asyncio.sleep(wait_after_audio_s)
            await ws.close()
            await recv_task

    server_audio_path.write_bytes(b"".join(server_audio_chunks))
    asr_events = [event for event in control_events if event.get("event") == "asr_turn_final"]
    grounding_started = [event for event in control_events if event.get("event") == "grounding_started"]
    grounding_complete = [event for event in control_events if event.get("event") == "grounding_complete"]
    queued = [event for event in control_events if event.get("event") == "grounding_stage_queued"]
    return {
        "ok": bool(asr_events and grounding_started and grounding_complete),
        "url": url,
        "timings": timings,
        "sent_pages": sent_pages,
        "control_event_count": len(control_events),
        "control_event_names": [event.get("event") for event in control_events],
        "asr_events": asr_events,
        "grounding_started": grounding_started,
        "grounding_stage_names": [event.get("stage") for event in queued],
        "grounding_complete": grounding_complete,
        "server_audio": {
            "path": str(server_audio_path),
            "chunks": len(server_audio_chunks),
            "bytes": server_audio_path.stat().st_size if server_audio_path.exists() else 0,
        },
        "events_jsonl": str(event_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--url-base", default="ws://127.0.0.1:9008")
    parser.add_argument("--trailing-silence-s", type=float, default=2.0)
    parser.add_argument("--wait-after-audio-s", type=float, default=18.0)
    return parser.parse_args()


def main() -> int:
    ensure_runtime_python()
    args = parse_args()
    output_dir = OUTPUT_ROOT / utc_stamp()
    output_dir.mkdir(parents=True, exist_ok=False)
    total_start = time.monotonic()
    wav_path = synthesize_question_wav(args.question, output_dir)
    probe = asyncio.run(
        live_probe(
            args.url_base,
            wav_path,
            output_dir,
            trailing_silence_s=args.trailing_silence_s,
            wait_after_audio_s=args.wait_after_audio_s,
        )
    )
    receipt = {
        "schema": "personaplex.deepgram_live_probe.v1",
        "status": "PASS" if probe["ok"] else "FAIL",
        "claim_boundary": "Live Deepgram websocket ASR/VAD from Opus user-audio fixture into PersonaPlex wrapper; fixture is synthesized speech, not microphone capture.",
        "deepgram_api_key_set": bool(os.environ.get("DEEPGRAM_API_KEY")),
        "question": args.question,
        "input_wav": wav_metrics(wav_path),
        "probe": probe,
        "total_ms": round((time.monotonic() - total_start) * 1000, 2),
    }
    receipt_path = output_dir / "personaplex-deepgram-live-probe-receipt.json"
    write_json(receipt_path, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path)}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
