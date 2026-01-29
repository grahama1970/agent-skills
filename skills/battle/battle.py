#!/usr/bin/env python3
"""
Battle Skill - Red vs Blue Team Security Competition Orchestrator

CLI entry point for the battle skill. The actual implementation is split across:
- config.py: Constants, paths, environment variables
- state.py: Data classes and BattleState
- memory.py: Team-isolated memory system
- scoring.py: AIxCC-style scoring
- digital_twin.py: Git worktree, Docker, QEMU isolation
- red_team.py: Red Team attack agent
- blue_team.py: Blue Team defense agent
- orchestrator.py: Battle orchestration and game loop

Based on research into:
- RvB Framework (arXiv 2601.19726)
- DARPA AIxCC scoring system
- Microsoft PyRIT multi-turn orchestration
- DeepTeam async batch processing
"""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from config import BATTLES_DIR, REPORTS_DIR, OVERNIGHT_ROUNDS, OVERNIGHT_CHECKPOINT_INTERVAL
from state import BattleState, TwinMode
from orchestrator import BattleOrchestrator
from report import generate_report

app = typer.Typer(help="Red vs Blue Team Security Competition Orchestrator")
console = Console()


@app.command()
def battle(
    target: str = typer.Argument(".", help="Target directory, firmware file, or Docker image"),
    rounds: int = typer.Option(100, help="Maximum number of rounds"),
    overnight: bool = typer.Option(False, help="Run as overnight job (1000 rounds, checkpoints every 50)"),
    checkpoint_interval: int = typer.Option(10, help="Checkpoint every N rounds"),
    mode: str = typer.Option(None, help="Digital twin mode: git_worktree, docker, qemu, copy"),
    docker_image: str = typer.Option(None, help="Docker image for container battles (e.g., nginx:latest)"),
    qemu_machine: str = typer.Option(None, help="QEMU machine type (e.g., arm, riscv64, x86_64)"),
):
    """
    Start a Red vs Blue team battle.

    DIGITAL TWIN MODES:

    1. Source Code (git_worktree): Battle over a git repository
       ./run.sh battle /path/to/repo

    2. Docker Container (docker): Battle over a containerized app
       ./run.sh battle --docker-image nginx:latest
       ./run.sh battle /path/with/Dockerfile

    3. Firmware/MCU (qemu): Battle over microprocessor firmware
       ./run.sh battle firmware.bin --qemu-machine arm
       ./run.sh battle firmware.elf

    Red Team attacks using hack skill.
    Blue Team defends using anvil skill.
    Both teams leverage memory for strategy recall.
    """
    if overnight:
        rounds = OVERNIGHT_ROUNDS
        checkpoint_interval = OVERNIGHT_CHECKPOINT_INTERVAL
        console.print(f"[yellow]Overnight mode: {rounds} rounds, checkpoints every {checkpoint_interval}[/yellow]")

    # Parse mode
    twin_mode = None
    if mode:
        try:
            twin_mode = TwinMode(mode)
        except ValueError:
            console.print(f"[red]Invalid mode: {mode}[/red]")
            console.print(f"[yellow]Valid modes: {', '.join(m.value for m in TwinMode)}[/yellow]")
            raise typer.Exit(1)

    # Handle Docker image as target
    if docker_image and target == ".":
        target_path = Path.cwd()
    else:
        target_path = Path(target).resolve()
        if not target_path.exists():
            console.print(f"[red]Target not found: {target}[/red]")
            raise typer.Exit(1)

    orchestrator = BattleOrchestrator(
        str(target_path),
        rounds,
        twin_mode=twin_mode,
        qemu_machine=qemu_machine,
        docker_image=docker_image,
    )
    state = orchestrator.run(checkpoint_interval)

    # Generate and save report
    report = generate_report(state)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{state.battle_id}.md"
    report_path.write_text(report)
    console.print(f"\n[green]Report saved: {report_path}[/green]")


@app.command()
def status():
    """Check status of running or recent battles."""
    BATTLES_DIR.mkdir(parents=True, exist_ok=True)

    battles = list(BATTLES_DIR.glob("battle_*.json"))
    if not battles:
        console.print("[yellow]No battles found[/yellow]")
        return

    table = Table(title="Battle Status")
    table.add_column("Battle ID")
    table.add_column("Status")
    table.add_column("Round")
    table.add_column("Red Score")
    table.add_column("Blue Score")
    table.add_column("Leader")

    for battle_file in sorted(battles, reverse=True)[:10]:
        try:
            state = BattleState.load(battle_file.stem)
            if state:
                leader = "Red" if state.red_total_score > state.blue_total_score else "Blue"
                table.add_row(
                    state.battle_id,
                    state.status,
                    f"{state.current_round}/{state.max_rounds}",
                    f"{state.red_total_score:.1f}",
                    f"{state.blue_total_score:.1f}",
                    leader
                )
        except Exception:
            pass

    console.print(table)


@app.command()
def resume(
    battle_id: str = typer.Argument(..., help="Battle ID to resume"),
):
    """Resume a paused battle."""
    state = BattleState.load(battle_id)
    if not state:
        console.print(f"[red]Battle not found: {battle_id}[/red]")
        raise typer.Exit(1)

    if state.status == "completed":
        console.print(f"[yellow]Battle already completed[/yellow]")
        return

    console.print(f"[green]Resuming battle from round {state.current_round}[/green]")

    # Recreate orchestrator with existing state
    orchestrator = BattleOrchestrator(state.target_path, state.max_rounds)
    orchestrator.state = state
    orchestrator.battle_id = state.battle_id

    # Continue battle
    final_state = orchestrator.run()

    # Generate report
    report = generate_report(final_state)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{final_state.battle_id}.md"
    report_path.write_text(report)
    console.print(f"\n[green]Report saved: {report_path}[/green]")


@app.command()
def report(
    battle_id: str = typer.Argument(..., help="Battle ID to generate report for"),
):
    """Generate report for a completed battle."""
    state = BattleState.load(battle_id)
    if not state:
        console.print(f"[red]Battle not found: {battle_id}[/red]")
        raise typer.Exit(1)

    report_content = generate_report(state)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{battle_id}.md"
    report_path.write_text(report_content)

    console.print(report_content)
    console.print(f"\n[green]Report saved: {report_path}[/green]")


@app.command()
def stop(
    battle_id: str = typer.Argument(..., help="Battle ID to stop"),
):
    """Stop a running battle (kill switch)."""
    state = BattleState.load(battle_id)
    if not state:
        console.print(f"[red]Battle not found: {battle_id}[/red]")
        raise typer.Exit(1)

    state.status = "paused"
    state.save()
    console.print(f"[yellow]Battle {battle_id} stopped[/yellow]")


if __name__ == "__main__":
    app()
