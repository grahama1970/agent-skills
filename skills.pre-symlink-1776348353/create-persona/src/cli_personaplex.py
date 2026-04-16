"""
PersonaPlex integration CLI commands for real-time conversation.
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from loguru import logger as log

from .cli_app import app, console

from .persona import (
    get_persona,
    list_personas,
)
from .personaplex import (
    PersonaPlexConfig,
    VoicePrompt,
    EmotionalState,
    load_emotional_mannerisms,
    save_emotional_mannerisms,
    extract_voice_prompts_from_references,
    personaplex_status,
    setup_personaplex,
    detect_register,
)

# =============================================================================
# PersonaPlex Command Group (Full-Duplex Speech-to-Speech)
# =============================================================================

personaplex_app = typer.Typer(help="PersonaPlex integration for real-time conversation")
app.add_typer(personaplex_app, name="personaplex")


@personaplex_app.command("status")
def personaplex_status_cmd(
    name: str = typer.Argument(..., help="Persona name"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Check PersonaPlex setup status for a persona.

    Shows readiness of:
    - Emotional mannerism config
    - Voice prompts (.pt files)
    - Text prompts

    Examples:
        ./run.sh personaplex status "Embry"
    """
    status = personaplex_status(name)

    if as_json:
        console.print(json.dumps(status, indent=2))
        return

    console.print(f"\n[bold]PersonaPlex Status: {name}[/bold]")
    console.print()

    # Overall readiness
    ready_color = "green" if status["ready"] else "red"
    console.print(f"  Ready: [{ready_color}]{status['ready']}[/{ready_color}]")
    console.print()

    # Components
    console.print("[bold]Components:[/bold]")
    config_status = "[green]✓[/green]" if status["components"]["config"] else "[red]✗[/red]"
    prompts_status = "[green]✓[/green]" if status["components"]["text_prompts"] else "[red]✗[/red]"
    console.print(f"  {config_status} Emotional mannerisms config")
    console.print(f"  {prompts_status} Text prompts")

    # Voice prompts by register
    voice_prompts = status["components"]["voice_prompts"]
    if voice_prompts:
        console.print(f"  [green]✓[/green] Voice prompts:")
        for register, path in voice_prompts.items():
            console.print(f"      - {register}: {Path(path).name}")
    else:
        console.print(f"  [red]✗[/red] Voice prompts (none extracted)")

    # Config details
    if status.get("states_count"):
        console.print()
        console.print(f"  States defined: {status['states_count']}")
        console.print(f"  Config version: {status.get('config_version', 'unknown')}")

    # Issues
    if status["issues"]:
        console.print()
        console.print("[bold red]Issues:[/bold red]")
        for issue in status["issues"]:
            console.print(f"  [red]•[/red] {issue}")

    # Paths
    console.print()
    console.print("[bold]Paths:[/bold]")
    for name, path in status["paths"].items():
        console.print(f"  {name}: {path}")


@personaplex_app.command("extract-prompts")
def personaplex_extract_prompts(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option("personas", "--scope", "-s", help="Memory scope"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without extracting"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Extract PersonaPlex voice prompts (.pt) from reference actor clips.

    Uses the persona's voice_references to find and extract speaker embeddings
    for each register (confident, uncertain, etc.).

    Examples:
        ./run.sh personaplex extract-prompts "Embry"
        ./run.sh personaplex extract-prompts "Embry" --dry-run
    """
    from .fictional import VoiceReference

    # Get persona
    persona = get_persona(name, scope)
    if not persona:
        for s in ["personas", "behavioral", "clients"]:
            persona = get_persona(name, s)
            if persona:
                scope = s
                break

    if not persona:
        console.print(f"[red]Persona '{name}' not found[/red]")
        raise typer.Exit(1)

    # Check for voice references
    voice_refs = persona.voice_references
    if not voice_refs:
        console.print(f"[red]No voice references defined for {name}[/red]")
        console.print("[dim]Add voice references with: ./run.sh voice-ref \"{}\" --actor \"Actor Name\" --register confident[/dim]".format(name))
        raise typer.Exit(1)

    console.print(f"\n[bold]Extracting PersonaPlex Voice Prompts: {name}[/bold]")
    console.print(f"  References: {len(voice_refs)}")
    for ref in voice_refs:
        ref_name = ref.get("name", "unknown") if isinstance(ref, dict) else ref.name
        ref_reg = ref.get("register", "neutral") if isinstance(ref, dict) else ref.register
        console.print(f"    - {ref_name} ({ref_reg})")
    console.print()

    if dry_run:
        console.print("[dim][dry-run] Would extract voice prompts[/dim]")
        return

    # Extract
    result = extract_voice_prompts_from_references(
        persona_name=name,
        voice_references=voice_refs if isinstance(voice_refs[0], dict) else [v.to_dict() for v in voice_refs],
        dry_run=dry_run,
    )

    if as_json:
        console.print(json.dumps(result, indent=2))
        return

    # Show results
    if result.get("extracted"):
        console.print("[green]Extracted voice prompts:[/green]")
        for vp in result["extracted"]:
            console.print(f"  [green]✓[/green] {vp['name']} from {vp['source']}")
            console.print(f"      Path: {vp['file_path']}")
    else:
        console.print("[yellow]No voice prompts extracted[/yellow]")

    if result.get("failed"):
        console.print()
        console.print("[red]Failed:[/red]")
        for failure in result["failed"]:
            console.print(f"  [red]✗[/red] {failure['actor']} ({failure['register']}): {failure['error']}")


@personaplex_app.command("config")
def personaplex_config_cmd(
    name: str = typer.Argument(..., help="Persona name"),
    show_states: bool = typer.Option(False, "--states", help="Show emotional states"),
    show_vernacular: bool = typer.Option(False, "--vernacular", help="Show vernacular libraries"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    View PersonaPlex emotional mannerism configuration.

    Shows the state machine, vernacular libraries, and transition behaviors.

    Examples:
        ./run.sh personaplex config "Embry"
        ./run.sh personaplex config "Embry" --states
        ./run.sh personaplex config "Embry" --vernacular
    """
    from pathlib import Path as P

    slug = name.lower().replace(" ", "_")
    config_path = P(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media" / "personas" / slug / "personaplex" / "configs" / "emotional_mannerisms.yaml"

    if not config_path.exists():
        # Try alternate locations
        alt_path = P.home() / "personas" / slug / "personaplex" / "configs" / "emotional_mannerisms.yaml"
        if alt_path.exists():
            config_path = alt_path
        else:
            console.print(f"[red]Config not found: {config_path}[/red]")
            console.print("[dim]Create one with: ./run.sh personaplex setup \"{}\"[/dim]".format(name))
            raise typer.Exit(1)

    config = load_emotional_mannerisms(config_path)

    if as_json:
        console.print(json.dumps(config.to_dict(), indent=2))
        return

    console.print(f"\n[bold]PersonaPlex Config: {config.name}[/bold]")
    console.print(f"  Version: {config.version}")
    console.print(f"  Model: {config.model}")
    console.print(f"  Default voice: {config.default_voice}")
    console.print()

    # Voice prompts
    console.print("[bold]Voice Prompts:[/bold]")
    for key, prompt in config.voice_prompts.items():
        console.print(f"  {key}:")
        console.print(f"    File: {prompt.file_path}")
        console.print(f"    Source: {prompt.source}")
        if prompt.characteristics:
            console.print(f"    Traits: {', '.join(prompt.characteristics)}")

    # Emotional states
    if show_states or not (show_vernacular):
        console.print()
        console.print(f"[bold]Emotional States ({len(config.states)}):[/bold]")
        for state in config.states:
            console.print(f"  [bold]{state.name}[/bold] (voice: {state.voice})")
            if state.triggers.get("keywords"):
                console.print(f"    Keywords: {', '.join(state.triggers['keywords'][:5])}")
            if state.triggers.get("context"):
                console.print(f"    Context: {', '.join(state.triggers['context'][:3])}")
            if state.behavior:
                console.print(f"    Behavior: {', '.join(f'{k}={v}' for k, v in list(state.behavior.items())[:3])}")
            if state.example:
                console.print(f"    Example: \"{state.example}\"")

    # Vernacular
    if show_vernacular:
        console.print()
        console.print("[bold]Vernacular Libraries:[/bold]")
        for origin, phrases in config.vernacular.items():
            console.print(f"  [bold]{origin}[/bold] ({len(phrases)} phrases)")
            for phrase in phrases[:5]:
                weight_color = (
                    "dim" if phrase.emotional_weight == "none" else
                    "yellow" if phrase.emotional_weight == "high_hurts" else
                    "red" if phrase.emotional_weight == "critical_never_say" else
                    "white"
                )
                console.print(f"    [{weight_color}]\"{phrase.phrase}\"[/{weight_color}] = {phrase.meaning}")
            if len(phrases) > 5:
                console.print(f"    ... and {len(phrases) - 5} more")

    # Transitions
    if config.transitions:
        console.print()
        console.print(f"[bold]Transitions ({len(config.transitions)}):[/bold]")
        for trans in config.transitions[:3]:
            if isinstance(trans, dict):
                console.print(f"  {trans.get('trigger_detection', 'unknown')}")


@personaplex_app.command("test-register")
def personaplex_test_register(
    name: str = typer.Argument(..., help="Persona name"),
    text: str = typer.Option(..., "--text", "-t", help="Text to analyze"),
    time_of_day: Optional[str] = typer.Option(None, "--time", help="Time of day (HH:MM)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Test which emotional register would be activated for given input.

    Analyzes the text against trigger keywords and context to determine
    which voice register should be used.

    Examples:
        ./run.sh personaplex test-register "Embry" --text "Tell me about the SPARTA controls"
        ./run.sh personaplex test-register "Embry" --text "How are you?" --time "23:30"
    """
    from pathlib import Path as P
    from datetime import datetime

    slug = name.lower().replace(" ", "_")
    config_path = P(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media" / "personas" / slug / "personaplex" / "configs" / "emotional_mannerisms.yaml"

    if not config_path.exists():
        console.print(f"[red]Config not found for {name}[/red]")
        raise typer.Exit(1)

    config = load_emotional_mannerisms(config_path)

    # Build context
    context = {}
    if time_of_day:
        try:
            hour, minute = map(int, time_of_day.split(":"))
            context["time"] = datetime.now().replace(hour=hour, minute=minute)
        except ValueError:
            console.print(f"[yellow]Invalid time format: {time_of_day}. Use HH:MM[/yellow]")

    # Detect register
    register = detect_register(text, context, config)

    # Find matching state
    matching_state = None
    for state in config.states:
        if state.voice == register:
            matching_state = state
            break

    if as_json:
        console.print(json.dumps({
            "input_text": text,
            "detected_register": register,
            "matching_state": matching_state.name if matching_state else None,
            "context": {k: str(v) for k, v in context.items()},
        }, indent=2))
        return

    console.print(f"\n[bold]Register Detection: {name}[/bold]")
    console.print(f"  Input: \"{text[:60]}...\"" if len(text) > 60 else f"  Input: \"{text}\"")
    if context.get("time"):
        console.print(f"  Time: {context['time'].strftime('%H:%M')}")
    console.print()

    console.print(f"  [bold]Detected Register:[/bold] [cyan]{register}[/cyan]")

    if matching_state:
        console.print(f"  [bold]State:[/bold] {matching_state.name}")
        if matching_state.behavior:
            console.print(f"  [bold]Behavior:[/bold]")
            for k, v in matching_state.behavior.items():
                console.print(f"    - {k}: {v}")
        if matching_state.vernacular:
            console.print(f"  [bold]Unlocked vernacular:[/bold] {', '.join(matching_state.vernacular[:3])}")
        if matching_state.example:
            console.print(f"  [bold]Example:[/bold] \"{matching_state.example}\"")


@personaplex_app.command("setup")
def personaplex_setup_cmd(
    name: str = typer.Argument(..., help="Persona name"),
    character_sheet: Optional[Path] = typer.Option(None, "--character-sheet", "-c", help="Path to character sheet"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Full PersonaPlex setup for a fictional persona.

    Orchestrates:
    1. Loading character sheet
    2. Extracting voice prompts from references
    3. Creating emotional mannerism config
    4. Creating text prompts

    Examples:
        ./run.sh personaplex setup "Embry" --character-sheet /path/to/embry.yaml
        ./run.sh personaplex setup "Embry" --dry-run
    """
    # Get persona for voice references
    persona = None
    for s in ["personas", "behavioral", "clients"]:
        persona = get_persona(name, s)
        if persona:
            break

    voice_refs = persona.voice_references if persona else None

    result = setup_personaplex(
        persona_name=name,
        voice_references=voice_refs,
        character_sheet_path=str(character_sheet) if character_sheet else None,
        dry_run=dry_run,
    )

    if as_json:
        console.print(json.dumps(result, indent=2))
        return

    console.print(f"\n[bold]PersonaPlex Setup: {name}[/bold]")
    console.print(f"  Status: {result['status']}")
    console.print()

    if result.get("steps_completed"):
        console.print("[green]Completed:[/green]")
        for step in result["steps_completed"]:
            console.print(f"  [green]✓[/green] {step}")

    if result.get("voice_prompts"):
        console.print()
        console.print("[green]Voice prompts extracted:[/green]")
        for vp in result["voice_prompts"]:
            console.print(f"  - {vp['name']}")

    if result.get("errors"):
        console.print()
        console.print("[red]Errors:[/red]")
        for error in result["errors"]:
            console.print(f"  [red]✗[/red] {error}")

