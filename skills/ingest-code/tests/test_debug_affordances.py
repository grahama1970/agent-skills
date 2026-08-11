"""Tests for static debugger invocation candidate generation."""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

from code_symbol_record import CodeSymbolRecord  # noqa: E402
from debug_affordance import build_debug_invocation_candidates  # noqa: E402


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = node.args
    return [
        arg.arg
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]
        if arg.arg not in {"self", "cls"}
    ]


def _records_for_file(root: Path, rel_path: str, text: str, repo: str = "repo") -> tuple[Path, list[CodeSymbolRecord]]:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    lines = path.read_text(encoding="utf-8").splitlines()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    records: list[CodeSymbolRecord] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _record(self, node: ast.AST, name: str, kind: str) -> None:
            qualified = ".".join([*self.stack, name]) if self.stack else name
            start = int(getattr(node, "lineno", 1))
            end = int(getattr(node, "end_lineno", start))
            code = "\n".join(lines[start - 1 : end])
            records.append(
                CodeSymbolRecord(
                    scope="code",
                    repo=repo,
                    root=str(root),
                    branch="main",
                    commit="abc123",
                    path=rel_path,
                    language="python",
                    symbol_kind=kind,
                    symbol_name=name,
                    qualified_name=qualified,
                    start_line=start,
                    end_line=end,
                    signature=lines[start - 1].strip(),
                    code=code,
                    parameters=_parameters(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else [],
                    content_hash=_hash(code),
                )
            )

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._record(node, node.name, "class")
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            kind = "method" if self.stack else "function"
            self._record(node, node.name, kind)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._record(node, node.name, "async_function")
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    Visitor().visit(tree)
    return path, records


def _all_candidates(root: Path, files: list[Path], records: list[CodeSymbolRecord]) -> list[dict[str, Any]]:
    return build_debug_invocation_candidates(
        root=root,
        repo="repo",
        branch="main",
        commit="abc123",
        symbols=records,
        files=files,
    )


def _for_symbol(candidates: list[dict[str, Any]], qualified_name: str, kind: str = "direct") -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if candidate["source"]["qualified_name"] == qualified_name and candidate["invocation_kind"] == kind
    ]


def test_plain_pure_function_with_defaults_gets_static_direct_candidate(tmp_path: Path) -> None:
    path, records = _records_for_file(tmp_path, "pkg/app.py", "def pure(value=1):\n    return value + 1")
    direct = _for_symbol(_all_candidates(tmp_path, [path], records), "pure")[0]
    assert direct["schema"] == "debugger.invocation_candidate.v1"
    assert direct["status"] == "candidate_static"
    assert direct["command"]
    assert direct["entry_breakpoint"]["requested_line"] == 2


def test_required_parameter_function_is_needs_fixture_not_runnable(tmp_path: Path) -> None:
    path, records = _records_for_file(tmp_path, "pkg/app.py", "def needs_object(client):\n    return client.fetch()")
    direct = _for_symbol(_all_candidates(tmp_path, [path], records), "needs_object")[0]
    assert direct["status"] == "needs_fixture"
    assert direct["command"] == []
    assert "required_parameters_need_fixture" in direct["limitations"]


def test_async_generator_and_context_manager_are_not_directly_runnable(tmp_path: Path) -> None:
    path, records = _records_for_file(
        tmp_path,
        "pkg/asyncs.py",
        """
from contextlib import contextmanager

async def fetch():
    return 1

def stream():
    yield 1

@contextmanager
def managed():
    yield object()
""",
    )
    candidates = _all_candidates(tmp_path, [path], records)
    assert _for_symbol(candidates, "fetch")[0]["status"] == "needs_fixture"
    assert "async_adapter_required" in _for_symbol(candidates, "fetch")[0]["limitations"]
    assert _for_symbol(candidates, "stream")[0]["status"] == "needs_fixture"
    assert "generator_iteration_required" in _for_symbol(candidates, "stream")[0]["limitations"]
    assert _for_symbol(candidates, "managed")[0]["status"] == "needs_fixture"
    assert "context_manager_entry_required" in _for_symbol(candidates, "managed")[0]["limitations"]


def test_class_gets_constructor_boundary_and_factory_is_separate_candidate(tmp_path: Path) -> None:
    path, records = _records_for_file(
        tmp_path,
        "pkg/models.py",
        """
class Builder:
    def __init__(self, path):
        self.path = path

    @classmethod
    def from_defaults(cls):
        return cls("x")
""",
    )
    candidates = _all_candidates(tmp_path, [path], records)
    class_direct = _for_symbol(candidates, "Builder")[0]
    factory_direct = _for_symbol(candidates, "Builder.from_defaults", "factory_method")[0]
    assert class_direct["status"] == "needs_fixture"
    assert class_direct["command"] == []
    assert "class_requires_constructor_or_factory_context" in class_direct["limitations"]
    assert factory_direct["status"] in {"candidate_static", "unsafe_direct"}
    assert factory_direct["source"]["qualified_name"] == "Builder.from_defaults"


def test_pytest_reference_emits_test_candidate_with_fixture_ref(tmp_path: Path) -> None:
    source, records = _records_for_file(tmp_path, "pkg/app.py", "def answer():\n    return 42")
    test_path = tmp_path / "tests" / "test_app.py"
    test_path.parent.mkdir()
    test_path.write_text("from pkg.app import answer\n\ndef test_answer():\n    assert answer() == 42\n", encoding="utf-8")
    pytest_candidate = _for_symbol(_all_candidates(tmp_path, [source, test_path], records), "answer", "pytest")[0]
    assert pytest_candidate["status"] == "candidate_static"
    assert pytest_candidate["command"] == ["python", "-m", "pytest", "tests/test_app.py"]
    assert pytest_candidate["fixture_refs"] == ["tests/test_app.py"]


def test_cli_http_and_worker_decorators_emit_entrypoint_candidates(tmp_path: Path) -> None:
    path, records = _records_for_file(
        tmp_path,
        "pkg/routes.py",
        """
@app.command()
def cli():
    return None

@api.get("/items")
def route():
    return {}

@queue.task
def worker():
    return None
""",
    )
    candidates = _all_candidates(tmp_path, [path], records)
    assert _for_symbol(candidates, "cli", "cli")[0]["status"] == "candidate_static"
    assert _for_symbol(candidates, "route", "http")[0]["status"] == "needs_fixture"
    assert _for_symbol(candidates, "worker", "attach_runtime")[0]["status"] == "attach_runtime"


def test_filesystem_database_network_and_destructive_indicators_are_unsafe(tmp_path: Path) -> None:
    path, records = _records_for_file(
        tmp_path,
        "pkg/effects.py",
        """
def write(path, value):
    path.write_text(value)

def query(db):
    db.execute("select 1")
""",
    )
    candidates = _all_candidates(tmp_path, [path], records)
    assert _for_symbol(candidates, "write")[0]["status"] == "unsafe_direct"
    assert _for_symbol(candidates, "write")[0]["command"] == []
    assert _for_symbol(candidates, "query")[0]["status"] == "unsafe_direct"


def test_overload_declaration_is_needs_fixture(tmp_path: Path) -> None:
    path, records = _records_for_file(
        tmp_path,
        "pkg/types.py",
        """
from typing import overload

@overload
def parse(value: str) -> str:
    ...
""",
    )
    direct = _for_symbol(_all_candidates(tmp_path, [path], records), "parse")[0]
    assert direct["status"] == "needs_fixture"
    assert "overload_declaration_not_runnable" in direct["limitations"]


def test_same_named_symbols_get_distinct_deterministic_recipe_ids(tmp_path: Path) -> None:
    first, records_a = _records_for_file(tmp_path, "pkg/a.py", "def run():\n    return 'a'")
    second, records_b = _records_for_file(tmp_path, "pkg/b.py", "def run():\n    return 'b'")
    candidates = _all_candidates(tmp_path, [first, second], [*records_a, *records_b])
    direct_ids = sorted(candidate["recipe_id"] for candidate in candidates if candidate["source"]["qualified_name"] == "run")
    assert len(direct_ids) == 2
    assert len(set(direct_ids)) == 2
    assert direct_ids == sorted(direct_ids)


def test_repeated_scan_is_deterministic_and_source_change_invalidates_recipe(tmp_path: Path) -> None:
    path, records = _records_for_file(tmp_path, "pkg/app.py", "def answer():\n    return 42")
    first = _all_candidates(tmp_path, [path], records)
    second = _all_candidates(tmp_path, [path], records)
    assert first == second
    changed_path, changed_records = _records_for_file(tmp_path, "pkg/app.py", "def answer():\n    return 43")
    changed = _all_candidates(tmp_path, [changed_path], changed_records)
    assert _for_symbol(first, "answer")[0]["recipe_id"] != _for_symbol(changed, "answer")[0]["recipe_id"]


def test_candidate_generation_does_not_modify_source(tmp_path: Path) -> None:
    path, records = _records_for_file(tmp_path, "pkg/app.py", "def answer():\n    return 42")
    before = path.read_text(encoding="utf-8")
    _all_candidates(tmp_path, [path], records)
    assert path.read_text(encoding="utf-8") == before
