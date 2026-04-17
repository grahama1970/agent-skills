#!/usr/bin/env python3
"""Code explanation stage for Dogpile (Stage 2.5).

After GitHub deep search finds relevant code, this module uses a fast LLM
to explain how the code works and why it's relevant to the query.

Graceful degradation: returns None on any failure — the report renders
without an explanation section and there is zero regression.
"""
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory to path for package imports when running as script
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

from dogpile.llm_fallback import call_fast
from dogpile.utils import log_status


def _collect_snippets(github_deep: Dict[str, Any], max_chars: int = 3000) -> str:
    """Pick the best code snippets from deep search results.

    Priority order: file_contents > symbol_matches > code_matches.
    Budget-capped to max_chars to keep the LLM prompt compact.

    Args:
        github_deep: Deep search result dict from github_deep.py
        max_chars: Maximum total characters of collected snippets

    Returns:
        Concatenated snippet text, or empty string if nothing found.
    """
    parts: List[str] = []
    budget = max_chars

    # 1. Full file contents (highest signal)
    for fc in github_deep.get("file_contents", []):
        if budget <= 0:
            break
        path = fc.get("path", "unknown")
        content = fc.get("content", "")
        if not content:
            continue
        chunk = content[:budget]
        parts.append(f"### {path}\n```\n{chunk}\n```")
        budget -= len(chunk)

    # 2. Symbol matches (function/class definitions)
    for item in github_deep.get("symbol_matches", []):
        if budget <= 0:
            break
        path = item.get("path", "unknown")
        symbol = item.get("symbol", "")
        for tm in item.get("textMatches", [])[:1]:
            fragment = tm.get("fragment", "")
            if not fragment:
                continue
            chunk = fragment[:budget]
            parts.append(f"### {path} — `{symbol}`\n```\n{chunk}\n```")
            budget -= len(chunk)

    # 3. Code text matches (keyword hits)
    for item in github_deep.get("code_matches", []):
        if budget <= 0:
            break
        path = item.get("path", "unknown")
        for tm in item.get("textMatches", [])[:1]:
            fragment = tm.get("fragment", "")
            if not fragment:
                continue
            chunk = fragment[:budget]
            parts.append(f"### {path}\n```\n{chunk}\n```")
            budget -= len(chunk)

    return "\n\n".join(parts)


def _build_prompt(query: str, repo: str, snippets: str) -> str:
    """Build the explanation prompt for the fast LLM.

    Args:
        query: Original search query
        repo: Target repository name (owner/repo)
        snippets: Collected code snippets text

    Returns:
        Prompt string.
    """
    return f"""You are a senior software engineer explaining code to a researcher.

**Query:** {query}
**Repository:** {repo}

**Code snippets found:**
{snippets}

Provide a concise explanation (3-6 paragraphs) covering:
1. **How it works:** What does this code do? Describe the key data structures, algorithms, or patterns.
2. **Why it's relevant:** How does this code relate to the query?
3. **Key patterns:** Notable design patterns, idioms, or architectural choices.

Be specific — reference function names, classes, and file paths from the snippets.
Do NOT repeat the raw code; explain it in plain language."""


def explain_code_results(
    query: str,
    repo: str,
    github_deep: Dict[str, Any],
) -> Optional[str]:
    """Generate an LLM explanation of code found during GitHub deep search.

    Uses call_fast() (Gemini Flash -> GPT-4o-mini -> Haiku) for speed and cost.
    Returns None on any failure so the report can render without this section.

    Args:
        query: Original search query
        repo: Target repository (owner/repo format)
        github_deep: Deep search result dict

    Returns:
        Explanation text, or None if generation fails or no snippets found.
    """
    try:
        snippets = _collect_snippets(github_deep)
        if not snippets:
            log_status("No code snippets to explain", provider="code_explanation", status="SKIP")
            return None

        prompt = _build_prompt(query, repo, snippets)
        log_status("Generating code explanation...", provider="code_explanation", status="RUNNING")

        provider_name, result = call_fast(prompt)

        if provider_name == "none" or result.startswith("Error:"):
            log_status(f"Code explanation failed: {result[:100]}", provider="code_explanation", status="FAILED")
            return None

        log_status(f"Code explanation done (via {provider_name})", provider="code_explanation", status="DONE")
        return result

    except Exception as e:
        log_status(f"Code explanation error: {e}", provider="code_explanation", status="ERROR")
        return None
