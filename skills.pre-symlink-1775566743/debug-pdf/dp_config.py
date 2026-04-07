"""
Path configuration and auto-detection for debug-pdf.
"""
import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

# Import task monitor client (optional, may not exist yet)
try:
    from task_monitor_client import DebugPdfTaskClient
    TASK_MONITOR_AVAILABLE = True
except ImportError:
    TASK_MONITOR_AVAILABLE = False
    DebugPdfTaskClient = None

SKILL_DIR = Path(__file__).parent.resolve()
PI_SKILLS_DIR = SKILL_DIR.parent

# Data directory for persistent state
DATA_DIR = Path(os.environ.get("DEBUG_PDF_DATA", Path.home() / ".pi" / "debug-pdf"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR = DATA_DIR / "sessions"
FIXTURES_DIR = DATA_DIR / "fixtures"
SESSIONS_DIR.mkdir(exist_ok=True)
FIXTURES_DIR.mkdir(exist_ok=True)

# Sibling skill paths (auto-detect)
FETCHER_RUN = PI_SKILLS_DIR / "fetcher" / "run.sh"
FIXTURE_TRICKY_DIR = PI_SKILLS_DIR / "fixture-tricky"
FIGURE_RUN = PI_SKILLS_DIR / "create-figure" / "run.sh"

# Extractor skill - check multiple locations
def find_extractor_run():
    candidates = [
        PI_SKILLS_DIR / "extractor" / "run.sh",
        PI_SKILLS_DIR.parent.parent.parent / "memory" / ".agents" / "skills" / "extractor" / "run.sh",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

EXTRACTOR_RUN = find_extractor_run()

# Memory skill for pattern recall/storage
def find_memory_run():
    candidates = [
        PI_SKILLS_DIR.parent.parent.parent / "memory" / ".agents" / "skills" / "memory" / "run.sh",
        PI_SKILLS_DIR / "memory" / "run.sh",
        Path.home() / ".pi" / "agent" / "skills" / "memory" / "run.sh",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

MEMORY_RUN = find_memory_run()

# Agent inbox - check multiple locations
def find_inbox_tool():
    _experiments_dir = PI_SKILLS_DIR.parent.parent.parent
    candidates = [
        _experiments_dir / "memory" / ".agents" / "skills" / "agent-inbox" / "run.sh",
        _experiments_dir / "memory" / ".agents" / "skills" / "agent-inbox" / "agent-inbox",
        PI_SKILLS_DIR / "agent-inbox" / "run.sh",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

INBOX_TOOL = find_inbox_tool()

