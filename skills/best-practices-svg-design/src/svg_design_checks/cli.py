"""Typer CLI for deterministic SVG card layout checks.

Commands: spacing (rows/columns/labels/connectors from artwork), grid
(manifest check), solve (emit uniform-grid coordinates), composition
(rule-of-thirds and golden-ratio metrics). Exit 1 on any failed check.
A failing rule may only be waived by a human-authored waiver file passed
via --waiver naming approved_by, rules, and reason.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
from loguru import logger

from .geometry import audit_composition, audit_spacing, load_layout

app = typer.Typer(add_completion=False, help=__doc__)


def _load_waiver(waiver: Path | None) -> dict:
    if waiver is None:
        return {}
    data = json.loads(waiver.read_text())
    if not data.get("approved_by") or not data.get("reason") or not data.get("rules"):
        raise typer.BadParameter("waiver must name approved_by, reason, and rules")
    logger.warning("HUMAN WAIVER active: {} by {} — {}", data["rules"], data["approved_by"], data["reason"])
    return data


@app.command()
def spacing(
    svg: Path,
    tol: float = typer.Option(2.0, help="max deviation in px"),
    waiver: Path = typer.Option(None, help="human waiver JSON (approved_by, rules, reason)"),
) -> None:
    """Assert even spacing computed from the SVG artwork itself."""
    w = _load_waiver(waiver)
    ok, findings = audit_spacing(load_layout(str(svg)), tol)
    waived_all = w and "spacing" in w.get("rules", [])
    for line in findings:
        print(line)
    for line in findings:
        if "SPACING_FAIL" in line:
            print(">>", line)
    if ok or waived_all:
        print("SPACING_OK" + (" (WAIVED)" if not ok else ""))
        raise typer.Exit(0)
    print("SPACING_FAIL")
    raise typer.Exit(1)


@app.command()
def pixels(
    png: Path,
    canvas_h: float = typer.Option(1200.0, help="artwork canvas height for tolerance scaling"),
    tol: float = typer.Option(4.0, help="max deviation in SVG px"),
    manifest: Path = typer.Option(None, help="grid manifest: assert painted bands land on row spans"),
) -> None:
    """Assert a rendered screenshot's ink bands sit on the manifest grid."""
    from .raster import audit_pixels

    try:
        ok, findings = audit_pixels(str(png), canvas_h, tol, manifest_path=str(manifest) if manifest else None)
    except Exception as exc:
        logger.error("unreadable screenshot {}: {}", png, exc)
        print(f"PIXELS_FAIL unreadable screenshot: {exc}")
        raise typer.Exit(1)
    for line in findings:
        print(line)
    print("PIXELS_OK" if ok else "PIXELS_FAIL")
    raise typer.Exit(0 if ok else 1)


@app.command()
def composition(svg: Path) -> None:
    """Report rule-of-thirds and golden-ratio deltas (advisory metrics)."""
    for line in audit_composition(load_layout(str(svg))):
        print(line)


@app.command()
def grid(manifest: Path) -> None:
    """Check a solved grid manifest (rows y/h) for uniform gaps and margins."""
    import subprocess
    import sys
    script = Path(__file__).resolve().parents[2] / "scripts" / "check_grid.py"
    raise typer.Exit(subprocess.call([sys.executable, str(script), str(manifest)]))


@app.command()
def place(svg: Path, manifest: Path) -> None:
    """Place an SVG's rows onto a solved grid manifest (machine-readable law)."""
    import subprocess
    import sys
    script = Path(__file__).resolve().parents[2] / "scripts" / "place_grid.py"
    raise typer.Exit(subprocess.call([sys.executable, str(script), str(svg), str(manifest)]))


@app.command()
def solve(spec: Path) -> None:
    """Emit exact row y-positions for a uniform grid from row heights."""
    import subprocess
    import sys
    script = Path(__file__).resolve().parents[2] / "scripts" / "solve_grid.py"
    raise typer.Exit(subprocess.call([sys.executable, str(script), str(spec)]))


if __name__ == "__main__":
    app()
