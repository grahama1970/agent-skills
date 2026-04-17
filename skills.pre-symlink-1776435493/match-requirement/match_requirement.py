#!/usr/bin/env python3
"""
/match-requirement skill — thin CLI wrapper for memory service /match/* endpoints.

All domain logic lives in the memory service:
  POST /match/requirement — match single requirement
  POST /match/batch — batch match from queue
  GET /match/review-queue — pending reviews
  GET /match/coverage — statistics
"""
from __future__ import annotations

import argparse
import csv
import json
import sys

import httpx

# Memory service endpoint (Unix socket or HTTP)
MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
MEMORY_HTTP = "http://localhost:8601"


def memory_request(endpoint: str, method: str = "GET", payload: dict | None = None, timeout: int = 120) -> dict:
    """Make request to memory daemon."""
    # Try Unix socket first
    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
            if method == "POST":
                resp = client.post(endpoint, json=payload or {})
            else:
                resp = client.get(endpoint, params=payload or {})
            resp.raise_for_status()
            return resp.json()
    except Exception:
        pass

    # Fallback to HTTP
    with httpx.Client(base_url=MEMORY_HTTP, timeout=float(timeout)) as client:
        if method == "POST":
            resp = client.post(endpoint, json=payload or {})
        else:
            resp = client.get(endpoint, params=payload or {})
        resp.raise_for_status()
        return resp.json()


def cmd_match(args):
    """Match a single requirement to controls."""
    result = memory_request(
        "/match/requirement",
        method="POST",
        payload={
            "chunk_key": args.chunk_key,
            "confidence_threshold": args.confidence_threshold,
            "dry_run": args.dry_run,
        },
    )
    print(json.dumps(result, indent=2))

    if result.get("error"):
        sys.exit(1)


def cmd_batch(args):
    """Process batch from proof_jobs queue."""
    result = memory_request(
        "/match/batch",
        method="POST",
        payload={
            "limit": args.limit,
            "confidence_threshold": args.confidence_threshold,
            "dry_run": args.dry_run,
        },
    )
    print(json.dumps(result, indent=2))


def cmd_coverage(args):
    """Show matching statistics."""
    params = {}
    if args.framework:
        params["framework"] = args.framework

    result = memory_request("/match/coverage", method="GET", payload=params)

    print("Relationship Coverage:")
    print("-" * 40)
    for row in result.get("by_relationship", []):
        print(f"  {row['relationship_type']}: {row['count']}")

    if result.get("by_framework"):
        print(f"\n{args.framework} Framework:")
        print("-" * 40)
        for row in result["by_framework"]:
            print(f"  {row['relationship_type']}: {row['count']}")

    print(f"\nTotals:")
    print(f"  Edges: {result.get('total_edges', 0)}")
    print(f"  Pending review: {result.get('total_pending', 0)}")
    print(f"  Conflicts: {result.get('total_conflicts', 0)}")


def cmd_review_queue(args):
    """List pending reviews and conflicts."""
    result = memory_request(
        "/match/review-queue",
        method="GET",
        payload={"limit": args.limit},
    )

    conflicts = result.get("conflicts", [])
    pending = result.get("pending", [])

    if args.export:
        with open(args.export, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "type", "chunk_key", "control_id", "relationship_type",
                "confidence", "extraction_method", "technique_match_type",
                "review_reason", "matched_at"
            ])
            for item in conflicts:
                writer.writerow([
                    "CONFLICT",
                    item.get("chunk_key", ""),
                    item.get("control_id", ""),
                    item.get("relationship_type", ""),
                    item.get("confidence", ""),
                    item.get("extraction_method", ""),
                    item.get("technique_match_type", ""),
                    "",
                    item.get("matched_at", ""),
                ])
            for item in pending:
                writer.writerow([
                    "PENDING",
                    item.get("chunk_key", ""),
                    item.get("control_id", ""),
                    item.get("relationship_type", ""),
                    item.get("confidence", ""),
                    item.get("extraction_method", ""),
                    item.get("technique_match_type", ""),
                    item.get("review_reason", ""),
                    item.get("matched_at", ""),
                ])
        print(f"Exported {len(conflicts)} conflicts + {len(pending)} pending to {args.export}")
    else:
        if conflicts:
            print(f"\n{'='*60}")
            print(f"CONFLICTS ({len(conflicts)}) - Require immediate attention")
            print(f"{'='*60}")
            for item in conflicts:
                print(f"  {item.get('chunk_key', '?')[:30]} <-> {item.get('control_id', '?')}")

        print(f"\n{'='*60}")
        print(f"PENDING REVIEW ({len(pending)})")
        print(f"{'='*60}")
        if not pending:
            print("  No items pending review.")
        else:
            for item in pending:
                reason = item.get("review_reason", "unknown")
                print(f"  {item.get('chunk_key', '?')[:30]} <-> {item.get('control_id', '?')} ({reason})")

        print(f"\nTotal: {len(conflicts)} conflicts, {len(pending)} pending")


def main():
    parser = argparse.ArgumentParser(description="/match-requirement — requirement-to-control matching")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # match command
    match_parser = subparsers.add_parser("match", help="Match a single requirement")
    match_parser.add_argument("--chunk-key", required=True, help="datalake_chunks key")
    match_parser.add_argument("--dry-run", action="store_true", help="Don't persist results")
    match_parser.add_argument("--confidence-threshold", type=float, default=0.7,
                              help="Confidence threshold for auto-accept (default: 0.7)")
    match_parser.set_defaults(func=cmd_match)

    # batch command
    batch_parser = subparsers.add_parser("batch", help="Process batch from queue")
    batch_parser.add_argument("--limit", type=int, default=10, help="Max jobs to process")
    batch_parser.add_argument("--dry-run", action="store_true", help="Don't persist results")
    batch_parser.add_argument("--confidence-threshold", type=float, default=0.7,
                              help="Confidence threshold for auto-accept (default: 0.7)")
    batch_parser.set_defaults(func=cmd_batch)

    # coverage command
    coverage_parser = subparsers.add_parser("coverage", help="Show matching statistics")
    coverage_parser.add_argument("--framework", help="Filter by framework (NIST, SPARTA, ISO)")
    coverage_parser.set_defaults(func=cmd_coverage)

    # review-queue command
    review_parser = subparsers.add_parser("review-queue", help="List pending reviews")
    review_parser.add_argument("--limit", type=int, default=50, help="Max items to show")
    review_parser.add_argument("--export", type=str, help="Export to CSV file")
    review_parser.set_defaults(func=cmd_review_queue)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
