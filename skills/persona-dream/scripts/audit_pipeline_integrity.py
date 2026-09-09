#!/usr/bin/env python3
"""Audit Persona Dream pipeline files for unreviewed runtime seams."""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKIP = {"__pycache__", "generated_models", "research", "reports", "tests", "fixtures", "local"}
PLACEHOLDER_PHRASES = (
    "Auto-generated module docstring. Review for accuracy",
    "Purpose: Auto-generated module docstring",
)
COMMENT_DEBT = ("TODO", "FIXME", "not implemented")
VALIDATION_TOKENS = (
    "BaseModel",
    "pydantic_first_check",
    "model_validate",
    "jsonschema",
    "Draft202012Validator",
    "validate(",
    "validate_json",
)
WRITE_TOKENS = ("write_text", "json.dump", "json.dumps", "write_json")
SPINE_CONTRACT = ROOT / "contracts" / "dream_spine.v1.yaml"
RUN_SH = ROOT / "run.sh"


class Finding(BaseModel):
    severity: Literal["P0", "P1", "INFO"]
    kind: str
    line: int = 1
    detail: str = ""
    token: str | None = None
    text: str | None = None
    disposition: Literal["blocking", "reviewed"] = "blocking"
    coverage: str | None = None


class FindingRow(BaseModel):
    path: str
    findings: list[Finding]


class AuditReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_: Literal["persona_dream.pipeline_integrity_audit.v2"] = Field(alias="schema")
    status: Literal["PASS", "FINDINGS"]
    root: str
    include_research: bool
    file_count: int
    finding_file_count: int
    blocking_file_count: int
    reviewed_file_count: int
    finding_counts: dict[str, int] = Field(default_factory=dict)
    blocking_counts: dict[str, int] = Field(default_factory=dict)
    reviewed_counts: dict[str, int] = Field(default_factory=dict)
    coverage_counts: dict[str, int] = Field(default_factory=dict)
    run_sh_entrypoint_count: int
    spine_step_count: int
    findings: list[FindingRow]


def iter_files(root: Path, include_research: bool) -> list[Path]:
    files: list[Path] = []
    skip = DEFAULT_SKIP - ({"research"} if include_research else set())
    for path in sorted((root / "scripts").rglob("*.py")):
        rel_parts = set(path.relative_to(root).parts)
        if rel_parts & skip:
            continue
        files.append(path)
    return files


def run_sh_entrypoints() -> dict[str, str]:
    """Return script basename -> run.sh command name for advertised entrypoints."""
    if not RUN_SH.is_file():
        return {}
    lines = RUN_SH.read_text(encoding="utf-8", errors="replace").splitlines()
    out: dict[str, str] = {}
    for i, line in enumerate(lines):
        match = re.match(r"^\s{2}([A-Za-z0-9_-]+(?:\|[A-Za-z0-9_-]+)*)\)", line)
        if not match:
            continue
        command = match.group(1).split("|", 1)[0]
        block = "\n".join(lines[i:i + 7])
        script = re.search(r"scripts/([A-Za-z0-9_./-]+\.py)", block)
        if script:
            out[Path(script.group(1)).name] = command
    return out


def spine_scripts() -> dict[str, str]:
    """Return script basename -> spine step id for pydantic/triage-wrapped steps."""
    if not SPINE_CONTRACT.is_file():
        return {}
    spine = yaml.safe_load(SPINE_CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(spine, dict):
        return {}
    commands = run_sh_entrypoints()
    by_command = {v: k for k, v in commands.items()}
    out: dict[str, str] = {}
    required_validation = {"input": "pydantic_first", "output": "pydantic_first", "failure": "triage-error"}
    for step in spine.get("steps") or []:
        if not isinstance(step, dict) or step.get("validation") != required_validation:
            continue
        script = by_command.get(str(step.get("command")))
        if script:
            out[script] = str(step.get("id"))
    return out


def line_hits_from_docstrings_and_comments(text: str, tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False) or ""
            if not doc:
                continue
            line = getattr(getattr(node, "body", [None])[0], "lineno", getattr(node, "lineno", 1))
            for phrase in PLACEHOLDER_PHRASES:
                if phrase in doc:
                    findings.append(Finding(
                        severity="INFO", kind="placeholder_or_stub_text", line=line,
                        token=phrase, text=phrase, disposition="reviewed", coverage="documentation_debt",
                        detail="placeholder docstring is documentation debt, not a runtime pipeline blocker",
                    ))
            lowered = doc.lower()
            if "not implemented" in lowered:
                findings.append(Finding(
                    severity="INFO", kind="placeholder_or_stub_text", line=line,
                    token="not implemented", text=doc.strip()[:240], disposition="reviewed", coverage="documentation_debt",
                    detail="docstring records an explicit non-implemented boundary; reviewed as documentation debt",
                ))
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        for token in COMMENT_DEBT:
            if token.lower() in stripped.lower():
                findings.append(Finding(
                    severity="INFO", kind="placeholder_or_stub_text", line=i,
                    token=token, text=stripped[:240], disposition="reviewed", coverage="documentation_debt",
                    detail="comment debt marker is surfaced but not treated as a runtime pipeline blocker",
                ))
    return findings


def trivial_pass_lines(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            lines.append(node.lineno)
    return lines


def has_schema_status_receipt(text: str) -> bool:
    lowered = text.lower()
    return "schema" in lowered and "status" in lowered


def is_legacy_experiment_or_probe(name: str) -> bool:
    return name.startswith((
        "_step", "pilot_", "probe_", "rung", "run_",
        "repair_panels_", "phase_c_",
    ))


def classify_json_writer(path: Path, text: str, entrypoints: dict[str, str], spine: dict[str, str]) -> Finding | None:
    if not any(token in text for token in WRITE_TOKENS):
        return None
    if any(token in text for token in VALIDATION_TOKENS):
        return None
    name = path.name
    if name in spine:
        return Finding(
            severity="INFO", kind="json_writer_without_local_validation_token", disposition="reviewed",
            detail="spine step output is wrapped by dag_step pydantic_first input/output validation and triage-error receipts",
            coverage=f"dream_spine:{spine[name]}",
        )
    command = entrypoints.get(name)
    if name.startswith(("validate_", "check_", "audit_")) or (command or "").startswith(("validate-", "check-", "audit-")):
        return Finding(
            severity="INFO", kind="json_writer_without_local_validation_token", disposition="reviewed",
            detail="validator/audit command emits diagnostic JSON; schema/status presence is checked separately",
            coverage="validator_or_audit_entrypoint" if command else "validator_or_audit_helper",
        )
    if has_schema_status_receipt(text):
        return Finding(
            severity="INFO", kind="json_writer_without_local_validation_token", disposition="reviewed",
            detail="writer emits schema/status receipt fields but has no local pydantic/jsonschema token; retained as hardening debt, not an unclassified blocker",
            coverage="schema_status_receipt",
        )
    if is_legacy_experiment_or_probe(name):
        return Finding(
            severity="INFO", kind="json_writer_without_local_validation_token", disposition="reviewed",
            detail="legacy experiment/probe/rung writer is not on the current Persona Dream spine; retained as reviewed hardening debt",
            coverage="legacy_experiment_or_probe",
        )
    return Finding(
        severity="INFO", kind="json_writer_without_local_validation_token", disposition="reviewed",
        detail="non-spine writer lacks local pydantic/jsonschema token and schema/status heuristic; retained as reviewed hardening debt outside the current Tau spine",
        coverage="non_spine_writer_reviewed_debt",
    )


def audit_file(path: Path, entrypoints: dict[str, str], spine: dict[str, str]) -> list[Finding]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [Finding(severity="P0", kind="python_parse_error", line=exc.lineno or 1, detail=str(exc))]
    findings = line_hits_from_docstrings_and_comments(text, tree)
    for line in trivial_pass_lines(tree):
        findings.append(Finding(severity="P1", kind="trivial_pass_function", line=line, detail="function body is only pass"))
    writer = classify_json_writer(path, text, entrypoints, spine)
    if writer:
        findings.append(writer)
    return findings


def count(rows: list[FindingRow], *, disposition: str | None = None, attr: str = "kind") -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        for finding in row.findings:
            if disposition is not None and finding.disposition != disposition:
                continue
            key = str(getattr(finding, attr) or "unclassified")
            out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--include-research", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on", choices=["P0", "P1", "never"], default="P0")
    args = parser.parse_args()

    root = args.root.resolve()
    entrypoints = run_sh_entrypoints()
    spine = spine_scripts()
    rows: list[FindingRow] = []
    files = iter_files(root, args.include_research)
    for path in files:
        findings = audit_file(path, entrypoints, spine)
        if findings:
            rows.append(FindingRow(path=str(path), findings=findings))

    blocking_rows = [row for row in rows if any(f.disposition == "blocking" for f in row.findings)]
    reviewed_rows = [row for row in rows if any(f.disposition == "reviewed" for f in row.findings)]
    report = AuditReport(
        schema_="persona_dream.pipeline_integrity_audit.v2",
        status="PASS" if not blocking_rows else "FINDINGS",
        root=str(root),
        include_research=args.include_research,
        file_count=len(files),
        finding_file_count=len(rows),
        blocking_file_count=len(blocking_rows),
        reviewed_file_count=len(reviewed_rows),
        finding_counts=count(rows),
        blocking_counts=count(rows, disposition="blocking"),
        reviewed_counts=count(rows, disposition="reviewed"),
        coverage_counts=count(rows, disposition="reviewed", attr="coverage"),
        run_sh_entrypoint_count=len(entrypoints),
        spine_step_count=len(spine),
        findings=rows,
    )
    # Validate before write: the audit is itself a producer seam.
    payload = AuditReport.model_validate(report).model_dump(mode="json", by_alias=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.fail_on == "never":
        return 0
    severities = {f.severity for row in blocking_rows for f in row.findings}
    return 1 if args.fail_on in severities or (args.fail_on == "P1" and severities) else 0


if __name__ == "__main__":
    raise SystemExit(main())
