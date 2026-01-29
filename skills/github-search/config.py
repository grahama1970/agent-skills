"""Configuration and constants for GitHub Search skill.

This module contains:
- Skill integration paths
- Default configuration values
- Console instance for rich output
"""
from pathlib import Path

try:
    from rich.console import Console
except ImportError:
    Console = None

# Skill directory paths
SKILLS_DIR = Path(__file__).resolve().parents[1]
TREESITTER_SKILL = SKILLS_DIR / "treesitter"
TAXONOMY_SKILL = SKILLS_DIR / "taxonomy"

# Default limits
DEFAULT_REPO_LIMIT = 5
DEFAULT_CODE_LIMIT = 5
DEFAULT_ISSUE_LIMIT = 5
DEFAULT_FILE_MAX_SIZE = 10000

# Command timeout (seconds)
DEFAULT_TIMEOUT = 60

# Default search paths for code search
DEFAULT_SEARCH_PATHS = ["src/", "lib/", "core/", "pkg/", "internal/"]

# Language extension mappings
EXTENSION_TO_LANGUAGE = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "go": "go",
    "rs": "rust",
    "java": "java",
    "rb": "ruby",
    "c": "c",
    "cpp": "cpp",
    "cc": "cpp",
}

LANGUAGE_TO_SUFFIX = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "go": ".go",
    "rust": ".rs",
    "java": ".java",
    "ruby": ".rb",
    "c": ".c",
    "cpp": ".cpp",
}

# Console instance (lazy initialization)
_console = None


def get_console() -> "Console":
    """Get or create the Rich console instance."""
    global _console
    if _console is None:
        if Console is not None:
            _console = Console()
        else:
            raise ImportError("Rich is not installed. Run: pip install rich")
    return _console
