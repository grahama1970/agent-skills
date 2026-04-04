"""Data source adapters for collecting timeout training data."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from lib.features import TaskFeatures

# Memory client (optional — graceful degradation if unavailable)
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient, MemoryScope
    _HAS_MEMORY = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source_from_path(name: str) -> str:
    """Infer corpus source from directory name."""
    name = name.lower()
    for tag in ("arxiv", "nasa", "nist", "faa", "ietf", "defense"):
        if tag in name:
            return tag
    if name.startswith("government"):
        return "government"
    if name.startswith("standards") or name.startswith("ecss"):
        return "standards"
    if name.startswith("engineering"):
        return "engineering"
    if name.startswith("adversarial"):
        return "adversarial"
    if "archive" in name:
        return "archive_org"
    return "other"


def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        pass
    return rows


# ---------------------------------------------------------------------------
# 1) Corpus Timings Adapter
# ---------------------------------------------------------------------------

class CorpusTimingsAdapter:
    """Reads profile.json + timings.jsonl from extractor corpus results."""

    def __init__(self, corpus_dir: Path) -> None:
        self.results_dir = corpus_dir / "results"

    def collect(self) -> list[TaskFeatures]:
        if not self.results_dir.is_dir():
            logger.warning(f"Corpus results dir not found: {self.results_dir}")
            return []

        samples: list[TaskFeatures] = []
        for result_dir in sorted(self.results_dir.iterdir()):
            if not result_dir.is_dir():
                continue
            feat = self._extract(result_dir)
            if feat:
                samples.append(feat)

        logger.info(f"CorpusTimingsAdapter: collected {len(samples)} samples")
        return samples

    def _extract(self, result_dir: Path) -> Optional[TaskFeatures]:
        profile = _load_json(result_dir / "00_profile_detector" / "profile.json")
        if not profile:
            return None

        # Aggregate timing
        total_ms = self._total_duration_ms(result_dir, profile)
        if total_ms <= 0:
            return None

        elements = profile.get("elements", {})
        hierarchy = profile.get("hierarchy", {})
        layout = profile.get("layout", {})

        return TaskFeatures(
            task_type="pdf_extraction",
            page_count=profile.get("page_count", 0),
            file_size_mb=profile.get("file_size_mb", 0.0),
            table_pages=elements.get("table_pages", 0),
            estimated_table_count=elements.get("estimated_table_count", 0),
            image_pages=elements.get("image_pages", 0),
            has_tables=elements.get("tables", False),
            has_figures=elements.get("figures", False),
            has_formulas=elements.get("formulas", False),
            has_requirements=elements.get("requirements", False),
            estimated_sections=hierarchy.get("estimated_sections", 0),
            domain=profile.get("domain", "general"),
            source=_source_from_path(result_dir.name),
            layout_columns=layout.get("columns", 1) if isinstance(layout, dict) else 1,
            max_tables_per_page=elements.get("max_tables_per_page", 0),
            actual_duration_s=total_ms / 1000.0,
            timed_out=False,
        )

    def _total_duration_ms(self, result_dir: Path, profile: dict) -> float:
        """Get total pipeline duration in ms from manifest or timings."""
        manifest = _load_json(result_dir / "manifest.json")
        if manifest and "timings_ms" in manifest:
            return sum(manifest["timings_ms"].values())

        rows = _load_jsonl(result_dir / "timings.jsonl")
        if rows:
            return sum(r.get("latency_ms", 0) for r in rows)

        return 0.0


# ---------------------------------------------------------------------------
# 2) Run Log Adapter
# ---------------------------------------------------------------------------

class RunLogAdapter:
    """Parses supervisor run logs for extract_timeout events."""

    TIMEOUT_RE = re.compile(
        r"extract_timeout.*?"
        r"page_count[=:](\d+).*?"
        r"timeout[=:](\d+)",
        re.IGNORECASE,
    )

    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = logs_dir

    def collect(self) -> list[TaskFeatures]:
        if not self.logs_dir.is_dir():
            logger.warning(f"Logs dir not found: {self.logs_dir}")
            return []

        samples: list[TaskFeatures] = []
        for log_file in sorted(self.logs_dir.glob("**/*.log")):
            samples.extend(self._parse_log(log_file))

        for log_file in sorted(self.logs_dir.glob("**/*.jsonl")):
            samples.extend(self._parse_jsonl_log(log_file))

        logger.info(f"RunLogAdapter: collected {len(samples)} samples")
        return samples

    def _parse_log(self, path: Path) -> list[TaskFeatures]:
        results: list[TaskFeatures] = []
        try:
            text = path.read_text(errors="replace")
        except OSError:
            return results

        for m in self.TIMEOUT_RE.finditer(text):
            page_count = int(m.group(1))
            timeout_s = int(m.group(2))
            results.append(TaskFeatures(
                task_type="pdf_extraction",
                page_count=page_count,
                actual_duration_s=float(timeout_s),
                timed_out=True,
            ))

        return results

    def _parse_jsonl_log(self, path: Path) -> list[TaskFeatures]:
        results: list[TaskFeatures] = []
        for row in _load_jsonl(path):
            if "extract_timeout" not in str(row.get("event", "")):
                continue
            results.append(TaskFeatures(
                task_type="pdf_extraction",
                page_count=row.get("page_count", 0),
                file_size_mb=row.get("file_size_mb", 0.0),
                actual_duration_s=row.get("timeout_seconds", row.get("actual_seconds", 0.0)),
                timed_out=row.get("timed_out", True),
            ))

        return results


# ---------------------------------------------------------------------------
# 3) Supervisor Report Adapter
# ---------------------------------------------------------------------------

class SupervisorReportAdapter:
    """Reads aggregate.json from supervisor batch reports."""

    def __init__(self, reports_dir: Path) -> None:
        self.reports_dir = reports_dir

    def collect(self) -> list[TaskFeatures]:
        if not self.reports_dir.is_dir():
            logger.warning(f"Reports dir not found: {self.reports_dir}")
            return []

        samples: list[TaskFeatures] = []
        for agg in sorted(self.reports_dir.glob("**/aggregate.json")):
            data = _load_json(agg)
            if not data:
                continue
            for item in data.get("items", []):
                feat = self._parse_item(item)
                if feat:
                    samples.append(feat)

        logger.info(f"SupervisorReportAdapter: collected {len(samples)} samples")
        return samples

    def _parse_item(self, item: dict) -> Optional[TaskFeatures]:
        duration = item.get("extraction_duration_s", item.get("duration_s"))
        if not duration:
            return None

        return TaskFeatures(
            task_type="pdf_extraction",
            page_count=item.get("page_count", 0),
            file_size_mb=item.get("file_size_mb", 0.0),
            has_tables=item.get("has_tables", False),
            domain=item.get("domain", "general"),
            source=item.get("source", "unknown"),
            actual_duration_s=float(duration),
            timed_out=item.get("timed_out", False),
        )


# ---------------------------------------------------------------------------
# 4) Observation Adapter (feedback loop)
# ---------------------------------------------------------------------------

class ObservationAdapter:
    """Reads observed outcomes from data/observations.jsonl."""

    def __init__(self, observations_path: Path) -> None:
        self.path = observations_path

    def collect(self) -> list[TaskFeatures]:
        if not self.path.exists():
            return []

        samples: list[TaskFeatures] = []
        for row in _load_jsonl(self.path):
            feat_raw = row.get("features", {})
            feat = TaskFeatures(
                task_type=feat_raw.get("task_type", "pdf_extraction"),
                page_count=feat_raw.get("page_count", 0),
                file_size_mb=feat_raw.get("file_size_mb", 0.0),
                table_pages=feat_raw.get("table_pages", 0),
                estimated_table_count=feat_raw.get("estimated_table_count", 0),
                image_pages=feat_raw.get("image_pages", 0),
                has_tables=feat_raw.get("has_tables", False),
                has_figures=feat_raw.get("has_figures", False),
                has_formulas=feat_raw.get("has_formulas", False),
                has_requirements=feat_raw.get("has_requirements", False),
                estimated_sections=feat_raw.get("estimated_sections", 0),
                domain=feat_raw.get("domain", "general"),
                source=feat_raw.get("source", "unknown"),
                prompt_tokens=feat_raw.get("prompt_tokens", 0),
                model=feat_raw.get("model", ""),
                provider=feat_raw.get("provider", ""),
                actual_duration_s=row.get("actual_seconds", 0.0),
                timed_out=row.get("timed_out", False),
            )
            if feat.actual_duration_s and feat.actual_duration_s > 0:
                samples.append(feat)

        logger.info(f"ObservationAdapter: collected {len(samples)} samples")
        return samples


# ---------------------------------------------------------------------------
# 5) Memory Execution Adapter (dogpile provider metrics)
# ---------------------------------------------------------------------------

class MemoryExecutionAdapter:
    """Reads dogpile execution metadata from /memory.

    Queries records tagged ``dogpile_exec`` and converts them into
    TaskFeatures with ``task_type="subprocess"`` and
    ``command_type="dogpile_{provider}"``.
    """

    def __init__(self, max_records: int = 500) -> None:
        self.max_records = max_records

    def collect(self) -> list[TaskFeatures]:
        if not _HAS_MEMORY:
            logger.debug("MemoryExecutionAdapter: memory client not available")
            return []

        try:
            client = MemoryClient(scope=MemoryScope.OPERATIONAL)
            result = client.recall(
                "dogpile exec",
                k=self.max_records,
            )
            if not result.found:
                logger.info("MemoryExecutionAdapter: no dogpile_exec records found")
                return []

            samples: list[TaskFeatures] = []
            for item in result.items:
                feat = self._parse_item(item)
                if feat:
                    samples.append(feat)

            logger.info(f"MemoryExecutionAdapter: collected {len(samples)} samples")
            return samples

        except Exception as e:
            logger.warning(f"MemoryExecutionAdapter: recall failed: {e}")
            return []

    def _parse_item(self, item) -> Optional[TaskFeatures]:
        """Parse a memory recall item into TaskFeatures."""
        try:
            solution = item.solution if hasattr(item, "solution") else item.get("solution", "")
            data = json.loads(solution)
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

        wall_clock = data.get("wall_clock_s", 0.0)
        if not wall_clock or wall_clock <= 0:
            return None

        provider = data.get("provider", "unknown")
        outcome = data.get("outcome", "success")

        return TaskFeatures(
            task_type="subprocess",
            command_type=f"dogpile_{provider}",
            actual_duration_s=float(wall_clock),
            timed_out=(outcome == "timeout"),
            provider=provider,
            source="dogpile",
            domain="search",
        )
