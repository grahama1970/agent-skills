"""lipsync - persona_dream_av_bakeoff.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .fal_utils import subscribe
from .io_utils import extract_url_from_result, write_json


def generate_lipsync(
    *,
    contract: dict[str, Any],
    shot: dict[str, Any],
    lane: str,
    out_dir: str | Path,
    base_video_url: str,
    audio_url: str,
    model_id: str = "fal-ai/kling-video/lipsync/audio-to-video",
    with_logs: bool = True,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    request = {
        "video_url": base_video_url,
        "audio_url": audio_url,
    }

    result = subscribe(model_id, request, with_logs=with_logs)
    video_url = extract_url_from_result(result, "video")

    payload = {
        "schema_version": "persona_dream_lipsync_result.v0.2",
        "contract_experiment_id": contract.get("experiment_id"),
        "shot_id": shot["shot_id"],
        "lane": lane,
        "model_id": model_id,
        "request": request,
        "result": result,
        "video_url": video_url,
    }

    write_json(out_dir / "lipsync.json", payload)
    return payload
