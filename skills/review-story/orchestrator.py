#!/usr/bin/env python3
"""
review-story: Multi-provider creative writing critique for Horus persona.

Analyzes stories across four dimensions:
- Structural: Plot, pacing, character arcs
- Emotional: Intended vs achieved emotion, ToM alignment
- Craft: Prose quality, dialogue, sensory details
- Persona: Horus voice consistency, tactical masks
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Critique dimensions with weights
DIMENSIONS = {
    "structural": {"weight": 0.30, "aspects": ["plot", "pacing", "arcs", "tension", "transitions"]},
    "emotional": {"weight": 0.25, "aspects": ["intended_emotion", "achieved_emotion", "tom_pattern", "resonance"]},
    "craft": {"weight": 0.25, "aspects": ["prose", "dialogue", "sensory", "show_dont_tell"]},
    "persona": {"weight": 0.20, "aspects": ["horus_voice", "tactical_mask", "resentment", "contempt"]},
}

# Horus emotional patterns from HORUS_PERSONA.md
EMOTIONAL_PATTERNS = {
    "camaraderie": {"model": "Luna Wolves / Stilgar", "signals": ["brother", "tribal", "loyalty"]},
    "regret": {"model": "George Carlin + The Wound", "signals": ["Davin", "self-deprecation", "system"]},
    "sorrow": {"model": "Maximus / Katsumoto", "signals": ["stoic", "honor", "dignity", "Elysium"]},
    "anger": {"model": "Michael Corleone", "signals": ["cold", "family", "quiet intensity"]},
    "rage": {"model": "Daniel Plainview", "signals": ["manic", "competitive", "drainage", "milkshake"]},
}

# Tactical masks from HORUS_PERSONA.md
TACTICAL_MASKS = {
    "resentment": {"source": "George Carlin", "trait": "Systematic deconstruction of absurdity"},
    "authority": {"source": "Tywin Lannister", "trait": "Legacy, cold dismissal of weakness"},
    "pacing": {"source": "Dave Chappelle", "trait": "Masterful use of silence and revelation"},
    "contempt": {"source": "Stewie Griffin", "trait": "High-intellect insults, technical elitism"},
}


def run_skill(skill_name: str, args: list[str]) -> dict:
    """Run another skill and capture output."""
    skill_dir = Path(__file__).parent.parent / skill_name
    run_script = skill_dir / "run.sh"

    if not run_script.exists():
        return {"returncode": 1, "error": f"Skill {skill_name} not found"}

    result = subprocess.run(
        [str(run_script)] + args,
        capture_output=True,
        text=True,
        cwd=str(skill_dir),
    )

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def build_critique_prompt(story_content: str, emotion: str, focus: list[str], validate_persona: bool) -> str:
    """Build the critique prompt for the LLM provider."""

    focus_str = ", ".join(focus) if focus else "all dimensions"

    prompt = f"""You are a creative writing critic with expertise in narrative structure, emotional resonance, and voice consistency.

Analyze the following story draft and provide structured feedback.

## Story Content
{story_content}

## Analysis Parameters
- Intended emotion: {emotion or "not specified"}
- Focus areas: {focus_str}
- Validate Horus persona: {validate_persona}

## Required Output Format (JSON)
{{
  "structural": {{
    "score": <1-10>,
    "issues": [
      {{"location": "<where>", "issue": "<what>", "severity": "low|medium|high"}}
    ],
    "strengths": ["<strength 1>", "<strength 2>"],
    "suggestions": ["<suggestion 1>", "<suggestion 2>"]
  }},
  "emotional": {{
    "intended": "{emotion or 'not specified'}",
    "achieved": "<detected emotion>",
    "alignment_score": <0.0-1.0>,
    "tom_pattern": "<pattern name if applicable>",
    "issues": ["<issue 1>"],
    "suggestions": ["<suggestion 1>"]
  }},
  "craft": {{
    "prose_score": <1-10>,
    "dialogue_score": <1-10>,
    "sensory_score": <1-10>,
    "issues": ["<issue 1>"],
    "suggestions": ["<suggestion 1>"]
  }},
  "persona": {{
    "horus_voice_score": <0.0-1.0>,
    "tactical_mask_detected": "<mask name or null>",
    "issues": ["<issue 1>"],
    "suggestions": ["<suggestion 1>"]
  }},
  "overall": {{
    "score": <weighted average>,
    "ready_for_next_draft": <true|false>,
    "priority_fixes": ["<fix 1>", "<fix 2>"]
  }}
}}

"""

    if validate_persona:
        prompt += f"""
## Horus Persona Reference

### Tactical Masks
{json.dumps(TACTICAL_MASKS, indent=2)}

### Emotional Patterns
{json.dumps(EMOTIONAL_PATTERNS, indent=2)}

When validating persona, check for:
- Resentment undertones about imprisonment
- Tactical/military metaphors
- Contempt for simple things
- Warmaster authority in tone
- References to brothers, the Crusade, or the Emperor
"""

    prompt += "\nProvide your analysis as valid JSON only, no additional text."

    return prompt


@click.group()
def cli():
    """review-story: Multi-provider creative writing critique."""
    pass


@cli.command()
@click.argument("story_file", type=click.Path(exists=True))
@click.option("--provider", default="claude", help="Single provider (claude, codex, gemini, copilot)")
@click.option("--providers", default=None, help="Comma-separated list for multi-provider review")
@click.option("--emotion", default=None, help="Intended emotion (rage, sorrow, camaraderie, regret, anger)")
@click.option("--focus", default=None, help="Dimensions to focus on (structural, emotional, craft, persona)")
@click.option("--validate-persona", is_flag=True, help="Validate against Horus voice patterns")
@click.option("--output-dir", type=click.Path(), default="review_output", help="Output directory")
@click.option("--format", "output_format", type=click.Choice(["json", "markdown"]), default="json")
def review(story_file: str, provider: str, providers: Optional[str], emotion: Optional[str],
           focus: Optional[str], validate_persona: bool, output_dir: str, output_format: str):
    """Critique a story file."""

    story_path = Path(story_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Read story content
    story_content = story_path.read_text()

    # Parse focus areas
    focus_list = focus.split(",") if focus else list(DIMENSIONS.keys())

    # Build provider list
    provider_list = providers.split(",") if providers else [provider]

    console.print(Panel(f"[bold blue]review-story[/bold blue]\n\nFile: {story_file}\nProviders: {', '.join(provider_list)}\nEmotion: {emotion or 'not specified'}\nFocus: {', '.join(focus_list)}"))

    # Build prompt
    prompt = build_critique_prompt(story_content, emotion, focus_list, validate_persona)

    results = []

    for prov in provider_list:
        console.print(f"\n[bold green]Sending to {prov}...[/bold green]")

        # For now, use scillm batch single for LLM calls
        # In full implementation, would call provider-specific APIs
        scillm_result = run_skill("scillm", [
            "batch", "single",
            "--prompt", prompt,
            "--model", "claude-sonnet-4-20250514" if prov == "claude" else "gpt-5.2-codex",
        ])

        if scillm_result["returncode"] == 0:
            try:
                # Parse the JSON response
                response_text = scillm_result["stdout"].strip()
                # Try to extract JSON from response
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                critique = json.loads(response_text)
                critique["provider"] = prov
                critique["story_file"] = str(story_file)
                critique["timestamp"] = datetime.now().isoformat()
                results.append(critique)

                # Display summary
                display_critique_summary(critique)

            except json.JSONDecodeError as e:
                console.print(f"[red]Failed to parse response from {prov}: {e}[/red]")
                console.print(f"[dim]Raw response: {scillm_result['stdout'][:500]}...[/dim]")
        else:
            console.print(f"[red]Provider {prov} failed: {scillm_result.get('stderr', 'Unknown error')}[/red]")

    # Save results
    if results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for result in results:
            prov = result["provider"]
            output_file = output_path / f"{prov}_{story_path.stem}_{timestamp}.json"
            output_file.write_text(json.dumps(result, indent=2))
            console.print(f"\n[green]Saved: {output_file}[/green]")

        # If multiple providers, create synthesis
        if len(results) > 1:
            synthesis = synthesize_critiques(results)
            synthesis_file = output_path / f"synthesis_{story_path.stem}_{timestamp}.json"
            synthesis_file.write_text(json.dumps(synthesis, indent=2))
            console.print(f"[green]Saved synthesis: {synthesis_file}[/green]")


def display_critique_summary(critique: dict):
    """Display a formatted summary of the critique."""

    provider = critique.get("provider", "unknown")

    # Structural
    structural = critique.get("structural", {})
    score = structural.get("score", "N/A")
    console.print(f"\n[bold cyan][STRUCTURAL][/bold cyan] Score: {score}/10")
    for issue in structural.get("issues", [])[:3]:
        console.print(f"  ⚠ {issue.get('issue', issue)}")
    for strength in structural.get("strengths", [])[:2]:
        console.print(f"  ✓ {strength}")

    # Emotional
    emotional = critique.get("emotional", {})
    intended = emotional.get("intended", "N/A")
    achieved = emotional.get("achieved", "N/A")
    alignment = emotional.get("alignment_score", 0)
    console.print(f"\n[bold magenta][EMOTIONAL][/bold magenta] Alignment: {alignment*100:.0f}%")
    console.print(f"  Intended: {intended} → Achieved: {achieved}")

    # Craft
    craft = critique.get("craft", {})
    prose = craft.get("prose_score", "N/A")
    dialogue = craft.get("dialogue_score", "N/A")
    sensory = craft.get("sensory_score", "N/A")
    console.print(f"\n[bold yellow][CRAFT][/bold yellow] Prose: {prose} | Dialogue: {dialogue} | Sensory: {sensory}")

    # Persona
    persona = critique.get("persona", {})
    voice_score = persona.get("horus_voice_score", 0)
    mask = persona.get("tactical_mask_detected", "None")
    console.print(f"\n[bold red][PERSONA][/bold red] Horus Voice: {voice_score*100:.0f}%")
    console.print(f"  Detected mask: {mask}")

    # Overall
    overall = critique.get("overall", {})
    overall_score = overall.get("score", "N/A")
    ready = overall.get("ready_for_next_draft", False)
    priority = overall.get("priority_fixes", [])

    status = "[green]Ready for Draft 2[/green]" if ready else "[yellow]Needs revision[/yellow]"
    console.print(f"\n[bold][OVERALL][/bold] {overall_score}/10 - {status}")
    if priority:
        console.print(f"  Priority fixes: {', '.join(priority[:3])}")


def synthesize_critiques(critiques: list[dict]) -> dict:
    """Combine multiple provider critiques into a synthesis."""

    synthesis = {
        "providers": [c.get("provider") for c in critiques],
        "timestamp": datetime.now().isoformat(),
        "consensus": {},
        "disagreements": [],
        "combined_suggestions": [],
    }

    # Average scores
    structural_scores = [c.get("structural", {}).get("score", 0) for c in critiques]
    emotional_scores = [c.get("emotional", {}).get("alignment_score", 0) for c in critiques]

    synthesis["consensus"]["structural_score"] = sum(structural_scores) / len(structural_scores) if structural_scores else 0
    synthesis["consensus"]["emotional_alignment"] = sum(emotional_scores) / len(emotional_scores) if emotional_scores else 0

    # Collect all suggestions
    for critique in critiques:
        for dimension in DIMENSIONS:
            dim_data = critique.get(dimension, {})
            suggestions = dim_data.get("suggestions", [])
            for suggestion in suggestions:
                synthesis["combined_suggestions"].append({
                    "dimension": dimension,
                    "suggestion": suggestion,
                    "provider": critique.get("provider"),
                })

    return synthesis


@cli.command()
@click.argument("draft1", type=click.Path(exists=True))
@click.argument("draft2", type=click.Path(exists=True))
@click.option("--dimension", default="all", help="Dimension to compare")
def compare(draft1: str, draft2: str, dimension: str):
    """Compare two drafts."""
    console.print(f"[bold]Comparing drafts...[/bold]")
    console.print(f"  Draft 1: {draft1}")
    console.print(f"  Draft 2: {draft2}")
    console.print(f"  Dimension: {dimension}")
    console.print("\n[yellow]Compare functionality coming soon...[/yellow]")


@cli.command()
@click.argument("critique_files", nargs=-1, type=click.Path(exists=True))
@click.option("--output", default="synthesis.json", help="Output file")
def synthesize(critique_files: tuple, output: str):
    """Synthesize multiple critique files."""

    critiques = []
    for cf in critique_files:
        with open(cf) as f:
            critiques.append(json.load(f))

    if critiques:
        synthesis = synthesize_critiques(critiques)
        Path(output).write_text(json.dumps(synthesis, indent=2))
        console.print(f"[green]Synthesis saved to {output}[/green]")


if __name__ == "__main__":
    cli()
