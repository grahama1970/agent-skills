"""
Detector function registry (plug-and-play pattern) and pattern definitions.

To add a new detector:
1. Create a function: def detect_my_pattern(page_or_doc) -> list[tuple[str, str]]
2. Register it: @register_page_detector or @register_doc_detector
3. Add pattern description to PATTERNS dict
"""
import re
from urllib.parse import urlparse


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

    # Extraction quality patterns (discovered during batch hardening)
    "symbol_fonts": "PUA characters from Microsoft Symbol/Wingdings fonts (U+F000-U+F8FF)",
    "section_under_segmentation": "Too few sections relative to page count (<1 per 20 pages)",
    "toc_leaders_in_headers": "Dotted leaders captured in section titles (TOC bleed)",
    "partial_sentence_headers": "Sentence fragments detected as section headers",
    "math_symbols_lost": "Mathematical symbols becoming '?' in extraction",
    "low_block_density": "Suspiciously few text blocks per page (<0.5 blocks/page)",
    "classifier_mismatch": "ML classifier disagrees with heuristic preset mapping",
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


