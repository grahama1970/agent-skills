"""Task feature extraction and vectorization for timeout prediction."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TaskFeatures:
    """Universal feature set for timeout estimation.

    Core fields apply to all task types. Task-specific fields are optional
    and handled gracefully by DictVectorizer (missing = 0).
    """

    # --- universal ---
    task_type: str = "pdf_extraction"

    # --- pdf_extraction ---
    page_count: int = 0
    file_size_mb: float = 0.0
    table_pages: int = 0
    estimated_table_count: int = 0
    image_pages: int = 0
    has_tables: bool = False
    has_figures: bool = False
    has_formulas: bool = False
    has_requirements: bool = False
    estimated_sections: int = 0
    domain: str = "general"
    source: str = "unknown"
    layout_columns: int = 1
    max_tables_per_page: int = 0

    # --- llm_api_call ---
    prompt_tokens: int = 0
    model: str = ""
    provider: str = ""
    image_count: int = 0

    # --- subprocess ---
    command_type: str = ""
    input_size: int = 0
    complexity_hints: int = 0

    # --- remediation ---
    issue_count: int = 0
    issue_severity: str = ""
    skill_name: str = ""

    # --- labels (only present in training data) ---
    actual_duration_s: Optional[float] = field(default=None, repr=False)
    timed_out: Optional[bool] = field(default=None, repr=False)


# Domains and sources used for one-hot encoding
KNOWN_DOMAINS = [
    "general",
    "scientific",
    "engineering",
    "government",
    "defense",
    "standards",
    "medical",
    "financial",
    "legal",
]

KNOWN_SOURCES = [
    "arxiv",
    "nasa",
    "nist",
    "faa",
    "government",
    "standards",
    "engineering",
    "adversarial",
    "archive_org",
    "ietf",
    "defense",
    "other",
]

KNOWN_TASK_TYPES = [
    "pdf_extraction",
    "llm_api_call",
    "subprocess",
    "remediation",
]


def features_to_dict(feat: TaskFeatures) -> dict:
    """Convert TaskFeatures to a flat dict suitable for DictVectorizer.

    Boolean fields become 0/1 ints.  Categorical fields (domain, source,
    task_type) are expanded into ``category=value`` keys so that
    DictVectorizer produces proper one-hot columns.
    """
    d: dict = {}

    # Numeric features
    d["page_count"] = feat.page_count
    d["file_size_mb"] = feat.file_size_mb
    d["table_pages"] = feat.table_pages
    d["estimated_table_count"] = feat.estimated_table_count
    d["image_pages"] = feat.image_pages
    d["estimated_sections"] = feat.estimated_sections
    d["layout_columns"] = feat.layout_columns
    d["max_tables_per_page"] = feat.max_tables_per_page
    d["prompt_tokens"] = feat.prompt_tokens
    d["image_count"] = feat.image_count
    d["input_size"] = feat.input_size
    d["complexity_hints"] = feat.complexity_hints
    d["issue_count"] = feat.issue_count

    # Binary features
    d["has_tables"] = int(feat.has_tables)
    d["has_figures"] = int(feat.has_figures)
    d["has_formulas"] = int(feat.has_formulas)
    d["has_requirements"] = int(feat.has_requirements)

    # Interaction features (non-linear helpers for GradientBoosting)
    d["pages_x_tables"] = feat.page_count * feat.table_pages
    d["pages_x_formulas"] = feat.page_count * int(feat.has_formulas)

    # Categorical → one-hot keys
    d[f"task_type={feat.task_type}"] = 1
    d[f"domain={feat.domain}"] = 1
    d[f"source={feat.source}"] = 1

    return d


def dict_to_features(raw: dict) -> TaskFeatures:
    """Build TaskFeatures from a JSON-parsed dict, tolerating extra keys."""
    known = {f.name for f in TaskFeatures.__dataclass_fields__.values()}
    filtered = {k: v for k, v in raw.items() if k in known}
    return TaskFeatures(**filtered)
