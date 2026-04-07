"""Ingestion report command — extracted from ingest_website.py for file size."""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import typer
from loguru import logger

SKILL_DIR = Path(__file__).parent

_MEMORY_SOCKET = f"/run/user/{os.getuid()}/embry/memory.sock"
_MEMORY_HTTP = os.environ.get("MEMORY_SERVICE_URL", "http://127.0.0.1:8601")


def _memory_client() -> httpx.Client:
    """Get httpx client for memory daemon (Unix socket preferred, HTTP fallback)."""
    socket = Path(_MEMORY_SOCKET)
    if socket.exists():
        transport = httpx.HTTPTransport(uds=str(socket))
        return httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)
    return httpx.Client(base_url=_MEMORY_HTTP, timeout=30.0)


def _build_ingestion_report(scope: str) -> dict:
    """Query memory daemon for ingestion metrics via Unix socket."""
    data: dict = {"scope": scope, "stats": {}, "sources": {}}

    try:
        client = _memory_client()
    except Exception as e:
        logger.error("Cannot connect to memory daemon: {}", e)
        return {**data, "error": str(e)}

    try:
        # 1. Recall sample to get doc count and quality metrics
        recall_resp = client.post("/recall", json={
            "q": "website ingestion content",
            "scope": scope,
            "limit": 50,
        })
        if recall_resp.status_code == 200:
            recall_data = recall_resp.json()
            results = recall_data.get("items", recall_data.get("results", []))
            if isinstance(results, list):
                data["stats"]["sample_docs"] = len(results)

                # Analyze sample quality
                word_counts = []
                tagged_count = 0
                source_counter: dict[str, int] = {}
                web_count = 0

                for doc in results:
                    solution = doc.get("solution", doc.get("playbook", ""))
                    if solution:
                        word_counts.append(len(str(solution).split()))
                    tags = doc.get("tags", [])
                    taxonomy_tags = doc.get("taxonomy_tags", [])
                    if tags or taxonomy_tags:
                        tagged_count += 1
                    if "ingested_web" in tags:
                        web_count += 1
                    for tag in tags:
                        if isinstance(tag, str) and tag.startswith("source:"):
                            domain = tag.replace("source:", "")
                            source_counter[domain] = source_counter.get(domain, 0) + 1

                sample_size = len(results)
                data["stats"]["ingested_web_docs"] = web_count
                data["sources"] = source_counter
                data["sample_quality"] = {
                    "sample_size": sample_size,
                    "avg_chunk_words": sum(word_counts) / len(word_counts) if word_counts else 0,
                    "min_chunk_words": min(word_counts) if word_counts else 0,
                    "max_chunk_words": max(word_counts) if word_counts else 0,
                    "tagged_pct": (tagged_count / sample_size * 100) if sample_size else 0,
                }

        # 2. Taxonomy coverage (collection-level, not scope-filtered)
        tax_resp = client.get("/taxonomy/coverage", params={"collection": "lessons"})
        if tax_resp.status_code == 200:
            tax_data = tax_resp.json()
            data["taxonomy_coverage"] = tax_data.get("coverage_pct", {})

    except Exception as e:
        logger.error("Memory daemon query failed: {}", e)
        data["error"] = str(e)
    finally:
        client.close()

    return data


def report_command(
    scope: str = typer.Argument(..., help="Memory scope to report on"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show diagnostic metrics for ingested content in a scope.

    Queries memory daemon endpoints for content stats: recall sample,
    taxonomy coverage, source domains, and last run state.
    """
    report_data = _build_ingestion_report(scope)

    if json_output:
        print(json.dumps(report_data, indent=2, default=str))
        return

    # Human-readable output
    print(f"\n{'='*60}")
    print(f"  Ingestion Report: scope={scope}")
    print(f"{'='*60}")

    stats = report_data.get("stats", {})
    print(f"\n  Sample docs:    {stats.get('sample_docs', 'N/A')}")
    print(f"  Ingested-web:   {stats.get('ingested_web_docs', 'N/A')}")

    sample = report_data.get("sample_quality", {})
    if sample:
        print(f"  Sample size:    {sample.get('sample_size', 0)}")
        print(f"  Avg chunk size: {sample.get('avg_chunk_words', 0):.0f} words")
        print(f"  Has tags:       {sample.get('tagged_pct', 0):.0f}%")

    sources = report_data.get("sources", {})
    if sources:
        print(f"\n  Sources ({len(sources)}):")
        for domain, count in sorted(sources.items(), key=lambda x: -x[1]):
            print(f"    {domain}: {count} docs")

    tags = report_data.get("taxonomy_coverage", {})
    if tags:
        print(f"\n  Taxonomy coverage:")
        for field, pct in tags.items():
            print(f"    {field}: {pct}%")

    err = report_data.get("error")
    if err:
        print(f"\n  Error: {err}")

    # Task state if available
    state_file = SKILL_DIR / ".batch_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            print(f"\n  Last run: {state.get('description', 'N/A')}")
            print(f"  Status:   {state.get('status', 'N/A')}")
            print(f"  Success:  {state.get('stats', {}).get('success', 0)}/{state.get('total', 0)}")
            elapsed = state.get("elapsed_seconds", 0)
            print(f"  Duration: {elapsed/60:.1f} min")
        except (json.JSONDecodeError, KeyError):
            pass

    print()
