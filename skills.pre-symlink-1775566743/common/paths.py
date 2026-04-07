"""Shared paths — single source of truth for project layout and storage.

All skills MUST use these paths instead of hardcoding absolute paths.
Override via environment variables for testing or alternate machines.

Key variables:
    SKILLS_DIR      — .pi/skills/ root  (always resolved relative to this file)
    PROJECT_ROOT    — pi-mono repo root (SKILLS_DIR.parent.parent)
    HOME_DIR        — current user home  (Path.home())
    EMBRY_STORAGE   — large storage mount (env EMBRY_STORAGE, default /mnt/storage12tb)
    SHARED_ARTIFACTS — shared agent artifacts on EMBRY_STORAGE
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "SHARED_ARTIFACTS",
    "SHADOW_FILE",
    "SUBGRAPH_FEEDBACK_FILE",
    "METRICS_FILE",
    "SYNTHESIS_DIR",
    "BATTLE_SHADOW_FILE",
    "SKILL_LAB_DIR",
    "PERSONAS_YAML",
]

# ---------------------------------------------------------------------------
# Core layout (relative to this file — never hardcoded)
# ---------------------------------------------------------------------------

SKILLS_DIR = Path(__file__).resolve().parent.parent          # .pi/skills/
PROJECT_ROOT = SKILLS_DIR.parent.parent                      # pi-mono/
HOME_DIR = Path.home()                                       # /home/<user>

# ---------------------------------------------------------------------------
# Large-storage mount (configurable)
# ---------------------------------------------------------------------------

EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))

# ---------------------------------------------------------------------------
# Shared agent artifacts
# ---------------------------------------------------------------------------

SHARED_ARTIFACTS = Path(
    os.environ.get(
        "AGENT_ARTIFACTS_DIR",
        str(EMBRY_STORAGE / "media/agents/shared"),
    )
)

SHADOW_FILE = SHARED_ARTIFACTS / "shadow.jsonl"
SUBGRAPH_FEEDBACK_FILE = SHARED_ARTIFACTS / "subgraph_feedback.jsonl"
METRICS_FILE = SHARED_ARTIFACTS / "metrics.jsonl"
SYNTHESIS_DIR = SHARED_ARTIFACTS / "synthesis"

# Per-skill artifact dirs
BATTLE_SHADOW_FILE = SHARED_ARTIFACTS / "battle_shadow.jsonl"
SKILL_LAB_DIR = SHARED_ARTIFACTS / "skill-lab"

# Persona registry (single source of truth)
PERSONAS_YAML = SKILLS_DIR / "monitor-personas" / "personas.yaml"


def skill_dir(name: str) -> Path:
    """Return the directory for a named skill, e.g. skill_dir("review-pdf")."""
    return SKILLS_DIR / name
