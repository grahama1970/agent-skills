"""Local code evidence search and evaluation orchestration for ranked repositories."""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from config import (
    DEFAULT_CLONE_TIMEOUT,
    DEFAULT_EVALUATION_TOP,
    DEFAULT_RUN_MEMORY_MB,
    DEFAULT_RUN_TIMEOUT,
)
from repo_runtime import clone_repository, detect_entrypoint, run_entrypoint

_WORD_RE = re.compile(r"[a-z][a-z0-9_+.-]{1,}", re.IGNORECASE)
_STOP_WORDS = {
    "about", "after", "also", "and", "are", "code", "find", "for", "from",
    "how", "implementation", "into", "repository", "that", "the", "this", "to",
    "using", "was", "what", "when", "where", "which", "with",
}
_EXCLUDED_DIRS = {
    ".git", ".hg", ".mypy_cache", ".next", ".pytest_cache", ".tox", ".venv",
    "build", "coverage", "dist", "node_modules", "target", "vendor", "venv",
}
_TEXT_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".go", ".h", ".hpp", ".html", ".java",
    ".js", ".jsx", ".json", ".kt", ".md", ".php", ".py", ".rb", ".rs",
    ".sh", ".sql", ".swift", ".toml", ".ts", ".tsx", ".vue", ".yaml", ".yml",
}


def _clip(text: str, limit: int = 3000) -> str:
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def _query_terms(query: str) -> List[str]:
    terms = {
        token.lower().strip(".-")
        for token in _WORD_RE.findall(query or "")
        if token.lower().strip(".-") not in _STOP_WORDS and len(token.strip(".-")) > 2
    }
    return sorted(terms, key=lambda item: (-len(item), item))[:12]


def find_relevant_code(repo_path: Path, query: str, max_matches: int = 24) -> Dict[str, Any]:
    """Search the clean clone locally and return scored line-level evidence."""
    terms = _query_terms(query)
    phrase = query.strip().lower()
    matches: List[Dict[str, Any]] = []
    for path in repo_path.rglob("*"):
        if not path.is_file() or path.is_symlink() or any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES and path.name not in {"Dockerfile", "Makefile"}:
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        relative = str(path.relative_to(repo_path))
        is_code = path.suffix.lower() not in {".md", ".json", ".yaml", ".yml"}
        for number, line in enumerate(lines, start=1):
            lowered = line.lower()
            hit_terms = [term for term in terms if term in lowered]
            exact = bool(phrase and len(phrase) >= 5 and phrase in lowered)
            if not hit_terms and not exact:
                continue
            boundary_hits = sum(bool(re.search(rf"\b{re.escape(term)}\b", lowered)) for term in hit_terms)
            score = (5.0 if exact else 0.0) + (1.25 * len(hit_terms)) + (0.75 * boundary_hits) + (1.0 if is_code else 0.0)
            start, end = max(0, number - 4), min(len(lines), number + 3)
            snippet = "\n".join(f"{idx + 1}: {lines[idx]}" for idx in range(start, end))
            matches.append({
                "path": relative,
                "line": number,
                "score": round(score, 3),
                "matched_terms": hit_terms,
                "kind": "code" if is_code else "documentation_or_config",
                "snippet": _clip(snippet),
            })
    matches.sort(key=lambda item: (item["score"], item["kind"] == "code", -item["line"]), reverse=True)
    code_matches = [item for item in matches if item["kind"] == "code"]
    other_matches = [item for item in matches if item["kind"] != "code"]
    selected = (code_matches + other_matches)[:max(1, max_matches)]
    return {
        "terms": terms,
        "matches": selected,
        "matched_files": sorted({item["path"] for item in selected}),
        "total_matches": len(matches),
    }


def _quality_signals(repo_path: Path) -> Dict[str, bool]:
    tests = (repo_path / "tests").is_dir() or any(repo_path.glob("test_*.py")) or any(repo_path.glob("*_test.go"))
    manifests = any((repo_path / name).exists() for name in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod"))
    return {
        "tests": tests,
        "ci": (repo_path / ".github" / "workflows").is_dir(),
        "license": any(repo_path.glob("LICENSE*")),
        "readme": any(repo_path.glob("README*")),
        "manifest": manifests,
    }


def assess_repository(candidate: Dict[str, Any], code_search: Dict[str, Any], repo_path: Path) -> Dict[str, Any]:
    signals = _quality_signals(repo_path)
    matches = code_search.get("matches", [])
    top_score = float(matches[0].get("score", 0)) if matches else 0.0
    code_score = min(1.0, (top_score / 10.0) * 0.7 + min(len(code_search.get("matched_files", [])), 5) / 5 * 0.3)
    quality_score = sum(1 for value in signals.values() if value) / len(signals)
    discovery_score = float(candidate.get("score") or 0.0)
    overall = (0.45 * discovery_score) + (0.35 * code_score) + (0.20 * quality_score)
    recommendation = (
        "strong candidate" if overall >= 0.75
        else "promising; inspect the cited code" if overall >= 0.55
        else "weak or incomplete evidence"
    )
    return {
        "score": round(overall, 4),
        "recommendation": recommendation,
        "components": {
            "discovery": round(discovery_score, 4),
            "code_evidence": round(code_score, 4),
            "repository_signals": round(quality_score, 4),
        },
        "quality_signals": signals,
        "rationale": [
            "The detected entry point exited successfully.",
            f"Relevant code evidence spans {len(code_search.get('matched_files', []))} file(s).",
            f"Repository has {int(candidate.get('stars') or 0)} GitHub stars.",
        ],
        "limitations": [
            "Relevance and quality scores are deterministic heuristics, not proof of correctness.",
            "A successful --help-style entry point check does not exercise every feature.",
            "Review the cited snippets and repository license before reuse.",
        ],
    }


def evaluate_ranked_repositories(
    ranked: Sequence[Dict[str, Any]],
    query: str,
    *,
    top: int = DEFAULT_EVALUATION_TOP,
    entrypoint_override: Optional[str] = None,
    run_timeout: int = DEFAULT_RUN_TIMEOUT,
    memory_mb: int = DEFAULT_RUN_MEMORY_MB,
    clone_timeout: int = DEFAULT_CLONE_TIMEOUT,
    sandbox: str = "auto",
    allow_network: bool = False,
    keep_workspace: bool = True,
) -> Dict[str, Any]:
    """Execute the requested pipeline in order for the highest-ranked repositories."""
    workspace = Path(tempfile.mkdtemp(prefix="github-search-eval-", dir="/tmp"))
    results: List[Dict[str, Any]] = []
    for candidate in list(ranked)[:max(1, min(int(top), 5))]:
        item: Dict[str, Any] = {"repo": candidate.get("repo"), "candidate": candidate}
        clone = clone_repository(candidate, workspace, timeout=clone_timeout)
        item["clone"] = clone
        if clone.get("status") != "passed":
            item["status"] = "clone_failed"
            results.append(item)
            continue
        repo_path = Path(str(clone["path"]))
        entrypoint = detect_entrypoint(repo_path, entrypoint_override)
        item["entrypoint"] = entrypoint
        if not entrypoint:
            item["status"] = "entrypoint_not_found"
            results.append(item)
            continue
        run = run_entrypoint(
            repo_path, entrypoint, workspace,
            timeout=run_timeout, memory_mb=memory_mb,
            sandbox=sandbox, allow_network=allow_network,
        )
        item["run"] = run
        if run.get("status") != "passed":
            item["status"] = "entrypoint_failed"
            results.append(item)
            continue
        code_search = find_relevant_code(repo_path, query)
        item["code_search"] = code_search
        item["assessment"] = assess_repository(candidate, code_search, repo_path)
        item["status"] = "evaluated"
        results.append(item)

    evaluated = [item for item in results if item.get("status") == "evaluated"]
    best = max(evaluated, key=lambda item: item["assessment"]["score"], default=None)
    response: Dict[str, Any] = {
        "workspace": str(workspace),
        "workspace_kept": keep_workspace,
        "results": results,
        "evaluated_count": len(evaluated),
        "best_repository": best.get("repo") if best else None,
    }
    if not keep_workspace:
        shutil.rmtree(workspace, ignore_errors=True)
        response["workspace_removed"] = True
    return response
