"""
ACE-Step FastAPI Server.

Endpoints:
- GET /healthz - Health check
- POST /generate - Submit generation job
- GET /jobs/{id} - Get job status
- GET /outputs/{filename} - Download output file
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from engine import GenerationParams, get_engine

# Configure logging
logger.add(
    "/app/logs/server.log",
    rotation="100 MB",
    retention="7 days",
    level=os.environ.get("LOG_LEVEL", "INFO"),
)

app = FastAPI(
    title="ACE-Step Music Generation",
    description="Generate scene music via ACE-Step",
    version="0.1.0",
)


# === Models ===

class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class Job:
    job_id: str
    state: JobState
    params: GenerationParams
    created_at: datetime
    output_path: Optional[Path] = None
    error: Optional[str] = None


class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="Text prompt for music generation")
    tags: Optional[str] = Field(None, description="Comma-separated tags")
    lyrics: Optional[str] = Field(None, description="Structured lyrics")
    instrumental: bool = Field(True, description="Instrumental only")
    duration_s: float = Field(30.0, ge=1.0, le=300.0, description="Duration in seconds")
    steps: int = Field(27, ge=1, le=400, description="Inference steps")
    seed: int = Field(-1, description="Seed (-1 for random)")
    cfg_scale: float = Field(4.0, ge=0.0, le=20.0, description="Guidance scale")
    format: str = Field("wav", description="Output format: wav, mp3, flac")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Extra params")


class GenerateResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    state: str
    detail: Optional[str] = None
    output_url: Optional[str] = None


# === State ===

jobs: Dict[str, Job] = {}
job_queue: asyncio.Queue[str] = asyncio.Queue()
worker_task: Optional[asyncio.Task] = None


# === Lifecycle ===

@app.on_event("startup")
async def startup():
    """Initialize engine and start worker."""
    global worker_task

    # Create logs directory
    Path("/app/logs").mkdir(parents=True, exist_ok=True)

    # Load model in background
    logger.info("Starting ACE-Step server...")
    engine = get_engine()

    # Start worker
    worker_task = asyncio.create_task(job_worker())

    # Preload model
    await asyncio.get_event_loop().run_in_executor(None, engine.load)
    logger.info("Server ready")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global worker_task
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


# === Worker ===

async def job_worker():
    """Background worker that processes jobs from the queue."""
    logger.info("Job worker started")
    engine = get_engine()

    while True:
        try:
            job_id = await job_queue.get()
            job = jobs.get(job_id)

            if not job:
                logger.warning("Job {} not found", job_id)
                continue

            logger.info("Processing job {}", job_id)
            job.state = JobState.RUNNING

            try:
                # Run generation in executor to avoid blocking
                loop = asyncio.get_event_loop()
                output_path = await loop.run_in_executor(
                    None, engine.generate, job.params
                )

                job.output_path = output_path
                job.state = JobState.DONE
                logger.info("Job {} completed: {}", job_id, output_path)

            except Exception as e:
                logger.error("Job {} failed: {}", job_id, e)
                job.state = JobState.ERROR
                job.error = str(e)

        except asyncio.CancelledError:
            logger.info("Job worker cancelled")
            break
        except Exception as e:
            logger.error("Worker error: {}", e)
            await asyncio.sleep(1)


# === Endpoints ===

@app.get("/healthz")
async def healthz():
    """Health check endpoint."""
    engine = get_engine()
    return {
        "ok": engine.is_ready(),
        "jobs_queued": job_queue.qsize(),
        "jobs_total": len(jobs),
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate(
    background_tasks: BackgroundTasks,
    json_data: Optional[str] = Form(None, alias="json"),
    reference_audio_file: Optional[UploadFile] = File(None),
    source_audio_file: Optional[UploadFile] = File(None),
    # Direct form fields (if not using json)
    prompt: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    duration_s: float = Form(30.0),
    steps: int = Form(27),
    seed: int = Form(-1),
    cfg_scale: float = Form(4.0),
    format: str = Form("wav"),
):
    """Submit a music generation job."""
    # Parse request from JSON or form fields
    if json_data:
        try:
            data = json.loads(json_data)
            req = GenerateRequest(**data)
        except Exception as e:
            raise HTTPException(400, f"Invalid JSON: {e}")
    elif prompt:
        req = GenerateRequest(
            prompt=prompt,
            tags=tags,
            duration_s=duration_s,
            steps=steps,
            seed=seed,
            cfg_scale=cfg_scale,
            format=format,
        )
    else:
        raise HTTPException(400, "Missing prompt")

    # Handle file uploads
    reference_audio_path: Optional[Path] = None
    if reference_audio_file:
        reference_audio_path = Path(f"/tmp/ref_{uuid.uuid4().hex[:8]}.wav")
        async with aiofiles.open(reference_audio_path, "wb") as f:
            content = await reference_audio_file.read()
            await f.write(content)

    # Create job
    job_id = str(uuid.uuid4())
    params = GenerationParams(
        prompt=req.prompt,
        tags=req.tags,
        lyrics=req.lyrics,
        instrumental=req.instrumental,
        duration_s=req.duration_s,
        steps=req.steps,
        seed=req.seed,
        cfg_scale=req.cfg_scale,
        format=req.format,
        reference_audio_path=reference_audio_path,
        extra=req.extra,
    )

    job = Job(
        job_id=job_id,
        state=JobState.QUEUED,
        params=params,
        created_at=datetime.utcnow(),
    )
    jobs[job_id] = job

    # Queue job
    await job_queue.put(job_id)
    logger.info("Job {} queued (queue size: {})", job_id, job_queue.qsize())

    return GenerateResponse(job_id=job_id)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str):
    """Get job status."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    output_url = None
    if job.state == JobState.DONE and job.output_path:
        output_url = f"/outputs/{job.output_path.name}"

    return JobStatusResponse(
        job_id=job.job_id,
        state=job.state.value,
        detail=job.error,
        output_url=output_url,
    )


@app.get("/outputs/{filename}")
async def get_output(filename: str):
    """Download generated output file."""
    # Sanitize filename
    safe_filename = Path(filename).name
    output_path = Path("/app/outputs") / safe_filename

    if not output_path.exists():
        raise HTTPException(404, "Output not found")

    media_type = "audio/wav"
    if safe_filename.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif safe_filename.endswith(".flac"):
        media_type = "audio/flac"

    return FileResponse(output_path, media_type=media_type, filename=safe_filename)


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "ACE-Step Music Generation",
        "version": "0.1.0",
        "endpoints": {
            "health": "GET /healthz",
            "generate": "POST /generate",
            "job_status": "GET /jobs/{job_id}",
            "download": "GET /outputs/{filename}",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
