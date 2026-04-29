#!/usr/bin/env python3
"""Normalize monitor-codebase scan sources into a Fallow-style contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
VERSION = "monitor-codebase-fallow-v2"
ERROR_SEVERITIES = {"error", "critical"}
WARN_SEVERITIES = {"warn", "warning", "high", "medium", "moderate", "major", "minor", "info"}


def load_json(path: str | None, default: Any = None) -> Any:
    """Load JSON from a path, returning a default on empty or invalid input."""
    if not path:
        return {} if default is None else default
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
        if not text:
            return {} if default is None else default
        return json.loads(text)
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def parse_json_text(text: str | None, default: Any = None) -> Any:
    """Parse JSON text from a shell argument."""
    if not text:
        return [] if default is None else default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return [] if default is None else default


def rel_path(value: Any, root: Path) -> str:
    """Return a stable project-relative path for a finding."""
    if value is None:
        return "."
    text = str(value).strip()
    if not text:
        return "."
    path = Path(text)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix()


def stable_id(rule: str, file_path: str, line: int, extra: Any = "") -> str:
    """Build a stable finding id with a short suffix when extra context exists."""
    base = f"{rule}:{file_path}:{line}"
    if not extra:
        return base
    digest = hashlib.sha1(json.dumps(extra, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:10]
    return f"{base}:{digest}"


def norm_severity(value: Any, default: str = "warn") -> str:
    """Map scanner-specific severities to monitor-codebase severities."""
    severity = str(value or default).lower()
    if severity in {"critical", "error", "warn", "info"}:
        return severity
    if severity in {"high", "major"}:
        return "error"
    if severity in {"medium", "moderate", "minor", "warning"}:
        return "warn"
    return default


def route_for(rule: str, file_path: str, severity: str, source: str) -> dict[str, Any]:
    """Choose the safest downstream remediation route for a normalized finding."""
    if rule.startswith("prompt-"):
        runner = "review-prompt"
        reason = "Prompt finding needs the prompt review loop."
        confidence = 0.68
    elif rule.startswith("embedding-"):
        runner = "local"
        reason = "Embedding coverage repair is deterministic ingest-code work."
        confidence = 0.74
    elif rule.startswith("security-"):
        runner = "human-review"
        reason = "Security findings need owner review before code changes."
        confidence = 0.55
    elif source in {"duplication", "dependency_graph"} or rule.endswith("large-file"):
        runner = "subagent-runner"
        reason = "Structural finding likely needs design judgment."
        confidence = 0.60
    elif severity in ERROR_SEVERITIES:
        runner = "code-runner"
        reason = "Blocking finding has bounded source evidence."
        confidence = 0.70
    else:
        runner = "code-runner"
        reason = "Bounded finding can be fixed with a narrow file allowlist."
        confidence = 0.66

    route: dict[str, Any] = {"runner": runner, "confidence": confidence, "reason": reason}
    if file_path and file_path != ".":
        route["allowlist"] = [file_path]
    if file_path.endswith(".py"):
        route["definition_of_done"] = {"command": "python -m py_compile <changed-python-files>", "assertion": "exit_code == 0"}
    elif file_path.endswith((".ts", ".tsx", ".js", ".jsx")):
        route["definition_of_done"] = {"command": "npm run check", "assertion": "exit_code == 0"}
    elif file_path.endswith(".rs"):
        route["definition_of_done"] = {"command": "cargo check", "assertion": "exit_code == 0"}
    elif rule.startswith("prompt-"):
        route["definition_of_done"] = {"command": "review-prompt --dry-run", "assertion": "payload assembles without missing context"}
    elif rule.startswith("embedding-"):
        route["definition_of_done"] = {"command": "ingest-code rescan --treesitter --scope monitor-<project>", "assertion": "embedding coverage status == pass"}
    return route


def action_for(rule: str, source: str, message: str, route: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the standard action list for a finding."""
    primary = {
        "type": rule,
        "auto_fixable": route.get("runner") in {"local", "code-runner"},
        "runner": route.get("runner", "human-review"),
        "description": message or f"Resolve `{rule}` from {source}.",
    }
    suppress = {
        "type": "suppress",
        "auto_fixable": False,
        "description": f"Document why `{rule}` is acceptable and add a narrow suppression only with owner approval.",
    }
    return [primary, suppress]


def make_finding(
    *,
    source: str,
    rule: str,
    file_path: str,
    line: Any = 0,
    message: str,
    severity: Any = "warn",
    confidence: float = 0.60,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a normalized finding."""
    try:
        line_int = int(line or 0)
    except (TypeError, ValueError):
        line_int = 0
    sev = norm_severity(severity)
    route = route_for(rule, file_path, sev, source)
    evidence_payload = {"source": source, **(evidence or {})}
    return {
        "finding_id": stable_id(rule, file_path, line_int, evidence_payload),
        "rule": rule,
        "source": source,
        "file": file_path or ".",
        "line": line_int,
        "message": message,
        "severity": sev,
        "confidence": confidence,
        "evidence": evidence_payload,
        "actions": action_for(rule, source, message, route),
        "remediation_route": route,
    }


def normalize_quality(data: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Normalize quality_checks.py violations, preserving existing rich metadata."""
    findings = []
    for item in data.get("violations", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        rule = str(item.get("rule", "quality-violation"))
        file_path = rel_path(item.get("file") or item.get("path"), root)
        line = item.get("line", 0)
        finding = dict(item)
        finding["source"] = "quality_checks"
        finding["file"] = file_path
        finding["line"] = int(line or 0)
        finding.setdefault("message", f"Quality violation: {rule}")
        finding.setdefault("severity", "warn")
        finding.setdefault("confidence", 0.60)
        finding.setdefault("finding_id", stable_id(rule, file_path, finding["line"]))
        finding.setdefault("evidence", {"source": "quality_checks", "detector": "quality_checks.py"})
        finding.setdefault("remediation_route", route_for(rule, file_path, finding["severity"], "quality_checks"))
        finding.setdefault("actions", action_for(rule, "quality_checks", finding["message"], finding["remediation_route"]))
        findings.append(finding)
    return findings


def normalize_best_practices(items: list[Any], root: Path) -> list[dict[str, Any]]:
    """Normalize shell best-practices findings."""
    findings = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rule = str(item.get("rule", "best-practice"))
        target = item.get("target") or item.get("file") or "."
        file_path = rel_path(target, root)
        skill = str(item.get("skill", "best-practices"))
        detail = str(item.get("detail", "") or "")
        message = f"{skill}: {rule}" + (f" ({detail})" if detail else "")
        findings.append(make_finding(
            source="best_practices",
            rule=rule,
            file_path=file_path,
            line=item.get("line", 0),
            message=message,
            severity=item.get("severity", "warn"),
            confidence=0.62,
            evidence={"skill": skill, "raw": item},
        ))
    return findings


def normalize_security(data: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Normalize security-scan output without assuming one exact schema."""
    if not isinstance(data, dict) or data.get("error"):
        return []
    findings: list[dict[str, Any]] = []

    buckets = [
        ("secrets", "security-secret", "critical"),
        ("deps", "security-vulnerable-dependency", "error"),
        ("vulnerabilities", "security-vulnerable-dependency", "error"),
        ("sast", "security-sast", "warn"),
        ("findings", "security-finding", "warn"),
    ]
    for key, default_rule, default_severity in buckets:
        values = data.get(key, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, str):
                raw = {"message": item}
            elif isinstance(item, dict):
                raw = item
            else:
                continue
            rule = str(raw.get("rule") or raw.get("check_id") or raw.get("type") or default_rule)
            file_path = rel_path(raw.get("file") or raw.get("path") or raw.get("location") or ".", root)
            message = str(raw.get("message") or raw.get("description") or raw.get("title") or default_rule)
            findings.append(make_finding(
                source="security_scan",
                rule=rule if rule.startswith("security-") else f"security-{rule}",
                file_path=file_path,
                line=raw.get("line", raw.get("start_line", 0)),
                message=message,
                severity=raw.get("severity", default_severity),
                confidence=0.82,
                evidence={"bucket": key, "raw": raw},
            ))
    return findings


def normalize_duplication(data: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Normalize duplicate function clusters."""
    findings = []
    for cluster in data.get("clusters", []) if isinstance(data, dict) else []:
        locations = cluster.get("locations", []) if isinstance(cluster, dict) else []
        if not locations:
            continue
        first = locations[0]
        file_path = rel_path(first.get("file", "."), root)
        name = first.get("name", "function")
        count = cluster.get("count", len(locations))
        findings.append(make_finding(
            source="duplication",
            rule="duplicate-function",
            file_path=file_path,
            line=first.get("line", 0),
            message=f"Function `{name}` is duplicated in {count} locations.",
            severity="warn",
            confidence=0.86,
            evidence={"locations": locations, "hash": cluster.get("hash")},
        ))
    return findings


def normalize_dependencies(data: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Normalize dependency graph findings."""
    del root
    findings = []
    for item in data.get("circular_deps", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        cycle = item.get("cycle", [])
        severity = "error" if item.get("severity") == "high" else "warn"
        findings.append(make_finding(
            source="dependency_graph",
            rule="circular-dependency",
            file_path=".",
            line=0,
            message="Circular dependency detected: " + " -> ".join(str(part) for part in cycle),
            severity=severity,
            confidence=0.78,
            evidence={"cycle": cycle, "raw": item},
        ))
    return findings


def normalize_coverage(data: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Normalize structural coverage findings."""
    if not isinstance(data, dict) or data.get("error") or data.get("skipped"):
        return []
    findings = []
    coverage_pct = float(data.get("coverage_pct", 0.0) or 0.0)
    if int(data.get("total_modules", 0) or 0) > 0 and coverage_pct < 30.0:
        findings.append(make_finding(
            source="coverage_analysis",
            rule="coverage-low",
            file_path=".",
            line=0,
            message=f"Structural Python test coverage is {coverage_pct:.2f}%, below 30%.",
            severity="warn",
            confidence=0.72,
            evidence={"coverage_pct": coverage_pct, "total_modules": data.get("total_modules")},
        ))
    for item in data.get("untested", [])[:25]:
        if not isinstance(item, dict):
            continue
        file_path = rel_path(item.get("path", "."), root)
        findings.append(make_finding(
            source="coverage_analysis",
            rule="module-untested",
            file_path=file_path,
            line=0,
            message=f"Module `{item.get('module', file_path)}` has no nearby test file.",
            severity="info",
            confidence=0.65,
            evidence={"raw": item},
        ))
    return findings


def normalize_embedding(data: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Normalize Qdrant embedding coverage results."""
    del root
    if not isinstance(data, dict) or data.get("status") == "pass":
        return []
    findings = []
    for file_path in data.get("missing_files", []) if isinstance(data.get("missing_files"), list) else []:
        findings.append(make_finding(
            source="embedding_coverage",
            rule="embedding-missing-file",
            file_path=str(file_path),
            line=0,
            message="Source file has no synced code_symbols embedding in Qdrant.",
            severity="warn",
            confidence=0.80,
            evidence={"scope": data.get("scope"), "status": data.get("status")},
        ))
    for file_path in data.get("unsynced_files", []) if isinstance(data.get("unsynced_files"), list) else []:
        findings.append(make_finding(
            source="embedding_coverage",
            rule="embedding-unsynced-file",
            file_path=str(file_path),
            line=0,
            message="Source file has code_symbols records but no synced Qdrant point.",
            severity="warn",
            confidence=0.80,
            evidence={"scope": data.get("scope"), "status": data.get("status")},
        ))
    if not findings:
        findings.append(make_finding(
            source="embedding_coverage",
            rule="embedding-coverage-unavailable",
            file_path=".",
            line=0,
            message=f"Embedding coverage status is {data.get('status', 'unknown')}.",
            severity="warn" if data.get("status") == "warn" else "error",
            confidence=0.70,
            evidence={"coverage": data},
        ))
    return findings


def normalize_skills_ci(data: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Normalize skills-ci findings."""
    findings = []
    for item in data.get("violations", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        rule = str(item.get("rule") or item.get("check") or item.get("id") or "skills-ci")
        file_path = rel_path(item.get("file") or item.get("path") or item.get("target") or ".", root)
        message = str(item.get("message") or item.get("detail") or f"skills-ci violation: {rule}")
        findings.append(make_finding(
            source="skills_ci",
            rule=rule,
            file_path=file_path,
            line=item.get("line", 0),
            message=message,
            severity=item.get("severity", item.get("level", "warn")),
            confidence=0.76,
            evidence={"raw": item},
        ))
    return findings


def source_error_findings(sources: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert failed scan source objects into findings."""
    findings = []
    for source, data in sources.items():
        if isinstance(data, dict) and data.get("error"):
            findings.append(make_finding(
                source=source,
                rule="scan-source-error",
                file_path=".",
                line=0,
                message=f"{source} failed: {data.get('error')}",
                severity="warn",
                confidence=0.90,
                evidence={"source_payload": data},
            ))
    return findings


def changed_files(base_ref: str, project_path: Path) -> tuple[list[str], str, str]:
    """Return changed files, effective base ref, and head sha for audit mode."""
    candidates = [base_ref] if base_ref else ["origin/main", "main", "HEAD~1"]
    head_sha = ""
    try:
        head_sha = subprocess.check_output(
            ["git", "-C", str(project_path), "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        pass

    for candidate in candidates:
        try:
            output = subprocess.check_output(
                ["git", "-C", str(project_path), "diff", "--name-only", f"{candidate}...HEAD", "--"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            files = sorted({line.strip() for line in output.splitlines() if line.strip()})
            return files, candidate, head_sha
        except (OSError, subprocess.CalledProcessError):
            continue
    return [], base_ref or "", head_sha


def read_changed_file(path: str | None) -> list[str]:
    """Read a newline-delimited changed file list."""
    if not path:
        return []
    try:
        return sorted({line.strip() for line in Path(path).read_text().splitlines() if line.strip()})
    except OSError:
        return []


def filter_to_changed(findings: list[dict[str, Any]], changed: list[str]) -> list[dict[str, Any]]:
    """Filter file-scoped findings to changed files while preserving repo-level findings."""
    if not changed:
        return []
    changed_set = {Path(path).as_posix() for path in changed}
    kept = []
    for finding in findings:
        file_path = Path(str(finding.get("file") or ".")).as_posix()
        if file_path == "." or file_path in changed_set:
            kept.append(finding)
            continue
        if any(file_path.startswith(f"{changed_file}/") for changed_file in changed_set):
            kept.append(finding)
    return kept


def summarize(findings: list[dict[str, Any]], sources: dict[str, Any]) -> dict[str, Any]:
    """Build a backward-compatible summary object."""
    by_source = Counter(str(item.get("source", "unknown")) for item in findings)
    by_rule = Counter(str(item.get("rule", "unknown")) for item in findings)
    by_severity = Counter(str(item.get("severity", "warn")) for item in findings)

    security_total = by_source.get("security_scan", 0)
    embedding = sources.get("embedding_coverage", {}) if isinstance(sources.get("embedding_coverage"), dict) else {}
    coverage = sources.get("coverage_analysis", {}) if isinstance(sources.get("coverage_analysis"), dict) else {}
    skills_ci = sources.get("skills_ci", {}) if isinstance(sources.get("skills_ci"), dict) else {}

    return {
        "total_findings": len(findings),
        "total_issues": len(findings),
        "by_source": dict(sorted(by_source.items())),
        "by_rule": dict(sorted(by_rule.items())),
        "by_severity": dict(sorted(by_severity.items())),
        "total_bp_violations": by_source.get("best_practices", 0),
        "total_quality_violations": by_source.get("quality_checks", 0),
        "total_security_findings": security_total,
        "secrets_found": by_rule.get("security-secret", 0),
        "vulnerable_deps": by_rule.get("security-vulnerable-dependency", 0),
        "sast_findings": by_rule.get("security-sast", 0),
        "duplicate_functions": by_source.get("duplication", 0),
        "circular_dependencies": by_rule.get("circular-dependency", 0),
        "coverage_pct": float(coverage.get("coverage_pct", 0.0) or 0.0),
        "embedding_coverage_pct": float(embedding.get("coverage_pct", 100.0) or 0.0),
        "embedding_missing_files": int(embedding.get("missing_files_count", 0) or 0),
        "embedding_unsynced_files": int(embedding.get("unsynced_files_count", 0) or 0),
        "embedding_coverage_issues": by_source.get("embedding_coverage", 0),
        "skills_ci_errors": skills_ci.get("summary", {}).get("error", 0) if isinstance(skills_ci.get("summary"), dict) else by_severity.get("error", 0),
        "skills_ci_warnings": skills_ci.get("summary", {}).get("warn", 0) if isinstance(skills_ci.get("summary"), dict) else by_source.get("skills_ci", 0),
    }


def verdict_for(findings: list[dict[str, Any]]) -> str:
    """Return pass/warn/fail from normalized severities."""
    if any(str(f.get("severity")) in ERROR_SEVERITIES for f in findings):
        return "fail"
    if findings:
        return "warn"
    return "pass"


def build_report(args: argparse.Namespace, *, command: str) -> dict[str, Any]:
    """Build the normalized scan or audit report."""
    project_path = Path(args.project_path).resolve()
    sources = {
        "project_state": load_json(getattr(args, "project_state", None)),
        "cleanup": load_json(getattr(args, "cleanup", None)),
        "quality_checks": load_json(getattr(args, "quality_checks", None)),
        "security_scan": load_json(getattr(args, "security_scan", None)),
        "duplication_scan": load_json(getattr(args, "duplication_scan", None)),
        "dependency_graph": load_json(getattr(args, "dependency_graph", None)),
        "coverage_analysis": load_json(getattr(args, "coverage_analysis", None)),
        "ingest_code": load_json(getattr(args, "ingest_code", None)),
        "embedding_coverage": load_json(getattr(args, "embedding_coverage", None)),
        "skills_ci": load_json(getattr(args, "skills_ci", None)),
    }
    best_practices = load_json(getattr(args, "best_practices", None), [])
    if not best_practices:
        best_practices = parse_json_text(getattr(args, "best_practices_json", None), [])
    sources["best_practices"] = best_practices

    findings: list[dict[str, Any]] = []
    findings.extend(normalize_best_practices(best_practices if isinstance(best_practices, list) else [], project_path))
    findings.extend(normalize_quality(sources["quality_checks"], project_path))
    findings.extend(normalize_security(sources["security_scan"], project_path))
    findings.extend(normalize_duplication(sources["duplication_scan"], project_path))
    findings.extend(normalize_dependencies(sources["dependency_graph"], project_path))
    findings.extend(normalize_coverage(sources["coverage_analysis"], project_path))
    findings.extend(normalize_embedding(sources["embedding_coverage"], project_path))
    findings.extend(normalize_skills_ci(sources["skills_ci"], project_path))
    findings.extend(source_error_findings(sources))

    base_ref = getattr(args, "base_ref", "") or ""
    head_sha = ""
    changed = read_changed_file(getattr(args, "changed_files_file", None))
    if command == "audit":
        if not changed:
            changed, base_ref, head_sha = changed_files(base_ref, project_path)
        else:
            try:
                head_sha = subprocess.check_output(
                    ["git", "-C", str(project_path), "rev-parse", "--short", "HEAD"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
            except (OSError, subprocess.CalledProcessError):
                head_sha = ""
        findings = filter_to_changed(findings, changed)

    summary = summarize(findings, sources)
    report = {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "command": command,
        "project": args.project_name,
        "path": str(project_path),
        "timestamp": getattr(args, "timestamp", "") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "verdict": verdict_for(findings),
        "summary": summary,
        "findings": findings,
        "sources": sources,
        "notifications": {"discord_warnings": notification_warnings(summary, findings)},
    }
    if command == "audit":
        report["base_ref"] = base_ref
        report["head_sha"] = head_sha
        report["changed_files_count"] = len(changed)
        report["changed_files"] = changed
    return report


def notification_warnings(summary: dict[str, Any], findings: list[dict[str, Any]]) -> list[str]:
    """Return short alert strings for dashboards/Discord."""
    warnings = []
    if summary.get("coverage_pct", 100.0) < 30.0:
        warnings.append(f"Low test coverage: {summary.get('coverage_pct', 0.0):.2f}% (<30%)")
    if summary.get("embedding_coverage_issues", 0):
        warnings.append(f"Code embedding coverage issues: {summary['embedding_coverage_issues']}")
    critical = sum(1 for item in findings if item.get("severity") == "critical")
    errors = sum(1 for item in findings if item.get("severity") == "error")
    if critical or errors:
        warnings.append(f"Blocking findings: {critical} critical, {errors} error")
    return warnings


def write_report(report: dict[str, Any], output: str | None) -> None:
    """Write the report to a file or stdout."""
    text = json.dumps(report, indent=2) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def add_source_args(parser: argparse.ArgumentParser) -> None:
    """Add shared source file arguments."""
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--project-path", required=True)
    parser.add_argument("--timestamp", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--project-state")
    parser.add_argument("--cleanup")
    parser.add_argument("--best-practices")
    parser.add_argument("--best-practices-json")
    parser.add_argument("--quality-checks")
    parser.add_argument("--security-scan")
    parser.add_argument("--duplication-scan")
    parser.add_argument("--dependency-graph")
    parser.add_argument("--coverage-analysis")
    parser.add_argument("--ingest-code")
    parser.add_argument("--embedding-coverage")
    parser.add_argument("--skills-ci")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Fallow-style monitor-codebase output.")
    sub = parser.add_subparsers(dest="command", required=True)

    aggregate = sub.add_parser("aggregate", help="Aggregate a full scan")
    add_source_args(aggregate)

    audit = sub.add_parser("audit", help="Aggregate a changed-file audit")
    add_source_args(audit)
    audit.add_argument("--base-ref", default="")
    audit.add_argument("--changed-files-file", default="")

    args = parser.parse_args()
    report = build_report(args, command=args.command)
    write_report(report, args.output)
    return 1 if args.command == "audit" and report["verdict"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
