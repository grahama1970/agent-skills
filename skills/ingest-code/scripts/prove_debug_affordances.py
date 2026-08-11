#!/usr/bin/env python3
"""Live proof for static debugger invocation candidates in ingest-code."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from code_graph_artifact import write_code_graph_bundle  # noqa: E402
from code_symbol_record import CodeSymbolRecord  # noqa: E402
from incremental_state import build_transform_fingerprints  # noqa: E402


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True, timeout=15)


def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = node.args
    return [
        arg.arg
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]
        if arg.arg not in {"self", "cls"}
    ]


def _records_for_file(root: Path, rel_path: str) -> list[CodeSymbolRecord]:
    path = root / rel_path
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
                    repo=root.name,
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
            self._record(node, node.name, "method" if self.stack else "function")
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._record(node, node.name, "async_function")
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    Visitor().visit(tree)
    return records


def _setup_repo(out: Path) -> Path:
    repo = out / "fixture-repo"
    if repo.exists():
        shutil.rmtree(repo)
    (repo / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pkg" / "app.py").write_text(
        """
from contextlib import contextmanager
from typing import overload

def pure(value=1):
    return value + 1

def needs_object(client):
    return client.fetch()

async def async_fetch():
    return 1

def stream():
    yield 1

@contextmanager
def managed():
    yield object()

class Builder:
    def __init__(self, path):
        self.path = path

    @classmethod
    def from_defaults(cls):
        return cls("x")

@app.command()
def cli():
    return None

@api.get("/items")
def route():
    return {}

@queue.task
def worker():
    return None

def write_file(path, value):
    path.write_text(value)

@overload
def parse(value: str) -> str:
    ...
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo / "pkg" / "other.py").write_text("def pure():\n    return 2\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").write_text(
        "from pkg.app import pure\n\n"
        "def test_pure():\n"
        "    assert pure() == 2\n",
        encoding="utf-8",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "agent@example.invalid")
    _git(repo, "config", "user.name", "Agent")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def _bundle(repo: Path) -> dict[str, Any]:
    files = sorted(repo.rglob("*.py"), key=lambda path: path.as_posix())
    symbols: list[CodeSymbolRecord] = []
    for path in files:
        symbols.extend(_records_for_file(repo, path.relative_to(repo).as_posix()))
    return write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=files,
        symbols=symbols,
        edges=[],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--live", action="store_true", help="Confirm this proof runs real local files.")
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("refusing to run without --live")

    out = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    repo = _setup_repo(out)
    before_sources = {path.relative_to(repo).as_posix(): path.read_text(encoding="utf-8") for path in repo.rglob("*.py")}
    first = _bundle(repo)
    bundle_path = Path(first["path"])
    first_rows = _jsonl(bundle_path / "debug_invocations.jsonl")
    first_bytes = (bundle_path / "debug_invocations.jsonl").read_bytes()
    checksums = json.loads((bundle_path / "checksums.json").read_text(encoding="utf-8"))

    second = _bundle(repo)
    second_rows = _jsonl(Path(second["path"]) / "debug_invocations.jsonl")
    second_bytes = (Path(second["path"]) / "debug_invocations.jsonl").read_bytes()

    (repo / "pkg" / "app.py").write_text(
        (repo / "pkg" / "app.py").read_text(encoding="utf-8").replace("return value + 1", "return value + 2"),
        encoding="utf-8",
    )
    changed = _bundle(repo)
    changed_rows = _jsonl(Path(changed["path"]) / "debug_invocations.jsonl")

    def rows_for(name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if row["source"]["qualified_name"] == name]

    pure_direct = [row for row in rows_for("pure", first_rows) if row["invocation_kind"] == "direct" and row["source"]["path"] == "pkg/app.py"][0]
    pure_pytest = [row for row in rows_for("pure", first_rows) if row["invocation_kind"] == "pytest"][0]
    changed_pure_direct = [row for row in rows_for("pure", changed_rows) if row["invocation_kind"] == "direct" and row["source"]["path"] == "pkg/app.py"][0]
    by_name = {row["source"]["qualified_name"]: row for row in first_rows}
    route_kinds = {(row["source"]["qualified_name"], row["invocation_kind"]): row for row in first_rows}
    after_sources = {path.relative_to(repo).as_posix(): path.read_text(encoding="utf-8") for path in repo.rglob("*.py")}

    checks = {
        "bundle_contains_debug_invocations": (bundle_path / "debug_invocations.jsonl").is_file(),
        "checksums_include_debug_invocations": "debug_invocations.jsonl" in checksums["files"],
        "checksum_matches_debug_invocations": hashlib.sha256(first_bytes).hexdigest() == checksums["files"]["debug_invocations.jsonl"],
        "records_are_static_candidates": all(not row["status"].startswith("verified_") for row in first_rows),
        "pure_function_direct_candidate": pure_direct["status"] == "candidate_static" and bool(pure_direct["command"]),
        "pytest_candidate_has_fixture_ref": pure_pytest["fixture_refs"] == ["tests/test_app.py"],
        "required_parameter_needs_fixture": by_name["needs_object"]["status"] == "needs_fixture" and by_name["needs_object"]["command"] == [],
        "async_needs_fixture": by_name["async_fetch"]["status"] == "needs_fixture",
        "generator_needs_fixture": by_name["stream"]["status"] == "needs_fixture",
        "context_manager_needs_fixture": by_name["managed"]["status"] == "needs_fixture",
        "class_not_generic_run": by_name["Builder"]["status"] == "needs_fixture" and by_name["Builder"]["command"] == [],
        "factory_method_candidate": route_kinds[("Builder.from_defaults", "factory_method")]["status"] in {"candidate_static", "unsafe_direct"},
        "cli_candidate": route_kinds[("cli", "cli")]["status"] == "candidate_static",
        "http_candidate_needs_fixture": route_kinds[("route", "http")]["status"] == "needs_fixture",
        "worker_candidate_attach_runtime": route_kinds[("worker", "attach_runtime")]["status"] == "attach_runtime",
        "side_effect_unsafe": by_name["write_file"]["status"] == "unsafe_direct" and by_name["write_file"]["command"] == [],
        "overload_needs_fixture": by_name["parse"]["status"] == "needs_fixture",
        "ambiguous_same_name_distinct_ids": len({row["recipe_id"] for row in rows_for("pure", first_rows)}) >= 3,
        "repeated_scan_deterministic": first_rows == second_rows and first_bytes == second_bytes,
        "source_change_invalidates_candidate": pure_direct["recipe_id"] != changed_pure_direct["recipe_id"],
        "generation_did_not_mutate_source_before_edit": all(
            after_sources.get(rel, "").replace("return value + 2", "return value + 1") == text
            for rel, text in before_sources.items()
        ),
        "transform_fingerprint_includes_debug_affordance": "debug_invocation_candidates"
        in build_transform_fingerprints(SKILL_ROOT, scope="code", patterns=["*.py"], scan_roots=["."]),
    }
    summary = {
        "schema": "ingest-code.debug_affordance_proof.v1",
        "status": "pass" if all(checks.values()) else "fail",
        "mocked": False,
        "live": True,
        "repo": str(repo),
        "bundle": first,
        "changed_bundle": changed,
        "debug_invocations_sha256": _sha256_file(bundle_path / "debug_invocations.jsonl"),
        "checksums_sha256": _sha256_file(bundle_path / "checksums.json"),
        "candidate_count": len(first_rows),
        "status_counts": {
            status: sum(1 for row in first_rows if row["status"] == status)
            for status in sorted({row["status"] for row in first_rows})
        },
        "checks": checks,
    }
    _write_json(out / "proof-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
