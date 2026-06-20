"""Generate closed-mouth hum guides via Pixazo ACE-Step API."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx

DEFAULT_SUBMIT_URL = os.environ.get(
    "PIXAZO_ACESTEP_URL",
    "https://gateway.pixazo.ai/ace-step/v1/generate",
)
STATUS_URL_TEMPLATE = "https://gateway.pixazo.ai/v2/requests/status/{request_id}"
HUM_PROMPT = (
    "solo closed-mouth humming only, dry a cappella vocal, no words, no lyrics, "
    "natural breath, soft human performance, preserve melody contour, "
    "no instrumentation, no drums, no backing, no reverb"
)


def _api_key() -> str:
    key = os.environ.get("PIXAZO_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "PIXAZO_API_KEY is not set. Export it in ~/.zshrc or the environment."
        )
    return key


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Ocp-Apim-Subscription-Key": _api_key(),
    }


def _hum_lyrics(duration_s: int) -> str:
    bars = max(4, duration_s // 3)
    line = " ".join(["mmm"] * 6 + ["hm"] * 2)
    body = "\n".join(line for _ in range(bars))
    return f"[verse]\n{body}"


def _poll_result(
    request_id: str,
    *,
    timeout_s: float = 600.0,
    interval_s: float = 8.0,
) -> dict:
    url = STATUS_URL_TEMPLATE.format(request_id=request_id)
    deadline = time.time() + timeout_s
    with httpx.Client(timeout=60.0) as client:
        while time.time() < deadline:
            resp = client.get(url, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
            status = (data.get("status") or "").upper()
            if status == "COMPLETED":
                return data
            if status in {"FAILED", "ERROR"}:
                raise RuntimeError(data.get("error") or data)
            time.sleep(interval_s)
    raise TimeoutError(f"Pixazo ACE-Step timed out after {timeout_s:.0f}s ({request_id})")


def _download_audio(url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
    return out_path


def _trim_audio(src: Path, dst: Path, duration_s: float) -> Path:
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-t", str(duration_s),
            "-ac", "2", "-ar", "44100",
            str(dst),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg trim failed: {(proc.stderr or '')[-300:]}")
    return dst


def generate_hum_guide(
    out_wav: Path,
    *,
    duration_s: int = 20,
    title: str = "",
    prompt: str | None = None,
    submit_url: str | None = None,
) -> Path:
    """Submit ACE-Step XL job, poll, download, and trim to guide length."""
    hum_prompt = prompt or HUM_PROMPT
    if title:
        hum_prompt = f"{hum_prompt} Song feel: {title}."
    dur = max(5, min(int(duration_s), 240))
    submit = submit_url or DEFAULT_SUBMIT_URL
    if "ace-step-xl" in submit:
        payload = {
            "prompt": hum_prompt,
            "lyrics": _hum_lyrics(duration_s),
            "duration": dur,
            "batch_size": 1,
            "thinking": False,
        }
    else:
        payload = {
            "prompt": hum_prompt,
            "lyrics": _hum_lyrics(duration_s),
            "instrumental": False,
            "duration": dur,
            "infer_steps": 25,
            "guidance_scale": 7.5,
        }

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(submit, headers=_headers(), json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Pixazo submit failed ({resp.status_code}): {resp.text[:500]}")
        queued = resp.json()

    request_id = queued.get("request_id")
    if not request_id:
        raise RuntimeError(f"Pixazo response missing request_id: {queued}")

    result = _poll_result(request_id)
    output = result.get("output") or {}
    media_urls = output.get("media_url") or []
    if not media_urls:
        raise RuntimeError(f"Pixazo completed without media_url: {result}")

    raw_path = out_wav.with_name(out_wav.stem + "_pixazo_raw.wav")
    _download_audio(media_urls[0], raw_path)
    return _trim_audio(raw_path, out_wav, float(duration_s))
