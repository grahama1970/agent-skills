import typer
from rich.console import Console
from rich.table import Table
from typing import Optional, List
from pathlib import Path
import sys

# Import local modules via package relative imports or standard import if existing in PYTHONPATH
from config import FeedConfig, FeedSource, SourceType
from storage import FeedStorage

app = typer.Typer(help="Consume Feed Agent Skill")
sources_app = typer.Typer(help="Manage feed sources")
app.add_typer(sources_app, name="sources")
console = Console()

@app.command()
def init():
    """Initialize a default configuration file."""
    config = FeedConfig.load()
    if config.sources:
        console.print("[yellow]Config already exists and has sources. Skipping init.[/yellow]")
        return
    
    config.save()
    console.print("[green]Initialized configs/feeds.yaml[/green]")

@app.command()
def doctor():
    """Verify environment health."""
    console.print("[bold]Checking Consume Feed Health...[/bold]")
    
    # Check 1: Config validity
    try:
        config = FeedConfig.load()
        console.print(f"[green]✓ Config loaded ({len(config.sources)} sources)[/green]")
    except Exception as e:
        console.print(f"[red]✗ Config error: {e}[/red]")
        sys.exit(1)

    # Check 2: ArangoDB Connection
    try:
        storage = FeedStorage()
        console.print(f"[green]✓ ArangoDB connected ('{storage.db_name}')[/green]")
    except Exception as e:
        console.print(f"[red]✗ ArangoDB error: {e}[/red]")
        sys.exit(1)

@app.command()
def run(
    mode: str = typer.Option("nightly", help="Run mode: nightly or manual"),
    source: Optional[List[str]] = typer.Option(None, help="Specific source keys to run"),
    dry_run: bool = typer.Option(False, help="Fetch only, do not write to DB"),
    limit: int = typer.Option(0, help="Max items to process per source (0=unlimited)")
):
    """Execute the ingestion loop."""
    from runner import FeedRunner
    
    config = FeedConfig.load()
    runner = FeedRunner(config, dry_run=dry_run, limit=limit)
    
    # Filter sources if specific keys provided
    target_sources = config.sources
    if source:
        target_sources = [s for s in config.sources if s.key in source]
        if not target_sources:
            console.print(f"[red]No matching sources found for keys: {source}[/red]")
            return

    if mode == "nightly":
        console.print("[blue]Starting Nightly Run...[/blue]")
        runner.run_batch(target_sources)
    else:
        console.print(f"[blue]Starting Manual Run ({len(target_sources)} sources)...[/blue]")
        runner.run_batch(target_sources)

# --- Source Management ---

@sources_app.command("list")
def list_sources():
    """List configured sources."""
    config = FeedConfig.load()
    table = Table("Key", "Type", "Enabled", "Details")
    for s in config.sources:
        details = ""
        if s.type == SourceType.RSS: details = s.rss_url
        elif s.type == SourceType.GITHUB: details = f"{s.gh_owner}/{s.gh_repo}"
        elif s.type == SourceType.NVD: details = f"Query: {s.nvd_query}"
        
        table.add_row(s.key, s.type.value, str(s.enabled), details)
    console.print(table)

@sources_app.command("add")
def add_source(
    type: SourceType,
    key: Optional[str] = None,
    # RSS params
    url: Optional[str] = None,
    # GitHub params
    repo: Optional[str] = None, # owner/repo
    # NVD params
    query: Optional[str] = None,
):
    """Add a new source."""
    config = FeedConfig.load()
    
    # Auto-generate key if missing
    if not key:
        import re
        if type == SourceType.RSS and url:
            key = re.sub(r'[^a-zA-Z0-9]', '_', url.split('//')[-1])[:30]
        elif type == SourceType.GITHUB and repo:
            key = repo.replace("/", "_")
        elif type == SourceType.NVD and query:
            key = f"nvd_{query.replace(' ', '_')}"
        else:
            console.print("[red]Could not auto-generate key. Please provide --key.[/red]")
            return

    # Check existence
    if any(s.key == key for s in config.sources):
        console.print(f"[red]Source '{key}' already exists.[/red]")
        return

    new_source = FeedSource(key=key, type=type)
    
    # Validate Type-Specific Args
    if type == SourceType.RSS:
        if not url:
            console.print("[red]RSS requires --url[/red]")
            return
        new_source.rss_url = url
        
    elif type == SourceType.GITHUB:
        if not repo or "/" not in repo:
            console.print("[red]GitHub requires --repo owner/name[/red]")
            return
        owner, name = repo.split("/", 1)
        new_source.gh_owner = owner
        new_source.gh_repo = name
        
    elif type == SourceType.NVD:
        if not query:
            console.print("[red]NVD requires --query[/red]")
            return
        new_source.nvd_query = query

    config.sources.append(new_source)
    config.save()
    console.print(f"[green]Added source {key} ({type})[/green]")

if __name__ == "__main__":
    app()
