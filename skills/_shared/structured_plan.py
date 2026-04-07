"""Structured orchestration plan helpers for /plan and /orchestrate.

Supports JSON/YAML plan files with explicit subagent-aware execution lanes.

Canonical schema: orchestrate-plan-v1.schema.json (same directory).
Both this file and plan/plan.py MUST stay aligned with that schema.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import typer
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

STRUCTURED_EXTS = {".json", ".yaml", ".yml"}


def is_structured_plan(path: Path) -> bool:
    return path.suffix.lower() in STRUCTURED_EXTS


def load_structured_plan(path: Path) -> dict[str, Any]:
    text = path.read_text()
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(text)
    else:
        if yaml is None:
            raise RuntimeError("PyYAML is required for YAML plan files")
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("Structured plan root must be an object")
    return data


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def summarize_structured_plan(data: dict[str, Any]) -> dict[str, Any]:
    tasks = []
    for task in _as_list(data.get("tasks")):
        if not isinstance(task, dict):
            continue
        dod = task.get("definition_of_done") or {}
        tests = _as_list(task.get("tests"))
        implementation = _as_list(task.get("implementation"))
        tasks.append(
            {
                "id": str(task.get("id", "")),
                "title": str(task.get("title", "")),
                "lane": str(task.get("lane", "")),
                "runner": str(task.get("runner", "")),
                "backend": str(task.get("backend") or task.get("model") or ""),
                "mode": str(task.get("mode", "")),
                "gate": str(task.get("gate", "")),
                "context_boundary": str(task.get("context_boundary", "")),
                "dependencies": [str(x) for x in _as_list(task.get("depends_on"))],
                "has_dod": bool(dod.get("command") and dod.get("assertion")),
                "has_test": bool(tests),
                "command": str(task.get("command") or ""),
                "prompt": str(task.get("prompt") or ""),
                "definition_of_done": dod,
                "tests": tests,
                "implementation": implementation,
                "allowlist": _as_list(task.get("allowlist")),
                "read_context": _as_list(task.get("read_context")),
                "allowlist_optional": bool(task.get("allowlist_optional")),
                "skills": _as_list(task.get("skills")),
                "skill": str(task.get("skill") or ""),
                "skill_command": str(task.get("skill_command") or ""),
                "skill_args": _as_list(task.get("skill_args")),
            }
        )
    return {
        "title": data.get("metadata", {}).get("title") or data.get("title") or "",
        "goal": data.get("metadata", {}).get("goal") or data.get("goal") or "",
        "questions_blockers": [str(x) for x in _as_list(data.get("questions_blockers"))],
        "capability_overlap": [str(x) for x in _as_list(data.get("capability_overlap"))],
        "tasks": tasks,
        "lanes": _as_list(data.get("lanes")),
        "execution": data.get("execution") or {},
    }


def validate_structured_plan(data: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    summary = summarize_structured_plan(data)

    repo_root = str(data.get("repo_root") or "").strip()
    if not repo_root:
        issues.append("Missing repo_root — required absolute path to the repository root")
    elif not Path(repo_root).is_absolute():
        issues.append(f"repo_root must be an absolute path, got: {repo_root}")
    if not summary["title"]:
        issues.append("Missing title/metadata.title")
    if summary["questions_blockers"] and not all(
        str(x).strip().lower() in {"none", "n/a", "no blockers", "no questions"}
        for x in summary["questions_blockers"]
    ):
        issues.append("Questions/blockers not resolved")
    if not summary["capability_overlap"]:
        issues.append("Missing capability_overlap rationale")

    lanes = {str(l.get("id")): l for l in summary["lanes"] if isinstance(l, dict) and l.get("id")}
    if not lanes:
        warnings.append("No lanes defined")

    for task in summary["tasks"]:
        if not task["id"]:
            issues.append("Task missing id")
            continue
        if not task["title"]:
            issues.append(f"Task {task['id']} missing title")
        if not task["runner"]:
            issues.append(f"Task {task['id']} missing runner")
        if not task["mode"] and task["runner"] != "local":
            issues.append(f"Task {task['id']} missing mode")
        if not task["has_dod"]:
            issues.append(f"Task {task['id']} missing definition_of_done")
        if not task["has_test"]:
            warnings.append(f"Task {task['id']} has no tests")
        if task["lane"] and task["lane"] not in lanes:
            issues.append(f"Task {task['id']} references unknown lane '{task['lane']}'")
        if task["runner"] == "subagent-service":
            issues.append(
                f"Task {task['id']} uses deprecated runner 'subagent-service' — "
                "use 'code-runner' (writes files) or 'scillm' (one-shot). "
                "/orchestrate will auto-migrate at runtime but plans should be updated."
            )
        if task["runner"] == "scillm":
            if task["mode"] != "one_shot":
                issues.append(f"Task {task['id']} uses scillm but mode is not one_shot")
            if not task["backend"]:
                issues.append(f"Task {task['id']} uses scillm but has no backend")
        if not task["backend"] and task["runner"] != "local":
            warnings.append(f"Task {task['id']} missing Model (sonnet/opus/codex/gemini/scillm)")
        if task["runner"] == "local" and task["backend"]:
            warnings.append(f"Task {task['id']} is local but also specifies backend")
        if task["runner"] == "local" and not task["command"]:
            issues.append(f"Task {task['id']} uses local runner but has no command")
        if task["runner"] == "skill":
            skill_name = str(task.get("skill") or "")
            if not skill_name:
                issues.append(f"Task {task['id']} uses skill runner but has no 'skill' field")
        if task["runner"] == "scillm":
            has_prompt = bool(task["prompt"] or task["implementation"])
            if not has_prompt:
                issues.append(
                    f"Task {task['id']} uses scillm but has no prompt or implementation"
                )

    return {"valid": not issues, "issues": issues, "warnings": warnings, "summary": summary}


def _markdown_tasks(text: str) -> list[dict[str, Any]]:
    tasks = []
    lines = text.splitlines()
    indices = []
    # Match both formats:
    #   ### Task 1.2: Title
    #   - [ ] **Task 1.2**: Title
    #   - [x] **Task 1.2**: Title
    pattern = re.compile(r"^(?:###\s*Task\s+|[-*]\s*\[[ x]\]\s*\*\*Task\s+)([0-9]+(?:\.[0-9]+)?)\s*[:\*]*\s*[:\*]*\s*(.+?)(?:\*\*)?$")
    for idx, line in enumerate(lines):
        m = pattern.match(line.strip())
        if m:
            indices.append((idx, m.group(1), m.group(2).strip()))
    for pos, (idx, task_id, title) in enumerate(indices):
        end = indices[pos + 1][0] if pos + 1 < len(indices) else len(lines)
        block = lines[idx:end]
        lane = ""
        agent = ""
        backend = ""
        runner = ""
        mode = ""
        deps: list[str] = []
        tests: list[str] = []
        dod_command = ""
        dod_assert = ""
        implementation: list[str] = []
        in_impl = False
        for line in block:
            if "- Parallel:" in line:
                lane = line.split(":", 1)[1].strip()
            if "- Agent:" in line:
                agent = line.split(":", 1)[1].strip()
            if "- Model:" in line:
                backend = line.split(":", 1)[1].strip()
            if "- Backend:" in line:
                backend = line.split(":", 1)[1].strip()
            if "- Runner:" in line:
                runner = line.split(":", 1)[1].strip()
            if "- Mode:" in line and "shadow" not in line.lower():
                mode = line.split(":", 1)[1].strip()
            if "- Dependencies:" in line:
                raw = line.split(":", 1)[1].strip()
                deps = [] if raw.lower() == "none" else [x.strip().replace("Task ", "") for x in raw.split(",")]
            if line.strip().startswith("- **Implementation**"):
                in_impl = True
                continue
            if in_impl:
                if line.strip().startswith("-") and not re.match(r"^\s*\d+\.", line.strip()):
                    in_impl = False
                elif re.match(r"^\s*\d+\.", line.strip()):
                    implementation.append(line.strip())
            if "- **Test**:" in line or line.strip().startswith("- **Test**:"):
                tests.append(line.split(":", 1)[1].strip())
            if "- Command:" in line:
                dod_command = line.split(":", 1)[1].strip()
            if "- Assertion:" in line:
                dod_assert = line.split(":", 1)[1].strip()
        tasks.append({
            "id": task_id,
            "title": title,
            "lane": lane,
            "agent": agent or "general-purpose",
            "runner": runner,
            "backend": backend,
            "mode": mode,
            "context_boundary": "",
            "depends_on": deps,
            "implementation": implementation,
            "tests": tests,
            "definition_of_done": {"command": dod_command, "assertion": dod_assert},
            "command": "",
            "prompt": "",
        })
    return tasks


def _auto_lanes(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Auto-generate lane definitions from Parallel: values in markdown tasks."""
    seen: dict[str, int] = {}
    for task in tasks:
        lane = str(task.get("lane", ""))
        if lane and lane not in seen:
            seen[lane] = len(seen)
    return [{"id": lane_id, "label": f"Wave {lane_id}"} for lane_id in sorted(seen)]


def markdown_to_structured(path: Path) -> dict[str, Any]:
    text = path.read_text()
    title_match = re.search(r"^# Task List:\s*(.+)$", text, re.M)
    goal_match = re.search(r"^\*\*Goal\*\*:\s*(.+)$", text, re.M)
    overlap_match = re.search(r"^## Capability Overlap\n(.*?)(?=^## )", text, re.M | re.S)
    blockers_match = re.search(r"^## Questions/Blockers\n(.*?)(?=^## |^---\s*$)", text, re.M | re.S)
    return {
        "version": 1,
        "kind": "orchestrate-plan",
        "repo_root": str(path.resolve().parent),
        "metadata": {
            "title": title_match.group(1).strip() if title_match else path.stem,
            "goal": goal_match.group(1).strip() if goal_match else "",
            "source_markdown": str(path),
        },
        "execution": {"max_concurrency": 3},
        "capability_overlap": [
            line.strip()[2:] for line in (overlap_match.group(1).splitlines() if overlap_match else []) if line.strip().startswith("- ")
        ],
        "questions_blockers": [
            line.strip()[2:] if line.strip().startswith("- ") else line.strip()
            for line in (blockers_match.group(1).splitlines() if blockers_match else [])
            if line.strip().startswith("- ") or line.strip().lower() == "none"
        ] or ["None"],
        "tasks": (tasks := _markdown_tasks(text)),
        "lanes": _auto_lanes(tasks),
    }


def dump_structured(data: dict[str, Any], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(data, indent=2)
    if yaml is None:
        raise RuntimeError("PyYAML is required for YAML output")
    return yaml.safe_dump(data, sort_keys=False)


def render_markdown_from_structured(data: dict[str, Any]) -> str:
    summary = summarize_structured_plan(data)
    lines = [
        f"# Task List: {summary['title'] or 'Structured Plan'}",
        "",
        f"**Goal**: {summary['goal'] or ''}",
        "",
        "## Capability Overlap",
    ]
    overlap = summary["capability_overlap"] or ["None"]
    lines.extend(f"- {item}" for item in overlap)
    lines.extend(["", "## Questions/Blockers"])
    blockers = summary["questions_blockers"] or ["None"]
    if blockers == ["None"]:
        lines.append("None")
    else:
        lines.extend(f"- {item}" for item in blockers)
    lines.extend(["", "## Tasks", ""])

    tasks = _as_list(data.get("tasks"))
    for task in tasks:
        if not isinstance(task, dict):
            continue
        lines.append(f"### Task {task.get('id', '')}: {task.get('title', '')}")
        lines.append(f"  - Agent: {task.get('agent', 'general-purpose')}")
        if task.get("backend"):
            lines.append(f"  - Model: {task.get('backend')}")
        if task.get("lane"):
            lines.append(f"  - Parallel: {task.get('lane')}")
        deps = ", ".join(str(x) for x in _as_list(task.get("depends_on"))) or "none"
        lines.append(f"  - Dependencies: {deps}")
        if task.get("runner"):
            lines.append(f"  - Runner: {task.get('runner')}")
        if task.get("mode"):
            lines.append(f"  - Mode: {task.get('mode')}")
        if task.get("context_boundary"):
            lines.append(f"  - Context Boundary: {task.get('context_boundary')}")
        lines.append("  - **Implementation**:")
        for idx, item in enumerate(_as_list(task.get("implementation")), 1):
            lines.append(f"    {idx}. {item}")
        tests = _as_list(task.get("tests"))
        if tests:
            lines.append(f"  - **Test**: {tests[0]}")
            for extra in tests[1:]:
                lines.append(f"    - {extra}")
        dod = task.get("definition_of_done") or {}
        lines.append("  - **Definition of Done**:")
        lines.append(f"    - Command: {dod.get('command', '')}")
        lines.append(f"    - Assertion: {dod.get('assertion', '')}")
        lines.append("")
    return "\n".join(lines)


app = typer.Typer(help="Structured orchestration plan helpers for /plan and /orchestrate.")


@app.command()
def validate(file: Path) -> None:
    """Validate a task file (markdown or structured)."""
    if is_structured_plan(file):
        data = load_structured_plan(file)
    else:
        data = markdown_to_structured(file)
    result = validate_structured_plan(data)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["valid"] else 1)


@app.command()
def summary(file: Path) -> None:
    """Print plan summary as JSON."""
    if is_structured_plan(file):
        data = load_structured_plan(file)
    else:
        data = markdown_to_structured(file)
    result = validate_structured_plan(data)
    print(json.dumps(result["summary"], indent=2))


@app.command()
def convert(file: Path, fmt: str = typer.Option("json", "--format", help="Output format: json or yaml")) -> None:
    """Convert markdown task file to structured format."""
    data = markdown_to_structured(file)
    print(dump_structured(data, fmt))


@app.command()
def render(file: Path) -> None:
    """Render a structured plan as markdown."""
    data = load_structured_plan(file) if is_structured_plan(file) else markdown_to_structured(file)
    print(render_markdown_from_structured(data))


if __name__ == "__main__":
    app()
