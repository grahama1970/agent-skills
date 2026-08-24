"""Audit agent instruction files for parity, required clauses, and receipts.

Inputs are markdown instruction files. Outputs are JSON or text reports naming
file existence, hashes, line counts, required-clause coverage, identical-content
status, and the proof boundary. Failure modes are explicit: missing files,
missing required clauses, and mismatched files make readiness NOT_READY.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)


@dataclass(frozen=True, slots=True)
class RequiredClause:
    clause_id: str
    description: str
    needles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FileAudit:
    label: str
    path: str
    exists: bool
    line_count: int | None
    sha256: str | None
    missing_clauses: list[str] = field(default_factory=list)


DEFAULT_PATHS = (
    "codex=/home/graham/.codex/AGENTS.md",
    "claude=/home/graham/.claude/CLAUDE.md",
)

REQUIRED_CLAUSES = (
    RequiredClause(
        "memory_recall",
        "uses $memory recall as the durable recall path",
        ("$memory recall --brief", "items[]", "skill_chain"),
    ),
    RequiredClause(
        "optimized_skill_chain",
        "treats memory skill chains as suggestions and reads current SKILL.md",
        ("skill_chain.skills", "SKILL.md", "current file overrides memory"),
    ),
    RequiredClause(
        "agentic_evals_gate",
        "requires agentic evals for new feature and skill behavior claims",
        ("/agentic-evals", "fixtures/agentic_eval.json", "new feature"),
    ),
    RequiredClause(
        "unit_test_boundary",
        "states that unit tests do not prove a feature works",
        ("Unit tests do not determine", "feature-working claim"),
    ),
    RequiredClause(
        "proof_boundary",
        "requires mocked/live proof-boundary reporting",
        ("Proof Boundary", "mocked: yes|no", "live: yes|no"),
    ),
    RequiredClause(
        "operational_state_first",
        "leads reports with concrete operational state",
        ("Status/Phase", "operational state", "exists, works"),
    ),
    RequiredClause(
        "no_commit_hiding",
        "does not let commits, branches, pushes, or SHAs hide failures",
        ("Do not hide failure", "committed", "pushed", "SHAs"),
    ),
    RequiredClause(
        "alpha_main_branch",
        "requires alpha+ work on the primary checkout main branch",
        ("alpha+", "primary checkout", "`main` branch"),
    ),
    RequiredClause(
        "blocker_plain_language",
        "requires exact blocker and next needed input or command",
        ("exact blocker", "next needed input", "what evidence is missing"),
    ),
)


def parse_path_specs(specs: list[str]) -> dict[str, Path]:
    """Parse label=path arguments into expanded Paths."""
    parsed: dict[str, Path] = {}
    for spec in specs:
        if "=" not in spec:
            raise typer.BadParameter(f"path spec must be label=/path, got {spec!r}")
        label, raw_path = spec.split("=", 1)
        label = label.strip()
        if not label:
            raise typer.BadParameter(f"path spec has empty label: {spec!r}")
        parsed[label] = Path(raw_path).expanduser()
    return parsed


def sha256_text(text: str) -> str:
    """Return a stable sha256 digest for text content."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def audit_one(label: str, path: Path) -> tuple[FileAudit, str | None]:
    """Audit one instruction file and return its report plus content."""
    if not path.is_file():
        return FileAudit(label=label, path=str(path), exists=False, line_count=None, sha256=None), None
    text = path.read_text(encoding="utf-8", errors="replace")
    missing = [
        clause.clause_id
        for clause in REQUIRED_CLAUSES
        if not all(needle in text for needle in clause.needles)
    ]
    return (
        FileAudit(
            label=label,
            path=str(path),
            exists=True,
            line_count=len(text.splitlines()),
            sha256=sha256_text(text),
            missing_clauses=missing,
        ),
        text,
    )


def build_report(paths: dict[str, Path], require_identical: bool) -> dict[str, object]:
    """Build the machine-readable audit report."""
    file_reports: list[FileAudit] = []
    contents: dict[str, str] = {}
    for label, path in paths.items():
        file_report, text = audit_one(label, path)
        file_reports.append(file_report)
        if text is not None:
            contents[label] = text

    existing_hashes = {report.sha256 for report in file_reports if report.sha256}
    all_exist = all(report.exists for report in file_reports)
    no_missing_clauses = all(not report.missing_clauses for report in file_reports)
    identical = len(existing_hashes) <= 1 and all_exist
    ready = all_exist and no_missing_clauses and (identical or not require_identical)
    missing_by_file = {
        report.label: report.missing_clauses for report in file_reports if report.missing_clauses
    }
    return {
        "schema": "ops_agent_instructions.audit.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "readiness": "READY" if ready else "NOT_READY",
        "require_identical": require_identical,
        "identical": identical,
        "required_clauses": [asdict(clause) for clause in REQUIRED_CLAUSES],
        "files": [asdict(report) for report in file_reports],
        "missing_by_file": missing_by_file,
        "proof_boundary": {
            "mocked": False,
            "live": True,
            "exercised": "read back current instruction files from disk and checked required clauses",
            "unverified": "future agent obedience and provider-specific runtime behavior",
        },
    }


def emit_report(report: dict[str, object], json_output: bool, output: Path | None) -> None:
    """Write the report to stdout and optionally to a receipt path."""
    text = json.dumps(report, indent=2, sort_keys=True)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    if json_output:
        typer.echo(text)
        return
    typer.echo(f"readiness: {report['readiness']}")
    typer.echo(f"identical: {report['identical']}")
    for file_report in report["files"]:
        typer.echo(
            f"{file_report['label']}: exists={file_report['exists']} "
            f"lines={file_report['line_count']} missing={file_report['missing_clauses']}"
        )


@app.command()
def audit(
    paths: Annotated[
        list[str],
        typer.Option("--path", help="Instruction file as label=/absolute/path."),
    ] = list(DEFAULT_PATHS),
    require_identical: Annotated[
        bool,
        typer.Option("--require-identical/--allow-provider-deltas"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Audit instruction files and exit non-zero unless readiness is READY."""
    report = build_report(parse_path_specs(paths), require_identical=require_identical)
    emit_report(report, json_output=json_output, output=output)
    if report["readiness"] != "READY":
        raise typer.Exit(code=1)


def good_instruction_text() -> str:
    """Return a minimal instruction file that satisfies every required clause."""
    return "\n".join(
        [
            "# Global Agent Instructions",
            "Use $memory recall --brief and read found, items[], and skill_chain.",
            "Use skill_chain.skills as guidance, then read SKILL.md.",
            "The current file overrides memory when they disagree.",
            "Every new feature must update fixtures/agentic_eval.json and run /agentic-evals.",
            "Unit tests do not determine that a feature works; require a feature-working claim.",
            "Status/Phase reports operational state: what exists, works, or remains broken.",
            "Proof Boundary reports mocked: yes|no and live: yes|no.",
            "Do not hide failure behind committed, pushed, branch names, or SHAs.",
            "For alpha+ work, use the primary checkout on the `main` branch.",
            "If blocked, name the exact blocker, next needed input, and what evidence is missing.",
            "",
        ]
    )


def run_self_case(case: str) -> dict[str, object]:
    """Run deterministic positive and negative controls against temp files."""
    with tempfile.TemporaryDirectory(prefix="ops-agent-instructions-") as raw_tmp:
        tmp = Path(raw_tmp)
        good_a = tmp / "AGENTS.md"
        good_b = tmp / "CLAUDE.md"
        good_a.write_text(good_instruction_text(), encoding="utf-8")
        good_b.write_text(good_instruction_text(), encoding="utf-8")

        if case == "positive":
            report = build_report({"agents": good_a, "claude": good_b}, require_identical=True)
            if report["readiness"] != "READY" or report["identical"] is not True:
                raise RuntimeError("positive control did not reach READY")
            return {"case": case, "readiness": report["readiness"], "identical": report["identical"]}

        if case == "missing-clause":
            bad = tmp / "BAD.md"
            bad.write_text(good_instruction_text().replace("Proof Boundary", "Boundary"), encoding="utf-8")
            report = build_report({"agents": bad, "claude": good_b}, require_identical=False)
            missing = report["missing_by_file"].get("agents", [])
            if report["readiness"] == "READY" or "proof_boundary" not in missing:
                raise RuntimeError("missing-clause control did not detect proof_boundary")
            return {"case": case, "readiness": report["readiness"], "missing": missing}

        if case == "mismatch":
            good_b.write_text(good_instruction_text() + "Provider delta.\n", encoding="utf-8")
            report = build_report({"agents": good_a, "claude": good_b}, require_identical=True)
            if report["readiness"] == "READY" or report["identical"] is not False:
                raise RuntimeError("mismatch control did not detect non-identical files")
            return {"case": case, "readiness": report["readiness"], "identical": report["identical"]}

    raise typer.BadParameter(f"unknown self-test case {case!r}")


@app.command("self-test")
def self_test(
    case: Annotated[str, typer.Option("--case", help="positive, missing-clause, mismatch, or all")] = "all",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run skill-local positive, negative, and adversarial controls."""
    selected = ["positive", "missing-clause", "mismatch"] if case == "all" else [case]
    results = [run_self_case(name) for name in selected]
    report = {
        "schema": "ops_agent_instructions.self_test.v1",
        "readiness": "READY",
        "case_count": len(results),
        "results": results,
    }
    if json_output:
        typer.echo(json.dumps(report, indent=2, sort_keys=True))
    else:
        for result in results:
            typer.echo(f"{result['case']}: {result['readiness']}")


if __name__ == "__main__":
    try:
        app()
    except Exception as exc:
        logger.error("ops-agent-instructions failed: {}", exc)
        raise
