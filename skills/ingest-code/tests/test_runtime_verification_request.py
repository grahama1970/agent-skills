"""Runtime verification request tests for static ingest-code candidates."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

from code_analysis_handoff import write_analysis_handoff  # noqa: E402
from code_graph_artifact import write_code_graph_bundle  # noqa: E402
from code_memory_client import code_graph_bundle_digest  # noqa: E402
from code_symbol_record import CodeSymbolRecord  # noqa: E402
from environment_manifest import write_environment_manifest  # noqa: E402
from runtime_verification_request import (  # noqa: E402
    AMBIGUOUS_TARGET,
    BLOCKED_POLICY,
    DYNAMIC_TARGET,
    NEEDS_INPUT,
    READY,
    UNSUPPORTED_PROFILE,
    build_runtime_verification_requests,
    verify_runtime_verification_request,
    write_runtime_verification_requests,
)


def _hash_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _records_for_file(root: Path, rel_path: str, text: str) -> tuple[Path, list[CodeSymbolRecord]]:
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
                    content_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(),
                )
            )

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            kind = "method" if self.stack else "function"
            self._record(node, node.name, kind)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    Visitor().visit(tree)
    return path, records


def _fixture(root: Path, *, incomplete: bool = False) -> dict[str, Any]:
    root.mkdir(parents=True)
    app_text = """
def answer():
    return 42

def needs_input(client):
    return client.fetch()

def write_file(path):
    path.write_text("x")

@api.get("/items")
def route():
    return {}

@queue.task
def worker():
    return None
"""
    app, app_records = _records_for_file(root, "pkg/app.py", app_text)
    test_path = root / "tests" / "test_app.py"
    test_path.parent.mkdir()
    test_path.write_text("from pkg.app import answer\n\ndef test_answer():\n    assert answer() == 42\n", encoding="utf-8")
    files = [app, test_path]
    if incomplete:
        bad = root / "bad.py"
        bad.write_text("def broken(:\n", encoding="utf-8")
        files.append(bad)
    bundle = write_code_graph_bundle(
        codebase_root=root,
        repo=root.name,
        branch="main",
        commit="abc123",
        scan_roots=[root],
        files=files,
        symbols=app_records,
        edges=[],
    )
    env = write_environment_manifest(
        root / "artifacts" / "ingest-code" / "environment_manifest.json",
        skill_root=MODULE_DIR,
        source_root=root,
        projection_mode="emit",
        argv=["ingest_code.py", "scan", str(root), "--treesitter", "--projection-mode", "emit"],
        terminal_status="complete",
    )
    handoff = write_analysis_handoff(
        root / "artifacts" / "ingest-code" / "analysis_handoff.json",
        code_graph_artifact=bundle,
        environment_manifest=env,
        projection_mode="emit",
    )
    return {"root": root, "bundle": bundle, "env": env, "handoff": handoff}


def _by_symbol_kind(rows: list[dict[str, Any]], qualified_name: str, kind: str) -> dict[str, Any]:
    for row in rows:
        if row["symbol"]["qualified_name"] == qualified_name and row["invocation"]["kind"] == kind:
            return row
    raise AssertionError(f"missing request for {qualified_name}:{kind}")


def test_ready_pytest_request_is_exact_bounded_and_deterministic(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "repo")
    first = build_runtime_verification_requests(
        code_graph_artifact=fixture["bundle"],
        analysis_handoff=fixture["handoff"],
        environment_manifest=fixture["env"],
    )
    second = build_runtime_verification_requests(
        code_graph_artifact=fixture["bundle"],
        analysis_handoff=fixture["handoff"],
        environment_manifest=fixture["env"],
    )
    request = _by_symbol_kind(first, "answer", "pytest")

    assert request["disposition"] == READY
    assert request["inputs"]["required_input_refs"][0]["relative_path"] == "tests/test_app.py"
    assert request["limits"]["timeout_seconds"] == 30
    assert request["request_identity_digest"] == _by_symbol_kind(second, "answer", "pytest")["request_identity_digest"]
    assert verify_runtime_verification_request(request)["status"] == "PASS"


def test_non_ready_dispositions_do_not_invent_inputs_or_runtime_proof(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "repo")
    rows = build_runtime_verification_requests(
        code_graph_artifact=fixture["bundle"],
        analysis_handoff=fixture["handoff"],
        environment_manifest=fixture["env"],
    )

    needs_input = _by_symbol_kind(rows, "needs_input", "direct")
    assert needs_input["disposition"] == NEEDS_INPUT
    assert needs_input["inputs"]["required_input_refs"] == []
    assert "runtime_result" not in json.dumps(needs_input)
    assert _by_symbol_kind(rows, "write_file", "direct")["disposition"] == BLOCKED_POLICY
    assert _by_symbol_kind(rows, "route", "http")["disposition"] == DYNAMIC_TARGET
    assert _by_symbol_kind(rows, "worker", "attach_runtime")["disposition"] == DYNAMIC_TARGET


def test_incomplete_coverage_and_unsupported_profile_are_non_ready(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "repo", incomplete=True)
    rows = build_runtime_verification_requests(
        code_graph_artifact=fixture["bundle"],
        analysis_handoff=fixture["handoff"],
        environment_manifest=fixture["env"],
    )
    unsupported = build_runtime_verification_requests(
        code_graph_artifact=fixture["bundle"],
        analysis_handoff=fixture["handoff"],
        environment_manifest=fixture["env"],
        profile="unknown-profile",
    )

    assert {row["disposition"] for row in rows} == {"INCOMPLETE_COVERAGE"}
    assert {row["disposition"] for row in unsupported} == {UNSUPPORTED_PROFILE}


def test_request_verifier_rejects_mutations_and_path_escapes(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "repo")
    rows = build_runtime_verification_requests(
        code_graph_artifact=fixture["bundle"],
        analysis_handoff=fixture["handoff"],
        environment_manifest=fixture["env"],
    )
    request = _by_symbol_kind(rows, "answer", "direct")
    assert verify_runtime_verification_request(request)["status"] == "PASS"

    mutated = json.loads(json.dumps(request))
    mutated["stdout"] = "not allowed"
    assert "runtime result field is forbidden: stdout" in verify_runtime_verification_request(mutated)["errors"]

    escaped = json.loads(json.dumps(request))
    escaped["containment"]["declared_file_grants"].append("../secret.txt")
    assert any("escapes root" in error for error in verify_runtime_verification_request(escaped)["errors"])

    stale_source = json.loads(json.dumps(request))
    (fixture["root"] / "pkg" / "app.py").write_text("def answer():\n    return 43\n", encoding="utf-8")
    assert "bound source file changed" in verify_runtime_verification_request(stale_source)["errors"]


def test_symbol_candidate_environment_and_handoff_mutations_invalidate_request(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "repo")
    request = _by_symbol_kind(
        build_runtime_verification_requests(
            code_graph_artifact=fixture["bundle"],
            analysis_handoff=fixture["handoff"],
            environment_manifest=fixture["env"],
        ),
        "answer",
        "direct",
    )

    candidate = json.loads(json.dumps(request))
    candidate["candidate"]["candidate_digest"] = "sha256:bad"
    assert "candidate digest mismatch" in verify_runtime_verification_request(candidate)["errors"]

    symbol = json.loads(json.dumps(request))
    symbol["symbol"]["symbol_version_id"] = "csv_bad"
    assert "symbol version mismatch" in verify_runtime_verification_request(symbol)["errors"]

    env = json.loads(json.dumps(request))
    Path(env["environment_manifest_ref"]["path"]).write_text('{"schema":"changed"}\n', encoding="utf-8")
    assert "environment manifest sha mismatch" in verify_runtime_verification_request(env)["errors"]

    fixture = _fixture(tmp_path / "repo2")
    handoff_request = _by_symbol_kind(
        build_runtime_verification_requests(
            code_graph_artifact=fixture["bundle"],
            analysis_handoff=fixture["handoff"],
            environment_manifest=fixture["env"],
        ),
        "answer",
        "direct",
    )
    Path(handoff_request["analysis_handoff_ref"]["path"]).write_text('{"schema":"changed"}\n', encoding="utf-8")
    assert "analysis handoff sha mismatch" in verify_runtime_verification_request(handoff_request)["errors"]


def test_emission_does_not_change_canonical_bundle_digest(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "repo")
    before = code_graph_bundle_digest(Path(fixture["bundle"]["path"]))
    artifact = write_runtime_verification_requests(
        fixture["root"] / "artifacts" / "ingest-code" / "runtime_verification_requests.jsonl",
        code_graph_artifact=fixture["bundle"],
        analysis_handoff=fixture["handoff"],
        environment_manifest=fixture["env"],
    )
    after = code_graph_bundle_digest(Path(fixture["bundle"]["path"]))

    assert before == after
    assert artifact["status"] == "PASS"
    assert _hash_bytes(Path(artifact["path"])).startswith("0") or artifact["sha256"].startswith("sha256:")
