"""Environment loading helpers for Hack.

Hack reads a small set of operator environment values for bounded worker
configuration. Load dotenv files once at process startup so environment-backed
configuration is explicit and testable.
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_hack_dotenv() -> None:
    """Load repository and skill-local dotenv files without overriding env."""
    skill_dir = Path(__file__).parent.resolve()
    repo_root = skill_dir.parents[1]
    for env_path in (repo_root / ".env", skill_dir / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False)


__all__ = ["load_hack_dotenv"]
