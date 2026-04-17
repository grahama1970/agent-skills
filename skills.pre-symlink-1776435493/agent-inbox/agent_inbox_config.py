#!/usr/bin/env python3
"""Shared configuration for agent-inbox dispatcher modules.

Contains model registry, directory paths, and project registry access.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger


def load_model_registry() -> Dict[str, List[str]]:
    """Load model registry from config or defaults."""
    registry_path = Path(os.environ.get("AGENT_INBOX_DIR", Path.home() / ".agent-inbox")) / "models.json"
    defaults = {
        "pi": ["pi"],
        "sonnet": ["claude", "--model", "sonnet"],
        "opus-4.5": ["claude", "--model", "opus"],
        "codex-5.2": ["codex", "--model", "gpt-5.2-codex"],
        "codex-5.2-high": ["codex", "--model", "gpt-5.2-codex", "--reasoning", "high"],
    }

    if registry_path.exists():
        try:
            custom = json.loads(registry_path.read_text())
            # Merge: customs override defaults
            defaults.update(custom)
            return defaults
        except Exception as e:
            print(f"Warning: Failed to load models.json: {e}")
            return defaults

    return defaults


# Model to CLI command mapping
MODEL_COMMANDS: Dict[str, List[str]] = load_model_registry()

# Inbox directory configuration
INBOX_DIR = Path(os.environ.get("AGENT_INBOX_DIR", Path.home() / ".agent-inbox"))
REGISTRY_FILE = INBOX_DIR / "projects.json"
LOG_DIR = INBOX_DIR / "logs"


def _load_registry() -> Dict[str, str]:
    """Load project registry."""
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text())
        except Exception as e:
            logger.debug("JSON parse failed: {}", e)
    return {}


def get_project_path(project_name: str) -> Optional[Path]:
    """Get filesystem path for a registered project.

    Args:
        project_name: Name of the project

    Returns:
        Path to project directory, or None if not registered
    """
    registry = _load_registry()
    path_str = registry.get(project_name)
    if path_str:
        return Path(path_str)
    return None
