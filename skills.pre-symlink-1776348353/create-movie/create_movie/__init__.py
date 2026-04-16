"""create-movie skill package."""

from .models import MovieProject
from .exceptions import Phase, PhaseError, SkillError, ConfigError, ResourceError
from .skill_registry import (
    run_skill, is_skill_available, check_skill_availability,
    display_skill_status, ensure_required_skills, SKILL_REGISTRY,
)
from .phases import *  # noqa: F401, F403 — phases defines __all__

__all__ = [
    "MovieProject",
    "Phase", "PhaseError", "SkillError", "ConfigError", "ResourceError",
    "run_skill", "is_skill_available", "check_skill_availability",
    "display_skill_status", "ensure_required_skills", "SKILL_REGISTRY",
    # Phase exports re-exported via phases.__all__:
    "HardwareProfile", "detect_hardware", "select_model_variant", "display_hardware_profile",
    "research_topic",
    "generate_script", "parse_screenplay_to_scenes", "load_preset",
    "build_tools_for_script", "analyze_tool_requirements",
    "generate_assets", "load_identity_packs", "assemble_movie", "assemble_mp4", "assemble_html",
    "study_topic", "study_all_topics", "list_topics", "FILMMAKING_TOPICS", "store_learnings", "extract_learnings",
]
