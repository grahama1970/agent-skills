#!/usr/bin/env python3
"""Brave Search integration for Dogpile.

Provides web search via Brave Search API with rate limiting protection.
"""
import json
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any, List, Tuple
from loguru import logger

# Add parent directory to path for package imports when running as script
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

from dogpile.config import SKILLS_DIR
from dogpile.utils import log_status, with_semaphore, run_command, create_retry_decorator, capture_execution_metadata

BRAVE_MAX_CHARS = 400
BRAVE_MAX_WORDS = 50
_SITE_FILTER_RE = re.compile(r"site:[^\s)]+", flags=re.IGNORECASE)
_TRAILING_SITE_BLOCK_RE = re.compile(r"^(?P<base>.*?)(?:\s*\((?P<sites>site:[^)]+)\))?\s*$", flags=re.IGNORECASE)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from",
    "how", "i", "if", "in", "is", "it", "of", "on", "or", "that", "the", "their",
    "they", "this", "to", "use", "using", "what", "when", "which", "who", "why",
    "with", "actually", "need", "see",
}


def _split_query_and_sites(query: str) -> Tuple[str, List[str]]:
    """Split a Brave query into the base text and trailing site: filters."""
    normalized = " ".join(query.split())
    match = _TRAILING_SITE_BLOCK_RE.match(normalized)
    if not match:
        return normalized, []
    base = (match.group("base") or "").strip()
    sites_blob = match.group("sites") or ""
    sites = _SITE_FILTER_RE.findall(sites_blob)
    return base, sites


def _compress_base_query(base_query: str) -> str:
    """Rewrite a natural-language query into a search-engine friendly keyword query."""
    cleaned = re.sub(r"[^A-Za-z0-9_./:+-]+", " ", base_query)
    tokens = cleaned.split()
    compact_tokens: List[str] = []
    seen_lower = set()

    for token in tokens:
        lowered = token.lower()
        if lowered in _STOP_WORDS:
            continue
        if lowered in seen_lower:
            continue
        compact_tokens.append(token)
        seen_lower.add(lowered)

    if not compact_tokens:
        return base_query.strip()
    return " ".join(compact_tokens)


def normalize_brave_query(query: str) -> Tuple[str, Dict[str, Any]]:
    """Fit a Brave query into Brave's documented 400 char / 50 word limits."""
    original = " ".join(query.split())
    base_query, sites = _split_query_and_sites(original)
    compact_base = _compress_base_query(base_query)
    compact_base = compact_base.strip() or base_query.strip() or original

    def build(site_count: int) -> str:
        if site_count <= 0 or not sites:
            return compact_base
        site_clause = " OR ".join(sites[:site_count])
        return f"{compact_base} ({site_clause})".strip()

    selected_site_count = len(sites)
    candidate = build(selected_site_count)
    while selected_site_count > 0 and (
        len(candidate) > BRAVE_MAX_CHARS or len(candidate.split()) > BRAVE_MAX_WORDS
    ):
        selected_site_count -= 1
        candidate = build(selected_site_count)

    if len(candidate.split()) > BRAVE_MAX_WORDS:
        words = candidate.split()[:BRAVE_MAX_WORDS]
        candidate = " ".join(words)

    while len(candidate) > BRAVE_MAX_CHARS:
        words = candidate.split()
        if len(words) <= 1:
            candidate = candidate[:BRAVE_MAX_CHARS].rstrip()
            break
        candidate = " ".join(words[:-1]).rstrip()

    metadata = {
        "original_query": original,
        "normalized": candidate != original,
        "original_chars": len(original),
        "original_words": len(original.split()),
        "final_chars": len(candidate),
        "final_words": len(candidate.split()),
        "site_filters_requested": len(sites),
        "site_filters_used": selected_site_count,
    }
    return candidate, metadata


@capture_execution_metadata("brave", stage="stage1")
@create_retry_decorator("brave")
@with_semaphore("brave")
def search_brave(query: str) -> Dict[str, Any]:
    """Search Brave Web with rate limiting protection.

    Args:
        query: Search query

    Returns:
        Dict with search results or error
    """
    brave_query, query_meta = normalize_brave_query(query)
    if query_meta["normalized"]:
        dropped_sites = query_meta["site_filters_requested"] - query_meta["site_filters_used"]
        detail = (
            f"Brave query normalized {query_meta['original_chars']}c/{query_meta['original_words']}w"
            f" -> {query_meta['final_chars']}c/{query_meta['final_words']}w"
        )
        if dropped_sites > 0:
            detail += f" (dropped {dropped_sites} site filters)"
        log_status(detail, provider="brave", status="NORMALIZED")

    log_status(f"Starting Brave Search for '{brave_query}'...", provider="brave", status="RUNNING")
    script = SKILLS_DIR / "brave-search" / "brave_search.py"
    cmd = [sys.executable, str(script), "web", brave_query, "--count", "5", "--json"]

    try:
        output = run_command(cmd)
        if output.startswith("Error:"):
            # Check for rate limit errors
            if "429" in output or "rate limit" in output.lower():
                log_status("Brave rate limited, backing off...", provider="brave", status="RATE_LIMITED")
                time.sleep(5)  # Brief backoff for subprocess errors
            return {"error": output, "query": brave_query, "query_adjustment": query_meta}

        data = json.loads(output)
        log_status("Brave Search finished.", provider="brave", status="DONE")
        if isinstance(data, dict):
            data.setdefault("query", brave_query)
            data["query_adjustment"] = query_meta
        return data
    except json.JSONDecodeError:
        return {
            "error": "Invalid JSON output from Brave",
            "raw": output,
            "query": brave_query,
            "query_adjustment": query_meta,
        }


def build_brave_question_queries(query: str, tailored: Dict[str, str] | None = None) -> List[str]:
    """Build bounded Brave queries that replace the retired Perplexity lane.

    Dogpile used to ask Perplexity one natural-language research question. The
    free replacement is a small set of concurrent Brave searches: the original
    question, the tailored natural-language question when available, and a
    source/evidence-oriented variant.
    """
    tailored = tailored or {}
    candidates = [
        tailored.get("perplexity") or query,
        tailored.get("brave") or query,
        f"{query} sources evidence",
    ]

    queries: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = " ".join(str(candidate).split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(normalized)
    return queries[:3]


@capture_execution_metadata("brave_questions", stage="stage1")
def search_brave_questions(queries: List[str]) -> Dict[str, Any]:
    """Run multiple Brave web searches concurrently as Perplexity replacement."""
    if not queries:
        return {
            "replacement_for": "perplexity",
            "queries": [],
            "results": [],
            "error": "No Brave question queries were generated",
        }

    log_status(
        f"Starting {len(queries)} concurrent Brave question searches...",
        provider="brave_questions",
        status="RUNNING",
    )
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(3, len(queries))) as executor:
        future_to_query = {executor.submit(search_brave, q): q for q in queries}
        for future in as_completed(future_to_query):
            q = future_to_query[future]
            try:
                result = future.result()
            except Exception as exc:
                logger.error("Brave question search failed for {!r}: {}", q, exc)
                result = {"error": str(exc), "query": q}
            results.append({
                "query": q,
                "ok": not (isinstance(result, dict) and result.get("error")),
                "result": result,
            })

    ok_count = sum(1 for item in results if item["ok"])
    log_status(
        f"Brave question searches finished: {ok_count}/{len(results)} succeeded",
        provider="brave_questions",
        status="DONE" if ok_count else "ERROR",
    )
    return {
        "replacement_for": "perplexity",
        "queries": queries,
        "results": results,
        "succeeded": ok_count,
        "total": len(results),
    }


def deep_extract_url(url: str, title: str = "") -> Dict[str, Any]:
    """Deep extraction for web URLs via /fetcher + /extractor.

    Fetches full page content for relevant Brave search results.

    Args:
        url: URL to fetch and extract
        title: Optional title for the result

    Returns:
        Dict with extracted content or error
    """
    log_status(f"Deep extracting URL: {url[:50]}...", provider="brave", status="EXTRACTING")

    fetcher_dir = SKILLS_DIR / "fetcher"
    if not fetcher_dir.exists():
        return {"error": "fetcher skill not found", "url": url}

    out_dir = Path(tempfile.mkdtemp(prefix="dogpile_brave_"))
    try:
        # fetcher's CLI requires the `get` subcommand and writes content to an
        # --out directory (stdout is only a summary report). Calling
        # `run.sh <url>` errors with a usage message and extracts nothing.
        fetch_cmd = ["bash", "run.sh", "get", url, "--out", str(out_dir)]
        fetch_output = run_command(fetch_cmd, cwd=fetcher_dir)
        if isinstance(fetch_output, str) and fetch_output.startswith("Error:"):
            return {"url": url, "title": title, "extracted": False, "error": fetch_output[:300], "content_verdict": "error"}

        # Read the fetcher's content verdict from consumer_summary.json.
        verdict = None
        summary_path = out_dir / "consumer_summary.json"
        if summary_path.exists():
            try:
                items = (json.loads(summary_path.read_text()) or {}).get("items") or []
                if items:
                    verdict = items[0].get("verdict") or items[0].get("paywall_verdict")
            except Exception as e:
                logger.warning("could not parse fetcher summary for {}: {}", url, e)

        # Extracted content lands under markdown/ (preferred) or extracted_text/.
        content = ""
        for sub in ("markdown", "extracted_text"):
            sub_dir = out_dir / sub
            files = sorted(sub_dir.glob("*")) if sub_dir.exists() else []
            if files:
                content = files[0].read_text(errors="replace")
                break

        if not content.strip():
            return {"url": url, "title": title, "extracted": False, "content": "", "content_verdict": verdict or "empty"}

        log_status("URL extraction finished.", provider="brave", status="DONE")
        return {
            "url": url,
            "title": title,
            "content": content[:8000],  # Limit to 8k chars
            "content_verdict": verdict or "ok",
            "extracted": True,
        }

    except Exception as e:
        logger.error("deep extract failed for {}: {}", url, e)
        return {"url": url, "title": title, "extracted": False, "error": str(e)}
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _select_domain_diverse(web_results: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    """Pick up to n results preferring distinct domains, preserving Brave rank order."""
    selected: List[Dict[str, Any]] = []
    seen_domains: set = set()
    # First pass: one per domain, in rank order.
    for r in web_results:
        if len(selected) >= n:
            break
        domain = urlparse(r.get("url", "")).netloc
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            selected.append(r)
    # Second pass: backfill from remaining rank order if under n.
    if len(selected) < n:
        for r in web_results:
            if len(selected) >= n:
                break
            if r not in selected:
                selected.append(r)
    return selected


def _deep_read_urls(web_results: List[Dict[str, Any]], read_n: int) -> List[Dict[str, Any]]:
    """Deep-read up to read_n domain-diverse Brave URLs concurrently (Deep-Research style)."""
    selected = _select_domain_diverse(web_results, read_n)
    if not selected:
        return []
    log_status(
        f"Brave Stage 2: deep-reading {len(selected)} sources (read_n={read_n})...",
        provider="brave", status="EXTRACTING",
    )
    deep: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(len(selected), 5)) as ex:
        futures = {
            ex.submit(deep_extract_url, r.get("url", ""), r.get("title", "")): r
            for r in selected if r.get("url")
        }
        for fut in as_completed(futures):
            try:
                dr = fut.result()
                if dr.get("extracted"):
                    deep.append(dr)
            except Exception as e:
                logger.warning("brave deep-read failed for one source: {}", e)
    log_status(f"Brave Stage 2 deep-read finished ({len(deep)} extracted).", provider="brave", status="DONE")
    return deep


def run_stage2_brave(brave_res: Dict[str, Any], query: str, search_codex_fn, read_n: int = 1) -> List[Dict]:
    """Stage 2: Brave URL deep extraction.

    Args:
        brave_res: Stage 1 Brave search results
        query: Original search query
        search_codex_fn: Function to call Codex for evaluation
        read_n: When >1, deep-read the top-N domain-diverse URLs concurrently
            (Deep-Research style). When <=1, keep the single best-of-top-3 pick.

    Returns:
        List of deep extracted content
    """
    import re as regex

    brave_deep = []

    if brave_res and isinstance(brave_res, dict) and "web" in brave_res:
        if read_n and read_n > 1:
            all_web = brave_res.get("web", {}).get("results", []) or []
            return _deep_read_urls(all_web, read_n)

        web_results = brave_res.get("web", {}).get("results", [])[:3]

        if web_results:
            urls_summary = "\n".join([
                f"[{i+1}] {r.get('title', 'Unknown')}: {r.get('description', '')[:200]}"
                for i, r in enumerate(web_results)
            ])
            eval_prompt = f"""Given these web results for query "{query}", which ONE is MOST relevant for technical/documentation purposes?
{urls_summary}

Return just the number (1, 2, or 3) of the most relevant result, or 0 if none are worth deep extraction."""

            best_url_idx = -1
            eval_result = search_codex_fn(eval_prompt)

            try:
                match = regex.search(r'(\d)', eval_result)
                if match:
                    best_url_idx = int(match.group(1)) - 1
            except Exception as e:
                logger.error("matching failed: {}", e)

            if 0 <= best_url_idx < len(web_results):
                best_result = web_results[best_url_idx]
                log_status(
                    f"Brave Stage 2: Deep extracting '{best_result.get('title', 'Unknown')[:50]}'...",
                    provider="brave",
                    status="EXTRACTING"
                )
                deep_result = deep_extract_url(
                    best_result.get("url", ""),
                    best_result.get("title", "")
                )
                if deep_result.get("extracted"):
                    brave_deep.append(deep_result)
                    log_status("Brave Stage 2 deep extraction finished.", provider="brave", status="DONE")

    return brave_deep
