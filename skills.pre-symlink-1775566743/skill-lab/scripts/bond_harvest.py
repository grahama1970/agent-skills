#!/usr/bin/env python3
"""Bond Harvest — nightly collection of bond data from all sources.

Collects training signal from:
1. Execution traces — real pipeline runs (production)
2. Battle outcomes — competitive selection results
3. Warm pond simulations — Docker-isolated batch experiments
4. Shadow disagreements — where local models diverged from teacher

The warm pond is the key evolutionary mechanism:
    - Spin up a Docker container (like /battle's isolation)
    - Run 100s of skill composition simulations
    - Each simulation: compose → execute → record success/failure
    - Harvest all results as training labels
    - This is Darwin's "warm little pond" — isolated experiments
      driving natural selection of bond affinities

Designed to run as a nightly cron job or via /scheduler:
    python bond_harvest.py nightly --skills-root /path/to/skills
    python bond_harvest.py warm-pond --iterations 200
    python bond_harvest.py stats

Follows the /monitor-sparta and /assistant harvest patterns.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPTS_DIR.parent.parent

STATE_DIR = SCRIPTS_DIR.parent / "state"
STATE_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(SCRIPTS_DIR))
from bond_predictor import append_jsonl
from evolution import (
    register_nightly_evolution,
    evolution_status,
)
from warm_pond import run_warm_pond, run_bootstrap_warm_pond

TRACES_FILE = STATE_DIR / "execution_traces.jsonl"
LABELS_FILE = STATE_DIR / "bond_labels.jsonl"
SHADOW_FILE = STATE_DIR / "bond_shadow.jsonl"
HARVEST_LOG = STATE_DIR / "harvest_log.jsonl"
WARM_POND_DIR = STATE_DIR / "warm_pond"


# ---------------------------------------------------------------------------
# Nightly harvest — combine all sources
# ---------------------------------------------------------------------------

def _tm_cmd(args: list[str]) -> bool:
    """Run a task-monitor command. Returns True on success."""
    tm_run = SKILLS_DIR / "task-monitor" / "run.sh"
    if not tm_run.exists():
        return False
    try:
        proc = subprocess.run(
            [str(tm_run), *args],
            capture_output=True, text=True, timeout=30, check=False,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return proc.returncode == 0
    except Exception:
        return False


def run_nightly_harvest(skills_root: Path) -> dict:
    """Run the complete nightly harvest pipeline.

    1. Harvest execution traces from production
    2. Harvest battle outcomes
    3. Run warm pond simulation (if Docker available)
    4. Collect shadow disagreements for correction
    5. Retrain classifier
    """
    from bond_teacher import (
        harvest_execution_traces,
        harvest_battle_outcomes,
        train_classifier,
    )

    # Task-monitor: start session
    _tm_cmd(["start-session", "--project", "skill_lab_evolution"])

    results = {"phases": {}}

    # Phase 1: Execution traces
    print("=== Phase 1: Harvest execution traces ===")
    trace_labels = harvest_execution_traces()
    append_jsonl(LABELS_FILE, trace_labels)
    results["phases"]["traces"] = len(trace_labels)
    _tm_cmd(["add-accomplishment", "--text", f"Phase 1: harvested {len(trace_labels)} execution traces"])

    # Phase 2: Battle outcomes
    print("\n=== Phase 2: Harvest battle outcomes ===")
    battle_labels = harvest_battle_outcomes()
    append_jsonl(LABELS_FILE, battle_labels)
    results["phases"]["battles"] = len(battle_labels)
    _tm_cmd(["add-accomplishment", "--text", f"Phase 2: harvested {len(battle_labels)} battle outcomes"])

    # Phase 3: Shadow disagreements
    print("\n=== Phase 3: Shadow disagreements ===")
    shadow_corrections = _harvest_shadow_disagreements()
    results["phases"]["shadow_corrections"] = shadow_corrections

    # Phase 4: Warm pond (if Docker available)
    print("\n=== Phase 4: Warm pond simulation ===")
    docker_available = _check_docker()
    if docker_available:
        pond_results = run_warm_pond(
            skills_root,
            iterations=100,
            use_docker=True,
            timeout_per_sim=30,
        )
        results["phases"]["warm_pond"] = pond_results
    else:
        # Run limited local simulation
        pond_results = run_warm_pond(
            skills_root,
            iterations=50,
            use_docker=False,
            timeout_per_sim=15,
        )
        results["phases"]["warm_pond"] = pond_results

    # Phase 5: Update learned energy model
    print("\n=== Phase 5: Update learned energy model ===")
    from bond_predictor import update_learned_energy
    energy_result = update_learned_energy()
    results["phases"]["learned_energy"] = {
        "skills_updated": len(energy_result.get("skills", {})),
        "source_traces": energy_result.get("source_traces", 0),
    }
    print(f"  Updated energy for {len(energy_result.get('skills', {}))} skills")

    # Phase 6: Retrain classifier
    print("\n=== Phase 6: Retrain classifier ===")
    train_metrics = train_classifier()
    results["phases"]["retrain"] = train_metrics

    # Phase 7: Sync chains to /memory (skill_chains collection)
    # chain-bootstrap is a specialized batch command — run via uv in memory project
    print("\n=== Phase 7: Sync chains to /memory ===")
    memory_root = Path.home() / "workspace" / "experiments" / "memory"
    cmd = [
        "uv", "run", "--directory", str(memory_root), "--all-extras",
        "python", "-m", "graph_memory.lessons.skill_chains", "bootstrap",
        "--traces-file", str(TRACES_FILE),
        "--chains-file", str(STATE_DIR / "skill_chains.jsonl"),
        "--labels-file", str(LABELS_FILE),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
            env={**{k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                 "PYTHONPATH": str(memory_root / "src")},
        )
        if proc.returncode != 0:
            err_msg = f"chain-bootstrap exit {proc.returncode}: {proc.stderr[:200]}"
            results["phases"]["memory_sync"] = f"error: {err_msg}"
            print(f"  Chain sync failed: {err_msg}")
        else:
            results["phases"]["memory_sync"] = proc.stdout.strip()
            print(f"  {proc.stdout.strip()}")
    except Exception as exc:
        results["phases"]["memory_sync"] = f"error: {exc}"
        print(f"  Chain sync failed: {exc}")

    # Phase 8: Rebuild transition matrix
    print("\n=== Phase 8: Rebuild transition matrix ===")
    try:
        from transition_matrix import build_matrix, build_task_matrices, matrix_status
        tm_result = build_matrix()
        print(f"  Matrix: {len(tm_result['skills'])} skills, "
              f"{tm_result['total_transitions']:.0f} transitions")
        task_result = build_task_matrices()
        print(f"  Task matrices: {len(task_result['task_counts'])} types")
        results["phases"]["transition_matrix"] = {
            "skills": len(tm_result["skills"]),
            "transitions": tm_result["total_transitions"],
            "task_types": len(task_result["task_counts"]),
        }
    except Exception as e:
        print(f"  Warning: transition matrix build failed: {e}")
        results["phases"]["transition_matrix"] = {"error": str(e)}

    # Phase 9: Gap detection + LLM synthesis + classifier training
    print("\n=== Phase 9: Gap synthesis pipeline ===")
    try:
        from gap_synthesizer import (
            gap_status, train_gap_classifier, export_gap_sft_data,
        )
        from transition_matrix import detect_missing_skills

        # 9a: Mine probe tasks from real chain data (not hardcoded)
        from probe_tasks import load_probe_tasks as _load_probe_tasks
        probe_tasks = _load_probe_tasks()
        gaps_found = 0
        for probe_task in probe_tasks:
            gap_result = detect_missing_skills(probe_task)
            gaps_found += len(gap_result.get("missing_positions", []))

            # For each gap, synthesize (dry-run — don't auto-create skills)
            for gap in gap_result.get("missing_positions", []):
                if gap.get("source") == "transition_matrix":
                    from gap_synthesizer import reason_about_gap
                    reason_about_gap(
                        probe_task,
                        chain=gap_result.get("predicted_chain", []),
                        from_skill=gap.get("from_skill"),
                        to_skill=gap.get("to_skill"),
                    )

        print(f"  Probed {len(probe_tasks)} tasks, found {gaps_found} gaps")

        # 9b: Train gap classifier if enough labels
        status = gap_status()
        if status["total_labels"] >= status["classifier_threshold"]:
            clf_result = train_gap_classifier()
            print(f"  Gap classifier: {clf_result.get('status')}")
        else:
            print(f"  Gap classifier: {status['total_labels']}/{status['classifier_threshold']} labels")

        # 9c: Export SFT data if enough labels for GPT training
        if status["total_labels"] >= status["gpt_threshold"]:
            sft_result = export_gap_sft_data()
            print(f"  Gap SFT export: {sft_result.get('status')}")
        else:
            print(f"  Gap GPT: {status['total_labels']}/{status['gpt_threshold']} labels")

        results["phases"]["gap_synthesis"] = {
            "gaps_found": gaps_found,
            "total_labels": status["total_labels"],
            "classifier_ready": status["classifier_ready"],
            "tier": status["tier"],
        }
    except Exception as e:
        print(f"  Warning: gap synthesis failed: {e}")
        results["phases"]["gap_synthesis"] = {"error": str(e)}

    # Phase 10: Trajectory distillation (SkillRL-inspired)
    print("\n=== Phase 10: Trajectory distillation ===")
    try:
        from trajectory_distiller import distill
        distill_stats = distill(top_k=5, use_llm=True, dry_run=False)
        results["phases"]["distillation"] = {
            "patterns": distill_stats.get("patterns_distilled", 0),
            "lessons": distill_stats.get("lessons_distilled", 0),
            "stored": distill_stats.get("stored_to_memory", 0),
            "affinities_updated": distill_stats.get("affinities_updated", 0),
        }
        print(f"  Patterns: {distill_stats.get('patterns_distilled', 0)}, "
              f"Lessons: {distill_stats.get('lessons_distilled', 0)}, "
              f"Stored: {distill_stats.get('stored_to_memory', 0)}")
        _tm_cmd(["add-accomplishment", "--text",
                 f"Phase 10: distilled {distill_stats.get('patterns_distilled', 0)} patterns, "
                 f"{distill_stats.get('lessons_distilled', 0)} lessons"])
    except Exception as e:
        print(f"  Warning: trajectory distillation failed: {e}")
        results["phases"]["distillation"] = {"error": str(e)}

    # Log harvest
    results["timestamp"] = datetime.now(timezone.utc).isoformat()
    _log_harvest("nightly", results)

    total_new = (
        results["phases"]["traces"]
        + results["phases"]["battles"]
        + shadow_corrections
        + pond_results.get("bond_labels", 0)
    )
    print(f"\n=== Nightly Harvest Complete ===")
    print(f"  Total new labels: {total_new}")
    print(f"  Classifier: {train_metrics.get('status', 'unknown')}")

    # Task-monitor: end session
    _tm_cmd(["end-session", "--notes",
             f"skill-lab harvest: {total_new} labels, classifier={train_metrics.get('status', 'unknown')}"])

    return results


def _harvest_shadow_disagreements() -> int:
    """Extract correction labels from shadow disagreements."""
    if not SHADOW_FILE.exists():
        return 0

    from bond_teacher import make_label

    corrections = 0
    for line in SHADOW_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("agreed"):
                continue  # Only care about disagreements

            # The teacher grade is ground truth
            teacher_grade = entry.get("teacher_grade", "")
            if not teacher_grade:
                continue

            # This is a correction signal — local model was wrong
            # We don't have skill names in shadow entries (just grades)
            # but we log the correction for metrics
            corrections += 1

        except (json.JSONDecodeError, KeyError):
            continue

    print(f"  Found {corrections} shadow disagreements")
    return corrections


def _check_docker() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        return result.returncode == 0
    except Exception:
        return False


def _log_harvest(harvest_type: str, results: dict) -> None:
    """Log harvest entry."""
    entry = {
        "type": harvest_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    append_jsonl(HARVEST_LOG, [entry])


# ---------------------------------------------------------------------------
# Attractor Detection — BFF: replicators are "attractors"
# ---------------------------------------------------------------------------

ATTRACTORS_FILE = STATE_DIR / "attractors.json"


def detect_attractors(
    min_sessions: int = 3,
    min_frequency: float = 0.1,
) -> list[dict]:
    """Detect attractor compositions from warm pond sessions.

    BFF alignment: Self-replicators are "attractors in the space of all
    possible programs" — they emerge reliably regardless of initial conditions.

    A skill pair is an attractor if:
    - Appears in >= min_sessions different warm pond sessions
    - Frequency >= min_frequency within sessions where it appears
    - Convergence > 0 (appears MORE in later iterations than earlier)

    Returns ranked list of attractor compositions with stats.
    """
    if not WARM_POND_DIR.exists():
        return []

    session_files = sorted(WARM_POND_DIR.glob("session_*.jsonl"))
    if len(session_files) < 1:
        return []

    # Aggregate pair stats across all sessions
    pair_sessions: dict[str, dict] = {}

    for session_file in session_files:
        session_pairs: dict[str, dict] = {}
        lines = session_file.read_text().splitlines()

        for line_idx, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                chain = entry.get("chain", [])
                success = entry.get("success", False)
                iteration = entry.get("iteration", line_idx)

                for i in range(len(chain) - 1):
                    pair = f"{chain[i]}+{chain[i+1]}"
                    if pair not in session_pairs:
                        session_pairs[pair] = {
                            "count": 0,
                            "successes": 0,
                            "early_count": 0,
                            "late_count": 0,
                        }
                    session_pairs[pair]["count"] += 1
                    if success:
                        session_pairs[pair]["successes"] += 1
                    # Track early vs late for convergence
                    total_iterations = len(lines)
                    if iteration < total_iterations // 2:
                        session_pairs[pair]["early_count"] += 1
                    else:
                        session_pairs[pair]["late_count"] += 1
            except (json.JSONDecodeError, KeyError):
                continue

        # Merge session data into global
        total_entries = sum(v["count"] for v in session_pairs.values()) or 1
        for pair, stats in session_pairs.items():
            if pair not in pair_sessions:
                pair_sessions[pair] = {
                    "sessions": [],
                    "total_count": 0,
                    "total_successes": 0,
                    "early_total": 0,
                    "late_total": 0,
                }
            pair_sessions[pair]["sessions"].append(str(session_file.name))
            pair_sessions[pair]["total_count"] += stats["count"]
            pair_sessions[pair]["total_successes"] += stats["successes"]
            pair_sessions[pair]["early_total"] += stats["early_count"]
            pair_sessions[pair]["late_total"] += stats["late_count"]

    # Identify attractors
    attractors = []
    for pair, data in pair_sessions.items():
        session_count = len(data["sessions"])
        frequency = data["total_count"] / max(1, sum(
            d["total_count"] for d in pair_sessions.values()
        ))
        # Convergence: appears more in later iterations than earlier
        convergence = data["late_total"] - data["early_total"]
        success_rate = (
            data["total_successes"] / data["total_count"]
            if data["total_count"] else 0
        )

        # Require minimum sample size AND 50% more observations in late phase
        convergence_ratio = (
            data["late_total"] / max(1, data["early_total"])
        )
        if (
            session_count >= min_sessions
            and frequency >= min_frequency
            and data["total_count"] >= 5
            and data["late_total"] >= 1.5 * max(1, data["early_total"])
        ):
            skills = pair.split("+")
            attractors.append({
                "pair": pair,
                "skill_a": skills[0],
                "skill_b": skills[1],
                "frequency": round(frequency, 4),
                "cross_session_stability": session_count,
                "convergence": convergence,
                "convergence_ratio": round(convergence_ratio, 3),
                "success_rate": round(success_rate, 3),
                "total_observations": data["total_count"],
            })

    # Rank by frequency * success_rate (strongest attractors first)
    attractors.sort(key=lambda a: -(a["frequency"] * a["success_rate"]))

    # Save to file for bond_predictor to use as prior
    ATTRACTORS_FILE.write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attractors": attractors,
        "sessions_analyzed": len(session_files),
    }, indent=2))

    # Sync attractors to /memory for cross-agent discovery
    _sync_attractors_to_memory(attractors)

    return attractors


def _sync_attractors_to_memory(attractors: list[dict]) -> None:
    """Store attractor compositions in /memory for agent discovery."""
    try:
        from scan_soup import _memory_learn
    except ImportError:
        return
    for att in attractors[:10]:
        _memory_learn(
            problem=(f"attractor: {att['pair']} — proven stable composition "
                     f"({att['success_rate']:.0%} success)"),
            solution=json.dumps(att),
            tags=["attractor", f"skill:{att['skill_a']}", f"skill:{att['skill_b']}"],
        )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def print_stats():
    """Print bond training data statistics."""
    print("=== Bond Training Stats ===\n")

    # Labels
    if LABELS_FILE.exists():
        labels = LABELS_FILE.read_text().splitlines()
        labels = [json.loads(l) for l in labels if l.strip()]

        by_source = {}
        by_type = {}
        for l in labels:
            src = l.get("source", "unknown")
            by_source[src] = by_source.get(src, 0) + 1
            bt = l.get("bond_type", "unknown")
            by_type[bt] = by_type.get(bt, 0) + 1

        print(f"Labels: {len(labels)}")
        print(f"  By source: {json.dumps(by_source)}")
        print(f"  By type: {json.dumps(by_type)}")
    else:
        print("Labels: 0 (no data)")

    # Traces
    if TRACES_FILE.exists():
        traces = TRACES_FILE.read_text().splitlines()
        traces = [json.loads(l) for l in traces if l.strip()]
        successes = sum(1 for t in traces if t.get("success"))
        print(f"\nExecution traces: {len(traces)} ({successes} success, {len(traces)-successes} failure)")
    else:
        print("\nExecution traces: 0")

    # Shadow
    if SHADOW_FILE.exists():
        entries = SHADOW_FILE.read_text().splitlines()
        entries = [json.loads(l) for l in entries if l.strip()]
        agree = sum(1 for e in entries if e.get("agreed"))
        print(f"\nShadow entries: {len(entries)} ({agree} agree, {len(entries)-agree} disagree)")
        if entries:
            rate = agree / len(entries)
            status = "ready" if rate >= 0.90 else "learning" if rate >= 0.70 else "early"
            print(f"  Agreement rate: {rate:.1%} ({status})")
    else:
        print("\nShadow entries: 0")

    # Model
    classifier_model = STATE_DIR / "bond_classifier.pkl"
    if classifier_model.exists():
        size = os.path.getsize(classifier_model)
        print(f"\nClassifier model: {classifier_model} ({size/1024:.0f} KB)")
    else:
        print("\nClassifier model: not trained")

    gpt_model = STATE_DIR / "bond_gpt.gguf"
    if gpt_model.exists():
        size = os.path.getsize(gpt_model)
        print(f"GPT model: {gpt_model} ({size/1024/1024:.0f} MB)")
    else:
        print("GPT model: not trained")

    # Warm pond sessions
    if WARM_POND_DIR.exists():
        sessions = list(WARM_POND_DIR.glob("session_*.jsonl"))
        print(f"\nWarm pond sessions: {len(sessions)}")

    # Training metrics
    metrics_file = STATE_DIR / "training_metrics.json"
    if metrics_file.exists():
        metrics = json.loads(metrics_file.read_text())
        print(f"\nLatest training: {metrics.get('timestamp', 'unknown')}")
        print(f"  Accuracy: {metrics.get('cv_accuracy', 'n/a')}")
        print(f"  Samples: {metrics.get('samples', 0)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

import typer
from typing import Optional

app = typer.Typer(help="Bond Harvest — nightly training data collection")


@app.command()
def nightly(
    skills_root: str = typer.Option(str(SKILLS_DIR), help="Root of skills directory"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Run full nightly harvest."""
    results = run_nightly_harvest(Path(skills_root))
    if json_output:
        print(json.dumps(results, indent=2))


@app.command(name="warm-pond")
def warm_pond_cmd(
    skills_root: str = typer.Option(str(SKILLS_DIR), help="Root of skills directory"),
    iterations: int = typer.Option(500, help="Number of iterations"),
    max_chain: int = typer.Option(4, help="Maximum chain length"),
    no_docker: bool = typer.Option(False, help="Disable Docker isolation"),
    timeout: int = typer.Option(60, help="Timeout per simulation in seconds"),
    task_type: Optional[str] = typer.Option(None, help="Task type filter"),
    min_iterations: int = typer.Option(100, help="Minimum iterations before early stop"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Run warm pond simulation."""
    results = run_warm_pond(
        Path(skills_root),
        iterations=iterations,
        max_chain_length=max_chain,
        use_docker=not no_docker,
        timeout_per_sim=timeout,
        task_type=task_type,
        min_iterations=min_iterations,
    )
    if json_output:
        print(json.dumps(results, indent=2))


@app.command(name="bootstrap-pond")
def bootstrap_pond(
    skills_root: str = typer.Option(str(SKILLS_DIR), help="Root of skills directory"),
    target_labels: int = typer.Option(100, help="Target number of labels"),
    max_iterations: int = typer.Option(2000, help="Maximum iterations"),
    no_docker: bool = typer.Option(False, help="Disable Docker isolation"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Bootstrap warm pond to target labels."""
    results = run_bootstrap_warm_pond(
        Path(skills_root),
        target_labels=target_labels,
        max_iterations=max_iterations,
        use_docker=not no_docker,
    )
    if json_output:
        print(json.dumps(results, indent=2))


@app.command()
def stats() -> None:
    """Show training data statistics."""
    print_stats()


@app.command()
def attractors(
    min_sessions: int = typer.Option(3, help="Minimum sessions for attractor detection"),
    min_frequency: float = typer.Option(0.1, help="Minimum frequency threshold"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Detect attractor compositions."""
    found = detect_attractors(
        min_sessions=min_sessions,
        min_frequency=min_frequency,
    )
    if json_output:
        print(json.dumps(found, indent=2))
    else:
        if not found:
            print("No attractor compositions detected yet.")
            print("Run warm pond simulations to generate data.")
        else:
            print(f"=== Attractor Compositions ({len(found)} found) ===\n")
            for a in found:
                print(f"  {a['pair']}")
                print(f"    Frequency: {a['frequency']:.2%}")
                print(f"    Sessions: {a['cross_session_stability']}")
                print(f"    Convergence: +{a['convergence']}")
                print(f"    Success rate: {a['success_rate']:.1%}")
                print()


@app.command()
def evolve(
    skills_root: str = typer.Option(str(SKILLS_DIR), help="Root of skills directory"),
    status: bool = typer.Option(False, "--status", help="Show evolution health"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Continuous evolution management."""
    if status:
        evo_status = evolution_status()
        if json_output:
            print(json.dumps(evo_status, indent=2))
        else:
            print("=== Skill-Lab evolution Health ===\n")
            print(f"  Last harvest:        {evo_status.get('last_harvest', 'never')}")
            print(f"  Total labels:        {evo_status.get('total_labels', 0)}")
            print(f"  Total traces:        {evo_status.get('total_traces', 0)}")
            print(f"  Shadow entries:      {evo_status.get('total_shadow', 0)}")
            print(f"  Classifier trained:  {evo_status.get('classifier_trained', False)}")
            acc = evo_status.get('classifier_accuracy')
            if acc:
                print(f"  Classifier accuracy: {acc}")
            top_attractors = evo_status.get('top_attractors', [])
            if top_attractors:
                print(f"\n  Top attractors:")
                for a in top_attractors:
                    print(f"    {a['pair']} (freq={a['frequency']:.2%})")
            extinct = evo_status.get('extinction_candidates', [])
            if extinct:
                print(f"\n  Extinction candidates ({len(extinct)}):")
                for s in extinct[:10]:
                    print(f"    {s}")
    else:
        # Register + run immediate harvest
        print("=== Registering nightly evolution ===")
        reg = register_nightly_evolution()
        print(f"  Scheduler: {reg.get('status', 'unknown')}")
        if reg.get("message"):
            print(f"  {reg['message']}")

        print("\n=== Running immediate harvest ===")
        results = run_nightly_harvest(Path(skills_root))
        if json_output:
            print(json.dumps({"registration": reg, "harvest": results}, indent=2))


if __name__ == "__main__":
    app()
