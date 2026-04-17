"""create-design-board: Generate and maintain iterative design boards."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

app = typer.Typer(help="Design board generator for iterative visual review.")

# ---------------------------------------------------------------------------
# Task-monitor integration (mandatory per /best-practices-skills)
# ---------------------------------------------------------------------------

SKILLS_DIR = Path(__file__).parent.parent
TM_RUN = SKILLS_DIR / "task-monitor" / "run.sh"


def _tm(args: list[str]) -> bool:
    """Report to task-monitor. Fails silently if task-monitor not installed."""
    if not TM_RUN.exists():
        return False
    try:
        return subprocess.run(
            [str(TM_RUN), *args],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        ).returncode == 0
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
SIZE_VARIANTS = [72, 128, 256, 512]
DEFAULT_BG = "#0e0e1c"
DEFAULT_COLS = 3
CELL_PADDING = 20
LABEL_HEIGHT = 30
THUMB_SIZE = 72


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _collect_images(images_dir: Path) -> list[Path]:
    """Collect image files from a directory, sorted by name."""
    if not images_dir.is_dir():
        logger.error(f"'{images_dir}' is not a directory")
        raise typer.Exit(1)
    files = sorted(
        [f for f in images_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS],
        key=lambda p: p.name.lower(),
    )
    if not files:
        logger.error(f"no images found in '{images_dir}'")
        raise typer.Exit(1)
    return files


def _get_font(size: int = 14) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a clean font, fall back to default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _detect_round(board_path: Path | None, images_dir: Path | None) -> int:
    """Auto-detect round number from existing board or directory naming."""
    # Check existing board markdown for highest round number
    if board_path and board_path.exists():
        text = board_path.read_text()
        rounds = re.findall(r"[Rr]ound\s+(\d+)", text)
        if rounds:
            return max(int(r) for r in rounds) + 1

    # Check directory name for version pattern (v1, v2, etc.)
    if images_dir:
        match = re.search(r"v(\d+)", images_dir.name)
        if match:
            return int(match.group(1))

    return 1


def _make_composite(
    image_files: list[Path],
    output: Path,
    cols: int = DEFAULT_COLS,
    bg: str = DEFAULT_BG,
    title: str | None = None,
    cell_size: int = 256,
) -> None:
    """Build a composite PNG grid from a list of images."""
    bg_rgb = _hex_to_rgb(bg)
    n = len(image_files)
    rows = (n + cols - 1) // cols

    title_band = 60 if title else 0
    grid_w = cols * (cell_size + CELL_PADDING) + CELL_PADDING
    grid_h = rows * (cell_size + LABEL_HEIGHT + CELL_PADDING) + CELL_PADDING + title_band

    canvas = Image.new("RGB", (grid_w, grid_h), bg_rgb)
    draw = ImageDraw.Draw(canvas)

    if title:
        title_font = _get_font(24)
        draw.text((CELL_PADDING, 15), title, fill="white", font=title_font)

    label_font = _get_font(12)
    thumb_font = _get_font(9)

    for idx, img_path in enumerate(image_files):
        row, col = divmod(idx, cols)
        x = CELL_PADDING + col * (cell_size + CELL_PADDING)
        y = title_band + CELL_PADDING + row * (cell_size + LABEL_HEIGHT + CELL_PADDING)

        # Load and resize image to fit cell
        try:
            img = Image.open(img_path).convert("RGBA")
        except Exception as e:
            logger.warning(f"could not open {img_path}: {e}")
            continue

        img.thumbnail((cell_size, cell_size), Image.Resampling.LANCZOS)

        # Center image in cell
        paste_x = x + (cell_size - img.width) // 2
        paste_y = y + (cell_size - img.height) // 2

        # Paste with alpha compositing
        temp = Image.new("RGB", (img.width, img.height), bg_rgb)
        temp.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
        canvas.paste(temp, (paste_x, paste_y))

        # 72px thumbnail in top-right corner of cell
        thumb = img.copy()
        thumb.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
        thumb_temp = Image.new("RGB", (thumb.width, thumb.height), bg_rgb)
        thumb_temp.paste(thumb, mask=thumb.split()[3] if thumb.mode == "RGBA" else None)
        # Draw a subtle border around thumbnail
        thumb_x = x + cell_size - thumb.width - 4
        thumb_y = y + 4
        canvas.paste(thumb_temp, (thumb_x, thumb_y))
        draw.rectangle(
            [thumb_x - 1, thumb_y - 1, thumb_x + thumb.width, thumb_y + thumb.height],
            outline=(100, 100, 120),
            width=1,
        )
        draw.text(
            (thumb_x, thumb_y + thumb.height + 2),
            f"{THUMB_SIZE}px",
            fill=(150, 150, 170),
            font=thumb_font,
        )

        # Label underneath
        label = img_path.stem
        draw.text(
            (x + 4, y + cell_size + 4),
            label,
            fill="white",
            font=label_font,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(output), "PNG")
    logger.info(f"composite: {output} ({grid_w}x{grid_h}, {n} images)")


def _make_board_md(
    image_files: list[Path],
    output: Path,
    title: str = "Design Board",
    round_name: str | None = None,
    notes: str | None = None,
) -> str:
    """Generate a markdown design board section. Returns the markdown text."""
    rel_base = output.parent

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    rname = round_name or f"Round {_detect_round(None, image_files[0].parent if image_files else None)}"
    lines.append(f"## {rname}")
    lines.append("")
    if notes:
        lines.append(f"> {notes}")
        lines.append("")

    # Summary table
    lines.append("| # | Image | Filename | Dimensions |")
    lines.append("|---|-------|----------|------------|")
    for i, img_path in enumerate(image_files, 1):
        try:
            img = Image.open(img_path)
            dims = f"{img.width}x{img.height}"
        except Exception:
            dims = "?"
        rel = os.path.relpath(img_path, rel_base)
        lines.append(f"| {i} | ![{img_path.stem}]({rel}) | `{img_path.name}` | {dims} |")
    lines.append("")

    # Size previews section
    lines.append("### Size Previews")
    lines.append("")
    lines.append("| Image | 72x72 | 128x128 | Full |")
    lines.append("|-------|-------|---------|------|")
    for img_path in image_files:
        rel = os.path.relpath(img_path, rel_base)
        # Markdown doesn't natively support image resizing in GFM,
        # but we use HTML img tags for size control
        lines.append(
            f"| `{img_path.stem}` "
            f'| <img src="{rel}" width="72" height="72"> '
            f'| <img src="{rel}" width="128" height="128"> '
            f'| <img src="{rel}" width="256"> |'
        )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------


@app.command()
def board(
    images: Path = typer.Option(..., help="Directory of images"),
    output: Path = typer.Option("DESIGN_BOARD.md", help="Output markdown path"),
    title: str = typer.Option("Design Board", help="Board title"),
    round: Optional[str] = typer.Option(None, help="Round name"),
    notes: Optional[str] = typer.Option(None, help="Round notes"),
) -> None:
    """Generate design board markdown from image directory."""
    _tm(["start-session", "--project", "create-design-board"])
    image_files = _collect_images(images)
    md = _make_board_md(image_files, output, title=title, round_name=round, notes=notes)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(md)
    logger.info(f"board: {output} ({len(image_files)} images)")
    _tm(["add-accomplishment", "--text", f"Generated board: {output} ({len(image_files)} images)"])
    _tm(["end-session", "--notes", f"Board generated: {len(image_files)} images"])


@app.command()
def append(
    images: Path = typer.Option(..., help="Directory of new images"),
    board: Path = typer.Option(..., help="Existing board markdown"),
    round: Optional[str] = typer.Option(None, help="Round name"),
    notes: Optional[str] = typer.Option(None, help="Round notes"),
) -> None:
    """Append a new round to an existing board markdown."""
    _tm(["start-session", "--project", "create-design-board"])
    if not board.exists():
        logger.error(f"board file '{board}' not found")
        raise typer.Exit(1)

    image_files = _collect_images(images)
    round_num = _detect_round(board, images)
    rname = round or f"Round {round_num}"

    # Build just the round section (no top-level title)
    lines: list[str] = []
    lines.append("")
    lines.append(f"## {rname}")
    lines.append("")
    lines.append(f"*Appended {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")
    if notes:
        lines.append(f"> {notes}")
        lines.append("")

    rel_base = board.parent

    lines.append("| # | Image | Filename | Dimensions |")
    lines.append("|---|-------|----------|------------|")
    for i, img_path in enumerate(image_files, 1):
        try:
            img = Image.open(img_path)
            dims = f"{img.width}x{img.height}"
        except Exception:
            dims = "?"
        rel = os.path.relpath(img_path, rel_base)
        lines.append(f"| {i} | ![{img_path.stem}]({rel}) | `{img_path.name}` | {dims} |")
    lines.append("")

    # Size previews
    lines.append("### Size Previews")
    lines.append("")
    lines.append("| Image | 72x72 | 128x128 | Full |")
    lines.append("|-------|-------|---------|------|")
    for img_path in image_files:
        rel = os.path.relpath(img_path, rel_base)
        lines.append(
            f"| `{img_path.stem}` "
            f'| <img src="{rel}" width="72" height="72"> '
            f'| <img src="{rel}" width="128" height="128"> '
            f'| <img src="{rel}" width="256"> |'
        )
    lines.append("")

    existing = board.read_text()
    board.write_text(existing.rstrip() + "\n" + "\n".join(lines))
    logger.info(f"appended: {rname} to {board} ({len(image_files)} images)")
    _tm(["add-accomplishment", "--text", f"Appended {rname}: {len(image_files)} images"])
    _tm(["end-session", "--notes", f"Appended round to board"])


@app.command()
def composite(
    images: Path = typer.Option(..., help="Directory of images"),
    output: Path = typer.Option("board.png", help="Output PNG path"),
    cols: int = typer.Option(DEFAULT_COLS, help="Grid columns"),
    bg: str = typer.Option(DEFAULT_BG, help="Background color hex"),
    title: Optional[str] = typer.Option(None, help="Board title"),
    cell_size: int = typer.Option(256, help="Cell size in pixels"),
) -> None:
    """Generate composite PNG grid from image directory."""
    _tm(["start-session", "--project", "create-design-board"])
    image_files = _collect_images(images)
    _make_composite(image_files, output, cols=cols, bg=bg, title=title, cell_size=cell_size)
    _tm(["add-accomplishment", "--text", f"Generated composite: {output} ({len(image_files)} images)"])
    _tm(["end-session", "--notes", f"Composite generated"])


@app.command()
def compare(
    images: list[Path] = typer.Option(..., help="Image files to compare"),
    output: Path = typer.Option("comparison.png", help="Output PNG path"),
    labels: Optional[list[str]] = typer.Option(None, help="Labels for each image"),
    bg: str = typer.Option(DEFAULT_BG, help="Background color hex"),
    cell_size: int = typer.Option(300, help="Cell size in pixels"),
) -> None:
    """Side-by-side comparison of specific images."""
    _tm(["start-session", "--project", "create-design-board"])
    for img_path in images:
        if not img_path.exists():
            logger.error(f"'{img_path}' not found")
            raise typer.Exit(1)

    bg_rgb = _hex_to_rgb(bg)
    n = len(images)
    title_band = 50
    grid_w = n * (cell_size + CELL_PADDING) + CELL_PADDING
    grid_h = cell_size + LABEL_HEIGHT + CELL_PADDING * 2 + title_band

    canvas = Image.new("RGB", (grid_w, grid_h), bg_rgb)
    draw = ImageDraw.Draw(canvas)

    title_font = _get_font(20)
    label_font = _get_font(14)

    draw.text((CELL_PADDING, 12), "Comparison", fill="white", font=title_font)

    actual_labels = labels if labels and len(labels) == n else [p.stem for p in images]

    for idx, img_path in enumerate(images):
        x = CELL_PADDING + idx * (cell_size + CELL_PADDING)
        y = title_band

        try:
            img = Image.open(img_path).convert("RGBA")
        except Exception as e:
            logger.warning(f"could not open {img_path}: {e}")
            continue

        img.thumbnail((cell_size, cell_size), Image.Resampling.LANCZOS)
        paste_x = x + (cell_size - img.width) // 2
        paste_y = y + (cell_size - img.height) // 2

        temp = Image.new("RGB", (img.width, img.height), bg_rgb)
        temp.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
        canvas.paste(temp, (paste_x, paste_y))

        # Label
        draw.text(
            (x + 4, y + cell_size + 4),
            actual_labels[idx],
            fill="white",
            font=label_font,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(output), "PNG")
    logger.info(f"compare: {output} ({n} images)")
    _tm(["add-accomplishment", "--text", f"Generated comparison: {output} ({n} images)"])
    _tm(["end-session", "--notes", f"Comparison generated"])


@app.command()
def sizes(
    image: Path = typer.Option(..., help="Source image"),
    output: Path = typer.Option(None, help="Output directory (default: <image>_sizes/)"),
) -> None:
    """Generate size variant previews (72, 128, 256, 512)."""
    _tm(["start-session", "--project", "create-design-board"])
    if not image.exists():
        logger.error(f"'{image}' not found")
        raise typer.Exit(1)

    out_dir = output or image.parent / f"{image.stem}_sizes"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        src = Image.open(image)
    except Exception as e:
        logger.error(f"could not open {image}: {e}")
        raise typer.Exit(1)

    for sz in SIZE_VARIANTS:
        variant = src.copy()
        variant.thumbnail((sz, sz), Image.Resampling.LANCZOS)
        out_path = out_dir / f"{image.stem}_{sz}x{sz}{image.suffix}"
        variant.save(str(out_path))
        logger.info(f"  {sz}x{sz}: {out_path}")

    logger.info(f"sizes: {len(SIZE_VARIANTS)} variants in {out_dir}")
    _tm(["add-accomplishment", "--text", f"Generated {len(SIZE_VARIANTS)} size variants for {image.name}"])
    _tm(["end-session", "--notes", f"Size variants generated"])


# ---------------------------------------------------------------------------
# Persona Assessment
# ---------------------------------------------------------------------------

# Trait-to-design mapping categories learned from Embry Lawson icon design
TRAIT_CATEGORIES = {
    "education": {
        "label": "Education / Training",
        "design_axis": "Structure vs. Expressiveness",
        "examples": {
            "engineering": "Geometric, precise, structured",
            "linguistics": "Language-aware, readable, semantic",
            "art": "Expressive, creative, organic",
            "military": "Clean, utilitarian, no-nonsense",
            "science": "Data-driven, systematic, analytical",
        },
    },
    "personality": {
        "label": "Personality / Temperament",
        "design_axis": "Warmth vs. Authority",
        "examples": {
            "warm": "Rounded corners, soft edges, approachable",
            "formal": "Sharp edges, high contrast, professional",
            "playful": "Bouncy, animated, whimsical",
            "serious": "Muted palette, heavy weight, minimal",
            "curious": "Open forms, exploratory, light",
        },
    },
    "context": {
        "label": "Operating Context / Domain",
        "design_axis": "Consumer vs. Industrial",
        "examples": {
            "defense": "Subdued palette, high legibility, NVIS-compatible",
            "consumer": "Vibrant, trendy, expressive",
            "medical": "Clean, precise, trust-building",
            "industrial": "Utilitarian, high-contrast, durable",
            "academic": "Classic, structured, citation-style",
        },
    },
    "voice": {
        "label": "Communication Style / Register",
        "design_axis": "Casual vs. Institutional",
        "examples": {
            "register-switching": "Must work in both formal and casual — avoid extremes",
            "always-formal": "Serif or structured sans, professional spacing",
            "always-casual": "Rounded, friendly, relaxed spacing",
            "technical": "Monospace-influenced, precise kerning",
            "poetic": "Light, airy, generous whitespace",
        },
    },
}


def _parse_persona_yaml(yaml_path: Path) -> dict:
    """Parse persona YAML and extract design-relevant traits.

    Handles YAML without requiring PyYAML — extracts key/value patterns
    and section headers for trait mapping.
    """
    text = yaml_path.read_text()
    traits: dict = {
        "name": "",
        "age": "",
        "background": [],
        "personality": [],
        "communication": [],
        "interests": [],
        "raw_sections": {},
    }

    current_section = ""
    for line in text.splitlines():
        stripped = line.strip()

        # Top-level keys
        if stripped.startswith("name:"):
            traits["name"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.startswith("age:"):
            traits["age"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")

        # Section headers (YAML keys ending with :)
        if re.match(r"^[a-z_]+:\s*$", stripped):
            current_section = stripped.rstrip(":").strip()
            traits["raw_sections"][current_section] = []
        elif current_section and stripped.startswith("- "):
            val = stripped[2:].strip().strip('"').strip("'")
            traits["raw_sections"].setdefault(current_section, []).append(val)

            # Classify into trait buckets
            lower = val.lower()
            if any(kw in lower for kw in ["degree", "university", "engineer", "school", "studied", "major"]):
                traits["background"].append(val)
            elif any(kw in lower for kw in ["warm", "friend", "empat", "kind", "curious", "imposter", "anxious", "check"]):
                traits["personality"].append(val)
            elif any(kw in lower for kw in ["register", "formal", "casual", "speak", "voice", "tone", "switch"]):
                traits["communication"].append(val)
            elif any(kw in lower for kw in ["hobby", "interest", "love", "enjoy", "watch", "read", "build", "make"]):
                traits["interests"].append(val)

    return traits


def _generate_persona_assessment(traits: dict) -> str:
    """Generate a persona-to-design mapping markdown section."""
    name = traits.get("name", "Unknown Persona")
    age = traits.get("age", "")

    lines: list[str] = []
    lines.append(f"## Persona Assessment: {name}")
    lines.append("")
    if age:
        lines.append(f"**Age**: {age}")
        lines.append("")

    # Background traits
    if traits["background"]:
        lines.append("### Background / Education")
        lines.append("")
        for t in traits["background"][:8]:
            lines.append(f"- {t}")
        lines.append("")

    # Personality traits
    if traits["personality"]:
        lines.append("### Personality Traits (design-relevant)")
        lines.append("")
        for t in traits["personality"][:8]:
            lines.append(f"- {t}")
        lines.append("")

    # Communication style
    if traits["communication"]:
        lines.append("### Communication Style")
        lines.append("")
        for t in traits["communication"][:6]:
            lines.append(f"- {t}")
        lines.append("")

    # Persona-to-Design Mapping table
    lines.append("### Persona-to-Design Mapping")
    lines.append("")
    lines.append("| Persona Trait | Typographic Implication | Eliminates |")
    lines.append("|---------------|------------------------|------------|")

    # Auto-generate mapping rows from extracted traits
    bg_lower = " ".join(t.lower() for t in traits["background"])
    pers_lower = " ".join(t.lower() for t in traits["personality"])
    comm_lower = " ".join(t.lower() for t in traits["communication"])

    if "engineer" in bg_lower or "mechanic" in bg_lower:
        lines.append("| Engineering background | Structured, geometric, precise | Decorative / ornamental fonts |")
    if "linguist" in bg_lower or "language" in bg_lower:
        lines.append("| Language / linguistics | Readable, semantic, language-aware | Purely technical / monospace |")
    if "military" in bg_lower or "base" in bg_lower or "brat" in bg_lower:
        lines.append("| Military context | Utilitarian, nothing fussy | Ornate, heavy, decorative |")
    if "warm" in pers_lower or "empat" in pers_lower or "friend" in pers_lower:
        lines.append("| Warm personality | Rounded corners, soft edges | Sharp/angular/aggressive fonts |")
    if "imposter" in pers_lower or "anxious" in pers_lower:
        lines.append("| Imposter syndrome / modesty | Can't look like trying too hard | Nunito (bubbly), Quicksand (playful) |")
    if "check" in pers_lower or "precise" in pers_lower or "careful" in pers_lower:
        lines.append("| Checks everything twice | Precision, not flash | Trendy or showy fonts |")
    if "register" in comm_lower or "switch" in comm_lower:
        lines.append("| Register-switching voice | Works in formal AND casual | Anything too polished OR too casual |")
    if "python" in bg_lower or "code" in bg_lower or "terminal" in bg_lower:
        lines.append("| Grew up around code | Terminal/monospace influence | Pure serif (too academic) |")

    lines.append("")

    # Design direction recommendations
    lines.append("### Recommended Design Direction")
    lines.append("")
    lines.append("Based on persona assessment:")
    lines.append("")

    if "warm" in pers_lower and ("engineer" in bg_lower or "struct" in bg_lower):
        lines.append("- **Typography**: Geometric sans with rounded corners (Rubik, Plus Jakarta Sans, Lexend)")
        lines.append("- **Why**: Structured (engineer brain) but every edge softened (warmth)")
    elif "warm" in pers_lower:
        lines.append("- **Typography**: Rounded sans-serif (Nunito, Quicksand, Comfortaa)")
        lines.append("- **Why**: Approachable and friendly")
    elif "engineer" in bg_lower:
        lines.append("- **Typography**: Clean geometric sans (Inter, DM Sans, Outfit)")
        lines.append("- **Why**: Precise and systematic")
    else:
        lines.append("- **Typography**: Assess further based on full persona context")

    lines.append("- **Palette**: Derive from persona's domain and emotional tone")
    lines.append("- **Iconography**: Must reflect persona's world, not generic tech")
    lines.append("")

    # Eliminated directions
    lines.append("### Pre-Eliminated Directions (from persona assessment)")
    lines.append("")
    if "warm" in pers_lower:
        lines.append("- Script / calligraphy (too ornate for utilitarian personality)")
    if "engineer" in bg_lower or "military" in bg_lower:
        lines.append("- Decorative / display fonts (too flashy for engineering context)")
    if "imposter" in pers_lower:
        lines.append("- Overly playful / bubbly fonts (trying too hard)")
    if "register" in comm_lower:
        lines.append("- Anything extremely formal OR extremely casual (must work in both registers)")
    lines.append("")

    return "\n".join(lines)


@app.command()
def assess_persona(
    persona: Path = typer.Option(..., help="Path to persona YAML file"),
    output: Optional[Path] = typer.Option(None, help="Append to design board markdown (optional)"),
) -> None:
    """Assess persona YAML for design direction. ALWAYS do this first."""
    _tm(["start-session", "--project", "create-design-board"])
    if not persona.exists():
        logger.error(f"persona file '{persona}' not found")
        raise typer.Exit(1)

    traits = _parse_persona_yaml(persona)
    assessment = _generate_persona_assessment(traits)

    if output:
        if output.exists():
            existing = output.read_text()
            # Insert after the header block, before first round
            if "## Round" in existing:
                parts = existing.split("## Round", 1)
                output.write_text(parts[0].rstrip() + "\n\n" + assessment + "\n---\n\n## Round" + parts[1])
            else:
                output.write_text(existing.rstrip() + "\n\n---\n\n" + assessment)
        else:
            output.write_text(assessment)
        logger.info(f"persona assessment: appended to {output}")
    else:
        typer.echo(assessment)  # stdout output for piping — intentional
    _tm(["add-accomplishment", "--text", f"Assessed persona: {traits.get('name', 'unknown')}"])
    _tm(["end-session", "--notes", f"Persona assessment complete"])


# ---------------------------------------------------------------------------
# Dry-run for sanity check
# ---------------------------------------------------------------------------

@app.command()
def dry_run() -> None:
    """Generate a test composite from synthetic images (no files needed)."""
    import tempfile

    tmpdir = Path(tempfile.mkdtemp(prefix="design-board-"))

    # Create 4 simple test images
    colors = [
        ("red", (200, 50, 50)),
        ("green", (50, 200, 50)),
        ("blue", (50, 50, 200)),
        ("gold", (200, 180, 50)),
    ]
    for name, color in colors:
        img = Image.new("RGB", (128, 128), color)
        img.save(str(tmpdir / f"test_{name}.png"))

    # Generate composite
    out_png = tmpdir / "board.png"
    image_files = _collect_images(tmpdir)
    _make_composite(image_files, out_png, cols=2, title="Dry Run Test")

    # Generate markdown
    out_md = tmpdir / "DESIGN_BOARD.md"
    md = _make_board_md(image_files, out_md, title="Dry Run Test", round_name="Round 1")
    out_md.write_text(md)

    # Validate
    assert out_png.exists(), "composite PNG not created"
    assert out_md.exists(), "board markdown not created"

    img = Image.open(out_png)
    assert img.width > 0 and img.height > 0, "composite has zero dimensions"

    md_text = out_md.read_text()
    assert "# Dry Run Test" in md_text, "missing title in markdown"
    assert "Round 1" in md_text, "missing round in markdown"
    assert "72" in md_text, "missing size preview"
    assert "128" in md_text, "missing size preview"

    # Clean up
    import shutil
    shutil.rmtree(tmpdir)

    logger.info("PASS: dry-run composite + markdown verified")


if __name__ == "__main__":
    app()
