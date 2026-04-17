"""Configuration for monitor-memory nightly health orchestrator.

Centralises persona lists, ArangoDB connection params, probe thresholds,
and filesystem paths. All env vars are loaded via dotenv before first access.

Inputs: environment variables, dotenv file.
Outputs: module-level constants consumed by probes and reporter.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from loguru import logger

# --- dotenv (MUST be before any os.getenv) ---
SKILLS_DIR = Path(__file__).resolve().parents[1]
if str(SKILLS_DIR) not in sys.path:
    sys.path.append(str(SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env():
        try:
            from dotenv import load_dotenv, find_dotenv
            load_dotenv(find_dotenv(usecwd=True), override=False)
        except Exception as e:
            logger.debug("loading failed: {}", e)

_load_env()

# --- Skill paths ---
SKILL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SKILL_DIR.parents[2]

# --- Personas ---
PERSONAS_DREAM = ["horus", "embry"]
PERSONAS_ALL = ["horus", "embry", "brandon_bailey", "margaret_chen", "jennifer_cheung"]
PERSONAS_JOURNAL = PERSONAS_ALL

# --- ArangoDB ---
ARANGO_URL = os.getenv("ARANGO_URL", "http://127.0.0.1:8529")
ARANGO_DB = os.getenv("ARANGO_DB", "memory")

# --- Services ---
EMBEDDING_SERVICE_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://localhost:8080")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MEMORY_PROJECT_PATH = Path(os.getenv(
    "MEMORY_PROJECT_PATH",
    str(_PROJECT_ROOT / "memory"),
))

# --- Paths ---
STORAGE_12TB = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
BACKUP_DIR = Path(os.environ.get(
    "EMBRY_BACKUP_DIR",
    str(STORAGE_12TB / "backups" / "arangodb"),
))
TARGETS_FILE = Path.home() / ".agent_skills_targets"
STATE_DIR = Path.home() / ".pi/monitor-memory"

# --- Thresholds ---
EMBEDDING_WARN_PCT = 99.0
TAXONOMY_WARN_PCT = 90.0
BACKUP_MAX_AGE_HOURS = 26
EDGE_MAX_AGE_HOURS = 26
DISK_WARN_PCT = 85.0
SECURITY_MAX_AGE_DAYS = 7

# --- Auto-fix limits ---
EMBEDDING_FIX_BATCH = 500       # Docs per nightly run per collection
EMBEDDING_FIX_TIMEOUT = 600     # 10 min
TAXONOMY_FIX_BATCH = 200        # Lessons per P02/P26 autofix run
TAXONOMY_FIX_TIMEOUT = 600      # 10 min
EDGE_FIX_TIMEOUT = 600          # 10 min
ORPHAN_FIX_BATCH = 100          # Orphaned lessons per run

# --- Embeddable collections registry ---
# (text_fields, separate_embeddings_collection_or_None)
EMBEDDABLE_COLLECTIONS = {
    "lessons": (["problem", "playbook"], "lesson_embeddings"),
    "lean_theorems": (["lean_code", "notes", "error"], None),
    "agent_conversations": (["topic", "body", "summary"], None),
    "code_symbols": (["name", "kind", "signature", "docstring"], None),
    "doc_chunks": (["title", "content"], None),
    "horus_lore_chunks": (["content"], None),
    "horus_lore_docs": (["content"], None),
    "sfx_library": (["description", "keywords", "filename"], None),
    "requirements": (["text"], None),
    "sparta_qra": (["question", "answer", "reasoning"], None),  # inline embeddings on doc.embedding
    "sparta_controls": (["name", "description"], None),  # inline embeddings on doc.embedding
    "sparta_url_knowledge": (["text", "topic"], None),  # inline embeddings on doc.embedding
}
