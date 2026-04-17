"""Memory client bridge with subprocess fallback for inline review loop.

Provides MemoryClient and add_edge with three modes:
- "native": graph_memory.api is importable (python-arango available)
- "subprocess": calls memory/run.sh via subprocess (uv environment lacks python-arango)
- "unavailable": no memory access

Also exports HAS_MEMORY (tri-state string) and HAS_TAXONOMY (bool).

RULE: NEVER use get_db() directly. Only MemoryClient, search(), add_edge().
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

import importlib as _importlib
import importlib.util as _importlib_util

def _import_local_json_utils():
    """Import json_utils from THIS directory, not the skills-level shim."""
    _local = Path(__file__).resolve().parent / "json_utils.py"
    spec = _importlib_util.spec_from_file_location("_local_json_utils", _local)
    mod = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_local_ju = _import_local_json_utils()
parse_json_safe = _local_ju.parse_json_safe

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _THIS_DIR.parent  # pi-mono/.pi/skills
# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)

# ---------------------------------------------------------------------------
# Memory client: native or subprocess fallback
# ---------------------------------------------------------------------------
HAS_MEMORY = "unavailable"

try:
    from graph_memory.api import MemoryClient, add_edge  # noqa: F401
    HAS_MEMORY = "native"
except ImportError:
    pass


if HAS_MEMORY == "unavailable":

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

    MemoryClient = _HttpxMemoryClient  # type: ignore[misc]
    HAS_MEMORY = "httpx"

    def add_edge(*args, **kwargs):  # noqa: ARG001
        """Stub -- edge creation not supported via subprocess fallback."""
        return {"meta": {"ok": False}}

    print("review-pdf inline_review_loop using subprocess MemoryClient fallback", flush=True)

# If still unavailable, provide stubs so importers don't break
if HAS_MEMORY == "unavailable":

    class MemoryClient:  # type: ignore[no-redef]
        """Stub MemoryClient when no memory backend is available."""

        def __init__(self, scope: str = ""):
            self.scope = scope

        def recall(self, query: str, k: int = 10):  # noqa: ARG002
            return {"found": False, "items": []}

        def learn(self, problem: str = "", solution: str = "", tags=None):  # noqa: ARG002
            return {"meta": {"ok": False}}

    def add_edge(*args, **kwargs):  # noqa: ARG001, F811
        """Stub -- no memory backend available."""
        return {"meta": {"ok": False}}


# ---------------------------------------------------------------------------
# Taxonomy for bridge_tags
# ---------------------------------------------------------------------------
HAS_TAXONOMY = False
extract_taxonomy_features = None
ContentType = None

try:
    from common.taxonomy import extract_taxonomy_features, ContentType  # type: ignore[no-redef] # noqa: F811
    HAS_TAXONOMY = True
except ImportError:
    pass
