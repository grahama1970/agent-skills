#!/usr/bin/env python3
"""
Voice design workflow for personas without source material.

Uses /interview skill for collaborative voice design when we don't know
what someone sounded like (historical figures, obscure experts).

Gathers:
- Geographic origin (accent basis)
- Time period (speech patterns)
- Historical events (emotional coloring)
- Personality traits (pacing, energy)
- Modern voice references (training targets)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
import typer
from loguru import logger

console = Console()

SKILLS_DIR = Path(__file__).parent.parent
VOICE_STORAGE = Path(os.environ.get("VOICE_STORAGE", "/mnt/storage12tb/media/personas"))

# Re-export all public names from submodules for backward compatibility
from design_constants import (
    SUPPRESSION_INDICATORS,
    GRIEF_PROCESSING_MARKERS,
    CULTURAL_EMOTIONAL_NORMS,
    ACCENT_DATABASE,
)
from design_questions import generate_interview_questions
from design_guidance import generate_tts_guidance
from design_processing import process_interview_results


def run_interview(persona: str, mode: str = "auto") -> Optional[dict]:
    """Run the voice design interview using /interview skill."""
    questions = generate_interview_questions(persona)

    # Write questions to temp file
    questions_file = Path(f"/tmp/voice_design_{persona.lower().replace(' ', '_')}.json")
    with open(questions_file, "w") as f:
        json.dump(questions, f, indent=2)

    console.print(f"[dim]Interview questions saved to {questions_file}[/dim]")

    # Run interview skill
    interview_skill = SKILLS_DIR / "interview" / "run.sh"

    if not interview_skill.exists():
        console.print("[yellow]Interview skill not found, using fallback prompts[/yellow]")
        return run_fallback_interview(persona, questions)

    result = subprocess.run(
        [str(interview_skill), "--mode", mode, "--file", str(questions_file)],
        capture_output=True, text=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    if result.returncode != 0:
        console.print(f"[red]Interview failed: {result.stderr}[/red]")
        return None

    # Parse response
    try:
        response_file = Path(f"/tmp/voice_design_{persona.lower().replace(' ', '_')}_response.json")
        if response_file.exists():
            with open(response_file) as f:
                return json.load(f)
    except Exception as e:
        logger.debug("JSON parse failed: {}", e)

    return None


def run_fallback_interview(persona: str, questions: dict) -> dict:
    """Simple CLI fallback if interview skill unavailable."""
    from rich.prompt import Prompt

    console.print(Panel(f"[bold]Voice Design: {persona}[/bold]", style="blue"))
    console.print("[dim]Interview skill not available, using simple prompts[/dim]\n")

    responses = {}

    for q in questions["questions"]:
        console.print(f"\n[bold]{q['text']}[/bold]")
        for i, opt in enumerate(q["options"], 1):
            console.print(f"  {i}. {opt['label']}: [dim]{opt['description']}[/dim]")

        if q.get("multi_select"):
            answer = Prompt.ask("Enter numbers (comma-separated)")
            indices = [int(x.strip()) - 1 for x in answer.split(",") if x.strip().isdigit()]
            responses[q["id"]] = [q["options"][i]["label"] for i in indices if 0 <= i < len(q["options"])]
        else:
            answer = Prompt.ask("Enter number")
            idx = int(answer) - 1 if answer.isdigit() else 0
            if 0 <= idx < len(q["options"]):
                responses[q["id"]] = q["options"][idx]["label"]

    return {"responses": responses}


def save_voice_design(persona: str, design: dict):
    """Save voice design to persona directory."""
    slug = persona.lower().replace(" ", "_")
    persona_dir = VOICE_STORAGE / slug
    persona_dir.mkdir(parents=True, exist_ok=True)

    design_file = persona_dir / "voice_design.json"
    with open(design_file, "w") as f:
        json.dump(design, f, indent=2)

    console.print(f"\n[green]Voice design saved: {design_file}[/green]")
    return design_file


def main(
    persona: str = typer.Argument(..., help="Persona name"),
    mode: str = typer.Option("auto", help="Interview mode (tui/html/auto)"),
    output: Optional[str] = typer.Option(None, help="Output file path"),
    skip_train: bool = typer.Option(False, help="Don"),
):

    console.print(Panel(f"[bold]Voice Design: {persona}[/bold]", style="blue"))
    console.print(
        f"Since no recordings exist for {persona}, we'll collaboratively "
        "design their voice based on background, era, and personality.\n"
    )

    # Run interview
    responses = run_interview(persona, mode)

    if not responses:
        console.print("[red]Interview incomplete or cancelled[/red]")
        sys.exit(1)

    # Process responses
    design = process_interview_results(persona, responses)

    # Display summary
    console.print("\n[bold]Voice Design Summary[/bold]")
    vd = design["voice_design"]
    console.print(f"  Origin: {vd['geographic_origin']}")
    console.print(f"  Era: {vd['time_period']}")
    console.print(f"  Class: {vd['social_class']}")
    console.print(f"  Personality: {', '.join(vd['personality'])}")
    console.print(f"  Voice Coloring: {vd['voice_coloring']}")
    console.print(f"  Inferred Accent: {vd.get('inferred_accent', 'Unknown')}")
    console.print(f"  Modern References: {', '.join(vd['modern_reference'])}")

    if vd["historical_context"]["major_events"]:
        console.print(f"  Shaping Events: {', '.join(vd['historical_context']['major_events'])}")

    # Save design
    design_file = save_voice_design(persona, design)

    if output:
        with open(output, "w") as f:
            json.dump(design, f, indent=2)
        console.print(f"[dim]Also saved to: {output}[/dim]")

    # Offer to proceed with training
    if not skip_train and vd.get("modern_reference"):
        console.print("\n")
        if Confirm.ask("Download reference clips from suggested actors and proceed to training?"):
            refs = ",".join(f"{ref}:default" for ref in vd["modern_reference"][:2])
            raise NotImplementedError(
                f"Auto-training not yet implemented. Run manually: ./run.sh train \"{persona}\" --references \"{refs}\""
            )


if __name__ == "__main__":
    main()
