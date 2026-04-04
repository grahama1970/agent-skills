"""Particle data loader and state configs for Embry force-ring animation.

Ports STATE_CONFIGS, STATE_RING_CONFIGS, STATE_COLORS from EmbryThinkingIcon.tsx.
Loads particle_data.json and samples ~200 particles for 256px canvas.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# ── Data Loading ─────────────────────────────────────────────

_EMBRY_OS_ROOT = Path(
    os.environ.get("EMBRY_OS_ROOT", Path.home() / "workspace/experiments/embry-os")
)
PARTICLE_DATA_PATH = (
    _EMBRY_OS_ROOT / "apps" / "embry-ui" / "icons" / "v10" / "final" / "particle_data.json"
)

_cache: dict | None = None


def _load_raw() -> dict:
    global _cache
    if _cache is None:
        with open(PARTICLE_DATA_PATH) as f:
            _cache = json.load(f)
    return _cache


def load_ring() -> dict:
    """Return {innerR, outerR} normalized ring radii."""
    return _load_raw()["ring"]


def load_font() -> dict:
    """Return {family, weight, letter, sizeRatio}."""
    return _load_raw()["font"]


def sample_particles(target_size: int = 256) -> list[dict]:
    """Sample particles proportional to canvas size (~200 at 256px)."""
    all_particles = _load_raw()["particles"]
    ratio = min(1, (target_size / 1024) * 2)
    min_particles = 40 if target_size < 64 else 100
    count = max(min_particles, round(len(all_particles) * ratio))
    if count >= len(all_particles):
        return all_particles
    stride = len(all_particles) / count
    return [all_particles[int(i * stride)] for i in range(count)]


def load_stars() -> list[dict]:
    """Return star background data."""
    return _load_raw()["stars"]


# ── State Configs ────────────────────────────────────────────


@dataclass(frozen=True)
class StateConfig:
    radiusMul: float
    charge: float
    breathHz: float
    breathAmp: float
    sparkEvery: int
    dualRing: bool = False
    pulseOut: bool = False
    orbitSpeed: float = 0.0
    converge: bool = False


@dataclass(frozen=True)
class RingConfig:
    width: float
    alpha: float
    dashPattern: list[float] = field(default_factory=list)
    pulseHz: float = 0.0
    pulseAmp: float = 0.0
    rippleCount: int = 0
    rotateSpeed: float = 0.0


@dataclass(frozen=True)
class StateColor:
    particle: tuple[int, int, int]
    glow: tuple[int, int, int]
    glowAlpha: float


STATE_CONFIGS: dict[str, StateConfig] = {
    "idle":         StateConfig(radiusMul=1.0,  charge=-0.15, breathHz=0.15, breathAmp=0.03, sparkEvery=0),
    "listening":    StateConfig(radiusMul=0.65, charge=-0.05, breathHz=0.4,  breathAmp=0.08, sparkEvery=0),
    "thinking":     StateConfig(radiusMul=1.0,  charge=-0.3,  breathHz=1.2,  breathAmp=0.0,  sparkEvery=3, dualRing=True, orbitSpeed=1.5),
    "synthesizing": StateConfig(radiusMul=0.45, charge=-0.4,  breathHz=0.8,  breathAmp=0.06, sparkEvery=3, dualRing=True, converge=True),
    "speaking":     StateConfig(radiusMul=1.0,  charge=-0.2,  breathHz=3.0,  breathAmp=0.08, sparkEvery=4, pulseOut=True),
}

STATE_RING_CONFIGS: dict[str, RingConfig | None] = {
    "idle":         None,
    "listening":    RingConfig(width=3, alpha=0.85, pulseHz=0.8, pulseAmp=6),
    "thinking":     RingConfig(width=3, alpha=0.80, dashPattern=[12, 8], rotateSpeed=1.5),
    "synthesizing": RingConfig(width=5, alpha=0.85, dashPattern=[4, 4], rotateSpeed=-2.0),
    "speaking":     RingConfig(width=3, alpha=0.85, rippleCount=5),
}

STATE_COLORS: dict[str, StateColor] = {
    "idle":         StateColor(particle=(0, 200, 180),  glow=(212, 175, 55),  glowAlpha=0.18),
    "listening":    StateColor(particle=(0, 207, 255),  glow=(0, 207, 255),   glowAlpha=0.25),
    "thinking":     StateColor(particle=(255, 140, 0),  glow=(255, 140, 0),   glowAlpha=0.28),
    "synthesizing": StateColor(particle=(180, 100, 255), glow=(140, 80, 220), glowAlpha=0.32),
    "speaking":     StateColor(particle=(136, 255, 0),  glow=(170, 215, 30),  glowAlpha=0.30),
}

RING_EMERGE_MS = 250
COLOR_TRANSITION_MS = 300

ARIA_LABELS: dict[str, str] = {
    "idle": "Embry is idle",
    "listening": "Embry is listening",
    "thinking": "Embry is thinking",
    "synthesizing": "Embry is synthesizing a response",
    "speaking": "Embry is speaking",
}
