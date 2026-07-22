"""Configuration and constants for the GitHub Search skill."""
from pathlib import Path

try:
    from rich.console import Console
except ImportError:
    Console = None

# Skill directory paths
SKILLS_DIR = Path(__file__).resolve().parents[1]
BRAVE_SEARCH_SKILL = SKILLS_DIR / "brave-search"
TREESITTER_SKILL = SKILLS_DIR / "treesitter"
TAXONOMY_SKILL = SKILLS_DIR / "taxonomy"

# Search limits
DEFAULT_REPO_LIMIT = 5
DEFAULT_CODE_LIMIT = 5
DEFAULT_ISSUE_LIMIT = 5
DEFAULT_FILE_MAX_SIZE = 10_000
DEFAULT_BRAVE_CANDIDATES = 12
DEFAULT_EVALUATION_TOP = 3
DEFAULT_MIN_STARS = 0
DEFAULT_MAX_REPO_SIZE_MB = 250

# Command and execution limits
DEFAULT_TIMEOUT = 60
DEFAULT_CLONE_TIMEOUT = 180
DEFAULT_RUN_TIMEOUT = 30
DEFAULT_RUN_MEMORY_MB = 1024
DEFAULT_OUTPUT_LIMIT = 20_000

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
