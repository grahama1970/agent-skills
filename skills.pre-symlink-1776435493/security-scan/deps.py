#!/usr/bin/env python3
"""
Dependency audit module.

Runs pip-audit and Trivy for vulnerability scanning.
"""
import json
import os
import subprocess
from pathlib import Path
from typing import Any

# Add ~/.local/bin to PATH for trivy
os.environ["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{os.environ.get('PATH', '')}"


def run_deps_audit(path: Path) -> list[dict[str, Any]]:
    """
    Run dependency vulnerability scans.

    Auto-detects package managers and runs appropriate tools:
    - Python (requirements.txt, pyproject.toml): pip-audit
    - Node.js (package.json): npm audit
    - General/containers: Trivy filesystem scan

    Args:
        path: Directory to scan

    Returns:
        List of vulnerabilities with package, version, cve, severity
    """
    findings: list[dict[str, Any]] = []
    path = Path(path)

    # Detect and run Python audit
    if _has_python_deps(path):
        pip_findings = _run_pip_audit(path)
        findings.extend(pip_findings)

    # Detect and run Node.js audit
    if (path / "package.json").exists():
        npm_findings = _run_npm_audit(path)
        findings.extend(npm_findings)

    # Always run Trivy for comprehensive scan
    trivy_findings = _run_trivy(path)
    findings.extend(trivy_findings)

    # Deduplicate by CVE
    seen_cves: set[str] = set()
    unique_findings: list[dict[str, Any]] = []
    for f in findings:
        cve = f.get("cve", "")
        if cve and cve in seen_cves:
            continue
        if cve:
            seen_cves.add(cve)
        unique_findings.append(f)

    return unique_findings


def _has_python_deps(path: Path) -> bool:
    """Check if path has Python dependency files."""
    return any([
        (path / "requirements.txt").exists(),
        (path / "pyproject.toml").exists(),
        (path / "setup.py").exists(),
        (path / "Pipfile").exists(),
    ])


def _run_pip_audit(path: Path) -> list[dict[str, Any]]:
    """Run pip-audit and return normalized findings."""
    findings: list[dict[str, Any]] = []

    try:
        cmd = ["pip-audit", "--format", "json"]

        # If there's a requirements.txt, use it
        req_file = path / "requirements.txt"
        if req_file.exists():
            cmd.extend(["-r", str(req_file)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=300
        )

        output = result.stdout or result.stderr
        if output:
            try:
                data = json.loads(output)
                # pip-audit returns list of vulnerabilities
                vulns = data if isinstance(data, list) else data.get("dependencies", [])
                for dep in vulns:
                    for vuln in dep.get("vulns", []):
                        findings.append({
                            "tool": "pip-audit",
                            "package": dep.get("name", "unknown"),
                            "version": dep.get("version", ""),
                            "cve": vuln.get("id", ""),
                            "severity": _normalize_severity(vuln.get("fix_versions", [])),
                            "description": vuln.get("description", "")[:200] if vuln.get("description") else "",
                            "fix_version": vuln.get("fix_versions", [None])[0] if vuln.get("fix_versions") else None,
                        })
            except json.JSONDecodeError:
                pass

    except FileNotFoundError:
        print("  [WARN] pip-audit not found, skipping")
    except subprocess.TimeoutExpired:
        print("  [WARN] pip-audit timed out")
    except Exception as e:
        print(f"  [WARN] pip-audit error: {e}")

    return findings


def _run_npm_audit(path: Path) -> list[dict[str, Any]]:
    """Run npm audit and return normalized findings."""
    findings: list[dict[str, Any]] = []

    try:
        cmd = ["npm", "audit", "--json"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=300
        )

        if result.stdout:
            try:
                data = json.loads(result.stdout)
                vulns = data.get("vulnerabilities", {})
                for name, info in vulns.items():
                    findings.append({
                        "tool": "npm-audit",
                        "package": name,
                        "version": info.get("range", ""),
                        "cve": info.get("via", [{}])[0].get("cve", "") if isinstance(info.get("via", []), list) and info.get("via") else "",
                        "severity": info.get("severity", "unknown"),
                        "description": info.get("via", [{}])[0].get("title", "") if isinstance(info.get("via", []), list) and info.get("via") else "",
                    })
            except (json.JSONDecodeError, IndexError, TypeError):
                pass

    except FileNotFoundError:
        print("  [WARN] npm not found, skipping")
    except subprocess.TimeoutExpired:
        print("  [WARN] npm audit timed out")
    except Exception as e:
        print(f"  [WARN] npm audit error: {e}")

    return findings


def _run_trivy(path: Path) -> list[dict[str, Any]]:
    """Run Trivy filesystem scan and return normalized findings."""
    findings: list[dict[str, Any]] = []

    try:
        cmd = [
            "trivy", "filesystem",
            "--format", "json",
            "--quiet",
            str(path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # Trivy can be slow
        )

        if result.stdout:
            try:
                data = json.loads(result.stdout)
                for result_item in data.get("Results", []):
                    for vuln in result_item.get("Vulnerabilities", []):
                        findings.append({
                            "tool": "trivy",
                            "package": vuln.get("PkgName", "unknown"),
                            "version": vuln.get("InstalledVersion", ""),
                            "cve": vuln.get("VulnerabilityID", ""),
                            "severity": vuln.get("Severity", "UNKNOWN").lower(),
                            "description": vuln.get("Title", "")[:200] if vuln.get("Title") else "",
                            "fix_version": vuln.get("FixedVersion"),
                            "target": result_item.get("Target", ""),
                        })
            except json.JSONDecodeError:
                pass

    except FileNotFoundError:
        print("  [WARN] trivy not found, skipping")
    except subprocess.TimeoutExpired:
        print("  [WARN] trivy timed out")
    except Exception as e:
        print(f"  [WARN] trivy error: {e}")

    return findings


def _normalize_severity(fix_versions: list[str] | None) -> str:
    """Estimate severity based on whether a fix exists."""
    # pip-audit doesn't provide severity, so we estimate
    if fix_versions:
        return "medium"  # Fixable
    return "high"  # No known fix


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    results = run_deps_audit(target)
    print(json.dumps(results, indent=2))
