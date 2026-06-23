#!/usr/bin/env python3
from __future__ import annotations
"""PersonaPlex P8 Deepgram WebSocket probe with deterministic fallback.

The only truthful real-service proof is `real_deepgram=true`, which requires a
live WebSocket attempt and at least one Deepgram message with `speech_final=true`.
When the API key, dependency, audio file, or endpoint is unavailable, this module
writes a deterministic transcript fixture and records `real_deepgram=false`.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-3&encoding=linear16&sample_rate=16000&channels=1"
    "&interim_results=false&smart_format=false&endpointing=1000"
)
DEFAULT_SANITY_ROOT = Path("/tmp/personaplex-p6-p7-p8-sanity")
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "p6_p7_p8" / "deterministic_transcript_fixture.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(value, sort_keys=True) + "\n")


def load_transcript_fixture() -> dict[str, Any]:
    if FIXTURE_PATH.exists():
        return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {
        "schema": "personaplex.p8.deepgram_fixture.v1",
        "transcript": "Focus on the west gateway.",
        "speech_final": True,
        "source": "built_in_fixture",
    }


def _transcript_from_message(message: Mapping[str, Any]) -> str:
    channel = message.get("channel") if isinstance(message, Mapping) else None
    if not isinstance(channel, Mapping):
        return ""
    alternatives = channel.get("alternatives")
    if not isinstance(alternatives, list) or not alternatives:
        return ""
    first = alternatives[0]
    if not isinstance(first, Mapping):
        return ""
    transcript = first.get("transcript")
    return transcript if isinstance(transcript, str) else ""


async def _run_deepgram_ws_once(
    *,
    url: str,
    api_key: str,
    audio_path: Path,
    events_jsonl: Path,
    timeout: float,
    header_kwarg_name: str,
) -> dict[str, Any]:
    import websockets  # type: ignore[import-not-found]

    headers = {"Authorization": f"Token {api_key}"}
    kwargs = {header_kwarg_name: headers, "max_size": 4 * 1024 * 1024}
    observed_speech_final = False
    transcript_parts: list[str] = []
    message_count = 0
    started = time.monotonic()

    async with websockets.connect(url, **kwargs) as ws:  # noqa: S310 - user configured endpoint.
        with audio_path.open("rb") as fh:
            while True:
                chunk = fh.read(8192)
                if not chunk:
                    break
                await ws.send(chunk)
        await ws.send(json.dumps({"type": "CloseStream"}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            wait_for = max(0.05, min(1.0, deadline - time.monotonic()))
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=wait_for)
            except asyncio.TimeoutError:
                continue
            message_count += 1
            text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
            try:
                parsed: Any = json.loads(text)
            except json.JSONDecodeError:
                parsed = {"raw": text}
            append_jsonl(events_jsonl, {"created_at_utc": utc_now_iso(), "deepgram_event": parsed})
            if isinstance(parsed, Mapping):
                fragment = _transcript_from_message(parsed)
                if fragment:
                    transcript_parts.append(fragment)
                if parsed.get("speech_final") is True:
                    observed_speech_final = True
                    break

    return {
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
        "message_count": message_count,
        "observed_speech_final": observed_speech_final,
        "transcript": " ".join(part for part in transcript_parts if part).strip(),
    }


async def _run_deepgram_ws(
    *,
    url: str,
    api_key: str,
    audio_path: Path,
    events_jsonl: Path,
    timeout: float,
) -> dict[str, Any]:
    try:
        return await _run_deepgram_ws_once(
            url=url,
            api_key=api_key,
            audio_path=audio_path,
            events_jsonl=events_jsonl,
            timeout=timeout,
            header_kwarg_name="additional_headers",
        )
    except TypeError as exc:
        if "additional_headers" not in str(exc):
            raise
        return await _run_deepgram_ws_once(
            url=url,
            api_key=api_key,
            audio_path=audio_path,
            events_jsonl=events_jsonl,
            timeout=timeout,
            header_kwarg_name="extra_headers",
        )


def _fallback_receipt(
    *,
    out_dir: Path,
    reason: str,
    attempted: bool,
    live_websocket: bool = False,
    deepgram_url: str | None = None,
    audio_metadata: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fixture = load_transcript_fixture()
    fixture_path = write_json(out_dir / "p8-deterministic-transcript-fixture-used.json", fixture)
    receipt: dict[str, Any] = {
        "schema": "personaplex.p8.deepgram_websocket_attempt.v1",
        "created_at_utc": utc_now_iso(),
        "attempted": attempted,
        "live_websocket": live_websocket,
        "real_deepgram": False,
        "real_gpu_personaplex": False,
        "deepgram_mode": "deterministic_transcript_fixture",
        "observed_speech_final": False,
        "speech_final_required": True,
        "fallback_used": True,
        "unavailable_reason": reason,
        "deepgram_url": deepgram_url,
        "transcript": fixture.get("transcript", "Focus on the west gateway."),
        "fixture_path": str(fixture_path),
        "audio_metadata": dict(audio_metadata or {}),
        "claim_boundary": "Fixture transcript is not real Deepgram proof because real_deepgram=false.",
    }
    if extra:
        receipt.update(dict(extra))
    write_json(out_dir / "p8-deepgram-receipt.json", receipt)
    return receipt


def deepgram_websocket_probe(
    *,
    audio_path: str | Path | None = None,
    deepgram_url: str | None = None,
    api_key: str | None = None,
    out_dir: str | Path = DEFAULT_SANITY_ROOT,
    timeout: float = 10.0,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    url = (deepgram_url or os.environ.get("PERSONAPLEX_DEEPGRAM_URL") or os.environ.get("DEEPGRAM_URL") or DEFAULT_DEEPGRAM_URL).strip()
    key = api_key if api_key is not None else os.environ.get("DEEPGRAM_API_KEY", "")
    events_jsonl = out / "p8-deepgram-events.jsonl"

    if not key:
        return _fallback_receipt(out_dir=out, reason="missing_deepgram_api_key", attempted=False, deepgram_url=url)

    try:
        import websockets  # noqa: F401  # type: ignore[import-not-found]
    except Exception as exc:
        return _fallback_receipt(
            out_dir=out,
            reason="websockets_package_unavailable",
            attempted=False,
            deepgram_url=url,
            extra={"dependency_error": f"{type(exc).__name__}:{exc}"},
        )

    if not audio_path:
        return _fallback_receipt(out_dir=out, reason="audio_path_not_configured", attempted=False, deepgram_url=url)
    audio = Path(audio_path)
    if not audio.exists() or not audio.is_file():
        return _fallback_receipt(out_dir=out, reason="audio_path_not_found", attempted=False, deepgram_url=url, audio_metadata={"path": str(audio)})

    audio_metadata = {
        "path": str(audio),
        "sha256": sha256_file(audio),
        "size_bytes": audio.stat().st_size,
    }
    started = time.monotonic()
    try:
        live = asyncio.run(_run_deepgram_ws(url=url, api_key=key, audio_path=audio, events_jsonl=events_jsonl, timeout=timeout))
    except Exception as exc:
        return _fallback_receipt(
            out_dir=out,
            reason="deepgram_websocket_error",
            attempted=True,
            live_websocket=False,
            deepgram_url=url,
            audio_metadata=audio_metadata,
            extra={"websocket_error": f"{type(exc).__name__}:{exc}", "duration_ms": round((time.monotonic() - started) * 1000, 3)},
        )

    observed = bool(live.get("observed_speech_final"))
    if not observed:
        return _fallback_receipt(
            out_dir=out,
            reason="speech_final_not_observed",
            attempted=True,
            live_websocket=True,
            deepgram_url=url,
            audio_metadata=audio_metadata,
            extra=live,
        )

    receipt = {
        "schema": "personaplex.p8.deepgram_websocket_attempt.v1",
        "created_at_utc": utc_now_iso(),
        "attempted": True,
        "live_websocket": True,
        "real_deepgram": True,
        "real_gpu_personaplex": False,
        "deepgram_mode": "live_deepgram_websocket",
        "observed_speech_final": True,
        "speech_final_required": True,
        "fallback_used": False,
        "deepgram_url": url,
        "events_jsonl": str(events_jsonl),
        "audio_metadata": audio_metadata,
        "transcript": live.get("transcript") or "",
        "message_count": live.get("message_count", 0),
        "duration_ms": live.get("duration_ms"),
        "claim_boundary": "Deepgram proof only; GPU PersonaPlex owner-loop proof remains deferred.",
    }
    write_json(out / "p8-deepgram-receipt.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PersonaPlex P8 live Deepgram WebSocket probe")
    parser.add_argument("--out-dir", default=str(DEFAULT_SANITY_ROOT))
    parser.add_argument("--audio-path", default=os.environ.get("PERSONAPLEX_P8_AUDIO_PATH"))
    parser.add_argument("--deepgram-url", default=None)
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("PERSONAPLEX_DEEPGRAM_TIMEOUT", "10")))
    parser.add_argument("--require-real", action="store_true", help="Exit 2 unless real_deepgram=true.")
    args = parser.parse_args(argv)
    receipt = deepgram_websocket_probe(
        audio_path=args.audio_path,
        deepgram_url=args.deepgram_url,
        out_dir=args.out_dir,
        timeout=args.timeout,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.require_real and not receipt.get("real_deepgram"):
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
