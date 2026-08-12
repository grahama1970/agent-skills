"""Research pass for Premium-derived prospects (viewers, hiring contacts, warm orgs).

A scraped name is not a lead. Before any person or org from LinkedIn Premium
reaches the morning digest, it gets a bounded research pass — /dogpile when
available (brave web + arxiv + github fan-out), else /brave-search — so the
digest presents who they are, what the company does, and any recent
budget/urgency news alongside the raw signal.

Inputs: prospect dicts {name, org, headline}. Output: the same dicts with a
`research` field {summary_snippets, sources, researched_via}. Fail-soft: no
search tool or no results -> research is None, never fabricated.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

DOGPILE_RUN = Path.home() / ".claude" / "skills" / "dogpile" / "run.sh"
BRAVE_SEARCH = Path.home() / ".claude" / "skills" / "brave-search" / "brave_search.py"


def _dogpile(query: str, timeout: int = 90) -> list[dict[str, Any]]:
    if not DOGPILE_RUN.exists():
        return []
    try:
        proc = subprocess.run(
            [str(DOGPILE_RUN), "search", query, "--json"],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        start = proc.stdout.find("{")
        data = json.loads(proc.stdout[start:]) if start >= 0 else {}
    except ValueError:
        return []
    results = data.get("results") or data.get("items") or []
    return [r for r in results if isinstance(r, dict)][:5]


def _brave(query: str, timeout: int = 45) -> list[dict[str, Any]]:
    if not BRAVE_SEARCH.exists():
        return []
    import os

    def run(env: dict[str, str] | None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(BRAVE_SEARCH), "web", query, "--count", "4"],
            capture_output=True, text=True, timeout=timeout, env=env,
        )

    try:
        proc = run(None)
        paid = os.environ.get("BRAVE_API_KEY_PAID")
        failed = proc.returncode != 0 or not proc.stdout.strip()
        quota = (
            "429" in proc.stderr or "QUOTA" in proc.stderr.upper()
            or "not found in env" in proc.stderr
        )
        if failed and paid and quota:
            proc = run(dict(os.environ, BRAVE_API_KEY=paid))
        if proc.returncode != 0 or not proc.stdout.strip():
            return []
        data = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return []
    return [r for r in data.get("results", []) if isinstance(r, dict)][:4]


def _snippets(results: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    snippets: list[str] = []
    sources: list[str] = []
    for r in results:
        desc = str(r.get("description") or r.get("snippet") or r.get("summary") or "").strip()
        url = str(r.get("url") or r.get("link") or "").strip()
        if desc:
            snippets.append(desc[:280])
        if url:
            sources.append(url)
    return snippets[:4], sources[:4]


def research_prospect(prospect: dict[str, Any]) -> dict[str, Any] | None:
    """Bounded research brief for one prospect. None when nothing credible found."""
    name = str(prospect.get("name") or "").strip()
    org = str(prospect.get("org") or prospect.get("organization") or "").strip()
    headline = str(prospect.get("headline") or "").strip()
    if not (name or org):
        return None
    query = " ".join(p for p in (name, org or headline.split(" at ")[-1]) if p)
    results = _dogpile(query)
    via = "dogpile"
    if not results:
        results = _brave(query)
        via = "brave-search"
    if not results:
        return None
    snippets, sources = _snippets(results)
    if not snippets:
        return None
    return {"summary_snippets": snippets, "sources": sources, "researched_via": via}


def research_prospects(prospects: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Research the top-N prospects in place (bounded for nightly speed)."""
    enriched: list[dict[str, Any]] = []
    for p in prospects[:limit]:
        try:
            p = dict(p)
            p["research"] = research_prospect(p)
        except Exception as exc:  # noqa: BLE001 - research must never fail the run
            logger.warning("prospect research skipped for {}: {}", p.get("name"), exc)
            p["research"] = None
        enriched.append(p)
    return enriched + [dict(p) for p in prospects[limit:]]
