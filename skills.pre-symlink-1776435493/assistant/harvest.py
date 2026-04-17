#!/usr/bin/env python3
"""Nightly harvest: extract tier-2 scillm escalations as training data.

Runs after monitor-* skills (typically 4:00 AM cron). Workflow:

1. Scan ~/.pi/assistant/metrics.jsonl for tier-2 escalations from last N hours
2. For each escalation, re-fetch the scillm result as a teacher label
3. Write labels to create-gpt/data/{task}/teacher/nightly_harvest.jsonl
4. Write classifier disagreements to create-classifier/data/{task}/corrections.jsonl
5. Optionally trigger single-round retraining via teacher_student_loop.py
6. (v2) Filter by evidence_case_verdict — only train on SATISFIED QRAs,
   route NOT_SATISFIED to adversarial bank for /test-lab

Usage:
    python harvest.py --since 24h
    python harvest.py --since 48h --dry-run
    python harvest.py --retrain
    python harvest.py --require-evidence          # only harvest verdict=satisfied
    python harvest.py --require-evidence --allow-inconclusive
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from loguru import logger

# ---------------------------------------------------------------------------
# dotenv: load .env BEFORE any os.environ / os.getenv calls
# ---------------------------------------------------------------------------
SKILLS_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
    _root_env = SKILLS_DIR.parent / ".env"
    if _root_env.exists():
        load_dotenv(_root_env, override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on parent env

METRICS_DIR = Path(os.environ.get("ASSISTANT_METRICS_DIR", str(Path.home() / ".pi" / "assistant")))
METRICS_FILE = METRICS_DIR / "metrics.jsonl"
SHADOW_FILE = METRICS_DIR / "shadow.jsonl"
CASCADE_LABELS_DIR = Path.home() / ".local" / "share" / "embry" / "cascade-labels"
CREATE_GPT_DATA = SKILLS_DIR / "create-gpt" / "data"

ADVERSARIAL_SCOPE = "adversarial_qra"

# Valid evidence case verdict states (from /create-evidence-case)
VERDICT_SATISFIED = "satisfied"
VERDICT_NOT_SATISFIED = "not_satisfied"
VERDICT_INCONCLUSIVE = "inconclusive"


@dataclass
class EvidenceFilterStats:
    """Statistics from evidence-case verdict filtering."""
    total_checked: int = 0
    accepted: int = 0
    rejected_not_satisfied: int = 0
    rejected_inconclusive: int = 0
    no_verdict: int = 0  # entries without evidence_case_verdict field
    adversarial_routed: int = 0
    adversarial_errors: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "total_checked": self.total_checked,
            "accepted": self.accepted,
            "rejected_not_satisfied": self.rejected_not_satisfied,
            "rejected_inconclusive": self.rejected_inconclusive,
            "no_verdict": self.no_verdict,
            "adversarial_routed": self.adversarial_routed,
            "adversarial_errors": self.adversarial_errors,
        }


def _get_memory_client():
    """Lazy-load MemoryClient to avoid import overhead when not needed."""
    try:
        from common.memory_client import MemoryClient
        return MemoryClient(scope=ADVERSARIAL_SCOPE)
    except ImportError:
        # Fallback: try relative path
        import importlib.util
        import sys as _sys
        mc_path = SKILLS_DIR / "common" / "memory_client.py"
        if mc_path.exists():
            spec = importlib.util.spec_from_file_location("common.memory_client", mc_path)
            mod = importlib.util.module_from_spec(spec)
            _sys.modules["common.memory_client"] = mod
            spec.loader.exec_module(mod)
            return mod.MemoryClient(scope=ADVERSARIAL_SCOPE)
        raise


def _route_to_adversarial(entry: Dict[str, Any], dry_run: bool = False) -> bool:
    """Route a NOT_SATISFIED QRA to /memory learn scope=adversarial_qra.

    Uses MemoryClient (subprocess to /memory run.sh) per project rules.
    Returns True on success, False on error.
    """
    if dry_run:
        return True

    input_data = entry.get("input_data") or entry.get("input", {})
    teacher_result = entry.get("teacher_result", {})
    task = entry.get("task", "unknown")
    verdict = entry.get("evidence_case_verdict", "unknown")

    # Build problem/solution for /memory learn
    if isinstance(input_data, dict):
        question = input_data.get("question", input_data.get("text", str(input_data)))
    else:
        question = str(input_data)

    if isinstance(teacher_result, dict):
        answer = teacher_result.get("answer", teacher_result.get("result", str(teacher_result)))
    else:
        answer = str(teacher_result)

    problem = f"[adversarial][{task}][{verdict}] {question}"
    solution = (
        f"This QRA was rejected by evidence-case verdict={verdict}. "
        f"Original teacher answer: {answer}"
    )

    try:
        client = _get_memory_client()
        result = client.learn(
            problem=problem,
            solution=solution,
            scope=ADVERSARIAL_SCOPE,
            tags=["adversarial", "harvest_rejected", task, f"verdict_{verdict}"],
        )
        if result.success:
            logger.debug(f"Routed adversarial QRA to memory: task={task} verdict={verdict}")
            return True
        else:
            logger.warning(f"Memory learn failed for adversarial QRA: {result.error}")
            return False
    except Exception as e:
        logger.error(f"Failed to route adversarial QRA to memory: {e}")
        return False


def filter_by_evidence_verdict(
    entries: List[Dict[str, Any]],
    allow_inconclusive: bool = False,
    dry_run: bool = False,
) -> tuple:
    """Filter shadow entries by evidence_case_verdict field.

    Args:
        entries: Shadow entries to filter.
        allow_inconclusive: If True, also accept verdict=inconclusive.
        dry_run: If True, don't actually route adversarial QRAs.

    Returns:
        (accepted_entries, stats): Tuple of filtered list and statistics.
    """
    stats = EvidenceFilterStats()
    accepted = []

    allowed = {VERDICT_SATISFIED}
    if allow_inconclusive:
        allowed.add(VERDICT_INCONCLUSIVE)

    for entry in entries:
        stats.total_checked += 1
        verdict = entry.get("evidence_case_verdict", "").lower().strip()

        if not verdict:
            # No verdict field — entry predates evidence-case integration
            stats.no_verdict += 1
            # Pass through: backward compat (these are pre-v2 entries)
            accepted.append(entry)
            continue

        if verdict in allowed:
            stats.accepted += 1
            accepted.append(entry)
            continue

        # Rejected — track by reason
        if verdict == VERDICT_NOT_SATISFIED:
            stats.rejected_not_satisfied += 1
            # Route to adversarial bank for /test-lab
            ok = _route_to_adversarial(entry, dry_run=dry_run)
            if ok:
                stats.adversarial_routed += 1
            else:
                stats.adversarial_errors += 1
        elif verdict == VERDICT_INCONCLUSIVE:
            stats.rejected_inconclusive += 1
            # Inconclusive rejected (allow_inconclusive=False) — don't
            # route to adversarial, just skip. These are uncertain, not bad.
        else:
            # Unknown verdict value — treat as no_verdict for safety
            logger.warning(f"Unknown evidence_case_verdict='{verdict}', passing through")
            stats.no_verdict += 1
            accepted.append(entry)
            continue

    logger.info(
        f"Evidence filter: {stats.accepted} accepted, "
        f"{stats.rejected_not_satisfied} not_satisfied (→adversarial), "
        f"{stats.rejected_inconclusive} inconclusive rejected, "
        f"{stats.no_verdict} no-verdict (passthrough)"
    )

    return accepted, stats


app = typer.Typer(add_completion=False, help="Harvest tier-2 escalations as training data")


def parse_duration(since: str) -> timedelta:
    """Parse a duration string like '24h', '48h', '7d' into a timedelta."""
    since = since.strip().lower()
    if since.endswith("h"):
        return timedelta(hours=int(since[:-1]))
    elif since.endswith("d"):
        return timedelta(days=int(since[:-1]))
    elif since.endswith("m"):
        return timedelta(minutes=int(since[:-1]))
    return timedelta(hours=24)


def load_escalations(since: timedelta) -> List[Dict[str, Any]]:
    """Load tier-2 escalations from metrics.jsonl within the time window."""
    if not METRICS_FILE.exists():
        logger.warning(f"Metrics file not found: {METRICS_FILE}")
        return []

    cutoff = datetime.now(timezone.utc) - since
    escalations = []

    with open(METRICS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("tier") != 2:
                    continue

                ts_str = entry.get("timestamp", "")
                if ts_str:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue

                escalations.append(entry)
            except (json.JSONDecodeError, ValueError):
                continue

    logger.info(f"Found {len(escalations)} tier-2 escalations in last {since}")
    return escalations


def load_shadow_entries(since: timedelta) -> List[Dict[str, Any]]:
    """Load shadow entries from shadow.jsonl within the time window.

    Shadow entries contain input_data and teacher_result — the actual
    training data needed for model improvement.
    """
    entries = []
    for src in [SHADOW_FILE, *CASCADE_LABELS_DIR.glob("*_labels.jsonl")]:
        if not src.exists():
            continue
        cutoff = datetime.now(timezone.utc) - since
        with open(src) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts_raw = entry.get("timestamp", "")
                    if ts_raw:
                        if isinstance(ts_raw, (int, float)):
                            ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                        else:
                            ts = datetime.fromisoformat(str(ts_raw))
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                        if ts < cutoff:
                            continue
                    # Only harvest entries that have real data
                    if not entry.get("input_data") and not entry.get("input"):
                        continue
                    if not entry.get("teacher_result") and not entry.get("teacher_grade"):
                        continue
                    entries.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue

    logger.info(f"Found {len(entries)} shadow entries with training data in last {since}")
    return entries


def write_teacher_labels(
    escalations: List[Dict[str, Any]],
    dry_run: bool = False,
    shadow_entries: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """Write teacher labels for retraining from shadow entries.

    Shadow entries (from shadow.jsonl) contain input_data and teacher_result.
    Metrics escalations (from metrics.jsonl) are used as a fallback when
    shadow entries are unavailable.

    Returns dict of task_name → count of labels written.
    """
    counts: Dict[str, int] = {}

    # Primary source: shadow entries with real input/output data
    if shadow_entries:
        for entry in shadow_entries:
            task = entry.get("task", "unknown")
            if task == "unknown":
                continue

            input_data = entry.get("input_data") or entry.get("input", {})
            teacher_result = entry.get("teacher_result", {})
            teacher_grade = entry.get("teacher_grade", "")

            label = {
                "input": input_data,
                "output": teacher_result,
                "task": task,
                "teacher_grade": teacher_grade,
                "scope": entry.get("scope", ""),
                "source": "shadow_harvest",
                "timestamp": entry.get("timestamp"),
            }

            counts[task] = counts.get(task, 0) + 1

            if dry_run:
                continue

            task_dir = CREATE_GPT_DATA / "tasks" / "raw" / task
            task_dir.mkdir(parents=True, exist_ok=True)
            output_file = task_dir / "nightly_harvest.jsonl"

            with open(output_file, "a") as f:
                f.write(json.dumps(label) + "\n")

    # Fallback: metrics escalations (no input/output, just metadata)
    for entry in escalations:
        task = entry.get("task", "unknown")
        if task == "unknown":
            continue
        # Skip if we already got this task from shadow entries
        if shadow_entries and task in counts:
            continue

        label = {
            "input": {},
            "output": {},
            "task": task,
            "teacher_grade": "",
            "scope": entry.get("scope", ""),
            "source": "metrics_fallback",
            "confidence": entry.get("confidence", 1.0),
            "timestamp": entry.get("timestamp"),
        }

        counts[task] = counts.get(task, 0) + 1

        if dry_run:
            continue

        task_dir = CREATE_GPT_DATA / "tasks" / "raw" / task
        task_dir.mkdir(parents=True, exist_ok=True)
        output_file = task_dir / "nightly_harvest.jsonl"

        with open(output_file, "a") as f:
            f.write(json.dumps(label) + "\n")

    return counts


def write_classifier_corrections(
    escalations: List[Dict[str, Any]],
    dry_run: bool = False,
) -> int:
    """Write classifier disagreements as correction data.

    Returns count of corrections written.
    """
    corrections = [e for e in escalations if e.get("source") == "scillm"]
    if not corrections:
        return 0

    if dry_run:
        return len(corrections)

    corrections_dir = SKILLS_DIR / "create-classifier" / "data" / "corrections"
    corrections_dir.mkdir(parents=True, exist_ok=True)
    output_file = corrections_dir / "nightly_corrections.jsonl"

    with open(output_file, "a") as f:
        for entry in corrections:
            correction = {
                "timestamp": entry.get("timestamp"),
                "task": entry.get("task"),
                "scope": entry.get("scope"),
                "source": "harvest_correction",
            }
            f.write(json.dumps(correction) + "\n")

    return len(corrections)


@app.command()
def harvest(
    since: str = typer.Option("24h", "--since", help="Time window (e.g. 24h, 48h, 7d)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be harvested"),
    retrain: bool = typer.Option(False, "--retrain", help="Trigger single-round retraining after harvest"),
    auto_improve: bool = typer.Option(False, "--auto-improve", help="Trigger model_factory.auto_improve for tasks with >50 labels"),
    require_evidence: bool = typer.Option(
        False, "--require-evidence",
        help="Only harvest QRAs with evidence_case_verdict=satisfied. "
             "NOT_SATISFIED entries are routed to adversarial bank for /test-lab.",
    ),
    allow_inconclusive: bool = typer.Option(
        False, "--allow-inconclusive",
        help="When --require-evidence is set, also accept verdict=inconclusive.",
    ),
):
    """Extract tier-2 escalations as training data for model improvement."""
    duration = parse_duration(since)
    logger.info(f"Harvesting escalations from last {since} (dry_run={dry_run}, require_evidence={require_evidence})")

    # Load shadow entries (primary source — has input_data + teacher_result)
    shadow_entries = load_shadow_entries(duration)

    # Load escalations from metrics (fallback)
    escalations = load_escalations(duration)

    if not escalations and not shadow_entries:
        logger.info("No data found, nothing to harvest")
        typer.echo(json.dumps({"status": "empty", "escalations": 0, "shadow_entries": 0}))
        return

    # --- Evidence verdict filtering (v2) ---
    evidence_stats: Optional[EvidenceFilterStats] = None
    pre_filter_count = len(shadow_entries)

    if require_evidence and shadow_entries:
        shadow_entries, evidence_stats = filter_by_evidence_verdict(
            shadow_entries,
            allow_inconclusive=allow_inconclusive,
            dry_run=dry_run,
        )
        logger.info(
            f"Evidence filter: {pre_filter_count} → {len(shadow_entries)} shadow entries "
            f"({pre_filter_count - len(shadow_entries)} filtered out)"
        )

    # Write teacher labels (shadow entries first, metrics fallback)
    teacher_counts = write_teacher_labels(
        escalations, dry_run=dry_run, shadow_entries=shadow_entries,
    )

    # Write classifier corrections
    correction_count = write_classifier_corrections(escalations, dry_run=dry_run)

    summary: Dict[str, Any] = {
        "status": "dry_run" if dry_run else "harvested",
        "total_escalations": len(escalations),
        "shadow_entries": len(shadow_entries),
        "shadow_entries_pre_filter": pre_filter_count,
        "teacher_labels_by_task": teacher_counts,
        "classifier_corrections": correction_count,
        "time_window": since,
        "require_evidence": require_evidence,
    }

    if evidence_stats is not None:
        summary["evidence_filter"] = evidence_stats.to_dict()

    typer.echo(json.dumps(summary, indent=2))
    logger.info(
        f"Harvest complete: {len(shadow_entries)} shadow + "
        f"{len(escalations)} metrics → {sum(teacher_counts.values())} labels"
    )
    if evidence_stats is not None:
        logger.info(
            f"Evidence filter stats: "
            f"accepted={evidence_stats.accepted}, "
            f"not_satisfied={evidence_stats.rejected_not_satisfied} "
            f"(→adversarial={evidence_stats.adversarial_routed}), "
            f"inconclusive_rejected={evidence_stats.rejected_inconclusive}, "
            f"no_verdict_passthrough={evidence_stats.no_verdict}"
        )

    # Auto-improve: trigger model_factory for tasks with sufficient labels
    if auto_improve and not dry_run:
        _trigger_auto_improve(teacher_counts)

    # Optional: trigger retraining
    if retrain and not dry_run and teacher_counts:
        logger.info("Triggering single-round retraining...")
        try:
            loop_script = SKILLS_DIR / "create-gpt" / "scripts" / "teacher_student_loop.py"
            if loop_script.exists():
                for task_name in teacher_counts:
                    input_file = CREATE_GPT_DATA / "tasks" / "raw" / task_name / "nightly_harvest.jsonl"
                    if input_file.exists():
                        cmd = [
                            "python3", str(loop_script),
                            "--task", task_name,
                            "--input", str(input_file),
                            "--max-rounds", "1",
                        ]
                        logger.info(f"Retraining {task_name}: {' '.join(cmd)}")
                        subprocess.run(cmd, timeout=600, check=False,
                            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                        )
            else:
                logger.warning(f"Teacher-student loop not found at {loop_script}")
        except Exception as e:
            logger.error(f"Retraining failed: {e}")


def _trigger_auto_improve(teacher_counts: Dict[str, int]) -> None:
    """Trigger model_factory.auto_improve for tasks with sufficient labels."""
    MIN_LABELS_FOR_AUTO_IMPROVE = 50
    tasks_to_improve = [
        task for task, count in teacher_counts.items()
        if count >= MIN_LABELS_FOR_AUTO_IMPROVE
    ]

    if not tasks_to_improve:
        logger.info(
            f"No tasks with >= {MIN_LABELS_FOR_AUTO_IMPROVE} labels, "
            f"skipping auto-improve"
        )
        return

    try:
        import importlib.util
        import sys as _sys
        mf_path = SKILLS_DIR / "common" / "model_factory.py"
        spec = importlib.util.spec_from_file_location("model_factory", mf_path)
        mf_mod = importlib.util.module_from_spec(spec)
        _sys.modules["model_factory"] = mf_mod  # Python 3.13 dataclass needs this
        spec.loader.exec_module(mf_mod)

        factory = mf_mod.ModelFactory()
        for task_name in tasks_to_improve:
            logger.info(f"Auto-improving task={task_name} ({teacher_counts[task_name]} labels)")
            result = factory.auto_improve(task_name)
            logger.info(f"Auto-improve result for {task_name}: {result.get('actions', [])}")
    except Exception as e:
        logger.error(f"Auto-improve failed: {e}")


if __name__ == "__main__":
    app()
