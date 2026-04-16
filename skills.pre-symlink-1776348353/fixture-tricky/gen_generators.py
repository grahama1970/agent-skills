"""
PDF generator functions for each trick category.

Each function creates a PyMuPDF document exercising specific
adversarial patterns for extractor testing.
"""
from pathlib import Path
from typing import Optional

import fitz
import typer
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

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


def generate_false_tables_pdf(output: Path, tricks: Optional[list[str]] = None):
    """Generate PDF with false-positive table content."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 50

    page.insert_text((50, y), "False-Positive Table Test Patterns", fontsize=18, fontname="helv")
    y += 40

    tricks_to_use = tricks or list(FALSE_TABLE_TRICKS.keys())

    for trick_name in tricks_to_use:
        if trick_name not in FALSE_TABLE_TRICKS:
            continue

        trick = FALSE_TABLE_TRICKS[trick_name]

        if y > 650:
            page = doc.new_page(width=612, height=792)
            y = 50

        # Section header
        page.insert_text((50, y), f"[{trick_name}]", fontsize=12, fontname="helv", color=(0.3, 0.3, 0.7))
        y += 15
        page.insert_text((50, y), trick["description"], fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        # Content
        rect = fitz.Rect(50, y, 562, y + 150)
        rc = page.insert_textbox(rect, trick["content"], fontsize=10, fontname="cour")
        y += abs(rc) + 30

    doc.save(str(output))
    doc.close()
    typer.echo(f"Created: {output} ({len(tricks_to_use)} false-table tricks)")


def generate_malformed_tables_pdf(output: Path, tricks: Optional[list[str]] = None):
    """Generate PDF with malformed/corrupted tables."""
    doc = SimpleDocTemplate(
        str(output),
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch,
    )

    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Malformed Table Test Patterns", styles["Title"]))
    elements.append(Spacer(1, 0.3*inch))

    tricks_to_use = tricks or list(MALFORMED_TABLE_TRICKS.keys())

    for trick_name in tricks_to_use:
        if trick_name not in MALFORMED_TABLE_TRICKS:
            continue

        trick = MALFORMED_TABLE_TRICKS[trick_name]

        elements.append(Paragraph(f"[{trick_name}]", styles["Heading2"]))
        elements.append(Paragraph(trick["description"], styles["Italic"]))
        elements.append(Spacer(1, 0.1*inch))

        columns = trick["columns"]
        rows = trick["rows"]

        # Normalize rows to have correct column count (pad with empty strings)
        normalized_rows = []
        for row in rows:
            if len(row) < len(columns):
                normalized_rows.append(row + [""] * (len(columns) - len(row)))
            elif len(row) > len(columns):
                normalized_rows.append(row[:len(columns)])  # Truncate
            else:
                normalized_rows.append(row)

        table_data = [columns] + normalized_rows

        # Create table with visible issues
        col_width = (letter[0] - 1*inch) / len(columns)
        table = Table(table_data, colWidths=[col_width] * len(columns))

        # Check if borderless table
        is_borderless = trick.get("borderless", False)

        if is_borderless:
            # NASA-style borderless table - only horizontal lines
            table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LINEABOVE", (0, 0), (-1, 0), 1, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ]))
        else:
            table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))

        elements.append(table)
        elements.append(Spacer(1, 0.3*inch))

    doc.build(elements)
    typer.echo(f"Created: {output} ({len(tricks_to_use)} malformed-table tricks)")


def generate_cursed_text_pdf(output: Path, tricks: Optional[list[str]] = None):
    """Generate PDF with text extraction nightmares."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 50

    page.insert_text((50, y), "Cursed Text Test Patterns", fontsize=18, fontname="helv")
    y += 40

    tricks_to_use = tricks or list(CURSED_TEXT_TRICKS.keys())

    for trick_name in tricks_to_use:
        if trick_name not in CURSED_TEXT_TRICKS:
            continue

        trick = CURSED_TEXT_TRICKS[trick_name]

        if y > 600:
            page = doc.new_page(width=612, height=792)
            y = 50

        # Section header
        page.insert_text((50, y), f"[{trick_name}]", fontsize=12, fontname="helv", color=(0.7, 0.3, 0.3))
        y += 15
        page.insert_text((50, y), trick["description"], fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        # Content
        rect = fitz.Rect(50, y, 562, y + 150)
        rc = page.insert_textbox(rect, trick["content"], fontsize=10)
        y += abs(rc) + 30

    doc.save(str(output))
    doc.close()
    typer.echo(f"Created: {output} ({len(tricks_to_use)} cursed-text tricks)")


def generate_layout_traps_pdf(output: Path, tricks: Optional[list[str]] = None):
    """Generate PDF with layout patterns that confuse extractors."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 50

    page.insert_text((50, y), "Layout Trap Test Patterns", fontsize=18, fontname="helv")
    y += 40

    # Deep nesting
    if not tricks or "deep-nesting" in tricks:
        page.insert_text((50, y), "[deep-nesting]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "Deeply nested section hierarchy", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        for title, level in LAYOUT_TRAP_TRICKS["deep-nesting"]["sections"]:
            indent = 20 + (level - 1) * 15
            fontsize = max(8, 14 - level)
            page.insert_text((indent, y), title, fontsize=fontsize, fontname="helv")
            y += fontsize + 5

        y += 20

    # Footnote sections
    if not tricks or "footnote-sections" in tricks:
        if y > 500:
            page = doc.new_page(width=612, height=792)
            y = 50

        page.insert_text((50, y), "[footnote-sections]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "Footnotes that look like sections", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        rect = fitz.Rect(50, y, 562, y + 200)
        rc = page.insert_textbox(rect, LAYOUT_TRAP_TRICKS["footnote-sections"]["content"], fontsize=10)
        y += abs(rc) + 30

    # Page number sections (new 2026-01-23)
    if not tricks or "page-number-sections" in tricks:
        if y > 500:
            page = doc.new_page(width=612, height=792)
            y = 50

        page.insert_text((50, y), "[page-number-sections]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "Standalone numbers mistaken for section headers", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        rect = fitz.Rect(50, y, 562, y + 200)
        rc = page.insert_textbox(rect, LAYOUT_TRAP_TRICKS["page-number-sections"]["content"], fontsize=10)
        y += abs(rc) + 30

    # Partial header (new 2026-01-23)
    if not tricks or "partial-header" in tricks:
        if y > 500:
            page = doc.new_page(width=612, height=792)
            y = 50

        page.insert_text((50, y), "[partial-header]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "Incomplete headers truncated during extraction", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        rect = fitz.Rect(50, y, 562, y + 200)
        rc = page.insert_textbox(rect, LAYOUT_TRAP_TRICKS["partial-header"]["content"], fontsize=10)
        y += abs(rc) + 30

    # Sentence as header (new 2026-01-23)
    if not tricks or "sentence-as-header" in tricks:
        if y > 500:
            page = doc.new_page(width=612, height=792)
            y = 50

        page.insert_text((50, y), "[sentence-as-header]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "Partial sentences detected as section headers", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        rect = fitz.Rect(50, y, 562, y + 200)
        rc = page.insert_textbox(rect, LAYOUT_TRAP_TRICKS["sentence-as-header"]["content"], fontsize=10)
        y += abs(rc) + 30

    # TOC leaders captured (new 2026-02-04)
    if not tricks or "toc-leaders-captured" in tricks:
        if y > 500:
            page = doc.new_page(width=612, height=792)
            y = 50

        page.insert_text((50, y), "[toc-leaders-captured]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "TOC dotted leaders captured in section headers", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        rect = fitz.Rect(50, y, 562, y + 300)
        rc = page.insert_textbox(rect, LAYOUT_TRAP_TRICKS["toc-leaders-captured"]["content"], fontsize=10, fontname="cour")
        y += abs(rc) + 30

    # Requirements doc (new 2026-02-04)
    if not tricks or "requirements-doc" in tricks:
        if y > 500:
            page = doc.new_page(width=612, height=792)
            y = 50

        page.insert_text((50, y), "[requirements-doc]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "Engineering doc with SHALL/MUST requirements", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        rect = fitz.Rect(50, y, 562, y + 350)
        rc = page.insert_textbox(rect, LAYOUT_TRAP_TRICKS["requirements-doc"]["content"], fontsize=10)
        y += abs(rc) + 30

    # Section merge cascade (new 2026-02-04)
    if not tricks or "section-merge-cascade" in tricks:
        if y > 500:
            page = doc.new_page(width=612, height=792)
            y = 50

        page.insert_text((50, y), "[section-merge-cascade]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "Short sections that cascade-merge when content measured wrong", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        rect = fitz.Rect(50, y, 562, y + 350)
        rc = page.insert_textbox(rect, LAYOUT_TRAP_TRICKS["section-merge-cascade"]["content"], fontsize=10)
        y += abs(rc) + 30

    # Code-heavy font skew (new 2026-02-04)
    if not tricks or "code-heavy-font-skew" in tricks:
        # This trick uses DIFFERENT font sizes to simulate the real problem:
        # body at 10pt, code at 7pt, headings at 14pt
        page = doc.new_page(width=612, height=792)
        y = 50

        page.insert_text((50, y), "[code-heavy-font-skew]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "7pt code listings dominating font distribution", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 25

        # Heading at 14pt
        page.insert_text((50, y), "1. Introduction", fontsize=14, fontname="helv")
        y += 20
        page.insert_text((50, y), "This document contains extensive code examples.", fontsize=10, fontname="helv")
        y += 15

        # Code block at 7pt (many lines to dominate median)
        code_lines = [
            "    def process_data(input: str) -> dict:",
            "        result = {}",
            "        for line in input.split('\\n'):",
            "            key, val = line.split('=')",
            "            result[key.strip()] = val.strip()",
            "        return result",
            "",
            "    class DataProcessor:",
            "        def __init__(self, config):",
            "            self.config = config",
            "            self.cache = {}",
            "        def run(self, data):",
            "            processed = self.process_data(data)",
            "            self.cache.update(processed)",
            "            return processed",
        ]
        for code_line in code_lines:
            page.insert_text((70, y), code_line, fontsize=7, fontname="cour")
            y += 9

        y += 10
        page.insert_text((50, y), "2. Architecture", fontsize=14, fontname="helv")
        y += 20
        page.insert_text((50, y), "The system follows a pipeline pattern.", fontsize=10, fontname="helv")
        y += 30

    # Front-matter heavy (new 2026-02-04)
    if not tricks or "front-matter-heavy" in tricks:
        page = doc.new_page(width=612, height=792)
        y = 50

        page.insert_text((50, y), "[front-matter-heavy]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "Extensive front matter before real content", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 25

        rect = fitz.Rect(50, y, 562, y + 500)
        rc = page.insert_textbox(rect, LAYOUT_TRAP_TRICKS["front-matter-heavy"]["content"], fontsize=10)
        y += abs(rc) + 30

    # Boundary heading sizes (new 2026-02-04)
    if not tricks or "boundary-heading-sizes" in tricks:
        # Use actual different font sizes: body=10pt, headings=12pt (exactly 1.2x)
        page = doc.new_page(width=612, height=792)
        y = 50

        page.insert_text((50, y), "[boundary-heading-sizes]", fontsize=12, fontname="helv", color=(0.3, 0.7, 0.3))
        y += 15
        page.insert_text((50, y), "Headings at exactly 1.2x body font (12pt vs 10pt)", fontsize=9, color=(0.5, 0.5, 0.5))
        y += 25

        sections = [
            ("1. Overview", "This section provides a high-level description of the system."),
            ("2. Background", "Previous work established the baseline performance metrics."),
            ("3. Methodology", "The approach uses a three-phase pipeline for extraction."),
            ("4. Results", "Measurements show significant improvement in detection accuracy."),
            ("5. Discussion", "The combined approach addresses fundamental limitations."),
        ]
        for heading, body in sections:
            page.insert_text((50, y), heading, fontsize=12, fontname="helv")  # exactly 1.2x body
            y += 18
            page.insert_text((70, y), body, fontsize=10, fontname="helv")  # body text
            y += 15
            page.insert_text((70, y), "Additional detail text for this section to establish body font.", fontsize=10, fontname="helv")
            y += 25

    doc.save(str(output))
    doc.close()
    typer.echo(f"Created: {output} (layout-trap tricks)")


def generate_requirements_pdf(output: Path, tricks: Optional[list[str]] = None):
    """Generate PDF with requirements extraction test patterns."""
    doc = SimpleDocTemplate(
        str(output),
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch,
    )

    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Requirements Extraction Test Patterns", styles["Title"]))
    elements.append(Paragraph("Adversarial fixtures for S08 requirements extraction", styles["Italic"]))
    elements.append(Spacer(1, 0.3*inch))

    tricks_to_use = tricks or list(REQUIREMENTS_TRICKS.keys())

    for trick_name in tricks_to_use:
        if trick_name not in REQUIREMENTS_TRICKS:
            continue

        trick = REQUIREMENTS_TRICKS[trick_name]

        elements.append(Paragraph(f"[{trick_name}]", styles["Heading2"]))
        elements.append(Paragraph(trick["description"], styles["Italic"]))
        elements.append(Spacer(1, 0.1*inch))

        # Handle table-type tricks
        if trick.get("type") == "table":
            columns = trick["columns"]
            rows = trick["rows"]
            table_data = [columns] + rows

            col_width = (letter[0] - 1*inch) / len(columns)
            table = Table(table_data, colWidths=[col_width] * len(columns))
            table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            elements.append(table)
        else:
            # Text content
            for line in trick["content"].strip().split("\n"):
                if line.strip():
                    elements.append(Paragraph(line, styles["Normal"]))
                else:
                    elements.append(Spacer(1, 0.1*inch))

        elements.append(Spacer(1, 0.3*inch))

    doc.build(elements)
    typer.echo(f"Created: {output} ({len(tricks_to_use)} requirements tricks)")


def generate_math_noise_pdf(output: Path, tricks: Optional[list[str]] = None):
    """Generate PDF with math noise test patterns."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 50

    page.insert_text((50, y), "Math Noise Test Patterns", fontsize=18, fontname="helv")
    y += 40

    tricks_to_use = tricks or list(MATH_NOISE_TRICKS.keys())

    for trick_name in tricks_to_use:
        if trick_name not in MATH_NOISE_TRICKS:
            continue

        trick = MATH_NOISE_TRICKS[trick_name]

        if y > 650:
            page = doc.new_page(width=612, height=792)
            y = 50

        # Section header
        page.insert_text((50, y), f"[{trick_name}]", fontsize=12, fontname="helv", color=(0.3, 0.3, 0.7))
        y += 15
        page.insert_text((50, y), trick["description"], fontsize=9, color=(0.5, 0.5, 0.5))
        y += 20

        # Content - use centered alignment for certain tricks
        align = 1 if "centered" in trick_name else 0 
        
        rect = fitz.Rect(50, y, 562, y + 150)
        rc = page.insert_textbox(rect, trick["content"], fontsize=10, fontname="cour", align=align)
        y += abs(rc) + 30

    doc.save(str(output))
    doc.close()
    typer.echo(f"Created: {output} ({len(tricks_to_use)} math-noise tricks)")


def generate_gauntlet_pdf(output: Path):
    """Generate comprehensive stress test with all tricks."""
    import tempfile

    temp_files = []

    # Generate each category
    false_tables = Path(tempfile.mktemp(suffix=".pdf"))
    generate_false_tables_pdf(false_tables)
    temp_files.append(false_tables)

    malformed = Path(tempfile.mktemp(suffix=".pdf"))
    generate_malformed_tables_pdf(malformed)
    temp_files.append(malformed)

    cursed = Path(tempfile.mktemp(suffix=".pdf"))
    generate_cursed_text_pdf(cursed)
    temp_files.append(cursed)

    layout = Path(tempfile.mktemp(suffix=".pdf"))
    generate_layout_traps_pdf(layout)
    temp_files.append(layout)

    # Add requirements (new category)
    requirements = Path(tempfile.mktemp(suffix=".pdf"))
    generate_requirements_pdf(requirements)
    temp_files.append(requirements)

    # Add math noise (new category)
    math_noise = Path(tempfile.mktemp(suffix=".pdf"))
    generate_math_noise_pdf(math_noise)
    temp_files.append(math_noise)

    # Merge all
    result = fitz.open()
    for pdf_path in temp_files:
        src = fitz.open(str(pdf_path))
        result.insert_pdf(src)
        src.close()
        pdf_path.unlink()

    result.save(str(output))
    result.close()

    typer.echo(f"Created gauntlet: {output} (all trick categories including requirements)")



