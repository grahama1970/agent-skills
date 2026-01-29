"""
Paper Writer Skill - Research
Literature search and knowledge learning functions.
"""
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from config import (
    ARXIV_SCRIPT,
    LiteratureReview,
    PaperScope,
    ProjectAnalysis,
)


def search_literature(scope: PaperScope, analysis: ProjectAnalysis) -> LiteratureReview:
    """Stage 3: Literature search using /arxiv.

    Args:
        scope: Paper scope configuration
        analysis: Project analysis results

    Returns:
        LiteratureReview with papers found and selected
    """
    typer.echo("\n=== STAGE 3: LITERATURE SEARCH ===\n")

    # Validate dependencies before proceeding
    if not scope.contributions:
        typer.echo("[ERROR] No contributions defined - cannot generate context", err=True)
        raise typer.Exit(1)

    if not ARXIV_SCRIPT.exists():
        typer.echo(f"[ERROR] Skill script not found: {ARXIV_SCRIPT}", err=True)
        raise typer.Exit(1)

    # Generate arxiv context file in system temp directory
    temp_dir = Path(tempfile.gettempdir())
    context_file = temp_dir / f"arxiv_context_{scope.target_venue.replace(' ', '_')}.md"
    context_content = f"""# Research Context: {scope.contributions[0]}

## What We're Building
{scope.paper_type.capitalize()} paper for {scope.target_venue}

## Current State
Features: {', '.join(f.get('feature', '') for f in analysis.features[:5]) if analysis.features else 'None'}

## What We Need From Papers
{chr(10).join(f"{i+1}. {c}" for i, c in enumerate(scope.contributions))}

## Search Terms to Try
{' '.join(scope.prior_work_areas)}

## Relevance Criteria
- HIGH: Directly addresses our contributions
- MEDIUM: Related techniques that could adapt
- LOW: Tangentially related
"""
    context_file.write_text(context_content)
    typer.echo(f"Generated context: {context_file}")

    # Search arxiv
    query = " ".join(scope.prior_work_areas)
    typer.echo(f"\nSearching arXiv for: {query}")

    papers_found = []
    try:
        result = subprocess.run(
            [str(ARXIV_SCRIPT), "search", "--query", query, "--max-results", "20"],
            capture_output=True,
            text=True,
            check=True,
            timeout=90,
        )
        # Parse JSON output from arxiv search
        arxiv_result = json.loads(result.stdout)
        items = arxiv_result.get("items", [])
        for item in items:
            papers_found.append({
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "abstract": item.get("abstract", ""),
                "authors": item.get("authors", []),
                "published": item.get("published", ""),
                "categories": item.get("categories", []),
                "pdf_url": item.get("pdf_url", ""),
                "html_url": item.get("html_url", ""),
            })
        typer.echo(f"  Found {len(papers_found)} papers")
    except json.JSONDecodeError as e:
        typer.echo(f"[ERROR] Failed to parse arxiv output as JSON: {e}", err=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        if isinstance(e, subprocess.CalledProcessError):
            typer.echo(f"[ERROR] /arxiv search failed with exit code {e.returncode}", err=True)
            if e.stderr:
                typer.echo(f"[ERROR] stderr: {e.stderr}", err=True)
        else:
            typer.echo("[ERROR] /arxiv search timed out after 90s", err=True)

    # Paper triage - show papers with abstracts for user selection
    typer.echo(f"\n--- FOUND {len(papers_found)} PAPERS ---\n")

    high_relevance = []
    medium_relevance = []
    low_relevance = []

    if papers_found:
        # Categorize by relevance (simple keyword matching)
        for p in papers_found:
            title_lower = p["title"].lower()
            abstract_lower = p["abstract"].lower()
            # Check if contribution keywords appear in title/abstract
            contrib_keywords = " ".join(scope.contributions).lower().split()
            matches = sum(1 for kw in contrib_keywords if kw in title_lower or kw in abstract_lower)

            if matches >= 3:
                high_relevance.append(p)
            elif matches >= 1:
                medium_relevance.append(p)
            else:
                low_relevance.append(p)

        # Display HIGH relevance papers
        if high_relevance:
            typer.echo("HIGH RELEVANCE (directly related):")
            for i, p in enumerate(high_relevance[:5], 1):
                typer.echo(f"  [{i}] {p['id']}: {p['title'][:60]}...")
                typer.echo(f"      Authors: {', '.join(p['authors'][:3])}")
                typer.echo(f"      Abstract: {p['abstract'][:150]}...")
                typer.echo()

        # Display MEDIUM relevance papers
        if medium_relevance:
            typer.echo("MEDIUM RELEVANCE (tangentially related):")
            for i, p in enumerate(medium_relevance[:5], len(high_relevance) + 1):
                typer.echo(f"  [{i}] {p['id']}: {p['title'][:60]}...")
            typer.echo()

        # Show LOW count
        if low_relevance:
            typer.echo(f"LOW RELEVANCE: {len(low_relevance)} papers (not shown)")
            typer.echo()

    # Manual selection with better guidance
    typer.echo("Options:")
    typer.echo("  - Enter paper IDs (comma-separated): 2501.12345, 2502.67890")
    typer.echo("  - 'all-high' to select all high-relevance papers")
    typer.echo("  - 'skip' to skip literature review")

    selection = typer.prompt(
        "\nWhich papers to extract?",
        default="all-high" if papers_found else "skip",
    )

    papers_selected = []
    if selection != "skip":
        if selection == "all-high":
            # Select high relevance, fall back to top 5 if none
            if high_relevance:
                papers_selected = [p["id"] for p in high_relevance[:5]]
            else:
                papers_selected = [p["id"] for p in papers_found[:5]]
            typer.echo(f"  Selected {len(papers_selected)} papers: {', '.join(papers_selected)}")
        else:
            papers_selected = [p.strip() for p in selection.split(",")]

    review = LiteratureReview(
        papers_found=papers_found,
        papers_selected=papers_selected,
        extractions=[],
    )

    return review


def learn_from_papers(review: LiteratureReview, scope: PaperScope) -> LiteratureReview:
    """Stage 4: Extract knowledge from selected papers.

    Args:
        review: Literature review with selected papers
        scope: Paper scope configuration

    Returns:
        Updated LiteratureReview with extractions
    """
    typer.echo("\n=== STAGE 4: KNOWLEDGE LEARNING ===\n")

    if not review.papers_selected:
        typer.echo("No papers selected. Skipping learning stage.")
        return review

    # Use the same context file path as search_literature
    temp_dir = Path(tempfile.gettempdir())
    context_file = temp_dir / f"arxiv_context_{scope.target_venue.replace(' ', '_')}.md"

    if not ARXIV_SCRIPT.exists():
        typer.echo(f"[ERROR] Skill script not found: {ARXIV_SCRIPT}", err=True)
        typer.echo("[ERROR] Cannot proceed without arxiv skill", err=True)
        return review

    # Build extraction command args
    base_args = [str(ARXIV_SCRIPT), "learn"]

    typer.echo(f"Extracting knowledge from {len(review.papers_selected)} papers...")
    typer.echo("  Using scope: paper-writing")

    # Determine context arguments
    if context_file.exists():
        typer.echo(f"  Using context file: {context_file}")
        context_args = ["--context-file", str(context_file)]
    else:
        # Fallback to context string
        context_str = f"{scope.paper_type} paper on {', '.join(scope.contributions[:2])}"
        typer.echo(f"  Using context string: {context_str}")
        context_args = ["--context", context_str]

    # Ask user if they want interactive review
    from config import INTERVIEW_SKILL
    use_interview = False
    if INTERVIEW_SKILL.exists():
        use_interview = typer.confirm("\nUse interactive review for extracted Q&A pairs?", default=False)

    for i, paper_id in enumerate(review.papers_selected, 1):
        typer.echo(f"\n[{i}/{len(review.papers_selected)}] Extracting: {paper_id}")

        cmd_args = base_args + [
            paper_id,
            "--scope", "paper-writing",
        ] + context_args

        if not use_interview:
            cmd_args.append("--skip-interview")

        try:
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,  # 5 min per paper
            )
            # Parse output to count Q&A pairs if possible
            output = result.stdout
            qa_count = output.lower().count("q:") + output.lower().count("question:")
            typer.echo(f"  [OK] Extracted (~{qa_count} Q&A pairs)")
            extraction = {
                "paper_id": paper_id,
                "status": "success",
                "output": output,
                "qa_count": qa_count,
            }
        except subprocess.CalledProcessError as e:
            typer.echo(f"  [FAIL] Exit code {e.returncode}", err=True)
            if e.stderr:
                typer.echo(f"  stderr: ...{e.stderr[-200:]}", err=True)
            extraction = {"paper_id": paper_id, "status": "failed", "error": str(e)}
        except subprocess.TimeoutExpired:
            typer.echo("  [FAIL] Timed out after 5 min", err=True)
            extraction = {"paper_id": paper_id, "status": "timeout", "error": "Extraction timed out"}

        review.extractions.append(extraction)

    # Calculate summary statistics
    success_count = sum(1 for e in review.extractions if e["status"] == "success")
    failed_count = len(review.extractions) - success_count
    total_qa = sum(e.get("qa_count", 0) for e in review.extractions)

    typer.echo(f"\n  Successful: {success_count}/{len(review.extractions)}")
    typer.echo(f"  Failed: {failed_count}")
    typer.echo(f"  Total Q&A pairs extracted: ~{total_qa}")

    if failed_count > 0:
        typer.echo("\nFailed papers:")
        for e in review.extractions:
            if e["status"] != "success":
                typer.echo(f"  - {e['paper_id']}: {e.get('error', 'unknown error')[:50]}")

    if success_count == 0:
        typer.echo("\n[WARN] No papers successfully extracted. Draft will use stub content.", err=True)

    if not typer.confirm("\nProceed to draft generation?"):
        typer.echo("Stopping before draft generation.")
        raise typer.Exit(0)

    return review


def fetch_paper_details(paper_id: str) -> Optional[Dict[str, Any]]:
    """Fetch paper details from arxiv by ID.

    Args:
        paper_id: arXiv paper ID

    Returns:
        Paper dict or None
    """
    if not ARXIV_SCRIPT.exists():
        return None

    try:
        result = subprocess.run(
            [str(ARXIV_SCRIPT), "get", "--id", paper_id],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            items = data.get("items", [])
            if items:
                return items[0]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


def search_arxiv_papers(query: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """Search arXiv for papers matching query.

    Args:
        query: Search query
        max_results: Maximum number of results

    Returns:
        List of paper dicts
    """
    if not ARXIV_SCRIPT.exists():
        return []

    try:
        result = subprocess.run(
            [str(ARXIV_SCRIPT), "search", "--query", query, "--max-results", str(max_results)],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("items", [])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return []
