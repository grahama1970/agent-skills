#!/usr/bin/env python3
"""
Memory skill integration for security-scan.

Stores scan results for cross-session knowledge and trend analysis.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


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
    """Store entry via memory skill CLI."""
    memory_skill = Path.home() / ".pi" / "agent" / "skills" / "memory" / "run.sh"

    if not memory_skill.exists():
        # Try alternate locations
        for alt in [
            Path.home() / ".pi" / "skills" / "memory" / "run.sh",
            Path(__file__).parent.parent / "memory" / "run.sh",
        ]:
            if alt.exists():
                memory_skill = alt
                break

    if not memory_skill.exists():
        raise FileNotFoundError("Memory skill not found")

    # Store as a learning
    cmd = [
        str(memory_skill), "learn",
        "--content", json.dumps(entry),
        "--tags", "security,scan,findings",
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
    # Try memory skill first
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
