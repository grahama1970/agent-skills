#!/usr/bin/env python3
"""FastAPI status service for youtube-transcripts batch monitoring.

Provides HTTP endpoints for cross-project agents to monitor batch job progress.

Usage:
    uv run python status_api.py                    # Start on port 8765
    uv run python status_api.py --port 9000        # Custom port

Endpoints:
    GET /                     - List all known batch jobs
    GET /status/{job_name}    - Get status of specific job
    GET /all                  - Get status of all jobs
"""
import json
import os
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Known batch job locations (can be extended via env var)
DEFAULT_JOBS = {
    "luetin09": "/home/graham/workspace/experiments/pi-mono/run/youtube-transcripts/luetin09",
    "remembrancer": "/home/graham/workspace/experiments/pi-mono/run/youtube-transcripts/remembrancer",
}

app = FastAPI(
    title="YouTube Transcripts Status API",
    description="Monitor batch transcript downloads",
    version="1.0.0",
)

cli = typer.Typer()


def get_job_status(output_dir: str) -> dict:
    """Get status of a batch job from its output directory."""
    output_path = Path(output_dir)
    state_file = output_path / ".batch_state.json"

    if not output_path.exists():
        return {"error": "Output directory not found", "output_dir": str(output_dir)}

    if not state_file.exists():
        return {"error": "No batch state found", "output_dir": str(output_dir)}

    try:
        with open(state_file) as f:
            state = json.load(f)
    except Exception as e:
        return {"error": f"Failed to read state: {e}", "output_dir": str(output_dir)}

    # Count completed files
    json_files = list(output_path.glob("*.json"))
    completed_count = len([f for f in json_files if f.name != ".batch_state.json"])

    # Count total from input file if we can find it
    total = None
    # Try to infer total from parent directory patterns

    return {
        "output_dir": str(output_dir),
        "completed": completed_count,
        "stats": state.get("stats", {}),
        "current_video": state.get("current_video", ""),
        "current_method": state.get("current_method", ""),
        "last_updated": state.get("last_updated", ""),
        "consecutive_failures": state.get("consecutive_failures", 0),
    }


def get_known_jobs() -> dict:
    """Get list of known jobs from env or defaults."""
    jobs = DEFAULT_JOBS.copy()

    # Allow override via env var (JSON format)
    extra_jobs = os.environ.get("YOUTUBE_TRANSCRIPT_JOBS")
    if extra_jobs:
        try:
            jobs.update(json.loads(extra_jobs))
        except json.JSONDecodeError:
            pass

    return jobs


@app.get("/")
async def list_jobs():
    """List all known batch jobs."""
    jobs = get_known_jobs()
    return {
        "jobs": list(jobs.keys()),
        "endpoints": {
            "list": "/",
            "status": "/status/{job_name}",
            "all": "/all",
        }
    }


@app.get("/status/{job_name}")
async def get_status(job_name: str):
    """Get status of a specific batch job."""
    jobs = get_known_jobs()

    if job_name not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found. Known jobs: {list(jobs.keys())}")

    return get_job_status(jobs[job_name])


@app.get("/all")
async def get_all_status():
    """Get status of all batch jobs."""
    jobs = get_known_jobs()

    result = {}
    total_completed = 0
    total_success = 0
    total_failed = 0
    total_whisper = 0

    for name, path in jobs.items():
        status = get_job_status(path)
        result[name] = status
        if "completed" in status:
            total_completed += status["completed"]
            stats = status.get("stats", {})
            total_success += stats.get("success", 0)
            total_failed += stats.get("failed", 0)
            total_whisper += stats.get("whisper", 0)

    return {
        "jobs": result,
        "totals": {
            "completed": total_completed,
            "success": total_success,
            "failed": total_failed,
            "whisper": total_whisper,
        }
    }


@cli.command()
def serve(port: int = typer.Option(8765, "--port", "-p", help="Port to run on")):
    """Start the status API server."""
    print(f"Starting YouTube Transcripts Status API on port {port}")
    print(f"  GET http://localhost:{port}/           - List jobs")
    print(f"  GET http://localhost:{port}/all        - All job status")
    print(f"  GET http://localhost:{port}/status/luetin09  - Specific job")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    cli()
