"""
Persona relationship and export/import CLI commands.
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
    PersonaRelationship,
    create_persona,
    get_persona,
    list_personas,
    update_persona,
    delete_persona,
    create_relationship,
    get_relationships,
    run_skill,
)
from .templates import (
    TEMPLATES,
    get_template,
    get_template_names,
    get_default_scope,
    should_auto_learn,
    get_default_bridges,
)
from .interview import create_persona_interactively
from .research import enrich_persona_with_colleagues


# =============================================================================
# Relate Command
# =============================================================================

@app.command()
def relate(
    name: str = typer.Argument(..., help="Persona name"),
    colleague: Optional[str] = typer.Option(None, "--colleague", help="Add colleague"),
    reports_to: Optional[str] = typer.Option(None, "--reports-to", help="Reports to"),
    manages: Optional[str] = typer.Option(None, "--manages", help="Manages"),
    mentors: Optional[str] = typer.Option(None, "--mentors", help="Mentors"),
    bridges: Optional[str] = typer.Option(None, "--bridges", help="Shared bridges (comma-separated)"),
    context: Optional[str] = typer.Option(None, "--context", help="Relationship context"),
    scope: Optional[str] = typer.Option("personas", "--scope", "-s", help="Memory scope"),
):
    """Create relationship between personas."""
    # Determine relationship type and target
    if colleague:
        rel_type, target = "colleague", colleague
    elif reports_to:
        rel_type, target = "reports_to", reports_to
    elif manages:
        rel_type, target = "manages", manages
    elif mentors:
        rel_type, target = "mentors", mentors
    else:
        console.print("[red]Specify a relationship: --colleague, --reports-to, --manages, or --mentors[/red]")
        raise typer.Exit(1)

    # Parse bridges
    bridge_list = []
    if bridges:
        bridge_list = [b.strip() for b in bridges.split(",")]

    # Create relationship
    rel = PersonaRelationship(
        from_persona=name,
        to_persona=target,
        relationship=rel_type,
        bridges=bridge_list,
        context=context or "",
    )

    if create_relationship(rel, scope):
        console.print(f"[green]Created relationship: {name} → {target} ({rel_type})[/green]")
        if bridge_list:
            console.print(f"  Shared bridges: {', '.join(bridge_list)}")
    else:
        console.print("[red]Failed to create relationship[/red]")
        raise typer.Exit(1)


# =============================================================================
# Export/Import Commands
# =============================================================================

@app.command("export")
def export_cmd(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    format: str = typer.Option("json", "--format", "-f", help="Output format"),
    with_relationships: bool = typer.Option(True, "--with-relationships", help="Include relationships"),
):
    """Export a persona."""
    # Find persona
    scopes_to_search = [scope] if scope else ["personas", "clients", "behavioral", "stakeholders"]
    persona = None
    for s in scopes_to_search:
        persona = get_persona(name, s)
        if persona:
            break

    if not persona:
        console.print(f"[red]Persona '{name}' not found[/red]", err=True)
        raise typer.Exit(1)

    data = persona.to_dict()

    if with_relationships:
        relationships = get_relationships(name, persona.scope)
        data["_relationships"] = [r.to_dict() for r in relationships]

    print(json.dumps(data, indent=2))


@app.command("import")
def import_cmd(
    file: Path = typer.Argument(..., help="JSON file to import"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Override scope"),
):
    """Import a persona from JSON."""
    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    data = json.loads(file.read_text())

    # Extract relationships
    relationships = data.pop("_relationships", [])

    # Create persona
    persona = Persona.from_dict(data)
    if scope:
        persona.scope = scope

    if create_persona(persona, store=True):
        console.print(f"[green]Imported persona: {persona.name}[/green]")

        # Import relationships
        for rel_data in relationships:
            rel = PersonaRelationship(**rel_data)
            create_relationship(rel, persona.scope)
            console.print(f"  Imported relationship: {rel.from_persona} → {rel.to_persona}")
    else:
        console.print("[red]Failed to import persona[/red]")
        raise typer.Exit(1)
