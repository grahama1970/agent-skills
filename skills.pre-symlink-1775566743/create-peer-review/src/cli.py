"""CLI for /create-peer-review.

Commands:
    review           Full multi-persona peer review
    compare-exemplars Compare against arxiv papers
    score-section    Score a single section
    train            Train reviewer GPTs from shadow data
    shadow-report    Shadow agreement statistics
    visualize        Generate visual review dashboard
    review-arxiv     Review arxiv paper for curriculum training
    converge         Iterative review-refine convergence loop
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from loguru import logger

from .cli_benchmark import app as benchmark_app

app = typer.Typer(
    help="/create-peer-review — Self-improving peer review via Shadow-LEGO cascade",
    no_args_is_help=True,
)
app.registered_commands += benchmark_app.registered_commands
console = Console()


@app.command()
def review(
    paper_dir: Path = typer.Argument(..., help="Path to paper directory"),
    reviewers: Optional[str] = typer.Option(
        None, "--reviewers", help="Comma-separated reviewer IDs (default: all)"
    ),
    shadow: bool = typer.Option(True, "--shadow/--no-shadow", help="Enable shadow mode"),
    parallel: bool = typer.Option(False, "--parallel", help="Dispatch reviewers concurrently via scillm"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run full multi-persona peer review."""
    from .review_engine import ReviewEngine

    reviewer_ids = reviewers.split(",") if reviewers else None

    console.print(f"\n[bold]Peer Review[/bold]: {paper_dir}")
    console.print(f"Shadow mode: {'ON' if shadow else 'OFF'}")
    if parallel:
        console.print("[bold cyan]Parallel mode[/bold cyan]: via scillm")
    if reviewer_ids:
        console.print(f"Reviewers: {', '.join(reviewer_ids)}")

    engine = ReviewEngine(
        paper_dir=paper_dir,
        reviewer_ids=reviewer_ids,
        shadow_mode=shadow,
    )

    meta = engine.run_full_review(parallel=parallel)

    # Display results
    _display_meta_review(meta)


@app.command("compare-exemplars")
def compare_exemplars(
    paper_dir: Path = typer.Argument(..., help="Path to paper directory"),
    papers: Optional[str] = typer.Option(
        None, "--papers", help="Comma-separated arxiv IDs"
    ),
) -> None:
    """Compare paper against arxiv exemplars."""
    from .exemplar_comparison import ExemplarComparator

    comparator = ExemplarComparator()

    # Extract candidate metrics
    console.print(f"\n[bold]Extracting metrics[/bold]: {paper_dir}")
    candidate = comparator.extract_metrics(paper_dir)

    # Display candidate metrics
    _display_paper_metrics(candidate)

    # Compare against exemplars or norms
    exemplar_ids = papers.split(",") if papers else None
    comparison = comparator.compare(paper_dir, exemplar_ids=exemplar_ids)

    # Display gaps
    _display_gaps(comparison.gaps)

    console.print(f"\n[bold]Overall similarity[/bold]: {comparison.overall_similarity:.0%}")
    console.print(f"[bold]Recommendation[/bold]: {comparison.recommendation}")

    # Save
    output_dir = Path(paper_dir) / "reviews"
    comparison.save(output_dir)


@app.command("score-section")
def score_section(
    tex_file: Path = typer.Argument(..., help="Path to section .tex file"),
    reviewer: str = typer.Option("reviewer_alpha", "--reviewer", help="Reviewer persona ID"),
) -> None:
    """Score a single section with one reviewer."""
    from .review_engine import ReviewEngine

    paper_dir = tex_file.parent.parent  # sections/*.tex → paper_dir
    section_key = tex_file.stem

    engine = ReviewEngine(
        paper_dir=paper_dir,
        reviewer_ids=[reviewer],
    )

    console.print(f"\n[bold]Scoring[/bold]: {section_key} (reviewer: {reviewer})")
    sr = engine.review_section(section_key, reviewer)

    console.print(f"\n[bold]Dimension Scores[/bold] (1-4 scale, tier {sr.tier_used}):")
    console.print(f"  Soundness:         {sr.scores.soundness:.1f}/4")
    console.print(f"  Technical Novelty: {sr.scores.technical_novelty:.1f}/4")
    console.print(f"  Empirical Novelty: {sr.scores.empirical_novelty:.1f}/4")
    console.print(f"  Significance:      {sr.scores.significance:.1f}/4")
    console.print(f"  Clarity:           {sr.scores.clarity:.1f}/4")
    console.print(f"  Presentation:      {sr.scores.presentation:.1f}/4")
    console.print(f"  Advisory Signal:   {sr.scores.weighted_signal():.2f}/10")
    if sr.overall_score > 0:
        console.print(f"  Overall (holistic): {sr.overall_score:.2f}/10")

    if sr.strengths:
        console.print(f"\n[green]Strengths[/green]:")
        for s in sr.strengths:
            console.print(f"  + {s}")
    if sr.weaknesses:
        console.print(f"\n[red]Weaknesses[/red]:")
        for w in sr.weaknesses:
            console.print(f"  - {w}")
    if sr.code_issues:
        console.print(f"\n[yellow]Code Issues[/yellow]:")
        for c in sr.code_issues:
            console.print(f"  ! {c}")


@app.command()
def train(
    reviewer: Optional[str] = typer.Option(None, "--reviewer", help="Reviewer ID to train"),
    data: Optional[Path] = typer.Option(None, "--data", help="Shadow data path"),
) -> None:
    """Train reviewer GPTs from shadow observation data.

    Harvests teacher reviews from the shadow journal and fine-tunes
    Tier 1.5 reviewer GPTs via /create-gpt. This is the self-improvement
    loop: as the teacher generates reviews, the local GPT learns to
    replicate them.
    """
    shadow_file = data or Path.home() / ".pi" / "peer_review" / "shadow.jsonl"

    console.print(f"\n[bold]Training reviewer GPTs[/bold]")

    # Harvest from two sources:
    # 1. shadow.jsonl (shadow observations with teacher comparisons)
    # 2. Review JSON files (direct teacher outputs from completed reviews)
    training_data = []

    # Source 1: Shadow journal
    shadow_count = 0
    if shadow_file.exists():
        entries = shadow_file.read_text().strip().split("\n")
        shadow_count = len(entries)
        console.print(f"Shadow entries: {shadow_count}")
        for line in entries:
            try:
                entry = json.loads(line)
                if entry.get("teacher_result"):
                    training_data.append({
                        "input": entry.get("input_data", {}),
                        "output": entry["teacher_result"],
                        "task": "peer_review_section",
                        "source": "shadow",
                    })
            except json.JSONDecodeError:
                continue
    else:
        console.print("[dim]No shadow.jsonl found — checking review files...[/dim]")

    # Source 2: Review JSON files (teacher baseline data)
    review_dirs = list(Path.home().glob(".pi/peer_review/reviews/*/reviews"))
    # Also check paper artifacts
    skill_dir = Path(__file__).parent.parent
    artifacts_dir = skill_dir.parent.parent.parent / "artifacts"
    for paper_dir in artifacts_dir.glob("*/reviews"):
        if paper_dir.is_dir():
            review_dirs.append(paper_dir)

    review_file_count = 0
    for reviews_dir in review_dirs:
        for review_file in reviews_dir.glob("reviewer_*_review.json"):
            try:
                review_data = json.loads(review_file.read_text())
                for sr in review_data.get("section_reviews", []):
                    training_data.append({
                        "input": {
                            "section_key": sr.get("section_key", ""),
                            "reviewer_id": review_data.get("reviewer_id", ""),
                            "paper_dir": review_data.get("paper_dir", ""),
                        },
                        "output": sr,
                        "task": "peer_review_section",
                        "source": "review_json",
                    })
                    review_file_count += 1
            except (json.JSONDecodeError, OSError):
                continue

    if review_file_count:
        console.print(f"Review file entries: {review_file_count}")

    console.print(f"Total training examples: {len(training_data)}")

    if len(training_data) < 20:
        console.print("[yellow]Need ≥20 training examples. Run more reviews first.[/yellow]")
        console.print("[dim]Tip: bash run.sh review-arxiv <arxiv_id> --shadow[/dim]")
        raise typer.Exit(1)

    if training_data:
        # Write training data for /create-gpt
        skills_dir = Path(__file__).parent.parent.parent
        train_dir = skills_dir / "create-gpt" / "data" / "tasks" / "peer-review-critic"
        train_dir.mkdir(parents=True, exist_ok=True)
        train_file = train_dir / "train.jsonl"

        with open(train_file, "w") as f:
            for example in training_data:
                f.write(json.dumps(example) + "\n")

        console.print(f"[green]Training data written to {train_file}[/green]")
        console.print("Run: bash .pi/skills/create-gpt/run.sh train --task peer-review-critic")
    else:
        console.print("[yellow]No teacher reviews found in shadow data.[/yellow]")


@app.command("shadow-report")
def shadow_report() -> None:
    """Display shadow agreement statistics for reviewer GPTs."""
    shadow_file = Path.home() / ".pi" / "peer_review" / "shadow.jsonl"
    if not shadow_file.exists():
        console.print("[yellow]No shadow data found.[/yellow]")
        raise typer.Exit(0)

    entries = []
    for line in shadow_file.read_text().strip().split("\n"):
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not entries:
        console.print("[yellow]Shadow journal is empty.[/yellow]")
        raise typer.Exit(0)

    # Compute agreement stats
    total = len(entries)
    agreed = sum(1 for e in entries if e.get("agreed", False))
    rate = agreed / total if total > 0 else 0.0

    status = "ready" if rate >= 0.90 else "learning" if rate >= 0.70 else "early"
    status_color = {"ready": "green", "learning": "yellow", "early": "red"}[status]

    table = Table(title="Shadow Agreement Report")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Total shadow entries", str(total))
    table.add_row("Agreed", str(agreed))
    table.add_row("Disagreed", str(total - agreed))
    table.add_row("Agreement rate", f"{rate:.1%}")
    table.add_row("Status", f"[{status_color}]{status}[/{status_color}]")
    table.add_row("Promotion threshold", "90%")
    table.add_row("Min samples", "50")

    console.print(table)

    if status == "ready" and total >= 50:
        console.print(
            "\n[green bold]Ready for promotion![/green bold] "
            "Reviewer GPT can operate autonomously."
        )
    elif total < 50:
        console.print(f"\n[yellow]Need {50 - total} more shadow entries before promotion.[/yellow]")


@app.command()
def visualize(
    paper_dir: Path = typer.Argument(..., help="Path to paper directory"),
    output: Optional[Path] = typer.Option(None, "--output", help="Output image path"),
) -> None:
    """Generate visual review dashboard via /create-figure + /analytics.

    Produces:
    - Radar chart of rubric scores per reviewer
    - Gap analysis bar chart vs exemplars
    - Score history across drafts (if multiple reviews exist)
    """
    reviews_dir = Path(paper_dir) / "reviews"
    if not reviews_dir.exists():
        console.print("[yellow]No reviews found. Run 'review' first.[/yellow]")
        raise typer.Exit(1)

    output_dir = reviews_dir / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load reviews
    review_files = list(reviews_dir.glob("*_review.json"))
    if not review_files:
        console.print("[yellow]No review JSON files found.[/yellow]")
        raise typer.Exit(1)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        console.print("[yellow]matplotlib not available. Install with: pip install matplotlib numpy[/yellow]")
        raise typer.Exit(1)

    reviews = []
    for rf in review_files:
        if rf.name == "meta_review.json":
            continue
        reviews.append(json.loads(rf.read_text()))

    if not reviews:
        console.print("[yellow]No reviewer reviews found.[/yellow]")
        raise typer.Exit(1)

    # Radar chart of rubric scores (6-dimension, 1-4 scale)
    dimensions = ["soundness", "technical_novelty", "empirical_novelty", "significance", "clarity", "presentation"]
    angles = np.linspace(0, 2 * np.pi, len(dimensions), endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    colors = ["#2196F3", "#4CAF50", "#FF9800", "#E91E63"]

    for i, rev in enumerate(reviews):
        scores = []
        for dim in dimensions:
            # Average across sections
            section_scores = []
            for sr in rev.get("section_reviews", []):
                s = sr.get("scores", {}).get(dim, 2.0)
                section_scores.append(s)
            scores.append(sum(section_scores) / len(section_scores) if section_scores else 2.0)
        scores += scores[:1]

        color = colors[i % len(colors)]
        ax.fill(angles, scores, alpha=0.15, color=color)
        ax.plot(angles, scores, "o-", color=color, linewidth=2,
                label=rev.get("reviewer_name", f"Reviewer {i+1}"))

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([d.capitalize() for d in dimensions], fontsize=12)
    ax.set_ylim(0, 4)
    ax.set_yticks([1, 2, 3, 4])
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)
    ax.set_title("Peer Review Rubric Scores", fontsize=14, fontweight="bold", pad=20)

    radar_path = output_dir / "rubric_radar.png"
    fig.savefig(radar_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    console.print(f"[green]Saved radar chart: {radar_path}[/green]")

    # Score summary bar chart
    fig, ax = plt.subplots(figsize=(10, 5))
    names = [r.get("reviewer_name", f"R{i}") for i, r in enumerate(reviews)]
    scores = [r.get("overall_score", 0) for r in reviews]
    bar_colors = [
        "#4CAF50" if s >= 6.5 else "#FF9800" if s >= 5.0 else "#E91E63"
        for s in scores
    ]
    bars = ax.barh(names, scores, color=bar_colors, edgecolor="white", height=0.5)

    # Add threshold lines
    ax.axvline(x=6.5, color="#4CAF50", linestyle="--", alpha=0.5, label="Accept (6.5)")
    ax.axvline(x=5.0, color="#FF9800", linestyle="--", alpha=0.5, label="Borderline (5.0)")

    ax.set_xlim(0, 10)
    ax.set_xlabel("Overall Score", fontsize=12)
    ax.set_title("Reviewer Scores", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)

    for bar, score in zip(bars, scores):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                f"{score:.1f}", va="center", fontsize=11, fontweight="bold")

    summary_path = output_dir / "score_summary.png"
    fig.savefig(summary_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    console.print(f"[green]Saved score summary: {summary_path}[/green]")

    # If exemplar comparison exists, generate gap chart
    exemplar_path = reviews_dir / "exemplar_comparison.json"
    if exemplar_path.exists():
        comparison = json.loads(exemplar_path.read_text())
        gaps = comparison.get("gaps", [])

        if gaps:
            fig, ax = plt.subplots(figsize=(12, 6))
            gap_names = [g["metric"] for g in gaps]
            gap_values = [g["candidate_value"] for g in gaps]
            exemplar_values = [g["exemplar_mean"] for g in gaps]
            severities = [g["severity"] for g in gaps]

            x = np.arange(len(gap_names))
            width = 0.35
            ax.bar(x - width/2, gap_values, width, label="Candidate", color="#2196F3")
            ax.bar(x + width/2, exemplar_values, width, label="Exemplar Mean", color="#9E9E9E")

            # Color-code background by severity
            for i, sev in enumerate(severities):
                if sev == "critical":
                    ax.axvspan(i - 0.5, i + 0.5, alpha=0.1, color="red")
                elif sev == "warning":
                    ax.axvspan(i - 0.5, i + 0.5, alpha=0.1, color="orange")

            ax.set_xticks(x)
            ax.set_xticklabels(gap_names, rotation=45, ha="right", fontsize=10)
            ax.legend(fontsize=11)
            ax.set_title("Exemplar Gap Analysis", fontsize=14, fontweight="bold")

            gap_path = output_dir / "exemplar_gap.png"
            fig.savefig(gap_path, dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            console.print(f"[green]Saved gap chart: {gap_path}[/green]")

    final_output = output or radar_path
    console.print(f"\n[bold]Dashboard generated at: {output_dir}[/bold]")


@app.command("review-arxiv")
def review_arxiv_cmd(
    arxiv_id: str = typer.Argument(..., help="Arxiv paper ID (e.g., 2305.05176)"),
    shadow: bool = typer.Option(True, "--shadow/--no-shadow", help="Enable shadow mode"),
    reviewers: Optional[str] = typer.Option(
        None, "--reviewers", help="Comma-separated reviewer IDs (default: all)"
    ),
    batch: Optional[str] = typer.Option(
        None, "--batch", help="Comma-separated arxiv IDs for batch review"
    ),
) -> None:
    """Review arxiv paper(s) for curriculum training data.

    Downloads paper via ar5iv HTML (with PDF fallback), segments into
    sections, and runs full peer review through the Shadow-LEGO cascade.
    Shadow mode generates training data for Tier 1.5 reviewer GPTs.
    """
    from .curriculum import review_arxiv, review_arxiv_batch

    reviewer_ids = reviewers.split(",") if reviewers else None

    if batch:
        ids = [aid.strip() for aid in batch.split(",") if aid.strip()]
        console.print(f"\n[bold]Batch curriculum review[/bold]: {len(ids)} papers")
        console.print(f"Shadow mode: {'ON' if shadow else 'OFF'}")
        results = review_arxiv_batch(ids, shadow=shadow, reviewer_ids=reviewer_ids)
        for r in results:
            if "error" in r:
                console.print(f"  [red]FAIL[/red] {r.get('arxiv_id', '?')}: {r['error']}")
            else:
                score = r.get("overall_score", 0)
                scolor = "green" if score >= 6.0 else "yellow" if score >= 5.0 else "red"
                console.print(
                    f"  [{scolor}]{r.get('decision', '?').upper()}[/{scolor}] "
                    f"{r.get('title', r.get('arxiv_id', '?'))}: {score:.2f}/10 "
                    f"({r.get('section_count', 0)} sections)"
                )
        console.print(f"\n[bold]Reviewed {len(results)} papers[/bold]")
    else:
        console.print(f"\n[bold]Curriculum review[/bold]: arxiv:{arxiv_id}")
        console.print(f"Shadow mode: {'ON' if shadow else 'OFF'}")
        result = review_arxiv(arxiv_id, shadow=shadow, reviewer_ids=reviewer_ids)
        if "error" in result:
            console.print(f"[red]Error[/red]: {result['error']}")
            raise typer.Exit(1)

        score = result.get("overall_score", 0)
        scolor = "green" if score >= 6.0 else "yellow" if score >= 5.0 else "red"
        console.print(f"\n[bold]Title[/bold]: {result.get('title', 'Unknown')}")
        console.print(f"[bold]Score[/bold]: [{scolor}]{score:.2f}/10[/{scolor}]")
        console.print(f"[bold]Decision[/bold]: [{scolor}]{result.get('decision', '?').upper()}[/{scolor}]")
        console.print(f"[bold]Sections[/bold]: {result.get('section_count', 0)}")
        if result.get("fallback_used"):
            console.print("[yellow]Note: Used PDF fallback (ar5iv unavailable)[/yellow]")
        if result.get("shadow_stats"):
            stats = result["shadow_stats"]
            console.print(
                f"[bold]Shadow[/bold]: {stats.get('total', 0)} entries, "
                f"{stats.get('rate', 0):.0%} agreement"
            )


@app.command()
def converge(
    paper_dir: Path = typer.Argument(..., help="Path to paper directory"),
    threshold: float = typer.Option(6.0, "--threshold", help="Target overall score"),
    max_rounds: int = typer.Option(5, "--max-rounds", help="Maximum convergence rounds"),
    epsilon: float = typer.Option(0.5, "--epsilon", help="Stability threshold"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Review only, don't modify files"),
    shadow: bool = typer.Option(True, "--shadow/--no-shadow", help="Enable shadow mode"),
    reviewers: Optional[str] = typer.Option(
        None, "--reviewers", help="Comma-separated reviewer IDs (default: all)"
    ),
) -> None:
    """Run review-refine convergence loop on a paper.

    The meta-recursive heart of Shadow-LEGO: the paper is reviewed by
    its own cascade, refined based on those reviews, and re-reviewed
    until quality converges. Each round generates shadow data that
    trains the cascade described in the paper itself.
    """
    from .converge import converge as run_converge

    reviewer_ids = reviewers.split(",") if reviewers else None

    console.print(f"\n[bold]Convergence Loop[/bold]: {paper_dir}")
    console.print(f"  Threshold: {threshold}/10 | Max rounds: {max_rounds} | Epsilon: {epsilon}")
    console.print(f"  Shadow: {'ON' if shadow else 'OFF'} | Dry run: {'YES' if dry_run else 'NO'}")

    trajectory = run_converge(
        paper_dir=paper_dir,
        threshold=threshold,
        max_rounds=max_rounds,
        epsilon=epsilon,
        dry_run=dry_run,
        shadow=shadow,
        reviewer_ids=reviewer_ids,
    )

    # Display results
    console.print(f"\n[bold]{'='*50}[/bold]")
    conv_color = "green" if trajectory.converged else "yellow"
    console.print(f"[{conv_color}]Converged: {trajectory.converged}[/{conv_color}]")
    console.print(f"Stop reason: {trajectory.stop_reason}")
    console.print(f"Final score: {trajectory.final_score:.2f}/10")
    console.print(f"Rounds: {len(trajectory.rounds)}")

    # Per-round summary
    table = Table(title="Convergence Trajectory")
    table.add_column("Round", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Decision")
    table.add_column("Delta", justify="right")

    for i, r in enumerate(trajectory.rounds):
        prev = trajectory.rounds[i - 1] if i > 0 else None
        delta = r.overall_score - prev.overall_score if prev else 0.0
        scolor = "green" if r.overall_score >= threshold else "yellow" if r.overall_score >= 5.0 else "red"
        dcolor = "green" if delta > 0 else "red" if delta < 0 else "white"
        table.add_row(
            str(r.round_num),
            f"[{scolor}]{r.overall_score:.2f}[/{scolor}]",
            r.decision,
            f"[{dcolor}]{delta:+.2f}[/{dcolor}]",
        )
    console.print(table)

    if trajectory.total_shadow_entries:
        console.print(f"\nShadow entries: {trajectory.total_shadow_entries}")


def _display_meta_review(meta) -> None:
    """Display meta-review results in a Rich table."""
    # Decision with color
    decision_colors = {
        "strong_accept": "bold green",
        "accept": "green",
        "borderline": "yellow",
        "reject": "red",
    }
    color = decision_colors.get(meta.decision, "white")

    console.print(Panel(
        f"[{color}]{meta.decision.upper()}[/{color}]  "
        f"(score: {meta.overall_score:.2f}/10)",
        title="Meta-Review Decision",
    ))

    # Per-reviewer scores
    table = Table(title="Reviewer Scores")
    table.add_column("Reviewer", style="bold")
    table.add_column("Score", justify="right")
    for rid, score in meta.reviewer_scores.items():
        scolor = "green" if score >= 6.5 else "yellow" if score >= 5.0 else "red"
        table.add_row(rid, f"[{scolor}]{score:.2f}[/{scolor}]")
    console.print(table)

    if meta.consensus_strengths:
        console.print("\n[bold green]Consensus Strengths:[/bold green]")
        for s in meta.consensus_strengths[:5]:
            console.print(f"  + {s}")

    if meta.consensus_weaknesses:
        console.print("\n[bold red]Consensus Weaknesses:[/bold red]")
        for w in meta.consensus_weaknesses[:5]:
            console.print(f"  - {w}")

    if meta.disagreements:
        console.print("\n[bold yellow]Reviewer Disagreements:[/bold yellow]")
        for d in meta.disagreements:
            console.print(f"  ~ {d}")

    if meta.revision_priority:
        console.print("\n[bold]Revision Priority:[/bold]")
        for i, rp in enumerate(meta.revision_priority[:5], 1):
            console.print(f"  {i}. {rp}")


def _display_paper_metrics(metrics) -> None:
    """Display paper structural metrics."""
    table = Table(title="Paper Metrics")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Total words", str(metrics.total_words))
    table.add_row("Citations", str(metrics.citation_count))
    table.add_row("Citation density", f"{metrics.citation_density:.1f}/1K words")
    table.add_row("Figures", str(metrics.figure_count))
    table.add_row("Tables", str(metrics.table_count))
    table.add_row("Code blocks", str(metrics.code_block_count))
    table.add_row("References", str(metrics.reference_count))

    for key, wc in sorted(metrics.section_words.items()):
        ratio = metrics.section_ratios.get(key, 0)
        table.add_row(f"  {key}", f"{wc} words ({ratio:.0%})")

    console.print(table)


def _display_gaps(gaps) -> None:
    """Display exemplar gap analysis."""
    table = Table(title="Exemplar Gap Analysis")
    table.add_column("Metric", style="bold")
    table.add_column("Candidate", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Status")
    table.add_column("Suggestion")

    for g in gaps:
        scolor = {"ok": "green", "warning": "yellow", "critical": "red"}.get(g.severity, "white")
        table.add_row(
            g.metric,
            f"{g.candidate_value:.1f}",
            f"{g.exemplar_mean:.1f}",
            f"[{scolor}]{g.severity}[/{scolor}]",
            g.suggestion or "",
        )
    console.print(table)


def main():
    app()


if __name__ == "__main__":
    main()
