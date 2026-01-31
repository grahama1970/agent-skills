import feedparser
import time
from typing import List, Dict, Any
from rich.console import Console

from .base import BaseSource, SourceStats
from ..util.dedupe import generate_rss_key
from ..util.text import clean_summary

console = Console()

class RSSSource(BaseSource):
    def fetch(self, dry_run: bool = False, limit: int = 0) -> SourceStats:
        stats = SourceStats(source_key=self.key)
        
        # 1. Load state
        state = self.load_state()
        etag = state.get("etag")
        last_modified = state.get("last_modified")
        
        # 2. Fetch
        with self.make_http_client() as client:
            try:
                status, text, headers = client.fetch_text(
                    self.config.rss_url, 
                    etag=etag, 
                    last_modified=last_modified
                )
            except Exception as e:
                stats.errors += 1
                stats.status = "failed"
                console.print(f"[red]Fetch failed for {self.key}: {e}[/red]")
                return stats

            if status == 304:
                console.print(f"[dim]No changes for {self.key} (304 Not Modified)[/dim]")
                stats.status = "skipped_304"
                # Persist last_fetch_at even if not modified to reflect polling
                if not dry_run:
                    state["last_fetch_at"] = time.time()
                    self.save_state(state)
                return stats

            # 3. Parse
            feed = feedparser.parse(text)
            if feed.bozo:
                 console.print(f"[yellow]Feed {self.key} parsing warning: {feed.bozo_exception}[/yellow]")

            items_to_upsert = []
            entries = feed.entries
            if limit > 0:
                entries = entries[:limit]

            for entry in entries:
                try:
                    # Normalize
                    link = getattr(entry, "link", "")
                    guid = getattr(entry, "id", None)
                    title = getattr(entry, "title", "Untitled")
                    
                    # Dedupe Key
                    _key = generate_rss_key(self.key, guid, link)
                    
                    # Published Date
                    pub_struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
                    if pub_struct:
                        published_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", pub_struct)
                    else:
                        published_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

                    raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                    summary = clean_summary(raw_summary)

                    item = {
                        "_key": _key,
                        "source_key": self.key,
                        "type": "rss",
                        "title": title,
                        "url": link,
                        "published_at": published_at,
                        "summary": summary,
                        "tags": self.config.tags,
                        "ingested_at": time.time(),
                        "meta": {
                            "guid": guid,
                            "author": getattr(entry, "author", None)
                        }
                    }
                    items_to_upsert.append(item)
                    stats.parsed_count += 1
                    
                except Exception as e:
                    console.print(f"[red]Failed to parse item in {self.key}: {e}[/red]")
                    stats.errors += 1
                    if not dry_run:
                        self.storage.log_deadletter({
                            "source_key": self.key,
                            "error": str(e),
                            "item_raw": str(entry)[:1000]
                        })

        # 4. Upsert
        if not dry_run and items_to_upsert:
            writes = self.storage.upsert_items(items_to_upsert)
            stats.upserted_count = writes
        elif dry_run:
            console.print(f"[dim]Dry run: would upsert {len(items_to_upsert)} items[/dim]")

        # 5. Save State
        if not dry_run:
            new_state = {
                "etag": headers.get("ETag"),
                "last_modified": headers.get("Last-Modified"),
                "last_fetch_at": time.time(),
                "last_success_at": time.time()
            }
            self.save_state(new_state)

        return stats
