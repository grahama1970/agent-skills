#!/usr/bin/env python3
"""
SAST (Static Application Security Testing) module.

Runs Semgrep and Bandit for Python code analysis.
"""
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def run_sast(path: Path, language: str = "python") -> list[dict[str, Any]]:
    """
    Run SAST scans using Semgrep and Bandit.

    Args:
        path: Directory to scan
        language: Primary language (currently only 'python' supported)

    Returns:
        List of findings with severity, rule_id, file, line, description
    """
    findings: list[dict[str, Any]] = []

    # Run Semgrep
    semgrep_findings = _run_semgrep(path, language)
    findings.extend(semgrep_findings)

    # Run Bandit (Python only)
    if language == "python":
        bandit_findings = _run_bandit(path)
        findings.extend(bandit_findings)

    return findings


def _run_semgrep(path: Path, language: str) -> list[dict[str, Any]]:
    """Run Semgrep scan and return normalized findings."""
    findings: list[dict[str, Any]] = []

    try:
        # Use auto config for language detection
        cmd = [
            "semgrep", "scan",
            "--config", "auto",
            "--json",
            "--quiet",
            str(path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.stdout:
            data = json.loads(result.stdout)
            for r in data.get("results", []):
                findings.append({
                    "tool": "semgrep",
                    "rule_id": r.get("check_id", "unknown"),
                    "severity": _normalize_severity(r.get("extra", {}).get("severity", "INFO")),
                    "file": r.get("path", ""),
                    "line": r.get("start", {}).get("line", 0),
                    "description": r.get("extra", {}).get("message", ""),
                    "category": r.get("extra", {}).get("metadata", {}).get("category", "security"),
                })

    except FileNotFoundError:
        print("  [WARN] semgrep not found, skipping")
    except subprocess.TimeoutExpired:
        print("  [WARN] semgrep timed out")
    except json.JSONDecodeError:
        print("  [WARN] semgrep output not valid JSON")
    except Exception as e:
        print(f"  [WARN] semgrep error: {e}")

    return findings


def _run_bandit(path: Path) -> list[dict[str, Any]]:
    """Run Bandit scan and return normalized findings."""
    findings: list[dict[str, Any]] = []

    try:
        cmd = [
            "bandit",
            "-r", str(path),
            "-f", "json",
            "--quiet"
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        # Bandit may return non-zero if it finds issues
        output = result.stdout or result.stderr
        if output:
            try:
                data = json.loads(output)
                for r in data.get("results", []):
                    findings.append({
                        "tool": "bandit",
                        "rule_id": r.get("test_id", "unknown"),
                        "severity": _normalize_severity(r.get("issue_severity", "LOW")),
                        "file": r.get("filename", ""),
                        "line": r.get("line_number", 0),
                        "description": r.get("issue_text", ""),
                        "confidence": r.get("issue_confidence", "MEDIUM"),
                        "category": "security",
                    })
            except json.JSONDecodeError:
                # Bandit sometimes outputs non-JSON warnings first
                pass

    except FileNotFoundError:
        print("  [WARN] bandit not found, skipping")
    except subprocess.TimeoutExpired:
        print("  [WARN] bandit timed out")
    except Exception as e:
        print(f"  [WARN] bandit error: {e}")

    return findings


def _normalize_severity(sev: str) -> str:
    """Normalize severity to standard levels."""
    sev = sev.upper()
    if sev in ("CRITICAL", "ERROR"):
        return "critical"
    elif sev in ("HIGH", "WARNING"):
        return "high"
    elif sev in ("MEDIUM",):
        return "medium"
    elif sev in ("LOW", "INFO"):
        return "low"
    else:
        return "info"


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    results = run_sast(target)
    print(json.dumps(results, indent=2))
