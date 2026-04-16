"""
Registry of all phase exports for create-movie skill.

Consolidates re-exports from every phase submodule so that __init__.py
stays thin (≤20 non-blank non-comment lines).
"""

from .hardware import (
    HardwareProfile,
    detect_hardware,
    select_model_variant,
    display_hardware_profile,
)
from .research import research_topic
from .script import generate_script, parse_screenplay_to_scenes, load_preset
from .build_tools import build_tools_for_script, analyze_tool_requirements
from .generate import generate_assets, load_identity_packs
from .assemble import assemble_movie, assemble_mp4, assemble_html
from .study import study_topic, study_all_topics, list_topics, FILMMAKING_TOPICS
from .learn import store_learnings, extract_learnings
from .archiving import archive_creation_session
from .dream_mode import (
    DreamPersona,
    fetch_day_residue,
    augment_dream_style,
    render_shots,
    render_veo_shots,
    load_identity_packs_for_veo,
)

__all__ = [
    # Hardware (Phase 0)
    "HardwareProfile",
    "detect_hardware",
    "select_model_variant",
    "display_hardware_profile",
    # Research (Phase 1)
    "research_topic",
    # Script (Phase 2)
    "generate_script",
    "parse_screenplay_to_scenes",
    "load_preset",
    # Build Tools (Phase 3)
    "build_tools_for_script",
    "analyze_tool_requirements",
    # Generate (Phase 4)
    "generate_assets",
    "load_identity_packs",
    # Assemble (Phase 5)
    "assemble_movie",
    "assemble_mp4",
    "assemble_html",
    # Study (Pre-phase)
    "study_topic",
    "study_all_topics",
    "list_topics",
    "FILMMAKING_TOPICS",
    # Learn (Phase 6)
    "store_learnings",
    "extract_learnings",
    # Archiving
    "archive_creation_session",
    # Dream Mode
    "DreamPersona",
    "fetch_day_residue",
    "augment_dream_style",
    "render_shots",
    "render_veo_shots",
    "load_identity_packs_for_veo",
]
