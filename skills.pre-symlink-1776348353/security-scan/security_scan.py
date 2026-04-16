#!/usr/bin/env python3
"""
Security-Scan: Self-hosted security scanning orchestrator.

Integrates:
- Semgrep + Bandit for SAST
- pip-audit + Trivy for dependency scanning
- gitleaks for secrets detection
"""
import json
import os
import sys
from pathlib import Path
from typing import Any

import typer

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

# Version
__version__ = "0.1.0"

# Add ~/.local/bin to PATH for gitleaks/trivy
os.environ["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{os.environ.get('PATH', '')}"


# Global format state for subcommands
_output_format: str = "text"


def _print_summary(results: dict[str, Any]) -> None:
    """Print human-readable summary."""
    print("\n=== Security Scan Summary ===")
    print(f"Path: {results.get('path', 'unknown')}")
    print(f"SAST findings: {len(results.get('sast', []))}")
    print(f"Dependency vulnerabilities: {len(results.get('deps', []))}")
    print(f"Potential secrets: {len(results.get('secrets', []))}")

    total = len(results.get("sast", [])) + len(results.get("deps", [])) + len(results.get("secrets", []))
    if total == 0:
        print("\n[OK] No security issues found!")
    else:
        print(f"\n[WARN] Found {total} total security issues")


app = typer.Typer(help="Self-hosted security scanning orchestrator")


def _format_callback(value: str) -> str:
    global _output_format
    _output_format = value
    return value


@app.callback()
def callback(
    version: bool = typer.Option(False, "--version", help="Print version"),
    format: str = typer.Option("text", "--format", help="Output format (json or text)"),
) -> None:
    """Self-hosted security scanning orchestrator."""
    global _output_format
    _output_format = format
    if version:
        print(f"security-scan {__version__}")
        raise typer.Exit(0)


@app.command("scan")
def cmd_scan(
    path: Path = typer.Option(".", "--path", help="Path to scan"),
    language: str = typer.Option("python", "--language", help="Primary language"),
    store_results: bool = typer.Option(False, "--store-results", help="Store results in memory"),
) -> None:
    """Run all security scans."""
    print(f"Running full security scan on: {path}")
    results: dict[str, Any] = {
        "path": str(path),
        "sast": [],
        "deps": [],
        "secrets": [],
    }

    scan_steps = ["sast", "deps", "secrets"]
    monitor = TaskClient("security-scan", total=len(scan_steps)) if TaskClient else None

    # Import modules (lazy to avoid import errors if not all installed)
    try:
        from sast import run_sast
        results["sast"] = run_sast(path, language)
    except ImportError:
        print("  [WARN] SAST module not available", file=sys.stderr)
    except Exception as e:
        print(f"  [ERROR] SAST failed: {e}", file=sys.stderr)
    if monitor:
        monitor.update(item="sast")

    try:
        from deps import run_deps_audit
        results["deps"] = run_deps_audit(path)
    except ImportError:
        print("  [WARN] Deps module not available", file=sys.stderr)
    except Exception as e:
        print(f"  [ERROR] Deps audit failed: {e}", file=sys.stderr)
    if monitor:
        monitor.update(item="deps")

    try:
        from secrets import run_secrets_scan
        results["secrets"] = run_secrets_scan(path)
    except ImportError:
        print("  [WARN] Secrets module not available", file=sys.stderr)
    except Exception as e:
        print(f"  [ERROR] Secrets scan failed: {e}", file=sys.stderr)
    if monitor:
        monitor.update(item="secrets")
        monitor.finish()

    # Output results
    if _output_format == "json":
        print(json.dumps(results, indent=2))
    else:
        _print_summary(results)

    # Store results if requested
    if store_results:
        try:
            from memory_integration import store_scan_results
            store_scan_results(results)
            print("\n[INFO] Results stored in memory")
        except ImportError:
            print("\n[WARN] Memory integration not available", file=sys.stderr)


@app.command("sast")
def cmd_sast(
    path: Path = typer.Option(".", "--path", help="Path to scan"),
    language: str = typer.Option("python", "--language", help="Language to scan"),
) -> None:
    """Run SAST scan only."""
    print(f"Running SAST scan on: {path}")
    try:
        from sast import run_sast
        results = run_sast(path, language)
        if _output_format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} SAST findings")
            for r in results[:10]:
                print(f"  [{r.get('severity', 'UNKNOWN')}] {r.get('rule_id', 'unknown')}: {r.get('file', '')}:{r.get('line', '')}")
    except Exception as e:
        print(f"SAST scan failed: {e}", file=sys.stderr)
        raise typer.Exit(1)


@app.command("deps")
def cmd_deps(
    path: Path = typer.Option(".", "--path", help="Path to scan"),
) -> None:
    """Run dependency audit only."""
    print(f"Running dependency audit on: {path}")
    try:
        from deps import run_deps_audit
        results = run_deps_audit(path)
        if _output_format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} vulnerable dependencies")
            for r in results[:10]:
                print(f"  [{r.get('severity', 'UNKNOWN')}] {r.get('package', 'unknown')}: {r.get('cve', '')}")
    except Exception as e:
        print(f"Dependency audit failed: {e}", file=sys.stderr)
        raise typer.Exit(1)


@app.command("secrets")
def cmd_secrets(
    path: Path = typer.Option(".", "--path", help="Path to scan"),
) -> None:
    """Run secrets detection only."""
    print(f"Running secrets detection on: {path}")
    try:
        from secrets import run_secrets_scan
        results = run_secrets_scan(path)
        if _output_format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} potential secrets")
            for r in results[:10]:
                print(f"  [{r.get('rule', 'unknown')}] {r.get('file', '')}:{r.get('line', '')}")
    except Exception as e:
        print(f"Secrets detection failed: {e}", file=sys.stderr)
        raise typer.Exit(1)


@app.command("version")
def cmd_version() -> None:
    """Print version."""
    print(f"security-scan {__version__}")


if __name__ == "__main__":
    app()
