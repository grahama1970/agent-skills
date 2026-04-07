"""PDF triage, quarantine checks, and document slug generation.

Provides pre-extraction validation (corruption, encryption, garbled text,
suspicious executable content) and hard-tail quarantine via /memory recall.
Also provides slug generation for mapping document paths to run directories.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from loguru import logger

# RULE: NEVER use get_db() directly. Only MemoryClient.recall() for queries.
# recall() provides BM25 + semantic + multi-hop graph traversal via /taxonomy.
try:
    from graph_memory.api import MemoryClient
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False

# Formats the extractor pipeline can process (provider registry).
EXTRACTABLE_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".xml",
    ".md", ".markdown", ".rst", ".epub",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp",
}

# Code files — routed to /treesitter, not the extractor.
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rs", ".rb", ".sh",
}

TREESITTER_DIR = Path(__file__).resolve().parent.parent.parent / "treesitter"

GENERATED_DIR_NAMES = {
    "extracted_runs",
    "debug_output",
    "reports",
    "results",
}
GENERATED_DIR_PREFIXES = (
    "results_iteration_",
    "results_iter",
)

# Module-level cache: PDF hashes already confirmed as hard_tail.
# Avoids redundant /memory queries in hot discovery loop.
_hard_tail_cache: set[str] = set()


def _check_hard_tail_quarantine(pdf_path: Path) -> bool:
    """Check if a PDF is quarantined as hard_tail in /memory.

    Returns True if the PDF should be skipped (quarantined).
    Gracefully returns False if /memory is unavailable.
    """
    if not _HAS_MEMORY:
        return False

    pdf_hash = hashlib.md5(
        str(pdf_path.resolve()).encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    short_hash = pdf_hash[:8]

    # Fast path: already checked this session
    if short_hash in _hard_tail_cache:
        return True

    try:
        client = MemoryClient(scope="extractor")
        result = client.recall(f"hard_tail {short_hash}", k=3)
        if not result.get("found"):
            return False
        # Check if any returned item actually references this PDF's hash
        for item in result.get("items", []):
            text = f"{item.get('problem', '')} {item.get('solution', '')} {' '.join(item.get('tags', []))}"
            if "hard_tail" in text and short_hash in text:
                _hard_tail_cache.add(short_hash)
                return True
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    return False


def _preflight_triage(pdf_path: Path) -> dict | None:
    """Fast pre-extraction triage. Returns failure dict or None if clean.

    Checks for corruption, encryption, zero pages, garbled encoding,
    and suspicious executable content (JavaScript/Launch actions).
    Runs in < 50ms for typical PDFs.
    """
    import fitz

    # 1. Can we open it at all?
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        return {"reason": "corrupt_unreadable", "detail": str(e)[:500]}

    try:
        # 2. Encrypted?
        if doc.is_encrypted:
            return {
                "reason": "encrypted_no_password",
                "detail": f"encryption={doc.is_encrypted}",
            }

        # 3. Zero pages?
        if doc.page_count == 0:
            return {"reason": "zero_pages", "detail": "empty document"}

        # 4. Garbled text? (sample first 3 pages)
        sample_text = ""
        for i in range(min(3, doc.page_count)):
            sample_text += doc[i].get_text()
        if len(sample_text) > 20:
            control_chars = sum(
                1 for c in sample_text if ord(c) < 32 and c not in "\n\r\t"
            )
            ratio = control_chars / len(sample_text)
            if ratio > 0.30:
                return {
                    "reason": "garbled_encoding",
                    "detail": f"control_char_ratio={ratio:.2f}",
                }

        # 5. Suspicious executable content? (JavaScript, Launch actions)
        suspicious_signals = []
        for i in range(min(5, doc.page_count)):
            page = doc[i]
            for annot in page.annots() or []:
                annot_name = annot.info.get("name", "").lower()
                if annot_name in ("javascript", "launch"):
                    suspicious_signals.append(f"page_{i}_{annot_name}")

        # Check document-level JavaScript catalog
        try:
            catalog = doc.pdf_catalog()
            if catalog:
                xref_text = doc.xref_object(catalog)
                # Only flag true executable content — /OpenAction and /AA are
                # benign (page navigation, bookmark zoom). /JavaScript, /JS,
                # and /Launch are the real threats.
                for keyword in ["/JavaScript", "/JS ", "/Launch"]:
                    if keyword in xref_text:
                        suspicious_signals.append(f"catalog_{keyword.strip('/')}")
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

        if suspicious_signals:
            return {
                "reason": "suspicious_executable",
                "detail": ",".join(suspicious_signals),
                "security": True,
            }

        return None  # Clean — proceed with extraction
    finally:
        doc.close()


def _slug_for_doc(doc_path: Path) -> str:
    """Generate a filesystem-safe slug for a document path."""
    digest = hashlib.md5(
        str(doc_path.resolve()).encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:10]
    stem = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in doc_path.stem)
    return f"{stem}_{digest}"


# Backward compatibility alias
_slug_for_pdf = _slug_for_doc
