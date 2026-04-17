"""
Shared Typer app and Rich console for /create-persona CLI.

All CLI sub-modules import app and console from here.
"""

import typer
from rich.console import Console

app = typer.Typer(help="/create-persona \u2014 Deliberate persona creation for client modeling")
console = Console()
