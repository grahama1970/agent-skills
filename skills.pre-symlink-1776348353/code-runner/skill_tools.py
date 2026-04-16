"""Dynamic skill injection for code-runner.

Before writing bespoke code, code-runner checks if an existing skill already
does the job. Relevant skills are injected as callable tools based on task keywords.

Flow:
1. Extract keywords from task prompt
2. Search skills-manifest.json for matches
3. Generate tool definitions for matched skills
4. Inject into tool list for this run
5. LLM calls skill tools like any other tool
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger


# Path to skills manifest (project-level or global)
def _find_manifest() -> Path | None:
    """Find skills-manifest.json in project or global location."""
    candidates = [
        Path(os.environ.get("PROJECT_ROOT", ".")) / ".pi" / "skills-manifest.json",
        Path.home() / ".pi" / "skills-manifest.json",
        Path(__file__).parent.parent.parent / "skills-manifest.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_manifest() -> list[dict]:
    """Load skills from manifest."""
    manifest_path = _find_manifest()
    if not manifest_path:
        logger.warning("skills-manifest.json not found")
        return []

    try:
        with open(manifest_path) as f:
            data = json.load(f)
            return data.get("skills", [])
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to load skills manifest: {}", e)
        return []


def _extract_keywords(prompt: str) -> set[str]:
    """Extract relevant keywords from task prompt for skill matching."""
    # Common task-related keywords to look for
    task_keywords = {
        # Visualization
        "chart", "graph", "plot", "figure", "visualization", "diagram",
        "bar", "line", "scatter", "heatmap", "pie",
        # Data
        "analyze", "analytics", "data", "metrics", "statistics",
        "csv", "json", "table", "extract",
        # Media
        "image", "png", "svg", "pdf", "audio", "video",
        # Code quality
        "test", "lint", "format", "review",
        # Documentation
        "document", "readme", "markdown",
    }

    prompt_lower = prompt.lower()
    words = set(prompt_lower.split())

    # Find matches
    found = words & task_keywords

    # Also extract potential skill names (hyphenated words)
    import re
    hyphenated = re.findall(r'\b[a-z]+-[a-z]+(?:-[a-z]+)*\b', prompt_lower)
    found.update(hyphenated)

    return found


def find_relevant_skills(prompt: str, max_skills: int = 5) -> list[dict]:
    """Find skills relevant to the task prompt.

    Returns list of skill dicts with: name, description, has_run_sh
    """
    keywords = _extract_keywords(prompt)
    if not keywords:
        return []

    skills = _load_manifest()
    if not skills:
        return []

    # Score each skill by keyword matches in name + description
    scored = []
    for skill in skills:
        if not skill.get("has_run_sh"):
            continue  # Only skills with run.sh are callable

        name = skill.get("name", "").lower()
        desc = (skill.get("description") or "").lower()

        score = 0
        for kw in keywords:
            if kw in name:
                score += 3  # Name match is strong signal
            if kw in desc:
                score += 1

        if score > 0:
            scored.append((score, skill))

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:max_skills]]


def skill_to_tool_definition(skill: dict) -> dict:
    """Convert a skill to OpenAI tool definition format."""
    name = skill.get("name", "").replace("-", "_")  # OpenAI requires underscore
    description = skill.get("description", f"Run the {skill.get('name')} skill")

    return {
        "type": "function",
        "function": {
            "name": f"skill_{name}",
            "description": f"[SKILL] {description}. Before writing code to do this, use this skill which already implements it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "string",
                        "description": "Command-line arguments to pass to the skill's run.sh",
                    },
                },
                "required": [],
            },
        },
    }


def get_dynamic_tools(prompt: str) -> tuple[list[dict], dict[str, str]]:
    """Get dynamic tool definitions for relevant skills.

    Returns:
        - List of tool definitions (OpenAI format)
        - Dict mapping tool name -> skill name (for execution)
    """
    skills = find_relevant_skills(prompt)

    tools = []
    name_map = {}  # skill_create_figure -> create-figure

    for skill in skills:
        tool_def = skill_to_tool_definition(skill)
        tools.append(tool_def)

        tool_name = tool_def["function"]["name"]
        skill_name = skill.get("name")
        name_map[tool_name] = skill_name

        logger.info("  Injected skill tool: {} -> /{}", tool_name, skill_name)

    return tools, name_map


def execute_skill(skill_name: str, args: str, cwd: str) -> dict:
    """Execute a skill via its run.sh and return result.

    Returns dict with: ok, stdout, stderr, exit_code
    """
    # Find skill directory
    skills_dir = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).parent.parent)))
    skill_path = skills_dir / skill_name / "run.sh"

    # Also check user skills
    user_skill_path = Path.home() / ".claude" / "skills" / skill_name / "run.sh"

    if skill_path.exists():
        run_sh = skill_path
    elif user_skill_path.exists():
        run_sh = user_skill_path
    else:
        return {
            "ok": False,
            "error": f"Skill {skill_name} not found at {skill_path} or {user_skill_path}",
        }

    try:
        result = subprocess.run(
            [str(run_sh)] + (args.split() if args else []),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout for skill execution
        )

        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout[:10000] if result.stdout else "",
            "stderr": result.stderr[:2000] if result.stderr else "",
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"Skill {skill_name} timed out after 120s",
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Failed to execute skill {skill_name}: {e}",
        }
