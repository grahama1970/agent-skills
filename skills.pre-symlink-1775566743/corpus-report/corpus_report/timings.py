"""Scan result directories for timings_summary.json and aggregate."""
from __future__ import annotations

import json
import random
import statistics
from pathlib import Path

from .models import BottleneckReport, StageTiming


def scan_timings(
    results_dir: Path,
    *,
    sample: int | None = None,
) -> list[dict]:
    """Read timings_summary.json from completed result directories.

    Args:
        results_dir: Root results directory (contains per-PDF subdirs).
        sample: If set, randomly sample this many directories.

    Returns:
        List of raw timing dicts (one per PDF).
    """
    if not results_dir.exists():
        return []

    # Collect all dirs that contain timings_summary.json
    timing_files = sorted(results_dir.glob("*/timings_summary.json"))

    if sample and sample < len(timing_files):
        timing_files = random.sample(timing_files, sample)

    raw: list[dict] = []
    for tf in timing_files:
        try:
            with open(tf) as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                raw.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return raw


def aggregate_timings(raw: list[dict]) -> BottleneckReport:
    """Aggregate per-PDF timing data into a bottleneck report.

    Handles multiple formats:
      List: {"stages": [{"name": "s01", "latency_ms": 123}, ...], "total_ms": 1234}
      Dict: {"stages": {"s01": 123.4, ...}, "total_ms": 1234}
      Flat: {"s01_ms": 123.4, "total_ms": 1234}
    """
    if not raw:
        return BottleneckReport()

    # Collect per-stage times across all files
    stage_times: dict[str, list[float]] = {}
    totals: list[float] = []

    for entry in raw:
        total = entry.get("total_ms", 0.0)
        if total:
            totals.append(float(total))

        stages_raw = entry.get("stages", {})

        # Format 1: list of {"name": ..., "latency_ms": ...}
        if isinstance(stages_raw, list):
            for item in stages_raw:
                if not isinstance(item, dict):
                    continue
                name = item.get("name", "")
                ms = item.get("latency_ms", item.get("ms", 0))
                if name and isinstance(ms, (int, float)):
                    stage_times.setdefault(name, []).append(float(ms))

        # Format 2: dict of {"stage_name": ms_value}
        elif isinstance(stages_raw, dict) and stages_raw:
            for stage_name, ms in stages_raw.items():
                if isinstance(ms, (int, float)):
                    stage_times.setdefault(stage_name, []).append(float(ms))

        # Format 3: flat keys like "s01_ms"
        else:
            for k, v in entry.items():
                if k.endswith("_ms") and k != "total_ms" and isinstance(v, (int, float)):
                    stage_times.setdefault(k.replace("_ms", ""), []).append(float(v))

    avg_total = statistics.mean(totals) if totals else 0.0

    # Build stage timings sorted by avg descending (worst first)
    stage_list: list[StageTiming] = []
    for name, times in stage_times.items():
        avg = statistics.mean(times)
        stage_list.append(StageTiming(
            name=name,
            avg_ms=round(avg, 1),
            median_ms=round(statistics.median(times), 1),
            max_ms=round(max(times), 1),
            pct_of_total=round(avg / avg_total * 100, 1) if avg_total else 0.0,
        ))

    stage_list.sort(key=lambda s: -s.avg_ms)

    return BottleneckReport(
        files_sampled=len(raw),
        stages=stage_list,
        avg_total_ms=round(avg_total, 1),
    )
