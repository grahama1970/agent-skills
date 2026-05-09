"""DAG loading and rendering helpers for /plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sys

sys.path.append(str(Path(__file__).resolve().parents[3]))
from _shared.structured_plan import (  # type: ignore  # noqa: E402
    is_structured_plan,
    load_structured_plan,
    markdown_to_structured,
    summarize_structured_plan,
)


def load_dag(filepath: Path) -> tuple[dict[str, Any], list[dict], dict[str, dict], dict[str, list[str]], list[list[str]], list[str]]:
    """Load a plan and compute DAG structure."""
    if is_structured_plan(filepath):
        data = load_structured_plan(filepath)
    else:
        data = markdown_to_structured(filepath)

    summary = summarize_structured_plan(data)
    tasks = summary.get("tasks", [])
    task_map = {t["id"]: t for t in tasks}
    indegree: dict[str, int] = {}
    children: dict[str, list[str]] = {t["id"]: [] for t in tasks}
    for task in tasks:
        deps = [dep for dep in (task.get("dependencies") or []) if dep in task_map]
        indegree[task["id"]] = len(deps)
        for dep in deps:
            children[dep].append(task["id"])

    waves: list[list[str]] = []
    remaining = dict(indegree)
    executed: set[str] = set()
    while True:
        ready = [task_id for task_id, deg in remaining.items() if deg == 0 and task_id not in executed]
        if not ready:
            break
        waves.append(sorted(ready))
        for task_id in ready:
            executed.add(task_id)
            del remaining[task_id]
            for child in children.get(task_id, []):
                if child in remaining:
                    remaining[child] -= 1

    orphans = [task_id for task_id in indegree if task_id not in executed]
    return summary, tasks, task_map, children, waves, orphans


def visualize_dag(filepath: Path) -> None:
    """Print the execution DAG showing waves, parallelism, and task routing."""
    summary, tasks, task_map, children, waves, orphans = load_dag(filepath)
    execution = summary.get("execution", {})
    max_conc = execution.get("max_concurrency", 1)

    if not tasks:
        print("No tasks found.")
        return

    title = summary.get("title") or filepath.stem
    goal = summary.get("goal") or ""
    print(f"DAG: {title}")
    if goal:
        print(f"Goal: {goal}")
    print(f"Tasks: {len(tasks)}  Waves: {len(waves)}  Max concurrency: {max_conc}")
    print()

    for i, wave in enumerate(waves):
        parallel = len(wave) > 1
        wave_label = f"Wave {i}" + (" (parallel)" if parallel else "")
        print(f"── {wave_label} {'─' * (50 - len(wave_label))}")
        for task_id in wave:
            task = task_map[task_id]
            runner = task.get("runner") or "?"
            backend = task.get("backend") or ""
            lane = task.get("lane") or ""
            deps = task.get("dependencies") or []
            title_str = task.get("title") or ""
            icon = {"local": "sh", "scillm": "llm", "code-runner": "cr"}.get(runner, "?")
            dep_str = f" ← [{', '.join(deps)}]" if deps else ""
            model_str = f" ({backend})" if backend else ""
            lane_str = f" L{lane}" if lane else ""
            print(f"  [{icon}] Task {task_id}: {title_str[:45]}{model_str}{lane_str}{dep_str}")
        print()

    if orphans:
        print(f"⚠ CYCLE DETECTED — these tasks can never execute: {', '.join(orphans)}")
        print()

    print("── Edges ──────────────────────────────────────────────")
    has_edges = False
    for task in tasks:
        deps = [dep for dep in (task.get("dependencies") or []) if dep in task_map]
        if deps:
            has_edges = True
            for dep in deps:
                print(f"  {dep} → {task['id']}")
    if not has_edges:
        print("  (no dependencies — all tasks are independent)")
    print()

    lanes_used: dict[str, list[str]] = {}
    for task in tasks:
        lane = task.get("lane") or "default"
        lanes_used.setdefault(lane, []).append(task["id"])
    if len(lanes_used) > 1:
        print("── Lanes (1 Docker container each) ─────────────────────")
        for lane_id in sorted(lanes_used):
            task_ids = lanes_used[lane_id]
            print(f"  Lane {lane_id}: {' → '.join(task_ids)} (sequential within lane)")
        print()


def visualize_mermaid(filepath: Path) -> None:
    """Print the execution DAG as a Mermaid flowchart for external docs."""
    summary, tasks, task_map, children, waves, orphans = load_dag(filepath)
    del children, orphans

    if not tasks:
        print("No tasks found.")
        return

    title = summary.get("title") or filepath.stem
    lines = ["---", f"title: {title}", "---", "flowchart TD"]
    lines.append("    classDef sh fill:#2d4a3e,stroke:#4ade80,color:#fff")
    lines.append("    classDef llm fill:#4a2d4a,stroke:#c084fc,color:#fff")
    lines.append("    classDef agent fill:#2d3a4a,stroke:#60a5fa,color:#fff")
    lines.append("")

    for i, wave in enumerate(waves):
        parallel = len(wave) > 1
        label = f"Wave {i}" + (" ∥" if parallel else "")
        lines.append(f"    subgraph W{i}[\"{label}\"]")
        for task_id in wave:
            task = task_map[task_id]
            backend = task.get("backend") or ""
            title_str = (task.get("title") or "")[:40]
            safe_title = title_str.replace('"', "'").replace("(", "").replace(")", "")
            model_tag = f" [{backend}]" if backend else ""
            node_id = f"T{task_id.replace('.', '_')}"
            lines.append(f"        {node_id}[\"{task_id}: {safe_title}{model_tag}\"]")
        lines.append("    end")
        lines.append("")

    for task in tasks:
        deps = [dep for dep in (task.get("dependencies") or []) if dep in task_map]
        for dep in deps:
            src = f"T{dep.replace('.', '_')}"
            dst = f"T{task['id'].replace('.', '_')}"
            lines.append(f"    {src} --> {dst}")

    lines.append("")
    for task in tasks:
        runner = task.get("runner") or ""
        cls = {"local": "sh", "scillm": "llm", "code-runner": "cr"}.get(runner)
        if cls:
            node_id = f"T{task['id'].replace('.', '_')}"
            lines.append(f"    class {node_id} {cls}")

    print("\n".join(lines))

