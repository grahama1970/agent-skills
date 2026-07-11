from __future__ import annotations

from pathlib import Path
from typing import Any

from .fal_utils import subscribe
from .io_utils import extract_url_from_result, write_json


def generate_elevenlabs_tts(
    *,
    contract: dict[str, Any],
    shot: dict[str, Any],
    out_dir: str | Path,
    voice_override: str | None = None,
    with_logs: bool = True,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    voice_cfg = shot.get("voice", {})
    model_id = voice_cfg.get("elevenlabs_model", "fal-ai/elevenlabs/tts/eleven-v3")
    text = shot.get("tts_text_elevenlabs") or shot.get("tts_text_plain") or shot["dialogue"]

    request = {
        "text": text,
        "voice": voice_override or voice_cfg.get("elevenlabs_voice", "Aria"),
        "stability": voice_cfg.get("stability", 0.55),
        "timestamps": voice_cfg.get("timestamps", True),
        "output_format": voice_cfg.get("output_format", "mp3_44100_128"),
        "seed": voice_cfg.get("seed", 1701),
    }

    # Some fal/ElevenLabs schemas accept similarity_boost and speed, but keep them optional.
    if "similarity_boost" in voice_cfg:
        request["similarity_boost"] = voice_cfg["similarity_boost"]
    if "speed" in voice_cfg:
        request["speed"] = voice_cfg["speed"]

    result = subscribe(model_id, request, with_logs=with_logs)
    audio_url = extract_url_from_result(result, "audio")

    payload = {
        "schema_version": "persona_dream_tts_result.v0.2",
        "backend": "fal_elevenlabs_v3",
        "contract_experiment_id": contract.get("experiment_id"),
        "shot_id": shot["shot_id"],
        "model_id": model_id,
        "request": request,
        "result": result,
        "audio_url": audio_url,
        "timestamps": result.get("timestamps"),
    }

    write_json(out_dir / "tts.json", payload)
    return payload
