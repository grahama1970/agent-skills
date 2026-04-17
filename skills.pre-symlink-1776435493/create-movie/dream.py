"""
Dream Movie Orchestrator (Phase 3)

Coordinates the detailed generation of surreal dream sequences from day residue.
Uses the skill_registry to fetch memories from persona scopes.
Parameterized by persona — any registered persona can dream.

Pipeline:
  1. Fetch Day Residue (with contradiction detection)
  2. Generate Dream Scenes (DreamPrompter)
  3. Dream Casting (create-cast) — optional
  4. Dream Storyboard (create-storyboard) — optional
  5. Generate Global Score (create-score)
  6. Sound Design (create-sound-design) — optional, replaces ad-hoc SFX
  7. Process Scenes (video + TTS + audio mix)
  8. Assembly (FFmpeg concat)
  9. Store Dream
  9.5. Dream Reflection (meta-cognitive note stored to memory)
  9.6. Dream Quality Assessment (/assess) — optional
  9.7. Thin Theme Enrichment (/dogpile) — optional
"""

from typing import Optional, List, Dict, Any
import os
import json
import shutil
import subprocess
import typer
from datetime import datetime
from rich.console import Console
from pathlib import Path
from loguru import logger

console = Console()

def _resolve_persona(persona_id: str):
    """Resolve any persona ID to DreamPersona instance.

    No hardcoded registry — any persona can dream. Scope is derived
    automatically: {id}-memories, {id}-dreams, {id}-dream-journals.
    """
    from create_movie.phases.dream_mode import DreamPersona
    display_name = persona_id.capitalize()
    return DreamPersona(id=persona_id, display_name=display_name)


def _scenes_to_script(scenes: list) -> dict:
    """Convert dream scenes to a minimal script format for cast/storyboard."""
    script_scenes = []
    characters: set[str] = set()
    for scene in scenes:
        scene_chars = _extract_characters(scene.narration)
        characters.update(scene_chars)
        script_scenes.append({
            "scene_number": scene.id,
            "description": scene.visual_prompt,
            "dialogue": scene.narration,
            "audio_cue": scene.audio_cue,
            "duration": scene.duration,
            "characters": list(scene_chars),
        })
    return {
        "title": "Dream Sequence",
        "type": "dream",
        "scenes": script_scenes,
        "characters": [{"name": c} for c in characters],
    }


def _extract_characters(narration: str) -> set[str]:
    """Extract character-like proper nouns from narration text."""
    chars: set[str] = set()
    for word in narration.split():
        # Simple heuristic: capitalized words not at sentence start, > 2 chars
        cleaned = word.strip(".,;:!?\"'()[]")
        if cleaned and cleaned[0].isupper() and len(cleaned) > 2:
            chars.add(cleaned)
    # Filter common non-character words
    noise = {"The", "And", "But", "For", "Not", "This", "That", "With", "From", "Into"}
    return chars - noise


def _load_shot_plan(shot_plan_path: Path) -> dict:
    """Load shot plan from storyboard output."""
    if not shot_plan_path.exists():
        return {}
    return json.loads(shot_plan_path.read_text())


def _enrich_scenes_with_shots(scenes: list, shot_plan: dict) -> list:
    """Enrich scene visual prompts with camera directions from storyboard."""
    shots = shot_plan.get("shots", [])
    for i, scene in enumerate(scenes):
        if i < len(shots):
            shot = shots[i]
            camera = shot.get("camera", "")
            if camera and camera not in scene.visual_prompt:
                scene.visual_prompt = f"{camera}, {scene.visual_prompt}"
    return scenes


# ── Bridge → Mood mapping for dream reflections ──
BRIDGE_MOOD_MAP = {
    "Fragility": "anxious, melancholic",
    "Resilience": "hopeful, satisfied",
    "Corruption": "frustrated, restless",
    "Loyalty": "contemplative, focused",
    "Stealth": "curious, scattered",
    "Precision": "focused, energized",
    "Intimacy": "yearning, tender",
}


def _generate_dream_reflection(
    scenes: list,
    contradictions: list,
    persona,
    output_dir: Path,
) -> Optional[dict]:
    """
    Generate a brief post-dream reflection — 3-6 sentences, stream-of-consciousness.

    This is NOT a journal entry. It's a short meta-cognitive note about what images
    stuck, what feelings lingered, what connections to waking life emerged.
    Stored to memory with taxonomy bridges to close the recursive dream loop.
    """
    from create_movie.skill_registry import run_skill

    if not scenes:
        return None

    # 1. Summarize dream content
    scene_summaries = []
    for s in scenes:
        vp = s.visual_prompt if hasattr(s, "visual_prompt") else s.get("visual_prompt", "")
        narr = s.narration if hasattr(s, "narration") else s.get("narration", "")
        scene_summaries.append(f"{vp[:80]}; {narr[:80]}")
    dream_summary = "\n".join(scene_summaries[:5])

    # 2. Determine reflection mood from dream bridges
    try:
        from common.taxonomy_core import get_bridge_attributes
        all_text = " ".join(scene_summaries)
        bridges = get_bridge_attributes(all_text)
    except ImportError:
        bridges = []

    mood = "contemplative"
    bridge_tags = []
    if bridges:
        bridge_tags = bridges[:3]
        mood = BRIDGE_MOOD_MAP.get(bridges[0], "contemplative")

    # 2b. Smell modulates emotional tone (per PMC11202128 — olfactory cues
    # don't create literal dream content but shift the emotional register)
    try:
        from common.taxonomy_core import extract_sensory_modalities
        dream_senses = extract_sensory_modalities(all_text)
        if "smell" in dream_senses:
            # Smell deepens emotional coloring — append to mood
            mood = f"{mood}, haunted by something half-remembered"
        if "touch" in dream_senses or "temperature" in dream_senses:
            mood = f"{mood}, still feeling phantom sensations"
    except ImportError:
        dream_senses = []

    # 3. Build contradiction context
    tension_ctx = ""
    if contradictions:
        tension_lines = [c.get("description", "") if isinstance(c, dict) else c.description for c in contradictions[:2]]
        tension_ctx = f"\nUnresolved tensions from the dream:\n" + "\n".join(f"- {t}" for t in tension_lines)

    # 4. Generate reflection via scillm
    sensory_hint = ""
    if dream_senses:
        sensory_hint = f"\nSensations that lingered: {', '.join(dream_senses)}"

    prompt = f"""You are {persona.display_name}. You just woke from this dream:
{dream_summary}
{tension_ctx}{sensory_hint}
Write 3-6 sentences in your dream journal. Stream of consciousness.
What images stuck? What feelings linger? What did your body remember?
Any connection to your waking life?
Tone: {mood}"""

    from prompter import _find_scillm_run_sh
    scillm_path = _find_scillm_run_sh()
    if not scillm_path:
        console.print("[dim]Dream reflection skipped — scillm not available[/dim]")
        return None

    try:
        clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        result = subprocess.run(
            ["bash", str(scillm_path), "batch", "single", prompt],
            capture_output=True, text=True, timeout=45,
            cwd=str(scillm_path.parent), env=clean_env,
        )
        if result.returncode != 0:
            console.print(f"[dim]Dream reflection generation failed (exit {result.returncode})[/dim]")
            return None

        reflection_text = result.stdout.strip()
        if not reflection_text or len(reflection_text) < 20:
            console.print("[dim]Dream reflection too short, skipping[/dim]")
            return None
    except subprocess.TimeoutExpired:
        console.print("[dim]Dream reflection timed out[/dim]")
        return None
    except Exception as e:
        console.print(f"[dim]Dream reflection failed: {e}[/dim]")
        return None

    # 5. Store to memory
    date_str = datetime.now().strftime("%Y-%m-%d")
    tags_csv = ",".join(bridge_tags) if bridge_tags else "dream,reflection"
    learn_args = [
        "learn",
        "--problem", f"Dream reflection: {date_str}",
        "--solution", reflection_text,
        "--scope", persona.scope("dream-journals"),
        "--tag", tags_csv,
    ]
    learn_result = run_skill("memory", learn_args, capture=True)
    if learn_result.get("returncode") == 0:
        console.print(f"[dim]Dream reflection: {mood} tone, stored to {persona.id}-dream-journals[/dim]")
    else:
        console.print("[dim]Dream reflection generated but memory storage failed[/dim]")

    # 6. Write to disk
    reflection_path = output_dir / "dream_reflection.txt"
    reflection_path.write_text(reflection_text)

    return {
        "text": reflection_text,
        "mood": mood,
        "bridges": bridge_tags,
        "path": str(reflection_path),
    }


def _assess_dream_quality(
    scenes: list,
    contradictions: list,
    output_dir: Path,
) -> Optional[dict]:
    """Optionally assess dream coherence via /assess. Graceful skip if unavailable."""
    from create_movie.skill_registry import run_skill

    scene_lines = []
    for i, s in enumerate(scenes):
        vp = s.visual_prompt if hasattr(s, "visual_prompt") else s.get("visual_prompt", "")
        narr = s.narration if hasattr(s, "narration") else s.get("narration", "")
        scene_lines.append(f"## Scene {i+1}\n**Visual:** {vp}\n**Narration:** {narr}")

    contradiction_section = ""
    if contradictions:
        c_lines = []
        for c in contradictions:
            desc = c.get("description", "") if isinstance(c, dict) else c.description
            c_lines.append(f"- {desc}")
        contradiction_section = "\n## Contradictions\n" + "\n".join(c_lines)

    doc = f"# Dream Assessment\n\n" + "\n\n".join(scene_lines) + contradiction_section
    temp_path = output_dir / "dream_assessment_input.md"
    temp_path.write_text(doc)

    quality_path = output_dir / "dream_quality.json"
    assess_result = run_skill("assess", [
        "run", str(temp_path), "--output", str(quality_path),
    ], capture=True)

    if assess_result.get("returncode") == 0 and quality_path.exists():
        try:
            quality = json.loads(quality_path.read_text())
            # Simple health score from assess output
            scores = quality.get("scores", {})
            if scores:
                health_score = sum(scores.values()) / len(scores)
                console.print(f"[dim]Dream coherence: {health_score:.0%}[/dim]")
            return quality
        except Exception as e:
            logger.debug("value lookup failed: {}", e)
    else:
        console.print("[dim]Dream quality assessment skipped[/dim]")

    return None


def _enrich_thin_themes(scenes: list, output_dir: Path) -> Optional[str]:
    """If >50% of scenes have thin visual prompts, research deeper via /dogpile."""
    from create_movie.skill_registry import run_skill
    from create_movie.phases.dream_mode import _extract_themes

    thin_scenes = [
        s for s in scenes
        if len(s.visual_prompt if hasattr(s, "visual_prompt") else s.get("visual_prompt", "")) < 50
    ]
    if not thin_scenes or len(thin_scenes) <= len(scenes) // 2:
        return None

    all_prompts = [
        s.visual_prompt if hasattr(s, "visual_prompt") else s.get("visual_prompt", "")
        for s in scenes
    ]
    themes = _extract_themes(all_prompts)
    if not themes:
        return None

    console.print(f"[dim]Enriching thin dream themes: {themes}[/dim]")
    res = run_skill("dogpile", ["search", themes, "--no-interactive"], capture=True)
    if res.get("returncode") == 0:
        return res.get("stdout", "").strip()[:500]
    return None


dream_group = typer.Typer(name="dream", help="Dream generation commands.")

@dream_group.command("generate")
def generate_cmd(
    limit: int = typer.Option(5, help="Number of memory items to fetch (residue)"),
    duration: int = typer.Option(30, help="Target duration in seconds"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without generating assets"),
    persona: str = typer.Option("horus", help="Persona to dream as (horus, embry)"),
    work_dir: str | None = typer.Option(None, help="Output directory (default: dream_assets)"),
):
    """Generate a dream movie from recent memories."""

    persona_obj = _resolve_persona(persona)
    console.print(f"[bold cyan]Initiating Dream Sequence for {persona_obj.display_name} (limit={limit})...[/bold cyan]")

    # 1. Fetch Day Residue using skill_registry approach
    from create_movie.phases.dream_mode import fetch_day_residue, store_dream

    console.print(f"[dim]Fetching day residue from {persona_obj.display_name} memory...[/dim]")
    contradictions = []
    try:
        residue_data = fetch_day_residue(persona=persona_obj)
        prompt = residue_data.get("prompt", "")
        source_ids = residue_data.get("ids", [])
        structured_items = residue_data.get("items", [])
        contradictions = residue_data.get("contradictions", [])
    except Exception as e:
        console.print(f"[red]Failed to fetch residue: {e}[/red]")
        return

    # Convert to items format expected by downstream code
    items = []
    if structured_items:
        items = [{"type": si.get("type", "Unknown"), "text": si.get("text", "")} for si in structured_items]
    elif prompt:
        for line in prompt.split("\n\n"):
            if ":" in line:
                type_label, text = line.split(":", 1)
                if text.strip():
                    items.append({"type": type_label.strip(), "text": text.strip()})

    if not items:
        console.print("[yellow]No day residue found. Persona has no memories to dream from.[/yellow]")
        return

    console.print(f"[green]Found {len(items)} residue items from {len(source_ids)} sources.[/green]")
    for item in items[:limit]:
        text_preview = item.get('text', '')[:60]
        console.print(f"  - [{item.get('type')}] {text_preview}...")

    # Initialize clients
    from prompter import DreamPrompter, DreamScene
    from core.together_renderer import TogetherRenderer
    from audio_mixer import AudioMixer
    from create_movie.skill_registry import run_skill

    prompter = DreamPrompter()
    renderer = TogetherRenderer(model="kling-2.1-std")

    tts_project_dir = Path(__file__).parent.parent / "tts-train"
    # TTS checkpoint: check persona-specific, then env var, then known locations
    tts_checkpoint_path = None
    if persona_obj.tts_checkpoint and persona_obj.tts_checkpoint.exists():
        tts_checkpoint_path = str(persona_obj.tts_checkpoint)
    if not tts_checkpoint_path:
        tts_checkpoint_path = os.environ.get("HORUS_TTS_CHECKPOINT")
    if tts_checkpoint_path:
        tts_checkpoint = Path(tts_checkpoint_path)
    else:
        experiments_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        checkpoint_candidates = [
            experiments_root / "memory" / "artifacts" / "tts" / "horus_qwen3_1.7b_repaired" / "checkpoint-epoch-9",
            experiments_root / "memory" / "artifacts" / "tts" / "horus_qwen3_06b_final" / "checkpoint-epoch-1",
            experiments_root / "memory" / "artifacts" / "tts" / "horus_final_prod",
            Path.home() / ".pi" / "tts-checkpoints" / "horus_qwen3",
        ]
        tts_checkpoint = None
        for candidate in checkpoint_candidates:
            if candidate.exists():
                tts_checkpoint = candidate
                console.print(f"[dim]Using TTS checkpoint: {candidate}[/dim]")
                break
        if not tts_checkpoint:
            console.print("[yellow]Warning: No TTS checkpoint found. Set HORUS_TTS_CHECKPOINT env var.[/yellow]")
            tts_checkpoint = checkpoint_candidates[0]
    mixer = AudioMixer(tts_project_dir, tts_checkpoint)

    # Setup output
    output_dir = Path(work_dir) if work_dir else Path("dream_assets")
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Phase 2: Generate Dream Scenes (Prompting) ──
    max_scenes = max(1, duration // 5)
    console.print(f"[bold cyan]Dreaming via {prompter.model_name} ({max_scenes} scenes, {duration}s target)...[/bold cyan]")
    try:
        scenes = prompter.generate_dream_prompts(
            items, count=max_scenes,
            structured_items=structured_items if structured_items else None,
        )
    except Exception as e:
        console.print(f"[bold red]Failed to generate dream scenes: {e}[/bold red]")
        return

    if not scenes:
        console.print("[red]No scenes generated from memories.[/red]")
        return

    console.print(f"[green]Generated {len(scenes)} dream scenes:[/green]")
    for scene in scenes:
        console.print(f"  Scene {scene.id} ({scene.duration}s): {scene.visual_prompt[:60]}...")

    # ── Phase 3: Dream Casting (optional) ──
    characters_dir = None
    dream_script = _scenes_to_script(scenes)
    script_path = output_dir / "dream_script.json"
    script_path.write_text(json.dumps(dream_script, indent=2))

    if not dry_run:
        console.print("[cyan]Running dream casting via create-cast...[/cyan]")
        cast_result = run_skill("create-cast", [
            "auto", "--script", str(script_path),
            "--output", str(output_dir / "characters"),
        ])
        if cast_result.get("returncode") == 0:
            characters_dir = output_dir / "characters"
            console.print(f"[green]Cast generated: {characters_dir}[/green]")
        else:
            console.print("[dim]Casting skipped — no character consistency[/dim]")
    else:
        console.print("[dim]Dry Run: Would run dream casting[/dim]")

    # ── Phase 4: Dream Storyboard (optional) ──
    if not dry_run:
        console.print("[cyan]Generating dream storyboard via create-storyboard...[/cyan]")
        storyboard_result = run_skill("create-storyboard", [
            "start", str(script_path),
            "--auto-approve",
            "--output", str(output_dir / "storyboard"),
            "--json",
        ])
        if storyboard_result.get("returncode") == 0:
            shot_plan = _load_shot_plan(output_dir / "storyboard" / "shot_plan.json")
            if shot_plan:
                scenes = _enrich_scenes_with_shots(scenes, shot_plan)
                console.print(f"[green]Storyboard: {len(shot_plan.get('shots', []))} shots planned[/green]")
            else:
                console.print("[dim]Storyboard completed but no shot plan found[/dim]")
        else:
            console.print("[dim]Storyboard skipped — using raw scene prompts[/dim]")
    else:
        console.print("[dim]Dry Run: Would generate storyboard[/dim]")

    # ── Phase 5: Generate global soundtrack via create-score ──
    score_path = output_dir / "dream_score.wav"
    if not dry_run and not score_path.exists():
        mood_cues = " ".join(s.audio_cue for s in scenes[:3])
        console.print(f"[cyan]Generating {duration}s dream score via create-score...[/cyan]")
        score_result = run_skill("create-score", [
            "generate",
            "--prompt", f"atmospheric dreamlike ambient score: {mood_cues}",
            "--out", str(score_path),
            "--duration-s", str(duration),
        ])
        if score_result.get("returncode") == 0:
            console.print(f"[green]Score generated: {score_path.name}[/green]")
        else:
            console.print(f"[yellow]Score generation skipped: {score_result.get('error', 'unknown')}[/yellow]")
    elif dry_run:
        console.print(f"[dim]Dry Run: Would generate {duration}s dream score[/dim]")

    # ── Phase 6: Sound Design (optional, replaces ad-hoc SFX) ──
    sfx_manifest = None
    if not dry_run:
        storyboard_yaml = output_dir / "storyboard" / "shot_plan.yaml"
        console.print("[cyan]Running sound design via create-sound-design...[/cyan]")
        sound_args = [
            "auto",
            "--script", str(script_path),
            "--output", str(output_dir / "sound_design"),
        ]
        if storyboard_yaml.exists():
            sound_args.extend(["--storyboard", str(storyboard_yaml)])
        sound_result = run_skill("create-sound-design", sound_args)
        if sound_result.get("returncode") == 0:
            manifest_path = output_dir / "sound_design" / "manifest.json"
            if manifest_path.exists():
                sfx_manifest = json.loads(manifest_path.read_text())
                event_count = sum(
                    len(s.get("events", []))
                    for s in sfx_manifest.get("scenes", {}).values()
                )
                console.print(f"[green]Sound design: {event_count} SFX events[/green]")
            else:
                console.print("[dim]Sound design completed but no manifest found[/dim]")
        else:
            console.print("[dim]Sound design skipped — using per-scene SFX lookup[/dim]")
    else:
        console.print("[dim]Dry Run: Would run sound design[/dim]")

    # ── Phase 7: Process Scenes ──
    video_clips = []
    audio_clips = []

    for i, scene in enumerate(scenes):
        console.rule(f"[bold]Scene {i+1}: {scene.visual_prompt[:40]}...[/bold]")

        # A. Video Generation (Together API)
        video_filename = f"scene_{i+1:03d}.mp4"
        video_path = output_dir / video_filename

        if dry_run:
            console.print(f"[dim]Dry Run: Would generate video for prompt: {scene.visual_prompt}[/dim]")
        else:
            if not video_path.exists():
                console.print(f"[cyan]Generating video for Scene {i+1} via {renderer.name}...[/cyan]")
                enhanced_prompt = f"{scene.visual_prompt}, cinematic, dreamlike, 4k, surreal"
                try:
                    render_result = renderer.render_shot(
                        prompt=enhanced_prompt,
                        output_path=video_path,
                        duration_s=scene.duration,
                    )
                    if not render_result.success:
                        console.print(f"[red]Video generation failed for scene {i+1}: {render_result.error}[/red]")
                        continue
                except Exception as e:
                    console.print(f"[red]Render Error: {e}[/red]")
                    continue
            else:
                console.print(f"[dim]Video for Scene {i+1} already exists: {video_path.name}[/dim]")
        video_clips.append(str(video_path))

        # B. Narration Generation (TTS)
        audio_filename = f"scene_{i+1:03d}_audio.wav"
        audio_path = output_dir / audio_filename

        if dry_run:
            console.print(f"[dim]Dry Run: Would generate narration for: {scene.narration}[/dim]")
        else:
            if not audio_path.exists():
                console.print(f"[cyan]Generating narration for Scene {i+1}...[/cyan]")
                try:
                    mixer.generate_narration(scene.narration, audio_path)
                except Exception as e:
                    console.print(f"[red]TTS Error: {e}[/red]")
            else:
                console.print(f"[dim]Narration for Scene {i+1} already exists: {audio_path.name}[/dim]")
        audio_clips.append(str(audio_path))

        # C. SFX — use sound design manifest if available, else ad-hoc lookup
        sfx_filename = f"scene_{i+1:03d}_sfx.wav"
        sfx_path = output_dir / sfx_filename

        if dry_run:
            console.print(f"[dim]Dry Run: Would query SFX for: {scene.audio_cue}[/dim]")
        else:
            if not sfx_path.exists():
                if sfx_manifest:
                    # Use sound design manifest
                    scene_key = str(i + 1)
                    scene_sfx = sfx_manifest.get("scenes", {}).get(scene_key, {})
                    events = scene_sfx.get("events", [])
                    if events and events[0].get("path"):
                        try:
                            shutil.copy(events[0]["path"], sfx_path)
                            console.print(f"[green]SFX (designed): {Path(events[0]['path']).name}[/green]")
                        except Exception as e:
                            console.print(f"[yellow]SFX copy failed: {e}[/yellow]")
                    else:
                        console.print(f"[dim]No designed SFX for scene {i+1}[/dim]")
                else:
                    # Fallback: ad-hoc sfx-catalog search
                    console.print(f"[cyan]Querying SFX for Scene {i+1}...[/cyan]")
                    try:
                        sfx_result = run_skill("sfx-catalog", [
                            "search", scene.audio_cue, "--limit", "1", "--json"
                        ])
                        if sfx_result.get("returncode") == 0:
                            sfx_data = json.loads(sfx_result.get("stdout", "[]"))
                            if sfx_data and isinstance(sfx_data, list) and sfx_data[0].get("path"):
                                shutil.copy(sfx_data[0]["path"], sfx_path)
                                console.print(f"[green]SFX: {Path(sfx_data[0]['path']).name}[/green]")
                            else:
                                console.print(f"[dim]No SFX matched for scene {i+1}[/dim]")
                        else:
                            console.print(f"[dim]SFX catalog not available[/dim]")
                    except Exception as e:
                        console.print(f"[yellow]SFX query failed: {e}[/yellow]")

        # D. Mix Audio (Narration + SFX)
        final_audio_filename = f"scene_{i+1:03d}_final_audio.m4a"
        final_audio_path = output_dir / final_audio_filename

        if dry_run:
            console.print(f"[dim]Dry Run: Would mix narration + SFX -> {final_audio_path.name}[/dim]")
        else:
            if not final_audio_path.exists():
                console.print(f"[cyan]Mixing audio for Scene {i+1}...[/cyan]")
                try:
                    sfx_file = str(sfx_path) if sfx_path.exists() else None
                    mixer.mix_scene_audio(
                        narration_text=scene.narration,
                        output_path=str(final_audio_path),
                        sfx_path=sfx_file,
                        duration=scene.duration,
                        dry_run=False
                    )
                except Exception as e:
                    console.print(f"[red]Audio Mixing Error: {e}[/red]")
            else:
                console.print(f"[dim]Mixed audio for Scene {i+1} already exists: {final_audio_path.name}[/dim]")

    # ── Phase 8: Assembly ──
    console.print("\n[dim]Assembling final cut...[/dim]")
    final_clips = []

    for i, scene in enumerate(scenes):
        shot_id = f"scene_{i+1:03d}"
        video_path = output_dir / f"{shot_id}.mp4"
        audio_path = output_dir / f"{shot_id}_final_audio.m4a"
        clip_path = output_dir / f"{shot_id}_final.mp4"

        if dry_run:
             console.print(f"[dim]Dry run: Would merge {video_path.name} + {audio_path.name} -> {clip_path.name}[/dim]")
             final_clips.append(str(clip_path))
             continue

        if not video_path.exists():
            console.print(f"[yellow]Missing video for Scene {i+1}, skipping assembly.[/yellow]")
            continue

        # Merge Video + Audio
        cmd = ["ffmpeg", "-y", "-i", str(video_path)]
        if audio_path.exists():
            cmd.extend(["-i", str(audio_path), "-c:v", "copy", "-c:a", "aac", "-shortest"])
        else:
            cmd.extend(["-c:v", "copy", "-an"])

        cmd.append(str(clip_path))

        try:
            subprocess.run(cmd, capture_output=True, check=True)
            final_clips.append(str(clip_path))
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to merge clip {i+1}: {e.stderr}[/red]")

    if final_clips:
        concat_file = Path(output_dir) / "concat.txt"
        with open(concat_file, "w") as f:
            for clip in final_clips:
                f.write(f"file '{clip}'\n")

        final_movie = Path(output_dir) / "dream_movie.mp4"
        console.print(f"[dim]Concatenating {len(final_clips)} clips -> {final_movie}...[/dim]")

        if dry_run:
            console.print(f"[dim]Dry run: Would concat to {final_movie}[/dim]")
        else:
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_file), "-c", "copy", str(final_movie)
                ], capture_output=True, check=True)

                # Overlay global score if available
                if score_path.exists():
                    scored_movie = Path(output_dir) / "dream_movie_scored.mp4"
                    subprocess.run([
                        "ffmpeg", "-y",
                        "-i", str(final_movie),
                        "-i", str(score_path),
                        "-filter_complex",
                        "[1:a]volume=0.25[score];[0:a][score]amix=inputs=2:duration=first[out]",
                        "-map", "0:v", "-map", "[out]",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-t", str(duration),
                        str(scored_movie)
                    ], capture_output=True, check=True)
                    scored_movie.rename(final_movie)
                    console.print("[green]Score overlaid onto dream movie[/green]")
                else:
                    # Just trim to target duration
                    trimmed = Path(output_dir) / "dream_movie_trimmed.mp4"
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(final_movie),
                        "-t", str(duration), "-c", "copy", str(trimmed)
                    ], capture_output=True, check=True)
                    trimmed.rename(final_movie)

                console.print(f"[bold green]Dream Movie created: {final_movie} ({duration}s)[/bold green]")

                # Copy player
                template_path = Path(__file__).parent / "templates" / "player.html"
                if template_path.exists():
                    shutil.copy(template_path, Path(output_dir) / "index.html")
                    console.print("[green]Generated player: index.html[/green]")
            except subprocess.CalledProcessError as e:
                console.print(f"[red]Concatenation/scoring failed: {e.stderr}[/red]")

    # ── Phase 9: Store Dream ──
    if dry_run:
        console.print("[yellow]Dry run complete. No assets generated.[/yellow]")
    else:
        final_movie = Path(output_dir) / "dream_movie.mp4"
        console.print(f"\n[cyan]Storing {persona_obj.display_name}'s dream in memory...[/cyan]")
        store_dream(
            scenes=scenes,
            source_ids=source_ids,
            duration=duration,
            output_path=final_movie if final_movie.exists() else None,
            persona=persona_obj,
        )

        # ── Phase 9.5: Dream Reflection ──
        console.print(f"\n[cyan]{persona_obj.display_name} reflects on the dream...[/cyan]")
        reflection = _generate_dream_reflection(
            scenes=scenes,
            contradictions=contradictions,
            persona=persona_obj,
            output_dir=output_dir,
        )
        if reflection:
            console.print(f"[green]Reflection written ({reflection['mood']} tone)[/green]")

            # ── Phase 9.55: Update BDI state with dream mood ──
            try:
                from create_persona.src.theory_of_mind import (
                    get_or_create_bdi_state,
                    save_bdi_state,
                )

                DREAM_MOOD_TO_BDI = {
                    "anxious": "defensive",
                    "melancholic": "contemplative",
                    "hopeful": "supportive",
                    "satisfied": "engaged",
                    "frustrated": "critical",
                    "restless": "intense",
                    "contemplative": "contemplative",
                    "focused": "intense",
                    "curious": "engaged",
                    "scattered": "neutral",
                    "energized": "enthusiastic",
                    "yearning": "wistful",
                    "tender": "supportive",
                }

                # Extract primary mood word (before comma if compound)
                raw_mood = reflection["mood"].split(",")[0].strip()
                bdi_mood = DREAM_MOOD_TO_BDI.get(raw_mood, "contemplative")

                bdi_state = get_or_create_bdi_state(
                    persona_name=persona_obj.display_name,
                    user_id="dream_system",
                )
                bdi_state.current_mood = bdi_mood
                bdi_state.mood_history.append(f"dream:{bdi_mood}")
                bdi_state.mood_history = bdi_state.mood_history[-10:]

                # Store dream bridges as beliefs
                for bridge in reflection.get("bridges", []):
                    bdi_state.beliefs[f"dream_bridge:{bridge}"] = 0.8
                bdi_state.beliefs["has_recent_dream"] = 1.0

                save_bdi_state(bdi_state)
                console.print(f"[dim]BDI updated: mood={bdi_mood}, bridges={reflection.get('bridges', [])}[/dim]")
            except ImportError:
                console.print("[dim]BDI update skipped — create-persona not available[/dim]")
            except Exception as e:
                console.print(f"[dim]BDI update failed (non-fatal): {e}[/dim]")

        # ── Phase 9.6: Dream Quality Assessment (optional) ──
        _assess_dream_quality(scenes, contradictions, output_dir)

        # ── Phase 9.7: Enrich thin themes via /dogpile (optional) ──
        _enrich_thin_themes(scenes, output_dir)

        console.print(f"[bold green]{persona_obj.display_name}'s dream generation complete![/bold green]")

if __name__ == "__main__":
    dream_group(prog_name="dream")
