#!/usr/bin/env python3
"""
Amend legacy QRAs with new schema fields using /create-evidence-case.

Uses the daemon's /create-evidence-case endpoint for deterministic:
- Entity extraction (flashtext)
- Crosswalk chain resolution
- Framework relationship detection

Adds: qra_type, sparta_linked, source_framework, source_id, target_framework, target_id

Usage:
    python amend_legacy_qras.py stats              # Current field coverage
    python amend_legacy_qras.py amend --dry-run    # Preview changes
    python amend_legacy_qras.py amend --all        # Full run
"""

import json
import httpx
import typer
from typing import Optional

app = typer.Typer()

MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
COLLECTION = "sparta_qra"


def get_client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=60.0)


def build_evidence_case(client: httpx.Client, question: str) -> dict:
    """Call /create-evidence-case for deterministic entity + crosswalk resolution."""
    try:
        resp = client.post("/create-evidence-case", json={"question": question})
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"crosswalk_chains": [], "glossary": []}


def analyze_chains(chains: list) -> dict:
    """Extract framework relationships from crosswalk_chains."""
    result = {
        "sparta_linked": False,
        "source_framework": None,
        "source_id": None,
        "target_framework": None,
        "target_id": None,
        "frameworks_found": set(),
    }

    for chain in chains:
        from_fw = chain.get("from_framework", "")
        to_fw = chain.get("to_framework", "")
        from_id = chain.get("from", "")

        result["frameworks_found"].add(from_fw)
        result["frameworks_found"].add(to_fw)

        # Check for SPARTA involvement
        if from_fw == "SPARTA" or to_fw == "SPARTA":
            result["sparta_linked"] = True

        # First non-SPARTA framework is source
        if not result["source_framework"] and from_fw and from_fw != "SPARTA":
            result["source_framework"] = from_fw
            result["source_id"] = from_id

        # SPARTA in target position
        if to_fw == "SPARTA" and not result["target_framework"]:
            result["target_framework"] = "SPARTA"
            # Get first SPARTA ID from hops
            hops = chain.get("hops", [])
            for hop in hops:
                if hop.get("framework") == "SPARTA" or hop.get("id", "").startswith("SV-"):
                    result["target_id"] = hop["id"]
                    break

    result["frameworks_found"].discard("")
    return result


def determine_qra_type(doc: dict, chain_analysis: dict) -> str:
    """Determine QRA type from document fields and chain analysis."""
    if doc.get("qra_type"):
        return doc["qra_type"]

    # Explicit relationship fields
    if doc.get("source_framework") and doc.get("target_framework"):
        return "relationship"

    # Crosswalk evidence
    if doc.get("crosswalk_chain") or doc.get("bridge_evidence"):
        return "relationship"

    # Multiple frameworks from chain analysis
    if len(chain_analysis.get("frameworks_found", set())) >= 2:
        return "relationship"

    # Standalone indicators
    if doc.get("source_doc") or doc.get("source_url"):
        return "standalone"

    # Single framework
    if len(chain_analysis.get("frameworks_found", set())) == 1:
        return "independent"

    return "legacy"


def amend_document(client: httpx.Client, doc: dict) -> dict | None:
    """Build amendments using /create-evidence-case."""
    # Skip if already has new fields
    if doc.get("qra_type") and doc.get("sparta_linked") is not None:
        return None

    question = doc.get("question", "")
    if not question:
        return None

    evidence = build_evidence_case(client, question)
    chains = evidence.get("crosswalk_chains", [])
    chain_analysis = analyze_chains(chains)

    qra_type = determine_qra_type(doc, chain_analysis)

    amendments = {
        "_key": doc["_key"],
        "qra_type": qra_type,
        "sparta_linked": chain_analysis["sparta_linked"],
    }

    # Add source/target from chain analysis if not present
    if not doc.get("source_framework") and chain_analysis["source_framework"]:
        amendments["source_framework"] = chain_analysis["source_framework"]
        amendments["source_id"] = chain_analysis["source_id"]

    if not doc.get("target_framework") and chain_analysis["target_framework"]:
        amendments["target_framework"] = chain_analysis["target_framework"]
        amendments["target_id"] = chain_analysis["target_id"]

    return amendments


def fetch_qras(client: httpx.Client, filters: dict, limit: int, offset: int = 0) -> tuple[list, int]:
    """Fetch QRAs from memory."""
    resp = client.post("/list", json={
        "collection": COLLECTION,
        "limit": limit,
        "offset": offset,
        "filters": filters if filters else None,
    })
    resp.raise_for_status()
    data = resp.json()
    return data.get("documents", []), data.get("total", 0)


def upsert_batch(client: httpx.Client, documents: list) -> dict:
    """Upsert batch of documents."""
    resp = client.post("/upsert", json={
        "collection": COLLECTION,
        "documents": documents,
    })
    resp.raise_for_status()
    return resp.json()


@app.command()
def amend(
    framework: Optional[str] = typer.Option(None, help="Filter by source_framework"),
    all_qras: bool = typer.Option(False, "--all", help="Process all QRAs"),
    batch_size: int = typer.Option(100, help="Batch size for processing"),
    limit: int = typer.Option(0, help="Max QRAs to process (0=unlimited)"),
    dry_run: bool = typer.Option(False, help="Show changes without writing"),
):
    """Amend legacy QRAs with new schema fields."""
    if not any([framework, all_qras]):
        typer.echo("Specify --framework or --all")
        raise typer.Exit(1)

    client = get_client()

    filters = {}
    if framework:
        filters["source_framework"] = framework

    typer.echo(f"Fetching QRAs (filters: {filters or 'none'})")

    total_processed = 0
    total_amended = 0
    offset = 0

    while True:
        fetch_limit = min(batch_size, limit - total_processed) if limit else batch_size
        if fetch_limit <= 0:
            break

        docs, total = fetch_qras(client, filters, fetch_limit, offset)
        if not docs:
            break

        if offset == 0:
            typer.echo(f"Total matching QRAs: {total:,}")

        typer.echo(f"Processing {len(docs)} QRAs (offset={offset})")

        amendments = []
        for doc in docs:
            amended = amend_document(client, doc)
            if amended:
                amendments.append(amended)

        if amendments:
            if dry_run:
                typer.echo(f"  Would amend {len(amendments)} QRAs:")
                for a in amendments[:3]:
                    typer.echo(f"    {a['_key']}: type={a['qra_type']}, sparta={a['sparta_linked']}")
                if len(amendments) > 3:
                    typer.echo(f"    ... and {len(amendments) - 3} more")
            else:
                upsert_batch(client, amendments)
                typer.echo(f"  Amended {len(amendments)} QRAs")

            total_amended += len(amendments)

        total_processed += len(docs)
        offset += len(docs)

        if len(docs) < batch_size:
            break

    typer.echo(f"\nTotal processed: {total_processed:,}")
    typer.echo(f"Total amended: {total_amended:,}")
    if dry_run:
        typer.echo("(dry run - no changes written)")


@app.command()
def stats():
    """Show current QRA schema field coverage."""
    client = get_client()

    docs, total = fetch_qras(client, {}, 500, 0)  # /list max is 500
    typer.echo(f"Total QRAs: {total:,}")
    typer.echo(f"Sample size: {len(docs)}")
    typer.echo()

    field_counts = {
        "qra_type": 0,
        "sparta_linked": 0,
        "source_framework": 0,
        "source_id": 0,
        "target_framework": 0,
        "target_id": 0,
    }

    qra_types = {}

    for doc in docs:
        for field in field_counts:
            if doc.get(field) is not None:
                field_counts[field] += 1

        qra_type = doc.get("qra_type", "missing")
        qra_types[qra_type] = qra_types.get(qra_type, 0) + 1

    typer.echo("Field coverage:")
    for field, count in field_counts.items():
        pct = count / len(docs) * 100
        typer.echo(f"  {field}: {count} ({pct:.1f}%)")

    typer.echo()
    typer.echo("QRA types:")
    for qra_type, count in sorted(qra_types.items(), key=lambda x: -x[1]):
        pct = count / len(docs) * 100
        typer.echo(f"  {qra_type}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    app()
