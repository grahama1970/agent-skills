#!/usr/bin/env python3
"""
Persona audit and batch operations: batch quality assessment, simulacrum
validation with iterative improvement loop.

Provides AuditReport, SimulacrumBatchResult, validate_and_improve_batch,
and audit_personas.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .persona import (
    list_personas,
    run_skill,
    store_to_memory,
)
from .quality_metrics import PersonaQualityScore
from .quality_diagnose import diagnose_persona
from .quality_validate import validate_simulacrum

from loguru import logger as log


@dataclass
class AuditReport:
    """Batch quality audit report."""

    scope: str
    total_personas: int
    scores: list[PersonaQualityScore]

    @property
    def average_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.overall_score for s in self.scores) / len(self.scores)

    @property
    def grade_distribution(self) -> dict[str, int]:
        dist = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for s in self.scores:
            dist[s.grade] += 1
        return dist

    @property
    def common_gaps(self) -> dict[str, int]:
        """Most common gaps across all personas."""
        gap_counts: dict[str, int] = {}
        for s in self.scores:
            for gap in s.gaps:
                gap_counts[gap] = gap_counts.get(gap, 0) + 1
        return dict(sorted(gap_counts.items(), key=lambda x: x[1], reverse=True)[:10])

    @property
    def failing_personas(self) -> list[str]:
        """Personas with grade F."""
        return [s.name for s in self.scores if s.grade == "F"]

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "total_personas": self.total_personas,
            "average_score": round(self.average_score, 2),
            "grade_distribution": self.grade_distribution,
            "common_gaps": self.common_gaps,
            "failing_personas": self.failing_personas,
            "details": [s.to_dict() for s in self.scores],
        }


# =============================================================================
# Batch Simulacrum Validation & Improvement Loop
# =============================================================================

@dataclass
class SimulacrumBatchResult:
    """Result of batch simulacrum validation and improvement."""

    scope: str
    total_personas: int
    initial_passing: int
    final_passing: int
    iterations: int
    max_iterations: int
    convergence_threshold: float

    # Per-persona results
    persona_results: list[dict] = field(default_factory=list)

    # Aggregate stats
    total_tests_run: int = 0
    total_improvements_made: int = 0

    @property
    def improvement_rate(self) -> float:
        if self.total_personas == 0:
            return 0.0
        return (self.final_passing - self.initial_passing) / self.total_personas

    @property
    def pass_rate(self) -> float:
        if self.total_personas == 0:
            return 0.0
        return self.final_passing / self.total_personas

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "total_personas": self.total_personas,
            "initial_passing": self.initial_passing,
            "final_passing": self.final_passing,
            "pass_rate": round(self.pass_rate, 2),
            "improvement_rate": round(self.improvement_rate, 2),
            "iterations": self.iterations,
            "max_iterations": self.max_iterations,
            "convergence_threshold": self.convergence_threshold,
            "total_tests_run": self.total_tests_run,
            "total_improvements_made": self.total_improvements_made,
            "persona_results": self.persona_results,
        }


def validate_and_improve_batch(
    scope: str = "personas",
    convergence_threshold: float = 0.7,
    max_iterations: int = 3,
    probe_types: list[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    checkpoint_file: Optional[Path] = None,
) -> SimulacrumBatchResult:
    """
    Batch simulacrum validation with iterative improvement loop.

    Like /prompt-lab or /debug-pdf, this:
    1. Tests each persona with simulacrum probes
    2. Identifies failing personas
    3. Runs improvement actions on failures
    4. Re-tests until convergence or max iterations

    Args:
        scope: Memory scope to process
        convergence_threshold: Accuracy threshold to pass (0.0-1.0)
        max_iterations: Max improvement iterations per persona
        probe_types: Types of probes (philosophy, technique, motivation, criticism, hypothetical)
        limit: Max personas to process
        dry_run: Preview without making changes
        checkpoint_file: File to save/resume progress

    Returns:
        SimulacrumBatchResult with all results
    """
    if probe_types is None:
        probe_types = ["philosophy", "technique", "motivation"]

    # Load personas
    personas = list_personas(scope=scope)
    if limit:
        personas = personas[:limit]

    log.info("Starting batch simulacrum validation for %d personas", len(personas))

    # Load checkpoint if exists
    checkpoint = {}
    if checkpoint_file and checkpoint_file.exists():
        try:
            checkpoint = json.loads(checkpoint_file.read_text())
            log.info("Resuming from checkpoint: %d already processed", len(checkpoint.get("completed", [])))
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    completed_names = set(checkpoint.get("completed", []))

    result = SimulacrumBatchResult(
        scope=scope,
        total_personas=len(personas),
        initial_passing=0,
        final_passing=0,
        iterations=0,
        max_iterations=max_iterations,
        convergence_threshold=convergence_threshold,
    )

    persona_results = []

    for persona in personas:
        name = persona.name

        # Skip if already completed in checkpoint
        if name in completed_names:
            log.info("Skipping %s (already in checkpoint)", name)
            continue

        log.info("Processing: %s", name)

        persona_result = {
            "name": name,
            "initial_accuracy": 0.0,
            "final_accuracy": 0.0,
            "iterations": 0,
            "passed": False,
            "improvements": [],
            "test_details": [],
        }

        # Initial validation
        score = validate_simulacrum(name, scope, probe_types)
        persona_result["initial_accuracy"] = score.accuracy
        persona_result["test_details"] = score.test_details
        result.total_tests_run += len(score.test_details)

        if score.accuracy >= convergence_threshold:
            persona_result["passed"] = True
            persona_result["final_accuracy"] = score.accuracy
            result.initial_passing += 1
            result.final_passing += 1
            log.info("  %s: PASSED (%.2f >= %.2f)", name, score.accuracy, convergence_threshold)
        else:
            log.info("  %s: FAILED (%.2f < %.2f) - starting improvement loop", name, score.accuracy, convergence_threshold)

            # Improvement loop
            for iteration in range(max_iterations):
                persona_result["iterations"] = iteration + 1
                result.iterations += 1

                # Identify what needs improvement based on test failures
                improvement_action = _identify_simulacrum_improvement(score)

                if improvement_action is None:
                    log.info("    Iteration %d: No more improvements available", iteration + 1)
                    break

                if dry_run:
                    persona_result["improvements"].append(f"(dry-run) Would: {improvement_action['description']}")
                    log.info("    Iteration %d: (dry-run) Would: %s", iteration + 1, improvement_action["description"])
                    continue

                # Execute improvement
                log.info("    Iteration %d: %s", iteration + 1, improvement_action["description"])
                persona_result["improvements"].append(improvement_action["description"])
                result.total_improvements_made += 1

                success = _execute_simulacrum_improvement(name, scope, improvement_action)
                if not success:
                    log.warning("    Improvement failed, continuing...")
                    continue

                # Re-validate
                score = validate_simulacrum(name, scope, probe_types)
                result.total_tests_run += len(score.test_details)

                if score.accuracy >= convergence_threshold:
                    persona_result["passed"] = True
                    persona_result["final_accuracy"] = score.accuracy
                    result.final_passing += 1
                    log.info("    CONVERGED at %.2f after %d iterations", score.accuracy, iteration + 1)
                    break
                else:
                    log.info("    Still at %.2f, continuing...", score.accuracy)

            if not persona_result["passed"]:
                persona_result["final_accuracy"] = score.accuracy
                log.info("  %s: Did not converge (final: %.2f)", name, score.accuracy)

        persona_results.append(persona_result)

        # Save checkpoint after each persona
        if checkpoint_file:
            completed_names.add(name)
            checkpoint["completed"] = list(completed_names)
            checkpoint["results"] = persona_results
            checkpoint_file.write_text(json.dumps(checkpoint, indent=2))

    result.persona_results = persona_results
    return result


def _identify_simulacrum_improvement(score: PersonaQualityScore) -> Optional[dict]:
    """
    Identify what improvement would help simulacrum quality.

    Analyzes test failures to determine what knowledge is missing.
    """
    # Analyze test failures
    failure_patterns = {
        "knowledge_gap": 0,
        "no_reasoning": 0,
        "too_short": 0,
        "trivia_focus": 0,
    }

    for test in score.test_details:
        failures = test.get("failures", [])
        notes = test.get("quality_notes", [])

        for f in failures:
            if "knowledge gap" in f.lower() or "don't have" in f.lower():
                failure_patterns["knowledge_gap"] += 1
            if "too short" in f.lower():
                failure_patterns["too_short"] += 1

        for n in notes:
            if "trivia" in n.lower():
                failure_patterns["trivia_focus"] += 1

    # Priority: knowledge gaps first, then depth issues
    if failure_patterns["knowledge_gap"] > 0:
        # Need more source material
        if score.sources_count < 5:
            return {
                "type": "deep_dogpile",
                "description": "Deep /dogpile research for philosophy and reasoning",
            }
        elif "youtube" not in str(score.gaps):
            return {
                "type": "youtube_lectures",
                "description": "Ingest YouTube lectures/interviews for first-person perspective",
            }
        else:
            return {
                "type": "books",
                "description": "Discover and ingest books for deeper knowledge",
            }

    if failure_patterns["too_short"] > 0:
        # Answers are too brief - need more QRA extraction
        return {
            "type": "qra_extraction",
            "description": "Extract more QRA pairs from existing sources",
        }

    if failure_patterns["trivia_focus"] > 0:
        # Too much trivia, not enough reasoning
        return {
            "type": "philosophy_focus",
            "description": "Research philosophy, interviews, and reasoning patterns",
        }

    # Default: more research
    return {
        "type": "deep_dogpile",
        "description": "Additional deep research",
    }


def _execute_simulacrum_improvement(name: str, scope: str, action: dict) -> bool:
    """Execute a simulacrum improvement action."""

    action_type = action["type"]

    if action_type == "deep_dogpile":
        # Focus on philosophy and reasoning, not biography
        result = run_skill("dogpile", [
            "search",
            f"{name} philosophy approach methodology interview reasoning creative process",
            "--no-interactive",
        ], timeout=300)
        # Store dogpile report to memory
        if result["returncode"] == 0 and result.get("stdout"):
            report = result["stdout"]
            if len(report) > 100:
                store_to_memory(
                    problem=f"{name}: philosophy, approach, methodology, reasoning patterns",
                    solution=report,
                    scope=scope,
                    tags=["dogpile", "philosophy", "simulacrum", name.lower().replace(" ", "_")],
                )
                log.info("Stored deep dogpile report for %s (%d chars)", name, len(report))
        return result["returncode"] == 0

    elif action_type == "youtube_lectures":
        # Get first-person content: lectures, interviews, talks
        # Use search command with correct syntax: search "query" --max N --no-interactive
        result = run_skill("ingest-youtube", [
            "search", f"{name} lecture interview talk masterclass",
            "--max", "5",
            "--no-interactive",
        ], timeout=600)
        # Store YouTube results to memory if we got any
        if result["returncode"] == 0 and result.get("stdout"):
            output = result["stdout"]
            if len(output) > 100:
                store_to_memory(
                    problem=f"{name}: YouTube lectures, interviews, talks (first-person content)",
                    solution=output,
                    scope=scope,
                    tags=["youtube", "lectures", "interviews", name.lower().replace(" ", "_")],
                )
                log.info("Stored YouTube results for %s", name)
        return result["returncode"] == 0

    elif action_type == "books":
        result = run_skill("discover-books", [
            "--query", f"{name}",
            "--max-results", "3",
        ], timeout=180)
        return result["returncode"] == 0

    elif action_type == "qra_extraction":
        # Re-run /ask learn with focus on QRA
        result = run_skill("ask", [
            "learn", "learn", name,
            "--scope", scope,
            "--depth", "standard",
        ], timeout=600)
        return result["returncode"] == 0

    elif action_type == "philosophy_focus":
        # Targeted search for philosophy and worldview
        result = run_skill("dogpile", [
            "search",
            f'"{name}" philosophy worldview beliefs "in my view" "I believe" interview',
            "--no-interactive",
        ], timeout=300)
        # Store philosophy research to memory
        if result["returncode"] == 0 and result.get("stdout"):
            report = result["stdout"]
            if len(report) > 100:
                store_to_memory(
                    problem=f"{name}: philosophy, worldview, beliefs, first-person perspective",
                    solution=report,
                    scope=scope,
                    tags=["dogpile", "philosophy", "worldview", name.lower().replace(" ", "_")],
                )
                log.info("Stored philosophy report for %s (%d chars)", name, len(report))
        return result["returncode"] == 0

    return False


def audit_personas(
    scope: Optional[str] = None,
    min_quality: float = 0.0,
    limit: Optional[int] = None,
) -> AuditReport:
    """
    Audit quality of all personas in a scope.

    Args:
        scope: Memory scope to audit (None = all common scopes)
        min_quality: Only report personas below this threshold
        limit: Maximum personas to audit

    Returns:
        AuditReport with quality scores
    """
    personas = list_personas(scope=scope)

    if limit:
        personas = personas[:limit]

    scores = []
    for persona in personas:
        score = diagnose_persona(persona.name, persona.scope)

        if min_quality > 0 and score.overall_score >= min_quality:
            continue  # Skip high-quality personas

        scores.append(score)

    return AuditReport(
        scope=scope or "all",
        total_personas=len(personas),
        scores=scores,
    )
