"""Configuration for monitor-security skill.

Paths, thresholds, tool locations, and environment-based overrides.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent  # .pi/skills/
PI_MONO_ROOT = SKILLS_DIR.parents[1]  # .pi/ -> pi-mono/

# Target to scan (defaults to pi-mono repo root, overridable for embry-os or other targets)
TARGET_ROOT = Path(os.getenv("MONITOR_TARGET_ROOT", str(PI_MONO_ROOT)))

# Backwards compat alias
EMBRY_OS_ROOT = TARGET_ROOT

# ---------------------------------------------------------------------------
# Sibling skills (all in .pi/skills/)
# ---------------------------------------------------------------------------
HACK_SKILL = SKILLS_DIR / "hack"
BATTLE_SKILL = SKILLS_DIR / "battle"
SECURITY_SCAN_SKILL = SKILLS_DIR / "security-scan"
CONSUME_FEED_SKILL = SKILLS_DIR / "consume-feed"
SOCIAL_BRIDGE_SKILL = SKILLS_DIR / "social-bridge"
DOGPILE_SKILL = SKILLS_DIR / "dogpile"
SCHEDULER_SKILL = SKILLS_DIR / "scheduler"
MEMORY_SKILL = SKILLS_DIR / "memory"
SCILLM_SKILL = SKILLS_DIR / "scillm"
ASSISTANT_SKILL = SKILLS_DIR / "assistant"

# ---------------------------------------------------------------------------
# State directories
# ---------------------------------------------------------------------------
STATE_DIR = Path(os.getenv("MONITOR_STATE_DIR", str(Path.home() / ".pi" / "monitor-security")))
SHADOW_FILE = Path(os.getenv("CASCADE_SHADOW_FILE", str(STATE_DIR / "shadow.jsonl")))
METRICS_FILE = Path(os.getenv("CASCADE_METRICS_FILE", str(STATE_DIR / "metrics.jsonl")))
THREAT_INTEL_DIGEST = Path(os.getenv("THREAT_INTEL_DIGEST", str(STATE_DIR / "threat_intel_digest.json")))
TRAINING_LABELS_FILE = STATE_DIR / "training_labels.jsonl"

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
RETRAIN_LABEL_THRESHOLD = int(os.getenv("RETRAIN_LABEL_THRESHOLD", "50"))

# Semgrep rules
OWASP_RULES_FILE = SKILL_DIR / "rules" / "owasp_llm_top10.yaml"

# Docker
SELFHACK_IMAGE = "embry-os-selfhack:latest"
SELFHACK_DOCKERFILE = SKILL_DIR / "docker" / "Dockerfile.embry-os"

# ---------------------------------------------------------------------------
# Swarm
# ---------------------------------------------------------------------------
SWARM_MAX_WORKERS = int(os.getenv("SWARM_MAX_WORKERS", "10"))
SWARM_TIMEOUT = int(os.getenv("SWARM_TIMEOUT", "60"))
