"""Configuration constants and paths for corpus-report skill.

Reads CORPUS_ROOT from environment to locate the 12TB extractor corpus.
All path derivation is centralized here.
"""
from __future__ import annotations

import os
from pathlib import Path

_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
CORPUS_ROOT = Path(os.environ.get("CORPUS_ROOT", str(_EMBRY_STORAGE / "extractor_corpus")))

MANIFEST_PATH = CORPUS_ROOT / "metadata" / "manifest.jsonl"
PATTERN_REGISTRY_PATH = CORPUS_ROOT / "metadata" / "pattern_registry.json"
RESULTS_DIR = CORPUS_ROOT / "results"

DATA_DIR = Path.home() / ".pi" / "corpus-report"

RATIO_HISTOGRAM_BUCKETS = [
    (0.0, 0.25, "[0, 0.25)"),
    (0.25, 0.5, "[0.25, 0.5)"),
    (0.5, 0.8, "[0.5, 0.8)"),
    (0.8, 1.2, "[0.8, 1.2)"),
    (1.2, 2.0, "[1.2, 2.0)"),
    (2.0, 5.0, "[2.0, 5.0)"),
    (5.0, float("inf"), "[5.0+)"),
]
