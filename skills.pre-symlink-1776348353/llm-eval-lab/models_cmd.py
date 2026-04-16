"""Model listing and memory CLI commands."""
import json
from pathlib import Path

import typer
from rich.table import Table

from config import SKILL_DIR, ensure_dirs
from model_memory import get_model_memory, get_model_recommendations, seed_known_observations

from eval_app import app, console


@app.command("models")
def list_models(
    capability: str = typer.Option("", "--cap", "-c", help="Filter by capability: json, reasoning, agentic, coding"),
    recommend: bool = typer.Option(False, "--recommend", "-r", help="Show recommendations from memory"),
    prompt_type: str = typer.Option("taxonomy", "--type", "-t", help="Prompt type for recommendations"),
):
    """List available models with metrics and recommendations."""
    models_file = SKILL_DIR / "models.json"

    if not models_file.exists():
        console.print("[red]models.json not found[/red]")
        raise typer.Exit(1)

    models = json.loads(models_file.read_text())

    if recommend:
        model_mem = get_model_memory()
        if model_mem.enabled:
            console.print(get_model_recommendations(model_mem, prompt_type))
        else:
            console.print("[dim]Model memory not available[/dim]")
        console.print()

    table = Table(title="Available Models")
    table.add_column("Alias", style="cyan")
    table.add_column("Params", style="green")
    table.add_column("Quant", style="yellow")
    table.add_column("Arch")
    table.add_column("Experts")
    table.add_column("Context")
    table.add_column("JSON")
    table.add_column("Caps", style="dim")

    for alias, config in models.items():
        if alias.startswith("_"):
            continue
        if not isinstance(config, dict):
            continue

        if capability:
            cap_map = {
                "json": "json_mode",
                "reasoning": "reasoning",
                "agentic": "agentic",
                "coding": "coding",
            }
            cap_key = cap_map.get(capability, capability)
            if not config.get(cap_key):
                continue

        params = config.get("params_b", "?")
        active = config.get("active_params_b")
        quant = config.get("quantization", "?")
        arch = config.get("architecture", "?")
        experts = config.get("experts")
        experts_active = config.get("experts_active")
        ctx = config.get("context_k", "?")
        json_mode = "Y" if config.get("json_mode") else "N"

        caps = []
        if config.get("reasoning"):
            caps.append("reason")
        if config.get("thinking_mode"):
            caps.append("think")
        if config.get("agentic"):
            caps.append("agent")
        if config.get("coding"):
            caps.append("code")
        if config.get("taxonomy_f1"):
            caps.append(f"F1:{config['taxonomy_f1']}")

        param_str = f"{params}B" if not active else f"{params}B/{active}B"
        expert_str = f"{experts_active}/{experts}" if experts else "-"
        ctx_str = f"{ctx}K" if ctx != "?" else "?"
        caps_str = ", ".join(caps)

        table.add_row(alias, param_str, quant, arch, expert_str, ctx_str, json_mode, caps_str)

    console.print(table)


@app.command("seed-memory")
def seed_memory():
    """Seed model memory with known observations."""
    model_mem = get_model_memory()
    if not model_mem.enabled:
        console.print("[yellow]Model memory not available (standalone mode)[/yellow]")
        return

    stored = seed_known_observations(model_mem)
    console.print(f"[green]Seeded {stored} known observations into model memory[/green]")
