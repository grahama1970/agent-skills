"""
Data models for create-movie skill.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class MovieProject:
    """Represents a movie project being created."""

    name: str
    prompt: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    research: dict = field(default_factory=dict)
    script: dict = field(default_factory=dict)
    tools: list = field(default_factory=list)
    assets: list = field(default_factory=list)
    output_path: Optional[str] = None

    def save(self, path: Path):
        """Save project state to JSON."""
        with open(path, "w") as f:
            json.dump(self.__dict__, f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "MovieProject":
        """Load project state from JSON."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)
