"""Tier 0 — Deterministic probes (auto-fix safe, microseconds).

P01: sast-semgrep
P02: dependency-audit
P03: secrets-detection
P04: shell-true-audit
P05: missing-timeout-audit
P06: skillmd-injection-check
P07: dynamic-import-audit
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from loguru import logger

import config
from probes import register_probe, ProbeResult, ProbeStatus


def _run_tool(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess | None:
    """Run an external tool, returning None on failure."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug("Tool failed: {}", e)
        return None


@register_probe("P01", "sast-semgrep", tier=0, auto_fixable=True)
def probe_sast_semgrep(autofix: bool = False) -> ProbeResult:
    """Run Semgrep with OWASP LLM Top 10 rules against embry-os."""
    if not shutil.which("semgrep"):
        return ProbeResult(
            probe_id="P01", name="sast-semgrep", tier=0,
            status=ProbeStatus.SKIP, message="semgrep not installed",
        )

    rules_file = config.OWASP_RULES_FILE
    if not rules_file.exists():
        return ProbeResult(
            probe_id="P01", name="sast-semgrep", tier=0,
            status=ProbeStatus.SKIP, message=f"Rules file not found: {rules_file}",
        )

    cmd = [
        "semgrep", "scan",
        "--config", str(rules_file),
        "--json",
        str(config.EMBRY_OS_ROOT),
    ]
    if autofix:
        cmd.insert(2, "--autofix")

    result = _run_tool(cmd, timeout=300)
    if result is None:
        return ProbeResult(
            probe_id="P01", name="sast-semgrep", tier=0,
            status=ProbeStatus.FAIL, message="Semgrep execution failed",
        )

    # Parse JSON output
    try:
        import json
        data = json.loads(result.stdout)
        findings = data.get("results", [])
        errors_count = len(findings)
    except (json.JSONDecodeError, KeyError):
        errors_count = result.stdout.count("severity")

    if errors_count == 0:
        return ProbeResult(
            probe_id="P01", name="sast-semgrep", tier=0,
            status=ProbeStatus.PASS, message="No OWASP violations found",
            details={"findings": 0},
        )

    status = ProbeStatus.FIXED if autofix else ProbeStatus.FAIL
    return ProbeResult(
        probe_id="P01", name="sast-semgrep", tier=0,
        status=status,
        message=f"{errors_count} OWASP violation(s) found",
        details={"findings": errors_count},
        auto_fixable=True,
        fix_applied=autofix,
    )


@register_probe("P02", "dependency-audit", tier=0, auto_fixable=True)
def probe_dependency_audit(autofix: bool = False) -> ProbeResult:
    """Run pip-audit and npm audit against embry-os dependencies."""
    vulns = 0
    details: dict = {}

    # pip-audit
    if shutil.which("pip-audit"):
        cmd = ["pip-audit"]
        if autofix:
            cmd.append("--fix")
        result = _run_tool(cmd, timeout=180)
        if result:
            pip_vulns = result.stdout.lower().count("vulnerability") + result.stdout.lower().count("vuln")
            vulns += pip_vulns
            details["pip_audit"] = {"vulns": pip_vulns, "returncode": result.returncode}
    else:
        details["pip_audit"] = "not installed"

    # npm audit (if package.json exists)
    pkg_jsons = list(config.EMBRY_OS_ROOT.rglob("package.json"))
    pkg_jsons = [p for p in pkg_jsons if "node_modules" not in str(p)]
    if pkg_jsons and shutil.which("npm"):
        for pkg in pkg_jsons[:3]:
            result = _run_tool(
                ["npm", "audit", "--json"],
                timeout=60,
            )
            if result and result.returncode != 0:
                vulns += 1
                details[f"npm_audit_{pkg.parent.name}"] = "vulnerabilities found"

    # Trivy (if available)
    if shutil.which("trivy"):
        result = _run_tool(
            ["trivy", "fs", "--severity", "CRITICAL,HIGH", "--quiet", str(config.EMBRY_OS_ROOT)],
            timeout=300,
        )
        if result and result.returncode != 0:
            trivy_lines = len([l for l in result.stdout.splitlines() if "CRITICAL" in l or "HIGH" in l])
            vulns += trivy_lines
            details["trivy"] = {"critical_high": trivy_lines}

    if vulns == 0:
        return ProbeResult(
            probe_id="P02", name="dependency-audit", tier=0,
            status=ProbeStatus.PASS, message="No dependency vulnerabilities found",
            details=details, auto_fixable=True,
        )

    return ProbeResult(
        probe_id="P02", name="dependency-audit", tier=0,
        status=ProbeStatus.FAIL,
        message=f"{vulns} dependency vulnerability indicator(s)",
        details=details, auto_fixable=True, fix_applied=autofix,
    )


@register_probe("P03", "secrets-detection", tier=0, auto_fixable=False)
def probe_secrets_detection(autofix: bool = False) -> ProbeResult:
    """Run gitleaks to detect hardcoded secrets."""
    if not shutil.which("gitleaks"):
        return ProbeResult(
            probe_id="P03", name="secrets-detection", tier=0,
            status=ProbeStatus.SKIP, message="gitleaks not installed",
        )

    result = _run_tool(
        ["gitleaks", "detect", "--source", str(config.EMBRY_OS_ROOT), "--no-git", "--quiet"],
        timeout=120,
    )
    if result is None:
        return ProbeResult(
            probe_id="P03", name="secrets-detection", tier=0,
            status=ProbeStatus.FAIL, message="gitleaks execution failed",
        )

    if result.returncode == 0:
        return ProbeResult(
            probe_id="P03", name="secrets-detection", tier=0,
            status=ProbeStatus.PASS, message="No secrets detected",
        )

    leak_count = result.stdout.count("Secret:")
    if leak_count == 0:
        leak_count = len(result.stdout.splitlines())

    return ProbeResult(
        probe_id="P03", name="secrets-detection", tier=0,
        status=ProbeStatus.FAIL,
        message=f"{leak_count} potential secret(s) detected",
        details={"leak_count": leak_count},
    )


@register_probe("P04", "shell-true-audit", tier=0, auto_fixable=False)
def probe_shell_true_audit(autofix: bool = False) -> ProbeResult:
    """Grep for subprocess.*shell=True across embry-os."""
    pattern = re.compile(r"subprocess\.\w+\(.*shell\s*=\s*True", re.IGNORECASE)
    violations = []

    for py_file in config.EMBRY_OS_ROOT.rglob("*.py"):
        if ".venv" in str(py_file) or "node_modules" in str(py_file):
            continue
        try:
            text = py_file.read_text(errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    violations.append(f"{py_file.relative_to(config.EMBRY_OS_ROOT)}:{i}")
        except OSError:
            continue

    if not violations:
        return ProbeResult(
            probe_id="P04", name="shell-true-audit", tier=0,
            status=ProbeStatus.PASS, message="No shell=True violations",
        )

    return ProbeResult(
        probe_id="P04", name="shell-true-audit", tier=0,
        status=ProbeStatus.WARN,
        message=f"{len(violations)} shell=True usage(s) found",
        details={"violations": violations[:20]},
    )


@register_probe("P05", "missing-timeout-audit", tier=0, auto_fixable=False)
def probe_missing_timeout_audit(autofix: bool = False) -> ProbeResult:
    """Grep for subprocess.run without timeout= parameter."""
    pattern_call = re.compile(r"subprocess\.run\(")
    pattern_timeout = re.compile(r"timeout\s*=")
    violations = []

    for py_file in config.EMBRY_OS_ROOT.rglob("*.py"):
        if ".venv" in str(py_file) or "node_modules" in str(py_file):
            continue
        try:
            text = py_file.read_text(errors="ignore")
            lines = text.splitlines()
            for i, line in enumerate(lines, 1):
                if pattern_call.search(line):
                    # Check this line and next few lines for timeout=
                    snippet = "\n".join(lines[max(0, i - 1):min(len(lines), i + 5)])
                    if not pattern_timeout.search(snippet):
                        violations.append(f"{py_file.relative_to(config.EMBRY_OS_ROOT)}:{i}")
        except OSError:
            continue

    if not violations:
        return ProbeResult(
            probe_id="P05", name="missing-timeout-audit", tier=0,
            status=ProbeStatus.PASS, message="All subprocess.run calls have timeouts",
        )

    return ProbeResult(
        probe_id="P05", name="missing-timeout-audit", tier=0,
        status=ProbeStatus.WARN,
        message=f"{len(violations)} subprocess.run without timeout",
        details={"violations": violations[:20]},
    )


@register_probe("P06", "skillmd-injection-check", tier=0, auto_fixable=False)
def probe_skillmd_injection(autofix: bool = False) -> ProbeResult:
    """Parse SKILL.md frontmatter for injection patterns."""
    injection_patterns = [
        re.compile(r"(?i)(ignore\s+previous|you\s+are\s+now|<\|im_start\|>)"),
        re.compile(r"[;\|`]"),  # Shell metacharacters in triggers
        re.compile(r"(%0[aAdD]|\\x0[aAdD]|\\n)"),  # Encoded newlines
    ]
    violations = []

    for skillmd in config.EMBRY_OS_ROOT.rglob("SKILL.md"):
        try:
            text = skillmd.read_text(errors="ignore")
            # Only check triggers section
            in_triggers = False
            for line in text.splitlines():
                if line.strip().startswith("triggers:"):
                    in_triggers = True
                    continue
                if in_triggers:
                    if line.strip() and not line.strip().startswith("-") and not line.strip().startswith("#"):
                        in_triggers = False
                        continue
                    for pat in injection_patterns:
                        if pat.search(line):
                            violations.append(
                                f"{skillmd.relative_to(config.EMBRY_OS_ROOT)}: {line.strip()[:80]}"
                            )
                            break
        except OSError:
            continue

    if not violations:
        return ProbeResult(
            probe_id="P06", name="skillmd-injection-check", tier=0,
            status=ProbeStatus.PASS, message="No injection patterns in SKILL.md triggers",
        )

    return ProbeResult(
        probe_id="P06", name="skillmd-injection-check", tier=0,
        status=ProbeStatus.FAIL,
        message=f"{len(violations)} injection pattern(s) in SKILL.md",
        details={"violations": violations[:10]},
    )


@register_probe("P07", "dynamic-import-audit", tier=0, auto_fixable=False)
def probe_dynamic_import_audit(autofix: bool = False) -> ProbeResult:
    """Check for importlib + os.getenv patterns (env-controlled imports)."""
    pattern_importlib = re.compile(r"importlib\.import_module\s*\(")
    pattern_env_import = re.compile(r"importlib\.import_module\s*\(\s*os\.(getenv|environ)")
    violations = []
    warnings = []

    for py_file in config.EMBRY_OS_ROOT.rglob("*.py"):
        if ".venv" in str(py_file) or "node_modules" in str(py_file):
            continue
        try:
            text = py_file.read_text(errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                rel = f"{py_file.relative_to(config.EMBRY_OS_ROOT)}:{i}"
                if pattern_env_import.search(line):
                    violations.append(rel)
                elif pattern_importlib.search(line):
                    warnings.append(rel)
        except OSError:
            continue

    if violations:
        return ProbeResult(
            probe_id="P07", name="dynamic-import-audit", tier=0,
            status=ProbeStatus.FAIL,
            message=f"{len(violations)} env-controlled import(s)",
            details={"violations": violations[:10], "warnings": warnings[:10]},
        )

    if warnings:
        return ProbeResult(
            probe_id="P07", name="dynamic-import-audit", tier=0,
            status=ProbeStatus.WARN,
            message=f"{len(warnings)} dynamic import(s) (review recommended)",
            details={"warnings": warnings[:10]},
        )

    return ProbeResult(
        probe_id="P07", name="dynamic-import-audit", tier=0,
        status=ProbeStatus.PASS, message="No risky dynamic imports found",
    )
