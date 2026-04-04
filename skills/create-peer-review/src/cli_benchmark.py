"""Benchmark CLI commands for /create-peer-review.

Extracted from cli.py to stay under 800-line limit.
Contains: benchmark, ingest-benchmark commands and their helpers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from loguru import logger

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def benchmark(
    paper_dir: Path = typer.Argument(..., help="Path to paper directory (or .tex file)"),
    corpus: Optional[Path] = typer.Option(
        None, "--corpus", help="Custom benchmark corpus JSON"
    ),
    output: Optional[Path] = typer.Option(None, "--output", help="Save report JSON"),
) -> None:
    """Score a paper against the arxiv benchmark corpus.

    Computes percentile ranks for structural metrics (equations/page,
    figures/page, refs/page, footnotes, etc.) against the embedded
    arxiv corpus. This is the eval that grounds Tier 2 reviewer scoring.
    """
    from .benchmarks import ArxivBenchmarks

    benchmarks = ArxivBenchmarks.load(corpus)

    if not benchmarks.corpus:
        console.print("[red]No benchmark corpus found.[/red]")
        console.print("Add papers: bash run.sh ingest-benchmark <arxiv_id>")
        raise typer.Exit(1)

    console.print(f"\n[bold]Arxiv Benchmark Eval[/bold] (corpus: {len(benchmarks.corpus)} papers)")

    # Extract metrics from the paper
    paper_dir = Path(paper_dir)
    if paper_dir.suffix == ".tex":
        tex_content = paper_dir.read_text()
        paper_id = paper_dir.stem
        words = len(re.sub(r"\\[a-zA-Z]+\*?\{[^}]*\}", " ", tex_content).split())
        est_pages = max(1, words // 350)
        equations = len(re.findall(r"\\begin\{(?:equation|align)\*?\}", tex_content))
        figures = len(re.findall(r"\\begin\{figure", tex_content))
        tables = len(re.findall(r"\\begin\{table", tex_content))
        refs = 0
        bib_path = paper_dir.parent / "references.bib"
        if bib_path.exists():
            refs = len(re.findall(r"@\w+\{", bib_path.read_text()))
        refs += len(re.findall(r"\\bibitem", tex_content))
        refs = max(refs, len(re.findall(r"\\cite[tp]?\*?\{", tex_content)))
        footnotes = len(re.findall(r"\\footnote\{", tex_content))
        paper_metrics = {
            "words": words, "est_pages": est_pages,
            "equations": equations, "figures": figures,
            "tables": tables, "refs": refs, "footnotes": footnotes,
            "eq_per_pg": equations / est_pages,
            "fig_per_pg": figures / est_pages,
            "ref_per_pg": refs / est_pages,
        }
    else:
        from .exemplar_comparison import ExemplarComparator
        comparator = ExemplarComparator()
        metrics = comparator.extract_metrics(paper_dir)
        est_pages = max(1, metrics.total_words // 350)
        paper_metrics = {
            "words": metrics.total_words, "est_pages": est_pages,
            "equations": 0,
            "figures": metrics.figure_count, "tables": metrics.table_count,
            "refs": metrics.reference_count, "footnotes": 0,
            "eq_per_pg": 0, "fig_per_pg": metrics.figure_count / est_pages,
            "ref_per_pg": metrics.reference_count / est_pages,
        }
        paper_id = paper_dir.name

    # Score against corpus
    report = benchmarks.score_paper(paper_metrics, paper_id=paper_id)
    comparison_rows = benchmarks.comparison_table(paper_metrics)

    # Display comparison table
    table = Table(title=f"Benchmark Comparison: {paper_id}")
    table.add_column("Metric", style="bold")
    table.add_column("Paper", justify="right")
    table.add_column("p25", justify="right")
    table.add_column("p50", justify="right")
    table.add_column("p75", justify="right")
    table.add_column("Rank", justify="right")
    table.add_column("Status")

    for row in comparison_rows:
        rank = row["rank"]
        status_color = {"strong": "green", "ok": "yellow", "weak": "red"}[row["status"]]
        table.add_row(
            row["metric"],
            f"{row['paper_value']:.2f}",
            f"{row['p25']:.2f}",
            f"{row['p50']:.2f}",
            f"{row['p75']:.2f}",
            f"{rank:.0%}",
            f"[{status_color}]{row['status']}[/{status_color}]",
        )

    console.print(table)

    # Flags
    if report.flags:
        console.print("\n[bold]Flags:[/bold]")
        for f in report.flags:
            console.print(f"  {'[green]+' if 'strong' in f else '[red]-'} {f}[/]")

    console.print(f"\n[bold]Structural Score[/bold]: {report.overall_structural_score:.1f}/10")

    # Get qualitative peer reviews from corpus senior authors
    PERSONAS_DIR = Path(__file__).parent.parent / "personas" / "corpus_reviewers"
    enriched_names = set()
    if PERSONAS_DIR.exists():
        for pf in PERSONAS_DIR.glob("*.json"):
            try:
                enriched_names.add(json.loads(pf.read_text()).get("name", ""))
            except Exception:
                pass

    all_candidates = benchmarks.select_reviewer_authors(n=12)
    enriched_reviewers = [a for a in all_candidates if a.get("senior_author") in enriched_names]
    other_reviewers = [a for a in all_candidates if a.get("senior_author") not in enriched_names]
    reviewer_authors = (enriched_reviewers + other_reviewers)[:3]
    if enriched_reviewers:
        console.print(f"[dim]Using {len(enriched_reviewers)} enriched reviewer persona(s)[/dim]")
    author_reviews = []
    if reviewer_authors:
        console.print(f"\n[bold]Generating peer reviews from {len(reviewer_authors)} corpus authors...[/bold]")
        tex_excerpt = ""
        if paper_dir.suffix == ".tex":
            tex_excerpt = paper_dir.read_text()[:4000]
        author_reviews = _get_author_reviews(
            reviewer_authors, paper_metrics, paper_id, comparison_rows, tex_excerpt
        )
        for rev in author_reviews:
            console.print(f"\n[bold cyan]{rev['author']}[/bold cyan] ({rev['venue']}):")
            console.print(f"  {rev['review'][:200]}...")

    # Generate markdown report
    md_report = _generate_benchmark_markdown(
        paper_id, paper_metrics, report, comparison_rows, benchmarks,
        author_reviews=author_reviews,
    )

    # Determine output directory
    if paper_dir.suffix == ".tex":
        report_dir = paper_dir.parent / "reviews"
    else:
        report_dir = paper_dir / "reviews"
    report_dir.mkdir(parents=True, exist_ok=True)

    md_path = report_dir / "benchmark_eval.md"
    md_path.write_text(md_report)
    console.print(f"[green]Saved markdown report to {md_path}[/green]")

    if output:
        output.write_text(json.dumps(report.to_dict(), indent=2))
        console.print(f"[green]Saved JSON report to {output}[/green]")


@app.command("ingest-benchmark")
def ingest_benchmark(
    arxiv_id: str = typer.Argument(..., help="Arxiv ID to add to benchmark corpus"),
    tex_file: Optional[Path] = typer.Option(
        None, "--tex", help="Local .tex file instead of arxiv download"
    ),
) -> None:
    """Add a paper to the benchmark corpus."""
    from .benchmarks import BENCHMARKS_FILE

    corpus = []
    if BENCHMARKS_FILE.exists():
        corpus = json.loads(BENCHMARKS_FILE.read_text())

    existing_ids = {p["id"] for p in corpus}
    if arxiv_id in existing_ids:
        console.print(f"[yellow]{arxiv_id} already in corpus[/yellow]")
        raise typer.Exit(0)

    if tex_file and tex_file.exists():
        content = tex_file.read_text()
    else:
        console.print("[yellow]Provide --tex <path> for local papers[/yellow]")
        raise typer.Exit(1)

    words = len(re.sub(r"\\[a-zA-Z]+\*?\{[^}]*\}", " ", content).split())
    est_pages = max(1, words // 350)
    equations = len(re.findall(r"\\begin\{(?:equation|align)\*?\}", content))
    figures = len(re.findall(r"\\begin\{figure", content))
    tables = len(re.findall(r"\\begin\{table", content))
    footnotes = len(re.findall(r"\\footnote\{", content))

    refs = 0
    bib_path = tex_file.parent / "references.bib" if tex_file else None
    if bib_path and bib_path.exists():
        refs = len(re.findall(r"@\w+\{", bib_path.read_text()))
    else:
        refs = len(re.findall(r"\\bibitem", content))

    sections = len(re.findall(r"\\section\{", content))

    entry = {
        "id": arxiv_id,
        "words": words, "est_pages": est_pages,
        "equations": equations, "figures": figures,
        "tables": tables, "refs": refs,
        "footnotes": footnotes, "sections": sections,
        "eq_per_pg": round(equations / est_pages, 2),
        "fig_per_pg": round(figures / est_pages, 2),
        "ref_per_pg": round(refs / est_pages, 2),
    }

    corpus.append(entry)
    BENCHMARKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BENCHMARKS_FILE.write_text(json.dumps(corpus, indent=2))

    console.print(f"[green]Added {arxiv_id} to corpus ({len(corpus)} total)[/green]")
    table = Table(title=f"Metrics: {arxiv_id}")
    for k, v in entry.items():
        if k != "id":
            table.add_column(k, justify="right")
    table.add_row(*[str(v) for k, v in entry.items() if k != "id"])
    console.print(table)


def _get_author_reviews(
    reviewer_authors: list[dict],
    paper_metrics: dict,
    paper_id: str,
    comparison_rows: list[dict],
    tex_excerpt: str = "",
) -> list[dict]:
    """Get qualitative peer review comments from corpus senior authors via /scillm."""
    import os
    import subprocess

    SKILLS_DIR = Path(__file__).parent.parent.parent
    scillm_script = SKILLS_DIR / "scillm" / "batch.py"

    if not scillm_script.exists():
        logger.warning(f"scillm not found at {scillm_script}, skipping qualitative reviews")
        return []

    metrics_summary = "\n".join(
        f"  {r['metric']}: {r['paper_value']:.1f} (p25={r['p25']:.1f}, p50={r['p50']:.1f}, "
        f"p75={r['p75']:.1f}, rank={r['rank']:.0%}, {r['status']})"
        for r in comparison_rows
    )

    PERSONAS_DIR = Path(__file__).parent.parent / "personas" / "corpus_reviewers"
    enriched_personas: dict[str, dict] = {}
    if PERSONAS_DIR.exists():
        for pf in PERSONAS_DIR.glob("*.json"):
            try:
                persona = json.loads(pf.read_text())
                enriched_personas[persona.get("name", "")] = persona
            except Exception:
                pass
        if enriched_personas:
            logger.info(f"Loaded {len(enriched_personas)} enriched reviewer personas")

    reviews = []
    for author_info in reviewer_authors:
        author = author_info.get("senior_author", "Unknown")
        their_paper = author_info.get("title", "")
        expertise = author_info.get("expertise", "")
        venue = author_info.get("venue", "")

        persona_context = ""
        persona = enriched_personas.get(author)
        if persona:
            recent_papers = "\n".join(
                f"  - \"{p['title']}\" ({p['venue']}): {p['contribution']}"
                for p in persona.get("notable_papers", [])[:4]
            )
            critiques = "\n".join(
                f"  - {c}" for c in persona.get("review_critiques", [])[:5]
            )
            biases = "\n".join(
                f"  - {b}" for b in persona.get("biases", [])[:3]
            )
            persona_context = f"""
YOUR DETAILED PROFILE (from research on your publications):
Title: {persona.get('title', '')}
Affiliation: {persona.get('affiliation', '')}
Review style: {persona.get('review_style', '')}

Your other recent publications:
{recent_papers}

What you typically critique in peer review:
{critiques}

Your known biases (be self-aware but still apply your perspective):
{biases}
"""

        prompt = f"""You are {author}, a senior researcher who published "{their_paper}" at {venue}.
Your expertise: {expertise}.
{persona_context}

You are serving as an anonymous peer reviewer for a top CS venue (NeurIPS/ICML/ICLR).
You are reviewing paper "{paper_id}". Here are its structural metrics compared against a 12-paper ArXiv CS corpus:

{metrics_summary}

{'Paper excerpt:' if tex_excerpt else ''}
{tex_excerpt[:4000] if tex_excerpt else '(Full text not provided — review based on structural metrics and abstract only.)'}

Write a thorough peer review (2-3 paragraphs) structured as:

**Strengths:** What the paper does well. Be specific — cite metric ranks, methodology choices, or claims from the excerpt that impress you.

**Weaknesses:** Be critical and adversarial. Real peer review is NOT polite cheerleading. Identify:
- Missing baselines, ablations, or comparisons that a serious venue would demand
- Overclaimed contributions vs actual evidence
- Methodological gaps from YOUR specific expertise (e.g., how does this compare to your work on {expertise.split(',')[0].strip()}?)
- Statistical rigor concerns (sample sizes, confidence intervals, reproducibility)

**Questions for Authors:** 2-3 pointed questions you would ask in the rebuttal phase.

Write in first person as {author}. Be direct, specific, and intellectually honest.
Real reviewers reject papers — do not be afraid to recommend rejection if warranted.
Output ONLY the review text, no headers or metadata beyond the bold section labels above.
Do NOT use <think> tags or chain-of-thought reasoning — write the review directly."""

        try:
            env = os.environ.copy()
            env.pop("VIRTUAL_ENV", None)
            cmd = [
                "uv", "run", "--project", str(SKILLS_DIR / "scillm"),
                "python", str(scillm_script), "single",
                "--model", env.get("PEER_REVIEW_MODEL", env.get("CHUTES_TEXT_MODEL", "deepseek-ai/DeepSeek-V3-0324")),
                "--max-tokens", "4096",
                "--temperature", "0.7",
                "--timeout", "90",
                prompt,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)

            if result.returncode == 0:
                review_text = result.stdout.strip()
                if "<think>" in review_text:
                    review_text = re.sub(r"<think>.*?</think>\s*", "", review_text, flags=re.DOTALL).strip()
                reviews.append({
                    "author": author,
                    "paper": their_paper,
                    "expertise": expertise,
                    "venue": venue,
                    "review": review_text,
                })
                logger.info(f"Got review from {author} ({len(review_text)} chars)")
            else:
                logger.warning(f"scillm failed for {author}: {result.stderr[:200]}")
        except Exception as e:
            logger.warning(f"Author review failed for {author}: {e}")

    return reviews


def _generate_benchmark_markdown(
    paper_id: str,
    paper_metrics: dict,
    report,
    comparison_rows: list[dict],
    benchmarks,
    author_reviews: list[dict] | None = None,
) -> str:
    """Generate a markdown benchmark eval report."""
    from datetime import datetime, timezone

    lines = [
        f"# Benchmark Eval: {paper_id}",
        "",
        f"**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Corpus**: {len(benchmarks.corpus)} ArXiv papers",
        f"**Structural Score**: {report.overall_structural_score:.1f}/10",
        "",
        "## Paper Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]
    metric_labels = {
        "words": "Word count", "est_pages": "Estimated pages",
        "equations": "Equations", "figures": "Figures",
        "tables": "Tables", "refs": "References", "footnotes": "Footnotes",
    }
    for key in ["words", "est_pages", "equations", "figures", "tables", "refs", "footnotes"]:
        val = paper_metrics.get(key, 0)
        lines.append(f"| {metric_labels.get(key, key)} | {val} |")

    corpus_papers = benchmarks.corpus_papers_table()
    if corpus_papers:
        lines.extend([
            "", "## Reference Corpus", "",
            "| ArXiv ID | Title | Senior Author | Venue | Pages |",
            "|----------|-------|---------------|-------|------:|",
        ])
        for p in corpus_papers:
            title = p["title"][:60] + "..." if len(p["title"]) > 60 else p["title"]
            lines.append(
                f"| [{p['id']}](https://arxiv.org/abs/{p['id']}) | {title} | "
                f"{p['senior_author']} | {p['venue']} | {p['pages']} |"
            )

    lines.extend([
        "", "## Comparison Against ArXiv Corpus", "",
        "| Metric | Paper | p25 | p50 | p75 | Rank | Status |",
        "|--------|------:|----:|----:|----:|-----:|--------|",
    ])
    for row in comparison_rows:
        status_icon = {"strong": "+", "ok": "~", "weak": "-"}[row["status"]]
        lines.append(
            f"| {row['metric']} | {row['paper_value']:.2f} | "
            f"{row['p25']:.2f} | {row['p50']:.2f} | {row['p75']:.2f} | "
            f"{row['rank']:.0%} | {status_icon} {row['status']} |"
        )

    strong_flags = [f for f in report.flags if "strong" in f]
    weak_flags = [f for f in report.flags if "below" in f]

    if strong_flags:
        lines.extend(["", "## Strengths (above p75)", ""])
        for f in strong_flags:
            lines.append(f"- {f}")

    if weak_flags:
        lines.extend(["", "## Weaknesses (below p25)", ""])
        for f in weak_flags:
            lines.append(f"- {f}")

    if author_reviews:
        lines.extend(["", "## Peer Review Comments", ""])
        lines.append("*Qualitative assessments from corpus senior authors (via Tier 2 LLM):*")
        lines.append("")
        for rev in author_reviews:
            lines.append(f"### {rev['author']} — *{rev['paper']}* ({rev['venue']})")
            lines.append(f"**Expertise**: {rev['expertise']}")
            lines.append("")
            for rl in rev['review'].strip().split('\n'):
                lines.append(f"> {rl}")
            lines.append("")

    lines.extend(["", "## Recommendations", ""])

    if not weak_flags and not author_reviews:
        lines.append("All structural metrics at or above corpus median. No structural gaps detected.")
    elif not weak_flags:
        lines.append("Structural metrics are strong. See peer review comments above for qualitative guidance.")
    else:
        lines.append("Address the following to reach corpus norms:")
        for f in weak_flags:
            lines.append(f"- {f}")
        if author_reviews:
            lines.append("")
            lines.append("See peer review comments above for additional qualitative guidance.")

    lines.extend([
        "", "---", "",
        f"*Generated by `/create-peer-review benchmark` from a corpus of "
        f"{len(benchmarks.corpus)} ArXiv CS papers.*",
        "",
    ])

    return "\n".join(lines)
