"""Shared constants, paths, dataclasses, and regex patterns for learn-datalake.

Purpose:
- Single source of truth for all configuration used across learn-datalake modules.

Inputs:
- None (pure configuration).

Outputs:
- Constants, dataclasses, and compiled regex patterns.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent  # .pi/skills/
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))

REVIEW_PDF_DIR = SKILLS_DIR / "review-pdf"
REVIEW_PDF_EXTRACTED_RUNS = _EMBRY_STORAGE / "skills/review-pdf/extracted_runs"
REVIEW_PDF_EXTRACTED_RUNS_NVME = SKILLS_DIR / "review-pdf" / "extracted_runs_staging"
REVIEW_PDF_EXTRACTED_RUNS_HDD = _EMBRY_STORAGE / "skills/review-pdf/extracted_runs"
REVIEW_PDF_EXTRACTED_RUNS_SYMLINK = SKILLS_DIR / "review-pdf" / "extracted_runs"
MEMORY_DIR = SKILLS_DIR / "memory"
DOGPILE_DIR = SKILLS_DIR / "dogpile"
FETCHER_DIR = SKILLS_DIR / "fetcher"
TASK_MONITOR_DIR = SKILLS_DIR / "task-monitor"
TASK_MONITOR_RUN = TASK_MONITOR_DIR / "run.sh"
STATE_DIR = SKILL_DIR / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
TASK_MONITOR_STATE_DIR = STATE_DIR / "task_monitor"
TASK_MONITOR_STATE_DIR.mkdir(parents=True, exist_ok=True)
QUESTION_BOOK_PATH = STATE_DIR / "question_book.jsonl"
FAILED_PDF_BLACKLIST = STATE_DIR / "failed_pdf_blacklist.jsonl"
DEFERRED_REVIEW_PATH = STATE_DIR / "deferred_review.jsonl"
EXTRACTABILITY_THRESHOLD = 0.3
EXTRACTABILITY_LOW_CONFIDENCE_LOG = STATE_DIR / "extractability_low_confidence.jsonl"

# All formats the extractor pipeline can process (provider registry).
EXTRACTABLE_FORMATS = {
    ".pdf", ".docx", ".doc", ".odt", ".pptx", ".ppt", ".odp",
    ".xlsx", ".xls", ".xlsm", ".ods", ".csv", ".tsv",
    ".html", ".htm", ".xml", ".md", ".markdown", ".rst", ".epub",
    ".txt", ".text", ".log",
    ".json", ".jsonl",
    ".reqif", ".reqifz",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".svg", ".webp",
}

# Code files — routed to /treesitter, not the extractor.
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rs", ".rb", ".sh",
}

# Legacy aliases — kept for backward compatibility with callers.
NON_PDF_EXTENSIONS = {
    ".html", ".htm", ".xml", ".json", ".yaml", ".yml", ".md", ".rst",
    ".txt", ".csv", ".tsv", ".docx", ".pptx", ".xlsx", ".ipynb",
} | CODE_EXTENSIONS

DOC_EXTENSIONS = EXTRACTABLE_FORMATS | {
    ".yaml", ".yml", ".ipynb",
}

SECTOR_KEYS = [
    "arxiv", "dtic", "faa", "nasa", "nist",
    "ietf", "industry", "adversarial", "edge_cases",
]

SECTOR_DOMAIN_HINTS: Dict[str, List[str]] = {
    "arxiv": ["arxiv.org"],
    "dtic": ["dtic.mil", "apps.dtic.mil"],
    "faa": ["faa.gov"],
    "nasa": ["nasa.gov", "ntrs.nasa.gov"],
    "nist": ["nist.gov", "nvlpubs.nist.gov"],
    "ietf": ["ietf.org", "rfc-editor.org", "datatracker.ietf.org"],
    "industry": [
        "ti.com", "nxp.com", "microchip.com", "infineon.com", "analog.com",
        "st.com", "intel.com", "amd.com", "nvidia.com", "qualcomm.com",
    ],
    "adversarial": [
        "courtlistener.com", "law.cornell.edu", "cia.gov",
        "justice.gov", "archive.org", "loc.gov",
    ],
    "edge_cases": [],
}

CANDIDATE_URL_FILES = [
    "expansion_manifest.txt",
    "industry_pdfs.txt",
    "finance_pdfs.txt",
    "finance_pdfs_v2.txt",
    "adversarial_pdfs.txt",
    "adversarial_pdfs_v2.txt",
]


@dataclass
class CommandResult:
    """Result from a subprocess execution."""

    cmd: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    stalled: bool = False
    elapsed_seconds: float = 0.0


@dataclass
class ParallelReviewResult:
    """Aggregated result from running multiple review-pdf workers."""

    worker_results: List[CommandResult] = field(default_factory=list)
    worker_summaries: List[Dict[str, Any]] = field(default_factory=list)
    aggregate_summary: Dict[str, Any] = field(default_factory=dict)
    worst_returncode: int = 0
    any_stalled: bool = False
    any_timed_out: bool = False
    pending_pdf_count: int = 0
    workers_used: int = 0


@dataclass
class ReviewConfig:
    """Shared configuration for review-pdf execution, replacing repeated kwargs."""

    root: Path
    target_score: float
    target_fail_ratio: float
    poll_seconds: int
    execute_jobs: bool
    ingest_memory: bool
    memory_scope: str
    taxonomy_collection: str
    watchdog_seconds: int
    watchdog_poll_seconds: int
    review_incremental: bool
    inline_review: bool = False
    extract_missing: bool = True


RE_EXTRACT_NEW = re.compile(
    r"extract_missing status=extracted new_count=(?P<count>[0-9]+)"
)
RE_EXTRACT_TIMEOUT = re.compile(r"extract_timeout seconds=(?P<seconds>[0-9]+)")
RE_DISCOVER_PROGRESS = re.compile(
    r"discover_progress scanned=(?P<scanned>[0-9]+) extracted_new=(?P<new_count>[0-9]+)"
)
RE_INCREMENTAL_SKIP = re.compile(
    r"incremental_skip .*changed_pdfs=(?P<changed>[0-9]+)"
)
