"""
Batch persona creation from YAML manifests.
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
# Batch Command
# =============================================================================

@app.command()
def batch(
    manifest: Path = typer.Argument(..., help="YAML manifest file (e.g., personas.yaml)"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Only process specific category"),
    skip_learn: bool = typer.Option(False, "--skip-learn", help="Skip auto-learning"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="Number of parallel learns (not implemented yet)"),
):
    """Batch create personas from a YAML manifest.

    The manifest format supports categories with defaults:

        defaults:
          scope: personas
          auto_learn: true

        writers:
          - name: Alan Moore
            template: expert
            domain: comics, literature
            expertise: [graphic novels, chaos magic]
            goals: [Challenge conventions]
            bridges:
              Corruption: 0.7
            colleagues: [Neil Gaiman]
    """
    try:
        import yaml
    except ImportError:
        console.print("[red]pyyaml not installed. Run: pip install pyyaml[/red]")
        raise typer.Exit(1)

    if not manifest.exists():
        console.print(f"[red]Manifest not found: {manifest}[/red]")
        raise typer.Exit(1)

    # Parse manifest
    with open(manifest) as f:
        data = yaml.safe_load(f)

    if not data:
        console.print("[red]Empty manifest[/red]")
        raise typer.Exit(1)

    # Extract defaults
    defaults = data.pop("defaults", {})
    default_scope = defaults.get("scope", "personas")
    default_auto_learn = defaults.get("auto_learn", True)
    default_depth = defaults.get("depth", "standard")

    # Collect personas from all categories
    personas_to_create = []

    for cat_name, cat_personas in data.items():
        # Skip if filtering by category
        if category and cat_name != category:
            continue

        if not isinstance(cat_personas, list):
            log.warning(f"Skipping non-list category: {cat_name}")
            continue

        for p_data in cat_personas:
            if not isinstance(p_data, dict) or "name" not in p_data:
                log.warning(f"Skipping invalid persona in {cat_name}")
                continue

            personas_to_create.append({
                "category": cat_name,
                "data": p_data,
            })

    if not personas_to_create:
        console.print("[yellow]No personas found in manifest[/yellow]")
        raise typer.Exit(0)

    console.print(f"\n[bold]Batch Create: {len(personas_to_create)} personas[/bold]")
    console.print(f"  Manifest: {manifest}")
    console.print(f"  Default scope: {default_scope}")
    console.print(f"  Auto-learn: {default_auto_learn and not skip_learn}")
    if category:
        console.print(f"  Category filter: {category}")
    console.print()

    # Create table for summary
    table = Table(title="Personas to Create")
    table.add_column("#", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Category")
    table.add_column("Template")
    table.add_column("Domain")
    table.add_column("Bridges")

    for i, item in enumerate(personas_to_create, 1):
        p_data = item["data"]
        bridges = p_data.get("bridges", {})
        bridges_str = ", ".join(f"{k}:{v}" for k, v in bridges.items()) if bridges else "-"
        table.add_row(
            str(i),
            p_data["name"],
            item["category"],
            p_data.get("template", "expert"),
            str(p_data.get("domain", "-"))[:30],
            bridges_str[:30],
        )

    console.print(table)
    console.print()

    if dry_run:
        console.print("[dim][dry-run] Would create the above personas[/dim]")
        return

    # Create personas
    created = 0
    failed = 0
    learn_queue = []

    from rich.progress import Progress, SpinnerColumn, TextColumn

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Creating personas...", total=len(personas_to_create))

        for item in personas_to_create:
            p_data = item["data"]
            name = p_data["name"]
            progress.update(task, description=f"Creating {name}...")

            # Build persona
            template = p_data.get("template", "expert")
            template_config = get_template(template) or {}

            # Determine scope
            scope = default_scope

            # Parse bridges
            bridge_weights = {}
            if "bridges" in p_data:
                bridge_weights = {k: float(v) for k, v in p_data["bridges"].items()}
            else:
                bridge_weights = get_default_bridges(template)

            # Parse domain (can be comma-separated string)
            domain = p_data.get("domain", "")
            if isinstance(domain, list):
                domain = ", ".join(domain)

            # Parse expertise
            expertise = p_data.get("expertise", [])
            if isinstance(expertise, str):
                expertise = [e.strip() for e in expertise.split(",")]

            # Parse goals
            goals = p_data.get("goals", [])
            if isinstance(goals, str):
                goals = [goals]

            # Create persona object
            persona = Persona(
                name=name,
                template=template,
                scope=scope,
                domain=domain,
                expertise=expertise,
                goals=goals,
                communication_style=p_data.get("communication_style", template_config.get("communication_style", "")),
                preferred_format=template_config.get("preferred_format", ""),
                bridge_weights=bridge_weights,
                tags=template_config.get("tags", []) + [item["category"]],
            )

            # Add notes to constraints if present
            if "notes" in p_data:
                persona.constraints.append(f"Note: {p_data['notes']}")

            # Store persona
            try:
                success = create_persona(persona, store=True)
                if success:
                    created += 1

                    # Create colleague relationships
                    colleagues = p_data.get("colleagues", [])
                    for coll_name in colleagues:
                        rel = PersonaRelationship(
                            from_persona=name,
                            to_persona=coll_name,
                            relationship="colleague",
                            bridges=list(bridge_weights.keys()),
                        )
                        create_relationship(rel, scope)

                    # Queue for learning
                    should_learn = default_auto_learn and not skip_learn
                    if should_learn and template in ("expert", "coder", "fictional"):
                        # Get top bridge for content discovery
                        top_bridge = max(bridge_weights, key=bridge_weights.get) if bridge_weights else None
                        learn_queue.append({
                            "name": name,
                            "scope": scope,
                            "depth": default_depth,
                            "template": template,
                            "bridge": top_bridge,
                        })
                else:
                    failed += 1
                    log.error(f"Failed to create persona: {name}")

            except Exception as e:
                failed += 1
                log.error(f"Error creating {name}: {e}")

            progress.advance(task)

    console.print()
    console.print(f"[green]Created: {created}[/green]")
    if failed:
        console.print(f"[red]Failed: {failed}[/red]")

    # Process learning queue
    if learn_queue:
        console.print(f"\n[bold]Auto-learning {len(learn_queue)} personas...[/bold]")
        console.print("[dim]This may take several minutes per persona[/dim]\n")

        learned = 0
        for item in learn_queue:
            name = item["name"]
            console.print(f"  Learning about {name}...", end=" ")

            try:
                # ./run.sh learn <topic> --scope ...
                # run.sh case "learn" shifts once, then execs learn.py <topic>
                learn_args = [
                    "learn", name,
                    "--scope", item["scope"],
                    "--depth", item["depth"],
                ]
                if item.get("template"):
                    learn_args.extend(["--persona-template", item["template"]])
                if item.get("bridge"):
                    learn_args.extend(["--persona-bridge", item["bridge"]])
                learn_result = run_skill("ask", learn_args, timeout=300)

                if learn_result["returncode"] == 0:
                    learned += 1
                    console.print("[green]✓[/green]")
                else:
                    # Show last meaningful line of stderr (skip loguru timestamps)
                    stderr_lines = [l for l in learn_result["stderr"].strip().splitlines() if l.strip()]
                    last_line = stderr_lines[-1] if stderr_lines else "unknown error"
                    console.print(f"[yellow]⚠ exit={learn_result['returncode']}: {last_line[:120]}[/yellow]")
            except Exception as e:
                console.print(f"[red]✗ {str(e)[:120]}[/red]")

        console.print(f"\n[green]Learning complete: {learned}/{len(learn_queue)}[/green]")

    console.print(f"\n[bold]Done![/bold] View personas with: ./run.sh list")

