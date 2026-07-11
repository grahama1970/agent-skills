"""Brave Search integration — composes the existing brave-search skill.

Uses the canonical skill CLI: skills/brave-search/brave_search.py web "query" --json
rather than reimplementing API calls. Returns structured receipts.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _brave_search_script() -> Path | None:
    """Locate the brave-search skill entry point."""
    # Look relative to this module: skills/brave-search/brave_search.py
    candidates = [
        Path(__file__).resolve().parents[3] / "brave-search" / "brave_search.py",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def search(
    query: str,
    *,
    count: int = 5,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Run a Brave Web Search through the brave-search skill CLI.

    Returns a receipt: {status, query, results[], errors[], searched_at}.
    """
    receipt: dict[str, Any] = {
        "status": "not_run",
        "query": query,
        "results": [],
        "errors": [],
        "searched_at": now_iso(),
    }

    script = _brave_search_script()
    if not script:
        receipt["status"] = "skipped"
        receipt["errors"].append("brave-search skill not found")
        return receipt

    try:
        proc = subprocess.run(
            [sys.executable, str(script), "web", query, "--count", str(count), "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if proc.returncode != 0:
            receipt["status"] = "error"
            receipt["errors"].append(f"brave-search exited {proc.returncode}: {proc.stderr.strip()[:500]}")
            return receipt

        parsed = _parse_search_output(proc.stdout)
        receipt["results"] = parsed
        receipt["status"] = "ok" if parsed else "empty"
    except subprocess.TimeoutExpired:
        receipt["status"] = "error"
        receipt["errors"].append("brave-search timed out")
    except Exception as exc:
        receipt["status"] = "error"
        receipt["errors"].append(str(exc))

    return receipt


def _parse_search_output(stdout: str) -> list[dict[str, str]]:
    """Parse brave-search JSON/JSONL output into uniform results."""
    results: list[dict[str, str]] = []
    if not stdout.strip():
        return results

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        # Try JSONL: one JSON object per line
        for line in stdout.strip().split("\n"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue

    # Handle different output shapes
    items: list[dict] = []
    if isinstance(parsed, dict):
        items = parsed.get("results") or parsed.get("web", {}).get("results") or []
    elif isinstance(parsed, list):
        items = parsed

    for r in items:
        if not isinstance(r, dict):
            continue
        title = r.get("title", "")
        url = r.get("url", "")
        desc = r.get("description", "")
        if title or desc:
            results.append({
                "title": title,
                "url": url,
                "description": desc[:300],
            })

    return results


def build_context_queries(
    persona_ids: list[str],
    about: str | None,
) -> list[str]:
    """Build Brave Search queries relevant to the dream persona(s) and topic."""
    queries: list[str] = []

    persona_query = " ".join(persona_ids)
    queries.append(f"recent news events connected to {persona_query}")

    if about:
        queries.append(f"{about} recent developments 2026")

    if len(queries) < 3:
        queries.append("notable world events this month 2026")

    return queries[:3]
