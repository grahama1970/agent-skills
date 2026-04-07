#!/usr/bin/env python3
"""
Persona improvement: iterative enhancement with convergence.

Provides improve_persona() which iteratively runs improvement actions
(dogpile research, YouTube ingest, book discovery, etc.) until
a quality threshold is met.
"""

from dataclasses import dataclass
from typing import Optional

from .persona import (
    run_skill,
    store_to_memory,
)
from .quality_metrics import PersonaQualityScore
from .quality_diagnose import diagnose_persona

from loguru import logger as log


@dataclass
class ImprovementResult:
    """Result of an improvement attempt."""
    name: str
    scope: str
    initial_score: float
    final_score: float
    iterations: int
    actions_taken: list[str]
    converged: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "scope": self.scope,
            "initial_score": round(self.initial_score, 2),
            "final_score": round(self.final_score, 2),
            "improvement": round(self.final_score - self.initial_score, 2),
            "iterations": self.iterations,
            "actions_taken": self.actions_taken,
            "converged": self.converged,
        }


def improve_persona(
    name: str,
    scope: str = "personas",
    quality_threshold: float = 0.7,
    max_iterations: int = 3,
    dry_run: bool = False,
) -> ImprovementResult:
    """
    Iteratively improve a persona until quality threshold is met.

    Improvement actions:
    - Re-run /dogpile for missing sources
    - Discover books if none
    - Ingest YouTube if none
    - Enrich colleague graph

    Args:
        name: Persona name
        scope: Memory scope
        quality_threshold: Target quality score (0.0-1.0)
        max_iterations: Maximum improvement iterations
        dry_run: Preview actions without executing

    Returns:
        ImprovementResult with actions taken
    """
    # Initial assessment
    initial_score = diagnose_persona(name, scope)

    result = ImprovementResult(
        name=name,
        scope=scope,
        initial_score=initial_score.overall_score,
        final_score=initial_score.overall_score,
        iterations=0,
        actions_taken=[],
        converged=initial_score.overall_score >= quality_threshold,
    )

    if result.converged:
        result.actions_taken.append(f"Already at quality {initial_score.overall_score:.2f} >= {quality_threshold}")
        return result

    current_score = initial_score

    for iteration in range(max_iterations):
        result.iterations = iteration + 1

        # Identify best action based on gaps
        action = _select_improvement_action(current_score)

        if action is None:
            result.actions_taken.append("No more improvement actions available")
            break

        if dry_run:
            result.actions_taken.append(f"(dry-run) Would: {action['description']}")
            continue

        # Execute action
        log.info("Improvement iteration %d: %s", iteration + 1, action["description"])
        result.actions_taken.append(action["description"])

        success = _execute_improvement_action(name, scope, action)
        if not success:
            result.actions_taken.append(f"  Failed: {action['description']}")
            continue

        # Re-assess
        current_score = diagnose_persona(name, scope)
        result.final_score = current_score.overall_score

        if current_score.overall_score >= quality_threshold:
            result.converged = True
            result.actions_taken.append(f"Converged at quality {current_score.overall_score:.2f}")
            break

    return result


def _select_improvement_action(score: PersonaQualityScore) -> Optional[dict]:
    """Select the best improvement action based on gaps."""

    # Priority order of actions
    for gap in score.gaps:
        if "No learning sources" in gap or "Missing source: dogpile" in gap:
            return {
                "type": "dogpile",
                "description": "Run /dogpile deep research",
            }

        if "Missing source: youtube" in gap:
            return {
                "type": "youtube",
                "description": "Ingest YouTube lectures/interviews",
            }

        if "Missing source: books" in gap:
            return {
                "type": "books",
                "description": "Discover and ingest books",
            }

        if "No colleague relationships" in gap:
            return {
                "type": "colleagues",
                "description": "Discover and create colleague relationships",
            }

        if "No QRA pairs" in gap:
            return {
                "type": "qra",
                "description": "Extract QRA pairs from existing knowledge",
            }

        if "Stale data" in gap:
            return {
                "type": "refresh",
                "description": "Refresh with latest content",
            }

    return None


def _execute_improvement_action(name: str, scope: str, action: dict) -> bool:
    """Execute an improvement action."""

    action_type = action["type"]

    if action_type == "dogpile":
        result = run_skill("dogpile", [
            "search", name,
            "--no-interactive",
        ], timeout=300)
        # Store dogpile report to memory if successful
        if result["returncode"] == 0 and result.get("stdout"):
            report = result["stdout"]
            if len(report) > 100:  # Only store substantial reports
                store_to_memory(
                    problem=f"Research on {name}: philosophy, approach, techniques",
                    solution=report,
                    scope=scope,
                    tags=["dogpile", "research", name.lower().replace(" ", "_")],
                )
                log.info("Stored dogpile report for %s (%d chars)", name, len(report))
        return result["returncode"] == 0

    elif action_type == "youtube":
        # Use search command with correct syntax: search "query" --max N --no-interactive
        result = run_skill("ingest-youtube", [
            "search", f"{name} lecture interview",
            "--max", "3",
            "--no-interactive",
        ], timeout=300)
        # Store YouTube results to memory
        if result["returncode"] == 0 and result.get("stdout"):
            output = result["stdout"]
            if len(output) > 100:
                store_to_memory(
                    problem=f"{name}: YouTube lectures and interviews",
                    solution=output,
                    scope=scope,
                    tags=["youtube", "lectures", name.lower().replace(" ", "_")],
                )
                log.info("Stored YouTube results for %s", name)
        return result["returncode"] == 0

    elif action_type == "books":
        result = run_skill("discover-books", [
            "--query", name,
            "--max-results", "3",
        ], timeout=120)
        return result["returncode"] == 0

    elif action_type == "colleagues":
        # Use /dogpile to find colleagues
        result = run_skill("dogpile", [
            "search", f"{name} colleagues collaborators",
            "--no-interactive",
        ], timeout=180)
        # Store colleague research to memory
        if result["returncode"] == 0 and result.get("stdout"):
            report = result["stdout"]
            if len(report) > 100:
                store_to_memory(
                    problem=f"Colleagues and collaborators of {name}",
                    solution=report,
                    scope=scope,
                    tags=["dogpile", "colleagues", name.lower().replace(" ", "_")],
                )
        return result["returncode"] == 0

    elif action_type == "refresh":
        # Re-run /ask learn
        result = run_skill("ask", [
            "learn", "learn", name,
            "--scope", scope,
            "--depth", "quick",
        ], timeout=300)
        return result["returncode"] == 0

    return False
