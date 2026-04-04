"""Configuration, constants, and paths for training datalake ingestion."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent  # .pi/skills/
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))

DOGPILE_DIR = SKILLS_DIR / "dogpile"
FETCHER_DIR = SKILLS_DIR / "fetcher"
MEMORY_DIR = SKILLS_DIR / "memory"
TAXONOMY_DIR = SKILLS_DIR / "taxonomy"

DEFAULT_ALLOWED_ROOT = _EMBRY_STORAGE / "extractor_corpus"
STATE_DIR = DEFAULT_ALLOWED_ROOT / ".ingest_training"
STATE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_MEMORY_EVENTS = STATE_DIR / "memory_events.jsonl"
MEMORY_SCOPE_PREFIX = "datalake_training_"

DOC_EXTENSIONS = {
    ".pdf",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".rst",
    ".xml",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".csv",
    ".tsv",
    ".docx",
    ".pptx",
    ".xlsx",
    ".ipynb",
}

SECTOR_KEYS = [
    "arxiv",
    "dtic",
    "faa",
    "nasa",
    "nist",
    "ietf",
    "industry",
    "adversarial",
    "edge_cases",
]

SECTOR_DOMAIN_HINTS: Dict[str, List[str]] = {
    "arxiv": ["arxiv.org"],
    "dtic": ["dtic.mil", "apps.dtic.mil"],
    "faa": ["faa.gov"],
    "nasa": ["nasa.gov", "ntrs.nasa.gov"],
    "nist": ["nist.gov", "nvlpubs.nist.gov"],
    "ietf": ["ietf.org", "rfc-editor.org", "datatracker.ietf.org"],
    "industry": [
        "ti.com",
        "nxp.com",
        "microchip.com",
        "infineon.com",
        "analog.com",
        "st.com",
        "intel.com",
        "amd.com",
        "nvidia.com",
        "qualcomm.com",
    ],
    "adversarial": [
        "courtlistener.com",
        "law.cornell.edu",
        "cia.gov",
        "justice.gov",
        "archive.org",
        "loc.gov",
    ],
    "edge_cases": [],
}

DEFAULT_CANDIDATE_FILES = [
    DOGPILE_DIR / "expansion_manifest.txt",
    DOGPILE_DIR / "industry_pdfs.txt",
    DOGPILE_DIR / "finance_pdfs.txt",
    DOGPILE_DIR / "finance_pdfs_v2.txt",
    DOGPILE_DIR / "adversarial_pdfs.txt",
    DOGPILE_DIR / "adversarial_pdfs_v2.txt",
]
