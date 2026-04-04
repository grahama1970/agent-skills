"""
Core operations for debug-pdf: download, analyze, fixture generation,
extractor invocation, memory integration, and session management.
"""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from uuid import uuid4

import fitz
import httpx
from loguru import logger

from dp_config import (
    SKILL_DIR, PI_SKILLS_DIR, DATA_DIR, SESSIONS_DIR, FIXTURES_DIR,
    FETCHER_RUN, FIXTURE_TRICKY_DIR, FIGURE_RUN,
    find_extractor_run, find_memory_run, find_inbox_tool,
    TASK_MONITOR_AVAILABLE, DebugPdfTaskClient,
)
from dp_registry import (
    PAGE_DETECTORS, DOC_DETECTORS, PATTERNS,
    is_wayback_url, extract_original_url, is_valid_url,
    WAYBACK_PATTERN,
)

# Import all detector modules to register their functions via decorators
import dp_detectors_layout  # noqa: F401
import dp_detectors_domain  # noqa: F401
import dp_detectors_quality  # noqa: F401


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
                cwd=str(FETCHER_RUN.parent),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
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
        except Exception as e:
            logger.debug("doc failed: {}", e)

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
                    check=False,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
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
            cwd=str(EXTRACTOR_RUN.parent),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        # Check for expected output
        summary_md = output_dir / "10_markdown_exporter" / "markdown_output" / "full_document.md"

        return {
            "success": summary_md.exists(),
            "doc_size": summary_md.stat().st_size if summary_md.exists() else 0,
            "exit_code": result.returncode,
            "stderr": (result.stderr or "")[:500] or None
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

        subprocess.run(cmd, check=True, capture_output=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        logger.info("Sent notification to extractor inbox")
    except Exception as e:
        logger.error(f"Failed to send to inbox: {e}")


def memory_recall(query: str) -> list[dict]:
    """Recall relevant patterns/solutions from memory via Unix socket."""
    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            resp = client.post("/recall", json={"q": query, "k": 5})
            if resp.status_code == 200:
                return resp.json().get("items", [])
        return []
    except Exception as e:
        logger.debug(f"Memory recall failed: {e}")
        return []


def memory_learn(pattern: str, details: str, url: str = None):
    """Store new pattern discovery to memory via Unix socket."""
    lesson = f"PDF pattern detected: {pattern}. {details}"
    if url:
        lesson += f" (Source: {url})"

    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            resp = client.post("/learn", json={
                "problem": lesson,
                "solution": lesson,
                "scope": "pdf-patterns",
                "tags": ["debug-pdf", "pdf", "pattern-detection"],
            })
            if resp.status_code == 200:
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



