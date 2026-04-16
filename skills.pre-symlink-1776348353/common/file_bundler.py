"""Shared file bundler for LLM prompts.

Reads files, extracts interface maps (AST signatures + types + line numbers),
and formats them for injection into LLM prompts. Used by any skill that sends
file content to an LLM: /code-runner, /code-review-runner, /review-code, etc.

Three modes per file:
  - FULL: complete file content (for files the LLM will edit)
  - INTERFACE_MAP: AST-extracted signatures only (for read-only context)
  - HEAD_TAIL: first 80 + last 40 lines + symbols (for oversized files)
"""
from __future__ import annotations

import ast as _ast
from pathlib import Path

from loguru import logger

MAX_FILE_CONTENT_CHARS = 50_000  # ~12K tokens


# ── Interface map extraction (AST-based) ────────────────────────────


def extract_interface_map(content: str, rel_path: str) -> str:
    """Extract structured interface map from Python source.

    Returns: module docstring + class/function signatures with line numbers
    and docstrings. The LLM gets the contract (what to call, what it returns,
    where to find it) — not the implementation.

    For non-Python files, returns first 30 lines with line numbers.
    """
    if not rel_path.endswith(".py"):
        return _head_with_line_numbers(content, 30)

    try:
        tree = _ast.parse(content)
    except SyntaxError:
        return _head_with_line_numbers(content, 30)

    parts: list[str] = []

    module_doc = _ast.get_docstring(tree)
    if module_doc:
        parts.append(f'"""{module_doc}"""')

    for node in _ast.iter_child_nodes(tree):
        if isinstance(node, _ast.ClassDef):
            bases = ", ".join(_ast.unparse(b) for b in node.bases) if node.bases else ""
            class_line = f"L{node.lineno}: class {node.name}({bases}):" if bases else f"L{node.lineno}: class {node.name}:"
            parts.append(class_line)
            class_doc = _ast.get_docstring(node)
            if class_doc:
                parts.append(f'    """{class_doc}"""')
            for item in node.body:
                if isinstance(item, _ast.FunctionDef):
                    parts.append(_format_func_sig(item, indent=4))

        elif isinstance(node, _ast.FunctionDef):
            parts.append(_format_func_sig(node, indent=0))

        elif isinstance(node, (_ast.Import, _ast.ImportFrom)):
            parts.append(f"L{node.lineno}: {_ast.unparse(node)}")

    if parts:
        return f"Interface map for {rel_path}:\n```python\n" + "\n".join(parts) + "\n```"
    return _head_with_line_numbers(content, 30)


def _format_func_sig(node: "_ast.FunctionDef", indent: int = 0) -> str:
    """Format a function signature with line number, return annotation, and docstring."""
    pad = " " * indent
    args = _ast.unparse(node.args) if node.args.args else ""
    ret = f" -> {_ast.unparse(node.returns)}" if node.returns else ""
    sig = f"{pad}L{node.lineno}: def {node.name}({args}){ret}: ..."
    doc = _ast.get_docstring(node)
    if doc:
        first_line = doc.split("\n")[0].strip()
        sig += f"  # {first_line}"
    return sig


def _head_with_line_numbers(content: str, n: int) -> str:
    """Return first n lines with line numbers."""
    lines = content.splitlines()[:n]
    return "```\n" + "\n".join(f"L{i+1}: {l}" for i, l in enumerate(lines)) + "\n```"


# ── File bundler ────────────────────────────────────────────────────


def bundle_files(
    files: list[str],
    cwd: str,
    *,
    read_only: set[str] | None = None,
    escalated: set[str] | None = None,
    max_chars: int = MAX_FILE_CONTENT_CHARS,
    label_prefix: str = "",
) -> str:
    """Bundle files into a prompt-ready string.

    Args:
        files: List of relative file paths to include.
        cwd: Working directory (files resolved relative to this).
        read_only: Files to show as interface maps (not full content).
        escalated: Read-only files promoted to full content (error referenced them).
        max_chars: Max chars per file before switching to head+tail mode.
        label_prefix: Optional prefix for section headers.

    Returns:
        Formatted string with all file contents, ready for LLM prompt injection.
    """
    read_only_set = read_only or set()
    escalated_set = escalated or set()
    sections: list[str] = []

    for rel_path in files:
        fpath = Path(cwd) / rel_path
        if not fpath.exists() or fpath.is_dir():
            continue

        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Could not read {}: {}", rel_path, exc)
            continue

        lines = content.splitlines()
        line_count = len(lines)
        is_ro = rel_path in read_only_set

        if is_ro and rel_path not in escalated_set:
            # Interface map only (round 1 for read-only context)
            imap = extract_interface_map(content, rel_path)
            sections.append(
                f"\n\n--- {label_prefix}READ-ONLY REFERENCE: {rel_path} ({line_count} lines) ---\n"
                f"{imap}"
            )
        elif is_ro and rel_path in escalated_set:
            # Escalated: full content (round 2+ after error referenced this file)
            sections.append(
                f"\n\n--- {label_prefix}READ-ONLY REFERENCE (ESCALATED): {rel_path} ({line_count} lines) ---\n"
                f"```\n{content}\n```"
            )
        elif len(content) <= max_chars:
            # Full content (editable file, fits in context)
            sections.append(
                f"\n\n--- {label_prefix}CURRENT FILE: {rel_path} ({line_count} lines) ---\n"
                f"```\n{content}\n```"
            )
        else:
            # Oversized: head + tail + interface map
            head = "\n".join(lines[:80])
            tail = "\n".join(lines[-40:])
            imap = extract_interface_map(content, rel_path) if rel_path.endswith(".py") else ""
            sections.append(
                f"\n\n--- {label_prefix}CURRENT FILE: {rel_path} ({line_count} lines, showing head+tail) ---\n"
                f"Lines 1-80:\n```\n{head}\n```\n"
                f"...\n"
                f"Lines {line_count - 40}-{line_count}:\n```\n{tail}\n```\n"
                + (f"\nSymbols:\n{imap}" if imap else "")
                + f"\nNOTE: This file is {line_count} lines. Use unified diff format to edit it."
            )

    if not sections:
        return ""
    return "\n\nHere are the current file contents for reference:" + "".join(sections)


def bundle_for_review(
    files: list[str],
    cwd: str,
    *,
    max_chars: int = MAX_FILE_CONTENT_CHARS,
) -> dict[str, str]:
    """Bundle files as a dict (path → content) for review skills.

    Simpler than bundle_files() — no labels, no interface maps.
    Returns raw content for each file, truncated if oversized.
    Used by /code-review-runner and /review-code.
    """
    result: dict[str, str] = {}
    for rel_path in files:
        fpath = Path(cwd) / rel_path
        if not fpath.exists() or fpath.is_dir():
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            if len(content) > max_chars:
                lines = content.splitlines()
                content = "\n".join(lines[:500]) + f"\n\n... ({len(lines) - 500} more lines truncated)"
            result[rel_path] = content
        except OSError as exc:
            logger.warning("Could not read {}: {}", rel_path, exc)
    return result
