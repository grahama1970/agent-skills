"""
Defense and aerospace domain-specific pattern detectors.

Detectors: ITAR/export control, military spec, aerospace spec,
technical drawing, classification marking, CAGE/DFAR references.
"""
import re

import fitz

from dp_registry import register_page_detector


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



