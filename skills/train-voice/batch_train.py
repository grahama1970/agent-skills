#!/usr/bin/env python3
"""
Batch voice training for personas.

Trains voices in priority order based on source availability.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from loguru import logger

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    print("Missing dependencies. Run: uv pip install typer rich")
    sys.exit(1)

app = typer.Typer(help="Batch voice training for personas")
console = Console()

_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
VOICE_MODELS_DIR = Path(os.environ.get("VOICE_STORAGE", str(_EMBRY_STORAGE / "media/personas")))
TRAIN_VOICE_DIR = Path(__file__).parent

# Use miniconda Python which has resemblyzer, whisper, and torch installed
MINICONDA_PYTHON = Path.home() / "miniconda3" / "bin" / "python"
PYTHON_EXE = str(MINICONDA_PYTHON) if MINICONDA_PYTHON.exists() else sys.executable

# Persona categories with training approach
PERSONAS = {
    # Phase 1: Actors (abundant source material)
    "phase1_actors": {
        "type": "known",
        "personas": [
            {"name": "Cate Blanchett", "slug": "cate-blanchett", "search": "Cate Blanchett interview"},
            {"name": "Denzel Washington", "slug": "denzel-washington", "search": "Denzel Washington interview"},
            {"name": "Meryl Streep", "slug": "meryl-streep", "search": "Meryl Streep interview"},
            {"name": "Viola Davis", "slug": "viola-davis", "search": "Viola Davis interview"},
            {"name": "Gary Oldman", "slug": "gary-oldman", "search": "Gary Oldman interview"},
            {"name": "Tilda Swinton", "slug": "tilda-swinton", "search": "Tilda Swinton interview"},
            {"name": "Joaquin Phoenix", "slug": "joaquin-phoenix", "search": "Joaquin Phoenix interview"},
            {"name": "Frances McDormand", "slug": "frances-mcdormand", "search": "Frances McDormand interview"},
            {"name": "Mads Mikkelsen", "slug": "mads-mikkelsen", "search": "Mads Mikkelsen interview"},
        ],
    },
    # Phase 2: Directors with interviews
    "phase2_directors": {
        "type": "known",
        "personas": [
            {"name": "Werner Herzog", "slug": "werner-herzog", "search": "Werner Herzog interview documentary"},
            {"name": "Quentin Tarantino", "slug": "quentin-tarantino", "search": "Quentin Tarantino interview"},
            {"name": "Terry Gilliam", "slug": "terry-gilliam", "search": "Terry Gilliam interview"},
            {"name": "Bong Joon-ho", "slug": "bong-joon-ho", "search": "Bong Joon-ho interview English"},
            {"name": "Hayao Miyazaki", "slug": "hayao-miyazaki", "search": "Hayao Miyazaki interview"},
            {"name": "Akira Kurosawa", "slug": "akira-kurosawa", "search": "Akira Kurosawa interview"},
            {"name": "Wong Kar-wai", "slug": "wong-kar-wai", "search": "Wong Kar-wai interview English"},
            {"name": "Jean-Luc Godard", "slug": "jean-luc-godard", "search": "Jean-Luc Godard interview"},
        ],
    },
    # Phase 3: Writers with interviews
    "phase3_writers": {
        "type": "known",
        "personas": [
            {"name": "Stephen King", "slug": "stephen-king", "search": "Stephen King interview"},
            {"name": "Aaron Sorkin", "slug": "aaron-sorkin", "search": "Aaron Sorkin masterclass interview"},
            {"name": "Kurt Vonnegut", "slug": "kurt-vonnegut", "search": "Kurt Vonnegut interview"},
        ],
    },
    # Phase 4: Experts with lectures
    "phase4_experts": {
        "type": "known",
        "personas": [
            {"name": "Donald Knuth", "slug": "donald-knuth", "search": "Donald Knuth lecture Stanford"},
            {"name": "Grace Hopper", "slug": "grace-hopper", "search": "Grace Hopper lecture interview"},
            {"name": "Joseph Campbell", "slug": "joseph-campbell", "search": "Joseph Campbell Power of Myth"},
            {"name": "Stefan Sagmeister", "slug": "stefan-sagmeister", "search": "Stefan Sagmeister TED talk"},
        ],
    },
    # Phase 5: Historical with some recordings
    "phase5_historical_known": {
        "type": "known",
        "personas": [
            {"name": "Carl Jung", "slug": "carl-jung", "search": "Carl Jung interview BBC"},
            {"name": "Dwight D. Eisenhower", "slug": "dwight-d-eisenhower", "search": "Eisenhower speech"},
            {"name": "Billy Wilder", "slug": "billy-wilder", "search": "Billy Wilder interview AFI"},
        ],
    },
    # Phase 6: Historical requiring voice design
    "phase6_historical_unknown": {
        "type": "design",
        "personas": [
            {"name": "Voltaire", "slug": "voltaire"},
            {"name": "Ada Lovelace", "slug": "ada-lovelace"},
            {"name": "Herodotus", "slug": "herodotus"},
            {"name": "F.W. Murnau", "slug": "fw-murnau"},
        ],
    },
    # Phase 7: Cinematographers (limited material)
    "phase7_cinematographers": {
        "type": "known",
        "personas": [
            {"name": "Roger Deakins", "slug": "roger-deakins", "search": "Roger Deakins interview ASC"},
            {"name": "Emmanuel Lubezki", "slug": "emmanuel-lubezki", "search": "Emmanuel Lubezki interview"},
            {"name": "Robert Richardson", "slug": "robert-richardson", "search": "Robert Richardson interview"},
        ],
    },
}


def get_persona_dir_slug(name: str) -> str:
    """Convert persona name to directory slug (same as train.py)."""
    return name.lower().replace(" ", "_")


def check_training_status(name: str) -> dict:
    """Check if a persona already has trained voice."""
    # Use the same slug format as train.py: name.lower().replace(" ", "_")
    slug = get_persona_dir_slug(name)
    persona_dir = VOICE_MODELS_DIR / slug

    status = {
        "has_metadata": (persona_dir / "voice_metadata.json").exists(),
        "has_personaplex": False,
        "has_qwen3": False,
        "trained": False,
    }

    # Check for PersonaPlex embeddings
    personaplex_dir = persona_dir / "personaplex" / "voices"
    if personaplex_dir.exists():
        pt_files = list(personaplex_dir.glob("*.pt"))
        status["has_personaplex"] = len(pt_files) > 0

    # Check for Qwen3-TTS checkpoints (inside model/ subdirectory)
    qwen3_model_dir = persona_dir / "qwen3_tts" / "model"
    if qwen3_model_dir.exists():
        checkpoints = list(qwen3_model_dir.glob("checkpoint*"))
        status["has_qwen3"] = len(checkpoints) > 0

    status["trained"] = status["has_personaplex"] or status["has_qwen3"]

    return status


@app.command()
def status():
    """Show training status for all personas."""
    table = Table(title="Persona Voice Training Status")
    table.add_column("Phase", style="cyan")
    table.add_column("Persona", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("PersonaPlex", style="green")
    table.add_column("Qwen3-TTS", style="green")
    table.add_column("Status", style="bold")

    total = 0
    trained = 0

    for phase_name, phase_data in PERSONAS.items():
        for persona in phase_data["personas"]:
            total += 1
            s = check_training_status(persona["name"])

            pp = "[green]Yes[/green]" if s["has_personaplex"] else "[red]No[/red]"
            q3 = "[green]Yes[/green]" if s["has_qwen3"] else "[red]No[/red]"
            status_str = "[green]TRAINED[/green]" if s["trained"] else "[yellow]PENDING[/yellow]"

            if s["trained"]:
                trained += 1

            table.add_row(
                phase_name.replace("_", " ").title(),
                persona["name"],
                phase_data["type"],
                pp,
                q3,
                status_str,
            )

    console.print(table)
    console.print(f"\n[bold]Summary:[/bold] {trained}/{total} personas trained ({100*trained/total:.1f}%)")


@app.command()
def train(
    phase: str = typer.Argument(..., help="Phase to train (e.g., 'phase1_actors')"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    skip_trained: bool = typer.Option(True, "--skip-trained/--retrain", help="Skip already trained"),
    max_personas: int = typer.Option(0, "--max", "-m", help="Max personas to train (0=all)"),
    skip_qwen3: bool = typer.Option(False, "--skip-qwen3", help="Skip Qwen3-TTS training (PersonaPlex only)"),
):
    """Train all personas in a phase."""
    if phase not in PERSONAS:
        console.print(f"[red]Unknown phase: {phase}[/red]")
        console.print(f"Available phases: {', '.join(PERSONAS.keys())}")
        raise typer.Exit(1)

    phase_data = PERSONAS[phase]
    personas = phase_data["personas"]
    training_type = phase_data["type"]

    console.print(f"[bold]Training phase: {phase}[/bold]")
    console.print(f"Type: {training_type}, Personas: {len(personas)}")

    to_train = []
    for persona in personas:
        s = check_training_status(persona["name"])
        if skip_trained:
            if skip_qwen3:
                # PersonaPlex-only mode: skip if has PersonaPlex
                if s["has_personaplex"]:
                    console.print(f"  [dim]Skipping {persona['name']} (has PersonaPlex)[/dim]")
                    continue
            else:
                # Full training mode: skip if has BOTH PersonaPlex AND Qwen3-TTS
                if s["has_personaplex"] and s["has_qwen3"]:
                    console.print(f"  [dim]Skipping {persona['name']} (fully trained)[/dim]")
                    continue
        to_train.append(persona)

    if max_personas > 0:
        to_train = to_train[:max_personas]

    console.print(f"\n[bold]Will train {len(to_train)} personas:[/bold]")
    for p in to_train:
        console.print(f"  - {p['name']}")

    if dry_run:
        console.print("\n[yellow]Dry run - no training performed[/yellow]")
        return

    # Train each persona
    for i, persona in enumerate(to_train, 1):
        # Clear GPU cache before each training to prevent OOM
        try:
            subprocess.run([PYTHON_EXE, "-c", "import torch; torch.cuda.empty_cache(); torch.cuda.synchronize()"],
                          capture_output=True, timeout=30)
        except Exception as e:
            logger.debug("GPU cache clearing failed: {}", e)

        console.print(f"\n[bold cyan]({i}/{len(to_train)}) Training {persona['name']}...[/bold cyan]")

        if training_type == "known":
            # Use train command with references (persona name is used for YouTube search)
            # Run in foreground mode to avoid parallel GPU conflicts
            cmd = [
                PYTHON_EXE, str(TRAIN_VOICE_DIR / "train.py"),
                "train", persona["name"],
                "--references", persona["name"],  # Use persona name as reference actor
                "--foreground",  # Critical: wait for training to complete before next persona
            ]
            if skip_qwen3:
                cmd.append("--skip-qwen3")
        else:
            # Use design command for unknown voices
            cmd = [
                PYTHON_EXE, str(TRAIN_VOICE_DIR / "design.py"),
                persona["name"],
            ]

        console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")

        try:
            # 2 hour timeout to handle very long videos during transcription/training
            result = subprocess.run(cmd, cwd=str(TRAIN_VOICE_DIR), timeout=7200)
            if result.returncode == 0:
                console.print(f"[green]Successfully trained {persona['name']}[/green]")
            else:
                console.print(f"[red]Failed to train {persona['name']}[/red]")
        except subprocess.TimeoutExpired:
            console.print(f"[red]Timeout training {persona['name']}[/red]")
        except Exception as e:
            console.print(f"[red]Error training {persona['name']}: {e}[/red]")
        finally:
            # Clear GPU cache after training to prevent OOM on next persona
            try:
                subprocess.run([PYTHON_EXE, "-c", "import torch; torch.cuda.empty_cache(); torch.cuda.synchronize()"],
                              capture_output=True, timeout=30)
            except Exception as e:
                logger.debug("subprocess call failed: {}", e)


@app.command()
def list_phases():
    """List all training phases."""
    table = Table(title="Training Phases")
    table.add_column("Phase", style="cyan")
    table.add_column("Type", style="yellow")
    table.add_column("Count", style="green")
    table.add_column("Personas", style="white")

    for phase_name, phase_data in PERSONAS.items():
        personas = [p["name"] for p in phase_data["personas"]]
        preview = ", ".join(personas[:3])
        if len(personas) > 3:
            preview += f", ... (+{len(personas)-3})"

        table.add_row(
            phase_name,
            phase_data["type"],
            str(len(personas)),
            preview,
        )

    console.print(table)


if __name__ == "__main__":
    app()
