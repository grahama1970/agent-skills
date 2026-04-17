"""
CLI commands for fixture-tricky.

Commands: false-tables, malformed-tables, cursed-text, layout-traps,
requirements, math-noise, gauntlet, list-tricks, single.
"""
import json
from pathlib import Path
from typing import Optional

import typer

from gen_app import app
from gen_tricks_core import (
    FALSE_TABLE_TRICKS,
    CLASSIFICATION_TRICKS,
    MALFORMED_TABLE_TRICKS,
    CURSED_TEXT_TRICKS,
    LAYOUT_TRAP_TRICKS,
)
from gen_tricks_ext import (
    REQUIREMENTS_TRICKS,
    MATH_NOISE_TRICKS,
)
from gen_generators import (
    generate_false_tables_pdf,
    generate_malformed_tables_pdf,
    generate_cursed_text_pdf,
    generate_layout_traps_pdf,
    generate_requirements_pdf,
    generate_math_noise_pdf,
    generate_gauntlet_pdf,
)
from gen_ground_truth import build_ground_truth, write_ground_truth


def _emit_gt(output: Path, tricks_used: list[str], category: str):
    """Build and write ground truth sidecar after fixture generation."""
    gt = build_ground_truth(output, tricks_used, category)
    gt_path = write_ground_truth(output, gt)
    typer.echo(f"Ground truth: {gt_path} ({gt['assertions']})")


@app.command("false-tables")
def cmd_false_tables(
    output: Path = typer.Option(Path("false_tables.pdf"), "--output", "-o"),
    tricks: Optional[str] = typer.Option(None, "--tricks", "-t", help="Comma-separated trick names"),
):
    """Generate PDF with false-positive table content."""
    output.parent.mkdir(parents=True, exist_ok=True)
    trick_list = tricks.split(",") if tricks else None
    generate_false_tables_pdf(output, trick_list)
    _emit_gt(output, trick_list or list(FALSE_TABLE_TRICKS.keys()), "false-tables")


@app.command("malformed-tables")
def cmd_malformed_tables(
    output: Path = typer.Option(Path("malformed_tables.pdf"), "--output", "-o"),
    tricks: Optional[str] = typer.Option(None, "--tricks", "-t", help="Comma-separated trick names"),
):
    """Generate PDF with malformed/corrupted tables."""
    output.parent.mkdir(parents=True, exist_ok=True)
    trick_list = tricks.split(",") if tricks else None
    generate_malformed_tables_pdf(output, trick_list)
    _emit_gt(output, trick_list or list(MALFORMED_TABLE_TRICKS.keys()), "malformed-tables")


@app.command("cursed-text")
def cmd_cursed_text(
    output: Path = typer.Option(Path("cursed_text.pdf"), "--output", "-o"),
    tricks: Optional[str] = typer.Option(None, "--tricks", "-t", help="Comma-separated trick names"),
):
    """Generate PDF with text extraction nightmares."""
    output.parent.mkdir(parents=True, exist_ok=True)
    trick_list = tricks.split(",") if tricks else None
    generate_cursed_text_pdf(output, trick_list)
    _emit_gt(output, trick_list or list(CURSED_TEXT_TRICKS.keys()), "cursed-text")


@app.command("layout-traps")
def cmd_layout_traps(
    output: Path = typer.Option(Path("layout_traps.pdf"), "--output", "-o"),
    tricks: Optional[str] = typer.Option(None, "--tricks", "-t", help="Comma-separated trick names"),
):
    """Generate PDF with layout patterns that confuse extractors."""
    output.parent.mkdir(parents=True, exist_ok=True)
    trick_list = tricks.split(",") if tricks else None
    generate_layout_traps_pdf(output, trick_list)
    _emit_gt(output, trick_list or list(LAYOUT_TRAP_TRICKS.keys()), "layout-traps")


@app.command("requirements")
def cmd_requirements(
    output: Path = typer.Option(Path("requirements_tricky.pdf"), "--output", "-o"),
    tricks: Optional[str] = typer.Option(None, "--tricks", "-t", help="Comma-separated trick names"),
):
    """Generate PDF with requirements extraction test patterns (for S08)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    trick_list = tricks.split(",") if tricks else None
    generate_requirements_pdf(output, trick_list)
    _emit_gt(output, trick_list or list(REQUIREMENTS_TRICKS.keys()), "requirements")


@app.command("math-noise")
def cmd_math_noise(
    output: Path = typer.Option(Path("math_noise.pdf"), "--output", "-o"),
    tricks: Optional[str] = typer.Option(None, "--tricks", "-t", help="Comma-separated trick names"),
):
    """Generate PDF with math noise test patterns."""
    output.parent.mkdir(parents=True, exist_ok=True)
    trick_list = tricks.split(",") if tricks else None
    generate_math_noise_pdf(output, trick_list)
    _emit_gt(output, trick_list or list(MATH_NOISE_TRICKS.keys()), "math-noise")


@app.command("gauntlet")
def cmd_gauntlet(
    output: Path = typer.Option(Path("gauntlet.pdf"), "--output", "-o"),
):
    """Generate comprehensive stress test with ALL tricks."""
    output.parent.mkdir(parents=True, exist_ok=True)
    generate_gauntlet_pdf(output)
    # Gauntlet uses ALL tricks from all categories
    all_tricks = (
        list(FALSE_TABLE_TRICKS.keys()) + list(MALFORMED_TABLE_TRICKS.keys()) +
        list(CURSED_TEXT_TRICKS.keys()) + list(LAYOUT_TRAP_TRICKS.keys()) +
        list(REQUIREMENTS_TRICKS.keys()) + list(MATH_NOISE_TRICKS.keys())
    )
    _emit_gt(output, all_tricks, "gauntlet")


@app.command("list-tricks")
def cmd_list_tricks(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all available tricks."""
    all_tricks = {
        "false-tables": FALSE_TABLE_TRICKS,
        "malformed-tables": MALFORMED_TABLE_TRICKS,
        "cursed-text": CURSED_TEXT_TRICKS,
        "layout-traps": LAYOUT_TRAP_TRICKS,
        "requirements": REQUIREMENTS_TRICKS,
        "math-noise": MATH_NOISE_TRICKS,
    }

    if category:
        if category not in all_tricks:
            typer.echo(f"Unknown category: {category}")
            typer.echo(f"Available: {', '.join(all_tricks.keys())}")
            raise typer.Exit(1)
        all_tricks = {category: all_tricks[category]}

    if json_output:
        # Simplify for JSON output
        output = {}
        for cat, tricks in all_tricks.items():
            output[cat] = {name: trick.get("description", "") for name, trick in tricks.items()}
        typer.echo(json.dumps(output, indent=2))
    elif category == "classification":
        tricks = CLASSIFICATION_TRICKS
    else:
        for cat, tricks in all_tricks.items():
            typer.echo(f"\n{cat}:")
            for name, trick in tricks.items():
                desc = trick.get("description", "No description")
                typer.echo(f"  {name:25} {desc}")


@app.command("single")
def cmd_single(
    trick: str = typer.Argument(..., help="Trick name (e.g., 'numbered-list', 'missing-columns')"),
    output: Path = typer.Option(Path("single_trick.pdf"), "--output", "-o"),
):
    """Generate PDF with a single specific trick."""
    output.parent.mkdir(parents=True, exist_ok=True)

    # Find which category contains this trick
    cat = None
    if trick in FALSE_TABLE_TRICKS:
        generate_false_tables_pdf(output, [trick])
        cat = "false-tables"
    elif trick in MALFORMED_TABLE_TRICKS:
        generate_malformed_tables_pdf(output, [trick])
        cat = "malformed-tables"
    elif trick in CURSED_TEXT_TRICKS:
        generate_cursed_text_pdf(output, [trick])
        cat = "cursed-text"
    elif trick in LAYOUT_TRAP_TRICKS:
        generate_layout_traps_pdf(output, [trick])
        cat = "layout-traps"
    elif trick in REQUIREMENTS_TRICKS:
        generate_requirements_pdf(output, [trick])
        cat = "requirements"
    elif trick in MATH_NOISE_TRICKS:
        generate_math_noise_pdf(output, [trick])
        cat = "math-noise"
    else:
        typer.echo(f"Unknown trick: {trick}")
        typer.echo("Use 'list-tricks' to see available tricks")
        raise typer.Exit(1)
    _emit_gt(output, [trick], cat)


if __name__ == "__main__":
    app()

