#!/usr/bin/env python3
"""SQLite-based result cache for Dogpile.

Caches search results per provider with configurable TTLs to avoid
redundant API calls. Single file, no external deps beyond stdlib.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


# Default TTLs per provider (hours)
DEFAULT_TTLS: Dict[str, int] = {
    "arxiv": 168,       # Papers change slowly (1 week)
    "github": 24,       # Repos update daily
    "brave": 12,        # Web results moderate freshness
    "perplexity": 12,
    "youtube": 48,      # Videos don't change often
    "readarr": 24,
    "wayback": 168,     # Archives are static
    "codex": 24,
    "discord": 6,       # Chat is time-sensitive
    "default": 24,
}


class ResultCache:
    """SQLite cache for search results with per-provider TTLs."""

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        ttl_hours: Optional[Dict[str, int]] = None,
    ):
        if cache_path is None:
            cache_path = Path(__file__).parent / "dogpile_cache.db"
        self.db = sqlite3.connect(str(cache_path), check_same_thread=False)
        self.ttl_hours = {**DEFAULT_TTLS, **(ttl_hours or {})}
        self._init_db()

    def _init_db(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                query TEXT NOT NULL,
                results TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_cache_provider ON cache(provider)")
        self.db.commit()

    @staticmethod
    def _cache_key(provider: str, query: str) -> str:
        raw = f"{provider}:{query.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, provider: str, query: str) -> Optional[Any]:
        """Get cached results if not expired. Returns None on miss."""
        key = self._cache_key(provider, query)
        ttl = self.ttl_hours.get(provider, self.ttl_hours["default"])
        cutoff = (datetime.now() - timedelta(hours=ttl)).isoformat()
        row = self.db.execute(
            "SELECT results FROM cache WHERE key = ? AND created_at > ?",
            (key, cutoff),
        ).fetchone()
        if row:
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return None
        return None

    def set(self, provider: str, query: str, results: Any):
        """Store results in cache."""
        key = self._cache_key(provider, query)
        self.db.execute(
            "INSERT OR REPLACE INTO cache (key, provider, query, results, created_at) VALUES (?, ?, ?, ?, ?)",
            (key, provider, query, json.dumps(results), datetime.now().isoformat()),
        )
        self.db.commit()

    def invalidate(self, provider: Optional[str] = None):
        """Clear cache. If provider given, clear only that provider."""
        if provider:
            self.db.execute("DELETE FROM cache WHERE provider = ?", (provider,))
        else:
            self.db.execute("DELETE FROM cache")
        self.db.commit()

    def stats(self) -> Dict[str, int]:
        """Return cache statistics by provider."""
        rows = self.db.execute(
            "SELECT provider, COUNT(*) FROM cache GROUP BY provider"
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def prune_expired(self):
        """Remove all expired entries."""
        for provider, ttl in self.ttl_hours.items():
            if provider == "default":
                continue
            cutoff = (datetime.now() - timedelta(hours=ttl)).isoformat()
            self.db.execute(
                "DELETE FROM cache WHERE provider = ? AND created_at <= ?",
                (provider, cutoff),
            )
        self.db.commit()

    def close(self):
        self.db.close()
