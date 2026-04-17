#!/usr/bin/env python3
"""Detect duplicated Python function bodies across a project."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import sys

from loguru import logger

_SKIP_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", ".cache", "site-packages", ".uv", "archive-v0", "dist", "build"}
_SKIP_NAMES = {"self", "cls", "True", "False", "None"}


class _IdentifierNormalizer(ast.NodeTransformer):
    """Replace identifiers with a stable placeholder before hashing."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id in _SKIP_NAMES:
            return node
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.arg:
        if node.arg in _SKIP_NAMES:
            return node
        return ast.copy_location(ast.arg(arg="_", annotation=None, type_comment=None), node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        clone = self.generic_visit(node)
        clone.attr = "_"
        return clone

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._normalize_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._normalize_function(node)

    def _normalize_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST:
        clone = self.generic_visit(node)
        clone.name = "_"
        clone.decorator_list = []
        clone.returns = None
        clone.type_comment = None
        return clone


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
            if _should_skip(path):
                continue
            if path not in seen:
                seen.add(path)
                files.append(path)
    return sorted(files)


def _line_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    end_lineno = getattr(node, "end_lineno", node.lineno)
    return max(0, end_lineno - node.lineno + 1)


def _function_nodes(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _normalized_dump(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    normalized = _IdentifierNormalizer().visit(ast.fix_missing_locations(copy.deepcopy(node)))
    return ast.dump(normalized, annotate_fields=False, include_attributes=False)


def _hash_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return hashlib.sha256(_normalized_dump(node).encode("utf-8")).hexdigest()


def detect_duplicates(scan_dirs: list[str], min_lines: int = 10) -> dict:
    """Return duplicate clusters for Python functions in the given directories."""
    clusters: dict[str, list[dict[str, str | int]]] = {}
    scanned_files = 0

    for py_file in _iter_py_files(scan_dirs):
        scanned_files += 1
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            logger.warning("Skipping {}: {}", py_file, exc)
            continue

        for node in _function_nodes(tree):
            if _line_count(node) < min_lines:
                continue
            cluster = clusters.setdefault(_hash_function(node), [])
            cluster.append({
                "file": str(py_file),
                "line": node.lineno,
                "name": node.name,
            })

    duplicate_clusters = [
        {
            "hash": digest,
            "count": len(locations),
            "locations": sorted(locations, key=lambda item: (str(item["file"]), int(item["line"]))),
        }
        for digest, locations in clusters.items()
        if len(locations) > 1
    ]
    duplicate_clusters.sort(key=lambda item: (-int(item["count"]), item["hash"]))

    total_duplicates = sum(cluster["count"] for cluster in duplicate_clusters)
    logger.info(
        "Duplicate scan complete: {} files, {} duplicate clusters, {} duplicated functions",
        scanned_files,
        len(duplicate_clusters),
        total_duplicates,
    )
    return {
        "clusters": duplicate_clusters,
        "scanned_files": scanned_files,
        "total_duplicates": total_duplicates,
    }


def main(argv: list[str]) -> int:
    """Run duplication detection for the provided scan directories."""
    if not argv:
        print("Usage: duplication_detector.py <scan_dir> [<scan_dir> ...]", file=sys.stderr)
        return 1

    result = detect_duplicates(argv)
    json.dump(result, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
