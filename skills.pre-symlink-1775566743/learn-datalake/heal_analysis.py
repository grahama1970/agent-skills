"""VLM-powered failure analysis for PDF extraction quality issues."""

from __future__ import annotations

import base64
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from loguru import logger

SCILLM_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_AUTH = {"Authorization": "Bearer sk-dev-proxy-123"}
SCREENSHOT_DIR = Path("/tmp/heal-failures/screenshots")


@dataclass
class FailureAnalysis:
    """Result of VLM-powered failure analysis for a single manifest entry."""

    toc_screenshots: list[Path] = field(default_factory=list)
    problem_screenshots: list[Path] = field(default_factory=list)
    s00_estimated_sections: int = 0
    s04_actual_sections: int = 0
    vlm_toc_analysis: str = ""
    vlm_section_count: int = 0
    font_analysis: dict = field(default_factory=dict)
    misclassified_fonts: list[dict] = field(default_factory=list)
    layout_type: str = "unknown"
    diagnosis: str = ""
    has_toc: bool = True
    needs_nico_review: bool = False
    toc_coverage: str = "unknown"  # "full", "partial", "none"


def _render_pages(pdf_path: str, page_indices: list[int], label: str) -> list[Path]:
    """Render specific PDF pages to PNG using pdf_oxide.render_page()."""
    try:
        from pdf_oxide import PdfDocument
    except ImportError:
        logger.error("pdf_oxide not importable — install with: maturin develop")
        return []

    output_dir = SCREENSHOT_DIR / Path(pdf_path).stem
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots: list[Path] = []

    try:
        doc = PdfDocument(pdf_path)
        total_pages = doc.page_count()
    except Exception as e:
        logger.error(f"Failed to open PDF {pdf_path}: {e}")
        return []

    for idx in page_indices:
        if idx >= total_pages:
            continue
        try:
            png_bytes = doc.render_page(idx, dpi=150)
            out_path = output_dir / f"{label}_page{idx}.png"
            out_path.write_bytes(png_bytes)
            screenshots.append(out_path)
            logger.debug(f"  Rendered {label} page {idx} -> {out_path}")
        except Exception as e:
            logger.warning(f"  Failed to render page {idx}: {e}")

    return screenshots


def _get_font_distribution(pdf_path: str, max_pages: int = 20) -> dict:
    """Extract font size distribution across pages using pdf_oxide spans."""
    try:
        from pdf_oxide import PdfDocument
    except ImportError:
        return {}

    try:
        doc = PdfDocument(pdf_path)
        total_pages = doc.page_count()
    except Exception as e:
        logger.warning(f"Failed to open PDF for font analysis: {e}")
        return {}

    font_size_counts: Counter = Counter()
    font_name_counts: Counter = Counter()
    bold_sizes: set[float] = set()
    samples_by_size: dict[float, list[str]] = {}

    pages_to_scan = min(total_pages, max_pages)
    for page_idx in range(pages_to_scan):
        try:
            spans = doc.extract_spans(page_idx)
        except Exception:
            continue
        for span in spans:
            size = round(span.font_size, 1)
            text = span.text.strip()
            if not text:
                continue
            font_size_counts[size] += len(text)
            font_name_counts[span.font_name] += len(text)
            if span.is_bold:
                bold_sizes.add(size)
            if size not in samples_by_size:
                samples_by_size[size] = []
            if len(samples_by_size[size]) < 3:
                samples_by_size[size].append(text[:80])

    if not font_size_counts:
        return {}

    # Body font = most frequent size by character count
    body_size = font_size_counts.most_common(1)[0][0]

    return {
        "body_font_size": body_size,
        "size_distribution": dict(font_size_counts.most_common(15)),
        "font_names": dict(font_name_counts.most_common(10)),
        "bold_sizes": sorted(bold_sizes),
        "samples_by_size": {k: v for k, v in sorted(samples_by_size.items(), reverse=True)},
        "pages_scanned": pages_to_scan,
    }


def _find_high_section_density_pages(pdf_path: str, top_n: int = 2) -> list[int]:
    """Find pages with the most header-like blocks (high section density)."""
    try:
        from pdf_oxide import PdfDocument
    except ImportError:
        return []

    try:
        doc = PdfDocument(pdf_path)
        total_pages = doc.page_count()
    except Exception:
        return []

    page_header_counts: list[tuple[int, int]] = []
    for page_idx in range(min(total_pages, 50)):
        try:
            blocks = doc.classify_blocks(page_idx)
            header_count = sum(
                1 for b in blocks
                if isinstance(b, dict) and b.get("block_type") in ("SectionHeader", "Heading")
            )
            page_header_counts.append((page_idx, header_count))
        except Exception:
            continue

    # Sort by header count descending, skip first 3 pages (TOC already captured)
    page_header_counts = [(p, c) for p, c in page_header_counts if p >= 3 and c > 0]
    page_header_counts.sort(key=lambda x: -x[1])
    return [p for p, _ in page_header_counts[:top_n]]


def _identify_misclassified_fonts(font_analysis: dict, s00_body_size: float) -> list[dict]:
    """Identify fonts that S00 likely confused with headers."""
    if not font_analysis or not font_analysis.get("size_distribution"):
        return []

    body_size = font_analysis["body_font_size"]
    misclassified = []

    for size, char_count in font_analysis["size_distribution"].items():
        size_f = float(size)
        # Fonts larger than body that have high char count = likely not headers
        # (e.g., large code blocks, title fonts used repeatedly)
        if size_f > body_size and char_count > 500:
            samples = font_analysis.get("samples_by_size", {}).get(size, [])
            misclassified.append({
                "font_size": size_f,
                "char_count": char_count,
                "reason": "high char count for non-body size — likely code, captions, or repeated decorative text",
                "samples": samples,
            })
        # Fonts S00 thought were body but are actually smaller (footnotes, captions)
        if s00_body_size and abs(size_f - s00_body_size) < 0.5 and size_f != body_size:
            samples = font_analysis.get("samples_by_size", {}).get(size, [])
            misclassified.append({
                "font_size": size_f,
                "char_count": char_count,
                "reason": f"S00 used body_size={s00_body_size} but actual body is {body_size} — font confusion",
                "samples": samples,
            })

    return misclassified


def _detect_layout_type(pdf_path: str) -> str:
    """Detect single-column, multi-column, or mixed layout."""
    try:
        from pdf_oxide import PdfDocument
    except ImportError:
        return "unknown"

    try:
        doc = PdfDocument(pdf_path)
        total_pages = doc.page_count()
    except Exception:
        return "unknown"

    multi_col_pages = 0
    single_col_pages = 0
    pages_to_check = min(total_pages, 10)

    for page_idx in range(pages_to_check):
        try:
            spans = doc.extract_spans(page_idx)
        except Exception:
            continue

        if not spans:
            continue

        # Collect unique x-positions of span starts (left edges)
        x_positions = [span.bbox[0] for span in spans if span.text.strip()]
        if len(x_positions) < 5:
            continue

        # Cluster x-positions: if there are 2+ distinct left-margin clusters, it is multi-column
        x_sorted = sorted(set(round(x, 0) for x in x_positions))
        # Group x-positions within 30pt of each other
        clusters: list[float] = []
        for x in x_sorted:
            if not clusters or abs(x - clusters[-1]) > 30:
                clusters.append(x)

        if len(clusters) >= 2:
            multi_col_pages += 1
        else:
            single_col_pages += 1

    if multi_col_pages == 0:
        return "single-column"
    elif single_col_pages == 0:
        return "multi-column"
    else:
        return "mixed"


def _vlm_analyze_toc(screenshots: list[Path]) -> tuple[str, int]:
    """Send TOC screenshots to VLM and ask for section analysis.

    Returns (vlm_analysis_text, section_count).
    """
    if not screenshots:
        return ("No TOC screenshots available", 0)

    # Build multimodal message with all TOC screenshots
    content_parts: list[dict] = [
        {
            "type": "text",
            "text": (
                "These are screenshots of the first pages of a PDF document. "
                "They likely contain a Table of Contents (TOC) or introductory material.\n\n"
                "Please analyze:\n"
                "1. Does this document have a visible Table of Contents? If yes, list every section "
                "title and its page number exactly as shown.\n"
                "2. How many top-level sections does the TOC show?\n"
                "3. Are there any sub-sections? How many total entries?\n"
                "4. Note anything unusual about the formatting (multi-column TOC, very long TOC, "
                "numbered lists that look like sections but aren't, code listings, etc.)\n\n"
                "End your response with a line: SECTION_COUNT: <number>"
            ),
        }
    ]

    for screenshot in screenshots:
        try:
            img_b64 = base64.b64encode(screenshot.read_bytes()).decode()
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"},
            })
        except Exception as e:
            logger.warning(f"Failed to encode screenshot {screenshot}: {e}")

    try:
        resp = httpx.post(
            SCILLM_URL,
            headers=SCILLM_AUTH,
            json={
                "model": "vlm",
                "messages": [{"role": "user", "content": content_parts}],
                "max_tokens": 2048,
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        analysis = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"VLM call failed: {e}")
        return (f"VLM call failed: {e}", 0)

    # Extract section count from the response
    section_count = 0
    match = re.search(r"SECTION_COUNT:\s*(\d+)", analysis)
    if match:
        section_count = int(match.group(1))

    return (analysis, section_count)


def _build_diagnosis(
    entry: dict,
    vlm_section_count: int,
    vlm_analysis: str,
    font_analysis: dict,
    misclassified_fonts: list[dict],
    layout_type: str,
) -> str:
    """Build a human-readable diagnosis of WHY the S00 estimate was wrong."""
    s00 = entry.get("s00_estimated_sections", 0)
    s04 = entry.get("s04_actual_sections", 0)
    label = entry.get("s00_s04_label", "UNKNOWN")
    s00_regex = entry.get("s00_estimated_regex", 0)
    s00_font = entry.get("s00_estimated_font", 0)
    s00_body = entry.get("s00_body_font_size", 0)
    actual_body = font_analysis.get("body_font_size", 0)
    filename = entry.get("filename", "unknown")

    parts = [
        f"FILE: {filename}",
        f"S00 estimated {s00} sections (regex={s00_regex}, font={s00_font}), S04 found {s04}.",
        f"Label: {label} (ratio={entry.get('s00_s04_ratio', '?')})",
        f"Layout: {layout_type}",
    ]

    # Font mismatch
    if s00_body and actual_body and abs(s00_body - actual_body) > 0.5:
        parts.append(
            f"FONT MISMATCH: S00 assumed body={s00_body}pt but actual body={actual_body}pt. "
            f"This means S00 classified {actual_body}pt text as non-body, inflating header count."
        )

    # VLM vs S00 comparison
    if vlm_section_count > 0:
        parts.append(f"VLM saw {vlm_section_count} sections in the TOC.")
        if s00 > vlm_section_count * 2:
            parts.append(
                f"OVERESTIMATE: S00 estimated {s00} but TOC only shows ~{vlm_section_count}. "
                f"S00 likely confused non-header elements with section headers."
            )
        elif s00 < vlm_section_count * 0.5:
            parts.append(
                f"UNDERESTIMATE: S00 estimated {s00} but TOC shows ~{vlm_section_count}. "
                f"S00 likely missed headers due to unusual formatting."
            )
        else:
            parts.append(
                f"S00 estimate ({s00}) roughly matches VLM TOC count ({vlm_section_count})."
            )

    # Misclassified font analysis
    if misclassified_fonts:
        parts.append(f"MISCLASSIFIED FONTS ({len(misclassified_fonts)} suspicious sizes):")
        for mf in misclassified_fonts[:3]:
            parts.append(
                f"  - {mf['font_size']}pt ({mf['char_count']} chars): {mf['reason']}"
            )
            if mf.get("samples"):
                parts.append(f"    Samples: {mf['samples'][0][:60]}")

    # Multi-column issues
    if layout_type == "multi-column" and label == "S00_OVERESTIMATE":
        parts.append(
            "MULTI-COLUMN: Document uses multi-column layout. S00 may have double-counted "
            "headers that appear in parallel columns."
        )

    # S00 font vs regex breakdown
    if s00_font > s00_regex * 2 and s00_font > s04 * 1.5:
        parts.append(
            f"FONT-BASED INFLATION: S00 font estimate ({s00_font}) >> regex estimate ({s00_regex}). "
            f"Font-based detection likely picked up styled text that isn't section headers."
        )
    elif s00_regex > s00_font * 2 and s00_regex > s04 * 1.5:
        parts.append(
            f"REGEX-BASED INFLATION: S00 regex estimate ({s00_regex}) >> font estimate ({s00_font}). "
            f"Regex patterns matched non-header numbered content (lists, references, etc.)."
        )

    return "\n".join(parts)


def analyze_failure(entry: dict) -> FailureAnalysis:
    """Analyze a single manifest failure entry using VLM screenshots and font analysis.

    Steps:
    1. Render TOC pages (first 3 pages) as PNG screenshots
    2. Find and render high-section-density pages
    3. Extract font distribution via pdf_oxide spans
    4. Send TOC screenshots to VLM for visual section counting
    5. Compare VLM count against S00/S04 numbers
    6. Build diagnosis explaining the mismatch
    """
    pdf_path = entry.get("original_path", "")
    filename = entry.get("filename") or Path(pdf_path).name
    s00 = entry.get("s00_estimated_sections", 0)
    s04 = entry.get("s04_actual_sections", 0)

    if not pdf_path or not Path(pdf_path).exists():
        logger.error(f"PDF not found: {pdf_path}")
        return FailureAnalysis(
            s00_estimated_sections=s00,
            s04_actual_sections=s04,
            diagnosis=f"PDF file not found at {pdf_path}",
        )

    logger.info(f"Analyzing failure: {filename} (S00={s00}, S04={s04})")

    # Step 1: Screenshot TOC pages (first 3)
    logger.info("  Rendering TOC pages (0-2)...")
    toc_screenshots = _render_pages(pdf_path, [0, 1, 2], "toc")

    # Step 2: Find and screenshot high-section-density pages
    logger.info("  Finding high-section-density pages...")
    dense_pages = _find_high_section_density_pages(pdf_path)
    problem_screenshots = _render_pages(pdf_path, dense_pages, "dense") if dense_pages else []

    # Step 3: Font distribution analysis
    logger.info("  Analyzing font distribution...")
    font_analysis = _get_font_distribution(pdf_path)

    # Step 4: Identify misclassified fonts
    s00_body = entry.get("s00_body_font_size", 0)
    misclassified = _identify_misclassified_fonts(font_analysis, s00_body)

    # Step 5: Detect layout type
    logger.info("  Detecting layout type...")
    layout_type = _detect_layout_type(pdf_path)

    # Step 6: VLM analysis of TOC screenshots
    logger.info("  Sending TOC screenshots to VLM for analysis...")
    vlm_analysis, vlm_section_count = _vlm_analyze_toc(toc_screenshots)

    # Step 6b: Determine TOC presence from VLM response
    vlm_lower = vlm_analysis.lower()
    no_toc_signals = ["no table of contents", "no toc", "does not contain", "not visible", "no sections listed"]
    has_toc = not any(sig in vlm_lower for sig in no_toc_signals) and vlm_section_count > 0
    if has_toc and vlm_section_count < s04 * 0.5:
        toc_coverage = "partial"
    elif has_toc:
        toc_coverage = "full"
    else:
        toc_coverage = "none"
    needs_nico = not has_toc or toc_coverage == "partial"

    # Step 7: Build diagnosis
    diagnosis = _build_diagnosis(
        entry, vlm_section_count, vlm_analysis,
        font_analysis, misclassified, layout_type,
    )
    if not has_toc:
        diagnosis += "\n\nNO TOC DETECTED — requires Nico review. Font analysis suggests "
        diagnosis += f"{len(misclassified)} misclassified font sizes." if misclassified else "no obvious font issues."

    result = FailureAnalysis(
        toc_screenshots=toc_screenshots,
        problem_screenshots=problem_screenshots,
        s00_estimated_sections=s00,
        s04_actual_sections=s04,
        vlm_toc_analysis=vlm_analysis,
        vlm_section_count=vlm_section_count,
        font_analysis=font_analysis,
        misclassified_fonts=misclassified,
        layout_type=layout_type,
        diagnosis=diagnosis,
        has_toc=has_toc,
        needs_nico_review=needs_nico,
        toc_coverage=toc_coverage,
    )

    logger.success(f"  Analysis complete for {filename}")
    logger.info(f"  Diagnosis:\n{diagnosis}")
    return result
