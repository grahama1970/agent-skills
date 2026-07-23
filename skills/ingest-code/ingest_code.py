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
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, Optional, Sequence

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
    "*.rs", "*.go", "*.java", "*.ts", "*.tsx", "*.js", "*.jsx",
    "*.rb", "*.php", "*.swift", "*.kt", "*.scala"
]
EXPLICIT_ROOT_DOC_STEMS = (
    "CONTEXT",
    "README",
    "CLAUDE",
    "MEMORY",
    "AGENTS",
)
EXPLICIT_MARKDOWN_SUFFIXES = (
    ".md",
    ".mdx",
)
EXPLICIT_MARKDOWN_GLOBS = (
    "*.md",
    "*.mdx",
)

# Skip patterns — dirs that are never useful
SKIP_DIRS = {
    ".venv", "venv", "node_modules", "__pycache__", ".git", ".tox",
    "dist", "build", "egg-info", ".eggs", ".mypy_cache", ".pytest_cache",
    "site-packages", ".uv",
}

MEMORY_SOCKET_PATH = "/run/user/1000/embry/memory.sock"
SCAN_INCLUDE_DIRS_ENV = "CODE_SYMBOLS_SCAN_INCLUDE_DIRS"
INGEST_WORKERS_ENV = "INGEST_WORKERS"
DEFAULT_INGEST_WORKERS = 8
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


class TreeSitterScanError(RuntimeError):
    """Tree-sitter extraction or persistence did not complete."""


class ScanConfigError(ValueError):
    """The repository-local ingest scan configuration is invalid."""


class FileDiscoveryError(RuntimeError):
    """The codebase file set could not be determined safely."""


class RescanSinceError(ValueError):
    """The rescan --since value is invalid."""


class ScanBatchSizeError(ValueError):
    """The scan --batch-size value is invalid."""


class IngestWorkersError(ValueError):
    """The INGEST_WORKERS override is invalid."""


class ScanGlobError(ValueError):
    """An explicit scan --glob value is invalid."""

    def __init__(self, pattern: str, index: int) -> None:
        self.pattern = pattern
        self.index = index
        super().__init__(
            f"--glob entry {index + 1} is not a safe "
            f"repository-relative pattern: {pattern!r}"
        )


class MemoryScopeError(ValueError):
    """The ingest-code memory scope is invalid."""


def _validate_memory_scope(scope: object) -> str:
    """Return a normalized nonblank memory scope."""
    if not isinstance(scope, str):
        raise MemoryScopeError("--scope must be a nonblank string")

    normalized = scope.strip()
    if not normalized:
        raise MemoryScopeError("--scope must be a nonblank string")

    return normalized


def _exit_invalid_memory_scope(scope: object, exc: MemoryScopeError) -> NoReturn:
    print(
        json.dumps({
            "error": "Invalid memory scope",
            "scope": scope,
            "detail": str(exc),
        }),
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


class SourceReadError(RuntimeError):
    """A discovered source file could not be read."""

    def __init__(self, filepath: Path, detail: str) -> None:
        self.filepath = filepath
        super().__init__(f"Could not read discovered source file {filepath}: {detail}")


class CweScanResultError(RuntimeError):
    """The local CWE scanner returned an invalid result."""

    def __init__(self, filepath: Path, location: str, detail: str) -> None:
        self.filepath = filepath
        self.location = location
        super().__init__(f"Invalid CWE result at {location} for {filepath}: {detail}")


class TaxonomyEnrichmentError(RuntimeError):
    """Taxonomy enrichment failed or returned an invalid result."""

    def __init__(self, *, item_index: int, problem: str, detail: str) -> None:
        self.item_index = item_index
        self.problem = problem[:160]
        super().__init__(f"Taxonomy enrichment failed for item {item_index}: {detail}")


class KnowledgeItemError(RuntimeError):
    """A functional-knowledge extractor returned invalid output."""

    def __init__(
        self,
        *,
        filepath: Path,
        item_index: int,
        location: str,
        detail: str,
    ) -> None:
        self.filepath = filepath
        self.item_index = item_index
        self.location = location
        super().__init__(
            f"Invalid knowledge result at {location} for {filepath}: {detail}"
        )


def _read_source_text(filepath: Path) -> str:
    """Read source text or raise a path-qualified failure."""
    try:
        return filepath.read_text(errors="ignore")
    except (OSError, UnicodeError) as exc:
        raise SourceReadError(filepath, str(exc)) from exc


def _exit_source_read_failure(
    *,
    codebase: Path,
    phase: str,
    exc: SourceReadError,
) -> NoReturn:
    print(
        json.dumps({
            "error": "Source file read failed",
            "phase": phase,
            "codebase": str(codebase),
            "file": str(exc.filepath),
            "detail": str(exc),
        }),
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


def _exit_cwe_result_failure(*, codebase: Path, exc: CweScanResultError) -> NoReturn:
    """Emit the structured CLI error for invalid CWE scanner results."""
    print(
        json.dumps({
            "error": "CWE scan result invalid",
            "phase": "cwe",
            "codebase": str(codebase),
            "file": str(exc.filepath),
            "location": exc.location,
            "detail": str(exc),
        }),
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


def _exit_taxonomy_enrichment_failure(
    *,
    codebase: Path,
    exc: TaxonomyEnrichmentError,
) -> NoReturn:
    """Emit the structured CLI error for invalid taxonomy enrichment results."""
    print(
        json.dumps({
            "error": "Taxonomy enrichment failed",
            "phase": "taxonomy_enrichment",
            "codebase": str(codebase),
            "item_index": exc.item_index,
            "problem": exc.problem,
            "detail": str(exc),
        }),
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


def _exit_knowledge_item_failure(
    *,
    codebase: Path,
    exc: KnowledgeItemError,
) -> NoReturn:
    """Emit the structured CLI error for invalid knowledge extractor results."""
    print(
        json.dumps({
            "error": "Functional knowledge result invalid",
            "phase": "knowledge",
            "codebase": str(codebase),
            "file": str(exc.filepath),
            "item_index": exc.item_index,
            "location": exc.location,
            "detail": str(exc),
        }),
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


def _validate_cwe_scan_result(filepath: Path, result: object) -> dict[str, Any]:
    """Validate and normalize one local CWE scan result."""
    if not isinstance(result, dict):
        raise CweScanResultError(filepath, "result", "expected object")

    error = result.get("error")
    if error:
        raise SourceReadError(filepath, str(error))

    mappings = result.get("cwe_mappings")
    if not isinstance(mappings, list):
        raise CweScanResultError(filepath, "cwe_mappings", "expected array")

    normalized_mappings: list[dict[str, Any]] = []
    for index, mapping in enumerate(mappings):
        location = f"cwe_mappings[{index}]"
        if not isinstance(mapping, dict):
            raise CweScanResultError(filepath, location, "expected object")

        cwe_id = mapping.get("cwe_id")
        if (
            not isinstance(cwe_id, str)
            or not re.fullmatch(r"CWE-[1-9]\d*", cwe_id.strip())
        ):
            raise CweScanResultError(
                filepath,
                f"{location}.cwe_id",
                "expected CWE-<positive integer>",
            )

        normalized = dict(mapping)
        normalized["cwe_id"] = cwe_id.strip()
        for field in ("name", "category"):
            value = normalized.get(field, "")
            if not isinstance(value, str):
                raise CweScanResultError(filepath, f"{location}.{field}", "expected string when present")
            normalized[field] = value.strip()
        normalized_mappings.append(normalized)

    normalized_result = dict(result)
    normalized_result["cwe_mappings"] = normalized_mappings

    if "bridge_tags" in normalized_result:
        bridge_tags = normalized_result["bridge_tags"]
        if not isinstance(bridge_tags, list) or any(
            not isinstance(tag, str)
            for tag in bridge_tags
        ):
            raise CweScanResultError(filepath, "bridge_tags", "expected array of strings")

    if (
        "worth_remembering" in normalized_result
        and not isinstance(normalized_result["worth_remembering"], bool)
    ):
        raise CweScanResultError(filepath, "worth_remembering", "expected boolean")

    return normalized_result


def _scan_file_cwe_checked(
    filepath: Path,
    taxonomy: Any,
    validate: bool,
) -> dict[str, Any]:
    return _validate_cwe_scan_result(filepath, scan_file_cwe(filepath, taxonomy, validate))


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


def _build_lesson_document(
    problem: str,
    solution: str,
    scope: str,
    tags: list[str],
) -> dict[str, Any]:
    """Build a generic memory compatibility lesson."""
    return {
        "problem": problem,
        "solution": solution,
        "scope": scope,
        "tags": list(tags),
    }


def _learn_http(problem: str, solution: str, scope: str, tags: list[str]) -> bool:
    """Store a lesson in /memory via Unix socket httpx."""
    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET_PATH)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=15.0) as client:
            document = _build_lesson_document(
                problem=problem,
                solution=solution,
                scope=scope,
                tags=tags,
            )
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


def _abort_if_memory_writes_incomplete(
    *,
    phase: str,
    attempted: int,
    stored: int,
    codebase: Path,
) -> None:
    """Exit nonzero when a required memory-write phase is incomplete."""
    if attempted == stored:
        return

    print(
        json.dumps({
            "error": "Memory write incomplete",
            "phase": phase,
            "codebase": str(codebase),
            "attempted": attempted,
            "stored": stored,
            "failed": max(attempted - stored, 0),
        }),
        file=sys.stderr,
    )
    raise SystemExit(1)


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
    content = _read_source_text(filepath)
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
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


def _extract_symbol_context(
    filepath: Path,
    codebase_root: Path | None = None,
) -> dict[str, Any]:
    """Extract per-file context used to enrich treesitter symbols."""
    if filepath.suffix != ".py":
        return {
            "imports": [],
            "import_summary": "",
            "class_hierarchies": {},
        }

    imports = extract_python_imports(filepath, codebase_root)
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
    lines = _read_source_text(filepath).splitlines()
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


def _python_declaration_start(node: ast.AST) -> int:
    """Return the first physical line belonging to a declaration."""
    starts = [getattr(node, "lineno", 0)]
    starts.extend(
        getattr(decorator, "lineno", 0)
        for decorator in getattr(node, "decorator_list", ())
    )
    return min((line for line in starts if line > 0), default=0)


def _python_node_matches_symbol_start(node: ast.AST, start_line: int) -> bool:
    """Match a Tree-sitter start to a def/class or its decorators."""
    declaration_start = _python_declaration_start(node)
    definition_line = getattr(node, "lineno", 0)
    return (
        declaration_start > 0
        and declaration_start <= start_line <= definition_line
    )


def _find_python_parent_symbol(tree: ast.AST, node: ast.AST) -> Optional[str]:
    """Return the immediate named lexical parent for a declaration node."""
    parent_by_node: dict[ast.AST, str] = {}
    active_declarations: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = []

    class ParentVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, candidate: ast.FunctionDef) -> None:
            self._visit_declaration(candidate)

        def visit_AsyncFunctionDef(self, candidate: ast.AsyncFunctionDef) -> None:
            self._visit_declaration(candidate)

        def visit_ClassDef(self, candidate: ast.ClassDef) -> None:
            self._visit_declaration(candidate)

        def _visit_declaration(
            self,
            candidate: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        ) -> None:
            if active_declarations:
                parent_by_node[candidate] = active_declarations[-1].name
            active_declarations.append(candidate)
            self.generic_visit(candidate)
            active_declarations.pop()

    ParentVisitor().visit(tree)
    return parent_by_node.get(node)


def _python_parameter_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Return Python parameter names in declaration order."""
    args = node.args
    ordered_args: list[ast.arg] = [
        *args.posonlyargs,
        *args.args,
    ]
    if args.vararg is not None:
        ordered_args.append(args.vararg)
    ordered_args.extend(args.kwonlyargs)
    if args.kwarg is not None:
        ordered_args.append(args.kwarg)

    return [arg.arg for arg in ordered_args if arg.arg != "self"]


class _PythonLexicalCollector(ast.NodeVisitor):
    """Collect lexical terms for one declaration without nested body leakage."""

    def __init__(self, root: ast.AST) -> None:
        self.root = root
        self.local_variables: set[str] = set()
        self.excluded_bindings: set[str] = set()
        self.called_symbols: set[str] = set()
        self.string_literals: set[str] = set()
        self._binding_suppression_depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is not self.root:
            self._add_local_binding(node.name)
        self._visit_function_header(node, suppress_bindings=node is self.root)
        if node is self.root:
            for statement in node.body:
                self.visit(statement)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is not self.root:
            self._add_local_binding(node.name)
        self._visit_function_header(node, suppress_bindings=node is self.root)
        if node is self.root:
            for statement in node.body:
                self.visit(statement)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node is not self.root:
            self._add_local_binding(node.name)
        self._visit_class_header(node, suppress_bindings=node is self.root)
        if node is self.root:
            for statement in node.body:
                self.visit(statement)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_arguments(node.args)
        if node is self.root:
            self.visit(node.body)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store) and self._binding_suppression_depth == 0:
            self._add_local_binding(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".", 1)[0]
            self._add_local_binding(name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            name = alias.asname or alias.name
            self._add_local_binding(name)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._add_local_binding(node.name)
        if node.type is not None:
            self.visit(node.type)
        for statement in node.body:
            self.visit(statement)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self._add_local_binding(node.name)
        if node.pattern is not None:
            self.visit(node.pattern)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self._add_local_binding(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self._add_local_binding(node.rest)
        for key in node.keys:
            self.visit(key)
        for pattern in node.patterns:
            self.visit(pattern)

    def visit_Global(self, node: ast.Global) -> None:
        self.excluded_bindings.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.excluded_bindings.update(node.names)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node.generators, node.elt)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node.generators, node.elt)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node.generators, node.elt)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node.generators, node.key, node.value)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _name_from_call(node.func)
        if call_name:
            self.called_symbols.add(call_name)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            literal = node.value.strip()
            if 1 < len(literal) <= 120:
                self.string_literals.add(literal)

    def _visit_function_header(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        suppress_bindings: bool = False,
    ) -> None:
        visit = self._visit_binding_suppressed if suppress_bindings else self.visit
        for decorator in node.decorator_list:
            visit(decorator)
        self._visit_arguments(node.args, suppress_bindings=suppress_bindings)
        if node.returns is not None:
            visit(node.returns)

    def _visit_class_header(
        self,
        node: ast.ClassDef,
        *,
        suppress_bindings: bool = False,
    ) -> None:
        visit = self._visit_binding_suppressed if suppress_bindings else self.visit
        for decorator in node.decorator_list:
            visit(decorator)
        for base in node.bases:
            visit(base)
        for keyword in node.keywords:
            visit(keyword.value)

    def _visit_arguments(
        self,
        arguments: ast.arguments,
        *,
        suppress_bindings: bool = False,
    ) -> None:
        visit = self._visit_binding_suppressed if suppress_bindings else self.visit
        ordered_args = [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        ]
        if arguments.vararg is not None:
            ordered_args.append(arguments.vararg)
        if arguments.kwarg is not None:
            ordered_args.append(arguments.kwarg)

        for arg in ordered_args:
            if arg.annotation is not None:
                visit(arg.annotation)
        for default in arguments.defaults:
            visit(default)
        for default in arguments.kw_defaults:
            if default is not None:
                visit(default)

    def _visit_comprehension(
        self,
        generators: list[ast.comprehension],
        *result_expressions: ast.AST,
    ) -> None:
        for generator in generators:
            self._visit_binding_suppressed(generator.target)
            self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)
        for expression in result_expressions:
            self.visit(expression)

    def _visit_binding_suppressed(self, node: ast.AST) -> None:
        self._binding_suppression_depth += 1
        try:
            self.visit(node)
        finally:
            self._binding_suppression_depth -= 1

    def _add_local_binding(self, name: str) -> None:
        if name:
            self.local_variables.add(name)

    def normalized_local_variables(self) -> list[str]:
        return sorted(self.local_variables - self.excluded_bindings)


def _extract_python_symbol_details(
    filepath: Path,
    kind: str,
    name: str,
    start_line: int,
) -> dict[str, Any]:
    """Extract richer Python symbol details for memory-backed hybrid retrieval."""
    content = _read_source_text(filepath)
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return {}

    node_types: tuple[type, ...]
    if kind == "class":
        node_types = (ast.ClassDef,)
    else:
        node_types = (ast.FunctionDef, ast.AsyncFunctionDef)

    candidates = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, node_types)
            and getattr(node, "name", "") == name
            and _python_node_matches_symbol_start(node, start_line)
        )
    ]

    if len(candidates) != 1:
        return {}

    node = candidates[0]
    parameters: list[str] = []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        parameters = _python_parameter_names(node)

    lexical_collector = _PythonLexicalCollector(node)
    lexical_collector.visit(node)

    parent_symbol = _find_python_parent_symbol(tree, node)
    return {
        "start_line": _python_declaration_start(node),
        "end_line": getattr(node, "end_lineno", start_line),
        "docstring": ast.get_docstring(node) or "",
        "parameters": parameters,
        "local_variables": lexical_collector.normalized_local_variables(),
        "called_symbols": sorted(lexical_collector.called_symbols),
        "string_literals": sorted(lexical_collector.string_literals),
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
        if details:
            start_line = int(details.get("start_line") or start_line)
            end_line = int(details.get("end_line") or end_line)
            docstring = docstring or details.get("docstring", "")
            parent_symbol = details.get("parent_symbol") or ""
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
    return _collapse_overlapping_scan_roots(roots)


def _collapse_overlapping_scan_roots(roots: Sequence[Path]) -> list[Path]:
    """Remove exact duplicates and roots covered by another configured root."""
    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved not in seen:
            unique.append(resolved)
            seen.add(resolved)

    effective: list[Path] = []
    for root in unique:
        covered = False
        for other in unique:
            if root == other:
                continue
            try:
                root.relative_to(other)
            except ValueError:
                continue
            covered = True
            break
        if not covered:
            effective.append(root)

    return effective


def _configured_include_entries(config: dict[str, Any]) -> tuple[str, ...] | None:
    """Return validated include_dirs entries when explicitly configured."""
    if "include_dirs" not in config:
        return None

    raw_entries = config["include_dirs"]
    if not isinstance(raw_entries, list):
        raise ScanConfigError("include_dirs must be a JSON array of strings")

    if not raw_entries:
        return None

    entries: list[str] = []
    for raw in raw_entries:
        if not isinstance(raw, str) or not raw.strip():
            raise ScanConfigError("include_dirs entries must be nonblank strings")
        entries.append(raw.strip())

    return tuple(entries)


def _extract_configured_scan_roots(codebase_path: Path) -> list[Path]:
    """Resolve scan roots from env override or .monitor-codebase.json include_dirs."""
    env_roots = os.environ.get(SCAN_INCLUDE_DIRS_ENV)
    if env_roots and env_roots.strip():
        return _resolve_existing_scan_roots(codebase_path, env_roots.split(","))

    config = _load_monitor_config(codebase_path)
    if config:
        include_entries = _configured_include_entries(config)
        if include_entries is not None:
            return _resolve_existing_scan_roots(codebase_path, include_entries)
    return [codebase_path.resolve()]


def _configured_exclude_entries(config: dict[str, Any]) -> tuple[str, ...]:
    """Validate repository-relative exclude_dirs entries."""
    if "exclude_dirs" not in config:
        return ()

    raw_entries = config["exclude_dirs"]
    if not isinstance(raw_entries, list):
        raise ScanConfigError("exclude_dirs must be a JSON array of strings")

    entries: list[str] = []
    for raw in raw_entries:
        if not isinstance(raw, str):
            raise ScanConfigError("exclude_dirs entries must be nonblank strings")

        entry = raw.strip().replace("\\", "/")
        while entry.startswith("./"):
            entry = entry[2:]
        entry = entry.rstrip("/")

        if not entry or entry == "." or "\x00" in entry:
            raise ScanConfigError(
                "exclude_dirs entries must be nonblank repository-relative directory paths"
            )

        candidate = PurePosixPath(entry)
        if candidate.is_absolute() or ".." in candidate.parts or re.match(r"^[A-Za-z]:/", entry):
            raise ScanConfigError(f"unsafe exclude_dirs entry: {raw!r}")

        if any(character in entry for character in "*?["):
            raise ScanConfigError(f"exclude_dirs does not accept glob syntax: {raw!r}")

        if entry not in entries:
            entries.append(entry)

    return tuple(entries)


def _configured_exclude_dirs(codebase_root: Path) -> tuple[str, ...]:
    """Return hardcoded and monitor-configured repository-relative exclusions."""
    config = _load_monitor_config(codebase_root)
    configured = _configured_exclude_entries(config) if config is not None else ()
    return tuple(dict.fromkeys([*sorted(SKIP_DIRS), *configured]))


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


def _treesitter_completed(completed_scan_roots: Sequence[str | Path]) -> bool:
    """Return whether Tree-sitter completed at least one configured root."""
    return bool(completed_scan_roots)


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
    scope = _validate_memory_scope(scope)
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
    try:
        tmp_path.write_text(json.dumps(marker, indent=2))
        tmp_path.replace(marker_path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return marker_path


def _write_required_ingest_marker(
    path: Path,
    **marker_fields: Any,
) -> Path:
    """Write the required local completion marker or terminate the command."""
    try:
        return _write_ingest_marker(path, **marker_fields)
    except Exception as exc:
        print(
            json.dumps({
                "error": "Could not write ingest marker",
                "codebase": str(path),
                "marker": str(_marker_path(path)),
                "detail": str(exc),
            }),
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def _disabled_code_index() -> dict[str, bool]:
    return {"enabled": False}


def _invalid_marker_status(errors: Sequence[str]) -> dict[str, Any]:
    return {
        "status": "invalid",
        "run_status": None,
        "completed": False,
        "scope": None,
        "scan_roots": [],
        "completed_scan_roots": [],
        "code_index": _disabled_code_index(),
        "validation_errors": list(errors),
    }


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _marker_string_list(value: object, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []

    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field}[{index}] must be a nonblank string")
            continue
        normalized.append(item.strip())
    return normalized


def _marker_iso_timestamp(value: object, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a nonblank ISO timestamp")
        return None

    timestamp = value.strip()
    try:
        datetime.fromisoformat(timestamp)
    except ValueError:
        errors.append(f"{field} must be a valid ISO timestamp")
    return timestamp


def _marker_nonblank_string(value: object, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a nonblank string")
        return None
    return value.strip()


def _marker_nonnegative_count(value: object, field: str, errors: list[str]) -> int:
    if not _is_nonnegative_int(value):
        errors.append(f"{field} must be a nonnegative integer")
        return 0
    return int(value)


def _validate_marker_code_index(value: object, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append("code_index must be an object")
        return _disabled_code_index()

    code_index = dict(value)
    enabled = code_index.get("enabled")
    if not isinstance(enabled, bool):
        errors.append("code_index.enabled must be a boolean")
        enabled = False

    symbols_stored = code_index.get("symbols_stored")
    if not _is_nonnegative_int(symbols_stored):
        errors.append("code_index.symbols_stored must be a nonnegative integer")
        symbols_stored = 0

    if isinstance(enabled, bool) and enabled != (symbols_stored > 0):
        errors.append("code_index.enabled must match symbols_stored > 0")

    backend = code_index.get("backend")
    if backend is not None and backend != "memory":
        errors.append('code_index.backend must be "memory" when present')

    collection = code_index.get("collection")
    if collection is not None and collection != "code_symbols":
        errors.append('code_index.collection must be "code_symbols" when present')

    treesitter = code_index.get("treesitter")
    if treesitter is not None and not isinstance(treesitter, bool):
        errors.append("code_index.treesitter must be a boolean when present")

    code_index["enabled"] = bool(enabled)
    code_index["symbols_stored"] = int(symbols_stored)
    return code_index


def _marker_roots_within_repo(
    values: Sequence[str],
    field: str,
    repo_root: Path,
    errors: list[str],
) -> set[str]:
    normalized: set[str] = set()
    for index, raw in enumerate(values):
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(repo_root)
        except (OSError, RuntimeError, ValueError):
            errors.append(f"{field}[{index}] must resolve inside the marker repository")
            continue
        normalized.add(str(resolved))
    return normalized


def _validate_completed_marker(
    payload: dict[str, Any],
    marker_path: Path,
    *,
    legacy: bool,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    repo_root = marker_path.parent.resolve()

    ingested_at = _marker_iso_timestamp(payload.get("ingested_at"), "ingested_at", errors)
    marker_path_value = _marker_nonblank_string(payload.get("path"), "path", errors)
    stem = _marker_nonblank_string(payload.get("stem"), "stem", errors)
    scope = _marker_nonblank_string(payload.get("scope"), "scope", errors)

    if marker_path_value:
        try:
            if Path(marker_path_value).expanduser().resolve() != repo_root:
                errors.append("path must match the marker repository")
        except OSError:
            errors.append("path must resolve to the marker repository")

    if stem and stem != repo_root.name:
        errors.append("stem must match the marker repository name")

    status = dict(payload)
    for field in ("files_scanned", "knowledge_stored", "cwe_stored", "edges_stored"):
        status[field] = _marker_nonnegative_count(payload.get(field), field, errors)

    status["code_index"] = _validate_marker_code_index(payload.get("code_index"), errors)
    status["ingested_at"] = ingested_at
    status["path"] = str(repo_root)
    status["stem"] = repo_root.name
    status["scope"] = scope
    status["run_status"] = "complete"
    status["completed"] = True

    if legacy:
        status["scan_roots"] = []
        status["completed_scan_roots"] = []
        return status, errors

    _marker_iso_timestamp(payload.get("started_at"), "started_at", errors)
    if payload.get("completed") is not True:
        errors.append("completed must be true for a complete marker")

    scan_roots = _marker_string_list(payload.get("scan_roots"), "scan_roots", errors)
    completed_scan_roots = _marker_string_list(
        payload.get("completed_scan_roots"),
        "completed_scan_roots",
        errors,
    )
    scan_root_set = _marker_roots_within_repo(scan_roots, "scan_roots", repo_root, errors)
    completed_root_set = _marker_roots_within_repo(
        completed_scan_roots,
        "completed_scan_roots",
        repo_root,
        errors,
    )
    for completed_root in completed_root_set:
        if completed_root not in scan_root_set:
            errors.append("completed_scan_roots entries must also appear in scan_roots")
            break

    status["scan_roots"] = scan_roots
    status["completed_scan_roots"] = completed_scan_roots
    return status, errors


def _normalize_incomplete_marker(
    payload: dict[str, Any],
    run_status: str,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    status = dict(payload)
    status["status"] = run_status
    status["run_status"] = run_status
    status["completed"] = False
    status["scope"] = payload.get("scope") if isinstance(payload.get("scope"), str) else None

    if "scan_roots" in payload:
        status["scan_roots"] = _marker_string_list(payload.get("scan_roots"), "scan_roots", errors)
    else:
        status["scan_roots"] = []

    if "completed_scan_roots" in payload:
        status["completed_scan_roots"] = _marker_string_list(
            payload.get("completed_scan_roots"),
            "completed_scan_roots",
            errors,
        )
    else:
        status["completed_scan_roots"] = []

    code_index = payload.get("code_index")
    if code_index is None:
        status["code_index"] = _disabled_code_index()
    elif isinstance(code_index, dict):
        status["code_index"] = code_index
    else:
        errors.append("code_index must be an object")
        status["code_index"] = _disabled_code_index()

    return status, errors


def build_marker_status(path: Path) -> dict[str, Any]:
    """Read the ingest-code marker status without raising for missing or bad files."""
    marker_path = _marker_path(path)
    if not marker_path.exists():
        return {
            "status": "missing",
            "run_status": None,
            "completed": False,
            "scope": None,
            "scan_roots": [],
            "completed_scan_roots": [],
            "code_index": _disabled_code_index(),
        }

    try:
        payload = json.loads(marker_path.read_text())
    except (OSError, json.JSONDecodeError):
        payload = None

    if not isinstance(payload, dict):
        return _invalid_marker_status(["marker must be a JSON object"])

    raw_run_status = payload.get("run_status")
    if raw_run_status is None:
        status, errors = _validate_completed_marker(payload, marker_path, legacy=True)
    elif raw_run_status == "complete":
        status, errors = _validate_completed_marker(payload, marker_path, legacy=False)
    elif raw_run_status in {"running", "failed"}:
        status, errors = _normalize_incomplete_marker(payload, raw_run_status)
    else:
        return _invalid_marker_status(["run_status must be running, complete, or failed"])

    if errors:
        return _invalid_marker_status(errors[:20])

    if status["run_status"] == "complete":
        status["status"] = "fresh"
    return status


def _parse_treesitter_scan_output(stdout: str) -> list[dict[str, Any]] | None:
    """Parse treesitter scan output, skipping human summary lines."""
    payload = stdout.strip()
    if not payload:
        return None

    json_start = payload.find("[")
    if json_start < 0:
        return None

    try:
        data = json.loads(payload[json_start:])
    except json.JSONDecodeError:
        return None

    return data if isinstance(data, list) else None


def _treesitter_schema_error(location: str, detail: str) -> TreeSitterScanError:
    return TreeSitterScanError(
        f"Tree-sitter result schema invalid at {location}: {detail}"
    )


def _validate_treesitter_text_field(
    value: object,
    location: str,
    *,
    required: bool,
) -> str | None:
    """Validate a Tree-sitter string/null field."""
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise _treesitter_schema_error(location, "expected nonblank string")
    stripped = value.strip()
    if not stripped:
        raise _treesitter_schema_error(location, "expected nonblank string")
    return stripped


def _validate_treesitter_line(
    value: object,
    location: str,
    *,
    minimum: int,
) -> int:
    """Validate a Tree-sitter source line number."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _treesitter_schema_error(location, "expected positive integer")
    return value


def _validate_treesitter_scan_results(
    scan_results: list[Any],
) -> tuple[dict[str, Any], ...]:
    """Validate and normalize the complete Tree-sitter result envelope."""
    normalized_entries: list[dict[str, Any]] = []

    for file_index, file_entry in enumerate(scan_results):
        file_location = f"files[{file_index}]"
        if not isinstance(file_entry, dict):
            raise _treesitter_schema_error(file_location, "expected object")

        path = _validate_treesitter_text_field(
            file_entry.get("path"),
            f"{file_location}.path",
            required=True,
        )
        assert path is not None

        if "symbols" not in file_entry or not isinstance(file_entry["symbols"], list):
            raise _treesitter_schema_error(f"{file_location}.symbols", "expected array")

        normalized_entry = dict(file_entry)
        normalized_entry["path"] = path
        language = normalized_entry.get("language")
        if language is not None:
            normalized_entry["language"] = _validate_treesitter_text_field(
                language,
                f"{file_location}.language",
                required=False,
            )

        normalized_symbols: list[dict[str, Any]] = []
        for symbol_index, symbol in enumerate(file_entry["symbols"]):
            symbol_location = f"{file_location}.symbols[{symbol_index}]"
            if not isinstance(symbol, dict):
                raise _treesitter_schema_error(symbol_location, "expected object")

            kind = _validate_treesitter_text_field(
                symbol.get("kind"),
                f"{symbol_location}.kind",
                required=True,
            )
            name = _validate_treesitter_text_field(
                symbol.get("name"),
                f"{symbol_location}.name",
                required=True,
            )
            assert kind is not None
            assert name is not None

            start_line = _validate_treesitter_line(
                symbol.get("start_line"),
                f"{symbol_location}.start_line",
                minimum=1,
            )
            raw_end_line = symbol.get("end_line")
            if raw_end_line is None:
                end_line = start_line
            else:
                end_line = _validate_treesitter_line(
                    raw_end_line,
                    f"{symbol_location}.end_line",
                    minimum=start_line,
                )

            normalized_symbol = dict(symbol)
            normalized_symbol.update({
                "kind": kind,
                "name": name,
                "start_line": start_line,
                "end_line": end_line,
            })
            for field_name in ("signature", "docstring", "parent", "parent_symbol"):
                if field_name in normalized_symbol and normalized_symbol[field_name] is not None:
                    if not isinstance(normalized_symbol[field_name], str):
                        raise _treesitter_schema_error(
                            f"{symbol_location}.{field_name}",
                            "expected string or null",
                        )
            normalized_symbols.append(normalized_symbol)

        normalized_entry["symbols"] = normalized_symbols
        normalized_entries.append(normalized_entry)

    return tuple(normalized_entries)


def _source_line_count(filepath: Path) -> int:
    """Count physical source lines without decoding the file."""
    try:
        with filepath.open("rb") as source:
            return sum(1 for _ in source)
    except OSError as exc:
        raise SourceReadError(filepath, str(exc)) from exc


def _validate_treesitter_source_ranges(
    symbols: Sequence[dict[str, Any]],
    *,
    filepath: Path,
    codebase_root: Path,
    file_index: int,
) -> None:
    """Require every reported symbol range to exist in the source file."""
    if not symbols:
        return

    line_count = _source_line_count(filepath)
    relative_path = _relative_path(filepath, codebase_root)

    for symbol_index, symbol in enumerate(symbols):
        for field_name in ("start_line", "end_line"):
            value = symbol[field_name]
            if value > line_count:
                raise TreeSitterScanError(
                    "Tree-sitter source range invalid at "
                    f"files[{file_index}].symbols[{symbol_index}].{field_name} "
                    f"for {relative_path}: {value} exceeds file line count {line_count}"
                )


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


def _resolved_file_manifest(
    files: Sequence[Path],
    codebase_root: Path,
) -> frozenset[Path]:
    """Return canonical in-repository files eligible for this ingest run."""
    root = codebase_root.resolve()
    resolved_files: set[Path] = set()

    for path in files:
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue

        if resolved.is_file():
            resolved_files.add(resolved)

    return frozenset(resolved_files)


def _extract_treesitter_records_for_directory(
    directory: Path,
    codebase_root: Path,
    scope: str,
    *,
    allowed_files: Collection[Path],
    mtime_after: datetime | None = None,
) -> tuple[CodeSymbolRecord, ...]:
    """Extract validated code-symbol records without writing to memory."""
    treesitter_script = find_treesitter_skill()
    if not treesitter_script:
        raise TreeSitterScanError(f"Tree-sitter skill not found for {directory}")

    try:
        resolved_directory = directory.resolve(strict=True)
        resolved_codebase_root = codebase_root.resolve(strict=True)
        resolved_directory.relative_to(resolved_codebase_root)
    except (OSError, RuntimeError, ValueError):
        raise TreeSitterScanError(
            f"Tree-sitter scan root is outside codebase or unavailable: {directory}"
        )

    if not resolved_directory.is_dir():
        raise TreeSitterScanError(f"Tree-sitter scan root is not a directory: {directory}")

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
        raise TreeSitterScanError(f"Tree-sitter scan timed out for {directory}")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise TreeSitterScanError(f"Tree-sitter scan failed for {directory}{detail}")

    scan_results = _parse_treesitter_scan_output(result.stdout)
    if scan_results is None:
        raise TreeSitterScanError(f"Tree-sitter scan produced malformed output for {directory}")
    validated_results = _validate_treesitter_scan_results(scan_results)
    if not validated_results:
        return ()

    repo = resolved_codebase_root.name
    branch = _current_branch(resolved_codebase_root)
    commit = _current_commit(resolved_codebase_root)
    exclude_dirs = _configured_exclude_dirs(resolved_codebase_root)
    allowed_file_paths = _resolved_file_manifest(tuple(allowed_files), resolved_codebase_root)
    records: list[CodeSymbolRecord] = []
    for file_index, file_entry in enumerate(validated_results):
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
        if filepath not in allowed_file_paths:
            continue
        if _path_is_excluded(filepath, resolved_codebase_root, exclude_dirs):
            continue
        try:
            modified_in_scope = _path_modified_at_or_after(
                filepath,
                mtime_after,
            )
        except FileDiscoveryError as exc:
            raise TreeSitterScanError(
                f"Tree-sitter modification-time check failed "
                f"for {filepath}: {exc}"
            ) from exc
        if not modified_in_scope:
            continue

        if not file_entry["symbols"]:
            continue
        try:
            _validate_treesitter_source_ranges(
                file_entry["symbols"],
                filepath=filepath,
                codebase_root=resolved_codebase_root,
                file_index=file_index,
            )
            try:
                symbol_context = _extract_symbol_context(
                    filepath,
                    resolved_codebase_root,
                )
            except TypeError as exc:
                if "positional" not in str(exc) and "argument" not in str(exc):
                    raise
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
        except SourceReadError as exc:
            raise TreeSitterScanError(
                f"Tree-sitter source read failed for {filepath}: {exc}"
            ) from exc

    return _canonicalize_treesitter_records(records)


def _store_treesitter_symbols_for_directory(
    directory: Path,
    codebase_root: Path,
    scope: str,
    verification_samples: Optional[list[dict[str, str]]] = None,
    *,
    allowed_files: Collection[Path],
    mtime_after: datetime | None = None,
) -> int:
    """Scan one configured directory and upsert structured code symbols to memory."""
    records = _extract_treesitter_records_for_directory(
        directory,
        codebase_root,
        scope,
        allowed_files=allowed_files,
        mtime_after=mtime_after,
    )
    if not records:
        return 0

    resolved_directory = directory.resolve(strict=True)
    result = CodeMemoryClient().upsert_code_symbols(list(records))
    if result.errors:
        detail = "; ".join(result.errors[:5])
        raise TreeSitterScanError(
            f"Tree-sitter memory write incomplete for {resolved_directory}: "
            f"stored={result.stored} attempted={result.attempted}; {detail}"
        )

    if verification_samples is not None:
        for record in result.stored_records:
            verification_samples.append(_code_symbol_verification_sample(record))

    return result.stored


def _treesitter_record_identity(record: CodeSymbolRecord) -> tuple[str, str, int]:
    """Identify one symbol declaration at a source location."""
    return (
        record.path,
        record.qualified_name,
        record.start_line,
    )


def _code_symbol_record_order_key(record: CodeSymbolRecord) -> tuple[str, int, int, str, str, str]:
    """Sort code-symbol records deterministically."""
    return (
        record.path,
        record.start_line,
        record.end_line,
        record.qualified_name,
        record.symbol_kind,
        record.content_hash,
    )


def _canonicalize_treesitter_records(
    records: Sequence[CodeSymbolRecord],
) -> tuple[CodeSymbolRecord, ...]:
    """Deduplicate exact records and reject conflicting source identities."""
    by_identity: dict[tuple[str, str, int], CodeSymbolRecord] = {}

    for record in records:
        identity = _treesitter_record_identity(record)
        existing = by_identity.get(identity)
        if existing is None:
            by_identity[identity] = record
            continue

        if existing.to_document() != record.to_document():
            raise TreeSitterScanError(
                "Conflicting Tree-sitter records for "
                f"{record.path}:{record.start_line} {record.qualified_name}"
            )

    return tuple(sorted(by_identity.values(), key=_code_symbol_record_order_key))


def _print_code_symbol_dry_run_preview(records: Sequence[CodeSymbolRecord]) -> None:
    """Print code-symbol records that would be upserted."""
    for record in sorted(records, key=_code_symbol_record_order_key):
        print(
            f"  [CODE_SYMBOL] {record.path}:{record.start_line}-{record.end_line} "
            f"{record.symbol_kind} {record.qualified_name}",
            flush=True,
        )


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


def _python_package_parts(filepath: Path, codebase_root: Path) -> tuple[str, ...]:
    """Return repository-relative package components for a Python file."""
    try:
        resolved_file = filepath.resolve(strict=True)
        resolved_root = codebase_root.resolve(strict=True)
        relative = resolved_file.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        return ()

    if relative.suffix != ".py":
        return ()

    return tuple(relative.parent.parts)


def _resolve_relative_python_imports(
    *,
    filepath: Path,
    codebase_root: Path,
    level: int,
    module: str | None,
    names: Sequence[str],
    line: int,
) -> list[dict[str, Any]]:
    """Normalize relative imports to repository-relative dotted modules."""
    package_parts = _python_package_parts(filepath, codebase_root)
    if not package_parts or level < 1:
        return []

    parents_to_drop = level - 1
    if parents_to_drop >= len(package_parts):
        return []

    base_parts = package_parts[: len(package_parts) - parents_to_drop]

    if module:
        return [{
            "module": ".".join([*base_parts, *module.split(".")]),
            "names": list(names),
            "line": line,
        }]

    imports: list[dict[str, Any]] = []
    for name in names:
        if not name or name == "*":
            continue
        imports.append({
            "module": ".".join([*base_parts, *name.split(".")]),
            "names": [],
            "line": line,
        })
    return imports


def extract_python_imports(filepath: Path, codebase_root: Path | None = None) -> list[dict]:
    """Extract import relationships from a Python file using AST (fast, no treesitter needed)."""
    content = _read_source_text(filepath)
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names]
            if node.level > 0 and codebase_root is not None:
                imports.extend(
                    _resolve_relative_python_imports(
                        filepath=filepath,
                        codebase_root=codebase_root,
                        level=node.level,
                        module=node.module,
                        names=names,
                        line=node.lineno,
                    )
                )
            elif node.module:
                imports.append({
                    "module": node.module,
                    "names": names,
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


def build_module_index(files: list[Path], codebase_root: Path) -> dict[str, tuple[Path, ...]]:
    """Map each Python module alias to all matching repository files."""
    root = codebase_root.resolve()
    candidates: dict[str, set[Path]] = {}

    for filepath in files:
        if filepath.suffix != ".py":
            continue
        try:
            resolved = filepath.resolve(strict=True)
            relative = resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue

        # Convert path to module: src/extractor/pipeline/steps/s05.py → src.extractor.pipeline.steps.s05
        parts = list(relative.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = resolved.stem

        if not parts:
            continue

        # Also index without common prefixes (src.extractor → extractor)
        for index in range(len(parts)):
            alias = ".".join(parts[index:])
            if alias:
                candidates.setdefault(alias, set()).add(resolved)

    return {
        alias: tuple(sorted(paths, key=lambda path: path.as_posix()))
        for alias, paths in sorted(candidates.items())
    }


def _resolve_unique_python_module(
    module_index: dict[str, tuple[Path, ...]],
    module: str,
) -> Path | None:
    """Return the only matching file for a Python import alias."""
    candidates = module_index.get(module, ())
    return candidates[0] if len(candidates) == 1 else None


def _dependency_edge_identity(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    """Identify one concrete import relationship."""
    return (
        str(Path(edge["from_file"]).resolve()),
        str(Path(edge["to_file"]).resolve()),
        str(edge["edge_type"]),
        str(edge["module"]),
    )


def _normalized_edge_names(value: object) -> tuple[str, ...]:
    """Return unique imported names in deterministic order."""
    if not isinstance(value, (list, tuple)):
        return ()

    return tuple(sorted({
        name.strip()
        for name in value
        if isinstance(name, str) and name.strip()
    }))


def _canonicalize_dependency_edges(edges: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate import edges and merge imported names."""
    names_by_identity: dict[tuple[str, str, str, str], set[str]] = {}

    for edge in edges:
        identity = _dependency_edge_identity(edge)
        names_by_identity.setdefault(identity, set()).update(
            _normalized_edge_names(edge.get("names", []))
        )

    return [
        {
            "from_file": from_file,
            "to_file": to_file,
            "edge_type": edge_type,
            "module": module,
            "names": sorted(names_by_identity[identity]),
        }
        for identity in sorted(names_by_identity)
        for from_file, to_file, edge_type, module in [identity]
    ]


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
        imports = extract_python_imports(filepath, codebase_root)
        for imp in imports:
            module = imp["module"]
            # Try to resolve to a file in this codebase
            target = _resolve_unique_python_module(module_index, module)
            if target is None or target == filepath.resolve():
                continue  # External dep or self-import
            edges.append({
                "from_file": str(filepath),
                "to_file": str(target),
                "edge_type": "depends_on",
                "module": module,
                "names": imp.get("names", []),
            })

    return _canonicalize_dependency_edges(edges)


def _edge_preview_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(edge.get("from_file", "")),
        str(edge.get("to_file", "")),
        str(edge.get("edge_type", "")),
        str(edge.get("module", "")),
    )


def store_edges(edges: list[dict], scope: str = "code", dry_run: bool = False, monitor=None) -> int:
    """Store dependency edges in /memory via batch HTTP endpoint."""
    edges = _canonicalize_dependency_edges(edges)
    if dry_run:
        for edge in sorted(edges, key=_edge_preview_key):
            from_name = Path(edge["from_file"]).name
            to_name = Path(edge["to_file"]).name
            names = ", ".join(edge.get("names", [])[:3])
            print(f"  [EDGE] {from_name} → {to_name} (imports {names})")
            if monitor:
                monitor.update(1, item=f"{from_name}->{to_name} previewed")
        return 0

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

def _load_monitor_config(codebase_path: Path) -> Optional[dict[str, Any]]:
    """Load .monitor-codebase.json if present."""
    config_file = codebase_path / ".monitor-codebase.json"
    if not config_file.exists():
        return None

    try:
        payload = json.loads(config_file.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ScanConfigError(f"Could not parse {config_file}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ScanConfigError(f"{config_file} must contain a JSON object")

    return payload


def _preflight_scan_config(codebase_path: Path) -> None:
    """Validate repo-local scan configuration before external work starts."""
    config = _load_monitor_config(codebase_path)
    if config is None:
        return
    if not (os.environ.get(SCAN_INCLUDE_DIRS_ENV) or "").strip():
        _configured_include_entries(config)
    _configured_exclude_entries(config)


def _exit_invalid_scan_config(codebase_path: Path, exc: ScanConfigError) -> None:
    """Emit the structured CLI error for invalid scan configuration."""
    print(
        json.dumps({
            "error": "Invalid ingest scan configuration",
            "codebase": str(codebase_path.resolve()),
            "config": str(codebase_path.resolve() / ".monitor-codebase.json"),
            "detail": str(exc),
        }),
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


def _is_git_repo(path: Path) -> bool:
    """Check if path is inside a git repository."""
    git_marker = _nearest_git_marker(path)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if git_marker is not None:
            raise FileDiscoveryError(f"git repository probe failed: {exc}") from exc
        return False

    if result.returncode == 0 and result.stdout.strip() == "true":
        return True
    if git_marker is not None:
        stderr = (result.stderr or "").strip()[:500]
        detail = f"git repository probe failed with exit {result.returncode}"
        if stderr:
            detail = f"{detail}: {stderr}"
        raise FileDiscoveryError(detail)
    return False


def _nearest_git_marker(path: Path) -> Path | None:
    """Return the nearest .git marker at or above a path."""
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for directory in (resolved, *resolved.parents):
        marker = directory / ".git"
        if marker.exists():
            return marker
    return None


def _normalize_scan_glob(pattern: str) -> str | None:
    """Return a safe repository-relative glob pattern."""
    normalized = str(pattern).strip().replace("\\", "/")

    while normalized.startswith("./"):
        normalized = normalized[2:]

    if not normalized or normalized == "." or "\x00" in normalized:
        return None

    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or ".." in parsed.parts:
        return None

    if re.match(r"^[A-Za-z]:/", normalized):
        return None

    if "/" not in normalized:
        normalized = f"**/{normalized}"

    return normalized


def _validate_explicit_scan_globs(patterns: Sequence[str]) -> list[str]:
    """Validate, normalize, and deduplicate explicit CLI glob values."""
    normalized_patterns: list[str] = []

    for index, pattern in enumerate(patterns):
        normalized = _normalize_scan_glob(pattern)
        if normalized is None:
            raise ScanGlobError(pattern, index)
        if normalized not in normalized_patterns:
            normalized_patterns.append(normalized)

    return normalized_patterns


def _git_glob_pathspec(pattern: str) -> str | None:
    """Translate one safe relative glob pattern to a Git glob pathspec."""
    normalized = _normalize_scan_glob(pattern)
    if normalized is None:
        return None

    return f":(glob){normalized}"


def _git_ls_files(codebase_path: Path, patterns: list[str]) -> list[Path]:
    """Return existing tracked or unignored files matching scan patterns."""
    normalized_patterns = list(dict.fromkeys(
        normalized
        for pattern in patterns
        if (normalized := _normalize_scan_glob(pattern)) is not None
    ))
    pathspecs = [f":(glob){pattern}" for pattern in normalized_patterns]
    if not pathspecs:
        return []

    try:
        result = subprocess.run(
            [
                "git",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                *pathspecs,
            ],
            cwd=str(codebase_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FileDiscoveryError(f"git ls-files failed: {exc}") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[:500]
        detail = f"git ls-files failed with exit {result.returncode}"
        if stderr:
            detail = f"{detail}: {stderr}"
        raise FileDiscoveryError(detail)

    files: list[Path] = []
    for line in result.stdout.splitlines():
        candidate = codebase_path / line
        if candidate.is_file():
            files.append(candidate)
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
    """Compare source mtime to a cutoff, failing on unreadable metadata."""
    if threshold is None:
        return True

    try:
        cutoff = threshold.timestamp()
    except (OverflowError, ValueError) as exc:
        raise FileDiscoveryError(
            f"invalid modification-time threshold "
            f"{threshold.isoformat()}: {exc}"
        ) from exc

    try:
        modified_at = path.stat().st_mtime
    except OSError as exc:
        raise FileDiscoveryError(
            f"could not read modification time for {path}: {exc}"
        ) from exc

    return modified_at >= cutoff


def _parse_since_threshold(
    since: str | None,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Parse rescan --since into an mtime threshold."""
    if since is None:
        return None

    raw = since.strip()
    if not raw:
        raise RescanSinceError("--since must not be blank")

    relative = re.fullmatch(r"([1-9]\d*)([dh])", raw.lower())
    if relative:
        count = int(relative.group(1))
        reference = now or datetime.now()
        try:
            if relative.group(2) == "d":
                return reference - timedelta(days=count)
            return reference - timedelta(hours=count)
        except OverflowError as exc:
            raise RescanSinceError(f"--since duration is too large: {since}") from exc

    iso_value = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        return datetime.fromisoformat(iso_value)
    except ValueError as exc:
        raise RescanSinceError(
            "--since must be a positive integer followed by 'h' or 'd', "
            "or an ISO-8601 date/time"
        ) from exc


def _exit_invalid_since(since: str | None, exc: RescanSinceError) -> None:
    """Emit the structured CLI error for invalid rescan --since values."""
    print(
        json.dumps({
            "error": "Invalid rescan --since value",
            "since": since,
            "detail": str(exc),
            "accepted_formats": [
                "12h",
                "1d",
                "2026-07-23",
                "2026-07-23T12:00:00+00:00",
            ],
        }),
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


def _validate_scan_batch_size(batch_size: int) -> int:
    """Require a positive CWE file-batch size."""
    if isinstance(batch_size, bool) or batch_size < 1:
        raise ScanBatchSizeError("--batch-size must be a positive integer")
    return batch_size


def _resolve_ingest_workers(raw_value: str | None = None) -> int:
    """Resolve a positive live knowledge-write worker count."""
    raw = os.environ.get(INGEST_WORKERS_ENV) if raw_value is None else raw_value

    if raw is None or not raw.strip():
        return DEFAULT_INGEST_WORKERS

    try:
        workers = int(raw.strip())
    except ValueError as exc:
        raise IngestWorkersError(
            f"{INGEST_WORKERS_ENV} must be a positive integer"
        ) from exc

    if workers < 1:
        raise IngestWorkersError(
            f"{INGEST_WORKERS_ENV} must be a positive integer"
        )

    return workers


def _exit_invalid_ingest_workers(exc: IngestWorkersError) -> NoReturn:
    """Emit the structured CLI error for invalid INGEST_WORKERS values."""
    print(
        json.dumps({
            "error": "Invalid INGEST_WORKERS value",
            "environment": INGEST_WORKERS_ENV,
            "value": os.environ.get(INGEST_WORKERS_ENV),
            "detail": str(exc),
        }),
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


def _resolve_in_repo_file(path: Path, codebase_root: Path) -> Path | None:
    """Resolve an existing file and require repository containment."""
    try:
        root = codebase_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None

    return resolved if resolved.is_file() else None


def _resolve_in_repo_directory(path: Path, codebase_root: Path) -> Path | None:
    """Resolve an existing directory and require repository containment."""
    try:
        root = codebase_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None

    return resolved if resolved.is_dir() else None


def _append_explicit_markdown(
    files: list[Path],
    candidate: Path,
    codebase_root: Path,
    mtime_after: datetime | None,
) -> None:
    """Append one explicit in-repository Markdown file if eligible."""
    resolved = _resolve_in_repo_file(candidate, codebase_root)
    if resolved is None:
        return
    if resolved.suffix.lower() not in {".md", ".mdx"}:
        return
    if not _path_modified_at_or_after(resolved, mtime_after):
        return
    if resolved not in files:
        files.append(resolved)


def collect_files(codebase_path: Path, patterns: list[str], mtime_after: Optional[datetime] = None) -> list[Path]:
    """Collect files matching patterns, respecting .gitignore and .monitor-codebase.json."""
    files: list[Path] = []
    codebase_root = codebase_path.resolve()
    exclude_dirs = _configured_exclude_dirs(codebase_root)
    normalized_patterns = list(dict.fromkeys(
        normalized
        for pattern in patterns
        if (normalized := _normalize_scan_glob(pattern)) is not None
    ))

    # Determine scan roots — either scoped dirs or full codebase
    scan_roots = _extract_configured_scan_roots(codebase_root)

    # Use git ls-files if in a git repo (respects .gitignore)
    use_git = _is_git_repo(codebase_root)

    if use_git:
        for f in _git_ls_files(codebase_root, normalized_patterns):
            if not _path_is_within_scan_roots(f, scan_roots):
                continue
            if _path_is_excluded(f, codebase_root, exclude_dirs):
                continue
            if not _path_modified_at_or_after(f, mtime_after):
                continue
            files.append(f)
    else:
        for pattern in normalized_patterns:
            try:
                for f in codebase_root.glob(pattern):
                    if not f.is_file():
                        continue
                    if not _path_is_within_scan_roots(f, scan_roots):
                        continue
                    if _path_is_excluded(f, codebase_root, exclude_dirs):
                        continue
                    if not _path_modified_at_or_after(f, mtime_after):
                        continue
                    files.append(f)
            except (OSError, ValueError, NotImplementedError) as exc:
                raise FileDiscoveryError(f"non-git glob failed for pattern {pattern!r}: {exc}") from exc

    # Also include named Markdown docs at project root (always)
    for stem in EXPLICIT_ROOT_DOC_STEMS:
        for suffix in EXPLICIT_MARKDOWN_SUFFIXES:
            _append_explicit_markdown(
                files,
                codebase_root / f"{stem}{suffix}",
                codebase_root,
                mtime_after,
            )
    # Recurse for direct-child Markdown docs in special documentation dirs.
    for local_dir in [codebase_root / "local" / "docs", codebase_root / "local"]:
        resolved_dir = _resolve_in_repo_directory(local_dir, codebase_root)
        if resolved_dir is None:
            continue
        for pattern in EXPLICIT_MARKDOWN_GLOBS:
            for md in resolved_dir.glob(pattern):
                _append_explicit_markdown(files, md, codebase_root, mtime_after)
    resolved_docs_dir = _resolve_in_repo_directory(codebase_root / "docs", codebase_root)
    if resolved_docs_dir is not None:
        for pattern in EXPLICIT_MARKDOWN_GLOBS:
            for md in resolved_docs_dir.glob(pattern):
                _append_explicit_markdown(files, md, codebase_root, mtime_after)

    return sorted(set(files))


def _collect_files_or_exit(
    codebase: Path,
    patterns: list[str],
    *,
    mtime_after: datetime | None = None,
) -> list[Path]:
    """Collect files or emit the command-level discovery failure."""
    try:
        return collect_files(codebase, patterns, mtime_after=mtime_after)
    except FileDiscoveryError as exc:
        print(
            json.dumps({
                "error": "File discovery failed",
                "codebase": str(codebase),
                "detail": str(exc),
            }),
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def _normalized_tag_values(value: object) -> list[str]:
    """Return nonblank string tags while preserving encounter order."""
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        return []

    tags: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        tag = candidate.strip()
        if tag:
            tags.append(tag)
    return tags


def _taxonomy_tag_values(
    value: object,
    *,
    location: str,
    item_index: int,
    problem: str,
) -> object:
    """Validate supported taxonomy tag value shapes before normalizing tags."""
    if value is None:
        return []

    if isinstance(value, str):
        return value

    if isinstance(value, (list, tuple)):
        for index, tag in enumerate(value):
            if not isinstance(tag, str):
                raise TaxonomyEnrichmentError(
                    item_index=item_index,
                    problem=problem,
                    detail=f"{location}[{index}] expected string",
                )
        return list(value)

    raise TaxonomyEnrichmentError(
        item_index=item_index,
        problem=problem,
        detail=f"{location} expected string or array of strings",
    )


def _validate_taxonomy_enrichment_result(
    result: object,
    *,
    item_index: int,
    problem: str,
) -> tuple[object, object]:
    """Validate the taxonomy enrichment envelope consumed by ingest-code."""
    if not isinstance(result, dict):
        raise TaxonomyEnrichmentError(
            item_index=item_index,
            problem=problem,
            detail="result expected object",
        )

    bridge_tags = _taxonomy_tag_values(
        result.get("bridge_tags"),
        location="bridge_tags",
        item_index=item_index,
        problem=problem,
    )

    collection_tags = result.get("collection_tags")
    if collection_tags is None:
        return bridge_tags, {}

    if not isinstance(collection_tags, dict):
        raise TaxonomyEnrichmentError(
            item_index=item_index,
            problem=problem,
            detail="collection_tags expected object",
        )

    normalized_collections: dict[object, object] = {}
    for key, tag_value in collection_tags.items():
        normalized_collections[key] = _taxonomy_tag_values(
            tag_value,
            location=f"collection_tags[{key!r}]",
            item_index=item_index,
            problem=problem,
        )

    return bridge_tags, normalized_collections


def _merge_taxonomy_tags(
    existing_tags: object,
    bridge_tags: object,
    collection_tags: object,
) -> list[str]:
    """Append taxonomy tags without disturbing extractor tag order."""
    candidates = _normalized_tag_values(existing_tags)
    candidates.extend(_normalized_tag_values(bridge_tags))

    if isinstance(collection_tags, dict):
        for key in sorted(collection_tags, key=lambda value: str(value)):
            candidates.extend(_normalized_tag_values(collection_tags[key]))

    return list(dict.fromkeys(candidates))


def _build_cwe_lesson_payload(
    filepath: Path,
    cwe: dict[str, Any],
    bridge_tags: object,
) -> dict[str, Any]:
    """Build the canonical compatibility lesson for one CWE finding."""
    cwe_id = cwe["cwe_id"]
    cwe_name = cwe.get("name", "")
    category = cwe.get("category", "")
    extension = filepath.suffix.lstrip(".")

    base_tags = ["ingest-code", "cwe", cwe_id]
    if category:
        base_tags.append(category)
    if extension:
        base_tags.append(extension)

    finding = f"{cwe_id} ({cwe_name})" if cwe_name else cwe_id
    category_text = f" - Category: {category}" if category else ""

    return {
        "problem": f"What CWEs are relevant to {filepath.name}?",
        "solution": f"{finding}{category_text}. File: {filepath}",
        "tags": _merge_taxonomy_tags(base_tags, bridge_tags, {}),
    }


def enrich_with_taxonomy(items: list[dict], taxonomy_module) -> list[dict]:
    """Run /taxonomy on each knowledge item to add bridge_tags + collection_tags.

    Uses fast=True keyword mode (~10ms/call, no LLM). Merges taxonomy tags
    into the item's existing tags list so ArangoSearch can index them.
    """
    if not taxonomy_module or not items:
        return items

    extract_fn = getattr(taxonomy_module, "extract_taxonomy", None)
    if not callable(extract_fn):
        raise TaxonomyEnrichmentError(
            item_index=-1,
            problem="",
            detail="taxonomy module has no callable extract_taxonomy",
        )

    enriched_items: list[dict] = []
    for index, item in enumerate(items):
        problem = str(item.get("problem", ""))
        try:
            # Taxonomy on the solution text (richer than the problem/question)
            text = str(item.get("solution", ""))[:3000]
            result = extract_fn(text, collection="operational", fast=True)
        except Exception as exc:
            raise TaxonomyEnrichmentError(
                item_index=index,
                problem=problem,
                detail=str(exc),
            ) from exc

        bridge_tags, collection_tags = _validate_taxonomy_enrichment_result(
            result,
            item_index=index,
            problem=problem,
        )
        enriched_item = dict(item)
        enriched_item["tags"] = _merge_taxonomy_tags(
            item.get("tags", []),
            bridge_tags,
            collection_tags,
        )
        enriched_items.append(enriched_item)

    return enriched_items


def extract_knowledge(filepath: Path) -> list[dict]:
    """Extract functional knowledge from any file type."""
    content = _read_source_text(filepath)

    # Markdown documentation
    if filepath.suffix in (".md", ".mdx"):
        return extract_markdown_knowledge(filepath, content)

    # Python
    if filepath.suffix == ".py":
        return extract_python_knowledge(filepath, content)

    # TypeScript, JavaScript, etc.
    return extract_generic_knowledge(filepath, content)


def _validate_knowledge_items(
    filepath: Path,
    result: object,
) -> tuple[dict[str, Any], ...]:
    """Validate and normalize one file's functional-knowledge records."""
    if not isinstance(result, list):
        raise KnowledgeItemError(
            filepath=filepath,
            item_index=-1,
            location="result",
            detail="expected array",
        )

    normalized_items: list[dict[str, Any]] = []
    for index, item in enumerate(result):
        location = f"items[{index}]"
        if not isinstance(item, dict):
            raise KnowledgeItemError(
                filepath=filepath,
                item_index=index,
                location=location,
                detail="expected object",
            )

        problem = item.get("problem")
        if not isinstance(problem, str) or not problem.strip():
            raise KnowledgeItemError(
                filepath=filepath,
                item_index=index,
                location=f"{location}.problem",
                detail="expected nonblank string",
            )

        solution = item.get("solution")
        if not isinstance(solution, str) or not solution.strip():
            raise KnowledgeItemError(
                filepath=filepath,
                item_index=index,
                location=f"{location}.solution",
                detail="expected nonblank string",
            )

        tags = item.get("tags")
        if not isinstance(tags, list) or not tags:
            raise KnowledgeItemError(
                filepath=filepath,
                item_index=index,
                location=f"{location}.tags",
                detail="expected nonempty array of strings",
            )

        normalized_tags: list[str] = []
        for tag_index, tag in enumerate(tags):
            if not isinstance(tag, str) or not tag.strip():
                raise KnowledgeItemError(
                    filepath=filepath,
                    item_index=index,
                    location=f"{location}.tags[{tag_index}]",
                    detail="expected nonblank string",
                )
            normalized_tags.append(tag.strip())

        normalized = dict(item)
        normalized["problem"] = problem.strip()
        normalized["solution"] = solution.strip()
        normalized["tags"] = list(dict.fromkeys(normalized_tags))
        normalized_items.append(normalized)

    return tuple(normalized_items)


def _extract_validated_knowledge(filepath: Path) -> tuple[dict[str, Any], ...]:
    """Extract and validate functional-knowledge records for one file."""
    try:
        result = extract_knowledge(filepath)
    except SourceReadError:
        raise
    except Exception as exc:
        raise KnowledgeItemError(
            filepath=filepath,
            item_index=-1,
            location="extractor",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    return _validate_knowledge_items(filepath, result)


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
    batch_size: int = typer.Option(50, help="Positive number of files per CWE scan batch"),
):
    """Scan a codebase for functional knowledge and CWE mappings, store in /memory."""
    try:
        batch_size = _validate_scan_batch_size(batch_size)
    except ScanBatchSizeError as exc:
        print(
            json.dumps({
                "error": "Invalid scan --batch-size value",
                "batch_size": batch_size,
                "detail": str(exc),
            }),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    try:
        patterns = _validate_explicit_scan_globs(glob) if glob else list(DEFAULT_GLOB_PATTERNS)
    except ScanGlobError as exc:
        print(
            json.dumps({
                "error": "Invalid scan --glob value",
                "glob": exc.pattern,
                "index": exc.index,
                "detail": str(exc),
            }),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    try:
        scope = _validate_memory_scope(scope)
    except MemoryScopeError as exc:
        _exit_invalid_memory_scope(scope, exc)

    knowledge_workers = DEFAULT_INGEST_WORKERS
    if not dry_run and not cwe_only:
        try:
            knowledge_workers = _resolve_ingest_workers()
        except IngestWorkersError as exc:
            _exit_invalid_ingest_workers(exc)

    try:
        path = _resolve_codebase_directory(path)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
    try:
        _preflight_scan_config(path)
    except ScanConfigError as exc:
        _exit_invalid_scan_config(path, exc)

    taxonomy = load_taxonomy_module()
    memory_script = find_memory_skill()

    if not memory_script and not dry_run:
        print('{"error": "Memory skill not found"}', file=sys.stderr)
        raise SystemExit(1)

    files = _collect_files_or_exit(path, patterns)
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
        try:
            for filepath in file_iter:
                items = _extract_validated_knowledge(filepath)
                all_items.extend(items)
        except SourceReadError as exc:
            _exit_source_read_failure(codebase=path, phase="knowledge", exc=exc)
        except KnowledgeItemError as exc:
            _exit_knowledge_item_failure(codebase=path, exc=exc)
        knowledge_total = len(all_items)
        print(f"  Extracted {knowledge_total} knowledge items from {len(files)} files", flush=True)

        # Phase 1a½: Enrich with taxonomy bridge tags (fast keyword mode, ~10ms/item)
        if taxonomy:
            try:
                all_items = enrich_with_taxonomy(all_items, taxonomy)
            except TaxonomyEnrichmentError as exc:
                _exit_taxonomy_enrichment_failure(codebase=path, exc=exc)
            print(f"  Enriched {knowledge_total} items with taxonomy bridge tags", flush=True)

        if dry_run:
            for item in all_items:
                print(f"  [K] {item['problem']}")
        else:
            # Phase 1b: Store via threaded HTTP learns (I/O-bound, GPU embedding)
            _lock = threading.Lock()

            def _learn_item(item: dict) -> bool:
                return _learn(
                    memory_script, item["problem"], item["solution"],
                    scope, item["tags"],
                )

            print(f"  Storing with {knowledge_workers} threads...", flush=True)
            store_monitor = Monitor(None, name="ingest-code-store", desc="Storing to memory", total=knowledge_total) if Monitor else None
            with ThreadPoolExecutor(max_workers=knowledge_workers) as pool:
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
        if not dry_run:
            _abort_if_memory_writes_incomplete(
                phase="knowledge",
                attempted=knowledge_total,
                stored=knowledge_stored,
                codebase=path,
            )

    # --- Phase 2: CWE scanning ---
    total_cwes = 0
    cwe_stored = 0
    files_with_cwes = 0
    cwe_summary: dict[str, int] = {}

    print("\n--- Phase 2: CWE scanning ---", flush=True)
    if taxonomy is None:
        print(
            "Taxonomy module not found — running built-in CWE patterns without taxonomy bridge tags",
            flush=True,
        )
    cwe_files = [f for f in files if f.suffix not in (".md", ".mdx")]
    cwe_monitor = Monitor(None, name="ingest-code-cwe", desc="CWE scanning", total=len(cwe_files)) if Monitor else None
    scanned = 0

    for i in range(0, len(cwe_files), batch_size):
        batch = cwe_files[i:i + batch_size]
        for filepath in batch:
            try:
                result = _scan_file_cwe_checked(filepath, taxonomy, validate)
            except SourceReadError as exc:
                _exit_source_read_failure(codebase=path, phase="cwe", exc=exc)
            except CweScanResultError as exc:
                _exit_cwe_result_failure(codebase=path, exc=exc)
            scanned += 1
            cwes = result.get("cwe_mappings", [])
            if cwes:
                bridge_tags = result.get("bridge_tags", [])
                files_with_cwes += 1
                total_cwes += len(cwes)
                for cwe in cwes:
                    cwe_id = cwe.get("cwe_id", "unknown")
                    cwe_summary[cwe_id] = cwe_summary.get(cwe_id, 0) + 1
                    if dry_run:
                        print(f"  [CWE] {filepath.name}: {cwe_id}", flush=True)
                    elif memory_script:
                        payload = _build_cwe_lesson_payload(filepath, cwe, bridge_tags)
                        ok = _learn(
                            memory_script,
                            payload["problem"],
                            payload["solution"],
                            scope,
                            payload["tags"],
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
    if not dry_run:
        _abort_if_memory_writes_incomplete(
            phase="cwe",
            attempted=total_cwes,
            stored=cwe_stored,
            codebase=path,
        )

    # --- Phase 3: Relationship extraction (import graph edges) ---
    edges_stored = 0
    edges_total = 0

    if not cwe_only:
        print("\n--- Phase 3: Extracting code relationships ---", flush=True)
        try:
            edges = extract_edges(files, path)
        except SourceReadError as exc:
            _exit_source_read_failure(codebase=path, phase="edges", exc=exc)
        edges_total = len(edges)
        print(f"  Found {edges_total} internal dependency edges", flush=True)
        if edges_total > 0:
            edge_description = "Previewing edges" if dry_run else "Storing edges"
            edge_monitor = Monitor(None, name="ingest-code-edges", desc=edge_description, total=edges_total) if Monitor else None
            edges_stored = store_edges(edges, scope=scope, dry_run=dry_run, monitor=edge_monitor)
            if edge_monitor:
                edge_monitor._update(final=True)
            if dry_run:
                print(f"Edges: {edges_total} previewed, 0 stored", flush=True)
            else:
                print(f"Edges: {edges_stored} stored of {edges_total} found", flush=True)
        if not dry_run:
            _abort_if_memory_writes_incomplete(
                phase="edges",
                attempted=edges_total,
                stored=edges_stored,
                codebase=path,
            )

    # --- Phase 4: Structured code symbol index ---
    code_symbols_extracted = 0
    code_symbols_stored = 0
    code_symbol_scan_roots: list[Path] = []
    completed_code_symbol_scan_roots: list[Path] = []
    discovered_file_manifest = _resolved_file_manifest(files, path)
    if treesitter and code_index and not cwe_only:
        print("\n--- Phase 4: Structured code symbols ---", flush=True)
        verification_samples: list[dict[str, str]] = []
        code_symbol_scan_roots = _extract_configured_scan_roots(path)
        if dry_run:
            for scan_root in code_symbol_scan_roots:
                try:
                    records = _extract_treesitter_records_for_directory(
                        scan_root,
                        path,
                        scope,
                        allowed_files=discovered_file_manifest,
                    )
                except TreeSitterScanError as exc:
                    print(
                        json.dumps({
                            "error": "Tree-sitter code-symbol indexing failed",
                            "scan_root": str(scan_root),
                            "detail": str(exc),
                        }),
                        file=sys.stderr,
                    )
                    raise SystemExit(1) from exc
                code_symbols_extracted += len(records)
                completed_code_symbol_scan_roots.append(scan_root)
                _print_code_symbol_dry_run_preview(records)
                print(f"Code index: {len(records)} symbols extracted from {scan_root}", flush=True)
        else:
            for scan_root in code_symbol_scan_roots:
                try:
                    root_stored = _store_treesitter_symbols_for_directory(
                        scan_root,
                        path,
                        scope,
                        verification_samples=verification_samples,
                        allowed_files=discovered_file_manifest,
                    )
                except TreeSitterScanError as exc:
                    print(
                        json.dumps({
                            "error": "Tree-sitter code-symbol indexing failed",
                            "scan_root": str(scan_root),
                            "detail": str(exc),
                        }),
                        file=sys.stderr,
                    )
                    raise SystemExit(1) from exc
                code_symbols_extracted += root_stored
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
        "code_symbols_extracted": code_symbols_extracted,
        "code_symbols_stored": code_symbols_stored,
        "dry_run": dry_run,
    }
    print(f"\n{json.dumps(result, indent=2)}")

    # --- Write marker file + store ingestion record in /memory ---
    if not dry_run:
        marker_path = _write_required_ingest_marker(
            path,
            files_scanned=len(files),
            knowledge_stored=knowledge_stored,
            cwe_stored=cwe_stored,
            edges_stored=edges_stored,
            code_symbols_stored=code_symbols_stored,
            treesitter=_treesitter_completed(completed_code_symbol_scan_roots),
            scope=scope,
            scan_roots=code_symbol_scan_roots,
            completed_scan_roots=completed_code_symbol_scan_roots,
        )
        print(f"\nMarker written: {marker_path}")

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
    try:
        mtime_threshold = _parse_since_threshold(since)
    except RescanSinceError as exc:
        _exit_invalid_since(since, exc)

    try:
        scope = _validate_memory_scope(scope)
    except MemoryScopeError as exc:
        _exit_invalid_memory_scope(scope, exc)

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
    for path in resolved_codebases:
        try:
            _preflight_scan_config(path)
        except ScanConfigError as exc:
            _exit_invalid_scan_config(path, exc)

    print(f"Rescanning {len(resolved_codebases)} codebase(s)")
    if mtime_threshold:
        print(f"Only files modified since: {mtime_threshold.isoformat()}")

    discovered_codebases: list[tuple[Path, list[Path], frozenset[Path]]] = []
    for path in resolved_codebases:
        files = _collect_files_or_exit(path, DEFAULT_GLOB_PATTERNS, mtime_after=mtime_threshold)
        discovered_codebases.append((path, files, _resolved_file_manifest(files, path)))

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

    for path, files, discovered_file_manifest in discovered_codebases:
        print(f"Found {len(files)} files in {path}")
        codebase_knowledge = 0
        codebase_cwes = 0
        codebase_ts_symbols = 0
        codebase_knowledge_attempted = 0
        codebase_cwes_attempted = 0
        code_symbol_scan_roots: list[Path] = []
        completed_code_symbol_scan_roots: list[Path] = []

        all_items: list[dict] = []
        for filepath in files:
            try:
                all_items.extend(_extract_validated_knowledge(filepath))
            except SourceReadError as exc:
                _exit_source_read_failure(codebase=path, phase="knowledge", exc=exc)
            except KnowledgeItemError as exc:
                _exit_knowledge_item_failure(codebase=path, exc=exc)

        if taxonomy:
            try:
                all_items = enrich_with_taxonomy(all_items, taxonomy)
            except TaxonomyEnrichmentError as exc:
                _exit_taxonomy_enrichment_failure(codebase=path, exc=exc)

        for item in all_items:
            codebase_knowledge_attempted += 1
            if _learn(memory_script, item["problem"], item["solution"], scope, item["tags"]):
                total_knowledge += 1
                codebase_knowledge += 1
                verify_name = _extract_verification_name(item["tags"])
                if verify_name:
                    verifiable_samples.append({
                        "name": verify_name,
                        "problem": item["problem"],
                    })

        for filepath in files:
            if filepath.suffix not in (".md", ".mdx"):
                try:
                    result = _scan_file_cwe_checked(filepath, taxonomy, validate)
                except SourceReadError as exc:
                    _exit_source_read_failure(codebase=path, phase="cwe", exc=exc)
                except CweScanResultError as exc:
                    _exit_cwe_result_failure(codebase=path, exc=exc)
                bridge_tags = result.get("bridge_tags", [])
                for cwe in result.get("cwe_mappings", []):
                    payload = _build_cwe_lesson_payload(filepath, cwe, bridge_tags)
                    codebase_cwes_attempted += 1
                    if _learn(
                        memory_script,
                        payload["problem"],
                        payload["solution"],
                        scope,
                        payload["tags"],
                    ):
                        total_cwes += 1
                        codebase_cwes += 1

        _abort_if_memory_writes_incomplete(
            phase="knowledge",
            attempted=codebase_knowledge_attempted,
            stored=codebase_knowledge,
            codebase=path,
        )
        _abort_if_memory_writes_incomplete(
            phase="cwe",
            attempted=codebase_cwes_attempted,
            stored=codebase_cwes,
            codebase=path,
        )

        # Treesitter symbol extraction (per codebase, not per file)
        if treesitter and code_index:
            code_symbol_scan_roots = _extract_configured_scan_roots(path)
            for scan_root in code_symbol_scan_roots:
                try:
                    root_stored = _store_treesitter_symbols_for_directory(
                        scan_root,
                        path,
                        scope,
                        verification_samples=verifiable_samples,
                        allowed_files=discovered_file_manifest,
                        mtime_after=mtime_threshold,
                    )
                except TreeSitterScanError as exc:
                    print(
                        json.dumps({
                            "error": "Tree-sitter code-symbol indexing failed",
                            "scan_root": str(scan_root),
                            "detail": str(exc),
                        }),
                        file=sys.stderr,
                    )
                    raise SystemExit(1) from exc
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
            "treesitter_completed": _treesitter_completed(completed_code_symbol_scan_roots),
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
        marker_path = _write_required_ingest_marker(
            marker["path"],
            files_scanned=marker["files_scanned"],
            knowledge_stored=marker["knowledge_stored"],
            cwe_stored=marker["cwe_stored"],
            edges_stored=0,
            code_symbols_stored=marker["code_symbols_stored"],
            treesitter=marker["treesitter_completed"],
            scope=scope,
            scan_roots=marker["scan_roots"],
            completed_scan_roots=marker["completed_scan_roots"],
        )
        print(f"Marker written: {marker_path}", flush=True)

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
