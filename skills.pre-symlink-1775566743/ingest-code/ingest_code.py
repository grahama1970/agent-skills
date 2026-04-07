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


def load_taxonomy_module():
    """Load the taxonomy module for bridge tag + CWE extraction."""
    taxonomy_paths = [
        Path(__file__).parent.parent / "taxonomy" / "taxonomy.py",
        Path.home() / ".pi" / "skills" / "taxonomy" / "taxonomy.py",
        Path.home() / ".agents" / "skills" / "taxonomy" / "taxonomy.py",
    ]
    for tp in taxonomy_paths:
        if tp.exists():
            import importlib.util
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
        import httpx
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET_PATH)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=15.0) as client:
            resp = client.post("/learn", json={
                "problem": problem,
                "solution": solution,
                "scope": scope,
                "tags": tags,
                "code_symbol": True,
            })
            return resp.status_code == 200
    except Exception:
        return False


def _learn(memory_script: Path, problem: str, solution: str, scope: str, tags: list[str]) -> bool:
    """Store a lesson in /memory via Unix socket httpx."""
    return _learn_http(problem, solution, scope, tags)


def _recall_http(query: str, k: int = 1) -> dict[str, Any]:
    """Query /memory recall over the Unix socket."""
    import httpx

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


def _extract_configured_scan_roots(codebase_path: Path) -> list[Path]:
    """Resolve scan roots from .monitor-codebase.json include_dirs."""
    config = _load_monitor_config(codebase_path)
    if config and config.get("include_dirs"):
        roots: list[Path] = []
        for include_dir in config["include_dirs"]:
            full = codebase_path / include_dir
            if full.is_dir():
                roots.append(full)
        if roots:
            return roots
    return [codebase_path]


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


def _store_treesitter_symbols_for_directory(
    directory: Path,
    scope: str,
    verification_samples: Optional[list[dict[str, str]]] = None,
) -> int:
    """Scan one configured directory with the treesitter skill and store symbols."""
    treesitter_script = find_treesitter_skill()
    if not treesitter_script:
        print(f"Treesitter skill not found for {directory}", file=sys.stderr, flush=True)
        return 0

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
        return 0

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            print(f"Treesitter scan failed for {directory}: {stderr}", file=sys.stderr, flush=True)
        return 0

    scan_results = _parse_treesitter_scan_output(result.stdout)
    if not scan_results:
        return 0

    stored = 0
    for file_entry in scan_results:
        file_path_raw = file_entry.get("path")
        if not file_path_raw:
            continue

        filepath = Path(file_path_raw)
        symbol_context = _extract_symbol_context(filepath)
        import_summary = symbol_context["import_summary"]
        class_hierarchies = symbol_context["class_hierarchies"]

        for symbol in file_entry.get("symbols", []):
            raw_kind = symbol.get("kind", "")
            kind = _normalize_symbol_kind(raw_kind)
            name = symbol.get("name", "")
            if not kind or not name:
                continue

            start_line = symbol.get("start_line", 0)
            signature = symbol.get("signature", "")
            docstring = symbol.get("docstring", "")

            solution_parts = [f"File: {filepath}:{start_line}"]
            if signature:
                solution_parts.append(f"Signature: {signature}")
            if kind == "class":
                bases = class_hierarchies.get(name, [])
                hierarchy = ", ".join(bases) if bases else "None"
                solution_parts.append(f"Class hierarchy: {hierarchy}")
            if import_summary:
                solution_parts.append(f"Imports: {import_summary}")
            if docstring:
                solution_parts.append(docstring[:800])

            problem = f"What is {name} in {filepath.name}?"
            tags = _build_symbol_tags(kind, name, filepath.stem)
            if _learn_http(problem, "\n".join(solution_parts), scope, tags):
                stored += 1
                if verification_samples is not None:
                    verification_samples.append({
                        "name": name,
                        "problem": problem,
                    })

    return stored


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


def store_edges(edges: list[dict], scope: str = "code", dry_run: bool = False) -> int:
    """Store dependency edges in /memory via batch HTTP endpoint."""
    if dry_run:
        stored = 0
        for edge in edges:
            from_name = Path(edge["from_file"]).name
            to_name = Path(edge["to_file"]).name
            names = ", ".join(edge.get("names", [])[:3])
            print(f"  [EDGE] {from_name} → {to_name} (imports {names})")
            stored += 1
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

    # Send in chunks of 100
    import httpx
    stored = 0
    CHUNK = 100
    for i in range(0, len(batch), CHUNK):
        chunk = batch[i : i + CHUNK]
        try:
            resp = httpx.post(
                f"{MEMORY_SERVICE_URL}/add-edges",
                json={"edges": chunk},
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                stored += data.get("stored", 0)
                print(f"  Progress: {min(i + CHUNK, len(batch))}/{len(batch)} edges sent, {stored} stored", flush=True)
            else:
                print(f"  [WARN] Batch {i//CHUNK}: HTTP {resp.status_code}", flush=True)
        except Exception as exc:
            print(f"  [WARN] Batch {i//CHUNK}: {exc}", flush=True)
    return stored


# ---------------------------------------------------------------------------
# CWE scanning (original functionality)
# ---------------------------------------------------------------------------

from ingest_code_cwe import scan_file_cwe  # noqa: E402


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


def collect_files(codebase_path: Path, patterns: list[str], mtime_after: Optional[datetime] = None) -> list[Path]:
    """Collect files matching patterns, scoped by .monitor-codebase.json if present."""
    config = _load_monitor_config(codebase_path)
    exclude_dirs = SKIP_DIRS.copy()
    if config:
        exclude_dirs.update(config.get("exclude_dirs", []))

    files: list[Path] = []

    # Determine scan roots — either scoped dirs or full codebase
    scan_roots = _extract_configured_scan_roots(codebase_path)

    for root in scan_roots:
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


@cli.command()
def scan(
    path: Path = typer.Argument(help="Codebase path to scan"),
    glob: list[str] = typer.Option([], "-g", "--glob", help="File patterns to scan"),
    cwe_only: bool = typer.Option(False, "--cwe-only", help="Only scan for CWEs (legacy mode)"),
    validate: bool = typer.Option(False, "--validate/--no-validate", help="Run LLM validation on CWEs"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be stored without writing"),
    scope: str = typer.Option("code", help="Memory scope for storage"),
    batch_size: int = typer.Option(50, help="Files per batch"),
):
    """Scan a codebase for functional knowledge and CWE mappings, store in /memory."""
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
        for filepath in files:
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
                    if done_count % 100 == 0:
                        print(f"  Progress: {knowledge_stored} stored, {failed} blocked, {done_count}/{knowledge_total} done", flush=True)

        print(f"Knowledge: {knowledge_stored} stored of {knowledge_total} extracted ({failed} blocked)", flush=True)

    # --- Phase 2: CWE scanning ---
    total_cwes = 0
    cwe_stored = 0
    files_with_cwes = 0
    cwe_summary: dict[str, int] = {}

    if taxonomy:
        print("\n--- Phase 2: CWE scanning ---", flush=True)
        monitor = TaskClient("ingest-code", total=len(files)) if TaskClient else None
        scanned = 0

        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            for filepath in batch:
                if filepath.suffix in (".md", ".mdx"):
                    continue  # Skip docs for CWE scanning
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
                if monitor:
                    monitor.update(item=str(filepath))
                if scanned % 100 == 0:
                    print(f"  Progress: {scanned} scanned, {total_cwes} CWEs in {files_with_cwes} files", flush=True)

        if monitor:
            monitor.finish()
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
            edges_stored = store_edges(edges, scope=scope, dry_run=dry_run)
            print(f"Edges: {edges_stored} stored of {edges_total} found", flush=True)

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
        "dry_run": dry_run,
    }
    print(f"\n{json.dumps(result, indent=2)}")


@cli.command()
def rescan(
    since: Optional[str] = typer.Option(None, help="Only files modified since (ISO date or '1d', '7d', etc.)"),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Run LLM validation"),
    treesitter: bool = typer.Option(False, "--treesitter", help="Run treesitter scan for symbol extraction"),
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

    print(f"Rescanning {len(codebases)} codebase(s)")
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

    for codebase_path in codebases:
        path = Path(codebase_path)
        files = collect_files(path, DEFAULT_GLOB_PATTERNS, mtime_after=mtime_threshold)
        print(f"Found {len(files)} files in {codebase_path}")

        for filepath in files:
            # Knowledge extraction
            for item in extract_knowledge(filepath):
                if _learn(memory_script, item["problem"], item["solution"], scope, item["tags"]):
                    total_knowledge += 1
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

        # Treesitter symbol extraction (per codebase, not per file)
        if treesitter:
            scan_roots = _extract_configured_scan_roots(path)
            ts_stored = 0
            for scan_root in scan_roots:
                root_stored = _store_treesitter_symbols_for_directory(
                    scan_root,
                    scope,
                    verification_samples=verifiable_samples,
                )
                ts_stored += root_stored
                print(f"Treesitter: {root_stored} symbols stored from {scan_root}", flush=True)
            total_ts_symbols += ts_stored

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
    }, indent=2))


if __name__ == "__main__":
    cli()
