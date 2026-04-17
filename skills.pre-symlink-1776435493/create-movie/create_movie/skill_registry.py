"""
Skill Registry for create-movie.

Provides centralized skill management with:
- Explicit skill mappings with metadata
- Optional vs required skill classification
- Graceful degradation for missing optional skills
- Skill availability checking
"""

import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

console = Console()

# Skill directory paths
SKILL_DIR = Path(__file__).parent.parent
PI_SKILLS_DIR = SKILL_DIR.parent


class SkillRequirement(Enum):
    """Whether a skill is required or optional."""
    REQUIRED = "required"
    OPTIONAL = "optional"


@dataclass
class SkillInfo:
    """Metadata about a skill dependency."""
    name: str
    requirement: SkillRequirement
    description: str
    fallback_behavior: str = "skip"  # skip, warn, error
    timeout_seconds: int = 300  # per-skill subprocess timeout


# Registry of all skills used by create-movie
SKILL_REGISTRY: dict[str, SkillInfo] = {
    # Core skills (required for basic functionality)
    "memory": SkillInfo(
        name="memory",
        requirement=SkillRequirement.REQUIRED,
        description="Memory recall and storage for learnings",
        fallback_behavior="error",
        timeout_seconds=60,
    ),

    # Research/discovery skills (optional enhancements)
    "dogpile": SkillInfo(
        name="dogpile",
        requirement=SkillRequirement.OPTIONAL,
        description="Deep multi-source research aggregator",
        fallback_behavior="warn",
    ),
    "ingest-movie": SkillInfo(
        name="ingest-movie",
        requirement=SkillRequirement.OPTIONAL,
        description="Movie ingestion and search",
        fallback_behavior="skip",
    ),
    "ingest-youtube": SkillInfo(
        name="ingest-youtube",
        requirement=SkillRequirement.OPTIONAL,
        description="YouTube transcript extraction",
        fallback_behavior="skip",
    ),

    # Generation skills (optional but improve quality)
    "create-story": SkillInfo(
        name="create-story",
        requirement=SkillRequirement.OPTIONAL,
        description="Advanced screenplay generation",
        fallback_behavior="warn",
        timeout_seconds=900,
    ),
    "create-image": SkillInfo(
        name="create-image",
        requirement=SkillRequirement.OPTIONAL,
        description="AI image generation",
        fallback_behavior="warn",
    ),
    "create-score": SkillInfo(
        name="create-score",
        requirement=SkillRequirement.OPTIONAL,
        description="Scene-specific music generation",
        fallback_behavior="skip",
        timeout_seconds=1200,
    ),
    "tts-train": SkillInfo(
        name="tts-train",
        requirement=SkillRequirement.OPTIONAL,
        description="Qwen3-TTS voice synthesis",
        fallback_behavior="skip",
        timeout_seconds=120,
    ),

    # Sound design and storyboard skills (optional)
    "create-sound-design": SkillInfo(
        name="create-sound-design",
        requirement=SkillRequirement.OPTIONAL,
        description="SFX selection and placement for scenes",
        fallback_behavior="skip",
    ),
    "create-storyboard": SkillInfo(
        name="create-storyboard",
        requirement=SkillRequirement.OPTIONAL,
        description="Screenplay to animatic conversion",
        fallback_behavior="skip",
    ),

    # Casting skills (optional for character consistency)
    "create-cast": SkillInfo(
        name="create-cast",
        requirement=SkillRequirement.OPTIONAL,
        description="Character casting and identity pack generation",
        fallback_behavior="skip",
    ),
    "discover-talent": SkillInfo(
        name="discover-talent",
        requirement=SkillRequirement.OPTIONAL,
        description="Actor/talent discovery via TMDB",
        fallback_behavior="skip",
    ),

    # Memory/archiving skills (optional)
    "episodic-archiver": SkillInfo(
        name="episodic-archiver",
        requirement=SkillRequirement.OPTIONAL,
        description="Session archiving to episodic memory",
        fallback_behavior="skip",
    ),
    "persona-journal": SkillInfo(
        name="persona-journal",
        requirement=SkillRequirement.OPTIONAL,
        description="Persona journal entries with mood and reflections",
        fallback_behavior="skip",
        timeout_seconds=30,
    ),
    "monitor-episodic-archiver": SkillInfo(
        name="monitor-episodic-archiver",
        requirement=SkillRequirement.OPTIONAL,
        description="Nightly episodic analysis with failure patterns",
        fallback_behavior="skip",
        timeout_seconds=60,
    ),

    # Consumed media (Horus's lived experience)
    "consume-book": SkillInfo(
        name="consume-book",
        requirement=SkillRequirement.OPTIONAL,
        description="Search ingested books for passages and notes",
        fallback_behavior="skip",
        timeout_seconds=30,
    ),
    "consume-movie": SkillInfo(
        name="consume-movie",
        requirement=SkillRequirement.OPTIONAL,
        description="Search ingested movies by subtitle/scene",
        fallback_behavior="skip",
        timeout_seconds=30,
    ),
    "consume-youtube": SkillInfo(
        name="consume-youtube",
        requirement=SkillRequirement.OPTIONAL,
        description="Search ingested YouTube transcripts",
        fallback_behavior="skip",
        timeout_seconds=30,
    ),
    "consume-feed": SkillInfo(
        name="consume-feed",
        requirement=SkillRequirement.OPTIONAL,
        description="RSS feed summaries and world events",
        fallback_behavior="skip",
        timeout_seconds=30,
    ),
    "consume-music": SkillInfo(
        name="consume-music",
        requirement=SkillRequirement.OPTIONAL,
        description="Search ingested music with HMT taxonomy",
        fallback_behavior="skip",
        timeout_seconds=30,
    ),

    # Code understanding (Horus's tools knowledge)
    "treesitter": SkillInfo(
        name="treesitter",
        requirement=SkillRequirement.OPTIONAL,
        description="Code symbol extraction and structure analysis",
        fallback_behavior="skip",
        timeout_seconds=30,
    ),
    "analytics": SkillInfo(
        name="analytics",
        requirement=SkillRequirement.OPTIONAL,
        description="Data schema discovery and trend analysis",
        fallback_behavior="skip",
        timeout_seconds=30,
    ),

    # SFX catalog
    "sfx-catalog": SkillInfo(
        name="sfx-catalog",
        requirement=SkillRequirement.OPTIONAL,
        description="Sound effect search from ArangoDB catalog",
        fallback_behavior="skip",
        timeout_seconds=30,
    ),

    # Quality assessment
    "assess": SkillInfo(
        name="assess",
        requirement=SkillRequirement.OPTIONAL,
        description="Content quality assessment with scoring",
        fallback_behavior="skip",
        timeout_seconds=60,
    ),

    # Infrastructure skills (optional)
    "task-monitor": SkillInfo(
        name="task-monitor",
        requirement=SkillRequirement.OPTIONAL,
        description="Real-time task progress monitoring",
        fallback_behavior="skip",
    ),
    "ops-workstation": SkillInfo(
        name="ops-workstation",
        requirement=SkillRequirement.OPTIONAL,
        description="Hardware detection and management",
        fallback_behavior="skip",
    ),
}


def get_skill_path(skill_name: str) -> Optional[Path]:
    """Get the path to a skill's run.sh, checking multiple locations."""
    # Check .pi/skills/ (project-level)
    project_path = PI_SKILLS_DIR / skill_name / "run.sh"
    if project_path.exists():
        return project_path

    # Check ~/.pi/skills/ (user-level)
    user_path = Path.home() / ".pi" / "skills" / skill_name / "run.sh"
    if user_path.exists():
        return user_path

    # Check ~/.claude/skills/ (Claude Code skills)
    claude_path = Path.home() / ".claude" / "skills" / skill_name / "run.sh"
    if claude_path.exists():
        return claude_path

    return None


def is_skill_available(skill_name: str) -> bool:
    """Check if a skill is available (has a run.sh)."""
    return get_skill_path(skill_name) is not None


def check_skill_availability() -> dict[str, bool]:
    """Check availability of all registered skills."""
    return {name: is_skill_available(name) for name in SKILL_REGISTRY}


def display_skill_status():
    """Display a table of skill availability."""
    table = Table(title="Skill Availability", show_header=True)
    table.add_column("Skill", style="cyan")
    table.add_column("Required", style="yellow")
    table.add_column("Available", style="green")
    table.add_column("Description")

    availability = check_skill_availability()

    for name, info in SKILL_REGISTRY.items():
        available = availability[name]
        req = "Yes" if info.requirement == SkillRequirement.REQUIRED else "No"
        status = "[green]✓[/green]" if available else "[red]✗[/red]"
        table.add_row(name, req, status, info.description[:40])

    console.print(table)


def run_skill(
    skill_name: str,
    args: list[str],
    capture: bool = True,
    allow_missing: bool = True,
) -> dict:
    """
    Run a skill from the registry.

    Args:
        skill_name: Name of the skill to run
        args: Command-line arguments for the skill
        capture: Whether to capture stdout/stderr
        allow_missing: If True, return graceful error for missing optional skills

    Returns:
        dict with stdout, stderr, returncode, or error
    """
    skill_path = get_skill_path(skill_name)
    skill_info = SKILL_REGISTRY.get(skill_name)

    if not skill_path:
        if skill_info:
            if skill_info.requirement == SkillRequirement.REQUIRED and not allow_missing:
                console.print(f"[red]Required skill not found: {skill_name}[/red]")
                return {"error": f"Required skill not found: {skill_name}", "skill": skill_name}

            if skill_info.fallback_behavior == "warn":
                console.print(f"[yellow]Optional skill not available: {skill_name}[/yellow]")
            elif skill_info.fallback_behavior == "skip":
                console.print(f"[dim]Skill not available, skipping: {skill_name}[/dim]")
        else:
            console.print(f"[dim]Unknown skill not found: {skill_name}[/dim]")

        return {"error": f"Skill not found: {skill_name}", "skill": skill_name, "skipped": True}

    cmd = ["bash", str(skill_path)] + args
    cwd = skill_path.parent

    skill_timeout = skill_info.timeout_seconds if skill_info else 300

    # Strip VIRTUAL_ENV to prevent uv venv collision in child processes
    skill_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}

    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=skill_timeout,
            cwd=str(cwd),
            env=skill_env,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Skill timed out after {skill_timeout}s", "skill": skill_name}
    except Exception as e:
        return {"error": str(e), "skill": skill_name}


def ensure_required_skills() -> bool:
    """
    Check that all required skills are available.

    Returns:
        True if all required skills are available, False otherwise.
    """
    missing = []
    for name, info in SKILL_REGISTRY.items():
        if info.requirement == SkillRequirement.REQUIRED:
            if not is_skill_available(name):
                missing.append(name)

    if missing:
        console.print(f"[red]Missing required skills: {', '.join(missing)}[/red]")
        return False
    return True
