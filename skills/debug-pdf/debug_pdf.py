#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pymupdf>=1.23.0",
#     "pymupdf4llm>=0.0.17",
#     "httpx>=0.25.0",
#     "typer>=0.9.0",
#     "loguru>=0.7.0",
# ]
# ///
"""
Debug PDF Skill - Failure-to-fixture automation for PDF extractors.

Analyzes failed PDF URLs, identifies breaking patterns, and generates
minimal reproduction fixtures for regression testing.

Usage:
    # Single URL analysis
    uv run debug_pdf.py --url "https://example.com/broken.pdf"

    # Batch analysis
    uv run debug_pdf.py batch --file failed_urls.txt

    # Combine all fixtures
    uv run debug_pdf.py combine --output stress_test.pdf --max-pages 20
"""

import os
import sys
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

import fitz  # PyMuPDF
import httpx
import typer
from loguru import logger

app = typer.Typer(help="Debug PDF - Failure-to-fixture automation")

# ============================================================================
# PATH CONFIGURATION - Auto-detect skill locations
# ============================================================================

SKILL_DIR = Path(__file__).parent.resolve()
PI_SKILLS_DIR = SKILL_DIR.parent

# Data directory for persistent state
DATA_DIR = Path(os.environ.get("DEBUG_PDF_DATA", Path.home() / ".pi" / "debug-pdf"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR = DATA_DIR / "sessions"
FIXTURES_DIR = DATA_DIR / "fixtures"
SESSIONS_DIR.mkdir(exist_ok=True)
FIXTURES_DIR.mkdir(exist_ok=True)

# Sibling skill paths (auto-detect)
FETCHER_RUN = PI_SKILLS_DIR / "fetcher" / "run.sh"
FIXTURE_TRICKY_DIR = PI_SKILLS_DIR / "fixture-tricky"
FIGURE_RUN = PI_SKILLS_DIR / "create-figure" / "run.sh"

# Extractor skill - check multiple locations
def find_extractor_run():
    candidates = [
        PI_SKILLS_DIR / "extractor" / "run.sh",
        Path("/home/graham/workspace/experiments/memory/.agents/skills/extractor/run.sh"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

EXTRACTOR_RUN = find_extractor_run()

# Memory skill for pattern recall/storage
def find_memory_run():
    candidates = [
        Path("/home/graham/workspace/experiments/memory/.agents/skills/memory/run.sh"),
        PI_SKILLS_DIR / "memory" / "run.sh",
        Path.home() / ".pi" / "agent" / "skills" / "memory" / "run.sh",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

MEMORY_RUN = find_memory_run()

# Agent inbox - check multiple locations
def find_inbox_tool():
    candidates = [
        Path("/home/graham/workspace/experiments/memory/.agents/skills/agent-inbox/run.sh"),
        Path("/home/graham/workspace/experiments/memory/.agents/skills/agent-inbox/agent-inbox"),
        PI_SKILLS_DIR / "agent-inbox" / "run.sh",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

INBOX_TOOL = find_inbox_tool()

# ============================================================================
# DETECTION FUNCTION REGISTRY (Plug-and-Play Pattern)
# ============================================================================
# To add a new detector:
# 1. Create a function: def detect_my_pattern(page_or_doc) -> list[tuple[str, str]]
# 2. Register it: PAGE_DETECTORS.append(detect_my_pattern) or DOC_DETECTORS.append(...)
# 3. Add pattern description to PATTERNS dict
# 4. (Optional) Add test in tests/test_debug_pdf.py

PAGE_DETECTORS: list = []  # Functions that run on each page
DOC_DETECTORS: list = []   # Functions that run once per document


def register_page_detector(func):
    """Decorator to register a page-level detection function."""
    PAGE_DETECTORS.append(func)
    return func


def register_doc_detector(func):
    """Decorator to register a document-level detection function."""
    DOC_DETECTORS.append(func)
    return func


# ============================================================================
# FAILURE PATTERN DEFINITIONS
# ============================================================================

PATTERNS = {
    # Structural
    "scanned_no_ocr": "Scanned image PDF without text layer",
    "sparse_content_slides": "Slide deck with minimal text per page",
    "multi_column": "Complex multi-column layouts",
    "watermarks": "Text obscured by watermark overlays",

    # Encoding
    "toc_noise": "Table of contents with dotted leaders",
    "metadata_artifacts": "Print metadata (Jkt/PO/Frm) in content",
    "invisible_chars": "Zero-width spaces, direction markers",
    "curly_quotes": "Windows-1252 encoded smart quotes",
    "ligatures": "fi/fl/ff ligature characters",

    # Layout
    "footnotes_inline": "Footnotes merged into body text",
    "split_tables": "Tables spanning multiple pages",
    "header_footer_bleed": "Headers/footers mixed into content",
    "diagram_heavy": "Many embedded diagrams/charts",

    # Network (detected during download)
    "archive_org_wrap": "Wayback Machine URL wrapper",
    "auth_required": "Marketing platform cookie/login gate",
    "access_restricted": "Government/defense access control (403)",

    # Contract/Signature (aerospace engineering documents)
    "signed_contract": "Contract with signature fields (first pages)",
    "government_signed": "DoD/Federal PKI signed document",

    # Aerospace-specific patterns
    "itar_export_control": "ITAR/Export control notice detected",
    "mil_spec_reference": "Military specification reference (MIL-STD, MIL-PRF)",
    "aerospace_spec": "Aerospace specification (SAE AS, DO-178, RTCA)",
    "technical_drawing": "Technical drawing with title block/part numbers",
    "classification_marking": "Classification marking (CUI, FOUO, UNCLASSIFIED)",
    "cage_dfar_reference": "CAGE code or DFAR clause reference",
}

# ============================================================================
# WAYBACK URL DETECTION
# ============================================================================

WAYBACK_PATTERN = re.compile(
    r'https?://web\.archive\.org/web/(\d{1,14})/(.+)',
    re.IGNORECASE
)


def is_wayback_url(url: str) -> bool:
    """Check if URL is an Archive.org Wayback Machine URL."""
    return bool(WAYBACK_PATTERN.match(url))


def extract_original_url(wayback_url: str) -> str | None:
    """Extract original URL from Wayback Machine URL."""
    match = WAYBACK_PATTERN.match(wayback_url)
    return match.group(2) if match else None


# ============================================================================
# SECURITY HELPERS
# ============================================================================

def is_valid_url(url: str) -> bool:
    """Validate URL: http/https with netloc; reject control chars/newlines."""
    if not isinstance(url, str) or len(url) > 2048:
        return False
    if any(c in url for c in ["\n", "\r", "\x00"]):
        return False
    parsed = urlparse(url)
    return bool(parsed.scheme in {"http", "https"} and parsed.netloc)


# ============================================================================
# PATTERN DETECTION FUNCTIONS
# ============================================================================

@register_page_detector
def detect_header_footer_bleed(page) -> list[tuple[str, str]]:
    """Detect header/footer content bleeding into body text using PyMuPDF4LLM Layout."""
    try:
        # Try using pymupdf4llm for ML-based layout detection
        import pymupdf4llm

        doc = page.parent
        page_num = page.number

        # Extract with headers/footers
        with_hf = pymupdf4llm.to_markdown(doc, pages=[page_num])

        # Extract without headers/footers (if supported)
        try:
            without_hf = pymupdf4llm.to_markdown(
                doc, pages=[page_num],
                margins=(72, 72, 72, 72)  # Use margins to exclude header/footer areas
            )

            # If significant difference, headers/footers are bleeding
            if len(with_hf) > len(without_hf) * 1.15:  # >15% difference
                diff_chars = len(with_hf) - len(without_hf)
                return [("header_footer_bleed", f"Detected via Layout API: {diff_chars} chars in header/footer regions")]
        except (TypeError, AttributeError):
            pass  # Fallback if margins param not supported

    except ImportError:
        pass

    # Fallback: Heuristic-based detection
    page_height = page.rect.height
    blocks = page.get_text("dict").get("blocks", [])

    header_threshold = page_height * 0.08  # Top 8%
    footer_threshold = page_height * 0.92  # Bottom 8%

    header_text = []
    footer_text = []

    for block in blocks:
        if block.get("type") != 0:  # Not text
            continue
        bbox = block.get("bbox", [0, 0, 0, 0])

        # Check header region
        if bbox[1] < header_threshold:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text and len(text) > 10:  # Substantial text
                        header_text.append(text)

        # Check footer region
        if bbox[3] > footer_threshold:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text and len(text) > 10:
                        footer_text.append(text)

    results = []
    if header_text:
        results.append(("header_footer_bleed", f"Header content: {header_text[0][:50]}"))
    if footer_text:
        results.append(("header_footer_bleed", f"Footer content: {footer_text[0][:50]}"))

    return results


@register_page_detector
def detect_multi_column(page) -> list[tuple[str, str]]:
    """Detect multi-column layouts using text block analysis."""
    blocks = page.get_text("dict").get("blocks", [])
    text_blocks = [b for b in blocks if b.get("type") == 0]

    if len(text_blocks) < 4:
        return []

    # Get x-coordinates of block centers
    page_width = page.rect.width
    mid = page_width / 2

    # Analyze block positions
    left_blocks = []
    right_blocks = []

    for b in text_blocks:
        bbox = b.get("bbox", [0, 0, 0, 0])
        block_center_x = (bbox[0] + bbox[2]) / 2
        block_width = bbox[2] - bbox[0]

        # Skip blocks that span most of the page (likely headers/titles)
        if block_width > page_width * 0.7:
            continue

        if block_center_x < mid * 0.85:
            left_blocks.append(b)
        elif block_center_x > mid * 1.15:
            right_blocks.append(b)

    # Need multiple blocks on each side for column detection
    if len(left_blocks) >= 3 and len(right_blocks) >= 3:
        # Verify vertical overlap (columns should have content at similar y-positions)
        left_y_ranges = [(b["bbox"][1], b["bbox"][3]) for b in left_blocks]
        right_y_ranges = [(b["bbox"][1], b["bbox"][3]) for b in right_blocks]

        overlap_count = 0
        for ly1, ly2 in left_y_ranges:
            for ry1, ry2 in right_y_ranges:
                if ly1 < ry2 and ly2 > ry1:  # Ranges overlap
                    overlap_count += 1

        if overlap_count >= 2:
            return [("multi_column", f"Detected 2 columns: {len(left_blocks)} left, {len(right_blocks)} right blocks")]

    return []


def detect_split_tables(doc, page_num: int) -> list[tuple[str, str]]:
    """Detect tables that may span across pages (flag only, no merging)."""
    page = doc[page_num]

    try:
        tables = page.find_tables()
    except Exception:
        return []

    if not tables:
        return []

    page_height = page.rect.height
    results = []

    for table in tables:
        bbox = table.bbox

        # Table extends to bottom 5% of page
        if bbox[3] > page_height * 0.95:
            # Check if next page starts with a table
            if page_num + 1 < len(doc):
                next_page = doc[page_num + 1]
                try:
                    next_tables = next_page.find_tables()
                    for nt in next_tables:
                        # Table starts in top 10% of next page
                        if nt.bbox[1] < page_height * 0.10:
                            results.append((
                                "split_tables",
                                f"Table likely spans pages {page_num + 1}-{page_num + 2}"
                            ))
                            break
                except Exception:
                    pass

    return results


@register_page_detector
def detect_footnotes(page) -> list[tuple[str, str]]:
    """Detect footnote patterns in page content."""
    blocks = page.get_text("dict").get("blocks", [])
    page_height = page.rect.height

    # Find text in bottom 15%
    bottom_threshold = page_height * 0.85
    bottom_text_blocks = []
    body_font_sizes = []

    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                origin = span.get("origin", [0, 0])
                y = origin[1] if len(origin) > 1 else 0
                size = span.get("size", 12)
                text = span.get("text", "")

                if y > bottom_threshold:
                    bottom_text_blocks.append({
                        "text": text,
                        "size": size,
                        "y": y
                    })
                else:
                    body_font_sizes.append(size)

    if not body_font_sizes or not bottom_text_blocks:
        return []

    avg_body_size = sum(body_font_sizes) / len(body_font_sizes)

    # Check for footnote indicators
    results = []

    for span_data in bottom_text_blocks:
        text = span_data["text"]
        size = span_data["size"]

        # Check if bottom text is smaller (footnote-like)
        if size < avg_body_size * 0.85:
            # Check for footnote markers
            if re.match(r'^[\d\*†‡§¶\[\(]', text.strip()):
                results.append(("footnotes_inline", f"Footnote marker: {text[:60]}"))
                break
            elif len(text.strip()) > 20:  # Substantial small text at bottom
                results.append(("footnotes_inline", f"Small text at bottom: {text[:60]}"))
                break

    # Also check for superscript numbers in body
    body_text = ""
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                body_text += span.get("text", "")

    # Look for footnote reference patterns in body
    if re.search(r'\[\d+\]|\(\d+\)|[\*†‡§]\s', body_text):
        if not results:  # Only add if not already detected
            results.append(("footnotes_inline", "Footnote references detected in body"))

    return results


@register_doc_detector
def detect_signed_contract(doc, max_pages: int = 5) -> list[tuple[str, str]]:
    """Detect signature fields in first N pages (typical for contracts/aerospace docs)."""
    results = []
    sig_flags = doc.get_sigflags()

    if sig_flags == -1:
        return []  # Error or no signature support
    elif sig_flags == 0:
        return []  # No signature fields
    elif sig_flags >= 1:
        # Has signature fields - find them
        signature_pages = []
        for page_num in range(min(max_pages, len(doc))):
            page = doc[page_num]
            try:
                sig_widgets = list(page.widgets(types=[fitz.PDF_WIDGET_TYPE_SIGNATURE]))
                if sig_widgets:
                    for widget in sig_widgets:
                        is_signed = getattr(widget, 'is_signed', None)
                        field_name = getattr(widget, 'field_name', 'unknown')
                        signature_pages.append({
                            "page": page_num + 1,
                            "field": field_name,
                            "signed": is_signed
                        })
            except Exception:
                pass

        if signature_pages:
            signed_count = sum(1 for s in signature_pages if s.get("signed"))
            total = len(signature_pages)
            pages_with_sigs = list(set(s["page"] for s in signature_pages))
            results.append((
                "signed_contract",
                f"{signed_count}/{total} signatures on pages {pages_with_sigs}"
            ))

    return results


@register_doc_detector
def detect_government_signatures(doc) -> list[tuple[str, str]]:
    """Detect government/DoD certificate signatures in PDF."""
    results = []
    gov_issuers = [
        "Department of Defense",
        "DoD Root CA",
        "Federal PKI",
        "FPKI",
        "DOD ID CA",
        "DOD EMAIL CA",
        "Common Access Card",
        "PIV",
        "US Government"
    ]

    for page in doc:
        try:
            for widget in page.widgets(types=[fitz.PDF_WIDGET_TYPE_SIGNATURE]):
                xref = widget.xref
                # Try to extract signature details via low-level API
                try:
                    v_key = doc.xref_get_key(xref, "V")
                    if v_key[0] == "xref":
                        v_xref = int(v_key[1].split()[0])
                        keys = doc.xref_get_keys(v_xref)

                        # Check for Name/Reason fields that might indicate gov certs
                        for key in ["Name", "Reason", "ContactInfo", "Location"]:
                            if key in keys:
                                val = doc.xref_get_key(v_xref, key)
                                if val[0] == "string":
                                    text = val[1]
                                    for issuer in gov_issuers:
                                        if issuer.lower() in text.lower():
                                            results.append((
                                                "government_signed",
                                                f"Detected {issuer} signature: {text[:60]}"
                                            ))
                                            return results  # One is enough
                except Exception:
                    pass
        except Exception:
            pass

    return results


# ============================================================================
# AEROSPACE-SPECIFIC DETECTORS (Plug-and-Play)
# ============================================================================

@register_page_detector
def detect_itar_export_control(page) -> list[tuple[str, str]]:
    """Detect ITAR and export control notices in page content."""
    text = page.get_text().upper()

    itar_patterns = [
        "ITAR",
        "INTERNATIONAL TRAFFIC IN ARMS",
        "EXPORT CONTROLLED",
        "EXPORT CONTROL",
        "EAR99",
        "ECCN",
        "DISTRIBUTION STATEMENT",
        "DISTRIBUTION A",
        "DISTRIBUTION B",
        "DISTRIBUTION C",
        "DISTRIBUTION D",
        "DISTRIBUTION E",
        "DISTRIBUTION F",
        "22 CFR 120",
        "22 CFR 121",
        "15 CFR 730",
    ]

    for pattern in itar_patterns:
        if pattern in text:
            # Find context around the match
            idx = text.find(pattern)
            context = text[max(0, idx-20):min(len(text), idx+50)].replace("\n", " ")
            return [("itar_export_control", f"Found: {context.strip()[:80]}")]

    return []


@register_page_detector
def detect_mil_spec_reference(page) -> list[tuple[str, str]]:
    """Detect military specification references (MIL-STD, MIL-PRF, etc.)."""
    text = page.get_text()

    # Military specification patterns
    mil_patterns = [
        r"MIL-STD-\d+[A-Z]?",
        r"MIL-PRF-\d+[A-Z]?",
        r"MIL-DTL-\d+[A-Z]?",
        r"MIL-HDBK-\d+[A-Z]?",
        r"MIL-S-\d+[A-Z]?",
        r"MIL-A-\d+[A-Z]?",
        r"MIL-C-\d+[A-Z]?",
        r"MIL-I-\d+[A-Z]?",
        r"QPL-\d+",
        r"QML-\d+",
    ]

    for pattern in mil_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return [("mil_spec_reference", f"Found: {match.group(0)}")]

    return []


@register_page_detector
def detect_aerospace_spec(page) -> list[tuple[str, str]]:
    """Detect aerospace industry specifications (SAE, RTCA, etc.)."""
    text = page.get_text()

    # Aerospace specification patterns
    aero_patterns = [
        r"SAE\s*AS\d+[A-Z]?",          # SAE Aerospace Standards
        r"SAE\s*AMS\d+[A-Z]?",         # SAE Aerospace Material Specs
        r"SAE\s*ARP\d+[A-Z]?",         # SAE Aerospace Recommended Practices
        r"DO-\d+[A-Z]?",               # RTCA standards (DO-178, DO-254, etc.)
        r"RTCA/DO-\d+[A-Z]?",
        r"AS9100[A-Z]?",               # Aerospace Quality Management
        r"AS9110[A-Z]?",
        r"AS9120[A-Z]?",
        r"NADCAP",                      # Special process accreditation
        r"ATA\s*\d{2,3}",              # ATA chapters
        r"ASTM\s*[A-Z]\d+",            # ASTM standards
        r"NAS\d+",                      # National Aerospace Standards
        r"AN\d+",                       # Air Force/Navy standards
        r"MS\d+",                       # Military standards
    ]

    for pattern in aero_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return [("aerospace_spec", f"Found: {match.group(0)}")]

    return []


@register_page_detector
def detect_technical_drawing(page) -> list[tuple[str, str]]:
    """Detect technical drawing elements (title blocks, part numbers, revisions)."""
    text = page.get_text()

    # Technical drawing patterns
    drawing_patterns = [
        (r"PART\s*(?:NO|NUMBER|#)[:\s]*[\w\-]+", "Part number"),
        (r"DWG\s*(?:NO|NUMBER|#)[:\s]*[\w\-]+", "Drawing number"),
        (r"REV(?:ISION)?[:\s]*[A-Z0-9]+", "Revision"),
        (r"SCALE[:\s]*\d+[:/]\d+", "Scale"),
        (r"SHEET\s*\d+\s*OF\s*\d+", "Sheet reference"),
        (r"CAGE\s*(?:CODE)?[:\s]*[A-Z0-9]{5}", "CAGE code"),
        (r"DRAWN\s*BY[:\s]*\w+", "Drawn by"),
        (r"CHECKED\s*BY[:\s]*\w+", "Checked by"),
        (r"APPROVED\s*BY[:\s]*\w+", "Approved by"),
        (r"DATE[:\s]*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", "Date"),
        (r"UNLESS\s*OTHERWISE\s*SPECIFIED", "General notes"),
        (r"THIRD\s*ANGLE\s*PROJECTION", "Projection type"),
        (r"TOLERANCES[:\s]", "Tolerances"),
        (r"MATERIAL[:\s]", "Material callout"),
    ]

    matches = []
    for pattern, desc in drawing_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            matches.append(f"{desc}: {match.group(0)[:30]}")

    # Need multiple indicators to confirm it's a technical drawing
    if len(matches) >= 3:
        return [("technical_drawing", f"Title block elements: {', '.join(matches[:3])}")]

    return []


@register_page_detector
def detect_classification_marking(page) -> list[tuple[str, str]]:
    """Detect classification and handling markings."""
    text = page.get_text().upper()

    # Classification markings (check both header and footer regions)
    page_height = page.rect.height
    blocks = page.get_text("dict").get("blocks", [])

    classification_terms = [
        "UNCLASSIFIED",
        "CONTROLLED UNCLASSIFIED INFORMATION",
        "CUI",
        "FOR OFFICIAL USE ONLY",
        "FOUO",
        "SENSITIVE BUT UNCLASSIFIED",
        "SBU",
        "LIMITED DISTRIBUTION",
        "PROPRIETARY",
        "COMPANY CONFIDENTIAL",
        "BUSINESS SENSITIVE",
        "COMPETITION SENSITIVE",
        "SOURCE SELECTION INFORMATION",
    ]

    # Check text in header/footer regions (top/bottom 10%)
    for block in blocks:
        if block.get("type") != 0:
            continue
        bbox = block.get("bbox", [0, 0, 0, 0])

        # Header or footer region
        if bbox[1] < page_height * 0.10 or bbox[3] > page_height * 0.90:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "").upper()
                    for term in classification_terms:
                        if term in span_text:
                            return [("classification_marking", f"Found: {term}")]

    # Also check full page text
    for term in classification_terms:
        if term in text:
            return [("classification_marking", f"Found in content: {term}")]

    return []


@register_page_detector
def detect_cage_dfar_reference(page) -> list[tuple[str, str]]:
    """Detect CAGE codes and DFAR clause references."""
    text = page.get_text()

    patterns = [
        (r"CAGE\s*(?:CODE)?[:\s]*([A-Z0-9]{5})", "CAGE code"),
        (r"DFARS?\s*\d{3}\.\d+", "DFAR clause"),
        (r"FAR\s*\d{1,2}\.\d+", "FAR clause"),
        (r"DPAS\s*(?:RATING)?[:\s]*[A-Z]{2}\d?", "DPAS rating"),
        (r"CONTRACT\s*(?:NO|NUMBER|#)[:\s]*[\w\-]+", "Contract number"),
        (r"CLIN\s*\d+", "Contract line item"),
        (r"CDRL\s*[A-Z]\d+", "Contract data item"),
        (r"DD\s*FORM\s*\d+", "DD Form reference"),
        (r"SF\s*\d+", "Standard Form reference"),
    ]

    results = []
    for pattern, desc in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            results.append(f"{desc}: {match.group(0)}")

    if results:
        return [("cage_dfar_reference", "; ".join(results[:3]))]

    return []


# ============================================================================
# CORE FUNCTIONS
# ============================================================================

def download_pdf(url: str, output_path: Path) -> tuple[bool, list[str]]:
    """Download PDF using fetcher skill or direct HTTP.

    Returns:
        Tuple of (success: bool, detected_patterns: list[str])
        Patterns may include 'auth_required', 'access_restricted'
    """
    logger.info(f"Downloading {url}...")
    detected_patterns = []

    # Validate URL first
    if not is_valid_url(url):
        logger.error("Invalid URL: only http/https schemes are allowed")
        return False, []

    # Try fetcher skill first
    if FETCHER_RUN and FETCHER_RUN.exists():
        # Use unique temp dir to avoid race conditions
        tmp_fetch_dir = SKILL_DIR / f"tmp_fetch_{uuid4().hex}"
        if tmp_fetch_dir.exists():
            shutil.rmtree(tmp_fetch_dir)

        try:
            result = subprocess.run(
                [str(FETCHER_RUN), "get", url, "--out", str(tmp_fetch_dir)],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
                cwd=str(FETCHER_RUN.parent)
            )

            if result.returncode == 0:
                downloads_dir = tmp_fetch_dir / "downloads"
                if downloads_dir.exists():
                    pdfs = list(downloads_dir.glob("*.pdf"))
                    if not pdfs:
                        pdfs = [p for p in downloads_dir.glob("*") if p.is_file()]
                    if pdfs:
                        shutil.copy(pdfs[0], output_path)
                        logger.info(f"Downloaded to {output_path}")
                        return True, detected_patterns
        except subprocess.TimeoutExpired:
            logger.warning("Fetcher timed out, trying direct HTTP")
        except Exception as e:
            logger.warning(f"Fetcher failed: {e}, trying direct HTTP")
        finally:
            if tmp_fetch_dir.exists():
                shutil.rmtree(tmp_fetch_dir)

    # Fallback to direct HTTP
    try:
        with httpx.Client(follow_redirects=True, timeout=60) as client:
            response = client.get(url)

            # Check for auth/access patterns BEFORE raising for status
            if response.status_code == 401:
                logger.warning("HTTP 401 - Authentication required")
                detected_patterns.append("auth_required")
                return False, detected_patterns
            elif response.status_code == 403:
                logger.warning("HTTP 403 - Access restricted")
                detected_patterns.append("access_restricted")
                return False, detected_patterns

            response.raise_for_status()

            # Check if response is actually a PDF
            content_type = response.headers.get("content-type", "")
            content = response.content

            if "text/html" in content_type.lower():
                # Likely a login wall or redirect page
                if any(kw in content.decode("utf-8", errors="ignore").lower()
                       for kw in ["login", "sign in", "authenticate", "password"]):
                    logger.warning("Login wall detected - content is HTML login page")
                    detected_patterns.append("auth_required")
                    return False, detected_patterns

            # Check for valid PDF signature
            if not content[:5] == b"%PDF-":
                logger.warning("Response does not appear to be a valid PDF")
                if b"<!DOCTYPE" in content[:100] or b"<html" in content[:100]:
                    detected_patterns.append("auth_required")
                return False, detected_patterns

            output_path.write_bytes(content)
            logger.info(f"Downloaded via HTTP to {output_path}")
            return True, detected_patterns
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            detected_patterns.append("auth_required")
        elif e.response.status_code == 403:
            detected_patterns.append("access_restricted")
        logger.error(f"Download failed: {e}")
        return False, detected_patterns
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False, detected_patterns


def analyze_pdf(pdf_path: Path) -> dict:
    """Analyze PDF structure and identify failure patterns."""
    logger.info(f"Analyzing {pdf_path.name}...")

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return {
            "pages": 0,
            "is_scanned": True,
            "patterns": ["corrupted_file"],
            "cursed_content": [],
            "error": str(e)
        }

    report = {
        "pages": len(doc),
        "is_scanned": True,
        "patterns": [],
        "cursed_content": [],
        "file_size_kb": pdf_path.stat().st_size // 1024
    }

    text_count = 0
    words_per_page = []
    image_pages = 0

    try:
        for page_num, page in enumerate(doc):
            text = page.get_text()
            text_count += len(text)
            words_per_page.append(len(text.split()))

            # Check if page is primarily images
            images = page.get_images()
            if images and len(text.strip()) < 100:
                image_pages += 1

            # TOC dots pattern
            if re.search(r".*\.{5,}\s*\d+", text):
                match = re.search(r".*\.{5,}\s*\d+", text)
                report["cursed_content"].append(("toc_noise", match.group(0)[:100]))

            # Metadata artifacts (Jkt / PO / Frm)
            if "Jkt" in text and "PO" in text and "Frm" in text:
                lines = [l for l in text.split("\n") if "Jkt" in l and "PO" in l]
                if lines:
                    report["cursed_content"].append(("metadata_artifacts", lines[0][:100]))

            # Zero-width and invisible chars
            if re.search(r"[\u200b-\u200d\uFEFF]", text):
                report["cursed_content"].append(("invisible_chars", "Zero-width spaces detected"))

            # Windows-1252 curly quotes
            if re.search(r"[\u2018\u2019\u201c\u201d]", text):
                report["cursed_content"].append(("curly_quotes", "Smart quotes detected"))

            # Ligatures
            if re.search(r"[\ufb00-\ufb06]", text):
                report["cursed_content"].append(("ligatures", "Ligature characters detected"))

            # Watermark detection (gray diagonal text patterns)
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            for block in blocks.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            # Check for gray/light colored text (potential watermark)
                            color = span.get("color", 0)
                            if 0.5 < color < 0.9 and span.get("size", 12) > 20:
                                report["cursed_content"].append(("watermarks", f"Large gray text: {span.get('text', '')[:50]}"))
    finally:
        try:
            doc.close()
        except Exception:
            pass

    # Determine patterns
    if text_count > 100:
        report["is_scanned"] = False

    avg_words = sum(words_per_page) / max(1, len(words_per_page))

    if report["is_scanned"]:
        report["patterns"].append("scanned_no_ocr")
    if avg_words < 50:
        report["patterns"].append("sparse_content_slides")
    if image_pages > len(words_per_page) * 0.5:
        report["patterns"].append("diagram_heavy")

    # Add patterns from cursed content
    for label, _ in report["cursed_content"]:
        if label not in report["patterns"]:
            report["patterns"].append(label)

    # Run advanced pattern detection using registered detectors
    try:
        doc = fitz.open(pdf_path)
        try:
            # Run document-level detectors (registered via @register_doc_detector)
            for detector in DOC_DETECTORS:
                try:
                    results = detector(doc)
                    for label, detail in results:
                        if label not in report["patterns"]:
                            report["patterns"].append(label)
                            report["cursed_content"].append((label, detail))
                except Exception as e:
                    logger.debug(f"Doc detector {detector.__name__} failed: {e}")

            # Run page-level detectors (registered via @register_page_detector)
            for page_num, page in enumerate(doc):
                for detector in PAGE_DETECTORS:
                    try:
                        results = detector(page)
                        for label, detail in results:
                            if label not in report["patterns"]:
                                report["patterns"].append(label)
                                report["cursed_content"].append((label, detail))
                    except Exception as e:
                        logger.debug(f"Page detector {detector.__name__} failed on page {page_num}: {e}")

                # Split table detection (special case: needs doc + page_num)
                if page_num < len(doc) - 1:
                    try:
                        split_results = detect_split_tables(doc, page_num)
                        for label, detail in split_results:
                            if label not in report["patterns"]:
                                report["patterns"].append(label)
                                report["cursed_content"].append((label, detail))
                    except Exception as e:
                        logger.debug(f"Split table detection failed on page {page_num}: {e}")
        finally:
            doc.close()
    except Exception as e:
        logger.warning(f"Advanced pattern detection failed: {e}")

    return report


def generate_fixture(report: dict, output_path: Path) -> Optional[Path]:
    """Generate reproduction fixture using fixture-tricky or create-figure."""
    logger.info(f"Generating fixture at {output_path}...")

    cursed_items = report.get("cursed_content", [])
    patterns = report.get("patterns", [])

    try:
        # Option 1: Use fixture-tricky gauntlet for comprehensive test
        if FIXTURE_TRICKY_DIR.exists():
            generate_py = FIXTURE_TRICKY_DIR / "generate.py"
            if generate_py.exists():
                # Select trick type based on patterns
                trick_type = "gauntlet"
                if "toc_noise" in patterns:
                    trick_type = "false-tables"
                elif "watermarks" in patterns:
                    trick_type = "malformed-tables"

                result = subprocess.run(
                    ["uv", "run", str(generate_py), trick_type, "--output", str(output_path)],
                    cwd=FIXTURE_TRICKY_DIR,
                    capture_output=True,
                    text=True,
                    check=False
                )

                if result.returncode == 0 and output_path.exists():
                    logger.info(f"Generated fixture via fixture-tricky: {output_path}")
                    return output_path

        # Option 2: Create custom fixture with cursed content
        if cursed_items:
            # Create PDF with extracted cursed content
            doc = fitz.open()
            page = doc.new_page()

            y_pos = 72
            page.insert_text(
                (72, y_pos),
                "REPRODUCTION FIXTURE - Extracted Failure Patterns",
                fontsize=14,
                fontname="helv"
            )
            y_pos += 30

            for label, content in cursed_items[:10]:  # Limit to 10 items
                page.insert_text(
                    (72, y_pos),
                    f"[{label.upper()}]",
                    fontsize=10,
                    fontname="helv",
                    color=(0.8, 0, 0)
                )
                y_pos += 15

                # Truncate long content
                display_content = content[:200] if len(content) > 200 else content
                for line in display_content.split("\n")[:5]:
                    page.insert_text((72, y_pos), line, fontsize=9, fontname="cour")
                    y_pos += 12

                y_pos += 10
                if y_pos > 700:
                    page = doc.new_page()
                    y_pos = 72

            doc.save(output_path)
            doc.close()
            logger.info(f"Generated custom fixture: {output_path}")
            return output_path

        # Option 3: Fallback - copy fixture-tricky gauntlet
        logger.warning("No specific fixture generated, using fallback")
        return None

    except Exception as e:
        logger.error(f"Failed to generate fixture: {e}")
        return None


def run_extractor_on_repro(pdf_path: Path) -> dict:
    """Verify fixture with current extractor."""
    logger.info(f"Running extractor on {pdf_path.name}...")

    if not EXTRACTOR_RUN or not EXTRACTOR_RUN.exists():
        return {"success": False, "error": "Extractor skill not found"}

    output_dir = SKILL_DIR / "debug_output"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(exist_ok=True)

    try:
        result = subprocess.run(
            [str(EXTRACTOR_RUN), str(pdf_path), "--out", str(output_dir), "--fast"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            cwd=str(EXTRACTOR_RUN.parent)
        )

        # Check for expected output
        summary_md = output_dir / "10_markdown_exporter" / "markdown_output" / "full_document.md"

        return {
            "success": summary_md.exists(),
            "doc_size": summary_md.stat().st_size if summary_md.exists() else 0,
            "exit_code": result.returncode,
            "stderr": result.stderr[:500] if result.stderr else None
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Extractor timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_to_inbox(message: str, msg_type: str = "info"):
    """Send message to extractor's agent inbox."""
    if not INBOX_TOOL or not INBOX_TOOL.exists():
        logger.warning("Agent inbox not available, skipping notification")
        return

    try:
        cmd = [str(INBOX_TOOL)]
        if INBOX_TOOL.name == "run.sh":
            cmd.extend(["send", "--to", "extractor", "--from", "debug-pdf", "--type", msg_type])
        else:
            cmd.extend(["send", "--to", "extractor", "--from", "debug-pdf", "--type", msg_type])
        cmd.append(message)

        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        logger.info("Sent notification to extractor inbox")
    except Exception as e:
        logger.error(f"Failed to send to inbox: {e}")


def memory_recall(query: str) -> list[dict]:
    """Recall relevant patterns/solutions from memory."""
    if not MEMORY_RUN or not MEMORY_RUN.exists():
        logger.debug("Memory skill not available")
        return []

    try:
        result = subprocess.run(
            [str(MEMORY_RUN), "recall", "--query", query, "--k", "5", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            cwd=str(MEMORY_RUN.parent)
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return []
    except Exception as e:
        logger.debug(f"Memory recall failed: {e}")
        return []


def memory_learn(pattern: str, details: str, url: str = None):
    """Store new pattern discovery to memory for future recall."""
    if not MEMORY_RUN or not MEMORY_RUN.exists():
        logger.debug("Memory skill not available")
        return

    lesson = f"PDF pattern detected: {pattern}. {details}"
    if url:
        lesson += f" (Source: {url})"

    try:
        result = subprocess.run(
            [str(MEMORY_RUN), "learn", "--lesson", lesson, "--scope", "pdf-patterns", "--tags", "debug-pdf,pdf,pattern-detection"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            cwd=str(MEMORY_RUN.parent)
        )
        if result.returncode == 0:
            logger.info(f"Stored pattern '{pattern}' to memory")
    except Exception as e:
        logger.debug(f"Memory learn failed: {e}")


def save_session(url: str, report: dict, fixture_path: Optional[Path]):
    """Save analysis session for later reference."""
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_data = {
        "id": session_id,
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "report": report,
        "fixture": str(fixture_path) if fixture_path else None,
        "patterns": report.get("patterns", [])
    }

    session_file = SESSIONS_DIR / f"{session_id}.json"
    session_file.write_text(json.dumps(session_data, indent=2))

    # Also save as last_analysis for quick reference
    (DATA_DIR / "last_analysis.json").write_text(json.dumps(session_data, indent=2))

    return session_id


# ============================================================================
# CLI COMMANDS
# ============================================================================

@app.command()
def main(
    url: str = typer.Option(..., "--url", help="URL of the failed PDF"),
    repro: bool = typer.Option(True, "--repro/--no-repro", help="Generate reproduction fixture"),
    send_inbox: bool = typer.Option(False, "--send-inbox", help="Send results to extractor inbox"),
):
    """Analyze a single failed PDF URL."""
    # Use unique temp file to avoid race conditions
    tmp_pdf = SKILL_DIR / f"temp_failed_{uuid4().hex}.pdf"

    # Check for Wayback URL pattern
    original_url = None
    if is_wayback_url(url):
        original_url = extract_original_url(url)
        logger.info(f"Detected Archive.org Wayback URL. Original: {original_url}")

    try:
        # URL validation happens in download_pdf
        download_success, download_patterns = download_pdf(url, tmp_pdf)

        if not download_success:
            # Even if download failed, we detected patterns
            if download_patterns:
                report = {
                    "pages": 0,
                    "is_scanned": False,
                    "patterns": download_patterns,
                    "cursed_content": [(p, f"Detected during download: {url}") for p in download_patterns],
                    "file_size_kb": 0
                }
                session_id = save_session(url, report, None)
                msg = f"DEBUG-PDF ANALYSIS [{session_id}]\n"
                msg += f"URL: {url}\n"
                msg += f"Download blocked - Patterns: {', '.join(download_patterns)}\n"
                print(msg)
                if send_inbox:
                    send_to_inbox(msg)
                raise typer.Exit(0)  # Not an error, we detected patterns
            logger.error("Failed to download PDF")
            raise typer.Exit(1)

        report = analyze_pdf(tmp_pdf)

        # Add download-detected patterns
        for p in download_patterns:
            if p not in report["patterns"]:
                report["patterns"].append(p)

        # Add archive_org_wrap pattern if detected
        if original_url:
            report["patterns"].append("archive_org_wrap")
            report["cursed_content"].append(("archive_org_wrap", f"Original URL: {original_url}"))
        logger.info(f"Analysis complete: {len(report.get('patterns', []))} patterns detected")

        fixture_path = None
        if repro:
            fixture_name = f"repro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            fixture_path = FIXTURES_DIR / fixture_name
            fixture_path = generate_fixture(report, fixture_path)

        session_id = save_session(url, report, fixture_path)

        # Build result message
        msg = f"DEBUG-PDF ANALYSIS [{session_id}]\n"
        msg += f"URL: {url}\n"
        msg += f"Pages: {report['pages']}\n"
        msg += f"Scanned: {report['is_scanned']}\n"
        msg += f"Patterns: {', '.join(report['patterns']) if report['patterns'] else 'None'}\n"

        if fixture_path:
            msg += f"\nFixture: {fixture_path.name}\n"

            if EXTRACTOR_RUN:
                verif = run_extractor_on_repro(fixture_path)
                msg += f"Verification: {'PASS' if verif['success'] else 'FAIL'}\n"
                if not verif['success'] and verif.get('error'):
                    msg += f"Error: {verif['error']}\n"

        print(msg)

        if send_inbox:
            send_to_inbox(msg)

    finally:
        if tmp_pdf.exists():
            tmp_pdf.unlink()


@app.command()
def batch(
    file: Path = typer.Option(..., "--file", help="File containing URLs (one per line)"),
    output: Path = typer.Option(None, "--output", help="Output JSON report path"),
    send_inbox: bool = typer.Option(False, "--send-inbox", help="Send summary to inbox"),
):
    """Analyze multiple failed PDF URLs from a file."""
    if not file.exists():
        logger.error(f"URL file not found: {file}")
        raise typer.Exit(1)

    # Validate output path parent if provided
    if output:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            if not os.access(str(output.parent), os.W_OK):
                raise PermissionError("No write permission")
        except Exception as e:
            logger.error(f"Cannot write to output directory {output.parent}: {e}")
            raise typer.Exit(1)

    urls = [line.strip() for line in file.read_text().splitlines() if line.strip() and not line.startswith("#")]
    logger.info(f"Processing {len(urls)} URLs...")

    results = []
    pattern_counts = {}

    for i, url in enumerate(urls, 1):
        logger.info(f"[{i}/{len(urls)}] {url}")
        # Use unique temp file to avoid race conditions
        tmp_pdf = SKILL_DIR / f"temp_{i}_{uuid4().hex}.pdf"

        try:
            # Validate URL before attempting download
            if not is_valid_url(url):
                results.append({
                    "url": url,
                    "patterns": ["invalid_url"],
                    "success": False
                })
                continue

            download_success, download_patterns = download_pdf(url, tmp_pdf)

            if download_success:
                report = analyze_pdf(tmp_pdf)
                # Add download-detected patterns
                for p in download_patterns:
                    if p not in report.get("patterns", []):
                        report["patterns"].append(p)
                fixture_name = f"batch_{i}_{datetime.now().strftime('%H%M%S')}.pdf"
                fixture_path = FIXTURES_DIR / fixture_name
                fixture_path = generate_fixture(report, fixture_path)

                results.append({
                    "url": url,
                    "patterns": report.get("patterns", []),
                    "pages": report.get("pages", 0),
                    "fixture": str(fixture_path) if fixture_path else None,
                    "success": True
                })

                for p in report.get("patterns", []):
                    pattern_counts[p] = pattern_counts.get(p, 0) + 1
            else:
                # Download failed but may have detected patterns
                results.append({
                    "url": url,
                    "patterns": download_patterns if download_patterns else ["download_failed"],
                    "success": False
                })
                for p in download_patterns:
                    pattern_counts[p] = pattern_counts.get(p, 0) + 1
        except Exception as e:
            results.append({
                "url": url,
                "patterns": ["analysis_error"],
                "error": str(e),
                "success": False
            })
        finally:
            if tmp_pdf.exists():
                tmp_pdf.unlink()

    # Generate report
    batch_report = {
        "timestamp": datetime.now().isoformat(),
        "total": len(urls),
        "success": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "pattern_counts": pattern_counts,
        "results": results
    }

    if output:
        output.write_text(json.dumps(batch_report, indent=2))
        logger.info(f"Report saved to {output}")

    # Print summary
    print(f"\n=== BATCH ANALYSIS COMPLETE ===")
    print(f"Total: {batch_report['total']}")
    print(f"Success: {batch_report['success']}")
    print(f"Failed: {batch_report['failed']}")
    print(f"\nPattern Distribution:")
    for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"  {pattern}: {count}")

    if send_inbox:
        msg = f"BATCH DEBUG-PDF: {batch_report['total']} URLs analyzed\n"
        msg += f"Patterns: {', '.join(f'{k}({v})' for k,v in pattern_counts.items())}"
        send_to_inbox(msg)


@app.command()
def combine(
    output: Path = typer.Option("combined_fixtures.pdf", "--output", help="Output combined PDF path"),
    max_pages: int = typer.Option(20, "--max-pages", help="Maximum pages in combined PDF"),
):
    """Combine all generated fixtures into one stress test PDF."""
    # Validate output path
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        if not os.access(str(output.parent), os.W_OK):
            raise PermissionError("No write permission")
    except Exception as e:
        logger.error(f"Cannot write to output directory {output.parent}: {e}")
        raise typer.Exit(1)

    fixtures = list(FIXTURES_DIR.glob("*.pdf"))

    if not fixtures:
        logger.warning("No fixtures found to combine")
        raise typer.Exit(1)

    logger.info(f"Combining {len(fixtures)} fixtures (max {max_pages} pages)...")

    combined = fitz.open()
    total_pages = 0
    included_fixtures = []

    for fixture_path in fixtures:
        if total_pages >= max_pages:
            break

        try:
            src = fitz.open(fixture_path)
            pages_to_add = min(len(src), max_pages - total_pages)
            combined.insert_pdf(src, to_page=pages_to_add - 1)
            total_pages += pages_to_add
            included_fixtures.append(fixture_path.name)
            src.close()
        except Exception as e:
            logger.warning(f"Could not include {fixture_path.name}: {e}")

    if total_pages > 0:
        # Add index page at the beginning
        index_page = combined.new_page(pno=0)
        y_pos = 72
        index_page.insert_text(
            (72, y_pos),
            f"COMBINED STRESS TEST FIXTURE",
            fontsize=16,
            fontname="helv"
        )
        y_pos += 30
        index_page.insert_text(
            (72, y_pos),
            f"Generated: {datetime.now().isoformat()}",
            fontsize=10,
            fontname="helv"
        )
        y_pos += 20
        index_page.insert_text(
            (72, y_pos),
            f"Total Pages: {total_pages + 1}",
            fontsize=10,
            fontname="helv"
        )
        y_pos += 30
        index_page.insert_text(
            (72, y_pos),
            "Included Fixtures:",
            fontsize=12,
            fontname="helv"
        )
        y_pos += 20

        for name in included_fixtures:
            index_page.insert_text((90, y_pos), f"- {name}", fontsize=9, fontname="cour")
            y_pos += 12
            if y_pos > 750:
                break

        combined.save(output)
        combined.close()

        print(f"Combined fixture saved: {output}")
        print(f"Total pages: {total_pages + 1} (including index)")
        print(f"Fixtures included: {len(included_fixtures)}")
    else:
        logger.error("No pages could be combined")
        raise typer.Exit(1)


@app.command()
def recall(
    query: str = typer.Argument("PDF extraction failure patterns"),
):
    """Recall known patterns from memory."""
    results = memory_recall(query)
    if results:
        print(f"Found {len(results)} relevant memories:\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. {r.get('title', 'Untitled')}")
            print(f"   {r.get('content', '')[:200]}...")
            print()
    else:
        print("No relevant patterns found in memory.")
        print("Run analysis on PDFs to build up pattern knowledge.")


@app.command()
def learn(
    pattern: str = typer.Option(..., "--pattern", help="Pattern name to store"),
    details: str = typer.Option(..., "--details", help="Pattern details/description"),
    url: str = typer.Option(None, "--url", help="Source URL if applicable"),
):
    """Manually store a pattern to memory."""
    memory_learn(pattern, details, url)
    print(f"Stored pattern '{pattern}' to memory.")


@app.command()
def detectors():
    """List all registered detection functions."""
    print("=== Document-Level Detectors ===")
    for i, d in enumerate(DOC_DETECTORS, 1):
        print(f"  {i}. {d.__name__}")
        if d.__doc__:
            print(f"     {d.__doc__.split('.')[0]}.")

    print("\n=== Page-Level Detectors ===")
    for i, d in enumerate(PAGE_DETECTORS, 1):
        print(f"  {i}. {d.__name__}")
        if d.__doc__:
            print(f"     {d.__doc__.split('.')[0]}.")

    print(f"\nTotal: {len(DOC_DETECTORS)} doc-level, {len(PAGE_DETECTORS)} page-level")
    print("\nTo add a new detector:")
    print("  1. Create function: def detect_my_pattern(page_or_doc) -> list[tuple[str, str]]")
    print("  2. Add decorator: @register_page_detector or @register_doc_detector")
    print("  3. Add pattern description to PATTERNS dict")


if __name__ == "__main__":
    app()
