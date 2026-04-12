#!/usr/bin/env python3
"""Analyze misuse_events and propose corrections.

Nightly job that:
1. Queries misuse_events from last N hours
2. Filters for unknown patterns (was_known=false)
3. Clusters similar errors
4. Proposes corrections via LLM
5. Stores proposals in misuse_corrections collection
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict

import httpx


MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
SCILLM_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_KEY = "sk-dev-proxy-123"


def get_memory_client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)


def fetch_recent_events(client: httpx.Client, hours: int) -> list[dict]:
    """Fetch misuse events from the last N hours."""
    cutoff = int(time.time()) - (hours * 3600)

    resp = client.post("/list", json={
        "collection": "misuse_events",
        "limit": 1000,
        "filters": {},
    })

    if resp.status_code != 200:
        print(f"Failed to fetch events: {resp.status_code}")
        return []

    data = resp.json()
    events = data.get("documents", [])

    # Filter by timestamp and unknown patterns
    recent = [
        e for e in events
        if e.get("ts", 0) >= cutoff
    ]

    print(f"Found {len(recent)} events in last {hours}h ({len(events)} total)")
    return recent


def cluster_events(events: list[dict]) -> dict[str, list[dict]]:
    """Group events by skill + error_type."""
    clusters: dict[str, list[dict]] = defaultdict(list)

    for event in events:
        key = f"{event.get('skill', 'unknown')}:{event.get('error_type', 'unknown')}"
        clusters[key].append(event)

    return dict(clusters)


def propose_correction(
    skill: str,
    error_type: str,
    examples: list[dict],
) -> dict | None:
    """Ask LLM to propose a correction for a cluster of misuses."""
    sent_values = [e.get("sent_value", "") for e in examples]
    total_count = sum(e.get("count", 1) for e in examples)

    # Skip if all were known patterns
    if all(e.get("was_known", False) for e in examples):
        return None

    # Skip small clusters
    if total_count < 3:
        return None

    prompt = f"""Analyze this API misuse pattern and propose a correction.

Skill: {skill}
Error type: {error_type}
Wrong values sent by agents: {json.dumps(sent_values[:10])}
Total occurrences: {total_count}

Based on the pattern, what is the correct value they should use?

Common patterns:
- Plural vs singular collection names (sparta_qras → sparta_qra)
- Typos (sparat_qra → sparta_qra)
- Wrong model names (text-claude → claude-sonnet-4-6)
- Missing required fields

Return JSON only:
{{"correction": "correct_value_or_null", "confidence": 0.0-1.0, "explanation": "why"}}

If you cannot determine a correction, return {{"correction": null, "confidence": 0.0, "explanation": "reason"}}
"""

    try:
        resp = httpx.post(
            SCILLM_URL,
            headers={"Authorization": f"Bearer {SCILLM_KEY}"},
            json={
                "model": "text",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
            timeout=30.0,
        )

        if resp.status_code != 200:
            print(f"LLM call failed: {resp.status_code}")
            return None

        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    except Exception as exc:
        print(f"LLM proposal failed: {exc}")
        return None


def store_proposal(
    client: httpx.Client,
    skill: str,
    error_type: str,
    sent_value: str,
    proposal: dict,
    occurrence_count: int,
    auto_apply: bool,
) -> bool:
    """Store a correction proposal in misuse_corrections collection."""
    correction = proposal.get("correction")
    confidence = proposal.get("confidence", 0.0)

    if not correction:
        return False

    key = hashlib.sha256(f"{skill}:{error_type}:{sent_value}".encode()).hexdigest()[:16]

    # Determine status
    if auto_apply and confidence >= 0.95 and occurrence_count >= 10:
        status = "auto_approved"
    else:
        status = "pending"

    doc = {
        "_key": key,
        "skill": skill,
        "error_type": error_type,
        "sent_value": sent_value,
        "proposed_correction": correction,
        "confidence": confidence,
        "explanation": proposal.get("explanation", ""),
        "occurrence_count": occurrence_count,
        "status": status,
        "proposed_at": int(time.time()),
    }

    resp = client.post("/store", json={
        "document": doc,
        "collection": "misuse_corrections",
    })

    if resp.status_code == 200:
        print(f"  Stored proposal: {sent_value} → {correction} (conf={confidence:.2f}, status={status})")
        return True
    else:
        print(f"  Failed to store proposal: {resp.status_code}")
        return False


def report_to_task_monitor(events_count: int, unknown_count: int, proposals_count: int) -> None:
    """Report status to /task-monitor for dashboard visibility."""
    try:
        import httpx
        # task-monitor uses the same memory socket
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=5.0) as client:
            client.post("/store", json={
                "document": {
                    "_key": "monitor-misuse-status",
                    "skill": "monitor-misuse",
                    "status": "ok" if unknown_count == 0 else "warn",
                    "events_24h": events_count,
                    "unknown_patterns": unknown_count,
                    "proposals_generated": proposals_count,
                    "ts": int(time.time()),
                },
                "collection": "skill_health",
            })
    except Exception as exc:
        print(f"Failed to report to task-monitor: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Analyze misuse events")
    parser.add_argument("--hours", type=int, default=24, help="Time window in hours")
    parser.add_argument("--auto-apply", action="store_true", help="Auto-apply high-confidence corrections")
    args = parser.parse_args()

    print(f"Analyzing misuse events from last {args.hours} hours...")

    client = get_memory_client()
    events = fetch_recent_events(client, args.hours)

    if not events:
        print("No events to analyze")
        report_to_task_monitor(0, 0, 0)
        return

    # Cluster by skill + error_type
    clusters = cluster_events(events)
    print(f"Found {len(clusters)} distinct error clusters")

    # Count unknown patterns
    total_unknown = sum(
        1 for evts in clusters.values()
        for e in evts if not e.get("was_known", False)
    )

    # Process each cluster
    proposals_stored = 0
    for cluster_key, cluster_events in clusters.items():
        skill, error_type = cluster_key.split(":", 1)

        # Get unknown events only
        unknown = [e for e in cluster_events if not e.get("was_known", False)]
        if not unknown:
            continue

        total_count = sum(e.get("count", 1) for e in unknown)
        if total_count < 3:
            continue

        print(f"\nCluster: {skill}/{error_type} ({len(unknown)} unknown, {total_count} total)")

        # Get most common sent_value
        value_counts: dict[str, int] = defaultdict(int)
        for e in unknown:
            value_counts[e.get("sent_value", "")] += e.get("count", 1)

        top_value = max(value_counts, key=value_counts.get)
        print(f"  Top sent_value: {top_value} ({value_counts[top_value]} times)")

        # Propose correction
        proposal = propose_correction(skill, error_type, unknown)
        if proposal and proposal.get("correction"):
            if store_proposal(
                client, skill, error_type, top_value, proposal,
                value_counts[top_value], args.auto_apply
            ):
                proposals_stored += 1

    print(f"\nDone. Stored {proposals_stored} correction proposals.")

    # Report to task-monitor
    report_to_task_monitor(len(events), total_unknown, proposals_stored)


if __name__ == "__main__":
    main()
