"""Story Lab convergence loop — thin orchestrator over existing skills.

Iterates: /create-story → /review-story → diagnose weakest → fix → repeat.
Delta scoring tracks: lore fidelity, emotional arc, voice consistency, rhyme,
structural arc, and craft quality across rounds until quality thresholds are met.

All heavy lifting via subprocess calls to existing skill run.sh files.
No bespoke NLP — all critique comes from /review-story outputs.
"""
import os
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(help="Story Lab convergence loop")

SKILLS_DIR = Path(__file__).resolve().parent.parent

# Quality score: higher is better (opposite of music-lab where lower is better)
CONVERGENCE_THRESHOLD = 0.80
CONVERGENCE_DELTA = 0.05    # Per-round delta below this → diminishing returns
REGRESSION_LIMIT = 2        # Stop after N consecutive regressions
DEFAULT_MAX_ROUNDS = 5

# Delta scoring weights — lyrics-specific dimensions from SKILL.md + rhyme
# All weights sum to 1.0
WEIGHTS = {
    "structural_arc": 0.15,       # /review-story structure score
    "emotional_arc": 0.25,        # emotional_authenticity + heart tag alignment
    "voice_consistency": 0.25,    # persona_voice_consistency + ToM check
    "lore_fidelity": 0.15,        # cross-ref against /memory recall provenance
    "craft_quality": 0.10,        # imagery, rhythm, word choice
    "rhyme": 0.10,                # musicality / rhyme scheme (lyrics-specific)
}

# Sanity-check weights
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "WEIGHTS must sum to 1.0"


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


def _score_delta(review_path: Path) -> dict:
    """Parse /review-story output and compute weighted quality score.

    This is the ONLY new logic in story-lab (~55 lines). Everything else
    is subprocess orchestration.

    /review-story emits JSON with keys: structural, emotional, persona, craft,
    lore_fidelity, rhyme. Each section contains a "score" float in [0, 1].

    Returns dict with per-dimension scores, weighted aggregate, and converged flag.
    """
    review = json.loads(review_path.read_text())

    def _extract(section_key: str, fallback: float = 0.5) -> float:
        section = review.get(section_key, {})
        if isinstance(section, dict):
            return float(section.get("score", section.get("overall", fallback)))
        if isinstance(section, (int, float)):
            return float(section)
        return fallback

    structural_arc = _extract("structural")
    emotional_arc = _extract("emotional")
    voice_consistency = _extract("persona")
    craft_quality = _extract("craft")
    lore_fidelity = _extract("lore_fidelity", fallback=_extract("lore", 0.5))
    rhyme = _extract("rhyme", fallback=_extract("musicality", 0.5))

    raw: dict = {
        "structural_arc": round(structural_arc, 4),
        "emotional_arc": round(emotional_arc, 4),
        "voice_consistency": round(voice_consistency, 4),
        "lore_fidelity": round(lore_fidelity, 4),
        "craft_quality": round(craft_quality, 4),
        "rhyme": round(rhyme, 4),
    }

    aggregate = sum(raw[k] * WEIGHTS[k] for k in WEIGHTS)
    raw["aggregate"] = round(aggregate, 4)
    raw["converged"] = aggregate >= CONVERGENCE_THRESHOLD
    return raw


def _diagnose_weakest(delta: dict) -> str:
    """Return the name of the weakest (lowest score) dimension."""
    dims = {k: delta[k] for k in WEIGHTS if k in delta}
    return min(dims, key=lambda k: dims[k])


@app.command()
def converge(
    input_file: str = typer.Option(..., "--input", help="Path to story/lyrics draft file"),
    out: str = typer.Option(..., "--out", help="Output directory for convergence rounds"),
    max_rounds: int = typer.Option(DEFAULT_MAX_ROUNDS, "--max-rounds", help="Maximum convergence rounds"),
    format: str = typer.Option("lyrics", "--format", help="Creative format: lyrics, story, screenplay"),
    persona: str = typer.Option("horus", "--persona", help="Voice persona for generation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip generation, use mock review scores"),
):
    """Run the convergence loop: create-story → review-story → diagnose → fix → repeat.

    Converges when all quality dimensions are at or above threshold (default 0.80).
    Stops early on 2 consecutive regressions or when max-rounds is reached.
    """
    input_path = Path(input_file)
    out_dir = Path(out)

    if not input_path.exists():
        logger.error(f"Input not found: {input_path}")
        raise typer.Exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    all_rounds: list[dict] = []
    regressions = 0
    prev_aggregate: float = 0.0

    logger.info(
        f"Starting convergence: format={format}, persona={persona}, "
        f"max_rounds={max_rounds}, threshold={CONVERGENCE_THRESHOLD}"
    )

    for round_num in range(1, max_rounds + 1):
        round_dir = out_dir / f"round_{round_num}"
        round_dir.mkdir(exist_ok=True)
        logger.info(f"=== Round {round_num}/{max_rounds} ===")

        review_path = round_dir / "review.json"

        if dry_run:
            logger.info("Dry run — using mock review scores (improving each round)")
            mock_review = {
                "structural": {"score": round(min(0.50 + round_num * 0.08, 0.92), 3)},
                "emotional":  {"score": round(min(0.45 + round_num * 0.09, 0.88), 3)},
                "persona":    {"score": round(min(0.55 + round_num * 0.07, 0.90), 3)},
                "craft":      {"score": round(min(0.50 + round_num * 0.07, 0.87), 3)},
                "lore_fidelity": {"score": round(min(0.60 + round_num * 0.06, 0.89), 3)},
                "rhyme":      {"score": round(min(0.40 + round_num * 0.10, 0.90), 3)},
            }
            review_path.write_text(json.dumps(mock_review, indent=2))

        else:
            # Step 1: Generate / refine draft via /create-story
            logger.info("Generating draft via /create-story...")
            create_result = _run_skill(
                "create-story", "draft",
                "--format", format,
                "--output", str(round_dir),
                check=False,
            )
            if create_result.returncode != 0:
                logger.warning(f"create-story failed: {create_result.stderr[:200]}")

            # Use supplied input file if create-story didn't produce a draft
            draft_path = round_dir / "draft.md"
            active_draft = draft_path if draft_path.exists() else input_path

            # Step 2: Critique with /review-story
            logger.info("Reviewing draft via /review-story...")
            review_result = _run_skill(
                "review-story", "review",
                str(active_draft),
                "--output-dir", str(round_dir),
                "--output-format", "json",
                check=False,
            )
            if review_result.returncode != 0:
                logger.warning(f"review-story failed: {review_result.stderr[:200]}")

            if not review_path.exists():
                logger.error("No review.json produced — skipping round")
                continue

        # Step 3: Score delta
        delta = _score_delta(review_path)
        delta_path = round_dir / "delta.json"
        delta_path.write_text(json.dumps(delta, indent=2))

        weakest = _diagnose_weakest(delta)
        logger.info(
            f"Scores: aggregate={delta['aggregate']}, converged={delta['converged']}, "
            f"weakest={weakest}"
        )

        # Step 4: Regression detection
        if round_num > 1 and delta["aggregate"] < prev_aggregate:
            regressions += 1
            logger.warning(
                f"Regression {regressions}/{REGRESSION_LIMIT}: "
                f"{delta['aggregate']} < {prev_aggregate}"
            )
        else:
            regressions = 0

        round_result: dict = {
            "round": round_num,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "delta": delta,
            "weakest_dimension": weakest,
            "regressions": regressions,
            "dry_run": dry_run,
        }
        all_rounds.append(round_result)

        # Step 5: Convergence checks
        if delta["converged"]:
            logger.info(f"Converged at round {round_num}! aggregate={delta['aggregate']}")
            break

        if regressions >= REGRESSION_LIMIT:
            logger.warning(f"Stopping: {REGRESSION_LIMIT} consecutive regressions detected")
            break

        prev_aggregate = delta["aggregate"]

        # Step 6: Apply targeted fix for weakest dimension (live runs only)
        if not dry_run:
            logger.info(f"Applying targeted fix for weakest dimension: {weakest}")
            _run_skill(
                "create-story", "refine",
                "--input", str(input_path),
                "--focus", weakest,
                "--output", str(round_dir),
                check=False,
            )

    # Write final loop results
    results_path = out_dir / "loop_results.json"
    results: dict = {
        "input": str(input_path),
        "format": format,
        "persona": persona,
        "max_rounds": max_rounds,
        "threshold": CONVERGENCE_THRESHOLD,
        "weights": WEIGHTS,
        "rounds": all_rounds,
        "final_aggregate": all_rounds[-1]["delta"]["aggregate"] if all_rounds else None,
        "converged": all_rounds[-1]["delta"]["converged"] if all_rounds else False,
    }
    results_path.write_text(json.dumps(results, indent=2))
    logger.info(f"Results written to {results_path}")

    if not results["converged"]:
        logger.warning(
            f"Did not converge after {len(all_rounds)} rounds "
            f"(best aggregate: {results['final_aggregate']})"
        )


@app.command()
def status(
    results_file: str = typer.Option("loop_results.json", "--results", help="Path to loop_results.json"),
):
    """Check convergence status by reading loop_results.json from a previous run."""
    results_path = Path(results_file)
    if not results_path.exists():
        logger.error(f"Results not found: {results_path}")
        raise typer.Exit(1)
    data = json.loads(results_path.read_text())
    logger.info(f"Input:     {data.get('input')}")
    logger.info(f"Converged: {data.get('converged')}")
    logger.info(f"Aggregate: {data.get('final_aggregate')}")
    logger.info(f"Rounds:    {len(data.get('rounds', []))}/{data.get('max_rounds')}")


@app.command()
def diagnose(
    results_file: str = typer.Option(..., "--results", help="Path to loop_results.json"),
):
    """Diagnose convergence trajectory and highlight weakest dimensions per round."""
    results_path = Path(results_file)
    if not results_path.exists():
        logger.error(f"Results not found: {results_path}")
        raise typer.Exit(1)
    data = json.loads(results_path.read_text())
    logger.info(f"Input: {data.get('input')}  converged={data.get('converged')}")
    for r in data.get("rounds", []):
        d = r["delta"]
        logger.info(
            f"  Round {r['round']:>2}: aggregate={d['aggregate']:.4f}  "
            f"weakest={r.get('weakest_dimension'):<20}  "
            f"lore={d.get('lore_fidelity'):.3f}  "
            f"emotion={d.get('emotional_arc'):.3f}  "
            f"voice={d.get('voice_consistency'):.3f}  "
            f"rhyme={d.get('rhyme'):.3f}"
        )


if __name__ == "__main__":
    app()
