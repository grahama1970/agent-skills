"""
Discover Contacts - Configuration
Constants, paths, and skill references.
"""
import os
from pathlib import Path

# Paths
SKILL_DIR = Path(__file__).parent.resolve()
SKILLS_DIR = SKILL_DIR.parent
REFERENCES_DIR = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media/personas/references"
COMPANY_PROFILES_DIR = REFERENCES_DIR / "company_profiles"
CHANGE_LOG_DIR = REFERENCES_DIR / "change_log"

# Sibling Skills
DOGPILE_SKILL = SKILLS_DIR / "dogpile"
MEMORY_SKILL = SKILLS_DIR / "memory"
BRAVE_SEARCH_SKILL = SKILLS_DIR / "brave-search"
PERPLEXITY_SKILL = SKILLS_DIR / "perplexity"
OPS_SAM_GOV_SKILL = SKILLS_DIR / "ops-sam-gov"
OPS_DARPA_SKILL = SKILLS_DIR / "ops-darpa"

# Default contact sources
DEFAULT_CONTACTS_CSV = REFERENCES_DIR / "darpa_arcos_contacts.csv"
DEFAULT_ENRICHED_YAML = REFERENCES_DIR / "darpa_arcos_enriched.yaml"

# Rate limiting
DEFAULT_CONCURRENCY = 2
DEFAULT_DELAY_SECONDS = 10
DEFAULT_BUDGET = 20  # Max /dogpile calls per run

# Staleness
STALENESS_THRESHOLD_DAYS = 30  # Re-research after this many days

# Defaults
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Memory + Taxonomy integration (graceful degradation)
_HAS_MEMORY_INTEGRATION = False
try:
    from memory_integration import recall_prior_research, learn_contact
    _HAS_MEMORY_INTEGRATION = True
except ImportError:
    pass
