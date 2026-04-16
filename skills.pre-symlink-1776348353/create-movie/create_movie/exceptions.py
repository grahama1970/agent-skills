"""
Custom exceptions for create-movie skill.

Provides structured error handling with phase context.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Phase(Enum):
    """Movie creation phases."""
    HARDWARE = "hardware"
    RESEARCH = "research"
    SCRIPT = "script"
    CASTING = "casting"
    BUILD_TOOLS = "build_tools"
    GENERATE = "generate"
    ASSEMBLE = "assemble"
    LEARN = "learn"
    DREAM = "dream"


@dataclass
class PhaseError(Exception):
    """
    Exception raised during a movie creation phase.

    Provides context about which phase failed and why.
    """
    phase: Phase
    message: str
    details: Optional[str] = None
    recoverable: bool = False

    def __str__(self) -> str:
        base = f"[{self.phase.value}] {self.message}"
        if self.details:
            base += f"\n  Details: {self.details}"
        return base


class SkillError(PhaseError):
    """Exception raised when a skill call fails."""

    def __init__(
        self,
        skill_name: str,
        phase: Phase,
        message: str,
        details: Optional[str] = None,
    ):
        self.skill_name = skill_name
        super().__init__(
            phase=phase,
            message=f"Skill '{skill_name}' failed: {message}",
            details=details,
            recoverable=True,  # Skill errors are often recoverable
        )


class ConfigError(PhaseError):
    """Exception raised for configuration errors."""

    def __init__(self, message: str, phase: Phase = Phase.HARDWARE):
        super().__init__(
            phase=phase,
            message=message,
            recoverable=False,
        )


class ResourceError(PhaseError):
    """Exception raised when required resources are missing."""

    def __init__(self, resource: str, phase: Phase, message: str = ""):
        super().__init__(
            phase=phase,
            message=f"Missing resource: {resource}",
            details=message if message else None,
            recoverable=False,
        )
