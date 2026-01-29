"""
Paper Writer Skill - Analysis
Project analysis functions using assess, dogpile, and code-review.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import typer

from config import (
    ASSESS_SCRIPT,
    CODE_REVIEW_SCRIPT,
    DOGPILE_SCRIPT,
    PaperScope,
    ProjectAnalysis,
)


def analyze_project(
    project_path: Path,
    scope: PaperScope,
    auto_approve: bool = False,
) -> ProjectAnalysis:
    """Stage 2: Project analysis using assess + dogpile + code-review.

    Args:
        project_path: Path to project to analyze
        scope: Paper scope configuration
        auto_approve: If True, skip interactive prompts

    Returns:
        ProjectAnalysis with features, architecture, issues, etc.
    """
    # Validate project path exists and is directory
    if not project_path.exists():
        typer.echo(f"[ERROR] Project path does not exist: {project_path}", err=True)
        raise typer.Exit(1)
    if not project_path.is_dir():
        typer.echo(f"[ERROR] Project path is not a directory: {project_path}", err=True)
        raise typer.Exit(1)

    # Validate skill scripts exist
    if not ASSESS_SCRIPT.exists():
        typer.echo(f"[ERROR] Skill script not found: {ASSESS_SCRIPT}", err=True)
        raise typer.Exit(1)

    typer.echo("\n=== STAGE 2: PROJECT ANALYSIS ===\n")

    # 1. Run assess
    typer.echo("Running /assess...")
    assessment = _run_assess(project_path)

    features = assessment.get("categories", {}).get("working_well", [])
    architecture = {"patterns": assessment.get("architecture_patterns", [])}
    issues = assessment.get("categories", {}).get("brittle", [])

    # 2. Run dogpile for each contribution
    research_context = _run_dogpile_research(scope.contributions)

    # 3. Code-review alignment check (optional)
    alignment_report = _run_code_review_alignment(
        project_path, scope, auto_approve
    )

    analysis = ProjectAnalysis(
        features=features,
        architecture=architecture,
        issues=issues,
        research_context=research_context,
        alignment_report=alignment_report,
    )

    # Confirmation gate
    typer.echo("\n--- ANALYSIS SUMMARY ---")
    typer.echo(f"Features found: {len(features)}")
    typer.echo(f"Architecture patterns: {len(architecture.get('patterns', []))}")
    typer.echo(f"Issues detected: {len(issues)}")
    typer.echo(f"Research context: {len(research_context)} chars")

    # Show first 3 features
    if features:
        typer.echo("\nTop Features:")
        for f in features[:3]:
            typer.echo(f"  - {f.get('feature', 'Unknown')}")

    if not auto_approve:
        if not typer.confirm("\nDoes this analysis match your understanding?"):
            if typer.confirm("Refine scope and re-run?"):
                typer.echo("Exiting. Adjust scope and re-run.")
                raise typer.Exit(1)

    return analysis


def _run_assess(project_path: Path) -> Dict[str, Any]:
    """Run the assess skill on a project.

    Args:
        project_path: Path to the project

    Returns:
        Assessment dict
    """
    try:
        result = subprocess.run(
            [sys.executable, str(ASSESS_SCRIPT), "run", str(project_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        # Parse JSON from output
        output = result.stdout
        json_start = output.find('{')
        return json.loads(output[json_start:]) if json_start >= 0 else {}
    except subprocess.CalledProcessError as e:
        typer.echo(f"[ERROR] /assess failed with exit code {e.returncode}", err=True)
        if e.stderr:
            typer.echo(f"[ERROR] stderr: {e.stderr}", err=True)
        if e.stdout:
            typer.echo(f"[ERROR] stdout: {e.stdout}", err=True)
        return {}
    except json.JSONDecodeError as e:
        typer.echo(f"[ERROR] Failed to parse assess output as JSON: {e}", err=True)
        return {}


def _run_dogpile_research(contributions: list) -> str:
    """Run dogpile research for contributions.

    Args:
        contributions: List of contribution claims

    Returns:
        Combined research context string
    """
    typer.echo("\nRunning /dogpile for research context...")
    research_parts = []

    for contrib in contributions[:2]:  # Limit to 2 to avoid rate limits
        typer.echo(f"  Researching: {contrib}")
        try:
            result = subprocess.run(
                [str(DOGPILE_SCRIPT), "search", contrib],
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            research_parts.append(f"## {contrib}\n{result.stdout}")
        except subprocess.CalledProcessError as e:
            typer.echo(f"  [WARN] Dogpile failed for '{contrib}' with exit code {e.returncode}", err=True)
            if e.stderr:
                typer.echo(f"  [WARN] stderr: {e.stderr}", err=True)
            research_parts.append(f"## {contrib}\n(Research failed)")
        except subprocess.TimeoutExpired:
            typer.echo(f"  [WARN] Dogpile timed out for '{contrib}' after 120s", err=True)
            research_parts.append(f"## {contrib}\n(Research failed)")

    return "\n\n".join(research_parts)


def _run_code_review_alignment(
    project_path: Path,
    scope: PaperScope,
    auto_approve: bool,
) -> str:
    """Run code-review alignment check.

    Args:
        project_path: Path to the project
        scope: Paper scope
        auto_approve: If True, skip interactive prompts

    Returns:
        Alignment report string
    """
    if not CODE_REVIEW_SCRIPT.exists():
        typer.echo("\n[WARN] Code-review skill not found, skipping alignment check", err=True)
        return "Code-review skill not available"

    run_review = auto_approve or typer.confirm("\nRun code-review alignment check? (can take 2-5 min)")
    if not run_review:
        return "Skipped by user"

    typer.echo("Running /code-review for alignment check...")
    try:
        # Build a quick review request
        review_request = f"""# Code-Paper Alignment Check

## Title
Alignment check for paper: {scope.contributions[0] if scope.contributions else 'Project'}

## Summary
Verify that code implementation matches documented features and claims.

## Objectives
- Check if features in code match documentation
- Identify gaps between implementation and claims
- Find technical debt that should be mentioned in paper

## Path
{project_path}
"""
        review_file = Path(tempfile.gettempdir()) / "paper_alignment_review.md"
        review_file.write_text(review_request)

        result = subprocess.run(
            [
                sys.executable, str(CODE_REVIEW_SCRIPT),
                "review-full",
                "--file", str(review_file),
                "--provider", "github",
                "--model", "gpt-5",
                "--rounds", "1",
            ],
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout
        )
        if result.returncode == 0:
            typer.echo("  [PASS] Code-review completed")
            return result.stdout
        else:
            typer.echo(f"  [WARN] Code-review returned non-zero: {result.returncode}", err=True)
            return f"Code-review failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        typer.echo("  [WARN] Code-review timed out after 5 min", err=True)
        return "Code-review timed out"
    except Exception as e:
        typer.echo(f"  [WARN] Code-review error: {e}", err=True)
        return f"Code-review error: {e}"
