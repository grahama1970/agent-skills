#!/usr/bin/env python3
"""Proposal-first docstring remediation for monitor-codebase.

This module scans Python source for missing docstrings, emits hash-bound JSONL
candidate records, and applies only reviewed candidates to a bounded target.

Inputs:
- A Python file or project directory.
- Optional `.monitor-codebase.json` scan scoping.
- A JSONL candidate file for the apply phase.

Outputs:
- Read-only proposal JSONL and summary receipts.
- Apply receipts with accepted, rejected, and rolled-back candidate outcomes.

Failure modes:
- Missing or stale source hashes reject a candidate.
- Unsupported claims, parameter mismatches, return/yield/raise mismatches, compile
  errors, or AST changes reject and roll back an attempted patch.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

import typer

SCHEMA_CANDIDATE = "monitor_codebase.docstring_candidate.v1"
SCHEMA_SUMMARY = "monitor_codebase.docstring_candidates_summary.v1"
SCHEMA_APPLY = "monitor_codebase.docstring_apply_receipt.v1"

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_EXCLUDES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".uv",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
}
BANNED_CLAIM_PATTERN = re.compile(
    r"\b(atomic(?:ally)?|thread[- ]safe|secure|safe(?:ly)?|idempotent|complete|comprehensive|"
    r"guarantee[sd]?|always|never|fast|performant|constant[- ]time)\b",
    re.IGNORECASE,
)


class Need(StrEnum):
    """Closed vocabulary for documentation need policy results."""

    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"
    EXEMPT = "exempt"


class SymbolKind(StrEnum):
    """Closed vocabulary for supported docstring targets."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"


@dataclass(frozen=True, slots=True)
class SymbolEvidence:
    """Evidence extracted from a Python symbol before proposal generation."""

    project_root: str
    path: str
    symbol_kind: str
    qualified_name: str
    start_line: int
    end_line: int
    body_start_line: int
    source_sha256: str
    source_range_sha256: str
    signature: str
    decorators: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    returns_value: bool = False
    yields_value: bool = False
    raises: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    external_systems: list[str] = field(default_factory=list)
    mutation_indicators: list[str] = field(default_factory=list)
    complexity_score: int = 0


def utc_now() -> str:
    """Return an RFC3339 UTC timestamp for receipts."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    """Return a stable SHA-256 digest for text."""
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    """Return stable JSON text for candidate identity."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from a file, returning an empty object for absence."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_text(path: Path) -> str:
    """Read source text with explicit UTF-8 handling."""
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    """Write an indented JSON receipt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    """Yield JSON objects from a JSONL file."""
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_no}: expected JSON object")
        yield payload


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    """Write JSONL rows with stable key order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")


def is_generated_file(path: Path, text: str) -> bool:
    """Return whether a file should be treated as generated output."""
    lowered_path = path.as_posix().lower()
    head = "\n".join(text.splitlines()[:20]).lower()
    return "generated" in lowered_path or "auto-generated" in head or "generated by" in head


def is_test_path(path: Path) -> bool:
    """Return whether a path belongs to tests."""
    parts = {part.lower() for part in path.parts}
    return "tests" in parts or path.name.startswith("test_")


def scoped_targets(project_path: Path, scoped: bool) -> list[Path]:
    """Return scan roots, respecting `.monitor-codebase.json` when requested."""
    if not scoped or not project_path.is_dir():
        return [project_path]
    config = load_json(project_path / ".monitor-codebase.json")
    include_dirs = config.get("include_dirs")
    if not isinstance(include_dirs, list):
        return [project_path]
    targets = [project_path / str(item) for item in include_dirs]
    return [target for target in targets if target.exists()] or [project_path]


def should_skip(path: Path) -> bool:
    """Return whether a path is excluded from docstring scanning."""
    return bool(set(path.parts) & DEFAULT_EXCLUDES) or any(part.startswith(".venv") for part in path.parts)


def iter_python_files(target: Path, scoped: bool = False) -> list[Path]:
    """Return Python files below the scan target."""
    if target.is_file():
        return [target] if target.suffix == ".py" and not should_skip(target) else []
    files: list[Path] = []
    for root in scoped_targets(target, scoped):
        files.extend(path for path in root.rglob("*.py") if path.is_file() and not should_skip(path))
    return sorted(set(files))


def source_segment(lines: list[str], start_line: int, end_line: int) -> str:
    """Return a 1-based inclusive line slice."""
    return "".join(lines[start_line - 1 : end_line])


def normalize_ast_without_docstrings(text: str) -> str:
    """Return an AST dump with module/class/function docstrings removed."""
    tree = ast.parse(text)

    class StripDocstrings(ast.NodeTransformer):
        def visit_Module(self, node: ast.Module) -> ast.AST:
            self.generic_visit(node)
            node.body = strip_first_docstring(node.body)
            return node

        def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
            self.generic_visit(node)
            node.body = strip_first_docstring(node.body)
            return node

        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            self.generic_visit(node)
            node.body = strip_first_docstring(node.body)
            return node

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
            self.generic_visit(node)
            node.body = strip_first_docstring(node.body)
            return node

    stripped = StripDocstrings().visit(tree)
    ast.fix_missing_locations(stripped)
    return ast.dump(stripped, include_attributes=False)


def strip_first_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """Drop the first docstring statement from an AST body."""
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            return body[1:]
    return body


def node_docstring(node: ast.AST) -> str:
    """Return the raw docstring for supported AST nodes."""
    try:
        return ast.get_docstring(node, clean=False) or ""
    except TypeError:
        return ""


def node_kind(node: ast.AST) -> SymbolKind:
    """Return the supported symbol kind for an AST node."""
    if isinstance(node, ast.ClassDef):
        return SymbolKind.CLASS
    if isinstance(node, ast.AsyncFunctionDef):
        return SymbolKind.ASYNC_FUNCTION
    if isinstance(node, ast.FunctionDef):
        return SymbolKind.FUNCTION
    return SymbolKind.MODULE


def is_overload(node: ast.AST) -> bool:
    """Return whether a function is a typing overload declaration."""
    decorators = getattr(node, "decorator_list", [])
    return any(ast.unparse(decorator).endswith("overload") for decorator in decorators)


def collect_names(nodes: Iterable[ast.AST]) -> list[str]:
    """Return sorted AST-unparsed names for call and decorator evidence."""
    names = []
    for node in nodes:
        try:
            names.append(ast.unparse(node))
        except Exception:
            continue
    return sorted(set(names))


def function_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Return function parameter names."""
    args = node.args
    params = [arg.arg for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]]
    if args.vararg:
        params.append(args.vararg.arg)
    if args.kwarg:
        params.append(args.kwarg.arg)
    return [param for param in params if param not in {"self", "cls"}]


def symbol_complexity(node: ast.AST) -> int:
    """Return a conservative complexity score for documentation policy."""
    scored_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.With,
        ast.AsyncWith,
        ast.Match,
        ast.BoolOp,
        ast.comprehension,
    )
    return sum(1 for child in ast.walk(node) if isinstance(child, scored_nodes))


def evidence_for_node(project_root: Path, path: Path, node: ast.AST, lines: list[str], qualified_name: str) -> SymbolEvidence:
    """Build bounded symbol evidence from AST and source text."""
    start_line = int(getattr(node, "lineno", 1))
    end_line = int(getattr(node, "end_lineno", start_line))
    body = getattr(node, "body", [])
    body_start = int(getattr(body[0], "lineno", end_line)) if body else end_line
    text = source_segment(lines, start_line, end_line)
    kind = node_kind(node)
    params: list[str] = []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        params = function_parameters(node)
    calls = collect_names(child.func for child in ast.walk(node) if isinstance(child, ast.Call))
    raises = collect_names(child.exc for child in ast.walk(node) if isinstance(child, ast.Raise) and child.exc)
    external = sorted(
        {
            value
            for value in calls
            if any(marker in value for marker in ("open", "Path.", "httpx.", "subprocess.", "socket.", "requests."))
        }
    )
    mutations = sorted(
        {
            type(child).__name__
            for child in ast.walk(node)
            if isinstance(child, (ast.Assign, ast.AugAssign, ast.Delete, ast.AnnAssign))
        }
    )
    signature = lines[start_line - 1].strip() if kind != SymbolKind.MODULE else path.name
    decorators = collect_names(getattr(node, "decorator_list", []))
    return SymbolEvidence(
        project_root=str(project_root),
        path=str(path.relative_to(project_root)),
        symbol_kind=kind.value,
        qualified_name=qualified_name,
        start_line=start_line,
        end_line=end_line,
        body_start_line=body_start,
        source_sha256=sha256_text(read_text(path)),
        source_range_sha256=sha256_text(text),
        signature=signature,
        decorators=decorators,
        parameters=params,
        returns_value=any(isinstance(child, ast.Return) and child.value is not None for child in ast.walk(node)),
        yields_value=any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node)),
        raises=raises,
        calls=calls[:40],
        external_systems=external,
        mutation_indicators=mutations,
        complexity_score=symbol_complexity(node),
    )


def policy_for(path: Path, node: ast.AST, evidence: SymbolEvidence, generated: bool) -> tuple[Need, list[str]]:
    """Return the documentation need and reason codes for one symbol."""
    name = evidence.qualified_name.rsplit(".", 1)[-1]
    if generated:
        return Need.EXEMPT, ["generated_file"]
    if evidence.symbol_kind == SymbolKind.MODULE:
        return Need.REQUIRED, ["module"]
    if is_overload(node):
        return Need.EXEMPT, ["overload_declaration"]
    if is_test_path(path) or name.startswith("test_"):
        return Need.OPTIONAL, ["test_symbol"]
    if evidence.symbol_kind == SymbolKind.CLASS:
        return (Need.REQUIRED, ["public_class"]) if not name.startswith("_") else (Need.RECOMMENDED, ["private_class"])
    if not name.startswith("_"):
        reasons = ["public_api"]
        if evidence.external_systems:
            reasons.append("external_io")
        if evidence.raises:
            reasons.append("explicit_failure")
        return Need.REQUIRED, reasons
    if evidence.complexity_score >= 2 or evidence.external_systems or evidence.raises:
        return Need.RECOMMENDED, ["complex_private_logic"]
    return Need.OPTIONAL, ["trivial_private_helper"]


def proposal_contract(evidence: SymbolEvidence) -> dict[str, Any]:
    """Build a structured contract from static evidence only."""
    return {
        "purpose": "",
        "inputs": evidence.parameters,
        "returns": {"returns_value": evidence.returns_value},
        "yields": {"yields_value": evidence.yields_value},
        "raises": evidence.raises,
        "side_effects": evidence.mutation_indicators,
        "external_systems": evidence.external_systems,
        "unsupported_claims": ["requires_human_or_model_review"],
    }


def candidate_id(evidence: SymbolEvidence, policy: Need, reasons: list[str]) -> str:
    """Build a stable candidate id from bound source and symbol fields."""
    payload = {
        "path": evidence.path,
        "kind": evidence.symbol_kind,
        "qualified_name": evidence.qualified_name,
        "start_line": evidence.start_line,
        "source_sha256": evidence.source_sha256,
        "policy": policy.value,
        "reasons": reasons,
    }
    return "doc_" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:24]


def scan_file(project_root: Path, path: Path, include_optional: bool) -> list[dict[str, Any]]:
    """Return read-only docstring candidate records for one Python file."""
    text = read_text(path)
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    generated = is_generated_file(path, text)
    candidates: list[dict[str, Any]] = []

    def add_candidate(node: ast.AST, qualified_name: str) -> None:
        if node_docstring(node):
            return
        evidence = evidence_for_node(project_root, path, node, lines, qualified_name)
        need, reasons = policy_for(path, node, evidence, generated)
        if need in {Need.OPTIONAL, Need.EXEMPT} and not include_optional:
            return
        candidate = {
            "schema": SCHEMA_CANDIDATE,
            "candidate_id": candidate_id(evidence, need, reasons),
            "created_at": utc_now(),
            "status": "needs_review" if need != Need.EXEMPT else "exempt",
            "documentation_need": need.value,
            "documentation_need_reasons": reasons,
            "symbol": asdict(evidence),
            "contract": proposal_contract(evidence),
            "proposed_docstring": "",
            "approval": {"status": "unreviewed"},
        }
        candidates.append(candidate)

    add_candidate(tree, "<module>")

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _qualified(self, name: str) -> str:
            return ".".join([*self.stack, name]) if self.stack else name

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            qualified = self._qualified(node.name)
            add_candidate(node, qualified)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            qualified = self._qualified(node.name)
            add_candidate(node, qualified)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            qualified = self._qualified(node.name)
            add_candidate(node, qualified)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    Visitor().visit(tree)
    return candidates


def propose(target: Path, output: Path, scoped: bool = False, include_optional: bool = False) -> dict[str, Any]:
    """Scan target and write read-only docstring candidates."""
    root = target.resolve() if target.is_dir() else target.resolve().parent
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in iter_python_files(target.resolve(), scoped=scoped):
        try:
            candidates.extend(scan_file(root, path.resolve(), include_optional))
        except (OSError, SyntaxError, ValueError) as exc:
            errors.append({"path": str(path), "error": str(exc)})
    write_jsonl(output, candidates)
    by_need: dict[str, int] = {}
    for candidate in candidates:
        need = str(candidate.get("documentation_need", "unknown"))
        by_need[need] = by_need.get(need, 0) + 1
    summary = {
        "schema": SCHEMA_SUMMARY,
        "status": "pass" if not errors else "warn",
        "target": str(target.resolve()),
        "output": str(output.resolve()),
        "generated_at": utc_now(),
        "candidate_count": len(candidates),
        "by_documentation_need": by_need,
        "errors": errors,
        "mutated_source": False,
    }
    write_json(output.with_suffix(output.suffix + ".summary.json"), summary)
    return summary


def approval_status(candidate: dict[str, Any]) -> str:
    """Return normalized review approval state for a candidate."""
    approval = candidate.get("approval")
    if isinstance(approval, dict):
        return str(approval.get("status", "")).lower()
    if candidate.get("approved") is True:
        return "approved"
    return str(candidate.get("review_status", "")).lower()


def find_node(tree: ast.Module, candidate: dict[str, Any]) -> ast.AST | None:
    """Find the AST node addressed by a candidate."""
    symbol = candidate.get("symbol") if isinstance(candidate.get("symbol"), dict) else {}
    target_kind = str(symbol.get("symbol_kind") or "")
    target_name = str(symbol.get("qualified_name") or "")
    target_line = int(symbol.get("start_line") or 0)
    if target_kind == SymbolKind.MODULE.value and target_name == "<module>":
        return tree

    class Finder(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []
            self.match: ast.AST | None = None

        def _qualified(self, name: str) -> str:
            return ".".join([*self.stack, name]) if self.stack else name

        def _check(self, node: ast.AST, name: str) -> None:
            kind = node_kind(node).value
            if kind == target_kind and self._qualified(name) == target_name and getattr(node, "lineno", 0) == target_line:
                self.match = node

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._check(node, node.name)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._check(node, node.name)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._check(node, node.name)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    finder = Finder()
    finder.visit(tree)
    return finder.match


def validate_contract(candidate: dict[str, Any], node: ast.AST) -> list[str]:
    """Return validation errors for a reviewed candidate contract."""
    errors: list[str] = []
    docstring = str(candidate.get("proposed_docstring") or "").strip()
    if not docstring:
        errors.append("missing_proposed_docstring")
    if BANNED_CLAIM_PATTERN.search(docstring):
        errors.append("unsupported_claim_in_docstring")
    contract = candidate.get("contract") if isinstance(candidate.get("contract"), dict) else {}
    if contract.get("unsupported_claims"):
        errors.append("contract_has_unsupported_claims")
    expected_inputs = contract.get("inputs") if isinstance(contract.get("inputs"), list) else []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        actual_inputs = set(function_parameters(node))
        missing = [str(item) for item in expected_inputs if str(item) not in actual_inputs]
        if missing:
            errors.append("documented_parameter_missing:" + ",".join(missing))
    returns = contract.get("returns") if isinstance(contract.get("returns"), dict) else {}
    if returns.get("returns_value") is True:
        has_return = any(isinstance(child, ast.Return) and child.value is not None for child in ast.walk(node))
        if not has_return:
            errors.append("return_claim_without_return")
    yields = contract.get("yields") if isinstance(contract.get("yields"), dict) else {}
    if yields.get("yields_value") is True:
        has_yield = any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node))
        if not has_yield:
            errors.append("yield_claim_without_yield")
    raises = contract.get("raises") if isinstance(contract.get("raises"), list) else []
    if raises:
        has_raise = any(isinstance(child, ast.Raise) for child in ast.walk(node))
        if not has_raise:
            errors.append("raise_claim_without_raise")
    return errors


def docstring_line(docstring: str, indent: str) -> str:
    """Render a one-line Python docstring."""
    escaped = docstring.replace('"""', '\\"\\"\\"').strip()
    if not escaped.endswith("."):
        escaped += "."
    return f'{indent}"""{escaped}"""\n'


def insertion_index(node: ast.AST, lines: list[str]) -> tuple[int, str]:
    """Return zero-based insertion index and indentation from AST body metadata."""
    if isinstance(node, ast.Module):
        insert_at = 0
        if lines and lines[0].startswith("#!"):
            insert_at = 1
        if len(lines) > insert_at and re.match(r"#.*coding[:=]", lines[insert_at]):
            insert_at += 1
        return insert_at, ""
    body = getattr(node, "body", [])
    if not body:
        raise ValueError("target_node_has_empty_body")
    first_body_line = int(getattr(body[0], "lineno", 0))
    if first_body_line <= 0:
        raise ValueError("target_node_missing_body_line")
    line = lines[first_body_line - 1]
    indent = line[: len(line) - len(line.lstrip())]
    return first_body_line - 1, indent


def apply_candidate(root: Path, candidate: dict[str, Any]) -> dict[str, Any]:
    """Apply one approved candidate and return an outcome receipt."""
    candidate_id_value = str(candidate.get("candidate_id") or "")
    symbol = candidate.get("symbol") if isinstance(candidate.get("symbol"), dict) else {}
    rel_path = Path(str(symbol.get("path") or ""))
    target = (root / rel_path).resolve()
    outcome: dict[str, Any] = {
        "candidate_id": candidate_id_value,
        "path": rel_path.as_posix(),
        "qualified_name": symbol.get("qualified_name"),
        "applied": False,
        "errors": [],
    }
    try:
        target.relative_to(root.resolve())
    except ValueError:
        outcome["errors"].append("path_outside_target")
        return outcome
    if approval_status(candidate) != "approved":
        outcome["errors"].append("candidate_not_approved")
        return outcome
    if not target.exists():
        outcome["errors"].append("source_file_missing")
        return outcome
    original = read_text(target)
    expected_hash = str(symbol.get("source_sha256") or "")
    if expected_hash and sha256_text(original) != expected_hash:
        outcome["errors"].append("stale_source_hash")
        return outcome
    try:
        before_ast = normalize_ast_without_docstrings(original)
        tree = ast.parse(original)
        node = find_node(tree, candidate)
    except SyntaxError as exc:
        outcome["errors"].append(f"source_syntax_error:{exc}")
        return outcome
    if node is None:
        outcome["errors"].append("target_symbol_not_found")
        return outcome
    if node_docstring(node):
        outcome["errors"].append("target_already_documented")
        return outcome
    contract_errors = validate_contract(candidate, node)
    if contract_errors:
        outcome["errors"].extend(contract_errors)
        return outcome
    lines = original.splitlines(keepends=True)
    try:
        insert_at, indent = insertion_index(node, lines)
    except ValueError as exc:
        outcome["errors"].append(str(exc))
        return outcome
    mutated = list(lines)
    mutated.insert(insert_at, docstring_line(str(candidate["proposed_docstring"]), indent))
    updated = "".join(mutated)
    target.write_text(updated, encoding="utf-8")
    try:
        compile(updated, str(target), "exec")
        after_ast = normalize_ast_without_docstrings(updated)
        if before_ast != after_ast:
            raise ValueError("non_docstring_ast_changed")
    except Exception as exc:
        target.write_text(original, encoding="utf-8")
        outcome["errors"].append(f"rolled_back:{exc}")
        return outcome
    outcome["applied"] = True
    outcome["new_source_sha256"] = sha256_text(updated)
    return outcome


def apply_candidates(candidates_path: Path, branch_or_worktree: Path, receipt_path: Path) -> dict[str, Any]:
    """Apply approved candidates to a bounded worktree and write a receipt."""
    root = branch_or_worktree.resolve()
    if not root.is_dir():
        raise typer.BadParameter(f"branch/worktree target is not a directory: {root}")
    outcomes = [apply_candidate(root, candidate) for candidate in iter_jsonl(candidates_path)]
    receipt = {
        "schema": SCHEMA_APPLY,
        "status": "pass" if all(item["applied"] or item["errors"] for item in outcomes) else "fail",
        "generated_at": utc_now(),
        "candidate_file": str(candidates_path.resolve()),
        "branch_or_worktree": str(root),
        "outcomes": outcomes,
        "applied": sum(1 for item in outcomes if item["applied"]),
        "rejected": sum(1 for item in outcomes if item["errors"] and not item["applied"]),
    }
    write_json(receipt_path, receipt)
    return receipt


app = typer.Typer(add_completion=False, help="Proposal-first docstring remediation.")


@app.command("propose-docstrings")
def propose_docstrings_cmd(
    target: Path = typer.Argument(..., help="Project directory or Python file to scan."),
    output: Path = typer.Option(..., "--output", "-o", help="JSONL candidate output path."),
    scoped: bool = typer.Option(False, "--scoped", help="Respect .monitor-codebase.json include_dirs."),
    include_optional: bool = typer.Option(False, "--include-optional", help="Emit optional/exempt candidates too."),
) -> None:
    """Generate read-only docstring candidates."""
    summary = propose(target, output, scoped=scoped, include_optional=include_optional)
    typer.echo(json.dumps(summary, indent=2, sort_keys=True))


@app.command("apply-docstrings")
def apply_docstrings_cmd(
    candidates_jsonl: Path = typer.Argument(..., help="Reviewed JSONL candidates."),
    branch_or_worktree: Path = typer.Option(..., "--branch-or-worktree", help="Bounded target repository/worktree."),
    receipt: Path = typer.Option(..., "--receipt", help="Apply receipt path."),
) -> None:
    """Apply approved, source-hash-bound docstring candidates."""
    result = apply_candidates(candidates_jsonl, branch_or_worktree, receipt)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))
    if result["applied"] == 0 and result["rejected"] == 0:
        raise typer.Exit(1)


def main() -> None:
    """Run the Typer CLI."""
    app()


if __name__ == "__main__":
    main()
