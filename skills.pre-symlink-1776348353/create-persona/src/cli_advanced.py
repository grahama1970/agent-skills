"""
Advanced persona CLI commands: BDI (Theory of Mind), bridges, route.
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
    Persona,
    get_persona,
    create_persona,
)
from .persona_router import (
    route_question,
    format_routing_result,
)

# =============================================================================
# BDI (Theory of Mind) Command
# =============================================================================

@app.command()
def bdi(
    name: str = typer.Argument(..., help="Persona name"),
    user_id: str = typer.Option("default", "--user", "-u", help="User ID for relationship"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    show_history: bool = typer.Option(False, "--history", help="Show mood history"),
    reset: bool = typer.Option(False, "--reset", help="Reset BDI state"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    View and manage Theory of Mind (BDI) state for a persona.

    Shows the Belief-Desire-Intention model and mood state for
    persona-user relationships. Based on Horus persona architecture.

    Examples:
        ./run.sh bdi "Hayao Miyazaki" --user graham
        ./run.sh bdi "Hayao Miyazaki" --history
        ./run.sh bdi "Hayao Miyazaki" --reset
    """
    from .theory_of_mind import (
        get_or_create_bdi_state,
        save_bdi_state,
        BDIState,
        MOODS,
    )

    scope = scope or "personas"

    if reset:
        # Create fresh state
        state = BDIState(persona_name=name, user_id=user_id)
        save_bdi_state(state, scope)
        console.print(f"[green]Reset BDI state for {name} <-> {user_id}[/green]")
        return

    state = get_or_create_bdi_state(name, user_id, scope)

    if as_json:
        console.print(json.dumps(state.to_dict(), indent=2))
        return

    # Rich output
    console.print(f"\n[bold]Theory of Mind: {state.persona_name}[/bold]")
    console.print(f"  User: {state.user_id}")
    console.print(f"  Interactions: {state.interaction_count}")
    console.print()

    # Current mood
    mood_desc = MOODS.get(state.current_mood, "Unknown")
    console.print(f"  [bold]Current Mood:[/bold] {state.current_mood}")
    console.print(f"    [dim]{mood_desc}[/dim]")
    console.print()

    # Relationship metrics
    console.print("[bold]Relationship Metrics:[/bold]")
    for metric, value in [
        ("Trust", state.trust_level),
        ("Respect", state.respect_level),
    ]:
        bar = "█" * int(value * 10) + "░" * (10 - int(value * 10))
        color = "green" if value >= 0.7 else "yellow" if value >= 0.4 else "red"
        console.print(f"  {metric:10} [{bar}] [{color}]{value:.1f}[/{color}]")
    console.print()

    # Beliefs about user
    if state.beliefs:
        console.print("[bold]Beliefs about User:[/bold]")
        for belief, confidence in state.beliefs.items():
            bar = "█" * int(confidence * 10) + "░" * (10 - int(confidence * 10))
            console.print(f"  {belief:20} [{bar}] {confidence:.2f}")
        console.print()

    # Current desires/intentions
    if state.desires:
        console.print("[bold]User Desires:[/bold]")
        for desire in state.desires:
            console.print(f"  • {desire}")
        console.print()

    if state.intentions:
        console.print("[bold]User Intentions:[/bold]")
        for intention in state.intentions:
            console.print(f"  • {intention}")
        console.print()

    # Mood history
    if show_history and state.mood_history:
        console.print("[bold]Mood History:[/bold]")
        for i, mood in enumerate(state.mood_history[-10:], 1):
            console.print(f"  {i}. {mood}")
        console.print()

    # Edges created
    if state.edges:
        console.print(f"[bold]BDI Edges:[/bold] {len(state.edges)} edges created")

    console.print(f"\n[dim]Last interaction: {state.last_interaction[:19]}[/dim]")


# =============================================================================
# Bridges Command
# =============================================================================

@app.command()
def bridges(
    name: Optional[str] = typer.Argument(None, help="Persona name (omit for list)"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    add: Optional[str] = typer.Option(None, "--add", "-a", help="Add bridge (name:weight)"),
    extract_from: Optional[str] = typer.Option(None, "--extract-from", help="Extract bridges from text"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    View and manage Federated Taxonomy bridges for personas.

    Bridges enable cross-domain reasoning:
    - Precision: Methodical, optimized approaches
    - Resilience: Endurance, fault tolerance
    - Fragility: Vulnerability, emotional depth
    - Corruption: Decay, moral compromise
    - Loyalty: Honor, duty, trust
    - Stealth: Hidden, subtle, deceptive

    Examples:
        ./run.sh bridges                          # Show all bridges
        ./run.sh bridges "Hayao Miyazaki"        # Show persona's bridges
        ./run.sh bridges "Miyazaki" --add Fragility:0.8
        ./run.sh bridges --extract-from "His work endures through careful attention to detail"
    """
    from .theory_of_mind import BRIDGE_ATTRIBUTES, extract_bridges

    scope = scope or "personas"

    # Just show bridge definitions
    if not name and not extract_from:
        if as_json:
            console.print(json.dumps(BRIDGE_ATTRIBUTES, indent=2))
            return

        console.print("\n[bold]Federated Taxonomy Bridges[/bold]")
        console.print("[dim]Cross-domain connectors for multi-hop reasoning[/dim]\n")

        for bridge, desc in BRIDGE_ATTRIBUTES.items():
            console.print(f"  [bold]{bridge}[/bold]")
            console.print(f"    {desc}")
        console.print()
        return

    # Extract bridges from text
    if extract_from:
        bridges_found = extract_bridges(extract_from)
        if as_json:
            console.print(json.dumps({"bridges": bridges_found, "text": extract_from[:100]}, indent=2))
            return

        console.print("\n[bold]Extracted Bridges:[/bold]")
        console.print(f"  Text: {extract_from[:80]}...")
        console.print(f"  Bridges: {', '.join(bridges_found) if bridges_found else 'None found'}")
        return

    # Show or modify persona bridges
    persona = get_persona(name, scope)
    if not persona:
        # Try other scopes
        for s in ["personas", "behavioral", "clients", "coders"]:
            persona = get_persona(name, s)
            if persona:
                scope = s
                break

    if not persona:
        console.print(f"[red]Persona '{name}' not found[/red]")
        raise typer.Exit(1)

    # Add bridge if specified
    if add:
        if ":" in add:
            b_name, b_weight = add.split(":", 1)
            persona.bridge_weights[b_name] = float(b_weight)
        else:
            persona.bridge_weights[add] = 0.7

        persona.update_timestamp()
        create_persona(persona, store=True)
        console.print(f"[green]Added bridge: {add}[/green]")

    if as_json:
        console.print(json.dumps({
            "name": persona.name,
            "bridges": persona.bridge_weights,
        }, indent=2))
        return

    console.print(f"\n[bold]Bridges: {persona.name}[/bold]")
    if persona.bridge_weights:
        for bridge, weight in persona.bridge_weights.items():
            bar = "█" * int(weight * 10) + "░" * (10 - int(weight * 10))
            desc = BRIDGE_ATTRIBUTES.get(bridge, "Custom bridge")
            console.print(f"  {bridge:12} [{bar}] {weight:.1f}")
            console.print(f"    [dim]{desc}[/dim]")
    else:
        console.print("  [dim]No bridges assigned[/dim]")
        console.print("  [dim]Use --add to add bridges[/dim]")



# =============================================================================
# Route Command (Bridge Classifier Routing)
# =============================================================================

@app.command()
def route(
    question: str = typer.Argument(..., help="Question to route to personas"),
    scope: str = typer.Option("personas", "--scope", "-s", help="Memory scope to search"),
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Bridge detection threshold"),
    overlap: float = typer.Option(0.4, "--overlap", "-o", help="Minimum bridge overlap score"),
    max_results: int = typer.Option(5, "--max", "-m", help="Max personas to return"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Route a question to relevant personas using the bridge classifier.

    Uses Federated Taxonomy bridges (Precision, Resilience, Fragility, etc.)
    to find both expected experts AND wildcard matches (serendipitous discovery).

    This is FAST (~4ms) - no LLM calls, just classifier inference.

    Examples:
        ./run.sh route "How does the 10ft ambient display look visually?"
        ./run.sh route "Is the typography readable at distance?" --scope personas
        ./run.sh route "Does the Discord notification feel trustworthy?" --json
    """
    result = route_question(
        question=question,
        scope=scope,
        bridge_threshold=threshold,
        min_overlap=overlap,
        max_results=max_results,
    )

    if as_json:
        output = {
            "question": result.question,
            "detected_bridges": result.detected_bridges,
            "expected": [
                {
                    "name": m.persona.name,
                    "role": m.persona.role,
                    "score": m.match_score,
                    "matched_bridges": m.matched_bridges,
                    "reason": m.reason,
                }
                for m in result.expected_matches
            ],
            "wildcards": [
                {
                    "name": m.persona.name,
                    "role": m.persona.role,
                    "score": m.match_score,
                    "matched_bridges": m.matched_bridges,
                    "reason": m.reason,
                }
                for m in result.wildcard_matches
            ],
            "routing_time_ms": result.routing_time_ms,
        }
        console.print(json.dumps(output, indent=2))
    else:
        console.print(format_routing_result(result))
        console.print()
        console.print(f"[dim]Routed in {result.routing_time_ms:.1f}ms (no LLM calls)[/dim]")

