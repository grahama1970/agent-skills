#!/usr/bin/env python3
"""
Utility CLI commands for fixture-graph skill.

Contains discovery, inspection, and help commands:
- check: Backend availability check
- domains: List visualization domains
- presets: Show IEEE presets and colormaps
- list: List commands by domain
- recommend: Recommend visualizations by data type
"""

import typer

from config import (
    DOMAIN_GROUPS,
    DATA_TYPE_RECOMMENDATIONS,
    IEEE_FIGURE_SIZES,
    COLORBLIND_SAFE_CMAPS,
    PROBLEMATIC_CMAPS,
    LEAN4_PROVE_SCRIPT,
)
from utils import (
    check_graphviz,
    check_mermaid,
    check_matplotlib,
    check_seaborn,
    check_plotly,
    check_networkx,
    check_pandas,
    check_squarify,
    check_scipy,
    check_control,
    check_pydeps,
    check_pyreverse,
)


def register_utility_commands(app: typer.Typer) -> None:
    """Register all utility/discovery commands on the given Typer app."""

    @app.command()
    def check() -> None:
        """Check available backends and dependencies."""
        typer.echo("Checking fixture-graph backends...")
        typer.echo("")

        checks = [
            ("Graphviz (dot)", check_graphviz()),
            ("Mermaid (mmdc)", check_mermaid()),
            ("matplotlib", check_matplotlib()),
            ("seaborn", check_seaborn()),
            ("plotly", check_plotly()),
            ("NetworkX", check_networkx()),
            ("pandas", check_pandas()),
            ("squarify", check_squarify()),
            ("scipy", check_scipy()),
            ("python-control", check_control()),
            ("pydeps", check_pydeps()),
            ("pyreverse", check_pyreverse()),
            ("lean4-prove", LEAN4_PROVE_SCRIPT.exists()),
        ]

        for name, available in checks:
            status = "[OK]" if available else "[NOT AVAILABLE]"
            typer.echo(f"  {name}: {status}")

        typer.echo("")
        available_count = sum(1 for _, a in checks if a)
        typer.echo(f"{available_count}/{len(checks)} backends available")

    @app.command()
    def domains() -> None:
        """List available visualization domains."""
        typer.echo("Available Visualization Domains")
        typer.echo("=" * 50)
        typer.echo("")

        for domain_name, info in DOMAIN_GROUPS.items():
            typer.echo(f"  {domain_name.upper()}")
            typer.echo(f"    {info['description']}")
            typer.echo(f"    Use when: {info['use_when']}")
            typer.echo(f"    Commands: {len(info['commands'])}")
            typer.echo("")

        typer.echo("Usage:")
        typer.echo("  fixture-graph list --domain <domain>  # Show commands for domain")
        typer.echo("  fixture-graph recommend --data-type <type>  # Get suggestions")

    @app.command()
    def presets() -> None:
        """Show IEEE figure size presets and colorblind-safe colormaps."""
        typer.echo("IEEE Figure Size Presets")
        typer.echo("=" * 40)
        for name, (w, h) in IEEE_FIGURE_SIZES.items():
            typer.echo(f"  {name:15} {w:.2f}\" x {h:.2f}\"")

        typer.echo("")
        typer.echo("Colorblind-Safe Colormaps (Recommended)")
        typer.echo("=" * 40)
        for cmap in COLORBLIND_SAFE_CMAPS:
            typer.echo(f"  {cmap}")

        typer.echo("")
        typer.echo("Avoid These Colormaps (Accessibility Issues)")
        typer.echo("=" * 40)
        for cmap in PROBLEMATIC_CMAPS:
            typer.echo(f"  {cmap}")

    @app.command("list")
    def list_commands(
        domain: str = typer.Option("", "--domain", "-d", help="Filter by domain"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command descriptions"),
    ) -> None:
        """List available commands, optionally filtered by domain."""
        if domain:
            domain_lower = domain.lower()
            if domain_lower not in DOMAIN_GROUPS:
                typer.echo(f"[ERROR] Unknown domain: {domain}", err=True)
                typer.echo(f"Available: {', '.join(DOMAIN_GROUPS.keys())}")
                raise typer.Exit(1)

            info = DOMAIN_GROUPS[domain_lower]
            typer.echo(f"Domain: {domain_lower.upper()} - {info['description']}")
            typer.echo(f"Use when: {info['use_when']}")
            typer.echo("")
            typer.echo("Commands:")
            for cmd in info["commands"]:
                typer.echo(f"  - {cmd}")
        else:
            typer.echo("All Visualization Commands by Domain")
            typer.echo("=" * 50)
            for domain_name, info in DOMAIN_GROUPS.items():
                typer.echo(f"\n{domain_name.upper()}: {info['description']}")
                typer.echo(f"  {', '.join(info['commands'])}")

    @app.command()
    def recommend(
        data_type: str = typer.Option("", "--data-type", "-t", help="Type of data"),
        show_types: bool = typer.Option(False, "--show-types", "-s", help="Show all supported data types"),
    ) -> None:
        """Recommend visualization commands based on data type."""
        if show_types or not data_type:
            typer.echo("Supported Data Types and Recommended Visualizations")
            typer.echo("=" * 50)
            for dt, commands in sorted(DATA_TYPE_RECOMMENDATIONS.items()):
                typer.echo(f"  {dt}: {', '.join(commands)}")
            typer.echo("")
            typer.echo("Usage: fixture-graph recommend --data-type <type>")
            return

        data_type_lower = data_type.lower().replace("-", "_").replace(" ", "_")
        if data_type_lower not in DATA_TYPE_RECOMMENDATIONS:
            typer.echo(f"[ERROR] Unknown data type: {data_type}", err=True)
            typer.echo(f"Available: {', '.join(sorted(DATA_TYPE_RECOMMENDATIONS.keys()))}")
            raise typer.Exit(1)

        commands = DATA_TYPE_RECOMMENDATIONS[data_type_lower]
        typer.echo(f"Recommended visualizations for '{data_type}':")
        typer.echo("")
        for i, cmd in enumerate(commands, 1):
            domain = "core"
            for d_name, d_info in DOMAIN_GROUPS.items():
                if cmd in d_info["commands"]:
                    domain = d_name
                    break
            typer.echo(f"  {i}. {cmd} (domain: {domain})")

        typer.echo("")
        typer.echo(f"Run: fixture-graph {commands[0]} --help  # for usage")
