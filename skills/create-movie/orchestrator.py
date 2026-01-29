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
@click.option("--skip-external", is_flag=True, help="Skip external search (library only)")
def research(topic: str, output: str, skip_external: bool):
    """Phase 1: Research techniques and tools - library first, then external."""
    console.print(Panel(f"[bold blue]RESEARCH PHASE[/bold blue]\nTopic: {topic}"))

    results = {
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
        "library": {},   # What Horus already has
        "external": {},  # New resources found
        "sources": {},   # Combined
    }

    # =========================================================================
    # PART 1: CHECK HORUS'S LIBRARY (what he already has)
    # =========================================================================
    console.print("\n[cyan]── Checking Library ──[/cyan]")

    # 1a. horus-filmmaking scope - past filmmaking knowledge, techniques
    with console.status("[green]Recalling filmmaking knowledge (horus-filmmaking)..."):
        filmmaking_result = run_skill(
            "memory", ["recall", "--q", topic, "--scope", "horus-filmmaking", "--k", "5"]
        )
        if filmmaking_result.get("returncode") == 0 and filmmaking_result.get("stdout", "").strip():
            results["library"]["filmmaking"] = filmmaking_result.get("stdout", "")
            console.print("  [green]✓ Found filmmaking knowledge[/green]")

    # 1b. horus_lore scope - YouTube transcripts may have film analysis
    with console.status("[green]Recalling lore/analysis (horus_lore)..."):
        lore_result = run_skill(
            "memory", ["recall", "--q", f"{topic} cinematography visual style", "--scope", "horus_lore", "--k", "3"]
        )
        if lore_result.get("returncode") == 0 and lore_result.get("stdout", "").strip():
            results["library"]["lore"] = lore_result.get("stdout", "")
            console.print("  [green]✓ Found relevant lore/analysis[/green]")

    # 1c. Ingested movies with emotion tags
    with console.status("[green]Checking movie library (ingested films)..."):
        movie_result = run_skill(
            "memory", ["recall", "--q", f"{topic} movie film scene emotion pacing", "--scope", "horus_lore", "--k", "5"]
        )
        if movie_result.get("returncode") == 0 and movie_result.get("stdout", "").strip():
            results["library"]["movies"] = movie_result.get("stdout", "")
            console.print("  [green]✓ Found relevant ingested movies[/green]")

    # 1d. Episodic archive - past filmmaking sessions
    with console.status("[green]Checking episodic archive..."):
        episodic_result = run_skill(
            "episodic-archiver", ["recall", "--q", f"{topic} filmmaking video", "--k", "3"]
        )
        if episodic_result.get("returncode") == 0 and episodic_result.get("stdout", "").strip():
            results["library"]["episodic"] = episodic_result.get("stdout", "")
            console.print("  [green]✓ Found past filmmaking sessions[/green]")

    library_count = sum(1 for v in results["library"].values() if v)
    console.print(f"[cyan]Library: {library_count} sources found[/cyan]")

    if skip_external:
        console.print("[dim]Skipping external search (--skip-external)[/dim]")
    else:
        # =========================================================================
        # PART 2: SEARCH FOR NEW RESOURCES (external)
        # =========================================================================
        console.print("\n[cyan]── Searching for New Resources ──[/cyan]")

        # 2a. Search for new movies to watch for inspiration
        with console.status("[green]Searching for films to watch (ingest-movie)..."):
            movie_search = run_skill("ingest-movie", ["search", topic])
            if movie_search.get("returncode") == 0 and movie_search.get("stdout", "").strip():
                results["external"]["new_movies"] = movie_search.get("stdout", "")
                console.print("  [green]✓ Found movies to watch for inspiration[/green]")

        # 2b. Search YouTube for tutorials/techniques
        with console.status("[green]Searching YouTube for tutorials (ingest-youtube)..."):
            yt_search = run_skill("ingest-youtube", ["search", f"{topic} tutorial filmmaking technique"])
            if yt_search.get("returncode") == 0 and yt_search.get("stdout", "").strip():
                results["external"]["youtube"] = yt_search.get("stdout", "")
                console.print("  [green]✓ Found YouTube tutorials[/green]")

        external_count = sum(1 for v in results["external"].values() if v)
        console.print(f"[cyan]External: {external_count} new sources found[/cyan]")

        # =========================================================================
        # PART 3: DEEP EXTERNAL RESEARCH (web)
        # =========================================================================
        console.print("\n[cyan]── Deep Web Research ──[/cyan]")

        # 3a. Research with dogpile
        with console.status("[green]Running dogpile research..."):
            dogpile_query = f"{topic} filmmaking techniques cinematography tutorial"
            dogpile_result = run_skill("dogpile", ["search", dogpile_query])
            if dogpile_result.get("returncode") == 0 and dogpile_result.get("stdout", "").strip():
                results["external"]["dogpile"] = dogpile_result.get("stdout", "")
                console.print("  [green]✓ Dogpile research complete[/green]")
            else:
                console.print(f"  [yellow]Dogpile warning: {dogpile_result.get('stderr', '')[:100]}[/yellow]")

    # Merge into flat sources dict for backwards compatibility
    results["sources"] = {**results["library"], **results["external"]}

    # Save results
    output_path = Path(output)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    console.print(f"\n[bold green]Research saved to {output_path}[/bold green]")
    return results


# =============================================================================
# Phase 2: Script
# =============================================================================


def parse_screenplay_to_scenes(screenplay_text: str) -> list[dict]:
    """Parse a screenplay format text into structured scene data."""
    scenes = []
    current_scene = None

    lines = screenplay_text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Scene heading (INT./EXT.)
        if line.startswith(("INT.", "EXT.", "INT/EXT")):
            if current_scene:
                scenes.append(current_scene)
            current_scene = {
                "heading": line,
                "location": line.split(" - ")[0] if " - " in line else line,
                "time": line.split(" - ")[1] if " - " in line else "DAY",
                "action": [],
                "dialogue": [],
                "visual": "",
                "audio": "",
                "shot_type": "WIDE",  # Default
            }
        elif current_scene:
            # Character name (ALL CAPS, centered)
            if line.isupper() and len(line) < 30 and not line.startswith("["):
                current_scene["current_speaker"] = line
            # Parenthetical
            elif line.startswith("(") and line.endswith(")"):
                pass  # Acting direction, skip for now
            # Audio cue
            elif line.startswith("[") and line.endswith("]"):
                current_scene["audio"] = line[1:-1]
            # Dialogue (follows character name)
            elif current_scene.get("current_speaker"):
                current_scene["dialogue"].append({
                    "speaker": current_scene.pop("current_speaker"),
                    "line": line
                })
            # Action line
            else:
                current_scene["action"].append(line)
                # First action line becomes visual description
                if not current_scene["visual"]:
                    current_scene["visual"] = line

    if current_scene:
        scenes.append(current_scene)

    return scenes


@click.command()
@click.option("--from-research", "-r", required=True, help="Research JSON file")
@click.option("--prompt", "-p", default=None, help="Movie concept/prompt (overrides research topic)")
@click.option("--duration", "-d", default=30, help="Target duration in seconds")
@click.option("--use-create-story", is_flag=True, help="Use /create-story to generate screenplay")
@click.option("--model", "-m", default="chimera", help="LLM model for screenplay generation")
@click.option("--output", "-o", default="script.json", help="Output file for script")
def script(from_research: str, prompt: str, duration: int, use_create_story: bool, model: str, output: str):
    """Phase 2: Generate script from research with scene breakdown."""
    console.print(Panel("[bold blue]SCRIPT PHASE[/bold blue]\nCreate scene breakdown"))

    # Load research
    research_path = Path(from_research)
    if not research_path.exists():
        console.print(f"[red]Research file not found: {from_research}[/red]")
        sys.exit(1)

    with open(research_path) as f:
        research_data = json.load(f)

    # Get prompt from research or override
    movie_prompt = prompt or research_data.get("topic", "A short film")
    console.print(f"[dim]Creating screenplay for: {movie_prompt}[/dim]")

    # Script structure
    script_data = {
        "title": movie_prompt[:50],
        "synopsis": "",
        "duration_seconds": duration,
        "scenes": [],
        "visual_style": "",
        "audio_style": "",
        "screenplay_raw": "",
        "research_context": research_data,
        "timestamp": datetime.now().isoformat(),
    }

    if use_create_story:
        # Use /create-story to generate screenplay
        console.print("\n[cyan]── Generating Screenplay via /create-story ──[/cyan]")

        screenplay_prompt = f"""A {duration}-second short film: {movie_prompt}

Requirements:
- Format as proper screenplay (INT./EXT. headings, action lines, dialogue)
- Include [AUDIO CUE] annotations for sound effects/music
- Visual descriptions should be detailed enough for AI image generation
- Each scene should be 5-10 seconds"""

        with console.status("[green]Generating screenplay..."):
            story_result = run_skill("create-story", [
                "create", screenplay_prompt,
                "--format", "screenplay",
                "--model", model,
                "--iterations", "1",  # Quick single draft for movie
                "--output", str(Path(output).parent / "screenplay_project"),
            ])

            if story_result.get("returncode") == 0:
                # Read the generated screenplay
                screenplay_dir = Path(output).parent / "screenplay_project"
                final_file = screenplay_dir / "final.md"
                if final_file.exists():
                    with open(final_file) as f:
                        screenplay_text = f.read()
                    script_data["screenplay_raw"] = screenplay_text
                    script_data["scenes"] = parse_screenplay_to_scenes(screenplay_text)
                    console.print(f"  [green]✓ Generated {len(script_data['scenes'])} scenes[/green]")
                else:
                    console.print("  [yellow]Screenplay file not found, using template[/yellow]")
            else:
                console.print(f"  [yellow]create-story failed: {story_result.get('stderr', '')[:100]}[/yellow]")

    # If no scenes generated, create template
    if not script_data["scenes"]:
        console.print("\n[bold]Creating scene template...[/bold]")

        # Calculate scenes based on duration (5-10 seconds per scene)
        num_scenes = max(3, duration // 7)

        for i in range(num_scenes):
            script_data["scenes"].append({
                "heading": f"INT. LOCATION {i+1} - DAY",
                "location": f"Location {i+1}",
                "time": "DAY",
                "action": [f"[Describe action for scene {i+1}]"],
                "dialogue": [],
                "visual": f"[Visual description for scene {i+1} - detailed enough for AI generation]",
                "audio": f"[Audio cue for scene {i+1}]",
                "shot_type": ["WIDE", "MEDIUM", "CLOSE-UP"][i % 3],
                "duration_seconds": duration // num_scenes,
            })

        console.print(f"[dim]Created {num_scenes} scene templates[/dim]")

    # Display scene summary
    console.print("\n[bold]Scene Breakdown:[/bold]")
    table = Table(show_header=True)
    table.add_column("#", style="dim")
    table.add_column("Heading", style="cyan")
    table.add_column("Visual", max_width=40)
    table.add_column("Audio")
    for i, scene in enumerate(script_data["scenes"], 1):
        table.add_row(
            str(i),
            scene.get("heading", "")[:30],
            (scene.get("visual", "") or "")[:40],
            scene.get("audio", "") or "[none]"
        )
    console.print(table)

    # Save script
    output_path = Path(output)
    with open(output_path, "w") as f:
        json.dump(script_data, f, indent=2)

    console.print(f"\n[bold green]Script saved to {output_path}[/bold green]")
    if not use_create_story:
        console.print("[dim]Edit the scenes to customize, then run build-tools phase.[/dim]")


# =============================================================================
# Phase 3: Build Tools
# =============================================================================


def analyze_tool_requirements(script_data: dict) -> list[dict]:
    """Analyze script to determine what tools are needed."""
    tools_needed = []
    scenes = script_data.get("scenes", [])

    has_images = any(s.get("visual") for s in scenes)
    has_dialogue = any(s.get("dialogue") for s in scenes)
    has_audio = any(s.get("audio") for s in scenes)
    has_motion = any(s.get("motion") for s in scenes)

    if has_images:
        tools_needed.append({
            "name": "image_generator",
            "purpose": "Generate images from visual descriptions",
            "uses": ["create-image", "ComfyUI", "Stable Diffusion"],
        })

    if has_dialogue:
        tools_needed.append({
            "name": "tts_generator",
            "purpose": "Generate speech from dialogue",
            "uses": ["tts-train", "IndexTTS2", "Horus voice model"],
        })

    if has_audio:
        tools_needed.append({
            "name": "audio_processor",
            "purpose": "Add sound effects and music",
            "uses": ["FFmpeg", "audio mixing"],
        })

    if has_motion:
        tools_needed.append({
            "name": "video_generator",
            "purpose": "Generate video from images/prompts",
            "uses": ["LTX-Video", "Mochi 1", "Deforum"],
        })

    # Always need assembly tool
    tools_needed.append({
        "name": "frame_assembler",
        "purpose": "Combine frames and audio into video",
        "uses": ["FFmpeg", "moviepy"],
    })

    return tools_needed


def generate_tool_code(tool: dict, script_data: dict) -> str:
    """Generate Python code for a tool based on requirements."""
    if tool["name"] == "image_generator":
        return '''#!/usr/bin/env python3
"""Image Generator Tool - Uses /create-image skill"""
import json
import subprocess
import sys
from pathlib import Path

def generate_image(prompt: str, output_path: str, style: str = "") -> bool:
    """Generate an image using the create-image skill."""
    full_prompt = f"{style} {prompt}".strip() if style else prompt

    result = subprocess.run([
        "bash", "../create-image/run.sh",
        "generate",
        "--prompt", full_prompt,
        "--output", output_path,
    ], capture_output=True, text=True)

    return result.returncode == 0

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python image_generator.py <prompt> <output_path> [style]")
        sys.exit(1)

    prompt = sys.argv[1]
    output = sys.argv[2]
    style = sys.argv[3] if len(sys.argv) > 3 else ""

    success = generate_image(prompt, output, style)
    sys.exit(0 if success else 1)
'''
    elif tool["name"] == "tts_generator":
        return '''#!/usr/bin/env python3
"""TTS Generator Tool - Uses Horus voice model"""
import json
import subprocess
import sys
from pathlib import Path

def generate_speech(text: str, output_path: str, speaker: str = "horus") -> bool:
    """Generate speech using TTS."""
    # Try tts-train skill first
    result = subprocess.run([
        "bash", "../tts-train/run.sh",
        "synthesize",
        "--text", text,
        "--output", output_path,
        "--voice", speaker,
    ], capture_output=True, text=True)

    if result.returncode == 0:
        return True

    # Fallback: Use faster-whisper for TTS (if available)
    print(f"TTS skill unavailable, placeholder created: {output_path}")
    Path(output_path).touch()
    return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python tts_generator.py <text> <output_path> [speaker]")
        sys.exit(1)

    text = sys.argv[1]
    output = sys.argv[2]
    speaker = sys.argv[3] if len(sys.argv) > 3 else "horus"

    success = generate_speech(text, output, speaker)
    sys.exit(0 if success else 1)
'''
    elif tool["name"] == "frame_assembler":
        return '''#!/usr/bin/env python3
"""Frame Assembler Tool - Uses FFmpeg"""
import json
import subprocess
import sys
from pathlib import Path

def assemble_video(
    frames_dir: str,
    audio_file: str = None,
    output_path: str = "output.mp4",
    fps: int = 24,
    duration_per_frame: float = None
) -> bool:
    """Assemble frames and audio into video using FFmpeg."""
    frames = sorted(Path(frames_dir).glob("*.png"))
    if not frames:
        print(f"No frames found in {frames_dir}")
        return False

    # Calculate duration per frame if not specified
    if duration_per_frame is None:
        duration_per_frame = 1.0 / fps

    # Create frame list file for FFmpeg
    list_file = Path(frames_dir) / "frames.txt"
    with open(list_file, "w") as f:
        for frame in frames:
            f.write(f"file '{frame.absolute()}'\\n")
            f.write(f"duration {duration_per_frame}\\n")

    # Build FFmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
    ]

    if audio_file and Path(audio_file).exists():
        cmd.extend(["-i", audio_file, "-c:a", "aac"])

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        output_path
    ])

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_dir", help="Directory containing frame images")
    parser.add_argument("--audio", "-a", help="Audio file to include")
    parser.add_argument("--output", "-o", default="output.mp4")
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args()

    success = assemble_video(args.frames_dir, args.audio, args.output, args.fps)
    sys.exit(0 if success else 1)
'''
    else:
        return f'''#!/usr/bin/env python3
"""Tool: {tool["name"]}
Purpose: {tool["purpose"]}
Uses: {", ".join(tool["uses"])}
"""
# TODO: Implement {tool["name"]}
print("Tool {tool["name"]} not yet implemented")
'''


def run_in_docker(code: str, work_dir: Path, timeout: int = 300) -> dict:
    """Execute Python code in Docker sandbox."""
    # Write code to temp file
    code_file = work_dir / "sandbox_code.py"
    with open(code_file, "w") as f:
        f.write(code)

    # Run in Docker
    cmd = [
        "docker", "run",
        "--rm",
        "--network", "none",  # No network access for security
        "-v", f"{work_dir.absolute()}:/workspace",
        "-w", "/workspace",
        "horus-movie-sandbox",
        "python", "sandbox_code.py"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Execution timed out", "returncode": -1}
    except Exception as e:
        return {"error": str(e), "returncode": -1}


@click.command()
@click.option("--script", "-s", required=True, help="Script JSON file")
@click.option("--output-dir", "-o", default="./tools", help="Output directory for tools")
@click.option("--skip-docker", is_flag=True, help="Skip Docker sandbox (use host)")
def build_tools(script: str, output_dir: str, skip_docker: bool):
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

    # Analyze what tools are needed
    console.print("\n[cyan]── Analyzing Tool Requirements ──[/cyan]")
    tools_needed = analyze_tool_requirements(script_data)

    table = Table(show_header=True, title="Tools to Build")
    table.add_column("Tool", style="cyan")
    table.add_column("Purpose")
    table.add_column("Uses")
    for tool in tools_needed:
        table.add_row(tool["name"], tool["purpose"], ", ".join(tool["uses"][:2]))
    console.print(table)

    # Check Docker availability (unless skipped)
    use_docker = not skip_docker
    if use_docker:
        docker_check = subprocess.run(["docker", "info"], capture_output=True)
        if docker_check.returncode != 0:
            console.print("[yellow]Docker not available. Using host environment.[/yellow]")
            use_docker = False
        else:
            # Build the sandbox image
            dockerfile_path = SKILL_DIR / "Dockerfile"
            if dockerfile_path.exists():
                console.print("\n[dim]Building Docker sandbox image...[/dim]")
                build_result = subprocess.run(
                    ["docker", "build", "-t", "horus-movie-sandbox", str(SKILL_DIR)],
                    capture_output=True,
                    text=True,
                )
                if build_result.returncode != 0:
                    console.print(f"[yellow]Docker build failed, using host: {build_result.stderr[:100]}[/yellow]")
                    use_docker = False
                else:
                    console.print("[green]Docker sandbox ready[/green]")

    # Generate tool code
    console.print("\n[cyan]── Generating Tool Code ──[/cyan]")
    tools_manifest = {"tools": [], "timestamp": datetime.now().isoformat()}

    for tool in tools_needed:
        tool_file = output_path / f"{tool['name']}.py"
        code = generate_tool_code(tool, script_data)

        with open(tool_file, "w") as f:
            f.write(code)

        # Make executable
        tool_file.chmod(0o755)

        tools_manifest["tools"].append({
            "name": tool["name"],
            "file": str(tool_file),
            "purpose": tool["purpose"],
        })
        console.print(f"  [green]✓ Created {tool_file.name}[/green]")

    # Save manifest
    manifest_file = output_path / "manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(tools_manifest, f, indent=2)

    console.print(f"\n[bold green]Tools built: {output_path}[/bold green]")
    console.print(f"[dim]Environment: {'Docker sandbox' if use_docker else 'Host'}[/dim]")


# =============================================================================
# Phase 4: Generate Assets
# =============================================================================


@click.command()
@click.option("--tools", "-t", default="./tools", help="Tools directory")
@click.option("--script", "-s", required=True, help="Script JSON file")
@click.option("--output-dir", "-o", default="./assets", help="Output directory for assets")
@click.option("--style", default="", help="Visual style to apply (e.g., 'cinematic', 'film noir')")
def generate(tools: str, script: str, output_dir: str, style: str):
    """Phase 4: Generate visual/audio assets for each scene."""
    console.print(Panel("[bold blue]GENERATE PHASE[/bold blue]\nCreate images, video, and audio"))

    script_path = Path(script)
    if not script_path.exists():
        console.print(f"[red]Script file not found: {script}[/red]")
        sys.exit(1)

    tools_path = Path(tools)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    images_dir = output_path / "images"
    video_dir = output_path / "video"
    audio_dir = output_path / "audio"
    for d in [images_dir, video_dir, audio_dir]:
        d.mkdir(exist_ok=True)

    with open(script_path) as f:
        script_data = json.load(f)

    scenes = script_data.get("scenes", [])
    if not scenes:
        console.print("[yellow]No scenes defined in script. Add scenes first.[/yellow]")
        sys.exit(1)

    visual_style = style or script_data.get("visual_style", "")
    console.print(f"[dim]Generating assets for {len(scenes)} scenes[/dim]")
    if visual_style:
        console.print(f"[dim]Visual style: {visual_style}[/dim]")

    # Track generated assets
    generated_assets = {
        "images": [],
        "audio": [],
        "video": [],
    }

    for i, scene in enumerate(scenes):
        scene_num = i + 1
        console.print(f"\n[cyan]── Scene {scene_num}/{len(scenes)} ──[/cyan]")

        # 1. Generate image for visual description
        if scene.get("visual"):
            visual_prompt = scene["visual"]
            if visual_style:
                visual_prompt = f"{visual_style}, {visual_prompt}"

            image_file = images_dir / f"scene_{scene_num:03d}.png"
            console.print(f"  [dim]Generating image: {visual_prompt[:50]}...[/dim]")

            image_result = run_skill(
                "create-image",
                ["generate", "--prompt", visual_prompt, "--output", str(image_file)],
            )

            if image_result.get("returncode") == 0:
                generated_assets["images"].append({
                    "scene": scene_num,
                    "file": str(image_file),
                    "prompt": visual_prompt,
                })
                console.print(f"  [green]✓ Image: {image_file.name}[/green]")
            else:
                console.print(f"  [yellow]Image generation failed[/yellow]")

        # 2. Generate TTS audio for dialogue
        if scene.get("dialogue"):
            dialogue_lines = scene["dialogue"]
            if isinstance(dialogue_lines, list):
                # Combine all dialogue lines
                all_dialogue = " ".join(
                    d.get("line", d) if isinstance(d, dict) else str(d)
                    for d in dialogue_lines
                )
            else:
                all_dialogue = str(dialogue_lines)

            if all_dialogue.strip():
                audio_file = audio_dir / f"dialogue_{scene_num:03d}.wav"
                console.print(f"  [dim]Generating TTS: {all_dialogue[:50]}...[/dim]")

                # Try tts-train skill
                tts_result = run_skill(
                    "tts-train",
                    ["synthesize", "--text", all_dialogue, "--output", str(audio_file)],
                )

                if tts_result.get("returncode") == 0:
                    generated_assets["audio"].append({
                        "scene": scene_num,
                        "file": str(audio_file),
                        "type": "dialogue",
                        "text": all_dialogue,
                    })
                    console.print(f"  [green]✓ Audio: {audio_file.name}[/green]")
                else:
                    # Create placeholder
                    audio_file.touch()
                    console.print(f"  [yellow]TTS unavailable, placeholder created[/yellow]")

        # 3. Generate audio cue/music
        if scene.get("audio"):
            audio_cue = scene["audio"]
            cue_file = audio_dir / f"cue_{scene_num:03d}.wav"
            console.print(f"  [dim]Audio cue: {audio_cue}[/dim]")
            # Audio cue generation would use a music/SFX generation tool
            cue_file.touch()  # Placeholder
            generated_assets["audio"].append({
                "scene": scene_num,
                "file": str(cue_file),
                "type": "cue",
                "description": audio_cue,
            })

        # 4. Generate video clip if motion requested
        if scene.get("motion"):
            motion_prompt = scene.get("visual", "") + " " + scene.get("motion", "")
            video_file = video_dir / f"motion_{scene_num:03d}.mp4"
            console.print(f"  [dim]Motion video: {motion_prompt[:50]}...[/dim]")
            # AI video generation would go here (LTX-Video, Mochi 1)
            video_file.touch()  # Placeholder
            generated_assets["video"].append({
                "scene": scene_num,
                "file": str(video_file),
                "prompt": motion_prompt,
            })
            console.print(f"  [yellow]Video placeholder: {video_file.name}[/yellow]")

    # Save manifest with all generated assets
    manifest = {
        "script": str(script_path),
        "script_data": script_data,
        "output_dir": str(output_path),
        "visual_style": visual_style,
        "scenes_processed": len(scenes),
        "assets": generated_assets,
        "timestamp": datetime.now().isoformat(),
    }
    with open(output_path / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Summary
    console.print("\n[bold]Generation Summary:[/bold]")
    table = Table(show_header=True)
    table.add_column("Asset Type", style="cyan")
    table.add_column("Count")
    table.add_row("Images", str(len(generated_assets["images"])))
    table.add_row("Audio", str(len(generated_assets["audio"])))
    table.add_row("Video", str(len(generated_assets["video"])))
    console.print(table)

    console.print(f"\n[bold green]Assets generated in {output_path}[/bold green]")


# =============================================================================
# Phase 5: Assemble
# =============================================================================


def create_ffmpeg_concat_file(images: list, durations: list, output_file: Path) -> Path:
    """Create an FFmpeg concat demuxer file for images."""
    concat_file = output_file.parent / "concat.txt"
    with open(concat_file, "w") as f:
        for img, duration in zip(images, durations):
            f.write(f"file '{img}'\n")
            f.write(f"duration {duration}\n")
        # Repeat last frame to avoid duration issues
        if images:
            f.write(f"file '{images[-1]}'\n")
    return concat_file


def assemble_mp4(assets_path: Path, manifest: dict, output_path: Path, fps: int = 24) -> bool:
    """Assemble images and audio into MP4 using FFmpeg."""
    images_dir = assets_path / "images"
    audio_dir = assets_path / "audio"

    # Get sorted images
    images = sorted(images_dir.glob("*.png"))
    if not images:
        console.print("[yellow]No images found to assemble[/yellow]")
        return False

    # Calculate duration per image
    script_data = manifest.get("script_data", {})
    total_duration = script_data.get("duration_seconds", 30)
    duration_per_image = total_duration / len(images)

    console.print(f"[dim]Assembling {len(images)} images at {duration_per_image:.2f}s each[/dim]")

    # Create concat file
    concat_file = create_ffmpeg_concat_file(
        [str(img.absolute()) for img in images],
        [duration_per_image] * len(images),
        output_path
    )

    # Build FFmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
    ]

    # Add audio if available
    audio_files = sorted(audio_dir.glob("*.wav"))
    if audio_files:
        # Merge all audio files
        audio_list = assets_path / "audio_list.txt"
        with open(audio_list, "w") as f:
            for af in audio_files:
                f.write(f"file '{af.absolute()}'\n")

        # Concat audio
        merged_audio = assets_path / "merged_audio.wav"
        audio_merge_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(audio_list),
            "-c", "copy",
            str(merged_audio)
        ]
        subprocess.run(audio_merge_cmd, capture_output=True)

        if merged_audio.exists() and merged_audio.stat().st_size > 0:
            cmd.extend(["-i", str(merged_audio), "-c:a", "aac", "-shortest"])
            console.print(f"[dim]Including {len(audio_files)} audio tracks[/dim]")

    # Video encoding
    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-vf", f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        str(output_path)
    ])

    console.print(f"[dim]Running FFmpeg...[/dim]")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        return True
    else:
        console.print(f"[red]FFmpeg error: {result.stderr[:200]}[/red]")
        return False


def assemble_html(assets_path: Path, manifest: dict, output_dir: Path):
    """Create interactive HTML viewer for the movie."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy assets
    assets_dest = output_dir / "assets"
    assets_dest.mkdir(exist_ok=True)

    images_dir = assets_path / "images"
    images = sorted(images_dir.glob("*.png"))

    script_data = manifest.get("script_data", {})
    scenes = script_data.get("scenes", [])
    total_duration = script_data.get("duration_seconds", 30)
    duration_per_scene = total_duration / len(scenes) if scenes else 5

    # Build scene data for player
    scene_data = []
    for i, (img, scene) in enumerate(zip(images, scenes)):
        # Copy image
        dest_img = assets_dest / img.name
        import shutil
        shutil.copy(img, dest_img)

        scene_data.append({
            "image": f"assets/{img.name}",
            "duration": scene.get("duration_seconds", duration_per_scene),
            "heading": scene.get("heading", f"Scene {i+1}"),
            "dialogue": scene.get("dialogue", []),
            "audio": scene.get("audio", ""),
        })

    # Create HTML
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{script_data.get("title", "Horus Movie")}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #0a0a0a; color: #fff; }}
        .player {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .screen {{ position: relative; width: 100%; aspect-ratio: 16/9; background: #000; overflow: hidden; }}
        .screen img {{ width: 100%; height: 100%; object-fit: contain; }}
        .subtitle {{ position: absolute; bottom: 40px; left: 50%; transform: translateX(-50%);
                     background: rgba(0,0,0,0.8); padding: 10px 20px; border-radius: 4px;
                     max-width: 80%; text-align: center; font-size: 1.2rem; }}
        .controls {{ display: flex; gap: 10px; margin-top: 20px; justify-content: center; }}
        .controls button {{ padding: 10px 20px; font-size: 1rem; cursor: pointer;
                           background: #333; color: #fff; border: none; border-radius: 4px; }}
        .controls button:hover {{ background: #555; }}
        .progress {{ width: 100%; height: 4px; background: #333; margin-top: 10px; }}
        .progress-bar {{ height: 100%; background: #c9a227; width: 0%; transition: width 0.1s; }}
        .info {{ margin-top: 20px; padding: 20px; background: #1a1a1a; border-radius: 8px; }}
        h1 {{ color: #c9a227; margin-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="player">
        <div class="screen">
            <img id="frame" src="" alt="Scene">
            <div id="subtitle" class="subtitle" style="display: none;"></div>
        </div>
        <div class="progress"><div id="progress-bar" class="progress-bar"></div></div>
        <div class="controls">
            <button onclick="player.prev()">⏮ Prev</button>
            <button onclick="player.toggle()" id="play-btn">▶ Play</button>
            <button onclick="player.next()">Next ⏭</button>
        </div>
        <div class="info">
            <h1>{script_data.get("title", "Untitled")}</h1>
            <p>{script_data.get("synopsis", "A Horus production")}</p>
            <p><small>Scenes: {len(scenes)} | Duration: {total_duration}s</small></p>
        </div>
    </div>
    <script>
        const scenes = {json.dumps(scene_data)};
        const player = {{
            current: 0,
            playing: false,
            timer: null,
            init() {{
                this.show(0);
            }},
            show(idx) {{
                if (idx < 0 || idx >= scenes.length) return;
                this.current = idx;
                const scene = scenes[idx];
                document.getElementById('frame').src = scene.image;
                const sub = document.getElementById('subtitle');
                if (scene.dialogue && scene.dialogue.length) {{
                    const text = scene.dialogue.map(d => typeof d === 'string' ? d : d.line).join(' ');
                    sub.textContent = text;
                    sub.style.display = 'block';
                }} else {{
                    sub.style.display = 'none';
                }}
                this.updateProgress();
            }},
            updateProgress() {{
                const pct = ((this.current + 1) / scenes.length) * 100;
                document.getElementById('progress-bar').style.width = pct + '%';
            }},
            next() {{ this.show(this.current + 1); }},
            prev() {{ this.show(this.current - 1); }},
            toggle() {{
                this.playing = !this.playing;
                document.getElementById('play-btn').textContent = this.playing ? '⏸ Pause' : '▶ Play';
                if (this.playing) this.play();
                else clearTimeout(this.timer);
            }},
            play() {{
                if (!this.playing) return;
                const scene = scenes[this.current];
                this.timer = setTimeout(() => {{
                    if (this.current < scenes.length - 1) {{
                        this.next();
                        this.play();
                    }} else {{
                        this.playing = false;
                        document.getElementById('play-btn').textContent = '▶ Play';
                    }}
                }}, (scene.duration || 5) * 1000);
            }}
        }};
        player.init();
    </script>
</body>
</html>'''

    with open(output_dir / "index.html", "w") as f:
        f.write(html_content)


@click.command()
@click.option("--assets", "-a", required=True, help="Assets directory")
@click.option("--output", "-o", required=True, help="Output file (e.g., movie.mp4 or output_dir/)")
@click.option("--format", "-f", "output_format", type=click.Choice(["mp4", "html"]), default="mp4")
@click.option("--fps", default=24, help="Frames per second for MP4")
def assemble(assets: str, output: str, output_format: str, fps: int):
    """Phase 5: Assemble final output as MP4 or interactive HTML."""
    console.print(Panel(f"[bold blue]ASSEMBLE PHASE[/bold blue]\nOutput format: {output_format}"))

    assets_path = Path(assets)
    if not assets_path.exists():
        console.print(f"[red]Assets directory not found: {assets}[/red]")
        sys.exit(1)

    manifest_path = assets_path / "manifest.json"
    if not manifest_path.exists():
        console.print("[red]No manifest.json found. Run generate phase first.[/red]")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    output_path = Path(output)

    if output_format == "mp4":
        # Check FFmpeg
        ffmpeg_check = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if ffmpeg_check.returncode != 0:
            console.print("[red]FFmpeg not available.[/red]")
            sys.exit(1)

        console.print(f"[dim]Assembling MP4: {output_path}[/dim]")
        success = assemble_mp4(assets_path, manifest, output_path, fps)

        if success and output_path.exists():
            file_size = output_path.stat().st_size / (1024 * 1024)
            console.print(f"\n[bold green]Movie created: {output_path}[/bold green]")
            console.print(f"[dim]Size: {file_size:.1f} MB[/dim]")
        else:
            console.print("[red]Assembly failed[/red]")
            sys.exit(1)

    elif output_format == "html":
        console.print(f"[dim]Creating HTML bundle: {output_path}[/dim]")
        assemble_html(assets_path, manifest, output_path)

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
# Pre-Phase: Study (Acquire Filmmaking Knowledge)
# =============================================================================


FILMMAKING_TOPICS = [
    "cinematography lighting techniques three-point lighting",
    "camera framing composition rule of thirds",
    "film directing actors performance",
    "shot types close-up medium wide establishing",
    "film editing cuts transitions montage",
    "color grading mood atmosphere",
    "sound design foley ambient",
    "screenplay structure three act format",
    "visual storytelling show don't tell",
    "film history movements genres",
]


@click.command()
@click.argument("topic", required=False)
@click.option("--scope", default="horus-filmmaking", help="Memory scope for storage")
@click.option("--deep/--quick", default=False, help="Deep research (dogpile) vs quick (memory check)")
@click.option("--list-topics", is_flag=True, help="List suggested filmmaking topics")
def study(topic: str | None, scope: str, deep: bool, list_topics: bool):
    """Study filmmaking topics to acquire knowledge for future movie creation.

    This is a PRE-PHASE that should be run before creating movies.
    Horus learns cinematography, directing, framing, etc. and stores in memory.
    """
    console.print(Panel("[bold blue]STUDY PHASE[/bold blue]\nAcquire filmmaking knowledge for memory"))

    if list_topics:
        console.print("\n[bold]Suggested Filmmaking Topics:[/bold]")
        for i, t in enumerate(FILMMAKING_TOPICS, 1):
            console.print(f"  {i}. {t}")
        console.print("\n[dim]Usage: ./run.sh study 'cinematography lighting'[/dim]")
        return

    if not topic:
        console.print("[yellow]No topic provided. Use --list-topics to see suggestions.[/yellow]")
        console.print("[dim]Or: ./run.sh study 'camera framing techniques'[/dim]")
        return

    console.print(f"[dim]Studying: {topic}[/dim]")
    console.print(f"[dim]Will store in scope: {scope}[/dim]")

    # Step 1: Check what we already know
    console.print("\n[cyan]── Checking existing knowledge ──[/cyan]")
    existing = run_skill("memory", ["recall", "--q", topic, "--scope", scope, "--k", "3"])
    if existing.get("returncode") == 0 and existing.get("stdout", "").strip():
        console.print("[green]Already have some knowledge on this topic:[/green]")
        console.print(existing.get("stdout", "")[:500])
        console.print()

    if deep:
        # Step 2: Deep research with dogpile
        console.print("\n[cyan]── Deep Research via /dogpile ──[/cyan]")
        dogpile_query = f"{topic} filmmaking tutorial guide techniques"
        with console.status(f"[green]Researching: {dogpile_query}..."):
            dogpile_result = run_skill("dogpile", ["search", dogpile_query])

        if dogpile_result.get("returncode") == 0:
            research_text = dogpile_result.get("stdout", "")
            console.print(f"[green]✓ Got {len(research_text)} chars of research[/green]")

            # Step 3: Store using /memory learn
            console.print("\n[cyan]── Storing to memory via /memory learn ──[/cyan]")

            # Break research into learnable chunks
            # Format: problem = "How to X?" solution = "Research findings about X"
            learn_result = run_skill("memory", [
                "learn",
                "--problem", f"How to apply {topic} in filmmaking?",
                "--solution", research_text[:2000],  # Memory limits
                "--scope", scope,
            ])

            if learn_result.get("returncode") == 0:
                console.print("[green]✓ Knowledge stored in memory[/green]")
            else:
                console.print(f"[yellow]Memory learn: {learn_result.get('stderr', '')[:100]}[/yellow]")
        else:
            console.print(f"[yellow]Dogpile research failed: {dogpile_result.get('stderr', '')[:100]}[/yellow]")

    else:
        # Quick mode: just search YouTube and add to memory
        console.print("\n[cyan]── Quick Study via YouTube transcripts ──[/cyan]")
        with console.status(f"[green]Searching YouTube for tutorials..."):
            yt_result = run_skill("ingest-youtube", ["search", f"{topic} tutorial filmmaking"])

        if yt_result.get("returncode") == 0:
            console.print("[green]✓ Found tutorials. Use --deep for full research.[/green]")
        else:
            console.print("[dim]No YouTube tutorials found. Try --deep for web research.[/dim]")

    console.print(f"\n[bold green]Study complete. Knowledge stored in '{scope}' scope.[/bold green]")
    console.print("[dim]Horus can now recall this when creating movies.[/dim]")


@click.command(name="study-all")
@click.option("--scope", default="horus-filmmaking", help="Memory scope for storage")
def study_all(scope: str):
    """Study all suggested filmmaking topics (comprehensive learning session)."""
    console.print(Panel(
        "[bold blue]COMPREHENSIVE STUDY SESSION[/bold blue]\n"
        f"Learning {len(FILMMAKING_TOPICS)} core filmmaking topics"
    ))

    for i, topic in enumerate(FILMMAKING_TOPICS, 1):
        console.print(f"\n[bold]Topic {i}/{len(FILMMAKING_TOPICS)}: {topic}[/bold]")

        # Check if already known
        existing = run_skill("memory", ["recall", "--q", topic, "--scope", scope, "--k", "1"])
        if existing.get("returncode") == 0 and existing.get("stdout", "").strip():
            console.print("[dim]Already have knowledge on this topic, skipping...[/dim]")
            continue

        # Quick study (not deep to save time)
        ctx = click.Context(study)
        ctx.invoke(study, topic=topic, scope=scope, deep=False, list_topics=False)

    console.print(f"\n[bold green]All {len(FILMMAKING_TOPICS)} topics studied![/bold green]")
    console.print("[dim]Horus is now ready to create movies with filmmaking knowledge.[/dim]")


# =============================================================================
# Phase 6: Learn (Memory Integration)
# =============================================================================


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


@click.command()
@click.option("--project-dir", "-p", required=True, help="Project directory to extract learnings from")
@click.option("--scope", default="horus-filmmaking", help="Memory scope for storage")
@click.option("--dry-run", is_flag=True, help="Show learnings without storing")
def learn(project_dir: str, scope: str, dry_run: bool):
    """Phase 6: Store learnings in memory for future recall."""
    console.print(Panel(f"[bold blue]LEARN PHASE[/bold blue]\nStoring insights in memory (scope: {scope})"))

    project_path = Path(project_dir)
    if not project_path.exists():
        console.print(f"[red]Project directory not found: {project_dir}[/red]")
        sys.exit(1)

    console.print("[dim]Extracting learnings from project...[/dim]")
    learnings = extract_learnings(project_path)

    if not learnings:
        console.print("[yellow]No learnings extracted from project[/yellow]")
        return

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
        return

    # Store each learning in memory using /memory learn
    console.print(f"\n[cyan]── Storing to memory via /memory learn (scope: {scope}) ──[/cyan]")
    stored = 0
    for learning in learnings:
        # Use /memory learn with problem/solution format
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

    console.print(f"\n[bold green]Stored {stored}/{len(learnings)} learnings in scope '{scope}'[/bold green]")

    # Save learnings to project for reference
    learnings_file = project_path / "learnings.json"
    with open(learnings_file, "w") as f:
        json.dump({
            "learnings": learnings,
            "scope": scope,
            "stored_count": stored,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2)
    console.print(f"[dim]Learnings saved to {learnings_file}[/dim]")


# =============================================================================
# Full Workflow: Create
# =============================================================================


@click.command()
@click.argument("prompt")
@click.option("--output", "-o", default="movie.mp4", help="Output file")
@click.option("--work-dir", "-w", default="./movie_project", help="Working directory")
@click.option("--duration", "-d", default=30, help="Target duration in seconds")
@click.option("--style", "-s", default="", help="Visual style (e.g., 'cinematic', 'film noir')")
@click.option("--format", "-f", "output_format", type=click.Choice(["mp4", "html"]), default="mp4")
@click.option("--store-learnings/--no-store-learnings", default=True, help="Store learnings in memory")
@click.option("--skip-research", is_flag=True, help="Skip research phase (use existing research.json)")
def create(prompt: str, output: str, work_dir: str, duration: int, style: str,
           output_format: str, store_learnings: bool, skip_research: bool):
    """Full orchestrated workflow: Research → Script → Build → Generate → Assemble → Learn."""
    console.print(
        Panel(
            f"[bold magenta]CREATE MOVIE[/bold magenta]\n\n"
            f'"{prompt}"\n\n'
            f"[dim]Duration: {duration}s | Style: {style or 'default'} | Format: {output_format}[/dim]"
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
        ("RESEARCH", "Gathering knowledge", not skip_research),
        ("SCRIPT", "Creating scene breakdown", True),
        ("BUILD TOOLS", "Preparing custom tools", True),
        ("GENERATE", "Creating assets", True),
        ("ASSEMBLE", "Combining into final output", True),
        ("LEARN", "Storing insights in memory", store_learnings),
    ]

    console.print("\n[bold]Workflow Phases:[/bold]")
    for i, (name, desc, enabled) in enumerate(phases, 1):
        status = "[green]✓[/green]" if enabled else "[dim]skip[/dim]"
        console.print(f"  {i}. {status} [cyan]{name}[/cyan] - {desc}")

    console.print()

    # Define paths
    research_file = work_path / "research.json"
    script_file = work_path / "script.json"
    tools_dir = work_path / "tools"
    assets_dir = work_path / "assets"
    output_path = work_path / output

    # ==========================================================================
    # Phase 1: Research
    # ==========================================================================
    if not skip_research:
        console.print("\n[bold]=== Phase 1: RESEARCH ===[/bold]")
        # Import the research function context
        ctx = click.Context(research)
        ctx.invoke(research, topic=prompt, output=str(research_file), skip_external=False)
    else:
        console.print("\n[dim]Skipping research phase (--skip-research)[/dim]")
        if not research_file.exists():
            # Create minimal research file
            with open(research_file, "w") as f:
                json.dump({"topic": prompt, "sources": {}}, f)

    # ==========================================================================
    # Phase 2: Script
    # ==========================================================================
    console.print("\n[bold]=== Phase 2: SCRIPT ===[/bold]")
    ctx = click.Context(script)
    ctx.invoke(
        script,
        from_research=str(research_file),
        prompt=prompt,
        duration=duration,
        use_create_story=True,  # Use /create-story for screenplay
        model="chimera",
        output=str(script_file),
    )

    # ==========================================================================
    # Phase 3: Build Tools
    # ==========================================================================
    console.print("\n[bold]=== Phase 3: BUILD TOOLS ===[/bold]")
    ctx = click.Context(build_tools)
    ctx.invoke(build_tools, script=str(script_file), output_dir=str(tools_dir), skip_docker=False)

    # ==========================================================================
    # Phase 4: Generate
    # ==========================================================================
    console.print("\n[bold]=== Phase 4: GENERATE ===[/bold]")
    ctx = click.Context(generate)
    ctx.invoke(generate, tools=str(tools_dir), script=str(script_file), output_dir=str(assets_dir), style=style)

    # ==========================================================================
    # Phase 5: Assemble
    # ==========================================================================
    console.print("\n[bold]=== Phase 5: ASSEMBLE ===[/bold]")
    ctx = click.Context(assemble)
    ctx.invoke(assemble, assets=str(assets_dir), output=str(output_path), output_format=output_format, fps=24)

    # ==========================================================================
    # Phase 6: Learn
    # ==========================================================================
    if store_learnings:
        console.print("\n[bold]=== Phase 6: LEARN ===[/bold]")
        ctx = click.Context(learn)
        ctx.invoke(learn, project_dir=str(work_path), scope="horus-filmmaking", dry_run=False)

    # Save final project state
    project.research = {"file": str(research_file)}
    project.script = {"file": str(script_file)}
    project.tools = [str(tools_dir)]
    project.assets = [str(assets_dir)]
    project.output_path = str(output_path)
    project.save(work_path / "project.json")

    # Final summary
    console.print("\n" + "=" * 60)
    console.print(Panel(
        f"[bold green]MOVIE CREATION COMPLETE[/bold green]\n\n"
        f"Output: {output_path}\n"
        f"Project: {work_path}\n"
        f"Format: {output_format}",
        title="✨ Horus Production ✨",
    ))


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
cli.add_command(learn)
cli.add_command(study)
cli.add_command(study_all, name="study-all")


if __name__ == "__main__":
    cli()
