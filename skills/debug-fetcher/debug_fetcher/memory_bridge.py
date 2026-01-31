"""Memory bridge for storing and recalling fetch strategies.

Integrates with the /memory skill for persistent storage of
learned fetch strategies.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .memory_schema import FetchStrategy


# Path to memory skill
MEMORY_SKILL_PATH = Path(__file__).parent.parent.parent / "memory" / "run.sh"

# Default memory scope for fetch strategies
DEFAULT_SCOPE = os.getenv("LEARN_FETCHER_MEMORY_SCOPE", "fetcher_strategies")


def _run_memory_command(args: List[str], timeout: int = 30) -> Dict[str, Any]:
    """Run a memory skill command and return parsed JSON result.

    Args:
        args: Command arguments to pass to memory skill
        timeout: Command timeout in seconds

    Returns:
        Parsed JSON response from memory skill

    Raises:
        RuntimeError: If command fails or returns invalid JSON
    """
    if not MEMORY_SKILL_PATH.exists():
        raise RuntimeError(f"Memory skill not found at {MEMORY_SKILL_PATH}")

    try:
        result = subprocess.run(
            [str(MEMORY_SKILL_PATH)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=MEMORY_SKILL_PATH.parent,
        )

        # Try to parse JSON from stdout
        output = result.stdout.strip()
        if output:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                # If not JSON, return as raw output
                return {"raw": output, "ok": result.returncode == 0}

        return {"ok": result.returncode == 0, "stderr": result.stderr}

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Memory command timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def recall_strategy(domain: str, path: str = "/") -> Optional[FetchStrategy]:
    """Recall a learned strategy for a domain/path from /memory.

    Args:
        domain: Target domain (e.g., "attack.mitre.org")
        path: URL path (e.g., "/techniques/T1059")

    Returns:
        FetchStrategy if found, None otherwise
    """
    # Build query string
    query = f"fetch strategy {domain} {path}"

    # Call memory recall
    result = _run_memory_command(["recall", "--q", query])

    if not result.get("found", False):
        return None

    # Parse items and find best match
    items = result.get("items", [])
    if not items:
        return None

    # Try each item until we find a valid strategy that matches
    for item in items:
        strategy = FetchStrategy.from_memory_format(item)
        if strategy and strategy.domain in domain:
            return strategy

    return None


def recall_strategies_for_domain(domain: str) -> List[FetchStrategy]:
    """Recall all learned strategies for a domain.

    Args:
        domain: Target domain

    Returns:
        List of FetchStrategy objects for this domain
    """
    query = f"fetch strategy {domain}"
    result = _run_memory_command(["recall", "--q", query])

    if not result.get("found", False):
        return []

    strategies = []
    for item in result.get("items", []):
        strategy = FetchStrategy.from_memory_format(item)
        if strategy and strategy.domain in domain:
            strategies.append(strategy)

    return strategies


def learn_strategy(
    url: str,
    strategy_used: str,
    timing_ms: int = 0,
    headers: Optional[Dict[str, str]] = None,
    user_agent: Optional[str] = None,
    human_provided: bool = False,
    human_notes: str = "",
    tags: Optional[List[str]] = None,
) -> bool:
    """Store a successful fetch strategy in /memory.

    Args:
        url: The URL that was successfully fetched
        strategy_used: Name of strategy that worked (e.g., "playwright")
        timing_ms: Response time in milliseconds
        headers: Custom headers that helped
        user_agent: User agent that worked
        human_provided: Whether this came from human input
        human_notes: Notes from human
        tags: Additional tags for categorization

    Returns:
        True if stored successfully, False otherwise
    """
    # Parse URL to extract domain and path
    try:
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        path = parsed.path or "/"
    except Exception:
        return False

    if not domain:
        return False

    # Determine path pattern
    # For specific paths, store exact; for generic, use pattern
    if len(path) > 50 or any(c.isdigit() for c in path.split("/")[-1]):
        # Likely contains IDs, generalize the pattern
        parts = path.split("/")
        pattern_parts = []
        for part in parts:
            if part and any(c.isdigit() for c in part):
                pattern_parts.append("*")
            else:
                pattern_parts.append(part)
        path_pattern = "/".join(pattern_parts) or "*"
    else:
        path_pattern = path if path != "/" else "*"

    # Create strategy
    strategy = FetchStrategy(
        domain=domain,
        path_pattern=path_pattern,
        successful_strategy=strategy_used,
        headers=headers or {},
        user_agent=user_agent,
        timing_ms=timing_ms,
        human_provided=human_provided,
        human_notes=human_notes,
        tags=tags or [],
    )

    # Convert to memory format
    memory_data = strategy.to_memory_format()

    # Call memory learn
    result = _run_memory_command([
        "learn",
        "--problem", memory_data["problem"],
        "--solution", memory_data["solution"],
    ])

    return result.get("ok", False) or "stored" in str(result).lower()


def update_strategy_stats(
    domain: str,
    path: str,
    success: bool,
    timing_ms: int = 0,
) -> bool:
    """Update statistics for an existing strategy.

    Args:
        domain: Target domain
        path: URL path
        success: Whether the fetch succeeded
        timing_ms: Response time

    Returns:
        True if updated, False if strategy not found
    """
    strategy = recall_strategy(domain, path)
    if not strategy:
        return False

    strategy.update_stats(success=success, timing_ms=timing_ms)

    # Re-store with updated stats
    memory_data = strategy.to_memory_format()
    result = _run_memory_command([
        "learn",
        "--problem", memory_data["problem"],
        "--solution", memory_data["solution"],
    ])

    return result.get("ok", False)


def get_best_strategy_for_url(url: str) -> Optional[FetchStrategy]:
    """Get the best known strategy for a URL.

    Checks /memory for learned strategies and returns the best match
    based on domain and path pattern.

    Args:
        url: Target URL

    Returns:
        FetchStrategy if found, None otherwise
    """
    try:
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        path = parsed.path or "/"
    except Exception:
        return None

    if not domain:
        return None

    # Get all strategies for this domain
    strategies = recall_strategies_for_domain(domain)
    if not strategies:
        return None

    # Find best match based on path pattern
    best_match = None
    best_score = -1

    for strategy in strategies:
        if strategy.matches_url(url):
            # Score based on specificity and success rate
            specificity = len(strategy.path_pattern.replace("*", ""))
            score = specificity * strategy.success_rate
            if score > best_score:
                best_score = score
                best_match = strategy

    return best_match
