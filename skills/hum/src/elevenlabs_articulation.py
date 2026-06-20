"""Generate local articulation-token WAV inventory with ElevenLabs Sound Effects.

This creates diagnostic source samples for the articulated PSOLA renderer. It
does not establish a singing/humming voice model or cache approval.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from .articulated_psola_renderer import REQUIRED_TOKENS

ELEVENLABS_SOUND_GENERATION_URL = "https://api.elevenlabs.io/v1/sound-generation"
DEFAULT_MODEL_ID = "eleven_text_to_sound_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_DURATION_SECONDS = 1.2
DEFAULT_PROMPT_INFLUENCE = 0.72


TOKEN_PROMPTS: dict[str, str] = {
    "hm": "Short close-mic female alto closed-mouth hum texture: 'HM'. One clean non-lexical pulse, no words.",
    "m_held": "Steady held female alto closed-mouth hum texture: 'MMMM'. Smooth sustained tone, no words.",
    "m": "Brief percussive female closed-mouth hum pulse: 'M'. Dry studio sample, no words.",
    "ng": "Nasal female alto hum texture: 'NG'. Sustained velar nasal resonance, no words.",
    "oo": "Rounded deep vowel female hum texture: 'OO'. Soft chest-voice resonance, no words.",
    "hm_to_m": "Female alto texture moving from 'HM' into 'MMMM'. Closed-mouth non-lexical hum, no words.",
    "m_gliss_up": "Closed-mouth female 'MMMM' hum sliding upward in pitch. Smooth glissando, no words.",
    "m_gliss_down": "Closed-mouth female 'MMMM' hum sliding downward in pitch. Smooth glissando, no words.",
    "breathy_m": "Breathy close-mic female closed-mouth hum: 'HMM'. Airy attack, soft m resonance, no words.",
    "m_chant": (
        "Forceful guttural alto hum, percussive Hawaiian war chant texture. "
        "Female chest-voice rhythmic 'TAH-HOO-WAH, TAH-HOO-WAY' energy, but non-lexical closed-mouth m resonance."
    ),
    "sigh": "Soft female nonverbal sigh texture with Hawaiian open-vowel color: 'AH'. No spoken words.",
    "breath": "Quiet close-mic natural breath between chant phrases. No voice, no words.",
}

WAR_CHANT_RIFF_PROMPT = (
    "Forceful, guttural alto hum building in intensity, percussive Hawaiian war chant. "
    "Female voice performing rhythmic 'TAH-HOO-WAH, TAH-HOO-WAY' staccato vocalizations. "
    "High energy, tribal chest-voice resonance, 170 BPM."
)

DEEP_VOWEL_PROMPT = (
    "Rhythmic female chanting with emphasized open vowels: 'AH, EH, EE, OH, OO'. "
    "Guttural percussive breathing between phrases. Authentic Hawaiian phoneme textures, "
    "raw and unpolished, close-mic studio recording."
)


@dataclass(frozen=True)
class GeneratedToken:
    token: str
    text: str
    mp3_path: str
    wav_path: str
    mp3_sha256: str
    wav_sha256: str
    bytes_mp3: int
    bytes_wav: int


@dataclass(frozen=True)
class ArticulationInventoryResult:
    output_dir: str
    samples_dir: str
    manifest_json: str
    receipt_json: str
    token_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _convert_to_wav(input_audio: Path, output_wav: Path, sample_rate: int) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_audio),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        str(output_wav),
    ]
    subprocess.run(cmd, check=True)


def _request_token_audio(
    *,
    client: httpx.Client,
    api_key: str,
    token: str,
    text: str,
    model_id: str,
    output_format: str,
    duration_seconds: float | None,
    prompt_influence: float,
    loop: bool,
    timeout_s: float,
) -> tuple[bytes, dict[str, Any]]:
    body: dict[str, Any] = {
        "text": text,
        "model_id": model_id,
        "prompt_influence": prompt_influence,
        "loop": loop,
    }
    if duration_seconds is not None:
        body["duration_seconds"] = duration_seconds
    response = client.post(
        ELEVENLABS_SOUND_GENERATION_URL,
        params={"output_format": output_format},
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=timeout_s,
    )
    payload = response.content
    receipt = {
        "token": token,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
        "request_id": response.headers.get("request-id") or response.headers.get("x-request-id"),
        "bytes": len(payload),
        "api_key_logged": False,
    }
    if response.status_code >= 400:
        snippet = payload[:300].decode("utf-8", errors="replace")
        raise RuntimeError(f"ElevenLabs token={token} status={response.status_code}: {snippet}")
    return payload, receipt


def generate_elevenlabs_articulation_inventory(
    *,
    output_dir: Path,
    api_key: str | None = None,
    model_id: str = DEFAULT_MODEL_ID,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    sample_rate: int = 44100,
    duration_seconds: float | None = DEFAULT_DURATION_SECONDS,
    prompt_influence: float = DEFAULT_PROMPT_INFLUENCE,
    loop: bool = False,
    timeout_s: float = 180.0,
) -> ArticulationInventoryResult:
    resolved_api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not resolved_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is required, or pass --api-key.")
    if duration_seconds is not None and not 0.5 <= duration_seconds <= 30.0:
        raise RuntimeError("--duration-seconds must be between 0.5 and 30.0.")
    if not 0.0 <= prompt_influence <= 1.0:
        raise RuntimeError("--prompt-influence must be between 0 and 1.")

    raw_dir = output_dir / "elevenlabs_raw"
    samples_dir = output_dir / "samples"
    raw_dir.mkdir(parents=True, exist_ok=True)
    samples_dir.mkdir(parents=True, exist_ok=True)

    generated: list[GeneratedToken] = []
    receipts: list[dict[str, Any]] = []
    with httpx.Client() as client:
        for token in REQUIRED_TOKENS:
            text = TOKEN_PROMPTS[token]
            payload, receipt = _request_token_audio(
                client=client,
                api_key=resolved_api_key,
                token=token,
                text=text,
                model_id=model_id,
                output_format=output_format,
                duration_seconds=duration_seconds,
                prompt_influence=prompt_influence,
                loop=loop,
                timeout_s=timeout_s,
            )
            mp3_path = raw_dir / f"{token}.mp3"
            wav_path = samples_dir / f"{token}.wav"
            mp3_path.write_bytes(payload)
            _convert_to_wav(mp3_path, wav_path, sample_rate)
            generated.append(
                GeneratedToken(
                    token=token,
                    text=text,
                    mp3_path=str(mp3_path.resolve()),
                    wav_path=str(wav_path.resolve()),
                    mp3_sha256=_sha256_file(mp3_path),
                    wav_sha256=_sha256_file(wav_path),
                    bytes_mp3=mp3_path.stat().st_size,
                    bytes_wav=wav_path.stat().st_size,
                )
            )
            receipts.append(receipt)

    manifest_path = output_dir / "elevenlabs_articulation_inventory_manifest.json"
    receipt_path = output_dir / "elevenlabs_articulation_request_receipts.json"
    _write_json(
        manifest_path,
        {
            "schema": "hum.elevenlabs_articulation_inventory.v1",
            "api": "sound-generation",
            "endpoint": ELEVENLABS_SOUND_GENERATION_URL,
            "model_id": model_id,
            "output_format": output_format,
            "sample_rate": sample_rate,
            "duration_seconds": duration_seconds,
            "prompt_influence": prompt_influence,
            "loop": loop,
            "prompt_templates": {
                "war_chant_riff": WAR_CHANT_RIFF_PROMPT,
                "deep_vowel": DEEP_VOWEL_PROMPT,
            },
            "required_tokens": list(REQUIRED_TOKENS),
            "tokens": [asdict(item) for item in generated],
            "scope_note": (
                "Diagnostic Sound Effects articulation inventory for PSOLA rendering only; "
                "requires human listening review and does not approve cache publication."
            ),
        },
    )
    _write_json(
        receipt_path,
        {
            "schema": "hum.elevenlabs_articulation_receipts.v1",
            "api_key_logged": False,
            "receipts": receipts,
        },
    )
    return ArticulationInventoryResult(
        output_dir=str(output_dir.resolve()),
        samples_dir=str(samples_dir.resolve()),
        manifest_json=str(manifest_path.resolve()),
        receipt_json=str(receipt_path.resolve()),
        token_count=len(generated),
    )
