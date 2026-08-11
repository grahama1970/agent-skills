"""Load local non-secret dotenv configuration for captcha skill commands.

Inputs: the installed skill root and any local ``.env`` file beneath it.
Outputs: process environment updates performed by ``python-dotenv``.
Failure modes: missing dotenv files are ignored; malformed dotenv values follow
python-dotenv parsing behavior.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_skill_dotenv() -> None:
    """Load a skill-local ``.env`` file without overriding existing variables."""

    skill_root = Path(__file__).resolve().parents[2]
    load_dotenv(skill_root / ".env", override=False)
