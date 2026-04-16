#!/usr/bin/env python3
"""Convert monochrome PNG icons into cleaned SVGs using ImageMagick and potrace."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import typer

NS = {"svg": "http://www.w3.org/2000/svg"}
ET.register_namespace("", NS["svg"])


REQUIRED_BINS = ("magick", "potrace", "identify")


def require_bins() -> dict[str, str]:
    missing = [name for name in REQUIRED_BINS if shutil.which(name) is None]
    if missing:
        raise SystemExit(f"missing required binaries: {', '.join(missing)}")
    return {name: shutil.which(name) or "" for name in REQUIRED_BINS}


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def identify_size(path: Path) -> str:
    result = subprocess.run(
        ["identify", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def trace_png(input_png: Path, threshold: str, tmpdir: Path) -> Path:
    pbm = tmpdir / "trace.pbm"
    svg = tmpdir / "trace.svg"
    run([
        "magick",
        str(input_png),
        "-colorspace",
        "gray",
        "-threshold",
        threshold,
        str(pbm),
    ])
    run(["potrace", str(pbm), "-s", "-o", str(svg)])
    return svg


def clean_svg(traced_svg: Path, output_svg: Path, mode: str, color: str, stroke_width: float, background: str) -> None:
    tree = ET.parse(traced_svg)
    root = tree.getroot()
    view_box = root.attrib.get("viewBox", "0 0 512 512")

    traced_group = root.find("svg:g", NS)
    if traced_group is None:
        raise SystemExit("potrace output missing <g> group")

    new_root = ET.Element(
        "{http://www.w3.org/2000/svg}svg",
        {
            "xmlns": NS["svg"],
            "viewBox": view_box,
            "fill": "none" if mode == "stroke" else color,
        },
    )

    if background != "transparent":
        min_x, min_y, width, height = view_box.split()
        ET.SubElement(
            new_root,
            "{http://www.w3.org/2000/svg}rect",
            {
                "x": min_x,
                "y": min_y,
                "width": width,
                "height": height,
                "fill": background,
            },
        )

    group_attrs = {k: v for k, v in traced_group.attrib.items() if k != "fill"}
    group_attrs["fill"] = color if mode == "fill" else "none"
    if mode == "stroke":
        group_attrs["stroke"] = color
        group_attrs["stroke-width"] = str(stroke_width)
        group_attrs["stroke-linejoin"] = "round"
        group_attrs["stroke-linecap"] = "round"

    new_group = ET.SubElement(new_root, "{http://www.w3.org/2000/svg}g", group_attrs)
    for child in traced_group:
        if child.tag.endswith("metadata"):
            continue
        new_group.append(child)
        if mode == "stroke":
            child.attrib["fill"] = "none"
            child.attrib["stroke"] = color
            child.attrib["stroke-width"] = str(stroke_width)
            child.attrib["stroke-linejoin"] = "round"
            child.attrib["stroke-linecap"] = "round"
        else:
            child.attrib["fill"] = color
            child.attrib.pop("stroke", None)
            child.attrib.pop("stroke-width", None)
            child.attrib.pop("stroke-linejoin", None)
            child.attrib.pop("stroke-linecap", None)

    ET.ElementTree(new_root).write(output_svg, encoding="utf-8", xml_declaration=True)


def cmd_check() -> int:
    bins = require_bins()
    for name, path in bins.items():
        print(f"{name}: {path}")
    return 0


app = typer.Typer(name="png-svg-converter", no_args_is_help=True)


@app.command()
def check() -> None:
    """Check that required binaries are available."""
    bins = require_bins()
    for name, path in bins.items():
        print(f"{name}: {path}")


@app.command()
def convert(
    input_path: str = typer.Argument(..., help="Input PNG file"),
    output: str = typer.Option(..., "--output", help="Output SVG file"),
    threshold: str = typer.Option("50%", "--threshold", help="Binarization threshold"),
    mode: str = typer.Option("fill", "--mode", help="SVG mode: fill or stroke"),
    color: str = typer.Option("currentColor", "--color", help="SVG color"),
    stroke_width: float = typer.Option(1.5, "--stroke-width", help="Stroke width (stroke mode)"),
    background: str = typer.Option("transparent", "--background", help="Background color"),
) -> None:
    """Convert a monochrome PNG icon to a cleaned SVG."""
    if mode not in ("fill", "stroke"):
        raise typer.BadParameter(f"Invalid mode: {mode}. Choose fill or stroke")
    require_bins()
    input_png = Path(input_path).expanduser().resolve()
    output_svg = Path(output).expanduser().resolve()
    if not input_png.exists():
        raise SystemExit(f"input not found: {input_png}")
    output_svg.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="png-svg-converter-") as tmp:
        tmpdir = Path(tmp)
        traced = trace_png(input_png, threshold, tmpdir)
        clean_svg(traced, output_svg, mode, color, stroke_width, background)

    print(f"input: {identify_size(input_png)}")
    print(f"output: {output_svg}")
    print(f"mode: {mode}")
    print(f"color: {color}")
    if mode == "stroke":
        print(f"stroke_width: {stroke_width}")


if __name__ == "__main__":
    app()
