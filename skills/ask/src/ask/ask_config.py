"""Shared configuration for the ask skill."""


from .env import load_dotenv_once

load_dotenv_once()
import os
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = SKILL_ROOT.parent

DEFAULT_ORACLE_MODEL = os.environ.get("ASK_ORACLE_MODEL", "gpt-5.5")
DEFAULT_ORACLE_REASONING = os.environ.get("ASK_ORACLE_REASONING", "high")
DEFAULT_ORACLE_TIMEOUT = float(os.environ.get("ASK_ORACLE_TIMEOUT", "300"))
DEFAULT_ORACLE_IDLE_TIMEOUT = float(os.environ.get("ASK_ORACLE_IDLE_TIMEOUT", "300"))
DEFAULT_ORACLE_HEARTBEAT_INTERVAL = float(os.environ.get("ASK_ORACLE_HEARTBEAT_INTERVAL", "30"))
DEFAULT_ORACLE_BACKEND = os.environ.get("ASK_ORACLE_BACKEND", "auto")
SCILLM_BASE_URL = os.environ.get("SCILLM_BASE_URL", "http://localhost:4001")
SCILLM_API_KEY = os.environ.get("SCILLM_API_KEY", "sk-dev-proxy-123")
SUBAGENT_RUNNER = os.environ.get(
    "ASK_SUBAGENT_RUNNER",
    str(SKILLS_DIR / "subagent-runner" / "run.sh"),
)
SUBAGENT_OUTPUT_DIR = os.environ.get(
    "ASK_SUBAGENT_OUTPUT_DIR",
    str(Path(tempfile.gettempdir()) / "ask-oracle-subagents"),
)
MEMORY_RUN = os.environ.get(
    "ASK_MEMORY_RUN",
    str(SKILLS_DIR / "memory" / "run.sh"),
)
SCILLM_RUN = os.environ.get(
    "ASK_SCILLM_RUN",
    str(SKILLS_DIR / "scillm" / "run.sh"),
)
DOGPILE_RUN = os.environ.get(
    "ASK_DOGPILE_RUN",
    str(SKILLS_DIR / "dogpile" / "run.sh"),
)
MONITOR_PERSONAS_RUN = os.environ.get(
    "ASK_MONITOR_PERSONAS_RUN",
    str(SKILLS_DIR / "monitor-personas" / "run.sh"),
)
ORACLE_BACKENDS = frozenset({"auto", "scillm", "subagent-runner"})
