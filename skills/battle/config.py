"""
Battle Skill - Configuration
Constants, paths, environment variables, and skill references.
"""
from pathlib import Path

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
SKILL_DIR = Path(__file__).parent.resolve()
SKILLS_DIR = SKILL_DIR.parent
BATTLES_DIR = SKILL_DIR / "battles"
REPORTS_DIR = SKILL_DIR / "reports"
WORKTREES_DIR = SKILL_DIR / "worktrees"

# -----------------------------------------------------------------------------
# Sibling Skills
# -----------------------------------------------------------------------------
HACK_SKILL = SKILLS_DIR / "hack"
ANVIL_SKILL = SKILLS_DIR / "anvil"
MEMORY_SKILL = SKILLS_DIR.parent.parent / ".agent" / "skills" / "memory"
TASK_MONITOR_SKILL = SKILLS_DIR / "task-monitor"
DOGPILE_SKILL = SKILLS_DIR.parent.parent / ".agent" / "skills" / "dogpile"
TAXONOMY_SKILL = SKILLS_DIR.parent.parent / ".agent" / "skills" / "taxonomy"

# -----------------------------------------------------------------------------
# Scoring Constants (AIxCC-style)
# -----------------------------------------------------------------------------
VULN_DISCOVERY_SCORE = 1.0
EXPLOIT_PROOF_SCORE = 0.5
SUCCESSFUL_PATCH_SCORE = 3.0
TIME_DECAY_FACTOR = 0.1

SEVERITY_MULTIPLIERS = {
    "critical": 2.0,
    "high": 1.5,
    "medium": 1.0,
    "low": 0.5,
}

# -----------------------------------------------------------------------------
# Default Configuration
# -----------------------------------------------------------------------------
DEFAULT_MAX_ROUNDS = 1000
DEFAULT_CHECKPOINT_INTERVAL = 10
OVERNIGHT_ROUNDS = 1000
OVERNIGHT_CHECKPOINT_INTERVAL = 50
DEFAULT_RESEARCH_BUDGET = 3

# Termination conditions
NULL_ROUND_THRESHOLD = 3
STABLE_ROUND_THRESHOLD = 5

# QEMU configuration
FIRMWARE_EXTENSIONS = {'.bin', '.hex', '.elf', '.img', '.rom', '.fw'}

# Filename validation pattern (for corpus filenames)
SAFE_FILENAME_PATTERN = r"[A-Za-z0-9._-]{1,128}"
