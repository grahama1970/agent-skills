"""Configuration constants and paths for batch-report skill.

This module centralizes all configuration, paths, and constants used
throughout the batch-report skill.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

# Agent inbox locations - search multiple paths
AGENT_INBOX_PATHS = [
    Path.home() / ".pi/skills/agent-inbox/inbox.py",
    Path.home() / ".claude/skills/agent-inbox/inbox.py",
]
AGENT_INBOX_SCRIPT = next(
    (p for p in AGENT_INBOX_PATHS if p.exists()), AGENT_INBOX_PATHS[0]
)

# Batch config location
BATCH_CONFIG_PATH = Path.home() / ".pi" / "batch-report" / "batch_config.yaml"

# scillm script paths for LLM-based quality gates
SCILLM_SEARCH_PATHS = [
    Path.home() / ".pi/skills/scillm/run.sh",
    Path.home() / ".agent/skills/scillm/run.sh",
]
SCILLM_SCRIPT = next((p for p in SCILLM_SEARCH_PATHS if p.exists()), None)

# Default quality gates when none specified
DEFAULT_QUALITY_GATES = [
    {
        "metric": "success_rate",
        "min": 0.8,
        "severity": "warning",
        "message": "Success rate below 80%",
    }
]


class BatchFormat(str, Enum):
    """Supported batch output formats."""

    extractor = "extractor"
    youtube = "youtube"
    generic = "generic"
    auto = "auto"
