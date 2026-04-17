"""Treesitter-based symbol extraction for ingest-code rescan.

Invokes the treesitter skill (run.sh scan) on directories and stores
extracted symbols (functions, classes, methods) to memory via Unix socket.
"""

import json
import subprocess
import sys
from pathlib import Path


def _learn_symbol(problem: str, solution: str, scope: str, tags: list[str]) -> bool:
    """Store a symbol in /memory via Unix socket httpx."""
    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
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

    stored = 0
    for file_entry in scan_results:
        file_path = file_entry.get("path", "")
        symbols = file_entry.get("symbols", [])
        if not symbols:
            continue

        file_stem = Path(file_path).stem
        for sym in symbols:
            kind = sym.get("kind", "unknown")
            name = sym.get("name", "")
            signature = sym.get("signature", "")
            docstring = sym.get("docstring", "")
            start_line = sym.get("start_line", 0)

            if not name:
                continue

            problem = f"What is {name} in {Path(file_path).name}?"
            solution_parts = [f"File: {file_path}:{start_line}"]
            if signature:
                solution_parts.append(signature)
            if docstring:
                solution_parts.append(docstring[:800])
            solution = "\n".join(solution_parts)

            tags = ["codebase", "symbol", kind, name, file_stem]

            if _learn_symbol(problem, solution, scope, tags):
                stored += 1

    return stored
