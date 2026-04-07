"""
CLI for create-sound-design skill.

Provides commands for interactive and headless sound design sessions.
"""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from .orchestrator import (
    start_session,
    continue_session,
    get_session_status,
    run_sound_design_session,
)
from .collaboration import list_sessions, delete_session
from .schemas import SoundDesignPhase

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO", format="<level>{message}</level>")

app = typer.Typer(
    name="create-sound-design",
    help="Orchestrate sound effects selection and placement for movie scenes.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def start(
    script: str = typer.Option(..., "--script", "-s", help="Path to script JSON"),
    storyboard: Optional[str] = typer.Option(None, "--storyboard", "-b", help="Path to storyboard YAML"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Start a new sound design session."""
    result = start_session(
        script_path=script,
        storyboard_path=storyboard or "",
        output_dir=output or "",
    )
    
    if json_output:
        print(json.dumps({
            "status": result.status,
            "phase": result.phase.value,
            "session_id": result.session_id,
            "questions": [
                {"id": q.id, "question": q.question, "options": q.options, "default": q.default}
                for q in result.questions
            ],
            "error": result.error,
            "resume_command": result.resume_command,
        }, indent=2))
        return
    
    if result.status == "error":
        console.print(f"[red]Error: {result.error}[/red]")
        raise typer.Exit(1)
    
    console.print(f"[green]Session started: {result.session_id}[/green]")
    console.print(f"Phase: {result.phase.value}")
    console.print(f"\nQuestions ({len(result.questions)}):")
    
    for q in result.questions[:5]:
        console.print(f"\n[bold]{q.id}[/bold]: {q.question}")
        for opt in q.options:
            marker = "[*]" if opt == q.default else "[ ]"
            console.print(f"  {marker} {opt}")
    
    if len(result.questions) > 5:
        console.print(f"\n... and {len(result.questions) - 5} more questions")
    
    console.print(f"\n[dim]Resume: {result.resume_command}[/dim]")


@app.command("continue")
def continue_cmd(
    session_id: str = typer.Argument(..., help="Session ID to continue"),
    answers: Optional[str] = typer.Option(None, "--answers", "-a", help="JSON answers"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Continue an existing session with answers."""
    # Parse answers
    if answers:
        try:
            answers_dict = json.loads(answers)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON answers: {e}[/red]")
            raise typer.Exit(1)
    else:
        answers_dict = {}
    
    result = continue_session(session_id, answers_dict)
    
    if json_output:
        print(json.dumps({
            "status": result.status,
            "phase": result.phase.value,
            "session_id": result.session_id,
            "event_count": result.event_count,
            "manifest_path": result.manifest_path,
            "questions": [
                {"id": q.id, "question": q.question, "options": q.options, "default": q.default}
                for q in result.questions
            ],
            "error": result.error,
        }, indent=2))
        return
    
    if result.status == "error":
        console.print(f"[red]Error: {result.error}[/red]")
        raise typer.Exit(1)
    
    if result.status == "complete":
        console.print(f"[green]Session complete![/green]")
        console.print(f"Events placed: {result.event_count}")
        if result.manifest_path:
            console.print(f"Manifest: {result.manifest_path}")
        return
    
    console.print(f"Phase: {result.phase.value}")
    console.print(f"Questions remaining: {len(result.questions)}")
    
    for q in result.questions[:3]:
        console.print(f"\n[bold]{q.id}[/bold]: {q.question}")


@app.command()
def status(
    session_id: str = typer.Argument(..., help="Session ID to check"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check session status."""
    result = get_session_status(session_id)
    
    if json_output:
        print(json.dumps({
            "status": result.status,
            "phase": result.phase.value,
            "session_id": result.session_id,
            "event_count": result.event_count,
            "questions_pending": len(result.questions),
            "error": result.error,
        }, indent=2))
        return
    
    if result.status == "error":
        console.print(f"[red]Error: {result.error}[/red]")
        raise typer.Exit(1)
    
    console.print(f"Session: {result.session_id}")
    console.print(f"Status: {result.status}")
    console.print(f"Phase: {result.phase.value}")
    console.print(f"Events: {result.event_count}")
    console.print(f"Questions pending: {len(result.questions)}")


@app.command()
def list(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all sessions."""
    sessions = list_sessions()
    
    if json_output:
        print(json.dumps(sessions, indent=2))
        return
    
    if not sessions:
        console.print("[dim]No sessions found[/dim]")
        return
    
    table = Table(title="Sound Design Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Phase")
    table.add_column("Cues")
    table.add_column("Events")
    table.add_column("Updated")
    
    for s in sessions:
        table.add_row(
            s["session_id"],
            s["phase"],
            str(s["cue_count"]),
            str(s["event_count"]),
            s.get("updated_at", "")[:19],
        )
    
    console.print(table)


@app.command()
def auto(
    script: str = typer.Option(..., "--script", "-s", help="Path to script JSON"),
    storyboard: Optional[str] = typer.Option(None, "--storyboard", "-b", help="Path to storyboard YAML"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run headless sound design (auto-approve all decisions)."""
    result = run_sound_design_session(
        script_path=script,
        storyboard_path=storyboard or "",
        output_dir=output or "",
        auto_approve=True,
    )
    
    if json_output:
        print(json.dumps({
            "status": result.status,
            "phase": result.phase.value,
            "session_id": result.session_id,
            "event_count": result.event_count,
            "manifest_path": result.manifest_path,
            "memory_ids": result.memory_ids,
            "error": result.error,
        }, indent=2))
        return
    
    if result.status == "error":
        console.print(f"[red]Error: {result.error}[/red]")
        raise typer.Exit(1)
    
    console.print(f"[green]Sound design complete![/green]")
    console.print(f"Session: {result.session_id}")
    console.print(f"Events placed: {result.event_count}")
    if result.manifest_path:
        console.print(f"Manifest: {result.manifest_path}")
    if result.memory_ids:
        console.print(f"Usage records: {len(result.memory_ids)}")


@app.command()
def export(
    session_id: str = typer.Argument(..., help="Session ID to export"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output path for manifest"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Export sound design manifest."""
    result = get_session_status(session_id)
    
    if result.status == "error":
        console.print(f"[red]Error: {result.error}[/red]")
        raise typer.Exit(1)
    
    if not result.manifest_path:
        console.print("[yellow]No manifest available. Run session to completion first.[/yellow]")
        raise typer.Exit(1)
    
    # Copy manifest if output specified
    if output:
        import shutil
        src = Path(result.manifest_path)
        if src.exists():
            shutil.copy(src, output)
            manifest_path = output
        else:
            console.print(f"[red]Manifest file not found: {result.manifest_path}[/red]")
            raise typer.Exit(1)
    else:
        manifest_path = result.manifest_path
    
    if json_output:
        with open(manifest_path) as f:
            print(f.read())
        return
    
    console.print(f"[green]Manifest exported: {manifest_path}[/green]")
    console.print(f"Events: {result.event_count}")
    console.print(f"Scenes: {len(result.scenes)}")


@app.command()
def delete(
    session_id: str = typer.Argument(..., help="Session ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a session."""
    if not force:
        confirm = typer.confirm(f"Delete session {session_id}?")
        if not confirm:
            raise typer.Abort()
    
    if delete_session(session_id):
        console.print(f"[green]Deleted: {session_id}[/green]")
    else:
        console.print(f"[yellow]Session not found: {session_id}[/yellow]")


@app.command()
def check():
    """Check dependencies and connectivity."""
    console.print("=== create-sound-design Health Check ===\n")
    
    # Check sfx-catalog
    sfx_path = Path(__file__).parent.parent.parent / "sfx-catalog"
    if sfx_path.exists():
        console.print("[green]sfx-catalog: Available[/green]")
        
        # Try importing
        try:
            sys.path.insert(0, str(sfx_path))
            from src.query_engine import SFXQueryEngine
            console.print("[green]  - SFXQueryEngine: Importable[/green]")
        except ImportError as e:
            console.print(f"[yellow]  - SFXQueryEngine: Not importable ({e})[/yellow]")
    else:
        console.print("[yellow]sfx-catalog: Not found (will use mock)[/yellow]")
    
    # Check sessions directory
    from .collaboration import get_sessions_dir
    sessions_dir = get_sessions_dir()
    sessions = list_sessions()
    console.print(f"\nSessions directory: {sessions_dir}")
    console.print(f"Active sessions: {len(sessions)}")
    
    console.print("\n[green]Health check complete![/green]")


if __name__ == "__main__":
    app()
