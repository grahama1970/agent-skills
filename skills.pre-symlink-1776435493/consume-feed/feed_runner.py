"""feed_runner - consume-feed.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import concurrent.futures
import sys
from typing import List, Dict, Any, Optional
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table

from feed_config import FeedConfig, FeedSource, SourceType
from feed_storage import FeedStorage

# ── TaskClient integration ──────────────────────────────────────────────────
try:
    sys.path.insert(0, str(Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None
from sources.rss import RSSSource
# from sources.github import GitHubSource
# from sources.nvd import NVDSource

console = Console()

class FeedRunner:
    def __init__(self, config: FeedConfig):
        self.config = config
        self.storage = FeedStorage()
        self.user_agent = config.run_options.user_agent

    def _get_source_instance(self, source_config: FeedSource):
        """Factory method to instantiate the correct source class."""
        if source_config.type == SourceType.RSS:
            return RSSSource(source_config, self.storage, user_agent=self.user_agent)
        if source_config.type in (SourceType.GITHUB, SourceType.NVD):
            raise NotImplementedError(
                f"Source '{source_config.key}' is {source_config.type.value} (Phase 2 not yet implemented)"
            )
        return None

    def run(self, sources: Optional[List[FeedSource]] = None, dry_run: bool = False, limit: int = 0):
        """
        Execute ingestion for a list of sources or all configured ones.
        """
        # Ensure schema exists before running
        self.storage.ensure_schema()

        sources_to_run = sources
        if sources_to_run is None:
            sources_to_run = [s for s in self.config.sources if s.enabled]

        if not sources_to_run:
            console.print("[yellow]No sources to run.[/yellow]")
            return

        console.print(f"[bold blue]Starting ingestion for {len(sources_to_run)} sources...[/bold blue]")

        results = []
        start_time = time.time()
        monitor = TaskClient("consume-feed", total=len(sources_to_run)) if TaskClient else None

        # ThreadPool for parallel fetching
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.run_options.concurrency) as executor:
            future_to_source = {}
            for s_cfg in sources_to_run:
                inst = self._get_source_instance(s_cfg)
                if inst:
                    future_to_source[executor.submit(inst.fetch, dry_run=dry_run, limit=limit)] = s_cfg.key

            for future in concurrent.futures.as_completed(future_to_source):
                s_key = future_to_source[future]
                try:
                    stats = future.result()
                    results.append(stats)
                except Exception as e:
                    console.print(f"[red]Source '{s_key}' crashed: {e}[/red]")
                if monitor:
                    monitor.update(item=s_key)

        if monitor:
            monitor.finish()
        duration = time.time() - start_time
        self._print_summary(results, duration)
        
        if not dry_run:
            self.storage.log_run({
                "duration": duration,
                "source_count": len(sources_to_run),
                "total_items": sum(r.upserted_count for r in results),
                "total_errors": sum(r.errors for r in results)
            })

    def _print_summary(self, results: List[Any], duration: float):
        table = Table(title="Ingestion Summary")
        table.add_column("Source", style="cyan")
        table.add_column("Parsed", justify="right")
        table.add_column("Upserted", justify="right")
        table.add_column("Errors", justify="right", style="red")
        table.add_column("Status")

        for r in results:
            table.add_row(
                r.source_key,
                str(r.parsed_count),
                str(r.upserted_count),
                str(r.errors),
                r.status
            )

        console.print(table)
        console.print(f"[dim]Total time: {duration:.2f}s[/dim]")
