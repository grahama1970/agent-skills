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
from dataclasses import asdict
from enum import Enum
import hashlib
import importlib.util
import json
import os
import random
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

from code_memory_client import (
    CodeMemoryClient,
    code_graph_bundle_digest,
    write_code_projection_request,
)
from environment_manifest import write_environment_manifest
from code_freshness_preflight import refresh_allowed, run_preflight
from code_graph_artifact import write_code_graph_bundle
from code_symbol_record import CodeSymbolRecord
from incremental_state import FileComponentState, build_transform_fingerprints
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


class ProjectionMode(str, Enum):
    EMIT = "emit"
    APPLY = "apply"
    NONE = "none"


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


def _store_lessons_threaded(
    memory_script: Path,
    items: list[dict],
    scope: str,
    *,
    label: str,
) -> int:
    """Store lesson-like records with bounded concurrency and visible progress."""
    if not items:
        print(f"{label}: 0 stored of 0 attempted", flush=True)
        return 0

    try:
        workers = max(1, int(os.environ.get("INGEST_WORKERS", "8")))
    except ValueError:
        workers = 8

    stored = 0
    failed = 0
    lock = threading.Lock()

    def _learn_item(item: dict) -> bool:
        return _learn(
            memory_script,
            item["problem"],
            item["solution"],
            scope,
            item["tags"],
        )

    print(f"{label}: storing {len(items)} records with {workers} threads", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_learn_item, item) for item in items]
        for done_count, future in enumerate(as_completed(futures), start=1):
            if future.result():
                with lock:
                    stored += 1
            else:
                with lock:
                    failed += 1
            if done_count % 100 == 0 or done_count == len(items):
                print(
                    f"{label}: progress {stored} stored, {failed} blocked, "
                    f"{done_count}/{len(items)} done",
                    flush=True,
                )
    return stored


def _write_ingest_marker(
    path: Path,
    *,
    files_scanned: int,
    knowledge_stored: int,
    cwe_stored: int,
    edges_stored: int,
    code_symbols_stored: int,
    treesitter: bool,
    scope: str,
    run_status: str = "complete",
    started_at: str | None = None,
    scan_roots: list[str | Path] | None = None,
    completed_scan_roots: list[str | Path] | None = None,
    local_code_symbols_artifact: str | Path | None = None,
    local_code_symbols_written: int = 0,
    environment_manifest: dict[str, Any] | None = None,
    code_graph_artifact: dict[str, Any] | None = None,
    code_projection_request: dict[str, Any] | None = None,
    code_projection_receipt: dict[str, Any] | None = None,
) -> Path:
    """Write the local ingest-code marker consumed by monitor-codebase."""
    now = datetime.now().isoformat()
    marker = {
        "ingested_at": now,
        "started_at": started_at or now,
        "completed_at": now if run_status == "complete" else None,
        "path": str(path.resolve()),
        "stem": path.resolve().name,
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
            "projection_mode": (
                code_projection_request or code_projection_receipt or {}
            ).get("projection_mode"),
            "bundle_validated": bool(code_graph_artifact),
            "projection_requested": bool(code_projection_request),
            "projection_applied": bool(code_projection_receipt),
            "projection_status": (
                "applied"
                if code_projection_receipt
                else "requested_not_applied"
                if code_projection_request
                else "not_requested"
            ),
            "projection_authority": "memory.code_projection.apply_receipt.v1"
            if code_projection_receipt
            else None,
            "projection_generation_id": (
                (code_projection_receipt.get("generation") or {}).get("generation_id")
                if code_projection_receipt
                else None
            ),
            "projection_bundle_digest": (
                code_projection_receipt.get("submitted_bundle_digest")
                if code_projection_receipt
                else None
            ),
        },
        "scope": scope,
        "run_status": run_status,
        "completed": run_status == "complete",
        "scan_roots": [str(Path(root).resolve()) for root in (scan_roots or [])],
        "completed_scan_roots": [
            str(Path(root).resolve()) for root in (completed_scan_roots or [])
        ],
        "local_artifacts": {
            "code_symbols_jsonl": (
                str(Path(local_code_symbols_artifact).resolve())
                if local_code_symbols_artifact else None
            ),
            "code_symbols_written": local_code_symbols_written,
            "environment_manifest": environment_manifest,
            "code_graph": code_graph_artifact,
            "code_projection_request": code_projection_request,
            "code_projection_receipt": code_projection_receipt,
            "cleanup_evidence": str((path / ".cleanup-evidence.json").resolve()),
        },
    }
    marker_path = path / ".ingest-code.json"
    marker_path.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n")
    return marker_path


def _prepare_local_code_symbols_artifact(codebase_root: Path) -> Path:
    """Create an empty local JSONL code-symbol artifact for offline agents."""
    artifact = codebase_root / "artifacts" / "ingest-code" / "code-symbols.jsonl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("")
    return artifact


def _append_local_code_symbols(artifact: Path, records: list[CodeSymbolRecord]) -> int:
    """Append code symbols as JSONL so agents can inspect them without Memory."""
    if not records:
        return 0
    with artifact.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_document(), sort_keys=True) + "\n")
    return len(records)


def build_marker_status(path: Path) -> dict[str, Any]:
    """Return normalized status for a repository's local ingest marker."""
    marker_path = path / ".ingest-code.json"
    if not marker_path.exists():
        return {
            "status": "missing",
            "path": str(path.resolve()),
            "stem": path.resolve().name,
            "code_index": {"enabled": False},
        }
    try:
        marker = json.loads(marker_path.read_text())
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid",
            "path": str(path.resolve()),
            "stem": path.resolve().name,
            "error": str(exc),
            "code_index": {"enabled": False},
        }
    status = "fresh" if marker.get("run_status") == "complete" and marker.get("completed") is True else "running"
    marker["status"] = status
    return marker


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

    chosen = random.sample(samples, min(sample_size, len(samples)))
    failures: list[dict[str, str]] = []
    passed = 0

    for sample in chosen:
        name = sample["name"]
        problem = sample["problem"]
        try:
            result = _recall_http(name, k=1)
            items = _recall_items(result)
            if items and _recall_item_matches_name(items[0], name):
                passed += 1
            else:
                failures.append({
                    "name": name,
                    "problem": problem,
                    "reason": "recall did not return matching entry",
                })
        except Exception as exc:
            failures.append({
                "name": name,
                "problem": problem,
                "reason": str(exc),
            })

    return {
        "requested": sample_size,
        "checked": len(chosen),
        "passed": passed,
        "failed": len(failures),
        "failures": failures,
    }


def _expected_projection_counts(code_graph_artifact: dict[str, Any]) -> dict[str, int]:
    counts = code_graph_artifact.get("counts") or {}
    return {
        "files": int(counts.get("files", 0)),
        "symbols": int(counts.get("symbols", 0)),
        "edges": int(counts.get("edges_active_for_traversal", counts.get("edges", 0))),
    }


def _apply_code_projection_artifact(
    *,
    path: Path,
    scope: str,
    code_graph_artifact: dict[str, Any],
    environment_manifest: dict[str, Any] | None = None,
    client: CodeMemoryClient | None = None,
):
    """Submit one complete code graph artifact to Memory/GMO and require a bound receipt."""
    expected_counts = _expected_projection_counts(code_graph_artifact)
    bundle_path = Path(code_graph_artifact["path"])
    submitted_bundle_digest = code_graph_bundle_digest(bundle_path)
    idempotency_key = "ingest-code:" + hashlib.sha256(
        json.dumps([scope, submitted_bundle_digest, expected_counts], sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    active_client = client or CodeMemoryClient()
    return active_client.apply_code_projection_bundle(
        bundle_path=bundle_path,
        scope=scope,
        repo=path.resolve().name,
        branch=_current_branch(path),
        root=str(path.resolve()),
        source_commit=_current_commit(path),
        expected_counts=expected_counts,
        idempotency_key=idempotency_key,
        environment_manifest_digest=(
            environment_manifest or {}
        ).get("environment_manifest_digest"),
    )


def _projection_request_for_artifact(
    *,
    path: Path,
    scope: str,
    code_graph_artifact: dict[str, Any],
    environment_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit a code projection request artifact without opening the Memory socket."""
    expected_counts = _expected_projection_counts(code_graph_artifact)
    bundle_path = Path(code_graph_artifact["path"])
    submitted_bundle_digest = code_graph_bundle_digest(bundle_path)
    idempotency_key = "gmo-code-projection:" + hashlib.sha256(
        json.dumps([scope, path.resolve().name, _current_branch(path), submitted_bundle_digest], sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    result = write_code_projection_request(
        bundle_path=bundle_path,
        scope=scope,
        repo=path.resolve().name,
        branch=_current_branch(path),
        root=str(path.resolve()),
        source_commit=_current_commit(path),
        expected_counts=expected_counts,
        idempotency_key=idempotency_key,
        environment_manifest_digest=(
            environment_manifest or {}
        ).get("environment_manifest_digest"),
    )
    return {
        "schema": "ingest-code.code_projection_request_artifact.v1",
        "projection_mode": ProjectionMode.EMIT.value,
        "path": str(result.request_path.resolve()),
        "sha256": result.request_digest,
        "submitted_bundle_digest": result.submitted_bundle_digest,
        "checksums_digest": result.checksums_digest,
        "idempotency_key": idempotency_key,
        "environment_manifest_digest": (
            environment_manifest or {}
        ).get("environment_manifest_digest"),
        "status": "emitted_not_applied",
        "non_claims": result.request.get("non_claims", []),
    }


def _legacy_projection_flags_present() -> bool:
    return any(arg in {"--code-index", "--no-code-index"} for arg in sys.argv[1:])


def _resolve_projection_mode(
    projection_mode: ProjectionMode | None,
    *,
    code_index: bool,
    compat_symbol_upsert: bool,
) -> ProjectionMode:
    if not isinstance(projection_mode, ProjectionMode):
        projection_mode = None
    if projection_mode is not None:
        if _legacy_projection_flags_present():
            print(
                "[ERROR] --projection-mode conflicts with legacy --code-index/--no-code-index flags",
                file=sys.stderr,
                flush=True,
            )
            raise SystemExit(2)
        if compat_symbol_upsert and projection_mode is not ProjectionMode.APPLY:
            print(
                "[ERROR] --compat-symbol-upsert is only compatible with --projection-mode apply",
                file=sys.stderr,
                flush=True,
            )
            raise SystemExit(2)
        return projection_mode
    return ProjectionMode.APPLY if code_index else ProjectionMode.NONE


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
        source_docstring=docstring,
        code=code,
        imports=_flatten_import_symbols(imports),
        parameters=parameters,
        local_variables=local_variables,
        called_symbols=called_symbols,
        string_literals=string_literals,
        content_hash=_content_hash(code or signature or docstring or name),
        tags=tags,
    )


def _extract_configured_scan_roots(codebase_path: Path) -> list[Path]:
    """Resolve scan roots from env override or .monitor-codebase.json include_dirs."""
    env_roots = os.environ.get("CODE_SYMBOLS_SCAN_INCLUDE_DIRS")
    if env_roots and env_roots.strip():
        roots: list[Path] = []
        for include_dir in env_roots.split(","):
            include_dir = include_dir.strip()
            if not include_dir:
                continue
            full = (codebase_path / include_dir).resolve()
            if full.is_dir():
                roots.append(full)
        return roots

    config = _load_monitor_config(codebase_path)
    if config and config.get("include_dirs"):
        roots: list[Path] = []
        for include_dir in config["include_dirs"]:
            full = (codebase_path / include_dir).resolve()
            if full.is_dir():
                roots.append(full)
        return roots
    return [codebase_path.resolve()]


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


def _parse_treesitter_symbol_lines(stdout: str, filepath: Path) -> list[dict[str, Any]]:
    """Parse `treesitter symbols --ndjson` output into one file-entry shape."""
    symbols: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            symbols.append(payload)
    return [{"path": str(filepath), "symbols": symbols}] if symbols else []


def _store_treesitter_symbols_for_directory(
    directory: Path,
    codebase_root: Path,
    scope: str,
    verification_samples: Optional[list[dict[str, str]]] = None,
    local_artifact_path: Optional[Path] = None,
) -> int:
    """Scan one directory, write local symbols, and upsert symbols to memory."""
    records = _scan_treesitter_symbol_records_for_directory(directory, codebase_root, scope)

    if local_artifact_path is not None:
        _append_local_code_symbols(local_artifact_path, records)

    result = CodeMemoryClient().upsert_code_symbols(records)
    for error in result.errors[:5]:
        print(f"  [WARN] {error}", file=sys.stderr, flush=True)

    if verification_samples is not None:
        for record in records[:result.stored]:
            verification_samples.append({
                "name": record.symbol_name,
                "problem": record.problem,
            })

    return result.stored


def _records_from_treesitter_file_entries(
    scan_results: list[dict[str, Any]],
    *,
    codebase_root: Path,
    scope: str,
) -> list[CodeSymbolRecord]:
    repo = codebase_root.resolve().name
    branch = _current_branch(codebase_root)
    commit = _current_commit(codebase_root)
    records: list[CodeSymbolRecord] = []
    for file_entry in scan_results:
        file_path_raw = file_entry.get("path")
        if not file_path_raw:
            continue

        filepath = Path(file_path_raw)
        if not filepath.is_absolute():
            filepath = codebase_root / filepath
        symbol_context = _extract_symbol_context(filepath)

        for symbol in file_entry.get("symbols", []):
            record = _build_code_symbol_record(
                symbol=symbol,
                filepath=filepath,
                codebase_root=codebase_root,
                scope=scope,
                repo=repo,
                branch=branch,
                commit=commit,
                imports=symbol_context["imports"],
            )
            if record is None:
                continue
            records.append(record)
    return records


def _scan_treesitter_symbol_records_for_directory(
    directory: Path,
    codebase_root: Path,
    scope: str,
) -> list[CodeSymbolRecord]:
    """Scan one directory and return CodeSymbolRecord instances without writing Memory."""
    directory = directory.resolve()
    codebase_root = codebase_root.resolve()
    treesitter_script = find_treesitter_skill()
    if not treesitter_script:
        print(f"Treesitter skill not found for {directory}", file=sys.stderr, flush=True)
        return []

    cmd = [
        "bash",
        str(treesitter_script),
        "scan",
        str(directory),
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
        return []

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            print(f"Treesitter scan failed for {directory}: {stderr}", file=sys.stderr, flush=True)
        return []

    scan_results = _parse_treesitter_scan_output(result.stdout)
    if not scan_results:
        return []

    return _records_from_treesitter_file_entries(scan_results, codebase_root=codebase_root, scope=scope)


def _scan_treesitter_symbol_records_for_file(
    filepath: Path,
    codebase_root: Path,
    scope: str,
) -> list[CodeSymbolRecord]:
    """Scan one source file and return CodeSymbolRecord instances."""
    filepath = filepath.resolve()
    codebase_root = codebase_root.resolve()
    treesitter_script = find_treesitter_skill()
    if not treesitter_script:
        print(f"Treesitter skill not found for {filepath}", file=sys.stderr, flush=True)
        return []

    cmd = [
        "bash",
        str(treesitter_script),
        "symbols",
        str(filepath),
        "--content",
        "--ndjson",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(treesitter_script.parent),
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
    except subprocess.TimeoutExpired:
        print(f"Treesitter symbol scan timed out for {filepath}", file=sys.stderr, flush=True)
        return []

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            print(f"Treesitter symbol scan failed for {filepath}: {stderr}", file=sys.stderr, flush=True)
        return []

    scan_results = _parse_treesitter_symbol_lines(result.stdout, filepath)
    return _records_from_treesitter_file_entries(scan_results, codebase_root=codebase_root, scope=scope)


def _code_files_within_scan_roots(files: list[Path], scan_roots: list[Path], codebase_root: Path) -> list[Path]:
    roots = [root.resolve() for root in scan_roots] or [codebase_root.resolve()]
    result: list[Path] = []
    for filepath in files:
        resolved = filepath.resolve()
        for root in roots:
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            result.append(resolved)
            break
    return sorted(set(result), key=lambda item: _relative_path(item, codebase_root))


def _record_from_component_payload(payload: dict[str, Any]) -> CodeSymbolRecord:
    allowed = set(CodeSymbolRecord.__dataclass_fields__)
    values = {key: payload[key] for key in allowed if key in payload}
    return CodeSymbolRecord(**values)


def _symbols_by_path(records: list[CodeSymbolRecord]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record.normalized_path, []).append(asdict(record))
    for rel_path in grouped:
        grouped[rel_path].sort(key=lambda item: (item.get("qualified_name", ""), item.get("start_line", 0)))
    return grouped


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
        if isinstance(node, ast.ImportFrom):
            imports.append({
                "module": node.module or "",
                "names": [alias.name for alias in node.names],
                "line": node.lineno,
                "col_offset": getattr(node, "col_offset", 0),
                "end_line": getattr(node, "end_lineno", node.lineno),
                "end_col_offset": getattr(node, "end_col_offset", 0),
                "level": int(getattr(node, "level", 0) or 0),
            })
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "module": alias.name,
                    "names": [],
                    "line": node.lineno,
                    "col_offset": getattr(node, "col_offset", 0),
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "end_col_offset": getattr(node, "end_col_offset", 0),
                    "level": 0,
                })
    return imports


def build_module_index(files: list[Path], codebase_root: Path) -> dict[str, Path]:
    """Build a mapping from Python module dotted path → file path."""
    index: dict[str, Path] = {}
    root = codebase_root.resolve()
    for fp in files:
        fp = fp.resolve()
        if fp.suffix != ".py":
            continue
        try:
            rel = fp.relative_to(root)
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


def _resolve_python_relative_import_module(
    filepath: Path,
    codebase_root: Path,
    module: str,
    level: int,
) -> str:
    if level <= 0:
        return module
    try:
        rel = filepath.resolve().relative_to(codebase_root.resolve())
    except ValueError:
        return module
    package_parts = list(rel.parent.parts)
    keep_count = max(0, len(package_parts) - level + 1)
    module_parts = [part for part in module.split(".") if part]
    return ".".join([*package_parts[:keep_count], *module_parts])


def extract_edges(
    files: list[Path],
    codebase_root: Path,
    treesitter_sh: Optional[Path] = None,
) -> list[dict]:
    """Extract import-based dependency edges between files in the codebase.

    The returned records preserve unresolved and candidate imports for the code
    graph artifact, but only resolved edges are active for traversal/storage.
    """
    codebase_root = codebase_root.resolve()
    files = [filepath.resolve() for filepath in files]
    module_index = build_module_index(files, codebase_root)
    edges: list[dict] = []

    for filepath in files:
        if filepath.suffix != ".py":
            continue
        imports = extract_python_imports(filepath)
        for imp in imports:
            module = _resolve_python_relative_import_module(
                filepath,
                codebase_root,
                imp["module"],
                int(imp.get("level") or 0),
            )
            candidate_files: list[str] = []
            for name in imp.get("names", []):
                candidate = module_index.get(".".join(part for part in [module, name] if part))
                if candidate and candidate != filepath:
                    candidate_files.append(str(candidate))
            target = module_index.get(module)
            if candidate_files and (not target or target.name == "__init__.py"):
                unique_candidates = sorted(set(candidate_files))
                if len(unique_candidates) == 1:
                    target = Path(unique_candidates[0])
                    candidate_files = []
            if not target and candidate_files:
                if len(set(candidate_files)) == 1:
                    target = Path(candidate_files[0])
                    candidate_files = []
            resolution_status = "resolved" if target and target != filepath else "unresolved"
            edges.append({
                "from_file": str(filepath),
                "to_file": str(target) if resolution_status == "resolved" else None,
                "edge_type": "depends_on",
                "module": module,
                "names": imp.get("names", []),
                "line": imp.get("line"),
                "col_offset": imp.get("col_offset"),
                "end_line": imp.get("end_line"),
                "end_col_offset": imp.get("end_col_offset"),
                "level": imp.get("level", 0),
                "resolution_status": resolution_status,
                "resolution_method": "python_import_alias_and_scope",
                "candidate_files": sorted(set(candidate_files)),
                "unresolved_reason": "" if resolution_status == "resolved" else "module_not_in_scan",
                "attempted_resolution_stages": [
                    "exact_module_path",
                    "relative_import_module_scope",
                    "candidate_or_unresolved",
                ],
            })

    return edges


def store_edges(edges: list[dict], scope: str = "code", dry_run: bool = False, monitor=None) -> int:
    """Store dependency edges in /memory via batch HTTP endpoint."""
    if dry_run:
        stored = 0
        for edge in edges:
            if edge.get("resolution_status", "resolved") != "resolved" or not edge.get("to_file"):
                continue
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
        if edge.get("resolution_status", "resolved") != "resolved" or not edge.get("to_file"):
            continue
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
                    if path.is_file() and path.suffix in extensions:
                        files.append(path)
    except Exception:
        pass
    return files


def collect_files(codebase_path: Path, patterns: list[str], mtime_after: Optional[datetime] = None) -> list[Path]:
    """Collect files matching patterns, respecting .gitignore and .monitor-codebase.json."""
    config = _load_monitor_config(codebase_path)
    exclude_dirs = SKIP_DIRS.copy()
    if config:
        exclude_dirs.update(config.get("exclude_dirs", []))

    files: list[Path] = []

    # Determine scan roots — either scoped dirs or full codebase
    scan_roots = _extract_configured_scan_roots(codebase_path)

    # Use git ls-files if in a git repo (respects .gitignore)
    use_git = _is_git_repo(codebase_path)

    for root in scan_roots:
        if use_git and root == codebase_path:
            # Use git ls-files for the main codebase root
            git_files = _git_ls_files(root, patterns)
            for f in git_files:
                if any(skip in f.parts for skip in exclude_dirs):
                    continue
                if mtime_after:
                    try:
                        file_mtime = datetime.fromtimestamp(f.stat().st_mtime)
                        if file_mtime < mtime_after:
                            continue
                    except OSError:
                        continue
                files.append(f)
        else:
            # Fallback to rglob for non-git or scoped subdirectories
            for pattern in patterns:
                for f in root.rglob(pattern):
                    if any(skip in f.parts for skip in exclude_dirs):
                        continue
                    if mtime_after:
                        file_mtime = datetime.fromtimestamp(f.stat().st_mtime)
                        if file_mtime < mtime_after:
                            continue
                    files.append(f)

    # Also include markdown docs at project root (always)
    for md_name in ["CONTEXT.md", "README.md", "CLAUDE.md", "MEMORY.md", "AGENTS.md"]:
        md_path = codebase_path / md_name
        if md_path.exists() and md_path not in files:
            files.append(md_path)
    # Recurse for local/docs/*.md and local/*.md
    for local_dir in [codebase_path / "local" / "docs", codebase_path / "local"]:
        if local_dir.exists():
            for md in local_dir.glob("*.md"):
                if md not in files:
                    files.append(md)
    docs_dir = codebase_path / "docs"
    if docs_dir.exists():
        for md in docs_dir.glob("*.md"):
            if md not in files:
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


@cli.command("ensure-current")
def ensure_current(
    repo: Path = typer.Option(..., "--repo", help="Repository worktree to check."),
    branch: str = typer.Option("", "--branch", help="Expected branch/ref name. Defaults to current branch."),
    commit: str = typer.Option("", "--commit", help="Expected commit SHA. Defaults to current HEAD."),
    target_paths: list[str] = typer.Option([], "--path", help="Repository-relative target path. Repeatable."),
    scope: str = typer.Option("code", "--scope", help="Memory/GMO projection scope."),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Emit machine-readable JSON."),
    refresh: bool = typer.Option(False, "--refresh", help="Refresh canonical projection when policy allows it."),
    canonical_branch: str = typer.Option("main", "--canonical-branch", help="Branch allowed to activate canonical projection."),
    max_target_files: int = typer.Option(200, "--max-target-files", min=1, max=1000),
):
    """Check whether Memory/GMO's active code projection is fresh for target paths."""
    repo = repo.expanduser().resolve()
    requested_branch = branch or _current_branch(repo)
    requested_commit = commit or _current_commit(repo)
    receipt = run_preflight(
        repo=repo,
        branch=requested_branch,
        commit=requested_commit,
        targets=target_paths,
        scope=scope,
        max_target_files=max_target_files,
    )

    if refresh and receipt.get("status") in {"STALE", "UNINDEXED", "SOURCE_CURRENT_INDEX_INCOMPLETE"}:
        allowed, errors = refresh_allowed(
            repo=repo,
            branch=requested_branch,
            commit=requested_commit,
            canonical_branch=canonical_branch,
        )
        if not allowed:
            receipt["status"] = "BLOCKED"
            receipt["modification_ready"] = False
            receipt["absence_claims_allowed"] = False
            receipt.setdefault("errors", []).extend(errors)
            receipt.setdefault("unresolved_limitations", []).append(
                "canonical projection refresh refused by checkout policy"
            )
        else:
            scan(
                path=repo,
                glob=[],
                cwe_only=False,
                validate=False,
                treesitter=True,
                code_index=True,
                compat_symbol_upsert=False,
                dry_run=False,
                scope=scope,
                batch_size=50,
            )
            receipt = run_preflight(
                repo=repo,
                branch=requested_branch,
                commit=requested_commit,
                targets=target_paths,
                scope=scope,
                max_target_files=max_target_files,
            )
            receipt["refresh_attempted"] = True

    if json_output:
        print(json.dumps(receipt, indent=2, sort_keys=True), flush=True)
    else:
        print(f"{receipt.get('status')}: {', '.join(receipt.get('target_paths') or [])}", flush=True)
        for error in receipt.get("errors") or []:
            print(f"  error: {error}", file=sys.stderr, flush=True)

    if receipt.get("status") == "BLOCKED":
        raise typer.Exit(2)


@cli.command()
def scan(
    path: Path = typer.Argument(help="Codebase path to scan"),
    glob: list[str] = typer.Option([], "-g", "--glob", help="File patterns to scan"),
    cwe_only: bool = typer.Option(False, "--cwe-only", help="Only scan for CWEs (legacy mode)"),
    validate: bool = typer.Option(False, "--validate/--no-validate", help="Run LLM validation on CWEs"),
    treesitter: bool = typer.Option(False, "--treesitter", help="Run treesitter scan for structured code symbols"),
    code_index: bool = typer.Option(True, "--code-index/--no-code-index", help="Apply treesitter code graph bundle to Memory/GMO projection"),
    projection_mode: ProjectionMode | None = typer.Option(None, "--projection-mode", help="Projection handling: emit, apply, or none"),
    compat_symbol_upsert: bool = typer.Option(False, "--compat-symbol-upsert", help="Use legacy per-symbol upserts instead of complete projection application"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be stored without writing"),
    scope: str = typer.Option("code", help="Memory scope for storage"),
    batch_size: int = typer.Option(50, help="Files per batch"),
):
    """Scan a codebase for functional knowledge and CWE mappings, store in /memory."""
    selected_projection_mode = _resolve_projection_mode(
        projection_mode,
        code_index=code_index,
        compat_symbol_upsert=compat_symbol_upsert,
    )
    taxonomy = load_taxonomy_module()
    memory_script = find_memory_skill()

    if not memory_script and not dry_run and selected_projection_mode is not ProjectionMode.EMIT:
        print('{"error": "Memory skill not found"}', file=sys.stderr)
        raise SystemExit(1)

    # Collect files
    patterns = list(glob) if glob else DEFAULT_GLOB_PATTERNS
    files = collect_files(path, patterns)
    print(f"Found {len(files)} files to scan in {path}", flush=True)

    # Build deterministic structured artifacts before Memory writes. This leaves
    # inspectable extraction evidence even when later upserts fail.
    code_symbol_scan_roots: list[Path] = []
    code_symbol_records: list[CodeSymbolRecord] = []
    component_state = None
    component_plan = None
    current_entries: dict[str, str] = {}
    code_symbols_pruned = 0
    code_projection_request: dict[str, Any] | None = None
    code_projection_receipt: dict[str, Any] | None = None
    environment_manifest = write_environment_manifest(
        path / "artifacts" / "ingest-code" / "environment_manifest.json",
        skill_root=Path(__file__).parent,
        source_root=path,
        projection_mode=selected_projection_mode.value,
        argv=sys.argv,
        terminal_status="complete",
    )
    precomputed_edges: list[dict[str, Any]] | None = None
    code_graph_artifact: dict[str, Any] | None = None
    local_code_symbols_artifact: Path | None = None
    local_code_symbols_written = 0
    if treesitter and not cwe_only:
        print("\n--- Preparing deterministic code graph artifacts ---", flush=True)
        code_symbol_scan_roots = _extract_configured_scan_roots(path)
        local_code_symbols_artifact = _prepare_local_code_symbols_artifact(path)
        repo_name = path.resolve().name
        branch = _current_branch(path)
        rel_scan_roots = [
            _relative_path(scan_root, path) if scan_root.resolve() != path.resolve() else "."
            for scan_root in code_symbol_scan_roots
        ]
        transform_fingerprints = build_transform_fingerprints(
            Path(__file__).parent,
            scope=scope,
            patterns=patterns,
            scan_roots=rel_scan_roots,
        )
        component_state = FileComponentState(
            path / "artifacts" / "ingest-code" / "incremental-components.json",
            repo=repo_name,
            branch=branch,
            transform_fingerprints=transform_fingerprints,
        )
        code_files = _code_files_within_scan_roots(files, code_symbol_scan_roots, path)
        component_plan = component_state.plan(code_files, path)
        code_symbol_records.extend(
            _record_from_component_payload(payload)
            for payload in component_state.reused_symbols(component_plan.reused)
        )
        parsed_count = 0
        for rel_path in component_plan.to_parse:
            filepath = path / rel_path
            root_records = _scan_treesitter_symbol_records_for_file(filepath, path, scope)
            parsed_count += 1
            code_symbol_records.extend(root_records)
            print(f"Code graph: {len(root_records)} symbols extracted from {rel_path}", flush=True)
        code_symbol_records.sort(key=lambda item: (item.normalized_path, item.qualified_name, item.start_line))
        print(
            "File components: "
            f"{parsed_count} parsed, {len(component_plan.reused)} reused, {len(component_plan.deleted)} deleted",
            flush=True,
        )
        local_code_symbols_written = _append_local_code_symbols(local_code_symbols_artifact, code_symbol_records)
        precomputed_edges = extract_edges(files, path)
        code_graph_artifact = write_code_graph_bundle(
            codebase_root=path,
            repo=repo_name,
            branch=branch,
            commit=_current_commit(path),
            scan_roots=code_symbol_scan_roots,
            files=files,
            symbols=code_symbol_records,
            edges=precomputed_edges,
            environment_manifest_digest=environment_manifest["environment_manifest_digest"],
        )
        print(f"Code graph artifacts: {code_graph_artifact['path']}", flush=True)

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
        edges = precomputed_edges if precomputed_edges is not None else extract_edges(files, path)
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
    if treesitter and selected_projection_mode is not ProjectionMode.NONE and not cwe_only:
        print("\n--- Phase 4: Structured code projection boundary ---", flush=True)
        if dry_run:
            print("  [DRY RUN] code projection request/application skipped", flush=True)
        elif not code_graph_artifact:
            print("  [ERROR] code graph artifact missing; refusing projection write", file=sys.stderr, flush=True)
            raise SystemExit(1)
        elif selected_projection_mode is ProjectionMode.EMIT:
            code_projection_request = _projection_request_for_artifact(
                path=path,
                scope=scope,
                code_graph_artifact=code_graph_artifact,
                environment_manifest=environment_manifest,
            )
            print(
                "Code projection request: "
                f"{code_projection_request['path']} (not applied)",
                flush=True,
            )
        elif not compat_symbol_upsert:
            apply_result = _apply_code_projection_artifact(
                path=path,
                scope=scope,
                code_graph_artifact=code_graph_artifact,
                environment_manifest=environment_manifest,
            )
            if apply_result.errors:
                for error in apply_result.errors[:5]:
                    print(f"  [ERROR] projection apply: {error}", file=sys.stderr, flush=True)
                raise SystemExit(1)
            code_symbols_stored = apply_result.stored
            code_projection_receipt = apply_result.receipt
            if component_state and component_plan and code_graph_artifact:
                component_state.commit(
                    current_sources=component_plan.current_sources,
                    symbols_by_path=_symbols_by_path(code_symbol_records),
                    bundle_digest=apply_result.submitted_bundle_digest,
                    accepted_complete_bundle=bool(code_graph_artifact.get("complete")),
                    receipt={
                        "schema": "ingest-code.projection_application_receipt.v1",
                        "component_plan": component_plan.summary(),
                        "symbols_total": len(code_symbol_records),
                        "symbols_written": apply_result.stored,
                        "bundle_path": code_graph_artifact["path"],
                        "memory_receipt": apply_result.receipt,
                    },
                )
            print(
                "Code projection: "
                f"{code_symbols_stored} symbols activated via complete bundle",
                flush=True,
            )
        else:
            print(
                "  [WARN] --compat-symbol-upsert uses legacy per-symbol writes; "
                "this is not complete-projection lifecycle authority",
                file=sys.stderr,
                flush=True,
            )
            verification_samples: list[dict[str, str]] = []
            memory_result = CodeMemoryClient().upsert_code_symbols(code_symbol_records)
            code_symbols_stored = memory_result.stored
            if not memory_result.errors:
                if component_state and component_plan and code_graph_artifact:
                    bundle_checksum = hashlib.sha256(
                        Path(code_graph_artifact["checksums"]).read_bytes()
                    ).hexdigest()
                    component_state.commit(
                        current_sources=component_plan.current_sources,
                        symbols_by_path=_symbols_by_path(code_symbol_records),
                        bundle_digest=f"sha256:{bundle_checksum}",
                        accepted_complete_bundle=bool(code_graph_artifact.get("complete")),
                        receipt={
                            "schema": "ingest-code.incremental_receipt.v1",
                            "component_plan": component_plan.summary(),
                            "symbols_total": len(code_symbol_records),
                            "symbols_written": memory_result.stored,
                            "bundle_path": code_graph_artifact["path"],
                        },
                    )
            for error in memory_result.errors[:5]:
                print(f"  [WARN] {error}", file=sys.stderr, flush=True)
            for record in code_symbol_records[:memory_result.stored]:
                verification_samples.append({
                    "name": record.symbol_name,
                    "problem": record.problem,
                })
            print(f"Code index: {code_symbols_stored} symbols stored", flush=True)

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
        "file_components": component_plan.summary() if component_plan else None,
        "local_code_symbols_written": local_code_symbols_written,
        "local_code_symbols_artifact": str(local_code_symbols_artifact) if local_code_symbols_artifact else None,
        "environment_manifest": environment_manifest,
        "code_graph_artifact": code_graph_artifact,
        "code_projection_request": code_projection_request,
        "code_projection_receipt": code_projection_receipt,
        "projection_mode": selected_projection_mode.value,
        "dry_run": dry_run,
    }
    print(f"\n{json.dumps(result, indent=2)}")

    # --- Write marker file + store ingestion record in /memory ---
    if not dry_run and (knowledge_stored > 0 or code_symbols_stored > 0 or local_code_symbols_written > 0):
        try:
            scan_roots = code_symbol_scan_roots if treesitter else []
            marker_path = _write_ingest_marker(
                path,
                files_scanned=len(files),
                knowledge_stored=knowledge_stored,
                cwe_stored=cwe_stored,
                edges_stored=edges_stored,
                code_symbols_stored=code_symbols_stored,
                treesitter=bool(treesitter and code_index and code_symbols_stored > 0),
                scope=scope,
                scan_roots=scan_roots,
                completed_scan_roots=scan_roots if code_symbols_stored > 0 else [],
                local_code_symbols_artifact=local_code_symbols_artifact,
                local_code_symbols_written=local_code_symbols_written,
                environment_manifest=environment_manifest,
                code_graph_artifact=code_graph_artifact,
                code_projection_request=code_projection_request,
                code_projection_receipt=code_projection_receipt,
            )
            print(f"\nMarker written: {marker_path}")
        except Exception as e:
            print(f"Warning: Could not write marker file: {e}", file=sys.stderr)

        # Store ingestion record in /memory for discoverability
        _learn_http(
            problem=f"Has codebase {path.resolve().name} been indexed for semantic search?",
            solution=f"Yes, indexed on {datetime.now().isoformat()}. {knowledge_stored} lessons, {code_symbols_stored} code symbols, {cwe_stored} CWEs. Path: {path.resolve()}",
            scope="system",
            tags=["ingest-code", "indexed-codebase", path.resolve().name, str(path.resolve())],
        )


@cli.command()
def rescan(
    since: Optional[str] = typer.Option(None, help="Only files modified since (ISO date or '1d', '7d', etc.)"),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Run LLM validation"),
    treesitter: bool = typer.Option(False, "--treesitter", help="Run treesitter scan for symbol extraction"),
    code_index: bool = typer.Option(True, "--code-index/--no-code-index", help="Upsert treesitter symbols to memory code_symbols"),
    projection_mode: ProjectionMode | None = typer.Option(None, "--projection-mode", help="Projection handling: emit, apply, or none"),
    verify_embeddings: bool = typer.Option(False, "--verify-embeddings", help="Spot-check recalled embeddings for stored symbols"),
    scope: str = typer.Option("code", help="Memory scope for storage"),
    codebase: list[str] = typer.Option([], "-c", "--codebase", help="Codebase paths to rescan"),
):
    """Nightly rescan for living document updates. Designed for /scheduler."""
    selected_projection_mode = _resolve_projection_mode(
        projection_mode,
        code_index=code_index,
        compat_symbol_upsert=False,
    )
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

    print(f"Rescanning {len(codebases)} codebase(s)", flush=True)
    if mtime_threshold:
        print(f"Only files modified since: {mtime_threshold.isoformat()}", flush=True)

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

    for codebase_path in codebases:
        started_at = datetime.now().isoformat()
        path = Path(codebase_path).resolve()
        files = collect_files(path, DEFAULT_GLOB_PATTERNS, mtime_after=mtime_threshold)
        print(f"Found {len(files)} files in {path}", flush=True)

        all_items: list[dict] = []
        for filepath in files:
            all_items.extend(extract_knowledge(filepath))
        if taxonomy:
            all_items = enrich_with_taxonomy(all_items, taxonomy)
        codebase_knowledge = _store_lessons_threaded(
            memory_script,
            all_items,
            scope,
            label=f"Knowledge[{path.name}]",
        )
        total_knowledge += codebase_knowledge
        for item in all_items:
            verify_name = _extract_verification_name(item["tags"])
            if verify_name:
                verifiable_samples.append({
                    "name": verify_name,
                    "problem": item["problem"],
                })

        cwe_items: list[dict] = []
        for filepath in files:
            if taxonomy and filepath.suffix not in (".md", ".mdx"):
                result = scan_file_cwe(filepath, taxonomy, validate)
                for cwe in result.get("cwe_mappings", []):
                    cwe_id = cwe.get("cwe_id", "unknown")
                    tags = ["ingest-code", "cwe", cwe_id, filepath.suffix.lstrip(".")]
                    cwe_items.append({
                        "problem": f"What CWEs are relevant to {filepath.name}?",
                        "solution": f"{cwe_id} ({cwe.get('name', '')}) - File: {filepath}",
                        "tags": tags,
                    })
        codebase_cwes = _store_lessons_threaded(
            memory_script,
            cwe_items,
            scope,
            label=f"CWE[{path.name}]",
        )
        total_cwes += codebase_cwes

        # Treesitter symbol extraction (per codebase, not per file)
        code_symbol_scan_roots: list[Path] = []
        completed_code_symbol_scan_roots: list[Path] = []
        local_code_symbols_artifact = None
        local_code_symbols_written = 0
        codebase_ts_symbols = 0
        code_graph_artifact: dict[str, Any] | None = None
        code_projection_request: dict[str, Any] | None = None
        code_projection_receipt: dict[str, Any] | None = None
        environment_manifest = write_environment_manifest(
            path / "artifacts" / "ingest-code" / "environment_manifest.json",
            skill_root=Path(__file__).parent,
            source_root=path,
            projection_mode=selected_projection_mode.value,
            argv=sys.argv,
            terminal_status="complete",
        )
        if treesitter and selected_projection_mode is not ProjectionMode.NONE:
            code_symbol_scan_roots = _extract_configured_scan_roots(path)
            local_code_symbols_artifact = _prepare_local_code_symbols_artifact(path)
            projection_files = collect_files(path, DEFAULT_GLOB_PATTERNS)
            projection_records: list[CodeSymbolRecord] = []
            for scan_root in code_symbol_scan_roots:
                root_records = _scan_treesitter_symbol_records_for_directory(scan_root, path, scope)
                projection_records.extend(root_records)
                completed_code_symbol_scan_roots.append(scan_root)
                print(f"Treesitter: {len(root_records)} symbols extracted from {scan_root}", flush=True)
            projection_records.sort(key=lambda item: (item.normalized_path, item.qualified_name, item.start_line))
            local_code_symbols_written = _append_local_code_symbols(local_code_symbols_artifact, projection_records)
            projection_edges = extract_edges(projection_files, path)
            code_graph_artifact = write_code_graph_bundle(
                codebase_root=path,
                repo=path.resolve().name,
                branch=_current_branch(path),
                commit=_current_commit(path),
                scan_roots=code_symbol_scan_roots,
                files=projection_files,
                symbols=projection_records,
                edges=projection_edges,
                environment_manifest_digest=environment_manifest["environment_manifest_digest"],
            )
            if selected_projection_mode is ProjectionMode.EMIT:
                code_projection_request = _projection_request_for_artifact(
                    path=path,
                    scope=scope,
                    code_graph_artifact=code_graph_artifact,
                    environment_manifest=environment_manifest,
                )
                print(
                    "Code projection request: "
                    f"{code_projection_request['path']} (not applied)",
                    flush=True,
                )
            else:
                apply_result = _apply_code_projection_artifact(
                    path=path,
                    scope=scope,
                    code_graph_artifact=code_graph_artifact,
                    environment_manifest=environment_manifest,
                )
                if apply_result.errors:
                    for error in apply_result.errors[:5]:
                        print(f"  [ERROR] projection apply: {error}", file=sys.stderr, flush=True)
                    raise SystemExit(1)
                codebase_ts_symbols = apply_result.stored
                code_projection_receipt = apply_result.receipt
                for record in projection_records[:codebase_ts_symbols]:
                    verifiable_samples.append({
                        "name": record.symbol_name,
                        "problem": record.problem,
                    })
            if local_code_symbols_artifact.exists():
                local_code_symbols_written = sum(
                    1 for line in local_code_symbols_artifact.read_text().splitlines() if line.strip()
                )
            total_ts_symbols += codebase_ts_symbols

        marker_path = _write_ingest_marker(
            path,
            files_scanned=len(files),
            knowledge_stored=codebase_knowledge,
            cwe_stored=codebase_cwes,
            edges_stored=0,
            code_symbols_stored=codebase_ts_symbols,
            treesitter=bool(completed_code_symbol_scan_roots),
            scope=scope,
            started_at=started_at,
            scan_roots=code_symbol_scan_roots,
            completed_scan_roots=completed_code_symbol_scan_roots,
            local_code_symbols_artifact=local_code_symbols_artifact,
            local_code_symbols_written=local_code_symbols_written,
            environment_manifest=environment_manifest,
            code_graph_artifact=code_graph_artifact,
            code_projection_request=code_projection_request,
            code_projection_receipt=code_projection_receipt,
        )
        print(f"Marker written: {marker_path}", flush=True)
        pending_markers.append({"path": str(marker_path), "codebase": str(path)})

    verification_result = None
    if verify_embeddings:
        verification_result = verify_embedding_recall(verifiable_samples, sample_size=10)
        print(json.dumps({
            "embedding_verification": verification_result,
        }, indent=2))
        if verification_result["failed"] > 0:
            raise SystemExit(1)

    print(json.dumps({
        "codebases_scanned": len(codebases),
        "knowledge_stored": total_knowledge,
        "cwe_stored": total_cwes,
        "treesitter_symbols": total_ts_symbols,
        "since": since,
        "embedding_verification": verification_result,
        "markers": pending_markers,
    }, indent=2), flush=True)


if __name__ == "__main__":
    cli()
