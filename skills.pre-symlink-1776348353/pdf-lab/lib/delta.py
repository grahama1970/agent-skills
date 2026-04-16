"""ExtractionDelta and ReviewContext dataclasses for pdf-lab.

The delta is the gap between S00's estimate and actual extraction.
There is no absolute ground truth — only this relative measure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


@dataclass
class ReviewContext:
    """Traces a code change back to the persona review that triggered it."""

    persona_name: str = "Margaret Chen"
    persona_role: str = "extraction quality"
    issue_codes: List[str] = field(default_factory=list)
    score: float = 0.0
    review_timestamp: str = ""
    review_notes: str = ""
    source_pdf: str = ""
    source_pdf_hash: str = ""
    escalation_skill: str = "pdf-lab"

    def __post_init__(self) -> None:
        """Validate and clamp score to [0.0, 1.0]."""
        if not isinstance(self.score, (int, float)):
            try:
                self.score = float(self.score)
            except (TypeError, ValueError):
                logger.warning(f"Invalid score {self.score!r}, defaulting to 0.0")
                self.score = 0.0
        self.score = max(0.0, min(float(self.score), 1.0))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_review_json(cls, data: Dict[str, Any]) -> ReviewContext:
        return cls(
            persona_name=data.get("persona", data.get("persona_name", "Margaret Chen")),
            persona_role=data.get("persona_role", "extraction quality"),
            issue_codes=data.get("issue_codes", []),
            score=float(data.get("score", data.get("review_score", 0.0))),
            review_timestamp=data.get("timestamp", data.get("review_timestamp", "")),
            review_notes=data.get("notes", data.get("review_notes", "")),
            source_pdf=data.get("source_pdf", data.get("pdf_path", "")),
            source_pdf_hash=data.get("source_pdf_hash", data.get("pdf_hash", "")),
            escalation_skill=data.get("escalation_skill", "pdf-lab"),
        )


@dataclass
class ExtractionDelta:
    """The gap between S00 estimate and actual extraction."""

    estimated_sections: int = 0
    estimated_tables: int = 0
    estimated_figures: int = 0
    estimated_pages: int = 0
    actual_sections: int = 0
    actual_tables: int = 0
    actual_figures: int = 0
    actual_pages: int = 0

    @staticmethod
    def _ratio(actual: int, estimated: int) -> float:
        """Compute actual/estimated ratio, clamped to [0.0, 1.0].

        Overextraction (actual > estimated) is capped at 1.0 so it doesn't
        mask quality issues by inflating the overall delta.
        """
        if estimated == 0:
            return 1.0 if actual == 0 else 0.0
        return min(actual / estimated, 1.0)

    @property
    def section_delta(self) -> float:
        """Ratio: actual/estimated. 1.0 = perfect, <1 = underextraction."""
        return self._ratio(self.actual_sections, self.estimated_sections)

    @property
    def table_delta(self) -> float:
        return self._ratio(self.actual_tables, self.estimated_tables)

    @property
    def figure_delta(self) -> float:
        return self._ratio(self.actual_figures, self.estimated_figures)

    @property
    def page_delta(self) -> float:
        return self._ratio(self.actual_pages, self.estimated_pages)

    @property
    def section_ratio_raw(self) -> float:
        """Unclamped ratio for diagnosis (oversegmentation detection)."""
        if self.estimated_sections == 0:
            return 1.0 if self.actual_sections == 0 else 0.0
        return self.actual_sections / self.estimated_sections

    @property
    def table_ratio_raw(self) -> float:
        """Unclamped ratio for diagnosis (false positive detection)."""
        if self.estimated_tables == 0:
            return 1.0 if self.actual_tables == 0 else 0.0
        return self.actual_tables / self.estimated_tables

    @property
    def overall_delta(self) -> float:
        """Weighted average. 1.0 = estimates match extraction. Clamped to [0.0, 1.0]."""
        raw = (
            0.35 * self.section_delta
            + 0.35 * self.table_delta
            + 0.15 * self.figure_delta
            + 0.15 * self.page_delta
        )
        return max(0.0, min(raw, 1.0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "section_delta": round(self.section_delta, 4),
            "table_delta": round(self.table_delta, 4),
            "figure_delta": round(self.figure_delta, 4),
            "page_delta": round(self.page_delta, 4),
            "overall_delta": round(self.overall_delta, 4),
        }

    def summary(self) -> str:
        parts = []
        if self.estimated_sections or self.actual_sections:
            parts.append(
                f"sections: {self.actual_sections}/{self.estimated_sections} "
                f"({self.section_delta:.2f})"
            )
        if self.estimated_tables or self.actual_tables:
            parts.append(
                f"tables: {self.actual_tables}/{self.estimated_tables} "
                f"({self.table_delta:.2f})"
            )
        if self.estimated_figures or self.actual_figures:
            parts.append(
                f"figures: {self.actual_figures}/{self.estimated_figures} "
                f"({self.figure_delta:.2f})"
            )
        parts.append(f"overall: {self.overall_delta:.2f}")
        return " | ".join(parts)


@dataclass
class Diagnosis:
    """Result of diagnosing an extraction delta."""

    patterns: List[str] = field(default_factory=list)
    root_cause: str = ""
    failing_steps: List[str] = field(default_factory=list)
    issue_codes: List[str] = field(default_factory=list)
    s00_overestimated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_delta_from_json(
    profile_json: Path,
    structural_json: Path,
) -> ExtractionDelta:
    """Compute ExtractionDelta from S00 profile and S11 structural JSON files."""
    profile = json.loads(profile_json.read_text())
    structural = json.loads(structural_json.read_text())

    # S00 estimates
    hierarchy = profile.get("hierarchy", {})
    elements = profile.get("elements", {})
    estimated_sections = hierarchy.get("estimated_sections", 0)
    estimated_tables = elements.get("estimated_table_count", 0)
    estimated_figures = elements.get("image_pages", 0)
    estimated_pages = profile.get("page_count", 0)

    # Actual extraction counts from structural JSON
    actual_sections = structural.get("section_count", len(structural.get("sections", [])))
    actual_tables = structural.get("table_count", len(structural.get("tables", [])))
    actual_figures = structural.get("figure_count", len(structural.get("figures", [])))
    actual_pages = structural.get("page_count", estimated_pages)

    return ExtractionDelta(
        estimated_sections=estimated_sections,
        estimated_tables=estimated_tables,
        estimated_figures=estimated_figures,
        estimated_pages=estimated_pages,
        actual_sections=actual_sections,
        actual_tables=actual_tables,
        actual_figures=actual_figures,
        actual_pages=actual_pages,
    )


def compute_delta_from_review(review_data: Dict[str, Any]) -> ExtractionDelta:
    """Compute delta from a review result JSON (contains both S00 and extraction)."""
    s00 = review_data.get("s00_estimates", review_data.get("estimates", {}))
    actual = review_data.get("actual_extraction", review_data.get("extraction", {}))

    return ExtractionDelta(
        estimated_sections=s00.get("sections", 0),
        estimated_tables=s00.get("tables", 0),
        estimated_figures=s00.get("figures", 0),
        estimated_pages=s00.get("pages", 0),
        actual_sections=actual.get("sections", 0),
        actual_tables=actual.get("tables", 0),
        actual_figures=actual.get("figures", 0),
        actual_pages=actual.get("pages", 0),
    )


def diagnose_delta(
    delta: ExtractionDelta,
    debug_patterns: Optional[List[str]] = None,
    issue_codes: Optional[List[str]] = None,
) -> Diagnosis:
    """Diagnose what went wrong from a delta and optional debug patterns.

    Detects systematic issues:
    - If 3+ extractions find ~same count but S00 is far off → S00 miscalibrated
    - If section_delta < 0.5 → likely undersegmentation (S04)
    - If table_delta < 0.7 → table extraction issues (S05)
    """
    patterns = list(debug_patterns or [])
    failing_steps: List[str] = []
    codes = list(issue_codes or [])

    # Section analysis (use raw unclamped ratios for over-detection)
    if delta.section_delta < 0.5:
        if "section_undersegmentation" not in patterns:
            patterns.append("section_undersegmentation")
        failing_steps.append("s04")
        if "section_alignment_critical" not in codes:
            codes.append("section_alignment_critical")
    elif delta.section_ratio_raw > 2.0:
        if "section_oversegmentation" not in patterns:
            patterns.append("section_oversegmentation")
        failing_steps.append("s04")

    # Table analysis (use raw unclamped ratios for false positive detection)
    if delta.table_delta < 0.7:
        if "missed_tables" not in patterns:
            patterns.append("missed_tables")
        failing_steps.append("s05")
        if "table_recall_low" not in codes:
            codes.append("table_recall_low")
    elif delta.table_ratio_raw > 1.5:
        if "false_positive_tables" not in patterns:
            patterns.append("false_positive_tables")
        failing_steps.append("s05")

    # Figure analysis
    if delta.figure_delta < 0.5:
        failing_steps.append("s06")

    # Determine root cause
    root_cause = _infer_root_cause(delta, patterns)

    # Check if S00 is systematically wrong
    s00_overestimated = (
        delta.section_delta < 0.5
        and delta.estimated_sections > 20
        and delta.actual_sections < delta.estimated_sections * 0.4
    )

    return Diagnosis(
        patterns=patterns,
        root_cause=root_cause,
        failing_steps=list(set(failing_steps)),
        issue_codes=codes,
        s00_overestimated=s00_overestimated,
    )


def _infer_root_cause(delta: ExtractionDelta, patterns: List[str]) -> str:
    """Build human-readable root cause from delta and patterns."""
    causes = []

    if "multi_column" in patterns and delta.section_delta < 0.7:
        causes.append(
            "Multi-column layout causing section headers to be missed or merged"
        )
    if "split_tables" in patterns and delta.table_delta < 0.7:
        causes.append("Tables spanning multiple pages not being stitched together")
    if "section_undersegmentation" in patterns:
        causes.append(
            f"S04 undersegmenting: found {delta.actual_sections} sections "
            f"vs S00 estimate of {delta.estimated_sections} "
            f"(font threshold or merge heuristic too aggressive)"
        )
    if "section_oversegmentation" in patterns:
        causes.append(
            f"S04 oversegmenting: found {delta.actual_sections} sections "
            f"vs S00 estimate of {delta.estimated_sections}"
        )
    if "missed_tables" in patterns:
        causes.append(
            f"S05 missing tables: found {delta.actual_tables} "
            f"vs S00 estimate of {delta.estimated_tables} "
            f"(line_scale or strategy selection may need adjustment)"
        )
    if "scanned_no_ocr" in patterns:
        causes.append("Scanned PDF without OCR text layer")

    if not causes:
        causes.append(
            f"Overall delta {delta.overall_delta:.2f} — "
            f"extraction underperforming relative to S00 estimates"
        )

    return "; ".join(causes)
