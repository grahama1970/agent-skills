"""Find command for code-review skill."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer


def find(
    pattern: str = typer.Option("*review*.md", "--pattern", "-p", help="Glob pattern for filenames"),
    directory: Path = typer.Option(".", "--dir", "-d", help="Directory to search"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r", help="Search recursively"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results to show"),
    sort_by: str = typer.Option("modified", "--sort", "-s", help="Sort by: modified, name, size"),
    contains: Optional[str] = typer.Option(None, "--contains", "-c", help="Filter by content substring"),
) -> None:
    """Find review request markdown files."""
    if not directory.exists():
        typer.echo(f"Error: Directory not found: {directory}", err=True)
        raise typer.Exit(code=1)

    matches = []
    search_paths = directory.rglob(pattern) if recursive else directory.glob(pattern)

    for path in search_paths:
        if not path.is_file():
            continue
        if contains:
            try:
                content = path.read_text(errors="ignore")
                if contains.lower() not in content.lower():
                    continue
            except Exception:
                continue
        try:
            stat = path.stat()
        except Exception:
            continue
        matches.append({
            "path": str(path),
            "name": path.name,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "modified_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })

    if sort_by == "modified":
        matches.sort(key=lambda item: item["modified"], reverse=True)
    elif sort_by == "name":
        matches.sort(key=lambda item: item["name"].lower())
    elif sort_by == "size":
        matches.sort(key=lambda item: item["size"], reverse=True)

    matches = matches[:limit]
    if not matches:
        typer.echo(f"No files matching '{pattern}' found in {directory}", err=True)
        raise typer.Exit(code=0)

    typer.echo(f"Found {len(matches)} file(s):\n", err=True)
    for match in matches:
        size_kb = match["size"] / 1024
        typer.echo(f"  {match['modified_str']}  {size_kb:6.1f}KB  {match['path']}", err=True)

    print(json.dumps({
        "pattern": pattern,
        "directory": str(directory),
        "count": len(matches),
        "files": matches,
    }, indent=2))
