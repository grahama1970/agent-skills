#!/usr/bin/env python3
"""Machine-parseable skill validator.

Validates a skill directory against rules.yml.
Used by /skills-ci and /skill-lab for automated checks.

Usage:
    python validate_skill.py /path/to/skill
    python validate_skill.py /path/to/skill --json
    python validate_skill.py /path/to/skill --fix  # auto-fix where possible
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from loguru import logger

# ---------------------------------------------------------------------------
# YAML parsing — try ruamel first, fall back to PyYAML, then minimal parser
# ---------------------------------------------------------------------------
try:
    from ruamel.yaml import YAML as _YAML

    def _load_yaml(path: Path) -> dict:
        yaml_loader = _YAML(typ="safe")
        with open(path, encoding="utf-8") as f:
            return yaml_loader.load(f) or {}
except ImportError:
    try:
        import yaml

        def _load_yaml(path: Path) -> dict:
            with open(path) as f:
                return yaml.safe_load(f) or {}
    except ImportError:

        def _load_yaml(path: Path) -> dict:
            """Minimal frontmatter parser — handles simple key: value only."""
            text = path.read_text()
            result: dict = {}
            for line in text.split("\n"):
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    k, v = line.split(":", 1)
                    result[k.strip()] = v.strip()
            return result


RULES_FILE = Path(__file__).parent.parent / "references" / "rules.yml"
VOCAB_FILE = Path(__file__).parent.parent / "references" / "capability_vocabulary.yml"
FRONTMATTER_RE = re.compile(r"\A---\n(?P<frontmatter>.*?)\n---(?:\n|$)", re.DOTALL)
LIVE_RUNTIME_DEPS = {"ask", "dogpile", "memory", "scillm", "surf"}
LIVE_E2E_MARKERS = ("sanity-live.sh", "sanity-e2e.sh", "sanity-webgpt.sh", "scripts/live_e2e.py")
EVAL_FIXTURES = ("fixtures/agentic_eval.json", "fixtures/eval.json")
EVAL_PROVIDER_SKILLS = {"agentic-evals", "eval-skills"}
EVAL_TRIGGER_PROVIDES = {
    "agentic-evaluation",
    "behavioral-testing",
    "progress-tracking",
    "readiness-scoring",
    "skill-evaluation",
    "task-orchestration",
}


def _extract_frontmatter(skill_md: Path) -> dict | None:
    """Extract YAML frontmatter from SKILL.md with strict delimiters."""
    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    frontmatter_text = match.group("frontmatter")
    try:
        import yaml
        parsed = yaml.safe_load(frontmatter_text) or {}
        return parsed if isinstance(parsed, dict) else None
    except ImportError:
        # Minimal parser
        fm: dict = {}
        current_key: str | None = None
        for line in frontmatter_text.strip().split("\n"):
            raw_line = line.rstrip()
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- "):
                # List item — append to last key
                if current_key and isinstance(fm.get(current_key), list):
                    fm[current_key].append(line[2:].strip())
                else:
                    return None
            elif ":" in line and not line.startswith("#"):
                k, v = raw_line.split(":", 1)
                key = k.strip()
                v = v.strip()
                if not key:
                    return None
                if v == "" or v == ">":
                    fm[key] = []
                    current_key = key
                elif v.startswith("[") and v.endswith("]"):
                    items = [item.strip().strip("'\"") for item in v[1:-1].split(",") if item.strip()]
                    fm[key] = items
                    current_key = key
                else:
                    fm[key] = v
                    current_key = key
            else:
                return None
        return fm


def validate_skill(skill_dir: Path, skills_root: Path | None = None) -> list[dict]:
    """Validate a skill directory. Returns list of findings."""
    findings: list[dict] = []
    skill_dir = Path(skill_dir).resolve()

    if skills_root is None:
        skills_root = skill_dir.parent

    def _add(rule_id: str, severity: str, message: str):
        findings.append({
            "rule": rule_id,
            "severity": severity,
            "message": message,
            "skill": skill_dir.name,
        })

    # --- Structure checks ---
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        _add("STRUCT", "error", "Missing SKILL.md")
        return findings

    fm = _extract_frontmatter(skill_md)

    if (skill_dir / "CHANGELOG.md").exists():
        _add("STRUCT", "warning", "Has CHANGELOG.md (anti-pattern)")
    if (skill_dir / "README.md").exists():
        # README.md is allowed for skills that declare `provides:` (composable primitives)
        if not fm or not fm.get("provides"):
            _add("STRUCT", "info", "Has README.md (allowed for provides: skills, consider if needed)")

    # --- Frontmatter checks ---
    if fm is None:
        _add("FM001", "error", "No valid YAML frontmatter found (must use standalone --- delimiters)")
        return findings

    if fm.get("name") != skill_dir.name:
        _add("FM001", "error", f"name '{fm.get('name')}' != dir '{skill_dir.name}'")

    if "description" not in fm:
        _add("FM002", "error", "Missing description field")

    # --- Composition checks ---
    provides = fm.get("provides")
    if provides is None:
        _add("FM003", "error", "Missing provides: field")
    elif not isinstance(provides, list):
        _add("FM003", "error", "provides: must be a list")

    composes = fm.get("composes")
    if composes is None:
        _add("FM004", "error", "Missing composes: field")
    elif not isinstance(composes, list):
        _add("FM004", "error", "composes: must be a list")
    elif skills_root:
        for dep in composes:
            dep_dir = skills_root / dep
            if not dep_dir.exists():
                _add("COMP001", "warning", f"composes '{dep}' not found in {skills_root}")

    # --- Circular composition check ---
    if isinstance(composes, list) and skill_dir.name in composes:
        _add("COMP002", "error", f"Self-referential composition: {skill_dir.name}")

    if isinstance(composes, list):
        live_deps = sorted(set(composes) & LIVE_RUNTIME_DEPS)
        if len(live_deps) >= 3 and not any((skill_dir / marker).exists() for marker in LIVE_E2E_MARKERS):
            _add(
                "LIVE001",
                "error",
                "Composite runtime skill composes "
                f"{', '.join(live_deps)} but has no opt-in live E2E gate "
                "(expected sanity-live.sh, sanity-e2e.sh, sanity-webgpt.sh, or scripts/live_e2e.py)",
            )

    # --- Vocabulary check ---
    if isinstance(provides, list) and VOCAB_FILE.exists():
        try:
            vocab = _load_yaml(VOCAB_FILE)
            known = set(vocab.get("capabilities", {}).keys())
            for cap in provides:
                if cap not in known:
                    _add("COMP003", "warning", f"provides '{cap}' not in capability vocabulary")
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    # --- Content checks ---
    text = skill_md.read_text()
    line_count = len(text.split("\n"))
    if line_count > 500:
        _add("CONT002", "warning", f"SKILL.md has {line_count} lines (max 500)")

    # --- Agentic evaluation posture ---
    provides_list = provides if isinstance(provides, list) else []
    composes_list = composes if isinstance(composes, list) else []
    requires_eval = (
        fm.get("runtime_self_improvement") == "substantial"
        or (skill_dir / "run.sh").exists()
        or (skill_dir / "sanity.sh").exists()
        or bool(composes_list)
        or bool(set(provides_list) & EVAL_TRIGGER_PROVIDES)
    )
    has_eval_posture = (
        skill_dir.name in EVAL_PROVIDER_SKILLS
        or any((skill_dir / fixture).exists() for fixture in EVAL_FIXTURES)
        or any(dep in EVAL_PROVIDER_SKILLS for dep in composes_list)
        or "eval_not_required" in fm
        or "eval_not_required" in text
    )
    if requires_eval and not has_eval_posture:
        _add(
            "EVAL001",
            "warning",
            "Skill has runtime/orchestration surface but no agentic eval posture "
            "(add fixtures/agentic_eval.json, compose/delegate to agentic-evals, "
            "or document eval_not_required)",
        )

    # --- Storage checks ---
    for d in [".venv", "node_modules", "models", "outputs", "logs", "data",
              "weights", "checkpoints", "artifacts", "datasets"]:
        p = skill_dir / d
        if p.exists() and not p.is_symlink():
            _add("STOR002", "warning", f"'{d}' exists but is not a symlink")

    # --- Dotenv check (skip .venv, node_modules, __pycache__) ---
    _SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".git", "models", "data"}
    def _should_skip(p: Path) -> bool:
        return any(part in _SKIP_DIRS for part in p.parts)

    for py_file in skill_dir.rglob("*.py"):
        if _should_skip(py_file.relative_to(skill_dir)):
            continue
        try:
            py_text = py_file.read_text()
        except Exception:
            continue
        if "os.getenv(" in py_text or "os.environ" in py_text:
            if "load_dotenv" not in py_text and "dotenv_helper" not in py_text:
                rel = py_file.relative_to(skill_dir)
                _add("INT004", "error", f"{rel}: uses os.getenv but no dotenv loading")

    return findings


import typer

app = typer.Typer()


@app.command()
def main(
    skill_dir: str = typer.Argument(..., help="Path to skill directory"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    skills_root: str = typer.Option(None, "--skills-root", help="Root of all skills (for composition checks)"),
):
    skill_dir_path = Path(skill_dir).resolve()
    skills_root_path = Path(skills_root).resolve() if skills_root else skill_dir_path.parent

    findings = validate_skill(skill_dir_path, skills_root_path)

    if json_output:
        print(json.dumps(findings, indent=2))
    else:
        errors = [f for f in findings if f["severity"] == "error"]
        warnings = [f for f in findings if f["severity"] == "warning"]

        for f in findings:
            icon = {"error": "FAIL", "warning": "WARN", "info": "INFO"}[f["severity"]]
            print(f"  [{icon}] {f['rule']}: {f['message']}")

        print()
        if errors:
            print(f"Result: FAIL ({len(errors)} errors, {len(warnings)} warnings)")
            raise typer.Exit(code=1)
        elif warnings:
            print(f"Result: PASS with {len(warnings)} warnings")
        else:
            print("Result: PASS")


if __name__ == "__main__":
    app()
