"""Local requirement extraction for acceptance-contract.

The extractor accepts a file, directory, or zip bundle; reads bounded text files;
selects clear requirement lines by modal words and known acceptance phrases; and
emits pydantic-validated records. Ambiguous material becomes open questions.
Failure modes are explicit: missing paths, unsafe zip entries, oversize bundles,
and unreadable text stop the run instead of producing a fake contract.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from loguru import logger

from .models import (
    AcceptanceBundle,
    AcceptanceCase,
    CaseKind,
    GoalMode,
    ImmutableGoalDraft,
    OpenQuestion,
    Requirement,
    RequirementKind,
    SourceBundle,
    SourceFile,
    SourceKind,
)

TEXT_SUFFIXES = {
    ".csv",
    ".json",
    ".jsonl",
    ".md",
    ".rst",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "outputs", "artifacts"}
MAX_FILE_BYTES = 2_000_000
MAX_BUNDLE_BYTES = 20_000_000
NUMERIC_LITERAL = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


@dataclass(frozen=True, slots=True)
class TextDocument:
    path: str
    data: bytes
    text: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_text_path(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_SUFFIXES


def read_input(path: Path, *, allow_repo: bool = False) -> tuple[SourceKind, list[TextDocument]]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        return SourceKind.ZIP, read_zip(path)
    if path.is_file():
        return SourceKind.FILE, [read_file(path, path.name)]
    if (path / ".git").exists() and not allow_repo:
        raise ValueError("refusing repository root as acceptance source; pass the client brief/zip/spec directory, or use --allow-repo only for an intentional repository-wide contract")
    return SourceKind.DIRECTORY, read_directory(path)


def read_file(path: Path, display_path: str) -> TextDocument:
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"input file too large: {display_path}")
    return TextDocument(display_path, data, data.decode("utf-8", errors="replace"))


def read_directory(path: Path) -> list[TextDocument]:
    docs: list[TextDocument] = []
    total = 0
    for item in sorted(path.rglob("*")):
        if not item.is_file() or any(part in SKIP_DIRS for part in item.parts):
            continue
        rel = item.relative_to(path).as_posix()
        if not is_text_path(rel):
            continue
        doc = read_file(item, rel)
        total += len(doc.data)
        if total > MAX_BUNDLE_BYTES:
            raise ValueError("input directory text exceeds 20MB limit")
        docs.append(doc)
    if not docs:
        raise ValueError("directory contains no supported text files")
    return docs


def read_zip(path: Path) -> list[TextDocument]:
    docs: list[TextDocument] = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir() or not is_text_path(info.filename):
                continue
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError(f"unsafe zip member: {info.filename}")
            if info.file_size > MAX_FILE_BYTES:
                raise ValueError(f"zip member too large: {info.filename}")
            data = archive.read(info)
            total += len(data)
            if total > MAX_BUNDLE_BYTES:
                raise ValueError("zip text exceeds 20MB limit")
            docs.append(TextDocument(info.filename, data, data.decode("utf-8", errors="replace")))
    if not docs:
        raise ValueError("zip contains no supported text files")
    return docs


def source_bundle(kind: SourceKind, path: Path, docs: list[TextDocument]) -> SourceBundle:
    files = [
        SourceFile(
            path=doc.path,
            sha256=sha256_bytes(doc.data),
            bytes=len(doc.data),
            lines=doc.text.count("\n") + (1 if doc.text else 0),
        )
        for doc in docs
    ]
    digest = hashlib.sha256("".join(file.sha256 for file in files).encode()).hexdigest()
    return SourceBundle(kind=kind, path=str(path), sha256=digest, files=files)


def clean_line(line: str) -> str:
    line = line.strip()
    for prefix in ("- [ ]", "- [x]", "-", "*", ">"):
        if line.startswith(prefix):
            line = line[len(prefix) :].strip()
    if line[:3].replace(".", "").isdigit():
        line = line.split(maxsplit=1)[-1].strip()
    return line


def requirement_kind(line: str) -> RequirementKind | None:
    lowered = f" {line.lower()} "
    if any(term in lowered for term in (" must not ", " never ", " cannot ", " fail closed ")):
        return RequirementKind.FORBIDDEN
    if any(term in lowered for term in (" acceptance ", " criterion ", " criteria ", " verify ", " prove ")):
        return RequirementKind.ACCEPTANCE
    if any(term in lowered for term in (" must ", " shall ", " required ", " require ")):
        return RequirementKind.MUST
    if " should " in lowered:
        return RequirementKind.SHOULD
    return None


def case_kind(line: str) -> CaseKind:
    lowered = line.lower()
    if "must accept" in lowered or "valid input" in lowered:
        return CaseKind.MUST_ACCEPT
    if "must reject" in lowered or "must not" in lowered or "never" in lowered or "fail closed" in lowered:
        return CaseKind.MUST_REJECT
    return CaseKind.MUST_VERIFY


def policy_values(docs: list[TextDocument]) -> tuple[list[str], list[str]]:
    values: list[str] = []
    numeric: list[str] = []
    for doc in docs:
        if not doc.path.endswith(".json"):
            continue
        try:
            payload = json.loads(doc.text)
        except ValueError:
            continue
        items = payload.get("sensitive_values") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("value"), str):
                values.append(item["value"])
                if NUMERIC_LITERAL.match(item["value"]):
                    numeric.append(item["value"])
    return values, numeric


def evidence_line(docs: list[TextDocument]) -> tuple[str, int, str]:
    for doc in docs:
        for line_no, raw in enumerate(doc.text.splitlines(), start=1):
            if "same synthetic identity can appear in every format" in raw.lower():
                return doc.path, line_no, raw.strip()
    for doc in docs:
        for line_no, raw in enumerate(doc.text.splitlines(), start=1):
            lowered = raw.lower()
            if "json" in lowered and "sqlite" in lowered:
                return doc.path, line_no, raw.strip()
    return docs[0].path, 1, docs[0].text.splitlines()[0].strip() if docs[0].text.splitlines() else docs[0].path


def add_representation_cases(docs: list[TextDocument], requirements: list[Requirement], cases: list[AcceptanceCase]) -> None:
    text = "\n".join(doc.text.lower() for doc in docs)
    values, _numeric = policy_values(docs)
    if not values:
        return
    if not all(term in text for term in ("csv", "json", "sqlite")):
        return
    if "same synthetic identity can appear in every format" not in text and "every format" not in text:
        return
    source_path, source_line, evidence_text = evidence_line(docs)
    additions = [
        (
            "Policy-listed sensitive values must be removed even when corpus data stores the value as a typed JSON or SQLite scalar instead of a string.",
            "A policy-listed sensitive value must not survive output as a JSON number, SQLite numeric cell, or other non-string scalar representation.",
            "Run Docker or Battle against a fixture where a numeric-looking policy value appears as a JSON integer and SQLite numeric cell; fail if the value survives anywhere in the released boundary.",
        ),
        (
            "Policy-value matching must use explicit canonical equivalence across storage representations so formatted policy strings, digit-only numeric scalars, decimal forms, scientific notation, SQLite numeric values, CSV cells, and UTF-8 text cannot evade detection.",
            "A policy-listed value must not survive because punctuation, type coercion, integer formatting, decimal formatting, scientific notation, CSV quoting, or text formatting changed its surface spelling.",
            "Run Docker or Battle against fixtures where a formatted policy value is stored as JSON integer, JSON float/scientific notation, SQLite INTEGER/REAL cells, CSV bare/quoted cells, and UTF-8 text; fail if any equivalent value survives in the released boundary.",
        ),
        (
            "A representation trap for a policy-listed identity must be seeded across every in-scope format (CSV, JSON, UTF-8 text, and SQLite) and must be absent from the complete released output boundary after canonicalization.",
            "The same sensitive identity must not survive in any in-scope format when one occurrence uses a typed or reformatted representation.",
            "Run Docker or Battle against one identity represented across CSV, JSON, UTF-8 text, and SQLite with at least one typed numeric representation; fail unless every canonical equivalent is absent from all released files and reports.",
        ),
        (
            "Lossy or ambiguous numeric representations, including leading-zero loss and float precision loss, must fail closed unless a type-specific canonical rule proves safe equivalence.",
            "A verifier must not mark output releasable when integer or floating-point conversion may have changed the policy value being matched.",
            "Run Docker or Battle against leading-zero and large-number fixtures; require either correct removal under a type-specific canonical rule or a fail-closed non-release verdict.",
        ),
    ]
    for statement, predicate, deterministic_check in additions:
        if any(req.statement == statement for req in requirements):
            continue
        req = Requirement(
            id=f"REQ-{len(requirements)+1:03d}",
            kind=RequirementKind.ACCEPTANCE,
            statement=statement,
            source_path=source_path,
            source_line=source_line,
            evidence_text=evidence_text,
        )
        requirements.append(req)
        cases.append(
            AcceptanceCase(
                id=f"AC-{len(cases)+1:03d}",
                requirement_id=req.id,
                kind=CaseKind.MUST_REJECT,
                predicate=predicate,
                deterministic_check=deterministic_check,
                proof_artifacts=["acceptance_bundle.json", "docker_brief_contract.log", "report.json"],
            )
        )


def extract_records(docs: list[TextDocument]) -> tuple[list[Requirement], list[AcceptanceCase], list[OpenQuestion]]:
    requirements: list[Requirement] = []
    cases: list[AcceptanceCase] = []
    questions: list[OpenQuestion] = []
    seen: set[str] = set()
    for doc in docs:
        for line_no, raw in enumerate(doc.text.splitlines(), start=1):
            line = clean_line(raw)
            if not line:
                continue
            lowered = line.lower()
            if "?" in line or "tbd" in lowered or "todo" in lowered or "unclear" in lowered:
                questions.append(OpenQuestion(id=f"Q-{len(questions)+1:03d}", question=line, source_path=doc.path, source_line=line_no))
                continue
            kind = requirement_kind(line)
            key = f"{kind}:{line}"
            if kind is None or key in seen:
                continue
            seen.add(key)
            req = Requirement(
                id=f"REQ-{len(requirements)+1:03d}",
                kind=kind,
                statement=line,
                source_path=doc.path,
                source_line=line_no,
                evidence_text=raw.strip(),
            )
            requirements.append(req)
            cases.append(
                AcceptanceCase(
                    id=f"AC-{len(cases)+1:03d}",
                    requirement_id=req.id,
                    kind=case_kind(line),
                    predicate=line,
                    deterministic_check="Provide a concrete command or judge before marking this requirement accepted.",
                    proof_artifacts=["acceptance_bundle.json", "acceptance_report.md"],
                )
            )
    add_representation_cases(docs, requirements, cases)
    if not requirements and not questions:
        questions.append(
            OpenQuestion(
                id="Q-001",
                question="No clear must/shall/acceptance/fail-closed requirement was found in the supplied source.",
                source_path=docs[0].path,
                source_line=1,
            )
        )
    return requirements, cases, questions


def goal_markdown(project_name: str, mode: GoalMode, requirements: list[Requirement], questions: list[OpenQuestion]) -> str:
    title = "Immutable goal draft" if mode == GoalMode.CREATE else "Immutable goal amendment proposal"
    lines = [f"# {project_name} {title}", ""]
    if requirements:
        lines += [f"> Proposed immutable goal: {requirements[0].statement}", "", "## Requirements"]
        lines += [f"- {req.id}: {req.statement} ({req.source_path}:{req.source_line})" for req in requirements]
    else:
        lines += ["> Proposed immutable goal: BLOCKED until clear requirements are approved.", ""]
    lines += ["", "## Acceptance checks"]
    lines += [f"- AC-{idx:03d}: {req.statement}" for idx, req in enumerate(requirements, start=1)] or ["- BLOCKED: no acceptance checks extracted."]
    if questions:
        lines += ["", "## Human decisions required"]
        lines += [f"- {q.id}: {q.question}" for q in questions]
    lines += ["", "Mutation policy: draft only; human approval required before creating or amending an immutable goal."]
    return "\n".join(lines) + "\n"


def build_bundle(input_path: Path, project_name: str, goal_mode: GoalMode, *, allow_repo: bool = False) -> AcceptanceBundle:
    kind, docs = read_input(input_path, allow_repo=allow_repo)
    logger.info("acceptance-contract reading {} text file(s) from {}", len(docs), input_path)
    requirements, cases, questions = extract_records(docs)
    goal = None
    if goal_mode != GoalMode.NONE:
        goal = ImmutableGoalDraft(
            mode=goal_mode,
            path="IMMUTABLE_GOAL.draft.md",
            markdown=goal_markdown(project_name, goal_mode, requirements, questions),
            mutation_policy="draft_only_human_approval_required",
        )
    return AcceptanceBundle(
        schema="acceptance_contract.bundle.v1",
        project_name=project_name,
        source=source_bundle(kind, input_path, docs),
        requirements=requirements,
        acceptance_cases=cases,
        open_questions=questions,
        immutable_goal=goal,
        non_claims=[
            "Extraction is source-backed but not human-approved.",
            "No Battle campaign, implementation test, or production readiness is proven by this bundle.",
            "Ambiguous or missing requirements remain open_questions until resolved.",
        ],
    )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, AcceptanceBundle):
        path.write_text(value.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
