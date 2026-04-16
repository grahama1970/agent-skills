"""Generate orchestration-ready YAML task files from skills-ci violations.

Reads the skills-ci report.json and produces a YAML plan where each
violation becomes a task with runner: code-runner. Tier 1 violations
(handled by autofix) are excluded. Only Tier 2 violations that code-runner
can fix deterministically are included.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
import yaml
from loguru import logger

app = typer.Typer()

REPORT_PATH = Path("/mnt/storage12tb/media/agents/shared/skills-ci/report.json")

# Tier 1: handled by skills-ci autofix — skip these
_TIER1_RULES = {
    "python.module_docstring",
    "python.requests",
    "python.logging",
    "python.missing_dep",
    "python.hatchling_flat_layout",
    "skills.frontmatter_description",
    "testing.handwritten_tests",
}

# Tier 3: needs human judgment — alert only, don't generate tasks
_TIER3_RULES = {
    "routing.ptc_candidate",       # architectural suggestion
    "routing.composes_phantom",    # may need skill creation
    "testing.no_blind_tests",      # needs test design
}

# Tier 2: code-runner can fix these — generate tasks
_FIX_INSTRUCTIONS: dict[str, str] = {
    "subprocess.venv_leak": (
        "Add env={{k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'}} "
        "to the subprocess.run() or subprocess.Popen() call that references run.sh "
        "or /skills/. Add 'import os' if not present. Do NOT change any other code."
    ),
    "subprocess.stderr_fatal": (
        "Change 'if result.stderr:' to 'if result.returncode != 0:' for error raising. "
        "Add '(rc={{result.returncode}})' to the error message so returncode appears on "
        "the same line as stderr. Keep stderr in the message for context."
    ),
    "subprocess.service_bypass": (
        "Replace the subprocess call to run.sh with a direct httpx call to the service. "
        "Memory service: Unix socket /run/user/1000/embry/memory.sock. "
        "Scillm: http://localhost:4001/v1/chat/completions. "
        "Chutes: http://localhost:8630/batch. "
        "Embedding: http://localhost:8602/embed. "
        "Add 'import httpx' if not present."
    ),
    "subprocess.shell_aql": (
        "Replace inline AQL in the shell script with a call to /memory skill. "
        "Use: .pi/skills/memory/run.sh recall 'query' or search --collection name. "
        "If the AQL is in a sanity.sh test, add '# skills-ci-exempt: shell_aql' comment."
    ),
    "subprocess.raw_aql": (
        "Replace direct ArangoDB AQL execution with /memory HTTP API. "
        "POST /recall, /learn, /search to Unix socket /run/user/1000/embry/memory.sock. "
        "If this is the memory or embedding skill, add to _AQL_EXCEPTIONS in skills-ci scanner."
    ),
    "subprocess.hardcoded_skill_path": (
        "Replace hardcoded absolute path to /home/graham/.../.pi/skills/ with "
        "Path(__file__).resolve().parent.parent / 'skill-name' / 'run.sh' or similar "
        "relative path computation."
    ),
    "python.argparse": (
        "Replace argparse with typer. Convert ArgumentParser to typer.Typer(). "
        "Convert add_argument to typer.Argument/typer.Option. "
        "Convert subparsers to @app.command() pattern."
    ),
    "python.click": (
        "Replace click with typer. Convert @click.command to @app.command. "
        "Convert @click.option to typer.Option. Convert @click.argument to typer.Argument."
    ),
    "python.file_length": (
        "Split the file into two modules. Keep the main entry point / CLI / public API "
        "in the original file. Move helper functions, dataclasses, and utilities to a "
        "new module in the same directory. Update imports. Both files must be under 800 lines."
    ),
    "skills.memory_read_directive": (
        "Add '> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.' "
        "immediately after the frontmatter closing --- with a blank line before and after."
    ),
    "skills.missing_antipatterns": (
        "Add a '## Common Mistakes' section to SKILL.md with 3-5 concrete WRONG/RIGHT "
        "examples. Document actual antipatterns for this skill's domain."
    ),
    "skills.skill_md_bloat": (
        "Move detailed content from SKILL.md to references/ subdirectory. "
        "Keep frontmatter, quick start, and CLI reference. "
        "Extract examples, architecture, detailed docs to separate .md files. "
        "Replace extracted sections with one-line links."
    ),
    "skills.extra_docs": (
        "Move extra .md files from the skill root directory into a docs/ subdirectory. "
        "Update any references to the moved files."
    ),
    "style.thin_init_py": (
        "Condense the __init__.py to under 20 non-blank lines. Collapse verbose "
        "docstrings to single-line, remove redundant __all__ lists, combine imports."
    ),
    "runtime.bare_python_no_uv": (
        "Replace bare 'python3' or 'python' in run.sh with "
        "'uv run --project \"$SCRIPT_DIR\" python'. Remove 'if command -v uv' conditionals."
    ),
    "runtime.run_sh_not_executable": "Run: chmod +x on the run.sh file.",
    "naming.noun_only": (
        "Add the skill name to _NOUN_ALLOWLIST in skills-ci/scanners.py. "
        "These are established skills that won't be renamed."
    ),
    "regex.classifier_pattern": (
        "Add the skill to _REGEX_EXEMPT in skills-ci/quality_scanners.py with a comment "
        "explaining why the regex usage is legitimate pattern matching, not NL classification."
    ),
    "routing.missing_model_flag": (
        "Add a --model CLI option to the skill's typer command. "
        "Default to 'deepseek-ai/DeepSeek-V3'. Pass through to LLM calls."
    ),
    "routing.composes_common": (
        "Add the skill to _COMPOSES_COMMON_ALLOWED in skills-ci/scanners.py."
    ),
    "prompt.inline_prompt": (
        "Extract the inline LLM prompt to a .txt file in prompt-lab/prompts/. "
        "Add a _load_prompt() helper that reads from prompt-lab/prompts/{name}.txt. "
        "Use .format() for variable substitution."
    ),
}


def _violation_to_task(v: dict[str, Any], idx: int) -> dict[str, Any] | None:
    """Convert a single violation to a YAML task dict, or None if not fixable."""
    rule = v["rule"]

    if rule in _TIER1_RULES or rule in _TIER3_RULES:
        return None

    instruction = _FIX_INSTRUCTIONS.get(rule)
    if not instruction:
        return None

    skill = v["skill"]
    path = v["path"]
    filename = Path(path).name

    task_id = f"fix-{idx:03d}-{rule.replace('.', '-')}"
    title = f"[{skill}] {v['message'][:80]}"

    return {
        "id": task_id,
        "title": title,
        "runner": "code-runner",
        "lane": "default",
        "backend": "sonnet",
        "mode": "edit",
        "cwd": str(Path(path).parent),
        "allowlist": [path],
        "max_rounds": 3,
        "prompt": (
            f"Fix this skills-ci violation in {filename}:\n\n"
            f"Rule: {rule}\n"
            f"File: {path}\n"
            f"Message: {v['message']}\n\n"
            f"Instructions: {instruction}\n\n"
            f"IMPORTANT: Read the file first. Make minimal changes. "
            f"Do not modify anything beyond what's needed to fix this violation."
        ),
        "definition_of_done": {
            "command": (
                f"cd /home/graham/workspace/experiments/pi-mono/.pi/skills/skills-ci && "
                f"uv run python skills_ci.py --mode scan 2>&1 | "
                f"grep -c '{rule}.*{skill}'"
            ),
            "assertion": "exit_code == 1",  # grep returns 1 when no match = violation gone
        },
    }


@app.command()
def generate(
    report: str = typer.Option(str(REPORT_PATH), "--report", help="Path to report.json"),
    output: str = typer.Option(None, "--output", "-o", help="Output YAML path"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Print plan without writing"),
) -> None:
    """Generate a fix plan YAML from skills-ci violations."""
    report_path = Path(report)
    if not report_path.exists():
        logger.error(f"Report not found: {report_path}")
        raise typer.Exit(1)

    data = json.loads(report_path.read_text())
    violations = data.get("violations", [])

    # Filter to Tier 2 only
    tasks = []
    tier3_alerts = []
    for i, v in enumerate(violations):
        if v["rule"] in _TIER1_RULES:
            continue
        if v["rule"] in _TIER3_RULES:
            tier3_alerts.append(v)
            continue
        task = _violation_to_task(v, i)
        if task:
            tasks.append(task)

    if not tasks and not tier3_alerts:
        logger.info("No violations to fix. Estate is clean.")
        raise typer.Exit(0)

    date_str = datetime.now().strftime("%Y-%m-%d")
    plan = {
        "plan": f"skills-ci-fix-{date_str}",
        "description": f"Auto-generated fix plan for {len(tasks)} violations ({date_str})",
        "tasks": tasks,
    }

    if dry_run:
        print(yaml.dump(plan, default_flow_style=False, sort_keys=False))
        if tier3_alerts:
            print(f"\n# {len(tier3_alerts)} Tier 3 alerts (human review):")
            for a in tier3_alerts:
                print(f"#   [{a['skill']}] {a['rule']}: {a['message'][:60]}")
        return

    out_path = Path(output) if output else Path(f"0N_FIX_{date_str}.yaml")
    out_path.write_text(yaml.dump(plan, default_flow_style=False, sort_keys=False))
    logger.info(f"Generated {len(tasks)} fix tasks → {out_path}")

    if tier3_alerts:
        logger.warning(f"{len(tier3_alerts)} Tier 3 alerts need human review:")
        for a in tier3_alerts:
            logger.warning(f"  [{a['skill']}] {a['rule']}: {a['message'][:60]}")


if __name__ == "__main__":
    app()
