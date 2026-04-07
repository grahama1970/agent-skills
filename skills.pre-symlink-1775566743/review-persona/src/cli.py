#!/usr/bin/env python3
"""
review-persona CLI - Character realism and voice casting review.

Usage:
    python -m src.cli review persona.yaml
    python -m src.cli review persona.yaml --images ./casting/
    python -m src.cli deep-review persona.yaml --research-focus voice,domain
    python -m src.cli check persona.yaml
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer

from .review import (
    PersonaReview,
    load_persona_yaml,
    review_persona,
    review_persona_visual,
    deep_review_persona,
    quick_check_persona,
)

from loguru import logger as log

app = typer.Typer(help="Persona review for character realism and voice casting")


@app.command()
def review(
    persona_file: Path = typer.Argument(..., help="Path to persona YAML file"),
    provider: str = typer.Option("claude", "--provider", "-p", help="LLM provider"),
    focus: str = typer.Option("", "--focus", "-f", help="Dimensions to focus on (comma-separated)"),
    character_sheet: Optional[Path] = typer.Option(None, "--character-sheet", "-c", help="Character document"),
    images: Optional[Path] = typer.Option(None, "--images", "-i", help="Directory with casting images"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Review a persona for realism, voice casting, and domain accuracy."""
    if not persona_file.exists():
        typer.echo(f"Error: Persona file not found: {persona_file}", err=True)
        raise typer.Exit(1)

    focus_dims = [f.strip() for f in focus.split(",")] if focus else None

    typer.echo(f"Reviewing persona: {persona_file}")

    result = review_persona(
        persona_path=persona_file,
        character_sheet_path=character_sheet,
        images_dir=images,
        provider=provider,
        focus_dimensions=focus_dims,
    )

    if json_output:
        output_text = json.dumps(result.to_dict(), indent=2)
    else:
        output_text = result.to_markdown()

    if output:
        output.write_text(output_text)
        typer.echo(f"Review saved to: {output}")
    else:
        typer.echo(output_text)


@app.command("deep-review")
def deep_review(
    persona_file: Path = typer.Argument(..., help="Path to persona YAML file"),
    research_focus: str = typer.Option("voice,domain,role", "--research-focus", "-r", help="What to research"),
    provider: str = typer.Option("claude", "--provider", "-p", help="LLM provider"),
    character_sheet: Optional[Path] = typer.Option(None, "--character-sheet", "-c", help="Character document"),
    images: Optional[Path] = typer.Option(None, "--images", "-i", help="Directory with casting images"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Deep review with /dogpile research for validation."""
    if not persona_file.exists():
        typer.echo(f"Error: Persona file not found: {persona_file}", err=True)
        raise typer.Exit(1)

    focus_areas = [f.strip() for f in research_focus.split(",")]

    typer.echo(f"Deep reviewing persona: {persona_file}")
    typer.echo(f"Research focus: {', '.join(focus_areas)}")

    result = deep_review_persona(
        persona_path=persona_file,
        character_sheet_path=character_sheet,
        images_dir=images,
        research_focus=focus_areas,
        provider=provider,
    )

    if json_output:
        output_text = json.dumps(result.to_dict(), indent=2)
    else:
        output_text = result.to_markdown()

    if output:
        output.write_text(output_text)
        typer.echo(f"Deep review saved to: {output}")
    else:
        typer.echo(output_text)


@app.command()
def check(
    persona_file: Path = typer.Argument(..., help="Path to persona YAML file"),
):
    """Quick sanity check for required fields and valid values."""
    if not persona_file.exists():
        typer.echo(f"Error: Persona file not found: {persona_file}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Checking persona: {persona_file}")

    issues = quick_check_persona(persona_file)

    if not issues:
        typer.echo("✓ All checks passed!")
        raise typer.Exit(0)
    else:
        typer.echo(f"Found {len(issues)} issues:")
        for issue in issues:
            typer.echo(f"  ⚠ {issue}")
        raise typer.Exit(1)


@app.command("review-visual")
def review_visual(
    persona_file: Path = typer.Argument(..., help="Path to persona YAML file"),
    images: Path = typer.Option(..., "--images", "-i", help="Directory with casting images"),
    provider: str = typer.Option("claude", "--provider", "-p", help="Vision-capable provider"),
    character_sheet: Optional[Path] = typer.Option(None, "--character-sheet", "-c", help="Character document"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Vision-based review of casting images against character sheet."""
    if not persona_file.exists():
        typer.echo(f"Error: Persona file not found: {persona_file}", err=True)
        raise typer.Exit(1)

    if not images.exists():
        typer.echo(f"Error: Images directory not found: {images}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Visual review of: {persona_file}")
    typer.echo(f"Images: {images}")

    result = review_persona_visual(
        persona_path=persona_file,
        images_dir=images,
        character_sheet_path=character_sheet,
        provider=provider,
    )

    if json_output:
        output_text = json.dumps(result.to_dict(), indent=2)
    else:
        output_text = result.to_markdown()

    if output:
        output.write_text(output_text)
        typer.echo(f"Visual review saved to: {output}")
    else:
        typer.echo(output_text)


@app.command("compare-voice")
def compare_voice(
    persona_file: Path = typer.Argument(..., help="Path to persona YAML file"),
    find_alternatives: bool = typer.Option(False, "--find-alternatives", help="Search for alternative voice refs"),
    validate_blend: bool = typer.Option(True, "--validate-blend", help="Check if blend makes sense"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
):
    """Validate voice casting choices for the persona."""
    if not persona_file.exists():
        typer.echo(f"Error: Persona file not found: {persona_file}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Validating voice casting for: {persona_file}")

    # Load persona and validate voice references
    persona = load_persona_yaml(persona_file)
    voice_refs = persona.get("voice_references", [])

    if not voice_refs:
        typer.echo("⚠ No voice references defined in persona")
        raise typer.Exit(1)

    # Check blend weights
    total_weight = sum(ref.get("weight", 0) for ref in voice_refs)
    typer.echo(f"\nVoice References ({len(voice_refs)}):")
    for ref in voice_refs:
        typer.echo(f"  - {ref.get('name', 'Unknown')} ({ref.get('register', 'neutral')}): {ref.get('weight', 0):.0%}")

    if validate_blend:
        if abs(total_weight - 1.0) > 0.1:
            typer.echo(f"\n⚠ Weights sum to {total_weight:.0%}, should be ~100%")
        else:
            typer.echo(f"\n✓ Weights sum correctly: {total_weight:.0%}")

    if find_alternatives:
        typer.echo("\nSearching for alternative voice references...")
        # This would use /dogpile to find alternatives
        typer.echo("  (Not implemented yet - use /dogpile manually)")


if __name__ == "__main__":
    app()
