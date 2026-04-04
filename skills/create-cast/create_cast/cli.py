#!/usr/bin/env python3
"""
CLI for create-cast skill.

Usage:
    python -m create_cast.cli start script.json
    python -m create_cast.cli continue-session --session ID --answers '{...}'
    python -m create_cast.cli status --session ID
"""

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import (
    start_casting_session,
    continue_session,
    export_session,
    get_session_status,
    list_sessions,
)
from .collaboration import format_questions_for_display

app = typer.Typer(help="Character casting orchestrator for Horus movies")
console = Console()


@app.command()
def start(
    script: str = typer.Argument(..., help="Path to script file (JSON or markdown)"),
    output: str = typer.Option("", "--output", "-o", help="Output directory for identity packs"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Skip questions, use defaults"),
):
    """Start a new casting session from a script."""
    console.print(f"[dim]Starting casting session for: {script}[/dim]")
    
    result = start_casting_session(script, output, auto_approve)
    
    if json_output:
        print(result.to_json())
    else:
        _display_result(result)


@app.command("continue-session")
def continue_cmd(
    session: str = typer.Option(..., "--session", "-s", help="Session ID to continue"),
    answers: str = typer.Option(..., "--answers", "-a", help="JSON answers to questions"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Skip remaining questions"),
):
    """Continue a casting session with answers."""
    try:
        answers_dict = json.loads(answers)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON in answers: {e}[/red]")
        raise typer.Exit(1)
    
    console.print(f"[dim]Continuing session: {session}[/dim]")
    
    result = continue_session(session, answers_dict, auto_approve)
    
    if json_output:
        print(result.to_json())
    else:
        _display_result(result)


@app.command()
def status(
    session: str = typer.Option(..., "--session", "-s", help="Session ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Check status of a casting session."""
    status_info = get_session_status(session)
    
    if json_output:
        print(json.dumps(status_info, indent=2))
    else:
        if "error" in status_info:
            console.print(f"[red]{status_info['error']}[/red]")
            raise typer.Exit(1)
        
        console.print(f"\n[bold]Session: {status_info['session_id']}[/bold]")
        console.print(f"Phase: {status_info['phase']}")
        console.print(f"Script: {status_info['script_path']}")
        console.print(f"Created: {status_info['created_at']}")
        console.print(f"Updated: {status_info['updated_at']}")
        console.print(f"\nCharacters: {', '.join(status_info['characters'])}")
        console.print(f"With packs: {', '.join(status_info['characters_with_packs'])}")
        console.print(f"With voices: {', '.join(status_info['characters_with_voices'])}")
        console.print(f"\nPending questions: {status_info['pending_questions']}")
        console.print(f"Answers provided: {status_info['answers_provided']}")
        
        if status_info.get('error'):
            console.print(f"\n[red]Error: {status_info['error']}[/red]")


@app.command("export-packs")
def export_cmd(
    session: str = typer.Option(..., "--session", "-s", help="Session ID"),
    output: str = typer.Option(..., "--output", "-o", help="Output directory"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Export identity packs from a completed session."""
    console.print(f"[dim]Exporting session {session} to {output}[/dim]")
    
    result = export_session(session, output)
    
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        if "error" in result:
            console.print(f"[red]{result['error']}[/red]")
            raise typer.Exit(1)
        
        console.print(f"[green]Exported {len(result)} identity packs:[/green]")
        for char_name, path in result.items():
            console.print(f"  {char_name}: {path}")


@app.command("list-sessions")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List all casting sessions."""
    sessions = list_sessions()
    
    if json_output:
        print(json.dumps(sessions, indent=2))
    else:
        if not sessions:
            console.print("[yellow]No casting sessions found.[/yellow]")
            return
        
        table = Table(title="Casting Sessions")
        table.add_column("Session ID", style="cyan")
        table.add_column("Phase")
        table.add_column("Characters", justify="right")
        table.add_column("Updated")
        table.add_column("Status")
        
        for s in sessions:
            status = "[red]ERROR[/red]" if s.get("has_error") else "[green]OK[/green]"
            table.add_row(
                s["session_id"],
                s["phase"],
                str(s["character_count"]),
                s["updated_at"][:19] if s.get("updated_at") else "-",
                status,
            )
        
        console.print(table)


def _display_result(result):
    """Display a CastingResult in human-readable format."""
    console.print(f"\n[bold]Session: {result.session_id}[/bold]")
    console.print(f"Status: {result.status}")
    console.print(f"Phase: {result.phase.value}")
    
    if result.error:
        console.print(f"\n[red]Error: {result.error}[/red]")
        return
    
    if result.characters_complete:
        console.print(f"\nCharacters complete: {', '.join(result.characters_complete)}")
    
    if result.questions:
        console.print(format_questions_for_display(result.questions))
    
    if result.status == "needs_input":
        console.print(f"\n[dim]Resume with:[/dim]")
        console.print(f"  {result.resume_command}")
    
    if result.status == "complete":
        console.print("\n[green]Casting complete! Export with:[/green]")
        console.print(f"  ./run.sh export --session {result.session_id} --output ./characters")


def main():
    app()


if __name__ == "__main__":
    main()
