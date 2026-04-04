#!/usr/bin/env python3
"""
create-movie Orchestrator for Horus Persona

Coordinates the movie creation workflow through phases:
Research → Script → Build Tools → Generate → Assemble → Learn

Philosophy: "AI isn't the artist, it's the amplifier"

This file contains the CLI commands that orchestrate the extracted phase modules.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Load .env walking up from cwd, then also load monorepo root .env
# (override=False means earlier loads win — closer .env takes priority)
load_dotenv(find_dotenv(usecwd=True), override=False)
_root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env, override=False)

import typer
from rich.console import Console
from rich.panel import Panel

# Import from create_movie package
from create_movie import MovieProject
from create_movie.phases import (
    HardwareProfile,
    detect_hardware,
    select_model_variant,
    display_hardware_profile,
    research_topic,
    generate_script,
    build_tools_for_script,
    generate_assets,
    assemble_movie,
    study_topic,
    study_all_topics,
    list_topics,
    store_learnings,
    FILMMAKING_TOPICS,
    archive_creation_session,
    # Dream mode
    DreamPersona,
    fetch_day_residue,
    load_identity_packs_for_veo,
    render_shots,
)

# Veo adapter imports
from veo_adapter import export_to_veo

# Multi-renderer support
from core.renderer import get_renderer, list_renderers
# Ensure all renderer backends are registered by importing them
import core.veo_renderer      # noqa: F401 - registers "veo"
import core.fal_renderer       # noqa: F401 - registers "fal"
import core.together_renderer  # noqa: F401 - registers "together"

console = Console()

SKILL_DIR = Path(__file__).parent
PI_SKILLS_DIR = SKILL_DIR.parent  # .pi/skills/

# task-monitor integration
try:
    sys.path.append(str(PI_SKILLS_DIR / "task-monitor"))
    from monitor_adapter import Monitor
except ImportError:
    Monitor = None

# =============================================================================
# CLI Commands (thin wrappers around phase modules)
# =============================================================================


def research(
    topic: str = typer.Argument(help="Research topic"),
    output: str = typer.Option("research.json", "-o", "--output", help="Output file for research results"),
    skip_external: bool = typer.Option(False, "--skip-external", help="Skip external search (library only)"),
):
    """Phase 1: Research techniques and tools - library first, then external."""
    console.print(Panel(f"[bold blue]RESEARCH PHASE[/bold blue]\nTopic: {topic}"))
    research_topic(topic, Path(output), skip_external)


def script(
    from_research: str = typer.Option(..., "-r", "--from-research", help="Research JSON file"),
    prompt: str = typer.Option(None, "-p", "--prompt", help="Movie concept/prompt (overrides research topic)"),
    duration: int = typer.Option(30, "-d", "--duration", help="Target duration in seconds"),
    use_create_story: bool = typer.Option(False, "--use-create-story", help="Use /create-story to generate screenplay"),
    model: str = typer.Option("chimera", "-m", "--model", help="LLM model for screenplay generation"),
    output: str = typer.Option("script.json", "-o", "--output", help="Output file for script"),
    dream: bool = typer.Option(False, "--dream", help="[DEPRECATED] Use --mode dream"),
    mode: str = typer.Option("standard", help="Narrative mode: standard, dream"),
    preset: str = typer.Option(None, help="Cinematic preset/persona ID (e.g., persona_kubrick_v1)"),
    renderer: str = typer.Option("veo", help="Video renderer: veo, fal:<model>, together:<model>, none"),
):
    """Phase 2: Generate script from research with scene breakdown."""
    console.print(Panel("[bold blue]SCRIPT PHASE[/bold blue]\nCreate scene breakdown"))

    # Handle legacy --dream flag
    if dream:
        mode = "dream"
        console.print("[yellow]Note: --dream is deprecated, using --mode dream[/yellow]")

    generate_script(
        research_path=Path(from_research),
        prompt=prompt,
        duration=duration,
        use_create_story=use_create_story,
        model=model,
        output_path=Path(output),
        mode=mode,
        preset=preset,
    )


def build_tools(
    script: str = typer.Option(..., "-s", "--script", help="Script JSON file"),
    output_dir: str = typer.Option("./tools", "-o", "--output-dir", help="Output directory for tools"),
    skip_docker: bool = typer.Option(False, "--skip-docker", help="Skip Docker sandbox (use host)"),
):
    """Phase 3: Build custom tools in Docker sandbox."""
    console.print(Panel("[bold blue]BUILD TOOLS PHASE[/bold blue]\nWrite code in Docker sandbox"))
    build_tools_for_script(Path(script), Path(output_dir), skip_docker)


def generate(
    tools: str = typer.Option("./tools", "-t", "--tools", help="Tools directory"),
    script: str = typer.Option(..., "-s", "--script", help="Script JSON file"),
    output_dir: str = typer.Option("./assets", "-o", "--output-dir", help="Output directory for assets"),
    style: str = typer.Option("", help="Visual style to apply (e.g., 'cinematic', 'film noir')"),
    model: str = typer.Option("ltx2-fp8", "-m", "--model", help="Video model variant"),
    resolution: str = typer.Option("720p", help="Output resolution (720p, 1080p)"),
    max_clip_seconds: int = typer.Option(10, help="Maximum clip length in seconds"),
    audio: bool = typer.Option(True, "--audio/--no-audio", help="Enable audio generation"),
    hardware_profile: str = typer.Option(None, help="Path to hardware_profile.json"),
    renderer: str = typer.Option("none", help="Video renderer: veo, fal:<model>, together:<model>, none"),
    characters: str = typer.Option(None, help="Path to characters directory with identity packs"),
):
    """Phase 4: Generate visual/audio assets for each scene."""
    console.print(Panel(
        f"[bold blue]GENERATE PHASE[/bold blue]\n"
        f"Model: {model} | Resolution: {resolution} | Audio: {'ON' if audio else 'OFF'}"
    ))
    generate_assets(
        script_path=Path(script),
        output_dir=Path(output_dir),
        tools_dir=Path(tools) if tools else None,
        style=style,
        model=model,
        resolution=resolution,
        max_clip_seconds=max_clip_seconds,
        audio_enabled=audio,
        hardware_profile_path=Path(hardware_profile) if hardware_profile else None,
        renderer=renderer,
        characters_path=Path(characters) if characters else None,
    )


def assemble(
    assets: str = typer.Option(..., "-a", "--assets", help="Assets directory"),
    output: str = typer.Option(..., "-o", "--output", help="Output file (e.g., movie.mp4 or output_dir/)"),
    output_format: str = typer.Option("mp4", "-f", "--format", help="Output format: mp4, html"),
    fps: int = typer.Option(24, help="Frames per second for MP4"),
):
    """Phase 5: Assemble final output as MP4 or interactive HTML."""
    console.print(Panel(f"[bold blue]ASSEMBLE PHASE[/bold blue]\nOutput format: {output_format}"))
    assemble_movie(Path(assets), Path(output), output_format, fps)


def study(
    topic: str | None = typer.Argument(None, help="Filmmaking topic to study"),
    scope: str = typer.Option("horus-filmmaking", help="Memory scope for storage"),
    deep: bool = typer.Option(False, "--deep/--quick", help="Deep research (dogpile) vs quick (memory check)"),
    list_topics_flag: bool = typer.Option(False, "--list-topics", help="List suggested filmmaking topics"),
):
    """Study filmmaking topics to acquire knowledge for future movie creation."""
    console.print(Panel("[bold blue]STUDY PHASE[/bold blue]\nAcquire filmmaking knowledge for memory"))

    if list_topics_flag:
        list_topics()
        return

    if not topic:
        console.print("[yellow]No topic provided. Use --list-topics to see suggestions.[/yellow]")
        console.print("[dim]Or: ./run.sh study 'camera framing techniques'[/dim]")
        return

    study_topic(topic, scope, deep)


def study_all(
    scope: str = typer.Option("horus-filmmaking", help="Memory scope for storage"),
):
    """Study all suggested filmmaking topics (comprehensive learning session)."""
    console.print(Panel(
        "[bold blue]COMPREHENSIVE STUDY SESSION[/bold blue]\n"
        f"Learning {len(FILMMAKING_TOPICS)} core filmmaking topics"
    ))
    study_all_topics(scope)


def learn(
    project_dir: str = typer.Option(..., "-p", "--project-dir", help="Project directory to extract learnings from"),
    scope: str = typer.Option("horus-filmmaking", help="Memory scope for storage"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show learnings without storing"),
):
    """Phase 6: Store learnings in memory for future recall."""
    console.print(Panel(f"[bold blue]LEARN PHASE[/bold blue]\nStoring insights in memory (scope: {scope})"))
    store_learnings(Path(project_dir), scope, dry_run)




# =============================================================================
# Full Workflow: Create
# =============================================================================


def create(
    prompt: str | None = typer.Argument(None, help="Movie concept prompt"),
    output: str = typer.Option("movie.mp4", "-o", "--output", help="Output file"),
    work_dir: str = typer.Option("./movie_project", "-w", "--work-dir", help="Working directory"),
    duration: int = typer.Option(30, "-d", "--duration", help="Target duration in seconds"),
    style: str = typer.Option("cinematic", "-s", "--style", help="Visual style"),
    output_format: str = typer.Option("mp4", "-f", "--format", help="Output format: mp4, html"),
    enable_learnings: bool = typer.Option(True, "--store-learnings/--no-store-learnings", help="Store learnings in memory"),
    skip_research: bool = typer.Option(False, "--skip-research", help="Skip research phase"),
    skip_casting: bool = typer.Option(False, "--skip-casting", help="Skip character casting phase"),
    skip_storyboard: bool = typer.Option(False, "--skip-storyboard", help="Skip storyboard/shot planning phase"),
    skip_sound_design: bool = typer.Option(False, "--skip-sound-design", help="Skip sound design phase"),
    skip_expert_review: bool = typer.Option(False, "--skip-expert-review", help="Skip expert/director review loop (use with caution)"),
    platform: str = typer.Option("kling", help="Video generation platform: kling, veo, ltx2, runway, wan"),
    expert_scope: str = typer.Option(None, help="Override memory scope for technical expert (default: auto from platform)"),
    director_scope: str = typer.Option("horus-filmmaking", help="Memory scope for director persona"),
    llm_review: bool = typer.Option(False, "--llm-review", help="Use LLM-based expert review (more thorough, slower)"),
    max_review_iterations: int = typer.Option(3, help="Max iterations for expert review loop"),
    model: str = typer.Option("auto", "-m", "--model", help="Video model variant: auto, ltx2-fp8, ltx2-fp4, ltx2-distilled, wan2.2, mochi"),
    runpod: bool = typer.Option(False, "--runpod", help="Force cloud generation via RunPod"),
    skip_hardware_check: bool = typer.Option(False, "--skip-hardware-check", help="Skip hardware detection"),
    dream: bool = typer.Option(False, "--dream", help="Activate Dream Mode (surreal narrative + Veo export)"),
    renderer: str = typer.Option("veo", help="Video renderer: veo, fal:kling-2.6, fal:hailuo-std, fal:hailuo-pro, none"),
    preset: str = typer.Option("neutral", help="Cinematic preset/persona ID"),
    persona: str = typer.Option("horus", help="Persona to dream as (e.g. horus, embry)"),
):
    """Full orchestrated workflow through all phases."""

    # Handle optional prompt
    if not prompt:
        if dream:
            prompt = "Surreal Dream"
        else:
            console.print("[red]Error: 'prompt' argument is required unless --dream mode is active.[/red]")
            sys.exit(1)

    work_path = Path(work_dir)
    work_path.mkdir(parents=True, exist_ok=True)

    mode_label = "[bold magenta]DREAM MODE[/bold magenta]" if dream else "STANDARD MODE"
    console.print(Panel(f"[bold blue]CREATE MOVIE[/bold blue]\nPrompt: {prompt}\nMode: {mode_label}"))

    use_renderer = (renderer != "none")
    # Validate renderer spec early
    if use_renderer:
        try:
            video_renderer = get_renderer(renderer)
            console.print(f"[cyan]Video renderer: {video_renderer.name}[/cyan]")
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)
    else:
        video_renderer = None

    # 0. Hardware Detection
    if runpod:
        hardware = HardwareProfile(runpod_suggested=True, model_variant="runpod")
        console.print("[cyan]Using RunPod for cloud generation (--runpod flag)[/cyan]")
    elif skip_hardware_check:
        hardware = HardwareProfile()
        console.print("[dim]Skipping hardware check, using safe defaults[/dim]")
    else:
        hardware = detect_hardware()
        hardware = select_model_variant(hardware)
        display_hardware_profile(hardware)

    # Override model if specified
    if model != "auto":
        hardware.model_variant = model
        console.print(f"[cyan]Model override: {model}[/cyan]")

    # Check if RunPod is needed but not requested
    if hardware.runpod_suggested and not runpod:
        console.print("\n[yellow]⚠️  WARNING: Insufficient local VRAM detected[/yellow]")
        console.print(f"[yellow]   Detected: {hardware.vram_gb}GB VRAM (need 12GB+ for local generation)[/yellow]")
        console.print("[yellow]   Options:[/yellow]")
        console.print("[yellow]   1. Re-run with --runpod to use cloud generation[/yellow]")
        console.print("[yellow]   2. Re-run with --model ltx2-distilled for minimal VRAM[/yellow]")
        console.print()
        if not typer.confirm("Continue with local generation anyway?", default=False):
            console.print("[dim]Aborted. Re-run with --runpod for cloud generation.[/dim]")
            sys.exit(0)

    # Store hardware profile
    hardware_file = work_path / "hardware_profile.json"
    with open(hardware_file, "w") as f:
        json.dump({
            "gpu_name": hardware.gpu_name,
            "vram_gb": hardware.vram_gb,
            "ram_gb": hardware.ram_gb,
            "cuda_available": hardware.cuda_available,
            "model_variant": hardware.model_variant,
            "resolution": hardware.resolution,
            "max_clip_seconds": hardware.max_clip_seconds,
            "audio_enabled": hardware.audio_enabled,
            "weight_streaming": hardware.weight_streaming,
            "runpod_suggested": hardware.runpod_suggested,
            "detected_at": datetime.now().isoformat(),
        }, f, indent=2)

    project = MovieProject(
        name=prompt[:50].replace(" ", "_"),
        prompt=prompt,
    )

    # Dream Mode: Day Residue Injection
    if dream:
        dream_persona = DreamPersona(id=persona, display_name=persona.capitalize())
        console.print(f"\n[magenta]── Dream Mode: Gathering Day Residue for {dream_persona.display_name} ──[/magenta]")
        res_data = fetch_day_residue(persona=dream_persona)
        day_residue = res_data["prompt"]
        if day_residue:
            prompt = f"{prompt} (Influenced by: {day_residue})"
            console.print(f"[dim]Updated Prompt: {prompt}[/dim]")
        style = f"{style}, surreal, dreamlike, non-linear, shifting geometry"

    # Phase indicators
    phases = [
        ("HARDWARE CHECK", "Detecting GPU/RAM", not skip_hardware_check and not runpod),
        ("RESEARCH", "Gathering knowledge", not skip_research),
        ("SCRIPT", "Creating scene breakdown", True),
        ("STORYBOARD", "Shot planning and panels", not skip_storyboard),
        ("CASTING", "Character identity packs", not skip_casting),
        ("BUILD TOOLS", "Preparing custom tools", True),
        ("GENERATE", f"Creating assets ({hardware.model_variant})", True),
        ("SOUND DESIGN", "SFX selection and placement", not skip_sound_design),
        ("ASSEMBLE", "Combining into final output", True),
        ("LEARN", "Storing insights in memory", enable_learnings),
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
    characters_dir = work_path / "characters"
    output_path = work_path / output

    # Phase 1: Research
    if not skip_research:
        console.print("\n[bold]=== Phase 1: RESEARCH ===[/bold]")
        research_topic(prompt, research_file, skip_external=False)
    else:
        console.print("\n[dim]Skipping research phase (--skip-research)[/dim]")
        if not research_file.exists():
            with open(research_file, "w") as f:
                json.dump({"topic": prompt, "sources": {}}, f)

    # Phase 2: Script
    console.print("\n[bold]=== Phase 2: SCRIPT ===[/bold]")
    generate_script(
        research_path=research_file,
        prompt=prompt,
        duration=duration,
        use_create_story=True,
        model="chimera",
        output_path=script_file,
        preset=preset,
    )

    # Phase 2.5: Storyboard (optional)
    shot_plan_file = None
    if not skip_storyboard:
        console.print("\n[bold]=== Phase 2.5a: STORYBOARD ===[/bold]")
        from create_movie.skill_registry import is_skill_available, run_skill
        if is_skill_available("create-storyboard"):
            storyboard_dir = work_path / "storyboard"
            storyboard_dir.mkdir(parents=True, exist_ok=True)

            sb_result = run_skill("create-storyboard", [
                "start",
                str(script_file),
                "--output-dir", str(storyboard_dir),
                "--fidelity", "sketch",
                "--format", "panels",
                "--auto-approve",
                "--json",
            ])

            if sb_result.get("returncode") == 0:
                try:
                    sb_data = json.loads(sb_result.get("stdout", "{}"))
                    if sb_data.get("status") == "complete":
                        shot_plan_file = storyboard_dir / "shot_plan.json"
                        panel_count = sb_data.get("total_shots", 0)
                        console.print(f"[green]Storyboard complete: {panel_count} shots planned[/green]")
                    else:
                        console.print(f"[yellow]Storyboard incomplete: {sb_data.get('status', 'unknown')}[/yellow]")
                except json.JSONDecodeError:
                    console.print("[yellow]Storyboard output not parseable[/yellow]")
            else:
                error_msg = sb_result.get("stderr", sb_result.get("error", ""))[:100]
                console.print(f"[yellow]Storyboard failed: {error_msg}[/yellow]")
        else:
            console.print("[dim]Storyboard skipped (create-storyboard skill not available)[/dim]")
    else:
        console.print("\n[dim]Skipping storyboard phase (--skip-storyboard)[/dim]")

    # Phase 2.5b: Casting
    if not skip_casting:
        console.print("\n[bold]=== Phase 2.5: CASTING ===[/bold]")
        from create_movie.skill_registry import is_skill_available
        if is_skill_available("create-cast"):
            try:
                sys.path.insert(0, str(PI_SKILLS_DIR / "create-cast"))
                from create_cast import run_casting_session

                casting_result = run_casting_session(
                    script_path=script_file,
                    output_dir=characters_dir,
                    auto_approve=True,
                )

                if casting_result.status == "error":
                    console.print(f"[yellow]Casting warning: {casting_result.error}[/yellow]")
                else:
                    char_count = len((casting_result.partial_results or {}).get('characters', []))
                    console.print(f"[green]Casting complete: {char_count} characters[/green]")
            except ImportError as e:
                console.print(f"[dim]Casting skipped (create-cast import failed): {e}[/dim]")
            except Exception as e:
                console.print(f"[yellow]Casting warning: {e}[/yellow]")
        else:
            console.print("[dim]Casting skipped (create-cast skill not available)[/dim]")
    else:
        console.print("\n[dim]Skipping casting phase (--skip-casting)[/dim]")

    # Phase 3: Build Tools
    console.print("\n[bold]=== Phase 3: BUILD TOOLS ===[/bold]")
    build_tools_for_script(script_file, tools_dir, skip_docker=False)

    # Phase 3.5: Expert Review Loop (NON-NEGOTIABLE when creative team assigned)
    if not skip_expert_review:
        console.print("\n[bold]=== Phase 3.5: EXPERT REVIEW ===[/bold]")
        try:
            from persona_integration import ExpertDirectorReviewLoop, get_expert_for_platform, CreativeTeam

            # Auto-select expert based on platform
            expert_config = get_expert_for_platform(platform)
            effective_expert_scope = expert_scope or expert_config.scope

            console.print(f"[dim]Platform: {platform} | Expert: {expert_config.name} ({effective_expert_scope})[/dim]")
            console.print(f"[dim]Director: {director_scope} | LLM Review: {llm_review} | Max iterations: {max_review_iterations}[/dim]")

            # Create creative team configuration
            creative_team = CreativeTeam(
                director=director_scope,
                technical_expert=effective_expert_scope,
                platform=platform,
            )

            review_loop = ExpertDirectorReviewLoop(
                creative_team=creative_team,
                max_iterations=max_review_iterations,
                work_dir=work_path,
                use_llm_review=llm_review,
                project_name=prompt[:50] if prompt else "Untitled",
            )

            # Look for instructions file (multiple possible names)
            instructions_candidates = [
                work_path / "generation_instructions.md",
                work_path / f"{platform.upper()}_INSTRUCTIONS_V1.md",
                work_path / "KLING_INSTRUCTIONS_V1.md",
                work_path / "shot_list.md",
            ]
            instructions_path = None
            for candidate in instructions_candidates:
                if candidate.exists():
                    instructions_path = candidate
                    break

            if instructions_path:
                console.print(f"[dim]Reviewing: {instructions_path.name}[/dim]")
                approved, history = review_loop.run_loop(
                    instructions_path=instructions_path,
                    expert_id=expert_config.name,
                    director_id="director",
                    generate_documents=True,
                )
                if not approved:
                    console.print("[yellow]WARNING: Expert/Director review not fully approved[/yellow]")
                    console.print("[yellow]Review documents in work directory before proceeding[/yellow]")
                    # List generated documents
                    for doc in work_path.glob("*_REVIEW_*.md"):
                        console.print(f"  - {doc.name}")
                    for doc in work_path.glob("*_FEEDBACK.md"):
                        console.print(f"  - {doc.name}")
                else:
                    console.print(f"[green]Expert ({expert_config.name}) + Director approval obtained[/green]")
            else:
                console.print(f"[dim]No instructions file found in {work_path}[/dim]")
                console.print("[dim]Looked for: generation_instructions.md, {PLATFORM}_INSTRUCTIONS_V1.md, shot_list.md[/dim]")
        except ImportError as e:
            console.print(f"[dim]Expert review skipped: {e}[/dim]")
    else:
        console.print("\n[dim]Skipping expert review (--skip-expert-review)[/dim]")

    # Phase 4: Generate
    console.print("\n[bold]=== Phase 4: GENERATE ===[/bold]")
    generate_assets(
        script_path=script_file,
        output_dir=assets_dir,
        tools_dir=tools_dir,
        style=style,
        model=hardware.model_variant,
        resolution=hardware.resolution,
        max_clip_seconds=hardware.max_clip_seconds,
        audio_enabled=hardware.audio_enabled,
        hardware_profile_path=hardware_file,
        renderer=renderer,
        characters_path=characters_dir if characters_dir.exists() else None,
    )

    # Export HorusShotSpec YAML for video rendering (any mode with a renderer)
    if use_renderer:
        mode_label = "Dream Mode" if dream else "Standard Mode"
        console.print(f"\n[magenta]── {mode_label}: Exporting HorusShotSpec YAML ──[/magenta]")
        try:
            from core.shot_compiler import PERMISSIVE_CONSTRAINTS, VEO_CONSTRAINTS
            # Use permissive constraints for non-Veo renderers so the compiler
            # doesn't reject durations or add params the target doesn't support.
            compile_constraints = VEO_CONSTRAINTS if renderer == "veo" else PERMISSIVE_CONSTRAINTS
            identity_packs = load_identity_packs_for_veo(characters_dir) if characters_dir.exists() else None
            veo_requests = export_to_veo(
                work_path, script_file, assets_dir,
                identity_packs=identity_packs,
                constraints=compile_constraints,
            )
            console.print(f"[green]✓ HorusShotSpec export ready in {work_path}/veo_export[/green]")
            console.print(f"[green]✓ Compiled {len(veo_requests)} shots for {video_renderer.name}[/green]")
        except Exception as e:
            console.print(f"[red]HorusShotSpec export failed: {e}[/red]")

    # Video rendering (multi-backend)
    if use_renderer and (work_path / "veo_export" / "manifest.yaml").exists():
        console.print(f"\n[magenta]── Rendering via {video_renderer.name} ──[/magenta]")
        render_monitor = None
        if Monitor:
            compiled_dir = work_path / "veo_export" / "compiled"
            shot_count = len(list(compiled_dir.glob("*.json")))
            render_monitor = Monitor(name=f"movie-render-{work_path.name}", total=shot_count)
        shots_rendered = render_shots(work_path, renderer=video_renderer, monitor=render_monitor)

    # Phase 4.5: Sound Design
    sfx_manifest = None
    if not skip_sound_design:
        console.print("\n[bold]=== Phase 4.5: SOUND DESIGN ===[/bold]")
        from create_movie.skill_registry import is_skill_available
        if is_skill_available("create-sound-design"):
            try:
                # Import create-sound-design skill
                sound_design_path = Path(__file__).parent.parent / "create-sound-design"
                if str(sound_design_path) not in sys.path:
                    sys.path.insert(0, str(sound_design_path))
                from create_sound_design import run_sound_design_session

                # Get storyboard path if exists
                storyboard_file = work_path / "veo_export" / "manifest.yaml"
                storyboard_path = str(storyboard_file) if storyboard_file.exists() else ""

                # Run sound design in auto-approve mode
                audio_sfx_dir = assets_dir / "sfx"
                sound_result = run_sound_design_session(
                    script_path=str(script_file),
                    storyboard_path=storyboard_path,
                    output_dir=str(audio_sfx_dir),
                    auto_approve=True,
                )

                if sound_result.status == "complete":
                    console.print(f"[green]✓ Sound design complete: {sound_result.event_count} SFX events placed[/green]")
                    sfx_manifest = sound_result.manifest_path
                else:
                    console.print(f"[yellow]Sound design incomplete: {sound_result.status}[/yellow]")
                    if sound_result.error:
                        console.print(f"[dim]Error: {sound_result.error}[/dim]")

            except ImportError as e:
                console.print(f"[yellow]create-sound-design import failed, skipping SFX ({e})[/yellow]")
            except Exception as e:
                console.print(f"[red]Sound design failed: {e}[/red]")
        else:
            console.print("[dim]Sound design skipped (create-sound-design skill not available)[/dim]")
    else:
        console.print("\n[dim]Skipping sound design phase (--skip-sound-design)[/dim]")

    # Phase 5: Assemble
    console.print("\n[bold]=== Phase 5: ASSEMBLE ===[/bold]")
    assemble_movie(assets_dir, output_path, output_format, fps=24)

    # Phase 6: Learn
    if enable_learnings:
        console.print("\n[bold]=== Phase 6: LEARN ===[/bold]")
        learn_scope = f"{persona}-filmmaking" if dream else "horus-filmmaking"
        store_learnings(work_path, scope=learn_scope, dry_run=False)

    # Persona: Archive Creation Session
    archive_creation_session(
        project_name=project.name,
        prompt=prompt,
        output_path=output_path,
        script_file=script_file,
        skip_casting=skip_casting,
        store_learnings_enabled=enable_learnings,
        duration=duration,
    )

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


cli = typer.Typer(help="create-movie: Orchestrated movie creation for Horus persona.")

cli.command("create")(create)
cli.command("research")(research)
cli.command("script")(script)
cli.command("build-tools")(build_tools)
cli.command("generate")(generate)
cli.command("assemble")(assemble)
cli.command("learn")(learn)
cli.command("study")(study)
cli.command("study-all")(study_all)

# Phase 3: Dream Integration
from dream import dream_group
cli.add_typer(dream_group, name="dream")

if __name__ == "__main__":
    cli()
