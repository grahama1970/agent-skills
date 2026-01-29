#!/usr/bin/env python3
"""
create-movie Orchestrator for Horus Persona

Coordinates the movie creation workflow through phases:
Research → Script → Build Tools → Generate → Assemble → Learn

Philosophy: "AI isn't the artist, it's the amplifier"
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

SKILL_DIR = Path(__file__).parent
PI_SKILLS_DIR = SKILL_DIR.parent  # .pi/skills/


@dataclass
class MovieProject:
    """Represents a movie project being created."""

    name: str
    prompt: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    research: dict = field(default_factory=dict)
    script: dict = field(default_factory=dict)
    tools: list = field(default_factory=list)
    assets: list = field(default_factory=list)
    output_path: Optional[str] = None

    def save(self, path: Path):
        """Save project state to JSON."""
        with open(path, "w") as f:
            json.dump(self.__dict__, f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "MovieProject":
        """Load project state from JSON."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)


def run_skill(skill_name: str, args: list[str], capture: bool = True) -> dict:
    """Run a skill from .pi/skills/ and return result."""
    skill_path = PI_SKILLS_DIR / skill_name / "run.sh"

    if not skill_path.exists():
        return {"error": f"Skill not found: {skill_name}", "path": str(skill_path)}

    cmd = ["bash", str(skill_path)] + args
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")

    try:
        result = subprocess.run(
            cmd, capture_output=capture, text=True, timeout=300, cwd=str(PI_SKILLS_DIR / skill_name)
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Skill timed out", "skill": skill_name}
    except Exception as e:
        return {"error": str(e), "skill": skill_name}


# =============================================================================
# Phase 1: Research
# =============================================================================


@click.command()
@click.argument("topic")
@click.option("--output", "-o", default="research.json", help="Output file for research results")
def research(topic: str, output: str):
    """Phase 1: Research techniques and tools via /dogpile, /surf, /memory."""
    console.print(Panel(f"[bold blue]RESEARCH PHASE[/bold blue]\nTopic: {topic}"))

    results = {"topic": topic, "timestamp": datetime.now().isoformat(), "sources": {}}

    # 1. Check memory first
    with console.status("[bold green]Checking memory for prior knowledge..."):
        memory_result = run_skill("memory", ["recall", "--q", topic, "--scope", "horus-filmmaking"])
        if memory_result.get("returncode") == 0:
            results["sources"]["memory"] = memory_result.get("stdout", "")
            console.print("[green]Found prior knowledge in memory[/green]")
        else:
            console.print("[dim]No prior knowledge found[/dim]")

    # 2. Research with dogpile
    with console.status("[bold green]Running deep research via /dogpile..."):
        dogpile_result = run_skill("dogpile", ["search", topic])
        if dogpile_result.get("returncode") == 0:
            results["sources"]["dogpile"] = dogpile_result.get("stdout", "")
            console.print("[green]Dogpile research complete[/green]")
        else:
            console.print(f"[yellow]Dogpile warning: {dogpile_result.get('stderr', '')}[/yellow]")

    # Save results
    output_path = Path(output)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    console.print(f"\n[bold green]Research saved to {output_path}[/bold green]")
    return results


# =============================================================================
# Phase 2: Script
# =============================================================================


@click.command()
@click.option("--from-research", "-r", required=True, help="Research JSON file")
@click.option("--output", "-o", default="script.json", help="Output file for script")
def script(from_research: str, output: str):
    """Phase 2: Generate script from research with scene breakdown."""
    console.print(Panel("[bold blue]SCRIPT PHASE[/bold blue]\nCollaborate on creative vision"))

    # Load research
    research_path = Path(from_research)
    if not research_path.exists():
        console.print(f"[red]Research file not found: {from_research}[/red]")
        sys.exit(1)

    with open(research_path) as f:
        research_data = json.load(f)

    # Script structure template
    script_data = {
        "title": "",
        "synopsis": "",
        "duration_seconds": 30,
        "scenes": [],
        "visual_style": "",
        "audio_style": "",
        "research_context": research_data,
        "timestamp": datetime.now().isoformat(),
    }

    # Interactive script building (placeholder for human collaboration)
    console.print("\n[bold]Script Template Created[/bold]")
    console.print("Edit the script.json file to define:")

    table = Table(show_header=True)
    table.add_column("Field", style="cyan")
    table.add_column("Description")
    table.add_row("title", "Movie title")
    table.add_row("synopsis", "Brief description")
    table.add_row("duration_seconds", "Target duration")
    table.add_row("scenes", "Array of scene objects (shot, dialogue, visual, audio)")
    table.add_row("visual_style", "e.g., 'film noir', 'vibrant colors'")
    table.add_row("audio_style", "e.g., 'dramatic narration', 'ambient music'")
    console.print(table)

    # Save template
    output_path = Path(output)
    with open(output_path, "w") as f:
        json.dump(script_data, f, indent=2)

    console.print(f"\n[bold green]Script template saved to {output_path}[/bold green]")
    console.print("[dim]Edit this file to define your scenes, then run build-tools phase.[/dim]")


# =============================================================================
# Phase 3: Build Tools
# =============================================================================


@click.command()
@click.option("--script", "-s", required=True, help="Script JSON file")
@click.option("--output-dir", "-o", default="./tools", help="Output directory for tools")
def build_tools(script: str, output_dir: str):
    """Phase 3: Build custom tools in Docker sandbox."""
    console.print(Panel("[bold blue]BUILD TOOLS PHASE[/bold blue]\nWrite code in Docker sandbox"))

    script_path = Path(script)
    if not script_path.exists():
        console.print(f"[red]Script file not found: {script}[/red]")
        sys.exit(1)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    with open(script_path) as f:
        script_data = json.load(f)

    console.print(f"[dim]Building tools for: {script_data.get('title', 'Untitled')}[/dim]")

    # Check Docker availability
    docker_check = subprocess.run(["docker", "info"], capture_output=True)
    if docker_check.returncode != 0:
        console.print("[red]Docker not available. Cannot build tools in sandbox.[/red]")
        sys.exit(1)

    # Build the sandbox image if needed
    dockerfile_path = SKILL_DIR / "Dockerfile"
    if dockerfile_path.exists():
        console.print("[dim]Building Docker sandbox image...[/dim]")
        build_result = subprocess.run(
            ["docker", "build", "-t", "horus-movie-sandbox", str(SKILL_DIR)],
            capture_output=True,
            text=True,
        )
        if build_result.returncode != 0:
            console.print(f"[red]Docker build failed: {build_result.stderr}[/red]")
            sys.exit(1)
        console.print("[green]Docker sandbox ready[/green]")
    else:
        console.print("[yellow]No Dockerfile found. Using host environment.[/yellow]")

    console.print(f"\n[bold green]Tools directory ready: {output_path}[/bold green]")
    console.print("[dim]Custom tools can be developed here for the generate phase.[/dim]")


# =============================================================================
# Phase 4: Generate Assets
# =============================================================================


@click.command()
@click.option("--tools", "-t", default="./tools", help="Tools directory")
@click.option("--script", "-s", required=True, help="Script JSON file")
@click.option("--output-dir", "-o", default="./assets", help="Output directory for assets")
def generate(tools: str, script: str, output_dir: str):
    """Phase 4: Generate visual/audio assets."""
    console.print(Panel("[bold blue]GENERATE PHASE[/bold blue]\nCreate images, video, and audio"))

    script_path = Path(script)
    if not script_path.exists():
        console.print(f"[red]Script file not found: {script}[/red]")
        sys.exit(1)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "images").mkdir(exist_ok=True)
    (output_path / "video").mkdir(exist_ok=True)
    (output_path / "audio").mkdir(exist_ok=True)

    with open(script_path) as f:
        script_data = json.load(f)

    scenes = script_data.get("scenes", [])
    if not scenes:
        console.print("[yellow]No scenes defined in script. Add scenes first.[/yellow]")
        sys.exit(1)

    console.print(f"[dim]Generating assets for {len(scenes)} scenes[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for i, scene in enumerate(scenes):
            task = progress.add_task(f"Scene {i + 1}: {scene.get('description', '')[:30]}...", total=3)

            # 1. Generate images via /create-image
            if scene.get("visual"):
                progress.update(task, description=f"Scene {i + 1}: Generating image...")
                image_result = run_skill(
                    "create-image",
                    ["generate", "--prompt", scene["visual"], "--output", str(output_path / "images" / f"scene_{i + 1}.png")],
                )
                progress.advance(task)

            # 2. Generate audio via /tts-train (Horus voice)
            if scene.get("dialogue"):
                progress.update(task, description=f"Scene {i + 1}: Generating audio...")
                # TTS would go here
                progress.advance(task)

            # 3. Generate video clip (if AI motion video requested)
            if scene.get("motion"):
                progress.update(task, description=f"Scene {i + 1}: Generating video...")
                # AI video generation would go here (LTX-Video, Mochi)
                progress.advance(task)

            progress.remove_task(task)

    # Save manifest
    manifest = {
        "script": str(script_path),
        "output_dir": str(output_path),
        "scenes_processed": len(scenes),
        "timestamp": datetime.now().isoformat(),
    }
    with open(output_path / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"\n[bold green]Assets generated in {output_path}[/bold green]")


# =============================================================================
# Phase 5: Assemble
# =============================================================================


@click.command()
@click.option("--assets", "-a", required=True, help="Assets directory")
@click.option("--output", "-o", required=True, help="Output file (e.g., movie.mp4)")
@click.option("--format", "-f", type=click.Choice(["mp4", "html"]), default="mp4")
def assemble(assets: str, output: str, format: str):
    """Phase 5: Assemble final output as MP4 or interactive HTML."""
    console.print(Panel(f"[bold blue]ASSEMBLE PHASE[/bold blue]\nOutput format: {format}"))

    assets_path = Path(assets)
    if not assets_path.exists():
        console.print(f"[red]Assets directory not found: {assets}[/red]")
        sys.exit(1)

    manifest_path = assets_path / "manifest.json"
    if not manifest_path.exists():
        console.print("[red]No manifest.json found. Run generate phase first.[/red]")
        sys.exit(1)

    output_path = Path(output)

    if format == "mp4":
        console.print("[dim]Assembling MP4 with FFmpeg...[/dim]")

        # Check FFmpeg
        ffmpeg_check = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if ffmpeg_check.returncode != 0:
            console.print("[red]FFmpeg not available.[/red]")
            sys.exit(1)

        # Build FFmpeg command to concat video/images with audio
        # This is a placeholder - actual implementation depends on asset structure
        console.print(f"[bold green]MP4 would be assembled to: {output_path}[/bold green]")
        console.print("[dim]FFmpeg concat/filter logic to be implemented based on assets.[/dim]")

    elif format == "html":
        console.print("[dim]Creating interactive HTML bundle...[/dim]")

        html_dir = output_path.parent / output_path.stem
        html_dir.mkdir(parents=True, exist_ok=True)

        # Create basic HTML viewer structure
        index_html = html_dir / "index.html"
        with open(index_html, "w") as f:
            f.write(
                """<!DOCTYPE html>
<html>
<head>
    <title>Horus Movie</title>
    <style>
        body { font-family: sans-serif; background: #1a1a1a; color: #fff; }
        .player { max-width: 800px; margin: 0 auto; padding: 20px; }
    </style>
</head>
<body>
    <div class="player">
        <h1>Movie Player</h1>
        <div id="canvas"></div>
        <div id="controls"></div>
    </div>
    <script src="player.js"></script>
</body>
</html>"""
            )

        console.print(f"[bold green]HTML bundle created at: {html_dir}[/bold green]")


# =============================================================================
# Full Workflow: Create
# =============================================================================


@click.command()
@click.argument("prompt")
@click.option("--output", "-o", default="movie.mp4", help="Output file")
@click.option("--work-dir", "-w", default="./movie_project", help="Working directory")
def create(prompt: str, output: str, work_dir: str):
    """Full orchestrated workflow: Research → Script → Build → Generate → Assemble → Learn."""
    console.print(
        Panel(
            f"[bold magenta]CREATE MOVIE[/bold magenta]\n\n"
            f'"{prompt}"\n\n'
            f"[dim]Orchestrating full workflow...[/dim]"
        )
    )

    work_path = Path(work_dir)
    work_path.mkdir(parents=True, exist_ok=True)

    project = MovieProject(
        name=prompt[:50].replace(" ", "_"),
        prompt=prompt,
    )

    # Phase indicators
    phases = [
        ("RESEARCH", "Gathering knowledge"),
        ("SCRIPT", "Creating scene breakdown"),
        ("BUILD TOOLS", "Preparing custom tools"),
        ("GENERATE", "Creating assets"),
        ("ASSEMBLE", "Combining into final output"),
        ("LEARN", "Storing insights in memory"),
    ]

    console.print("\n[bold]Workflow Phases:[/bold]")
    for i, (name, desc) in enumerate(phases, 1):
        console.print(f"  {i}. [cyan]{name}[/cyan] - {desc}")

    console.print("\n[dim]This is the orchestrator skeleton. Each phase will be implemented with full functionality.[/dim]")

    # Save project state
    project.save(work_path / "project.json")
    console.print(f"\n[bold green]Project initialized at: {work_path}[/bold green]")


# =============================================================================
# CLI Entry Point
# =============================================================================


@click.group()
def cli():
    """create-movie: Orchestrated movie creation for Horus persona."""
    pass


cli.add_command(create)
cli.add_command(research)
cli.add_command(script)
cli.add_command(build_tools, name="build-tools")
cli.add_command(generate)
cli.add_command(assemble)


if __name__ == "__main__":
    cli()
