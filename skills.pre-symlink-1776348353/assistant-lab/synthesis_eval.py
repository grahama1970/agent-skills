"""Post-training synthesis evaluation step.

After training a model, this runs focused persona conversations to validate
that the model produces quality synthesis responses — not just shadow agreement.

A model must pass BOTH:
  1. Shadow agreement >= 90% (existing check in auto-improve)
  2. Synthesis quality >= min_synthesis_rate (this module)

Usage:
    python synthesis_eval.py --task qra-assessor --count 20
    python synthesis_eval.py --task bridge-tagger --min-rate 0.5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from loguru import logger

SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent

if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

from common.persona_router import route_personas_for_task
from common.persona_synthesis import (
    QuestionSource,
    SynthesisConfig,
    generate_questions,
    run_batch_synthesis,
)
from common.paths import SYNTHESIS_DIR

app = typer.Typer(add_completion=False, help="Post-training synthesis evaluation")


def _task_question_generator(task: str) -> QuestionSource:
    """Build a generic question source for a task using shadow data."""

    def _generate(persona_name: str, n: int) -> list[dict]:
        """Mine questions from shadow.jsonl for this task."""
        from common.paths import SHADOW_FILE

        questions: list[dict] = []
        if not SHADOW_FILE.exists():
            return questions

        seen: set[str] = set()
        for line in SHADOW_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("task") != task:
                    continue
                input_hash = entry.get("input_hash", "")
                if input_hash in seen:
                    continue
                seen.add(input_hash)
                questions.append({
                    "question": json.dumps(entry.get("input_data", entry.get("input", "")))[:300],
                    "persona": persona_name or "evaluator",
                    "source": "shadow_replay",
                })
                if len(questions) >= n:
                    break
            except (json.JSONDecodeError, KeyError):
                continue
        return questions

    return QuestionSource("shadow_replay", 1.0, _generate)


def evaluate_synthesis(
    task: str,
    count: int = 20,
    min_synthesis_rate: float = 0.4,
) -> dict[str, Any]:
    """Run synthesis evaluation for a trained model.

    Args:
        task: Task name (e.g. "qra-assessor").
        count: Number of synthesis conversations to run.
        min_synthesis_rate: Minimum fraction of conversations that must
            trigger synthesis (multi-QRA retrieval) to pass.

    Returns:
        Dict with passing status and metrics.
    """
    # Route to best persona for this task
    matches = route_personas_for_task(task, {}, top_k=1)
    persona_name = matches[0].name if matches else "evaluator"
    scope = matches[0].scope if matches else task

    # Build respond_fn from assistant
    try:
        from assistant.assistant import validate

        def respond_fn(question: str) -> dict:
            result = validate(
                {"text": question},
                task=task,
                scope=scope,
            )
            return {
                "confidence": str(getattr(result, "confidence", "")),
                "qras_used": getattr(result, "result", {}).get("qras_used", 0)
                if isinstance(getattr(result, "result", None), dict) else 0,
                "avg_grounding": 0.0,
            }
    except ImportError:
        logger.warning("assistant.assistant not importable; using stub respond_fn")

        def respond_fn(question: str) -> dict:
            return {"confidence": "0.5", "qras_used": 0, "avg_grounding": 0.0}

    config = SynthesisConfig(
        respond_fn=respond_fn,
        scope=scope,
        question_sources=[_task_question_generator(task)],
        results_dir=SYNTHESIS_DIR / "eval",
        batch_log_interval=10,
    )

    questions = generate_questions(config, count=count, persona_name=persona_name)
    if not questions:
        return {
            "task": task,
            "passing": False,
            "reason": "no_questions_generated",
            "synthesis_rate": 0.0,
        }

    summary = run_batch_synthesis(questions, config)

    synthesis_rate = summary.get("synthesis_rate", 0.0)
    passing = synthesis_rate >= min_synthesis_rate

    return {
        "task": task,
        "passing": passing,
        "synthesis_rate": synthesis_rate,
        "min_synthesis_rate": min_synthesis_rate,
        "conversations": summary.get("conversations_completed", 0),
        "errors": summary.get("errors", 0),
        "persona": persona_name,
        "scope": scope,
        "output_path": summary.get("output_path", ""),
    }


@app.command()
def run(
    task: str = typer.Option(..., help="Task to evaluate"),
    count: int = typer.Option(20, help="Number of synthesis conversations"),
    min_rate: float = typer.Option(0.4, help="Minimum synthesis rate to pass"),
):
    """Run synthesis evaluation for a task."""
    result = evaluate_synthesis(task, count=count, min_synthesis_rate=min_rate)
    status = "PASSED" if result["passing"] else "FAILED"
    print(f"\n=== Synthesis Eval: {status} ===")
    print(json.dumps(result, indent=2))
    raise typer.Exit(0 if result["passing"] else 1)


if __name__ == "__main__":
    app()
