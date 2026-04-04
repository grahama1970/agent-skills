#!/usr/bin/env python3
"""
Persona Router - Uses bridge classifier to find relevant personas.

When Embry has a question, this module:
1. Runs the question through the bridge classifier
2. Finds personas in memory whose bridge_weights match
3. Returns both expected experts AND wildcards

The power is finding experts you wouldn't have thought to ask.
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger as log

from .persona import Persona, recall_from_memory
import typer

# Path to bridge classifier
CLASSIFIER_SKILL = Path(__file__).parent.parent.parent / "create-classifier"
BRIDGE_INFERENCE = CLASSIFIER_SKILL / "scripts" / "bridge_inference.py"

# The 6 Federated Taxonomy bridges
BRIDGES = ["Corruption", "Precision", "Resilience", "Fragility", "Loyalty", "Stealth"]


@dataclass
class PersonaMatch:
    """A persona match with relevance scoring."""
    persona: Persona
    match_score: float  # 0.0 - 1.0 overall match
    matched_bridges: dict[str, float]  # {bridge: overlap_score}
    is_wildcard: bool  # True if unexpected match
    reason: str  # Why this persona was matched


@dataclass
class RoutingResult:
    """Result of routing a question to personas."""
    question: str
    detected_bridges: dict[str, float]  # Raw classifier output
    expected_matches: list[PersonaMatch]  # Obviously relevant personas
    wildcard_matches: list[PersonaMatch]  # Unexpected but valuable
    routing_time_ms: float


def classify_bridges(text: str, threshold: float = 0.3) -> dict[str, float]:
    """Run text through bridge classifier.

    Args:
        text: Question or text to classify
        threshold: Minimum confidence to include a bridge

    Returns:
        Dict of {bridge_name: confidence_score}
    """
    if not BRIDGE_INFERENCE.exists():
        log.warning("Bridge classifier not found at %s", BRIDGE_INFERENCE)
        return {}

    try:
        result = subprocess.run(
            [sys.executable, str(BRIDGE_INFERENCE), text, "--all", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(CLASSIFIER_SKILL),
        )

        if result.returncode == 0:
            bridges = json.loads(result.stdout)
            # Filter by threshold
            return {k: v for k, v in bridges.items() if v >= threshold}
        else:
            log.warning("Bridge classifier failed: %s", result.stderr)
            return {}

    except subprocess.TimeoutExpired:
        log.error("Bridge classifier timed out")
        return {}
    except json.JSONDecodeError as e:
        log.error("Failed to parse classifier output: %s", e)
        return {}
    except Exception as e:
        log.error("Bridge classification error: %s", e)
        return {}


def find_personas_by_bridges(
    bridges: dict[str, float],
    scope: str = "personas",
    min_overlap: float = 0.5,
) -> list[tuple[Persona, dict[str, float]]]:
    """Find personas whose bridge_weights overlap with detected bridges.

    Args:
        bridges: Detected bridges from classifier
        scope: Memory scope to search
        min_overlap: Minimum bridge overlap to include

    Returns:
        List of (persona, overlap_scores) tuples
    """
    if not bridges:
        return []

    # Search for personas with relevant bridge tags
    bridge_tags = [f"bridge:{b}" for b in bridges.keys()]

    # Query memory for personas
    matches = []

    for bridge_name in bridges.keys():
        items = recall_from_memory(
            query=f"Persona with {bridge_name} bridge",
            scope=scope,
            k=10,
            tags=[f"bridge:{bridge_name}"],
        )

        for item in items:
            solution = item.get("solution", "")
            try:
                data = json.loads(solution)
                persona = Persona.from_dict(data)

                # Calculate bridge overlap
                overlap = calculate_bridge_overlap(bridges, persona.bridge_weights)

                if overlap["score"] >= min_overlap:
                    matches.append((persona, overlap))

            except (json.JSONDecodeError, TypeError):
                continue

    # Deduplicate by persona name
    seen = set()
    unique_matches = []
    for persona, overlap in matches:
        if persona.name not in seen:
            seen.add(persona.name)
            unique_matches.append((persona, overlap))

    # Sort by overlap score
    unique_matches.sort(key=lambda x: x[1]["score"], reverse=True)

    return unique_matches


def calculate_bridge_overlap(
    query_bridges: dict[str, float],
    persona_bridges: dict[str, float],
) -> dict:
    """Calculate how well a persona's bridges match the query.

    Args:
        query_bridges: Detected bridges from classifier
        persona_bridges: Persona's bridge_weights

    Returns:
        Dict with score and per-bridge overlaps
    """
    if not query_bridges or not persona_bridges:
        return {"score": 0.0, "bridges": {}}

    overlaps = {}
    total_weight = 0.0
    weighted_overlap = 0.0

    for bridge, query_score in query_bridges.items():
        persona_score = persona_bridges.get(bridge, 0.0)

        # Overlap is product of scores (both need to be high)
        overlap = query_score * persona_score
        overlaps[bridge] = overlap

        total_weight += query_score
        weighted_overlap += overlap

    # Normalize by query weight
    score = weighted_overlap / total_weight if total_weight > 0 else 0.0

    return {"score": score, "bridges": overlaps}


def is_wildcard_match(
    persona: Persona,
    primary_bridges: list[str],
    matched_bridges: dict[str, float],
) -> bool:
    """Determine if a persona is a wildcard (unexpected) match.

    A wildcard matches via secondary bridges, not the primary ones.

    Args:
        persona: The matched persona
        primary_bridges: Top 2 bridges from query
        matched_bridges: How this persona matched

    Returns:
        True if this is a wildcard match
    """
    if not primary_bridges:
        return False

    # Get persona's top bridges
    persona_top = sorted(
        persona.bridge_weights.items(),
        key=lambda x: x[1],
        reverse=True
    )[:2]
    persona_top_names = [b[0] for b in persona_top]

    # Wildcard if persona's top bridges don't overlap with query's top bridges
    overlap = set(persona_top_names) & set(primary_bridges)

    return len(overlap) == 0


def route_question(
    question: str,
    scope: str = "personas",
    bridge_threshold: float = 0.3,
    min_overlap: float = 0.4,
    max_results: int = 5,
) -> RoutingResult:
    """Route a question to relevant personas using the bridge classifier.

    This is the main entry point. Given a question:
    1. Classify it to detect relevant bridges
    2. Find personas matching those bridges
    3. Separate into expected vs wildcard matches

    Args:
        question: The question to route
        scope: Memory scope to search
        bridge_threshold: Min confidence to include a bridge
        min_overlap: Min overlap score to include a persona
        max_results: Max total personas to return

    Returns:
        RoutingResult with matched personas
    """
    import time
    start = time.perf_counter()

    # Step 1: Classify bridges
    detected = classify_bridges(question, threshold=bridge_threshold)

    if not detected:
        log.warning("No bridges detected for: %s", question[:50])
        return RoutingResult(
            question=question,
            detected_bridges={},
            expected_matches=[],
            wildcard_matches=[],
            routing_time_ms=(time.perf_counter() - start) * 1000,
        )

    # Get primary bridges (top 2)
    sorted_bridges = sorted(detected.items(), key=lambda x: x[1], reverse=True)
    primary_bridges = [b[0] for b in sorted_bridges[:2]]

    log.info("Detected bridges: %s", detected)
    log.info("Primary bridges: %s", primary_bridges)

    # Step 2: Find matching personas
    matches = find_personas_by_bridges(detected, scope, min_overlap)

    # Step 3: Categorize as expected vs wildcard
    expected = []
    wildcards = []

    for persona, overlap in matches[:max_results]:
        is_wild = is_wildcard_match(persona, primary_bridges, overlap["bridges"])

        # Generate reason
        top_match_bridge = max(overlap["bridges"].items(), key=lambda x: x[1])[0] if overlap["bridges"] else "unknown"

        if is_wild:
            reason = f"Wildcard via {top_match_bridge} bridge - brings unexpected perspective"
        else:
            reason = f"Strong {top_match_bridge} alignment ({overlap['score']:.0%})"

        match = PersonaMatch(
            persona=persona,
            match_score=overlap["score"],
            matched_bridges=overlap["bridges"],
            is_wildcard=is_wild,
            reason=reason,
        )

        if is_wild:
            wildcards.append(match)
        else:
            expected.append(match)

    elapsed_ms = (time.perf_counter() - start) * 1000

    return RoutingResult(
        question=question,
        detected_bridges=detected,
        expected_matches=expected,
        wildcard_matches=wildcards,
        routing_time_ms=elapsed_ms,
    )


def format_routing_result(result: RoutingResult) -> str:
    """Format routing result for display."""
    lines = [
        f"Question: {result.question}",
        f"",
        f"Detected Bridges:",
    ]

    for bridge, score in sorted(result.detected_bridges.items(), key=lambda x: -x[1]):
        lines.append(f"  {bridge}: {score:.0%}")

    lines.append("")

    if result.expected_matches:
        lines.append("Expected Experts:")
        for match in result.expected_matches:
            lines.append(f"  {match.persona.name} ({match.match_score:.0%})")
            lines.append(f"    Role: {match.persona.role}")
            lines.append(f"    Reason: {match.reason}")
    else:
        lines.append("No expected experts found")

    lines.append("")

    if result.wildcard_matches:
        lines.append("Wildcard Experts (unexpected but valuable):")
        for match in result.wildcard_matches:
            lines.append(f"  {match.persona.name} ({match.match_score:.0%})")
            lines.append(f"    Role: {match.persona.role}")
            lines.append(f"    Reason: {match.reason}")

    lines.append("")
    lines.append(f"Routing time: {result.routing_time_ms:.1f}ms")

    return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

def main(
    question: str = typer.Argument(..., help="Question to route"),
    scope: str = typer.Option("personas", help="Memory scope"),
    threshold: float = typer.Option(0.3, help="Bridge threshold"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    test: bool = typer.Option(False, help="Run test questions"),
):

    if test:
        # Test with sample UX questions
        test_questions = [
            "How does the 10ft ambient display look visually?",
            "Is the typography readable at distance?",
            "Does the Discord notification feel trustworthy?",
            "Are the animations natural and responsive?",
        ]

        for q in test_questions:
            print(f"\n{'='*60}")
            result = route_question(q, scope=scope)
            print(format_routing_result(result))

        return

    if not question:
        # Read from stdin
        question = sys.stdin.read().strip()

    if not question:
        print("Error: No question provided", file=sys.stderr)
        sys.exit(1)

    result = route_question(
        question,
        scope=scope,
        bridge_threshold=threshold,
    )

    if json:
        output = {
            "question": result.question,
            "detected_bridges": result.detected_bridges,
            "expected": [
                {
                    "name": m.persona.name,
                    "role": m.persona.role,
                    "score": m.match_score,
                    "reason": m.reason,
                }
                for m in result.expected_matches
            ],
            "wildcards": [
                {
                    "name": m.persona.name,
                    "role": m.persona.role,
                    "score": m.match_score,
                    "reason": m.reason,
                }
                for m in result.wildcard_matches
            ],
            "routing_time_ms": result.routing_time_ms,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_routing_result(result))


if __name__ == "__main__":
    main()
