import sys
import os
from rich.console import Console

# Ensure import path to skill root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SKILL_ROOT)

from feed_storage import FeedStorage
from feed_config import FeedSource, SourceType
from sources.rss import RSSSource

console = Console()

def test_live_rss():
    console.print("[bold blue]Testing Live RSS Ingestion (GitHub Blog)...[/bold blue]")
    
    try:
        storage = FeedStorage()
        source_cfg = FeedSource(
            key="live_test_github",
            type=SourceType.RSS,
            rss_url="https://github.blog/feed/"
        )
        source = RSSSource(source_cfg, storage)
        
        console.print(f"Fetching {source_cfg.rss_url}...")
        stats = source.fetch(dry_run=True, limit=3)
        
        if stats.status == "ok" and stats.parsed_count > 0:
            console.print(f"[green]✅ Successfully parsed {stats.parsed_count} items from live feed![/green]")
            # Note: Items are NOT written to DB because dry_run=True
            return True
        else:
            console.print(f"[red]❌ Live fetch failed. Status: {stats.status}, Parsed: {stats.parsed_count}[/red]")
            return False
            
    except Exception as e:
        console.print(f"[red]❌ Live test crashed: {e}[/red]")
        return False

if __name__ == "__main__":
    success = test_live_rss()
    if not success:
        sys.exit(1)
