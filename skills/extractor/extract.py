#!/usr/bin/env python3
"""Delegate one-file extraction to the canonical Extractor CLI.

Inputs are a local file path plus a small stable option set. Output is the
canonical Extractor stdout payload. Failures are reported with the wrapped
process return code and stderr/stdout passthrough.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer


def _candidate_roots(script_dir: Path) -> list[Path]:
    return [
        Path(os.environ["EXTRACTOR_ROOT"]).expanduser()
        if os.environ.get("EXTRACTOR_ROOT")
        else Path(),
        script_dir.parent.parent,
        script_dir.parent.parent.parent.parent / "extractor",
        Path.home() / "workspace" / "experiments" / "extractor",
    ]


def find_extractor_root(script_dir: Path) -> Path:
    """Find the Extractor project root without relying on its .venv."""

    for candidate in _candidate_roots(script_dir):
        if not str(candidate):
            continue
        root = candidate.resolve()
        if (root / "pyproject.toml").is_file() and (root / "src" / "extractor").is_dir():
            return root
    raise typer.BadParameter(
        "Extractor project not found. Set EXTRACTOR_ROOT to the checkout containing "
        "pyproject.toml and src/extractor."
    )


def _run_passthrough(command: list[str], *, cwd: Path) -> int:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    process = subprocess.run(command, cwd=str(cwd), env=env, check=False)
    return process.returncode


def _extract(
    input_file: Path,
    *,
    out: Path | None,
    offline: bool,
    output_format: str,
) -> None:
    script_dir = Path(__file__).resolve().parent
    extractor_root = find_extractor_root(script_dir)

    command = [
        "uv",
        "run",
        "--project",
        str(extractor_root),
        "extractor",
        "extract",
        str(input_file),
    ]
    if out is not None:
        command.extend(["--out", str(out)])
    if offline:
        command.append("--offline")
    command.extend(["--format", output_format])

    raise typer.Exit(code=_run_passthrough(command, cwd=extractor_root))


def main(
    input_file: Annotated[
        Path,
        typer.Argument(help="Local file to extract."),
    ],
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Output directory for extraction artifacts."),
    ] = None,
    offline: Annotated[
        bool,
        typer.Option("--offline", help="Disable network/model enrichment."),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Presentation format: json or markdown.",
            case_sensitive=False,
        ),
    ] = "json",
    json_alias: Annotated[
        bool,
        typer.Option("--json", help="Compatibility alias for --format json."),
    ] = False,
    markdown_alias: Annotated[
        bool,
        typer.Option("--markdown", help="Compatibility alias for --format markdown."),
    ] = False,
) -> None:
    """Extract a single file through Extractor."""

    if json_alias and markdown_alias:
        raise typer.BadParameter("Use only one of --json or --markdown.")
    if markdown_alias:
        output_format = "markdown"
    elif json_alias:
        output_format = "json"
    output_format = output_format.lower()
    if output_format not in {"json", "markdown"}:
        raise typer.BadParameter("--format must be json or markdown.")

    _extract(input_file, out=out, offline=offline, output_format=output_format)


def _doctor() -> int:
    script_dir = Path(__file__).resolve().parent
    extractor_root = find_extractor_root(script_dir)
    command = ["uv", "run", "--project", str(extractor_root), "extractor", "version"]
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    result = subprocess.run(
        command,
        cwd=str(extractor_root),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        typer.echo(result.stdout.rstrip())
    if result.stderr:
        typer.echo(result.stderr.rstrip(), err=True)
    return result.returncode


def doctor() -> None:
    """Check that the canonical Extractor command is available."""

    raise typer.Exit(code=_doctor())


def _debug_routing(
    input_file: Path | None,
) -> int:
    script_dir = Path(__file__).resolve().parent
    extractor_root = find_extractor_root(script_dir)
    if input_file is not None:
        typer.echo(f"input={input_file}", err=True)
    command = [
        "uv",
        "run",
        "--project",
        str(extractor_root),
        "extractor",
        "extract",
        "--help",
    ]
    return _run_passthrough(command, cwd=extractor_root)


def debug_routing(
    input_file: Annotated[
        Path | None,
        typer.Argument(help="Optional local file path to echo for debugging."),
    ] = None,
) -> None:
    """Print canonical Extractor routing surface for maintainers."""

    raise typer.Exit(code=_debug_routing(input_file))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("--help")
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        raise SystemExit(_doctor())
    elif len(sys.argv) > 1 and sys.argv[1] == "debug-routing":
        raise SystemExit(_debug_routing(Path(sys.argv[2]) if len(sys.argv) > 2 else None))
    else:
        typer.run(main)
