"""
create-story data models, constants, and utility helpers.

Contains StoryProject dataclass, model/format constants, and the run_skill helper.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

console = Console()

SKILL_DIR = Path(__file__).parent
PI_SKILLS_DIR = SKILL_DIR.parent  # .pi/skills/

# Creative writing models (Chutes only)
CREATIVE_MODELS = {
    "chimera": "tngtech/DeepSeek-TNG-R1T2-Chimera",
    "qwen": "Qwen/Qwen3-235B-A22B-Instruct-2507-TEE",
    "deepseek-r1": "deepseek-ai/DeepSeek-R1-0528-TEE",
    "deepseek-v3": "deepseek-ai/DeepSeek-V3",
    "default": "tngtech/DeepSeek-TNG-R1T2-Chimera",
}

STORY_FORMATS = {
    "story": "Short Story (prose narrative)",
    "screenplay": "Screenplay (Fountain format)",
    "podcast": "Podcast Script (with audio cues)",
    "novella": "Novella (chapters)",
    "flash": "Flash Fiction (<1000 words)",
}


@dataclass
class StoryProject:
    """Represents a story being created."""

    thought: str
    format: str = "story"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    research: dict = field(default_factory=dict)
    drafts: list = field(default_factory=list)
    critiques: list = field(default_factory=list)
    final: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def save(self, path: Path):
        """Save project state to JSON."""
        with open(path, "w") as f:
            json.dump(self.__dict__, f, indent=2, default=str)

    @classmethod
    def load(cls, path: Path) -> "StoryProject":
        """Load project state from JSON."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)


def run_skill(skill_name: str, args: list[str], capture: bool = True) -> dict:
    """Run a skill from .pi/skills/ and return result."""
    skill_path = PI_SKILLS_DIR / skill_name / "run.sh"

    if not skill_path.exists():
        return {"error": f"Skill not found: {skill_name}", "path": str(skill_path)}

    cmd = ["bash", str(skill_path)] + args
    console.print(f"[dim]Running: {skill_name} {' '.join(args[:2])}...[/dim]")

    # Strip VIRTUAL_ENV to prevent uv venv collision in child processes
    skill_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}

    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=600,
            cwd=str(PI_SKILLS_DIR / skill_name),
            env=skill_env,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Skill timed out", "skill": skill_name}
    except Exception as e:
        return {"error": str(e), "skill": skill_name}
