"""
Trace Upgrader: Multi-role critique for improving persona reasoning traces.

Implements ArkAgent-style trace upgrading:
1. PROPOSER: Generate initial reasoning
2. SKEPTIC: Challenge each step
3. ALT_PATH: Propose alternatives
4. VERIFIER: Check against grounding
5. MODERATOR: Synthesize final trace + correction episodes

Based on ArkAgent framework adapted for persona training.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import typer
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

app = typer.Typer()


@dataclass
class CorrectionEpisode:
    """A correction episode from trace upgrading."""
    episode_id: str
    state_before: str
    bad_step: str
    critique: str
    fixed_step: str
    verification: str


@dataclass
class UpgradedTrace:
    """An upgraded trace with correction episodes."""
    original_query: str
    original_response: str
    improved_trace: list[dict]
    final_response: str
    episodes: list[CorrectionEpisode]
    confidence: float
    route: str  # "one_shot" | "two_stage" | "stepwise"


# ============================================================================
# Multi-Role Critique Prompts
# ============================================================================

MULTI_ROLE_SYSTEM = """You are a multi-role reasoning critic. Given a query and response, you will:

1. PROPOSER: Analyze the existing reasoning trace
2. SKEPTIC: Identify weaknesses in each step
3. ALT_PATH: Suggest alternative reasoning approaches
4. VERIFIER: Check claims against known facts
5. MODERATOR: Synthesize an improved trace with explicit corrections

Output JSON with this schema:
{
  "proposer_analysis": "...",
  "skeptic_critiques": [
    {"step_id": 1, "issue": "...", "severity": "low|medium|high"}
  ],
  "alt_path": "...",
  "verifier_checks": [
    {"claim": "...", "verified": true|false, "source": "..."}
  ],
  "improved_trace": [
    {"step": 1, "thought": "..."},
    {"step": 2, "thought": "..."}
  ],
  "final_response": "...",
  "episodes": [
    {
      "state_before": "...",
      "bad_step": "...",
      "critique": "...",
      "fixed_step": "..."
    }
  ],
  "confidence": 0.85,
  "disputed_points": []
}
"""

CRITIQUE_PROMPT = """Query: {query}

Original Response: {response}

Original Reasoning Trace:
{trace}

Perform multi-role critique and output improved trace as JSON.
Focus on:
1. Factual accuracy (especially SPARTA IDs, technique names)
2. Logical coherence between steps
3. Appropriate citations and grounding
4. Persona-appropriate tone and humility

Output valid JSON only."""


# ============================================================================
# Complexity Scoring (for routing)
# ============================================================================

def compute_complexity(query: str, response: str) -> tuple[float, str]:
    """
    Compute complexity score for routing decisions.

    Returns (score, bucket) where bucket is easy|medium|hard|ambiguous.
    """
    score = 0.0

    # Length factors
    query_len = len(query.split())
    response_len = len(response.split())

    if query_len > 30:
        score += 0.2
    if response_len > 200:
        score += 0.2

    # Multi-hop cues
    multi_hop_patterns = [
        r'\b(compare|contrast)\b',
        r'\b(derive|deduce)\b',
        r'\b(prove|demonstrate)\b',
        r'\b(reconcile|integrate)\b',
        r'\b(and|or).*\b(and|or)\b',  # Multiple conditions
    ]
    for pattern in multi_hop_patterns:
        if re.search(pattern, query, re.I):
            score += 0.15

    # Technical complexity
    technical_patterns = [
        r'\bCWE-\d+\b',
        r'\bCVE-\d{4}-\d+\b',
        r'\b[A-Z]{2,3}-\d{4}\b',  # SPARTA IDs
        r'\bATT&CK\b',
    ]
    for pattern in technical_patterns:
        if re.search(pattern, query) or re.search(pattern, response):
            score += 0.1

    # Normalize to [0, 1]
    score = min(1.0, score)

    # Bucket assignment
    if score < 0.3:
        bucket = "easy"
    elif score < 0.5:
        bucket = "medium"
    elif score < 0.7:
        bucket = "hard"
    else:
        bucket = "ambiguous"

    return score, bucket


# ============================================================================
# LLM Client
# ============================================================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def call_llm(prompt: str, system: str = MULTI_ROLE_SYSTEM) -> dict:
    """
    Call LLM for critique. Uses scillm skill or direct API.

    Future work: Integrate with /scillm skill for consistent model access.
    """
    raise NotImplementedError(
        "LLM critique call not yet implemented — integrate with /scillm skill for consistent model access"
    )


# ============================================================================
# Trace Upgrading Logic
# ============================================================================

def upgrade_single_trace(
    query: str,
    response: str,
    trace: Optional[list[dict]] = None,
    route: str = "one_shot",
) -> UpgradedTrace:
    """
    Upgrade a single trace using multi-role critique.

    Routes:
    - one_shot: Single LLM call with multi-role prompt (default)
    - two_stage: Initial critique + targeted fixes
    - stepwise: Iterative step-by-step debate (expensive)
    """
    trace_str = ""
    if trace:
        for step in trace:
            trace_str += f"Step {step.get('step', '?')}: {step.get('thought', '')}\n"
    else:
        # Extract reasoning from response if no explicit trace
        trace_str = response

    prompt = CRITIQUE_PROMPT.format(
        query=query,
        response=response,
        trace=trace_str,
    )

    if route == "one_shot":
        result = call_llm(prompt)
    elif route == "two_stage":
        # Stage 1: Get critique
        result = call_llm(prompt)
        # Stage 2: Apply fixes (if issues found)
        if result.get("skeptic_critiques"):
            fix_prompt = f"Fix these issues: {result['skeptic_critiques']}\n{prompt}"
            result = call_llm(fix_prompt)
    else:  # stepwise
        # Iterative debate - expensive, only for hard cases
        result = call_llm(prompt)
        # Future work: Implement iterative loop

    # Extract correction episodes
    episodes = []
    for i, ep_data in enumerate(result.get("episodes", [])):
        episodes.append(CorrectionEpisode(
            episode_id=f"ep_{i:03d}",
            state_before=ep_data.get("state_before", ""),
            bad_step=ep_data.get("bad_step", ""),
            critique=ep_data.get("critique", ""),
            fixed_step=ep_data.get("fixed_step", ""),
            verification="Pending verification",
        ))

    return UpgradedTrace(
        original_query=query,
        original_response=response,
        improved_trace=result.get("improved_trace", []),
        final_response=result.get("final_response", response),
        episodes=episodes,
        confidence=result.get("confidence", 0.5),
        route=route,
    )


def route_trace(query: str, response: str) -> str:
    """
    Decide routing strategy based on complexity.

    Returns: "one_shot" | "two_stage" | "stepwise"
    """
    score, bucket = compute_complexity(query, response)

    if bucket == "easy":
        return "one_shot"
    elif bucket == "medium":
        return "one_shot"  # Still efficient enough
    elif bucket == "hard":
        return "two_stage"
    else:  # ambiguous
        return "two_stage"


# ============================================================================
# CLI Commands
# ============================================================================

@app.command()
def upgrade(
    input: Path = typer.Option(..., help="Input JSONL file"),
    output: Path = typer.Option(..., help="Output JSONL file for upgraded traces"),
    episodes_output: Optional[Path] = typer.Option(None, help="Output JSONL for correction episodes"),
    max_items: int = typer.Option(0, help="Max items to process (0=all)"),
    route: str = typer.Option("auto", help="Route: auto, one_shot, two_stage, stepwise"),
):
    """Upgrade reasoning traces using multi-role critique."""

    logger.info(f"Loading input from {input}")
    with open(input) as f:
        data = [json.loads(line) for line in f]

    if max_items > 0:
        data = data[:max_items]

    logger.info(f"Processing {len(data)} items")

    upgraded = []
    all_episodes = []

    for i, item in enumerate(data):
        query = item.get("query", item.get("question", ""))
        response = item.get("response", item.get("answer", ""))
        trace = item.get("reasoning_trace")

        # Determine route
        if route == "auto":
            selected_route = route_trace(query, response)
        else:
            selected_route = route

        logger.info(f"[{i+1}/{len(data)}] Processing with route: {selected_route}")

        try:
            result = upgrade_single_trace(query, response, trace, selected_route)

            # Build output record
            upgraded_record = {
                "query": query,
                "original_response": response,
                "improved_trace": result.improved_trace,
                "final_response": result.final_response,
                "confidence": result.confidence,
                "route": result.route,
                "episode_count": len(result.episodes),
            }
            upgraded.append(upgraded_record)

            # Collect episodes
            for ep in result.episodes:
                all_episodes.append({
                    "episode_id": ep.episode_id,
                    "query": query,
                    "state_before": ep.state_before,
                    "bad_step": ep.bad_step,
                    "critique": ep.critique,
                    "fixed_step": ep.fixed_step,
                    "verification": ep.verification,
                })

        except Exception as e:
            logger.error(f"Failed to process item {i}: {e}")
            # Keep original
            upgraded.append({
                "query": query,
                "original_response": response,
                "improved_trace": [],
                "final_response": response,
                "confidence": 0.0,
                "route": "failed",
                "error": str(e),
            })

    # Write outputs
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for record in upgraded:
            f.write(json.dumps(record) + "\n")
    logger.info(f"Wrote {len(upgraded)} upgraded traces to {output}")

    if episodes_output:
        with open(episodes_output, "w") as f:
            for ep in all_episodes:
                f.write(json.dumps(ep) + "\n")
        logger.info(f"Wrote {len(all_episodes)} correction episodes to {episodes_output}")

    # Summary
    success_count = sum(1 for u in upgraded if u["route"] != "failed")
    episode_count = len(all_episodes)
    avg_confidence = sum(u["confidence"] for u in upgraded) / len(upgraded) if upgraded else 0

    logger.info(f"Summary: {success_count}/{len(data)} succeeded, {episode_count} episodes, avg confidence: {avg_confidence:.2f}")


@app.command()
def analyze(
    input: Path = typer.Option(..., help="Upgraded traces JSONL"),
):
    """Analyze upgraded trace quality."""

    with open(input) as f:
        data = [json.loads(line) for line in f]

    # Compute stats
    routes = {}
    confidences = []
    episode_counts = []

    for item in data:
        route = item.get("route", "unknown")
        routes[route] = routes.get(route, 0) + 1
        confidences.append(item.get("confidence", 0))
        episode_counts.append(item.get("episode_count", 0))

    print("\n=== Trace Upgrade Analysis ===\n")
    print(f"Total items: {len(data)}")
    print(f"\nRoutes:")
    for route, count in sorted(routes.items()):
        print(f"  {route}: {count} ({count/len(data)*100:.1f}%)")

    print(f"\nConfidence:")
    print(f"  Mean: {sum(confidences)/len(confidences):.2f}")
    print(f"  Min: {min(confidences):.2f}")
    print(f"  Max: {max(confidences):.2f}")

    print(f"\nCorrection Episodes:")
    print(f"  Total: {sum(episode_counts)}")
    print(f"  Mean per item: {sum(episode_counts)/len(data):.2f}")
    print(f"  Items with episodes: {sum(1 for c in episode_counts if c > 0)}")


if __name__ == "__main__":
    app()
