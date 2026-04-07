#!/usr/bin/env python3
"""Runtime skill composer — chain existing skills to execute a task.

Given a task description, builds a skill pipeline from the capability graph
(using binding affinities and taxonomy multi-hop) and executes it.

This is the "run a reaction" mode — no new skill is created, just
a one-shot pipeline from existing elements.

Usage:
    python composer.py --task "extract this PDF and learn it to memory" --file doc.pdf
    python composer.py --task "research topic and store findings" --args "quantum computing"
    python composer.py --task "..." --dry-run     # show pipeline without executing
    python composer.py --task "..." --json         # output pipeline as JSON
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from scan_soup import scan_soup


# Binding affinity table — empirical co-occurrence patterns
# "hydrogen likes to bond with oxygen"
# Higher weight = stronger bond = more likely to be chained
AFFINITIES: dict[str, list[tuple[str, float]]] = {
    # extraction chain
    "extractor":    [("review-pdf", 0.9), ("memory", 0.8), ("doc2qra", 0.8)],
    "review-pdf":   [("memory", 0.9), ("extractor", 0.9)],
    "doc2qra":      [("memory", 0.9), ("extractor", 0.7), ("taxonomy", 0.6)],

    # research chain
    "dogpile":      [("doc2qra", 0.8), ("memory", 0.8), ("arxiv", 0.7)],
    "arxiv":        [("fetcher", 0.9), ("doc2qra", 0.8), ("memory", 0.7)],
    "brave-search": [("fetcher", 0.7), ("dogpile", 0.6)],
    "fetcher":      [("doc2qra", 0.8), ("extractor", 0.7)],

    # security chain
    "hack":         [("battle", 0.8), ("monitor-security", 0.7), ("memory", 0.6)],
    "battle":       [("hack", 0.8), ("anvil", 0.7), ("memory", 0.6)],
    "anvil":        [("battle", 0.6), ("memory", 0.5)],

    # creation chain
    "prompt-lab":   [("memory", 0.7), ("scillm", 0.8)],
    "gpt-lab":      [("create-gpt", 0.9), ("memory", 0.7), ("scillm", 0.6)],
    "classifier-lab": [("memory", 0.7), ("scillm", 0.7)],

    # orchestration chain
    "plan":         [("orchestrate", 0.9), ("memory", 0.7)],
    "orchestrate":  [("plan", 0.9), ("task-monitor", 0.7), ("memory", 0.6)],

    # knowledge chain
    "memory":       [("taxonomy", 0.7), ("edge-verifier", 0.6)],
    "taxonomy":     [("memory", 0.8), ("edge-verifier", 0.6)],
}


def get_affinities() -> dict[str, list[tuple[str, float]]]:
    """Return merged affinities: learned (if available) overlaid on static.

    Learned affinities from trajectory_distiller take priority when present.
    Static AFFINITIES serve as prior for cold-start and uncovered pairs.
    """
    merged = {k: list(v) for k, v in AFFINITIES.items()}

    try:
        from trajectory_distiller import load_learned_affinities
        learned = load_learned_affinities()
    except ImportError:
        return merged

    if not learned:
        return merged

    for skill, partners in learned.items():
        if skill not in merged:
            merged[skill] = list(partners)
        else:
            # Learned weights override static for the same partner
            static_dict = dict(merged[skill])
            for partner, weight in partners:
                static_dict[partner] = weight
            merged[skill] = sorted(
                static_dict.items(), key=lambda x: -x[1],
            )

    return merged


# Temporal ordering — "A often precedes B"
PRECEDES: dict[str, list[str]] = {
    "extractor":     ["review-pdf", "doc2qra", "memory"],
    "arxiv":         ["fetcher", "doc2qra", "memory"],
    "dogpile":       ["doc2qra", "memory"],
    "fetcher":       ["doc2qra", "extractor"],
    "doc2qra":       ["memory", "taxonomy"],
    "review-pdf":    ["memory"],
    "hack":          ["battle", "anvil"],
    "plan":          ["orchestrate"],
    "memory":        [],  # terminal — usually last
    "taxonomy":      ["memory"],
    "normalize":     ["extractor", "doc2qra"],
}


def _recall_known_composition(task: str) -> dict | None:
    """Check /memory for known successful compositions matching this task."""
    try:
        from scan_soup import _memory_recall
        items = _memory_recall(task, scope="skill_registry", k=3, threshold=0.4)
        for item in items:
            try:
                data = json.loads(item.get("solution", "{}"))
                if data.get("chain"):
                    return data
            except (json.JSONDecodeError, TypeError):
                continue
    except ImportError:
        pass
    return None


def _store_successful_chain(task: str, skills: list[str], latency_ms: float) -> None:
    """Store a successful chain in /memory for future reuse."""
    try:
        from scan_soup import _memory_learn
    except ImportError:
        return
    chain_str = " → ".join(skills)
    _memory_learn(
        problem=f"successful chain for: {task}",
        solution=json.dumps({
            "chain": skills,
            "chain_str": chain_str,
            "latency_ms": round(latency_ms, 1),
            "task": task,
        }),
        tags=["composition", "successful_chain"]
             + [f"skill:{s}" for s in skills],
    )


def build_pipeline(task: str, graph: dict, extra_args: dict | None = None) -> list[dict]:
    """Build an ordered skill pipeline for a task.

    Uses:
    1. /memory recall for known successful compositions
    2. Capability matching (from gap_detector)
    3. Binding affinities (empirical co-occurrence)
    4. Temporal ordering (precedes relationships)
    """
    # Check /memory for known successful compositions
    known = _recall_known_composition(task)
    if known:
        print(f"  /memory suggests: {known.get('chain_str', '?')}")

    from gap_detector import decompose_task

    required_caps = decompose_task(task)

    # Find skills that provide required capabilities
    needed_skills: dict[str, dict] = {}
    for cap in required_caps:
        providers = graph.get("capabilities", {}).get(cap, [])
        if providers:
            skill_name = providers[0]  # Best provider
            if skill_name not in needed_skills:
                needed_skills[skill_name] = {
                    "skill": skill_name,
                    "capabilities": [],
                    "path": graph["skills"].get(skill_name, {}).get("path", ""),
                }
            needed_skills[skill_name]["capabilities"].append(cap)

    if not needed_skills:
        return []

    # Topological sort using precedes relationships
    ordered = _topological_sort(list(needed_skills.keys()))

    # Build pipeline steps
    pipeline = []
    for skill_name in ordered:
        info = needed_skills.get(skill_name)
        if not info:
            continue
        step = {
            "skill": skill_name,
            "capabilities": info["capabilities"],
            "path": info["path"],
            "run_cmd": _build_run_cmd(skill_name, info["capabilities"], extra_args),
            "affinities": _get_affinities(skill_name, ordered),
        }
        pipeline.append(step)

    return pipeline


def _topological_sort(skills: list[str]) -> list[str]:
    """Sort skills by temporal ordering (precedes relationships)."""
    # Build adjacency from PRECEDES
    in_degree: dict[str, int] = {s: 0 for s in skills}
    adj: dict[str, list[str]] = {s: [] for s in skills}

    for s in skills:
        successors = PRECEDES.get(s, [])
        for succ in successors:
            if succ in in_degree:
                adj[s].append(succ)
                in_degree[succ] += 1

    # Kahn's algorithm
    queue = [s for s in skills if in_degree[s] == 0]
    result = []
    while queue:
        # Pick the one with highest affinity to already-ordered skills
        queue.sort(key=lambda s: -_affinity_score(s, result))
        node = queue.pop(0)
        result.append(node)
        for succ in adj.get(node, []):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # Add any remaining (cycles)
    for s in skills:
        if s not in result:
            result.append(s)

    return result


def _affinity_score(skill: str, ordered: list[str]) -> float:
    """Score how well a skill bonds with already-ordered skills."""
    if not ordered:
        return 0.0
    affinities = get_affinities().get(skill, [])
    score = 0.0
    for partner, weight in affinities:
        if partner in ordered:
            score += weight
    return score


def _get_affinities(skill: str, pipeline: list[str]) -> list[dict]:
    """Get binding affinities for a skill within the pipeline."""
    result = []
    for partner, weight in get_affinities().get(skill, []):
        if partner in pipeline:
            result.append({"skill": partner, "weight": weight})
    return result


def _build_run_cmd(skill: str, capabilities: list[str], extra_args: dict | None = None) -> str:
    """Build the run.sh command for a skill step."""
    # Simple heuristic — map capability to subcommand
    cmd = f"run.sh"
    if extra_args:
        file_arg = extra_args.get("file", "")
        query_arg = extra_args.get("query", extra_args.get("args", ""))
        if file_arg:
            cmd += f" --file {file_arg}"
        if query_arg:
            cmd += f" {query_arg}"
    return cmd


def execute_pipeline(pipeline: list[dict], dry_run: bool = False) -> list[dict]:
    """Execute the pipeline steps sequentially.

    Each step's stdout is captured to a temp file and passed to the next step
    via --pipeline-input <file> arg and PIPELINE_PREV_OUTPUT env var.
    Skills that don't support these simply ignore them.

    After execution, logs bidirectional traces for bond prediction training.
    """
    import tempfile
    import shutil
    from bond_predictor import log_execution_trace

    results = []
    chain_skills = [step["skill"] for step in pipeline]
    pipeline_start = time.time()

    # Create temp dir for inter-step data piping
    run_id = int(time.time())
    pipeline_dir = Path(tempfile.mkdtemp(prefix=f"pipeline_{run_id}_"))
    prev_output_file: Path | None = None

    try:
        for i, step in enumerate(pipeline):
            skill = step["skill"]
            path = step["path"]
            run_sh = Path(path) / "run.sh" if path else None

            print(f"[{i+1}/{len(pipeline)}] {skill} ({', '.join(step['capabilities'])})")

            if dry_run:
                results.append({"skill": skill, "status": "dry_run"})
                continue

            if not run_sh or not run_sh.exists():
                print(f"  SKIP: {skill}/run.sh not found")
                results.append({"skill": skill, "status": "skip", "reason": "no run.sh"})
                continue

            # Build command with pipeline input from previous step
            cmd = [str(run_sh)] + step.get("run_cmd", "").split()[1:]
            if prev_output_file and prev_output_file.exists():
                cmd.extend(["--pipeline-input", str(prev_output_file)])

            # Environment: pass previous output path
            env = dict(os.environ)
            if prev_output_file and prev_output_file.exists():
                env["PIPELINE_PREV_OUTPUT"] = str(prev_output_file)

            # Output file for this step
            step_output_file = pipeline_dir / f"step_{i}_output.txt"

            # Execute
            start = time.time()
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=300,
                    cwd=str(run_sh.parent),
                    env=env,
                )
                elapsed = time.time() - start
                status = "ok" if result.returncode == 0 else "error"
                print(f"  {status} ({elapsed:.1f}s)")

                # Write stdout for next step to consume
                step_output_file.write_text(result.stdout)
                prev_output_file = step_output_file

                results.append({
                    "skill": skill,
                    "status": status,
                    "returncode": result.returncode,
                    "elapsed_s": round(elapsed, 1),
                    "stdout_lines": len(result.stdout.split("\n")),
                    "output_file": str(step_output_file),
                })
            except subprocess.TimeoutExpired:
                print(f"  TIMEOUT (300s)")
                results.append({"skill": skill, "status": "timeout"})
                prev_output_file = None  # No output to pipe
            except Exception as e:
                print(f"  ERROR: {e}")
                results.append({"skill": skill, "status": "error", "error": str(e)})
                prev_output_file = None

        # Log execution traces (bidirectional) for bond prediction training
        if not dry_run and len(chain_skills) >= 2:
            pipeline_elapsed_ms = (time.time() - pipeline_start) * 1000
            all_ok = all(r.get("status") == "ok" for r in results if r.get("status") != "dry_run")
            error_msg = ""
            if not all_ok:
                failed = [r for r in results if r.get("status") not in ("ok", "dry_run")]
                if failed:
                    error_msg = f"step_failed:{failed[0].get('skill', '?')}"
            log_execution_trace(
                skills=chain_skills,
                success=all_ok,
                latency_ms=pipeline_elapsed_ms,
                error=error_msg,
            )

            # Store successful chains in /memory for future reuse
            if all_ok:
                task_desc = os.environ.get("PIPELINE_TASK", "")
                if task_desc:
                    _store_successful_chain(task_desc, chain_skills, pipeline_elapsed_ms)
    finally:
        # Clean up temp dir
        shutil.rmtree(pipeline_dir, ignore_errors=True)

    return results


def _optimize_pipeline(pipeline: list[dict], graph: dict, prediction: dict) -> list[dict] | None:
    """Attempt to find a shorter equivalent chain by removing redundant skills.

    Strategy:
    1. Remove skills whose capabilities are subsets of other skills in the chain
    2. Check if attractor compositions offer a simpler path
    """
    if len(pipeline) <= 2:
        return None  # Can't optimize a 2-step chain

    # Try removing each non-terminal skill and check if capabilities are still covered
    all_caps = set()
    for step in pipeline:
        all_caps.update(step.get("capabilities", []))

    best = None
    for i in range(len(pipeline)):
        candidate = [s for j, s in enumerate(pipeline) if j != i]
        candidate_caps = set()
        for step in candidate:
            candidate_caps.update(step.get("capabilities", []))
        if candidate_caps >= all_caps:
            # All capabilities still covered — this skill was redundant
            if best is None or len(candidate) < len(best):
                best = candidate

    return best


import typer
from typing import Optional

app = typer.Typer(help="Compose and run skill pipeline")


@app.callback(invoke_without_command=True)
def main(
    task: str = typer.Option(..., help="Task description"),
    skills_root: Optional[str] = typer.Option(None, help="Root of skills directory"),
    file: Optional[str] = typer.Option(None, help="File argument to pass to skills"),
    args: Optional[str] = typer.Option(None, help="Additional arguments"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show pipeline without executing"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    execute: bool = typer.Option(False, help="Actually execute the pipeline"),
    optimize: bool = typer.Option(False, help="Attempt to find shorter equivalent chain"),
) -> None:
    """Compose and run skill pipeline."""
    root = Path(skills_root) if skills_root else Path(__file__).parent.parent.parent
    graph = scan_soup(root)

    extra_args = {}
    if file:
        extra_args["file"] = file
    if args:
        extra_args["args"] = args

    pipeline = build_pipeline(task, graph, extra_args or None)

    # Compute elegance scoring for the pipeline
    skills_list = [s["skill"] for s in pipeline]
    elegance_info = None
    if len(skills_list) >= 2:
        from bond_predictor import predict_chain_success, build_runner
        runner = build_runner()
        prediction = predict_chain_success(skills_list, graph, runner)
        elegance_info = prediction.get("elegance", {})

        # Always-on: auto-optimize chains >=3 skills with bloated/wasteful grade
        should_optimize = optimize or (
            len(pipeline) >= 3
            and elegance_info.get("grade") in ("bloated", "wasteful")
        )
        if should_optimize and elegance_info.get("grade") in ("bloated", "wasteful"):
            optimized = _optimize_pipeline(pipeline, graph, prediction)
            if optimized and len(optimized) < len(pipeline):
                opt_skills = [s["skill"] for s in optimized]
                opt_prediction = predict_chain_success(opt_skills, graph, runner)
                opt_elegance = opt_prediction.get("elegance", {})
                if opt_elegance.get("elegance_score", 0) > elegance_info.get("elegance_score", 0):
                    print(f"Optimization: {len(pipeline)} steps → {len(optimized)} steps")
                    print(f"  Original:  {elegance_info.get('grade', '?')} ({elegance_info.get('elegance_score', 0):.3f})")
                    print(f"  Optimized: {opt_elegance.get('grade', '?')} ({opt_elegance.get('elegance_score', 0):.3f})")
                    print()
                    pipeline = optimized
                    skills_list = opt_skills
                    elegance_info = opt_elegance
                    prediction = opt_prediction

    if json_output:
        out = [s.copy() for s in pipeline]
        if elegance_info:
            result = {"pipeline": out, "elegance": elegance_info}
        else:
            result = {"pipeline": out}
        print(json.dumps(result, indent=2))
    elif execute or dry_run:
        print(f"Task: {task}")
        print(f"Pipeline: {' → '.join(s['skill'] for s in pipeline)}")
        if elegance_info:
            print(f"Elegance: {elegance_info.get('elegance_score', 0):.3f} ({elegance_info.get('grade', '?')})")
        print()
        os.environ["PIPELINE_TASK"] = task
        results = execute_pipeline(pipeline, dry_run=dry_run)
        print()
        ok = sum(1 for r in results if r["status"] in ("ok", "dry_run"))
        print(f"Result: {ok}/{len(results)} steps succeeded")
    else:
        # Default: show the pipeline
        print(f"Task: {task}")
        print(f"Pipeline: {len(pipeline)} steps")
        if elegance_info:
            print(f"Elegance: {elegance_info.get('elegance_score', 0):.3f} ({elegance_info.get('grade', '?')})")
        print()
        for i, step in enumerate(pipeline):
            affinities = step.get("affinities", [])
            bonds = ", ".join(f"{a['skill']}({a['weight']:.1f})" for a in affinities)
            print(f"  {i+1}. {step['skill']}")
            print(f"     Capabilities: {', '.join(step['capabilities'])}")
            if bonds:
                print(f"     Bonds: {bonds}")
            print()

        print(f"Chain: {' → '.join(s['skill'] for s in pipeline)}")
        print()
        print("To execute: ./run.sh run --task '...' --execute")
        print("To preview: ./run.sh run --task '...' --dry-run")


if __name__ == "__main__":
    app()
