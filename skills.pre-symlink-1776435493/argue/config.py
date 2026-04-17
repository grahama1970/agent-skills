"""
Argue Skill - Configuration
Constants, paths, and skill references.
"""
import os
from pathlib import Path

# Paths
SKILL_DIR = Path(__file__).parent.resolve()
SKILLS_DIR = SKILL_DIR.parent
DEBATES_DIR = SKILL_DIR / "debates"
STORAGE_BASE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media" / "personas"

# Sibling Skills
DOGPILE_SKILL = SKILLS_DIR / "dogpile"
ASK_SKILL = SKILLS_DIR / "ask"
MEMORY_SKILL = SKILLS_DIR / "memory"
TAXONOMY_SKILL = SKILLS_DIR / "taxonomy"
CONSUME_BOOK_SKILL = SKILLS_DIR / "consume-book"
CONSUME_YOUTUBE_SKILL = SKILLS_DIR / "consume-youtube"
TASK_MONITOR_SKILL = SKILLS_DIR / "task-monitor"
EPISODIC_ARCHIVER_SKILL = SKILLS_DIR / "episodic-archiver"

# Persona storage
PERSONA_DIR = STORAGE_BASE  # /mnt/storage12tb/media/personas/{name}/

# Scoring weights
EVIDENCE_QUALITY_WEIGHT = 2.0
ARGUMENT_NOVELTY_WEIGHT = 1.5
CONCESSION_QUALITY_WEIGHT = 2.0  # Concessions are GOOD
LOGICAL_COHERENCE_WEIGHT = 1.0
REBUTTAL_PRECISION_WEIGHT = 1.0
CONFIDENCE_CALIBRATION_WEIGHT = 0.5

# Termination
CONVERGENCE_DELTA = 0.1  # Confidence change threshold
CONVERGENCE_ROUNDS = 2   # Rounds below delta to trigger convergence
NULL_ROUND_THRESHOLD = 2  # Rounds with no new arguments
DEFAULT_MAX_ROUNDS = 7
RESEARCH_BUDGET_PER_ROUND = 3  # Max /dogpile + /ask calls per persona per round

# Defaults
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_MODE = "adversarial"
VALID_MODES = ("adversarial", "panel", "socratic", "devils-advocate")
