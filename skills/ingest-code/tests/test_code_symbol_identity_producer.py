from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

artifact_spec = importlib.util.spec_from_file_location("code_graph_artifact", MODULE_DIR / "code_graph_artifact.py")
assert artifact_spec and artifact_spec.loader
code_graph_artifact = importlib.util.module_from_spec(artifact_spec)
sys.modules[artifact_spec.name] = code_graph_artifact
artifact_spec.loader.exec_module(code_graph_artifact)

ingest_spec = importlib.util.spec_from_file_location("ingest_code", MODULE_DIR / "ingest_code.py")
assert ingest_spec and ingest_spec.loader
ingest_code = importlib.util.module_from_spec(ingest_spec)
sys.modules[ingest_spec.name] = ingest_code
ingest_spec.loader.exec_module(ingest_code)

from code_symbol_record import CodeSymbolRecord


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _make_git_repo(path: Path, remote: str | None = None) -> None:
    path.mkdir(parents=True)
    _git(path, "init")
    if remote:
        _git(path, "remote", "add", "origin", remote)


def _record_for(repo: Path, source: Path, *, start_line: int = 1, name: str = "target") -> CodeSymbolRecord:
    identity = ingest_code.resolve_repository_identity(repo)
    record = ingest_code._build_code_symbol_record(
        symbol={"kind": "function", "name": name, "start_line": start_line, "end_line": start_line + 1},
        filepath=source,
        codebase_root=repo,
        scope="code",
        repo=identity.repository_id,
        branch="main",
        commit="abc123",
        imports=[],
        repository_identity=identity,
    )
    assert record is not None
    return record


def test_same_remote_repository_has_stable_id_across_checkout_names(tmp_path: Path) -> None:
    first = tmp_path / "alpha"
    second = tmp_path / "renamed"
    remote = "git@github.com:Example/Project.git"
    _make_git_repo(first, remote)
    _make_git_repo(second, remote)
    for repo in (first, second):
        (repo / "pkg").mkdir()
        (repo / "pkg" / "code.py").write_text("def target():\n    return 1\n")

    first_record = _record_for(first, first / "pkg" / "code.py")
    second_record = _record_for(second, second / "pkg" / "code.py")

    assert first_record.effective_repository_id == "github.com/example/project"
    assert second_record.effective_repository_id == first_record.effective_repository_id
    assert second_record.symbol_id == first_record.symbol_id


def test_unrelated_same_basename_repositories_do_not_collide(tmp_path: Path) -> None:
    first = tmp_path / "one" / "repo"
    second = tmp_path / "two" / "repo"
    _make_git_repo(first, "https://github.com/example/one.git")
    _make_git_repo(second, "https://github.com/example/two.git")
    for repo in (first, second):
        (repo / "pkg").mkdir()
        (repo / "pkg" / "code.py").write_text("def target():\n    return 1\n")

    first_record = _record_for(first, first / "pkg" / "code.py")
    second_record = _record_for(second, second / "pkg" / "code.py")

    assert first.name == second.name == "repo"
    assert first_record.effective_repository_id != second_record.effective_repository_id
    assert first_record.symbol_id != second_record.symbol_id


def test_no_remote_repository_identity_is_not_reconciliation_eligible(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_git_repo(repo)
    source = repo / "app.py"
    source.write_text("def target():\n    return 1\n")
    identity = ingest_code.resolve_repository_identity(repo)
    record = _record_for(repo, source)

    result = code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=identity.repository_id,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[source],
        symbols=[record],
        edges=[],
        extractor_outcomes=[{
            "root": ".",
            "status": "succeeded",
            "reason": "",
            "extractor": "treesitter",
            "extractor_version": "test",
            "command": ["test-treesitter"],
            "declared_languages": ["python"],
            "discovered_file_count": 1,
            "reported_file_count": 1,
            "reported_paths": ["app.py"],
            "stderr": "",
        }],
        repository_id_authoritative=identity.authoritative,
        repository_id_source=identity.source,
    )

    coverage = json.loads((Path(result["path"]) / "coverage.json").read_text())
    manifest = json.loads((Path(result["path"]) / "manifest.json").read_text())
    assert identity.authoritative is False
    assert coverage["complete"] is True
    assert coverage["reconciliation_eligible"] is False
    assert manifest["repository_id_authoritative"] is False


def test_nested_functions_and_methods_use_full_lexical_qualification(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_git_repo(repo, "https://github.com/example/nested.git")
    source = repo / "nested.py"
    source.write_text(
        "def outer_a():\n"
        "    def dup():\n"
        "        return 'a'\n"
        "    return dup()\n"
        "\n"
        "def outer_b():\n"
        "    def dup():\n"
        "        return 'b'\n"
        "    return dup()\n"
        "\n"
        "class First:\n"
        "    def same(self):\n"
        "        return 1\n"
        "\n"
        "class Second:\n"
        "    def same(self):\n"
        "        return 2\n"
    )

    first_nested = _record_for(repo, source, start_line=2, name="dup")
    second_nested = _record_for(repo, source, start_line=7, name="dup")
    first_method = _record_for(repo, source, start_line=12, name="same")
    second_method = _record_for(repo, source, start_line=16, name="same")

    assert first_nested.qualified_name == "outer_a.dup"
    assert second_nested.qualified_name == "outer_b.dup"
    assert first_method.qualified_name == "First.same"
    assert second_method.qualified_name == "Second.same"
    assert len({item.symbol_id for item in [first_nested, second_nested, first_method, second_method]}) == 4


def test_duplicate_declarations_get_deterministic_discriminators() -> None:
    records = [
        CodeSymbolRecord(
            scope="code",
            repo="github.com/example/repo",
            repository_id="github.com/example/repo",
            root="/repo",
            branch="main",
            commit="abc123",
            path="pkg/code.py",
            language="python",
            symbol_kind="function",
            symbol_name="dup",
            qualified_name="dup",
            start_line=1,
            end_line=2,
        ),
        CodeSymbolRecord(
            scope="code",
            repo="github.com/example/repo",
            repository_id="github.com/example/repo",
            root="/repo",
            branch="main",
            commit="abc123",
            path="pkg/code.py",
            language="python",
            symbol_kind="function",
            symbol_name="dup",
            qualified_name="dup",
            start_line=5,
            end_line=6,
        ),
    ]

    discriminated = ingest_code._with_duplicate_identity_discriminators(list(reversed(records)))

    assert [record.identity_discriminator for record in discriminated] == ["decl:1:1:2", "decl:2:5:6"]
    assert discriminated[0].symbol_id != discriminated[1].symbol_id


def test_path_separator_normalization_and_unsafe_paths() -> None:
    posix = CodeSymbolRecord(
        scope="code",
        repo="github.com/example/repo",
        root="/repo",
        branch="main",
        commit="abc123",
        path="pkg/code.py",
        language="python",
        symbol_kind="function",
        symbol_name="target",
        qualified_name="target",
        start_line=1,
        end_line=2,
    )
    windows = CodeSymbolRecord(
        scope="code",
        repo="github.com/example/repo",
        root="/repo",
        branch="main",
        commit="abc123",
        path=r".\pkg\code.py",
        language="python",
        symbol_kind="function",
        symbol_name="target",
        qualified_name="target",
        start_line=1,
        end_line=2,
    )

    assert windows.normalized_path == posix.normalized_path
    assert windows.symbol_id == posix.symbol_id
    for unsafe in ["/repo/pkg/code.py", "../code.py", "pkg/../code.py", r"C:\repo\code.py"]:
        with pytest.raises(ValueError):
            CodeSymbolRecord(
                scope="code",
                repo="github.com/example/repo",
                root="/repo",
                branch="main",
                commit="abc123",
                path=unsafe,
                language="python",
                symbol_kind="function",
                symbol_name="target",
                qualified_name="target",
                start_line=1,
                end_line=2,
            ).symbol_id


def test_symlink_escape_path_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    _make_git_repo(repo, "https://github.com/example/repo.git")
    outside.mkdir()
    escaped_source = outside / "code.py"
    escaped_source.write_text("def target():\n    return 1\n")
    link = repo / "link.py"
    link.symlink_to(escaped_source)
    identity = ingest_code.resolve_repository_identity(repo)

    with pytest.raises(ValueError):
        ingest_code._build_code_symbol_record(
            symbol={"kind": "function", "name": "target", "start_line": 1, "end_line": 2},
            filepath=link,
            codebase_root=repo,
            scope="code",
            repo=identity.repository_id,
            branch="main",
            commit="abc123",
            imports=[],
            repository_identity=identity,
        )


def test_legacy_key_remains_present_in_symbol_bundle(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_git_repo(repo, "https://github.com/example/repo.git")
    source = repo / "app.py"
    source.write_text("def target():\n    return 1\n")
    record = _record_for(repo, source)
    identity = ingest_code.resolve_repository_identity(repo)

    result = code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=identity.repository_id,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[source],
        symbols=[record],
        edges=[],
        extractor_outcomes=[{
            "root": ".",
            "status": "succeeded",
            "reason": "",
            "extractor": "treesitter",
            "extractor_version": "test",
            "command": ["test-treesitter"],
            "declared_languages": ["python"],
            "discovered_file_count": 1,
            "reported_file_count": 1,
            "reported_paths": ["app.py"],
            "stderr": "",
        }],
        repository_id_authoritative=identity.authoritative,
        repository_id_source=identity.source,
    )

    symbols = _jsonl(Path(result["path"]) / "symbols.jsonl")
    assert symbols[0]["legacy_key"] == record.legacy_key
    assert symbols[0]["memory_document"]["repository_id"] == "github.com/example/repo"
    assert symbols[0]["memory_document"]["identity_algorithm_version"] == record.identity_algorithm_version
