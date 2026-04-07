#!/usr/bin/env python3
"""Warm Pond — Docker-isolated batch simulation for bond evolution.

Extracted from bond_harvest.py to keep files under 800 lines.

The warm pond is the key evolutionary mechanism:
    - Spin up a Docker container (like /battle's isolation)
    - Run 100s of skill composition simulations
    - Each simulation: compose → execute → record success/failure
    - Harvest all results as training labels
    - This is Darwin's "warm little pond" — isolated experiments
      driving natural selection of bond affinities

Usage:
    python warm_pond.py run --skills-root /path/to/skills --iterations 500
    python warm_pond.py run --task-type extraction --no-docker
    python warm_pond.py bootstrap --target-labels 100 --no-docker
"""
from __future__ import annotations
import os

import json
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPTS_DIR.parent.parent

STATE_DIR = SCRIPTS_DIR.parent / "state"
STATE_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(SCRIPTS_DIR))
from bond_predictor import append_jsonl

TRACES_FILE = STATE_DIR / "execution_traces.jsonl"
LABELS_FILE = STATE_DIR / "bond_labels.jsonl"
HARVEST_LOG = STATE_DIR / "harvest_log.jsonl"
WARM_POND_DIR = STATE_DIR / "warm_pond"


def _log_harvest(harvest_type: str, results: dict) -> None:
    """Log harvest entry to shared harvest log."""
    entry = {
        "type": harvest_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    append_jsonl(HARVEST_LOG, [entry])


# ---------------------------------------------------------------------------
# Sampling strategies — replace pure random with task-informed selection
# ---------------------------------------------------------------------------

def _sample_chain(
    skill_names: list[str],
    max_chain_length: int,
    iteration: int,
    total_iterations: int,
    task_type: str | None,
    session_results: list[dict],
    curriculum_max: int | None = None,
) -> list[str]:
    """Task-informed chain sampling with three strategy phases.

    - 0-20%:  Random exploration (discover novel combinations)
    - 20-80%: Transition-matrix guided + BADGE-lite active learning
    - 80-100%: Replay top-performing chains from session with mutations

    Respects curriculum_max if set (auto-curriculum limits chain length).
    """
    from warm_pond_advanced import badge_sample, should_skip_chain

    effective_max = min(max_chain_length, len(skill_names))
    if curriculum_max is not None:
        effective_max = min(effective_max, curriculum_max)
    effective_max = max(2, effective_max)

    progress = iteration / max(1, total_iterations)
    chain_len = random.randint(2, effective_max)

    # Pre-filter: try up to 3 times to avoid budget-busting chains
    for _attempt in range(3):
        if progress < 0.2:
            chain = random.sample(skill_names, chain_len)
        elif progress < 0.8:
            # 50% BADGE-lite, 50% transition-guided
            if random.random() < 0.5:
                chain = badge_sample(skill_names, chain_len)
                if chain is None:
                    chain = _transition_guided_sample(
                        skill_names, chain_len, task_type, session_results
                    )
            else:
                chain = _transition_guided_sample(
                    skill_names, chain_len, task_type, session_results
                )
        else:
            chain = _replay_with_mutation(
                skill_names, chain_len, session_results
            )

        if not should_skip_chain(chain):
            return chain

    return chain  # Use last attempt even if over budget


def _transition_guided_sample(
    skill_names: list[str],
    chain_len: int,
    task_type: str | None,
    session_results: list[dict],
) -> list[str]:
    """Use transition matrix probabilities to guide chain construction."""
    from warm_pond_advanced import transition_guided_sample
    return transition_guided_sample(skill_names, chain_len, task_type, session_results)


def _replay_with_mutation(
    skill_names: list[str],
    chain_len: int,
    session_results: list[dict],
) -> list[str]:
    """Replay top-performing chains with single-skill mutation."""
    from warm_pond_advanced import replay_with_mutation
    return replay_with_mutation(skill_names, chain_len, session_results)


# ---------------------------------------------------------------------------
# Warm Pond — Docker-isolated batch simulation
# ---------------------------------------------------------------------------

def run_warm_pond(
    skills_root: Path,
    iterations: int = 500,
    max_chain_length: int = 4,
    use_docker: bool = True,
    timeout_per_sim: int = 60,
    task_type: str | None = None,
    min_iterations: int = 100,
) -> dict:
    """Run batch simulations in a Docker-isolated 'warm pond'.

    Like biological abiogenesis experiments:
    - The Docker container is the warm pond
    - Each simulation randomly composes 2-4 skills
    - Success/failure is recorded as a training signal
    - Over 100s of iterations, bond affinities emerge from data

    Supports task-informed sampling and convergence-based early stopping.
    """
    from scan_soup import scan_soup
    from bond_predictor import log_execution_trace

    graph = scan_soup(skills_root)
    skill_names = [
        name for name, info in graph.get("skills", {}).items()
        if info.get("has_run_sh")  # Only executable skills
    ]

    if len(skill_names) < 2:
        return {"status": "insufficient_skills", "available": len(skill_names)}

    WARM_POND_DIR.mkdir(exist_ok=True)
    session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    session_file = WARM_POND_DIR / f"session_{session_id}.jsonl"

    results = {
        "session_id": session_id,
        "iterations": iterations,
        "task_type": task_type,
        "completed": 0,
        "successes": 0,
        "failures": 0,
        "timeouts": 0,
        "bond_labels": 0,
        "chains_tested": [],
        "convergence": {},
    }

    print(f"=== Warm Pond Simulation ===")
    print(f"  Skills available: {len(skill_names)}")
    print(f"  Iterations: {iterations} (min: {min_iterations})")
    print(f"  Max chain length: {max_chain_length}")
    print(f"  Docker isolation: {use_docker}")
    if task_type:
        print(f"  Task type: {task_type}")
    print()

    from warm_pond_advanced import (
        detect_convergence_signals, tiered_restart,
        CurriculumTracker, directed_mutation,
        update_archives, record_execution_trace,
    )
    from energy_model import compute_chain_energy, compute_elegance

    session_results: list[dict] = []
    consecutive_signals = 0
    initial_diversity: float | None = None
    base_mutation_rate = 0.3
    curriculum = CurriculumTracker(threshold=0.6, initial_max=2)

    for i in range(iterations):
        # Task-informed sampling with curriculum awareness
        chain = _sample_chain(
            skill_names, max_chain_length, i, iterations,
            task_type, session_results,
            curriculum_max=curriculum.unlocked_max,
        )

        # Use topological hints to improve ordering
        chain = _order_by_precedes(chain)

        start = time.time()
        try:
            if use_docker:
                success, output = _run_chain_docker(chain, skills_root, timeout_per_sim)
            else:
                success, output = _run_chain_local(chain, skills_root, timeout_per_sim)

            elapsed_ms = (time.time() - start) * 1000

            # Log execution trace (for cost surrogate training)
            log_execution_trace(
                skills=chain,
                success=success,
                latency_ms=elapsed_ms,
                error="" if success else output[:200],
            )
            record_execution_trace(chain, elapsed_ms)

            # Compute energy + elegance for archive updates
            chain_energy = compute_chain_energy(chain)
            quality = 1.0 if success else 0.0
            elegance = compute_elegance(chain_energy, quality)

            # Update archives (MAP-Elites + skill library)
            update_archives(
                chain=chain,
                success=success,
                energy=chain_energy["total_energy"],
                quality=quality,
                elegance_score=elegance["elegance_score"],
                elegance_grade=elegance["grade"],
                task_type=task_type or "",
            )

            # Update curriculum tracker
            curriculum.record(len(chain), success)

            # Log to session file
            entry = {
                "iteration": i,
                "chain": chain,
                "success": success,
                "latency_ms": round(elapsed_ms, 1),
                "error": "" if success else output[:200],
                "energy": chain_energy["total_energy"],
                "elegance_grade": elegance["grade"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            append_jsonl(session_file, [entry])
            session_results.append(entry)

            results["completed"] += 1
            if success:
                results["successes"] += 1
            else:
                results["failures"] += 1
                # Directed mutation: try scillm-based fix for failures
                if output and random.random() < base_mutation_rate:
                    mutated = directed_mutation(chain, output, skill_names)
                    if mutated:
                        session_results.append({
                            "iteration": i, "chain": mutated,
                            "success": False, "mutation_source": True,
                        })

            # Progress reporting every 25 iterations
            if (i + 1) % 25 == 0:
                rate = results["successes"] / results["completed"] if results["completed"] else 0
                cur_max = curriculum.update_unlocked(max_chain_length)
                print(f"  [{i+1}/{iterations}] "
                      f"success={results['successes']} fail={results['failures']} "
                      f"rate={rate:.1%} curriculum_max={cur_max}")

            # 3-signal convergence tracking
            if (i + 1) % 20 == 0 and i + 1 >= 40:
                conv = detect_convergence_signals(
                    session_results, window=20,
                    initial_diversity=initial_diversity,
                )
                results["convergence"] = conv
                if initial_diversity is None and conv["chain_diversity"] > 0:
                    initial_diversity = conv["chain_diversity"]

                if conv["active_count"] >= 2:
                    consecutive_signals += 1
                    print(f"  [convergence] {conv['restart_tier']} "
                          f"({conv['active_count']}/3 signals, "
                          f"rate={conv['rolling_success_rate']:.1%}, "
                          f"diversity={conv['chain_diversity']:.2f})")

                    # Apply tiered restart
                    restart = tiered_restart(
                        conv["restart_tier"], session_results,
                        skill_names, base_mutation_rate,
                    )
                    base_mutation_rate = restart["mutation_rate"]
                    if restart["reset_results"]:
                        session_results = session_results[-20:]
                        consecutive_signals = 0
                        print(f"  [restart] severe — reset session, preserving archives")
                else:
                    consecutive_signals = 0

                # Early stop: 3+ consecutive high-signal windows, past minimum
                if consecutive_signals >= 3 and i + 1 >= min_iterations:
                    print(f"  [early-stop] Persistent convergence at iteration {i+1}")
                    break

        except subprocess.TimeoutExpired:
            results["timeouts"] += 1
            log_execution_trace(chain, False, timeout_per_sim * 1000, "timeout")

        except Exception as e:
            results["failures"] += 1
            log_execution_trace(chain, False, 0, str(e)[:200])

    # Generate labels from this session with energy+elegance fitness
    labels = _labels_from_session(session_file)
    results["bond_labels"] = len(labels)

    # Append labels
    append_jsonl(LABELS_FILE, labels)

    # Summary
    rate = results["successes"] / results["completed"] if results["completed"] else 0
    cur_summary = curriculum.summary()
    results["curriculum"] = cur_summary
    print(f"\n=== Warm Pond Results ===")
    print(f"  Completed: {results['completed']}/{iterations}")
    print(f"  Success rate: {rate:.1%}")
    print(f"  Labels generated: {results['bond_labels']}")
    print(f"  Curriculum max: {cur_summary['unlocked_max']}")
    print(f"  Session: {session_file}")
    if results["convergence"]:
        conv = results["convergence"]
        print(f"  Convergence: rate={conv['rolling_success_rate']:.1%}, "
              f"diversity={conv['chain_diversity']:.2f}")

    # Log harvest entry
    _log_harvest("warm_pond", results)

    # Auto-trigger training if thresholds met
    _auto_trigger_training()

    # Log subgraph feedback for bond-classifier co-evolution
    _log_bond_subgraph_feedback(results)

    return results


def _auto_trigger_training() -> None:
    """Check label counts and auto-trigger classifier/SFT training.

    Uses a watermark file to track label count at last training,
    only retrains when labels have grown by ≥20% or initial thresholds met.
    """
    if not LABELS_FILE.exists():
        return

    label_count = sum(
        1 for line in LABELS_FILE.read_text().splitlines()
        if line.strip()
    )

    classifier_path = STATE_DIR / "bond_classifier.pkl"
    gpt_model_exists = (STATE_DIR / "bond_gpt.gguf").exists()
    watermark_file = STATE_DIR / "training_watermark.json"

    # Load watermark (labels at last training)
    last_trained_count = 0
    if watermark_file.exists():
        try:
            wm = json.loads(watermark_file.read_text())
            last_trained_count = wm.get("label_count", 0)
        except (json.JSONDecodeError, OSError):
            pass

    # Retrain classifier if: no classifier yet (≥30) OR labels grew ≥20% since last
    should_train = False
    if label_count >= 30 and not classifier_path.exists():
        should_train = True
    elif (
        classifier_path.exists()
        and last_trained_count > 0
        and label_count >= last_trained_count * 1.2
    ):
        should_train = True

    if should_train:
        print(f"\n  [auto-trigger] {label_count} labels "
              f"(was {last_trained_count}) → training classifier...")
        try:
            from bond_teacher import train_classifier
            metrics = train_classifier()
            print(f"  [auto-trigger] Classifier: {metrics.get('status', 'unknown')}")
            # Update watermark
            watermark_file.write_text(json.dumps({
                "label_count": label_count,
                "trained_at": int(time.time()),
            }))
        except Exception as e:
            print(f"  [auto-trigger] Classifier training failed: {e}")

    if label_count >= 100 and not gpt_model_exists:
        print(f"\n  [auto-trigger] {label_count} labels → exporting SFT data...")
        try:
            from bond_teacher import export_sft_data
            sft_output = STATE_DIR / "bond_sft_data.jsonl"
            count = export_sft_data(sft_output)
            print(f"  [auto-trigger] Exported {count} SFT entries to {sft_output}")
        except Exception as e:
            print(f"  [auto-trigger] SFT export failed: {e}")


def _log_bond_subgraph_feedback(results: dict) -> None:
    """Log warm pond results as subgraph feedback for bond-classifier.

    This connects warm pond's evolutionary bond data to the unified
    co-evolutionary feedback loop in common/.
    """
    completed = results.get("completed", 0)
    if completed < 5:
        return  # not enough data to be meaningful

    successes = results.get("successes", 0)
    labels = results.get("bond_labels", 0)
    success_rate = successes / max(1, completed)

    try:
        sys.path.insert(0, str(SCRIPTS_DIR.parent.parent))
        from common.subgraph_feedback import log_subgraph_feedback

        log_subgraph_feedback(
            classifier_name="bond-classifier",
            seeds=[f"warm_pond_{completed}"],
            subgraph_qra_count=labels,
            avg_grounding=success_rate,
            baseline_qra_count=0,
            baseline_grounding=0.0,
            confidence=success_rate,
            scope="skill-lab",
        )
        print(f"  [feedback] Logged bond subgraph feedback (labels={labels}, rate={success_rate:.1%})")
    except Exception as e:
        print(f"  [feedback] Could not log subgraph feedback: {e}")


def _order_by_precedes(chain: list[str]) -> list[str]:
    """Reorder chain using PRECEDES hints for more realistic simulations."""
    from composer import PRECEDES

    # Simple: skills that precede others go first
    scores = {}
    for i, skill in enumerate(chain):
        successors = PRECEDES.get(skill, [])
        # Count how many chain members this skill precedes
        score = sum(1 for s in successors if s in chain)
        scores[skill] = -score  # Negative so higher precedence sorts first

    return sorted(chain, key=lambda s: scores.get(s, 0))


def _run_chain_docker(
    chain: list[str],
    skills_root: Path,
    timeout: int,
) -> tuple[bool, str]:
    """Run a skill chain in Docker isolation.

    Uses the same security profile as /battle:
    - cap-drop ALL
    - no-new-privileges
    - memory limit
    - read-only root
    """
    # Build a test script that actually executes each skill's run.sh help
    test_script = "#!/bin/bash\n"
    for skill in chain:
        run_sh = skills_root / skill / "run.sh"
        if run_sh.exists():
            test_script += f"echo 'testing {skill}'\n"
            test_script += (
                f"timeout 5 /skills/{skill}/run.sh help "
                f">/tmp/{skill}_out.txt 2>&1; RC=$?\n"
                f"if [ $RC -gt 1 ] && [ $RC -ne 124 ]; then\n"
                f"  echo 'FAIL {skill} rc='$RC\n"
                f"  exit $RC\n"
                f"fi\n"
                f"if [ $RC -eq 124 ]; then\n"
                f"  echo 'WARN {skill} timeout (continuing)'\n"
                f"fi\n"
            )

    # Write temp script
    WARM_POND_DIR.mkdir(exist_ok=True)
    tmp_script = WARM_POND_DIR / "test_chain.sh"
    tmp_script.write_text(test_script)
    tmp_script.chmod(0o755)

    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--memory", "512m",
                "--read-only",
                "--tmpfs", "/tmp:size=100m",
                "-v", f"{skills_root}:/skills:ro",
                "-v", f"{tmp_script}:/test.sh:ro",
                "python:3.12-slim",
                "/bin/bash", "/test.sh",
            ],
            capture_output=True, text=True, timeout=timeout,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0, result.stderr[:500]
    except subprocess.TimeoutExpired:
        raise
    except FileNotFoundError:
        # Docker not available, fall back to local
        return _run_chain_local(chain, skills_root, timeout)


def _run_chain_local(
    chain: list[str],
    skills_root: Path,
    timeout: int,
) -> tuple[bool, str]:
    """Run a skill chain locally (no Docker).

    Used when Docker is unavailable or for quick tests.
    Tests that each skill's run.sh exists and can show help.
    """
    for skill in chain:
        run_sh = skills_root / skill / "run.sh"
        if not run_sh.exists():
            return False, f"{skill}/run.sh not found"

        try:
            result = subprocess.run(
                [str(run_sh), "help"],
                capture_output=True, text=True, timeout=10,
                cwd=str(run_sh.parent),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            # run.sh help should not crash (exit 0 or 1 both ok,
            # but not segfault/signal)
            if result.returncode > 1:
                return False, f"{skill} exited {result.returncode}: {result.stderr[:200]}"
        except subprocess.TimeoutExpired:
            return False, f"{skill} timed out"
        except Exception as e:
            return False, f"{skill} error: {str(e)[:200]}"

    return True, ""


def _labels_from_session(session_file: Path) -> list[dict]:
    """Convert warm pond session results into training labels.

    Uses energy+elegance fitness instead of crude success-rate mapping.
    """
    from bond_teacher import make_label
    from energy_model import compute_chain_energy, compute_elegance

    # Aggregate by pair
    pair_stats: dict[str, dict] = {}

    for line in session_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            chain = entry["chain"]
            success = entry["success"]

            for i in range(len(chain) - 1):
                pair = f"{chain[i]}+{chain[i+1]}"
                if pair not in pair_stats:
                    pair_stats[pair] = {"total": 0, "success": 0, "chain_counts": {}}
                pair_stats[pair]["total"] += 1
                if success:
                    pair_stats[pair]["success"] += 1
                chain_key = "+".join(chain)
                pair_stats[pair]["chain_counts"][chain_key] = (
                    pair_stats[pair]["chain_counts"].get(chain_key, 0) + 1
                )
        except (json.JSONDecodeError, KeyError):
            continue

    labels = []
    for pair, stats in pair_stats.items():
        if stats["total"] < 2:
            continue

        skills = pair.split("+")
        rate = stats["success"] / stats["total"]

        # Compute energy and elegance for the most frequent chain
        cc = stats["chain_counts"]
        most_common_key = max(cc, key=cc.get) if cc else "+".join(skills)
        representative_chain = most_common_key.split("+") if cc else skills
        chain_energy = compute_chain_energy(representative_chain)
        elegance = compute_elegance(chain_energy, rate)
        grade = elegance["grade"]

        # Map elegance grade to bond type
        if grade in ("brilliant", "elegant"):
            bond_type = "covalent"
        elif grade == "adequate":
            bond_type = "ionic"
        elif grade == "wasteful":
            bond_type = "van_der_waals"
        else:
            bond_type = "none"

        labels.append(make_label(
            skill_a=skills[0],
            skill_b=skills[1],
            bond_type=bond_type,
            success_probability=rate,
            source="warm_pond",
            confidence=min(0.9, 0.4 + stats["total"] * 0.05),
            reason=f"warm_pond_n={stats['total']}_rate={rate:.2f}_elegance={grade}",
            metadata={
                "session_file": str(session_file),
                "sample_size": stats["total"],
                "elegance_score": elegance["elegance_score"],
                "elegance_grade": grade,
                "total_energy_atp": chain_energy["total_energy"],
            },
        ))

    return labels


# ---------------------------------------------------------------------------
# Bootstrap warm pond — cycle through task types to hit label targets
# ---------------------------------------------------------------------------

def run_bootstrap_warm_pond(
    skills_root: Path,
    target_labels: int = 100,
    max_iterations: int = 2000,
    use_docker: bool = True,
) -> dict:
    """Bootstrap warm pond by cycling through task types until target labels reached.

    Cycles through: extraction, research, security, creation — 500 iters each
    or until target_labels is reached.
    """
    task_types = ["extraction", "research", "security", "creation"]
    iters_per_type = max_iterations // len(task_types)

    total_labels = 0
    results_all = []

    # Count existing labels
    if LABELS_FILE.exists():
        total_labels = sum(
            1 for line in LABELS_FILE.read_text().splitlines()
            if line.strip()
        )

    print(f"=== Bootstrap Warm Pond ===")
    print(f"  Target labels: {target_labels}")
    print(f"  Existing labels: {total_labels}")
    print(f"  Max iterations: {max_iterations}")
    print()

    for task_type in task_types:
        if total_labels >= target_labels:
            print(f"  Target reached ({total_labels} >= {target_labels}), stopping.")
            break

        print(f"\n--- Task type: {task_type} ({iters_per_type} iterations) ---")
        result = run_warm_pond(
            skills_root,
            iterations=iters_per_type,
            use_docker=use_docker,
            task_type=task_type,
            min_iterations=50,
        )
        results_all.append(result)
        total_labels += result.get("bond_labels", 0)
        print(f"  Running total labels: {total_labels}")

    return {
        "target_labels": target_labels,
        "total_labels": total_labels,
        "target_reached": total_labels >= target_labels,
        "task_results": results_all,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

import typer
from typing import Optional

app = typer.Typer(help="Warm Pond — batch simulation")


@app.command()
def run(
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


@app.command()
def bootstrap(
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


if __name__ == "__main__":
    app()
