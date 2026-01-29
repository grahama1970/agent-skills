#!/usr/bin/env python3
"""
Memory skill integration for ops-compliance.

Stores compliance scan results for trend analysis and historical tracking.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


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
    """Store entry via memory skill CLI."""
    memory_skill = Path.home() / ".pi" / "agent" / "skills" / "memory" / "run.sh"

    for alt in [
        memory_skill,
        Path.home() / ".pi" / "skills" / "memory" / "run.sh",
        Path(__file__).parent.parent / "memory" / "run.sh",
    ]:
        if alt.exists():
            memory_skill = alt
            break

    if not memory_skill.exists():
        raise FileNotFoundError("Memory skill not found")

    cmd = [
        str(memory_skill), "learn",
        "--content", json.dumps(entry),
        "--tags", f"compliance,{entry['framework'].lower()},audit",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30
    )

    return result.returncode == 0


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

    memory_skill = Path.home() / ".pi" / "agent" / "skills" / "memory" / "run.sh"
    for alt in [
        memory_skill,
        Path.home() / ".pi" / "skills" / "memory" / "run.sh",
        Path(__file__).parent.parent / "memory" / "run.sh",
    ]:
        if alt.exists():
            memory_skill = alt
            break

    if memory_skill.exists():
        try:
            cmd = [str(memory_skill), "recall", "--q", query, "--k", str(limit)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass

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
