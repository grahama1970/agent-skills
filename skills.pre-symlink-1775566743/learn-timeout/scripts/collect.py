"""Collect training data from all available sources."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

import typer
from loguru import logger

# Ensure lib/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.features import TaskFeatures, features_to_dict
from lib.sources import (
    CorpusTimingsAdapter,
    MemoryExecutionAdapter,
    ObservationAdapter,
    RunLogAdapter,
    SupervisorReportAdapter,
)

app = typer.Typer(add_completion=False)

# Default paths — overridable via env
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
CORPUS_DIR = Path(os.environ.get(
    "EXTRACTOR_CORPUS_DIR",
    str(_EMBRY_STORAGE / "extractor_corpus"),
))
LOGS_DIR = Path(os.environ.get(
    "SUPERVISOR_LOGS_DIR",
    str(_EMBRY_STORAGE / "supervisor/logs"),
))
REPORTS_DIR = Path(os.environ.get(
    "SUPERVISOR_REPORTS_DIR",
    str(_EMBRY_STORAGE / "supervisor/reports"),
))
OBSERVATIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "observations.jsonl"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "training_data.jsonl"


def _deduplicate(samples: list[TaskFeatures]) -> list[TaskFeatures]:
    """Deduplicate by (task_type, page_count, file_size_mb, actual_duration_s)."""
    seen: set[tuple] = set()
    unique: list[TaskFeatures] = []
    for s in samples:
        key = (s.task_type, s.page_count, round(s.file_size_mb, 2), round(s.actual_duration_s or 0, 1))
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


@app.command()
def main(
    corpus_dir: Path = typer.Option(CORPUS_DIR, help="Path to extractor corpus"),
    logs_dir: Path = typer.Option(LOGS_DIR, help="Path to supervisor logs"),
    reports_dir: Path = typer.Option(REPORTS_DIR, help="Path to supervisor reports"),
    output: Path = typer.Option(OUTPUT_PATH, help="Output JSONL path"),
) -> None:
    """Gather training data from all sources."""
    all_samples: list[TaskFeatures] = []

    # 1) Corpus timings
    adapter1 = CorpusTimingsAdapter(corpus_dir)
    all_samples.extend(adapter1.collect())

    # 2) Run logs
    adapter2 = RunLogAdapter(logs_dir)
    all_samples.extend(adapter2.collect())

    # 3) Supervisor reports
    adapter3 = SupervisorReportAdapter(reports_dir)
    all_samples.extend(adapter3.collect())

    # 4) Observations (feedback loop)
    adapter4 = ObservationAdapter(OBSERVATIONS_PATH)
    all_samples.extend(adapter4.collect())

    # 5) Dogpile execution metadata from /memory
    adapter5 = MemoryExecutionAdapter()
    all_samples.extend(adapter5.collect())

    # Filter out samples without duration
    all_samples = [s for s in all_samples if s.actual_duration_s and s.actual_duration_s > 0]

    # Deduplicate
    unique = _deduplicate(all_samples)

    # Write output
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for s in unique:
            row = {
                "task_type": s.task_type,
                "page_count": s.page_count,
                "file_size_mb": s.file_size_mb,
                "table_pages": s.table_pages,
                "estimated_table_count": s.estimated_table_count,
                "image_pages": s.image_pages,
                "has_tables": s.has_tables,
                "has_figures": s.has_figures,
                "has_formulas": s.has_formulas,
                "has_requirements": s.has_requirements,
                "estimated_sections": s.estimated_sections,
                "domain": s.domain,
                "source": s.source,
                "layout_columns": s.layout_columns,
                "max_tables_per_page": s.max_tables_per_page,
                "prompt_tokens": s.prompt_tokens,
                "actual_duration_s": s.actual_duration_s,
                "timed_out": s.timed_out,
            }
            f.write(json.dumps(row) + "\n")

    # Summary
    timeout_count = sum(1 for s in unique if s.timed_out)
    by_type: dict[str, int] = {}
    for s in unique:
        by_type[s.task_type] = by_type.get(s.task_type, 0) + 1

    logger.info(f"Collection complete: {len(unique)} unique samples")
    logger.info(f"  Timeout events: {timeout_count}")
    logger.info(f"  By task_type: {by_type}")
    logger.info(f"  Written to: {output}")


if __name__ == "__main__":
    app()
