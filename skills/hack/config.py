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

# Agent skills directory (for .agent/skills)
AGENT_SKILLS = SKILL_DIR.parent.parent.parent / ".agent" / "skills"

# Sibling skill paths
MEMORY_SKILL = AGENT_SKILLS / "memory"
ANVIL_SKILL = SKILLS_DIR / "anvil"
DOCKER_OPS_SKILL = SKILLS_DIR / "docker-ops"
TASK_MONITOR_SKILL = SKILLS_DIR / "task-monitor"
TAXONOMY_SKILL = SKILLS_DIR / "taxonomy"
TREESITTER_SKILL = SKILLS_DIR / "treesitter"

# Skill script mapping for research command
SKILL_MAP = {
    "dogpile": "dogpile/run.sh",
    "arxiv": "arxiv/run.sh",
    "perplexity": "perplexity/run.sh",
    "code-review": "code-review/run.sh",
    "wayback": "dogpile/run.sh",
    "lean4-prove": "lean4-prove/run.sh",
    "fixture-graph": "fixture-graph/run.sh",
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

# Explicit module exports for clarity
__all__ = [
    "SECURITY_IMAGE",
    "SKILL_DIR",
    "SKILLS_DIR",
    "AGENT_SKILLS",
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
]
