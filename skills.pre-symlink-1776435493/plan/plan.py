#!/usr/bin/env python3
"""
Plan Skill - Create orchestration-ready YAML task files.

Outputs structured YAML plans that /orchestrate executes directly via
structured_execute.py. No markdown intermediate — YAML is the source of truth.

Key principles:
- Planner-Executor-Verifier loop: separate planning from execution and verification
- Task graph (DAG) over flat lists: represent dependencies explicitly
- Stop when testable: decompose until each task has a concrete test
- Definition of Done per node: exact pass criteria, expected artifacts
- Every task declares runner, backend, mode — no guessing at execution time
"""

from __future__ import annotations
import os

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
import yaml
from loguru import logger

sys.path.append(str(Path(__file__).resolve().parents[1]))
from _shared.structured_plan import (  # type: ignore
    dump_structured,
    is_structured_plan,
    load_structured_plan,
    markdown_to_structured,
    render_markdown_from_structured,
    summarize_structured_plan,
    validate_structured_plan,
)

SKILLS_DIR = Path(__file__).parent.parent

from design_pipeline import detect_plan_type  # noqa: E402


# ---------------------------------------------------------------------------
# Structured Plan Dataclasses
# Canonical schema: _shared/orchestrate-plan-v1.schema.json
# Both plan.py and structured_plan.py MUST stay aligned with that schema.
# ---------------------------------------------------------------------------


@dataclass
class DefinitionOfDone:
    """Concrete verification for a task."""
    command: str = ""
    assertion: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"command": self.command, "assertion": self.assertion}


@dataclass
class Task:
    """A single task in the structured plan.

    Matches the schema that structured_execute.py consumes:
    - runner: how the task runs (local, code-runner, scillm). subagent-service is deprecated.
    - backend: which LLM model (sonnet, opus, codex, gemini)
    - mode: execution style (iterative, one_shot, review)
    - lane: parallel group (tasks in same lane run sequentially)
    - skills: skill names whose SKILL.md gets compiled into code-runner context
    """
    id: str
    title: str
    lane: str = "0"
    runner: str = ""  # auto-routed if empty — see _suggest_runner()
    backend: str = ""
    mode: str = ""
    agent: str = "general-purpose"
    depends_on: list[str] = field(default_factory=list)
    implementation: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    definition_of_done: DefinitionOfDone = field(default_factory=DefinitionOfDone)
    command: str = ""
    prompt: str = ""
    context_boundary: str = ""
    # code-runner specific fields
    read_context: list[str] = field(default_factory=list)
    blind_tests: list[str] = field(default_factory=list)
    max_rounds: int = 5
    allowlist: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # skill names compiled into context by /orchestrate

    def to_dict(self) -> dict[str, Any]:
        # Auto-route runner/backend/mode if not explicitly set
        runner, backend, mode = suggest_runner(self)
        d: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "lane": self.lane,
            "runner": runner,
            "backend": backend,
            "mode": mode,
            "agent": self.agent,
            "depends_on": self.depends_on,
            "implementation": self.implementation,
            "tests": self.tests,
            "definition_of_done": self.definition_of_done.to_dict(),
        }
        if self.command:
            d["command"] = self.command
        if self.prompt:
            d["prompt"] = self.prompt
        if self.context_boundary:
            d["context_boundary"] = self.context_boundary
        if self.read_context:
            d["read_context"] = self.read_context
        if self.blind_tests:
            d["blind_tests"] = self.blind_tests
        if self.max_rounds != 5:
            d["max_rounds"] = self.max_rounds
        if self.allowlist:
            d["allowlist"] = self.allowlist
        if self.skills:
            d["skills"] = self.skills
        return d


def suggest_runner(task: Task) -> tuple[str, str, str]:
    """Auto-route runner/backend/mode based on task characteristics.

    Returns (runner, backend, mode). Only fills in empty fields.

    Routing heuristic:
      - Has command, no prompt → local (shell command)
      - Has prompt, no allowlist, no DoD with assertion → scillm (one-shot text)
      - Has prompt + allowlist + DoD → code-runner (bounded code task with verification)

    code-runner is EXPENSIVE (worktree, git cycle, multi-round LLM, T0 scoring).
    Only use it when the task genuinely needs iteration and verification.
    """
    runner = task.runner
    backend = task.backend
    mode = task.mode

    if runner:
        # Explicit runner — just fill missing backend/mode
        if runner == "local":
            return runner, "", ""
        if runner == "scillm":
            return runner, backend or "text", mode or "one_shot"
        if runner == "code-runner":
            return runner, backend or "codex", mode or "iterative"
        return runner, backend, mode

    # Auto-route based on task shape
    has_command = bool(task.command)
    has_prompt = bool(task.prompt or task.implementation)
    has_allowlist = bool(task.allowlist)
    has_dod_assertion = bool(task.definition_of_done.assertion) if task.definition_of_done else False

    if has_command and not has_prompt:
        # Pure shell command — local
        return "local", "", ""

    if has_prompt and has_allowlist and has_dod_assertion:
        # Bounded code task with file scope + verification → code-runner
        return "code-runner", backend or "codex", mode or "iterative"

    if has_prompt:
        # Text generation, simple edit, classification → scillm one-shot
        return "scillm", backend or "text", mode or "one_shot"

    # Fallback — command or unknown
    if has_command:
        return "local", "", ""

    return "scillm", backend or "text", mode or "one_shot"


@dataclass
class Lane:
    """Execution lane (wave/parallel group)."""
    id: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label}


@dataclass
class PlanFile:
    """A complete orchestration plan that outputs YAML.

    Supports three plan types:
    - code: standard task decomposition (local + code-runner)
    - design: UI pipeline (/ux-lab → /review-design → /test-interactions → write)
    - hybrid: both code and design tasks
    """
    title: str
    goal: str
    plan_type: str = "code"
    max_concurrency: int = 3
    primary_persona: str = ""
    persona_role: str = ""
    persona_source: str = ""
    capability_overlap: list[str] = field(default_factory=list)
    questions_blockers: list[str] = field(default_factory=lambda: ["None"])
    lanes: list[Lane] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)

    def auto_lanes(self) -> None:
        """Generate lane definitions from task lane values."""
        seen: dict[str, int] = {}
        for task in self.tasks:
            if task.lane not in seen:
                seen[task.lane] = len(seen)
        self.lanes = [
            Lane(id=lane_id, label=f"Wave {lane_id}")
            for lane_id in sorted(seen)
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert to the structured plan dict that /orchestrate consumes."""
        if not self.lanes:
            self.auto_lanes()

        d: dict[str, Any] = {
            "version": 1,
            "kind": "orchestrate-plan",
            "metadata": {
                "title": self.title,
                "goal": self.goal,
                "plan_type": self.plan_type,
                "created": datetime.now().strftime("%Y-%m-%d"),
            },
            "execution": {
                "max_concurrency": self.max_concurrency,
            },
            "capability_overlap": self.capability_overlap or ["None checked"],
            "questions_blockers": self.questions_blockers or ["None"],
            "lanes": [lane.to_dict() for lane in self.lanes],
            "tasks": [task.to_dict() for task in self.tasks],
        }

        if self.primary_persona:
            d["metadata"]["primary_persona"] = {
                "name": self.primary_persona,
                "role": self.persona_role,
                "source": self.persona_source,
            }

        return d

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        return yaml.safe_dump(self.to_dict(), sort_keys=False, default_flow_style=False)

    def write(self, path: Path) -> None:
        """Write plan to a YAML file."""
        path.write_text(self.to_yaml())
        logger.info("Plan written to {}", path)


def _discover_skills(task_title: str, task_body: str) -> list[str]:
    """Auto-discover relevant skills for a task via /recommend-skill-chain.

    Primary: calls recommend-skill-chain with 4-tier cascade.
    Fallback: keyword search in skills-manifest.json.
    """
    recommend_run = SKILLS_DIR / "recommend-skill-chain" / "run.sh"
    task_text = f"{task_title}: {task_body}".strip().rstrip(":")

    if recommend_run.exists() and task_text:
        try:
            result = subprocess.run(
                [str(recommend_run), "recommend", "--task", task_text, "--json", "--limit", "5"],
                capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )
            if result.returncode == 0 and result.stdout.strip():
                payload = json.loads(result.stdout)
                candidates: list[dict] = []
                if isinstance(payload, list):
                    candidates = [c for c in payload if isinstance(c, dict)]
                elif isinstance(payload, dict):
                    for key in ("recommendations", "skills", "results", "chains"):
                        v = payload.get(key)
                        if isinstance(v, list):
                            candidates = [c for c in v if isinstance(c, dict)]
                            if candidates:
                                break
                discovered: list[str] = []
                for c in candidates:
                    conf = float(c.get("confidence", c.get("score", 0)) or 0)
                    if conf <= 0.5:
                        continue
                    name = c.get("skill") or c.get("name") or ""
                    if isinstance(name, str) and name and name not in discovered:
                        discovered.append(name)
                if discovered:
                    return discovered
        except Exception:
            pass

    # Fallback: keyword search in manifest
    manifest_path = SKILLS_DIR.parent / "skills-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
        skills_list = manifest.get("skills", []) if isinstance(manifest, dict) else []
        haystack = f"{task_title} {task_body}".lower()
        found: list[str] = []
        for s in skills_list:
            if not isinstance(s, dict):
                continue
            name = str(s.get("name", "")).strip()
            if name and name.lower() in haystack and name not in found:
                found.append(name)
        return found[:5]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def generate_hidden_tests(task_file_path: Path) -> bool:
    """Spawn test-lab to generate hidden tests for this plan."""
    test_lab_run = SKILLS_DIR / "test-lab" / "run.sh"
    if not test_lab_run.exists():
        logger.warning("test-lab not installed — skipping blind test generation")
        return False
    try:
        result = subprocess.run(
            [str(test_lab_run), "generate", str(task_file_path)],
            capture_output=True, text=True, timeout=60,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            logger.info("Hidden tests generated by test-lab")
        else:
            logger.warning("test-lab generate failed: {}", result.stderr.strip())
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.warning("test-lab generate timed out (60s)")
        return False
    except Exception as e:
        logger.warning("test-lab generate error: {}", e)
        return False


def add_task_to_plan(filepath: Path, task: Task) -> dict[str, Any]:
    """Add a task to an existing YAML plan file.

    - Auto-assigns next ID if task.id is empty
    - Adds lane to lanes list if new
    - Validates after adding
    - Writes back to the same file
    """
    data = load_structured_plan(filepath)

    existing_tasks = data.get("tasks") or []
    existing_ids = {str(t.get("id", "")) for t in existing_tasks if isinstance(t, dict)}

    # Auto-assign ID
    if not task.id or task.id in existing_ids:
        max_int = 0
        for tid in existing_ids:
            try:
                max_int = max(max_int, int(tid.split(".")[-1]))
            except ValueError:
                pass
        task.id = str(max_int + 1)

    # Append task
    existing_tasks.append(task.to_dict())
    data["tasks"] = existing_tasks

    # Ensure lane exists
    lanes = data.get("lanes") or []
    lane_ids = {str(l.get("id", "")) for l in lanes if isinstance(l, dict)}
    if task.lane and task.lane not in lane_ids:
        lanes.append({"id": task.lane, "label": f"Wave {task.lane}"})
        data["lanes"] = lanes

    # Validate
    result = validate_structured_plan(data)

    # Write back
    filepath.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    logger.info("Added task {} to {}", task.id, filepath)

    return {"task_id": task.id, "valid": result["valid"], "issues": result["issues"], "warnings": result["warnings"]}


def remove_task_from_plan(filepath: Path, task_id: str) -> dict[str, Any]:
    """Remove a task from an existing YAML plan and clean up dangling deps."""
    data = load_structured_plan(filepath)

    tasks = data.get("tasks") or []
    before = len(tasks)
    tasks = [t for t in tasks if str(t.get("id", "")) != task_id]
    if len(tasks) == before:
        return {"removed": False, "error": f"Task {task_id} not found"}

    # Remove dangling depends_on references
    for t in tasks:
        deps = t.get("depends_on") or []
        t["depends_on"] = [d for d in deps if str(d) != task_id]

    data["tasks"] = tasks
    result = validate_structured_plan(data)
    filepath.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    logger.info("Removed task {} from {}", task_id, filepath)

    return {"removed": True, "valid": result["valid"], "issues": result["issues"]}


def _load_dag(filepath: Path) -> tuple[dict[str, Any], list[dict], dict[str, dict], dict[str, list[str]], list[list[str]], list[str]]:
    """Load a plan and compute DAG structure. Returns (summary, tasks, task_map, children, waves, orphans)."""
    if is_structured_plan(filepath):
        data = load_structured_plan(filepath)
    else:
        data = markdown_to_structured(filepath)

    summary = summarize_structured_plan(data)
    tasks = summary.get("tasks", [])

    task_map = {t["id"]: t for t in tasks}
    indegree: dict[str, int] = {}
    children: dict[str, list[str]] = {t["id"]: [] for t in tasks}
    for t in tasks:
        deps = [d for d in (t.get("dependencies") or []) if d in task_map]
        indegree[t["id"]] = len(deps)
        for d in deps:
            children[d].append(t["id"])

    # Kahn's algorithm
    waves: list[list[str]] = []
    remaining = dict(indegree)
    executed: set[str] = set()
    while True:
        ready = [tid for tid, deg in remaining.items() if deg == 0 and tid not in executed]
        if not ready:
            break
        waves.append(sorted(ready))
        for tid in ready:
            executed.add(tid)
            del remaining[tid]
            for child in children.get(tid, []):
                if child in remaining:
                    remaining[child] -= 1

    orphans = [tid for tid in indegree if tid not in executed]
    return summary, tasks, task_map, children, waves, orphans


def visualize_dag(filepath: Path) -> None:
    """Print the execution DAG showing waves, parallelism, and task routing."""
    summary, tasks, task_map, children, waves, orphans = _load_dag(filepath)
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
        for tid in wave:
            t = task_map[tid]
            runner = t.get("runner") or "?"
            backend = t.get("backend") or ""
            lane = t.get("lane") or ""
            deps = t.get("dependencies") or []
            title_str = t.get("title") or ""
            icon = {"local": "sh", "scillm": "llm", "code-runner": "cr"}.get(runner, "?")
            dep_str = f" ← [{', '.join(deps)}]" if deps else ""
            model_str = f" ({backend})" if backend else ""
            lane_str = f" L{lane}" if lane else ""
            print(f"  [{icon}] Task {tid}: {title_str[:45]}{model_str}{lane_str}{dep_str}")
        print()

    if orphans:
        print(f"⚠ CYCLE DETECTED — these tasks can never execute: {', '.join(orphans)}")
        print()

    print("── Edges ──────────────────────────────────────────────")
    has_edges = False
    for t in tasks:
        deps = [d for d in (t.get("dependencies") or []) if d in task_map]
        if deps:
            has_edges = True
            for d in deps:
                print(f"  {d} → {t['id']}")
    if not has_edges:
        print("  (no dependencies — all tasks are independent)")
    print()

    lanes_used: dict[str, list[str]] = {}
    for t in tasks:
        lane = t.get("lane") or "default"
        lanes_used.setdefault(lane, []).append(t["id"])
    if len(lanes_used) > 1:
        print("── Lanes (1 Docker container each) ─────────────────────")
        for lane_id in sorted(lanes_used):
            task_ids = lanes_used[lane_id]
            print(f"  Lane {lane_id}: {' → '.join(task_ids)} (sequential within lane)")
        print()


def visualize_mermaid(filepath: Path) -> None:
    """Print the execution DAG as a Mermaid flowchart."""
    summary, tasks, task_map, children, waves, orphans = _load_dag(filepath)

    if not tasks:
        print("No tasks found.")
        return

    title = summary.get("title") or filepath.stem
    lines = [f"---", f"title: {title}", f"---", "flowchart TD"]

    # Style classes for runner types
    lines.append("    classDef sh fill:#2d4a3e,stroke:#4ade80,color:#fff")
    lines.append("    classDef llm fill:#4a2d4a,stroke:#c084fc,color:#fff")
    lines.append("    classDef agent fill:#2d3a4a,stroke:#60a5fa,color:#fff")
    lines.append("")

    # Group tasks into subgraphs by wave
    for i, wave in enumerate(waves):
        parallel = len(wave) > 1
        label = f"Wave {i}" + (" ∥" if parallel else "")
        lines.append(f"    subgraph W{i}[\"{label}\"]")
        for tid in wave:
            t = task_map[tid]
            runner = t.get("runner") or "?"
            backend = t.get("backend") or ""
            title_str = (t.get("title") or "")[:40]
            # Sanitize for Mermaid (no quotes or special chars in node labels)
            safe_title = title_str.replace('"', "'").replace("(", "").replace(")", "")
            model_tag = f" [{backend}]" if backend else ""
            # Node ID must be alphanumeric — replace dots with underscores
            node_id = f"T{tid.replace('.', '_')}"
            lines.append(f"        {node_id}[\"{tid}: {safe_title}{model_tag}\"]")
        lines.append("    end")
        lines.append("")

    # Edges
    for t in tasks:
        deps = [d for d in (t.get("dependencies") or []) if d in task_map]
        for d in deps:
            src = f"T{d.replace('.', '_')}"
            dst = f"T{t['id'].replace('.', '_')}"
            lines.append(f"    {src} --> {dst}")

    lines.append("")

    # Apply classes
    for t in tasks:
        runner = t.get("runner") or ""
        cls = {"local": "sh", "scillm": "llm", "code-runner": "cr"}.get(runner)
        if cls:
            node_id = f"T{t['id'].replace('.', '_')}"
            lines.append(f"    class {node_id} {cls}")

    print("\n".join(lines))


def validate_plan(filepath: Path) -> dict[str, Any]:
    """Validate a plan file (YAML or legacy markdown).

    For YAML: delegates to structured_plan.validate_structured_plan()
    For markdown: converts to structured first, then validates
    """
    if not filepath.exists():
        return {"valid": False, "issues": [f"File not found: {filepath}"], "warnings": []}

    if is_structured_plan(filepath):
        data = load_structured_plan(filepath)
    else:
        data = markdown_to_structured(filepath)

    result = validate_structured_plan(data)

    # Add plan_type to result
    plan_type = (data.get("metadata") or {}).get("plan_type") or "code"
    if not plan_type or plan_type == "code":
        goal = (data.get("metadata") or {}).get("goal") or ""
        if goal:
            plan_type = detect_plan_type(goal)
    result["plan_type"] = plan_type

    return result


def print_validation_report(result: dict[str, Any], filepath: Path) -> None:
    """Print a formatted validation report."""
    print(f"\n{'=' * 60}")
    print(f"Plan Validation: {filepath}")
    print("=" * 60)

    summary = result.get("summary", {})
    tasks = summary.get("tasks", [])
    print(f"\nTasks: {len(tasks)}")
    print(f"Plan type: {result.get('plan_type', 'unknown')}")

    if result["valid"]:
        print("\n[PASS] Plan is ready for /orchestrate")
    else:
        print("\n[FAIL] Plan has blocking issues:")
        for issue in result["issues"]:
            print(f"  - {issue}")

    if result.get("warnings"):
        print("\nWarnings (non-blocking):")
        for warning in result["warnings"]:
            print(f"  - {warning}")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# Interview gates are SKILL.md instructions, not embedded in plan.py.
# The agent calls /interview before writing YAML and after for review.
# interviews.py provides the question definitions for programmatic use.
# from interviews import run_pre_plan_interview, run_post_plan_interview

app = typer.Typer(help="Create orchestration-ready YAML task files")


@app.command()
def main(
    goal: str = typer.Argument(None, help="High-level goal to plan"),
    validate: str = typer.Option(None, "--validate", help="Validate an existing plan file"),
    dag: str = typer.Option(None, "--dag", help="Visualize execution DAG for a plan file"),
    mermaid: str = typer.Option(None, "--mermaid", help="Output execution DAG as Mermaid flowchart"),
    add_task: str = typer.Option(None, "--add-task", help="Add a task to an existing plan (YAML). Provide plan file path."),
    remove_task: str = typer.Option(None, "--remove-task", help="Remove a task by ID from a plan. Format: FILE:TASK_ID"),
    generate_tests: str = typer.Option(None, "--generate-tests", help="Generate blind evaluation tests for a plan"),
    convert: str = typer.Option(None, "--convert", help="Convert markdown task file to YAML"),
    render: str = typer.Option(None, "--render", help="Render structured plan as markdown (for human review)"),
    output: str = typer.Option(None, "-o", "--output", help="Output file (default: stdout)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    output_format: str = typer.Option("yaml", "--format", help="Output format: json or yaml"),
) -> None:
    """Create orchestration-ready YAML task files."""
    if generate_tests:
        filepath = Path(generate_tests)
        if not filepath.exists():
            logger.error("Plan file not found: {}", filepath)
            raise typer.Exit(1)
        ok = generate_hidden_tests(filepath)
        raise typer.Exit(0 if ok else 1)

    if dag:
        filepath = Path(dag)
        if not filepath.exists():
            logger.error("Plan file not found: {}", filepath)
            raise typer.Exit(1)
        visualize_dag(filepath)
        raise typer.Exit(0)

    if mermaid:
        filepath = Path(mermaid)
        if not filepath.exists():
            logger.error("Plan file not found: {}", filepath)
            raise typer.Exit(1)
        visualize_mermaid(filepath)
        raise typer.Exit(0)

    if add_task:
        filepath = Path(add_task)
        if not filepath.exists():
            logger.error("Plan file not found: {}", filepath)
            raise typer.Exit(1)
        # The agent provides task details via the goal argument as YAML-like fields
        # Example: plan.py --add-task plan.yaml "title=Fix auth|runner=subagent-service|backend=sonnet|lane=1|depends_on=2,3"
        if not goal:
            logger.error("Provide task fields as goal argument: 'title=X|runner=Y|backend=Z|lane=N|depends_on=A,B'")
            raise typer.Exit(1)
        fields: dict[str, str] = {}
        for pair in goal.split("|"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                fields[k.strip()] = v.strip()
        new_task = Task(
            id=fields.get("id", ""),
            title=fields.get("title", "Untitled"),
            lane=fields.get("lane", "0"),
            runner=fields.get("runner", ""),  # auto-routed by suggest_runner()
            backend=fields.get("backend", ""),
            mode=fields.get("mode", ""),
            agent=fields.get("agent", "general-purpose"),
            depends_on=[d.strip() for d in fields.get("depends_on", "").split(",") if d.strip()],
            implementation=[s.strip() for s in fields.get("implementation", "").split(";") if s.strip()],
            command=fields.get("command", ""),
            definition_of_done=DefinitionOfDone(
                command=fields.get("dod_command", ""),
                assertion=fields.get("dod_assertion", ""),
            ),
        )
        result = add_task_to_plan(filepath, new_task)
        if json_output:
            print(json.dumps(result, indent=2))
        else:
            print(f"Added task {result['task_id']} to {filepath}")
            if not result["valid"]:
                print("Validation issues:")
                for issue in result["issues"]:
                    print(f"  - {issue}")
        raise typer.Exit(0 if result["valid"] else 1)

    if remove_task:
        if ":" not in remove_task:
            logger.error("Format: --remove-task FILE:TASK_ID")
            raise typer.Exit(1)
        file_str, task_id = remove_task.rsplit(":", 1)
        filepath = Path(file_str)
        if not filepath.exists():
            logger.error("Plan file not found: {}", filepath)
            raise typer.Exit(1)
        result = remove_task_from_plan(filepath, task_id)
        if json_output:
            print(json.dumps(result, indent=2))
        else:
            if result.get("removed"):
                print(f"Removed task {task_id} from {filepath}")
            else:
                print(f"Error: {result.get('error')}")
        raise typer.Exit(0 if result.get("removed") else 1)

    if validate:
        filepath = Path(validate)
        result = validate_plan(filepath)

        if json_output:
            print(json.dumps(result, indent=2))
        else:
            print_validation_report(result, filepath)

        if result["valid"]:
            generate_hidden_tests(filepath)

        raise typer.Exit(0 if result["valid"] else 1)

    if convert:
        filepath = Path(convert)
        if not filepath.exists():
            logger.error("File not found: {}", filepath)
            raise typer.Exit(1)
        if is_structured_plan(filepath):
            structured = load_structured_plan(filepath)
        else:
            structured = markdown_to_structured(filepath)
        rendered = dump_structured(structured, "json" if json_output else output_format)
        if output:
            Path(output).write_text(rendered)
            logger.info("Converted to {}", output)
        else:
            print(rendered)
        raise typer.Exit(0)

    if render:
        filepath = Path(render)
        if not filepath.exists():
            logger.error("File not found: {}", filepath)
            raise typer.Exit(1)
        if not is_structured_plan(filepath):
            logger.error("--render requires a .yaml/.yml/.json plan file")
            raise typer.Exit(1)
        rendered = render_markdown_from_structured(load_structured_plan(filepath))
        if output:
            Path(output).write_text(rendered)
        else:
            print(rendered)
        raise typer.Exit(0)

    if not goal:
        # No goal — emit an empty template for the agent to fill
        template = PlanFile(
            title="<Feature Name>",
            goal="<one-line summary>",
            plan_type="code",
            max_concurrency=3,
            capability_overlap=["<what /memory recall returned>"],
            questions_blockers=["None"],
            lanes=[Lane(id="0", label="Wave 0: Setup"), Lane(id="1", label="Wave 1: Implementation")],
            tasks=[
                Task(
                    id="1",
                    title="<Setup task>",
                    lane="0",
                    runner="local",
                    backend="",
                    mode="",
                    command="<shell command>",
                    definition_of_done=DefinitionOfDone(
                        command="<verification command>",
                        assertion="<what success looks like>",
                    ),
                ),
                Task(
                    id="2",
                    title="<Implementation task>",
                    lane="1",
                    runner="code-runner",
                    backend="codex",
                    mode="iterative",
                    depends_on=["1"],
                    implementation=["Step 1", "Step 2"],
                    tests=["tests/test_feature.py::test_behavior"],
                    definition_of_done=DefinitionOfDone(
                        command="uv run pytest tests/ -q",
                        assertion="All tests pass",
                    ),
                ),
            ],
        )
        print(template.to_yaml())
        raise typer.Exit(0)

    # Goal provided — print planning guidance for the agent
    # NOTE: The /interview gates are SKILL.md instructions, not embedded here.
    # The agent reads SKILL.md and calls /interview before writing YAML.
    # plan.py is a CLI utility — it doesn't drive the conversation.
    plan_type = detect_plan_type(goal)
    print(f"Goal: {goal}")
    print(f"Detected plan type: {plan_type}")
    print(f"\nOutput YAML using the structured plan schema.")
    print(f"Required fields per task: id, title, lane, runner, backend, mode, depends_on, definition_of_done")
    print(f"\nRunner routing (auto-routed if runner field is empty):")
    print(f"  local       — shell commands (setup, tests, scripts). Has command, no prompt.")
    print(f"  scillm      — one-shot LLM (simple edits, classification, extraction). Has prompt, no allowlist/DoD.")
    print(f"  code-runner — ONLY for complex bounded code tasks with DoD verification. Has prompt + allowlist + DoD assertion.")
    print(f"\n  code-runner is EXPENSIVE. Don't use it for mechanical edits, config changes, or simple text generation.")
    print(f"\nBackend models:")
    print(f"  sonnet  — boilerplate, scaffolding, monitoring (low cost)")
    print(f"  opus    — architecture, novel design, cross-skill composition (high cost)")
    print(f"  codex   — code review, refactoring (medium cost)")
    print(f"  gemini  — long content, large context (medium cost)")


if __name__ == "__main__":
    app()
