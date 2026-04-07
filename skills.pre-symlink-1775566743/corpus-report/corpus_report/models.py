"""Typed dataclasses for corpus-report intermediate data."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ManifestEntry:
    id: str
    filename: str
    status: str
    path: str = ""
    category: str = ""
    source: str = ""
    page_count: int | None = None
    file_size_mb: float | None = None
    duration_sec: int | None = None
    s00_preset: str | None = None
    s00_estimated_sections: int | None = None
    s00_estimated_regex: int | None = None
    s00_estimated_font: int | None = None
    s00_body_font_size: float | None = None
    s04_actual_sections: int | None = None
    s00_s04_ratio: float | None = None
    s00_s04_label: str | None = None
    quality_signal: str | None = None
    debug_patterns: list[str] = field(default_factory=list)
    lessons_stored: bool = False
    processing_started: str | None = None
    processing_finished: str | None = None
    results_dir: str | None = None
    error: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> ManifestEntry:
        return cls(
            id=d.get("id", ""),
            filename=d.get("filename", ""),
            status=d.get("status", "unknown"),
            path=d.get("path", ""),
            category=d.get("category", ""),
            source=d.get("source", ""),
            page_count=d.get("page_count"),
            file_size_mb=d.get("file_size_mb"),
            duration_sec=d.get("duration_sec"),
            s00_preset=d.get("s00_preset"),
            s00_estimated_sections=d.get("s00_estimated_sections"),
            s00_estimated_regex=d.get("s00_estimated_regex"),
            s00_estimated_font=d.get("s00_estimated_font"),
            s00_body_font_size=d.get("s00_body_font_size"),
            s04_actual_sections=d.get("s04_actual_sections"),
            s00_s04_ratio=d.get("s00_s04_ratio"),
            s00_s04_label=d.get("s00_s04_label"),
            quality_signal=d.get("quality_signal"),
            debug_patterns=d.get("debug_patterns", []),
            lessons_stored=d.get("lessons_stored", False),
            processing_started=d.get("processing_started"),
            processing_finished=d.get("processing_finished"),
            results_dir=d.get("results_dir"),
            error=d.get("error"),
        )


@dataclass
class CorpusSummary:
    total: int = 0
    completed: int = 0
    pending: int = 0
    failed: int = 0
    processing: int = 0
    categories: dict[str, int] = field(default_factory=dict)
    presets: dict[str, int] = field(default_factory=dict)
    median_duration_sec: float | None = None
    total_pages: int = 0
    total_size_mb: float = 0.0
    label_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class QualityReport:
    label_counts: dict[str, int] = field(default_factory=dict)
    ratio_histogram: dict[str, int] = field(default_factory=dict)
    worst_offenders: list[dict] = field(default_factory=list)
    good_pct: float = 0.0
    acceptable_pct: float = 0.0
    total_with_ratio: int = 0


@dataclass
class StageTiming:
    name: str = ""
    avg_ms: float = 0.0
    median_ms: float = 0.0
    max_ms: float = 0.0
    pct_of_total: float = 0.0


@dataclass
class BottleneckReport:
    files_sampled: int = 0
    stages: list[StageTiming] = field(default_factory=list)
    avg_total_ms: float = 0.0


@dataclass
class TrendPoint:
    window_label: str = ""
    count: int = 0
    good_pct: float = 0.0
    acceptable_pct: float = 0.0
    median_ratio: float | None = None
    median_duration_sec: float | None = None
