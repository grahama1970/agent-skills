"""Image generation orchestration for /ask."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import httpx

from .ask_config import SCILLM_API_KEY, SCILLM_BASE_URL


IMAGE_MIME_BY_FORMAT = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "webp": "image/webp",
}


def _output_paths(output: str | None, *, run_dir: Path | None, count: int, output_format: str) -> list[Path]:
    extension = output_format.lower().lstrip(".") or "png"
    if extension == "jpg":
        extension = "jpeg"

    if output:
        output_path = Path(output).expanduser()
        if output_path.suffix:
            if count == 1:
                return [output_path]
            return [
                output_path.with_name(f"{output_path.stem}-{index:03d}{output_path.suffix}")
                for index in range(1, count + 1)
            ]
        return [output_path / f"image-{index:03d}.{extension}" for index in range(1, count + 1)]

    base = (run_dir or Path.cwd() / ".ask_artifacts" / "image-generation") / "images"
    return [base / f"image-{index:03d}.{extension}" for index in range(1, count + 1)]


def _response_error(response: httpx.Response) -> RuntimeError:
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    return RuntimeError(f"scillm image generation failed ({response.status_code}): {payload}")


def generate_image_with_scillm(
    prompt: str,
    *,
    run_state: Any,
    model: str = "gpt-image-2",
    size: str = "auto",
    quality: str = "auto",
    count: int = 1,
    output: str | None = None,
    output_format: str = "png",
    timeout: float = 300.0,
    scillm_base_url: str = SCILLM_BASE_URL,
    scillm_api_key: str = SCILLM_API_KEY,
) -> dict[str, Any]:
    """Generate images through scillm and write response artifacts."""
    if not prompt.strip():
        raise ValueError("image prompt is empty")
    if count < 1:
        raise ValueError("image count must be >= 1")

    normalized_format = output_format.lower().lstrip(".") or "png"
    if normalized_format == "jpg":
        normalized_format = "jpeg"
    if normalized_format not in IMAGE_MIME_BY_FORMAT:
        raise ValueError("image output format must be one of: png, jpeg, webp")

    run_dir = Path(run_state.run_dir) if getattr(run_state, "run_dir", None) else None
    output_paths = _output_paths(output, run_dir=run_dir, count=count, output_format=normalized_format)
    ask_id = getattr(run_state, "ask_id", "")
    payload = {
        "model": model,
        "prompt": prompt,
        "n": count,
        "size": size,
        "quality": quality,
        "response_format": "b64_json",
        "output_format": normalized_format,
        "scillm_metadata": {
            "ask_id": ask_id,
            "mode": "image-generation",
        },
    }
    headers = {
        "Authorization": f"Bearer {scillm_api_key}",
        "X-Caller-Skill": "ask",
    }

    run_state.step_started("image_generation", model=model, size=size, quality=quality, count=count)
    started = time.monotonic()
    response = httpx.post(
        f"{scillm_base_url.rstrip('/')}/v1/images/generations",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise _response_error(response)
    data = response.json()
    images = data.get("data")
    if not isinstance(images, list) or len(images) < count:
        raise RuntimeError("scillm image response did not include the requested data[] items")

    artifacts: dict[str, str] = {}
    files: list[dict[str, Any]] = []
    for index, item in enumerate(images[:count], start=1):
        if not isinstance(item, dict) or not item.get("b64_json"):
            raise RuntimeError(f"scillm image data[{index - 1}] did not include b64_json")
        output_path = output_paths[index - 1]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(str(item["b64_json"])))
        artifact_key = f"image_{index:03d}"
        artifacts[artifact_key] = str(output_path)
        files.append(
            {
                "index": index - 1,
                "path": str(output_path),
                "mime_type": IMAGE_MIME_BY_FORMAT[normalized_format],
                "revised_prompt": item.get("revised_prompt", ""),
            }
        )

    manifest = {
        "ask_id": ask_id,
        "prompt": prompt,
        "model": data.get("model") or model,
        "size": size,
        "quality": quality,
        "count": count,
        "output_format": normalized_format,
        "created": data.get("created"),
        "files": files,
        "scillm": data.get("scillm", {}),
    }
    manifest_path = (run_dir or output_paths[0].parent) / "image_generation.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n")
    artifacts["image_manifest"] = str(manifest_path)
    run_state.add_artifacts(artifacts)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    run_state.step_finished("image_generation", files=len(files), manifest=str(manifest_path), elapsed_ms=elapsed_ms)

    return {
        "question": prompt,
        "scope": "image-generation",
        "items": [],
        "bridges_found": [],
        "answer": f"Generated {len(files)} image file(s).",
        "auto_learned": False,
        "hybrid_mode": False,
        "image_generation": manifest,
        "artifacts": artifacts,
    }
