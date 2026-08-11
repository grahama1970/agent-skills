"""Static debugger invocation candidates for ingest-code symbol bundles.

The records emitted here are read-only hints for `$debugger`. They never prove a
recipe reaches a symbol; only a later debugger proof may promote a candidate.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from code_symbol_record import CodeSymbolRecord

SCHEMA_VERSION = "debugger.invocation_candidate.v1"
EXTRACTION_VERSION = "ingest-code.debug_affordance.v1"
SAFE_DIRECT = "candidate_static"
NEEDS_FIXTURE = "needs_fixture"
UNSAFE_DIRECT = "unsafe_direct"
ATTACH_RUNTIME = "attach_runtime"

SIDE_EFFECT_CALL_MARKERS = (
    ".write_text",
    ".write_bytes",
    ".unlink",
    ".rename",
    ".replace",
    ".mkdir",
    ".rmdir",
    "open",
    "remove",
    "rmtree",
    "subprocess.",
    "requests.",
    "httpx.",
    "socket.",
    "connect",
    "execute",
    "commit",
    "delete",
    "insert",
    "update",
    "upsert",
)
CLI_DECORATORS = ("typer", "click", ".command", ".group")
HTTP_DECORATORS = (".get", ".post", ".put", ".patch", ".delete", ".route")
WORKER_DECORATORS = ("celery", ".task", ".worker", ".job", ".enqueue")


@dataclass(frozen=True)
class SymbolFacts:
    """Static execution facts for one Python symbol."""

    decorators: list[str] = field(default_factory=list)
    first_executable_line: int = 0
    required_parameters: list[str] = field(default_factory=list)
    has_defaults: bool = False
    is_async: bool = False
    is_generator: bool = False
    is_async_generator: bool = False
    is_context_manager: bool = False
    is_overload: bool = False
    returns_value: bool = False
    raises: list[str] = field(default_factory=list)
    side_effect_indicators: list[str] = field(default_factory=list)
    route_metadata: dict[str, Any] = field(default_factory=dict)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()[:40]}"


def _name_from_node(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_from_node(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _name_from_node(node.func)
    if isinstance(node, ast.Subscript):
        return _name_from_node(node.value)
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return ""


def _decorators(node: ast.AST) -> list[str]:
    return sorted({_name_from_node(item) for item in getattr(node, "decorator_list", []) if _name_from_node(item)})


def _required_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[list[str], bool]:
    args = node.args
    positional = [*args.posonlyargs, *args.args]
    defaults = list(args.defaults)
    defaulted = {arg.arg for arg in positional[len(positional) - len(defaults) :]}
    keyword_defaults = {
        arg.arg
        for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=False)
        if default is not None
    }
    required = [
        arg.arg
        for arg in [*positional, *args.kwonlyargs]
        if arg.arg not in {"self", "cls"} and arg.arg not in defaulted and arg.arg not in keyword_defaults
    ]
    return required, bool(defaults or keyword_defaults or args.vararg or args.kwarg)


def _first_executable_line(node: ast.AST) -> int:
    body = list(getattr(node, "body", []) or [])
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    return int(getattr(body[0], "lineno", getattr(node, "lineno", 0)) or 0) if body else 0


def _raises(node: ast.AST) -> list[str]:
    values = []
    for child in ast.walk(node):
        if isinstance(child, ast.Raise) and child.exc:
            values.append(_name_from_node(child.exc).split("(", 1)[0])
    return sorted({value for value in values if value})


def _side_effects(node: ast.AST) -> list[str]:
    calls = [_name_from_node(child.func) for child in ast.walk(node) if isinstance(child, ast.Call)]
    effects = []
    for call in calls:
        lowered = call.lower()
        if any(marker in lowered for marker in SIDE_EFFECT_CALL_MARKERS):
            effects.append(call)
    for child in ast.walk(node):
        if isinstance(child, (ast.Assign, ast.AugAssign, ast.Delete, ast.AnnAssign)):
            effects.append(type(child).__name__)
    return sorted(set(effects))


def _route_metadata(decorators: Iterable[str]) -> dict[str, Any]:
    values = list(decorators)
    if any(any(marker in value for marker in CLI_DECORATORS) for value in values):
        return {"entrypoint": "cli", "decorators": values}
    if any(any(marker in value for marker in HTTP_DECORATORS) for value in values):
        return {"entrypoint": "http", "decorators": values}
    if any(any(marker in value for marker in WORKER_DECORATORS) for value in values):
        return {"entrypoint": "worker", "decorators": values}
    return {}


def _node_facts(node: ast.AST) -> SymbolFacts:
    decorators = _decorators(node)
    required: list[str] = []
    has_defaults = False
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        required, has_defaults = _required_parameters(node)
    is_generator = any(isinstance(child, ast.Yield) for child in ast.walk(node))
    is_async_generator = isinstance(node, ast.AsyncFunctionDef) and is_generator
    return SymbolFacts(
        decorators=decorators,
        first_executable_line=_first_executable_line(node),
        required_parameters=required,
        has_defaults=has_defaults,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        is_generator=is_generator,
        is_async_generator=is_async_generator,
        is_context_manager="contextmanager" in " ".join(decorators),
        is_overload=any(value.endswith("overload") for value in decorators),
        returns_value=any(isinstance(child, ast.Return) and child.value is not None for child in ast.walk(node)),
        raises=_raises(node),
        side_effect_indicators=_side_effects(node),
        route_metadata=_route_metadata(decorators),
    )


def _symbol_nodes(path: Path) -> dict[tuple[str, int], ast.AST]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return {}
    nodes: dict[tuple[str, int], ast.AST] = {("<module>", 1): tree}

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _qualified(self, name: str) -> str:
            return ".".join([*self.stack, name]) if self.stack else name

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            qualified = self._qualified(node.name)
            nodes[(qualified, int(node.lineno))] = node
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            qualified = self._qualified(node.name)
            nodes[(qualified, int(node.lineno))] = node
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            qualified = self._qualified(node.name)
            nodes[(qualified, int(node.lineno))] = node
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    Visitor().visit(tree)
    return nodes


def _load_symbol_facts(root: Path, files: list[Path]) -> dict[tuple[str, str, int], SymbolFacts]:
    facts: dict[tuple[str, str, int], SymbolFacts] = {}
    for path in files:
        if path.suffix != ".py":
            continue
        rel_path = path.resolve().relative_to(root.resolve()).as_posix()
        for (qualified_name, start_line), node in _symbol_nodes(path).items():
            facts[(rel_path, qualified_name, start_line)] = _node_facts(node)
    return facts


def _test_files(files: list[Path], root: Path) -> list[Path]:
    result = []
    for path in files:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        if path.suffix == ".py" and ("/tests/" in f"/{rel}" or path.name.startswith("test_")):
            result.append(path)
    return sorted(result, key=lambda item: item.as_posix())


def _pytest_evidence(symbol: CodeSymbolRecord, test_files: list[Path], root: Path) -> list[dict[str, Any]]:
    evidence = []
    pattern = re.compile(rf"\b{re.escape(symbol.symbol_name)}\s*\(")
    for path in test_files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        for idx, line in enumerate(lines, start=1):
            if pattern.search(line):
                evidence.append({
                    "path": rel,
                    "line": idx,
                    "raw_reference": symbol.symbol_name,
                    "source_site": line.strip(),
                })
    return evidence


def _base_record(
    *,
    symbol: CodeSymbolRecord,
    repo: str,
    branch: str,
    commit: str,
    invocation_kind: str,
    status: str,
    command: list[str],
    facts: SymbolFacts,
    evidence: dict[str, Any],
    limitations: list[str],
    fixture_refs: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": SCHEMA_VERSION,
        "repository": repo,
        "branch": branch,
        "commit": commit,
        "symbol_id": symbol.symbol_id,
        "symbol_version_id": symbol.symbol_version_id,
        "symbol_content_hash": symbol.effective_content_hash,
        "symbol_ref": f"{symbol.normalized_path}:{symbol.qualified_name}",
        "source": {
            "path": symbol.normalized_path,
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
            "qualified_name": symbol.qualified_name,
            "symbol_kind": symbol.symbol_kind,
            "signature": symbol.signature,
        },
        "status": status,
        "adapter_family": "python",
        "runtime": "python",
        "language": symbol.language,
        "invocation_kind": invocation_kind,
        "command": command,
        "cwd": ".",
        "environment_refs": [],
        "fixture_refs": fixture_refs or [],
        "launch_configuration_template": {},
        "entry_breakpoint": {
            "path": symbol.normalized_path,
            "requested_line": facts.first_executable_line or symbol.start_line,
            "verified_line": None,
        },
        "side_effect_class": "unsafe_direct" if status == UNSAFE_DIRECT else ("unknown" if status == NEEDS_FIXTURE else "isolated_test" if invocation_kind == "pytest" else "controlled_local"),
        "evidence": evidence,
        "limitations": limitations,
        "recipe_schema_version": EXTRACTION_VERSION,
    }
    payload["recipe_id"] = _sha256_id(
        "dbg",
        {
            "schema": EXTRACTION_VERSION,
            "repo": repo,
            "branch": branch,
            "commit": commit,
            "symbol_version_id": symbol.symbol_version_id,
            "invocation_kind": invocation_kind,
            "status": status,
            "evidence": evidence,
        },
    )
    return payload


def _direct_candidate(symbol: CodeSymbolRecord, facts: SymbolFacts, repo: str, branch: str, commit: str) -> dict[str, Any]:
    limitations: list[str] = ["static_candidate_not_runtime_verified"]
    status = SAFE_DIRECT
    invocation_kind = "direct"
    if symbol.symbol_kind == "class":
        status = NEEDS_FIXTURE
        limitations.append("class_requires_constructor_or_factory_context")
    elif symbol.symbol_kind == "method" and "classmethod" in facts.decorators:
        invocation_kind = "factory_method"
    elif symbol.symbol_kind == "method":
        status = NEEDS_FIXTURE
        limitations.append("method_requires_instance_context")
    elif facts.is_overload:
        status = NEEDS_FIXTURE
        limitations.append("overload_declaration_not_runnable")
    elif facts.side_effect_indicators:
        status = UNSAFE_DIRECT
        limitations.append("side_effects_require_harness")
    elif facts.required_parameters:
        status = NEEDS_FIXTURE
        limitations.append("required_parameters_need_fixture")
    if facts.is_async:
        status = NEEDS_FIXTURE
        limitations.append("async_adapter_required")
    if facts.is_generator:
        status = NEEDS_FIXTURE
        limitations.append("generator_iteration_required")
    if facts.is_context_manager:
        status = NEEDS_FIXTURE
        limitations.append("context_manager_entry_required")
    command = []
    if status == SAFE_DIRECT:
        access = f"getattr(m, '{symbol.symbol_name}')"
        if invocation_kind == "factory_method" and "." in symbol.qualified_name:
            owner, method = symbol.qualified_name.rsplit(".", 1)
            access = f"getattr(getattr(m, '{owner}'), '{method}')"
        command = [
            "python",
            "-c",
            f"import importlib; m=importlib.import_module('{_module_name(symbol.normalized_path)}'); {access}()",
        ]
    return _base_record(
        symbol=symbol,
        repo=repo,
        branch=branch,
        commit=commit,
        invocation_kind=invocation_kind,
        status=status,
        command=command,
        facts=facts,
        evidence={
            "required_parameters": facts.required_parameters,
            "side_effect_indicators": facts.side_effect_indicators,
            "decorators": facts.decorators,
        },
        limitations=limitations,
    )


def _module_name(rel_path: str) -> str:
    path = Path(rel_path)
    parts = list(path.parts)
    if not parts:
        return ""
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(path.suffix)
    return ".".join(parts)


def _route_candidates(symbol: CodeSymbolRecord, facts: SymbolFacts, repo: str, branch: str, commit: str) -> list[dict[str, Any]]:
    entrypoint = facts.route_metadata.get("entrypoint")
    if entrypoint == "cli":
        return [
            _base_record(
                symbol=symbol,
                repo=repo,
                branch=branch,
                commit=commit,
                invocation_kind="cli",
                status=SAFE_DIRECT,
                command=["python", "-m", _module_name(symbol.normalized_path)],
                facts=facts,
                evidence=facts.route_metadata,
                limitations=["static_cli_entrypoint_not_runtime_verified"],
            )
        ]
    if entrypoint == "http":
        return [
            _base_record(
                symbol=symbol,
                repo=repo,
                branch=branch,
                commit=commit,
                invocation_kind="http",
                status=NEEDS_FIXTURE,
                command=[],
                facts=facts,
                evidence=facts.route_metadata,
                limitations=["http_client_or_running_app_required"],
            )
        ]
    if entrypoint == "worker":
        return [
            _base_record(
                symbol=symbol,
                repo=repo,
                branch=branch,
                commit=commit,
                invocation_kind="attach_runtime",
                status=ATTACH_RUNTIME,
                command=[],
                facts=facts,
                evidence=facts.route_metadata,
                limitations=["worker_runtime_required"],
            )
        ]
    return []


def build_debug_invocation_candidates(
    *,
    root: Path,
    repo: str,
    branch: str,
    commit: str,
    symbols: list[CodeSymbolRecord],
    files: list[Path],
) -> list[dict[str, Any]]:
    """Build deterministic static debugger invocation candidates."""
    resolved_root = root.resolve()
    python_symbols = [symbol for symbol in symbols if symbol.language == "python"]
    facts_by_symbol = _load_symbol_facts(resolved_root, files)
    tests = _test_files(files, resolved_root)
    records: list[dict[str, Any]] = []

    for symbol in sorted(python_symbols, key=lambda item: (item.normalized_path, item.qualified_name, item.start_line)):
        facts = facts_by_symbol.get(
            (symbol.normalized_path, symbol.qualified_name, symbol.start_line),
            SymbolFacts(first_executable_line=symbol.start_line, required_parameters=list(symbol.parameters)),
        )
        pytest_sites = _pytest_evidence(symbol, tests, resolved_root)
        for site in pytest_sites:
            records.append(
                _base_record(
                    symbol=symbol,
                    repo=repo,
                    branch=branch,
                    commit=commit,
                    invocation_kind="pytest",
                    status=SAFE_DIRECT,
                    command=["python", "-m", "pytest", site["path"]],
                    facts=facts,
                    evidence={"test_reference": site},
                    limitations=["static_pytest_candidate_not_runtime_verified"],
                    fixture_refs=[site["path"]],
                )
            )
        records.extend(_route_candidates(symbol, facts, repo, branch, commit))
        records.append(_direct_candidate(symbol, facts, repo, branch, commit))

    return sorted(records, key=lambda item: (item["source"]["path"], item["source"]["qualified_name"], item["invocation_kind"], item["recipe_id"]))
