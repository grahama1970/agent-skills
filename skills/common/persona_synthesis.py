"""Generic focused conversation runner for persona synthesis.

Extracts the reusable conversation pattern from sparta-stress-test into
a domain-agnostic runner. Domain-specific question generation is pluggable
via QuestionSource callbacks.

Usage:
    from common.persona_synthesis import (
        QuestionSource, SynthesisConfig, SynthesisResult,
        run_batch_synthesis,
    )

    config = SynthesisConfig(
        respond_fn=my_persona.respond,
        scope="my_domain",
        question_sources=[
            QuestionSource("source_a", 0.5, generate_a),
            QuestionSource("source_b", 0.5, generate_b),
        ],
    )
    questions = generate_questions(config, count=100)
    summary = run_batch_synthesis(questions, config)
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from .paths import SYNTHESIS_DIR

__all__ = [
    "QuestionSource",
    "SynthesisConfig",
    "SynthesisResult",
    "generate_questions",
    "run_batch_synthesis",
]


@dataclass
class QuestionSource:
    """Pluggable question generator — replaces hardcoded Source A/B/C/D.

    Attrs:
        name: Short identifier (e.g. "f36_lessons", "qra_adversarial").
        weight: Sampling weight (0.0-1.0). Weights are normalized at generation time.
        generate_fn: Callable(persona_name, count) -> list[dict].
            Each dict must have at least {"question": str, "persona": str}.
            May also include id, source, difficulty, bridge_tags, etc.
    """

    name: str
    weight: float
    generate_fn: Callable[[str, int], list[dict]]


@dataclass
class SynthesisResult:
    """Result of a single focused conversation turn."""

    persona: str
    question: str
    source: str = ""
    response_text: str = ""
    response_confidence: str = ""
    qras_used: int = 0
    synthesis_triggered: bool = False
    items_before: int = -1
    items_after: int = -1
    items_captured: int = 0
    avg_grounding: float = 0.0
    feedback_logged: bool = False
    error: str = ""
    duration_s: float = 0.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items()}


@dataclass
class SynthesisConfig:
    """Configuration for a focused conversation batch.

    Attrs:
        respond_fn: persona.respond(question_text) -> dict with at least
            {confidence, qras_used, avg_grounding}.
        count_fn: Optional callable returning domain item count (e.g. QRA count).
            Used for before/after measurement.
        feedback_check_fn: Optional callable returning int (feedback entry count).
            Used to detect whether subgraph feedback was logged.
        scope: Memory scope for this domain.
        question_sources: Pluggable question generators with weights.
        results_dir: Where to write result JSONL files.
        batch_log_interval: Log progress every N conversations.
    """

    respond_fn: Callable[[str], dict]
    scope: str
    question_sources: list[QuestionSource]
    count_fn: Optional[Callable[[], int]] = None
    feedback_check_fn: Optional[Callable[[], int]] = None
    results_dir: Path = SYNTHESIS_DIR
    batch_log_interval: int = 50


def generate_questions(
    config: SynthesisConfig,
    count: int,
    persona_name: str = "",
) -> list[dict]:
    """Generate questions from weighted sources.

    Distributes ``count`` across sources proportional to their weights,
    then calls each source's generate_fn.

    Args:
        config: SynthesisConfig with question_sources.
        count: Total questions to generate.
        persona_name: Persona name passed to generators.

    Returns:
        Shuffled list of question dicts.
    """
    sources = config.question_sources
    if not sources:
        return []

    total_weight = sum(s.weight for s in sources)
    if total_weight <= 0:
        return []

    questions: list[dict] = []
    for source in sources:
        n = max(1, int(count * source.weight / total_weight))
        try:
            qs = source.generate_fn(persona_name, n)
            for q in qs:
                q.setdefault("source", source.name)
            questions.extend(qs)
        except Exception as e:
            logger.warning(f"Question source '{source.name}' failed: {e}")

    random.shuffle(questions)
    return questions[:count]


def run_synthesis_conversation(
    question: dict,
    config: SynthesisConfig,
) -> SynthesisResult:
    """Run a single focused conversation turn.

    Measures items before/after, calls respond_fn, checks feedback.

    Args:
        question: Dict with at least {"question": str, "persona": str}.
        config: SynthesisConfig with respond_fn, count_fn, etc.

    Returns:
        SynthesisResult with metrics.
    """
    persona = question.get("persona", "")
    q_text = question.get("question", "")

    result = SynthesisResult(
        persona=persona,
        question=q_text,
        source=question.get("source", ""),
    )
    start = time.monotonic()

    try:
        # Count domain items before
        if config.count_fn is not None:
            result.items_before = config.count_fn()

        # Count feedback entries before
        feedback_before = 0
        if config.feedback_check_fn is not None:
            feedback_before = config.feedback_check_fn()

        # Run the conversation
        response = config.respond_fn(q_text)

        result.response_confidence = str(response.get("confidence", ""))
        result.qras_used = response.get("qras_used", 0)
        result.avg_grounding = response.get("avg_grounding", 0.0)
        result.response_text = str(response.get("response", response.get("text", "")))[:500]
        result.synthesis_triggered = result.qras_used >= 2

        # Count domain items after
        if config.count_fn is not None:
            result.items_after = config.count_fn()
            if result.items_before >= 0 and result.items_after >= 0:
                result.items_captured = max(
                    0, result.items_after - result.items_before
                )

        # Check if feedback was logged
        if config.feedback_check_fn is not None:
            feedback_after = config.feedback_check_fn()
            result.feedback_logged = feedback_after > feedback_before

    except Exception as e:
        import traceback
        result.error = str(e)
        logger.warning(f"Synthesis conversation failed: {e}\n{traceback.format_exc()}")

    result.duration_s = round(time.monotonic() - start, 2)
    return result


def run_batch_synthesis(
    questions: list[dict],
    config: SynthesisConfig,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run batch focused conversations with progress logging.

    Args:
        questions: List of question dicts.
        config: SynthesisConfig with respond_fn, etc.
        output_path: Override output JSONL path.

    Returns:
        Summary dict with aggregate metrics.
    """
    if output_path is None:
        config.results_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        output_path = config.results_dir / f"synthesis_{config.scope}_{ts}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[SynthesisResult] = []
    start = time.monotonic()
    total_items_captured = 0
    total_synthesis = 0
    total_feedback = 0

    logger.info(
        f"Starting {len(questions)} synthesis conversations "
        f"(scope={config.scope}, batch_interval={config.batch_log_interval})"
    )

    with open(output_path, "w") as f:
        for i, question in enumerate(questions):
            result = run_synthesis_conversation(question, config)
            results.append(result)

            f.write(json.dumps(result.to_dict(), default=str) + "\n")
            f.flush()

            total_items_captured += result.items_captured
            if result.synthesis_triggered:
                total_synthesis += 1
            if result.feedback_logged:
                total_feedback += 1

            if (i + 1) % config.batch_log_interval == 0 or (i + 1) == len(questions):
                elapsed = time.monotonic() - start
                rate = (i + 1) / elapsed * 60 if elapsed > 0 else 0
                logger.info(
                    f"Progress: {i+1}/{len(questions)} "
                    f"({rate:.0f}/min) "
                    f"synthesis={total_synthesis} "
                    f"items_captured={total_items_captured} "
                    f"feedback={total_feedback}"
                )

    elapsed = time.monotonic() - start
    errors = sum(1 for r in results if r.error)
    grounding_values = [r.avg_grounding for r in results if r.avg_grounding > 0]
    avg_grounding = (
        sum(grounding_values) / len(grounding_values) if grounding_values else 0.0
    )

    # Per-persona breakdown
    personas_seen: dict[str, list[SynthesisResult]] = {}
    for r in results:
        personas_seen.setdefault(r.persona, []).append(r)

    by_persona: dict[str, dict] = {}
    for persona, p_results in sorted(personas_seen.items()):
        p_grounding = [r.avg_grounding for r in p_results if r.avg_grounding > 0]
        by_persona[persona] = {
            "total": len(p_results),
            "synthesis_triggered": sum(1 for r in p_results if r.synthesis_triggered),
            "items_captured": sum(r.items_captured for r in p_results),
            "avg_grounding": round(
                sum(p_grounding) / len(p_grounding) if p_grounding else 0.0, 3
            ),
        }

    summary = {
        "scope": config.scope,
        "questions_asked": len(questions),
        "conversations_completed": len(results) - errors,
        "errors": errors,
        "synthesis_triggered": total_synthesis,
        "synthesis_rate": round(total_synthesis / max(1, len(results)), 3),
        "items_captured": total_items_captured,
        "avg_grounding": round(avg_grounding, 3),
        "feedback_entries_logged": total_feedback,
        "duration_s": round(elapsed, 1),
        "rate_per_min": round(len(results) / elapsed * 60, 1) if elapsed > 0 else 0,
        "output_path": str(output_path),
        "by_persona": by_persona,
    }

    logger.info(f"Batch complete: {json.dumps(summary, indent=2)}")
    return summary
