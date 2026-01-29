"""QRA (Question-Reasoning-Answer) knowledge extraction skill.

Extracts grounded QRA pairs from text using parallel LLM calls.
Supports domain-specific context for focused extraction.

Usage:
    python -m qra --text "large text..." --scope research
    python -m qra --file doc.md --context "cybersecurity expert"
    python -m qra --from-extractor /path/to/extractor/results --scope research
    cat text.txt | python -m qra --scope myproject

Modules:
    config - Constants, paths, environment settings
    utils - Logging, progress, text processing
    extractor - Q&A extraction with LLM batch processing
    validator - Answer grounding validation
    storage - Memory storage integration
"""

from qra.config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_GROUNDING_THRESHOLD,
    DEFAULT_MAX_SECTION_CHARS,
    get_scillm_config,
)
from qra.extractor import extract_qra_batch, build_system_prompt
from qra.validator import check_grounding, validate_qra_structure, deduplicate_qras
from qra.storage import store_qra, batch_store_qras, check_memory_available
from qra.utils import build_sections, split_sentences, log

__all__ = [
    # Config
    "DEFAULT_CONCURRENCY",
    "DEFAULT_GROUNDING_THRESHOLD",
    "DEFAULT_MAX_SECTION_CHARS",
    "get_scillm_config",
    # Extraction
    "extract_qra_batch",
    "build_system_prompt",
    # Validation
    "check_grounding",
    "validate_qra_structure",
    "deduplicate_qras",
    # Storage
    "store_qra",
    "batch_store_qras",
    "check_memory_available",
    # Utils
    "build_sections",
    "split_sentences",
    "log",
]

__version__ = "2.0.0"
