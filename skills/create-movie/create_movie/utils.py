"""
Utility functions for create-movie skill.

Note: run_skill is now provided by skill_registry.
This module re-exports it for backward compatibility.
"""

# Re-export from skill_registry for backward compatibility
from .skill_registry import run_skill, PI_SKILLS_DIR, SKILL_DIR

__all__ = ["run_skill", "PI_SKILLS_DIR", "SKILL_DIR"]
