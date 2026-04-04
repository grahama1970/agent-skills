"""create-score: Scene music generation via ACE-Step Docker with HMT integration."""

from .engine import generate_scene_score, start_service, stop_service, is_service_available  # noqa: F401
from .bridge_prompts import (  # noqa: F401
    get_all_bridges, get_bridges_for_episode, augment_prompt_for_bridges, extract_bridges_from_prompt,
)
from .task_monitor import ScoreMonitor, start_generation, end_generation  # noqa: F401
from .schemas import ScoreResult, HMTTaxonomy  # noqa: F401
