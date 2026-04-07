"""Convergence loop for iterative paper refinement via Shadow-LEGO.

Implements the self-improving review-refine cycle described in the
Shadow-LEGO paper. Each round: review → compute_delta → check_convergence
→ extract_revision_notes → apply_revisions → snapshot → loop.

The paper must be built using its own technique. This module IS the
meta-recursive loop that makes the paper self-referential.

Adapted from paper-lab's SKILL.md convergence spec for peer review.
"""

from __future__ import annotations
import os

import json
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger


SKILL_DIR = Path(__file__).parent.parent
SKILLS_DIR = SKILL_DIR.parent


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RoundResult:
    """Result of a single convergence round."""
    round_num: int
    overall_score: float = 0.0
    decision: str = ""
    reviewer_scores: dict[str, float] = field(default_factory=dict)
    dimension_averages: dict[str, float] = field(default_factory=dict)
    section_scores: dict[str, float] = field(default_factory=dict)
    revision_notes: dict[str, list[str]] = field(default_factory=dict)
    snapshot_path: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ConvergenceTrajectory:
    """Full convergence trajectory across all rounds."""
    paper_dir: str
    threshold: float = 6.0
    epsilon: float = 0.5
    max_rounds: int = 5
    rounds: list[RoundResult] = field(default_factory=list)
    converged: bool = False
    stop_reason: str = ""
    final_score: float = 0.0
    total_shadow_entries: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def save(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "convergence.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info(f"Saved convergence trajectory to {path}")
        return path


# ---------------------------------------------------------------------------
# Delta computation
# ---------------------------------------------------------------------------

def compute_delta(
    current: RoundResult,
    previous: Optional[RoundResult],
) -> dict:
    """Compute score deltas between consecutive rounds.

    Returns per-dimension and per-section deltas, plus aggregate delta.
    """
    if previous is None:
        return {
            "delta": 0.0,
            "dimension_deltas": {},
            "section_deltas": {},
            "round": current.round_num,
        }

    overall_delta = current.overall_score - previous.overall_score

    # Per-dimension deltas
    dim_deltas = {}
    for dim in current.dimension_averages:
        prev_val = previous.dimension_averages.get(dim, 0.0)
        curr_val = current.dimension_averages[dim]
        dim_deltas[dim] = {
            "prev": prev_val,
            "curr": curr_val,
            "delta": round(curr_val - prev_val, 3),
        }

    # Per-section deltas
    sec_deltas = {}
    for sec in current.section_scores:
        prev_val = previous.section_scores.get(sec, 0.0)
        curr_val = current.section_scores[sec]
        sec_deltas[sec] = {
            "prev": prev_val,
            "curr": curr_val,
            "delta": round(curr_val - prev_val, 3),
        }

    return {
        "delta": round(overall_delta, 3),
        "dimension_deltas": dim_deltas,
        "section_deltas": sec_deltas,
        "round": current.round_num,
    }


# ---------------------------------------------------------------------------
# Convergence check
# ---------------------------------------------------------------------------

def check_convergence(
    trajectory: ConvergenceTrajectory,
    delta: dict,
) -> tuple[bool, str]:
    """Check five stopping criteria. Returns (should_stop, reason).

    Criteria (any terminates):
    1. Quality met: overall_score >= threshold (ICLR Accept)
    2. Stability: |delta| < epsilon for 2 consecutive rounds
    3. Max rounds: round >= max_rounds
    4. Regression: score dropped 2 consecutive rounds
    5. Decisive argument: high-confidence reviewer scored < 4.0
    """
    rounds = trajectory.rounds
    if not rounds:
        return False, ""

    current = rounds[-1]

    # 1. Quality met
    if current.overall_score >= trajectory.threshold:
        return True, f"quality_met: score {current.overall_score:.2f} >= {trajectory.threshold}"

    # 2. Stability (need at least 2 rounds of deltas)
    if len(rounds) >= 3:
        recent_deltas = []
        for i in range(max(0, len(rounds) - 2), len(rounds)):
            prev = rounds[i - 1] if i > 0 else None
            d = compute_delta(rounds[i], prev)
            recent_deltas.append(abs(d["delta"]))
        if len(recent_deltas) >= 2 and all(d < trajectory.epsilon for d in recent_deltas[-2:]):
            return True, (
                f"stability: |delta| < {trajectory.epsilon} for 2 consecutive rounds "
                f"(deltas: {recent_deltas[-2:]!r})"
            )

    # 3. Max rounds
    if current.round_num >= trajectory.max_rounds:
        return True, f"max_rounds: reached {trajectory.max_rounds}"

    # 4. Regression (score dropped 2 consecutive rounds)
    if len(rounds) >= 3:
        r1, r2, r3 = rounds[-3], rounds[-2], rounds[-1]
        if r2.overall_score < r1.overall_score and r3.overall_score < r2.overall_score:
            return True, (
                f"regression: score dropped 2 consecutive rounds "
                f"({r1.overall_score:.2f} → {r2.overall_score:.2f} → {r3.overall_score:.2f})"
            )

    # 5. Decisive argument (check meta-review disagreements)
    # This is detected during review and stored in the meta_review
    reviews_dir = Path(trajectory.paper_dir) / "reviews"
    meta_path = reviews_dir / "meta_review.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        for d in meta.get("disagreements", []):
            if "DECISIVE" in d:
                return True, f"decisive_argument: {d}"

    return False, ""


# ---------------------------------------------------------------------------
# Revision notes extraction (Task 3)
# ---------------------------------------------------------------------------

def extract_revision_notes(
    meta_review_path: Path,
    review_dir: Optional[Path] = None,
) -> dict[str, list[str]]:
    """Parse MetaReview + per-reviewer SectionReviews into section feedback.

    Bridges peer review output to /create-paper refine input:
        MetaReview.revision_priority + SectionReview.weaknesses
        → {section_key: [feedback_string, ...]}

    Each feedback string is actionable and suitable for:
        bash run.sh refine paper_dir --section X --feedback "..."
    """
    if not meta_review_path.exists():
        logger.warning(f"Meta-review not found: {meta_review_path}")
        return {}

    meta = json.loads(meta_review_path.read_text())
    revision_priority = meta.get("revision_priority", [])

    # Collect per-section weaknesses from individual reviews
    section_feedback: dict[str, list[str]] = {}
    review_dir = review_dir or meta_review_path.parent

    for review_file in review_dir.glob("*_review.json"):
        if review_file.name == "meta_review.json":
            continue
        try:
            review = json.loads(review_file.read_text())
        except json.JSONDecodeError:
            continue

        reviewer_name = review.get("reviewer_name", "Anonymous")
        for sr in review.get("section_reviews", []):
            section_key = sr.get("section_key", "")
            if not section_key:
                continue

            weaknesses = sr.get("weaknesses", [])
            suggestions = sr.get("suggestions", [])

            for w in weaknesses:
                section_feedback.setdefault(section_key, []).append(
                    f"[{reviewer_name}] Weakness: {w}"
                )
            for s in suggestions:
                section_feedback.setdefault(section_key, []).append(
                    f"[{reviewer_name}] Suggestion: {s}"
                )

    # Add revision priority items as general feedback
    for priority_item in revision_priority[:5]:
        # Try to attribute to a section based on content
        attributed = False
        for section_key in section_feedback:
            if section_key.lower() in priority_item.lower():
                section_feedback[section_key].insert(
                    0, f"[META-REVIEW PRIORITY] {priority_item}"
                )
                attributed = True
                break
        if not attributed:
            # Add to all sections as general guidance
            for section_key in section_feedback:
                section_feedback[section_key].append(
                    f"[META-REVIEW] {priority_item}"
                )

    return section_feedback


def _format_feedback_for_refine(feedback_items: list[str]) -> str:
    """Format a list of feedback items into a single string for /create-paper refine."""
    if not feedback_items:
        return ""
    # Deduplicate and limit to top 5 most important
    seen = set()
    unique = []
    for item in feedback_items:
        normalized = item.strip().lower()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(item)
    return " | ".join(unique[:5])


# ---------------------------------------------------------------------------
# Paper snapshots
# ---------------------------------------------------------------------------

def snapshot_paper(paper_dir: Path, round_num: int) -> Path:
    """Create a versioned snapshot of the paper between rounds.

    Copies sections/*.tex and references.bib to a round-specific directory.
    Allows rollback if a refinement degrades quality.
    """
    snapshot_dir = paper_dir / "reviews" / "snapshots" / f"round_{round_num:02d}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    sections_dir = paper_dir / "sections"
    if sections_dir.exists():
        for tex_file in sections_dir.glob("*.tex"):
            shutil.copy2(tex_file, snapshot_dir / tex_file.name)

    bib_file = paper_dir / "references.bib"
    if bib_file.exists():
        shutil.copy2(bib_file, snapshot_dir / "references.bib")

    logger.info(f"Snapshot round {round_num} saved to {snapshot_dir}")
    return snapshot_dir


def restore_snapshot(paper_dir: Path, round_num: int) -> bool:
    """Restore paper sections from a previous snapshot."""
    snapshot_dir = paper_dir / "reviews" / "snapshots" / f"round_{round_num:02d}"
    if not snapshot_dir.exists():
        logger.error(f"Snapshot not found: {snapshot_dir}")
        return False

    sections_dir = paper_dir / "sections"
    for tex_file in snapshot_dir.glob("*.tex"):
        target = sections_dir / tex_file.name
        shutil.copy2(tex_file, target)
        logger.info(f"Restored {tex_file.name} from round {round_num}")

    bib_snapshot = snapshot_dir / "references.bib"
    if bib_snapshot.exists():
        shutil.copy2(bib_snapshot, paper_dir / "references.bib")

    return True


# ---------------------------------------------------------------------------
# Section-level score guard
# ---------------------------------------------------------------------------

def _extract_section_scores(meta: dict) -> dict[str, float]:
    """Extract per-section scores from a meta-review's underlying reviews."""
    section_scores: dict[str, float] = {}
    reviews_dir = Path(meta.get("paper_dir", "")) / "reviews"
    if not reviews_dir.exists():
        return section_scores

    for review_file in reviews_dir.glob("*_review.json"):
        if review_file.name == "meta_review.json":
            continue
        try:
            review = json.loads(review_file.read_text())
        except json.JSONDecodeError:
            continue

        for sr in review.get("section_reviews", []):
            key = sr.get("section_key", "")
            score = sr.get("overall_score", 0.0)
            if key and score > 0:
                if key not in section_scores:
                    section_scores[key] = []
                if isinstance(section_scores[key], list):
                    section_scores[key].append(score)

    # Average across reviewers
    return {
        k: round(sum(v) / len(v), 2) if isinstance(v, list) and v else 0.0
        for k, v in section_scores.items()
    }


def _extract_dimension_averages(reviews_dir: Path) -> dict[str, float]:
    """Extract average dimension scores across all reviewers and sections."""
    dim_totals: dict[str, list[float]] = {}
    dimensions = [
        "soundness", "technical_novelty", "empirical_novelty",
        "significance", "clarity", "presentation",
    ]

    for review_file in reviews_dir.glob("*_review.json"):
        if review_file.name == "meta_review.json":
            continue
        try:
            review = json.loads(review_file.read_text())
        except json.JSONDecodeError:
            continue

        for sr in review.get("section_reviews", []):
            scores = sr.get("scores", {})
            for dim in dimensions:
                val = scores.get(dim, 0.0)
                if val > 0:
                    dim_totals.setdefault(dim, []).append(val)

    return {
        dim: round(sum(vals) / len(vals), 3) if vals else 0.0
        for dim, vals in dim_totals.items()
    }


# ---------------------------------------------------------------------------
# Apply revisions via /create-paper refine
# ---------------------------------------------------------------------------

def apply_revisions(
    paper_dir: Path,
    revision_notes: dict[str, list[str]],
    dry_run: bool = False,
) -> dict[str, bool]:
    """Apply section revisions via /create-paper refine.

    For each section with feedback, invokes:
        bash .pi/skills/create-paper/run.sh refine <paper_dir> \\
            --section <key> --feedback "<feedback>" --rounds 1

    Returns dict of {section_key: success}.
    """
    if dry_run:
        logger.info("[DRY RUN] Would apply revisions to:")
        for key, notes in revision_notes.items():
            logger.info(f"  {key}: {len(notes)} feedback items")
        return {key: True for key in revision_notes}

    paper_run = SKILLS_DIR / "create-paper" / "run.sh"
    if not paper_run.exists():
        logger.warning(f"/create-paper not found at {paper_run}")
        return {}

    results = {}
    for section_key, notes in revision_notes.items():
        if not notes:
            continue

        feedback = _format_feedback_for_refine(notes)
        logger.info(f"Refining {section_key} with {len(notes)} feedback items")

        try:
            result = subprocess.run(
                [
                    "bash", str(paper_run), "refine",
                    str(paper_dir),
                    "--section", section_key,
                    "--feedback", feedback,
                    "--rounds", "1",
                ],
                capture_output=True, text=True, timeout=120,
                cwd=str(SKILLS_DIR / "create-paper"),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            results[section_key] = result.returncode == 0
            if result.returncode != 0:
                logger.warning(f"Refine failed for {section_key}: {result.stderr[:200]}")
        except Exception as e:
            logger.error(f"Refine error for {section_key}: {e}")
            results[section_key] = False

    return results


# ---------------------------------------------------------------------------
# Main convergence loop
# ---------------------------------------------------------------------------

def converge(
    paper_dir: str | Path,
    threshold: float = 6.0,
    max_rounds: int = 5,
    epsilon: float = 0.5,
    dry_run: bool = False,
    shadow: bool = True,
    reviewer_ids: Optional[list[str]] = None,
) -> ConvergenceTrajectory:
    """Run the review-refine convergence loop.

    This is the meta-recursive heart of Shadow-LEGO applied to itself:
    the paper is reviewed by its own cascade, refined based on those
    reviews, and re-reviewed until convergence.

    Args:
        paper_dir: Path to paper directory (must have sections/*.tex)
        threshold: Target overall score (ICLR Accept = 6.0)
        max_rounds: Maximum number of review-refine rounds
        epsilon: Stability threshold for consecutive deltas
        dry_run: If True, review but don't modify files
        shadow: Enable shadow mode for self-improvement data
        reviewer_ids: Specific reviewers (default: all 4)

    Returns:
        ConvergenceTrajectory with per-round results and stop reason
    """
    from .review_engine import ReviewEngine, MetaReview

    paper_dir = Path(paper_dir)
    reviews_dir = paper_dir / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)

    trajectory = ConvergenceTrajectory(
        paper_dir=str(paper_dir),
        threshold=threshold,
        epsilon=epsilon,
        max_rounds=max_rounds,
    )

    logger.info(
        f"Starting convergence loop: threshold={threshold}, "
        f"max_rounds={max_rounds}, epsilon={epsilon}, dry_run={dry_run}"
    )

    for round_num in range(1, max_rounds + 1):
        logger.info(f"=== Convergence Round {round_num}/{max_rounds} ===")

        # Snapshot before review (round 0 = initial state)
        if round_num == 1 or not dry_run:
            snapshot_paper(paper_dir, round_num - 1)

        # Run full review
        engine = ReviewEngine(
            paper_dir=paper_dir,
            reviewer_ids=reviewer_ids,
            shadow_mode=shadow,
        )
        meta = engine.run_full_review()

        # Build round result
        section_scores = _extract_section_scores(meta.to_dict())
        # Fix: section_scores might have lists instead of floats from _extract_section_scores
        # Actually that function returns averages, but we call it with the meta dict
        # which has paper_dir. Let's just compute from reviews_dir directly.
        sec_scores_clean: dict[str, float] = {}
        for review_file in reviews_dir.glob("*_review.json"):
            if review_file.name == "meta_review.json":
                continue
            try:
                review = json.loads(review_file.read_text())
            except json.JSONDecodeError:
                continue
            for sr in review.get("section_reviews", []):
                key = sr.get("section_key", "")
                score = sr.get("overall_score", 0.0)
                if key and score > 0:
                    sec_scores_clean.setdefault(key, []).append(score)
        sec_scores_avg = {
            k: round(sum(v) / len(v), 2)
            for k, v in sec_scores_clean.items()
            if isinstance(v, list) and v
        }

        round_result = RoundResult(
            round_num=round_num,
            overall_score=meta.overall_score,
            decision=meta.decision,
            reviewer_scores=meta.reviewer_scores,
            dimension_averages=_extract_dimension_averages(reviews_dir),
            section_scores=sec_scores_avg,
        )

        # Extract revision notes
        meta_path = reviews_dir / "meta_review.json"
        revision_notes = extract_revision_notes(meta_path, reviews_dir)
        round_result.revision_notes = {
            k: v[:5] for k, v in revision_notes.items()  # Cap at 5 per section
        }

        trajectory.rounds.append(round_result)

        # Compute delta
        previous = trajectory.rounds[-2] if len(trajectory.rounds) >= 2 else None
        delta = compute_delta(round_result, previous)

        logger.info(
            f"Round {round_num}: score={meta.overall_score:.2f}, "
            f"decision={meta.decision}, delta={delta['delta']:.3f}"
        )

        # Check convergence
        should_stop, reason = check_convergence(trajectory, delta)
        if should_stop:
            trajectory.converged = "quality_met" in reason or "stability" in reason
            trajectory.stop_reason = reason
            trajectory.final_score = meta.overall_score
            logger.info(f"Convergence loop stopped: {reason}")
            break

        # Apply revisions (unless dry run or last round)
        if not dry_run and round_num < max_rounds:
            # Section-level score guard: check if any section regressed
            if previous and previous.section_scores:
                for sec_key, new_score in sec_scores_avg.items():
                    old_score = previous.section_scores.get(sec_key, 0.0)
                    if old_score > 0 and new_score < old_score - 1.0:
                        logger.warning(
                            f"Section {sec_key} regressed "
                            f"({old_score:.2f} → {new_score:.2f}), "
                            f"restoring from snapshot"
                        )
                        # Restore just this section from previous snapshot
                        prev_snapshot = (
                            paper_dir / "reviews" / "snapshots"
                            / f"round_{round_num - 1:02d}" / f"{sec_key}.tex"
                        )
                        if prev_snapshot.exists():
                            target = paper_dir / "sections" / f"{sec_key}.tex"
                            shutil.copy2(prev_snapshot, target)
                            # Remove from revision notes so we don't re-refine
                            revision_notes.pop(sec_key, None)

            revision_results = apply_revisions(paper_dir, revision_notes)
            logger.info(f"Revisions applied: {revision_results}")

    else:
        # Loop completed without break (max_rounds reached)
        if not trajectory.stop_reason:
            trajectory.stop_reason = f"max_rounds: reached {max_rounds}"
            trajectory.final_score = trajectory.rounds[-1].overall_score if trajectory.rounds else 0.0

    # Get shadow stats
    shadow_stats = engine.shadow_report() if 'engine' in dir() else {}
    trajectory.total_shadow_entries = shadow_stats.get("total", 0)

    # Save trajectory
    trajectory.save(reviews_dir)

    return trajectory


# ---------------------------------------------------------------------------
# Convergence visualization
# ---------------------------------------------------------------------------

def visualize_convergence(
    paper_dir: str | Path,
    output_dir: Optional[Path] = None,
) -> list[Path]:
    """Generate convergence trajectory visualization.

    Produces:
    - convergence_trajectory.png: Score over rounds with threshold line
    - dimension_heatmap.png: Per-dimension scores across rounds
    - section_progress.png: Per-section score improvement
    """
    paper_dir = Path(paper_dir)
    reviews_dir = paper_dir / "reviews"
    output_dir = output_dir or reviews_dir / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    trajectory_path = reviews_dir / "convergence.json"
    if not trajectory_path.exists():
        logger.warning("No convergence.json found. Run converge first.")
        return []

    trajectory = json.loads(trajectory_path.read_text())
    rounds = trajectory.get("rounds", [])
    if not rounds:
        logger.warning("No rounds in convergence trajectory.")
        return []

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logger.warning("matplotlib not available for visualization")
        return []

    generated = []

    # 1. Score trajectory chart
    fig, ax = plt.subplots(figsize=(10, 6))
    round_nums = [r["round_num"] for r in rounds]
    scores = [r["overall_score"] for r in rounds]

    ax.plot(round_nums, scores, "o-", color="#2196F3", linewidth=2.5, markersize=8, label="Overall Score")
    ax.axhline(y=trajectory["threshold"], color="#4CAF50", linestyle="--", linewidth=1.5, label=f"Accept Threshold ({trajectory['threshold']})")
    ax.fill_between(round_nums, scores, trajectory["threshold"],
                    where=[s >= trajectory["threshold"] for s in scores],
                    alpha=0.15, color="#4CAF50")
    ax.fill_between(round_nums, scores, trajectory["threshold"],
                    where=[s < trajectory["threshold"] for s in scores],
                    alpha=0.15, color="#E91E63")

    ax.set_xlabel("Round", fontsize=13)
    ax.set_ylabel("Overall Score (1-10)", fontsize=13)
    ax.set_title("Convergence Trajectory", fontsize=15, fontweight="bold")
    ax.set_ylim(0, 10)
    ax.set_xticks(round_nums)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    # Annotate stop reason
    if trajectory.get("stop_reason"):
        ax.annotate(
            trajectory["stop_reason"].split(":")[0],
            xy=(round_nums[-1], scores[-1]),
            xytext=(round_nums[-1] - 0.5, scores[-1] + 0.8),
            arrowprops=dict(arrowstyle="->", color="#333"),
            fontsize=10, color="#333",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="wheat", alpha=0.8),
        )

    path = output_dir / "convergence_trajectory.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    generated.append(path)

    # 2. Dimension heatmap across rounds
    if any(r.get("dimension_averages") for r in rounds):
        dimensions = ["soundness", "technical_novelty", "empirical_novelty",
                       "significance", "clarity", "presentation"]
        data = []
        for r in rounds:
            dims = r.get("dimension_averages", {})
            data.append([dims.get(d, 0.0) for d in dimensions])

        if data and any(any(v > 0 for v in row) for row in data):
            fig, ax = plt.subplots(figsize=(10, 4))
            im = ax.imshow(np.array(data).T, aspect="auto", cmap="RdYlGn",
                           vmin=1.0, vmax=4.0)
            ax.set_yticks(range(len(dimensions)))
            ax.set_yticklabels([d.replace("_", " ").title() for d in dimensions], fontsize=11)
            ax.set_xticks(range(len(rounds)))
            ax.set_xticklabels([f"R{r['round_num']}" for r in rounds], fontsize=11)
            ax.set_title("Dimension Scores Across Rounds (1-4 scale)", fontsize=14, fontweight="bold")
            plt.colorbar(im, ax=ax, label="Score")

            # Annotate cells
            for i, row in enumerate(data):
                for j, val in enumerate(row):
                    if val > 0:
                        ax.text(i, j, f"{val:.1f}", ha="center", va="center",
                                fontsize=9, color="black" if val > 2.0 else "white")

            path = output_dir / "dimension_heatmap.png"
            fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            generated.append(path)

    # 3. Section progress bar chart (first vs last round)
    if len(rounds) >= 2:
        first = rounds[0].get("section_scores", {})
        last = rounds[-1].get("section_scores", {})
        sections = sorted(set(first.keys()) | set(last.keys()))

        if sections:
            fig, ax = plt.subplots(figsize=(10, 5))
            x = np.arange(len(sections))
            width = 0.35

            first_scores = [first.get(s, 0.0) for s in sections]
            last_scores = [last.get(s, 0.0) for s in sections]

            ax.bar(x - width / 2, first_scores, width, label=f"Round {rounds[0]['round_num']}",
                   color="#90CAF9", edgecolor="white")
            ax.bar(x + width / 2, last_scores, width, label=f"Round {rounds[-1]['round_num']}",
                   color="#2196F3", edgecolor="white")

            ax.set_xlabel("Section", fontsize=12)
            ax.set_ylabel("Score (1-10)", fontsize=12)
            ax.set_title("Section Score Improvement", fontsize=14, fontweight="bold")
            ax.set_xticks(x)
            ax.set_xticklabels(sections, fontsize=11)
            ax.set_ylim(0, 10)
            ax.legend(fontsize=11)
            ax.grid(True, alpha=0.3, axis="y")

            path = output_dir / "section_progress.png"
            fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            generated.append(path)

    logger.info(f"Generated {len(generated)} convergence visualizations")
    return generated
