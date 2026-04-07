"""Convergence tracking and fix suggestion logic.

Tracks issue counts over time to detect improvement/regression trends,
and provides specific remediation guidance for failing checks.
"""

import json
from typing import List

from config import CONVERGENCE_FILE, FIX_SUGGESTIONS


def track_convergence(findings: dict, run_id: str):
    """Track issue counts over time for convergence analysis."""
    entry = {
        "timestamp": findings.get("timestamp", ""),
        "run_id": run_id,
        "total_issues": findings.get("total_issues_found", 0),
        "status": findings.get("overall_status", "UNKNOWN"),
        "check_results": {
            k: v.get("status", "UNKNOWN")
            for k, v in findings.items()
            if isinstance(v, dict) and "status" in v
        },
        "issue_counts": {
            k: len(v.get("issues", []))
            for k, v in findings.items()
            if isinstance(v, dict) and "issues" in v
        },
    }

    # Append to convergence file
    with open(CONVERGENCE_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_convergence_history() -> List[dict]:
    """Load convergence history."""
    if not CONVERGENCE_FILE.exists():
        return []
    entries = []
    with open(CONVERGENCE_FILE, "r") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def analyze_convergence() -> dict:
    """Analyze convergence trend over time."""
    history = get_convergence_history()
    if len(history) < 2:
        return {"status": "INSUFFICIENT_DATA", "message": "Need at least 2 runs to analyze trend"}

    recent = history[-5:]  # Last 5 runs
    issue_counts = [e["total_issues"] for e in recent]

    # Calculate trend
    if len(issue_counts) >= 2:
        trend = issue_counts[-1] - issue_counts[0]
        avg_issues = sum(issue_counts) / len(issue_counts)

        if trend < 0:
            status = "IMPROVING"
            message = f"Issues decreased from {issue_counts[0]} to {issue_counts[-1]}"
        elif trend == 0:
            status = "STABLE"
            message = f"Issues stable at ~{avg_issues:.1f}"
        else:
            status = "REGRESSING"
            message = f"Issues increased from {issue_counts[0]} to {issue_counts[-1]}"
    else:
        status = "UNKNOWN"
        message = "Not enough data points"

    return {
        "status": status,
        "message": message,
        "history": [{"timestamp": e["timestamp"], "issues": e["total_issues"]} for e in recent],
        "current_issues": issue_counts[-1] if issue_counts else 0,
    }


def suggest_fixes(findings: dict) -> List[dict]:
    """Suggest specific fixes for each failing check."""
    suggestions = []

    for check_name, check_data in findings.items():
        if not isinstance(check_data, dict):
            continue
        if check_data.get("status") in ["FAIL", "WARN"]:
            fix_info = FIX_SUGGESTIONS.get(check_name, {})
            if fix_info:
                suggestions.append({
                    "check": check_name,
                    "status": check_data.get("status"),
                    "description": fix_info.get("description"),
                    "root_cause": fix_info.get("root_cause"),
                    "severity": fix_info.get("severity"),
                    "owner": fix_info.get("owner"),
                    "fixes": fix_info.get("fixes", []),
                    "issues_found": len(check_data.get("issues", [])),
                })

    # Sort by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    suggestions.sort(key=lambda x: severity_order.get(x.get("severity", "LOW"), 4))

    return suggestions
