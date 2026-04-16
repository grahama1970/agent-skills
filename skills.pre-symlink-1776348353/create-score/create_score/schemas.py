"""
Request/response schemas for the ACE-Step Docker service.

Keep these stable even if the backend engine changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GenerateRequest(BaseModel):
    """Request payload for music generation."""

    prompt: str = Field(..., description="Text prompt describing desired music/audio.")
    tags: Optional[str] = Field(None, description="Comma-separated tags/genres/scene descriptors.")
    lyrics: Optional[str] = Field(None, description="Structured lyrics text, if supported.")
    instrumental: bool = Field(True, description="Generate instrumental output if True.")
    duration_s: float = Field(30.0, ge=1.0, le=300.0, description="Target duration in seconds.")
    steps: int = Field(27, ge=1, le=400, description="Inference steps / sampling steps.")
    seed: int = Field(-1, description="Seed. -1 means random.")
    cfg_scale: float = Field(4.0, ge=0.0, le=20.0, description="Guidance scale (a.k.a cfg).")

    sampler: Optional[str] = Field(None, description="Sampler name (backend-dependent).")
    scheduler: Optional[str] = Field(None, description="Scheduler name (backend-dependent).")

    # Output format
    format: str = Field("wav", description="Output format: wav, mp3, flac.")

    # Optional conditioning
    reference_audio: Optional[str] = Field(
        None, description="Server-side path or uploaded file handle for reference audio."
    )
    source_audio: Optional[str] = Field(
        None, description="Server-side path or uploaded file handle for audio2audio source."
    )

    # Passthrough for future parameters
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary passthrough params.")


class GenerateResponse(BaseModel):
    """Response from submitting a generation request."""

    job_id: str


class JobStatus(BaseModel):
    """Status of a generation job."""

    job_id: str
    state: str  # queued|running|done|error
    detail: Optional[str] = None
    output_url: Optional[str] = None


class HMTTaxonomy(BaseModel):
    """Horus Music Taxonomy metadata for generated scores."""

    bridge_attributes: List[str] = Field(default_factory=list)
    collection_tags: Dict[str, List[str]] = Field(default_factory=dict)
    tactical_tags: List[str] = Field(default_factory=list)
    episodic_associations: List[str] = Field(default_factory=list)
    confidence: float = Field(0.5)


class ScoreResult(BaseModel):
    """Result of a scene score generation."""

    output_path: Path
    prompt: str = Field(..., description="Final prompt (possibly augmented with bridge keywords).")
    original_prompt: str = Field(..., description="Original prompt before augmentation.")
    seed: int
    duration_s: float
    format: str
    hmt: HMTTaxonomy
    episode_association: Optional[str] = None
    reference_audio: Optional[Path] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
