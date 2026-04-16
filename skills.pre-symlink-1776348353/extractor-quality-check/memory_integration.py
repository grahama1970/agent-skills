"""Memory integration layer for the inline review loop.

Provides MemoryClient (native or subprocess fallback), add_edge, taxonomy
helpers, and safe JSON parsing for CLI subprocess output.

Pattern: Follows review-persona/memory_integration.py with graceful degradation.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, List

from loguru import logger

# ---------------------------------------------------------------------------
# Optional json_repair
# ---------------------------------------------------------------------------
try:
    from json_repair import repair_json as _repair_json
    _HAS_JSON_REPAIR = True
except ImportError:
    _HAS_JSON_REPAIR = False


def parse_json_safe(raw: str) -> Any:
    """Parse JSON from CLI output that may have warnings/text before the JSON.

    Uses json_repair as fallback (same pattern as extractor json_utils.parse_json).
    """
    if not raw or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Extract JSON object/array region
    match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
    if match:
        extracted = match.group(1)
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass
        if _HAS_JSON_REPAIR:
            try:
                repaired = _repair_json(extracted, return_objects=True)
                if isinstance(repaired, (dict, list)):
                    return repaired
            except Exception as e:
                logger.debug("extraction failed: {}", e)
    return None


# ---------------------------------------------------------------------------
# sys.path setup
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_REVIEW_PDF_DIR = _THIS_DIR.parent / "review-pdf"
_SKILLS_DIR = _THIS_DIR.parent  # pi-mono/.pi/skills -- for common.* imports

for _p in [str(_REVIEW_PDF_DIR), str(_THIS_DIR), str(_SKILLS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# graph_memory for edge creation and lessons
# RULE: NEVER use get_db() directly. Only MemoryClient, search(), add_edge().
# _HAS_MEMORY is tri-state: "native" | "httpx" | False
# ---------------------------------------------------------------------------
_HAS_MEMORY = False
MemoryClient: Any = None
add_edge: Any = None

try:
    from graph_memory.api import MemoryClient as _NativeMemoryClient, add_edge as _native_add_edge
    MemoryClient = _NativeMemoryClient
    add_edge = _native_add_edge
    _HAS_MEMORY = "native"
except ImportError:
    pass

# Subprocess fallback for MemoryClient (same pattern as convergence_tracker.py).
# The child process may run in a uv environment that lacks python-arango.
# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)

if not _HAS_MEMORY:

    class _HttpxMemoryClient:
        """Memory client using httpx to embry-memory Unix socket."""

        def __init__(self, scope: str = ""):
            self.scope = scope

        def recall(self, query: str, k: int = 10):
            try:
                import httpx
                transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
                with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                    body: dict = {"q": query, "k": k}
                    if self.scope:
                        body["scope"] = self.scope
                    resp = client.post("/recall", json=body)
                    return resp.json() if resp.status_code == 200 else {"found": False, "items": []}
            except Exception:
                return {"found": False, "items": []}

        def learn(self, problem: str = "", solution: str = "", tags=None):
            try:
                import httpx
                transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
                with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                    body: dict = {"problem": problem, "solution": solution}
                    if tags:
                        body["tags"] = list(tags)
                    resp = client.post("/learn", json=body)
                    return resp.json() if resp.status_code == 200 else {"meta": {"ok": False}}
            except Exception:
                return {"meta": {"ok": False}}

    MemoryClient = _HttpxMemoryClient
    _HAS_MEMORY = "httpx"

    def _subprocess_add_edge(*args, **kwargs):
        """Stub -- edge creation not supported via subprocess fallback."""
        return {"meta": {"ok": False}}

    add_edge = _subprocess_add_edge

    print("review-pdf inline_review_loop using subprocess MemoryClient fallback", flush=True)

# Keep legacy alias for backward compat
HAS_MEMORY = _HAS_MEMORY

# ---------------------------------------------------------------------------
# Bridge extraction (memory contract)
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["accuracy", "fidelity", "extraction", "correct", "verified"],
    "Resilience": ["robust", "recovery", "fallback", "retry", "adaptive"],
    "Fragility": ["failure", "broken", "corrupt", "missing", "degraded"],
    "Corruption": ["malformed", "invalid", "inconsistent", "garbled"],
    "Loyalty": ["pipeline", "provenance", "source", "lineage", "traceability"],
    "Stealth": ["subtle", "hidden", "edge-case", "corner-case", "latent"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from quality check content."""
    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Precision"]


# ---------------------------------------------------------------------------
# Pre-hook: Recall prior quality checks
# ---------------------------------------------------------------------------

def recall_quality_checks(query: str, k: int = 5) -> str:
    """Recall prior extractor quality check results from memory.

    Returns formatted context string, empty if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""
    try:
        client = MemoryClient(scope="extractor")
        result = client.recall(f"extractor quality check {query}", k=k)
        if isinstance(result, dict) and result.get("found"):
            items = result.get("items", [])
            if items:
                lines = [f"- {it.get('problem', '')}: {it.get('solution', '')}" for it in items[:k]]
                return "\n".join(lines)
        return ""
    except Exception as e:
        logger.warning(f"Prior quality check recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn quality check results
# ---------------------------------------------------------------------------

def learn_quality_check(
    problem: str,
    solution: str,
    tags: List[str] | None = None,
) -> bool:
    """Learn extractor quality check findings to memory.

    Returns True if successfully stored, False otherwise.
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping quality check learn")
        return False
    try:
        bridges = extract_bridges(f"{problem} {solution}")
        all_tags = ["extractor_quality_check"] + bridges + (tags or [])
        client = MemoryClient(scope="extractor")
        result = client.learn(problem=problem, solution=solution, tags=all_tags)
        ok = isinstance(result, dict) and result.get("meta", {}).get("ok", False)
        if ok:
            logger.info("Learned quality check result")
        return ok
    except Exception as e:
        logger.warning(f"Failed to learn quality check: {e}")
        return False


# ---------------------------------------------------------------------------
# Taxonomy for bridge_tags
# ---------------------------------------------------------------------------
HAS_TAXONOMY = False
extract_taxonomy_features: Any = None
ContentType: Any = None

try:
    from common.taxonomy import extract_taxonomy_features as _etf, ContentType as _CT
    extract_taxonomy_features = _etf
    ContentType = _CT
    HAS_TAXONOMY = True
except ImportError:
    pass
