#!/usr/bin/env python3
"""
Compliance-Ops: Check codebases against compliance frameworks.

Supports:
- SOC2 Type II
- GDPR
- HIPAA (coming soon)
- PCI-DSS (coming soon)
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Version
__version__ = "0.1.0"

# Available frameworks
FRAMEWORKS = {
    "soc2": "SOC2 Type II - Service Organization Control",
    "gdpr": "GDPR - General Data Protection Regulation",
    "hipaa": "HIPAA - Health Insurance Portability (coming soon)",
    "pci-dss": "PCI-DSS - Payment Card Industry (coming soon)",
}


def cmd_version(args: argparse.Namespace) -> int:
    """Print version."""
    print(f"ops-compliance {__version__}")
    return 0


def cmd_frameworks(args: argparse.Namespace) -> int:
    """List available frameworks."""
    print("Available compliance frameworks:\n")
    for key, desc in FRAMEWORKS.items():
        status = "[READY]" if key in ("soc2", "gdpr") else "[PLANNED]"
        print(f"  {status} {key}: {desc}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Run compliance check."""
    framework = args.framework.lower()

    if framework not in FRAMEWORKS:
        print(f"Unknown framework: {framework}", file=sys.stderr)
        print(f"Available: {', '.join(FRAMEWORKS.keys())}", file=sys.stderr)
        return 1

    print(f"Running {framework.upper()} compliance check on: {args.path}")

    results: dict[str, Any] = {
        "framework": framework,
        "path": str(args.path),
        "checks": [],
        "summary": {"passed": 0, "failed": 0, "warnings": 0},
    }

    try:
        if framework == "soc2":
            from frameworks.soc2 import run_soc2_checks
            results["checks"] = run_soc2_checks(args.path)
        elif framework == "gdpr":
            from frameworks.gdpr import run_gdpr_checks
            results["checks"] = run_gdpr_checks(args.path)
        else:
            print(f"Framework {framework} not yet implemented", file=sys.stderr)
            return 1

        # Calculate summary
        for check in results["checks"]:
            status = check.get("status", "unknown")
            if status == "pass":
                results["summary"]["passed"] += 1
            elif status == "fail":
                results["summary"]["failed"] += 1
            elif status == "warning":
                results["summary"]["warnings"] += 1

    except ImportError as e:
        print(f"Framework module not available: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Compliance check failed: {e}", file=sys.stderr)
        return 1

    # Output results
    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        _print_summary(results)

    # Store results if requested
    if getattr(args, "store_results", False):
        try:
            from memory_integration import store_compliance_results
            store_compliance_results(results)
            print("\n[INFO] Results stored in memory")
        except ImportError:
            print("\n[WARN] Memory integration not available", file=sys.stderr)

    return 0 if results["summary"]["failed"] == 0 else 1


def cmd_report(args: argparse.Namespace) -> int:
    """Generate compliance report."""
    print(f"Generating {args.format} report...")
    try:
        from report import generate_report
        output = generate_report(args.path, args.format, args.framework)

        if args.output:
            Path(args.output).write_text(output)
            print(f"Report written to: {args.output}")
        else:
            print(output)

        return 0
    except ImportError as e:
        print(f"Report module not available: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Report generation failed: {e}", file=sys.stderr)
        return 1


def _print_summary(results: dict[str, Any]) -> None:
    """Print human-readable summary."""
    print(f"\n=== {results['framework'].upper()} Compliance Summary ===")
    print(f"Path: {results.get('path', 'unknown')}")
    print(f"Passed: {results['summary']['passed']}")
    print(f"Failed: {results['summary']['failed']}")
    print(f"Warnings: {results['summary']['warnings']}")

    if results["summary"]["failed"] == 0:
        print("\n[OK] All compliance checks passed!")
    else:
        print(f"\n[FAIL] {results['summary']['failed']} checks failed")
        print("\nFailed checks:")
        for check in results["checks"]:
            if check.get("status") == "fail":
                print(f"  - [{check.get('control_id', 'N/A')}] {check.get('description', 'Unknown')}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="ops-compliance",
        description="Compliance framework checker",
    )
    parser.add_argument("--version", action="store_true", help="Print version")
    parser.add_argument("--format", choices=["json", "text", "markdown", "html"], default="text", help="Output format")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # check command
    check_parser = subparsers.add_parser("check", help="Run compliance check")
    check_parser.add_argument("--framework", required=True, help="Framework to check (soc2, gdpr, etc.)")
    check_parser.add_argument("--path", type=Path, default=".", help="Path to check")
    check_parser.add_argument("--store-results", action="store_true", help="Store results in memory")
    check_parser.set_defaults(func=cmd_check)

    # report command
    report_parser = subparsers.add_parser("report", help="Generate compliance report")
    report_parser.add_argument("--framework", default="all", help="Framework for report")
    report_parser.add_argument("--path", type=Path, default=".", help="Path to scan")
    report_parser.add_argument("--output", "-o", help="Output file path")
    report_parser.set_defaults(func=cmd_report)

    # frameworks command
    frameworks_parser = subparsers.add_parser("frameworks", help="List available frameworks")
    frameworks_parser.set_defaults(func=cmd_frameworks)

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
