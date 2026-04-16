#!/usr/bin/env python3
"""Markov chain transition matrix for skill orchestration prediction.

Builds a transition probability matrix from execution traces, predicts
optimal skill chains for task types, and detects missing skills via
zero-probability gaps.

Inspired by:
- AutoTool (arxiv:2511.14650): directed graph from historical trajectories
- ToolMem (arxiv:2510.06664): memory-augmented tool selection
- PM4Py process discovery algorithms

Usage:
    python transition_matrix.py build              # Build matrix from traces
    python transition_matrix.py predict "extract tables from PDF"
    python transition_matrix.py gaps "extract tables from PDF"
    python transition_matrix.py sankey              # Export Sankey flow data
    python transition_matrix.py status              # Matrix health check
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).parent.parent / "state"
TRACES_FILE = STATE_DIR / "execution_traces.jsonl"
MATRIX_FILE = STATE_DIR / "transition_matrix.json"
TASK_MATRICES_FILE = STATE_DIR / "task_transition_matrices.json"
PREDICTION_LOG = STATE_DIR / "prediction_log.jsonl"

# Laplace smoothing for cold-start (unseen transitions)
LAPLACE_ALPHA = 0.01

# Minimum observations before trusting learned probabilities over prior
MIN_OBSERVATIONS = 3

# Task intent keywords → task type classification
TASK_TYPES = {
    "extraction": ["extract", "parse", "ingest", "convert", "pdf", "document"],
    "research": ["search", "find", "discover", "arxiv", "paper", "research", "dogpile"],
    "security": ["hack", "scan", "vulnerability", "pentest", "security", "audit"],
    "training": ["train", "fine-tune", "qlora", "lora", "model", "classifier"],
    "creation": ["create", "generate", "build", "scaffold", "write"],
    "monitoring": ["monitor", "watch", "track", "alert", "check", "status"],
    "review": ["review", "assess", "evaluate", "quality", "validate"],
    "memory": ["learn", "recall", "remember", "store", "knowledge"],
    "voice": ["voice", "tts", "rvc", "audio", "speech", "sing"],
    "media": ["video", "movie", "image", "storyboard", "youtube"],
}


def classify_task(task: str) -> str:
    """Classify a task description into a task type for matrix conditioning."""
    task_lower = task.lower()
    scores: dict[str, int] = defaultdict(int)
    for task_type, keywords in TASK_TYPES.items():
        for kw in keywords:
            if kw in task_lower:
                scores[task_type] += 1
    if not scores:
        return "general"
    return max(scores, key=scores.get)


def load_traces() -> list[dict]:
    """Load all execution traces."""
    if not TRACES_FILE.exists():
        return []
    traces = []
    for line in TRACES_FILE.read_text().strip().split("\n"):
        if line.strip():
            try:
                traces.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return traces


def _load_composer_traces() -> list[dict]:
    """Also load traces from composer's chain executions if available."""
    composer_log = STATE_DIR / "composer_chains.jsonl"
    if not composer_log.exists():
        return []
    traces = []
    for line in composer_log.read_text().strip().split("\n"):
        if line.strip():
            try:
                traces.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return traces


def build_matrix(traces: list[dict] | None = None) -> dict:
    """Build a Markov chain transition matrix from execution traces.

    Returns:
        {
            "matrix": {skill_a: {skill_b: probability, ...}, ...},
            "counts": {skill_a: {skill_b: count, ...}, ...},
            "skills": [list of all skills],
            "total_transitions": int,
            "total_traces": int,
            "built_at": ISO timestamp,
        }
    """
    if traces is None:
        traces = load_traces() + _load_composer_traces()

    # Count transitions: for each chain [A, B, C], count A→B and B→C
    counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    all_skills: set[str] = set()

    for trace in traces:
        chain = trace.get("chain", [])
        success = trace.get("success", True)
        weight = trace.get("weight", 1.0)

        # Weight successful chains higher than failures
        effective_weight = weight * (1.0 if success else 0.3)

        for skill in chain:
            all_skills.add(skill)

        # Count pairwise transitions
        for i in range(len(chain) - 1):
            src, dst = chain[i], chain[i + 1]
            counts[src][dst] += effective_weight

    # Also integrate AFFINITIES as prior (weak evidence)
    try:
        from composer import AFFINITIES
        for src, partners in AFFINITIES.items():
            all_skills.add(src)
            for dst, affinity in partners:
                all_skills.add(dst)
                # Prior weight: 0.5 observation equivalent per affinity point
                counts[src][dst] += affinity * 0.5
    except ImportError:
        pass

    # Normalize to probabilities with Laplace smoothing
    skills = sorted(all_skills)
    matrix: dict[str, dict[str, float]] = {}

    for src in skills:
        row = counts.get(src, {})
        total = sum(row.values()) + LAPLACE_ALPHA * len(skills)
        matrix[src] = {}
        for dst in skills:
            raw_count = row.get(dst, 0)
            matrix[src][dst] = round(
                (raw_count + LAPLACE_ALPHA) / total, 6
            )

    result = {
        "matrix": matrix,
        "counts": {k: dict(v) for k, v in counts.items()},
        "skills": skills,
        "total_transitions": sum(sum(v.values()) for v in counts.values()),
        "total_traces": len(traces),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MATRIX_FILE.write_text(json.dumps(result, indent=2))
    return result


def build_task_matrices(traces: list[dict] | None = None) -> dict:
    """Build per-task-type transition matrices.

    Different task types produce different skill flows. A security task
    flows hack→battle→memory, while extraction flows extractor→review-pdf→memory.
    """
    if traces is None:
        traces = load_traces() + _load_composer_traces()

    # Group traces by inferred task type
    task_groups: dict[str, list[dict]] = defaultdict(list)
    for trace in traces:
        chain = trace.get("chain", [])
        # Infer task type from the chain's skills
        chain_str = " ".join(chain)
        task_type = classify_task(chain_str)
        task_groups[task_type].append(trace)

    # Build a matrix per task type
    task_matrices = {}
    for task_type, group_traces in task_groups.items():
        task_matrices[task_type] = build_matrix(group_traces)

    result = {
        "task_matrices": {k: v["matrix"] for k, v in task_matrices.items()},
        "task_counts": {k: len(v) for k, v in task_groups.items()},
        "built_at": datetime.now(timezone.utc).isoformat(),
    }

    TASK_MATRICES_FILE.write_text(json.dumps(result, indent=2))
    return result


def load_matrix() -> dict | None:
    """Load cached matrix from disk."""
    if MATRIX_FILE.exists():
        return json.loads(MATRIX_FILE.read_text())
    return None


def predict_chain(
    task: str,
    start_skills: list[str] | None = None,
    max_length: int = 5,
    min_probability: float = 0.05,
) -> dict:
    """Predict the optimal skill chain for a task.

    Uses the transition matrix to greedily build the most likely chain.
    If task-conditioned matrices exist, uses those instead of global.

    Returns:
        {
            "task": str,
            "task_type": str,
            "chain": [skill1, skill2, ...],
            "probabilities": [p1, p2, ...],  # per-transition
            "chain_probability": float,  # product of all
            "gaps": [{position, from_skill, expected_capability}],
            "confidence": "high" | "medium" | "low",
        }
    """
    task_type = classify_task(task)

    # Try task-conditioned matrix first, fall back to global
    matrix_data = None
    if TASK_MATRICES_FILE.exists():
        task_data = json.loads(TASK_MATRICES_FILE.read_text())
        if task_type in task_data.get("task_matrices", {}):
            matrix_data = {
                "matrix": task_data["task_matrices"][task_type],
                "skills": sorted(
                    set().union(
                        *[set(row.keys()) for row in task_data["task_matrices"][task_type].values()]
                    )
                ),
            }

    if matrix_data is None:
        matrix_data = load_matrix()

    if matrix_data is None:
        # Cold start — build from whatever we have
        matrix_data = build_matrix()

    matrix = matrix_data["matrix"]
    all_skills = matrix_data.get("skills", [])

    if not all_skills:
        return {
            "task": task,
            "task_type": task_type,
            "chain": [],
            "probabilities": [],
            "chain_probability": 0.0,
            "gaps": [],
            "confidence": "none",
            "reason": "No skills in transition matrix",
        }

    # Determine starting skill(s) from task keywords or provided list
    if start_skills:
        chain = list(start_skills[:1])
    else:
        chain = [_best_start_skill(task, all_skills, matrix)]

    probabilities = []
    visited = set(chain)

    # Greedy chain building: pick highest probability next skill
    for _ in range(max_length - 1):
        current = chain[-1]
        if current not in matrix:
            break

        row = matrix[current]
        # Sort candidates by probability, skip visited
        candidates = sorted(
            [(skill, prob) for skill, prob in row.items()
             if skill not in visited and prob > min_probability],
            key=lambda x: -x[1],
        )

        if not candidates:
            break

        next_skill, prob = candidates[0]
        chain.append(next_skill)
        probabilities.append(prob)
        visited.add(next_skill)

    chain_probability = 1.0
    for p in probabilities:
        chain_probability *= p

    # Detect gaps (very low probability transitions)
    gaps = []
    for i, p in enumerate(probabilities):
        if p < 0.02:  # Near-zero probability = likely gap
            gaps.append({
                "position": i + 1,
                "from_skill": chain[i],
                "to_skill": chain[i + 1],
                "probability": p,
                "likely_missing": True,
                "suggestion": f"Missing skill between '{chain[i]}' and '{chain[i+1]}'",
            })

    # Confidence based on data quality
    total_traces = matrix_data.get("total_traces", 0)
    if total_traces >= 100:
        confidence = "high"
    elif total_traces >= 20:
        confidence = "medium"
    elif total_traces > 0:
        confidence = "low"
    else:
        confidence = "cold_start"

    result = {
        "task": task,
        "task_type": task_type,
        "chain": chain,
        "probabilities": probabilities,
        "chain_probability": round(chain_probability, 8),
        "gaps": gaps,
        "confidence": confidence,
        "total_traces": total_traces,
    }

    # Log prediction for future training
    _log_prediction(result)

    return result


def _best_start_skill(task: str, skills: list[str], matrix: dict) -> str:
    """Find the best starting skill for a task.

    Combines:
    1. Keyword matching (task mentions skill name)
    2. Outgoing edge strength (skills with many transitions = good starters)
    """
    task_lower = task.lower()
    scores: dict[str, float] = {}

    for skill in skills:
        score = 0.0
        # Direct name match
        if skill.replace("-", " ") in task_lower or skill.replace("-", "") in task_lower:
            score += 5.0
        # Partial keyword match
        for part in skill.split("-"):
            if len(part) > 2 and part in task_lower:
                score += 2.0
        # Outgoing edge strength (good starters have many transitions)
        if skill in matrix:
            outgoing = sum(p for p in matrix[skill].values() if p > 0.01)
            score += outgoing * 0.5
        scores[skill] = score

    if not scores:
        return skills[0]
    return max(scores, key=scores.get)


def detect_missing_skills(task: str, partial_chain: list[str] | None = None) -> dict:
    """Detect missing skills in a task's predicted chain.

    Returns positions where the transition probability drops to near-zero,
    indicating a gap that needs a new skill.

    Args:
        task: Task description
        partial_chain: Optional known partial chain to analyze

    Returns:
        {
            "task": str,
            "predicted_chain": [skills],
            "missing_positions": [{position, from, to, suggestion}],
            "coverage": float,  # 0-1 how complete the chain is
        }
    """
    prediction = predict_chain(task, start_skills=partial_chain)

    # Also check gap_detector for capability-level gaps
    try:
        from gap_detector import decompose_task, detect_gaps
        from scan_soup import scan_soup
        skills_root = Path(__file__).parent.parent.parent
        graph = scan_soup(skills_root)
        capability_gaps = detect_gaps(task, graph)
    except (ImportError, Exception):
        capability_gaps = None

    missing = []

    # From transition matrix: near-zero probability transitions
    for gap in prediction.get("gaps", []):
        missing.append({
            "source": "transition_matrix",
            "position": gap["position"],
            "from_skill": gap["from_skill"],
            "to_skill": gap["to_skill"],
            "probability": gap["probability"],
            "suggestion": gap["suggestion"],
        })

    # From capability graph: missing capabilities entirely
    if capability_gaps:
        for cap_gap in capability_gaps.get("create", []):
            missing.append({
                "source": "capability_graph",
                "capability": cap_gap["capability"],
                "description": cap_gap["description"],
                "lab": cap_gap.get("lab"),
                "suggestion": f"Create skill providing '{cap_gap['capability']}'"
                    + (f" via /{cap_gap['lab']}" if cap_gap.get("lab") else ""),
            })

    chain = prediction.get("chain", [])
    total_needed = len(chain) + len(missing)
    coverage = len(chain) / total_needed if total_needed > 0 else 1.0

    return {
        "task": task,
        "task_type": prediction.get("task_type", "general"),
        "predicted_chain": chain,
        "chain_probability": prediction.get("chain_probability", 0),
        "missing_positions": missing,
        "coverage": round(coverage, 3),
        "confidence": prediction.get("confidence", "none"),
    }


def export_sankey(traces: list[dict] | None = None) -> dict:
    """Export transition data in Sankey-compatible format for visualization.

    Returns nodes + links suitable for D3.js Sankey or Plotly Sankey.
    """
    if traces is None:
        traces = load_traces() + _load_composer_traces()

    # Count transitions
    link_counts: dict[tuple[str, str], float] = defaultdict(float)
    skill_counts: dict[str, float] = defaultdict(float)

    for trace in traces:
        chain = trace.get("chain", [])
        weight = trace.get("weight", 1.0)
        for skill in chain:
            skill_counts[skill] += weight
        for i in range(len(chain) - 1):
            link_counts[(chain[i], chain[i + 1])] += weight

    # Also integrate AFFINITIES for visualization even without traces
    try:
        from composer import AFFINITIES
        for src, partners in AFFINITIES.items():
            skill_counts[src] = max(skill_counts.get(src, 0), 1)
            for dst, affinity in partners:
                skill_counts[dst] = max(skill_counts.get(dst, 0), 1)
                link_counts[(src, dst)] = max(
                    link_counts.get((src, dst), 0), affinity
                )
    except ImportError:
        pass

    # Build node list
    skills = sorted(skill_counts.keys())
    skill_to_idx = {s: i for i, s in enumerate(skills)}

    nodes = [{"name": s, "value": round(skill_counts[s], 2)} for s in skills]
    links = [
        {
            "source": skill_to_idx[src],
            "target": skill_to_idx[dst],
            "value": round(count, 2),
        }
        for (src, dst), count in sorted(link_counts.items(), key=lambda x: -x[1])
    ]

    return {
        "nodes": nodes,
        "links": links,
        "total_skills": len(nodes),
        "total_links": len(links),
    }


def matrix_status() -> dict:
    """Health check for the transition matrix."""
    matrix_data = load_matrix()
    traces = load_traces()

    result = {
        "matrix_exists": matrix_data is not None,
        "total_traces": len(traces),
        "trace_file": str(TRACES_FILE),
        "matrix_file": str(MATRIX_FILE),
    }

    if matrix_data:
        result.update({
            "skills_count": len(matrix_data.get("skills", [])),
            "total_transitions": matrix_data.get("total_transitions", 0),
            "built_at": matrix_data.get("built_at", "unknown"),
            "skills": matrix_data.get("skills", []),
        })

        # Compute sparsity
        matrix = matrix_data.get("matrix", {})
        total_cells = len(matrix) ** 2 if matrix else 0
        non_zero = sum(
            1 for row in matrix.values()
            for p in row.values()
            if p > LAPLACE_ALPHA * 2  # Significantly above smoothing floor
        )
        result["sparsity"] = round(1 - non_zero / total_cells, 3) if total_cells else 1.0
        result["density"] = round(non_zero / total_cells, 3) if total_cells else 0.0

        # Find strongest transitions
        top_transitions = []
        for src, row in matrix.items():
            for dst, prob in row.items():
                if prob > 0.1:
                    top_transitions.append((src, dst, prob))
        top_transitions.sort(key=lambda x: -x[2])
        result["top_transitions"] = [
            {"from": t[0], "to": t[1], "probability": round(t[2], 4)}
            for t in top_transitions[:10]
        ]

    # Cold start assessment
    if len(traces) < MIN_OBSERVATIONS:
        result["cold_start"] = True
        result["cold_start_reason"] = (
            f"Only {len(traces)} traces. Need {MIN_OBSERVATIONS}+ for reliable predictions. "
            "Run warm_pond simulations or log real skill executions."
        )
    else:
        result["cold_start"] = False

    return result


def _log_prediction(prediction: dict) -> None:
    """Log a prediction for future accuracy tracking."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": prediction.get("task", ""),
        "task_type": prediction.get("task_type", ""),
        "chain": prediction.get("chain", []),
        "chain_probability": prediction.get("chain_probability", 0),
        "confidence": prediction.get("confidence", "none"),
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PREDICTION_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


import typer
from typing import Optional

app = typer.Typer(help="Markov chain transition matrix for skill orchestration")


@app.command()
def build() -> None:
    """Build transition matrix from execution traces."""
    result = build_matrix()
    print(f"Built matrix: {len(result['skills'])} skills, "
          f"{result['total_transitions']:.0f} transitions from "
          f"{result['total_traces']} traces")
    print(f"Saved to {MATRIX_FILE}")


@app.command(name="predict")
def predict_cmd(
    task: str = typer.Argument(..., help="Task description"),
    start: Optional[list[str]] = typer.Option(None, help="Starting skill(s)"),
    max_length: int = typer.Option(5, help="Maximum chain length"),
) -> None:
    """Predict optimal skill chain."""
    result = predict_chain(
        task,
        start_skills=start,
        max_length=max_length,
    )
    print(json.dumps(result, indent=2))


@app.command()
def gaps(
    task: str = typer.Argument(..., help="Task description"),
    chain: Optional[list[str]] = typer.Option(None, help="Partial known chain"),
) -> None:
    """Detect missing skills."""
    result = detect_missing_skills(task, partial_chain=chain)
    print(json.dumps(result, indent=2))


@app.command()
def sankey() -> None:
    """Export Sankey flow data."""
    result = export_sankey()
    print(json.dumps(result, indent=2))


@app.command(name="status")
def status_cmd() -> None:
    """Matrix health check."""
    result = matrix_status()
    print(json.dumps(result, indent=2))


@app.command(name="task-matrices")
def task_matrices() -> None:
    """Build per-task-type matrices."""
    result = build_task_matrices()
    print(f"Built matrices for {len(result['task_counts'])} task types: "
          f"{', '.join(f'{k}({v})' for k, v in result['task_counts'].items())}")


if __name__ == "__main__":
    app()
