"""
Core persona CLI commands: create, list, show, update, delete.
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
# Create Command
# =============================================================================

@app.command()
def create(
    name: str = typer.Argument(..., help="Persona name"),
    template: str = typer.Option("client", "--template", "-t", help="Template type"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Use /interview"),
    learn: bool = typer.Option(False, "--learn", "-l", help="Trigger /ask learn"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    role: Optional[str] = typer.Option(None, "--role", help="Job title or role"),
    organization: Optional[str] = typer.Option(None, "--organization", "--org", help="Organization"),
    domain: Optional[str] = typer.Option(None, "--domain", help="Domain of expertise"),
    goal: Optional[list[str]] = typer.Option(None, "--goal", "-g", help="Add goal (repeatable)"),
    concern: Optional[list[str]] = typer.Option(None, "--concern", "-c", help="Add concern (repeatable)"),
    colleague: Optional[list[str]] = typer.Option(None, "--colleague", help="Add colleague (repeatable)"),
    bridge: Optional[list[str]] = typer.Option(None, "--bridge", "-b", help="Add bridge weight (repeatable)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without storing"),
):
    """Create a new persona."""
    # Validate template
    if template not in get_template_names():
        console.print(f"[red]Unknown template: {template}[/red]")
        console.print(f"Available: {', '.join(get_template_names())}")
        raise typer.Exit(1)

    template_config = get_template(template)

    # Determine scope
    if scope is None:
        scope = get_default_scope(template)

    # Interactive mode
    if interactive:
        result = create_persona_interactively(name, template, scope, organization)
        if result is None:
            raise typer.Exit(1)
        persona, learn_depth = result
    else:
        # Direct creation
        persona = Persona(
            name=name,
            template=template,
            scope=scope,
            role=role or "",
            organization=organization or "",
            domain=domain or "",
            goals=goal or [],
            concerns=concern or [],
            tags=template_config.get("tags", []),
            communication_style=template_config.get("communication_style", ""),
            preferred_format=template_config.get("preferred_format", ""),
            bridge_weights=get_default_bridges(template),
        )
        learn_depth = "quick"

    # Add bridges if specified
    if bridge:
        for b in bridge:
            if ":" in b:
                name_part, weight = b.split(":", 1)
                try:
                    persona.bridge_weights[name_part] = float(weight)
                except ValueError:
                    persona.bridge_weights[b] = 0.7
            else:
                persona.bridge_weights[b] = 0.7

    # Output
    if as_json:
        console.print(persona.to_json())
    else:
        console.print(f"\n[bold]Creating persona: {persona.name}[/bold]")
        console.print(f"  Template: {template}")
        console.print(f"  Scope: {scope}")
        if persona.role:
            console.print(f"  Role: {persona.role}")
        if persona.organization:
            console.print(f"  Organization: {persona.organization}")
        if persona.domain:
            console.print(f"  Domain: {persona.domain}")
        if persona.goals:
            console.print(f"  Goals: {', '.join(persona.goals)}")
        if persona.concerns:
            console.print(f"  Concerns: {', '.join(persona.concerns)}")
        if persona.bridge_weights:
            bridges_str = ", ".join(f"{k}:{v:.1f}" for k, v in persona.bridge_weights.items())
            console.print(f"  Bridges: {bridges_str}")

    # Store
    if not dry_run:
        success = create_persona(persona, store=True)
        if success:
            console.print(f"\n[green]Persona stored to memory (scope: {scope})[/green]")
        else:
            console.print("\n[red]Failed to store persona[/red]")
            raise typer.Exit(1)

        # Create colleague relationships if specified
        if colleague:
            for coll_name in colleague:
                rel = PersonaRelationship(
                    from_persona=persona.name,
                    to_persona=coll_name,
                    relationship="colleague",
                    bridges=list(persona.bridge_weights.keys()),
                )
                create_relationship(rel, scope)
                console.print(f"  Added colleague: {coll_name}")

        # Auto-learn for expert template or if explicitly requested
        should_learn = learn or (should_auto_learn(template) and not dry_run)
        if should_learn:
            console.print(f"\n[bold]Triggering /ask learn for {persona.name}...[/bold]")

            # Note: .pi/skills/ask/learn.py uses subcommand interface
            learn_result = run_skill("ask", [
                "learn", "learn", persona.name,
                "--scope", scope,
                "--depth", learn_depth,
            ], timeout=300)

            if learn_result["returncode"] == 0:
                console.print("[green]Learning complete[/green]")

                # Check if sparse and enrich with colleagues
                if "sparse" in learn_result["stdout"].lower():
                    console.print("\n[dim]Persona data is sparse. Discovering colleagues...[/dim]")
                    colleagues = enrich_persona_with_colleagues(persona, scope)
                    if colleagues:
                        console.print(f"  Found {len(colleagues)} colleague(s) with quotable work")
            else:
                console.print(f"[yellow]Learning had issues: {learn_result['stderr'][:100]}[/yellow]")
    else:
        console.print("\n[dim][dry-run] Would store persona[/dim]")


# =============================================================================
# List Command
# =============================================================================

@app.command("list")
def list_cmd(
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Filter by scope"),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="Filter by template"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List personas."""
    personas = list_personas(scope=scope, template=template, tag=tag)

    if as_json:
        console.print(json.dumps([p.to_dict() for p in personas], indent=2))
        return

    if not personas:
        console.print("[dim]No personas found[/dim]")
        return

    table = Table(title="Personas")
    table.add_column("Name", style="bold")
    table.add_column("Template")
    table.add_column("Scope")
    table.add_column("Role")
    table.add_column("Organization")
    table.add_column("Goals")

    for p in personas:
        table.add_row(
            p.name,
            p.template or "-",
            p.scope,
            p.role or "-",
            p.organization or "-",
            str(len(p.goals)),
        )

    console.print(table)


# =============================================================================
# Show Command
# =============================================================================

@app.command()
def show(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    with_colleagues: bool = typer.Option(False, "--with-colleagues", help="Include colleagues"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Display persona details."""
    # Search multiple scopes if not specified
    scopes_to_search = [scope] if scope else ["personas", "clients", "behavioral", "stakeholders", "threat-models"]

    persona = None
    for s in scopes_to_search:
        persona = get_persona(name, s)
        if persona:
            break

    if not persona:
        console.print(f"[red]Persona '{name}' not found[/red]")
        raise typer.Exit(1)

    if as_json:
        data = persona.to_dict()
        if with_colleagues:
            relationships = get_relationships(name, persona.scope)
            data["relationships"] = [r.to_dict() for r in relationships]
        console.print(json.dumps(data, indent=2))
        return

    # Rich output
    console.print(f"\n[bold]{persona.name}[/bold]")
    console.print(f"  Template: {persona.template or 'custom'}")
    console.print(f"  Scope: {persona.scope}")

    if persona.role:
        console.print(f"  Role: {persona.role}")
    if persona.organization:
        console.print(f"  Organization: {persona.organization}")
    if persona.domain:
        console.print(f"  Domain: {persona.domain}")

    if persona.expertise:
        console.print(f"  Expertise: {', '.join(persona.expertise)}")

    console.print(f"\n  Communication: {persona.communication_style or 'not set'}")
    console.print(f"  Preferred format: {persona.preferred_format or 'not set'}")

    if persona.goals:
        console.print("\n  [bold]Goals:[/bold]")
        for g in persona.goals:
            console.print(f"    - {g}")

    if persona.concerns:
        console.print("\n  [bold]Concerns:[/bold]")
        for c in persona.concerns:
            console.print(f"    - {c}")

    if persona.constraints:
        console.print("\n  [bold]Constraints:[/bold]")
        for c in persona.constraints:
            console.print(f"    - {c}")

    if persona.bridge_weights:
        console.print("\n  [bold]Federated Taxonomy Bridges:[/bold]")
        for bridge, weight in persona.bridge_weights.items():
            bar = "█" * int(weight * 10) + "░" * (10 - int(weight * 10))
            console.print(f"    {bridge:12} [{bar}] {weight:.1f}")

    if persona.sources:
        console.print("\n  [bold]Learning Sources:[/bold]")
        for src, count in persona.sources.items():
            console.print(f"    {src}: {count}")
        if persona.qra_count:
            console.print(f"    QRA pairs: {persona.qra_count}")

    if with_colleagues:
        relationships = get_relationships(name, persona.scope)
        if relationships:
            console.print("\n  [bold]Relationships:[/bold]")
            for rel in relationships:
                bridges_str = f" [{', '.join(rel.bridges)}]" if rel.bridges else ""
                console.print(f"    → {rel.to_persona} ({rel.relationship}){bridges_str}")
                if rel.context:
                    console.print(f"      {rel.context}")

    console.print(f"\n  Created: {persona.created_at[:10]}")
    console.print(f"  Updated: {persona.last_updated[:10]}")


# =============================================================================
# Update Command
# =============================================================================

@app.command()
def update(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    add_goal: Optional[list[str]] = typer.Option(None, "--add-goal", help="Add goal"),
    add_concern: Optional[list[str]] = typer.Option(None, "--add-concern", help="Add concern"),
    add_expertise: Optional[list[str]] = typer.Option(None, "--add-expertise", help="Add expertise"),
    set_role: Optional[str] = typer.Option(None, "--set-role", help="Update role"),
    set_org: Optional[str] = typer.Option(None, "--set-org", help="Update organization"),
    set_domain: Optional[str] = typer.Option(None, "--set-domain", help="Update domain"),
    add_bridge: Optional[str] = typer.Option(None, "--add-bridge", help="Add bridge (name:weight)"),
):
    """Update an existing persona."""
    # Find persona
    scopes_to_search = [scope] if scope else ["personas", "clients", "behavioral", "stakeholders"]
    found_scope = None
    for s in scopes_to_search:
        if get_persona(name, s):
            found_scope = s
            break

    if not found_scope:
        console.print(f"[red]Persona '{name}' not found[/red]")
        raise typer.Exit(1)

    # Build updates
    updates = {}
    if add_goal:
        updates["goals"] = add_goal
    if add_concern:
        updates["concerns"] = add_concern
    if add_expertise:
        updates["expertise"] = add_expertise
    if set_role:
        updates["role"] = set_role
    if set_org:
        updates["organization"] = set_org
    if set_domain:
        updates["domain"] = set_domain
    if add_bridge:
        if ":" in add_bridge:
            b_name, b_weight = add_bridge.split(":", 1)
            updates["bridge_weights"] = {b_name: float(b_weight)}
        else:
            updates["bridge_weights"] = {add_bridge: 0.7}

    if not updates:
        console.print("[yellow]No updates specified[/yellow]")
        raise typer.Exit(1)

    # Apply updates
    updated = update_persona(name, found_scope, **updates)
    if updated:
        console.print(f"[green]Updated persona '{name}'[/green]")
    else:
        console.print(f"[red]Failed to update persona[/red]")
        raise typer.Exit(1)


# =============================================================================
# Delete Command
# =============================================================================

@app.command()
def delete(
    name: str = typer.Argument(..., help="Persona name"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Memory scope"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirm deletion"),
):
    """Delete a persona."""
    if not confirm:
        console.print("[yellow]Use --confirm to delete[/yellow]")
        raise typer.Exit(1)

    # Find persona
    scopes_to_search = [scope] if scope else ["personas", "clients", "behavioral", "stakeholders"]
    found_scope = None
    for s in scopes_to_search:
        if get_persona(name, s):
            found_scope = s
            break

    if not found_scope:
        console.print(f"[red]Persona '{name}' not found[/red]")
        raise typer.Exit(1)

    if delete_persona(name, found_scope):
        console.print(f"[green]Deleted persona: {name}[/green]")
    else:
        console.print("[red]Failed to delete persona[/red]")
        raise typer.Exit(1)

