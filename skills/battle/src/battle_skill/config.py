"""Configuration for the Battle skill.

Inputs come from environment variables and repository-relative paths. Outputs are
path constants used by the CLI, orchestration modules, and fixture runner.
Generated runtime state defaults to ``/mnt/storage12tb/skills/battle`` so the
skill root remains code-only. Invalid environment values surface through normal
``Path`` or integer conversion errors rather than silent fallbacks.
"""
import os
from pathlib import Path

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = SKILL_DIR.parent
STORAGE_ROOT = Path(os.getenv("BATTLE_STORAGE_ROOT", "/mnt/storage12tb/skills/battle")).resolve()
BATTLES_DIR = STORAGE_ROOT / "battles"
REPORTS_DIR = STORAGE_ROOT / "reports"
WORKTREES_DIR = STORAGE_ROOT / "worktrees"
ARTIFACTS_DIR = STORAGE_ROOT / "artifacts"

# -----------------------------------------------------------------------------
# Sibling Skills
# -----------------------------------------------------------------------------
HACK_SKILL = SKILLS_DIR / "hack"
ANVIL_SKILL = SKILLS_DIR / "anvil"
CODE_RUNNER_SKILL = SKILLS_DIR / "code-runner"
MEMORY_SKILL = SKILLS_DIR / "memory"
TASK_MONITOR_SKILL = SKILLS_DIR / "task-monitor"
DOGPILE_SKILL = SKILLS_DIR / "dogpile"
TAXONOMY_SKILL = SKILLS_DIR / "taxonomy"

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

# Default Configuration
# -----------------------------------------------------------------------------
DEFAULT_MODEL = "gpt-5.2-codex"
DEFAULT_MAX_ROUNDS = 1000
DEFAULT_CHECKPOINT_INTERVAL = 10
OVERNIGHT_ROUNDS = 1000
OVERNIGHT_CHECKPOINT_INTERVAL = 50
DEFAULT_RESEARCH_BUDGET = 3

# Threat Profiles (ported from hack skill)
THREAT_PROFILES = {
    "script-kiddie": {
        "nmap_timing": "-T5",
        "semgrep_severity": "ERROR",
        "nuclei_severity": "critical",
        "rate_limit": 100
    },
    "hobbyist": {
        "nmap_timing": "-T4",
        "semgrep_severity": "ERROR,WARNING",
        "nuclei_severity": "critical,high",
        "rate_limit": 50
    },
    "organized-crime": {
        "nmap_timing": "-T3",
        "semgrep_severity": "ERROR,WARNING,INFO",
        "nuclei_severity": "critical,high,medium",
        "rate_limit": 20
    },
    "state-actor": {
        "nmap_timing": "-T2",
        "semgrep_severity": "ERROR,WARNING,INFO",
        "nuclei_severity": "critical,high,medium,low,info",
        "rate_limit": 5
    }
}

# Termination conditions
NULL_ROUND_THRESHOLD = 3
STABLE_ROUND_THRESHOLD = 5

# QEMU configuration
FIRMWARE_EXTENSIONS = {'.bin', '.hex', '.elf', '.img', '.rom', '.fw'}

# Filename validation pattern (for corpus filenames)
SAFE_FILENAME_PATTERN = r"[A-Za-z0-9._-]{1,128}"

# Swarm configuration
BATTLE_SWARM_WORKERS = int(os.getenv("BATTLE_SWARM_WORKERS", "10"))
BATTLE_SWARM_TIMEOUT = int(os.getenv("BATTLE_SWARM_TIMEOUT", "60"))
