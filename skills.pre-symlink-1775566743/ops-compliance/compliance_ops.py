#!/usr/bin/env python3
"""
Compliance-Ops: Check codebases against compliance frameworks.

Supports:
- SOC2 Type II
- GDPR
- HIPAA (not yet implemented)
- PCI-DSS (not yet implemented)
"""
import typer
import json
import sys
from pathlib import Path
from typing import Any, Optional

# Version
__version__ = "0.1.0"

# Available frameworks
FRAMEWORKS = {
    "soc2": "SOC2 Type II - Service Organization Control",
    "gdpr": "GDPR - General Data Protection Regulation",
    "hipaa": "HIPAA - Health Insurance Portability (not yet implemented)",
    "pci-dss": "PCI-DSS - Payment Card Industry (not yet implemented)",
}

app = typer.Typer(help="Compliance framework checker")

# Global state for --format flag
_output_format = "text"


@app.callback()
def main_callback(
    fmt: str = typer.Option("text", "--format", help="Output format (json, text, markdown, html)"),
):
    global _output_format
    _output_format = fmt


@app.command()
def version():
    """Print version."""
    print(f"ops-compliance {__version__}")


@app.command()
def frameworks():
    """List available frameworks."""
    print("Available compliance frameworks:\n")
    for key, desc in FRAMEWORKS.items():
        status = "[READY]" if key in ("soc2", "gdpr") else "[PLANNED]"
        print(f"  {status} {key}: {desc}")


@app.command()
def check(
    framework: str = typer.Option(..., help="Framework to check (soc2, gdpr, etc.)"),
    path: Path = typer.Option(".", help="Path to check"),
    store_results: bool = typer.Option(False, "--store-results", help="Store results in memory"),
):
    """Run compliance check."""
    fw = framework.lower()

    if fw not in FRAMEWORKS:
        print(f"Unknown framework: {fw}", file=sys.stderr)
        print(f"Available: {', '.join(FRAMEWORKS.keys())}", file=sys.stderr)
        raise typer.Exit(code=1)

    print(f"Running {fw.upper()} compliance check on: {path}")

    results: dict[str, Any] = {
        "framework": fw,
        "path": str(path),
        "checks": [],
        "summary": {"passed": 0, "failed": 0, "warnings": 0},
    }

    try:
        if fw == "soc2":
            from frameworks.soc2 import run_soc2_checks
            results["checks"] = run_soc2_checks(path)
        elif fw == "gdpr":
            from frameworks.gdpr import run_gdpr_checks
            results["checks"] = run_gdpr_checks(path)
        else:
            raise NotImplementedError(f"Compliance framework '{fw}' not yet implemented")

        # Calculate summary
        for chk in results["checks"]:
            status = chk.get("status", "unknown")
            if status == "pass":
                results["summary"]["passed"] += 1
            elif status == "fail":
                results["summary"]["failed"] += 1
            elif status == "warning":
                results["summary"]["warnings"] += 1

    except ImportError as e:
        print(f"Framework module not available: {e}", file=sys.stderr)
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        print(f"Compliance check failed: {e}", file=sys.stderr)
        raise typer.Exit(code=1)

    # Output results
    if _output_format == "json":
        print(json.dumps(results, indent=2))
    else:
        _print_summary(results)

    # Store results if requested
    if store_results:
        try:
            from memory_integration import store_compliance_results
            store_compliance_results(results)
            print("\n[INFO] Results stored in memory")
        except ImportError:
            print("\n[WARN] Memory integration not available", file=sys.stderr)

    if results["summary"]["failed"] > 0:
        raise typer.Exit(code=1)


@app.command()
def report(
    framework: str = typer.Option("all", help="Framework for report"),
    path: Path = typer.Option(".", help="Path to scan"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output file path"),
):
    """Generate compliance report."""
    print(f"Generating {_output_format} report...")
    try:
        from report import generate_report
        report_output = generate_report(path, _output_format, framework)

        if output:
            Path(output).write_text(report_output)
            print(f"Report written to: {output}")
        else:
            print(report_output)

    except ImportError as e:
        print(f"Report module not available: {e}", file=sys.stderr)
        raise typer.Exit(code=1)
    except Exception as e:
        print(f"Report generation failed: {e}", file=sys.stderr)
        raise typer.Exit(code=1)


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


if __name__ == "__main__":
    app()
