from __future__ import annotations

import hashlib
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


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "pkg").mkdir()
    source = path / "pkg" / "app.py"
    source.write_text("def app():\n    return 1\n")
    _git(path, "init")
    _git(path, "config", "user.email", "ingest-code@example.invalid")
    _git(path, "config", "user.name", "ingest-code fixture")
    _git(path, "add", "pkg/app.py")
    _git(path, "commit", "-m", "fixture")
    return source


def _symbol(repo: Path, source: Path, *, repo_id: str = "github.com/example/project") -> CodeSymbolRecord:
    return CodeSymbolRecord(
        scope="code",
        repo=repo_id,
        repository_id=repo_id,
        root=str(repo.resolve()),
        branch="main",
        commit="abc123",
        path=source.relative_to(repo).as_posix(),
        language="python",
        symbol_kind="function",
        symbol_name="app",
        qualified_name="app",
        start_line=1,
        end_line=2,
        code=source.read_text(),
        content_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
    )


def _outcome(paths: list[str]) -> dict:
    return {
        "root": ".",
        "status": "succeeded",
        "reason": "",
        "extractor": "treesitter",
        "extractor_version": "treesitter-test-v1",
        "command": ["treesitter-test"],
        "declared_languages": ["python"],
        "discovered_file_count": len(paths),
        "reported_file_count": len(paths),
        "reported_paths": paths,
        "stderr": "",
    }


def _write(repo: Path, source: Path, **kwargs) -> dict:
    config = {
        "glob_patterns": ["*.py"],
        "exclude_dirs": [".git", "__pycache__"],
        "ignore_rules": "git_exclude_standard",
        "treesitter": True,
        "code_index": True,
        "dry_run": False,
        "cwe_only": False,
    }
    config.update(kwargs.pop("scan_config", {}))
    return code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=kwargs.pop("repo_id", "github.com/example/project"),
        branch=kwargs.pop("branch", "main"),
        commit=kwargs.pop("commit", "abc123"),
        scan_roots=[repo],
        files=kwargs.pop("files", [source]),
        symbols=kwargs.pop("symbols", [_symbol(repo, source)]),
        edges=[],
        extractor_outcomes=[_outcome(kwargs.pop("reported_paths", [source.relative_to(repo).as_posix()]))],
        repository_id_authoritative=kwargs.pop("repository_id_authoritative", True),
        repository_id_source=kwargs.pop("repository_id_source", "git_remote_origin"),
        scan_config=config,
    )


def test_repeated_unchanged_scans_are_byte_identical_and_exact_file_set(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _make_repo(repo)

    first = _write(repo, source)
    bundle = Path(first["path"])
    before = {path.name: path.read_bytes() for path in bundle.iterdir() if path.is_file()}
    second = _write(repo, source)
    after = {path.name: path.read_bytes() for path in bundle.iterdir() if path.is_file()}

    assert second["bundle_digest"] == first["bundle_digest"]
    assert after == before
    assert sorted(after) == sorted(code_graph_artifact.ALLOWED_ARTIFACT_FILENAMES)
    assert code_graph_artifact.validate_code_graph_bundle(bundle)["ok"] is True


def test_portable_identity_and_digest_are_checkout_location_independent(tmp_path: Path) -> None:
    first_repo = tmp_path / "alpha"
    second_repo = tmp_path / "renamed"
    first_source = _make_repo(first_repo)
    second_source = _make_repo(second_repo)

    first = _write(first_repo, first_source)
    second = _write(second_repo, second_source)

    assert first["bundle_digest"] == second["bundle_digest"]
    assert _json(Path(first["manifest"]))["root"] == "."
    assert _jsonl(Path(first["path"]) / "symbols.jsonl")[0]["memory_document"]["root"] == "."


def test_configuration_changes_alter_configuration_digest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _make_repo(repo)

    first = _write(repo, source, scan_config={"glob_patterns": ["*.py"]})
    second = _write(repo, source, scan_config={"glob_patterns": ["pkg/*.py"]})

    assert first["configuration_digest"] != second["configuration_digest"]
    assert _json(Path(second["manifest"]))["configuration"]["glob_patterns"] == ["pkg/*.py"]


def test_worktree_state_distinguishes_tracked_untracked_and_detached_head(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _make_repo(repo)
    extra = repo / "pkg" / "extra.py"
    extra.write_text("def extra():\n    return 2\n")
    source.write_text("def app():\n    return 3\n")
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short=12", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(repo, "checkout", "--detach")

    result = _write(
        repo,
        source,
        branch=f"detached:{commit}",
        files=[source, extra],
        symbols=[_symbol(repo, source), _symbol(repo, extra)],
        reported_paths=["pkg/app.py", "pkg/extra.py"],
    )
    manifest = _json(Path(result["manifest"]))

    assert manifest["ref"].startswith("detached:")
    assert manifest["worktree_state"]["tracked_modified"] is True
    assert manifest["worktree_state"]["untracked_included_source"] is True
    assert manifest["worktree_state"]["untracked_included_source_paths"] == ["pkg/extra.py"]


def test_stale_extra_file_is_removed_from_published_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _make_repo(repo)
    stale = repo / "artifacts" / "ingest-code" / "code-graph" / "old-schema.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}\n")

    result = _write(repo, source)

    assert "old-schema.json" not in {path.name for path in Path(result["path"]).iterdir()}
    assert sorted(path.name for path in Path(result["path"]).iterdir()) == sorted(
        code_graph_artifact.ALLOWED_ARTIFACT_FILENAMES
    )


def test_interrupted_temporary_write_leaves_prior_complete_bundle_intact(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _make_repo(repo)
    first = _write(repo, source)
    bundle = Path(first["path"])
    before = {path.name: path.read_bytes() for path in bundle.iterdir() if path.is_file()}

    def interrupted(directory: Path, payloads: dict[str, bytes]) -> None:
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "manifest.json").write_bytes(payloads["manifest.json"])
        raise RuntimeError("simulated interrupted temp write")

    monkeypatch.setattr(code_graph_artifact, "_write_payload_files", interrupted)
    with pytest.raises(RuntimeError):
        _write(repo, source, scan_config={"glob_patterns": ["pkg/*.py"]})

    after = {path.name: path.read_bytes() for path in bundle.iterdir() if path.is_file()}
    assert after == before
    assert code_graph_artifact.validate_code_graph_bundle(bundle)["bundle_digest"] == first["bundle_digest"]


def test_tampered_manifest_count_checksum_and_schema_are_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _make_repo(repo)
    result = _write(repo, source)
    bundle = Path(result["path"])

    manifest = _json(bundle / "manifest.json")
    manifest["counts"]["files"] = 999
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="checksum mismatch|counts"):
        code_graph_artifact.validate_code_graph_bundle(bundle)

    _write(repo, source)
    checksums = _json(bundle / "checksums.json")
    checksums["schema_version"] = "unsupported"
    (bundle / "checksums.json").write_text(json.dumps(checksums, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="unsupported checksums schema_version"):
        code_graph_artifact.validate_code_graph_bundle(bundle)


def test_memory_document_disagreement_is_rejected_even_with_updated_checksum(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _make_repo(repo)
    result = _write(repo, source)
    bundle = Path(result["path"])

    symbols = _jsonl(bundle / "symbols.jsonl")
    symbols[0]["memory_document"]["qualified_name"] = "different"
    symbol_bytes = b"".join(
        (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for record in symbols
    )
    (bundle / "symbols.jsonl").write_bytes(symbol_bytes)
    checksums = _json(bundle / "checksums.json")
    checksums["files"]["symbols.jsonl"] = hashlib.sha256(symbol_bytes).hexdigest()
    checksums["bundle_digest"] = code_graph_artifact.calculate_bundle_digest(checksums)
    (bundle / "checksums.json").write_text(json.dumps(checksums, indent=2, sort_keys=True) + "\n")

    with pytest.raises(ValueError, match="memory_document disagrees"):
        code_graph_artifact.validate_code_graph_bundle(bundle)


def test_ingest_marker_binds_to_published_bundle_hashes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _make_repo(repo)
    result = _write(repo, source)

    marker_path = ingest_code._write_ingest_marker(
        repo,
        files_scanned=1,
        knowledge_stored=0,
        cwe_stored=0,
        edges_stored=0,
        code_symbols_stored=1,
        treesitter=True,
        scope="code",
        scan_roots=[repo],
        completed_scan_roots=[repo],
        code_graph_artifact=result,
    )
    marker = _json(marker_path)
    binding = marker["local_artifacts"]["code_graph_binding"]

    assert binding["manifest"] == result["manifest"]
    assert binding["manifest_hash"] == result["manifest_hash"]
    assert binding["checksums_hash"] == result["checksums_hash"]
    assert binding["bundle_digest"] == result["bundle_digest"]
    assert binding["commit"] == result["commit"]
    assert binding["configuration_digest"] == result["configuration_digest"]
    assert binding["coverage_complete"] == result["coverage_complete"]
    assert binding["reconciliation_eligible"] == result["reconciliation_eligible"]
