"""main - discover-lut.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import typer
import httpx
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

# Verified communal cinematic LUTs (Rec.709 targets from YahiaAngelo/Film-Luts)
LUT_CATALOG = {
    "noir_classic_v1": {
        "name": "Classic Noir",
        "description": "High contrast, deep blacks, subtle silver grain feel.",
        "url": "https://raw.githubusercontent.com/YahiaAngelo/Film-Luts/main/luts/bw/agfa_apx_100.cube"
    },
    "teal_orange_v1": {
        "name": "Blockbuster Teal & Orange",
        "description": "Modern cinematic grade with warm skin tones and cool shadows.",
        "url": "https://raw.githubusercontent.com/YahiaAngelo/Film-Luts/main/luts/colorslide/agfa_precisa_100.cube"
    },
    "film_stock_2383": {
        "name": "Kodak 2383 Print",
        "description": "Standard Hollywood print stock emulation.",
        "url": "https://raw.githubusercontent.com/YahiaAngelo/Film-Luts/main/luts/print/kodak_2383_constlmap.cube"
    }
}

app = typer.Typer()

@app.command("list")
def list_luts():
    """List available vetted LUT presets."""
    table = Table(title="Horus Vetted LUT Catalog")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")

    for lut_id, info in LUT_CATALOG.items():
        table.add_row(lut_id, info["name"], info["description"])

    console.print(table)

@app.command()
def fetch(
    lut_id: str = typer.Argument(help="LUT ID from the catalog"),
    output_dir: str = typer.Option(".", "-o", "--output-dir", help="Directory to save the LUT"),
):
    """Fetch a LUT by ID from the catalog."""
    if lut_id not in LUT_CATALOG:
        console.print(f"[red]Error: LUT ID '{lut_id}' not found in catalog.[/red]")
        return

    info = LUT_CATALOG[lut_id]
    output_path = Path(output_dir) / f"{lut_id}.cube"

    console.print(f"[blue]Fetching {info['name']}...[/blue]")
    try:
        response = httpx.get(info["url"])
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)

        console.print(f"[green]✓ Saved to {output_path}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to fetch LUT: {e}[/red]")

if __name__ == "__main__":
    app()
