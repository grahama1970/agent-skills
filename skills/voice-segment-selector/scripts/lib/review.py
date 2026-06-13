"""Human review helpers."""

from __future__ import annotations

import json
from pathlib import Path


def append_decision(job_dir: Path, clip_id: str, decision: str, reviewer: str = "human") -> None:
    if decision not in {"accept", "reject", "maybe"}:
        raise ValueError("decision must be accept, reject, or maybe")
    path = job_dir / "decisions.jsonl"
    row = {"id": clip_id, "decision": decision, "reviewer": reviewer}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def serve_review(job_dir: Path, host: str = "127.0.0.1", port: int = 8791) -> None:
    try:
        from fastapi import FastAPI
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install review extras: uv sync --extra review") from exc

    candidates = []
    for line in (job_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            candidates.append(json.loads(line))

    app = FastAPI(title="voice-segment-selector review")

    @app.get("/api/candidates")
    def list_candidates():
        return candidates

    @app.post("/api/decide/{clip_id}/{decision}")
    def decide(clip_id: str, decision: str):
        append_decision(job_dir, clip_id, decision)
        return {"ok": True, "id": clip_id, "decision": decision}

    @app.get("/")
    def index():
        return {
            "job_dir": str(job_dir),
            "instructions": "Use /api/candidates and POST /api/decide/{id}/{accept|reject|maybe}",
        }

    uvicorn.run(app, host=host, port=port, log_level="info")
