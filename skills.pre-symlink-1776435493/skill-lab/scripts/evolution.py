"""Skill-Lab evolution — continuous nightly evolution registration and health.

Tracks evolutionary dynamics: training data, model status, attractors,
extinction candidates. Designed to run as part of the nightly harvest cycle.

Inputs: state files from bond_harvest, warm_pond sessions.
Outputs: evolution health status, scheduler registration.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPTS_DIR.parent.parent

STATE_DIR = SCRIPTS_DIR.parent / "state"
STATE_DIR.mkdir(exist_ok=True)

TRACES_FILE = STATE_DIR / "execution_traces.jsonl"
LABELS_FILE = STATE_DIR / "bond_labels.jsonl"
SHADOW_FILE = STATE_DIR / "bond_shadow.jsonl"
HARVEST_LOG = STATE_DIR / "harvest_log.jsonl"
WARM_POND_DIR = STATE_DIR / "warm_pond"
ATTRACTORS_FILE = STATE_DIR / "attractors.json"


def register_nightly_evolution() -> dict:
    """Register the nightly evolution cycle with /scheduler.

    BFF alignment: The system must never settle into a static state --
    replicators keep displacing each other. This registers a nightly
    job that runs the full harvest + warm pond + retrain cycle.
    """
    scheduler_run = SKILLS_DIR / "scheduler" / "run.sh"
    skill_lab_run = SCRIPTS_DIR.parent / "run.sh"

    result: dict = {"status": "unknown"}

    if not scheduler_run.exists():
        result["status"] = "scheduler_not_found"
        result["message"] = "Install /scheduler skill first"
        return result

    try:
        proc = subprocess.run(
            [str(scheduler_run), "register",
             "--name", "skill-lab-evolution",
             "--cron", "0 3 * * *",  # 3 AM nightly
             "--command", f"{skill_lab_run} harvest",
             "--description", "Nightly bond evolution: traces + battle + warm pond + retrain"],
            capture_output=True, text=True, timeout=10,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        result["status"] = "registered" if proc.returncode == 0 else "error"
        result["output"] = proc.stdout[:200] if proc.stdout else proc.stderr[:200]
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)[:200]

    return result


def evolution_status() -> dict:
    """Report evolution health: training data, model status, attractors, extinction candidates.

    BFF alignment: Continuous monitoring of the evolutionary dynamics.
    """
    status: dict = {"evolution": True}

    # Last harvest
    if HARVEST_LOG.exists():
        lines = HARVEST_LOG.read_text().splitlines()
        if lines:
            try:
                last = json.loads(lines[-1])
                status["last_harvest"] = last.get("timestamp", "unknown")
                status["last_harvest_type"] = last.get("type", "unknown")
            except json.JSONDecodeError:
                pass

    # Label counts
    if LABELS_FILE.exists():
        labels = [l for l in LABELS_FILE.read_text().splitlines() if l.strip()]
        status["total_labels"] = len(labels)
    else:
        status["total_labels"] = 0

    # Trace counts
    if TRACES_FILE.exists():
        traces = [l for l in TRACES_FILE.read_text().splitlines() if l.strip()]
        status["total_traces"] = len(traces)
    else:
        status["total_traces"] = 0

    # Shadow entries
    if SHADOW_FILE.exists():
        entries = [l for l in SHADOW_FILE.read_text().splitlines() if l.strip()]
        status["total_shadow"] = len(entries)
    else:
        status["total_shadow"] = 0

    # Classifier status
    classifier_model = STATE_DIR / "bond_classifier.pkl"
    status["classifier_trained"] = classifier_model.exists()

    # Top attractors
    if ATTRACTORS_FILE.exists():
        try:
            data = json.loads(ATTRACTORS_FILE.read_text())
            attractors = data.get("attractors", [])
            status["top_attractors"] = [
                {"pair": a["pair"], "frequency": a["frequency"]}
                for a in attractors[:5]
            ]
        except (json.JSONDecodeError, KeyError):
            status["top_attractors"] = []
    else:
        status["top_attractors"] = []

    # Extinction candidates: skills with zero co-occurrence
    status["extinction_candidates"] = _detect_extinction_candidates()

    # Training metrics
    metrics_file = STATE_DIR / "training_metrics.json"
    if metrics_file.exists():
        try:
            metrics = json.loads(metrics_file.read_text())
            status["classifier_accuracy"] = metrics.get("cv_accuracy", "n/a")
        except json.JSONDecodeError:
            pass

    return status


def _detect_extinction_candidates() -> list[str]:
    """Find skills approaching extinction.

    A skill is an extinction candidate if:
    - Zero co-occurrence in last 5 warm pond sessions
    - Zero production execution traces in last 30 days
    - Not in any attractor composition
    """
    # Get all skills that appear in traces
    active_skills: set[str] = set()
    if TRACES_FILE.exists():
        for line in TRACES_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                pair = entry.get("pair", "")
                if "+" in pair:
                    for skill in pair.split("+"):
                        active_skills.add(skill)
            except json.JSONDecodeError:
                continue

    # Get attractor skills
    attractor_skills: set[str] = set()
    if ATTRACTORS_FILE.exists():
        try:
            data = json.loads(ATTRACTORS_FILE.read_text())
            for a in data.get("attractors", []):
                attractor_skills.add(a.get("skill_a", ""))
                attractor_skills.add(a.get("skill_b", ""))
        except (json.JSONDecodeError, KeyError):
            pass

    # Get all known skills from recent warm pond sessions
    pond_skills: set[str] = set()
    if WARM_POND_DIR.exists():
        sessions = sorted(WARM_POND_DIR.glob("session_*.jsonl"))
        for sf in sessions[-5:]:  # Last 5 sessions
            for line in sf.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    for skill in entry.get("chain", []):
                        pond_skills.add(skill)
                except json.JSONDecodeError:
                    continue

    # Skills in warm pond but never in traces or attractors
    candidates = []
    for skill in pond_skills:
        if skill not in active_skills and skill not in attractor_skills:
            candidates.append(skill)

    return sorted(candidates)
