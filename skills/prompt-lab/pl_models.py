"""Prompt extraction CLI command.

models and seed-memory commands migrated to llm-eval-lab.
"""
from pathlib import Path

import typer

from config import ensure_dirs
from prompt_extractor import PromptExtractor

from pl_app import app, console


@app.command("extract-prompts")
def extract_prompts(
    file: Path = typer.Option(..., "--file", "-f", help="Python file to extract from"),
    output: Path = typer.Option(Path("prompts"), "--output", "-o", help="Output directory"),
):
    """Extract prompts from Python file (variables ending in _PROMPT)."""
    ensure_dirs()
    console.print(f"[bold]Extracting prompts from {file}[/bold]")

    try:
        extractor = PromptExtractor()
        prompts = extractor.extract_from_file(file)
        extractor.save_prompts(prompts, output, prefix=f"{file.stem}_")

        console.print(f"[green]Extracted {len(prompts)} prompts to {output}[/green]")
        for name in prompts:
            console.print(f"  - {name}")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
