"""
Configuration constants for the hack skill.

This module contains all paths, constants, and configuration values
used across the hack skill modules.
"""
from pathlib import Path

# Docker image name for isolated scanning
SECURITY_IMAGE = "hack-skill-security:latest"

# Skill directory paths
SKILL_DIR = Path(__file__).parent.resolve()
SKILLS_DIR = SKILL_DIR.parent

# Canonical skills location
CANONICAL_SKILLS = Path.home() / "workspace" / "experiments" / "pi-mono" / ".pi" / "skills"

# Skill paths - use canonical location primarily, fallback to relative
MEMORY_SKILL = CANONICAL_SKILLS / "memory" if (CANONICAL_SKILLS / "memory" / "run.sh").exists() else SKILLS_DIR / "memory"
ANVIL_SKILL = CANONICAL_SKILLS / "anvil" if (CANONICAL_SKILLS / "anvil" / "run.sh").exists() else SKILLS_DIR / "anvil"
DOCKER_OPS_SKILL = CANONICAL_SKILLS / "ops-docker" if (CANONICAL_SKILLS / "ops-docker" / "run.sh").exists() else SKILLS_DIR / "ops-docker"
TASK_MONITOR_SKILL = CANONICAL_SKILLS / "task-monitor" if (CANONICAL_SKILLS / "task-monitor" / "run.sh").exists() else SKILLS_DIR / "task-monitor"
TAXONOMY_SKILL = CANONICAL_SKILLS / "taxonomy" if (CANONICAL_SKILLS / "taxonomy" / "run.sh").exists() else SKILLS_DIR / "taxonomy"
TREESITTER_SKILL = CANONICAL_SKILLS / "treesitter" if (CANONICAL_SKILLS / "treesitter" / "run.sh").exists() else SKILLS_DIR / "treesitter"
CODEX_SKILL = CANONICAL_SKILLS / "codex" if (CANONICAL_SKILLS / "codex" / "run.sh").exists() else SKILLS_DIR / "codex"
CODE_RUNNER_SKILL = CANONICAL_SKILLS / "code-runner" if (CANONICAL_SKILLS / "code-runner" / "run.sh").exists() else SKILLS_DIR / "code-runner"

# Skill script mapping for research command (use canonical paths)
SKILL_MAP = {
    "dogpile": str(CANONICAL_SKILLS / "dogpile" / "run.sh"),
    "arxiv": str(CANONICAL_SKILLS / "arxiv" / "run.sh"),
    "perplexity": str(CANONICAL_SKILLS / "perplexity" / "run.sh"),
    "code-review": str(CANONICAL_SKILLS / "review-code" / "run.sh"),
    "wayback": str(CANONICAL_SKILLS / "dogpile" / "run.sh"),
    "lean4-prove": str(CANONICAL_SKILLS / "lean4-prove" / "run.sh"),
    "fixture-graph": str(CANONICAL_SKILLS / "fixture-graph" / "run.sh"),
    "codex": str(CANONICAL_SKILLS / "codex" / "run.sh"),
}

# Base images for exploit environments
EXPLOIT_BASE_IMAGES = {
    "python": "python:3.9-slim",
    "c": "gcc:latest",
    "ruby": "ruby:3.0",
    "node": "node:18-slim",
    "kali": "kalilinux/kali-rolling",
}

# Tools information for display
TOOLS_INFO = [
    ("nmap", "Network", "scan", "Network vulnerability scanning"),
    ("semgrep", "SAST", "audit", "Multi-language static analysis"),
    ("bandit", "SAST", "audit", "Python security linter"),
    ("pip-audit", "SCA", "sca", "Python dependency vulnerabilities"),
    ("safety", "SCA", "sca --tool safety", "Python dependency checker"),
    ("nuclei", "DAST", "nuclei", "Template-based vulnerability scanning"),
]

# Severity mappings for bandit
BANDIT_SEVERITY_FLAGS = {"low": "-l", "medium": "-ll", "high": "-lll"}

# Default timeout values (in seconds)
DOCKER_RUN_TIMEOUT = 600
SKILL_RUN_TIMEOUT = 300
MEMORY_TIMEOUT = 30
DEFAULT_MODEL = "gpt-5.2-codex"

# Threat Profiles definitions
THREAT_PROFILES = {
    "script-kiddie": {
        "name": "Script-Kiddie",
        "level": 1,
        "nmap_timing": "-T4",
        "semgrep_severity": ["ERROR"],
        "nuclei_severity": ["critical"],
        "stealth": "low",
        "jitter": 0,
    },
    "hobbyist": {
        "name": "Hobbyist",
        "level": 2,
        "nmap_timing": "-T3",
        "semgrep_severity": ["ERROR", "WARNING"],
        "nuclei_severity": ["critical", "high"],
        "stealth": "moderate",
        "jitter": 1,
    },
    "organized-crime": {
        "name": "Organized-Crime",
        "level": 3,
        "nmap_timing": "-T2",
        "semgrep_severity": ["ERROR", "WARNING", "INFO"],
        "nuclei_severity": ["critical", "high", "medium"],
        "stealth": "high",
        "jitter": 5,
    },
    "state-actor": {
        "name": "State-Actor",
        "level": 4,
        "nmap_timing": "-T1",
        "semgrep_severity": ["ERROR", "WARNING", "INFO"],
        "nuclei_severity": ["critical", "high", "medium", "low"],
        "stealth": "expert",
        "jitter": 15,
    },
}

# Explicit module exports for clarity
__all__ = [
    "SECURITY_IMAGE",
    "SKILL_DIR",
    "SKILLS_DIR",
    "CANONICAL_SKILLS",
    "MEMORY_SKILL",
    "ANVIL_SKILL",
    "DOCKER_OPS_SKILL",
    "TASK_MONITOR_SKILL",
    "TAXONOMY_SKILL",
    "TREESITTER_SKILL",
    "SKILL_MAP",
    "EXPLOIT_BASE_IMAGES",
    "TOOLS_INFO",
    "BANDIT_SEVERITY_FLAGS",
    "DOCKER_RUN_TIMEOUT",
    "SKILL_RUN_TIMEOUT",
    "MEMORY_TIMEOUT",
    "THREAT_PROFILES",
    "DEFAULT_MODEL",
    "CODE_RUNNER_SKILL",
]
