#!/usr/bin/env python3
"""CLI interface for SFX catalog system."""

import sys
import typer
from rich.console import Console
from pathlib import Path

app = typer.Typer(help="SFX Catalog - Audio cataloging and search system")
console = Console()


@app.command()
def status():
    """Show system status and configuration."""
    console.print("[bold green]SFX Catalog Status[/bold green]")
    console.print("Status: Initialized")
    

@app.command()
def catalog(
    directory: Path = typer.Argument(..., help="Directory containing MP3 files"),
    output: Path = typer.Option("data/sfx_manifest.json", help="Output manifest file")
):
    """Scan directory and create audio catalog."""
    from .audio_analyzer import catalog_directory
    
    console.print(f"[yellow]Cataloging {directory}...[/yellow]")
    result = catalog_directory(directory, output)
    console.print(f"[green]✓ Cataloged {result['count']} files to {output}[/green]")


@app.command()
def ingest(manifest: Path = typer.Argument(..., help="Manifest JSON file")):
    """Ingest catalog into ArangoDB memory system."""
    from .memory_bridge import SFXMemoryBridge
    import json
    
    bridge = SFXMemoryBridge()
    with open(manifest) as f:
        data = json.load(f)
    
    console.print(f"[yellow]Ingesting {len(data.get('items', []))} items...[/yellow]")
    success = bridge.ingest_catalog(data)
    
    if success:
        console.print(f"[green]✓ Ingested {len(data.get('items', []))} items[/green]")
    else:
        console.print("[red]✗ Ingest failed[/red]")
        sys.exit(1)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(5, help="Maximum results to return"),
    categories: str = typer.Option(None, help="Filter by categories (comma-separated)")
):
    """Search for SFX by keyword."""
    from .memory_bridge import SFXMemoryBridge
    
    bridge = SFXMemoryBridge()
    cat_list = categories.split(",") if categories else None
    
    results = bridge.search_sfx(query, categories=cat_list, k=limit)
    
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return
    
    console.print(f"[bold]Found {len(results)} results:[/bold]")
    for i, r in enumerate(results, 1):
        console.print(f"{i}. {r.get('filename', 'unknown')}: {r.get('description', 'No description')}")


if __name__ == "__main__":
    app()
