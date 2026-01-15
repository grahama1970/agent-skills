from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ClarifyOption:
    id: str
    label: str
    description: Optional[str] = None


@dataclass
class ClarifyQuestion:
    id: str
    prompt: str
    kind: str = "text"  # text, textarea, single-choice, multi-choice
    options: List[ClarifyOption] = field(default_factory=list)
    docs_link: Optional[str] = None
    artifact_paths: List[str] = field(default_factory=list)
    visual_assets: List[str] = field(default_factory=list)
    required: bool = True
    allow_multiple: bool = False
