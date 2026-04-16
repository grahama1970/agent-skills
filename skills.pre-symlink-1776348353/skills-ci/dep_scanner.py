"""Dependency completeness scanner for skills-ci.

Scans Python files for imports and checks they are declared in pyproject.toml.
Catches the class of bug where a skill works in a shared venv but fails in
isolation because pyproject.toml is missing dependencies.
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path
from typing import Dict, List

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from models import Violation

EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", "dist", "build",
    "unsloth_compiled_cache", "third_party", "vendor",
    "references", ".cache", "site-packages", ".uv",
    "archive-v0", ".tox", ".ruff_cache",
}


def _is_excluded(parts: tuple[str, ...] | list[str]) -> bool:
    """Check if any path component should be excluded from scanning."""
    return any(p in EXCLUDE_DIRS or p.startswith(".venv") for p in parts)


# Map of common import names to their pip package names.
# When `import X` differs from `pip install Y`, add the mapping here.
_IMPORT_TO_PACKAGE = {
    # Data science / ML
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "PIL": "pillow",
    "umap": "umap-learn",
    "faiss": "faiss-cpu",
    # NLP / Tokenization
    "yaml": "pyyaml",
    "ruamel": "ruamel.yaml",
    "bs4": "beautifulsoup4",
    "attr": "attrs",
    "tomli": "tomli",
    # Database clients
    "arango": "python-arango",
    # Document processing
    "fitz": "pymupdf",
    "pymupdf4llm": "pymupdf4llm",
    "pdfminer": "pdfminer.six",
    "camelot": "camelot-py",
    "docx": "python-docx",
    # Web / API
    "dotenv": "python-dotenv",
    "jose": "python-jose",
    "jwt": "pyjwt",
    "websocket": "websocket-client",
    "googleapiclient": "google-api-python-client",
    # Audio / Voice
    "whisper": "openai-whisper",
    "faster_whisper": "faster-whisper",
    "audio_separator": "audio-separator",
    "resemblyzer": "resemblyzer",
    # HuggingFace ecosystem
    "huggingface_hub": "huggingface-hub",
    "sentence_transformers": "sentence-transformers",
    "flash_attn": "flash-attn",
    # D-Bus / System
    "dbus_fast": "dbus-fast",
    "dbus": "dbus-fast",
    "gi": "pygobject",
    # Hardware / Device
    "serial": "pyserial",
    "usb": "pyusb",
    "git": "gitpython",
    # Crypto
    "Cryptodome": "pycryptodome",
    # Dates
    "dateutil": "python-dateutil",
    # Other
    "magic": "python-magic",
    "colour": "colour-science",
    "rich_pixels": "rich-pixels",
    "textual_image": "textual-image",
    "llama_cpp": "llama-cpp-python",
    "json_repair": "json-repair",
    "discord": "discord.py",
    # ELF / Binary analysis
    "elftools": "pyelftools",
    # Namespace subpackages (import X is a subpackage of pip package Y)
    "mpl_toolkits": "matplotlib",
}

# Namespace packages where `import X` can be satisfied by ANY of several pip
# packages. If the declared deps contain any package matching the prefix,
# the import is considered satisfied.
_NAMESPACE_PREFIXES: Dict[str, str] = {
    "google": "google",     # google-auth, google-generativeai, google-api-python-client, etc.
}

# Standard library modules (Python 3.11+)
_STDLIB_MODULES = {
    "abc", "argparse", "ast", "asyncio", "base64", "binascii", "bisect",
    "calendar", "cgi", "cmd", "code", "codecs", "collections", "colorsys",
    "compileall", "concurrent", "configparser", "contextlib", "copy",
    "copyreg", "csv", "ctypes", "dataclasses", "datetime", "decimal",
    "difflib", "dis", "distutils", "email", "enum", "errno", "faulthandler",
    "fcntl", "filecmp", "fileinput", "fnmatch", "fractions", "ftplib",
    "functools", "gc", "getopt", "getpass", "gettext", "glob", "grp",
    "gzip", "hashlib", "heapq", "hmac", "html", "http", "imaplib",
    "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "keyword", "linecache", "locale", "logging", "lzma", "mailbox",
    "math", "mimetypes", "mmap", "multiprocessing", "numbers", "operator",
    "os", "pathlib", "pdb", "pickle", "pickletools", "pkgutil", "platform",
    "plistlib", "poplib", "posixpath", "pprint", "profile", "pstats",
    "pty", "pwd", "py_compile", "pyclbr", "pydoc", "queue", "quopri",
    "random", "re", "readline", "reprlib", "resource", "rlcompleter",
    "runpy", "sched", "secrets", "select", "selectors", "shelve", "shlex",
    "shutil", "signal", "site", "smtplib", "sndhdr", "socket",
    "socketserver", "sqlite3", "ssl", "stat", "statistics", "string",
    "stringprep", "struct", "subprocess", "sunau", "symtable", "sys",
    "sysconfig", "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile",
    "termios", "test", "textwrap", "threading", "time", "timeit",
    "tkinter", "token", "tokenize", "tomllib", "trace", "traceback",
    "tracemalloc", "tty", "turtle", "types", "typing", "unicodedata",
    "unittest", "urllib", "uuid", "venv", "warnings", "wave", "weakref",
    "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib", "xml",
    "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
    "__future__",
    # Effectively stdlib (always available, not pip packages)
    "builtins", "setuptools", "pkg_resources", "pip", "_thread", "_io",
}


def _normalize_dep(dep: str) -> str:
    """Normalize a dependency string to a comparable package name.

    PEP 503: package names are case-insensitive and treat hyphens, underscores,
    and dots as equivalent. We normalize to lowercase with underscores.
    """
    raw = re.split(r"[>=<\[;!]", dep)[0].strip().lower()
    return raw.replace("-", "_").replace(".", "_")


def _parse_declared_deps(pyproject_path: Path) -> set[str]:
    """Extract normalized package names from all pyproject.toml dependency sections.

    Checks: [project].dependencies, [project].optional-dependencies,
    [dependency-groups], and [tool.uv].dev-dependencies.
    """
    try:
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
    except Exception:
        return set()

    declared: set[str] = set()

    # [project].dependencies
    for dep in pyproject.get("project", {}).get("dependencies", []):
        declared.add(_normalize_dep(dep))

    # [project].optional-dependencies (all groups)
    for group_deps in pyproject.get("project", {}).get("optional-dependencies", {}).values():
        for dep in group_deps:
            declared.add(_normalize_dep(dep))

    # [dependency-groups] (PEP 735)
    for group_deps in pyproject.get("dependency-groups", {}).values():
        for dep in group_deps:
            if isinstance(dep, str):
                declared.add(_normalize_dep(dep))

    # [tool.uv].dev-dependencies
    for dep in pyproject.get("tool", {}).get("uv", {}).get("dev-dependencies", []):
        declared.add(_normalize_dep(dep))

    return declared


def _extract_imports(py_file: Path) -> list[tuple[str, bool]]:
    """Extract top-level module names from a Python file via AST.

    Returns list of (module_name, is_guarded) tuples. An import is "guarded"
    if it appears inside a try/except block that catches ImportError — meaning
    the module is optional and the code gracefully degrades without it.
    """
    try:
        source = py_file.read_text(errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except (SyntaxError, UnicodeDecodeError):
        return []

    # First pass: collect line numbers of imports inside try blocks that
    # have an except handler catching ImportError (or bare except).
    guarded_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            catches_import_error = any(
                h.type is None  # bare except
                or (isinstance(h.type, ast.Name) and h.type.id in ("ImportError", "ModuleNotFoundError", "Exception"))
                or (isinstance(h.type, ast.Tuple) and any(
                    isinstance(e, ast.Name) and e.id in ("ImportError", "ModuleNotFoundError", "Exception")
                    for e in h.type.elts
                ))
                for h in node.handlers
            )
            if catches_import_error:
                for child in ast.walk(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        guarded_lines.add(child.lineno)

    # Second pass: extract module names with guarded flag
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append((alias.name.split(".")[0], node.lineno in guarded_lines))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                modules.append((node.module.split(".")[0], node.lineno in guarded_lines))
    return modules


def _build_cross_skill_modules(skills_root: Path) -> set[str]:
    """Build a set of module names that exist as .py files or packages across
    ALL skill directories (and the skills root itself). These are cross-skill
    shared modules that get added to sys.path at runtime and are NOT pip packages.

    Also includes well-known project-level packages that live outside the skills
    tree but are added to sys.path by the runtime (e.g. graph_memory from the
    memory project).

    This is cached per skills_root to avoid rescanning for every skill.
    """
    cache_attr = "_cross_skill_cache"
    cached = getattr(_build_cross_skill_modules, cache_attr, None)
    if cached is not None and cached[0] == str(skills_root):
        return cached[1]

    modules: set[str] = set()
    if not skills_root.exists():
        return modules

    # 1. .py files and packages directly in the skills root (e.g. dotenv_helper.py)
    for py_file in skills_root.glob("*.py"):
        mod_name = py_file.stem
        if mod_name != "__init__":
            modules.add(mod_name)

    # 2. .py files and packages inside each skill directory (recursive)
    for skill_dir in skills_root.iterdir():
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        for py_file in skill_dir.rglob("*.py"):
            parts = py_file.relative_to(skill_dir).parts
            if _is_excluded(parts):
                continue
            mod_name = py_file.stem
            if mod_name != "__init__":
                modules.add(mod_name)
            else:
                modules.add(py_file.parent.name)
        # Directories containing .py files are importable packages
        for d in skill_dir.rglob("*"):
            if d.is_dir() and not _is_excluded((d.name,)):
                parts = d.relative_to(skill_dir).parts
                if _is_excluded(parts):
                    continue
                if any(d.glob("*.py")):
                    modules.add(d.name)

    # 3. Well-known project-level packages installed via editable installs
    # or added to sys.path by the runtime. These are NOT pip packages despite
    # not being in the skills tree.
    _KNOWN_PROJECT_PACKAGES = {
        "graph_memory",           # ~/workspace/experiments/memory/src/graph_memory
        "pdf_oxide",              # Rust extension compiled from extract-pdf
        "extract_tables_rs",      # Rust extension compiled from extract-tables
        "streamdeck",             # ~/workspace/streamdeck/src/streamdeck
    }
    modules.update(_KNOWN_PROJECT_PACKAGES)

    setattr(_build_cross_skill_modules, cache_attr, (str(skills_root), modules))
    return modules


def scan_dependency_completeness(skill_dir: Path) -> List[Violation]:
    """Check that Python imports are declared in pyproject.toml."""
    violations: List[Violation] = []
    skill_name = skill_dir.name
    pyproject_path = skill_dir / "pyproject.toml"

    if not pyproject_path.exists():
        return []

    declared = _parse_declared_deps(pyproject_path)
    if not declared:
        return []

    # Collect imports AND build local module index in one rglob pass
    # imported tracks: module_name → (first_file, is_guarded)
    # A module is only "guarded" if ALL its import sites are guarded.
    imported: Dict[str, tuple[Path, bool]] = {}
    local_modules: set[str] = set()
    for py_file in skill_dir.rglob("*.py"):
        parts = py_file.relative_to(skill_dir).parts
        if _is_excluded(parts):
            continue
        # Index: every .py file's stem is a local module at some depth
        stem = py_file.stem
        if stem != "__init__":
            local_modules.add(stem)
        else:
            # __init__.py → the parent dir name is the package
            local_modules.add(py_file.parent.name)
        for mod, guarded in _extract_imports(py_file):
            if mod not in imported:
                imported[mod] = (py_file, guarded)
            elif not guarded:
                # If ANY import site is unguarded, mark as unguarded
                imported[mod] = (imported[mod][0], False)

    # Also index directories that look like packages (contain .py files)
    for d in skill_dir.rglob("*"):
        if d.is_dir() and not _is_excluded((d.name,)):
            parts = d.relative_to(skill_dir).parts
            if _is_excluded(parts):
                continue
            if any(d.glob("*.py")):
                local_modules.add(d.name)

    # Sibling skill names and shared modules (not pip packages)
    skills_root = skill_dir.parent
    sibling_skills = {d.name for d in skills_root.iterdir() if d.is_dir()} if skills_root.exists() else set()
    cross_skill_modules = _build_cross_skill_modules(skills_root)

    # Also check if the skill's own package name matches (editable installs)
    try:
        with open(pyproject_path, "rb") as f:
            _pyproject = tomllib.load(f)
        own_package = _normalize_dep(
            _pyproject.get("project", {}).get("name", "")
        )
    except Exception:
        own_package = ""

    for module_name, (first_file, is_guarded) in sorted(imported.items()):
        if module_name in _STDLIB_MODULES:
            continue

        # Skip try/except guarded imports (optional dependencies)
        if is_guarded:
            continue

        # Skip sibling skill imports (skill-to-skill via subprocess is fine)
        if module_name in sibling_skills:
            continue

        # Skip cross-skill shared modules (.py files that exist in other skill dirs)
        if module_name in cross_skill_modules:
            continue

        # Skip local modules (files/packages anywhere within the skill dir tree)
        if module_name in local_modules:
            continue

        # Skip self-imports (skill installed as its own package via pip -e)
        if own_package and _normalize_dep(module_name) == own_package:
            continue

        # Namespace package check: if import name has a known prefix,
        # accept any declared dep starting with that prefix
        ns_prefix = _NAMESPACE_PREFIXES.get(module_name)
        if ns_prefix and any(d.startswith(ns_prefix) for d in declared):
            continue

        # Map import name → package name (normalize same as deps)
        package = _IMPORT_TO_PACKAGE.get(
            module_name, module_name
        ).lower().replace("-", "_").replace(".", "_")

        if package not in declared:
            rel = first_file.relative_to(skill_dir)
            violations.append(Violation(
                rule="deps.undeclared_import",
                severity="error",
                skill=skill_name,
                path=str(first_file),
                message=(
                    f"'{module_name}' is imported in {rel} "
                    f"but not declared in pyproject.toml dependencies."
                ),
            ))

    return violations
