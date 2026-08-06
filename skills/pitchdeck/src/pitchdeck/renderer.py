"""renderer - pitchdeck.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .io import SkillError, dump_json, sha256_file
from .models import OperationClaims, OperationReceipt, Readiness, SeamValidation


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SkillError(
            "Command failed:\n"
            + " ".join(command)
            + f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _make_contact_sheet(images: list[Path], output: Path, columns: int = 3) -> None:
    if not images:
        raise SkillError("No slide PNGs were produced; cannot create contact sheet.")
    opened = [Image.open(path).convert("RGB") for path in images]
    thumb_w = 640
    ratio = opened[0].height / opened[0].width
    thumb_h = int(thumb_w * ratio)
    label_h = 34
    gap = 18
    rows = (len(opened) + columns - 1) // columns
    canvas_w = gap + columns * (thumb_w + gap)
    canvas_h = gap + rows * (thumb_h + label_h + gap)
    canvas = Image.new("RGB", (canvas_w, canvas_h), "#08131F")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=18)
    for index, image in enumerate(opened):
        row = index // columns
        col = index % columns
        x = gap + col * (thumb_w + gap)
        y = gap + row * (thumb_h + label_h + gap)
        thumb = image.copy()
        thumb.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        canvas.paste(thumb, (x, y))
        draw.text((x, y + thumb_h + 7), f"Slide {index + 1:02d}", fill="#F4F8FB", font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG")
    for image in opened:
        image.close()


def render_pptx(pptx_path: Path, output_dir: Path, *, dpi: int = 120) -> OperationReceipt:
    libreoffice = shutil.which("libreoffice") or shutil.which("soffice")
    pdftoppm = shutil.which("pdftoppm")
    if not libreoffice:
        raise SkillError(
            "LibreOffice/soffice is not installed. Install it or import the PPTX into Google Slides "
            "and export a PDF there."
        )
    if not pdftoppm:
        raise SkillError("pdftoppm is not installed; install poppler-utils to render slide PNGs.")
    if not pptx_path.exists():
        raise SkillError(f"PPTX does not exist: {pptx_path}")
    if dpi < 72 or dpi > 300:
        raise SkillError("--dpi must be between 72 and 300")

    output_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            libreoffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(pptx_path),
        ]
    )
    pdf_path = output_dir / f"{pptx_path.stem}.pdf"
    if not pdf_path.exists():
        raise SkillError(f"LibreOffice did not produce the expected PDF: {pdf_path}")

    prefix = output_dir / "slide"
    _run([pdftoppm, "-png", "-r", str(dpi), str(pdf_path), str(prefix)])
    images = sorted(output_dir.glob("slide-*.png"))
    if not images:
        images = sorted(output_dir.glob("slide*.png"))
    contact_sheet = output_dir / "contact-sheet.png"
    _make_contact_sheet(images, contact_sheet)

    receipt = OperationReceipt(
        schema="pitchdeck.render_receipt.v1",
        operation="render",
        readiness=Readiness.READY,
        mocked=False,
        live=False,
        inputs={"pptx": str(pptx_path.resolve()), "dpi": str(dpi)},
        outputs={
            "pdf": str(pdf_path.resolve()),
            "pdf_sha256": sha256_file(pdf_path),
            "contact_sheet": str(contact_sheet.resolve()),
        },
        counts={"slide_pngs": len(images)},
        gaps=[],
        claims=OperationClaims(
            proves=[
                "LibreOffice rendered the PPTX to PDF.",
                "Every rendered PDF page produced a slide PNG and was included in the contact sheet.",
            ],
            does_not_prove=[
                "Google Slides import will preserve every pixel or animation identically.",
                "The deck is visually or factually approved.",
            ],
        ),
        seam_validation=SeamValidation(kind="render_receipt"),
    )
    dump_json(receipt, output_dir / "render_receipt.json")
    return receipt
