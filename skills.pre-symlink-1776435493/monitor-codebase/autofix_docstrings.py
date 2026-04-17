#!/usr/bin/env python3
"""Auto-fix missing docstrings using /treesitter + /scillm.

Composes two existing skills:
  /treesitter scan --content --json → finds undocumented symbols
  /scillm quick_completion()        → generates concise one-liner docstrings

The goal: make every .py file scannable. A human or agent should be able to
scroll through and read docstrings to quickly understand the flow without
reading implementation code.

Usage:
    # Dry-run: show what would be fixed
    python autofix_docstrings.py /path/to/project --dry-run

    # Fix missing docstrings in-place
    python autofix_docstrings.py /path/to/project

    # Fix a single file
    python autofix_docstrings.py /path/to/file.py

    # Respect .monitor-codebase.json scoping
    python autofix_docstrings.py /path/to/project --scoped
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Optional

SKILL_DIR = Path(__file__).resolve().parent
PI_MONO = SKILL_DIR.parents[2]
SKILLS_DIR = PI_MONO / ".pi" / "skills"
TREESITTER_RUN = SKILLS_DIR / "treesitter" / "run.sh"

# Skills directory for /scillm, /treesitter composition
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))


def _run_treesitter(target: Path) -> list[dict]:
    """Call /treesitter scan to get symbols with content as JSON."""
    import tempfile

    cmd = [str(TREESITTER_RUN)]
    if target.is_dir():
        # scan command writes JSON to --output file (no stdout JSON flag)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        cmd += ["scan", str(target), "--include", "**/*.py",
                "--exclude", "**/.venv/**", "--exclude", "**/venv/**",
                "--exclude", "**/node_modules/**", "--exclude", "**/site-packages/**",
                "--content", "--output", tmp_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            print(f"  treesitter error (rc={result.returncode}): {result.stderr[:200]}", file=sys.stderr)
            os.unlink(tmp_path) if os.path.exists(tmp_path) else None
            return []
        try:
            data = json.loads(Path(tmp_path).read_text())
            return data
        except (json.JSONDecodeError, FileNotFoundError):
            return []
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    else:
        # symbols command outputs JSON to stdout
        cmd += ["symbols", str(target), "--content"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode != 0:
            print(f"  treesitter error (rc={result.returncode}): {result.stderr[:200]}", file=sys.stderr,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return []
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return []


def _find_undocumented(scan_results: list[dict]) -> list[dict]:
    """Filter treesitter output to symbols missing docstrings."""
    undocumented = []

    if not scan_results:
        return undocumented

    # scan returns list of {path, language, symbols} for directories
    # symbols returns list of symbols for single files
    items = scan_results
    if items and "path" in items[0]:
        # Directory scan format
        for file_entry in items:
            fpath = file_entry.get("path", "")
            if not fpath.endswith(".py"):
                continue
            for sym in file_entry.get("symbols", []):
                if not sym.get("docstring") and sym.get("kind") in ("function", "class"):
                    sym["_file_path"] = fpath
                    undocumented.append(sym)
    else:
        # Single file format
        for sym in items:
            if not sym.get("docstring") and sym.get("kind") in ("function", "class"):
                undocumented.append(sym)

    return undocumented


def _call_scillm(prompt: str) -> str:
    """Call scillm HTTP proxy for LLM completion."""
    import httpx

    payload = {
        "model": "deepseek-ai/DeepSeek-V3",
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(
        "http://localhost:4001/v1/chat/completions",
        json=payload,
        timeout=120.0,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if not content:
        raise RuntimeError("Empty /scillm output")
    return content


def _generate_one_docstring(args_tuple: tuple) -> tuple[int, str]:
    """Generate one docstring for a single symbol."""
    i, sym, total = args_tuple
    name = sym.get("name", "unknown")
    kind = sym.get("kind", "function")
    content = sym.get("content", "")
    if len(content) > 400:
        content = content[:400] + "\n    # ... (truncated)"

    prompt = (
        f"Write ONE concise docstring for this Python {kind}.\n\n"
        "RULES:\n"
        '- Format: "Verb object [qualifier]." — one sentence, period at end\n'
        "- Start with a verb: Return, Extract, Parse, Build, Check, Load, Validate, etc.\n"
        "- WHAT it does, not HOW. Max 72 chars. No filler words.\n\n"
        "EXAMPLES:\n"
        '- "Validate and clamp an integer within min/max bounds."\n'
        '- "Load JSON from path, returning empty dict on failure."\n'
        '- "Extract table cells from a PDF page region."\n\n'
        f"```python\n{content}\n```\n\n"
        'Return ONLY the docstring text, no quotes, no JSON, just the sentence.'
    )

    try:
        response = _call_scillm(prompt)
        doc = response.strip().strip('"').strip("'").strip("`").strip()
        if doc.startswith("{") or doc.startswith("["):
            try:
                parsed = json.loads(doc)
                if isinstance(parsed, dict):
                    doc = parsed.get("docstring", doc)
                elif isinstance(parsed, list) and parsed:
                    doc = parsed[0].get("docstring", doc)
            except json.JSONDecodeError:
                pass
        if doc and len(doc) < 120:
            if not doc.endswith("."):
                doc += "."
            print(f"    [{i+1}/{total}] {name}: {doc}", flush=True)
            return (i, doc)
        else:
            fallback = _heuristic_docstring(sym)
            print(f"    [{i+1}/{total}] {name}: (heuristic) {fallback}", flush=True)
            return (i, fallback)
    except Exception as e:
        fallback = _heuristic_docstring(sym)
        print(f"    [{i+1}/{total}] {name}: (fallback: {e})", flush=True)
        return (i, fallback)


def _generate_docstrings(symbols: list[dict], workers: int = 4) -> dict[int, str]:
    """Generate docstrings concurrently via /scillm with ThreadPoolExecutor."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    tasks = [(i, sym, len(symbols)) for i, sym in enumerate(symbols)]
    results = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_generate_one_docstring, t): t[0] for t in tasks}
        for future in as_completed(futures):
            idx, doc = future.result()
            results[idx] = doc

    return results


def _heuristic_docstring(sym: dict) -> str:
    """Generate a basic docstring from symbol name when scillm is unavailable."""
    name = sym.get("name", "unknown")
    kind = sym.get("kind", "function")

    # Convert snake_case to words
    words = name.replace("_", " ").strip()

    if kind == "class":
        return f"{name.replace('_', ' ').title()} handler."
    if name.startswith("test_"):
        return f"Test {words[5:]}."
    if name.startswith("_"):
        words = words.lstrip()
    if name.startswith("get_") or name.startswith("fetch_"):
        return f"Return {words[4:]}."
    if name.startswith("set_"):
        return f"Set {words[4:]}."
    if name.startswith("is_") or name.startswith("has_"):
        return f"Check if {words[3:]}."
    if name.startswith("create_") or name.startswith("build_"):
        return f"Create {words[7:]}."
    if name.startswith("parse_"):
        return f"Parse {words[6:]}."
    if name.startswith("run_"):
        return f"Run {words[4:]}."
    if name.startswith("handle_"):
        return f"Handle {words[7:]}."

    return f"Perform {words} operation."


def _patch_file(filepath: Path, insertions: list[dict]) -> int:
    """Insert docstrings into a Python file at correct positions.

    Each insertion has: start_line, indent_level, docstring text.
    Returns count of docstrings added.
    """
    lines = filepath.read_text().splitlines(keepends=True)
    # Sort insertions in reverse line order so earlier inserts don't shift later ones
    insertions.sort(key=lambda x: x["line"], reverse=True)

    count = 0
    for ins in insertions:
        line_idx = ins["line"]  # 0-based index of the def/class line
        docstring = ins["docstring"]

        # Find the end of the def/class signature.
        # For multi-line signatures we must track parenthesis depth to find
        # the closing ')' before the final ':', otherwise we'd match ':'
        # inside type annotations (e.g. "stage: str,").
        insert_after = line_idx
        paren_depth = 0
        found_signature_end = False
        for k in range(line_idx, min(line_idx + 30, len(lines))):
            line_text = lines[k]
            for ch in line_text:
                if ch == '(':
                    paren_depth += 1
                elif ch == ')':
                    paren_depth -= 1
            # Signature ends when parens are balanced and we see ':'
            # For simple 'def foo():' or 'class Foo:', paren_depth will be 0
            if paren_depth <= 0 and ':' in line_text:
                # Make sure the ':' comes after any closing paren
                colon_pos = line_text.rfind(':')
                # Accept this line as the end of the signature
                insert_after = k
                found_signature_end = True
                break

        if not found_signature_end:
            continue

        # Compute indent from the actual def/class line in the file,
        # not from the treesitter signature (which may lack context for nested fns)
        def_line = lines[line_idx]
        raw_indent = def_line[: len(def_line) - len(def_line.lstrip())]
        body_indent = raw_indent + "    "
        doc_line = f'{body_indent}"""{docstring}"""\n'

        # Check if next line already has a docstring (safety check)
        next_idx = insert_after + 1
        if next_idx < len(lines):
            stripped = lines[next_idx].strip()
            if stripped.startswith('"""') or stripped.startswith("'''") or stripped.startswith('#'):
                continue  # Already documented or has comment

        # Insert
        lines.insert(next_idx, doc_line)
        count += 1

    if count > 0:
        filepath.write_text("".join(lines))

    return count


def _load_monitor_config(project_path: Path) -> Optional[dict]:
    """Load .monitor-codebase.json for directory scoping."""
    config_file = project_path / ".monitor-codebase.json"
    if config_file.exists():
        try:
            return json.loads(config_file.read_text())
        except Exception:
            pass
    return None


def _get_scan_targets(project_path: Path, scoped: bool) -> list[Path]:
    """Return list of directories to scan, respecting .monitor-codebase.json."""
    if not scoped or not project_path.is_dir():
        return [project_path]

    config = _load_monitor_config(project_path)
    if not config or not config.get("include_dirs"):
        return [project_path]

    targets = []
    for d in config["include_dirs"]:
        full = project_path / d
        if full.is_dir():
            targets.append(full)
    return targets or [project_path]


def main():
    """Entry point: scan for undocumented symbols and auto-fix with docstrings."""
    import typer

    _app = typer.Typer(add_completion=False)

    @_app.command()
    def _run(
        target: str = typer.Argument(help="Project directory or single .py file"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be fixed"),
        scoped: bool = typer.Option(False, "--scoped", help="Respect .monitor-codebase.json"),
        heuristic_only: bool = typer.Option(False, "--heuristic-only", help="Skip scillm, use name-based heuristics only"),
        batch_size: int = typer.Option(20, "--batch-size", help="Symbols per scillm batch"),
    ) -> None:
        _main_inner(target, dry_run, scoped, heuristic_only, batch_size)

    _app()
    return 0


def _main_inner(target_str: str, dry_run: bool, scoped: bool, heuristic_only: bool, batch_size: int) -> int:
    """Core logic, extracted for typer dispatch."""
    class _Args:
        pass
    args = _Args()
    args.dry_run = dry_run
    args.scoped = scoped
    args.heuristic_only = heuristic_only
    args.batch_size = batch_size

    target = Path(target_str).resolve()
    if not target.exists():
        print(f"ERROR: {target} does not exist", file=sys.stderr)
        sys.exit(1)

    scan_targets = _get_scan_targets(target, args.scoped)
    total_fixed = 0
    total_found = 0

    for scan_target in scan_targets:
        print(f"\nScanning: {scan_target}", flush=True)
        scan_results = _run_treesitter(scan_target)

        if not scan_results:
            print("  No symbols found (treesitter returned empty)")
            continue

        undocumented = _find_undocumented(scan_results)
        total_found += len(undocumented)

        if not undocumented:
            print("  All symbols have docstrings")
            continue

        print(f"  Found {len(undocumented)} undocumented symbols", flush=True)

        if args.dry_run:
            for sym in undocumented:
                fpath = sym.get("_file_path", "?")
                print(f"    [{sym['kind']}] {sym['name']} ({fpath}:{sym.get('start_line', '?')})")
            continue

        # Generate docstrings
        if args.heuristic_only:
            docstrings = {i: _heuristic_docstring(sym) for i, sym in enumerate(undocumented)}
        else:
            print(f"  Generating docstrings via /scillm (batch_size={args.batch_size})...", flush=True)
            docstrings = _generate_docstrings(undocumented)

        # Group insertions by file
        by_file: dict[str, list[dict]] = {}
        for i, sym in enumerate(undocumented):
            if i not in docstrings:
                continue
            fpath = sym.get("_file_path", "")
            if not fpath:
                # Single file mode
                fpath = str(scan_target)
            if fpath not in by_file:
                by_file[fpath] = []

            # Calculate indent from start_line
            start_line = sym.get("start_line", 1)
            sig = sym.get("signature", "")
            indent = " " * (len(sig) - len(sig.lstrip())) if sig else ""

            by_file[fpath].append({
                "line": start_line - 1,  # Convert to 0-based
                "indent": indent,
                "docstring": docstrings[i],
            })

        # Apply patches
        for fpath, insertions in by_file.items():
            p = Path(fpath)
            if not p.exists():
                # Try relative to scan target
                p = scan_target / fpath
            if not p.exists():
                continue

            count = _patch_file(p, insertions)
            if count > 0:
                print(f"  Patched {count} docstrings in {p.name}", flush=True)
                total_fixed += count

    print(f"\nDone: {total_fixed} docstrings added ({total_found} undocumented found)", flush=True)
    return total_fixed


if __name__ == "__main__":
    main()
