#!/usr/bin/env python3
"""Optional consume-feed integration for Dogpile."""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

from dogpile.config import SKILLS_DIR
from dogpile.utils import capture_execution_metadata, log_status, with_semaphore

FEED_PACK_DIR = _SCRIPT_DIR / "config" / "feed_packs"


class _NullFeedStorage:
    """Dry-run storage adapter for consume-feed RSS sources."""

    def get_state(self, key: str) -> Dict[str, Any]:
        return {}

    def save_state(self, key: str, state: Dict[str, Any]) -> None:
        return None

    def upsert_items(self, items: List[Dict[str, Any]]) -> int:
        return 0

    def log_deadletter(self, payload: Dict[str, Any]) -> None:
        return None


def _load_feed_pack(feed_pack: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Load a Dogpile feed pack, including optional parent pack sources."""
    pack_path = FEED_PACK_DIR / f"{feed_pack}.yaml"
    pack = yaml.safe_load(pack_path.read_text()) if pack_path.exists() else None
    if not pack:
        raise FileNotFoundError(f"Feed pack not found: {pack_path}")

    sources = list(pack.get("sources", []) or [])
    inherited_packs: List[str] = []
    parent_name = pack.get("extends")
    if parent_name:
        parent_pack, parent_sources = _load_feed_pack(parent_name)
        child_keys = {item.get("key") for item in sources}
        sources = [item for item in parent_sources if item.get("key") not in child_keys] + sources
        inherited_packs = [parent_name, *parent_pack.get("inherited_packs", [])]

    pack["inherited_packs"] = inherited_packs
    return pack, sources


@capture_execution_metadata("feeds", stage="stage1")
@with_semaphore("feeds")
def search_feeds(
    query: str,
    limit: int = 3,
    sources: Optional[List[str]] = None,
    feed_pack: str = "security_code",
    timeout_s: int = 120,
) -> Dict[str, Any]:
    """Run configured RSS feed monitors as an opt-in Dogpile lane.

    consume-feed is an ingestion monitor, not a query search API. Dogpile uses
    its RSS config/parser with null storage so this lane is live, no-write, and
    does not initialize Memory.
    """
    feed_dir = SKILLS_DIR / "consume-feed"
    if not feed_dir.exists():
        return {"error": f"consume-feed skill not found at {feed_dir}"}

    log_status("Running optional feed monitor dry-run...", provider="feeds", status="RUNNING")
    try:
        if str(feed_dir) not in sys.path:
            sys.path.insert(0, str(feed_dir))
        from feed_config import FeedConfig, FeedSource, SourceType
        from sources.rss import RSSSource
    except Exception as e:
        return {"error": f"consume-feed RSS modules unavailable: {e}", "query_context": query}

    try:
        if feed_pack:
            pack, pack_sources = _load_feed_pack(feed_pack)
            default_use = pack.get("default_use", "enrichment_only")
            false_positive_policy = pack.get(
                "false_positive_policy",
                "Feed hits are enrichment signals and must not be treated as automatic alerts or blocks.",
            )
            feed_sources = [
                FeedSource(
                    key=item["key"],
                    type=SourceType.RSS,
                    enabled=True,
                    tags=item.get("tags", []),
                    rss_url=item["rss_url"],
                )
                for item in pack_sources
            ]
            user_agent = "DogpileFeedMonitor/1.0"
            pack_description = pack.get("description")
        else:
            config = FeedConfig.load()
            default_use = "enrichment_only"
            false_positive_policy = (
                "Configured feed hits are enrichment signals and must not be treated as automatic alerts or blocks."
            )
            feed_sources = [
                source
                for source in config.sources
                if source.enabled and source.type == SourceType.RSS
            ]
            user_agent = config.run_options.user_agent
            pack_description = "consume-feed configured enabled RSS sources"
    except Exception as e:
        return {"error": f"feed source config failed to load: {e}", "query_context": query}

    requested = set(sources or [])
    if requested:
        feed_sources = [source for source in feed_sources if source.key in requested]
        found = {source.key for source in feed_sources}
        missing = sorted(requested - found)
    else:
        missing = []

    storage = _NullFeedStorage()
    source_results: List[Dict[str, Any]] = []

    def _fetch(source_cfg) -> Dict[str, Any]:
        source = RSSSource(source_cfg, storage, user_agent=user_agent)
        stats = source.fetch(dry_run=True, limit=limit)
        return {
            "source_key": stats.source_key,
            "status": stats.status,
            "parsed_count": stats.parsed_count,
            "errors": stats.errors,
            "rss_url": source_cfg.rss_url,
            "tags": source_cfg.tags,
        }

    max_workers = max(1, min(5, len(feed_sources) or 1))
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_source = {executor.submit(_fetch, source): source.key for source in feed_sources}
            for future in as_completed(future_to_source, timeout=timeout_s):
                source_key = future_to_source[future]
                try:
                    source_results.append(future.result())
                except Exception as e:
                    source_results.append({"source_key": source_key, "status": "failed", "errors": 1, "error": str(e)})
    except FuturesTimeoutError:
        done = {result.get("source_key") for result in source_results}
        for source in feed_sources:
            if source.key not in done:
                source_results.append({"source_key": source.key, "status": "timeout", "errors": 1})

    parsed_total = sum(int(result.get("parsed_count") or 0) for result in source_results)
    error_total = sum(int(result.get("errors") or 0) for result in source_results)
    result = {
        "query_context": query,
        "mode": "consume-feed-rss-dry-run",
        "feed_pack": feed_pack,
        "feed_pack_description": pack_description,
        "inherited_packs": pack.get("inherited_packs", []) if feed_pack else [],
        "default_use": default_use,
        "false_positive_policy": false_positive_policy,
        "limit": limit,
        "requested_sources": sorted(requested),
        "missing_sources": missing,
        "source_count": len(feed_sources),
        "parsed_total": parsed_total,
        "error_total": error_total,
        "results": sorted(source_results, key=lambda item: item.get("source_key", "")),
    }
    if not feed_sources:
        result["error"] = "No enabled RSS feed sources matched the request."
        log_status(result["error"], provider="feeds", status="ERROR")
    elif parsed_total <= 0:
        result["error"] = "No feed items parsed from configured RSS sources."
        log_status(result["error"], provider="feeds", status="ERROR")
    elif error_total:
        log_status("Optional feed monitor dry-run finished with degraded sources.", provider="feeds", status="DONE")
    else:
        log_status("Optional feed monitor dry-run finished.", provider="feeds", status="DONE")
    return result
