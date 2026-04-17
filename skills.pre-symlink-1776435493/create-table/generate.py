#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "reportlab>=4.0.0",
#     "typer>=0.9.0",
#     "pymupdf>=1.23.0",
# ]
# ///
"""
Generate PDF tables using ReportLab Table class.

Creates proper PDF table structures that Marker and other extractors can detect,
unlike raw PDF drawing commands which only create visual representations.

Usage:
    uv run generate.py generate --output test.pdf
    uv run generate.py generate --columns "ID,Name" --rows '[["1","Alice"],["2","Bob"]]'
    uv run generate.py generate --spec table_spec.json
    uv run generate.py generate --no-border  # borderless table
    uv run generate.py generate --line-width 2  # thick borders
"""

import json
import tempfile
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import typer
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

app = typer.Typer(help="Generate PDF tables with ReportLab for extraction testing")


def render_pdf_to_image(pdf_path: Path, output_path: Path, dpi: int = 150) -> None:
    """Render a PDF page to a PNG image (for scanned document simulation)."""
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    # Scale for desired DPI (72 is default PDF DPI)
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    pix.save(str(output_path))
    doc.close()
    print(f"Rendered: {output_path} ({pix.width}x{pix.height} @ {dpi}dpi)")


def get_table_style(style_name: str, border: bool = True, line_width: float = 1.0) -> TableStyle:
    """Return a TableStyle based on style name, with optional border control."""
    base_styles = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]

    if style_name == "plain":
        style_specific = []
    elif style_name == "colored":
        style_specific = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#D6DCE5")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#E9EDF4")]),
        ]
    else:  # grid (default)
        style_specific = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
        ]

    # Add border if requested
    border_styles = []
    if border:
        border_styles = [("GRID", (0, 0), (-1, -1), line_width, colors.black)]

    return TableStyle(base_styles + style_specific + border_styles)


def create_table_pdf(
    output_path: Path,
    columns: list[str],
    rows: list[list],
    title: Optional[str] = None,
    style: str = "grid",
    border: bool = True,
    line_width: float = 1.0,
    header_rows: Optional[list[list]] = None,
) -> None:
    """Create a PDF with a proper ReportLab table.

    Args:
        header_rows: Optional multi-index headers. Each row is a list where items can be:
            - string: normal cell
            - dict with "text" and "span": cell spanning multiple columns
              e.g. {"text": "Group A", "span": 2} spans 2 columns
    """
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    elements = []
    styles = getSampleStyleSheet()

    # Add title if provided
    if title:
        elements.append(Paragraph(title, styles["Heading1"]))
        elements.append(Spacer(1, 0.25 * inch))

    # Build table data
    if header_rows:
        # Multi-index: expand header rows then add column headers and data
        table_data = []
        span_commands = []

        for row_idx, header_row in enumerate(header_rows):
            expanded_row = []
            col_idx = 0
            for item in header_row:
                if isinstance(item, dict):
                    text = item.get("text", "")
                    span = item.get("span", 1)
                    expanded_row.append(text)
                    # Add empty cells for spanned columns
                    for _ in range(span - 1):
                        expanded_row.append("")
                    # Record span command
                    if span > 1:
                        span_commands.append(
                            ("SPAN", (col_idx, row_idx), (col_idx + span - 1, row_idx))
                        )
                    col_idx += span
                else:
                    expanded_row.append(item)
                    col_idx += 1
            table_data.append(expanded_row)

        # Add the regular column headers
        table_data.append(columns)
        num_header_rows = len(header_rows) + 1

        # Add data rows
        table_data.extend(rows)
    else:
        # Simple single header row
        table_data = [columns] + rows
        span_commands = []
        num_header_rows = 1

    # Calculate column widths (distribute evenly)
    num_cols = len(columns)
    available_width = letter[0] - 1 * inch  # page width minus margins
    col_width = available_width / num_cols
    col_widths = [col_width] * num_cols

    # Create table with proper structure
    table = Table(table_data, colWidths=col_widths)

    # Get base style and add span commands
    table_style = get_table_style(style, border=border, line_width=line_width)

    # Apply header styling to all header rows
    if num_header_rows > 1:
        table_style.add("FONTNAME", (0, 0), (-1, num_header_rows - 1), "Helvetica-Bold")
        table_style.add("BACKGROUND", (0, 0), (-1, num_header_rows - 1), colors.HexColor("#D9E2F3"))
        table_style.add("ALIGN", (0, 0), (-1, num_header_rows - 1), "CENTER")

    # Apply span commands
    for cmd in span_commands:
        table_style.add(*cmd)

    table.setStyle(table_style)
    elements.append(table)

    # Build PDF
    doc.build(elements)
    print(f"Created: {output_path}")


@app.command()
def generate(
    output: Path = typer.Option(
        Path("table_fixture.pdf"), "--output", "-o", help="Output PDF or PNG path"
    ),
    columns: Optional[str] = typer.Option(
        None, "--columns", "-c", help="Comma-separated column headers"
    ),
    rows: Optional[str] = typer.Option(
        None, "--rows", "-r", help="JSON array of row data"
    ),
    spec: Optional[Path] = typer.Option(
        None, "--spec", "-s", help="JSON spec file path"
    ),
    title: Optional[str] = typer.Option(
        None, "--title", "-t", help="Table title text"
    ),
    style: str = typer.Option(
        "grid", "--style", help="Table style: grid, plain, colored"
    ),
    border: bool = typer.Option(
        True, "--border/--no-border", help="Enable or disable table borders"
    ),
    line_width: float = typer.Option(
        1.0, "--line-width", "-w", help="Border line thickness in points"
    ),
    multi_index: Optional[str] = typer.Option(
        None, "--multi-index", "-m", help="JSON array of header rows for multi-index"
    ),
    as_image: bool = typer.Option(
        False, "--as-image", "-i", help="Render table as PNG image (for scanned doc testing)"
    ),
    dpi: int = typer.Option(
        150, "--dpi", help="DPI for image rendering (default 150)"
    ),
) -> None:
    """Generate a PDF with a properly structured table."""
    header_rows = None

    # Load from spec file if provided
    if spec and spec.exists():
        spec_data = json.loads(spec.read_text())
        col_list = spec_data.get("columns", ["Col1", "Col2", "Col3"])
        row_list = spec_data.get("rows", [])
        title = spec_data.get("title", title)
        style = spec_data.get("style", style)
        border = spec_data.get("border", border)
        line_width = spec_data.get("line_width", line_width)
        header_rows = spec_data.get("multi_index")
    else:
        # Parse columns
        if columns:
            col_list = [c.strip() for c in columns.split(",")]
        else:
            col_list = ["ID", "Name", "Value"]

        # Parse rows
        if rows:
            try:
                row_list = json.loads(rows)
            except json.JSONDecodeError as e:
                raise typer.BadParameter(f"Invalid JSON for --rows: {e}")
        else:
            # Default sample data
            row_list = [
                ["1", "Alpha", "100"],
                ["2", "Beta", "200"],
                ["3", "Gamma", "300"],
            ]

        # Parse multi-index headers
        if multi_index:
            try:
                header_rows = json.loads(multi_index)
            except json.JSONDecodeError as e:
                raise typer.BadParameter(f"Invalid JSON for --multi-index: {e}")

    # Ensure output directory exists
    output.parent.mkdir(parents=True, exist_ok=True)

    if as_image:
        # Generate PDF to temp file, then render to image
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_pdf = Path(tmp.name)

        create_table_pdf(
            tmp_pdf, col_list, row_list, title, style,
            border=border, line_width=line_width, header_rows=header_rows
        )

        # Ensure output has .png extension
        img_output = output.with_suffix(".png") if output.suffix.lower() != ".png" else output
        render_pdf_to_image(tmp_pdf, img_output, dpi=dpi)
        tmp_pdf.unlink()  # Clean up temp PDF
    else:
        create_table_pdf(
            output, col_list, row_list, title, style,
            border=border, line_width=line_width, header_rows=header_rows
        )


# Preset table definitions
PRESETS = {
    "simple": {
        "columns": ["ID", "Name", "Value"],
        "rows": [
            ["1", "Alpha", "100"],
            ["2", "Beta", "200"],
            ["3", "Gamma", "300"],
        ],
        "title": "Simple Table",
    },
    "medium": {
        "columns": ["ID", "Requirement", "Category", "Priority", "Status", "Owner"],
        "rows": [
            ["REQ-001", "System response time < 1s", "Performance", "High", "Verified", "Alice"],
            ["REQ-002", "Support 1000 concurrent users", "Scalability", "High", "Pending", "Bob"],
            ["REQ-003", "99.9% uptime SLA", "Reliability", "Critical", "In Review", "Carol"],
            ["REQ-004", "Data encrypted at rest", "Security", "Critical", "Verified", "Dave"],
            ["REQ-005", "GDPR compliance", "Compliance", "High", "Pending", "Eve"],
            ["REQ-006", "Mobile responsive UI", "Usability", "Medium", "Verified", "Frank"],
            ["REQ-007", "API rate limiting", "Security", "Medium", "In Progress", "Grace"],
            ["REQ-008", "Audit logging", "Compliance", "High", "Verified", "Henry"],
        ],
        "title": "Requirements Matrix",
    },
    "complex": {
        "columns": ["ID", "Q1", "Q2", "Q3", "Q4", "Total"],
        "rows": [
            ["Product A", "150", "180", "200", "220", "750"],
            ["Product B", "90", "110", "130", "140", "470"],
            ["Product C", "200", "190", "210", "230", "830"],
            ["Product D", "75", "85", "95", "100", "355"],
            ["Total", "515", "565", "635", "690", "2405"],
        ],
        "multi_index": [
            [{"text": "", "span": 1}, {"text": "2024 Sales (units)", "span": 4}, {"text": "", "span": 1}],
        ],
        "title": "Quarterly Sales Report",
    },
}


@app.command()
def preset(
    name: str = typer.Argument(..., help="Preset name: simple, medium, complex"),
    output: Path = typer.Option(
        None, "--output", "-o", help="Output path (default: {preset}_table.pdf or .png)"
    ),
    style: str = typer.Option("grid", "--style", help="Table style: grid, plain, colored"),
    border: bool = typer.Option(True, "--border/--no-border", help="Enable or disable borders"),
    line_width: float = typer.Option(1.0, "--line-width", "-w", help="Border line thickness"),
    as_image: bool = typer.Option(False, "--as-image", "-i", help="Render as PNG image"),
    dpi: int = typer.Option(150, "--dpi", help="DPI for image rendering"),
) -> None:
    """Generate a table from a preset (simple, medium, complex)."""
    if name not in PRESETS:
        raise typer.BadParameter(f"Unknown preset '{name}'. Choose from: {', '.join(PRESETS.keys())}")

    p = PRESETS[name]
    ext = ".png" if as_image else ".pdf"
    output_path = output or Path(f"{name}_table{ext}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if as_image:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_pdf = Path(tmp.name)

        create_table_pdf(
            tmp_pdf,
            p["columns"],
            p["rows"],
            title=p.get("title"),
            style=style,
            border=border,
            line_width=line_width,
            header_rows=p.get("multi_index"),
        )

        img_output = output_path.with_suffix(".png") if output_path.suffix.lower() != ".png" else output_path
        render_pdf_to_image(tmp_pdf, img_output, dpi=dpi)
        tmp_pdf.unlink()
    else:
        create_table_pdf(
            output_path,
            p["columns"],
            p["rows"],
            title=p.get("title"),
            style=style,
            border=border,
            line_width=line_width,
            header_rows=p.get("multi_index"),
        )


@app.command()
def example() -> None:
    """Generate example PDFs for all presets and styles."""
    examples_dir = Path("examples")
    examples_dir.mkdir(exist_ok=True)

    # Generate all presets
    for preset_name, p in PRESETS.items():
        create_table_pdf(
            examples_dir / f"{preset_name}_table.pdf",
            p["columns"],
            p["rows"],
            title=p.get("title"),
            style="grid",
            header_rows=p.get("multi_index"),
        )

    # Also generate style variations for simple preset
    simple = PRESETS["simple"]
    for style in ["grid", "plain", "colored"]:
        create_table_pdf(
            examples_dir / f"simple_{style}.pdf",
            simple["columns"],
            simple["rows"],
            title=f"Simple Table ({style})",
            style=style,
        )

    # Borderless example
    create_table_pdf(
        examples_dir / "simple_no_border.pdf",
        simple["columns"],
        simple["rows"],
        title="Borderless Table",
        style="plain",
        border=False,
    )

    # Thick border example
    create_table_pdf(
        examples_dir / "simple_thick_border.pdf",
        simple["columns"],
        simple["rows"],
        title="Thick Border (2pt)",
        style="grid",
        line_width=2.0,
    )

    print(f"\nExamples created in {examples_dir}/")


if __name__ == "__main__":
    app()
