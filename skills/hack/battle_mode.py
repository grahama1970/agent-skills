"""Hack-owned adapter for the advanced red/blue battle mode."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import typer
from rich.console import Console

console = Console()


def build_battle_command_args(
    *,
    target: str | None,
    rounds: int,
    overnight: bool,
    mode: str | None,
    docker_image: str | None,
) -> list[str]:
    """Build the sibling /battle command argv for /hack battle."""

    battle_run = Path(__file__).resolve().parents[1] / "battle" / "run.sh"
    args = [str(battle_run), "battle"]
    if target:
        args.append(target)
    if docker_image:
        args.extend(["--docker-image", docker_image])
    if mode:
        args.extend(["--mode", mode])
    if overnight:
        args.append("--overnight")
    else:
        args.extend(["--rounds", str(rounds)])
    return args


def create_battle_command() -> Callable[..., None]:
    """Create the Typer command for /hack's third top-level mode."""

    def battle(
        target: str | None = typer.Argument(
            None,
            help="Authorized codebase path, Dockerfile directory, firmware, or target handled by /battle.",
        ),
        rounds: int = typer.Option(100, "--rounds", help="Maximum red/blue rounds."),
        overnight: bool = typer.Option(False, "--overnight", help="Run the sibling /battle overnight preset."),
        mode: str | None = typer.Option(None, "--mode", help="Optional /battle digital twin mode."),
        docker_image: str | None = typer.Option(None, "--docker-image", help="Optional Docker image target for /battle."),
    ) -> None:
        """Run the advanced red/blue hardening arena through the battle skill."""

        if not target and not docker_image:
            raise typer.BadParameter("provide a target path or --docker-image")
        if rounds <= 0:
            raise typer.BadParameter("--rounds must be positive")
        args = build_battle_command_args(
            target=target,
            rounds=rounds,
            overnight=overnight,
            mode=mode,
            docker_image=docker_image,
        )
        console.print("[cyan]/hack battle delegates to sibling /battle for red/blue arena execution[/cyan]")
        result = subprocess.run(args, check=False)
        raise typer.Exit(result.returncode)

    return battle


__all__ = ["build_battle_command_args", "create_battle_command"]
