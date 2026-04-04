#!/usr/bin/env python3
"""
review-story: Multi-provider creative writing critique for Horus persona.

Analyzes stories across four dimensions:
- Structural: Plot, pacing, character arcs
- Emotional: Intended vs achieved emotion, ToM alignment
- Craft: Prose quality, dialogue, sensory details
- Persona: Horus voice consistency, tactical masks

Integrates with Federated Taxonomy for multi-hop graph traversal.
"""

import os
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Memory integration (graceful degradation)
try:
    from memory_integration import recall_prior_critiques, learn_critique
    _HAS_MEMORY_INTEGRATION = True
except ImportError:
    _HAS_MEMORY_INTEGRATION = False

console = Console()

# Import taxonomy extraction (with fallback)
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "taxonomy"))
    from taxonomy import extract_taxonomy
except ImportError:
    def extract_taxonomy(text: str, collection: str = "lore", fast: bool = True) -> dict[str, Any]:
        """Fallback taxonomy extraction using keywords."""
        text_lower = text.lower()
        bridge_tags = []

        # Simple keyword matching
        if any(w in text_lower for w in ["efficien", "precis", "calculat", "method"]):
            bridge_tags.append("Precision")
        if any(w in text_lower for w in ["endur", "resili", "withstand", "fault"]):
            bridge_tags.append("Resilience")
        if any(w in text_lower for w in ["brittle", "fragile", "weakness"]):
            bridge_tags.append("Fragility")
        if any(w in text_lower for w in ["corrupt", "taint", "warp", "chaos"]):
            bridge_tags.append("Corruption")
        if any(w in text_lower for w in ["loyal", "trust", "honor", "oath"]):
            bridge_tags.append("Loyalty")
        if any(w in text_lower for w in ["hidden", "stealth", "subterfuge"]):
            bridge_tags.append("Stealth")

        return {
            "bridge_tags": bridge_tags,
            "collection_tags": {},
            "confidence": 0.3,
            "worth_remembering": len(bridge_tags) > 0
        }

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
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
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


cli = typer.Typer(help="review-story: Multi-provider creative writing critique.")


@cli.command()
def review(
    story_file: Path = typer.Argument(help="Path to story file"),
    provider: str = typer.Option("claude", help="Single provider (claude, codex, gemini, copilot)"),
    providers: Optional[str] = typer.Option(None, help="Comma-separated list for multi-provider review"),
    emotion: Optional[str] = typer.Option(None, help="Intended emotion (rage, sorrow, camaraderie, regret, anger)"),
    focus: Optional[str] = typer.Option(None, help="Dimensions to focus on (structural, emotional, craft, persona)"),
    validate_persona: bool = typer.Option(False, "--validate-persona", help="Validate against Horus voice patterns"),
    output_dir: str = typer.Option("review_output", help="Output directory"),
    output_format: str = typer.Option("json", "--format", help="Output format: json, markdown"),
):
    """Critique a story file."""

    story_path = story_file
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Read story content
    story_content = story_path.read_text()

    # Parse focus areas
    focus_list = focus.split(",") if focus else list(DIMENSIONS.keys())

    # Build provider list
    provider_list = providers.split(",") if providers else [provider]

    console.print(Panel(f"[bold blue]review-story[/bold blue]\n\nFile: {story_file}\nProviders: {', '.join(provider_list)}\nEmotion: {emotion or 'not specified'}\nFocus: {', '.join(focus_list)}"))

    # Pre-hook: Recall prior critiques for context
    if _HAS_MEMORY_INTEGRATION:
        prior_context = recall_prior_critiques(story_path.stem)
        if prior_context:
            console.print("[dim]Found prior critiques in memory[/dim]")

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

                # Extract taxonomy for multi-hop graph traversal
                # Combine story content with critique for richer tagging
                combined_text = f"{story_content[:1000]} {json.dumps(critique.get('emotional', {}))}"
                critique["taxonomy"] = extract_taxonomy(combined_text, collection="lore", fast=True)

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

            # Post-hook: Learn critique findings to memory
            if _HAS_MEMORY_INTEGRATION:
                try:
                    overall = result.get("overall", {})
                    structural = result.get("structural", {})
                    craft = result.get("craft", {})
                    learned = learn_critique(
                        title=story_path.stem,
                        genre=emotion or "",
                        provider=prov,
                        findings=result,
                        strengths=structural.get("strengths", []),
                        weaknesses=[
                            issue.get("issue", str(issue))
                            for issue in structural.get("issues", [])
                        ] + craft.get("issues", []),
                        score=overall.get("score"),
                    )
                    if learned:
                        console.print(f"[dim]Learned {len(learned)} entries to memory[/dim]")
                except Exception as e:
                    console.print(f"[dim]Memory learn skipped: {e}[/dim]")

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

    # Aggregate taxonomy tags from all critiques for multi-hop traversal
    all_bridge_tags: set[str] = set()
    all_collection_tags: dict[str, set[str]] = {}

    for critique in critiques:
        taxonomy = critique.get("taxonomy", {})
        for tag in taxonomy.get("bridge_tags", []):
            all_bridge_tags.add(tag)
        for dim, val in taxonomy.get("collection_tags", {}).items():
            if dim not in all_collection_tags:
                all_collection_tags[dim] = set()
            all_collection_tags[dim].add(val)

    synthesis["taxonomy"] = {
        "bridge_tags": list(all_bridge_tags),
        "collection_tags": {k: list(v) for k, v in all_collection_tags.items()},
        "confidence": sum(c.get("taxonomy", {}).get("confidence", 0) for c in critiques) / len(critiques) if critiques else 0,
        "worth_remembering": len(all_bridge_tags) > 0
    }

    return synthesis


@cli.command()
def compare(
    draft1: Path = typer.Argument(help="Path to first draft"),
    draft2: Path = typer.Argument(help="Path to second draft"),
    dimension: str = typer.Option("all", help="Dimension to compare"),
):
    """Compare two drafts."""
    console.print(f"[bold]Comparing drafts...[/bold]")
    console.print(f"  Draft 1: {draft1}")
    console.print(f"  Draft 2: {draft2}")
    console.print(f"  Dimension: {dimension}")
    raise NotImplementedError("compare command not yet implemented")


@cli.command()
def synthesize(
    critique_files: list[Path] = typer.Argument(help="Critique JSON files to synthesize"),
    output: str = typer.Option("synthesis.json", help="Output file"),
):
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
