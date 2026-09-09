# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "httpx", "pydantic", "loguru"]
# ///
"""chatterbox-speak: one-shot voiced line through the live Chatterbox service.

Validates the request and the service receipt with Pydantic, calls
POST /synthesize on the Chatterbox agent server, copies the WAV and writes a
JSON receipt to /mnt/storage12tb/skills/chatterbox-speak/outputs/.
"""

import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import typer
from loguru import logger
from pydantic import BaseModel, ConfigDict, ValidationError

app = typer.Typer(add_completion=False)

BASE_URL = "http://127.0.0.1:8018"
OUT_DIR = Path("/mnt/storage12tb/skills/chatterbox-speak/outputs")
# Container /out is host chatterbox/logs (see docker inspect chatterbox-fork-agent-server)
CONTAINER_OUT = "/out"
HOST_OUT = Path.home() / "workspace/experiments/chatterbox/logs"

ANALYZER = Path.home() / ".pi/agent/skills/analyze-chatterbox-emotions/run.sh"

VOICES = {
    "embry": "/data/embry_ref.wav",
}
INTENSITY = {"low": 0.3, "medium": 0.6, "high": 0.9}


class SpeakRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    ref_audio: str
    tone: str | None = None
    label: str = "chatterbox-speak"
    voice_delivery: dict | None = None


class ServiceReceipt(BaseModel):
    """Minimal typed view of the service response; extra fields kept via model_extra."""

    model_config = ConfigDict(extra="allow")
    ok: bool
    live: bool
    mocked: bool
    audio: str
    duration_seconds: float
    tone: str | None = None


def _fail(msg: str) -> None:
    logger.error(msg)
    raise typer.Exit(code=1)


@app.command()
def voices() -> None:
    """List known voices and the service's live calibrated tones."""
    try:
        health = httpx.get(f"{BASE_URL}/health", timeout=5).json()
        tones = sorted(health.get("tone_calibration", {}))
    except Exception as exc:  # noqa: BLE001
        tones = [f"service unreachable: {exc}"]
    print(json.dumps({"voices": VOICES, "tones": tones}, indent=2))


@app.command()
def speak(
    text: str = typer.Option(..., help="Text to speak; may contain native tags like [sigh]"),
    voice: str = typer.Option("embry", help=f"Named voice: {sorted(VOICES)}"),
    ref_audio: str | None = typer.Option(None, help="Container path to reference WAV (overrides --voice)"),
    tone: str | None = typer.Option(None, help="Calibrated tone, e.g. neutral_warm, firm_boundary"),
    intensity: str | None = typer.Option(None, help="low|medium|high; routes to base-affect backend (tags become literal)"),
    context: str = typer.Option("", help="Grounding note stored in the receipt (does not change rendering)"),
    play: bool = typer.Option(False, help="Play locally via pw-play"),
    analyze: bool = typer.Option(False, help="Run /analyze-chatterbox-emotions on the WAV and embed the result in the receipt"),
) -> None:
    """Render one line and write WAV + receipt."""
    ref = ref_audio or VOICES.get(voice)
    if not ref:
        _fail(f"unknown voice '{voice}'; known: {sorted(VOICES)} (or pass --ref-audio)")
    if intensity is not None and intensity not in INTENSITY:
        _fail(f"intensity must be one of {sorted(INTENSITY)}")

    delivery = None
    if intensity:
        delivery = {"intensity": INTENSITY[intensity], "emotion_realization": "audible"}

    try:
        req = SpeakRequest(text=text, ref_audio=ref, tone=tone, voice_delivery=delivery)
    except ValidationError as exc:
        _fail(exc.json())

    try:
        resp = httpx.post(f"{BASE_URL}/synthesize", json=req.model_dump(exclude_none=True), timeout=300)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        _fail(f"chatterbox service call failed: {exc} {detail[:500]}")

    try:
        receipt = ServiceReceipt.model_validate(resp.json())
    except ValidationError as exc:
        _fail(f"service response failed typed validation: {exc.json()}")
    if not (receipt.ok and receipt.live) or receipt.mocked:
        _fail(f"render not live/ok: ok={receipt.ok} live={receipt.live} mocked={receipt.mocked}")

    host_wav = HOST_OUT / Path(receipt.audio).relative_to(CONTAINER_OUT)
    if not host_wav.is_file() or host_wav.stat().st_size == 0:
        _fail(f"rendered WAV missing/empty on host: {host_wav}")

    run_id = f"{int(time.time())}-{Path(receipt.audio).stem}"
    out = OUT_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    wav_copy = out / host_wav.name
    shutil.copy2(host_wav, wav_copy)

    full = resp.json()
    record = {
        "schema": "chatterbox_speak.receipt.v1",
        "voice": voice,
        "context": context,
        "requested_intensity": intensity,
        "request": req.model_dump(exclude_none=True),
        "wav": str(wav_copy),
        "duration_seconds": receipt.duration_seconds,
        "mocked": receipt.mocked,
        "live": receipt.live,
        "tag_handling": full.get("tag_handling"),
        "affect_effect": full.get("affect_effect"),
        "backend": full.get("backend"),
        "service_receipt": full,
    }
    receipt_path = out / "receipt.json"
    receipt_path.write_text(json.dumps(record, indent=2))

    if analyze:
        proc = subprocess.run(
            [str(ANALYZER), "analyze", "--audio", str(wav_copy), "--json"],
            capture_output=True, text=True, check=False,
        )
        try:
            record["analysis"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            _fail(f"analyzer failed (rc={proc.returncode}): {proc.stderr[:500]}")
        receipt_path.write_text(json.dumps(record, indent=2))

    if play:
        rc = subprocess.run(["pw-play", str(wav_copy)], check=False).returncode
        record["playback"] = {"cmd": f"pw-play {wav_copy}", "returncode": rc}
        receipt_path.write_text(json.dumps(record, indent=2))

    print(json.dumps({"ok": True, "wav": str(wav_copy), "receipt": str(receipt_path),
                      "duration_seconds": receipt.duration_seconds,
                      "backend": (full.get("backend") or {}).get("id"),
                      "tags_interpreted": (full.get("tag_handling") or {}).get("tags_interpreted"),
                      "analysis": (record.get("analysis") or {}).get("affect")}, indent=2))


if __name__ == "__main__":
    app()
