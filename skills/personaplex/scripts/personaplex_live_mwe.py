#!/usr/bin/env python3
"""Live PersonaPlex MWE against the running WebSocket server.

This probes the real live server at https://127.0.0.1:8998 instead of using
`moshi.offline`. It still uses a file-based synthesized question so the run is
deterministic and can write a receipt.
"""

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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path("/home/graham/workspace/experiments/agent-skills")
PERSONAPLEX_ROOT = Path("/home/graham/workspace/experiments/personaplex")
PERSONAPLEX_PYTHON = PERSONAPLEX_ROOT / ".venv/bin/python"
BRAVE_RUN = ROOT / "skills/brave-search/run.sh"
MEMORY_URL = "http://127.0.0.1:8601"
OUTPUT_ROOT = Path("/mnt/storage12tb/skills/personaplex/outputs/live-mwe/embry")
VOICE_PROMPT_NAME = "embry-current.pt"
VOICE_PROMPT_SHA256 = "4bbeb9b0d5245f0c30e5d2fc5ad9eaeb2cde58a2a72c4cca4ba6cbcea694feb6"
DEFAULT_QUESTION = (
    "Embry, what is the weather like in Hawaii today, "
    "and how would that make you feel about surfing with Kai?"
)
DEFAULT_BRAVE_QUERY = "Hawaii surf forecast today south swell weather"


def ensure_runtime_python() -> None:
    if PERSONAPLEX_PYTHON.exists() and Path(sys.executable).resolve() != PERSONAPLEX_PYTHON.resolve():
        os.execv(str(PERSONAPLEX_PYTHON), [str(PERSONAPLEX_PYTHON), __file__, *sys.argv[1:]])


def utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def short(value: Any, limit: int = 1000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def timed_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    start = time.monotonic()
    try:
        request = urllib.request.Request(
            f"{MEMORY_URL}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            text = response.read().decode("utf-8", errors="replace")
            status_code = response.status
            content_type = response.headers.get("content-type", "")
        parsed = json.loads(text) if "application/json" in content_type else None
        return {
            "ok": 200 <= status_code < 300,
            "status_code": status_code,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
            "request": payload,
            "json": parsed,
            "text_excerpt": None if parsed is not None else text[:1000],
        }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status_code": exc.code,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
            "request": payload,
            "text_excerpt": exc.read().decode("utf-8", errors="replace")[:1000],
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
            "request": payload,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def run_memory(question: str) -> dict[str, Any]:
    start = time.monotonic()
    result = {
        "intent": timed_post("/intent", {"q": question, "scope": "personaplex", "fast": True}),
        "recall": timed_post(
            "/recall",
            {
                "q": "What memory explains why Embry Lawson reacts to Hawaii, surfing, Kai, and afternoon rain?",
                "k": 4,
                "collections": ["persona_memory"],
                "tags": ["persona:embry"],
            },
        ),
    }
    result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 2)
    return result


def run_brave(query: str, count: int) -> dict[str, Any]:
    start = time.monotonic()
    completed = subprocess.run(
        [
            "bash",
            "-lc",
            f"source ~/.zshrc >/dev/null 2>&1; {BRAVE_RUN} web {json.dumps(query)} --count {count} --json",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=45,
    )
    payload: dict[str, Any] = {
        "ok": completed.returncode == 0,
        "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
        "returncode": completed.returncode,
        "stderr_excerpt": completed.stderr[-1200:],
    }
    try:
        payload["json"] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload["ok"] = False
        payload["stdout_excerpt"] = completed.stdout[:1200]
        payload["error"] = "Brave output was not JSON"
    return payload


def compact_memory(memory: dict[str, Any]) -> str:
    items = ((memory.get("recall") or {}).get("json") or {}).get("items") or []
    for item in items:
        text = item.get("retrieval_text") or item.get("text") or item.get("summary") or item.get("problem")
        if text:
            return short(text, 180)
    return "No strong Embry memory returned."


def compact_brave(brave: dict[str, Any]) -> str:
    results = (brave.get("json") or {}).get("results") or []
    if not results:
        return "No current search result returned."
    top = results[0]
    return short(f"{top.get('title', '')}: {top.get('description', '')}", 220)


def synthesize_question_wav(text: str, output_dir: Path) -> Path:
    raw = output_dir / "user-question-raw.wav"
    wav = output_dir / "user-question-24khz-mono.wav"
    espeak = subprocess.run(["bash", "-lc", "command -v espeak-ng || command -v espeak"], capture_output=True, text=True)
    espeak_path = espeak.stdout.strip().splitlines()[0] if espeak.stdout.strip() else ""
    if not espeak_path:
        raise RuntimeError("missing espeak/espeak-ng")
    subprocess.run([espeak_path, "-w", str(raw), text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
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


def build_prompt(question: str, memory: dict[str, Any], brave: dict[str, Any]) -> str:
    return (
        "You are Embry Lawson. Give one concise grounded reply.\n"
        f"Memory: {compact_memory(memory)}\n"
        f"Search: {compact_brave(brave)}\n"
        "If evidence is limited, say that."
    )


async def live_probe(prompt: str, input_wav: Path, output_dir: Path, *, url_base: str) -> dict[str, Any]:
    import aiohttp
    import numpy as np
    import soundfile as sf
    import sphn

    params = {
        "text_temperature": "0.8",
        "text_topk": "25",
        "audio_temperature": "0.8",
        "audio_topk": "250",
        "pad_mult": "1",
        "text_seed": "42424242",
        "audio_seed": "42424242",
        "repetition_penalty_context": "64",
        "repetition_penalty": "1",
        "text_prompt": prompt,
        "voice_prompt": VOICE_PROMPT_NAME,
    }
    url = f"{url_base}/api/chat?{urllib.parse.urlencode(params)}"
    event_path = output_dir / "live-websocket-events.jsonl"
    output_audio_ogg = output_dir / "server-audio.opus-pages.bin"
    output_text_path = output_dir / "server-text-tokens.json"

    def event(payload: dict[str, Any]) -> None:
        with event_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": dt.datetime.now(dt.UTC).isoformat(), **payload}, sort_keys=True) + "\n")

    audio, sample_rate = sf.read(str(input_wav), dtype="float32", always_2d=False)
    if audio.ndim != 1:
        audio = audio[:, 0]
    if sample_rate != 24000:
        raise ValueError(f"expected 24kHz input WAV, got {sample_rate}")

    writer = sphn.OpusStreamWriter(24000)
    server_audio_chunks: list[bytes] = []
    text_tokens: list[str] = []
    start = time.monotonic()
    timings: dict[str, float] = {}
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    async with aiohttp.ClientSession() as session:
        event({"event": "connect_start", "prompt_chars": len(prompt), "url_redacted": f"{url_base}/api/chat?...voice_prompt={VOICE_PROMPT_NAME}"})
        async with session.ws_connect(url, ssl=ssl_ctx, timeout=60, receive_timeout=30) as ws:
            timings["connected_ms"] = round((time.monotonic() - start) * 1000, 2)
            event({"event": "socket_open", "elapsed_ms": timings["connected_ms"]})
            pre_handshake_count = 0
            while True:
                msg = await asyncio.wait_for(ws.receive(), timeout=45)
                if msg.type == aiohttp.WSMsgType.BINARY and msg.data and msg.data[0] == 0:
                    timings["handshake_ms"] = round((time.monotonic() - start) * 1000, 2)
                    event({"event": "handshake", "elapsed_ms": timings["handshake_ms"]})
                    break
                pre_handshake_count += 1
                if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    raise RuntimeError(f"socket closed before handshake: {msg.type} {msg.data!r}")
                if pre_handshake_count <= 5:
                    event({"event": "pre_handshake_message", "type": str(msg.type), "bytes": len(msg.data) if isinstance(msg.data, (bytes, bytearray)) else None})

            async def receive_loop() -> None:
                while True:
                    msg = await ws.receive()
                    if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        event({"event": "socket_closed", "type": str(msg.type)})
                        return
                    if msg.type != aiohttp.WSMsgType.BINARY or not msg.data:
                        continue
                    kind = msg.data[0]
                    payload = bytes(msg.data[1:])
                    now_ms = round((time.monotonic() - start) * 1000, 2)
                    if kind == 1:
                        if "first_audio_ms" not in timings:
                            timings["first_audio_ms"] = now_ms
                            event({"event": "first_audio", "elapsed_ms": now_ms, "bytes": len(payload)})
                        server_audio_chunks.append(payload)
                    elif kind == 2:
                        token = payload.decode("utf-8", errors="replace")
                        if "first_text_ms" not in timings:
                            timings["first_text_ms"] = now_ms
                            event({"event": "first_text", "elapsed_ms": now_ms, "token": token})
                        text_tokens.append(token)
                    else:
                        event({"event": "server_message", "kind": kind, "elapsed_ms": now_ms, "bytes": len(payload)})

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
                await asyncio.sleep(0.02)
            timings["input_sent_ms"] = round((time.monotonic() - start) * 1000, 2)
            event({"event": "input_sent", "elapsed_ms": timings["input_sent_ms"], "sent_pages": sent_pages})
            await asyncio.sleep(4.0)
            await ws.close()
            await recv_task

    output_audio_ogg.write_bytes(b"".join(server_audio_chunks))
    write_json(output_text_path, text_tokens)
    timings["total_ms"] = round((time.monotonic() - start) * 1000, 2)
    return {
        "ok": bool(text_tokens or server_audio_chunks),
        "url_base": url_base,
        "prompt_chars": len(prompt),
        "timings": timings,
        "sent_input_wav": wav_metrics(input_wav),
        "server_text_tokens": {
            "path": str(output_text_path),
            "count": len(text_tokens),
            "joined_preview": short("".join(text_tokens), 500),
        },
        "server_audio": {
            "path": str(output_audio_ogg),
            "chunks": len(server_audio_chunks),
            "bytes": output_audio_ogg.stat().st_size if output_audio_ogg.exists() else 0,
        },
        "events_jsonl": str(event_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--brave-query", default=DEFAULT_BRAVE_QUERY)
    parser.add_argument("--brave-count", type=int, default=3)
    parser.add_argument("--url-base", default="wss://127.0.0.1:8998")
    return parser.parse_args()


def main() -> int:
    ensure_runtime_python()
    args = parse_args()
    total_start = time.monotonic()
    output_dir = OUTPUT_ROOT / utc_stamp()
    output_dir.mkdir(parents=True, exist_ok=False)
    timings: dict[str, float] = {}

    stage = time.monotonic()
    memory = run_memory(args.question)
    timings["memory_total_ms"] = round((time.monotonic() - stage) * 1000, 2)

    stage = time.monotonic()
    brave = run_brave(args.brave_query, args.brave_count)
    timings["brave_total_ms"] = round((time.monotonic() - stage) * 1000, 2)

    stage = time.monotonic()
    prompt = build_prompt(args.question, memory, brave)
    timings["prompt_build_ms"] = round((time.monotonic() - stage) * 1000, 2)
    prompt_path = output_dir / "live-compact-prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    stage = time.monotonic()
    input_wav = synthesize_question_wav(args.question, output_dir)
    timings["question_wav_synthesis_ms"] = round((time.monotonic() - stage) * 1000, 2)

    stage = time.monotonic()
    probe = asyncio.run(live_probe(prompt, input_wav, output_dir, url_base=args.url_base))
    timings["personaplex_live_probe_ms"] = round((time.monotonic() - stage) * 1000, 2)
    timings["total_script_ms"] = round((time.monotonic() - total_start) * 1000, 2)
    retrieval = {"memory": memory, "brave": brave}
    write_json(output_dir / "retrieval.json", retrieval)
    receipt = {
        "schema": "personaplex.live_mwe.v1",
        "status": "PASS" if probe.get("ok") and memory["recall"].get("ok") and brave.get("ok") else "FAIL",
        "claim_boundary": "live WebSocket probe against preloaded server; not production answer gate",
        "voice_prompt": {"server_filename": VOICE_PROMPT_NAME, "sha256": VOICE_PROMPT_SHA256},
        "question": args.question,
        "prompt_path": str(prompt_path),
        "timings": timings,
        "memory_recall_ok": memory["recall"].get("ok") and bool((memory["recall"].get("json") or {}).get("items")),
        "brave_search_ok": brave.get("ok") and bool((brave.get("json") or {}).get("results")),
        "live_probe": probe,
    }
    receipt_path = output_dir / "personaplex-live-mwe-receipt.json"
    write_json(receipt_path, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path)}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
