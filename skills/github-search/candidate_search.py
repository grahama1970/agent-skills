"""Brave-backed GitHub repository discovery and deterministic ranking."""
from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from config import (
    BRAVE_SEARCH_SKILL,
    DEFAULT_BRAVE_CANDIDATES,
    DEFAULT_MAX_REPO_SIZE_MB,
    DEFAULT_MIN_STARS,
)
from utils import parse_json_output, run_command

_GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+.-]*", re.IGNORECASE)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "into", "is", "it", "of", "on", "or", "that", "the",
    "this", "to", "using", "with", "implementation", "repository", "repo",
}
_NON_REPO_ROOTS = {
    "about", "apps", "collections", "customer-stories", "enterprise", "events",
    "features", "gist", "issues", "login", "marketplace", "new", "orgs",
    "pricing", "pulls", "search", "security", "settings", "site", "sponsors",
    "topics", "trending", "users",
}


def _tokens(text: str) -> Set[str]:
    """Return meaningful lower-cased tokens for deterministic relevance scoring."""
    return {
        token.lower().strip(".-")
        for token in _TOKEN_RE.findall(text or "")
        if len(token.strip(".-")) > 1 and token.lower().strip(".-") not in _STOP_WORDS
    }


def extract_github_repository(url: str) -> Optional[str]:
    """Normalize a GitHub URL, including deep file URLs, to ``owner/repo``."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0].lower() in _NON_REPO_ROOTS:
        return None
    owner, name = parts[0], parts[1]
    if name.endswith(".git"):
        name = name[:-4]
    repo = f"{owner}/{name}"
    return repo if _GITHUB_REPO_RE.fullmatch(repo) else None


def _metadata_for_repo(repo: str) -> Dict[str, Any]:
    """Fetch ranking metadata through the authenticated GitHub CLI."""
    fields = (
        "nameWithOwner,description,url,stargazerCount,forkCount,primaryLanguage,"
        "updatedAt,isArchived,isFork,licenseInfo,defaultBranchRef,diskUsage"
    )
    output = run_command(["gh", "repo", "view", repo, "--json", fields], timeout=45)
    data = parse_json_output(output)
    if not isinstance(data, dict):
        return {"repo": repo, "metadata_error": output or "Invalid GitHub metadata"}
    language = data.get("primaryLanguage") or {}
    license_info = data.get("licenseInfo") or {}
    branch = data.get("defaultBranchRef") or {}
    return {
        "repo": data.get("nameWithOwner") or repo,
        "description": data.get("description") or "",
        "url": data.get("url") or f"https://github.com/{repo}",
        "stars": int(data.get("stargazerCount") or 0),
        "forks": int(data.get("forkCount") or 0),
        "language": language.get("name") if isinstance(language, dict) else language,
        "updated_at": data.get("updatedAt"),
        "archived": bool(data.get("isArchived")),
        "is_fork": bool(data.get("isFork")),
        "license": license_info.get("spdxId") if isinstance(license_info, dict) else None,
        "default_branch": branch.get("name") if isinstance(branch, dict) else None,
        "disk_usage_kb": int(data.get("diskUsage") or 0),
    }


def _relevance_score(candidate: Dict[str, Any], query: str, criteria: str) -> float:
    requested = _tokens(f"{query} {criteria}")
    if not requested:
        return 0.0
    searchable = " ".join(
        str(candidate.get(key) or "")
        for key in ("repo", "title", "brave_description", "description", "language", "license")
    ).lower()
    present = sum(1 for token in requested if token in searchable)
    overlap = present / len(requested)
    phrase_bonus = 0.0
    for phrase in (query.strip().lower(), criteria.strip().lower()):
        if len(phrase) >= 5 and phrase in searchable:
            phrase_bonus += 0.15
    return min(1.0, overlap + phrase_bonus)


def _rank_candidate(candidate: Dict[str, Any], query: str, criteria: str, total: int) -> None:
    relevance = _relevance_score(candidate, query, criteria)
    brave_rank = max(1, int(candidate.get("brave_rank") or total or 1))
    brave_position = 1.0 - ((brave_rank - 1) / max(total - 1, 1))
    stars = max(0, int(candidate.get("stars") or 0))
    star_score = min(1.0, math.log10(stars + 1) / 6.0)
    overall = (0.55 * relevance) + (0.25 * star_score) + (0.20 * brave_position)
    candidate["score"] = round(overall, 4)
    candidate["score_components"] = {
        "relevance": round(relevance, 4),
        "stars": round(star_score, 4),
        "brave_position": round(brave_position, 4),
        "weights": {"relevance": 0.55, "stars": 0.25, "brave_position": 0.20},
    }


def _date_is_before(value: Optional[str], threshold: Optional[str]) -> bool:
    if not threshold:
        return False
    try:
        cutoff = date.fromisoformat(threshold)
        observed = date.fromisoformat((value or "")[:10])
    except ValueError:
        return True
    return observed < cutoff


def _filter_reasons(
    candidate: Dict[str, Any],
    *,
    min_stars: int,
    language: Optional[str],
    updated_after: Optional[str],
    license_name: Optional[str],
    include_archived: bool,
    include_forks: bool,
    max_size_mb: int,
) -> List[str]:
    reasons: List[str] = []
    if candidate.get("metadata_error"):
        reasons.append("metadata unavailable")
    if int(candidate.get("stars") or 0) < min_stars:
        reasons.append(f"fewer than {min_stars} stars")
    if language and str(candidate.get("language") or "").lower() != language.lower():
        reasons.append(f"language is not {language}")
    if _date_is_before(candidate.get("updated_at"), updated_after):
        reasons.append(f"not updated on or after {updated_after}")
    if license_name and str(candidate.get("license") or "").lower() != license_name.lower():
        reasons.append(f"license is not {license_name}")
    if candidate.get("archived") and not include_archived:
        reasons.append("repository is archived")
    if candidate.get("is_fork") and not include_forks:
        reasons.append("repository is a fork")
    size_mb = int(candidate.get("disk_usage_kb") or 0) / 1024
    if max_size_mb > 0 and size_mb > max_size_mb:
        reasons.append(f"repository exceeds {max_size_mb} MB")
    return reasons


def brave_repository_candidates(
    query: str,
    criteria: str = "",
    count: int = DEFAULT_BRAVE_CANDIDATES,
) -> Dict[str, Any]:
    """Use the sibling brave-search skill and retain only GitHub repository URLs."""
    run_script = BRAVE_SEARCH_SKILL / "run.sh"
    if not run_script.exists():
        return {"error": f"brave-search skill not found at {run_script}", "candidates": []}
    count = max(1, min(int(count), 20))
    brave_query = " ".join(part for part in ("site:github.com", query, criteria) if part).strip()
    output = run_command(
        ["bash", str(run_script), "web", brave_query, "--count", str(count), "--json"],
        timeout=120,
    )
    payload = parse_json_output(output)
    if not isinstance(payload, dict):
        return {
            "error": output or "Invalid JSON from brave-search",
            "brave_query": brave_query,
            "candidates": [],
        }

    deduped: Dict[str, Dict[str, Any]] = {}
    for rank, item in enumerate(payload.get("results", []), start=1):
        repo = extract_github_repository(str(item.get("url") or ""))
        if not repo:
            continue
        key = repo.lower()
        if key not in deduped:
            deduped[key] = {
                "repo": repo,
                "brave_rank": rank,
                "title": item.get("title") or "",
                "brave_description": item.get("description") or "",
                "source_url": item.get("url") or "",
            }
    return {
        "brave_query": brave_query,
        "raw_result_count": len(payload.get("results", [])),
        "candidates": list(deduped.values()),
    }


def discover_and_rank_repositories(
    query: str,
    criteria: str = "",
    *,
    count: int = DEFAULT_BRAVE_CANDIDATES,
    min_stars: int = DEFAULT_MIN_STARS,
    language: Optional[str] = None,
    updated_after: Optional[str] = None,
    license_name: Optional[str] = None,
    include_archived: bool = False,
    include_forks: bool = False,
    max_size_mb: int = DEFAULT_MAX_REPO_SIZE_MB,
) -> Dict[str, Any]:
    """Discover with Brave, enrich with GitHub metadata, filter, and rank."""
    discovery = brave_repository_candidates(query, criteria, count)
    raw_candidates = discovery.get("candidates", [])
    if discovery.get("error") or not raw_candidates:
        if not discovery.get("error"):
            discovery["error"] = "Brave returned no GitHub repository URLs"
        discovery.update({"ranked": [], "rejected": []})
        return discovery

    metadata: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(raw_candidates))) as executor:
        futures = {
            executor.submit(_metadata_for_repo, item["repo"]): item["repo"].lower()
            for item in raw_candidates
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                metadata[key] = future.result()
            except Exception as exc:
                metadata[key] = {"repo": key, "metadata_error": str(exc)}

    ranked: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for item in raw_candidates:
        candidate = {**item, **metadata.get(item["repo"].lower(), {})}
        reasons = _filter_reasons(
            candidate,
            min_stars=max(0, min_stars),
            language=language,
            updated_after=updated_after,
            license_name=license_name,
            include_archived=include_archived,
            include_forks=include_forks,
            max_size_mb=max_size_mb,
        )
        if reasons:
            candidate["rejected_reasons"] = reasons
            rejected.append(candidate)
            continue
        _rank_candidate(candidate, query, criteria, len(raw_candidates))
        ranked.append(candidate)

    ranked.sort(key=lambda item: (item.get("score", 0), item.get("stars", 0)), reverse=True)
    discovery.update({
        "ranked": ranked,
        "rejected": rejected,
        "filters": {
            "criteria": criteria,
            "min_stars": max(0, min_stars),
            "language": language,
            "updated_after": updated_after,
            "license": license_name,
            "include_archived": include_archived,
            "include_forks": include_forks,
            "max_size_mb": max_size_mb,
        },
    })
    return discovery
