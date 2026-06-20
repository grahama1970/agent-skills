"""Generate Orpheus reference clips via the warm infer service."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import httpx

DEFAULT_ORPHEUS_URL = os.environ.get(
    "ORPHEUS_INFER_URL",
    f"http://127.0.0.1:{os.environ.get('ORPHEUS_INFER_PORT', '8767')}",
)
DEFAULT_REF_PROMPT = (
    "This is a clean reference recording for voice conversion. "
    "Please keep the tone steady, natural, and clear. "
    "The voice should be relaxed and consistent."
)


def orpheus_base_url(url: str | None = None) -> str:
    return (url or DEFAULT_ORPHEUS_URL).rstrip("/")


def health_ok(url: str | None = None, timeout: float = 5.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{orpheus_base_url(url)}/health")
            resp.raise_for_status()
            data = resp.json()
            return data.get("status") == "ok" and bool(data.get("warm_runtime"))
    except Exception:
        return False


def make_orpheus_ref(
    out_wav: str | Path,
    *,
    speaker: str,
    orpheus_url: str | None = None,
    prompt: str = DEFAULT_REF_PROMPT,
    timeout: float = 300.0,
) -> Path:
    base = orpheus_base_url(orpheus_url)
    payload = {
        "speaker": speaker,
        "prompt": prompt,
        "temperature": 0.6,
        "top_p": 0.9,
        "repetition_penalty": 1.1,
    }

    out_path = Path(out_wav)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{base}/v1/synthesize", json=payload)
        resp.raise_for_status()
        data = resp.json()
        wav_path = data.get("wav_path")
        if wav_path and Path(wav_path).is_file():
            shutil.copy2(wav_path, out_path)
            return out_path

        dl = client.get(f"{base}/v1/audio/{speaker}/latest.wav")
        dl.raise_for_status()
        out_path.write_bytes(dl.content)
        return out_path
