#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pymupdf>=1.23.0",
#     "reportlab>=4.0.0",
#     "typer>=0.9.0",
# ]
# ///
"""
Generate adversarial PDF content that breaks extractors.

Creates false-positive tables, malformed tables, cursed text, and layout traps.
Extensible registry for adding new edge cases from real-world PDFs.

Usage:
    uv run generate.py false-tables --output false_tables.pdf
    uv run generate.py malformed-tables --output malformed.pdf
    uv run generate.py gauntlet --output stress_test.pdf
    uv run generate.py list-tricks
"""

from pathlib import Path
from typing import Optional, Callable
import json

import fitz  # PyMuPDF
import typer
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

app = typer.Typer(help="Generate adversarial PDF content for extractor testing")

# ============================================================================
# TRICK REGISTRY - Add new tricks here as they're discovered
# ============================================================================

FALSE_TABLE_TRICKS = {
    "numbered-list": {
        "description": "Numbered list with aligned numbers (triggers table detection)",
        "content": """1.  First item in the list that has some longer text
2.  Second item that continues the pattern
3.  Third item with similar formatting
4.  Fourth item to establish the pattern
5.  Fifth and final item in this sequence""",
    },
    "address-block": {
        "description": "Multi-line address with aligned fields",
        "content": """John Smith
Director of Engineering
Acme Corporation
123 Main Street, Suite 456
San Francisco, CA 94102
United States""",
    },
    "code-block": {
        "description": "Indented code with column-like alignment",
        "content": """def process_data(input_file, output_file):
    data = load_file(input_file)
    result = transform(data)
    save_file(result, output_file)
    return result""",
    },
    "signature-block": {
        "description": "Email/document signature with name/title/contact",
        "content": """Best regards,

Jane Doe
Senior Vice President
jane.doe@company.com
+1 (555) 123-4567""",
    },
    "key-value-pairs": {
        "description": "Key: Value patterns that look tabular",
        "content": """Document ID:     DOC-2024-00142
Author:          John Smith
Created:         January 15, 2024
Modified:        January 23, 2024
Status:          Under Review
Classification:  Internal Use Only""",
    },
    "toc-entries": {
        "description": "Table of contents with dotted leaders",
        "content": """1. Introduction .......................... 1
2. Background ............................ 5
3. Methodology .......................... 12
4. Results .............................. 28
5. Discussion ........................... 45
6. Conclusions .......................... 52
References .............................. 55""",
    },
    "receipt-text": {
        "description": "Receipt-style aligned text",
        "content": """Coffee, Large          $4.50
Bagel w/ Cream Cheese  $3.25
Orange Juice           $2.75
                      ------
Subtotal               $10.50
Tax (8.5%)             $0.89
                      ------
Total                  $11.39""",
    },
    "form-fields": {
        "description": "Form-like text with underlines",
        "content": """Name: _______________________

Date of Birth: _______________

Address: ____________________

City: _________ State: __ ZIP: _____

Phone: (___) ___-____""",
    },
}

MALFORMED_TABLE_TRICKS = {
    "missing-columns": {
        "description": "Rows with fewer cells than header (Word PDF import bug)",
        "columns": ["ID", "Name", "Department", "Status", "Notes"],
        "rows": [
            ["001", "Alice", "Engineering", "Active", "Team lead"],
            ["002", "Bob", "Marketing"],  # Missing 2 columns
            ["003", "Carol", "Sales", "Active"],  # Missing 1 column
            ["004"],  # Missing 4 columns
            ["005", "Eve", "HR", "Inactive", "On leave"],
        ],
    },
    "ragged-rows": {
        "description": "Completely inconsistent column counts",
        "columns": ["A", "B", "C", "D"],
        "rows": [
            ["1", "2", "3", "4", "5", "6"],  # Too many
            ["1", "2"],  # Too few
            ["1", "2", "3", "4"],  # Just right
            ["1"],  # Way too few
            ["1", "2", "3", "4", "5"],  # One too many
        ],
    },
    "empty-cells-chaos": {
        "description": "Random empty cells breaking structure",
        "columns": ["Col1", "Col2", "Col3", "Col4"],
        "rows": [
            ["", "Data", "", "More"],
            ["", "", "", ""],
            ["Value", "", "Something", ""],
            ["", "", "Only here", ""],
        ],
    },
    "merged-simulation": {
        "description": "Simulated merged cells with repeated values",
        "columns": ["Category", "Item", "Q1", "Q2"],
        "rows": [
            ["Electronics", "Phones", "100", "120"],
            ["", "Tablets", "50", "60"],  # Merged category cell
            ["", "Laptops", "30", "40"],  # Merged category cell
            ["Furniture", "Desks", "20", "25"],
            ["", "Chairs", "40", "45"],  # Merged category cell
        ],
    },
    "numeric-alignment-hell": {
        "description": "Numbers that don't align properly",
        "columns": ["Item", "Quantity", "Price", "Total"],
        "rows": [
            ["Widget A", "5", "$10.00", "$50.00"],
            ["Widget B", "123", "$0.50", "$61.50"],
            ["Gadget", "1", "$1,234.56", "$1,234.56"],
            ["Thing", "10000", "$0.01", "$100.00"],
        ],
    },
    "unicode-in-tables": {
        "description": "Unicode characters breaking table structure",
        "columns": ["Name", "Symbol", "Description"],
        "rows": [
            ["Alpha", "α", "First letter"],
            ["Beta", "β", "Second letter"],
            ["Sigma", "Σ", "Sum notation"],
            ["Infinity", "∞", "Unbounded"],
            ["Arrow", "→", "Direction"],
        ],
    },
}

CURSED_TEXT_TRICKS = {
    "ligatures": {
        "description": "Ligature characters that break text extraction",
        "content": """The officefficials were fi nding it diffi cult to handle the affl uent
fi nancial matters effi ciently. The effl orescence of fi nesse in their
offi cial duties was insufficient for the affl icted circumstances.""",
    },
    "math-notation": {
        "description": "Mathematical symbols and notation",
        "content": """Given f(x) = x² + 2x + 1, find f'(x).

The solution is: f'(x) = 2x + 2

For the integral: ∫₀^∞ e^(-x²) dx = √π/2

And the sum: Σᵢ₌₁ⁿ i = n(n+1)/2""",
    },
    "subscript-superscript": {
        "description": "Chemical formulas and footnote markers",
        "content": """Water (H₂O) reacts with carbon dioxide (CO₂) to form
carbonic acid (H₂CO₃)¹. The reaction proceeds as follows²:

H₂O + CO₂ → H₂CO₃

The equilibrium constant Kₐ = 4.3 × 10⁻⁷ at 25°C³.""",
    },
    "lookalike-chars": {
        "description": "Characters that look identical but aren't (homoglyphs)",
        # Mix of Latin, Cyrillic, and Greek lookalikes
        "content": """Compare these seemingly identical words:
- apple vs аpple (Cyrillic 'а')
- hello vs hеllo (Cyrillic 'е')
- office vs оffice (Cyrillic 'о')
- Example vs Ехample (Cyrillic 'Е' and 'х')""",
    },
    "invisible-chars": {
        "description": "Zero-width and invisible characters",
        "content": """This sentence has a zero\u200bwidth space in it.
This one has a soft\u00adhyphen that may or may not show.
And this has a word\u2060joiner between words.
Finally, a non\u00a0breaking space here.""",
    },
    "mixed-numbers": {
        "description": "Different number representations",
        "content": """Numbers in various forms:
- Arabic: 0 1 2 3 4 5 6 7 8 9
- Roman: I II III IV V VI VII VIII IX X
- Superscript: ⁰ ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹
- Circled: ① ② ③ ④ ⑤ ⑥ ⑦ ⑧ ⑨ ⑩""",
    },
}

LAYOUT_TRAP_TRICKS = {
    "deep-nesting": {
        "description": "Deeply nested section hierarchy (10+ levels)",
        "sections": [
            ("1. Introduction", 1),
            ("1.1 Background", 2),
            ("1.1.1 Historical Context", 3),
            ("1.1.1.1 Early Development", 4),
            ("1.1.1.1.1 Initial Research", 5),
            ("1.1.1.1.1.1 First Experiments", 6),
            ("1.1.1.1.1.1.1 Preliminary Results", 7),
            ("1.1.1.1.1.1.1.1 Data Analysis", 8),
            ("1.1.1.1.1.1.1.1.1 Statistical Methods", 9),
            ("1.1.1.1.1.1.1.1.1.1 Regression Analysis", 10),
        ],
    },
    "footnote-sections": {
        "description": "Footnotes that look like new sections",
        "content": """Main content paragraph discussing important topics.

¹ This is a footnote that spans multiple lines and looks very much
like it could be a new section with its own content that continues
for quite a while.

² Another footnote that might confuse section detection because it
starts with a number and has substantial content below it.

1. Actual Section One

This is the real content of section one.""",
    },
    "sidebar-content": {
        "description": "Marginal notes alongside main text",
        "main_text": "This is the primary content that flows down the page in the main column area.",
        "sidebar_text": "SIDEBAR: Additional context that appears in the margin.",
    },
    "out-of-order": {
        "description": "Content in non-reading order (like some PDFs)",
        "blocks": [
            {"text": "Third paragraph", "order": 3},
            {"text": "First paragraph", "order": 1},
            {"text": "Second paragraph", "order": 2},
        ],
    },
}


# ============================================================================
# GENERATORS
# ============================================================================

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

    doc.save(str(output))
    doc.close()
    typer.echo(f"Created: {output} (layout-trap tricks)")


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

    # Merge all
    result = fitz.open()
    for pdf_path in temp_files:
        src = fitz.open(str(pdf_path))
        result.insert_pdf(src)
        src.close()
        pdf_path.unlink()

    result.save(str(output))
    result.close()

    typer.echo(f"Created gauntlet: {output} (all trick categories)")


# ============================================================================
# CLI COMMANDS
# ============================================================================

@app.command("false-tables")
def cmd_false_tables(
    output: Path = typer.Option(Path("false_tables.pdf"), "--output", "-o"),
    tricks: Optional[str] = typer.Option(None, "--tricks", "-t", help="Comma-separated trick names"),
):
    """Generate PDF with false-positive table content."""
    output.parent.mkdir(parents=True, exist_ok=True)
    trick_list = tricks.split(",") if tricks else None
    generate_false_tables_pdf(output, trick_list)


@app.command("malformed-tables")
def cmd_malformed_tables(
    output: Path = typer.Option(Path("malformed_tables.pdf"), "--output", "-o"),
    tricks: Optional[str] = typer.Option(None, "--tricks", "-t", help="Comma-separated trick names"),
):
    """Generate PDF with malformed/corrupted tables."""
    output.parent.mkdir(parents=True, exist_ok=True)
    trick_list = tricks.split(",") if tricks else None
    generate_malformed_tables_pdf(output, trick_list)


@app.command("cursed-text")
def cmd_cursed_text(
    output: Path = typer.Option(Path("cursed_text.pdf"), "--output", "-o"),
    tricks: Optional[str] = typer.Option(None, "--tricks", "-t", help="Comma-separated trick names"),
):
    """Generate PDF with text extraction nightmares."""
    output.parent.mkdir(parents=True, exist_ok=True)
    trick_list = tricks.split(",") if tricks else None
    generate_cursed_text_pdf(output, trick_list)


@app.command("layout-traps")
def cmd_layout_traps(
    output: Path = typer.Option(Path("layout_traps.pdf"), "--output", "-o"),
    tricks: Optional[str] = typer.Option(None, "--tricks", "-t", help="Comma-separated trick names"),
):
    """Generate PDF with layout patterns that confuse extractors."""
    output.parent.mkdir(parents=True, exist_ok=True)
    trick_list = tricks.split(",") if tricks else None
    generate_layout_traps_pdf(output, trick_list)


@app.command("gauntlet")
def cmd_gauntlet(
    output: Path = typer.Option(Path("gauntlet.pdf"), "--output", "-o"),
):
    """Generate comprehensive stress test with ALL tricks."""
    output.parent.mkdir(parents=True, exist_ok=True)
    generate_gauntlet_pdf(output)


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
    if trick in FALSE_TABLE_TRICKS:
        generate_false_tables_pdf(output, [trick])
    elif trick in MALFORMED_TABLE_TRICKS:
        generate_malformed_tables_pdf(output, [trick])
    elif trick in CURSED_TEXT_TRICKS:
        generate_cursed_text_pdf(output, [trick])
    elif trick in LAYOUT_TRAP_TRICKS:
        generate_layout_traps_pdf(output, [trick])
    else:
        typer.echo(f"Unknown trick: {trick}")
        typer.echo("Use 'list-tricks' to see available tricks")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
