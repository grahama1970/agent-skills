"""Treesitter-based symbol extraction for ingest-code rescan.

Invokes the treesitter skill (run.sh scan) on directories and stores
extracted symbols (functions, classes, methods) to memory via Unix socket.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from code_memory_client import CodeMemoryClient
from code_symbol_record import CodeSymbolRecord


def _git_value(cwd: Path, args: list[str], default: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return default


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


def _language_for_path(filepath: Path) -> str:
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
    }.get(filepath.suffix, filepath.suffix.lstrip(".") or "unknown")


def _record_from_symbol(sym: dict, file_path: Path, root: Path, scope: str) -> CodeSymbolRecord | None:
    kind = sym.get("kind", "unknown")
    name = sym.get("name", "")
    if kind not in {"function", "class", "method"} or not name:
        return None

    start_line = int(sym.get("start_line") or 0)
    end_line = int(sym.get("end_line") or start_line)
    code = _source_slice(file_path, start_line, end_line)
    try:
        rel_path = file_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel_path = file_path.as_posix()

    repo = root.resolve().name
    branch = _git_value(root, ["rev-parse", "--abbrev-ref", "HEAD"], "unknown")
    commit = _git_value(root, ["rev-parse", "HEAD"], "unknown")
    tags = ["codebase", "symbol", kind, name, file_path.stem, "code_symbol"]

    return CodeSymbolRecord(
        scope=scope,
        repo=repo,
        root=str(root.resolve()),
        branch=branch,
        commit=commit,
        path=rel_path,
        language=_language_for_path(file_path),
        symbol_kind=kind,
        symbol_name=name,
        qualified_name=name,
        start_line=start_line,
        end_line=end_line,
        signature=sym.get("signature", "") or "",
        docstring=sym.get("docstring", "") or "",
        code=code,
        content_hash=hashlib.sha256((code or name).encode("utf-8")).hexdigest(),
        tags=tags,
    )


def treesitter_scan_dir(directory: str, scope: str) -> int:
    """Run treesitter scan on a directory and store symbols to memory.

    Invokes .pi/skills/treesitter/run.sh scan <directory>, parses JSON output,
    and stores each symbol (function, class, method) via memory daemon Unix socket.

    Returns count of symbols stored.
    """
    treesitter_script = Path.home() / ".pi" / "skills" / "treesitter" / "run.sh"
    if not treesitter_script.exists():
        print(f"  treesitter skill not found at {treesitter_script}", file=sys.stderr)
        return 0

    try:
        result = subprocess.run(
            [str(treesitter_script), "scan", directory],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        print(f"  treesitter scan timed out for {directory}", file=sys.stderr)
        return 0

    stdout = result.stdout.strip()
    if not stdout:
        return 0

    # Find the JSON array start (skip the "Scanned N files..." summary line)
    json_start = stdout.find("[")
    if json_start < 0:
        return 0

    try:
        scan_results = json.loads(stdout[json_start:])
    except json.JSONDecodeError:
        print(f"  treesitter returned invalid JSON for {directory}", file=sys.stderr)
        return 0

    records: list[CodeSymbolRecord] = []
    root = Path(directory)
    for file_entry in scan_results:
        file_path = file_entry.get("path", "")
        symbols = file_entry.get("symbols", [])
        if not symbols:
            continue

        path_obj = Path(file_path)
        for sym in symbols:
            record = _record_from_symbol(sym, path_obj, root, scope)
            if record:
                records.append(record)

    return CodeMemoryClient().upsert_code_symbols(records).stored
