#!/usr/bin/env python3
"""
Security-Scan: Self-hosted security scanning orchestrator.

Integrates:
- Semgrep + Bandit for SAST
- pip-audit + Trivy for dependency scanning
- gitleaks for secrets detection
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Version
__version__ = "0.1.0"

# Add ~/.local/bin to PATH for gitleaks/trivy
os.environ["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{os.environ.get('PATH', '')}"


def cmd_version(args: argparse.Namespace) -> int:
    """Print version."""
    print(f"security-scan {__version__}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    """Run all security scans."""
    print(f"Running full security scan on: {args.path}")
    results: dict[str, Any] = {
        "path": str(args.path),
        "sast": [],
        "deps": [],
        "secrets": [],
    }

    # Import modules (lazy to avoid import errors if not all installed)
    try:
        from sast import run_sast
        results["sast"] = run_sast(args.path, args.language if hasattr(args, "language") else "python")
    except ImportError:
        print("  [WARN] SAST module not available", file=sys.stderr)
    except Exception as e:
        print(f"  [ERROR] SAST failed: {e}", file=sys.stderr)

    try:
        from deps import run_deps_audit
        results["deps"] = run_deps_audit(args.path)
    except ImportError:
        print("  [WARN] Deps module not available", file=sys.stderr)
    except Exception as e:
        print(f"  [ERROR] Deps audit failed: {e}", file=sys.stderr)

    try:
        from secrets import run_secrets_scan
        results["secrets"] = run_secrets_scan(args.path)
    except ImportError:
        print("  [WARN] Secrets module not available", file=sys.stderr)
    except Exception as e:
        print(f"  [ERROR] Secrets scan failed: {e}", file=sys.stderr)

    # Output results
    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        _print_summary(results)

    # Store results if requested
    if getattr(args, "store_results", False):
        try:
            from memory_integration import store_scan_results
            store_scan_results(results)
            print("\n[INFO] Results stored in memory")
        except ImportError:
            print("\n[WARN] Memory integration not available", file=sys.stderr)

    return 0


def cmd_sast(args: argparse.Namespace) -> int:
    """Run SAST scan only."""
    print(f"Running SAST scan on: {args.path}")
    try:
        from sast import run_sast
        results = run_sast(args.path, args.language)
        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} SAST findings")
            for r in results[:10]:
                print(f"  [{r.get('severity', 'UNKNOWN')}] {r.get('rule_id', 'unknown')}: {r.get('file', '')}:{r.get('line', '')}")
        return 0
    except Exception as e:
        print(f"SAST scan failed: {e}", file=sys.stderr)
        return 1


def cmd_deps(args: argparse.Namespace) -> int:
    """Run dependency audit only."""
    print(f"Running dependency audit on: {args.path}")
    try:
        from deps import run_deps_audit
        results = run_deps_audit(args.path)
        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} vulnerable dependencies")
            for r in results[:10]:
                print(f"  [{r.get('severity', 'UNKNOWN')}] {r.get('package', 'unknown')}: {r.get('cve', '')}")
        return 0
    except Exception as e:
        print(f"Dependency audit failed: {e}", file=sys.stderr)
        return 1


def cmd_secrets(args: argparse.Namespace) -> int:
    """Run secrets detection only."""
    print(f"Running secrets detection on: {args.path}")
    try:
        from secrets import run_secrets_scan
        results = run_secrets_scan(args.path)
        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"Found {len(results)} potential secrets")
            for r in results[:10]:
                print(f"  [{r.get('rule', 'unknown')}] {r.get('file', '')}:{r.get('line', '')}")
        return 0
    except Exception as e:
        print(f"Secrets detection failed: {e}", file=sys.stderr)
        return 1


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


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="security-scan",
        description="Self-hosted security scanning orchestrator",
    )
    parser.add_argument("--version", action="store_true", help="Print version")
    parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Run all security scans")
    scan_parser.add_argument("--path", type=Path, default=".", help="Path to scan")
    scan_parser.add_argument("--language", default="python", help="Primary language")
    scan_parser.add_argument("--store-results", action="store_true", help="Store results in memory")
    scan_parser.set_defaults(func=cmd_scan)

    # sast command
    sast_parser = subparsers.add_parser("sast", help="Run SAST scan")
    sast_parser.add_argument("--path", type=Path, default=".", help="Path to scan")
    sast_parser.add_argument("--language", default="python", help="Language to scan")
    sast_parser.set_defaults(func=cmd_sast)

    # deps command
    deps_parser = subparsers.add_parser("deps", help="Run dependency audit")
    deps_parser.add_argument("--path", type=Path, default=".", help="Path to scan")
    deps_parser.set_defaults(func=cmd_deps)

    # secrets command
    secrets_parser = subparsers.add_parser("secrets", help="Run secrets detection")
    secrets_parser.add_argument("--path", type=Path, default=".", help="Path to scan")
    secrets_parser.set_defaults(func=cmd_secrets)

    # version command
    version_parser = subparsers.add_parser("version", help="Print version")
    version_parser.set_defaults(func=cmd_version)

    args = parser.parse_args()

    if args.version:
        return cmd_version(args)

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
