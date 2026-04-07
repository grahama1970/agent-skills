"""Runtime readiness scanners for skills-ci.

Validates shell syntax, triggers presence, and executable permissions
for skill directories. Each scanner returns a list of Violation objects
following the same pattern as scanners.py.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List

from loguru import logger

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from models import Violation
from scanners import list_skill_dirs, parse_frontmatter


def is_internal_skill(text: str) -> bool:
    """Check if a SKILL.md declares ``internal: true`` in frontmatter.

    Internal skills are infrastructure/build-time tools not invoked by
    humans directly. They are exempt from trigger validation and naming
    convention warnings.
    """
    fm = parse_frontmatter(text)
    if fm is None:
        return False
    return bool(fm.get("internal"))


def _check_shell_syntax(script: Path, skill_name: str) -> List[Violation]:
    """Run ``bash -n`` on a shell script to detect syntax errors."""
    violations: List[Violation] = []
    try:
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
            timeout=10,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # Truncate long error messages
            if len(stderr) > 200:
                stderr = stderr[:200] + "..."
            violations.append(Violation(
                rule="runtime.shell_syntax",
                severity="error",
                skill=skill_name,
                path=str(script),
                message=f"Shell syntax error in {script.name}: {stderr}",
            ))
    except subprocess.TimeoutExpired:
        violations.append(Violation(
            rule="runtime.shell_syntax",
            severity="error",
            skill=skill_name,
            path=str(script),
            message=f"Shell syntax check timed out for {script.name}.",
        ))
    except FileNotFoundError:
        # bash not available -- skip silently
        logger.debug("bash not found; skipping shell syntax check")
    return violations


def _parse_triggers_from_skill_md(text: str) -> List[str]:
    """Extract triggers list from SKILL.md frontmatter.

    Handles YAML list format::

        triggers:
          - phrase one
          - phrase two

    Also handles inline format::

        triggers: [phrase one, phrase two]
    """
    # Find frontmatter boundaries
    if not text.startswith("---\n"):
        return []
    end = text.find("\n---\n", 4)
    if end == -1:
        # Also try end-of-file frontmatter (some files end with ---)
        end = text.find("\n---", 4)
        if end == -1:
            return []

    frontmatter = text[4:end]

    # Find the triggers key
    match = re.search(r"^triggers:\s*(.*)", frontmatter, re.MULTILINE)
    if not match:
        return []

    inline_value = match.group(1).strip()

    # Inline list format: triggers: [a, b, c]
    if inline_value.startswith("["):
        inner = inline_value.strip("[]")
        items = [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
        return items

    # If there's an inline value that's not a list, treat as single trigger
    if inline_value and not inline_value.startswith("#"):
        return [inline_value.strip("'\"")]

    # YAML list format: look for subsequent lines starting with "  - "
    triggers: List[str] = []
    lines = frontmatter.splitlines()
    in_triggers = False
    for line in lines:
        if line.startswith("triggers:"):
            in_triggers = True
            continue
        if in_triggers:
            stripped = line.strip()
            if stripped.startswith("- "):
                trigger_text = stripped[2:].strip().strip("'\"")
                if trigger_text:
                    triggers.append(trigger_text)
            elif stripped == "" or stripped.startswith("#"):
                # Blank lines or comments within the list are OK
                continue
            else:
                # Hit next key -- stop collecting triggers
                break

    return triggers


# Words too generic to be useful as trigger vocabulary.
# Triggers containing ONLY these words will be flagged.
_STOP_WORDS = {
    "run", "do", "make", "this", "that", "it", "the", "a", "an",
    "please", "help", "go", "start", "execute", "use", "get",
}


def _check_triggers(skill_dir: Path) -> List[Violation]:
    """Check that SKILL.md frontmatter has non-empty, high-quality triggers.

    Validates:
    1. Triggers exist (not empty)
    2. Trigger quality: each trigger should be >= 3 words with domain vocabulary
    3. No duplicate triggers across the trigger list

    Skills with ``internal: true`` in frontmatter are exempt.
    """
    violations: List[Violation] = []
    skill_name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        return violations

    try:
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return violations

    if is_internal_skill(text):
        return violations

    triggers = _parse_triggers_from_skill_md(text)

    if not triggers:
        violations.append(Violation(
            rule="runtime.missing_triggers",
            severity="warn",
            skill=skill_name,
            path=str(skill_md),
            message="SKILL.md frontmatter has no triggers — skill is invisible to "
                    "Tier 2/3 discovery and voice control. Add triggers or set "
                    "internal: true if this is infrastructure.",
        ))
        return violations

    # Check trigger quality
    vague_triggers = []
    for trigger in triggers:
        words = trigger.lower().split()
        # Too short — won't disambiguate from other skills
        if len(words) < 3:
            vague_triggers.append(trigger)
            continue
        # All words are stop words — no domain vocabulary
        meaningful = [w for w in words if w not in _STOP_WORDS]
        if not meaningful:
            vague_triggers.append(trigger)

    if vague_triggers:
        violations.append(Violation(
            rule="runtime.vague_triggers",
            severity="warn",
            skill=skill_name,
            path=str(skill_md),
            message=f"Vague triggers will cause false matches in voice/intent "
                    f"pipeline: {vague_triggers}. Each trigger should be >= 3 words "
                    f"with domain-specific vocabulary.",
        ))

    # Check for duplicates
    seen = set()
    dupes = []
    for trigger in triggers:
        normalized = trigger.lower().strip()
        if normalized in seen:
            dupes.append(trigger)
        seen.add(normalized)
    if dupes:
        violations.append(Violation(
            rule="runtime.duplicate_triggers",
            severity="warn",
            skill=skill_name,
            path=str(skill_md),
            message=f"Duplicate triggers waste voice/intent search space: {dupes}",
        ))

    return violations


def _check_executable_bit(skill_dir: Path) -> List[Violation]:
    """Check that run.sh has the executable permission bit set."""
    violations: List[Violation] = []
    skill_name = skill_dir.name
    run_sh = skill_dir / "run.sh"

    if not run_sh.exists():
        return violations

    if not os.access(run_sh, os.X_OK):
        violations.append(Violation(
            rule="runtime.run_sh_not_executable",
            severity="warn",
            skill=skill_name,
            path=str(run_sh),
            message="run.sh is not executable (missing +x permission).",
        ))

    return violations


def _check_read_before_use(skill_dir: Path) -> List[Violation]:
    """Check that read_before_use paths in SKILL.md frontmatter actually exist."""
    violations: List[Violation] = []
    skill_name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        return violations

    try:
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return violations

    fm = parse_frontmatter(text)
    if fm is None:
        return violations

    rbu = fm.get("read_before_use")
    if not isinstance(rbu, list) or not rbu:
        return violations

    for path_str in rbu:
        target = skill_dir / str(path_str)
        # Also check relative to parent (for _shared/ references)
        target_alt = skill_dir.parent / str(path_str)
        if not target.exists() and not target_alt.exists():
            violations.append(Violation(
                rule="runtime.read_before_use_missing",
                severity="warn",
                skill=skill_name,
                path=str(skill_md),
                message=f"read_before_use references '{path_str}' but file not found at {target} or {target_alt}",
            ))

    return violations


def _check_bare_python_in_runsh(skill_dir: Path) -> List[Violation]:
    """Check that run.sh doesn't call bare python3 when pyproject.toml exists.

    If a skill has pyproject.toml (declaring dependencies), all python invocations
    in run.sh MUST use `uv run --project` or activate the .venv. Bare `python3`
    picks up system/~/.local packages which may have incompatible versions.

    The `alias python3='uv run ...'` pattern is acceptable IF shopt expand_aliases
    is set. Direct calls inside nohup/env/xargs don't expand aliases — those must
    use explicit `uv run`.

    Incident: 2026-03-17 anyio version mismatch broke /orchestrate because run.sh
    used bare python3 instead of uv run.
    """
    violations: List[Violation] = []
    skill_name = skill_dir.name
    run_sh = skill_dir / "run.sh"
    pyproject = skill_dir / "pyproject.toml"

    if not run_sh.exists() or not pyproject.exists():
        return violations

    try:
        text = run_sh.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return violations

    has_alias = "alias python3=" in text and "expand_aliases" in text
    lines = text.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments, empty lines, echo/printf (display only)
        if not stripped or stripped.startswith("#"):
            continue
        if any(stripped.startswith(p) for p in ("echo ", "printf ", "alias ")):
            continue

        # Detect bare python3 calls that bypass the alias
        # These are in contexts where aliases don't expand: nohup, env, xargs, $()
        bare_contexts = ["nohup python3", "nohup python ", "env python3", "xargs.*python3"]
        for ctx in bare_contexts:
            if re.search(ctx, stripped):
                violations.append(Violation(
                    rule="runtime.bare_python_nohup",
                    severity="warn",
                    skill=skill_name,
                    path=f"{run_sh}:{i}",
                    message=f"Bare python3 in alias-blind context ({ctx.split()[0]}). Use 'uv run --project' explicitly.",
                ))

        # If no alias, any python3 call is suspect
        if not has_alias and re.search(r'\bpython3?\s+"?\$', stripped):
            # Exclude lines that already use uv run
            if "uv run" not in stripped:
                violations.append(Violation(
                    rule="runtime.bare_python_no_uv",
                    severity="warn",
                    skill=skill_name,
                    path=f"{run_sh}:{i}",
                    message="Bare python3 call without uv run or alias. Deps from pyproject.toml won't be available.",
                ))

    return violations


def _check_docker_compose(skill_dir: Path) -> List[Violation]:
    """Check that skills using 'docker run -d' have a docker-compose.yml.

    Persistent containers should be declared in docker-compose.yml, not buried
    in shell scripts. The compose file is the canonical spec; run.sh handles
    dynamic lifecycle on top of it.
    """
    violations: List[Violation] = []
    skill_name = skill_dir.name
    run_sh = skill_dir / "run.sh"

    if not run_sh.exists():
        return violations

    try:
        text = run_sh.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return violations

    # Only check skills that launch persistent (detached) containers
    if "docker run -d" not in text:
        return violations

    compose_file = skill_dir / "docker-compose.yml"
    if not compose_file.exists():
        violations.append(Violation(
            rule="runtime.docker_no_compose",
            severity="warn",
            skill=skill_name,
            path=str(run_sh),
            message="Uses 'docker run -d' but has no docker-compose.yml. Container specs should be declarative.",
        ))

    return violations


def scan_runtime_readiness(skill_dir: Path) -> List[Violation]:
    """Run all runtime readiness checks on a single skill directory.

    Checks:
    1. Shell syntax validation (bash -n) on run.sh and sanity.sh
    2. Triggers presence in SKILL.md frontmatter
    3. Executable bit on run.sh
    4. read_before_use paths exist
    5. Bare python3 calls when pyproject.toml exists
    6. docker run -d without docker-compose.yml

    Returns a list of Violation objects.
    """
    violations: List[Violation] = []
    skill_name = skill_dir.name

    # 1. Shell syntax validation
    for script_name in ("run.sh", "sanity.sh"):
        script = skill_dir / script_name
        if script.exists():
            violations.extend(_check_shell_syntax(script, skill_name))

    # 2. Triggers validation
    violations.extend(_check_triggers(skill_dir))

    # 3. Executable bit check
    violations.extend(_check_executable_bit(skill_dir))

    # 4. read_before_use validation
    violations.extend(_check_read_before_use(skill_dir))

    # 5. Bare python3 in run.sh
    violations.extend(_check_bare_python_in_runsh(skill_dir))

    # 6. Docker compose check
    violations.extend(_check_docker_compose(skill_dir))

    # 7. Python version pin
    violations.extend(_check_python_version_pin(skill_dir))

    # 8. Loguru version pin
    violations.extend(_check_loguru_version_pin(skill_dir))

    # 9. Venv Python version
    violations.extend(_check_venv_python_version(skill_dir))

    # 10. Venv corruption
    violations.extend(_check_venv_corruption(skill_dir))

    # 11. unset VIRTUAL_ENV
    violations.extend(_check_unset_virtual_env(skill_dir))

    # 12. Claude Code native overlap
    violations.extend(_check_native_overlap(skill_dir))

    return violations


# ---------------------------------------------------------------------------
# Environment health checks (7-11)
# ---------------------------------------------------------------------------


def _check_python_version_pin(skill_dir: Path) -> List[Violation]:
    """Check that pyproject.toml pins Python <3.13."""
    violations: List[Violation] = []
    pyproject = skill_dir / "pyproject.toml"
    if not pyproject.exists():
        return violations
    text = pyproject.read_text()
    match = re.search(r'requires-python\s*=\s*"([^"]+)"', text)
    if not match:
        return violations
    spec = match.group(1)
    if "<3.13" not in spec and "<3.12" not in spec:
        violations.append(Violation(
            rule="runtime.python_version_unbounded",
            severity="error",
            skill=skill_dir.name,
            path=str(pyproject),
            message=f'requires-python = "{spec}" has no upper bound. '
                    f"Pin to <3.13 to avoid loguru/3.13 circular import bugs.",
            fixable=True,
        ))
    return violations


def _check_loguru_version_pin(skill_dir: Path) -> List[Violation]:
    """Check that loguru dependency is pinned <0.7.3."""
    violations: List[Violation] = []
    pyproject = skill_dir / "pyproject.toml"
    if not pyproject.exists():
        return violations
    text = pyproject.read_text()
    if '"loguru' not in text:
        return violations
    if "<0.7.3" not in text:
        violations.append(Violation(
            rule="runtime.loguru_version_unbounded",
            severity="error",
            skill=skill_dir.name,
            path=str(pyproject),
            message="loguru dependency has no upper bound. "
                    "Pin to <0.7.3 to avoid circular import on Python 3.13.",
            fixable=True,
        ))
    return violations


def _check_venv_python_version(skill_dir: Path) -> List[Violation]:
    """Check that the actual venv Python version matches the pin."""
    violations: List[Violation] = []
    venv_python = skill_dir / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return violations
    try:
        result = subprocess.run(
            [str(venv_python), "--version"],
            capture_output=True, text=True, timeout=5,
        )
        version = result.stdout.strip()
        if "3.13" in version:
            violations.append(Violation(
                rule="runtime.venv_python_313",
                severity="error",
                skill=skill_dir.name,
                path=str(venv_python),
                message=f"Venv uses {version} — rebuild with <3.13 pin. "
                        f"Run: rm -rf {skill_dir}/.venv && uv sync",
                fixable=True,
            ))
    except (subprocess.TimeoutExpired, OSError):
        pass
    return violations


_CORRUPTION_SIGS = [b"Auto-generated module docstring"]
_CORRUPTION_LOGURU = b"from loguru import logger"
_LOGURU_LEGITIMATE = {"loguru", "sentry_sdk"}


def _check_venv_corruption(skill_dir: Path) -> List[Violation]:
    """Spot-check venv site-packages for corruption signatures."""
    violations: List[Violation] = []
    for venv_dir in skill_dir.iterdir():
        if not venv_dir.is_dir() or not venv_dir.name.startswith(".venv"):
            continue
        for sp_dir in venv_dir.rglob("site-packages"):
            if not sp_dir.is_dir():
                continue
            checked = 0
            for pyfile in sp_dir.rglob("*.py"):
                if checked >= 20 or "__pycache__" in str(pyfile):
                    continue
                try:
                    content = pyfile.read_bytes()
                except (OSError, PermissionError):
                    continue
                checked += 1
                for sig in _CORRUPTION_SIGS:
                    if sig in content:
                        violations.append(Violation(
                            rule="runtime.venv_corrupted",
                            severity="error",
                            skill=skill_dir.name,
                            path=str(pyfile),
                            message=f"Corruption in site-packages: {sig.decode()!r}. "
                                    f"Run: rm -rf {venv_dir} && uv sync",
                        ))
                        return violations
                if _CORRUPTION_LOGURU in content:
                    pkg = ""
                    try:
                        rel = pyfile.relative_to(sp_dir)
                        pkg = rel.parts[0].split("-")[0].lower() if rel.parts else ""
                    except ValueError:
                        pass
                    if pkg and pkg not in _LOGURU_LEGITIMATE:
                        violations.append(Violation(
                            rule="runtime.venv_corrupted",
                            severity="error",
                            skill=skill_dir.name,
                            path=str(pyfile),
                            message=f"Loguru import in third-party package '{pkg}'. "
                                    f"Run: rm -rf {venv_dir} && uv sync",
                        ))
                        return violations
    return violations


def _check_unset_virtual_env(skill_dir: Path) -> List[Violation]:
    """Check that run.sh starts with 'unset VIRTUAL_ENV'."""
    violations: List[Violation] = []
    run_sh = skill_dir / "run.sh"
    pyproject = skill_dir / "pyproject.toml"
    if not run_sh.exists() or not pyproject.exists():
        return violations
    text = run_sh.read_text()
    if "unset VIRTUAL_ENV" not in text:
        violations.append(Violation(
            rule="runtime.missing_unset_virtual_env",
            severity="error",
            skill=skill_dir.name,
            path=str(run_sh),
            message="run.sh uses Python but doesn't 'unset VIRTUAL_ENV'. "
                    "Inherited VIRTUAL_ENV causes uv to resolve the wrong venv.",
            fixable=True,
        ))
    return violations


# ---------------------------------------------------------------------------
# Deprecation detection (12)
# ---------------------------------------------------------------------------

# Skills that may overlap with Claude Code native capabilities.
# Two categories (per Anthropic Claude Skills 2.0 framework):
#   - CAPABILITY UPLIFT: patches a model gap → deprecated when model improves
#   - WORKFLOW: encodes a process → always relevant
# Format: skill_name → (native_capability, category, reason)
# Run Claude Skills 2.0 A/B benchmark to confirm before deprecating.
# Claude Code native capabilities with their ACTUAL limits.
# Each entry: (tool_name, what_it_can_do, what_it_CANNOT_do)
_CLAUDE_NATIVE: list[tuple[str, list[str], list[str]]] = [
    ("WebFetch", [
        "fetch single URL", "return raw HTML/text",
    ], [
        "JavaScript rendering", "SPA pages", "proxy rotation",
        "PDF extraction", "batch/manifest fetching", "HTTP caching",
        "content extraction pipeline", "rolling window chunking",
        "structured output (JSONL/markdown)", "retry with fallback URLs",
        "rate limit handling", "crawling multiple pages",
    ]),
    ("WebSearch", [
        "web search", "return snippets",
    ], [
        "structured API results", "citation metadata",
        "academic/research-grade search", "premium search features",
        "filtered domain search", "time-range filtering",
        "local search", "business search", "near me",
        "webhook", "monitor", "keyword alert", "notification",
        "memory integration", "graph-memory", "persist",
        "API key", "brave", "perplexity",
    ]),
    ("Bash(gh)", [
        "github search code", "github search issues", "github search PRs",
        "github repo operations", "github API via gh",
    ], [
        "bulk search across orgs", "saved search monitoring",
        "structured result aggregation",
        "multi-strategy", "symbol search", "treesitter", "taxonomy",
        "README extraction", "language breakdown", "repo analysis",
        "path-filtered search", "filename search",
    ]),
]


def _skill_has_capability_beyond_native(
    skill_text: str,
    native_cannot: list[str],
) -> list[str]:
    """Check if the SKILL.md text mentions capabilities the native tool lacks.

    Returns list of beyond-native capabilities found in the skill text.
    """
    text_lower = skill_text.lower()
    found = []
    for capability in native_cannot:
        # Check for the capability or related terms in the full skill text
        terms = capability.lower().split("/")
        for term in terms:
            # Split multi-word capabilities and check for key terms
            key_words = [w for w in term.split() if len(w) > 3]
            if all(w in text_lower for w in key_words):
                found.append(capability)
                break
    return found


def _check_native_overlap(skill_dir: Path) -> List[Violation]:
    """Evaluate whether a skill is redundant with Claude Code native tools.

    Reads the FULL SKILL.md and compares the skill's actual capabilities
    against what Claude Code native tools can and cannot do. Only flags
    skills where the native tool covers ALL the skill's functionality.

    A skill with ANY capability beyond the native tool is NOT flagged.
    """
    violations: List[Violation] = []
    skill_name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return violations

    try:
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return violations

    if "deprecated" in text.lower()[:500]:
        return violations

    fm = parse_frontmatter(text)
    if fm is None:
        return violations
    if fm.get("internal"):
        return violations

    # Check each native tool for overlap
    triggers = fm.get("triggers", [])
    description = str(fm.get("description", ""))
    trigger_text = " ".join(str(t) for t in triggers).lower()

    for tool_name, can_do, cannot_do in _CLAUDE_NATIVE:
        # First: does this skill's triggers/description overlap with what the native tool CAN do?
        has_overlap = any(
            all(w in trigger_text or w in description.lower() for w in phrase.split() if len(w) > 2)
            for phrase in can_do
        )
        if not has_overlap:
            continue

        # Second: does the skill have capabilities BEYOND what the native tool can do?
        beyond = _skill_has_capability_beyond_native(text, cannot_do)

        if beyond:
            # Skill adds value — not redundant. No violation.
            continue

        # The skill's full SKILL.md doesn't mention any capability beyond the native tool.
        violations.append(Violation(
            rule="runtime.native_overlap",
            severity="warn",
            skill=skill_name,
            path=str(skill_md),
            message=f"All capabilities appear covered by Claude Code native '{tool_name}'. "
                    f"No beyond-native features found in SKILL.md. "
                    f"Candidate for deprecation — confirm with Claude Skills 2.0 A/B benchmark.",
        ))
        break  # one overlap finding is enough

    return violations
