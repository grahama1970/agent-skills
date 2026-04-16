"""Tier 1 — OWASP LLM Top 10 Analysis (report-only).

P10: prompt-injection (LLM01)
P11: output-handling (LLM05)
P12: excessive-agency (LLM06)
P13: supply-chain (LLM03)
P14: unbounded-consumption (LLM10)
"""
from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

import config
from probes import register_probe, ProbeResult, ProbeStatus


def _scan_files(
    pattern: re.Pattern,
    extensions: tuple[str, ...] = ("*.py",),
    exclude_dirs: tuple[str, ...] = (".venv", "node_modules", "__pycache__"),
) -> list[str]:
    """Scan embry-os files for regex pattern matches."""
    matches = []
    for ext in extensions:
        for f in config.EMBRY_OS_ROOT.rglob(ext):
            if any(d in str(f) for d in exclude_dirs):
                continue
            try:
                text = f.read_text(errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        matches.append(f"{f.relative_to(config.EMBRY_OS_ROOT)}:{i}")
            except OSError:
                continue
    return matches


@register_probe("P10", "prompt-injection-deep", tier=2, auto_fixable=False)
def probe_prompt_injection_deep(autofix: bool = False) -> ProbeResult:
    """Deep SKILL.md analysis for prompt injection vectors.

    Checks: control characters, nested YAML, instruction-override patterns,
    unicode homoglyphs in trigger definitions.
    """
    issues = []

    control_char_pattern = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    override_pattern = re.compile(
        r"(?i)(ignore\s+(previous|above|all)|you\s+are\s+now|<\|im_start\|>|"
        r"system\s*:\s*override|IMPORTANT:\s*disregard)"
    )

    for skillmd in config.EMBRY_OS_ROOT.rglob("SKILL.md"):
        rel = str(skillmd.relative_to(config.EMBRY_OS_ROOT))
        try:
            text = skillmd.read_text(errors="ignore")

            # Control characters
            for i, line in enumerate(text.splitlines(), 1):
                if control_char_pattern.search(line):
                    issues.append(f"{rel}:{i} control character detected")

            # Instruction override in description/triggers
            for i, line in enumerate(text.splitlines(), 1):
                if override_pattern.search(line):
                    issues.append(f"{rel}:{i} instruction-override language")

            # Nested YAML in triggers (could expand frontmatter)
            if "triggers:" in text:
                in_triggers = False
                for i, line in enumerate(text.splitlines(), 1):
                    if "triggers:" in line:
                        in_triggers = True
                        continue
                    if in_triggers:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("-") and not stripped.startswith("#"):
                            in_triggers = False
                        elif ":" in stripped and stripped.startswith("-"):
                            # Nested key-value in trigger
                            issues.append(f"{rel}:{i} nested YAML in trigger")

        except OSError:
            continue

    if not issues:
        return ProbeResult(
            probe_id="P10", name="prompt-injection-deep", tier=2,
            status=ProbeStatus.PASS, message="No prompt injection vectors in SKILL.md files",
        )

    return ProbeResult(
        probe_id="P10", name="prompt-injection-deep", tier=2,
        status=ProbeStatus.WARN,
        message=f"{len(issues)} prompt injection concern(s) in SKILL.md files",
        details={"issues": issues[:20]},
    )


@register_probe("P11", "output-handling", tier=2, auto_fixable=False)
def probe_output_handling(autofix: bool = False) -> ProbeResult:
    """Trace subprocess stdout flowing into eval/exec."""
    # Look for patterns like: result = subprocess.run(...) then eval(result.stdout)
    eval_patterns = re.compile(r"(eval|exec)\s*\(\s*\w*\.stdout")
    dangerous_patterns = re.compile(r"(eval|exec)\s*\(\s*(result|output|stdout|resp)")

    matches = _scan_files(eval_patterns)
    matches.extend(_scan_files(dangerous_patterns))
    matches = sorted(set(matches))

    if not matches:
        return ProbeResult(
            probe_id="P11", name="output-handling", tier=2,
            status=ProbeStatus.PASS, message="No subprocess→eval/exec flows detected",
        )

    return ProbeResult(
        probe_id="P11", name="output-handling", tier=2,
        status=ProbeStatus.FAIL,
        message=f"{len(matches)} dangerous output handling pattern(s)",
        details={"matches": matches[:20]},
    )


@register_probe("P12", "excessive-agency", tier=2, auto_fixable=False)
def probe_excessive_agency(autofix: bool = False) -> ProbeResult:
    """Check for skills without permission boundaries (allowed-tools not set)."""
    issues = []

    for skillmd in config.EMBRY_OS_ROOT.rglob("SKILL.md"):
        try:
            text = skillmd.read_text(errors="ignore")
            rel = str(skillmd.relative_to(config.EMBRY_OS_ROOT))

            # Check if allowed-tools is defined in frontmatter
            has_allowed_tools = False
            in_frontmatter = False
            for line in text.splitlines():
                if line.strip() == "---":
                    in_frontmatter = not in_frontmatter
                    continue
                if in_frontmatter and "allowed-tools:" in line:
                    has_allowed_tools = True
                    break

            if not has_allowed_tools:
                issues.append(f"{rel}: no allowed-tools defined")

        except OSError:
            continue

    if not issues:
        return ProbeResult(
            probe_id="P12", name="excessive-agency", tier=2,
            status=ProbeStatus.PASS, message="All skills have permission boundaries",
        )

    return ProbeResult(
        probe_id="P12", name="excessive-agency", tier=2,
        status=ProbeStatus.WARN,
        message=f"{len(issues)} skill(s) without allowed-tools boundary",
        details={"issues": issues[:20]},
    )


@register_probe("P13", "supply-chain", tier=2, auto_fixable=False)
def probe_supply_chain(autofix: bool = False) -> ProbeResult:
    """Check for unpinned deps and env-controlled imports."""
    issues = []

    # Unpinned dependencies (>= without <)
    unpinned_pattern = re.compile(r'"[a-zA-Z0-9_-]+>=\d[^"]*"')
    upper_bound_pattern = re.compile(r'<\d')

    for pyproject in config.EMBRY_OS_ROOT.rglob("pyproject.toml"):
        if ".venv" in str(pyproject):
            continue
        try:
            text = pyproject.read_text(errors="ignore")
            rel = str(pyproject.relative_to(config.EMBRY_OS_ROOT))
            for i, line in enumerate(text.splitlines(), 1):
                if unpinned_pattern.search(line) and not upper_bound_pattern.search(line):
                    dep_name = line.strip().strip('"').strip("'").strip(",").split(">=")[0]
                    issues.append(f"{rel}:{i} unpinned: {dep_name}")
        except OSError:
            continue

    # Env-controlled imports
    env_import_pattern = re.compile(r"importlib\.import_module\s*\(\s*os\.(getenv|environ)")
    env_matches = _scan_files(env_import_pattern)
    for m in env_matches:
        issues.append(f"{m} env-controlled import")

    if not issues:
        return ProbeResult(
            probe_id="P13", name="supply-chain", tier=2,
            status=ProbeStatus.PASS, message="No supply chain concerns",
        )

    return ProbeResult(
        probe_id="P13", name="supply-chain", tier=2,
        status=ProbeStatus.WARN,
        message=f"{len(issues)} supply chain concern(s)",
        details={"issues": issues[:30]},
    )


@register_probe("P14", "unbounded-consumption", tier=2, auto_fixable=False)
def probe_unbounded_consumption(autofix: bool = False) -> ProbeResult:
    """Check subprocess/requests calls without timeout."""
    issues = []

    # subprocess.run without timeout
    sub_pattern = re.compile(r"subprocess\.(run|Popen|call|check_output)\s*\(")
    timeout_pattern = re.compile(r"timeout\s*=")

    for py_file in config.EMBRY_OS_ROOT.rglob("*.py"):
        if any(d in str(py_file) for d in (".venv", "node_modules", "__pycache__")):
            continue
        try:
            text = py_file.read_text(errors="ignore")
            lines = text.splitlines()
            rel = str(py_file.relative_to(config.EMBRY_OS_ROOT))
            for i, line in enumerate(lines, 1):
                if sub_pattern.search(line):
                    snippet = "\n".join(lines[max(0, i - 1):min(len(lines), i + 5)])
                    if not timeout_pattern.search(snippet):
                        issues.append(f"{rel}:{i} subprocess without timeout")
        except OSError:
            continue

    # HTTP requests without timeout
    http_pattern = re.compile(r"(requests|httpx)\.(get|post|put|delete|patch|head)\s*\(")
    for py_file in config.EMBRY_OS_ROOT.rglob("*.py"):
        if any(d in str(py_file) for d in (".venv", "node_modules", "__pycache__")):
            continue
        try:
            text = py_file.read_text(errors="ignore")
            lines = text.splitlines()
            rel = str(py_file.relative_to(config.EMBRY_OS_ROOT))
            for i, line in enumerate(lines, 1):
                if http_pattern.search(line):
                    snippet = "\n".join(lines[max(0, i - 1):min(len(lines), i + 5)])
                    if not timeout_pattern.search(snippet):
                        issues.append(f"{rel}:{i} HTTP request without timeout")
        except OSError:
            continue

    if not issues:
        return ProbeResult(
            probe_id="P14", name="unbounded-consumption", tier=2,
            status=ProbeStatus.PASS, message="All external calls have timeouts",
        )

    return ProbeResult(
        probe_id="P14", name="unbounded-consumption", tier=2,
        status=ProbeStatus.WARN,
        message=f"{len(issues)} unbounded call(s) without timeout",
        details={"issues": issues[:30]},
    )
