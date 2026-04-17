"""
Monitor Contacts - Configuration
Constants, paths, and skill references.
"""
import os
from pathlib import Path

# Paths
SKILL_DIR = Path(__file__).parent.resolve()
SKILLS_DIR = SKILL_DIR.parent
REFERENCES_DIR = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media/personas/references"
CHANGE_LOG_DIR = REFERENCES_DIR / "change_log"
MONITOR_CONFIG = REFERENCES_DIR / "monitor_config.yaml"

# Sibling Skills
DISCOVER_CONTACTS_SKILL = SKILLS_DIR / "discover-contacts"
DOGPILE_SKILL = SKILLS_DIR / "dogpile"
MEMORY_SKILL = SKILLS_DIR / "memory"
OPS_DISCORD_SKILL = SKILLS_DIR / "ops-discord"
SCHEDULER_SKILL = SKILLS_DIR / "scheduler"
TASK_MONITOR_SKILL = SKILLS_DIR / "task-monitor"

# Staleness thresholds (days)
CRITICAL_STALENESS_DAYS = 14
STANDARD_STALENESS_DAYS = 30
COLD_STALENESS_DAYS = 90

# Budget
DEFAULT_BUDGET_PER_CYCLE = 10
DEFAULT_CONCURRENCY = 2

# Schedule
DEFAULT_INTERVAL = "weekly"
DEFAULT_CRON = "0 2 * * 0"  # Sunday 2am

# Defaults
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Memory + Taxonomy integration (graceful degradation)
_HAS_MEMORY_INTEGRATION = False
try:
    from memory_integration import recall_contact_changes, learn_contact_change
    _HAS_MEMORY_INTEGRATION = True
except ImportError:
    pass
