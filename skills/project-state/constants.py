"""Shared constants and path definitions for project-state skill.

Centralises filesystem paths, daemon socket addresses, document file lists, and
best-practice skill names used across the assessment pipeline.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib

from dotenv import load_dotenv

load_dotenv()

# ── Paths ────────────────────────────────────────────────────────────────────

def _resolve_project_root() -> Path:
    """Resolve the project checkout this skill should inspect."""
    raw = os.environ.get("PROJECT_STATE_ROOT") or os.environ.get("EMBRY_OS_ROOT")
    return Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()


def _read_pyproject_name(root: Path) -> str | None:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        data = tomllib.loads(pyproject.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    name = data.get("project", {}).get("name")
    return str(name) if name else None


def _read_package_name(root: Path) -> str | None:
    package_json = root / "package.json"
    if not package_json.exists():
        return None
    try:
        data = json.loads(package_json.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    name = data.get("name")
    return str(name) if name else None


def detect_project_name(root: Path | None = None) -> str:
    """Derive a stable report name from project metadata or directory name."""
    target = root or PROJECT_ROOT
    env_name = os.environ.get("PROJECT_STATE_NAME")
    if env_name:
        return env_name
    return _read_pyproject_name(target) or _read_package_name(target) or target.name


def is_embry_project(root: Path | None = None) -> bool:
    """Return true when the target root has Embry OS project structure."""
    target = root or PROJECT_ROOT
    return (target / "embry.yaml").exists() or target.name in {"embry-os", "embry_os"}


PROJECT_ROOT = _resolve_project_root()
PROJECT_NAME = detect_project_name(PROJECT_ROOT)
PROJECT_PROFILE = "embry" if is_embry_project(PROJECT_ROOT) else "generic"

# Legacy alias kept for external callers that import EMBRY_OS from this module.
EMBRY_OS = PROJECT_ROOT
PI_SKILLS = Path(os.environ.get(
    "PI_SKILLS_ROOT",
    Path(__file__).resolve().parents[1],
)).expanduser().resolve()
SHADOW_JSONL = Path.home() / ".pi" / "assistant" / "shadow.jsonl"
TRAINING_DIR = Path.home() / ".pi" / "assistant" / "training_data"
CLASSIFIERS_DIR = Path.home() / ".pi" / "models" / "classifiers"
REGISTRY_PATH = PI_SKILLS / "assistant" / "model_registry.json"
MEMORY_SKILL = PI_SKILLS / "memory" / "run.sh"
DOGPILE_SKILL = PI_SKILLS / "dogpile" / "run.sh"
BRAVE_SEARCH_SKILL = PI_SKILLS / "brave-search" / "run.sh"
GITHUB_SEARCH_SKILL = PI_SKILLS / "github-search" / "run.sh"
CREATE_FIGURE_SKILL = PI_SKILLS / "create-figure" / "run.sh"
ARXIV_SKILL = PI_SKILLS / "arxiv" / "run.sh"
EMBRY_YAML = PROJECT_ROOT / "embry.yaml"

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

REQUIRED_DOC_FILES = ["README.md"]
OPTIONAL_DOC_FILES = [
    "AGENTS.md",
    "CONTEXT.md",
    "PROJECT_KNOWLEDGE.md",
    "docs/PROJECT_KNOWLEDGE.md",
    "docs/STATE_OF_PROJECT.md",
    "docs/CONTEXT.md",
]
EMBRY_DOC_FILES = ["docs/DEPLOYMENT.md", "docs/DESIGN_SYSTEM.md"]
DOC_FILES = REQUIRED_DOC_FILES + OPTIONAL_DOC_FILES + (EMBRY_DOC_FILES if is_embry_project() else [])

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
