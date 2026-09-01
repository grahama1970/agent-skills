#!/usr/bin/env python3
"""Render one live Chatterbox sample for analyzer evals."""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8018/synthesize-batch"
HOST_LOG_ROOT = Path("/home/graham/workspace/experiments/chatterbox/logs")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-receipt", required=True, type=Path)
    ap.add_argument("--out-audio-path", required=True, type=Path)
    ap.add_argument("--url", default=DEFAULT_URL)
    args = ap.parse_args()
    payload = {
        "answer_text": "[sniff] [sniff] ... give me a second. This is tender, and I can keep going.",
        "label": "agentic-analyze-chatterbox-emotions-live",
        "use_blessed_qra_cache": False,
        "asr_verify": False,
        "voice_delivery": {"tone": "grief_safe", "emotion_realization": "audible"},
        "render_chunks": [
            {"text": "[sniff] [sniff] ...", "pause_after_ms": 1400, "tone": "grief_safe", "role": "collect_herself"},
            {"text": "give me a second. This is tender, and I can keep going.", "pause_after_ms": 0, "tone": "grief_safe", "role": "recover"},
        ],
    }
    req = urllib.request.Request(
        args.url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        receipt = json.load(resp)
    args.out_receipt.parent.mkdir(parents=True, exist_ok=True)
    args.out_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not receipt.get("ok"):
        raise SystemExit(f"BLOCKED_LIVE_CHATTERBOX_RENDER failed_gates={receipt.get('failed_gates')}")
    container_audio = str(receipt.get("finished_response_audio") or "")
    if not container_audio.startswith("/out/"):
        raise SystemExit(f"BLOCKED_UNEXPECTED_AUDIO_PATH {container_audio}")
    audio = HOST_LOG_ROOT / container_audio.removeprefix("/out/")
    if not audio.is_file():
        raise SystemExit(f"BLOCKED_AUDIO_NOT_FOUND {audio}")
    args.out_audio_path.write_text(str(audio) + "\n", encoding="utf-8")
    print(audio)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
