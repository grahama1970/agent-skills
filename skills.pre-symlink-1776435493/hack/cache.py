"""
Result caching for hack skill commands.

Provides TTL-based caching to avoid redundant scans of the same targets.
Falls back gracefully if cache is unavailable or corrupt.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from rich.console import Console
from loguru import logger

console = Console()

# Cache configuration
CACHE_DIR = Path.home() / ".cache" / "hack-skill"
DEFAULT_TTL = timedelta(hours=24)


def cache_key(command: str, target: str, **kwargs) -> str:
    """
    Generate cache key from command, target, and parameters.
    
    Args:
        command: Command name (e.g., "scan", "audit")
        target: Target identifier (IP, domain, file path)
        **kwargs: Additional parameters that affect the result
        
    Returns:
        16-character hex cache key
    """
    # Include command, target, and sorted kwargs in key
    key_parts = [command, target]
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={v}")
    
    key_string = ":".join(key_parts)
    return hashlib.sha256(key_string.encode()).hexdigest()[:16]


def get_cached_result(
    command: str,
    target: str,
    ttl: timedelta = DEFAULT_TTL,
    **kwargs
) -> dict[str, Any] | None:
    """
    Get cached result if fresh enough.
    
    Args:
        command: Command name
        target: Target identifier
        ttl: Time-to-live for cache freshness
        **kwargs: Additional parameters for cache key
        
    Returns:
        Cached result dict or None if not found/expired
    """
    try:
        key = cache_key(command, target, **kwargs)
        cache_file = CACHE_DIR / f"{key}.json"
        
        if not cache_file.exists():
            return None
        
        data = json.loads(cache_file.read_text())
        cached_at = datetime.fromisoformat(data["timestamp"])
        
        # Check if expired
        age = datetime.now() - cached_at
        if age > ttl:
            # Silently remove expired cache
            cache_file.unlink(missing_ok=True)
            return None
        
        # Return cached data with metadata
        return {
            "result": data["result"],
            "cached_at": cached_at,
            "age": age,
            "metadata": data.get("metadata", {})
        }
        
    except Exception as e:
        # Graceful degradation - log but don't fail
        console.print(f"[dim]Cache read failed: {e}[/dim]")
        return None


def cache_result(
    command: str,
    target: str,
    result: str | dict,
    metadata: dict[str, Any] | None = None,
    **kwargs
) -> bool:
    """
    Cache command result for future retrieval.
    
    Args:
        command: Command name
        target: Target identifier
        result: Result to cache (string or dict)
        metadata: Optional metadata about the result
        **kwargs: Additional parameters for cache key
        
    Returns:
        True if cached successfully, False otherwise
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        key = cache_key(command, target, **kwargs)
        cache_file = CACHE_DIR / f"{key}.json"
        
        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "target": target,
            "parameters": kwargs,
            "result": result,
            "metadata": metadata or {}
        }
        
        cache_file.write_text(json.dumps(cache_data, indent=2))
        return True
        
    except Exception as e:
        # Graceful degradation - log but don't fail
        console.print(f"[dim]Cache write failed: {e}[/dim]")
        return False


def clear_cache(
    command: str | None = None,
    target: str | None = None
) -> int:
    """
    Clear cached results.
    
    Args:
        command: Optional command filter (clear only this command's cache)
        target: Optional target filter (clear only this target's cache)
        
    Returns:
        Number of cache files removed
    """
    if not CACHE_DIR.exists():
        return 0
    
    removed = 0
    
    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            # Read cache metadata to check filters
            data = json.loads(cache_file.read_text())
            
            # Apply filters
            if command and data.get("command") != command:
                continue
            if target and data.get("target") != target:
                continue
            
            cache_file.unlink()
            removed += 1
            
        except Exception:
            # If corrupt, remove it
            cache_file.unlink(missing_ok=True)
            removed += 1
    
    return removed


def get_cache_stats() -> dict[str, Any]:
    """
    Get cache statistics.
    
    Returns:
        Dict with cache stats (total files, total size, oldest/newest entries)
    """
    if not CACHE_DIR.exists():
        return {
            "total_files": 0,
            "total_size_bytes": 0,
            "total_size_mb": 0.0,
            "oldest": None,
            "newest": None
        }
    
    cache_files = list(CACHE_DIR.glob("*.json"))
    total_size = sum(f.stat().st_size for f in cache_files)
    
    timestamps = []
    for cache_file in cache_files:
        try:
            data = json.loads(cache_file.read_text())
            timestamps.append(datetime.fromisoformat(data["timestamp"]))
        except Exception as e:
            logger.debug("value lookup failed: {}", e)
    
    return {
        "total_files": len(cache_files),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "oldest": min(timestamps) if timestamps else None,
        "newest": max(timestamps) if timestamps else None,
    }


# Explicit module exports
__all__ = [
    "cache_key",
    "get_cached_result",
    "cache_result",
    "clear_cache",
    "get_cache_stats",
    "CACHE_DIR",
    "DEFAULT_TTL",
]
