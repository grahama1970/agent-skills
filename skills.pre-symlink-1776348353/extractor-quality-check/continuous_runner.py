#!/usr/bin/env python3
"""
Continuous Teacher Label Runner — Unattended persona cycling.

Alternates between Margaret Chen and Jennifer Cheung personas,
accumulating teacher labels toward the training threshold (default: 2,000).
Automatically stops when threshold is reached or max cycles hit.

Usage:
    python continuous_runner.py                    # Run until 2,000 labels
    python continuous_runner.py --target 5000      # Custom target
    python continuous_runner.py --max-cycles 50    # Limit cycles
    python continuous_runner.py --queries 5        # Fewer queries per cycle
    python continuous_runner.py --dry-run          # Preview without executing

Environment:
    CHUTES_TEXT_MODEL    Model for teacher evals (default: deepseek-ai/DeepSeek-V3-0324)
    TEACHER_LABEL_THRESHOLD  Same as --target
    CONTINUOUS_COOLDOWN  Seconds between cycles (default: 15)
"""

import os
import sys
import json
import time
import signal
from pathlib import Path
from datetime import datetime, timezone

import typer
from loguru import logger

# Ensure the skill directory is importable
_SKILL_DIR = Path(__file__).resolve().parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from persona_autonomous_loop import run_cycle, _count_teacher_labels

app = typer.Typer(pretty_exceptions_enable=False)

_TASK_MAP = {
    "margaret_chen": "extraction-quality-assessor",
    "jennifer_cheung": "cybersecurity-extraction-auditor",
}

_PERSONAS = ["margaret_chen", "jennifer_cheung"]

# Graceful shutdown
_shutdown = False

def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Shutdown signal received — finishing current cycle")
    _shutdown = True

signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def _total_labels() -> dict:
    """Return per-task and total label counts."""
    counts = {}
    for persona, task in _TASK_MAP.items():
        counts[persona] = _count_teacher_labels(task)
    counts["total"] = sum(counts.values())
    return counts


@app.command()
def main(
    target: int = typer.Option(2000, help="Total label target across both personas"),
    max_cycles: int = typer.Option(200, help="Maximum cycles before stopping"),
    queries: int = typer.Option(10, help="Queries per cycle per persona"),
    cooldown: int = typer.Option(
        int(os.getenv("CONTINUOUS_COOLDOWN", "15")),
        help="Seconds between cycles",
    ),
    dry_run: bool = typer.Option(False, help="Preview mode"),
):
    """Run continuous persona cycles until label target is reached."""
    os.environ.setdefault("CHUTES_TEXT_MODEL", "deepseek-ai/DeepSeek-V3-0324")

    counts = _total_labels()
    logger.info(
        "Starting continuous runner: {} total labels, target {}",
        counts["total"], target,
    )

    if counts["total"] >= target:
        logger.success("Already at target ({} >= {})", counts["total"], target)
        return

    cycle = 0
    persona_idx = 0  # Alternate between personas

    # Status log file
    status_path = _SKILL_DIR / "continuous_status.json"

    while cycle < max_cycles and not _shutdown:
        counts = _total_labels()
        if counts["total"] >= target:
            logger.success(
                "Target reached: {} labels (target {})", counts["total"], target
            )
            break

        persona = _PERSONAS[persona_idx % len(_PERSONAS)]
        task = _TASK_MAP[persona]
        cycle += 1

        logger.info(
            "[Cycle {}/{}] {} — {} labels so far (target {})",
            cycle, max_cycles, persona, counts["total"], target,
        )

        try:
            result = run_cycle(persona, num_queries=queries, dry_run=dry_run)

            if result is None:
                logger.warning("Cycle {} returned None for {} — skipping", cycle, persona)
                time.sleep(10)
                continue

            new_counts = _total_labels()
            labels_added = new_counts["total"] - counts["total"]

            logger.info(
                "Cycle {} done: +{} labels, {} total ({:.1f}% of target)",
                cycle, labels_added, new_counts["total"],
                new_counts["total"] / target * 100,
            )

            # Write status file
            status = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cycle": cycle,
                "persona": persona,
                "labels_added": labels_added,
                "counts": new_counts,
                "target": target,
                "progress_pct": round(new_counts["total"] / target * 100, 1),
                "training_triggered": result.get("training_triggered", False),
                "quality_breakdown": result.get("quality_breakdown", {}),
            }
            status_path.write_text(json.dumps(status, indent=2))

        except Exception as e:
            logger.error("Cycle {} failed for {}: {}", cycle, persona, e)
            import traceback
            logger.error("Traceback: {}", traceback.format_exc())
            # Back off on error
            time.sleep(30)

        # Alternate persona
        persona_idx += 1

        # Cooldown between cycles
        if not _shutdown and cycle < max_cycles:
            logger.debug("Cooling down {} seconds", cooldown)
            time.sleep(cooldown)

    # Final report
    final = _total_labels()
    logger.info(
        "Continuous runner stopped after {} cycles: {} total labels",
        cycle, final["total"],
    )
    for persona, count in final.items():
        if persona != "total":
            logger.info("  {}: {}", persona, count)

    if final["total"] >= target:
        logger.success("Training threshold reached — /create-gpt can fire")
    else:
        logger.warning(
            "Stopped before target: {} / {} ({:.1f}%)",
            final["total"], target, final["total"] / target * 100,
        )


if __name__ == "__main__":
    app()
