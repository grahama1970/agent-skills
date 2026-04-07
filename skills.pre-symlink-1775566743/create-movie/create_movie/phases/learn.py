"""
Phase 6: Learn

Store learnings in memory for future recall.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..skill_registry import run_skill

console = Console()


def extract_learnings(project_dir: Path) -> list[dict]:
    """Extract learnings from a completed movie project for memory storage."""
    learnings = []

    # Load project and manifest
    project_file = project_dir / "project.json"
    assets_manifest = project_dir / "assets" / "manifest.json"

    project_data = {}
    manifest_data = {}

    if project_file.exists():
        with open(project_file) as f:
            project_data = json.load(f)

    if assets_manifest.exists():
        with open(assets_manifest) as f:
            manifest_data = json.load(f)

    prompt = project_data.get("prompt", "")
    script_data = manifest_data.get("script_data", {})

    # Extract learnings about successful prompts
    assets = manifest_data.get("assets", {})
    images = assets.get("images", [])
    for img in images:
        if img.get("file") and Path(img["file"]).exists():
            learnings.append({
                "question": f"What image prompt works well for: {img.get('prompt', '')[:50]}?",
                "reasoning": "This prompt successfully generated an image during movie creation",
                "answer": img.get("prompt", ""),
                "tags": ["image-generation", "prompt-engineering", "filmmaking"],
            })

    # Extract learnings about visual styles
    visual_style = manifest_data.get("visual_style", "")
    if visual_style:
        learnings.append({
            "question": f"What visual style works for movies about: {prompt[:50]}?",
            "reasoning": f"Used in successful movie creation with {len(images)} generated images",
            "answer": visual_style,
            "tags": ["visual-style", "cinematography", "filmmaking"],
        })

    # Extract scene structure learnings
    scenes = script_data.get("scenes", [])
    if len(scenes) >= 3:
        scene_structure = [s.get("heading", "") for s in scenes[:5]]
        learnings.append({
            "question": f"How to structure scenes for a {len(scenes)}-scene movie?",
            "reasoning": f"Scene breakdown from movie: {prompt[:30]}",
            "answer": "\n".join(scene_structure),
            "tags": ["scene-structure", "screenplay", "filmmaking"],
        })

    # Extract learnings from research
    research_file = project_dir / "research.json"
    if research_file.exists():
        with open(research_file) as f:
            research = json.load(f)
        topic = research.get("topic", "")
        sources = research.get("sources", {})
        if sources:
            source_types = list(sources.keys())
            learnings.append({
                "question": f"What sources are useful for researching: {topic[:50]}?",
                "reasoning": "These sources provided useful context for movie creation",
                "answer": f"Consulted: {', '.join(source_types)}",
                "tags": ["research", "sources", "filmmaking"],
            })

    return learnings


def store_learnings(
    project_dir: Path,
    scope: str = "horus-filmmaking",
    dry_run: bool = False,
) -> dict:
    """
    Store learnings in memory for future recall.

    Args:
        project_dir: Project directory to extract learnings from
        scope: Memory scope for storage
        dry_run: If True, show learnings without storing

    Returns:
        dict with learning results
    """
    if not project_dir.exists():
        console.print(f"[red]Project directory not found: {project_dir}[/red]")
        sys.exit(1)

    console.print("[dim]Extracting learnings from project...[/dim]")
    learnings = extract_learnings(project_dir)

    results = {
        "project_dir": str(project_dir),
        "scope": scope,
        "dry_run": dry_run,
        "learnings_count": len(learnings),
        "stored_count": 0,
        "learnings": learnings,
    }

    if not learnings:
        console.print("[yellow]No learnings extracted from project[/yellow]")
        return results

    console.print(f"\n[bold]Extracted {len(learnings)} learnings:[/bold]")
    table = Table(show_header=True)
    table.add_column("#", style="dim")
    table.add_column("Question", max_width=50)
    table.add_column("Tags")
    for i, learning in enumerate(learnings, 1):
        table.add_row(
            str(i),
            learning["question"][:50],
            ", ".join(learning.get("tags", [])[:2])
        )
    console.print(table)

    if dry_run:
        console.print("\n[dim]Dry run - not storing to memory[/dim]")
        return results

    # Store each learning in memory using /memory learn
    console.print(f"\n[cyan]── Storing to memory via /memory learn (scope: {scope}) ──[/cyan]")
    stored = 0
    for learning in learnings:
        result = run_skill("memory", [
            "learn",
            "--problem", learning['question'],
            "--solution", f"{learning['reasoning']}\n\n{learning['answer']}",
            "--scope", scope,
        ])

        if result.get("returncode") == 0:
            stored += 1
            console.print(f"  [green]✓ Stored: {learning['question'][:40]}...[/green]")
        else:
            console.print(f"  [yellow]✗ Failed to store: {result.get('stderr', '')[:50]}[/yellow]")

    results["stored_count"] = stored
    console.print(f"\n[bold green]Stored {stored}/{len(learnings)} learnings in scope '{scope}'[/bold green]")

    # Save learnings to project for reference
    learnings_file = project_dir / "learnings.json"
    with open(learnings_file, "w") as f:
        json.dump({
            "learnings": learnings,
            "scope": scope,
            "stored_count": stored,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2)
    console.print(f"[dim]Learnings saved to {learnings_file}[/dim]")

    return results
