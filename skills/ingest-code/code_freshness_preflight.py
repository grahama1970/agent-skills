"""Target-scoped code projection freshness preflight.

Inputs: a repository worktree, expected branch/commit identity, and one or more
repository-relative targets. Output: a deterministic JSON-compatible receipt
that states whether Memory/GMO's active code projection may be used for repair
guidance. Failure modes are explicit and fail closed; this module never talks
to ArangoDB or Qdrant directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Protocol


CODE_EXTENSIONS = {
    ".c",
    ".cpp",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".swift",
    ".ts",
    ".tsx",
}


class PreflightStatus(StrEnum):
    CURRENT = "CURRENT"
    SOURCE_CURRENT_INDEX_INCOMPLETE = "SOURCE_CURRENT_INDEX_INCOMPLETE"
    STALE = "STALE"
    UNINDEXED = "UNINDEXED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class TargetFreshness:
    path: str
    status: str
    current_hash: str | None
    indexed_hash: str | None
    modification_ready: bool
    current_source_available: bool
    indexed_record_count: int
    coverage_complete: bool | None = None
    absence_claims_allowed: bool = False
    source_path: str | None = None
    symbols: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PreflightReceipt:
    schema: str
    status: str
    generated_at: str
    read_only: bool
    repo: str
    root: str
    branch: str
    commit: str
    requested_branch: str
    requested_commit: str
    scope: str
    active_generation: dict[str, Any]
    coverage: dict[str, Any]
    target_paths: list[str]
    targets: list[dict[str, Any]]
    modification_ready: bool
    absence_claims_allowed: bool
    unresolved_limitations: list[str]
    errors: list[str]
    command_revision: dict[str, Any]


class ProjectionReader(Protocol):
    def code_coverage(self, *, scope: str, repo: str, branch: str) -> dict[str, Any]:
        """Return Memory/GMO active code coverage for the supplied identity."""

    def code_search(self, *, q: str, scope: str, repo: str, branch: str, limit: int) -> dict[str, Any]:
        """Return active code candidates for one target path query."""

    def code_node(self, *, symbol_id: str, scope: str, repo: str, branch: str) -> dict[str, Any]:
        """Return one active code node with source freshness metadata."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def git_value(repo: Path, args: list[str], default: str = "unknown") -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return default
    if result.returncode != 0:
        return default
    value = result.stdout.strip()
    return value or default


def git_is_clean(repo: Path) -> bool:
    return git_value(repo, ["status", "--porcelain"], "") == ""


def resolve_repo(repo: Path) -> Path:
    root = repo.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"repo path is not a directory: {root}")
    return root


def resolve_target_paths(repo: Path, targets: list[str], *, max_target_files: int = 200) -> list[str]:
    if not targets:
        raise ValueError("at least one --path target is required")

    resolved: list[str] = []
    root = repo.resolve()
    for raw in targets:
        if not raw or Path(raw).is_absolute():
            raise ValueError(f"target path must be repository-relative: {raw!r}")
        candidate = (root / raw).resolve()
        try:
            rel = candidate.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"target path escapes repository: {raw!r}") from exc
        if rel == "." or rel.startswith("../") or "/../" in f"/{rel}/":
            raise ValueError(f"target path is not allowed: {raw!r}")
        if candidate.is_dir():
            for item in sorted(candidate.rglob("*")):
                if item.is_file() and item.suffix in CODE_EXTENSIONS:
                    resolved.append(item.relative_to(root).as_posix())
        else:
            resolved.append(rel)
    unique = sorted(dict.fromkeys(resolved))
    if len(unique) > max_target_files:
        raise ValueError(f"target expansion too large: {len(unique)} files > {max_target_files}")
    return unique


def normalize_hash(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value.removeprefix("sha256:")


def extract_json(stdout: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    text = stdout.strip()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and not text[index + end :].strip():
            return parsed
    raise ValueError("command did not emit one JSON object")


class MemoryCliProjectionReader:
    """Read active code projection state through the Memory skill CLI boundary."""

    def __init__(self, memory_run_sh: Path | None = None, timeout_s: float = 30.0) -> None:
        default_run_sh = Path(__file__).resolve().parents[1] / "memory" / "run.sh"
        configured = os.environ.get("MEMORY_RUN_SH")
        selected = memory_run_sh or (Path(configured) if configured else default_run_sh)
        self.memory_run_sh = selected.resolve()
        self.timeout_s = timeout_s

    def _run(self, args: list[str]) -> dict[str, Any]:
        if not self.memory_run_sh.exists():
            raise RuntimeError(f"memory run.sh not found: {self.memory_run_sh}")
        result = subprocess.run(
            [str(self.memory_run_sh), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"memory command failed ({result.returncode}): {' '.join(args)} {detail}")
        return extract_json(result.stdout)

    def code_coverage(self, *, scope: str, repo: str, branch: str) -> dict[str, Any]:
        return self._run(["code-coverage", "--scope", scope, "--repo", repo, "--branch", branch])

    def code_search(self, *, q: str, scope: str, repo: str, branch: str, limit: int) -> dict[str, Any]:
        return self._run(
            [
                "code-search",
                "--q",
                q,
                "--scope",
                scope,
                "--repo",
                repo,
                "--branch",
                branch,
                "--limit",
                str(limit),
            ]
        )

    def code_node(self, *, symbol_id: str, scope: str, repo: str, branch: str) -> dict[str, Any]:
        return self._run(
            [
                "code-node",
                "--symbol-id",
                symbol_id,
                "--scope",
                scope,
                "--repo",
                repo,
                "--branch",
                branch,
                "--no-source",
            ]
        )


def _path_matches(candidate_path: str, target: str) -> bool:
    return candidate_path == target or candidate_path.endswith(f"/{target}")


def _coverage_complete(node: dict[str, Any]) -> bool | None:
    symbol = node.get("symbol") or {}
    file_doc = node.get("file") or {}
    for doc in (file_doc, symbol):
        value = doc.get("coverage_complete")
        if value is not None:
            return bool(value)
    return None


def _active_generation_from_node(node: dict[str, Any]) -> dict[str, Any]:
    symbol = node.get("symbol") or {}
    file_doc = node.get("file") or {}
    return {
        "code_index_id": file_doc.get("code_index_id") or symbol.get("code_index_id"),
        "generation_id": file_doc.get("generation_id") or symbol.get("generation_id"),
        "current_ingest_run": file_doc.get("current_ingest_run") or symbol.get("current_ingest_run"),
        "source_version_id": file_doc.get("source_version_id") or symbol.get("source_version_id"),
    }


def _target_from_node(repo: Path, target: str, search_items: list[dict[str, Any]], node: dict[str, Any]) -> TargetFreshness:
    file_doc = node.get("file") or {}
    symbol = node.get("symbol") or {}
    indexed_hash = normalize_hash(file_doc.get("source_hash") or symbol.get("content_hash"))
    source_path = repo / target
    current_hash = sha256_file(source_path)
    coverage_complete = _coverage_complete(node)
    limitations: list[str] = []

    if current_hash is None:
        status = PreflightStatus.BLOCKED.value
        limitations.append("current source is missing or unreadable")
    elif indexed_hash is None:
        status = PreflightStatus.BLOCKED.value
        limitations.append("active projection did not return an indexed source hash")
    elif current_hash != indexed_hash:
        status = PreflightStatus.STALE.value
        limitations.append("current source hash differs from the active Memory projection; do not edit from stored snippet")
    elif coverage_complete is False:
        status = PreflightStatus.SOURCE_CURRENT_INDEX_INCOMPLETE.value
        limitations.append("source hash matches but coverage is incomplete; callers/callees/impact absence claims are blocked")
    else:
        status = PreflightStatus.CURRENT.value

    generation = _active_generation_from_node(node)
    if not generation.get("generation_id"):
        limitations.append("Memory code navigation did not expose active generation_id")

    return TargetFreshness(
        path=target,
        status=status,
        current_hash=current_hash,
        indexed_hash=indexed_hash,
        modification_ready=status == PreflightStatus.CURRENT.value,
        current_source_available=current_hash is not None,
        indexed_record_count=len(search_items),
        coverage_complete=coverage_complete,
        absence_claims_allowed=status == PreflightStatus.CURRENT.value,
        source_path=str(source_path),
        symbols=[
            {
                "symbol_id": item.get("symbol_id") or item.get("stable_id"),
                "qualified_name": item.get("qualified_name"),
                "path": item.get("path"),
                "code_index_id": item.get("code_index_id"),
            }
            for item in search_items[:10]
        ],
        limitations=limitations,
    )


def _target_unindexed(repo: Path, target: str) -> TargetFreshness:
    current_hash = sha256_file(repo / target)
    return TargetFreshness(
        path=target,
        status=PreflightStatus.UNINDEXED.value,
        current_hash=current_hash,
        indexed_hash=None,
        modification_ready=False,
        current_source_available=current_hash is not None,
        indexed_record_count=0,
        coverage_complete=None,
        absence_claims_allowed=False,
        source_path=str(repo / target),
        limitations=["no active Memory/GMO code projection record matched this target path"],
    )


def _overall_status(targets: list[TargetFreshness], errors: list[str]) -> PreflightStatus:
    if errors or any(item.status == PreflightStatus.BLOCKED.value for item in targets):
        return PreflightStatus.BLOCKED
    if any(item.status == PreflightStatus.STALE.value for item in targets):
        return PreflightStatus.STALE
    if any(item.status == PreflightStatus.UNINDEXED.value for item in targets):
        return PreflightStatus.UNINDEXED
    if any(item.status == PreflightStatus.SOURCE_CURRENT_INDEX_INCOMPLETE.value for item in targets):
        return PreflightStatus.SOURCE_CURRENT_INDEX_INCOMPLETE
    return PreflightStatus.CURRENT


def run_preflight(
    *,
    repo: Path,
    branch: str,
    commit: str,
    targets: list[str],
    scope: str = "code",
    reader: ProjectionReader | None = None,
    memory_run_sh: Path | None = None,
    max_target_files: int = 200,
) -> dict[str, Any]:
    """Return a target-scoped code projection freshness receipt."""
    try:
        root = resolve_repo(repo)
        target_paths = resolve_target_paths(root, targets, max_target_files=max_target_files)
    except ValueError as exc:
        return asdict(
            PreflightReceipt(
                schema="ingest-code.code_projection_freshness.v1",
                status=PreflightStatus.BLOCKED.value,
                generated_at=utc_now(),
                read_only=True,
                repo=repo.name,
                root=str(repo),
                branch="unknown",
                commit="unknown",
                requested_branch=branch,
                requested_commit=commit,
                scope=scope,
                active_generation={},
                coverage={},
                target_paths=targets,
                targets=[],
                modification_ready=False,
                absence_claims_allowed=False,
                unresolved_limitations=[],
                errors=[str(exc)],
                command_revision=command_revision(),
            )
        )

    actual_branch = git_value(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    actual_commit = git_value(root, ["rev-parse", "HEAD"])
    repo_name = root.name
    errors: list[str] = []
    if branch and actual_branch != branch:
        errors.append(f"branch mismatch: requested={branch} actual={actual_branch}")
    if commit and actual_commit != commit:
        errors.append(f"commit mismatch: requested={commit} actual={actual_commit}")

    active_generation: dict[str, Any] = {}
    coverage: dict[str, Any] = {}
    target_results: list[TargetFreshness] = []
    projection_reader = reader or MemoryCliProjectionReader(memory_run_sh=memory_run_sh)

    if not errors:
        try:
            coverage = projection_reader.code_coverage(scope=scope, repo=repo_name, branch=actual_branch)
            for target in target_paths:
                search = projection_reader.code_search(q=target, scope=scope, repo=repo_name, branch=actual_branch, limit=50)
                items = [
                    item
                    for item in list(search.get("items") or [])
                    if _path_matches(str(item.get("path") or ""), target)
                ]
                if not items:
                    target_results.append(_target_unindexed(root, target))
                    continue
                symbol_id = str(items[0].get("symbol_id") or items[0].get("stable_id") or "")
                if not symbol_id:
                    target_results.append(
                        TargetFreshness(
                            path=target,
                            status=PreflightStatus.BLOCKED.value,
                            current_hash=sha256_file(root / target),
                            indexed_hash=None,
                            modification_ready=False,
                            current_source_available=(root / target).exists(),
                            indexed_record_count=len(items),
                            source_path=str(root / target),
                            limitations=["active projection candidate did not expose symbol_id/stable_id"],
                        )
                    )
                    continue
                node = projection_reader.code_node(symbol_id=symbol_id, scope=scope, repo=repo_name, branch=actual_branch)
                target_result = _target_from_node(root, target, items, node)
                target_results.append(target_result)
                if not active_generation:
                    active_generation = _active_generation_from_node(node)
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
            errors.append(str(exc))

    status = _overall_status(target_results, errors)
    limitations: list[str] = []
    for item in target_results:
        limitations.extend(item.limitations)
    if status == PreflightStatus.UNINDEXED:
        limitations.append("refresh is required before Memory code projection can guide this target")
    if status == PreflightStatus.STALE:
        limitations.append("use current source bytes, not Memory stored snippets, until projection refresh succeeds")

    return asdict(
        PreflightReceipt(
            schema="ingest-code.code_projection_freshness.v1",
            status=status.value,
            generated_at=utc_now(),
            read_only=True,
            repo=repo_name,
            root=str(root),
            branch=actual_branch,
            commit=actual_commit,
            requested_branch=branch,
            requested_commit=commit,
            scope=scope,
            active_generation=active_generation,
            coverage=coverage,
            target_paths=target_paths,
            targets=[asdict(item) for item in target_results],
            modification_ready=status == PreflightStatus.CURRENT,
            absence_claims_allowed=status == PreflightStatus.CURRENT,
            unresolved_limitations=sorted(dict.fromkeys(limitations)),
            errors=errors,
            command_revision=command_revision(),
        )
    )


def refresh_allowed(
    *,
    repo: Path,
    branch: str,
    commit: str,
    canonical_branch: str = "main",
) -> tuple[bool, list[str]]:
    """Return whether this checkout may activate a canonical code projection."""
    root = resolve_repo(repo)
    actual_branch = git_value(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    actual_commit = git_value(root, ["rev-parse", "HEAD"])
    errors: list[str] = []
    if actual_branch != canonical_branch:
        errors.append(f"canonical refresh requires branch {canonical_branch}; actual={actual_branch}")
    if branch and branch != canonical_branch:
        errors.append(f"requested branch is not canonical: {branch}")
    if commit and actual_commit != commit:
        errors.append(f"commit mismatch blocks refresh: requested={commit} actual={actual_commit}")
    if not git_is_clean(root):
        errors.append("canonical refresh requires a clean worktree")
    return not errors, errors


def command_revision() -> dict[str, Any]:
    skill_root = Path(__file__).resolve().parent
    return {
        "skill": "ingest-code",
        "module": "code_freshness_preflight.py",
        "module_sha256": sha256_file(Path(__file__).resolve()),
        "skill_commit": git_value(skill_root, ["rev-parse", "HEAD"]),
    }
