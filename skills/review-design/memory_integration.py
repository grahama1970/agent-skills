"""
Memory + Taxonomy integration for /review-design.

Pre-hook: Recalls prior design reviews for a project/component to surface
previously identified issues and track design evolution.

Post-hook: Learns design review findings to memory so future reviews can
leverage accumulated knowledge across sessions.

Pattern: Follows discover-contacts/memory_integration.py with graceful degradation.
"""
# --- dotenv (MUST be before any os.getenv / os.environ) ---
import sys
from pathlib import Path as _Path

def _resolve_skills_dir() -> _Path:
    p = _Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if parent.name == "skills":
            return parent
    return p.parents[1]

_SKILLS_DIR = _resolve_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env() -> None:
        return

_load_env()


import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Lazy imports with graceful degradation
# ---------------------------------------------------------------------------
_SKILLS_DIR = Path(__file__).parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient, MemoryScope, RecallResult
    _HAS_MEMORY = True
except ImportError:
    logger.debug("common.memory_client not available — memory integration disabled")

_taxonomy_extract = None
_TAXONOMY_PATH = _SKILLS_DIR / "taxonomy" / "taxonomy.py"
if _TAXONOMY_PATH.exists():
    try:
        _spec = importlib.util.spec_from_file_location("review_design_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


class _MemoryRecallTimeout(BaseException):
    pass


def _handle_recall_timeout(signum: int, frame: Any) -> None:
    raise _MemoryRecallTimeout()


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["accessible", "contrast", "aligned", "pixel-perfect"],
    "Resilience": ["responsive", "fallback", "adaptive"],
    "Fragility": ["broken", "overflow", "misaligned", "clipped"],
    "Corruption": ["dark pattern", "deceptive", "inconsistent"],
    "Loyalty": ["design system", "token", "component"],
    "Stealth": ["hidden", "invisible", "z-index", "opacity"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from design review content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="operational")
            bridges = result.get("bridge_tags", []) if isinstance(result, dict) else []
            if bridges:
                return bridges
        except Exception as e:
            logger.debug(f"Taxonomy extraction failed, using keyword fallback: {e}")

    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Precision"]


# ---------------------------------------------------------------------------
# Pre-hook: Recall prior design reviews
# ---------------------------------------------------------------------------

def recall_prior_design_reviews(
    project: str,
    component: str = "",
    k: int = 5,
    timeout_s: float = 2.0,
) -> str:
    """
    Recall prior design reviews for a project or component.

    Returns formatted markdown showing previously identified design issues,
    enabling agents to track design evolution and avoid duplicate feedback.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    def _recall() -> str:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        query = f"review_design {project} {component} accessibility responsive"
        run_script = client._get_run_script()
        result = subprocess.run(
            [
                str(run_script),
                "recall",
                "--q",
                query,
                "--k",
                str(k),
                "--threshold",
                "0.3",
                "--scope",
                str(MemoryScope.OPERATIONAL),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(client.memory_root),
            env={key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"},
        )
        if result.returncode != 0:
            logger.warning(f"Prior design review recall failed: {result.stderr.strip()}")
            return ""

        data = json.loads(result.stdout)
        recall_result = RecallResult(
            items=data.get("items", []),
            query=query,
            scope=str(MemoryScope.OPERATIONAL),
            k=k,
            meta=data.get("meta", {}),
        )
        if recall_result.found:
            return recall_result.to_context(max_items=k)
        return ""

    try:
        if threading.current_thread() is threading.main_thread():
            previous_handler = signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM, _handle_recall_timeout)
            signal.setitimer(signal.ITIMER_REAL, timeout_s)
            try:
                return _recall()
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)
        return _recall()
    except _MemoryRecallTimeout:
        logger.warning(
            f"Prior design review recall timed out after {timeout_s:.1f}s; continuing without memory context"
        )
        return ""
    except Exception as e:
        logger.warning(f"Prior design review recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn design review
# ---------------------------------------------------------------------------

def learn_design_review(
    project: str,
    component: str = "",
    findings: Optional[List[str]] = None,
    providers_used: Optional[List[str]] = None,
    score: float = 0.0,
) -> List[str]:
    """
    Learn design review findings to memory.

    Stores:
    1. Review summary (project, component, findings, score)
    2. Component association (for cross-review recall)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping design review learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([project or "", component or ""] + (findings or []))
    bridges = extract_bridges(all_text)
    base_tags = ["review_design", project] + bridges

    # 1. Review summary
    profile = json.dumps({
        "project": project,
        "component": component,
        "findings": findings or [],
        "providers_used": providers_used or [],
        "score": score,
        "reviewed_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Design review: {project}/{component} — score {score}",
            solution=profile,
            tags=base_tags + ["review"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned design review: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn design review: {e}")

    # 2. Component association
    if component:
        try:
            result = client.learn(
                problem=f"Component review: {component} in {project}",
                solution=json.dumps({
                    "component": component,
                    "project": project,
                    "score": score,
                    "date": now,
                }),
                tags=base_tags + ["component_association", component],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn component association: {e}")

    logger.info(f"Design review learn complete: {len(learned_ids)} entries stored")
    return learned_ids
