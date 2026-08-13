"""Phase 5: External research via /brave-search, /github-search, and /arxiv.

Builds targeted research queries from Phase 1-4 findings, then executes
them against recent retrieval skills. Dogpile remains a legacy deep aggregator
option, but current web and GitHub facts should prefer brave-search and
github-search.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from loguru import logger

from constants import (
    PROJECT_ROOT,
    ARXIV_SKILL,
    BRAVE_SEARCH_SKILL,
    DOGPILE_SKILL,
    GITHUB_SEARCH_SKILL,
    PROJECT_NAME,
    PROJECT_PROFILE,
)



def _target_topic_terms() -> str:
    """Topic words derived from the TARGET's own metadata.

    The generic branch used to hardcode "extraction pipeline" / "layout
    parsing" regardless of target (observed 2026-08-13: a slide-deck compiler
    was researched as a document-extraction project). Read the target's
    pyproject description or README heading instead; fall back to the project
    name alone rather than inventing a domain.
    """
    import re
    import tomllib

    pyproject = PROJECT_ROOT / "pyproject.toml"
    if pyproject.exists():
        try:
            description = tomllib.loads(pyproject.read_text()).get("project", {}).get("description", "")
            if description:
                return " ".join(re.findall(r"[A-Za-z][A-Za-z-]{3,}", description)[:6])
        except (OSError, tomllib.TOMLDecodeError):
            pass
    readme = PROJECT_ROOT / "README.md"
    if readme.exists():
        try:
            for line in readme.read_text(errors="replace").splitlines():
                text = line.strip().lstrip("#").strip()
                if len(text) > 20 and not text.startswith(("!", "[", "<")):
                    return " ".join(re.findall(r"[A-Za-z][A-Za-z-]{3,}", text)[:6])
        except OSError:
            pass
    return ""


def _build_research_queries(cascade: dict, daemons: dict,
                            doc_drift: dict | None, full: bool) -> list[dict[str, str]]:
    """Build targeted research queries from Phase 1-4 findings."""
    queries: list[dict[str, str]] = []

    if PROJECT_PROFILE == "embry":
        queries.append({
            "source": "brave-search",
            "query": "defense manufacturing compliance AI agentic 2026",
            "reason": "core competitive landscape",
        })
    else:
        queries.append({
            "source": "brave-search",
            "query": f"{PROJECT_NAME} {_target_topic_terms()} best practices".replace("  ", " "),
            "reason": "target-project technical landscape",
        })

    # Gap-driven queries
    if cascade.get("applicable", True) and cascade["tier_status"]["tier_1_5_gpt"] == "NOT_TRAINED":
        queries.append({
            "source": "arxiv",
            "query": "QLoRA knowledge distillation",
            "reason": "Tier 1.5 GPT training approach",
        })

    shadow = cascade.get("shadow", {})
    if cascade.get("applicable", True) and shadow.get("usable", 0) < shadow.get("total", 1) * 0.5:
        queries.append({
            "source": "arxiv",
            "query": "knowledge distillation teacher student",
            "reason": "shadow data quality improvement",
        })

    # Classifier quality -- look for better approaches if classifiers exist
    classifiers = cascade.get("classifiers_on_disk", [])
    if cascade.get("applicable", True) and len(classifiers) >= 5:
        queries.append({
            "source": "arxiv",
            "query": "text classification small data",
            "reason": "classifier improvement with limited labels",
        })

    if full and PROJECT_PROFILE == "embry":
        queries.append({
            "source": "brave-search",
            "query": "MES digital twin manufacturing compliance drift detection",
            "reason": "adjacent technology landscape",
        })
        queries.append({
            "source": "brave-search",
            "query": "OSCAL NIST compliance automation air-gapped deployment",
            "reason": "compliance tooling landscape",
        })
        queries.append({
            "source": "github-search",
            "query": "OSCAL compliance automation open issues",
            "reason": "current GitHub implementation and issue landscape",
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
    elif full:
        queries.append({
            "source": "brave-search",
            "query": f"{PROJECT_NAME} GitHub issues {_target_topic_terms()}".replace("  ", " "),
            "reason": "current implementation and issue landscape",
        })
        queries.append({
            "source": "arxiv",
            "query": f"{_target_topic_terms()}".strip() or f"{PROJECT_NAME} software engineering",
            "reason": "target-project technical approach validation",
            "categories": "cs.AI,cs.SE",
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
    """Run a legacy /dogpile search."""
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


def _run_brave(query: str, max_results: int = 5) -> dict[str, Any]:
    """Run a /brave-search web query."""
    if not BRAVE_SEARCH_SKILL.exists():
        return {"error": "brave-search skill not found"}
    try:
        out = subprocess.run(
            ["bash", str(BRAVE_SEARCH_SKILL), "web", query, "--count", str(max_results), "--json"],
            capture_output=True, text=True, timeout=45,
        )
        if out.returncode == 0:
            parsed = _parse_json_stdout(out.stdout)
            if parsed:
                results = parsed.get("results", [])
                summaries = [
                    f"{item.get('title', 'Untitled')} - {item.get('url', '')}"
                    for item in results[:max_results]
                ]
                return {"output": "\n".join(summaries), "count": len(results)}
            clean = "\n".join(ln for ln in out.stdout.splitlines() if ln.strip())[:800]
            return {"output": clean} if clean else {"error": "no results"}
        return {"error": (out.stderr or out.stdout)[:200]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout (45s)"}
    except Exception as e:
        return {"error": str(e)[:100]}


def _run_github_issues(query: str, max_results: int = 5) -> dict[str, Any]:
    """Run a /github-search issues query."""
    if not GITHUB_SEARCH_SKILL.exists():
        return {"error": "github-search skill not found"}
    try:
        out = subprocess.run(
            ["bash", str(GITHUB_SEARCH_SKILL), "issues", query, "--limit", str(max_results), "--json"],
            capture_output=True, text=True, timeout=45,
        )
        if out.returncode == 0:
            parsed = _parse_json_stdout(out.stdout)
            if parsed:
                issues = parsed.get("issues", parsed if isinstance(parsed, list) else [])
                if isinstance(issues, list):
                    summaries = [
                        f"{item.get('title', 'Untitled')} - {item.get('url', item.get('html_url', ''))}"
                        for item in issues[:max_results]
                    ]
                    return {"output": "\n".join(summaries), "count": len(issues)}
            clean = "\n".join(ln for ln in out.stdout.splitlines() if ln.strip())[:800]
            return {"output": clean} if clean else {"error": "no results"}
        return {"error": (out.stderr or out.stdout)[:200]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout (45s)"}
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
    """Query current external research skills based on detected gaps."""
    if skip:
        return {"skipped": True, "reason": "Use standard or --full mode"}

    cascade = cascade or {"tier_status": {}, "shadow": {}, "classifiers_on_disk": []}
    daemons = daemons or {"up": 0, "total": 0}

    queries = _build_research_queries(cascade, daemons, doc_drift, full=full)
    results = []

    for q in queries:
        entry = {"query": q["query"], "source": q["source"], "reason": q["reason"]}
        if q["source"] == "brave-search":
            entry.update(_run_brave(q["query"]))
        elif q["source"] == "github-search":
            entry.update(_run_github_issues(q["query"]))
        elif q["source"] == "dogpile":
            entry.update(_run_dogpile(q["query"]))
        elif q["source"] == "arxiv":
            entry.update(_run_arxiv(q["query"], q.get("categories", "")))
        results.append(entry)

    # `available` must describe whether any search lane ANSWERED, not that we
    # attempted queries (same silent-success class fixed in memory_recall on
    # 2026-08-13: 3 queries, 0 results, "available": true).
    answered = [r for r in results if (r.get("results") or r.get("items") or r.get("count"))
                and not r.get("error")]
    return {
        "available": bool(answered),
        "queries_run": len(results),
        "queries_answered": len(answered),
        "mode": "full" if full else "standard",
        "results": results,
        **({} if answered else {"error": "no search lane returned results"}),
    }
