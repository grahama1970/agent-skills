"""Prompt utility CLI commands: list, show, sync, history."""
import json
from pathlib import Path

import typer
from rich.table import Table

from config import SKILL_DIR, PROMPTS_DIR

from pl_app import app, console


@app.command()
def list_prompts():
    """List available prompts."""
    prompts_dir = SKILL_DIR / "prompts"
    if prompts_dir.exists():
        for f in prompts_dir.glob("*.txt"):
            console.print(f"  {f.stem}")
    else:
        console.print("No prompts found. Run 'eval' to create default.")


@app.command()
def show_prompt(name: str = typer.Argument(..., help="Prompt name")):
    """Show a prompt's content."""
    prompt_file = SKILL_DIR / "prompts" / f"{name}.txt"
    if prompt_file.exists():
        console.print(prompt_file.read_text())
    else:
        console.print(f"[red]Prompt '{name}' not found[/red]")


@app.command()
def sync(
    path: str = typer.Argument(str(Path.home() / "workspace/experiments/sparta/src/sparta/pipeline_duckdb/12_qra.py"), help="Path to file or directory to sync from"),
):
    """Sync prompts from source code markers: # [PROMPT-LAB: NAME] followed by triple-quoted string."""
    import re
    from pathlib import Path
    
    source_path = Path(path)
    if not source_path.exists():
        console.print(f"[red]Source path '{path}' does not exist.[/red]")
        raise typer.Exit(1)
        
    files = [source_path] if source_path.is_file() else list(source_path.rglob("*.py"))
    
    # Regex to find: # [PROMPT-LAB: NAME] \n NAME = """ CONTENT """
    pattern = re.compile(r'#\s*\[PROMPT-LAB:\s*([A-Za-z0-9_-]+)\]\s*\n\s*[A-Z0-9_-]+\s*=\s*"{3}(.*?)"{3}', re.DOTALL)
    
    synced_count = 0
    for f in files:
        content = f.read_text()
        matches = pattern.finditer(content)
        for match in matches:
            name = match.group(1).lower()
            prompt_content = match.group(2).strip()
            
            # Save to prompt-lab/prompts/
            output_file = PROMPTS_DIR / f"{name}.txt"
            output_file.write_text(prompt_content)
            console.print(f"  [green]Synced:[/green] {name} from {f.name}")
            synced_count += 1
            
    if synced_count == 0:
        console.print("[yellow]No markers found. Use: # [PROMPT-LAB: NAME] before a triple-quoted string variable.[/yellow]")
    else:
        console.print(f"\n[bold green]Successfully synced {synced_count} prompt(s).[/bold green]")


@app.command()
def changelog(
    prompt: str = typer.Option("", "--prompt", "-p", help="Filter by prompt name (empty=all)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries"),
):
    """View prompt version changelog (from optimize runs)."""
    changelog_file = PROMPTS_DIR / "changelog.jsonl"
    if not changelog_file.exists():
        console.print("No changelog yet. Run 'optimize' to generate prompt variations.")
        return

    entries = []
    for line in changelog_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if prompt and prompt not in entry.get("prompt", ""):
                continue
            entries.append(entry)
        except json.JSONDecodeError:
            continue

    if not entries:
        console.print(f"No changelog entries{f' for {prompt}' if prompt else ''}.")
        return

    table = Table(title="Prompt Changelog")
    table.add_column("Timestamp", style="dim")
    table.add_column("Prompt", style="cyan")
    table.add_column("Parent", style="yellow")
    table.add_column("Score", style="green")
    table.add_column("Description")

    for entry in entries[-limit:]:
        table.add_row(
            entry.get("timestamp", "")[:19],
            entry.get("prompt", ""),
            entry.get("parent", ""),
            f"{entry.get('score', 0):.3f}",
            entry.get("description", "")[:60],
        )

    console.print(table)


@app.command()
def history(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt name"),
):
    """View evaluation history for a prompt."""
    results_dir = SKILL_DIR / "results"
    if not results_dir.exists():
        console.print("No results found.")
        return

    pattern = f"{prompt}_*.json"
    result_files = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not result_files:
        console.print(f"No results found for prompt '{prompt}'")
        return

    console.print(f"[bold]History for prompt '{prompt}'[/bold]\n")

    table = Table()
    table.add_column("Timestamp", style="dim")
    table.add_column("Model", style="cyan")
    table.add_column("F1", style="green")
    table.add_column("Corrections", style="yellow")
    table.add_column("Status")

    for rf in result_files[:10]:
        data = json.loads(rf.read_text())
        metrics = data.get("metrics", {})
        passed = data.get("passed", metrics.get("avg_f1", 0) >= 0.8)

        table.add_row(
            data.get("timestamp", "")[:19],
            data.get("model", ""),
            f"{metrics.get('avg_f1', 0):.3f}",
            str(metrics.get("correction_rounds", 0)),
            "[green]PASS[/green]" if passed else "[red]FAIL[/red]",
        )

    console.print(table)



