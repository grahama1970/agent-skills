#!/usr/bin/env python3
"""Build a local Python import graph and detect circular dependencies."""
from __future__ import annotations

import ast
from pathlib import Path

from loguru import logger

_SKIP_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", ".cache", "site-packages", ".uv", "archive-v0", "dist", "build"}


def _should_skip(path: Path) -> bool:
    return any(part in _SKIP_DIRS or part.startswith(".venv") for part in path.parts)


def _iter_py_files(scan_dirs: list[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for scan_dir in scan_dirs:
        root = Path(scan_dir).resolve()
        if not root.exists():
            logger.warning("Scan directory does not exist: {}", root)
            continue
        for path in root.rglob("*.py"):
            if _should_skip(path) or path in seen:
                continue
            seen.add(path)
            files.append(path)
    return sorted(files)


def _module_name(path: Path, roots: list[Path]) -> str:
    for root in roots:
        try:
            relative = path.relative_to(root)
            parts = list(relative.with_suffix("").parts)
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            return ".".join(parts) if parts else path.parent.name
        except ValueError:
            continue
    return path.stem


def _alias_map(files: list[Path], roots: list[Path]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for path in files:
        module = _module_name(path, roots)
        parts = module.split(".")
        aliases[module] = module
        aliases[path.stem] = module
        for index in range(len(parts)):
            aliases[".".join(parts[index:])] = module
    return aliases


def _resolve_imports(node: ast.AST, current: str) -> set[str]:
    names: set[str] = set()
    current_parts = current.split(".")
    package_parts = current_parts[:-1]

    if isinstance(node, ast.Import):
        for alias in node.names:
            names.add(alias.name)
        return names

    if not isinstance(node, ast.ImportFrom):
        return names

    base_parts = package_parts.copy()
    if node.level:
        if node.level - 1 > len(base_parts):
            base_parts = []
        else:
            base_parts = base_parts[: len(base_parts) - (node.level - 1)]
    if node.module:
        base = ".".join([*base_parts, node.module]) if base_parts else node.module
        names.add(base)
    for alias in node.names:
        if alias.name == "*":
            continue
        if node.module:
            names.add(f"{base}.{alias.name}")
        else:
            names.add(".".join([*base_parts, alias.name]) if base_parts else alias.name)
    return {name for name in names if name}


def _local_target(name: str, aliases: dict[str, str]) -> str | None:
    parts = name.split(".")
    for index in range(len(parts), 0, -1):
        candidate = ".".join(parts[:index])
        if candidate in aliases:
            return aliases[candidate]
    return None


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    on_stack: dict[str, int] = {}
    cycles: set[tuple[str, ...]] = set()

    def record(cycle: list[str]) -> None:
        core = cycle[:-1]
        rotations = [tuple(core[index:] + core[:index]) for index in range(len(core))]
        canonical = min(rotations)
        cycles.add(canonical + (canonical[0],))

    def visit(node: str) -> None:
        state[node] = 1
        on_stack[node] = len(stack)
        stack.append(node)
        for neighbor in sorted(graph.get(node, ())):
            if state.get(neighbor) == 0:
                visit(neighbor)
            elif state.get(neighbor) == 1:
                start = on_stack[neighbor]
                record(stack[start:] + [neighbor])
        stack.pop()
        on_stack.pop(node, None)
        state[node] = 2

    for node in sorted(graph):
        if state.get(node, 0) == 0:
            visit(node)

    return [list(cycle) for cycle in sorted(cycles)]


def _max_depth(graph: dict[str, set[str]]) -> int:
    memo: dict[str, int] = {}

    def depth(node: str, path: set[str]) -> int:
        if node in memo:
            return memo[node]
        if node in path:
            return 0
        next_path = set(path)
        next_path.add(node)
        child_depth = max((depth(child, next_path) for child in graph.get(node, ())), default=0)
        memo[node] = child_depth + 1
        return memo[node]

    return max((depth(node, set()) for node in graph), default=0)


def analyze_dependencies(scan_dirs: list[str]) -> dict:
    """Analyze local Python imports and report cycles and graph depth."""
    roots = [Path(scan_dir).resolve() for scan_dir in scan_dirs]
    files = _iter_py_files(scan_dirs)
    aliases = _alias_map(files, roots)
    graph: dict[str, set[str]] = {_module_name(path, roots): set() for path in files}
    inbound = {module: 0 for module in graph}

    for path in files:
        module = _module_name(path, roots)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            logger.warning("Skipping {}: {}", path, exc)
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for name in _resolve_imports(node, module):
                target = _local_target(name, aliases)
                if target is None or target == module or target in graph[module]:
                    continue
                graph[module].add(target)
                inbound[target] += 1

    cycles = _find_cycles(graph)
    circular_deps = [
        {
            "cycle": cycle,
            "severity": "high" if len(cycle) <= 4 else "medium",
        }
        for cycle in cycles
    ]
    most_depended = [
        {"module": module, "dependents": count}
        for module, count in sorted(inbound.items(), key=lambda item: (-item[1], item[0]))
        if count > 0
    ][:5]

    edges = sum(len(targets) for targets in graph.values())
    logger.info(
        "Dependency scan complete: {} modules, {} edges, {} cycles, max depth {}",
        len(graph),
        edges,
        len(circular_deps),
        _max_depth(graph),
    )
    return {
        "modules": len(graph),
        "edges": edges,
        "circular_deps": circular_deps,
        "max_depth": _max_depth(graph),
        "most_depended": most_depended,
    }