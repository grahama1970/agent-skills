"""Registry of skills with misuse guards and their file paths.

Maps skill names to their _misuse_guard.py locations so /monitor-misuse
can propose and apply corrections directly to the source files.
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass


@dataclass
class SkillMisuseGuard:
    """Location and metadata for a skill's misuse guard."""
    skill_name: str
    guard_path: Path
    corrections_var: str = "COLLECTION_CORRECTIONS"  # Variable name in file


# Known skills with misuse guards
SKILL_GUARDS: dict[str, SkillMisuseGuard] = {
    "memory": SkillMisuseGuard(
        skill_name="memory",
        guard_path=Path("${HOME}/workspace/experiments/memory/src/graph_memory/service/app/_misuse_guard.py"),
        corrections_var="COLLECTION_CORRECTIONS",
    ),
    # Add more skills as they adopt misuse guards:
    # "scillm": SkillMisuseGuard(
    #     skill_name="scillm",
    #     guard_path=Path("${HOME}/workspace/experiments/scillm/src/scillm/proxy/_misuse_guard.py"),
    #     corrections_var="MODEL_CORRECTIONS",
    # ),
}


def get_skill_guard(skill_name: str) -> SkillMisuseGuard | None:
    """Get the misuse guard info for a skill."""
    return SKILL_GUARDS.get(skill_name)


def list_skills_with_guards() -> list[str]:
    """List all skills that have registered misuse guards."""
    return list(SKILL_GUARDS.keys())


def discover_guards() -> dict[str, Path]:
    """Discover misuse guard files across known skill locations.

    Searches common patterns:
    - ~/.claude/skills/*/src/*/_misuse_guard.py
    - ~/workspace/experiments/*/src/*/_misuse_guard.py
    """
    discovered = {}

    search_patterns = [
        Path.home() / ".claude/skills",
        Path.home() / "workspace/experiments",
    ]

    for base in search_patterns:
        if not base.exists():
            continue
        for guard_file in base.rglob("_misuse_guard.py"):
            # Extract skill name from path
            # e.g., ${HOME}/workspace/experiments/memory/src/... → memory
            parts = guard_file.parts
            for i, part in enumerate(parts):
                if part in ("experiments", "skills") and i + 1 < len(parts):
                    skill_name = parts[i + 1]
                    discovered[skill_name] = guard_file
                    break

    return discovered
