#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pymupdf>=1.23.0",
#     "reportlab>=4.0.0",
#     "typer>=0.9.0",
#     "pillow>=10.0.0",
# ]
# ///
"""
Generate complete PDF test fixtures combining proper ReportLab tables and images.

Orchestrates fixture-table and fixture-image skills to create PDFs that properly
test extractor capabilities and expose bugs.

Usage:
    uv run generate.py extractor-bugs --output test.pdf
    uv run generate.py simple --output simple_test.pdf
    uv run generate.py list-presets
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import typer
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

app = typer.Typer(help="Generate complete PDF test fixtures for extractor testing")

# Paths to sibling skills
SKILL_DIR = Path(__file__).parent
FIXTURE_IMAGE_DIR = SKILL_DIR.parent / "fixture-image"
FIXTURE_TABLE_DIR = SKILL_DIR.parent / "fixture-table"
CACHED_IMAGES_DIR = FIXTURE_IMAGE_DIR / "cached_images"
CACHED_FIXTURES_DIR = SKILL_DIR / "cached_fixtures"


def get_cached_image(name: str) -> Optional[Path]:
    """Get path to cached image if it exists."""
    for ext in [".png", ".jpg", ".jpeg"]:
        path = CACHED_IMAGES_DIR / f"{name}{ext}"
        if path.exists():
            return path
    return None


def create_reportlab_table(
    columns: list[str],
    rows: list[list],
    style: str = "grid",
    title: Optional[str] = None,
) -> tuple[Table, Optional[Paragraph]]:
    """Create a ReportLab Table object with proper structure."""
    styles = getSampleStyleSheet()

    # Build table data
    table_data = [columns] + rows

    # Calculate column widths
    num_cols = len(columns)
    available_width = letter[0] - 1.5 * inch
    col_width = available_width / num_cols
    col_widths = [col_width] * num_cols

    table = Table(table_data, colWidths=col_widths)

    # Style based on type
    base_styles = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]

    table.setStyle(TableStyle(base_styles))

    title_para = None
    if title:
        title_para = Paragraph(title, styles["Heading2"])

    return table, title_para


def create_cover_page(doc: fitz.Document, title: str, subtitle: str, image_path: Optional[Path] = None):
    """Create a cover page with optional decorative image."""
    page = doc.new_page(width=612, height=792)

    # Title
    page.insert_text((50, 100), title, fontsize=24, fontname="helv")
    page.insert_text((50, 140), subtitle, fontsize=16)
    page.insert_text((50, 180), "Version 1.0 - Test Fixture", fontsize=12)
    page.insert_text((50, 220), "CONFIDENTIAL", fontsize=14, color=(0.8, 0, 0))

    # Decorative image if provided
    if image_path and image_path.exists():
        img_rect = fitz.Rect(50, 280, 562, 550)
        page.insert_image(img_rect, filename=str(image_path))
        page.insert_text((50, 570), "Figure 0: Cover illustration (decorative)", fontsize=9, color=(0.5, 0.5, 0.5))

    return page


def create_text_page(
    doc: fitz.Document,
    sections: list[dict],
    start_y: int = 70,
) -> fitz.Page:
    """Create a page with text sections."""
    page = doc.new_page(width=612, height=792)
    y = start_y

    for section in sections:
        title = section.get("title", "Section")
        content = section.get("content", "")
        level = section.get("level", 1)

        # Title
        fontsize = 16 if level == 1 else 14 if level == 2 else 12
        page.insert_text((50, y), title, fontsize=fontsize, fontname="helv")
        y += fontsize + 10

        # Content
        if content:
            rect = fitz.Rect(50, y, 562, y + 200)
            rc = page.insert_textbox(rect, content, fontsize=10, fontname="helv")
            y += abs(rc) + 15
        else:
            y += 30  # Empty section gap

        if y > 700:
            break

    return page


def merge_pdfs(output_path: Path, pdf_paths: list[Path]):
    """Merge multiple PDFs into one."""
    result = fitz.open()
    for pdf_path in pdf_paths:
        if pdf_path.exists():
            src = fitz.open(str(pdf_path))
            result.insert_pdf(src)
            src.close()
    result.save(str(output_path))
    result.close()


def build_extractor_bugs_fixture(output: Path):
    """Build the comprehensive extractor bugs reproduction fixture."""
    typer.echo("Building extractor-bugs fixture...")

    # Get cached images
    decorative_img = get_cached_image("decorative")
    flowchart_img = get_cached_image("flowchart")
    network_img = get_cached_image("network_arch")

    # Create main document with PyMuPDF for text pages
    doc = fitz.open()

    # Page 1: Cover with decorative image (tests false table detection)
    create_cover_page(doc, "SPARTA Security Framework", "Technical Assessment Report", decorative_img)

    # Page 2: Executive Summary with malformed title and empty sections
    page = doc.new_page(width=612, height=792)
    y = 70

    # Malformed title (intentionally includes extra text)
    page.insert_text((50, y), "1. Executive Summary // This section gives a brief overview of the technical", fontsize=16, fontname="helv")
    y += 30
    page.insert_text((50, y), "This document presents findings.", fontsize=10)
    y += 40

    # Empty section (just title, no content - tests empty text_content bug)
    page.insert_text((50, y), "1.1 Scope", fontsize=14, fontname="helv")
    y += 60  # Large gap, no content

    page.insert_text((50, y), "1.2 Methodology", fontsize=14, fontname="helv")
    y += 25
    rect = fitz.Rect(50, y, 562, y + 100)
    page.insert_textbox(rect, "The assessment followed NIST SP 800-53 guidelines and incorporated threat modeling using STRIDE methodology. Testing was conducted over a 4-week period.", fontsize=10)

    # Page 3: Architecture with diagram
    page = doc.new_page(width=612, height=792)
    y = 70
    page.insert_text((50, y), "2. System Architecture", fontsize=16, fontname="helv")
    y += 30
    rect = fitz.Rect(50, y, 562, y + 60)
    page.insert_textbox(rect, "The target infrastructure consists of a multi-tier architecture with segregated network zones.", fontsize=10)
    y += 80

    if network_img and network_img.exists():
        img_rect = fitz.Rect(50, y, 562, y + 270)
        page.insert_image(img_rect, filename=str(network_img))
        y += 290
        page.insert_text((50, y), "Figure 1: Network Architecture Overview", fontsize=10)

    # Save text pages to temp file
    text_pdf = Path(tempfile.mktemp(suffix=".pdf"))
    doc.save(str(text_pdf))
    doc.close()

    # Create proper ReportLab table PDF
    table_pdf = Path(tempfile.mktemp(suffix=".pdf"))

    table_doc = SimpleDocTemplate(
        str(table_pdf),
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch,
    )

    styles = getSampleStyleSheet()
    elements = []

    # Page 4: Vulnerability table (proper ReportLab table)
    elements.append(Paragraph("3. Vulnerability Assessment Results", styles["Heading1"]))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("The following table summarizes identified vulnerabilities:", styles["Normal"]))
    elements.append(Spacer(1, 0.15*inch))

    vuln_table, _ = create_reportlab_table(
        columns=["ID", "Vulnerability", "Severity", "Status"],
        rows=[
            ["V-001", "SQL Injection in login form", "Critical", "Remediated"],
            ["V-002", "XSS in search function", "High", "In Progress"],
            ["V-003", "Missing CSRF tokens", "Medium", "Open"],
            ["V-004", "Weak password policy", "Medium", "Open"],
            ["V-005", "Outdated SSL/TLS version", "High", "Remediated"],
            ["V-006", "Information disclosure in errors", "Low", "Open"],
        ],
    )
    elements.append(vuln_table)
    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("Table 1: Vulnerability Summary", styles["Normal"]))
    elements.append(Spacer(1, 0.3*inch))

    # Page 5: Remediation flowchart
    elements.append(Paragraph("4. Remediation Process", styles["Heading1"]))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("The following flowchart outlines the remediation workflow:", styles["Normal"]))
    elements.append(Spacer(1, 0.15*inch))

    if flowchart_img and flowchart_img.exists():
        elements.append(Image(str(flowchart_img), width=5*inch, height=3.5*inch))
        elements.append(Paragraph("Figure 2: Remediation Workflow", styles["Normal"]))

    # Many sections to stress summarizer
    sections_data = [
        ("5. Access Control Assessment", "Access controls were evaluated across all system components."),
        ("5.1 Authentication Mechanisms", "Multi-factor authentication is deployed for administrative access."),
        ("5.2 Authorization Controls", "Privilege escalation paths were identified in the CI/CD pipeline."),
        ("6. Cryptographic Controls", "Encryption standards vary across the infrastructure."),
        ("6.1 Key Management", "HSMs are used for production keys."),
        ("6.2 Certificate Management", "SSL certificates are managed via Let's Encrypt."),
        ("7. Logging and Monitoring", "Centralized logging is implemented using ELK stack."),
        ("7.1 Log Retention", "Logs are retained for 90 days in hot storage."),
        ("7.2 Alerting Configuration", "Critical alerts route to PagerDuty."),
        ("8. Incident Response", "IR playbooks exist for common scenarios."),
        ("8.1 Detection Capabilities", "Mean time to detect is approximately 4 hours."),
        ("8.2 Response Procedures", "Documented procedures for containment phases."),
        ("9. Compliance Status", "The organization maintains SOC 2 Type II certification."),
        ("9.1 Gap Analysis", "Minor gaps identified in asset inventory."),
        ("9.2 Remediation Timeline", "All gaps targeted for Q2 2026."),
        ("10. Recommendations", "Priority recommendations focus on access control."),
        ("10.1 Short-term Actions", "Implement least privilege within 30 days."),
        ("10.2 Long-term Roadmap", "Zero-trust architecture planned for 18-month horizon."),
    ]

    for title, content in sections_data:
        is_main = "." not in title.split()[0] or title.split()[0].count(".") == 0
        style = "Heading1" if is_main else "Heading2"
        elements.append(Paragraph(title, styles[style]))
        elements.append(Paragraph(content, styles["Normal"]))
        elements.append(Spacer(1, 0.15*inch))

    # Appendices
    elements.append(Paragraph("Appendix A: Testing Tools", styles["Heading1"]))
    tools_text = """The following tools were used: Nmap 7.94 for network scanning,
    Burp Suite Professional for web application testing, Metasploit Framework for
    exploitation verification, Nessus for vulnerability scanning."""
    elements.append(Paragraph(tools_text, styles["Normal"]))

    table_doc.build(elements)

    # Merge text pages + table pages
    merge_pdfs(output, [text_pdf, table_pdf])

    # Cleanup temp files
    text_pdf.unlink(missing_ok=True)
    table_pdf.unlink(missing_ok=True)

    typer.echo(f"Created: {output}")
    typer.echo(f"  - Uses proper ReportLab tables (Marker-detectable)")
    typer.echo(f"  - Includes decorative images (tests VLM classification)")
    typer.echo(f"  - Has malformed titles and empty sections (tests edge cases)")


@app.command()
def extractor_bugs(
    output: Path = typer.Option(
        Path("extractor_bugs_fixture.pdf"),
        "--output", "-o",
        help="Output PDF path",
    ),
):
    """Generate fixture that reproduces known extractor bugs."""
    output.parent.mkdir(parents=True, exist_ok=True)
    build_extractor_bugs_fixture(output)

    # Also save to cached_fixtures
    cached = CACHED_FIXTURES_DIR / "extractor_bugs_fixture.pdf"
    if output.resolve() != cached.resolve():
        CACHED_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy(output, cached)
        typer.echo(f"Cached: {cached}")


@app.command()
def simple(
    output: Path = typer.Option(
        Path("simple_fixture.pdf"),
        "--output", "-o",
        help="Output PDF path",
    ),
):
    """Generate a simple 3-page test fixture."""
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output),
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
    )

    styles = getSampleStyleSheet()
    elements = []

    # Page 1: Title and intro
    elements.append(Paragraph("Simple Test Fixture", styles["Title"]))
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph("This is a simple test PDF for extraction testing.", styles["Normal"]))
    elements.append(Spacer(1, 0.3*inch))

    # Simple table
    table, title = create_reportlab_table(
        columns=["ID", "Name", "Value"],
        rows=[["1", "Alpha", "100"], ["2", "Beta", "200"], ["3", "Gamma", "300"]],
        title="Sample Data",
    )
    if title:
        elements.append(title)
        elements.append(Spacer(1, 0.1*inch))
    elements.append(table)

    doc.build(elements)
    typer.echo(f"Created: {output}")


@app.command()
def list_presets():
    """List available fixture presets."""
    presets = {
        "extractor-bugs": "Reproduces known extractor issues (empty sections, false tables, malformed titles)",
        "simple": "Basic 3-page PDF with table and text",
    }

    typer.echo("Available presets:\n")
    for name, desc in presets.items():
        typer.echo(f"  {name:20} {desc}")
    typer.echo("\nUsage: uv run generate.py <preset> --output file.pdf")


@app.command()
def custom(
    content: str = typer.Option(..., "--content", "-c", help="Custom text or pattern to inject"),
    title: str = typer.Option("Bug Reproduction", "--title", "-t", help="Title for the reproduction"),
    output: Path = typer.Option(
        Path("custom_repro.pdf"),
        "--output", "-o",
        help="Output PDF path",
    ),
):
    """Generate a 1-page PDF with custom cursed content."""
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    # Title
    page.insert_text((50, 70), title, fontsize=18, fontname="helv", color=(0.7, 0, 0))
    
    # Content block
    rect = fitz.Rect(50, 110, 562, 700)
    page.insert_textbox(rect, content, fontsize=12, fontname="helv")
    
    doc.save(str(output))
    doc.close()
    typer.echo(f"Created custom repro: {output}")

@app.command()
def verify(
    pdf_path: Path = typer.Argument(..., help="PDF file to verify"),
):
    """Verify a fixture PDF has proper table structure."""
    try:
        import camelot
        tables = camelot.read_pdf(str(pdf_path), pages="all", flavor="lattice")
        typer.echo(f"Tables detected by Camelot: {len(tables)}")
        for i, t in enumerate(tables):
            typer.echo(f"  Table {i+1}: {t.shape[0]} rows x {t.shape[1]} cols on page {t.page}")
    except ImportError:
        typer.echo("Install camelot-py for verification: pip install camelot-py[cv]")
    except Exception as e:
        typer.echo(f"Verification error: {e}")


if __name__ == "__main__":
    app()
