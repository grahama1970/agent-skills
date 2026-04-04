#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "httpx>=0.27", "loguru>=0.7", "rich>=13"]
# ///
"""Nico QA — Automated data quality audit for the SPARTA Explorer.

Runs deterministic checks against the Express API at localhost:3001 to verify
all 6 ArangoDB collections have complete, non-placeholder data. Produces
structured JSON findings with severity levels.

Design constraint: NO LLM calls, NO browser automation, NO data mutation.
All checks are pure httpx GET/POST against the Express proxy.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import httpx
import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("EXPLORER_API_URL", "http://localhost:3001")
TIMEOUT = int(os.environ.get("NICO_QA_TIMEOUT", "30"))
SAMPLE_SIZE = int(os.environ.get("NICO_QA_SAMPLE_SIZE", "2000"))

COLLECTIONS = [
    "sparta_controls",
    "sparta_qra",
    "sparta_relationships",
    "sparta_urls",
    "sparta_url_knowledge",
    "technique_knowledge",
]

PLACEHOLDER_PATTERNS = ["todo", "tbd", "placeholder", "lorem ipsum", "n/a", "none"]

app = typer.Typer(help="Nico QA — SPARTA Explorer data quality audit")
console = Console()

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _post_list(
    client: httpx.Client,
    collection: str,
    limit: int = 100,
    offset: int = 0,
    filter_: dict | None = None,
) -> dict:
    """POST /api/memory/list for a given collection."""
    payload: dict[str, Any] = {
        "collection": collection,
        "limit": limit,
        "offset": offset,
    }
    if filter_:
        payload["filter"] = filter_
    resp = client.post(f"{BASE_URL}/api/memory/list", json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def count_collection(client: httpx.Client, collection: str) -> int:
    """Return total count for a collection (limit=0 query)."""
    data = _post_list(client, collection, limit=0)
    return data.get("total", 0)


def paginate_collection(
    client: httpx.Client,
    collection: str,
    page_size: int = 500,
    max_pages: int | None = None,
) -> list[dict]:
    """Paginate through an entire collection. Returns all items."""
    items: list[dict] = []
    offset = 0
    page = 0
    while True:
        data = _post_list(client, collection, limit=page_size, offset=offset)
        batch = data.get("items", [])
        items.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
        page += 1
        if max_pages and page >= max_pages:
            break
    return items


def sample_collection(
    client: httpx.Client,
    collection: str,
    n: int,
    page_size: int = 500,
) -> list[dict]:
    """Sample n items from a collection using random offset pages."""
    total = count_collection(client, collection)
    if total == 0:
        return []
    if total <= n:
        return paginate_collection(client, collection, page_size=page_size)

    # Sample random offsets
    sampled: list[dict] = []
    offsets_tried: set[int] = set()
    while len(sampled) < n:
        offset = random.randint(0, max(0, total - page_size))
        if offset in offsets_tried:
            continue
        offsets_tried.add(offset)
        data = _post_list(client, collection, limit=page_size, offset=offset)
        batch = data.get("items", [])
        sampled.extend(batch)
        if not batch:
            break
    return sampled[:n]


# ---------------------------------------------------------------------------
# Finding builder
# ---------------------------------------------------------------------------


def finding(
    severity: str,
    category: str,
    message: str,
    count: int,
    sample_ids: list[str] | None = None,
    details: dict | None = None,
) -> dict:
    """Build a standardised finding dict."""
    f: dict[str, Any] = {
        "severity": severity,
        "category": category,
        "message": message,
        "count": count,
        "sample_ids": (sample_ids or [])[:50],
    }
    if details:
        f["details"] = details
    return f


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_controls_empty_description(client: httpx.Client) -> dict:
    """Check 1: Controls with empty or placeholder descriptions."""
    logger.info("Check 1: Controls — empty/placeholder descriptions")
    controls = paginate_collection(client, "sparta_controls")
    bad_ids: list[str] = []
    for c in controls:
        desc = (c.get("description") or "").strip()
        cid = c.get("control_id", c.get("_key", "unknown"))
        if not desc or len(desc) < 20:
            bad_ids.append(cid)
            continue
        if any(p in desc.lower() for p in PLACEHOLDER_PATTERNS):
            bad_ids.append(cid)
    return finding(
        severity="high",
        category="controls_empty_description",
        message=f"{len(bad_ids)} controls have empty or placeholder descriptions",
        count=len(bad_ids),
        sample_ids=bad_ids[:50],
    )


def check_controls_framework_distribution(client: httpx.Client) -> dict:
    """Check 2: Framework distribution across controls."""
    logger.info("Check 2: Controls — framework distribution")
    controls = paginate_collection(client, "sparta_controls")
    dist = Counter(c.get("source_framework", "UNKNOWN") for c in controls)
    dist_sorted = dict(dist.most_common())
    parts = ", ".join(f"{k}={v}" for k, v in dist_sorted.items())
    return finding(
        severity="info",
        category="controls_framework_distribution",
        message=f"Framework distribution: {parts}",
        count=len(dist_sorted),
        details=dist_sorted,
    )


def check_qra_zero_coverage(client: httpx.Client) -> dict:
    """Check 3: Controls that have zero QRAs."""
    logger.info("Check 3: QRAs — controls with zero coverage")
    controls = paginate_collection(client, "sparta_controls")
    all_control_ids = {c.get("control_id", c.get("_key")) for c in controls}

    # Get distinct control_ids from QRAs by sampling pages across the collection
    qra_control_ids: set[str] = set()
    total_qras = count_collection(client, "sparta_qra")
    if total_qras > 0:
        # Sample pages spread across the collection to get coverage of control_ids
        page_size = 500
        num_pages = min(100, (total_qras // page_size) + 1)
        step = max(1, total_qras // num_pages)
        for i in range(num_pages):
            offset = i * step
            data = _post_list(client, "sparta_qra", limit=page_size, offset=offset)
            for item in data.get("items", []):
                cid = item.get("control_id")
                if cid:
                    qra_control_ids.add(cid)

    gap = all_control_ids - qra_control_ids
    return finding(
        severity="high",
        category="qra_zero_coverage",
        message=f"{len(gap)} controls have 0 QRAs",
        count=len(gap),
        sample_ids=sorted(gap)[:50],
    )


def check_qra_placeholder_reasoning(client: httpx.Client) -> dict:
    """Check 4: QRAs with placeholder or generic reasoning."""
    logger.info("Check 4: QRAs — placeholder reasoning (sampling)")
    sampled = sample_collection(client, "sparta_qra", SAMPLE_SIZE)
    bad_ids: list[str] = []
    for q in sampled:
        reasoning = (q.get("reasoning") or "").strip()
        answer = (q.get("answer") or "").strip()
        question = (q.get("question") or "").strip()
        cid = q.get("control_id", q.get("_key", "unknown"))

        is_bad = False
        for field in [reasoning, answer]:
            if not field or len(field) < 30:
                is_bad = True
                break
            if field.lower().startswith("this is"):
                is_bad = True
                break
            if any(p in field.lower() for p in PLACEHOLDER_PATTERNS):
                is_bad = True
                break
        if not is_bad and answer and question and answer.strip() == question.strip():
            is_bad = True

        if is_bad:
            bad_ids.append(cid)

    pct = (len(bad_ids) / len(sampled) * 100) if sampled else 0
    return finding(
        severity="medium",
        category="qra_placeholder_reasoning",
        message=f"{len(bad_ids)} of {len(sampled)} sampled QRAs have placeholder or generic reasoning ({pct:.1f}%)",
        count=len(bad_ids),
        sample_ids=bad_ids[:50],
    )


def check_url_zero_coverage(client: httpx.Client) -> dict:
    """Check 5: Controls with no associated URLs."""
    logger.info("Check 5: URLs — controls with zero URL coverage")
    controls = paginate_collection(client, "sparta_controls")
    all_control_ids = {c.get("control_id", c.get("_key")) for c in controls}

    # Get control_ids referenced in url_knowledge
    url_control_ids: set[str] = set()
    knowledge_items = paginate_collection(client, "sparta_url_knowledge", page_size=500, max_pages=200)
    for item in knowledge_items:
        cids = item.get("control_ids", [])
        if isinstance(cids, list):
            url_control_ids.update(cids)
        elif isinstance(cids, str):
            url_control_ids.add(cids)

    gap = all_control_ids - url_control_ids
    return finding(
        severity="medium",
        category="url_zero_coverage",
        message=f"{len(gap)} controls have no associated URLs",
        count=len(gap),
        sample_ids=sorted(gap)[:50],
    )


def check_url_domain_errors(client: httpx.Client) -> dict:
    """Check 6: URLs with error status codes grouped by domain."""
    logger.info("Check 6: URLs — domain error distribution")
    urls = paginate_collection(client, "sparta_urls")
    error_domains: Counter[str] = Counter()
    for u in urls:
        status = u.get("status_code")
        if status is not None and (isinstance(status, int) and status >= 400):
            domain = u.get("domain", "unknown")
            error_domains[domain] += 1
        elif status is None:
            domain = u.get("domain", "unknown")
            error_domains[domain] += 1

    total_errors = sum(error_domains.values())
    top = dict(error_domains.most_common(10))
    parts = ", ".join(f"{k} ({v})" for k, v in error_domains.most_common(5) if v > 10)
    msg = f"{len(error_domains)} domains have error URLs (total {total_errors})"
    if parts:
        msg += f": {parts}"
    return finding(
        severity="medium",
        category="url_domain_errors",
        message=msg,
        count=total_errors,
        details=top,
    )


def check_relationship_orphans(client: httpx.Client) -> dict:
    """Check 7: Controls with zero relationships (orphan nodes)."""
    logger.info("Check 7: Relationships — orphan controls")
    controls = paginate_collection(client, "sparta_controls")
    all_control_ids = {c.get("control_id", c.get("_key")) for c in controls}

    # Collect distinct source/target IDs from relationships
    rel_ids: set[str] = set()
    rels = paginate_collection(client, "sparta_relationships", page_size=500, max_pages=300)
    for r in rels:
        src = r.get("source_control_id")
        tgt = r.get("target_control_id")
        if src:
            rel_ids.add(src)
        if tgt:
            rel_ids.add(tgt)

    orphans = all_control_ids - rel_ids
    return finding(
        severity="low",
        category="relationship_orphan_controls",
        message=f"{len(orphans)} controls have no relationships (disconnected nodes)",
        count=len(orphans),
        sample_ids=sorted(orphans)[:50],
    )


def check_knowledge_zero_chunks(client: httpx.Client) -> dict:
    """Check 8: URLs with zero extracted knowledge chunks."""
    logger.info("Check 8: Knowledge — URLs with zero chunks")
    urls = paginate_collection(client, "sparta_urls")
    all_url_ids = {u.get("url_id", u.get("_key")) for u in urls}

    knowledge_url_ids: set[str] = set()
    knowledge = paginate_collection(client, "sparta_url_knowledge", page_size=500, max_pages=200)
    for k in knowledge:
        uid = k.get("url_id")
        if uid:
            knowledge_url_ids.add(uid)

    zero_chunk = all_url_ids - knowledge_url_ids
    # Get sample URLs for context
    zero_chunk_list = sorted(zero_chunk)[:50]
    sample_urls = []
    url_map = {u.get("url_id", u.get("_key")): u.get("url", "") for u in urls}
    for uid in zero_chunk_list[:10]:
        url_str = url_map.get(uid, "")
        if url_str:
            sample_urls.append(url_str)

    return finding(
        severity="medium",
        category="knowledge_zero_chunks",
        message=f"{len(zero_chunk)} URLs have 0 extracted knowledge chunks",
        count=len(zero_chunk),
        sample_ids=zero_chunk_list,
        details={"sample_urls": sample_urls} if sample_urls else None,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    check_controls_empty_description,
    check_controls_framework_distribution,
    check_qra_zero_coverage,
    check_qra_placeholder_reasoning,
    check_url_zero_coverage,
    check_url_domain_errors,
    check_relationship_orphans,
    check_knowledge_zero_chunks,
]


def run_audit(checks: list | None = None) -> dict:
    """Execute all checks and return the audit result dict."""
    start = time.monotonic()
    findings: list[dict] = []
    errors: list[str] = []

    try:
        client = httpx.Client(timeout=TIMEOUT)
        # Quick connectivity check
        test = _post_list(client, "sparta_controls", limit=1)
        if "total" not in test and "items" not in test:
            logger.error("API responded but format unexpected: {}", test)
    except httpx.ConnectError:
        logger.error("Cannot connect to Explorer API at {}", BASE_URL)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(time.monotonic() - start, 2),
            "explorer_api": BASE_URL,
            "collections_checked": 0,
            "error": f"Cannot connect to Explorer API at {BASE_URL}. Is the Express server running?",
            "findings": [],
            "summary": {"total_findings": 0, "by_severity": {}, "errors": 1, "warnings": 0},
        }
    except httpx.HTTPStatusError as exc:
        logger.error("API returned error: {}", exc)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(time.monotonic() - start, 2),
            "explorer_api": BASE_URL,
            "collections_checked": 0,
            "error": f"API error: {exc}",
            "findings": [],
            "summary": {"total_findings": 0, "by_severity": {}, "errors": 1, "warnings": 0},
        }

    check_fns = checks or ALL_CHECKS
    for check_fn in check_fns:
        try:
            result = check_fn(client)
            findings.append(result)
            logger.info("  -> {} (count={})", result["category"], result["count"])
        except Exception as exc:
            name = getattr(check_fn, "__name__", str(check_fn))
            logger.error("Check {} failed: {}", name, exc)
            errors.append(f"{name}: {exc}")

    client.close()

    elapsed = round(time.monotonic() - start, 2)
    severity_counts: Counter[str] = Counter()
    for f in findings:
        severity_counts[f["severity"]] += 1

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": elapsed,
        "explorer_api": BASE_URL,
        "collections_checked": len(COLLECTIONS),
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_severity": dict(severity_counts),
            "errors": len(errors),
            "warnings": 0,
        },
    }


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@app.command()
def audit(
    output: str = typer.Option("", "--output", "-o", help="Write JSON to file instead of stdout"),
) -> None:
    """Run all 8 data quality checks against the Explorer API."""
    logger.info("Starting Nico QA audit against {}", BASE_URL)
    result = run_audit()

    json_str = json.dumps(result, indent=2, default=str)
    if output:
        with open(output, "w") as f:
            f.write(json_str)
        logger.info("Audit written to {}", output)
    else:
        print(json_str)


@app.command()
def report(
    input_file: str = typer.Option("", "--input", "-i", help="Read from previous audit JSON file"),
) -> None:
    """Pretty-print audit findings as a Rich table."""
    if input_file:
        with open(input_file) as f:
            result = json.load(f)
    else:
        logger.info("No input file — running fresh audit")
        result = run_audit()

    if result.get("error"):
        console.print(f"[bold red]ERROR:[/bold red] {result['error']}")
        raise typer.Exit(code=1)

    # Header
    console.print()
    console.print(f"[bold]Nico QA Audit Report[/bold]  {result['timestamp']}")
    console.print(f"API: {result['explorer_api']}  Duration: {result['duration_seconds']}s")
    console.print()

    # Summary
    summary = result.get("summary", {})
    sev = summary.get("by_severity", {})
    console.print(
        f"Findings: [red]{sev.get('high', 0)} high[/red]  "
        f"[yellow]{sev.get('medium', 0)} medium[/yellow]  "
        f"[blue]{sev.get('low', 0)} low[/blue]  "
        f"[dim]{sev.get('info', 0)} info[/dim]"
    )
    console.print()

    # Findings table
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    sorted_findings = sorted(
        result.get("findings", []),
        key=lambda f: severity_order.get(f.get("severity", "info"), 9),
    )

    table = Table(show_header=True, header_style="bold")
    table.add_column("Sev", width=6)
    table.add_column("Category", min_width=30)
    table.add_column("Count", justify="right", width=8)
    table.add_column("Message", min_width=40)

    sev_style = {"high": "red", "medium": "yellow", "low": "blue", "info": "dim"}
    for f in sorted_findings:
        sev = f.get("severity", "info")
        style = sev_style.get(sev, "")
        table.add_row(
            f"[{style}]{sev}[/{style}]",
            f["category"],
            str(f["count"]),
            f["message"],
        )

    console.print(table)

    # Sample IDs for high-severity findings
    for f in sorted_findings:
        if f.get("severity") == "high" and f.get("sample_ids"):
            console.print(f"\n[red bold]{f['category']}[/red bold] sample IDs:")
            for sid in f["sample_ids"][:20]:
                console.print(f"  - {sid}")


@app.command()
def screenshot() -> None:
    """Print /surf commands for visual verification (delegate to /surf)."""
    ui_url = os.environ.get("EXPLORER_UI_URL", "http://localhost:3002")
    console.print("[bold]Screenshot mode[/bold] — use /surf to capture Explorer tabs:")
    console.print(f"  1. surf navigate {ui_url}")
    console.print("  2. surf screenshot  (Overview tab)")
    console.print("  3. Click Controls tab, surf screenshot")
    console.print("  4. Click QRAs tab, surf screenshot")
    console.print()
    console.print("This command does not automate the browser. Invoke /surf directly.")


if __name__ == "__main__":
    app()
