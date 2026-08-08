"""video - persona_dream_av_bakeoff.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .fal_utils import subscribe
from .io_utils import extract_url_from_result, write_json


def generate_or_use_base_video(
    *,
    contract: dict[str, Any],
    shot: dict[str, Any],
    out_dir: str | Path,
    base_video_url: str | None = None,
    model_id: str = "fal-ai/kling-video/v3/standard/text-to-video",
    with_logs: bool = True,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if base_video_url:
        payload = {
            "schema_version": "persona_dream_base_video_result.v0.2",
            "contract_experiment_id": contract.get("experiment_id"),
            "shot_id": shot["shot_id"],
            "backend": "provided_base_video_url",
            "model_id": None,
            "request": None,
            "result": None,
            "video_url": base_video_url,
        }
        write_json(out_dir / "base_video.json", payload)
        return payload

    raw_duration = float(shot.get("end_sec", 5.0)) - float(shot.get("start_sec", 0.0))
    duration = "10" if raw_duration > 7.5 else "5"

    request = {
        "prompt": shot["visual_prompt"],
        "duration": duration,
        "aspect_ratio": "16:9",
        "generate_audio": False,
        "shot_type": "customize",
        "negative_prompt": shot.get("negative_prompt", ""),
        "cfg_scale": 0.5,
    }

    result = subscribe(model_id, request, with_logs=with_logs)
    video_url = extract_url_from_result(result, "video")

    payload = {
        "schema_version": "persona_dream_base_video_result.v0.2",
        "contract_experiment_id": contract.get("experiment_id"),
        "shot_id": shot["shot_id"],
        "backend": "fal_kling_v3_standard_t2v",
        "model_id": model_id,
        "request": request,
        "result": result,
        "video_url": video_url,
    }
    write_json(out_dir / "base_video.json", payload)
    return payload
