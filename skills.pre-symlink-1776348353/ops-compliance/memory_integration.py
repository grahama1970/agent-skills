#!/usr/bin/env python3
"""
Memory skill integration for ops-compliance.

Stores compliance scan results for trend analysis and historical tracking.
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
    "Precision": ["accuracy", "compliance", "audit", "control"],
    "Resilience": ["remediation", "recovery", "continuity"],
    "Fragility": ["failed", "non-compliant", "vulnerability", "gap"],
    "Loyalty": ["soc2", "gdpr", "hipaa", "pci", "framework"],
    "Stealth": ["edge case", "ambiguous", "partial"],
}


def extract_bridges(text: str) -> list[str]:
    """Extract taxonomy bridge attributes from compliance content."""
    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Precision"]


def learn_compliance_scan(results: dict[str, Any]) -> bool:
    """Learn compliance scan results to memory via common client."""
    if not _HAS_MEMORY:
        return store_compliance_results(results)

    try:
        entry = _build_memory_entry(results)
        bridges = extract_bridges(entry.get("summary", ""))
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.learn(
            problem=f"Compliance scan: {entry['framework']} — {entry['status']}",
            solution=json.dumps(entry, indent=2),
            tags=["compliance", entry["framework"].lower(), "audit"] + bridges,
        )
        return result.success
    except Exception as e:
        logger.warning(f"Memory learn failed: {e}")
        return store_compliance_results(results)


def store_compliance_results(results: dict[str, Any]) -> bool:
    """
    Store compliance scan results in memory.

    Args:
        results: Scan results with framework, checks, summary

    Returns:
        True if stored successfully
    """
    entry = _build_memory_entry(results)

    try:
        return _store_via_skill(entry)
    except Exception as e:
        print(f"[WARN] Memory storage failed: {e}")
        return _store_locally(entry)


def _build_memory_entry(results: dict[str, Any]) -> dict[str, Any]:
    """Build a memory-compatible entry from compliance results."""
    framework = results.get("framework", "unknown")
    summary = results.get("summary", {})

    # Extract failed checks for learning
    failed_checks = []
    for check in results.get("checks", []):
        if check.get("status") == "fail":
            failed_checks.append({
                "control_id": check.get("control_id"),
                "description": check.get("description"),
                "finding": check.get("finding"),
                "remediation": check.get("remediation"),
            })

    # Build compliance posture summary
    total = summary.get("passed", 0) + summary.get("failed", 0) + summary.get("warnings", 0)
    pass_rate = (summary.get("passed", 0) / total * 100) if total > 0 else 0

    compliance_status = "compliant" if summary.get("failed", 0) == 0 else "non-compliant"

    return {
        "type": "compliance_scan",
        "timestamp": datetime.now().isoformat(),
        "path": results.get("path", "unknown"),
        "framework": framework.upper(),
        "status": compliance_status,
        "summary": f"{framework.upper()} compliance: {compliance_status} "
                   f"(Pass: {summary.get('passed', 0)}, Fail: {summary.get('failed', 0)}, "
                   f"Warn: {summary.get('warnings', 0)}, Rate: {pass_rate:.1f}%)",
        "counts": {
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "warnings": summary.get("warnings", 0),
            "total": total,
            "pass_rate": pass_rate,
        },
        "failed_checks": failed_checks[:10],  # Limit to top 10
    }


def _store_via_skill(entry: dict[str, Any]) -> bool:
    """Store entry via embry-memory daemon Unix socket."""
    import httpx
    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
        resp = client.post("/learn", json={
            "problem": f"compliance-{entry.get('framework', 'unknown')}",
            "solution": json.dumps(entry),
            "tags": ["compliance", entry.get("framework", "").lower(), "audit"],
        })
        return resp.status_code == 200


def _store_locally(entry: dict[str, Any]) -> bool:
    """Fallback: store entry to local file."""
    local_path = Path.home() / ".pi" / "ops-compliance" / "history.jsonl"
    local_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(local_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return True
    except Exception:
        return False


def recall_compliance_history(
    framework: str = "all",
    limit: int = 10
) -> list[dict[str, Any]]:
    """
    Recall previous compliance scan results from memory.

    Args:
        framework: Filter by framework (soc2, gdpr, all)
        limit: Maximum results to return

    Returns:
        List of previous compliance entries
    """
    query = f"compliance {framework}" if framework != "all" else "compliance scan"

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
    local_path = Path.home() / ".pi" / "ops-compliance" / "history.jsonl"
    if local_path.exists():
        entries = []
        with open(local_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if framework == "all" or entry.get("framework", "").lower() == framework.lower():
                        entries.append(entry)
                except json.JSONDecodeError:
                    pass
        return entries[-limit:]

    return []


def get_compliance_trend(framework: str = "all", days: int = 30) -> dict[str, Any]:
    """
    Get compliance trend over time.

    Args:
        framework: Framework to analyze
        days: Number of days to look back

    Returns:
        Trend analysis with pass rate history
    """
    history = recall_compliance_history(framework, limit=100)

    if not history:
        return {"trend": "no_data", "history": []}

    # Sort by timestamp
    history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # Calculate trend
    recent = history[:5] if len(history) >= 5 else history
    older = history[5:10] if len(history) >= 10 else []

    recent_avg = sum(h.get("counts", {}).get("pass_rate", 0) for h in recent) / len(recent)

    if older:
        older_avg = sum(h.get("counts", {}).get("pass_rate", 0) for h in older) / len(older)
        if recent_avg > older_avg + 5:
            trend = "improving"
        elif recent_avg < older_avg - 5:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    return {
        "trend": trend,
        "current_pass_rate": recent_avg,
        "data_points": len(history),
        "framework": framework,
    }


if __name__ == "__main__":
    # Demo usage
    sample_results = {
        "framework": "soc2",
        "path": "/tmp/test",
        "checks": [
            {"control_id": "CC6.1", "status": "pass", "description": "Test check"},
            {"control_id": "CC6.2", "status": "fail", "description": "Failed check",
             "finding": "Issue found", "remediation": "Fix it"},
        ],
        "summary": {"passed": 1, "failed": 1, "warnings": 0},
    }
    success = store_compliance_results(sample_results)
    print(f"Storage {'succeeded' if success else 'failed'}")
