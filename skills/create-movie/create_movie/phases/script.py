"""
Phase 2: Script

Generate script from research with scene breakdown.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console
from rich.table import Table

from ..skill_registry import run_skill, SKILL_DIR

console = Console()

# Persona integration
try:
    from persona_integration import (
        enrich_screenplay_context,
    )
    PERSONA_AVAILABLE = True
except ImportError:
    PERSONA_AVAILABLE = False
    enrich_screenplay_context = None


def load_preset(preset_name: str) -> dict:
    """Load an equipment preset from the config directory."""
    presets_dir = SKILL_DIR / "config" / "presets"
    search_names = [f"PRESET_{preset_name.upper()}.yaml", f"{preset_name}.yaml", f"{preset_name.upper()}.yaml"]

    for name in search_names:
        preset_path = presets_dir / name
        if preset_path.exists():
            with open(preset_path) as f:
                return yaml.safe_load(f)

    # Search for versioned files (e.g., PRESET_NEUTRAL_V1.yaml)
    if presets_dir.exists():
        for pattern in [f"PRESET_{preset_name.upper()}_V*.yaml", f"{preset_name.upper()}_V*.yaml"]:
            matches = sorted(presets_dir.glob(pattern))
            if matches:
                with open(matches[-1]) as f:  # Latest version
                    return yaml.safe_load(f)

    console.print(f"[yellow]Warning: Preset '{preset_name}' not found in {presets_dir}[/yellow]")
    return {}


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


def generate_script(
    research_path: Path,
    prompt: Optional[str] = None,
    duration: int = 30,
    use_create_story: bool = True,
    model: str = "chimera",
    output_path: Optional[Path] = None,
    mode: str = "standard",
    preset: Optional[str] = None,
) -> dict:
    """
    Generate script from research with scene breakdown.

    Args:
        research_path: Path to research JSON file
        prompt: Movie concept/prompt (overrides research topic)
        duration: Target duration in seconds
        use_create_story: Use /create-story to generate screenplay
        model: LLM model for screenplay generation
        output_path: Path to save script JSON
        mode: Narrative mode (standard or dream)
        preset: Cinematic preset/persona ID

    Returns:
        dict with script data
    """
    # Load research
    if not research_path.exists():
        console.print(f"[red]Research file not found: {research_path}[/red]")
        sys.exit(1)

    with open(research_path) as f:
        research_data = json.load(f)

    # Get prompt from research or override
    movie_prompt = prompt or research_data.get("topic", "A short film")
    console.print(f"[dim]Creating screenplay for: {movie_prompt} (Mode: {mode})[/dim]")

    # Persona Integration: Enrich with Horus context
    persona_context = None
    bridges_detected = []
    if PERSONA_AVAILABLE and enrich_screenplay_context:
        with console.status("[cyan]Retrieving persona context..."):
            try:
                persona_context = enrich_screenplay_context(movie_prompt)
                bridges_detected = persona_context.bridge_attributes
                if bridges_detected:
                    console.print(f"[cyan]  Thematic bridges: {', '.join(bridges_detected)}[/cyan]")
                if persona_context.federated:
                    console.print(f"[dim]  Found {len(persona_context.federated)} lore connections[/dim]")
            except Exception as e:
                console.print(f"[dim]Persona context unavailable: {e}[/dim]")

    # Resolve Preset (Persona/Style)
    preset_id = preset or "neutral"
    console.print(f"\n[cyan]── Cinematic Style: {preset_id} ──[/cyan]")

    # Load Equipment Preset (YAML)
    eq_preset = load_preset(preset_id)
    preset_prompts = []
    preset_data = {}

    if eq_preset:
        preset_prompts = eq_preset.get("veo", {}).get("prompt_phrases", [])
        preset_data = eq_preset
        console.print(f"  [green]✓ Loaded Equipment Preset: {preset_id}[/green]")
    else:
        # Fallback to Memory-based Preset (ArangoDB)
        with console.status(f"[green]Compiling memory preset {preset_id}..."):
            preset_payload = json.dumps({"set": preset_id})
            preset_result = run_skill("memory", ["preset", "compile", "--ids", preset_payload, "--strict"])

            if preset_result.get("returncode") == 0:
                try:
                    raw_stdout = preset_result.get("stdout", "")
                    json_start = raw_stdout.find("{")
                    if json_start != -1:
                        preset_data = json.loads(raw_stdout[json_start:])
                        console.print(f"  [green]✓ Resolved: {len(preset_data.get('params', {}))} technical parameters[/green]")
                except json.JSONDecodeError:
                    pass

    # Script structure
    script_data = {
        "title": movie_prompt[:50],
        "synopsis": "",
        "duration_seconds": duration,
        "scenes": [],
        "visual_style": ", ".join(preset_prompts),
        "audio_style": "",
        "screenplay_raw": "",
        "research_context": research_data,
        "preset_data": preset_data,
        "preset_id": preset_id,
        "timestamp": datetime.now().isoformat(),
        "bridge_attributes": bridges_detected,
        "persona_context": persona_context.to_dict() if persona_context else None,
    }

    if use_create_story:
        # Use /create-story to generate screenplay
        console.print("\n[cyan]── Generating Screenplay via /create-story ──[/cyan]")

        # Build persona-enriched prompt
        persona_section = ""
        if persona_context and (persona_context.federated or bridges_detected):
            persona_section = f"""
Thematic Guidance (Horus Persona):
{persona_context.render() if persona_context else ''}

Thematic Bridges to emphasize: {', '.join(bridges_detected) if bridges_detected else 'None specified'}
"""

        screenplay_prompt = f"""A {duration}-second short film: {movie_prompt}
{persona_section}
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
                "--mode", mode,
                "--iterations", "1",
                "--output", str((output_path.parent / "screenplay_project") if output_path else Path("screenplay_project")),
            ])

            if story_result.get("returncode") == 0:
                screenplay_dir = (output_path.parent / "screenplay_project") if output_path else Path("screenplay_project")
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

    # If no scenes generated, create scenes from prompt
    if not script_data["scenes"]:
        console.print("\n[bold]Creating scenes from prompt...[/bold]")

        num_scenes = max(3, duration // 7)
        shot_types = ["WIDE", "MEDIUM", "CLOSE-UP"]

        # Build scene descriptions from the user's prompt
        # Each scene gets a cinematic variation with appropriate framing
        scene_framings = {
            "WIDE": "wide establishing shot",
            "MEDIUM": "medium shot",
            "CLOSE-UP": "extreme close-up, detailed",
        }

        for i in range(num_scenes):
            shot_type = shot_types[i % len(shot_types)]
            framing = scene_framings[shot_type]
            visual = f"{movie_prompt}, {framing}, cinematic"

            script_data["scenes"].append({
                "heading": f"INT. SCENE {i+1} - DAY",
                "location": f"Scene {i+1}",
                "time": "DAY",
                "action": [movie_prompt],
                "dialogue": [],
                "visual": visual,
                "audio": "ambient atmosphere",
                "shot_type": shot_type,
                "duration_seconds": duration // num_scenes,
            })

        console.print(f"[dim]Created {num_scenes} scenes from prompt[/dim]")

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

    # Inject technical specs into scenes
    tech_params = script_data.get("preset_data", {}).get("params", {})
    preset_prompts = script_data.get("preset_data", {}).get("veo", {}).get("prompt_phrases", [])

    if tech_params or preset_prompts:
        console.print(f"\n[cyan]Applying {preset_id} style to {len(script_data['scenes'])} scenes...[/cyan]")
        for scene in script_data["scenes"]:
            if preset_prompts:
                current_visual = scene.get("visual", "")
                scene["visual"] = f"{current_visual}, {' '.join(preset_prompts)}"
            if tech_params:
                for k, v in tech_params.items():
                    if k not in scene:
                        scene[k] = v

    # Save script
    if output_path:
        with open(output_path, "w") as f:
            json.dump(script_data, f, indent=2)
        console.print(f"\n[bold green]Script saved to {output_path}[/bold green]")
        if not use_create_story:
            console.print("[dim]Edit the scenes to customize, then run build-tools phase.[/dim]")

    return script_data
