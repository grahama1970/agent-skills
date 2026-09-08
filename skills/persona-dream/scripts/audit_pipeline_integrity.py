#!/usr/bin/env python3
"""Audit Persona Dream pipeline files for fake seams and missing validation."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKIP = {"__pycache__", "generated_models", "research", "reports", "tests", "fixtures", "local"}
PLACEHOLDERS = (
    "Auto-generated module docstring. Review for accuracy",
    "Purpose: Auto-generated module docstring",
    "TODO",
    "FIXME",
    "not implemented",
    "stub",
)
VALIDATION_TOKENS = (
    "BaseModel",
    "pydantic_first_check",
    "model_validate",
    "jsonschema",
    "Draft202012Validator",
    "validate(",
)
WRITE_TOKENS = ("write_text", "json.dump", "json.dumps", "write_json")


def iter_files(root: Path, include_research: bool) -> list[Path]:
    files: list[Path] = []
    for path in sorted((root / "scripts").rglob("*.py")):
        rel_parts = set(path.relative_to(root).parts)
        skip = DEFAULT_SKIP - ({"research"} if include_research else set())
        if rel_parts & skip:
            continue
        files.append(path)
    return files


def line_hits(text: str, needles: tuple[str, ...]) -> list[dict[str, Any]]:
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        lower = line.lower()
        for needle in needles:
            if needle.lower() in lower:
                hits.append({"line": i, "token": needle, "text": line.strip()[:240]})
    return hits


def has_trivial_pass(tree: ast.AST) -> list[int]:
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            lines.append(node.lineno)
    return lines


def audit_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[dict[str, Any]] = []
    for hit in line_hits(text, PLACEHOLDERS):
        findings.append({"severity": "P1", "kind": "placeholder_or_stub_text", **hit})
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [{"severity": "P0", "kind": "python_parse_error", "line": exc.lineno, "detail": str(exc)}]
    for line in has_trivial_pass(tree):
        findings.append({"severity": "P1", "kind": "trivial_pass_function", "line": line})
    writes_json = any(token in text for token in WRITE_TOKENS)
    validates = any(token in text for token in VALIDATION_TOKENS)
    if writes_json and not validates:
        findings.append({
            "severity": "P1",
            "kind": "json_writer_without_local_validation_token",
            "line": 1,
            "detail": "File writes JSON/text artifacts but has no local pydantic/jsonschema validation token; inspect producer seam.",
        })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--include-research", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on", choices=["P0", "P1", "never"], default="P0")
    args = parser.parse_args()

    rows = []
    for path in iter_files(args.root.resolve(), args.include_research):
        findings = audit_file(path)
        if findings:
            rows.append({"path": str(path), "findings": findings})
    counts: dict[str, int] = {}
    for row in rows:
        for finding in row["findings"]:
            counts[finding["kind"]] = counts.get(finding["kind"], 0) + 1
    report = {
        "schema": "persona_dream.pipeline_integrity_audit.v1",
        "status": "PASS" if not rows else "FINDINGS",
        "root": str(args.root.resolve()),
        "include_research": args.include_research,
        "file_count": len(iter_files(args.root.resolve(), args.include_research)),
        "finding_file_count": len(rows),
        "finding_counts": counts,
        "findings": rows,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on == "never":
        return 0
    severities = {f["severity"] for row in rows for f in row["findings"]}
    return 1 if args.fail_on in severities or (args.fail_on == "P1" and severities) else 0


if __name__ == "__main__":
    raise SystemExit(main())
