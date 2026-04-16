#!/usr/bin/env python3
"""Store monitor-codebase trend snapshots and detect anomalous spikes."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

MEMORY_SOCK = "/run/user/1000/embry/memory.sock"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
HISTORY_FILE_TEMPLATE = "trend_history_{project}.json"
MAX_HISTORY = 30  # rolling window for z-score
SPIKE_Z_THRESHOLD = 2.0  # z-score above which a spike is flagged


def _load_json(path: Path) -> dict:
    """Load a JSON file, returning an empty dict on failure."""
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _extract_total_issues(report: dict) -> int:
    """Return total issues from a monitor-codebase report."""
    summary = report.get("summary", {})
    value = summary.get("total_issues", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _extract_breakdown(report: dict) -> dict:
    """Extract per-category issue counts from report summary."""
    s = report.get("summary", {})
    return {
        "total_bp_violations": s.get("total_bp_violations", 0),
        "total_quality_violations": s.get("total_quality_violations", 0),
        "skills_ci_errors": s.get("skills_ci_errors", 0),
        "skills_ci_warnings": s.get("skills_ci_warnings", 0),
        "total_security_findings": s.get("total_security_findings", 0),
        "duplicate_functions": s.get("duplicate_functions", 0),
        "circular_dependencies": s.get("circular_dependencies", 0),
    }


def _load_history(project: str) -> list[dict]:
    """Load the rolling trend history for a project."""
    path = ARTIFACTS_DIR / HISTORY_FILE_TEMPLATE.format(project=project)
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_history(project: str, history: list[dict]) -> None:
    """Persist the rolling trend history, capped at MAX_HISTORY entries."""
    path = ARTIFACTS_DIR / HISTORY_FILE_TEMPLATE.format(project=project)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    trimmed = history[-MAX_HISTORY:]
    path.write_text(json.dumps(trimmed, indent=2) + "\n")


def detect_anomalies(
    current_total: int,
    current_breakdown: dict,
    history: list[dict],
) -> list[dict]:
    """Detect anomalous spikes using z-score on total and per-category counts.

    Returns a list of anomaly dicts with category, z_score, current, mean, and stddev.
    """
    anomalies: list[dict] = []
    if len(history) < 3:
        return anomalies

    # Check total issues
    totals = [h.get("total_issues", 0) for h in history]
    anomalies.extend(_check_zscore("total_issues", current_total, totals))

    # Check each breakdown category for per-category spikes
    for key, current_val in current_breakdown.items():
        values = [h.get("breakdown", {}).get(key, 0) for h in history]
        anomalies.extend(_check_zscore(key, current_val, values))

    return anomalies


def _check_zscore(category: str, current: int, history_values: list[int]) -> list[dict]:
    """Compute z-score and return anomaly if above threshold."""
    if len(history_values) < 3:
        return []
    mean = sum(history_values) / len(history_values)
    variance = sum((v - mean) ** 2 for v in history_values) / len(history_values)
    stddev = math.sqrt(variance)
    if stddev < 0.5:
        # Very low variance — flag if current is more than 3x the mean + 2
        if current > mean * 3 + 2:
            return [{"category": category, "z_score": float("inf"), "current": current,
                      "mean": round(mean, 2), "stddev": round(stddev, 2), "severity": "high"}]
        return []
    z = (current - mean) / stddev
    if z >= SPIKE_Z_THRESHOLD:
        severity = "critical" if z >= 3.0 else "high"
        return [{"category": category, "z_score": round(z, 2), "current": current,
                  "mean": round(mean, 2), "stddev": round(stddev, 2), "severity": severity}]
    return []


def main() -> int:
    """Read reports, compute trend delta, detect anomalies, and store snapshot."""
    if len(sys.argv) != 4:
        print("Usage: trend_tracker.py <project> <report_file> <previous_report>", file=sys.stderr)
        return 1

    project = sys.argv[1]
    report_path = Path(sys.argv[2])
    prev_arg = sys.argv[3]
    previous_path = Path(prev_arg) if prev_arg else None

    report = _load_json(report_path)
    previous = _load_json(previous_path) if previous_path and previous_path.is_file() else {}

    timestamp = report.get("timestamp", "")
    if isinstance(timestamp, str) and timestamp:
        date = timestamp.split("T", 1)[0]
    else:
        date = datetime.now(timezone.utc).date().isoformat()

    total_issues = _extract_total_issues(report)
    previous_total = _extract_total_issues(previous)
    delta = total_issues - previous_total
    breakdown = _extract_breakdown(report)

    # Anomaly detection against rolling history
    history = _load_history(project)
    anomalies = detect_anomalies(total_issues, breakdown, history)

    # Append current snapshot to history
    snapshot = {"date": date, "total_issues": total_issues, "breakdown": breakdown}
    history.append(snapshot)
    _save_history(project, history)

    # Classify trend
    if anomalies:
        worst = max(a["z_score"] for a in anomalies if a["z_score"] != float("inf"))  if any(a["z_score"] != float("inf") for a in anomalies) else 99.0
        trend_label = f"SPIKE (z={worst:.1f}, {len(anomalies)} anomalies)" if worst < 99 else f"SPIKE ({len(anomalies)} anomalies)"
    elif delta > 0:
        trend_label = f"REGRESSION (+{delta})"
    elif delta < 0:
        trend_label = f"IMPROVED ({delta})"
    else:
        trend_label = "STABLE"

    solution = json.dumps(
        {
            "project": project,
            "date": date,
            "total_issues": total_issues,
            "delta": delta,
            "trend": trend_label,
            "breakdown": breakdown,
            "anomalies": anomalies,
            "history_length": len(history),
        },
        sort_keys=True,
    )

    # Print anomalies to stderr for nightly pipeline visibility
    if anomalies:
        print(f"ANOMALY DETECTED for {project}:", file=sys.stderr)
        for a in anomalies:
            print(f"  {a['category']}: current={a['current']}, mean={a['mean']}, "
                  f"stddev={a['stddev']}, z={a['z_score']}, severity={a['severity']}", file=sys.stderr)

    payload = {
        "problem": f"monitor-codebase trend: {project} {date} [{trend_label}]",
        "solution": solution,
        "scope": "codebase_trends",
        "tags": ["trend", f"project:{project}"]
        + ([f"anomaly:{a['category']}" for a in anomalies] if anomalies else []),
    }

    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCK)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            response = client.post("/learn", json=payload)
            response.raise_for_status()
    except Exception as exc:
        print(f"trend_tracker: failed to store trend for {project}: {exc}", file=sys.stderr)

    # Output trend result as JSON for caller
    result = {"trend": trend_label, "delta": delta, "anomalies": anomalies}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())