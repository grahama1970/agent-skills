"""Phase 5: External research via /dogpile and /arxiv.

Builds targeted research queries from Phase 1-4 findings, then executes
them against dogpile (web search) and arxiv (academic papers) to inform
gap analysis with competitive intelligence and state-of-the-art techniques.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from loguru import logger

from constants import ARXIV_SKILL, DOGPILE_SKILL


def _build_research_queries(cascade: dict, daemons: dict,
                            doc_drift: dict | None, full: bool) -> list[dict[str, str]]:
    """Build targeted research queries from Phase 1-4 findings."""
    queries: list[dict[str, str]] = []

    # Always: competitive landscape (core domain)
    queries.append({
        "source": "dogpile",
        "query": "defense manufacturing compliance AI agentic 2026",
        "reason": "core competitive landscape",
    })

    # Gap-driven queries
    if cascade["tier_status"]["tier_1_5_gpt"] == "NOT_TRAINED":
        queries.append({
            "source": "arxiv",
            "query": "QLoRA knowledge distillation",
            "reason": "Tier 1.5 GPT training approach",
        })

    shadow = cascade.get("shadow", {})
    if shadow.get("usable", 0) < shadow.get("total", 1) * 0.5:
        queries.append({
            "source": "arxiv",
            "query": "knowledge distillation teacher student",
            "reason": "shadow data quality improvement",
        })

    # Classifier quality -- look for better approaches if classifiers exist
    classifiers = cascade.get("classifiers_on_disk", [])
    if len(classifiers) >= 5:
        queries.append({
            "source": "arxiv",
            "query": "text classification small data",
            "reason": "classifier improvement with limited labels",
        })

    if full:
        queries.append({
            "source": "dogpile",
            "query": "MES digital twin manufacturing compliance drift detection",
            "reason": "adjacent technology landscape",
        })
        queries.append({
            "source": "dogpile",
            "query": "OSCAL NIST compliance automation air-gapped deployment",
            "reason": "compliance tooling landscape",
        })
        queries.append({
            "source": "arxiv",
            "query": "compliance drift detection document extraction knowledge graph",
            "reason": "core technical approach validation",
            "categories": "cs.AI,cs.SE",
        })
        queries.append({
            "source": "arxiv",
            "query": "voice assistant ambient display aging accessibility manufacturing",
            "reason": "UX research for factory floor",
            "categories": "cs.HC",
        })

    return queries


def _parse_json_stdout(raw: str) -> dict | None:
    """Extract JSON from stdout, skipping uv/pip warnings."""
    for i, ch in enumerate(raw):
        if ch in ('{', '['):
            try:
                return json.loads(raw[i:])
            except json.JSONDecodeError:
                continue
    return None


def _run_dogpile(query: str, timeout: int = 180) -> dict[str, Any]:
    """Run a /dogpile search."""
    if not DOGPILE_SKILL.exists():
        return {"error": "dogpile skill not found"}
    try:
        out = subprocess.run(
            ["bash", str(DOGPILE_SKILL), "search", query,
             "--no-interactive", "--no-tailor", "--no-github-skill"],
            capture_output=True, text=True, timeout=timeout,
        )
        # Check both stdout and stderr for errors
        combined = out.stdout + out.stderr
        if "Traceback" in combined or "ModuleNotFoundError" in combined:
            return {"error": "dogpile skill broken (missing dependency)"}
        if out.returncode == 0:
            # Dogpile outputs markdown report -- extract key sections
            clean = "\n".join(
                ln for ln in out.stdout.splitlines()
                if not ln.startswith("warning:") and not ln.startswith("[DOGPILE-") and ln.strip()
            )[:1200]
            return {"output": clean} if clean else {"error": "no results"}
        return {"error": out.stderr[:200]}
    except subprocess.TimeoutExpired:
        return {"error": f"timeout ({timeout}s)"}
    except Exception as e:
        return {"error": str(e)[:100]}


def _run_arxiv(query: str, categories: str = "", max_results: int = 5) -> dict[str, Any]:
    """Run an /arxiv search."""
    if not ARXIV_SKILL.exists():
        return {"error": "arxiv skill not found"}
    cmd = ["bash", str(ARXIV_SKILL), "search", "-q", query, "-n", str(max_results),
           "-s", "relevance"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            parsed = _parse_json_stdout(out.stdout)
            if parsed:
                papers = parsed.get("items", parsed.get("papers", parsed.get("results", [])))
                count = parsed.get("meta", {}).get("count", len(papers) if isinstance(papers, list) else 0)
                if isinstance(papers, list) and papers:
                    summaries = []
                    for p in papers[:5]:
                        title = p.get("title", "Untitled")
                        authors = p.get("authors", ["?"])[0] if p.get("authors") else "?"
                        arxiv_id = p.get("arxiv_id", p.get("id", ""))
                        summaries.append(f"[{arxiv_id}] {title} ({authors} et al.)")
                    return {"output": "\n".join(summaries), "count": count}
                return {"output": f"Query returned {count} papers (no details)", "count": count}
            # Fallback
            clean = "\n".join(
                ln for ln in out.stdout.splitlines()
                if not ln.startswith("warning:") and ln.strip()
            )[:600]
            return {"output": clean} if clean else {"error": "no results"}
        return {"error": out.stderr[:200]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout (30s)"}
    except Exception as e:
        return {"error": str(e)[:100]}


def collect_competitive(skip: bool = False, full: bool = False,
                        cascade: dict | None = None, daemons: dict | None = None,
                        doc_drift: dict | None = None) -> dict[str, Any]:
    """Query /dogpile + /arxiv based on detected gaps."""
    if skip:
        return {"skipped": True, "reason": "Use standard or --full mode"}

    cascade = cascade or {"tier_status": {}, "shadow": {}, "classifiers_on_disk": []}
    daemons = daemons or {"up": 0, "total": 0}

    queries = _build_research_queries(cascade, daemons, doc_drift, full=full)
    results = []

    for q in queries:
        entry = {"query": q["query"], "source": q["source"], "reason": q["reason"]}
        if q["source"] == "dogpile":
            entry.update(_run_dogpile(q["query"]))
        elif q["source"] == "arxiv":
            entry.update(_run_arxiv(q["query"], q.get("categories", "")))
        results.append(entry)

    return {
        "available": True,
        "queries_run": len(results),
        "mode": "full" if full else "standard",
        "results": results,
    }
