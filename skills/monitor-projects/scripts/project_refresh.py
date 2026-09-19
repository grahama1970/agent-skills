"""Refresh source-backed project Q&A through Memory's governed lifecycle.

Inputs are the Project Watchdog registry, per-repository git history, and the
Memory HTTP API. Outputs are deterministic ``project_activity`` evidence rows
and active ``project_memory_versions`` records. Failures are explicit and do
not advance the caller's project watermark.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field


class RegistryProject(BaseModel):
    """The registry fields needed by Monitor Projects."""

    model_config = ConfigDict(extra="ignore")

    project_id: str = Field(min_length=1)
    worktree: Path
    status: str = "registered"


class RegistryDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    projects: list[RegistryProject]


class UpsertReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: str
    inserted: int = Field(ge=0)
    updated: int = Field(ge=0)
    errors: list[Any]
    total: int = Field(ge=0)
    writeahead_path: str | None = None


class StageReceipt(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_name: str = Field(alias="schema")
    ok: bool
    status: str
    candidate_ref: str | None = None
    run_ref: str | None = None
    reason: str | None = None


class PromoteReceipt(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_name: str = Field(alias="schema")
    ok: bool
    status: str
    candidate_ref: str | None = None
    head_ref: str | None = None
    generation: int | None = None
    reason: str | None = None


class StatusReceipt(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_name: str = Field(alias="schema")
    ok: bool
    project_id: str
    topic_id: str | None = None
    heads: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    versions: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ProjectCommit:
    project_id: str
    repo_root: Path
    sha: str
    committed_at: str
    subject: str
    body: str
    changed_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectSelection:
    project_id: str
    repo_root: Path
    before_sha: str | None
    head_sha: str
    commits: tuple[ProjectCommit, ...]


def _run_git(repo: Path, args: list[str], timeout: int = 180) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("git command failed in {}: {}", repo, exc)
        raise RuntimeError(f"git command failed: {args[0]}") from exc
    if result.returncode != 0:
        logger.error("git {} failed in {}: {}", args[0], repo, result.stderr.strip()[:400])
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()[:200]}")
    return result.stdout.strip()


def load_registered_projects(registry_path: Path) -> list[RegistryProject]:
    """Validate the Project Watchdog registry and deduplicate repository roots."""
    registry = RegistryDocument.model_validate_json(registry_path.read_text(encoding="utf-8"))
    seen: set[Path] = set()
    projects: list[RegistryProject] = []
    for project in registry.projects:
        if project.status not in {"registered", "active"}:
            continue
        root = Path(_run_git(project.worktree, ["rev-parse", "--show-toplevel"])).resolve()
        if root in seen:
            continue
        seen.add(root)
        projects.append(project.model_copy(update={"worktree": root}))
    return projects


def discover_project_commits(
    project: RegistryProject,
    before_sha: str | None,
    since_hours: int,
) -> ProjectSelection:
    """Fetch and enumerate unprocessed commits from ``origin/main``."""
    repo = project.worktree.resolve()
    _run_git(repo, ["fetch", "-q", "origin", "main"])
    head = _run_git(repo, ["rev-parse", "origin/main"])
    rev_args: list[str]
    if before_sha:
        present = subprocess.run(
            ["git", "cat-file", "-e", f"{before_sha}^{{commit}}"], cwd=repo,
            capture_output=True, timeout=30, check=False,
        ).returncode == 0
        if not present:
            raise RuntimeError(f"project watermark is unavailable: {before_sha}")
        rev_args = [f"{before_sha}..{head}"]
    else:
        rev_args = [head, f"--since={since_hours} hours ago"]
    shas = _run_git(repo, ["rev-list", "--reverse", *rev_args]).splitlines()
    commits: list[ProjectCommit] = []
    for sha in shas:
        fields = _run_git(repo, ["show", "-s", "--format=%cI%x00%s%x00%b", sha]).split("\x00", 2)
        paths = tuple(
            line for line in _run_git(repo, ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", sha]).splitlines()
            if line
        )
        commits.append(ProjectCommit(
            project_id=project.project_id,
            repo_root=repo,
            sha=sha,
            committed_at=fields[0],
            subject=fields[1],
            body=fields[2].strip() if len(fields) > 2 else "",
            changed_paths=paths,
        ))
    return ProjectSelection(project.project_id, repo, before_sha, head, tuple(commits))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _activity_document(commit: ProjectCommit) -> dict[str, Any]:
    key = "project_commit_" + _digest(f"{commit.repo_root}:{commit.sha}")[:40]
    source_ref = f"git:{commit.repo_root}@{commit.sha}"
    retrieval = f"{commit.project_id} commit {commit.sha[:12]}: {commit.subject}. Files: {', '.join(commit.changed_paths)}"
    return {
        "_key": key,
        "schema": "project_activity.git_commit.v1",
        "record_kind": "git_commit",
        "project": commit.project_id,
        "project_id": commit.project_id,
        "scope": commit.project_id,
        "repo_path": str(commit.repo_root),
        "commit_sha": commit.sha,
        "commit_short": commit.sha[:12],
        "commit_subject": commit.subject,
        "commit_body": commit.body,
        "committed_at": commit.committed_at,
        "activity_date": commit.committed_at[:10],
        "files_changed": list(commit.changed_paths),
        "source_refs": [source_ref],
        "content_sha256": "sha256:" + _digest(retrieval),
        "retrieval_text": retrieval,
        "tags": [f"project:{commit.project_id}", "project-activity", "git-commit"],
    }


def _version_document(commit: ProjectCommit, evidence: dict[str, Any]) -> dict[str, Any]:
    topic_id = f"commit:{commit.sha}"
    key = "pmv_" + _digest(f"{commit.project_id}:{topic_id}:{evidence['content_sha256']}")[:40]
    question = f"What changed in {commit.project_id} at commit {commit.sha[:12]}?"
    changed = ", ".join(f"`{path}`" for path in commit.changed_paths) or "no paths reported"
    answer = f"{commit.subject}. Changed paths: {changed}."
    if commit.body:
        answer += f" Commit detail: {commit.body}"
    return {
        "_key": key,
        "schema": "project_memory.version.v1",
        "record_kind": "project_memory_version",
        "project_id": commit.project_id,
        "scope_key": commit.project_id,
        "topic_id": topic_id,
        "topic_kind": "commit_question_answer",
        "title": question,
        "question": question,
        "answer": answer,
        "text": answer,
        "summary": commit.subject,
        "status": "candidate",
        "is_current": False,
        "last_verified_commit": commit.sha,
        "source_commit": commit.sha,
        "source_refs": evidence["source_refs"],
        "claims": [{
            "text": answer,
            "evidence_refs": [f"project_activity/{evidence['_key']}"],
            "evidence_digest": evidence["content_sha256"],
        }],
        "retrieval_text": f"{question}\n{answer}",
        "generated_by": {"skill": "monitor-projects", "mode": "deterministic_git_projection"},
        "tags": [f"project:{commit.project_id}", "project-memory", "question-answer", "git-commit"],
    }


def _post(client: httpx.Client, path: str, payload: dict[str, Any], model: type[BaseModel]) -> BaseModel:
    response = client.post(path, json=payload)
    response.raise_for_status()
    return model.model_validate(response.json())


def persist_commit_question(client: httpx.Client, commit: ProjectCommit, run_id: str) -> str:
    """Store evidence, stage/promote Q&A, then read back the exact active head."""
    evidence = _activity_document(commit)
    upsert = _post(
        client, "/upsert", {"collection": "project_activity", "documents": [evidence]}, UpsertReceipt,
    )
    if upsert.total != 1 or upsert.errors:
        raise RuntimeError(f"project_activity upsert incomplete for {commit.sha}")

    version = _version_document(commit, evidence)
    topic_id = version["topic_id"]
    status = _post(
        client, "/project-memory/status",
        {"project_id": commit.project_id, "topic_id": topic_id, "include_history": True},
        StatusReceipt,
    )
    candidate_ref = f"project_memory_versions/{version['_key']}"
    if status.heads:
        head = status.heads[0]
        if head.get("active_version_ref") == candidate_ref:
            return candidate_ref
        raise RuntimeError(f"unexpected existing project-memory head for {commit.project_id}/{topic_id}")

    stage = _post(client, "/project-memory/stage", {
        "candidate": version,
        "run": {
            "_key": "pmr_" + _digest(f"{run_id}:{commit.project_id}:{commit.sha}")[:40],
            "project_id": commit.project_id,
            "scope_key": commit.project_id,
            "status": "staging",
            "source_commit": commit.sha,
        },
        "evidence_refs": [{
            "ref": f"project_activity/{evidence['_key']}",
            "digest": evidence["content_sha256"],
        }],
    }, StageReceipt)
    if not stage.ok or not stage.candidate_ref:
        raise RuntimeError(f"project-memory stage blocked: {stage.reason or stage.status}")

    promoted = _post(client, "/project-memory/promote", {
        "candidate_ref": stage.candidate_ref,
        "expected_head": {"project_id": commit.project_id, "topic_id": topic_id, "generation": 0},
        "run_ref": stage.run_ref,
        "policy_receipt_ref": f"project_activity/{evidence['_key']}",
        "approval_required": False,
    }, PromoteReceipt)
    if not promoted.ok or promoted.status != "promoted":
        raise RuntimeError(f"project-memory promote blocked: {promoted.reason or promoted.status}")

    readback = _post(client, "/project-memory/status", {
        "project_id": commit.project_id, "topic_id": topic_id, "include_history": True,
    }, StatusReceipt)
    if not readback.heads or readback.heads[0].get("active_version_ref") != stage.candidate_ref:
        raise RuntimeError(f"project-memory exact read-back failed for {commit.project_id}/{topic_id}")
    if readback.heads[0].get("active_version_digest") != next(
        (item.get("source_digest") for item in readback.versions if item.get("_key") == version["_key"]), None
    ):
        raise RuntimeError(f"project-memory digest read-back failed for {commit.project_id}/{topic_id}")
    return stage.candidate_ref


def refresh_registered_projects(
    registry_path: Path,
    watermark_getter,
    watermark_writer,
    run_id: str,
    memory_url: str,
    since_hours: int = 24,
) -> list[dict[str, Any]]:
    """Refresh each registered repository independently and advance proven watermarks."""
    results: list[dict[str, Any]] = []
    timeout = httpx.Timeout(connect=5.0, read=90.0, write=30.0, pool=5.0)
    with httpx.Client(base_url=memory_url, timeout=timeout) as client:
        for project in load_registered_projects(registry_path):
            before = watermark_getter(project.worktree, "project_qa_last_sha")
            try:
                selection = discover_project_commits(project, before, since_hours)
                refs = [persist_commit_question(client, commit, run_id) for commit in selection.commits]
                watermark_writer(project.worktree, selection.head_sha, run_id, "project_qa_last_sha")
                results.append({
                    "project_id": project.project_id,
                    "repo_root": str(project.worktree),
                    "before_sha": before,
                    "head_sha": selection.head_sha,
                    "commits_detected": len(selection.commits),
                    "project_memory_refs": refs,
                    "status": "stored_verified",
                    "watermark_advanced": True,
                })
            except (httpx.HTTPError, RuntimeError, ValueError, OSError) as exc:
                logger.error("project refresh failed for {}: {}", project.project_id, exc)
                results.append({
                    "project_id": project.project_id,
                    "repo_root": str(project.worktree),
                    "before_sha": before,
                    "status": "NEEDS_ATTENTION",
                    "error": str(exc),
                    "watermark_advanced": False,
                })
    return results
