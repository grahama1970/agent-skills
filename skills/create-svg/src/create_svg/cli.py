"""Thin Typer CLI for README SVG generation, inspection, preview, and validation.

Business logic lives in named modules. CLI failures are logged with Loguru and exit
non-zero; successful commands print concrete artifact paths or typed receipts.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer
import yaml
from loguru import logger

from .inspect_style import inspect_sources
from .io import available_templates, load_theme, template_path
from .preview import write_preview
from .render import render_scene_file
from .validate import validate_svg_file, verify_scene_file

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _write_receipt(path: Path | None, payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if path is None:
        typer.echo(rendered)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered + "\n", encoding="utf-8")
    typer.echo(str(path))


@app.command("templates")
def list_templates() -> None:
    """List bundled semantic scene templates."""

    for name in available_templates():
        typer.echo(name)


@app.command()
def new(
    template: str = typer.Argument(..., help="Bundled template name"),
    output: Path = typer.Argument(..., help="Destination scene YAML"),
    force: bool = typer.Option(False, "--force", help="Replace an existing destination"),
) -> None:
    """Copy a starter semantic scene."""

    try:
        source = template_path(template)
        if output.exists() and not force:
            raise ValueError(f"destination exists; pass --force to replace it: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        typer.echo(str(output))
    except Exception as exc:
        logger.error("new command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def render(
    scene: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Argument(...),
) -> None:
    """Compile one validated scene into deterministic SVG."""

    try:
        render_scene_file(scene.resolve(), output.resolve())
        typer.echo(str(output.resolve()))
    except Exception as exc:
        logger.error("render command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def verify(
    scene: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Argument(...),
    receipt: Path = typer.Option(..., "--receipt", help="JSON validation receipt"),
    browser: bool = typer.Option(False, "--browser/--no-browser", help="Run real Chromium img-mode verification"),
) -> None:
    """Render twice, compare bytes, validate, and optionally verify in Chromium."""

    try:
        result = verify_scene_file(scene.resolve(), output.resolve(), browser=browser)
        _write_receipt(receipt.resolve(), result.model_dump(mode="json"))
        typer.echo(result.status)
        if result.status != "PASS":
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.error("verify command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def validate(
    svg: Path = typer.Argument(..., exists=True, dir_okay=False),
    receipt: Path | None = typer.Option(None, "--receipt", help="Optional JSON receipt path"),
    theme: str | None = typer.Option(None, "--theme", help="Bundled theme name or YAML path"),
    strict_theme: bool = typer.Option(False, "--strict-theme", help="Reject colors and stroke widths outside the theme"),
    browser: bool = typer.Option(False, "--browser/--no-browser", help="Run real Chromium img-mode verification"),
) -> None:
    """Validate an existing SVG and fail closed on any error finding."""

    try:
        loaded_theme = load_theme(theme, Path.cwd()) if theme else None
        result = validate_svg_file(
            svg.resolve(),
            theme=loaded_theme,
            strict_theme=strict_theme,
            browser=browser,
        )
        _write_receipt(receipt.resolve() if receipt else None, result.model_dump(mode="json"))
        typer.echo(result.status)
        if result.status != "PASS":
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.error("validate command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def inspect(
    sources: list[Path] = typer.Argument(..., exists=True),
    output: Path = typer.Option(..., "--output", help="YAML inspection report"),
) -> None:
    """Extract visual-system evidence from SVG files or directories."""

    try:
        report = inspect_sources(tuple(path.resolve() for path in sources))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
        typer.echo(str(output.resolve()))
    except Exception as exc:
        logger.error("inspect command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def preview(
    svg: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Argument(...),
) -> None:
    """Write a local self-contained HTML viewer."""

    try:
        write_preview(svg.resolve(), output.resolve())
        typer.echo(str(output.resolve()))
    except Exception as exc:
        logger.error("preview command failed: {}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def snippet(
    svg: Path = typer.Argument(...),
    alt: str = typer.Option(..., "--alt", help="Meaningful image description"),
    width: int = typer.Option(850, "--width", min=1, max=4000),
) -> None:
    """Print centered README HTML without modifying README.md."""

    escaped_path = str(svg).replace("&", "&amp;").replace('"', "&quot;")
    escaped_alt = alt.replace("&", "&amp;").replace('"', "&quot;")
    typer.echo(
        "<p align=\"center\">\n"
        f"  <img src=\"{escaped_path}\" alt=\"{escaped_alt}\" width=\"{width}\">\n"
        "</p>"
    )


if __name__ == "__main__":
    app()
