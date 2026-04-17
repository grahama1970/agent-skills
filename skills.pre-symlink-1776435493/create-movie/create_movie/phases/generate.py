"""
Phase 4: Generate Assets

Generate visual/audio assets for each scene.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from ..skill_registry import run_skill, PI_SKILLS_DIR

console = Console()

# Persona integration
try:
    from persona_integration import augment_prompt_with_bridges
    PERSONA_AVAILABLE = True
except ImportError:
    PERSONA_AVAILABLE = False
    augment_prompt_with_bridges = None

# create-score integration
try:
    sys.path.append(str(PI_SKILLS_DIR / "create-score"))
    from create_score import generate_scene_score, is_service_available as score_service_available
    CREATE_SCORE_AVAILABLE = True
except ImportError:
    CREATE_SCORE_AVAILABLE = False
    generate_scene_score = None
    score_service_available = None


def load_identity_packs(characters_path: Path) -> dict:
    """Load character identity packs from characters directory."""
    identity_packs = {}
    if characters_path.exists():
        for char_dir in characters_path.iterdir():
            if char_dir.is_dir() and (char_dir / "identity_pack").exists():
                char_name = char_dir.name
                pack_dir = char_dir / "identity_pack"
                identity_packs[char_name] = {
                    "front": pack_dir / "front.png" if (pack_dir / "front.png").exists() else None,
                    "three_quarter": pack_dir / "three_quarter.png" if (pack_dir / "three_quarter.png").exists() else None,
                    "full_body": pack_dir / "full_body.png" if (pack_dir / "full_body.png").exists() else None,
                }
    return identity_packs


def generate_assets(
    script_path: Path,
    output_dir: Path,
    tools_dir: Optional[Path] = None,
    style: str = "",
    model: str = "ltx2-fp8",
    resolution: str = "720p",
    max_clip_seconds: int = 10,
    audio_enabled: bool = True,
    hardware_profile_path: Optional[Path] = None,
    renderer: str = "none",
    characters_path: Optional[Path] = None,
) -> dict:
    """
    Generate visual/audio assets for each scene.

    Args:
        script_path: Path to script JSON file
        output_dir: Output directory for assets
        tools_dir: Tools directory
        style: Visual style to apply
        model: Video model variant
        resolution: Output resolution
        max_clip_seconds: Maximum clip length
        audio_enabled: Enable audio generation
        hardware_profile_path: Path to hardware_profile.json
        renderer: Video generation backend (veo or none)
        characters_path: Path to characters directory with identity packs

    Returns:
        dict with generated assets manifest
    """
    # Load hardware profile if provided
    hw_settings = {
        "model_variant": model,
        "resolution": resolution,
        "max_clip_seconds": max_clip_seconds,
        "audio_enabled": audio_enabled,
    }

    if hardware_profile_path and hardware_profile_path.exists():
        with open(hardware_profile_path) as f:
            hw_settings.update(json.load(f))
        console.print(f"[dim]Using hardware profile: {hw_settings['model_variant']}, {hw_settings['resolution']}[/dim]")

    if not script_path.exists():
        console.print(f"[red]Script file not found: {script_path}[/red]")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    images_dir = output_dir / "images"
    video_dir = output_dir / "video"
    audio_dir = output_dir / "audio"
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

    # Persona: Load bridge attributes for prompt augmentation
    script_bridges = script_data.get("bridge_attributes", [])
    if script_bridges and PERSONA_AVAILABLE:
        console.print(f"[cyan]Thematic bridges: {', '.join(script_bridges)}[/cyan]")

    # Load character identity packs if available
    identity_packs = {}
    if characters_path and characters_path.exists():
        console.print(f"[dim]Loading character identity packs from {characters_path}[/dim]")
        identity_packs = load_identity_packs(characters_path)
        if identity_packs:
            console.print(f"[cyan]Loaded identity packs for: {', '.join(identity_packs.keys())}[/cyan]")

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

            # Persona: Augment with bridge-specific visual cues
            if script_bridges and PERSONA_AVAILABLE and augment_prompt_with_bridges:
                visual_prompt = augment_prompt_with_bridges(visual_prompt, script_bridges)

            image_file = images_dir / f"scene_{scene_num:03d}.png"
            console.print(f"  [dim]Generating image: {visual_prompt[:50]}...[/dim]")

            image_result = run_skill(
                "create-image",
                ["generate", visual_prompt, "--output", str(image_file)],
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
                all_dialogue = " ".join(
                    d.get("line", d) if isinstance(d, dict) else str(d)
                    for d in dialogue_lines
                )
            else:
                all_dialogue = str(dialogue_lines)

            if all_dialogue.strip():
                audio_file = audio_dir / f"dialogue_{scene_num:03d}.wav"
                console.print(f"  [dim]Generating TTS: {all_dialogue[:50]}...[/dim]")

                tts_success = False

                # Persona: Try persona TTS first
                if PERSONA_AVAILABLE:
                    try:
                        from persona_integration import generate_narration
                        result_path = generate_narration(all_dialogue, audio_file)
                        if result_path and result_path.exists():
                            tts_success = True
                            console.print(f"  [green]✓ Audio (Persona): {audio_file.name}[/green]")
                    except Exception as e:
                        console.print(f"  [dim]Persona TTS unavailable: {e}[/dim]")

                # Fallback: Try tts-train skill
                if not tts_success:
                    tts_result = run_skill(
                        "tts-train",
                        ["synthesize", "--text", all_dialogue, "--output", str(audio_file)],
                    )
                    if tts_result.get("returncode") == 0:
                        tts_success = True
                        console.print(f"  [green]✓ Audio: {audio_file.name}[/green]")

                if tts_success:
                    generated_assets["audio"].append({
                        "scene": scene_num,
                        "file": str(audio_file),
                        "type": "dialogue",
                        "text": all_dialogue,
                    })
                else:
                    audio_file.touch()
                    console.print(f"  [yellow]TTS unavailable, placeholder created[/yellow]")

        # 3. Generate audio cue/music via create-score
        if scene.get("audio"):
            audio_cue = scene["audio"]
            cue_file = audio_dir / f"score_{scene_num:03d}.wav"
            console.print(f"  [dim]Generating score: {audio_cue[:50]}...[/dim]")

            scene_duration = script_data.get("duration_seconds", 30) / max(len(scenes), 1)
            scene_duration = min(max(scene_duration, 4), 30)

            # Extract bridge attributes from scene context
            scene_bridges = []
            visual = scene.get("visual", "").lower()
            if any(word in visual for word in ["battle", "fight", "war", "heroic"]):
                scene_bridges.append("Resilience")
            if any(word in visual for word in ["precise", "technical", "calculated"]):
                scene_bridges.append("Precision")
            if any(word in visual for word in ["dark", "corrupt", "sinister"]):
                scene_bridges.append("Corruption")
            if any(word in visual for word in ["delicate", "fragile", "tender"]):
                scene_bridges.append("Fragility")

            score_generated = False
            if CREATE_SCORE_AVAILABLE:
                try:
                    if score_service_available and score_service_available():
                        result = generate_scene_score(
                            prompt=audio_cue,
                            duration_s=scene_duration,
                            output_path=cue_file,
                            bridges=scene_bridges[:2] if scene_bridges else None,
                            episode=script_data.get("title", "movie"),
                            store_memory=True,
                        )
                        if result and result.output_path.exists():
                            score_generated = True
                            console.print(f"  [green]✓ Score: {cue_file.name} (bridges: {result.hmt.bridge_attributes})[/green]")
                    else:
                        console.print(f"  [yellow]create-score service not running, using placeholder[/yellow]")
                except Exception as e:
                    console.print(f"  [yellow]Score generation failed: {e}[/yellow]")
            else:
                score_result = run_skill(
                    "create-score",
                    ["generate", "--prompt", audio_cue, "--duration-s", str(int(scene_duration)), "--out", str(cue_file)],
                )
                if score_result.get("returncode") == 0 and cue_file.exists():
                    score_generated = True
                    console.print(f"  [green]✓ Score: {cue_file.name}[/green]")

            if not score_generated:
                cue_file.touch()
                console.print(f"  [yellow]Score placeholder: {cue_file.name}[/yellow]")

            generated_assets["audio"].append({
                "scene": scene_num,
                "file": str(cue_file),
                "type": "score",
                "description": audio_cue,
                "bridges": scene_bridges,
                "generated": score_generated,
            })

        # 4. Generate video clip if motion requested
        if scene.get("motion"):
            motion_prompt = scene.get("visual", "") + " " + scene.get("motion", "")
            video_file = video_dir / f"motion_{scene_num:03d}.mp4"
            console.print(f"  [dim]Motion video: {motion_prompt[:50]}...[/dim]")
            raise NotImplementedError(f"Video generation not yet implemented for motion prompt: {motion_prompt[:80]}")
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
        "output_dir": str(output_dir),
        "visual_style": visual_style,
        "scenes_processed": len(scenes),
        "assets": generated_assets,
        "timestamp": datetime.now().isoformat(),
    }
    with open(output_dir / "manifest.json", "w") as f:
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

    console.print(f"\n[bold green]Assets generated in {output_dir}[/bold green]")

    return manifest
