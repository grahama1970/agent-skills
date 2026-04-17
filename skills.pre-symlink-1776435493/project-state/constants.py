"""Shared constants and path definitions for project-state skill.

Centralises all filesystem paths, daemon socket addresses, document file lists,
and best-practice skill names used across the assessment pipeline.
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

EMBRY_OS = Path(os.environ.get(
    "EMBRY_OS_ROOT",
    Path.home() / "workspace" / "experiments" / "embry-os",
))
PI_SKILLS = Path(os.environ.get(
    "PI_SKILLS_ROOT",
    Path.home() / "workspace" / "experiments" / "pi-mono" / ".pi" / "skills",
))
SHADOW_JSONL = Path.home() / ".pi" / "assistant" / "shadow.jsonl"
TRAINING_DIR = Path.home() / ".pi" / "assistant" / "training_data"
CLASSIFIERS_DIR = Path.home() / ".pi" / "models" / "classifiers"
REGISTRY_PATH = PI_SKILLS / "assistant" / "model_registry.json"
MEMORY_SKILL = PI_SKILLS / "memory" / "run.sh"
DOGPILE_SKILL = PI_SKILLS / "dogpile" / "run.sh"
CREATE_FIGURE_SKILL = PI_SKILLS / "create-figure" / "run.sh"
ARXIV_SKILL = PI_SKILLS / "arxiv" / "run.sh"
EMBRY_YAML = EMBRY_OS / "embry.yaml"

# ── Daemon sockets ───────────────────────────────────────────────────────────

DAEMON_SOCKETS = {
    "state": "/run/user/1000/embry/state.sock",
    "voice": "/run/user/1000/embry/voice.sock",
    "sparta": "/run/user/1000/embry/sparta.sock",
    "memory": "/run/user/1000/embry/memory.sock",
    "inference": "/run/user/1000/embry/inference.sock",
    "datalake": "/run/user/1000/embry/datalake.sock",
    "discord": "/run/user/1000/embry/discord.sock",
}

# ── Documentation and best-practice lists ────────────────────────────────────

DOC_FILES = [
    "README.md", "docs/CONTEXT.md", "docs/DEPLOYMENT.md",
    "docs/DESIGN_SYSTEM.md",
]

BEST_PRACTICE_SKILLS = [
    "best-practices-python", "best-practices-react",
    "best-practices-skills", "best-practices-kde",
]

# ── Optional YAML import ─────────────────────────────────────────────────────

try:
    import yaml  # noqa: F401
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
