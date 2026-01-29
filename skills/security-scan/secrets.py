#!/usr/bin/env python3
"""
Secrets detection module.

Runs gitleaks for finding hardcoded credentials, API keys, and tokens.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Add ~/.local/bin to PATH for gitleaks
os.environ["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{os.environ.get('PATH', '')}"


def run_secrets_scan(path: Path) -> list[dict[str, Any]]:
    """
    Run secrets detection using gitleaks.

    Args:
        path: Directory to scan

    Returns:
        List of potential secrets with file, line, rule, description
    """
    findings: list[dict[str, Any]] = []
    path = Path(path)

    # Run gitleaks
    gitleaks_findings = _run_gitleaks(path)
    findings.extend(gitleaks_findings)

    return findings


def _run_gitleaks(path: Path) -> list[dict[str, Any]]:
    """Run gitleaks and return normalized findings."""
    findings: list[dict[str, Any]] = []

    try:
        # Create temp file for report
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            report_path = f.name

        cmd = [
            "gitleaks", "detect",
            "--source", str(path),
            "--report-format", "json",
            "--report-path", report_path,
            "--no-git",  # Scan files, not git history
        ]

        # Check for .gitleaksignore or .secretsignore
        ignore_file = path / ".gitleaksignore"
        if not ignore_file.exists():
            ignore_file = path / ".secretsignore"
        if ignore_file.exists():
            cmd.extend(["--config", str(ignore_file)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        # Read report file (gitleaks writes to file, not stdout)
        try:
            with open(report_path) as f:
                data = json.load(f)

            for finding in data if isinstance(data, list) else []:
                findings.append({
                    "tool": "gitleaks",
                    "rule": finding.get("RuleID", "unknown"),
                    "file": finding.get("File", ""),
                    "line": finding.get("StartLine", 0),
                    "description": finding.get("Description", ""),
                    "secret": _redact_secret(finding.get("Secret", "")),
                    "commit": finding.get("Commit", ""),
                    "author": finding.get("Author", ""),
                    "entropy": finding.get("Entropy", 0),
                    "match": finding.get("Match", "")[:50] + "..." if len(finding.get("Match", "")) > 50 else finding.get("Match", ""),
                })
        except (json.JSONDecodeError, FileNotFoundError):
            pass
        finally:
            # Clean up temp file
            try:
                os.unlink(report_path)
            except OSError:
                pass

    except FileNotFoundError:
        print("  [WARN] gitleaks not found, skipping")
    except subprocess.TimeoutExpired:
        print("  [WARN] gitleaks timed out")
    except Exception as e:
        print(f"  [WARN] gitleaks error: {e}")

    return findings


def _redact_secret(secret: str) -> str:
    """Redact secret value for safe display."""
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    # Show first 2 and last 2 characters
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    results = run_secrets_scan(target)
    print(json.dumps(results, indent=2))
