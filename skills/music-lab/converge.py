"""Music Lab convergence loop — thin orchestrator over existing skills.

Generates audio → analyzes with MIR → scores delta against spec → re-quantizes → repeats.
All heavy lifting via subprocess calls to existing skill run.sh files.
"""
import os
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(help="Music Lab convergence loop")

SKILLS_DIR = Path(__file__).resolve().parent.parent
CONVERGENCE_THRESHOLD = 0.3
DEFAULT_MAX_ROUNDS = 5

# Delta scoring weights
WEIGHTS = {
    "tempo_delta": 0.20,
    "key_match": 0.20,
    "chord_accuracy": 0.25,
    "dynamics_rmse": 0.20,
    "timing_drift_ms": 0.15,
}


def _run_skill(skill_name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a skill via its run.sh entry point."""
    run_sh = SKILLS_DIR / skill_name / "run.sh"
    if not run_sh.exists():
        logger.error(f"Skill not found: {run_sh}")
        raise typer.Exit(1)
    cmd = ["bash", str(run_sh), *args]
    logger.info(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=check,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )


def _score_delta(spec_path: Path, features_path: Path) -> dict:
    """Compare /review-music features against piano-roll-spec ground truth.

    This is the ONLY new logic in music-lab (~50 lines). Everything else
    is subprocess orchestration.

    Returns dict with per-dimension deltas and weighted aggregate score.
    """
    spec = json.loads(spec_path.read_text())
    features = json.loads(features_path.read_text())

    spec_bpm = spec.get("bpm", 120)
    feat_bpm = features.get("bpm", 120)
    tempo_delta = abs(spec_bpm - feat_bpm) / spec_bpm

    spec_key = spec.get("key", "C major").lower()
    feat_key = features.get("key", "").lower()
    key_match = 0.0 if spec_key == feat_key else 1.0

    spec_chords = []
    for section in spec.get("sections", []):
        spec_chords.extend(section.get("chord_progression", []))
    feat_chords = features.get("chords", [])
    if spec_chords and feat_chords:
        matches = sum(
            1 for s, f in zip(spec_chords, feat_chords)
            if s.lower() == f.lower()
        )
        chord_accuracy = 1.0 - (matches / max(len(spec_chords), 1))
    else:
        chord_accuracy = 0.5

    spec_energy = []
    for section in spec.get("sections", []):
        spec_energy.extend(section.get("energy_curve", []))
    feat_energy = features.get("energy_curve", features.get("dynamics", []))
    if spec_energy and feat_energy:
        min_len = min(len(spec_energy), len(feat_energy))
        squared_diffs = [(spec_energy[i] - feat_energy[i]) ** 2 for i in range(min_len)]
        dynamics_rmse = math.sqrt(sum(squared_diffs) / min_len)
    else:
        dynamics_rmse = 0.5

    timing_drift_ms = features.get("timing_drift_ms", 50.0)
    timing_score = min(timing_drift_ms / 200.0, 1.0)

    scores = {
        "tempo_delta": round(tempo_delta, 4),
        "key_match": round(key_match, 4),
        "chord_accuracy": round(chord_accuracy, 4),
        "dynamics_rmse": round(dynamics_rmse, 4),
        "timing_drift_ms": round(timing_score, 4),
    }

    aggregate = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
    scores["aggregate"] = round(aggregate, 4)
    scores["converged"] = aggregate < CONVERGENCE_THRESHOLD

    return scores


@app.command()
def converge(
    spec: str = typer.Option(..., help="Path to piano-roll-spec.json"),
    lyrics: str = typer.Option(..., help="Path to annotated-lyrics.json"),
    out: str = typer.Option(..., help="Output directory for rounds"),
    backend: str = typer.Option("yue", help="Audio backend: yue or sonauto"),
    max_rounds: int = typer.Option(DEFAULT_MAX_ROUNDS, help="Maximum convergence rounds"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip generation, use mock features"),
):
    """Run the convergence loop: generate → analyze → score → re-quantize → repeat."""
    spec_path = Path(spec)
    lyrics_path = Path(lyrics)
    out_dir = Path(out)

    if not spec_path.exists():
        logger.error(f"Spec not found: {spec_path}")
        raise typer.Exit(1)
    if not lyrics_path.exists():
        logger.error(f"Lyrics not found: {lyrics_path}")
        raise typer.Exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    all_rounds = []
    logger.info(f"Starting convergence: backend={backend}, max_rounds={max_rounds}, threshold={CONVERGENCE_THRESHOLD}")

    for round_num in range(1, max_rounds + 1):
        round_dir = out_dir / f"round_{round_num}"
        round_dir.mkdir(exist_ok=True)
        logger.info(f"=== Round {round_num}/{max_rounds} ===")

        if dry_run:
            logger.info("Dry run — using mock features")
            mock_features = {
                "bpm": json.loads(spec_path.read_text()).get("bpm", 120) + round_num * 2,
                "key": json.loads(spec_path.read_text()).get("key", "C major"),
                "chords": [],
                "energy_curve": [],
                "timing_drift_ms": 100.0 - round_num * 15,
            }
            features_path = round_dir / "features.json"
            features_path.write_text(json.dumps(mock_features, indent=2))
        else:
            # Step 1: Generate audio
            audio_path = round_dir / "audio.wav"
            logger.info(f"Generating audio with {backend}...")
            _run_skill("create-music", backend, "--lyrics", str(lyrics_path),
                        "--out", str(round_dir))

            # Step 2: Analyze with /review-music
            logger.info("Analyzing audio...")
            result = _run_skill("review-music", "analyze",
                                "--audio", str(audio_path),
                                "--out", str(round_dir / "features.json"),
                                check=False)
            if result.returncode != 0:
                logger.warning(f"review-music failed: {result.stderr[:200]}")

            features_path = round_dir / "features.json"
            if not features_path.exists():
                logger.error("No features.json produced — skipping round")
                continue

        # Step 3: Score delta
        delta = _score_delta(spec_path, features_path)
        delta_path = round_dir / "delta.json"
        delta_path.write_text(json.dumps(delta, indent=2))
        logger.info(f"Delta: aggregate={delta['aggregate']}, converged={delta['converged']}")

        round_result = {
            "round": round_num,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "delta": delta,
            "backend": backend,
            "dry_run": dry_run,
        }
        all_rounds.append(round_result)

        if delta["converged"]:
            logger.info(f"Converged at round {round_num}! aggregate={delta['aggregate']}")
            break

        # Step 4: Re-quantize prompts (only for non-dry-run)
        if not dry_run:
            logger.info("Re-quantizing prompts via /prompt-lab...")
            _run_skill("prompt-lab", "iterate",
                        "--context", json.dumps(delta),
                        check=False)

    # Write loop results
    results_path = out_dir / "loop_results.json"
    results = {
        "spec": str(spec_path),
        "lyrics": str(lyrics_path),
        "backend": backend,
        "max_rounds": max_rounds,
        "threshold": CONVERGENCE_THRESHOLD,
        "rounds": all_rounds,
        "final_aggregate": all_rounds[-1]["delta"]["aggregate"] if all_rounds else None,
        "converged": all_rounds[-1]["delta"]["converged"] if all_rounds else False,
    }
    results_path.write_text(json.dumps(results, indent=2))
    logger.info(f"Results written to {results_path}")

    if not results["converged"]:
        logger.warning(f"Did not converge after {max_rounds} rounds (best: {results['final_aggregate']})")


@app.command()
def status():
    """Check status of running convergence (reads loop_results.json)."""
    logger.info("Status check — look for loop_results.json in output directory")


@app.command()
def nightly():
    """Nightly wrapper — reads projects.json and runs convergence on active projects."""
    projects_path = Path(__file__).parent / "projects.json"
    if not projects_path.exists():
        logger.info("No projects.json found — nothing to run")
        raise typer.Exit(0)

    projects = json.loads(projects_path.read_text())
    for project in projects:
        if not project.get("active", True):
            continue
        logger.info(f"Running convergence for: {project['name']}")
        converge(
            spec=project["spec"],
            lyrics=project["lyrics"],
            out=project["out"],
            backend=project.get("backend", "yue"),
            max_rounds=project.get("max_rounds", DEFAULT_MAX_ROUNDS),
            dry_run=False,
        )


if __name__ == "__main__":
    app()
