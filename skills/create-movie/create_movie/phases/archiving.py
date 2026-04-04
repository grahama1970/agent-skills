"""
Archiving helpers for create-movie skill.

Handles session archiving to episodic memory via persona integration.
"""

import json
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


def archive_creation_session(
    project_name: str,
    prompt: str,
    output_path: Path,
    script_file: Path,
    skip_casting: bool,
    store_learnings_enabled: bool,
    duration: int,
) -> bool:
    """
    Archive creation session to episodic memory via persona integration.

    Returns True if archiving succeeded, False otherwise.
    """
    try:
        from persona_integration import archive_session
    except ImportError:
        console.print("[dim]Persona integration not available for archiving[/dim]")
        return False

    try:
        script_bridges = []
        if script_file.exists():
            with open(script_file) as f:
                script_data = json.load(f)
            script_bridges = script_data.get("bridge_attributes", [])

        phases_completed = ["research", "script"]
        if not skip_casting:
            phases_completed.append("casting")
        phases_completed.extend(["build-tools", "generate", "assemble"])
        if store_learnings_enabled:
            phases_completed.append("learn")

        archived = archive_session(
            project_name=project_name,
            prompt=prompt,
            phases=phases_completed,
            output=str(output_path),
            bridges=script_bridges,
            duration=duration * 2
        )
        if archived:
            console.print("[cyan]Archived creation session to episodic memory[/cyan]")
            return True
        return False
    except Exception as e:
        console.print(f"[dim]Episodic archiving skipped: {e}[/dim]")
        return False
