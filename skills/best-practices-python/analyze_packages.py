#!/usr/bin/env python3
"""Analyze pyproject.toml files across the workspace to find common Python packages.

Usage:
    uv run python analyze_packages.py                    # Table output
    uv run python analyze_packages.py --json             # JSON output
    uv run python analyze_packages.py --min-count 5      # Minimum project count
    uv run python analyze_packages.py --category ML/AI   # Filter by category
"""
from __future__ import annotations

import json
import os
import re
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

from collections import Counter, defaultdict
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Analyze Python package usage across all projects.")
console = Console()

SCAN_DIRS = [
    Path.home() / "workspace" / "experiments",
]

SKIP_DIRS = {
    ".venv", "node_modules", ".dbg", "archive", "repos",
    "_archive", ".cache", "site-packages", "__pycache__",
}

# Purpose annotations for known packages
ANNOTATIONS: dict[str, tuple[str, str]] = {
    # HTTP / Network
    "httpx": ("HTTP/Network", "Async/sync HTTP client. Project standard."),
    "requests": ("HTTP/Network", "DEPRECATED. Use httpx."),
    "aiohttp": ("HTTP/Network", "Async HTTP. Prefer httpx."),
    "fastapi": ("HTTP/Network", "REST API framework."),
    "uvicorn": ("HTTP/Network", "ASGI server for FastAPI."),
    # CLI
    "typer": ("CLI", "CLI framework. Project standard."),
    "rich": ("CLI", "Terminal formatting."),
    "textual": ("CLI", "TUI framework (built on Rich)."),
    "click": ("CLI", "DEPRECATED. Use typer."),
    # Logging
    "loguru": ("Logging", "Structured logging. Project standard."),
    # Config
    "python_dotenv": ("Config", ".env file loading."),
    "pyyaml": ("Config", "YAML parser."),
    "pydantic": ("Config", "Data validation + typed configs."),
    # Database
    "python_arango": ("Database", "ArangoDB driver."),
    "duckdb": ("Database", "In-process analytics DB."),
    "redis": ("Database", "Cache / message broker."),
    # PDF
    "pymupdf": ("PDF", "Fast PDF reader (fitz)."),
    "pymupdf4llm": ("PDF", "PDF-to-markdown."),
    "reportlab": ("PDF", "PDF generation."),
    "camelot_py": ("PDF", "PDF table extraction."),
    # ML/AI
    "scillm": ("ML/AI", "Internal LLM gateway."),
    "transformers": ("ML/AI", "HuggingFace models."),
    "torch": ("ML/AI", "PyTorch foundation."),
    "datasets": ("ML/AI", "HF dataset loading."),
    "scikit_learn": ("ML/AI", "Classical ML."),
    "sentence_transformers": ("ML/AI", "Embedding models."),
    "faiss_cpu": ("ML/AI", "Vector similarity search."),
    "openai": ("ML/AI", "OpenAI API client."),
    "litellm": ("ML/AI", "Universal LLM proxy."),
    # Audio
    "librosa": ("Audio", "Audio analysis."),
    "soundfile": ("Audio", "Audio I/O."),
    "faster_whisper": ("Audio", "Speech-to-text."),
    "yt_dlp": ("Audio", "Media downloader."),
    # Data
    "numpy": ("Data", "Numerical arrays."),
    "pandas": ("Data", "DataFrames."),
    "matplotlib": ("Viz", "Plotting."),
    # Testing
    "pytest": ("Testing", "Test framework."),
    "pytest_asyncio": ("Testing", "Async test support."),
    # Utility
    "tenacity": ("Utility", "Retry with backoff."),
    "json_repair": ("Utility", "Fix malformed LLM JSON."),
    "rapidfuzz": ("NLP", "Fuzzy string matching."),
    "beautifulsoup4": ("Scraping", "HTML parser."),
    "tree_sitter": ("Code", "Incremental code parser."),
}


def normalize_dep(dep: str) -> str:
    dep = re.split(r"\[", dep)[0]
    dep = re.split(r"[><=!~;@]", dep)[0].strip()
    return dep.lower().replace("-", "_")


def scan_pyproject_files() -> list[Path]:
    files = []
    for scan_dir in SCAN_DIRS:
        for root, dirs, filenames in os.walk(scan_dir):
            path = Path(root)
            if set(path.parts) & SKIP_DIRS:
                dirs.clear()
                continue
            if "pyproject.toml" in filenames:
                files.append(path / "pyproject.toml")
    return files


def analyze(min_count: int = 3) -> list[dict]:
    files = scan_pyproject_files()
    logger.info("Scanning {} pyproject.toml files", len(files))

    pkg_count: Counter[str] = Counter()
    pkg_skills: Counter[str] = Counter()
    pkg_projects: Counter[str] = Counter()

    for f in files:
        try:
            with open(f, "rb") as fh:
                data = tomllib.load(fh)
        except Exception:
            continue

        is_skill = ".pi" in f.parts and "skills" in f.parts
        deps = list(data.get("project", {}).get("dependencies", []))
        for group in data.get("project", {}).get("optional-dependencies", {}).values():
            deps.extend(group)

        seen: set[str] = set()
        for dep in deps:
            if isinstance(dep, str):
                pkg = normalize_dep(dep)
                if pkg and pkg not in seen:
                    seen.add(pkg)
                    pkg_count[pkg] += 1
                    if is_skill:
                        pkg_skills[pkg] += 1
                    else:
                        pkg_projects[pkg] += 1

    results = []
    for pkg, count in pkg_count.most_common():
        if count < min_count:
            break
        cat, purpose = ANNOTATIONS.get(pkg, ("", ""))
        results.append({
            "package": pkg,
            "count": count,
            "skills": pkg_skills.get(pkg, 0),
            "projects": pkg_projects.get(pkg, 0),
            "category": cat,
            "purpose": purpose,
        })
    return results


@app.command()
def main(
    min_count: int = typer.Option(3, help="Minimum number of projects using a package"),
    category: str = typer.Option("", help="Filter by category"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    results = analyze(min_count=min_count)

    if category:
        results = [r for r in results if r["category"].lower() == category.lower()]

    if as_json:
        print(json.dumps(results, indent=2))
        return

    table = Table(title=f"Python Package Usage ({len(results)} packages, min {min_count} projects)")
    table.add_column("Package", style="cyan")
    table.add_column("Total", justify="right", style="bold")
    table.add_column("Skills", justify="right")
    table.add_column("Projects", justify="right")
    table.add_column("Category", style="green")
    table.add_column("Purpose")

    for r in results:
        style = "red" if "DEPRECATED" in r["purpose"] else None
        table.add_row(
            r["package"],
            str(r["count"]),
            str(r["skills"]),
            str(r["projects"]),
            r["category"],
            r["purpose"],
            style=style,
        )

    console.print(table)


if __name__ == "__main__":
    app()
