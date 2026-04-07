"""
Paper Writer Skill - Shadow Quality Tracking (Shadow-LEGO integration)

Self-improvement loop for section generation quality. Tracks:
  - Heuristic critique (Tier 0) vs LLM critique (Tier 2) agreement
  - Per-section quality scores across paper generations
  - Lessons learned from each run

This is the meta-recursive property: the paper about Shadow-LEGO uses
Shadow-LEGO methodology for its own quality assessment.
"""
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# Default paths
DEFAULT_SHADOW_DIR = Path("~/.pi/create-paper").expanduser()
DEFAULT_LESSONS_FILE = DEFAULT_SHADOW_DIR / "lessons.jsonl"
DEFAULT_SHADOW_FILE = DEFAULT_SHADOW_DIR / "shadow.jsonl"
DEFAULT_METRICS_FILE = DEFAULT_SHADOW_DIR / "metrics.jsonl"


@dataclass
class SectionQuality:
    """Quality assessment for a single paper section."""
    section_key: str
    word_count: int
    target_min: int
    target_max: int
    within_target: bool
    citation_count: int
    heuristic_scores: Dict[str, int] = field(default_factory=dict)
    llm_scores: Dict[str, int] = field(default_factory=dict)
    persona_name: str = ""
    persona_strength: float = 0.0


@dataclass
class LessonLearned:
    """Single lesson from a paper generation run."""
    timestamp: str
    paper_id: str
    phase: str  # "generation", "critique", "citation", "submission"
    category: str  # "success", "failure", "warning", "insight"
    description: str
    section_key: str = ""
    metric_before: float = 0.0
    metric_after: float = 0.0
    action_taken: str = ""


def log_lesson(
    paper_id: str,
    phase: str,
    category: str,
    description: str,
    section_key: str = "",
    metric_before: float = 0.0,
    metric_after: float = 0.0,
    action_taken: str = "",
    lessons_file: Optional[Path] = None,
) -> None:
    """Append a lesson learned to the lessons log.

    Args:
        paper_id: Unique identifier for this paper run
        phase: Pipeline phase (generation, critique, citation, submission)
        category: Lesson type (success, failure, warning, insight)
        description: What happened and what was learned
        section_key: Optional section this applies to
        metric_before: Optional metric value before action
        metric_after: Optional metric value after action
        action_taken: Optional remediation action
        lessons_file: Path to lessons JSONL file
    """
    lf = (lessons_file or DEFAULT_LESSONS_FILE)
    lf.parent.mkdir(parents=True, exist_ok=True)

    lesson = LessonLearned(
        timestamp=datetime.now(timezone.utc).isoformat(),
        paper_id=paper_id,
        phase=phase,
        category=category,
        description=description,
        section_key=section_key,
        metric_before=metric_before,
        metric_after=metric_after,
        action_taken=action_taken,
    )

    try:
        with open(lf, "a") as f:
            f.write(json.dumps(asdict(lesson), ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"Failed to log lesson: {e}")


def log_section_shadow(
    paper_id: str,
    section: SectionQuality,
    shadow_file: Optional[Path] = None,
) -> None:
    """Log shadow comparison between heuristic and LLM critique scores.

    When both heuristic and LLM scores are available, track agreement.
    This is the cascade shadow for create-paper's critique pipeline.
    """
    sf = (shadow_file or DEFAULT_SHADOW_FILE)
    sf.parent.mkdir(parents=True, exist_ok=True)

    if not section.heuristic_scores or not section.llm_scores:
        return

    # Compare scores across shared aspects
    shared_aspects = set(section.heuristic_scores) & set(section.llm_scores)
    if not shared_aspects:
        return

    agreements = 0
    for aspect in shared_aspects:
        h_score = section.heuristic_scores[aspect]
        l_score = section.llm_scores[aspect]
        # Agree if within 1 point on 5-point scale
        if abs(h_score - l_score) <= 1:
            agreements += 1

    agreement_rate = agreements / len(shared_aspects)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "paper_id": paper_id,
        "section_key": section.section_key,
        "heuristic_scores": section.heuristic_scores,
        "llm_scores": section.llm_scores,
        "aspects_compared": len(shared_aspects),
        "agreements": agreements,
        "agreement_rate": round(agreement_rate, 4),
        "persona": section.persona_name,
        "word_count": section.word_count,
    }

    try:
        with open(sf, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"Failed to log section shadow: {e}")


def shadow_report(hours: int = 168, shadow_file: Optional[Path] = None) -> Dict[str, Any]:
    """Compute shadow agreement stats for create-paper critique.

    Args:
        hours: Look-back window (default 7 days)
        shadow_file: Path to shadow JSONL

    Returns:
        Dict with total, agree, disagree, agreement_rate, status, per-section breakdown
    """
    sf = (shadow_file or DEFAULT_SHADOW_FILE)
    if not sf.exists():
        return {"total": 0, "agreement_rate": 0.0, "status": "no_data"}

    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    entries = []

    for line in sf.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
            if ts >= cutoff:
                entries.append(entry)
        except (json.JSONDecodeError, KeyError):
            continue

    if not entries:
        return {"total": 0, "agreement_rate": 0.0, "status": "no_data"}

    total_aspects = sum(e.get("aspects_compared", 0) for e in entries)
    total_agreed = sum(e.get("agreements", 0) for e in entries)
    rate = total_agreed / total_aspects if total_aspects > 0 else 0.0

    # Per-section breakdown
    by_section: Dict[str, List[float]] = {}
    for e in entries:
        sk = e.get("section_key", "unknown")
        by_section.setdefault(sk, []).append(e.get("agreement_rate", 0.0))

    section_rates = {
        sk: round(sum(rates) / len(rates), 4)
        for sk, rates in by_section.items()
    }

    status = "ready" if rate >= 0.90 else "learning" if rate >= 0.70 else "early"

    return {
        "total": len(entries),
        "aspects_compared": total_aspects,
        "aspects_agreed": total_agreed,
        "agreement_rate": round(rate, 4),
        "status": status,
        "by_section": section_rates,
    }


def lessons_summary(
    paper_id: str = "",
    last_n: int = 50,
    lessons_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Summarize lessons learned from paper generation runs.

    Args:
        paper_id: Filter to specific paper (empty = all)
        last_n: Maximum entries to consider
        lessons_file: Path to lessons JSONL

    Returns:
        Dict with counts by category, recent lessons, recurring patterns
    """
    lf = (lessons_file or DEFAULT_LESSONS_FILE)
    if not lf.exists():
        return {"total": 0, "by_category": {}, "recent": []}

    entries = []
    for line in lf.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if paper_id and entry.get("paper_id") != paper_id:
                continue
            entries.append(entry)
        except json.JSONDecodeError:
            continue

    entries = entries[-last_n:]

    by_category: Dict[str, int] = {}
    by_phase: Dict[str, int] = {}
    for e in entries:
        cat = e.get("category", "unknown")
        phase = e.get("phase", "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1
        by_phase[phase] = by_phase.get(phase, 0) + 1

    return {
        "total": len(entries),
        "by_category": by_category,
        "by_phase": by_phase,
        "recent": entries[-5:],
    }
