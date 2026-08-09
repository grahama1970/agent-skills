"""File-component cache tests for complete ingest-code bundles."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from code_symbol_record import CodeSymbolRecord  # noqa: E402
from incremental_state import (  # noqa: E402
    FileComponentState,
    build_transform_fingerprints,
    component_key,
    source_fingerprint,
)
import ingest_code  # noqa: E402


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "agent@example.invalid")
    _git(repo, "config", "user.name", "Agent")
    return repo


def _fingerprints(repo: Path) -> dict[str, str]:
    return build_transform_fingerprints(SKILL_ROOT, scope="code", patterns=["*.py"], scan_roots=["."])


def _symbol(repo: Path, *, path: str = "app.py", name: str = "app", content_hash: str = "h1") -> CodeSymbolRecord:
    return CodeSymbolRecord(
        scope="code",
        repo=repo.name,
        root=str(repo),
        branch="main",
        commit="abc123",
        path=path,
        language="python",
        symbol_kind="function",
        symbol_name=name,
        qualified_name=name,
        start_line=1,
        end_line=2,
        signature=f"def {name}(): ...",
        code=f"def {name}():\n    return 1",
        content_hash=content_hash,
    )


def test_source_fingerprint_uses_git_blob_for_clean_tracked_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "initial")

    fingerprint = source_fingerprint(source, repo)

    assert fingerprint.startswith("git-blob:")
    source.write_text("def app():\n    return 2\n", encoding="utf-8")
    assert source_fingerprint(source, repo).startswith("sha256:")


def test_component_cache_reuses_only_matching_source_and_transform(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n", encoding="utf-8")
    fingerprints = _fingerprints(repo)
    state = FileComponentState(repo / "artifacts/ingest-code/incremental-components.json", repo=repo.name, branch="main", transform_fingerprints=fingerprints)
    current = {"app.py": source_fingerprint(source, repo)}
    record = _symbol(repo)
    state.commit(
        current_sources=current,
        symbols_by_path={"app.py": [record.__dict__]},
        bundle_digest="sha256:bundle",
        accepted_complete_bundle=True,
        receipt={"schema": "test"},
    )

    replay = FileComponentState(state.state_path, repo=repo.name, branch="main", transform_fingerprints=fingerprints)
    plan = replay.plan([source], repo)
    assert plan.reused == ("app.py",)
    assert plan.to_parse == ()
    assert replay.reused_symbols(plan.reused)[0]["symbol_name"] == "app"

    changed_transform = dict(fingerprints)
    changed_transform["typed_edge_resolver"] = "sha256:changed"
    stale = FileComponentState(state.state_path, repo=repo.name, branch="main", transform_fingerprints=changed_transform)
    stale_plan = stale.plan([source], repo)
    assert stale_plan.changed == ("app.py",)
    assert stale_plan.miss_reasons["app.py"] == "transform_fingerprint_changed"

    source.write_text("def app():\n    return 2\n", encoding="utf-8")
    edited = FileComponentState(state.state_path, repo=repo.name, branch="main", transform_fingerprints=fingerprints)
    edited_plan = edited.plan([source], repo)
    assert edited_plan.changed == ("app.py",)
    assert edited_plan.miss_reasons["app.py"] == "source_fingerprint_changed"


def test_deleted_and_incomplete_prior_bundle_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n", encoding="utf-8")
    fingerprints = _fingerprints(repo)
    state = FileComponentState(repo / "artifacts/ingest-code/incremental-components.json", repo=repo.name, branch="main", transform_fingerprints=fingerprints)
    state.commit(
        current_sources={"app.py": source_fingerprint(source, repo)},
        symbols_by_path={"app.py": [_symbol(repo).__dict__]},
        bundle_digest="sha256:bundle",
        accepted_complete_bundle=False,
        receipt={"schema": "test"},
    )

    incomplete = FileComponentState(state.state_path, repo=repo.name, branch="main", transform_fingerprints=fingerprints)
    plan = incomplete.plan([source], repo)
    assert plan.changed == ("app.py",)
    assert plan.miss_reasons["app.py"] == "prior_bundle_not_complete"

    deleted_plan = incomplete.plan([], repo)
    assert deleted_plan.deleted == ("app.py",)


def test_corrupt_component_hash_recomputes_exact_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n", encoding="utf-8")
    fingerprints = _fingerprints(repo)
    state = FileComponentState(repo / "artifacts/ingest-code/incremental-components.json", repo=repo.name, branch="main", transform_fingerprints=fingerprints)
    state.commit(
        current_sources={"app.py": source_fingerprint(source, repo)},
        symbols_by_path={"app.py": [_symbol(repo).__dict__]},
        bundle_digest="sha256:bundle",
        accepted_complete_bundle=True,
        receipt={"schema": "test"},
    )
    payload = json.loads(state.state_path.read_text(encoding="utf-8"))
    payload["components"]["app.py"]["component_hash"] = "sha256:bad"
    state.state_path.write_text(json.dumps(payload), encoding="utf-8")

    corrupt = FileComponentState(state.state_path, repo=repo.name, branch="main", transform_fingerprints=fingerprints)
    plan = corrupt.plan([source], repo)
    assert plan.changed == ("app.py",)
    assert plan.miss_reasons["app.py"] == "component_hash_mismatch"


def test_scan_component_helpers_rehydrate_cached_records(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n", encoding="utf-8")
    record = _symbol(repo)
    fingerprints = _fingerprints(repo)
    state = FileComponentState(repo / "artifacts/ingest-code/incremental-components.json", repo=repo.name, branch="main", transform_fingerprints=fingerprints)
    state.commit(
        current_sources={"app.py": source_fingerprint(source, repo)},
        symbols_by_path={"app.py": [record.__dict__]},
        bundle_digest="sha256:bundle",
        accepted_complete_bundle=True,
        receipt={"schema": "test"},
    )
    plan = state.plan([source], repo)
    cached = [
        ingest_code._record_from_component_payload(payload)
        for payload in state.reused_symbols(plan.reused)
    ]

    assert plan.reused == ("app.py",)
    assert cached == [record]
    assert component_key(repo.name, "main", "app.py").startswith("fc_")
