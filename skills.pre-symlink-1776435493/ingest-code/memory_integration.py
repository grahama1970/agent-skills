"""
Memory + Taxonomy integration for /ingest-code.

Pre-hook: Recalls prior CWE scans for a repository to surface previously
identified vulnerabilities and avoid redundant analysis.

Post-hook: Learns CWE findings to memory so future scans can leverage
accumulated vulnerability knowledge across sessions.

Pattern: Follows discover-contacts/memory_integration.py with graceful degradation.
"""

import importlib.util
import json
import sys
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
        _spec = importlib.util.spec_from_file_location("ingest_code_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["cwe", "vulnerability", "scan", "detected"],
    "Resilience": ["patched", "mitigated", "hardened"],
    "Fragility": ["buffer overflow", "race condition", "memory leak"],
    "Corruption": ["injection", "xss", "path traversal"],
    "Loyalty": ["dependency", "library", "upstream"],
    "Stealth": ["backdoor", "obfuscated"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from code scan content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="code")
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
# Pre-hook: Recall prior CWE scans
# ---------------------------------------------------------------------------

def recall_prior_cwe_scan(
    repo_path: str,
    language: str = "",
    k: int = 5,
) -> str:
    """
    Recall prior CWE scans for a repository.

    Returns formatted markdown showing previously identified vulnerabilities,
    enabling agents to avoid redundant scanning and track remediation.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.CODE)
        result = client.recall(
            f"ingest_code {repo_path} {language} cwe vulnerability scan",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior CWE scan recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn CWE findings
# ---------------------------------------------------------------------------

def learn_cwe_findings(
    repo_path: str,
    language: str = "",
    cwe_count: int = 0,
    severity_counts: Optional[Dict[str, int]] = None,
    files_scanned: int = 0,
) -> List[str]:
    """
    Learn CWE scan findings to memory.

    Stores:
    1. Scan summary (repo, language, CWE count, severity breakdown)
    2. Language association (for cross-repo vulnerability patterns)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping CWE findings learn")
        return []

    client = MemoryClient(scope=MemoryScope.CODE)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([repo_path or "", language or "", f"cwe count {cwe_count}"])
    bridges = extract_bridges(all_text)
    base_tags = ["ingest_code", language or "unknown"] + bridges

    # 1. Scan summary
    profile = json.dumps({
        "repo_path": repo_path,
        "language": language,
        "cwe_count": cwe_count,
        "severity_counts": severity_counts or {},
        "files_scanned": files_scanned,
        "scanned_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"CWE scan: {repo_path} ({language}) — {cwe_count} findings",
            solution=profile,
            tags=base_tags + ["cwe_scan"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned CWE scan: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn CWE scan: {e}")

    # 2. Language association
    if language:
        try:
            result = client.learn(
                problem=f"Language CWE pattern: {language} — {repo_path} ({cwe_count} findings)",
                solution=json.dumps({
                    "language": language,
                    "repo_path": repo_path,
                    "cwe_count": cwe_count,
                    "date": now,
                }),
                tags=base_tags + ["language_pattern", language],
            )
            if result.success:
                learned_ids.append(result.lesson_id)
        except Exception as e:
            logger.warning(f"Failed to learn language pattern: {e}")

    logger.info(f"CWE findings learn complete: {len(learned_ids)} entries stored")
    return learned_ids
