#!/usr/bin/env python3
"""Stratified QRA Sample Extractor for Sensai Cascade v2.

Extracts a 500-QRA stratified sample from sparta_qra via the memory daemon,
proportional to tactical_tags distribution with minimum guarantees for
rare categories.

Usage:
    python stratified_sample.py [--total 500] [--output /tmp/sensai_v2_sample_500.jsonl] [--seed 42]
    python stratified_sample.py sample --total 500 --seed 42

Architecture:
    - All ArangoDB access goes through /memory daemon (httpx -> Unix socket)
    - NO bespoke AQL queries
    - Composes with /quality-audit sampling concepts
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import typer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MEMORY_SOCKET = os.environ.get(
    "EMBRY_MEMORY_SOCKET",
    f"/run/user/{os.getuid()}/embry/memory.sock",
)

# Fallback: if the daemon is running in dev HTTP mode
MEMORY_HTTP_URL = os.environ.get("EMBRY_MEMORY_HTTP_URL", "")

# Tactical tag distribution from 218K sparta_qra corpus (MEMORY.md)
# Proportional targets for a 500-QRA sample
TACTICAL_TAGS = {
    "Harden":  {"population": 156_000, "pct": 0.45},
    "Detect":  {"population":  75_000, "pct": 0.22},
    "Isolate": {"population":  56_000, "pct": 0.16},
    "Model":   {"population":  20_000, "pct": 0.06},
    "Exploit": {"population":  16_000, "pct": 0.05},
    "Restore": {"population":   8_000, "pct": 0.025},
    "Evade":   {"population":   4_000, "pct": 0.015},
    "Persist": {"population":   3_000, "pct": 0.01},
}

# Minimum samples per rare category
MINIMUM_PER_CATEGORY = 20

# Regex for control IDs: ATT&CK (T1234, T1234.001), NIST (AC-2, SI-4(1)),
# CWE (CWE-89), STIG (SV-12345), CCI (CCI-001234), D3FEND (D3-FEV)
CONTROL_ID_PATTERN = re.compile(
    r"\b("
    r"T\d{4}(?:\.\d{3})?"       # ATT&CK: T1547, T1588.001
    r"|[A-Z]{2}-\d+(?:\(\d+\))?" # NIST: AC-2, SI-4(1)
    r"|CWE-\d+"                   # CWE: CWE-89
    r"|SV-\d+"                    # STIG: SV-12345
    r"|CCI-\d+"                   # CCI: CCI-001234
    r"|D3-[A-Z]{2,5}"            # D3FEND: D3-FEV
    r"|SRG-[A-Z]+-\d+"           # SRG: SRG-OS-000001
    r")\b"
)

# Recall queries per tactical tag -- diverse queries to get broad coverage
TAG_QUERIES = {
    "Harden": [
        "system hardening countermeasures",
        "configuration management security controls",
        "access control enforcement mechanisms",
        "authentication hardening techniques",
        "network perimeter defense hardening",
        "operating system hardening baseline",
        "application security hardening",
        "cryptographic protection implementation",
    ],
    "Detect": [
        "intrusion detection monitoring",
        "anomaly detection security events",
        "network traffic analysis detection",
        "log monitoring detection capabilities",
        "malware detection techniques",
        "behavioral analysis threat detection",
    ],
    "Isolate": [
        "network segmentation isolation",
        "system isolation containment",
        "privilege separation isolation",
        "sandbox isolation techniques",
        "microsegmentation zero trust",
        "air gap isolation strategy",
    ],
    "Model": [
        "threat modeling attack surface",
        "risk assessment model analysis",
        "attack tree modeling techniques",
        "security architecture modeling",
    ],
    "Exploit": [
        "exploitation technique countermeasure",
        "vulnerability exploitation defense",
        "exploit mitigation controls",
        "offensive security technique analysis",
    ],
    "Restore": [
        "disaster recovery restoration",
        "backup restore procedures",
        "system recovery resilience",
        "incident recovery continuity",
    ],
    "Evade": [
        "defense evasion techniques",
        "evasion detection countermeasures",
        "anti-forensics evasion analysis",
        "stealth evasion mechanisms",
    ],
    "Persist": [
        "persistence mechanism defense",
        "persistent access countermeasures",
        "boot persistence detection",
        "scheduled task persistence analysis",
    ],
}


# ---------------------------------------------------------------------------
# Memory daemon client (httpx over Unix socket)
# ---------------------------------------------------------------------------

def _get_http_client() -> httpx.Client:
    """Create httpx client connected to memory daemon."""
    if MEMORY_HTTP_URL:
        return httpx.Client(base_url=MEMORY_HTTP_URL, timeout=30.0)

    if not Path(MEMORY_SOCKET).exists():
        print(f"ERROR: Memory daemon socket not found: {MEMORY_SOCKET}", file=sys.stderr)
        print("Start the memory daemon or set EMBRY_MEMORY_HTTP_URL.", file=sys.stderr)
        sys.exit(1)

    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    return httpx.Client(
        transport=transport,
        base_url="http://memory-daemon",
        timeout=30.0,
    )


def recall_qras(
    client: httpx.Client,
    query: str,
    limit: int = 50,
    scope: str = "sparta_qra",
) -> list[dict[str, Any]]:
    """Recall QRAs from the memory daemon via /recall endpoint.

    Args:
        client: httpx client connected to memory daemon
        query: Search query text
        limit: Max results to return
        scope: Memory scope (sparta_qra for SPARTA collection)

    Returns:
        List of QRA dicts from memory
    """
    try:
        resp = client.post(
            "/recall",
            json={"q": query, "scope": scope, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])
    except httpx.HTTPStatusError as exc:
        print(f"  WARNING: Recall failed ({exc.response.status_code}): {query[:60]}", file=sys.stderr)
        return []
    except Exception as exc:
        print(f"  WARNING: Recall error: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Control-to-control comparison detection
# ---------------------------------------------------------------------------

def detect_control_comparison(question: str) -> dict[str, Any]:
    """Detect if a question is a control-to-control comparison.

    Heuristic: question contains 2+ distinct control IDs, suggesting
    a comparison like "How does T1659 prevent T1588.001?"

    Returns:
        dict with 'is_comparison' bool and 'control_ids' list
    """
    matches = CONTROL_ID_PATTERN.findall(question)
    unique_ids = list(dict.fromkeys(matches))  # preserve order, deduplicate
    return {
        "is_comparison": len(unique_ids) >= 2,
        "control_ids": unique_ids,
    }


# ---------------------------------------------------------------------------
# Stratified sampling with minimum guarantees
# ---------------------------------------------------------------------------

def compute_allocation(total: int, tags: dict[str, dict]) -> dict[str, int]:
    """Compute per-tag sample allocation with minimum guarantees.

    Algorithm:
    1. Assign MINIMUM_PER_CATEGORY to all tags
    2. Distribute remaining budget proportionally
    3. Adjust rounding to hit exact total

    Args:
        total: Total sample size
        tags: Tag distribution info

    Returns:
        Dict mapping tag -> sample count
    """
    n_tags = len(tags)
    guaranteed = MINIMUM_PER_CATEGORY * n_tags  # 20 * 8 = 160

    if guaranteed > total:
        # If minimums exceed total, distribute evenly
        base = total // n_tags
        allocation = {tag: base for tag in tags}
        remainder = total - base * n_tags
        for i, tag in enumerate(tags):
            if i < remainder:
                allocation[tag] += 1
        return allocation

    remaining = total - guaranteed
    allocation = {}

    # Proportional allocation of remaining budget
    total_pct = sum(t["pct"] for t in tags.values())
    raw_alloc = {}
    for tag, info in tags.items():
        prop = (info["pct"] / total_pct) * remaining
        raw_alloc[tag] = prop

    # Floor + distribute remainders
    for tag in tags:
        allocation[tag] = MINIMUM_PER_CATEGORY + int(raw_alloc[tag])

    # Fix rounding gap
    current_total = sum(allocation.values())
    gap = total - current_total
    if gap > 0:
        # Give extra to largest strata (most representative)
        sorted_tags = sorted(tags.keys(), key=lambda t: tags[t]["pct"], reverse=True)
        for i in range(gap):
            allocation[sorted_tags[i % n_tags]] += 1
    elif gap < 0:
        # Remove from largest strata
        sorted_tags = sorted(tags.keys(), key=lambda t: tags[t]["pct"], reverse=True)
        for i in range(-gap):
            if allocation[sorted_tags[i % n_tags]] > MINIMUM_PER_CATEGORY:
                allocation[sorted_tags[i % n_tags]] -= 1

    return allocation


def deduplicate_qras(qras: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate QRAs by content hash (question + answer).

    Uses a SHA256 hash of question + answer text to detect duplicates.
    """
    seen: set[str] = set()
    unique = []
    for qra in qras:
        q = qra.get("question", qra.get("problem", ""))
        a = qra.get("answer", qra.get("solution", ""))
        content_hash = hashlib.sha256(f"{q}|||{a}".encode()).hexdigest()[:16]
        if content_hash not in seen:
            seen.add(content_hash)
            unique.append(qra)
    return unique


def extract_tactical_tag(qra: dict[str, Any]) -> str | None:
    """Extract primary tactical tag from a QRA.

    Handles both list and string formats for tactical_tags field.
    """
    tags = qra.get("tactical_tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, ValueError):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
    if isinstance(tags, list) and tags:
        return tags[0]
    return None


# ---------------------------------------------------------------------------
# Main sampling pipeline
# ---------------------------------------------------------------------------

def run_sampling(
    total: int = 500,
    output_path: str = "/tmp/sensai_v2_sample_500.jsonl",
    seed: int = 42,
) -> dict[str, Any]:
    """Execute the stratified sampling pipeline.

    Steps:
    1. Connect to memory daemon
    2. Recall QRAs per tactical tag using diverse queries
    3. Deduplicate and pool per tag
    4. Stratified random sample with minimum guarantees
    5. Flag control-to-control comparisons
    6. Write JSONL output

    Returns:
        Summary statistics dict
    """
    random.seed(seed)
    print(f"Stratified QRA Sampler — target={total}, seed={seed}")
    print(f"Output: {output_path}")
    print()

    # Step 1: Compute allocation
    allocation = compute_allocation(total, TACTICAL_TAGS)
    print("Target allocation:")
    for tag, count in allocation.items():
        print(f"  {tag:10s}: {count:4d} ({TACTICAL_TAGS[tag]['pct']*100:.1f}%)")
    print()

    # Step 2: Connect to memory daemon
    client = _get_http_client()

    # Step 3: Recall QRAs per tag
    pools: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_hashes: set[str] = set()  # global dedup across tags

    for tag, queries in TAG_QUERIES.items():
        print(f"Recalling QRAs for [{tag}]...")
        tag_qras = []

        for query in queries:
            items = recall_qras(client, query, limit=100, scope="sparta_qra")
            for item in items:
                # Filter: must have this tactical tag
                item_tags = item.get("tactical_tags", [])
                if isinstance(item_tags, str):
                    try:
                        item_tags = json.loads(item_tags)
                    except (json.JSONDecodeError, ValueError):
                        item_tags = [t.strip() for t in item_tags.split(",") if t.strip()]

                if tag in (item_tags or []):
                    # Dedup
                    q = item.get("question", item.get("problem", ""))
                    a = item.get("answer", item.get("solution", ""))
                    h = hashlib.sha256(f"{q}|||{a}".encode()).hexdigest()[:16]
                    if h not in seen_hashes:
                        seen_hashes.add(h)
                        tag_qras.append(item)

        pools[tag] = tag_qras
        print(f"  {tag}: {len(tag_qras)} unique QRAs retrieved")

    print()
    client.close()

    # Step 4: Stratified sampling
    sampled: list[dict[str, Any]] = []
    actual_allocation: dict[str, int] = {}
    shortfall_tags: list[str] = []

    for tag, target_count in allocation.items():
        pool = pools.get(tag, [])
        if len(pool) < target_count:
            shortfall_tags.append(tag)
            print(
                f"  WARNING: {tag} has only {len(pool)} QRAs "
                f"(need {target_count}). Taking all available."
            )
            sample = pool
        else:
            sample = random.sample(pool, target_count)

        actual_allocation[tag] = len(sample)
        for qra in sample:
            qra["_sampled_tag"] = tag
            sampled.append(qra)

    # Redistribute shortfall budget to larger pools
    shortfall_total = sum(
        allocation[t] - actual_allocation[t] for t in shortfall_tags
    )
    if shortfall_total > 0:
        print(f"\n  Redistributing {shortfall_total} shortfall samples...")
        available_tags = [
            t for t in allocation
            if t not in shortfall_tags and len(pools[t]) > actual_allocation[t]
        ]
        if available_tags:
            per_tag_extra = shortfall_total // len(available_tags)
            remainder = shortfall_total % len(available_tags)
            for i, tag in enumerate(available_tags):
                extra = per_tag_extra + (1 if i < remainder else 0)
                pool = pools[tag]
                already_sampled = {
                    hashlib.sha256(
                        f"{q.get('question', q.get('problem', ''))}|||"
                        f"{q.get('answer', q.get('solution', ''))}".encode()
                    ).hexdigest()[:16]
                    for q in sampled if q.get("_sampled_tag") == tag
                }
                remaining_pool = [
                    q for q in pool
                    if hashlib.sha256(
                        f"{q.get('question', q.get('problem', ''))}|||"
                        f"{q.get('answer', q.get('solution', ''))}".encode()
                    ).hexdigest()[:16] not in already_sampled
                ]
                take = min(extra, len(remaining_pool))
                if take > 0:
                    extras = random.sample(remaining_pool, take)
                    for qra in extras:
                        qra["_sampled_tag"] = tag
                        sampled.append(qra)
                    actual_allocation[tag] += take
                    print(f"    {tag}: +{take} extra samples")

    # Step 5: Flag control-to-control comparisons
    comparison_count = 0
    for qra in sampled:
        question = qra.get("question", qra.get("problem", ""))
        comparison = detect_control_comparison(question)
        qra["_control_comparison"] = comparison["is_comparison"]
        qra["_control_ids"] = comparison["control_ids"]
        if comparison["is_comparison"]:
            comparison_count += 1

    # Step 6: Write JSONL
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        for qra in sampled:
            f.write(json.dumps(qra, ensure_ascii=False, default=str) + "\n")

    # Summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "target_total": total,
        "actual_total": len(sampled),
        "allocation": actual_allocation,
        "shortfall_tags": shortfall_tags,
        "control_comparisons": comparison_count,
        "output_path": str(output_file),
    }

    print(f"\n{'='*60}")
    print(f"SAMPLE COMPLETE")
    print(f"{'='*60}")
    print(f"Total QRAs sampled: {len(sampled)}")
    print(f"Control-to-control comparisons flagged: {comparison_count}")
    print()
    print("Per-tag breakdown:")
    for tag in TACTICAL_TAGS:
        target = allocation[tag]
        actual = actual_allocation.get(tag, 0)
        marker = " (SHORTFALL)" if tag in shortfall_tags else ""
        print(f"  {tag:10s}: {actual:4d} / {target:4d} target{marker}")
    print()
    print(f"Output: {output_file}")

    # Write summary sidecar
    summary_path = output_file.with_suffix(".summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary: {summary_path}")

    return summary


# ---------------------------------------------------------------------------
# CLI (typer)
# ---------------------------------------------------------------------------

app = typer.Typer(help="Stratified QRA sample from sparta_qra via /memory daemon")


@app.command()
def sample(
    total: int = typer.Option(500, help="Total sample size"),
    output: str = typer.Option(
        "/tmp/sensai_v2_sample_500.jsonl", help="Output JSONL path"
    ),
    seed: int = typer.Option(42, help="Random seed for reproducibility"),
) -> None:
    """Extract a stratified QRA sample from sparta_qra."""
    summary = run_sampling(total=total, output_path=output, seed=seed)

    # Exit with error if we got significantly fewer than target
    if summary["actual_total"] < summary["target_total"] * 0.8:
        typer.echo(
            f"\nWARNING: Only got {summary['actual_total']}/{summary['target_total']} "
            f"QRAs ({summary['actual_total']/summary['target_total']*100:.0f}%). "
            f"Check memory daemon connectivity and sparta_qra collection.",
            err=True,
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
