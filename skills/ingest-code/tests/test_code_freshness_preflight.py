"""Regression tests for target-scoped code projection freshness preflight."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

spec = importlib.util.spec_from_file_location(
    "code_freshness_preflight",
    MODULE_DIR / "code_freshness_preflight.py",
)
assert spec and spec.loader
code_freshness_preflight = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = code_freshness_preflight
spec.loader.exec_module(code_freshness_preflight)


class FakeProjectionReader:
    def __init__(
        self,
        *,
        repo: Path,
        indexed_hashes: dict[str, str],
        coverage_complete: bool = True,
        raise_error: str = "",
    ) -> None:
        self.repo = repo
        self.indexed_hashes = indexed_hashes
        self.coverage_complete = coverage_complete
        self.raise_error = raise_error
        self.coverage_calls = 0
        self.search_calls = 0
        self.node_calls = 0

    def code_coverage(self, *, scope: str, repo: str, branch: str) -> dict[str, Any]:
        self.coverage_calls += 1
        if self.raise_error:
            raise RuntimeError(self.raise_error)
        return {
            "status": "ok",
            "coverage": {
                "files": [{"code_index_id": repo, "branch": branch, "run_id": "run-current", "file_count": 1}],
                "symbols": len(self.indexed_hashes),
                "resolved_edges": 1,
            },
            "unresolved_limitations": [],
        }

    def code_search(self, *, q: str, scope: str, repo: str, branch: str, limit: int) -> dict[str, Any]:
        self.search_calls += 1
        if q not in self.indexed_hashes:
            return {"status": "ok", "items": []}
        return {
            "status": "ok",
            "items": [
                {
                    "symbol_id": f"sym-{q}",
                    "stable_id": f"sym-{q}",
                    "qualified_name": "app",
                    "path": q,
                    "code_index_id": repo,
                }
            ],
        }

    def code_node(self, *, symbol_id: str, scope: str, repo: str, branch: str) -> dict[str, Any]:
        self.node_calls += 1
        rel_path = symbol_id.removeprefix("sym-")
        return {
            "status": "ok",
            "symbol": {
                "symbol_id": symbol_id,
                "qualified_name": "app",
                "path": rel_path,
                "code_index_id": repo,
                "generation_id": "cg-current",
                "current_ingest_run": "run-current",
                "coverage_complete": self.coverage_complete,
            },
            "file": {
                "path": rel_path,
                "source_hash": self.indexed_hashes[rel_path],
                "code_index_id": repo,
                "generation_id": "cg-current",
                "current_ingest_run": "run-current",
                "coverage_complete": self.coverage_complete,
            },
            "freshness": {"status": "current"},
        }


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "codex@example.invalid")
    _git(repo, "config", "user.name", "Codex")
    (repo / "app.py").write_text("def app():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "seed")
    return repo


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def _hash(repo: Path, rel_path: str = "app.py") -> str:
    return code_freshness_preflight.sha256_file(repo / rel_path) or ""


def test_current_active_target_hash_is_read_only_current(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    reader = FakeProjectionReader(repo=repo, indexed_hashes={"app.py": _hash(repo)})

    receipt = code_freshness_preflight.run_preflight(
        repo=repo,
        branch="main",
        commit=_head(repo),
        targets=["app.py"],
        reader=reader,
    )

    assert receipt["status"] == "CURRENT"
    assert receipt["read_only"] is True
    assert receipt["modification_ready"] is True
    assert reader.coverage_calls == 1
    assert reader.search_calls == 1
    assert reader.node_calls == 1


def test_changed_target_source_is_stale_and_not_modification_ready(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    indexed_hash = _hash(repo)
    (repo / "app.py").write_text("def app():\n    return 2\n", encoding="utf-8")
    reader = FakeProjectionReader(repo=repo, indexed_hashes={"app.py": indexed_hash})

    receipt = code_freshness_preflight.run_preflight(
        repo=repo,
        branch="main",
        commit=_head(repo),
        targets=["app.py"],
        reader=reader,
    )

    assert receipt["status"] == "STALE"
    assert receipt["modification_ready"] is False
    assert receipt["targets"][0]["current_hash"] != receipt["targets"][0]["indexed_hash"]
    assert "do not edit from stored snippet" in " ".join(receipt["targets"][0]["limitations"])


def test_current_source_with_incomplete_coverage_blocks_absence_claims(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    reader = FakeProjectionReader(repo=repo, indexed_hashes={"app.py": _hash(repo)}, coverage_complete=False)

    receipt = code_freshness_preflight.run_preflight(
        repo=repo,
        branch="main",
        commit=_head(repo),
        targets=["app.py"],
        reader=reader,
    )

    assert receipt["status"] == "SOURCE_CURRENT_INDEX_INCOMPLETE"
    assert receipt["modification_ready"] is False
    assert receipt["absence_claims_allowed"] is False
    assert "coverage is incomplete" in " ".join(receipt["unresolved_limitations"])


def test_no_active_generation_for_target_is_unindexed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    reader = FakeProjectionReader(repo=repo, indexed_hashes={})

    receipt = code_freshness_preflight.run_preflight(
        repo=repo,
        branch="main",
        commit=_head(repo),
        targets=["app.py"],
        reader=reader,
    )

    assert receipt["status"] == "UNINDEXED"
    assert receipt["targets"][0]["indexed_record_count"] == 0
    assert receipt["modification_ready"] is False


def test_wrong_identity_and_path_escape_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    reader = FakeProjectionReader(repo=repo, indexed_hashes={"app.py": _hash(repo)})

    wrong_branch = code_freshness_preflight.run_preflight(
        repo=repo,
        branch="feature",
        commit=_head(repo),
        targets=["app.py"],
        reader=reader,
    )
    escaped = code_freshness_preflight.run_preflight(
        repo=repo,
        branch="main",
        commit=_head(repo),
        targets=["../outside.py"],
        reader=reader,
    )

    assert wrong_branch["status"] == "BLOCKED"
    assert "branch mismatch" in wrong_branch["errors"][0]
    assert escaped["status"] == "BLOCKED"
    assert "escapes repository" in escaped["errors"][0]


def test_repair_branch_cannot_refresh_canonical_main(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-b", "repair/issue")

    allowed, errors = code_freshness_preflight.refresh_allowed(
        repo=repo,
        branch="repair/issue",
        commit=_head(repo),
        canonical_branch="main",
    )

    assert allowed is False
    assert any("canonical refresh requires branch main" in error for error in errors)


def test_dirty_main_cannot_refresh_canonical_projection(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("def app():\n    return 99\n", encoding="utf-8")

    allowed, errors = code_freshness_preflight.refresh_allowed(
        repo=repo,
        branch="main",
        commit=_head(repo),
        canonical_branch="main",
    )

    assert allowed is False
    assert "clean worktree" in " ".join(errors)


def test_stable_selected_identities_and_hashes_across_unchanged_preflight(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    reader = FakeProjectionReader(repo=repo, indexed_hashes={"app.py": _hash(repo)})

    first = code_freshness_preflight.run_preflight(
        repo=repo,
        branch="main",
        commit=_head(repo),
        targets=["app.py"],
        reader=reader,
    )
    second = code_freshness_preflight.run_preflight(
        repo=repo,
        branch="main",
        commit=_head(repo),
        targets=["app.py"],
        reader=reader,
    )

    for key in ("status", "repo", "branch", "commit", "target_paths", "targets", "active_generation"):
        assert first[key] == second[key]


def test_memory_boundary_error_blocks_without_generic_fallback(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    reader = FakeProjectionReader(repo=repo, indexed_hashes={"app.py": _hash(repo)}, raise_error="service down")

    receipt = code_freshness_preflight.run_preflight(
        repo=repo,
        branch="main",
        commit=_head(repo),
        targets=["app.py"],
        reader=reader,
    )

    assert receipt["status"] == "BLOCKED"
    assert receipt["errors"] == ["service down"]
