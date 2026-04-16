"""PDF discovery and blacklist management for learn-datalake.

Purpose:
- Discover source documents not yet extracted into /memory,
  manage extraction blacklist, filter by extractability model predictions.

Inputs:
- Corpus root directory, blacklist state files.

Outputs:
- Lists of pending document paths, blacklist updates.

Three-layer "already done" check (fast → slow):
1. Slug match against extracted_runs/ directories (filesystem, ~1s)
2. /memory query for ingested doc hashes (ArangoDB, ~2s)
3. Pipeline output directory filter (skip results/, completed/, etc.)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from loguru import logger

from config import (
    DEFERRED_REVIEW_PATH,
    EXTRACTABILITY_LOW_CONFIDENCE_LOG,
    EXTRACTABILITY_THRESHOLD,
    FAILED_PDF_BLACKLIST,
    QUESTION_BOOK_PATH,
    REVIEW_PDF_EXTRACTED_RUNS_HDD,
    REVIEW_PDF_EXTRACTED_RUNS_NVME,
    STATE_DIR,
)

INTERVIEW_SESSIONS_DIR = STATE_DIR / "interview_sessions"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_blacklist() -> set[str]:
    """Load the set of blacklisted PDF stems (corrupt/unextractable)."""
    if not FAILED_PDF_BLACKLIST.exists():
        return set()
    stems: set[str] = set()
    for line in FAILED_PDF_BLACKLIST.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            stems.add(entry["stem"])
        except (json.JSONDecodeError, KeyError):
            logger.debug(f"blacklist_parse_skip line={line[:80]}")
    return stems


def blacklist_pdf(pdf_path: Path, reason: str = "extract_failed") -> None:
    """Add a PDF to the permanent blacklist so it's never retried."""
    FAILED_PDF_BLACKLIST.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "stem": pdf_path.stem,
        "path": str(pdf_path),
        "reason": reason,
        "timestamp": _utc_now(),
    }
    with open(FAILED_PDF_BLACKLIST, "a") as f:
        f.write(json.dumps(entry) + "\n")


def blacklist_failed_from_output(stdout: str) -> int:
    """Parse worker output for extract_failed lines and blacklist those PDFs.

    Returns the number of newly blacklisted PDFs.
    """
    existing = load_blacklist()
    count = 0
    for line in stdout.split("\n"):
        if "status=extract_failed" not in line:
            continue
        # discovery.py prints doc=<path>, match both doc= and pdf= for compat
        pdf_str = ""
        for prefix in ("doc=", "pdf="):
            idx = line.find(prefix)
            if idx >= 0:
                pdf_str = line[idx + len(prefix):].strip()
                break
        if not pdf_str:
            continue
        pdf_path = Path(pdf_str)
        if pdf_path.stem not in existing:
            # Classify reason from stderr content in the log line
            is_html_block = "not a valid PDF" in line or "HTML block" in line
            if is_html_block:
                # Defer HTML block pages to /interview — human may have
                # credentials or alternative download sources
                defer_pdf(pdf_path, reason="html_block_page",
                          detail="File has HTML content instead of PDF. "
                                 "Likely paywalled or access-denied download.")
            else:
                blacklist_pdf(pdf_path, reason="extract_failed")
            existing.add(pdf_path.stem)
            count += 1
    return count


def load_deferred() -> set[str]:
    """Load the set of PDF stems deferred for human review via /interview.

    Deferred items are NOT retried until the human resolves them.
    This prevents error cascades from repeated failed retries when
    /review-pdf or /pdf-lab is blocked on a document.
    """
    if not DEFERRED_REVIEW_PATH.exists():
        return set()
    stems: set[str] = set()
    for line in DEFERRED_REVIEW_PATH.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            stems.add(entry["stem"])
        except (json.JSONDecodeError, KeyError):
            pass
    return stems


def defer_pdf(
    pdf_path: Path,
    reason: str,
    detail: str = "",
    questions: list[dict] | None = None,
    screenshot_paths: list[str] | None = None,
    metadata: dict | None = None,
) -> None:
    """Park a PDF for human review — not retried until /interview resolves it.

    Args:
        pdf_path: Path to the PDF file.
        reason: Why this PDF was deferred (e.g. "ambiguous_merge", "low_accuracy",
                "password_required", "corrupt", "html_block_page").
        detail: Human-readable description.
        questions: Optional /interview Question dicts for structured review.
        screenshot_paths: Optional paths to evidence screenshots.
        metadata: Optional structured metadata (e.g. MergeEvidence dict).
    """
    DEFERRED_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry: dict = {
        "stem": pdf_path.stem,
        "path": str(pdf_path),
        "reason": reason,
        "detail": detail,
        "timestamp": _utc_now(),
    }
    if questions:
        entry["questions"] = questions
    if screenshot_paths:
        entry["screenshot_paths"] = screenshot_paths
    if metadata:
        entry["metadata"] = metadata
    with open(DEFERRED_REVIEW_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_deferred_with_questions() -> list[dict]:
    """Load deferred entries that have /interview questions attached.

    Returns a list of deferred entry dicts, each containing at minimum:
    stem, path, reason, questions, and optionally screenshot_paths.
    """
    if not DEFERRED_REVIEW_PATH.exists():
        return []
    entries: list[dict] = []
    for line in DEFERRED_REVIEW_PATH.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("questions"):
                entries.append(entry)
        except (json.JSONDecodeError, KeyError):
            pass
    return entries


def resolve_deferred(stem: str, resolution: dict) -> None:
    """Resolve a deferred PDF — remove from queue and log the resolution.

    Args:
        stem: PDF stem to resolve.
        resolution: Dict with resolution details (e.g. {"action": "merge",
                    "answered_by": "human", "answers": {...}}).
    """
    # Log to question book for training data
    QUESTION_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    resolution_entry = {
        "stem": stem,
        "resolution": resolution,
        "timestamp": _utc_now(),
    }
    with open(QUESTION_BOOK_PATH, "a") as f:
        f.write(json.dumps(resolution_entry) + "\n")

    # Remove from deferred queue
    undefer_pdf(stem)
    logger.info(f"resolved_deferred stem={stem} action={resolution.get('action', 'unknown')}")


def undefer_pdf(stem: str) -> None:
    """Remove a PDF from the deferred queue (human resolved it)."""
    if not DEFERRED_REVIEW_PATH.exists():
        return
    lines = DEFERRED_REVIEW_PATH.read_text().strip().split("\n")
    kept = []
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("stem") != stem:
                kept.append(line)
        except json.JSONDecodeError:
            kept.append(line)
    DEFERRED_REVIEW_PATH.write_text("\n".join(kept) + "\n" if kept else "")


def filter_by_extractability(pending: List[Path]) -> List[Path]:
    """Filter pending PDFs using the extractability model.

    Only filters PDFs that have existing run directories (with profile.json).
    Never-seen PDFs pass through (fail-open).
    """
    try:
        from extractability_model import (
            load_model,
            _find_run_dir,
            _profile_json_to_features,
            predict_extractability,
        )
    except ImportError:
        return pending

    model = load_model()
    if model is None:
        return pending

    kept: List[Path] = []
    skipped = 0
    for pdf_path in pending:
        run_dir = _find_run_dir(str(pdf_path))
        if run_dir is None:
            kept.append(pdf_path)
            continue
        profile_path = run_dir / "00_profile_detector" / "profile.json"
        if not profile_path.exists():
            kept.append(pdf_path)
            continue
        try:
            profile = json.loads(profile_path.read_text())
            features = _profile_json_to_features(profile)
            prob = predict_extractability(features, model)
            if prob < EXTRACTABILITY_THRESHOLD:
                skipped += 1
                with open(EXTRACTABILITY_LOW_CONFIDENCE_LOG, "a") as f:
                    f.write(json.dumps({
                        "pdf": str(pdf_path),
                        "probability": round(prob, 4),
                        "timestamp": _utc_now(),
                    }) + "\n")
                continue
        except (json.JSONDecodeError, ValueError, KeyError, OSError) as exc:
            logger.debug(f"extractability_check_error pdf={pdf_path} err={exc}")
        kept.append(pdf_path)

    if skipped:
        logger.info(
            f"extractability_gate skipped={skipped} "
            f"threshold={EXTRACTABILITY_THRESHOLD} kept={len(kept)}"
        )
    return kept


def _slug_for_doc(doc_path: Path) -> str:
    """Generate a filesystem-safe slug for a document path.

    Format: {sanitized_stem}_{md5(resolved_path)[:10]}
    MUST match review-pdf/verify/triage.py:_slug_for_doc().
    """
    digest = hashlib.md5(
        str(doc_path.resolve()).encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:10]
    stem = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in doc_path.stem)
    return f"{stem}_{digest}"


# Backward-compatible alias
_slug_for_pdf = _slug_for_doc

# Cache file: one slug per line for docs confirmed ingested into /memory.
_INGESTED_CACHE_PATH = STATE_DIR / "ingested_slugs.txt"


def _load_ingested_cache() -> set[str]:
    """Load the set of slugs that have been confirmed ingested into /memory."""
    if not _INGESTED_CACHE_PATH.exists():
        return set()
    return {
        line.strip()
        for line in _INGESTED_CACHE_PATH.read_text().splitlines()
        if line.strip()
    }


def mark_ingested(doc_path: Path) -> None:
    """Record that a document was successfully ingested into /memory.

    Called by the inline reviewer after a successful learn() call.
    """
    slug = _slug_for_doc(doc_path)
    _INGESTED_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Append-only: dedup on load
    with open(_INGESTED_CACHE_PATH, "a") as f:
        f.write(slug + "\n")


def _is_pipeline_output(p: Path) -> bool:
    """Return True if path is inside a pipeline output directory.

    Pipeline outputs live under ``results/`` subdirectories within each sector
    (e.g. ``defense/results/doc_stem/04_section_builder/``).  These contain
    intermediate artifacts (PNGs, JSONs, MDs, logs) that should never be
    re-discovered as source documents.
    """
    parts = p.parts
    for i, part in enumerate(parts):
        if part == "results" and i + 1 < len(parts):
            return True
        # Also skip other known output directories and pre-extracted text
        if part in (
            "completed", "failed", "quarantine", "results_iteration_1",
            "stress_test_results", "extracted_text", "fetcher_results",
            "__pycache__",
        ):
            return True
    return False


def discover_pending_content(root: Path) -> List[Path]:
    """Scan corpus for documents that have not been extracted or blacklisted.

    Discovers all extractable formats (PDF, HTML, DOCX, etc.).
    Skips pipeline output directories (``results/``, ``completed/``, etc.)
    to avoid re-discovering intermediate artifacts as source documents.
    A document is considered extracted if a matching directory exists under
    either the NVMe staging dir or the HDD archive dir.
    Blacklisted documents (corrupt, unextractable) are permanently skipped.
    """
    import time as _time

    from config import EXTRACTABLE_FORMATS

    logger.info("discover_pending scanning corpus root={}", root)
    t0 = _time.monotonic()
    all_docs: List[Path] = []
    skipped_output = 0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in EXTRACTABLE_FORMATS:
            if _is_pipeline_output(p):
                skipped_output += 1
                continue
            all_docs.append(p)
        # Progress heartbeat so supervisor knows we're alive
        if len(all_docs) % 2000 == 0 and len(all_docs) > 0:
            elapsed = _time.monotonic() - t0
            if elapsed > 5:
                logger.info(
                    "discover_pending scanning... docs_found={} skipped_output={} elapsed={:.0f}s",
                    len(all_docs), skipped_output, elapsed,
                )
    all_docs.sort(key=lambda p: p.name)
    scan_elapsed = _time.monotonic() - t0
    logger.info(
        "discover_pending scan_complete source_docs={} skipped_output={} elapsed={:.1f}s",
        len(all_docs), skipped_output, scan_elapsed,
    )

    # Layer 1: Collect all directory names under extracted_runs/ (NVMe + HDD).
    # These contain BOTH old-format (plain stem) and new-format (stem_md5[:10])
    # directory names.
    extracted_dirs: set[str] = set()
    for runs_dir in (REVIEW_PDF_EXTRACTED_RUNS_NVME, REVIEW_PDF_EXTRACTED_RUNS_HDD):
        if runs_dir.is_dir():
            for entry in runs_dir.iterdir():
                if entry.is_dir() or entry.is_symlink():
                    extracted_dirs.add(entry.name)
    logger.info(
        "discover_pending extracted_dirs={} nvme+hdd",
        len(extracted_dirs),
    )

    # Layer 2: Load the memory-ingested cache (slugs that passed quality gate
    # and were learned into /memory).  Updated by the inline reviewer after
    # each successful ingest.
    ingested_cache = _load_ingested_cache()
    logger.info("discover_pending ingested_cache={}", len(ingested_cache))

    blacklisted = load_blacklist()
    deferred = load_deferred()

    pending: List[Path] = []
    matched_slug = 0
    matched_stem = 0
    matched_ingested = 0
    for p in all_docs:
        if p.stem in blacklisted or p.stem in deferred:
            continue
        slug = _slug_for_doc(p)
        # Check new-format slug match (stem_md5[:10])
        if slug in extracted_dirs:
            matched_slug += 1
            continue
        # Check old-format stem-only match (legacy extractions)
        if p.stem in extracted_dirs:
            matched_stem += 1
            continue
        # Check /memory ingested cache
        if slug in ingested_cache:
            matched_ingested += 1
            continue
        pending.append(p)

    logger.info(
        "discover_pending total={} matched_slug={} matched_stem={} "
        "matched_ingested={} blacklisted={} deferred={} pending={}",
        len(all_docs), matched_slug, matched_stem,
        matched_ingested, len(blacklisted), len(deferred), len(pending),
    )
    return pending


def generate_quarantine_questions(reason: str, entry: dict) -> list[dict]:
    """Generate /interview v2 questions based on quarantine reason.

    Args:
        reason: Why the PDF was deferred (e.g. "low_confidence", "extraction_error").
        entry: The deferred entry dict (stem, path, detail, metadata, etc.).

    Returns:
        List of /interview v2 question dicts ready for session creation.
    """
    stem = entry.get("stem", "unknown")
    detail = entry.get("detail", "")
    path = entry.get("path", "")

    if reason == "low_confidence":
        return [
            {
                "id": f"{stem}_domain",
                "header": "Domain",
                "text": (
                    f"The extraction confidence for '{stem}' is low.\n"
                    f"Detail: {detail}\n\n"
                    f"What domain best describes this document?"
                ),
                "type": "select",
                "options": [
                    {"label": "defense", "description": "Military, DoD, or intelligence community"},
                    {"label": "aerospace", "description": "NASA, FAA, or aviation industry"},
                    {"label": "standards", "description": "NIST, ISO, or regulatory framework"},
                    {"label": "engineering", "description": "Technical datasheet or specification"},
                    {"label": "academic", "description": "Research paper or journal article"},
                    {"label": "other", "description": "None of the above"},
                ],
            },
            {
                "id": f"{stem}_strategy",
                "header": "Strategy",
                "text": "Should the extraction strategy be overridden for this document?",
                "type": "select",
                "options": [
                    {"label": "auto", "description": "Let the pipeline decide (default)"},
                    {"label": "structure_tree", "description": "Force tagged-PDF structure order"},
                    {"label": "spatial", "description": "Force spatial/geometric block assembly"},
                    {"label": "ocr_only", "description": "Ignore embedded text, run full OCR"},
                ],
            },
            {
                "id": f"{stem}_sections",
                "header": "Sections",
                "text": "Does this document have clear section headings and hierarchy?",
                "type": "yes_no",
                "recommendation": "yes",
                "reason": "Most technical documents have section structure.",
            },
        ]

    elif reason == "extraction_error":
        return [
            {
                "id": f"{stem}_table_strategy",
                "header": "Tables",
                "text": (
                    f"Extraction failed for '{stem}'.\n"
                    f"Detail: {detail}\n\n"
                    f"How should tables be handled on retry?"
                ),
                "type": "select",
                "options": [
                    {"label": "camelot_lattice", "description": "Use Camelot lattice mode (ruled tables)"},
                    {"label": "camelot_stream", "description": "Use Camelot stream mode (borderless tables)"},
                    {"label": "skip_tables", "description": "Skip table extraction entirely"},
                    {"label": "native_only", "description": "Use only pdf_oxide native table detection"},
                ],
            },
            {
                "id": f"{stem}_ocr_fallback",
                "header": "OCR",
                "text": "Should OCR fallback be enabled for this document?",
                "type": "yes_no",
                "recommendation": "yes",
                "reason": "OCR can recover text from scanned or image-heavy pages.",
            },
            {
                "id": f"{stem}_disposition",
                "header": "Action",
                "text": "What should happen with this document?",
                "type": "select",
                "options": [
                    {"label": "retry", "description": "Retry extraction with adjusted settings"},
                    {"label": "skip", "description": "Skip permanently (add to blacklist)"},
                    {"label": "defer", "description": "Keep in quarantine for later review"},
                ],
            },
        ]

    elif reason == "novel_layout":
        return [
            {
                "id": f"{stem}_columns",
                "header": "Columns",
                "text": (
                    f"Document '{stem}' has an unfamiliar layout.\n"
                    f"Detail: {detail}\n\n"
                    f"How many text columns does this document use?"
                ),
                "type": "select",
                "options": [
                    {"label": "1", "description": "Single column (standard)"},
                    {"label": "2", "description": "Two-column (academic paper style)"},
                    {"label": "3+", "description": "Three or more columns (newsletter/brochure)"},
                    {"label": "mixed", "description": "Mixed layout (varies by page)"},
                ],
            },
            {
                "id": f"{stem}_reading_order",
                "header": "Read Order",
                "text": "What reading order should be used?",
                "type": "select",
                "options": [
                    {"label": "left_to_right", "description": "Standard left-to-right, top-to-bottom"},
                    {"label": "column_first", "description": "Read each column top-to-bottom before next"},
                    {"label": "structure_tree", "description": "Follow PDF structure tree order"},
                ],
            },
            {
                "id": f"{stem}_special",
                "header": "Special",
                "text": "Does this document require any special handling?",
                "type": "multi",
                "multi_select": True,
                "options": [
                    {"label": "rotated_pages", "description": "Some pages are rotated 90/180 degrees"},
                    {"label": "watermarks", "description": "Watermarks overlap text content"},
                    {"label": "form_fields", "description": "Contains interactive form fields"},
                    {"label": "annotations", "description": "Has significant margin annotations"},
                    {"label": "none", "description": "No special handling needed"},
                ],
            },
        ]

    elif reason == "timeout":
        return [
            {
                "id": f"{stem}_page_range",
                "header": "Pages",
                "text": (
                    f"Extraction of '{stem}' timed out.\n"
                    f"Detail: {detail}\n\n"
                    f"Should extraction be limited to a page range?"
                ),
                "type": "select",
                "options": [
                    {"label": "all", "description": "Try all pages again (with higher timeout)"},
                    {"label": "first_50", "description": "Extract only the first 50 pages"},
                    {"label": "first_100", "description": "Extract only the first 100 pages"},
                    {"label": "first_200", "description": "Extract only the first 200 pages"},
                    {"label": "skip", "description": "Skip this document entirely"},
                ],
            },
            {
                "id": f"{stem}_quality",
                "header": "Quality",
                "text": "What quality trade-off is acceptable?",
                "type": "select",
                "options": [
                    {"label": "full", "description": "Full extraction (tables, figures, sections)"},
                    {"label": "text_only", "description": "Text extraction only (skip tables/figures)"},
                    {"label": "fast", "description": "Fast mode (skip OCR, basic block assembly)"},
                ],
            },
        ]

    else:
        # Fallback for unknown reasons — generic triage question
        return [
            {
                "id": f"{stem}_triage",
                "header": "Triage",
                "text": (
                    f"Document '{stem}' was quarantined.\n"
                    f"Reason: {reason}\n"
                    f"Detail: {detail}\n"
                    f"Path: {path}\n\n"
                    f"What should be done with this document?"
                ),
                "type": "select",
                "options": [
                    {"label": "retry", "description": "Retry extraction with default settings"},
                    {"label": "skip", "description": "Skip permanently (add to blacklist)"},
                    {"label": "defer", "description": "Keep in quarantine for later review"},
                ],
            },
        ]


def launch_interview(stem: str) -> dict:
    """Prepare an /interview session for a quarantined PDF.

    Loads the deferred entry, generates reason-appropriate questions,
    and writes a session JSON file for the /interview skill to consume.

    Args:
        stem: The PDF stem identifying the deferred entry.

    Returns:
        Dict with session metadata and questions, suitable for /interview.

    Raises:
        ValueError: If the stem is not found in the deferred queue.
    """
    # Load all deferred entries (not just those with pre-attached questions)
    if not DEFERRED_REVIEW_PATH.exists():
        raise ValueError(f"No deferred entries found (file missing): {stem}")

    entry = None
    for line in DEFERRED_REVIEW_PATH.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            candidate = json.loads(line)
            if candidate.get("stem") == stem:
                entry = candidate
                break
        except (json.JSONDecodeError, KeyError):
            pass

    if entry is None:
        raise ValueError(f"Stem not found in deferred queue: {stem}")

    reason = entry.get("reason", "unknown")
    questions = generate_quarantine_questions(reason, entry)

    # Build the session payload matching /interview's load_questions_file format
    session_payload = {
        "title": f"Quarantine Review: {stem}",
        "context": (
            f"PDF: {entry.get('path', 'unknown')}\n"
            f"Reason: {reason}\n"
            f"Detail: {entry.get('detail', '')}\n"
            f"Quarantined: {entry.get('timestamp', 'unknown')}"
        ),
        "questions": questions,
        "stem": stem,
        "reason": reason,
    }

    # Write session JSON for /interview consumption
    INTERVIEW_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_path = INTERVIEW_SESSIONS_DIR / f"{stem}.json"
    session_path.write_text(json.dumps(session_payload, indent=2))
    logger.info(f"interview_session_created stem={stem} reason={reason} path={session_path}")

    return session_payload


def load_all_deferred() -> list[dict]:
    """Load all deferred entries (with or without questions).

    Returns:
        List of deferred entry dicts, each containing at minimum:
        stem, path, reason, timestamp.
    """
    if not DEFERRED_REVIEW_PATH.exists():
        return []
    entries: list[dict] = []
    for line in DEFERRED_REVIEW_PATH.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            entries.append(entry)
        except (json.JSONDecodeError, KeyError):
            pass
    return entries


# Backward-compatible alias
discover_pending_pdfs = discover_pending_content
