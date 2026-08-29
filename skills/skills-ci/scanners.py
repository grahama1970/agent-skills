"""Scanning rules for skills-ci.

Contains all scan functions that detect violations across skill directories:
best-practices-skills checks, best-practices-python checks, pyproject.toml
dependency validation, hatchling layout detection, memory integration
validation, and naming convention checks.
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from models import Violation

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".cache",
    ".uv",
    "site-packages",
    ".eggs",
    ".tox",
    ".ruff_cache",
}

FIX_EXCLUDE_SEGMENTS = {
    "Qwen3-TTS",
    "rvc",
    "third_party",
    "vendor",
    "work",
    # Vendored reference repos (design inspiration, not our source)
    "references",
    # Generated project scaffolds (created by build_tools phase)
    "sanity_check_dream",
    "sanity_no_prompt",
    "test_prompt_fix",
    "movie_project",
    "test_e2e_together",
    "unsloth_compiled_cache",
    # Template generators that emit argparse code into generated dirs
    "phases",
}

ALLOWED_REQUESTS_METHODS = {
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "head",
    "request",
}

# Map from Python import name to the expected pyproject.toml package name.
_IMPORT_TO_PKG: Dict[str, str] = {
    "typer": "typer",
    "loguru": "loguru",
    "httpx": "httpx",
    "rich": "rich",
    "pydantic": "pydantic",
    "dotenv": "python-dotenv",
}

# Packages that are banned -- warn if declared in pyproject.toml.
_BANNED_DEPS = {"click", "argparse"}

_NOUN_ALLOWLIST = {
    "memory", "taxonomy", "scheduler", "embedding", "scillm",
    "analytics", "assess", "hum", "argue", "fetcher", "normalize",
    "extractor", "distill", "anvil", "codex", "interview",
    "dogpile", "perplexity", "arxiv", "ask", "converse",
    "orchestrate", "treesitter", "cleanup", "battle",
    "common", "context7",
    # Established skill names -- noun-only is accepted
    "assistant", "assistant-lab", "benchmark-models", "bootcamp",
    "cmmc-assessor", "compliance-timeline", "conversation-lab",
    "cui-marker", "dashboard", "embry-config", "episodic-archiver",
    "export-oscal", "extractor-quality-check", "figure-lab",
    "gpt-lab", "hack", "handoff", "intent-mapper", "paper-lab",
    "plan", "project-state", "recommend-skill-chain", "regressor-lab",
    "service-status", "skill-lab", "streamdeck-lab", "surf",
    "sync-sites", "table-lab", "task-monitor", "test-lab",
    "voice-lab", "shame",
    "qra-review",
    # Batch added 2026-03-29 -- established noun-only names
    "checkpoint", "chutes-call", "clean-text", "code-runner",
    "embry-dashboard", "evidence-case-lab", "evidence-case-viewer",
    "lie-detector", "llm-eval-lab", "mockup-lab", "music-lab",
    "nico-qa", "png-svg-converter", "story-lab",
    "switchboard", "test", "test-interactions", "thunderdome", "ux-lab",
}

_VERB_PREFIXES = (
    "analyze-", "create-", "discover-", "ingest-", "review-", "train-",
    "monitor-", "ops-", "learn-", "consume-", "debug-",
    "batch-", "mine-", "hack-", "surf-", "plan-",
    "best-practices-", "reality-check-", "prototype-",
    "formalize-", "edge-", "social-", "security-",
    "skills-", "agent-", "rate-limit-", "voice-",
    "quality-", "prompt-", "corpus-", "data-",
    "pdf-", "sfx-", "tts-", "doc2", "fixture-",
    "extract-", "persona-", "vector-", "classifier-",
    "github-", "brave-", "sparta-", "lean4-",
    "keybindings-",
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def list_skill_dirs(root: Path) -> List[Path]:
    skills = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if entry.name in EXCLUDE_DIRS:
            continue
        # Require SKILL.md to be a real skill directory
        if not (entry / "SKILL.md").exists():
            continue
        skills.append(entry)
    return sorted(skills)


def should_skip_path(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS or part in FIX_EXCLUDE_SEGMENTS:
            return True
        # Catch .venv-batch, .venv_old, .venv.bak and any other venv variant
        if part.startswith(".venv"):
            return True
    return False


# Directories that must NEVER be scanned or fixed, even if they appear as path ancestors.
# These are system/cache dirs that contain third-party code we don't own.
NEVER_TOUCH_ANCESTORS = {".cache", "site-packages", "archive-v0", "lib"}


def should_fix_path(path: Path) -> bool:
    if should_skip_path(path):
        return False
    # Hard boundary: NEVER fix files in cache, site-packages, or system dirs
    parts = set(path.resolve().parts)
    if parts & NEVER_TOUCH_ANCESTORS:
        return False
    # Never auto-fix test fixtures (they contain intentional violations)
    _FIX_ONLY_EXCLUDE = {"fixtures"}
    return not any(part in FIX_EXCLUDE_SEGMENTS or part in _FIX_ONLY_EXCLUDE for part in path.parts)


def iter_python_files(skill_dir: Path) -> Iterable[Path]:
    for path in skill_dir.rglob("*.py"):
        if should_skip_path(path):
            continue
        yield path


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> Optional[Dict]:
    """Parse YAML frontmatter using pyyaml for correct handling of fold syntax."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    raw = text[4:end]
    try:
        import yaml
        data = yaml.safe_load(raw)
        if isinstance(data, dict):
            return data
        return None
    except Exception:
        return None


def extract_frontmatter_raw(text: str) -> Optional[str]:
    """Return the raw frontmatter block (between --- delimiters) as a string."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    return text[4:end]


def has_module_docstring(text: str) -> bool:
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped.startswith('"""') or stripped.startswith("'''")
    return False


def uses_requests(text: str) -> bool:
    return bool(re.search(r"^\s*import\s+requests\b|^\s*from\s+requests\b", text, re.MULTILINE))


def requests_safe_to_alias(text: str) -> bool:
    if "from requests" in text:
        return False
    if "requests.Session" in text or "requests.adapters" in text or "requests.exceptions" in text:
        return False
    if re.search(r"\bimport\s+httpx\b", text):
        return False
    methods = re.findall(r"requests\.([A-Za-z_]+)", text)
    return all(m in ALLOWED_REQUESTS_METHODS for m in methods)


# ---------------------------------------------------------------------------
# Scan: best-practices-skills
# ---------------------------------------------------------------------------

def scan_best_practices_skills(skill_dir: Path) -> List[Violation]:
    violations: List[Violation] = []
    skill_name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        violations.append(Violation(
            rule="skills.missing_skill_md",
            severity="warn",
            skill=skill_name,
            path=str(skill_md),
            message="Missing SKILL.md; directory treated as non-skill.",
        ))
        return violations

    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    if text.lstrip().startswith("```"):
        violations.append(Violation(
            rule="skills.frontmatter_fenced",
            severity="error",
            skill=skill_name,
            path=str(skill_md),
            message="Frontmatter appears inside a fenced code block.",
        ))
        return violations

    frontmatter = parse_frontmatter(text)
    if frontmatter is None:
        violations.append(Violation(
            rule="skills.frontmatter_missing",
            severity="error",
            skill=skill_name,
            path=str(skill_md),
            message="Missing YAML frontmatter.",
        ))
        return violations

    name = frontmatter.get("name")
    desc = frontmatter.get("description")
    if not name:
        violations.append(Violation(
            rule="skills.frontmatter_name",
            severity="error",
            skill=skill_name,
            path=str(skill_md),
            message="Frontmatter missing name.",
        ))
    elif name.strip("'\"") != skill_name:
        violations.append(Violation(
            rule="skills.frontmatter_name_mismatch",
            severity="error",
            skill=skill_name,
            path=str(skill_md),
            message=f"Frontmatter name '{name}' does not match directory '{skill_name}'.",
        ))
    if not desc:
        violations.append(Violation(
            rule="skills.frontmatter_description",
            severity="error",
            skill=skill_name,
            path=str(skill_md),
            message="Frontmatter missing description.",
            fixable=True,
        ))

    _ALLOWED_ROOT_MD = {"SKILL.md", "CLAUDE.md", "AGENTS.md"}
    extra_docs = [p.name for p in skill_dir.glob("*.md") if p.name not in _ALLOWED_ROOT_MD]
    if extra_docs:
        violations.append(Violation(
            rule="skills.extra_docs",
            severity="warn",
            skill=skill_name,
            path=str(skill_dir),
            message=f"Extra docs in skill root: {', '.join(sorted(extra_docs))}.",
        ))

    # Antipattern documentation check (delegated to antipattern_scanner module)
    from antipattern_scanner import scan_missing_antipatterns
    violations.extend(scan_missing_antipatterns(skill_dir, skill_name, text))

    # Skills that compose memory/embedding/arango must have a "read before use" directive
    composes = frontmatter.get("composes", []) or []
    provides = frontmatter.get("provides", []) or []
    memory_adjacent = any(
        kw in str(composes) + str(provides)
        for kw in ["memory", "arango", "embedding", "upsert", "recall"]
    )
    if memory_adjacent:
        body = text.split("---", 2)[-1] if text.count("---") >= 2 else text
        first_200 = body[:500].upper()
        has_read_directive = any(
            phrase in first_200
            for phrase in ["READ THIS ENTIRE", "READ BEFORE USE", "STOP.", "DO NOT SKIM"]
        )
        if not has_read_directive:
            violations.append(Violation(
                rule="skills.memory_read_directive",
                severity="warn",
                skill=skill_name,
                path=str(skill_md),
                message="Skill composes /memory but has no 'read before use' directive in first 500 chars after frontmatter. "
                        "Add: '> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.' "
                        "See /memory SKILL.md for the pattern.",
            ))

    return violations


# ---------------------------------------------------------------------------
# Scan: best-practices-python
# ---------------------------------------------------------------------------

def scan_best_practices_python(skill_dir: Path) -> Tuple[List[Violation], Dict[str, List[Path]]]:
    violations: List[Violation] = []
    skill_name = skill_dir.name
    by_rule: Dict[str, List[Path]] = {
        "missing_docstring": [],
        "requests": [],
        "click": [],
        "argparse": [],
        "logging": [],
        "oversize": [],
    }

    for path in iter_python_files(skill_dir):
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()

        if not has_module_docstring(text):
            by_rule["missing_docstring"].append(path)
            violations.append(Violation(
                rule="python.module_docstring",
                severity="warn",
                skill=skill_name,
                path=str(path),
                message="Missing module docstring.",
                fixable=True,
            ))

        if re.search(r"^\s*import\s+requests\b|^\s*from\s+requests\b", text, re.MULTILINE):
            by_rule["requests"].append(path)
            violations.append(Violation(
                rule="python.requests",
                severity="warn",
                skill=skill_name,
                path=str(path),
                message="Uses requests; prefer httpx.",
                fixable=True,
            ))

        if re.search(r"^\s*import\s+click\b|^\s*from\s+click\b", text, re.MULTILINE):
            by_rule["click"].append(path)
            violations.append(Violation(
                rule="python.click",
                severity="warn",
                skill=skill_name,
                path=str(path),
                message="Uses click; prefer Typer.",
                fixable=False,
            ))

        if re.search(r"^\s*import\s+argparse\b|^\s*from\s+argparse\b", text, re.MULTILINE):
            by_rule["argparse"].append(path)
            violations.append(Violation(
                rule="python.argparse",
                severity="warn",
                skill=skill_name,
                path=str(path),
                message="Uses argparse; prefer Typer.",
                fixable=False,
            ))

        if re.search(r"^\s*import\s+logging\b|^\s*from\s+logging\b|logging\.getLogger", text, re.MULTILINE):
            by_rule["logging"].append(path)
            violations.append(Violation(
                rule="python.logging",
                severity="warn",
                skill=skill_name,
                path=str(path),
                message="Uses logging; prefer loguru.",
                fixable=True,
            ))

        if len(lines) > 900:
            by_rule["oversize"].append(path)
            violations.append(Violation(
                rule="python.file_length",
                severity="warn",
                skill=skill_name,
                path=str(path),
                message=f"File exceeds 900 LOC ({len(lines)}).",
                fixable=False,
            ))

    # Skill-level pyproject.toml checks
    violations.extend(_check_pyproject_deps(skill_dir))
    violations.extend(_check_hatchling_flat_layout(skill_dir))

    return violations, by_rule


# ---------------------------------------------------------------------------
# pyproject.toml dependency completeness check
# ---------------------------------------------------------------------------

def _parse_pyproject_deps(skill_dir: Path) -> Optional[List[str]]:
    """Return lowercased dependency names from pyproject.toml, or None if missing."""
    pyproject = skill_dir / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        raw = data.get("project", {}).get("dependencies", [])
        # Normalize: "typer>=0.9.0" -> "typer", "python-dotenv>=1.0" -> "python-dotenv"
        return [re.split(r"[>=<!\s@\[;]", dep.strip())[0].lower() for dep in raw]
    except Exception:
        return None


def _check_pyproject_deps(skill_dir: Path) -> List[Violation]:
    """Cross-reference Python imports against pyproject.toml dependencies."""
    violations: List[Violation] = []
    skill_name = skill_dir.name
    pyproject_path = str(skill_dir / "pyproject.toml")

    declared = _parse_pyproject_deps(skill_dir)
    if declared is None:
        return violations

    # Check for banned deps in pyproject.toml
    for banned in _BANNED_DEPS:
        if banned in declared:
            violations.append(Violation(
                rule="python.banned_dep",
                severity="warn",
                skill=skill_name,
                path=pyproject_path,
                message=f"pyproject.toml declares '{banned}'; use typer instead.",
                fixable=False,
            ))

    # Collect all imports across .py files using ast (not regex)
    imported: set[str] = set()
    for path in iter_python_files(skill_dir):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in _IMPORT_TO_PKG:
                        imported.add(top)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top in _IMPORT_TO_PKG:
                    imported.add(top)

    # Check each imported module has a matching pyproject.toml dep
    for import_name in sorted(imported):
        pkg_name = _IMPORT_TO_PKG[import_name]
        if pkg_name.lower() not in declared:
            violations.append(Violation(
                rule="python.missing_dep",
                severity="error",
                skill=skill_name,
                path=pyproject_path,
                message=f"Source imports '{import_name}' but pyproject.toml missing '{pkg_name}'.",
                fixable=True,
            ))

    return violations


def _check_hatchling_flat_layout(skill_dir: Path) -> List[Violation]:
    """Detect hatchling build-system in skills with flat .py layout (no package dir).

    Hatchling requires a package directory matching the project name or a src/
    layout. Skills with flat .py files and hatchling will fail with:
      ValueError: Unable to determine which files to ship inside the wheel
    Fix: remove [build-system] -- skills are not publishable packages.
    """
    violations: List[Violation] = []
    pyproject = skill_dir / "pyproject.toml"
    if not pyproject.exists():
        return violations
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:
        return violations

    bs = data.get("build-system", {})
    if "hatchling" not in str(bs.get("requires", [])):
        return violations

    name = data.get("project", {}).get("name", "")
    pkg_name = name.replace("-", "_")
    has_pkg_dir = (skill_dir / pkg_name).is_dir() or (skill_dir / "src").is_dir()
    has_flat_py = any(skill_dir.glob("*.py"))

    if not has_pkg_dir and has_flat_py:
        violations.append(Violation(
            rule="python.hatchling_flat_layout",
            severity="error",
            skill=skill_dir.name,
            path=str(pyproject),
            message="hatchling build-system with flat .py layout will fail wheel build; remove [build-system] section.",
            fixable=True,
        ))
    return violations


# ---------------------------------------------------------------------------
# Memory integration validation (opt-in)
# ---------------------------------------------------------------------------

def scan_memory_integration(skill_dir: Path) -> List[Violation]:
    """Validate memory_integration.py follows the standard pattern (opt-in).

    If any .py file in the skill imports from ``common.discovery``, the skill
    is considered to have memory integration via the discovery module and the
    check is skipped.  If no ``memory_integration.py`` exists the skill is
    simply not opted-in -- no violation is emitted.
    """
    violations: List[Violation] = []
    skill_name = skill_dir.name

    # Discovery-based skills (discover-*) use common.discovery -- skip
    for py_file in iter_python_files(skill_dir):
        try:
            text = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "from common.discovery import" in text:
            return []

    mi_path = skill_dir / "memory_integration.py"
    if not mi_path.exists():
        return []  # opt-in only

    text = mi_path.read_text(encoding="utf-8", errors="ignore")

    checks = [
        ("memory.missing_has_memory_flag", "_HAS_MEMORY"),
        ("memory.missing_recall_function", r"def recall_"),
        ("memory.missing_learn_function", r"def learn_"),
        ("memory.missing_extract_bridges", r"def extract_bridges"),
        ("memory.missing_graceful_import", r"except ImportError"),
        ("memory.missing_bridge_keywords", "_BRIDGE_KEYWORDS"),
    ]

    for rule, pattern in checks:
        if not re.search(pattern, text):
            violations.append(Violation(
                rule=rule,
                severity="warn",
                skill=skill_name,
                path=str(mi_path),
                message=f"memory_integration.py missing required pattern: {pattern}",
            ))

    return violations


# ---------------------------------------------------------------------------
# Naming convention check (warn-only)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Scan: subprocess hygiene (VIRTUAL_ENV, stderr handling)
# ---------------------------------------------------------------------------

def scan_subprocess_hygiene(skill_dir: Path) -> List[Violation]:
    """Check for subprocess patterns that break in scheduler/cron contexts.

    Rules:
    - subprocess.venv_leak: subprocess.run/Popen without stripping VIRTUAL_ENV
      from env — causes uv venv conflict warnings when called cross-skill.
    - subprocess.stderr_fatal: treating any stderr output as a fatal error
      instead of checking returncode — uv/pip emit warnings to stderr that
      are not errors.
    - subprocess.raw_aql: direct ArangoDB AQL execution — must use /memory.
    - subprocess.service_bypass: subprocess calls to skills that have running
      HTTP services (memory, embedding, taxonomy, doc2qra, scillm) — POST
      to the service instead of spawning a process per call.
    """
    violations: List[Violation] = []
    skill_name = skill_dir.name

    # Known exceptions for raw AQL:
    #   - memory/embedding: canonical AQL location and core vector service
    #   - monitor-*: health probes need aggregate queries on archiver collections
    #   - sparta-stress-test: integration test harness exercising full ArangoDB pipeline
    #   - episodic-archiver: cross-session edge analysis with passed-in db handle
    #   - evidence-case-lab: test data generators sampling from sparta_controls/qra
    #   - lean4-prove: benchmark scripts querying formalization collections
    #   - learn-datalake: post-ingestion taxonomy validation check
    #   - ask: RSS feed queries against ArangoSearch view (feed_items_view)
    _AQL_EXCEPTIONS = {
        "memory", "embedding",
        "monitor-memory", "monitor-episodic-archiver",
        "sparta-intent", "ops-arango",
        "sparta-stress-test",
        "episodic-archiver",
        "evidence-case-lab",
        "lean4-prove",
        "learn-datalake",
        "ask",
    }

    for py_file in iter_python_files(skill_dir):
        try:
            text = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # Rule: subprocess calls that shell out to other skills without
        # stripping VIRTUAL_ENV — causes uv venv mismatch warnings
        if ("subprocess.run" in text or "subprocess.Popen" in text):
            if ("run.sh" in text or "/skills/" in text):
                if "VIRTUAL_ENV" not in text and "env=" not in text:
                    violations.append(Violation(
                        rule="subprocess.venv_leak",
                        severity="warn",
                        skill=skill_name,
                        path=str(py_file),
                        message="Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context.",
                    ))

        # Rule: treating stderr as fatal without checking returncode
        if re.search(r"result\.stderr.*raise|raise.*result\.stderr|if result\.stderr", text):
            if "returncode" not in text.split("stderr")[0].split("\n")[-1]:
                violations.append(Violation(
                    rule="subprocess.stderr_fatal",
                    severity="warn",
                    skill=skill_name,
                    path=str(py_file),
                    message="Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead.",
                ))

        # Rule: raw AQL — must use /memory
        if skill_name not in _AQL_EXCEPTIONS:
            if re.search(r"db\.aql\.execute|\.aql\.execute", text):
                violations.append(Violation(
                    rule="subprocess.raw_aql",
                    severity="warn",
                    skill=skill_name,
                    path=str(py_file),
                    message="Direct ArangoDB AQL execution — must use /memory skill instead.",
                ))

        # Rule: subprocess to a skill that has a running HTTP service.
        # These skills have persistent daemons — POST to the service
        # instead of spawning a subprocess per call.
        _SERVICE_SKILLS = {
            "memory": "embry-memory (Unix socket / port 8601)",
            "embedding": "embry-embedding (port 8602)",
            "taxonomy": "embry-memory /taxonomy/* endpoints",
            "doc2qra": "embry-chutes-call /batch (port 8630)",
            "scillm": "scillm proxy (port 4001)",
        }
        if "subprocess" in text and ("run.sh" in text or "run_skill" in text):
            for svc_skill, svc_desc in _SERVICE_SKILLS.items():
                # Match patterns like: SKILLS_ROOT / "<svc>" / "run.sh"
                # or: "<svc>/run.sh" or <SVC>_RUN
                pattern = rf'["\'/]{svc_skill}["\'/].*run\.sh|{svc_skill.upper()}_RUN'
                if re.search(pattern, text):
                    violations.append(Violation(
                        rule="subprocess.service_bypass",
                        severity="warn",
                        skill=skill_name,
                        path=str(py_file),
                        message=(
                            f"Subprocess calls /{svc_skill} run.sh but {svc_desc} "
                            f"is a running HTTP service — POST to it instead."
                        ),
                    ))

    return violations


# ---------------------------------------------------------------------------
# Scan: model routing readiness
# ---------------------------------------------------------------------------

# Skills known to make LLM calls (from 2026-03-02 audit)
_LLM_CALLING_SKILLS = {
    "arxiv", "assistant", "batch-quality", "classifier-lab", "codex",
    "create-gpt", "create-icon", "create-intent-map", "create-movie",
    "create-music", "create-stems", "create-table-classifier", "doc2qra",
    "edge-verifier", "embedding", "episodic-archiver", "extract-html",
    "extractor-quality-check", "gpt-lab", "ingest-audiobook",
    "ingest-youtube", "lean4-prove", "lie-detector", "memory",
    "monitor-taxonomy", "prompt-lab", "review-music", "scillm",
    "skill-lab", "sparta-stress-test", "train-convo-steering", "tts-train",
}

# Compose threshold for PTC eligibility
_PTC_COMPOSE_THRESHOLD = 8

# Skills acknowledged as complex orchestrators that legitimately compose many
# skills.  PTC optimisation is desirable but not actionable today — suppress
# the warning so it doesn't inflate the violation count.
_PTC_ACKNOWLEDGED: set[str] = {
    "ask",
    "assistant-lab",
    "create-evidence-case",
    "create-paper",
    "create-peer-review",
    "lean4-prove",
    "lie-detector",
    "monitor-codebase",
    "monitor-workstation",
    "music-lab",
    "ops-f36-plant",
    "paper-lab",
    "project-state",
    "review-question",
    "skill-lab",
    "story-lab",
}

# Skills allowed to reference 'common' in composes — they depend on the shared
# module at runtime and the reference is intentional.
_COMPOSES_COMMON_ALLOWED: set[str] = {
    "monitor-skills",
    "skill-lab",
}

# Known composes references to skills that exist as directories but lack a
# SKILL.md (incomplete skills).  Suppress the phantom warning.
_COMPOSES_PHANTOM_ALLOWED: dict[str, set[str]] = {
    "sparta-stress-test": {"sparta-intent"},
}


def _parse_composes(text: str) -> List[str]:
    """Extract composes list from SKILL.md frontmatter."""
    fm = parse_frontmatter(text)
    if not fm:
        return []
    raw = fm.get("composes", [])
    # pyyaml returns a list for [a, b, c] syntax
    if isinstance(raw, list):
        return [str(c).strip().strip("'\"") for c in raw if c]
    # Fallback for string values
    raw = str(raw).strip().strip("[]")
    if not raw:
        return []
    return [c.strip().strip("'\"") for c in raw.split(",") if c.strip()]


def scan_model_routing(skill_dir: Path, all_skill_names: Optional[set] = None) -> List[Violation]:
    """Check model routing readiness, composes accuracy, and PTC eligibility.

    Rules:
    - routing.missing_model_flag: LLM-calling skill lacks --model CLI flag
    - routing.composes_phantom: composes references a skill that doesn't exist
    - routing.composes_common: composes references common/ (not a skill)
    - routing.ptc_candidate: skill composes 8+ skills (PTC would reduce tokens)
    """
    violations: List[Violation] = []
    skill_name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        return violations

    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    composes = _parse_composes(text)

    # Rule 1: LLM-calling skills should accept --model flag
    if skill_name in _LLM_CALLING_SKILLS:
        has_model_flag = False
        for py_file in iter_python_files(skill_dir):
            try:
                py_text = py_file.read_text(encoding="utf-8", errors="ignore")
                if "--model" in py_text or '"model"' in py_text:
                    has_model_flag = True
                    break
            except Exception:
                continue
        if not has_model_flag:
            violations.append(Violation(
                rule="routing.missing_model_flag",
                severity="warn",
                skill=skill_name,
                path=str(skill_md),
                message="LLM-calling skill lacks --model CLI flag for `with <model>` routing.",
            ))

    # Rule 2: Validate composes references exist
    if all_skill_names and composes:
        phantom_allowed = _COMPOSES_PHANTOM_ALLOWED.get(skill_name, set())
        for composed in composes:
            if composed == "common" or composed.startswith("common/"):
                if skill_name not in _COMPOSES_COMMON_ALLOWED:
                    violations.append(Violation(
                        rule="routing.composes_common",
                        severity="warn",
                        skill=skill_name,
                        path=str(skill_md),
                        message=f"composes references '{composed}' — common/ is a shared module, not a skill.",
                    ))
            elif composed not in all_skill_names and composed not in phantom_allowed:
                violations.append(Violation(
                    rule="routing.composes_phantom",
                    severity="warn",
                    skill=skill_name,
                    path=str(skill_md),
                    message=f"composes references '{composed}' which is not a known skill.",
                ))

    # Rule 3: PTC eligibility (informational) — skip acknowledged orchestrators
    if len(composes) >= _PTC_COMPOSE_THRESHOLD and skill_name not in _PTC_ACKNOWLEDGED:
        violations.append(Violation(
            rule="routing.ptc_candidate",
            severity="info" if hasattr(Violation, "info") else "warn",
            skill=skill_name,
            path=str(skill_md),
            message=f"Composes {len(composes)} skills — PTC backend would reduce orchestration tokens by ~85%.",
        ))

    return violations


# ---------------------------------------------------------------------------
# Naming convention check (warn-only)
# ---------------------------------------------------------------------------

def scan_naming_convention(skill_dir: Path) -> List[Violation]:
    """Warn-only check for skill naming conventions.

    Emits ``naming.noun_only`` for skill directories whose name doesn't start
    with a known verb prefix and isn't on the noun allowlist.  Internal skills
    (``internal: true``) are exempt.
    """
    violations: List[Violation] = []
    skill_name = skill_dir.name

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return []

    # Internal skills are exempt from naming conventions
    try:
        from runtime_scanners import is_internal_skill
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
        if is_internal_skill(text):
            return []
    except Exception:
        pass

    if any(skill_name.startswith(prefix) for prefix in _VERB_PREFIXES):
        return []

    if skill_name in _NOUN_ALLOWLIST:
        return []

    violations.append(Violation(
        rule="naming.noun_only",
        severity="warn",
        skill=skill_name,
        path=str(skill_dir / "SKILL.md"),
        message=f"Skill name '{skill_name}' appears noun-only; consider a verb- prefix or add to _NOUN_ALLOWLIST.",
    ))

    return violations
