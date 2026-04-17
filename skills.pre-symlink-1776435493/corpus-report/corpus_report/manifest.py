"""Load, filter, and aggregate manifest.jsonl data.

All corpus statistics derive from this module. No external dependencies
beyond stdlib -- manifest is small enough (<10k lines) that json +
statistics handles everything.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import RATIO_HISTOGRAM_BUCKETS
from .models import CorpusSummary, ManifestEntry, QualityReport, TrendPoint


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_manifest(path: Path) -> list[ManifestEntry]:
    """Stream JSONL manifest into ManifestEntry list.

    Returns empty list if file missing or empty.
    """
    if not path.exists():
        return []
    entries: list[ManifestEntry] = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(ManifestEntry.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                continue  # skip malformed lines
    return entries


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def filter_entries(
    entries: list[ManifestEntry],
    *,
    category: str | None = None,
    status: str | None = None,
    since_hours: float | None = None,
) -> list[ManifestEntry]:
    """Filter entries by category, status, and/or recency."""
    result = entries

    if category:
        result = [e for e in result if e.category == category]

    if status:
        result = [e for e in result if e.status == status]

    if since_hours is not None and since_hours > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        filtered = []
        for e in result:
            if e.processing_finished:
                try:
                    ts = _parse_ts(e.processing_finished)
                    if ts >= cutoff:
                        filtered.append(e)
                except (ValueError, TypeError):
                    continue
        result = filtered

    return result


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def compute_summary(entries: list[ManifestEntry]) -> CorpusSummary:
    """Compute high-level corpus counts and distributions."""
    s = CorpusSummary(total=len(entries))

    categories: dict[str, int] = {}
    presets: dict[str, int] = {}
    labels: dict[str, int] = {}
    durations: list[float] = []
    total_pages = 0
    total_size = 0.0

    for e in entries:
        # Status counts
        if e.status == "completed":
            s.completed += 1
        elif e.status == "pending":
            s.pending += 1
        elif e.status == "failed":
            s.failed += 1
        elif e.status == "processing":
            s.processing += 1

        # Category distribution
        cat = e.category or "uncategorized"
        categories[cat] = categories.get(cat, 0) + 1

        # Preset distribution
        if e.s00_preset:
            presets[e.s00_preset] = presets.get(e.s00_preset, 0) + 1

        # Label distribution
        if e.s00_s04_label:
            labels[e.s00_s04_label] = labels.get(e.s00_s04_label, 0) + 1

        # Aggregates
        if e.duration_sec is not None:
            durations.append(float(e.duration_sec))
        if e.page_count is not None:
            total_pages += e.page_count
        if e.file_size_mb is not None:
            total_size += e.file_size_mb

    s.categories = dict(sorted(categories.items(), key=lambda kv: -kv[1]))
    s.presets = dict(sorted(presets.items(), key=lambda kv: -kv[1]))
    s.label_distribution = dict(sorted(labels.items(), key=lambda kv: -kv[1]))
    s.median_duration_sec = statistics.median(durations) if durations else None
    s.total_pages = total_pages
    s.total_size_mb = round(total_size, 2)

    return s


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

def compute_quality(entries: list[ManifestEntry]) -> QualityReport:
    """Compute S00/S04 ratio analysis.

    Ratio = s04_actual / s00_estimated.  Ratio near 1.0 means S00 was
    accurate.  >1.0 means S00 underestimated.  <1.0 means overestimated.
    """
    q = QualityReport()

    # Label counts
    labels: dict[str, int] = {}
    for e in entries:
        if e.s00_s04_label:
            labels[e.s00_s04_label] = labels.get(e.s00_s04_label, 0) + 1
    q.label_counts = dict(sorted(labels.items(), key=lambda kv: -kv[1]))

    # Ratio histogram
    with_ratio = [e for e in entries if e.s00_s04_ratio is not None]
    q.total_with_ratio = len(with_ratio)

    histogram: dict[str, int] = {}
    for lo, hi, label in RATIO_HISTOGRAM_BUCKETS:
        count = sum(1 for e in with_ratio if lo <= (e.s00_s04_ratio or 0) < hi)
        histogram[label] = count
    q.ratio_histogram = histogram

    # Good / acceptable percentages
    if with_ratio:
        good = sum(1 for e in with_ratio if 0.8 <= (e.s00_s04_ratio or 0) < 1.2)
        acceptable = sum(1 for e in with_ratio if 0.5 <= (e.s00_s04_ratio or 0) < 2.0)
        q.good_pct = round(good / len(with_ratio) * 100, 1)
        q.acceptable_pct = round(acceptable / len(with_ratio) * 100, 1)

    # Worst offenders -- entries furthest from 1.0
    scored = [
        (abs((e.s00_s04_ratio or 1.0) - 1.0), e)
        for e in with_ratio
    ]
    scored.sort(key=lambda t: -t[0])
    q.worst_offenders = [
        {
            "filename": e.filename,
            "ratio": e.s00_s04_ratio,
            "label": e.s00_s04_label or "",
            "estimated": e.s00_estimated_sections,
            "actual": e.s04_actual_sections,
            "category": e.category,
        }
        for _, e in scored[:10]
    ]

    return q


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------

def compute_trends(
    entries: list[ManifestEntry],
    window_hours: float = 6,
) -> list[TrendPoint]:
    """Group completed entries by processing_finished into time windows.

    Returns list of TrendPoint sorted chronologically.
    """
    # Collect entries with timestamps
    timestamped: list[tuple[datetime, ManifestEntry]] = []
    for e in entries:
        if e.processing_finished and e.status == "completed":
            try:
                ts = _parse_ts(e.processing_finished)
                timestamped.append((ts, e))
            except (ValueError, TypeError):
                continue

    if not timestamped:
        return []

    timestamped.sort(key=lambda t: t[0])

    # Build windows
    window_delta = timedelta(hours=window_hours)
    first_ts = timestamped[0][0]
    last_ts = timestamped[-1][0]

    points: list[TrendPoint] = []
    window_start = first_ts

    while window_start <= last_ts:
        window_end = window_start + window_delta
        bucket = [e for ts, e in timestamped if window_start <= ts < window_end]

        if bucket:
            ratios = [e.s00_s04_ratio for e in bucket if e.s00_s04_ratio is not None]
            durations = [float(e.duration_sec) for e in bucket if e.duration_sec is not None]
            good = sum(1 for r in ratios if 0.8 <= r < 1.2) if ratios else 0
            acceptable = sum(1 for r in ratios if 0.5 <= r < 2.0) if ratios else 0

            points.append(TrendPoint(
                window_label=window_start.strftime("%Y-%m-%d %H:%M"),
                count=len(bucket),
                good_pct=round(good / len(ratios) * 100, 1) if ratios else 0.0,
                acceptable_pct=round(acceptable / len(ratios) * 100, 1) if ratios else 0.0,
                median_ratio=round(statistics.median(ratios), 3) if ratios else None,
                median_duration_sec=round(statistics.median(durations), 1) if durations else None,
            ))

        window_start = window_end

    return points


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(value: str) -> datetime:
    """Parse ISO-8601 timestamp, tolerating missing timezone."""
    value = value.strip()
    # Try standard ISO parse first
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        # Fallback: strip trailing Z and retry
        dt = datetime.fromisoformat(value.rstrip("Z"))

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
