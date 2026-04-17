#!/usr/bin/env python3
"""
Memory skill integration for security-scan.

Stores scan results for cross-session knowledge and trend analysis.
"""
import os
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient, MemoryScope
    _HAS_MEMORY = True
except ImportError:
    logger.debug("common.memory_client not available — memory integration disabled")


_BRIDGE_KEYWORDS = {
    "Precision": ["accuracy", "detection", "finding", "rule"],
    "Resilience": ["remediation", "recovery", "patch", "fix"],
    "Fragility": ["vulnerability", "exploit", "critical", "secret"],
    "Loyalty": ["pipeline", "scan", "audit", "compliance"],
    "Stealth": ["edge case", "false positive", "bypass", "evasion"],
}


def extract_bridges(text: str) -> list[str]:
    """Extract taxonomy bridge attributes from security content."""
    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Fragility"]


def learn_scan_results(results: dict[str, Any]) -> bool:
    """Learn security scan results to memory via common client."""
    if not _HAS_MEMORY:
        return store_scan_results(results)

    try:
        entry = _build_memory_entry(results)
        bridges = extract_bridges(entry.get("summary", ""))
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.learn(
            problem=f"Security scan: {entry['summary']}",
            solution=json.dumps(entry, indent=2),
            tags=["security", "scan", "findings"] + bridges,
        )
        return result.success
    except Exception as e:
        logger.warning(f"Memory learn failed: {e}")
        return store_scan_results(results)


def store_scan_results(results: dict[str, Any]) -> bool:
    """
    Store security scan results in memory.

    Args:
        results: Scan results with sast, deps, secrets findings

    Returns:
        True if stored successfully
    """
    # Build memory entry
    entry = _build_memory_entry(results)

    # Try to store via memory skill
    try:
        return _store_via_skill(entry)
    except Exception as e:
        print(f"[WARN] Memory storage failed: {e}")
        # Fallback to local file
        return _store_locally(entry)


def _build_memory_entry(results: dict[str, Any]) -> dict[str, Any]:
    """Build a memory-compatible entry from scan results."""
    # Count findings by category
    sast_count = len(results.get("sast", []))
    deps_count = len(results.get("deps", []))
    secrets_count = len(results.get("secrets", []))
    total = sast_count + deps_count + secrets_count

    # Extract high-severity findings
    high_severity = []
    for finding in results.get("sast", []):
        if finding.get("severity") in ("critical", "high"):
            high_severity.append({
                "type": "sast",
                "rule": finding.get("rule_id"),
                "file": finding.get("file"),
                "line": finding.get("line"),
            })

    for finding in results.get("deps", []):
        if finding.get("severity") in ("critical", "high"):
            high_severity.append({
                "type": "dependency",
                "package": finding.get("package"),
                "cve": finding.get("cve"),
            })

    for finding in results.get("secrets", []):
        high_severity.append({
            "type": "secret",
            "rule": finding.get("rule"),
            "file": finding.get("file"),
        })

    # Build summary
    summary = f"Security scan: {total} findings (SAST: {sast_count}, Deps: {deps_count}, Secrets: {secrets_count})"

    return {
        "type": "security_scan",
        "timestamp": datetime.now().isoformat(),
        "path": results.get("path", "unknown"),
        "summary": summary,
        "counts": {
            "sast": sast_count,
            "deps": deps_count,
            "secrets": secrets_count,
            "total": total,
        },
        "high_severity": high_severity[:10],  # Limit to top 10
        "tools_used": ["semgrep", "bandit", "pip-audit", "trivy", "gitleaks"],
    }


def _store_via_skill(entry: dict[str, Any]) -> bool:
    """Store entry via embry-memory daemon Unix socket."""
    import httpx
    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
        resp = client.post("/learn", json={
            "problem": "security-scan-findings",
            "solution": json.dumps(entry),
            "tags": ["security", "scan", "findings"],
        })
        return resp.status_code == 200


def _store_locally(entry: dict[str, Any]) -> bool:
    """Fallback: store entry to local file."""
    local_path = Path.home() / ".pi" / "security-scan" / "history.jsonl"
    local_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(local_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return True
    except Exception:
        return False


def recall_scan_history(query: str = "security scan", limit: int = 10) -> list[dict[str, Any]]:
    """
    Recall previous security scan results from memory.

    Args:
        query: Search query
        limit: Maximum results to return

    Returns:
        List of previous scan entries
    """
    # Try memory daemon via Unix socket
    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            resp = client.post("/recall", json={"q": query, "k": limit})
            if resp.status_code == 200:
                return resp.json().get("items", [])
    except Exception as e:
        logger.debug("Memory recall failed: {}", e)

    # Fallback: read local history
    local_path = Path.home() / ".pi" / "security-scan" / "history.jsonl"
    if local_path.exists():
        entries = []
        with open(local_path) as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries[-limit:]

    return []


if __name__ == "__main__":
    # Demo usage
    sample_results = {
        "path": "/tmp/test",
        "sast": [{"rule_id": "test", "severity": "high", "file": "test.py", "line": 1}],
        "deps": [],
        "secrets": [],
    }
    success = store_scan_results(sample_results)
    print(f"Storage {'succeeded' if success else 'failed'}")
