"""One straightforward fan-out: N candidate visuals from a prompt, image, or table.

Generating alternatives should not require knowing which backend fits. This
module takes the input you actually have and routes it:

    prompt  -> imagegen, run by codex under an OAuth session, across style axes
    image   -> imagegen re-interpretations of an existing picture
    table   -> create-figure, one candidate per chart type (bar/hbar/pie/line)

Every lane produces the same three things: numbered candidate files, a contact
sheet to choose from, and a ``candidates.json`` receipt recording exactly how
each was produced. Selection stays human — nothing is auto-adopted into a deck,
because a generated visual enters through the normal asset intake where the
GENERATED_ASSET_CLAIM_SURFACE gate applies (a generated image may decorate a
claim, never evidence one).

Failure modes: a missing backend reports NEEDS_ATTENTION with the exact command
that was unavailable; a lane that produces zero candidates fails rather than
returning an empty directory that looks like success.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from loguru import logger

InputKind = Literal["prompt", "image", "table"]

STYLE_AXES = [
    "clean minimal geometric composition, generous negative space",
    "abstract technical illustration, subtle grid texture",
    "dramatic single focal object, soft depth of field",
    "flat vector style, bold shapes, no text",
]
CHART_TYPES = ["bar", "hbar", "pie", "line"]
CODEX_TIMEOUT_SECONDS = 600
FIGURE_TIMEOUT_SECONDS = 180


def _contact_sheet(images: list[Path], destination: Path) -> Path | None:
    """Tile candidates so a human can choose at a glance."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:  # pragma: no cover - Pillow is a declared dependency
        return None
    loaded = []
    for index, path in enumerate(images, start=1):
        try:
            loaded.append((index, Image.open(path).convert("RGB")))
        except OSError:
            logger.warning("candidate {} is not a readable image: {}", index, path)
    if not loaded:
        return None
    width = 520
    tiles = []
    for index, image in loaded:
        scaled = image.resize((width, max(1, int(image.height * width / image.width))))
        tile = Image.new("RGB", (width, scaled.height + 28), "#111111")
        tile.paste(scaled, (0, 28))
        ImageDraw.Draw(tile).text((8, 8), f"candidate {index}", fill="#ffcc44")
        tiles.append(tile)
    columns = 2 if len(tiles) > 1 else 1
    rows = (len(tiles) + columns - 1) // columns
    cell_h = max(t.height for t in tiles) + 8
    sheet = Image.new("RGB", (width * columns + 8 * (columns + 1), cell_h * rows + 8), "#111111")
    for position, tile in enumerate(tiles):
        x = 8 + (position % columns) * (width + 8)
        y = 8 + (position // columns) * cell_h
        sheet.paste(tile, (x, y))
    sheet.save(destination)
    return destination


def _run_table_lane(table: Path, output_dir: Path, count: int, title: str) -> list[dict]:
    """create-figure is the right backend here: real data, one chart per type."""
    figure_cli = Path(__file__).resolve().parents[3] / "create-figure" / "run.sh"
    if not figure_cli.is_file():
        raise FileNotFoundError(f"create-figure not available at {figure_cli}")
    produced: list[dict] = []
    for index, chart_type in enumerate(CHART_TYPES[:count], start=1):
        target = output_dir / f"candidate-{index}-{chart_type}.png"
        command = [
            str(figure_cli), "metrics", "--input", str(table), "--output", str(target),
            "--type", chart_type, "--title", title, "--format", "png",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=FIGURE_TIMEOUT_SECONDS)
        if result.returncode != 0 or not target.is_file():
            logger.warning("chart '{}' failed (exit {})", chart_type, result.returncode)
            continue
        produced.append({"candidate": index, "backend": "create-figure",
                         "variant": chart_type, "path": str(target),
                         "command": " ".join(command)})
    return produced


def _run_codex_lane(brief: str, output_dir: Path, count: int, *, image: Path | None) -> list[dict]:
    """imagegen under codex's OAuth session — this house has no API-key lane."""
    if not shutil.which("codex"):
        raise FileNotFoundError("codex CLI not found; OAuth image generation unavailable")
    produced: list[dict] = []
    for index, axis in enumerate(STYLE_AXES[:count], start=1):
        target = output_dir / f"candidate-{index}.png"
        reference = f" Use {image} as the visual reference to reinterpret." if image else ""
        instruction = (
            "Use the imagegen skill's built-in image_gen tool to generate ONE image "
            f"and save it to {target}.{reference} Brief: {brief} Style: {axis}. "
            "No text or lettering in the image."
        )
        result = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check", instruction],
            capture_output=True, text=True, timeout=CODEX_TIMEOUT_SECONDS,
        )
        if result.returncode != 0 or not target.is_file():
            logger.warning("variant {} failed (codex exit {})", index, result.returncode)
            continue
        produced.append({"candidate": index, "backend": "imagegen (codex OAuth)",
                         "variant": axis, "path": str(target)})
    return produced


def generate_variations(
    *,
    output_dir: Path,
    prompt: str | None = None,
    image: Path | None = None,
    table: Path | None = None,
    count: int = 4,
    title: str = "Candidate",
    execute: bool = False,
) -> dict:
    """Fan out N candidates from whichever input was supplied."""
    supplied = [("prompt", prompt), ("image", image), ("table", table)]
    given = [name for name, value in supplied if value]
    if len(given) != 1:
        raise ValueError(f"supply exactly one of --prompt/--image/--table (got {given or 'none'})")
    kind: InputKind = given[0]  # type: ignore[assignment]
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = {
        "schema": "pitchdeck.variation_receipt.v1",
        "input_kind": kind,
        "count": count,
        "backend": "create-figure" if kind == "table" else "imagegen (codex OAuth)",
        "output_dir": str(output_dir),
    }

    if not execute:
        plan["status"] = "PLANNED"
        plan["variants"] = CHART_TYPES[:count] if kind == "table" else STYLE_AXES[:count]
        plan["next_command"] = "re-run with --execute to produce candidates"
        (output_dir / "candidates.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
        return plan

    try:
        if kind == "table":
            produced = _run_table_lane(Path(table), output_dir, count, title)  # type: ignore[arg-type]
        else:
            brief = prompt or f"a slide illustration reinterpreting {Path(image).name}"  # type: ignore[arg-type]
            produced = _run_codex_lane(brief, output_dir, count, image=Path(image) if image else None)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        plan.update({"status": "NEEDS_ATTENTION", "reason": str(exc), "candidates": []})
        (output_dir / "candidates.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
        return plan

    if not produced:
        plan.update({"status": "NEEDS_ATTENTION",
                     "reason": "every variant failed — no candidate was produced", "candidates": []})
        (output_dir / "candidates.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
        return plan

    sheet = _contact_sheet([Path(p["path"]) for p in produced], output_dir / "contact-sheet.png")
    plan.update({
        "status": "PASS",
        "candidates": produced,
        "contact_sheet": str(sheet) if sheet else None,
        "selection": "human selects; a chosen file enters through the normal asset intake "
                     "(GENERATED_ASSET_CLAIM_SURFACE applies)",
    })
    (output_dir / "candidates.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    return plan
