#!/usr/bin/env python3
"""
Ingest codebases into /memory for knowledge extraction and CWE scanning.

Extracts functional knowledge (module purpose, function signatures, class
hierarchies, docstrings) AND security taxonomy (CWE mappings, bridge tags)
from source files and stores them in /memory for Embry to recall.

Usage:
    ./run.sh scan /path/to/codebase                    # Full knowledge + CWE scan
    ./run.sh scan /path/to/codebase --cwe-only         # CWE scan only (legacy)
    ./run.sh scan /path/to/codebase --dry-run           # Preview without storing
    ./run.sh rescan --since 1d --validate
"""

import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Sequence

import httpx

from code_memory_client import CodeMemoryClient
from code_symbol_record import CodeSymbolRecord
from ingest_code_cwe import scan_file_cwe

try:
    import typer
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "-q"],
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    import typer

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

# Import Monitor adapter for TUI progress bar
try:
    _task_monitor_path = _Path.home() / ".pi" / "skills" / "task-monitor"
    if str(_task_monitor_path) not in _sys.path:
        _sys.path.insert(0, str(_task_monitor_path))
    from monitor_adapter import Monitor
except ImportError:
    Monitor = None


# Default file patterns for scanning
DEFAULT_GLOB_PATTERNS = [
    "*.py", "*.c", "*.cpp", "*.h", "*.hpp",
    "*.rs", "*.go", "*.java", "*.ts", "*.js",
    "*.rb", "*.php", "*.swift", "*.kt", "*.scala"
]

# Skip patterns — dirs that are never useful
SKIP_DIRS = {
    ".venv", "venv", "node_modules", "__pycache__", ".git", ".tox",
    "dist", "build", "egg-info", ".eggs", ".mypy_cache", ".pytest_cache",
    "site-packages", ".uv",
}

MEMORY_SOCKET_PATH = "/run/user/1000/embry/memory.sock"
SCAN_INCLUDE_DIRS_ENV = "CODE_SYMBOLS_SCAN_INCLUDE_DIRS"
CODE_SYMBOL_VERIFICATION_TOP_K = 5
_VERIFICATION_IDENTITY_FIELDS = (
    "repo",
    "path",
    "qualified_name",
    "start_line",
    "end_line",
    "name",
    "problem",
)


def load_taxonomy_module():
    """Load the taxonomy module for bridge tag + CWE extraction."""
    taxonomy_paths = [
        Path(__file__).parent.parent / "taxonomy" / "taxonomy.py",
        Path.home() / ".pi" / "skills" / "taxonomy" / "taxonomy.py",
        Path.home() / ".agents" / "skills" / "taxonomy" / "taxonomy.py",
    ]
    for tp in taxonomy_paths:
        if tp.exists():
            spec = importlib.util.spec_from_file_location("taxonomy", tp)
            module = importlib.util.module_from_spec(spec)
            sys.modules["taxonomy"] = module
            spec.loader.exec_module(module)
            return module
    return None


def find_memory_skill() -> Optional[Path]:
    """Check if embry-memory daemon is available via Unix socket."""
    sock = Path(MEMORY_SOCKET_PATH)
    return sock if sock.exists() else None


def _learn_http(problem: str, solution: str, scope: str, tags: list[str]) -> bool:
    """Store a lesson in /memory via Unix socket httpx."""
    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET_PATH)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=15.0) as client:
            document = {
                "problem": problem,
                "solution": solution,
                "scope": scope,
                "tags": tags,
                "code_symbol": True,
            }
            resp = client.post("/store", json={"document": document})
            if 200 <= resp.status_code < 300:
                return True
            resp = client.post("/learn", json=document)
            return 200 <= resp.status_code < 300
    except Exception:
        return False


def _learn(memory_script: Path, problem: str, solution: str, scope: str, tags: list[str]) -> bool:
    """Store a lesson in /memory via Unix socket httpx."""
    return _learn_http(problem, solution, scope, tags)


def _recall_http(query: str, k: int = 1) -> dict[str, Any]:
    """Query /memory recall over the Unix socket."""
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET_PATH)
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=15.0) as client:
        resp = client.post("/recall", json={"q": query, "k": k})
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"items": []}


def _extract_verification_name(tags: list[str]) -> Optional[str]:
    """Extract the symbol/function name used for embedding recall verification."""
    if "function" in tags:
        function_index = tags.index("function")
        if function_index + 1 < len(tags):
            return tags[function_index + 1]

    if "symbol" in tags:
        symbol_index = tags.index("symbol")
        if symbol_index + 2 < len(tags):
            kind = tags[symbol_index + 1]
            if kind in {"function", "method", "class"}:
                return tags[symbol_index + 2]

    if "class" in tags:
        class_index = tags.index("class")
        if class_index + 1 < len(tags):
            return tags[class_index + 1]

    return None


def _recall_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize recall responses into an item list."""
    items = data.get("items", [])
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _recall_item_matches_name(item: dict[str, Any], name: str) -> bool:
    """Check whether the recalled item looks like the stored symbol entry."""
    haystacks = [
        item.get("problem", ""),
        item.get("solution", ""),
        item.get("title", ""),
        item.get("text", ""),
    ]
    lower_name = name.lower()
    return any(lower_name in str(value).lower() for value in haystacks if value)


def _code_symbol_verification_sample(record: CodeSymbolRecord) -> dict[str, str]:
    """Build a path-qualified embedding verification sample for one stored symbol."""
    return {
        "name": record.symbol_name,
        "problem": record.problem,
        "repo": record.repo,
        "path": record.path,
        "qualified_name": record.qualified_name,
        "start_line": str(record.start_line),
        "end_line": str(record.end_line),
    }


def _verification_sample_identity(sample: dict[str, str]) -> str:
    """Return the stable logical identity of one verification sample."""
    return "\x1f".join(
        str(sample.get(field, "")).strip()
        for field in _VERIFICATION_IDENTITY_FIELDS
    )


def _select_verification_samples(
    samples: list[dict[str, str]],
    sample_size: int,
) -> list[dict[str, str]]:
    """Select a deterministic, duplicate-free verification subset."""
    if sample_size <= 0 or not samples:
        return []

    unique_samples: dict[str, dict[str, str]] = {}
    for sample in samples:
        identity = _verification_sample_identity(sample)
        unique_samples.setdefault(identity, sample)

    ranked = sorted(
        unique_samples.items(),
        key=lambda item: (
            hashlib.sha256(item[0].encode("utf-8")).hexdigest(),
            item[0],
        ),
    )
    return [sample for _, sample in ranked[:sample_size]]


def _verification_query(sample: dict[str, str]) -> str:
    """Build a recall query for a verification sample."""
    path = sample.get("path", "").strip()
    if not path:
        return sample["name"]

    qualified_name = sample.get("qualified_name", "").strip() or sample["name"]
    start_line = sample.get("start_line", "").strip()
    end_line = sample.get("end_line", "").strip()
    locator = path
    if start_line and end_line:
        locator = f"{path}:{start_line}-{end_line}"

    parts = [
        qualified_name,
        locator,
        sample.get("repo", "").strip(),
    ]
    return " ".join(dict.fromkeys(part for part in parts if part))


def _normalize_verification_path(value: object) -> str:
    return str(value or "").strip().replace("\\", "/")


def _verification_identity_sources(item: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = [item]
    for key in ("metadata", "document", "payload"):
        value = item.get(key)
        if isinstance(value, dict):
            sources.append(value)
            metadata = value.get("metadata")
            if isinstance(metadata, dict):
                sources.append(metadata)
    return sources


def _verification_text(item: dict[str, Any]) -> str:
    texts: list[str] = []
    for source in _verification_identity_sources(item):
        for key in ("problem", "solution", "title", "text"):
            value = source.get(key)
            if value:
                texts.append(str(value))
    return "\n".join(texts)


def _recall_item_matches_sample(item: dict[str, Any], sample: dict[str, str]) -> bool:
    """Check a recall item against generic or path-qualified sample identity."""
    expected_path = _normalize_verification_path(sample.get("path", ""))
    if not expected_path:
        return _recall_item_matches_name(item, sample["name"])

    expected_name = sample.get("qualified_name", "").strip() or sample["name"]
    expected_repo = sample.get("repo", "").strip()
    expected_start = sample.get("start_line", "").strip()
    expected_end = sample.get("end_line", "").strip()
    text = _verification_text(item)
    sources = _verification_identity_sources(item)

    paths = {
        _normalize_verification_path(source.get("path"))
        for source in sources
        if source.get("path")
    }
    path_match = expected_path in paths or f"File: {expected_path}:" in text
    if not path_match:
        return False

    names = {
        str(source.get(key, "")).strip()
        for source in sources
        for key in ("qualified_name", "symbol_name", "name")
        if source.get(key)
    }
    name_match = expected_name in names or f"Qualified name: {expected_name}" in text
    if not name_match:
        return False

    if expected_start and expected_end:
        field_line_match = any(
            str(source.get("start_line", "")).strip() == expected_start
            and str(source.get("end_line", "")).strip() == expected_end
            for source in sources
        )
        text_line_match = f"{expected_path}:{expected_start}-{expected_end}" in text
        if not field_line_match and not text_line_match:
            return False

    repos = {
        str(source.get("repo", "")).strip()
        for source in sources
        if source.get("repo")
    }
    if expected_repo and repos and expected_repo not in repos:
        return False

    return True


def verify_embedding_recall(samples: list[dict[str, str]], sample_size: int = 10) -> dict[str, Any]:
    """Spot-check stored symbol entries by recalling them with their symbol name."""
    if not samples:
        return {
            "requested": sample_size,
            "checked": 0,
            "passed": 0,
            "failed": 0,
            "failures": [],
        }

    chosen = _select_verification_samples(samples, sample_size)
    failures: list[dict[str, str]] = []
    passed = 0

    for sample in chosen:
        name = sample["name"]
        problem = sample["problem"]
        query = _verification_query(sample)
        top_k = CODE_SYMBOL_VERIFICATION_TOP_K if sample.get("path") else 1
        try:
            result = _recall_http(query, k=top_k)
            items = _recall_items(result)
            if any(_recall_item_matches_sample(item, sample) for item in items):
                passed += 1
            else:
                failures.append({
                    "name": name,
                    "problem": problem,
                    "path": sample.get("path", ""),
                    "qualified_name": sample.get("qualified_name", ""),
                    "query": query,
                    "reason": "recall did not return matching entry",
                })
        except Exception as exc:
            failures.append({
                "name": name,
                "problem": problem,
                "path": sample.get("path", ""),
                "qualified_name": sample.get("qualified_name", ""),
                "query": query,
                "reason": str(exc),
            })

    return {
        "requested": sample_size,
        "checked": len(chosen),
        "passed": passed,
        "failed": len(failures),
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Python-specific knowledge extraction via AST
# ---------------------------------------------------------------------------

def extract_python_knowledge(filepath: Path, content: str) -> list[dict]:
    """Extract functional knowledge from a Python file using AST parsing.

    Returns a list of knowledge items, each with:
        problem: A question someone would ask about this code
        solution: The answer with details
        tags: Taxonomy tags for /memory
    """
    items: list[dict] = []
    rel_path = filepath.name  # Just filename for concise questions

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return items

    # Module-level docstring — most important knowledge
    module_doc = ast.get_docstring(tree)
    if module_doc and len(module_doc) > 20:
        items.append({
            "problem": f"What does {rel_path} do?",
            "solution": f"Module: {filepath}\n\n{module_doc[:2000]}",
            "tags": ["codebase", "module", filepath.stem],
        })
    else:
        # Always create a module-level entry (needed for edge matching)
        top_level = [n.name for n in ast.iter_child_nodes(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        if top_level:
            summary = f"Module: {filepath}\n\nDefines: {', '.join(top_level[:20])}"
            items.append({
                "problem": f"What does {rel_path} do?",
                "solution": summary,
                "tags": ["codebase", "module", filepath.stem],
            })

    # Classes with docstrings
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node) or ""
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            bases = [_name_from_node(b) for b in node.bases]
            if class_doc or len(methods) >= 3:
                desc = f"Class {node.name}"
                if bases:
                    desc += f" (inherits: {', '.join(bases)})"
                desc += f"\nMethods: {', '.join(methods[:15])}"
                if class_doc:
                    desc += f"\n\n{class_doc[:1000]}"
                items.append({
                    "problem": f"What is the {node.name} class in {rel_path}?",
                    "solution": f"File: {filepath}\n\n{desc}",
                    "tags": ["codebase", "class", node.name, filepath.stem],
                })

        # Top-level functions with docstrings (skip private helpers)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue  # Skip private functions
            func_doc = ast.get_docstring(node) or ""
            if not func_doc and node.col_offset > 0:
                continue  # Skip undocumented nested functions
            args = _extract_func_args(node)
            returns = _extract_return_annotation(node)
            desc = f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}({args})"
            if returns:
                desc += f" -> {returns}"
            if func_doc:
                desc += f"\n\n{func_doc[:800]}"
            if func_doc or node.col_offset == 0:
                items.append({
                    "problem": f"What does {node.name}() do in {rel_path}?",
                    "solution": f"File: {filepath}\n\n{desc}",
                    "tags": ["codebase", "function", node.name, filepath.stem],
                })

    return items


def _name_from_node(node) -> str:
    """Get name string from an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_name_from_node(node.value)}.{node.attr}"
    return "?"


def _extract_func_args(node) -> str:
    """Extract function argument signature."""
    args = []
    for arg in node.args.args:
        name = arg.arg
        if name == "self":
            continue
        ann = ""
        if arg.annotation:
            ann = f": {_name_from_node(arg.annotation)}"
        args.append(f"{name}{ann}")
    return ", ".join(args[:8])  # Cap at 8 args for readability


def _extract_return_annotation(node) -> str:
    """Extract return type annotation."""
    if node.returns:
        return _name_from_node(node.returns)
    return ""


# ---------------------------------------------------------------------------
# Generic knowledge extraction (non-Python files)
# ---------------------------------------------------------------------------

def extract_generic_knowledge(filepath: Path, content: str) -> list[dict]:
    """Extract knowledge from non-Python files using regex heuristics."""
    items: list[dict] = []
    lines = content.split("\n")

    # Look for file-level documentation comment blocks
    doc_lines = []
    for line in lines[:30]:  # First 30 lines
        stripped = line.strip()
        if stripped.startswith(("//", "#", "/*", "*", "///", "/**")):
            clean = re.sub(r'^[/*#\s]+', '', stripped).strip()
            if clean:
                doc_lines.append(clean)
        elif stripped and not stripped.startswith(("import ", "from ", "use ", "#include")):
            break

    if len(doc_lines) >= 2:
        doc = " ".join(doc_lines)[:1000]
        items.append({
            "problem": f"What does {filepath.name} do?",
            "solution": f"File: {filepath}\n\n{doc}",
            "tags": ["codebase", "module", filepath.stem],
        })

    # TypeScript/JavaScript: export function/class
    if filepath.suffix in (".ts", ".tsx", ".js", ".jsx"):
        for m in re.finditer(r'export\s+(?:default\s+)?(?:function|class|const)\s+(\w+)', content):
            items.append({
                "problem": f"What is {m.group(1)} in {filepath.name}?",
                "solution": f"File: {filepath}\nExported symbol: {m.group(1)}",
                "tags": ["codebase", "export", m.group(1), filepath.stem],
            })

    return items


# ---------------------------------------------------------------------------
# Markdown knowledge extraction (CONTEXT.md, MEMORY.md, README.md)
# ---------------------------------------------------------------------------

def extract_markdown_knowledge(filepath: Path, content: str) -> list[dict]:
    """Extract knowledge from markdown documentation files.

    These are the richest sources — CONTEXT.md, README.md, MEMORY.md contain
    architectural decisions, bug fixes, and operational knowledge.
    """
    items: list[dict] = []

    # Split by headers and create one item per section
    sections = re.split(r'^(#{1,3}\s+.+)$', content, flags=re.MULTILINE)

    current_header = filepath.stem  # Default to filename
    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue
        if re.match(r'^#{1,3}\s+', section):
            current_header = re.sub(r'^#{1,3}\s+', '', section).strip()
            continue
        # Skip very short sections
        if len(section) < 50:
            continue

        # Truncate very long sections
        body = section[:2000]
        items.append({
            "problem": f"What does '{current_header}' say in {filepath.name}?",
            "solution": f"File: {filepath}\nSection: {current_header}\n\n{body}",
            "tags": ["codebase", "documentation", filepath.stem, current_header.lower().replace(" ", "-")[:30]],
        })

    return items


# ---------------------------------------------------------------------------
# Phase 3: Relationship extraction via /treesitter → /memory add_edge
# ---------------------------------------------------------------------------

def find_treesitter_skill() -> Optional[Path]:
    """Find the treesitter skill run.sh script."""
    candidates = [
        Path(__file__).parent.parent / "treesitter" / "run.sh",
        Path.home() / ".pi" / "skills" / "treesitter" / "run.sh",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _normalize_symbol_kind(kind: str) -> Optional[str]:
    """Map treesitter symbol kinds onto the ingest-code tag vocabulary."""
    normalized = kind.lower()
    if normalized in {"function", "class", "method"}:
        return normalized
    return None


def _build_symbol_tags(kind: str, name: str, file_stem: str) -> list[str]:
    """Build the required code symbol tag set."""
    return ["codebase", "symbol", kind, name, file_stem]


def _extract_python_class_hierarchies(filepath: Path) -> dict[str, list[str]]:
    """Extract Python class base names keyed by class name."""
    try:
        content = filepath.read_text(errors="ignore")
        tree = ast.parse(content)
    except (SyntaxError, Exception):
        return {}

    hierarchies: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            hierarchies[node.name] = [_name_from_node(base) for base in node.bases]
    return hierarchies


def _format_import_summary(imports: list[dict]) -> str:
    """Render a compact import summary for symbol storage."""
    if not imports:
        return ""

    parts: list[str] = []
    for imp in imports[:20]:
        module = imp.get("module", "")
        names = imp.get("names", [])
        if names:
            parts.append(f"{module} ({', '.join(names[:5])})")
        else:
            parts.append(module)
    return ", ".join(part for part in parts if part)


def _flatten_import_symbols(imports: list[dict]) -> list[str]:
    """Flatten import metadata into lexical import symbols."""
    symbols: list[str] = []
    for imp in imports:
        module = imp.get("module", "")
        if module:
            symbols.append(module)
        for name in imp.get("names", []):
            if module:
                symbols.append(f"{module}.{name}")
            symbols.append(name)
    return sorted(set(symbols))


def _extract_symbol_context(filepath: Path) -> dict[str, Any]:
    """Extract per-file context used to enrich treesitter symbols."""
    if filepath.suffix != ".py":
        return {
            "imports": [],
            "import_summary": "",
            "class_hierarchies": {},
        }

    imports = extract_python_imports(filepath)
    return {
        "imports": imports,
        "import_summary": _format_import_summary(imports),
        "class_hierarchies": _extract_python_class_hierarchies(filepath),
    }


def _git_value(cwd: Path, args: list[str], default: str) -> str:
    """Return a git value for indexing metadata, falling back when unavailable."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            if value:
                return value
    except Exception:
        pass
    return default


def _current_branch(codebase_root: Path) -> str:
    return _git_value(codebase_root, ["rev-parse", "--abbrev-ref", "HEAD"], "unknown")


def _current_commit(codebase_root: Path) -> str:
    return _git_value(codebase_root, ["rev-parse", "HEAD"], "unknown")


def _language_for_path(filepath: Path) -> str:
    mapping = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
    }
    return mapping.get(filepath.suffix, filepath.suffix.lstrip(".") or "unknown")


def _relative_path(filepath: Path, codebase_root: Path) -> str:
    try:
        return filepath.resolve().relative_to(codebase_root.resolve()).as_posix()
    except ValueError:
        return filepath.as_posix()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _source_slice(filepath: Path, start_line: int, end_line: int) -> str:
    if start_line <= 0:
        return ""
    try:
        lines = filepath.read_text(errors="ignore").splitlines()
    except Exception:
        return ""
    if end_line < start_line:
        end_line = start_line
    return "\n".join(lines[start_line - 1 : end_line])


def _name_from_call(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_from_call(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _find_python_parent_symbol(tree: ast.AST, start_line: int, node: ast.AST) -> Optional[str]:
    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.ClassDef):
            continue
        candidate_start = getattr(candidate, "lineno", 0)
        candidate_end = getattr(candidate, "end_lineno", 0)
        if candidate_start <= start_line <= candidate_end and candidate is not node:
            return candidate.name
    return None


def _extract_python_symbol_details(
    filepath: Path,
    kind: str,
    name: str,
    start_line: int,
) -> dict[str, Any]:
    """Extract richer Python symbol details for memory-backed hybrid retrieval."""
    try:
        content = filepath.read_text(errors="ignore")
        tree = ast.parse(content)
    except (SyntaxError, Exception):
        return {}

    candidates: list[ast.AST] = []
    node_types: tuple[type, ...]
    if kind == "class":
        node_types = (ast.ClassDef,)
    else:
        node_types = (ast.FunctionDef, ast.AsyncFunctionDef)

    for node in ast.walk(tree):
        if isinstance(node, node_types) and getattr(node, "name", "") == name:
            candidates.append(node)

    if not candidates:
        return {}

    node = min(candidates, key=lambda candidate: abs(getattr(candidate, "lineno", 0) - start_line))
    parameters: list[str] = []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        parameters = [arg.arg for arg in node.args.args if arg.arg != "self"]

    local_variables: set[str] = set()
    called_symbols: set[str] = set()
    string_literals: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            local_variables.add(child.id)
        elif isinstance(child, ast.Call):
            call_name = _name_from_call(child.func)
            if call_name:
                called_symbols.add(call_name)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            literal = child.value.strip()
            if 1 < len(literal) <= 120:
                string_literals.add(literal)

    parent_symbol = _find_python_parent_symbol(tree, getattr(node, "lineno", start_line), node)
    return {
        "end_line": getattr(node, "end_lineno", start_line),
        "docstring": ast.get_docstring(node) or "",
        "parameters": sorted(parameters),
        "local_variables": sorted(local_variables),
        "called_symbols": sorted(called_symbols),
        "string_literals": sorted(string_literals),
        "parent_symbol": parent_symbol,
    }


def _build_code_symbol_record(
    symbol: dict[str, Any],
    filepath: Path,
    codebase_root: Path,
    scope: str,
    repo: str,
    branch: str,
    commit: str,
    imports: list[dict],
) -> Optional[CodeSymbolRecord]:
    raw_kind = symbol.get("kind", "")
    kind = _normalize_symbol_kind(raw_kind)
    name = symbol.get("name", "")
    if not kind or not name:
        return None

    start_line = int(symbol.get("start_line") or 0)
    end_line = int(symbol.get("end_line") or start_line)
    signature = symbol.get("signature", "") or ""
    docstring = symbol.get("docstring", "") or ""
    parent_symbol = symbol.get("parent_symbol") or symbol.get("parent") or ""
    parameters: list[str] = []
    local_variables: list[str] = []
    called_symbols: list[str] = []
    string_literals: list[str] = []

    if filepath.suffix == ".py":
        details = _extract_python_symbol_details(filepath, kind, name, start_line)
        end_line = int(details.get("end_line") or end_line)
        docstring = docstring or details.get("docstring", "")
        parent_symbol = parent_symbol or details.get("parent_symbol") or ""
        parameters = list(details.get("parameters", []))
        local_variables = list(details.get("local_variables", []))
        called_symbols = list(details.get("called_symbols", []))
        string_literals = list(details.get("string_literals", []))

    code = _source_slice(filepath, start_line, end_line)
    qualified_name = ".".join(part for part in [parent_symbol, name] if part)
    if not qualified_name:
        qualified_name = name

    rel_path = _relative_path(filepath, codebase_root)
    tags = _build_symbol_tags(kind, name, filepath.stem)
    tags.extend([
        "code_symbol",
        f"repo:{repo}",
        f"lang:{_language_for_path(filepath)}",
        f"path:{rel_path}",
    ])

    return CodeSymbolRecord(
        scope=scope,
        repo=repo,
        root=str(codebase_root.resolve()),
        branch=branch,
        commit=commit,
        path=rel_path,
        language=_language_for_path(filepath),
        symbol_kind=kind,
        symbol_name=name,
        qualified_name=qualified_name,
        start_line=start_line,
        end_line=end_line,
        signature=signature,
        docstring=docstring,
        code=code,
        imports=_flatten_import_symbols(imports),
        parameters=parameters,
        local_variables=local_variables,
        called_symbols=called_symbols,
        string_literals=string_literals,
        content_hash=_content_hash(code or signature or docstring or name),
        tags=tags,
    )


def _resolve_existing_scan_roots(codebase_path: Path, entries: Sequence[str]) -> list[Path]:
    """Resolve configured scan roots inside the codebase, preserving order."""
    codebase_root = codebase_path.resolve()
    roots: list[Path] = []
    seen: set[Path] = set()
    for entry in entries:
        raw = str(entry).strip()
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = codebase_root / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(codebase_root)
        except (OSError, ValueError):
            continue
        if resolved.is_dir() and resolved not in seen:
            roots.append(resolved)
            seen.add(resolved)
    return roots


def _extract_configured_scan_roots(codebase_path: Path) -> list[Path]:
    """Resolve scan roots from env override or .monitor-codebase.json include_dirs."""
    env_roots = os.environ.get(SCAN_INCLUDE_DIRS_ENV)
    if env_roots and env_roots.strip():
        return _resolve_existing_scan_roots(codebase_path, env_roots.split(","))

    config = _load_monitor_config(codebase_path)
    if config and config.get("include_dirs"):
        roots = _resolve_existing_scan_roots(codebase_path, config["include_dirs"])
        if roots:
            return roots
    return [codebase_path.resolve()]


def _configured_exclude_dirs(codebase_root: Path) -> tuple[str, ...]:
    """Return hardcoded and monitor-configured repository-relative exclusions."""
    entries: list[str] = sorted(SKIP_DIRS)
    config = _load_monitor_config(codebase_root)
    raw_entries = config.get("exclude_dirs", []) if isinstance(config, dict) else []
    if isinstance(raw_entries, list):
        for raw in raw_entries:
            if not isinstance(raw, str):
                continue
            entry = raw.strip().replace("\\", "/")
            if not entry:
                continue
            candidate = Path(entry)
            if candidate.is_absolute() or ".." in candidate.parts:
                continue
            entries.append(entry)

    return tuple(dict.fromkeys(entries))


def _path_is_excluded(path: Path, codebase_root: Path, exclude_dirs: Sequence[str]) -> bool:
    """Return whether a path is inside a configured repository exclusion."""
    root = codebase_root.resolve()

    try:
        lexical_path = Path(os.path.abspath(path))
        relative = lexical_path.relative_to(root)
    except (OSError, ValueError):
        return True

    directory_parts = relative.parts[:-1]
    for entry in exclude_dirs:
        entry_parts = Path(entry).parts
        if not entry_parts:
            continue

        if len(entry_parts) == 1:
            if entry_parts[0] in directory_parts:
                return True
        elif directory_parts[: len(entry_parts)] == entry_parts:
            return True

    return False


def _resolve_codebase_directory(path: Path) -> Path:
    """Return a canonical existing codebase directory or raise ValueError."""
    expanded = path.expanduser()
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"Codebase path does not exist or is inaccessible: {path}") from exc

    if not resolved.is_dir():
        raise ValueError(f"Codebase path is not a directory: {path}")

    return resolved


def _marker_path(path: Path) -> Path:
    """Return the canonical ingest-code marker path for a directory or marker path."""
    if path.name == ".ingest-code.json":
        return path
    return path / ".ingest-code.json"


def _write_ingest_marker(
    path: Path,
    files_scanned: int,
    knowledge_stored: int,
    cwe_stored: int,
    edges_stored: int,
    code_symbols_stored: int,
    treesitter: bool,
    scope: str,
    *,
    run_status: str = "complete",
    started_at: str | None = None,
    scan_roots: Sequence[str | Path] = (),
    completed_scan_roots: Sequence[str | Path] = (),
) -> Path:
    """Write the local ingest-code marker and return its path."""
    allowed_statuses = {"running", "complete", "failed"}
    if run_status not in allowed_statuses:
        raise ValueError(f"unsupported run_status: {run_status}")

    marker_path = _marker_path(path)
    codebase_root = marker_path.parent.resolve()
    timestamp = started_at or datetime.now().isoformat()
    completed = run_status == "complete"
    marker = {
        "ingested_at": timestamp,
        "started_at": timestamp,
        "path": str(codebase_root),
        "stem": codebase_root.name,
        "files_scanned": files_scanned,
        "knowledge_stored": knowledge_stored,
        "cwe_stored": cwe_stored,
        "edges_stored": edges_stored,
        "code_index": {
            "enabled": code_symbols_stored > 0,
            "backend": "memory",
            "collection": "code_symbols",
            "treesitter": bool(treesitter),
            "symbols_stored": code_symbols_stored,
            "lexical_terms": code_symbols_stored > 0,
            "line_ranges": code_symbols_stored > 0,
            "content_hashes": code_symbols_stored > 0,
            "hybrid_retrieval_capable": code_symbols_stored > 0,
        },
        "scope": scope,
        "run_status": run_status,
        "completed": completed,
        "scan_roots": [str(root) for root in scan_roots],
        "completed_scan_roots": [str(root) for root in completed_scan_roots],
    }
    tmp_path = marker_path.with_suffix(marker_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(marker, indent=2))
    tmp_path.replace(marker_path)
    return marker_path


def build_marker_status(path: Path) -> dict[str, Any]:
    """Read the ingest-code marker status without raising for missing or bad files."""
    marker_path = _marker_path(path)
    disabled_code_index = {"enabled": False}
    if not marker_path.exists():
        return {
            "status": "missing",
            "run_status": None,
            "completed": False,
            "scope": None,
            "scan_roots": [],
            "completed_scan_roots": [],
            "code_index": disabled_code_index,
        }

    try:
        payload = json.loads(marker_path.read_text())
    except (OSError, json.JSONDecodeError):
        payload = None

    if not isinstance(payload, dict):
        return {
            "status": "invalid",
            "run_status": None,
            "completed": False,
            "scope": None,
            "scan_roots": [],
            "completed_scan_roots": [],
            "code_index": disabled_code_index,
        }

    status = dict(payload)
    run_status = status.get("run_status") or "complete"
    if run_status == "complete":
        public_status = "fresh"
        completed = True
    elif run_status == "running":
        public_status = "running"
        completed = False
    elif run_status == "failed":
        public_status = "failed"
        completed = False
    else:
        public_status = "invalid"
        completed = False

    code_index = status.get("code_index")
    if not isinstance(code_index, dict):
        code_index = disabled_code_index

    status.update({
        "status": public_status,
        "run_status": run_status,
        "completed": completed,
        "scan_roots": status.get("scan_roots") if isinstance(status.get("scan_roots"), list) else [],
        "completed_scan_roots": (
            status.get("completed_scan_roots")
            if isinstance(status.get("completed_scan_roots"), list)
            else []
        ),
        "code_index": code_index,
    })
    return status


def _parse_treesitter_scan_output(stdout: str) -> list[dict[str, Any]]:
    """Parse treesitter scan output, skipping human summary lines."""
    payload = stdout.strip()
    if not payload:
        return []

    json_start = payload.find("[")
    if json_start < 0:
        return []

    try:
        data = json.loads(payload[json_start:])
    except json.JSONDecodeError:
        return []

    if isinstance(data, list):
        return data
    return []


def _resolve_treesitter_result_path(raw_path: object, scan_root: Path) -> Path | None:
    """Resolve one Tree-sitter result path and require scan-root containment."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None

    try:
        resolved_root = scan_root.resolve(strict=True)
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = resolved_root / candidate

        resolved_path = candidate.resolve(strict=True)
        resolved_path.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        return None

    return resolved_path if resolved_path.is_file() else None


def _store_treesitter_symbols_for_directory(
    directory: Path,
    codebase_root: Path,
    scope: str,
    verification_samples: Optional[list[dict[str, str]]] = None,
    *,
    mtime_after: datetime | None = None,
) -> int:
    """Scan one configured directory and upsert structured code symbols to memory."""
    treesitter_script = find_treesitter_skill()
    if not treesitter_script:
        print(f"Treesitter skill not found for {directory}", file=sys.stderr, flush=True)
        return 0

    try:
        resolved_directory = directory.resolve(strict=True)
        resolved_codebase_root = codebase_root.resolve(strict=True)
        resolved_directory.relative_to(resolved_codebase_root)
    except (OSError, RuntimeError, ValueError):
        print(
            f"Treesitter scan root is outside codebase or unavailable: {directory}",
            file=sys.stderr,
            flush=True,
        )
        return 0

    if not resolved_directory.is_dir():
        print(f"Treesitter scan root is not a directory: {directory}", file=sys.stderr, flush=True)
        return 0

    cmd = [
        "bash",
        str(treesitter_script),
        "scan",
        str(resolved_directory),
    ]

    for pattern in DEFAULT_GLOB_PATTERNS:
        cmd.extend(["--include", f"**/{pattern}"])
    for skip_dir in sorted(SKIP_DIRS):
        cmd.extend(["--exclude", f"**/{skip_dir}/**"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(treesitter_script.parent),
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
    except subprocess.TimeoutExpired:
        print(f"Treesitter scan timed out for {directory}", file=sys.stderr, flush=True)
        return 0

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            print(f"Treesitter scan failed for {directory}: {stderr}", file=sys.stderr, flush=True)
        return 0

    scan_results = _parse_treesitter_scan_output(result.stdout)
    if not scan_results:
        return 0

    repo = resolved_codebase_root.name
    branch = _current_branch(resolved_codebase_root)
    commit = _current_commit(resolved_codebase_root)
    exclude_dirs = _configured_exclude_dirs(resolved_codebase_root)
    records: list[CodeSymbolRecord] = []
    for file_entry in scan_results:
        file_path_raw = file_entry.get("path")
        if isinstance(file_path_raw, str):
            lexical_path = Path(file_path_raw)
            if not lexical_path.is_absolute():
                lexical_path = resolved_directory / lexical_path
            if _path_is_excluded(lexical_path, resolved_codebase_root, exclude_dirs):
                continue

        filepath = _resolve_treesitter_result_path(file_path_raw, resolved_directory)
        if filepath is None:
            print(
                f"  [WARN] Skipping Tree-sitter result outside scan root: {file_path_raw}",
                file=sys.stderr,
                flush=True,
            )
            continue
        if _path_is_excluded(filepath, resolved_codebase_root, exclude_dirs):
            continue
        if not _path_modified_at_or_after(filepath, mtime_after):
            continue

        symbol_context = _extract_symbol_context(filepath)

        for symbol in file_entry.get("symbols", []):
            record = _build_code_symbol_record(
                symbol=symbol,
                filepath=filepath,
                codebase_root=resolved_codebase_root,
                scope=scope,
                repo=repo,
                branch=branch,
                commit=commit,
                imports=symbol_context["imports"],
            )
            if record is None:
                continue
            records.append(record)

    result = CodeMemoryClient().upsert_code_symbols(records)
    for error in result.errors[:5]:
        print(f"  [WARN] {error}", file=sys.stderr, flush=True)

    if verification_samples is not None:
        for record in result.stored_records:
            verification_samples.append(_code_symbol_verification_sample(record))

    return result.stored


def _treesitter_query(run_sh: Path, filepath: Path, query: str) -> list[dict]:
    """Run a tree-sitter query and return captures."""
    try:
        result = subprocess.run(
            ["bash", str(run_sh), "query", str(filepath), query,
             "--output", "/dev/stdout"],
            capture_output=True, text=True, timeout=15,
            cwd=str(run_sh.parent),
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass
    return []


def extract_python_imports(filepath: Path) -> list[dict]:
    """Extract import relationships from a Python file using AST (fast, no treesitter needed)."""
    try:
        content = filepath.read_text(errors="ignore")
        tree = ast.parse(content)
    except (SyntaxError, Exception):
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append({
                "module": node.module,
                "names": [alias.name for alias in node.names],
                "line": node.lineno,
            })
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "module": alias.name,
                    "names": [],
                    "line": node.lineno,
                })
    return imports


def build_module_index(files: list[Path], codebase_root: Path) -> dict[str, Path]:
    """Build a mapping from Python module dotted path → file path."""
    index: dict[str, Path] = {}
    for fp in files:
        if fp.suffix != ".py":
            continue
        try:
            rel = fp.relative_to(codebase_root)
        except ValueError:
            continue
        # Convert path to module: src/extractor/pipeline/steps/s05.py → src.extractor.pipeline.steps.s05
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1].replace(".py", "")
        dotted = ".".join(parts)
        index[dotted] = fp
        # Also index without common prefixes (src.extractor → extractor)
        for i in range(1, len(parts)):
            index[".".join(parts[i:])] = fp
    return index


def extract_edges(
    files: list[Path],
    codebase_root: Path,
    treesitter_sh: Optional[Path] = None,
) -> list[dict]:
    """Extract import-based dependency edges between files in the codebase.

    Returns list of {from_file, to_file, edge_type, module, names}.
    Only includes edges where both files are in the scanned codebase.
    """
    module_index = build_module_index(files, codebase_root)
    edges: list[dict] = []

    for filepath in files:
        if filepath.suffix != ".py":
            continue
        imports = extract_python_imports(filepath)
        for imp in imports:
            module = imp["module"]
            # Try to resolve to a file in this codebase
            target = module_index.get(module)
            if not target or target == filepath:
                continue  # External dep or self-import
            edges.append({
                "from_file": str(filepath),
                "to_file": str(target),
                "edge_type": "depends_on",
                "module": module,
                "names": imp.get("names", []),
            })

    return edges


def store_edges(edges: list[dict], scope: str = "code", dry_run: bool = False, monitor=None) -> int:
    """Store dependency edges in /memory via batch HTTP endpoint."""
    if dry_run:
        stored = 0
        for edge in edges:
            from_name = Path(edge["from_file"]).name
            to_name = Path(edge["to_file"]).name
            names = ", ".join(edge.get("names", [])[:3])
            print(f"  [EDGE] {from_name} → {to_name} (imports {names})")
            stored += 1
            if monitor:
                monitor.update(1, item=f"{from_name}→{to_name}")
        return stored

    # Build batch payload — use empty scope so add_edge matches any scope
    # (lessons may be stored as scope="code" or scope="extractor")
    batch = []
    for edge in edges:
        from_name = Path(edge["from_file"]).name
        to_name = Path(edge["to_file"]).name
        batch.append({
            "from_title": f"What does {from_name} do?",
            "to_title": f"What does {to_name} do?",
            "type": edge["edge_type"],
            "from_scope": "",
            "to_scope": "",
            "weight": 0.8,
            "rationale": f"import: {edge['module']}",
        })

    result = CodeMemoryClient().add_edges(batch)
    if monitor:
        monitor.update(result.attempted, item=f"{result.stored} edges stored")
    for error in result.errors[:5]:
        print(f"  [WARN] {error}", flush=True)
    return result.stored


# ---------------------------------------------------------------------------
# Main scan pipeline
# ---------------------------------------------------------------------------

def _load_monitor_config(codebase_path: Path) -> Optional[dict]:
    """Load .monitor-codebase.json if present."""
    config_file = codebase_path / ".monitor-codebase.json"
    if config_file.exists():
        try:
            return json.loads(config_file.read_text())
        except Exception:
            pass
    return None


def _is_git_repo(path: Path) -> bool:
    """Check if path is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(path),
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _git_ls_files(codebase_path: Path, patterns: list[str]) -> list[Path]:
    """Use git ls-files to get tracked files (respects .gitignore)."""
    # Build set of extensions from patterns like "*.py" -> ".py"
    extensions = set()
    for pattern in patterns:
        if pattern.startswith("*."):
            extensions.add(pattern[1:])  # "*.py" -> ".py"

    files = []
    try:
        # Get all tracked + untracked-but-not-ignored files
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(codebase_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line:
                    path = codebase_path / line
                    # Filter by extension
                    if path.suffix in extensions:
                        files.append(path)
    except Exception:
        pass
    return files


def _path_is_within_scan_roots(path: Path, scan_roots: Sequence[Path]) -> bool:
    """Return whether a candidate file lives under one configured scan root."""
    try:
        resolved_path = path.resolve()
    except OSError:
        return False
    for root in scan_roots:
        try:
            resolved_path.relative_to(root.resolve())
        except ValueError:
            continue
        return True
    return False


def _path_modified_at_or_after(path: Path, threshold: datetime | None) -> bool:
    """Return whether a path mtime is at or after a threshold."""
    if threshold is None:
        return True

    try:
        return path.stat().st_mtime >= threshold.timestamp()
    except (OSError, OverflowError, ValueError):
        return False


def collect_files(codebase_path: Path, patterns: list[str], mtime_after: Optional[datetime] = None) -> list[Path]:
    """Collect files matching patterns, respecting .gitignore and .monitor-codebase.json."""
    files: list[Path] = []
    codebase_root = codebase_path.resolve()
    exclude_dirs = _configured_exclude_dirs(codebase_root)

    # Determine scan roots — either scoped dirs or full codebase
    scan_roots = _extract_configured_scan_roots(codebase_root)

    # Use git ls-files if in a git repo (respects .gitignore)
    use_git = _is_git_repo(codebase_root)

    if use_git:
        for f in _git_ls_files(codebase_root, patterns):
            if not _path_is_within_scan_roots(f, scan_roots):
                continue
            if _path_is_excluded(f, codebase_root, exclude_dirs):
                continue
            if not _path_modified_at_or_after(f, mtime_after):
                continue
            files.append(f)
    else:
        for root in scan_roots:
            # Fallback to rglob for non-git directories
            for pattern in patterns:
                for f in root.rglob(pattern):
                    if _path_is_excluded(f, codebase_root, exclude_dirs):
                        continue
                    if not _path_modified_at_or_after(f, mtime_after):
                        continue
                    files.append(f)

    # Also include markdown docs at project root (always)
    for md_name in ["CONTEXT.md", "README.md", "CLAUDE.md", "MEMORY.md", "AGENTS.md"]:
        md_path = codebase_root / md_name
        if md_path.exists() and _path_modified_at_or_after(md_path, mtime_after) and md_path not in files:
            files.append(md_path)
    # Recurse for local/docs/*.md and local/*.md
    for local_dir in [codebase_root / "local" / "docs", codebase_root / "local"]:
        if local_dir.exists():
            for md in local_dir.glob("*.md"):
                if _path_modified_at_or_after(md, mtime_after) and md not in files:
                    files.append(md)
    docs_dir = codebase_root / "docs"
    if docs_dir.exists():
        for md in docs_dir.glob("*.md"):
            if _path_modified_at_or_after(md, mtime_after) and md not in files:
                files.append(md)

    return sorted(set(files))


def enrich_with_taxonomy(items: list[dict], taxonomy_module) -> list[dict]:
    """Run /taxonomy on each knowledge item to add bridge_tags + collection_tags.

    Uses fast=True keyword mode (~10ms/call, no LLM). Merges taxonomy tags
    into the item's existing tags list so ArangoSearch can index them.
    """
    if not taxonomy_module or not items:
        return items

    extract_fn = getattr(taxonomy_module, "extract_taxonomy", None)
    if not extract_fn:
        return items

    for item in items:
        try:
            # Taxonomy on the solution text (richer than the problem/question)
            text = item.get("solution", "")[:3000]
            result = extract_fn(text, collection="operational", fast=True)
            bridge = result.get("bridge_tags", [])
            collection = result.get("collection_tags", {})
            # Flatten collection_tags dict values into a list
            coll_flat = []
            for tag_list in collection.values():
                if isinstance(tag_list, list):
                    coll_flat.extend(tag_list)
                elif isinstance(tag_list, str):
                    coll_flat.append(tag_list)
            # Merge into existing tags (deduplicate)
            existing = set(item.get("tags", []))
            existing.update(bridge)
            existing.update(coll_flat)
            item["tags"] = list(existing)
        except Exception:
            pass  # Keep original tags on failure

    return items


def extract_knowledge(filepath: Path) -> list[dict]:
    """Extract functional knowledge from any file type."""
    try:
        content = filepath.read_text(errors="ignore")
    except Exception:
        return []

    # Markdown documentation
    if filepath.suffix in (".md", ".mdx"):
        return extract_markdown_knowledge(filepath, content)

    # Python
    if filepath.suffix == ".py":
        return extract_python_knowledge(filepath, content)

    # TypeScript, JavaScript, etc.
    return extract_generic_knowledge(filepath, content)


cli = typer.Typer(help="Ingest codebases into /memory for knowledge extraction and CWE scanning.")


@cli.command()
def scan(
    path: Path = typer.Argument(help="Codebase path to scan"),
    glob: list[str] = typer.Option([], "-g", "--glob", help="File patterns to scan"),
    cwe_only: bool = typer.Option(False, "--cwe-only", help="Only scan for CWEs (legacy mode)"),
    validate: bool = typer.Option(False, "--validate/--no-validate", help="Run LLM validation on CWEs"),
    treesitter: bool = typer.Option(False, "--treesitter", help="Run treesitter scan for structured code symbols"),
    code_index: bool = typer.Option(True, "--code-index/--no-code-index", help="Upsert treesitter symbols to memory code_symbols"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be stored without writing"),
    scope: str = typer.Option("code", help="Memory scope for storage"),
    batch_size: int = typer.Option(50, help="Files per batch"),
):
    """Scan a codebase for functional knowledge and CWE mappings, store in /memory."""
    try:
        path = _resolve_codebase_directory(path)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc

    taxonomy = load_taxonomy_module()
    memory_script = find_memory_skill()

    if not memory_script and not dry_run:
        print('{"error": "Memory skill not found"}', file=sys.stderr)
        raise SystemExit(1)

    # Collect files
    patterns = list(glob) if glob else DEFAULT_GLOB_PATTERNS
    files = collect_files(path, patterns)
    print(f"Found {len(files)} files to scan in {path}", flush=True)

    # --- Phase 1: Functional knowledge extraction ---
    knowledge_stored = 0
    knowledge_total = 0

    if not cwe_only:
        print("\n--- Phase 1: Extracting functional knowledge ---", flush=True)
        failed = 0

        # Phase 1a: Extract all knowledge items (CPU-bound, fast)
        all_items: list[dict] = []
        file_iter = Monitor(files, name="ingest-code-extract", desc="Extracting knowledge", total=len(files)) if Monitor else files
        for filepath in file_iter:
            items = extract_knowledge(filepath)
            all_items.extend(items)
        knowledge_total = len(all_items)
        print(f"  Extracted {knowledge_total} knowledge items from {len(files)} files", flush=True)

        # Phase 1a½: Enrich with taxonomy bridge tags (fast keyword mode, ~10ms/item)
        if taxonomy:
            all_items = enrich_with_taxonomy(all_items, taxonomy)
            print(f"  Enriched {knowledge_total} items with taxonomy bridge tags", flush=True)

        if dry_run:
            for item in all_items:
                print(f"  [K] {item['problem']}")
        else:
            # Phase 1b: Store via threaded HTTP learns (I/O-bound, GPU embedding)
            workers = int(os.environ.get("INGEST_WORKERS", "8"))
            _lock = threading.Lock()

            def _learn_item(item: dict) -> bool:
                return _learn(
                    memory_script, item["problem"], item["solution"],
                    scope, item["tags"],
                )

            print(f"  Storing with {workers} threads...", flush=True)
            store_monitor = Monitor(None, name="ingest-code-store", desc="Storing to memory", total=knowledge_total) if Monitor else None
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_learn_item, item): i for i, item in enumerate(all_items)}
                done_count = 0
                for future in as_completed(futures):
                    done_count += 1
                    if future.result():
                        with _lock:
                            knowledge_stored += 1
                    else:
                        with _lock:
                            failed += 1
                        if store_monitor:
                            store_monitor.fail()
                    if store_monitor:
                        store_monitor.update(1, item=f"{knowledge_stored} stored")
                    if done_count % 100 == 0:
                        print(f"  Progress: {knowledge_stored} stored, {failed} blocked, {done_count}/{knowledge_total} done", flush=True)
            if store_monitor:
                store_monitor._update(final=True)

        print(f"Knowledge: {knowledge_stored} stored of {knowledge_total} extracted ({failed} blocked)", flush=True)

    # --- Phase 2: CWE scanning ---
    total_cwes = 0
    cwe_stored = 0
    files_with_cwes = 0
    cwe_summary: dict[str, int] = {}

    if taxonomy:
        print("\n--- Phase 2: CWE scanning ---", flush=True)
        cwe_files = [f for f in files if f.suffix not in (".md", ".mdx")]
        cwe_monitor = Monitor(None, name="ingest-code-cwe", desc="CWE scanning", total=len(cwe_files)) if Monitor else None
        scanned = 0

        for i in range(0, len(cwe_files), batch_size):
            batch = cwe_files[i:i + batch_size]
            for filepath in batch:
                result = scan_file_cwe(filepath, taxonomy, validate)
                scanned += 1
                cwes = result.get("cwe_mappings", [])
                if cwes:
                    files_with_cwes += 1
                    total_cwes += len(cwes)
                    for cwe in cwes:
                        cwe_id = cwe.get("cwe_id", "unknown")
                        cwe_summary[cwe_id] = cwe_summary.get(cwe_id, 0) + 1
                        if dry_run:
                            print(f"  [CWE] {filepath.name}: {cwe_id}", flush=True)
                        elif memory_script:
                            cwe_name = cwe.get("name", "")
                            category = cwe.get("category", "")
                            tags = ["ingest-code", "cwe", cwe_id, category, filepath.suffix.lstrip(".")]
                            ok = _learn(
                                memory_script,
                                f"What CWEs are relevant to {filepath.name}?",
                                f"{cwe_id} ({cwe_name}) - Category: {category}. File: {filepath}",
                                scope, tags,
                            )
                            if ok:
                                cwe_stored += 1
                if cwe_monitor:
                    cwe_monitor.update(1, item=filepath.name)
                if scanned % 100 == 0:
                    print(f"  Progress: {scanned} scanned, {total_cwes} CWEs in {files_with_cwes} files", flush=True)

        if cwe_monitor:
            cwe_monitor._update(final=True)
        print(f"CWEs: {cwe_stored} stored, {total_cwes} found in {files_with_cwes} files", flush=True)
    else:
        print("Taxonomy module not found — skipping CWE scan (knowledge extraction still runs)", flush=True)

    # --- Phase 3: Relationship extraction (import graph edges) ---
    edges_stored = 0
    edges_total = 0

    if not cwe_only:
        print("\n--- Phase 3: Extracting code relationships ---", flush=True)
        edges = extract_edges(files, path)
        edges_total = len(edges)
        print(f"  Found {edges_total} internal dependency edges", flush=True)
        if edges_total > 0:
            edge_monitor = Monitor(None, name="ingest-code-edges", desc="Storing edges", total=edges_total) if Monitor else None
            edges_stored = store_edges(edges, scope=scope, dry_run=dry_run, monitor=edge_monitor)
            if edge_monitor:
                edge_monitor._update(final=True)
            print(f"Edges: {edges_stored} stored of {edges_total} found", flush=True)

    # --- Phase 4: Structured code symbol index ---
    code_symbols_stored = 0
    code_symbol_scan_roots: list[Path] = []
    completed_code_symbol_scan_roots: list[Path] = []
    if treesitter and code_index and not cwe_only:
        print("\n--- Phase 4: Upserting structured code symbols ---", flush=True)
        if dry_run:
            print("  [DRY RUN] treesitter code_symbols upsert skipped", flush=True)
        else:
            verification_samples: list[dict[str, str]] = []
            code_symbol_scan_roots = _extract_configured_scan_roots(path)
            for scan_root in code_symbol_scan_roots:
                root_stored = _store_treesitter_symbols_for_directory(
                    scan_root,
                    path,
                    scope,
                    verification_samples=verification_samples,
                )
                code_symbols_stored += root_stored
                completed_code_symbol_scan_roots.append(scan_root)
                print(f"Code index: {root_stored} symbols stored from {scan_root}", flush=True)

    # Output summary
    result = {
        "files_scanned": len(files),
        "knowledge_extracted": knowledge_total,
        "knowledge_stored": knowledge_stored,
        "files_with_cwes": files_with_cwes,
        "total_cwe_mappings": total_cwes,
        "cwe_stored": cwe_stored,
        "cwe_summary": cwe_summary,
        "edges_found": edges_total,
        "edges_stored": edges_stored,
        "code_symbols_stored": code_symbols_stored,
        "dry_run": dry_run,
    }
    print(f"\n{json.dumps(result, indent=2)}")

    # --- Write marker file + store ingestion record in /memory ---
    if not dry_run:
        try:
            marker_path = _write_ingest_marker(
                path,
                files_scanned=len(files),
                knowledge_stored=knowledge_stored,
                cwe_stored=cwe_stored,
                edges_stored=edges_stored,
                code_symbols_stored=code_symbols_stored,
                treesitter=treesitter,
                scope=scope,
                scan_roots=code_symbol_scan_roots,
                completed_scan_roots=completed_code_symbol_scan_roots,
            )
            print(f"\nMarker written: {marker_path}")
        except Exception as e:
            print(f"Warning: Could not write marker file: {e}", file=sys.stderr)

        # Store ingestion record in /memory for discoverability
        ingested_at = datetime.now().isoformat()
        _learn_http(
            problem=f"Has codebase {path.resolve().name} been indexed for semantic search?",
            solution=f"Yes, indexed on {ingested_at}. {knowledge_stored} lessons, {code_symbols_stored} code symbols, {cwe_stored} CWEs. Path: {path.resolve()}",
            scope="system",
            tags=["ingest-code", "indexed-codebase", path.resolve().name, str(path.resolve())],
        )


@cli.command()
def rescan(
    since: Optional[str] = typer.Option(None, help="Only files modified since (ISO date or '1d', '7d', etc.)"),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Run LLM validation"),
    treesitter: bool = typer.Option(False, "--treesitter", help="Run treesitter scan for symbol extraction"),
    code_index: bool = typer.Option(True, "--code-index/--no-code-index", help="Upsert treesitter symbols to memory code_symbols"),
    verify_embeddings: bool = typer.Option(False, "--verify-embeddings", help="Spot-check recalled embeddings for stored symbols"),
    scope: str = typer.Option("code", help="Memory scope for storage"),
    codebase: list[str] = typer.Option([], "-c", "--codebase", help="Codebase paths to rescan"),
):
    """Nightly rescan for living document updates. Designed for /scheduler."""
    mtime_threshold = None
    if since:
        if since.endswith("d"):
            mtime_threshold = datetime.now() - timedelta(days=int(since[:-1]))
        elif since.endswith("h"):
            mtime_threshold = datetime.now() - timedelta(hours=int(since[:-1]))
        else:
            mtime_threshold = datetime.fromisoformat(since)

    codebases = list(codebase) if codebase else []
    if not codebases:
        common = Path.home() / "workspace"
        if common.exists():
            codebases = [str(common)]

    if not codebases:
        print('{"error": "No codebases specified"}', file=sys.stderr)
        raise SystemExit(1)

    resolved_codebases: list[Path] = []
    for raw_codebase in codebases:
        try:
            resolved_codebases.append(_resolve_codebase_directory(Path(raw_codebase)))
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            raise SystemExit(2) from exc

    print(f"Rescanning {len(resolved_codebases)} codebase(s)")
    if mtime_threshold:
        print(f"Only files modified since: {mtime_threshold.isoformat()}")

    memory_script = find_memory_skill()
    if not memory_script:
        print('{"error": "Memory skill not found"}', file=sys.stderr)
        raise SystemExit(1)

    taxonomy = load_taxonomy_module()
    total_knowledge = 0
    total_cwes = 0
    total_ts_symbols = 0
    verifiable_samples: list[dict[str, str]] = []
    pending_markers: list[dict[str, Any]] = []

    for path in resolved_codebases:
        files = collect_files(path, DEFAULT_GLOB_PATTERNS, mtime_after=mtime_threshold)
        print(f"Found {len(files)} files in {path}")
        codebase_knowledge = 0
        codebase_cwes = 0
        codebase_ts_symbols = 0
        code_symbol_scan_roots: list[Path] = []
        completed_code_symbol_scan_roots: list[Path] = []

        for filepath in files:
            # Knowledge extraction
            for item in extract_knowledge(filepath):
                if _learn(memory_script, item["problem"], item["solution"], scope, item["tags"]):
                    total_knowledge += 1
                    codebase_knowledge += 1
                    verify_name = _extract_verification_name(item["tags"])
                    if verify_name:
                        verifiable_samples.append({
                            "name": verify_name,
                            "problem": item["problem"],
                        })

            # CWE scanning
            if taxonomy and filepath.suffix not in (".md", ".mdx"):
                result = scan_file_cwe(filepath, taxonomy, validate)
                for cwe in result.get("cwe_mappings", []):
                    cwe_id = cwe.get("cwe_id", "unknown")
                    tags = ["ingest-code", "cwe", cwe_id, filepath.suffix.lstrip(".")]
                    if _learn(memory_script, f"What CWEs are relevant to {filepath.name}?",
                              f"{cwe_id} ({cwe.get('name', '')}) - File: {filepath}", scope, tags):
                        total_cwes += 1
                        codebase_cwes += 1

        # Treesitter symbol extraction (per codebase, not per file)
        if treesitter and code_index:
            code_symbol_scan_roots = _extract_configured_scan_roots(path)
            for scan_root in code_symbol_scan_roots:
                root_stored = _store_treesitter_symbols_for_directory(
                    scan_root,
                    path,
                    scope,
                    verification_samples=verifiable_samples,
                    mtime_after=mtime_threshold,
                )
                codebase_ts_symbols += root_stored
                completed_code_symbol_scan_roots.append(scan_root)
                print(f"Treesitter: {root_stored} symbols stored from {scan_root}", flush=True)
            total_ts_symbols += codebase_ts_symbols

        pending_markers.append({
            "path": path,
            "files_scanned": len(files),
            "knowledge_stored": codebase_knowledge,
            "cwe_stored": codebase_cwes,
            "code_symbols_stored": codebase_ts_symbols,
            "scan_roots": code_symbol_scan_roots,
            "completed_scan_roots": completed_code_symbol_scan_roots,
        })

    verification_result = None
    if verify_embeddings:
        verification_result = verify_embedding_recall(verifiable_samples, sample_size=10)
        print(json.dumps({
            "embedding_verification": verification_result,
        }, indent=2))
        if verification_result["failed"] > 0:
            raise SystemExit(1)

    for marker in pending_markers:
        try:
            marker_path = _write_ingest_marker(
                marker["path"],
                files_scanned=marker["files_scanned"],
                knowledge_stored=marker["knowledge_stored"],
                cwe_stored=marker["cwe_stored"],
                edges_stored=0,
                code_symbols_stored=marker["code_symbols_stored"],
                treesitter=treesitter,
                scope=scope,
                scan_roots=marker["scan_roots"],
                completed_scan_roots=marker["completed_scan_roots"],
            )
            print(f"Marker written: {marker_path}", flush=True)
        except Exception as e:
            print(f"Warning: Could not write marker file: {e}", file=sys.stderr)

    print(json.dumps({
        "codebases_scanned": len(resolved_codebases),
        "knowledge_stored": total_knowledge,
        "cwe_stored": total_cwes,
        "treesitter_symbols": total_ts_symbols,
        "since": since,
        "embedding_verification": verification_result,
    }, indent=2))


if __name__ == "__main__":
    cli()
