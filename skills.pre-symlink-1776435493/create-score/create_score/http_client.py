"""
HTTP client for the Dockerized ACE-Step service.

Handles:
- Submitting generation requests with file uploads
- Polling job status
- Downloading output files
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

from .schemas import GenerateRequest, GenerateResponse, JobStatus


def submit_generate(
    base_url: str,
    req: GenerateRequest,
    reference_audio_path: Optional[Path] = None,
    source_audio_path: Optional[Path] = None,
) -> str:
    """
    Submit a generation request to the ACE-Step service.

    Returns the job_id.
    """
    url = base_url.rstrip("/") + "/generate"

    # Build multipart form data
    files: dict[str, tuple[str, bytes, str]] = {}
    data = req.model_dump(exclude_none=True)

    # Remove extra dict if empty
    if not data.get("extra"):
        data.pop("extra", None)

    # Handle file uploads
    if reference_audio_path and reference_audio_path.exists():
        files["reference_audio_file"] = (
            reference_audio_path.name,
            reference_audio_path.read_bytes(),
            "audio/wav",
        )
        # Remove the path from data since we're uploading the file
        data.pop("reference_audio", None)

    if source_audio_path and source_audio_path.exists():
        files["source_audio_file"] = (
            source_audio_path.name,
            source_audio_path.read_bytes(),
            "audio/wav",
        )
        data.pop("source_audio", None)

    logger.info("POST {} (prompt_len={}, duration={}s)", url, len(req.prompt), req.duration_s)

    with httpx.Client(timeout=60.0) as client:
        if files:
            # Multipart form with files - embed data in 'json' field
            r = client.post(
                url,
                data={"json": json.dumps(data)},
                files=files,
            )
        else:
            # Form data without files - send as form fields, not JSON body
            form_data = {
                "prompt": data.get("prompt", ""),
                "tags": data.get("tags") or "",
                "duration_s": str(data.get("duration_s", 30.0)),
                "steps": str(data.get("steps", 27)),
                "seed": str(data.get("seed", -1)),
                "cfg_scale": str(data.get("cfg_scale", 4.0)),
                "format": data.get("format", "wav"),
            }
            r = client.post(url, data=form_data)

        r.raise_for_status()
        out = GenerateResponse.model_validate(r.json())
        logger.info("Job submitted: {}", out.job_id)
        return out.job_id


def poll_job(base_url: str, job_id: str, timeout_s: int = 900, poll_interval_s: float = 2.0) -> JobStatus:
    """
    Poll a job until it completes or times out.

    Returns the final JobStatus.
    """
    url = base_url.rstrip("/") + f"/jobs/{job_id}"
    deadline = time.time() + timeout_s

    logger.info("Polling job {} (timeout: {}s)", job_id, timeout_s)

    with httpx.Client(timeout=10.0) as client:
        while time.time() < deadline:
            try:
                r = client.get(url)
                r.raise_for_status()
                js = JobStatus.model_validate(r.json())

                if js.state == "done":
                    logger.info("Job {} completed", job_id)
                    return js
                elif js.state == "error":
                    logger.error("Job {} failed: {}", job_id, js.detail)
                    return js
                else:
                    logger.debug("Job {} state: {}", job_id, js.state)

            except httpx.HTTPStatusError as e:
                logger.warning("HTTP error polling job: {}", e)
            except Exception as e:
                logger.warning("Error polling job: {}", e)

            time.sleep(poll_interval_s)

    raise TimeoutError(f"Timed out waiting for job {job_id} after {timeout_s}s")


def download_output(base_url: str, output_url: str, out_path: Path) -> Path:
    """
    Download the generated output file.

    Returns the path to the downloaded file.
    """
    # output_url may be absolute or relative
    if output_url.startswith("http://") or output_url.startswith("https://"):
        url = output_url
    else:
        url = base_url.rstrip("/") + output_url

    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading {} -> {}", url, out_path)

    with httpx.Client(timeout=120.0) as client:
        r = client.get(url)
        r.raise_for_status()
        out_path.write_bytes(r.content)

    logger.info("Downloaded {} bytes", out_path.stat().st_size)
    return out_path


def check_health(base_url: str) -> bool:
    """Quick health check."""
    url = base_url.rstrip("/") + "/healthz"
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(url)
            return r.status_code == 200
    except Exception:
        return False
