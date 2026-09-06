#!/usr/bin/env python3
"""Prepare and verify an immutable Persona Dream revision through Memory.

This command is deliberately bounded to revision persistence.  It never mutates
an active revision pointer, repair queue, provider state, or Persona Dream media.
"""

from __future__ import annotations

from pydantic_step_gate import validate_http_json

import argparse
import hashlib
import json
import os
import platform
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

import httpx
from pydantic_step_gate import pydantic_error_messages
from jsonschema import Draft202012Validator

from idea_lineage import (
    IdeaLineage,
    IdeaLineageError,
    validate_revision_idea_lineage,
)

DEFAULT_MEMORY_URL = "http://127.0.0.1:8601"
DEFAULT_COLLECTION = "project_knowledge"
PREPARE_RECEIPT_NAME = "revision_memory_prepare_receipt.json"
VERIFY_RECEIPT_NAME = "revision_memory_verify_receipt.json"
INDEX_NAME = "revision_artifact_index.json"
MANIFEST_NAME = "revision_manifest.json"
SOURCE_COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
IDENTITY_RE = re.compile(r"^[A-Za-z0-9._-]+$")

REQUIRED_ARTIFACTS_BY_PHASE: dict[str, tuple[str, ...]] = {
    "01": ("dream_request", "residue_links"),
    "02": ("story_contract",),
    "03": ("crew_contract", "crew_gate_receipt"),
    "04": (
        "contact_sheet_requirements",
        "contact_sheet_manifest",
        "contact_sheet_gate_receipt",
    ),
    "05": ("voice_evidence",),
    "06": ("script_contract",),
    "07": ("storyboard_packet",),
    "08": ("media_lock",),
    "09": ("video_provider_scorecard", "provider_final_gate"),
    "10": ("panel_distillation_contract", "provider_schema_receipt"),
}
PHASE_TITLES: dict[str, str] = {
    "01": "Idea and Memory Residue",
    "02": "Story",
    "03": "Crew",
    "04": "Contact Sheets",
    "05": "Voices",
    "06": "Script",
    "07": "Storyboard",
    "08": "Media Lock",
    "09": "Video Provider",
    "10": "Provider Distillation",
}
REQUIRED_ARTIFACT_IDS = tuple(
    artifact_id
    for phase_id in sorted(REQUIRED_ARTIFACTS_BY_PHASE)
    for artifact_id in REQUIRED_ARTIFACTS_BY_PHASE[phase_id]
)
EXPECTED_PHASE_IDS = tuple(sorted(REQUIRED_ARTIFACTS_BY_PHASE))
EXPECTED_RECORD_COUNT = 1 + len(EXPECTED_PHASE_IDS) + len(REQUIRED_ARTIFACT_IDS)

# Qualification records are identified by their record identity, NOT by raw
# (run_id, revision_id) keyspace membership.  The same keyspace legitimately
# holds governance/audit records (kind persona_dream_governance_audit and
# similar).  A record is a qualification record only when its schema,
# record_type, AND stable-key prefix all agree.  Selecting by these fields keeps
# the exact-match gate provably strict for the 27 qualification records while
# ignoring governance records the deletion-free Memory store cannot relocate.
QUALIFICATION_SCHEMA_RECORD_TYPES: dict[str, str] = {
    "persona_dream.pipeline_revision.v1": "revision",
    "persona_dream.pipeline_phase.v1": "phase",
    "persona_dream.pipeline_artifact_ref.v1": "required_artifact",
}
QUALIFICATION_RECORD_TYPES = frozenset(QUALIFICATION_SCHEMA_RECORD_TYPES.values())
# stable_memory_key() emits these prefixes; map each back to its record_type.
QUALIFICATION_KEY_PREFIXES: dict[str, str] = {
    "pd_rev_": "revision",
    "pd_phase_": "phase",
    "pd_artifact_": "required_artifact",
}

SERVER_OWNED_FIELDS = {
    "_id",
    "_rev",
    "qdrant_collection",
    "qdrant_point_id",
    "embedding_model",
    "embedding_version",
    "text_hash",
    "semantic_sync_state",
    "semantic_sync_error",
}
FORBIDDEN_VECTOR_FIELDS = {
    "embedding",
    "embedding_visual",
    "embedding_2",
    "embedding_multimodal",
    "vector",
    "vectors",
    "dense_vector",
    "text_vector",
    "image_vector",
}
SEMANTIC_REQUIRED_FIELDS = (
    "qdrant_collection",
    "qdrant_point_id",
    "embedding_model",
    "embedding_version",
    "text_hash",
    "semantic_sync_state",
)


class GateBlocked(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        details: Mapping[str, Any] | None = None,
        exit_code: int = 2,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})
        self.exit_code = exit_code


class MemoryCallFailed(GateBlocked):
    def __init__(
        self,
        code: str,
        *,
        endpoint: str,
        status_code: int | None,
        request_sha256: str,
        response_text: str,
        exit_code: int = 4,
    ) -> None:
        super().__init__(
            code,
            details={
                "endpoint": endpoint,
                "status_code": status_code,
                "request_sha256": request_sha256,
                "response_excerpt": response_text[:4000],
            },
            exit_code=exit_code,
        )


@dataclass(frozen=True)
class HttpEvidence:
    endpoint: str
    status_code: int
    request_sha256: str
    response_sha256: str
    response: dict[str, Any]


@dataclass(frozen=True)
class HashValidation:
    artifact_count: int
    recomputed_count: int
    matched_count: int
    mismatch_count: int
    symlink_count: int
    escape_count: int
    artifact_hash_manifest_sha256: str


@dataclass(frozen=True)
class RevisionSnapshot:
    run_root: Path
    revision_root: Path
    run_id: str
    revision_id: str
    source_revision_id: str
    source_commit: str
    runtime_release_id: str
    index_path: Path
    manifest_path: Path
    index: dict[str, Any]
    manifest: dict[str, Any]
    index_sha256: str
    manifest_sha256: str
    artifacts: dict[str, dict[str, Any]]
    hash_validation: HashValidation
    idea_lineage: IdeaLineage


class MemoryClient:
    def __init__(
        self,
        base_url: str,
        *,
        connect_timeout: float,
        read_timeout: float,
    ) -> None:
        timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=read_timeout,
            pool=connect_timeout,
        )
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    def __enter__(self) -> "MemoryClient":
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def post(self, endpoint: str, payload: dict[str, Any]) -> HttpEvidence:
        request_sha256 = sha256_json(payload)
        try:
            response = self._client.post(endpoint, json=payload)
        except httpx.TimeoutException as exc:
            raise MemoryCallFailed(
                "BLOCKED_MEMORY_HTTP_TIMEOUT",
                endpoint=endpoint,
                status_code=None,
                request_sha256=request_sha256,
                response_text=str(exc),
            ) from exc
        except httpx.RequestError as exc:
            raise MemoryCallFailed(
                "BLOCKED_MEMORY_HTTP_UNREACHABLE",
                endpoint=endpoint,
                status_code=None,
                request_sha256=request_sha256,
                response_text=str(exc),
            ) from exc

        response_text = response.text
        try:
            body = validate_http_json("memory_generic", response.json()) if response_text else {}
        except ValueError:
            body = {"raw_text": response_text}
        if not isinstance(body, dict):
            body = {"value": body}

        if response.status_code >= 400:
            code = (
                "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED"
                if endpoint == "/upsert" and is_semantic_failure(response_text)
                else "BLOCKED_MEMORY_HTTP_ERROR"
            )
            raise MemoryCallFailed(
                code,
                endpoint=endpoint,
                status_code=response.status_code,
                request_sha256=request_sha256,
                response_text=response_text,
                exit_code=3 if code == "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED" else 4,
            )

        return HttpEvidence(
            endpoint=endpoint,
            status_code=response.status_code,
            request_sha256=request_sha256,
            response_sha256=sha256_bytes(response.content),
            response=body,
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateBlocked(
            "BLOCKED_REVISION_JSON_INVALID",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    if not isinstance(value, dict):
        raise GateBlocked(
            "BLOCKED_REVISION_JSON_OBJECT_REQUIRED",
            details={"path": str(path)},
        )
    return value


def require_identity(value: str, label: str) -> None:
    if not value or not IDENTITY_RE.fullmatch(value):
        raise GateBlocked(
            "BLOCKED_REVISION_IDENTITY_INVALID",
            details={"field": label, "value": value},
        )


def safe_indexed_file(revision_root: Path, relative_path: str) -> Path:
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise GateBlocked(
            "BLOCKED_REVISION_PATH_ESCAPE",
            details={"relative_path": relative_path},
        )

    current = revision_root
    for part in pure.parts:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError as exc:
            raise GateBlocked(
                "BLOCKED_REVISION_ARTIFACT_MISSING",
                details={"relative_path": relative_path},
            ) from exc
        if stat.S_ISLNK(mode):
            raise GateBlocked(
                "BLOCKED_REVISION_SYMLINK_FORBIDDEN",
                details={"relative_path": relative_path, "component": str(current)},
            )

    resolved_root = revision_root.resolve(strict=True)
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise GateBlocked(
            "BLOCKED_REVISION_PATH_ESCAPE",
            details={"relative_path": relative_path, "resolved": str(resolved)},
        ) from exc
    if not resolved.is_file():
        raise GateBlocked(
            "BLOCKED_REVISION_ARTIFACT_NOT_REGULAR_FILE",
            details={"relative_path": relative_path},
        )
    return resolved


def validate_all_indexed_files(
    revision_root: Path,
    artifacts: Mapping[str, Mapping[str, Any]],
) -> HashValidation:
    mismatches: list[dict[str, Any]] = []
    hash_manifest: dict[str, str] = {}
    matched = 0

    for artifact_id, raw_entry in sorted(artifacts.items()):
        if not isinstance(raw_entry, Mapping):
            raise GateBlocked(
                "BLOCKED_REVISION_ARTIFACT_INDEX_INVALID",
                details={"artifact_id": artifact_id},
            )
        relative_path = str(raw_entry.get("relative_path") or "")
        expected_sha256 = str(raw_entry.get("sha256") or "")
        expected_size = raw_entry.get("size_bytes")
        path = safe_indexed_file(revision_root, relative_path)
        observed_sha256 = sha256_file(path)
        observed_size = path.stat().st_size
        hash_manifest[artifact_id] = observed_sha256

        if observed_sha256 != expected_sha256 or (
            isinstance(expected_size, int) and observed_size != expected_size
        ):
            mismatches.append(
                {
                    "artifact_id": artifact_id,
                    "relative_path": relative_path,
                    "expected_sha256": expected_sha256,
                    "observed_sha256": observed_sha256,
                    "expected_size_bytes": expected_size,
                    "observed_size_bytes": observed_size,
                }
            )
        else:
            matched += 1

    if mismatches:
        raise GateBlocked(
            "BLOCKED_REVISION_HASH_MISMATCH",
            details={
                "mismatch_count": len(mismatches),
                "mismatches": mismatches[:20],
            },
        )

    return HashValidation(
        artifact_count=len(artifacts),
        recomputed_count=len(artifacts),
        matched_count=matched,
        mismatch_count=0,
        symlink_count=0,
        escape_count=0,
        artifact_hash_manifest_sha256=sha256_json(hash_manifest),
    )


def load_snapshot(
    run_root: Path,
    revision_id: str,
    source_commit: str,
) -> RevisionSnapshot:
    require_identity(revision_id, "revision_id")
    if not SOURCE_COMMIT_RE.fullmatch(source_commit):
        raise GateBlocked(
            "BLOCKED_SOURCE_COMMIT_INVALID",
            details={"source_commit": source_commit},
        )

    resolved_run_root = run_root.expanduser().resolve(strict=True)
    run_id = resolved_run_root.name
    require_identity(run_id, "run_id")
    revision_root = (
        resolved_run_root / ".persona-dream" / "revisions" / revision_id
    ).resolve(strict=True)
    try:
        revision_root.relative_to(resolved_run_root)
    except ValueError as exc:
        raise GateBlocked("BLOCKED_REVISION_PATH_ESCAPE") from exc

    index_path = revision_root / INDEX_NAME
    manifest_path = revision_root / MANIFEST_NAME
    index = read_object(index_path)
    manifest = read_object(manifest_path)

    if index.get("schema") != "persona_dream.revision_artifact_index.v1":
        raise GateBlocked(
            "BLOCKED_REVISION_ARTIFACT_INDEX_SCHEMA",
            details={"observed": index.get("schema")},
        )
    if index.get("run_id") != run_id or index.get("revision_id") != revision_id:
        raise GateBlocked("BLOCKED_REVISION_ARTIFACT_INDEX_IDENTITY")
    if manifest.get("runId") != run_id or manifest.get("revisionId") != revision_id:
        raise GateBlocked("BLOCKED_REVISION_MANIFEST_IDENTITY")

    raw_artifacts = index.get("artifacts")
    if not isinstance(raw_artifacts, dict):
        raise GateBlocked("BLOCKED_REVISION_ARTIFACT_INDEX_INVALID")
    artifacts = {
        str(artifact_id): dict(entry)
        for artifact_id, entry in raw_artifacts.items()
        if isinstance(entry, dict)
    }
    if len(artifacts) != len(raw_artifacts):
        raise GateBlocked("BLOCKED_REVISION_ARTIFACT_INDEX_INVALID")
    if index.get("artifact_count") != len(artifacts):
        raise GateBlocked(
            "BLOCKED_REVISION_ARTIFACT_COUNT_MISMATCH",
            details={
                "declared": index.get("artifact_count"),
                "observed": len(artifacts),
            },
        )

    missing_required: list[str] = []
    wrong_phase: list[dict[str, str]] = []
    for phase_id, artifact_ids in REQUIRED_ARTIFACTS_BY_PHASE.items():
        for artifact_id in artifact_ids:
            entry = artifacts.get(artifact_id)
            if not entry:
                missing_required.append(artifact_id)
                continue
            if str(entry.get("phase_id") or "") != phase_id:
                wrong_phase.append(
                    {
                        "artifact_id": artifact_id,
                        "expected_phase": phase_id,
                        "observed_phase": str(entry.get("phase_id") or ""),
                    }
                )
    if missing_required or wrong_phase:
        raise GateBlocked(
            "BLOCKED_REQUIRED_ARTIFACT_CONTRACT",
            details={"missing": missing_required, "wrong_phase": wrong_phase},
        )
    if index.get("required_artifact_count") != len(REQUIRED_ARTIFACT_IDS):
        raise GateBlocked(
            "BLOCKED_REQUIRED_ARTIFACT_COUNT_MISMATCH",
            details={
                "declared": index.get("required_artifact_count"),
                "expected": len(REQUIRED_ARTIFACT_IDS),
            },
        )

    hash_validation = validate_all_indexed_files(revision_root, artifacts)
    try:
        idea_lineage = validate_revision_idea_lineage(
            revision_root, run_id, revision_id, index
        )
    except IdeaLineageError as exc:
        raise GateBlocked(exc.code, details=exc.details) from exc
    return RevisionSnapshot(
        run_root=resolved_run_root,
        revision_root=revision_root,
        run_id=run_id,
        revision_id=revision_id,
        source_revision_id=str(manifest.get("sourceRevisionId") or ""),
        source_commit=source_commit,
        runtime_release_id=f"agent-skills@{source_commit}",
        index_path=index_path,
        manifest_path=manifest_path,
        index=index,
        manifest=manifest,
        index_sha256=sha256_file(index_path),
        manifest_sha256=sha256_file(manifest_path),
        artifacts=artifacts,
        hash_validation=hash_validation,
        idea_lineage=idea_lineage,
    )


def stable_memory_key(record_type: str, *identity: str) -> str:
    digest = hashlib.sha256("\0".join(identity).encode("utf-8")).hexdigest()
    prefixes = {"revision": "rev", "phase": "phase", "artifact": "artifact"}
    return f"pd_{prefixes[record_type]}_{digest[:48]}"


def with_contract_hash(document: dict[str, Any]) -> dict[str, Any]:
    value = dict(document)
    value["document_contract_sha256"] = sha256_json(value)
    return value


def lineage(snapshot: RevisionSnapshot) -> dict[str, Any]:
    return {
        "run_id": snapshot.run_id,
        "revision_id": snapshot.revision_id,
        "source_revision_id": snapshot.source_revision_id,
        "source_commit": snapshot.source_commit,
        "revision_manifest_sha256": snapshot.manifest_sha256,
        "artifact_index_sha256": snapshot.index_sha256,
    }


def build_documents(
    snapshot: RevisionSnapshot,
    *,
    lifecycle_state: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    common = {
        "run_id": snapshot.run_id,
        "revision_id": snapshot.revision_id,
        "source_revision_id": snapshot.source_revision_id,
        "source_commit": snapshot.source_commit,
        "runtime_release_id": snapshot.runtime_release_id,
        "scope": f"persona-dream:{snapshot.run_id}:{snapshot.revision_id}",
        "source": f"persona-dream://{snapshot.run_id}/revisions/{snapshot.revision_id}",
        "project": "persona-dream",
        "lineage": lineage(snapshot),
        "idea_id": snapshot.idea_lineage.idea_id,
        "idea_sha256": snapshot.idea_lineage.idea_sha256,
        "idea_source": snapshot.idea_lineage.source,
        "idea_lineage_manifest_sha256": snapshot.idea_lineage.lineage_manifest_sha256,
        "idea_phase_binding_count": snapshot.idea_lineage.phase_binding_count,
        "actual_provider_call_attempts": 0,
    }

    revision_key = stable_memory_key(
        "revision", snapshot.run_id, snapshot.revision_id
    )
    phase_keys: dict[str, str] = {}
    artifact_keys: dict[str, str] = {}

    revision_document = with_contract_hash(
        {
            "_key": revision_key,
            "schema": "persona_dream.pipeline_revision.v1",
            "kind": "persona_dream_pipeline_revision",
            "record_type": "revision",
            **common,
            "lifecycle_state": lifecycle_state,
            "revision_manifest_sha256": snapshot.manifest_sha256,
            "artifact_index_sha256": snapshot.index_sha256,
            "artifact_hash_manifest_sha256": snapshot.hash_validation.artifact_hash_manifest_sha256,
            "phase_count": len(EXPECTED_PHASE_IDS),
            "phase_ids": list(EXPECTED_PHASE_IDS),
            "required_artifact_count": len(REQUIRED_ARTIFACT_IDS),
            "required_artifact_ids": list(REQUIRED_ARTIFACT_IDS),
            "artifact_count": snapshot.hash_validation.artifact_count,
            "human_idea_text": snapshot.idea_lineage.text,
            "human_idea_created_at": snapshot.idea_lineage.created_at,
            "problem": (
                f"Persona Dream immutable revision {snapshot.revision_id} "
                f"for run {snapshot.run_id}"
            ),
            "solution": (
                "Prepared immutable evidence for Persona Dream Phase 01 through "
                f"Phase 10 at source commit {snapshot.source_commit}."
            ),
            "retrieval_text": (
                f"Persona Dream immutable revision {snapshot.revision_id} for run "
                f"{snapshot.run_id}. This revision contains accepted local evidence "
                "for Phase 01 through Phase 10 and is prepared for Memory verification. "
                f"Source revision {snapshot.source_revision_id}; source commit "
                f"{snapshot.source_commit}; {snapshot.hash_validation.artifact_count} "
                f"indexed artifacts and {len(REQUIRED_ARTIFACT_IDS)} required artifact "
                f"references. Explicit human idea: {snapshot.idea_lineage.text}"
            ),
            "tags": [
                "persona-dream",
                "pipeline-revision",
                f"run:{snapshot.run_id}",
                f"revision:{snapshot.revision_id}",
                f"idea:{snapshot.idea_lineage.idea_id}",
                f"lifecycle:{lifecycle_state.lower()}",
            ],
        }
    )

    phase_documents: list[dict[str, Any]] = []
    for phase_id in EXPECTED_PHASE_IDS:
        required_ids = list(REQUIRED_ARTIFACTS_BY_PHASE[phase_id])
        required_hashes = {
            artifact_id: snapshot.artifacts[artifact_id]["sha256"]
            for artifact_id in required_ids
        }
        all_phase_artifacts = sorted(
            artifact_id
            for artifact_id, entry in snapshot.artifacts.items()
            if str(entry.get("phase_id") or "") == phase_id
        )
        phase_key = stable_memory_key(
            "phase", snapshot.run_id, snapshot.revision_id, phase_id
        )
        phase_keys[phase_id] = phase_key
        phase_documents.append(
            with_contract_hash(
                {
                    "_key": phase_key,
                    "schema": "persona_dream.pipeline_phase.v1",
                    "kind": "persona_dream_pipeline_phase",
                    "record_type": "phase",
                    **common,
                    "phase_id": phase_id,
                    "phase_title": PHASE_TITLES[phase_id],
                    "evidence_status": "CURRENT",
                    "required_artifact_ids": required_ids,
                    "required_artifact_hashes": required_hashes,
                    "phase_artifact_count": len(all_phase_artifacts),
                    "problem": (
                        f"Persona Dream Phase {phase_id} {PHASE_TITLES[phase_id]} "
                        f"for revision {snapshot.revision_id}"
                    ),
                    "solution": (
                        "Required immutable evidence: " + ", ".join(required_ids)
                    ),
                    "phase_artifact_hash_manifest_sha256": sha256_json(
                        {
                            artifact_id: snapshot.artifacts[artifact_id]["sha256"]
                            for artifact_id in all_phase_artifacts
                        }
                    ),
                    "retrieval_text": (
                        f"Persona Dream Phase {phase_id} {PHASE_TITLES[phase_id]} "
                        f"for run {snapshot.run_id}, revision {snapshot.revision_id}. "
                        f"Required immutable evidence: {', '.join(required_ids)}. "
                        "Evidence status is CURRENT and all indexed hashes were "
                        "recomputed from the immutable revision. The phase is bound to "
                        f"human idea {snapshot.idea_lineage.idea_id} with SHA-256 "
                        f"{snapshot.idea_lineage.idea_sha256}."
                    ),
                    "tags": [
                        "persona-dream",
                        "pipeline-phase",
                        f"run:{snapshot.run_id}",
                        f"revision:{snapshot.revision_id}",
                        f"idea:{snapshot.idea_lineage.idea_id}",
                        f"phase:{phase_id}",
                    ],
                }
            )
        )

    artifact_documents: list[dict[str, Any]] = []
    for phase_id in EXPECTED_PHASE_IDS:
        for artifact_id in REQUIRED_ARTIFACTS_BY_PHASE[phase_id]:
            entry = snapshot.artifacts[artifact_id]
            artifact_key = stable_memory_key(
                "artifact",
                snapshot.run_id,
                snapshot.revision_id,
                artifact_id,
            )
            artifact_keys[artifact_id] = artifact_key
            artifact_documents.append(
                with_contract_hash(
                    {
                        "_key": artifact_key,
                        "schema": "persona_dream.pipeline_artifact_ref.v1",
                        "kind": "persona_dream_pipeline_artifact_ref",
                        "record_type": "required_artifact",
                        **common,
                        "phase_id": phase_id,
                        "artifact_id": artifact_id,
                        "relative_path": str(entry["relative_path"]),
                        "sha256": str(entry["sha256"]),
                        "size_bytes": int(entry["size_bytes"]),
                        "media_type": str(entry.get("media_type") or "application/octet-stream"),
                        "artifact_kind": str(entry.get("kind") or "other"),
                        "artifact_schema": entry.get("schema"),
                        "roles": list(entry.get("roles") or []),
                        "consumer_contract": entry.get("consumer_contract"),
                        "evidence_status": "CURRENT",
                        "problem": (
                            f"Persona Dream required artifact {artifact_id} for "
                            f"revision {snapshot.revision_id}"
                        ),
                        "solution": (
                            f"Phase {phase_id} immutable SHA-256 {entry['sha256']}"
                        ),
                        "retrieval_text": (
                            f"Persona Dream required artifact {artifact_id} for Phase "
                            f"{phase_id} in run {snapshot.run_id}, revision "
                            f"{snapshot.revision_id}. Revision-relative path "
                            f"{entry['relative_path']}; immutable SHA-256 "
                            f"{entry['sha256']}."
                        ),
                        "tags": [
                            "persona-dream",
                            "required-artifact",
                            f"run:{snapshot.run_id}",
                            f"revision:{snapshot.revision_id}",
                            f"phase:{phase_id}",
                            f"artifact:{artifact_id}",
                        ],
                    }
                )
            )

    documents = [revision_document, *phase_documents, *artifact_documents]
    key_contract = {
        "revision_key": revision_key,
        "phase_keys": phase_keys,
        "required_artifact_keys": artifact_keys,
        "exact_keys": [document["_key"] for document in documents],
    }
    return documents, key_contract


def is_semantic_failure(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "semantic",
            "embedding",
            "embed/",
            "qdrant",
            "vector",
            "8603",
        )
    )


def response_counts(response: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: response.get(key)
        for key in (
            "collection",
            "inserted",
            "updated",
            "total",
            "count",
            "errors",
            "writeahead_path",
        )
        if key in response
    }


def http_evidence(value: HttpEvidence) -> dict[str, Any]:
    return {
        "endpoint": value.endpoint,
        "status_code": value.status_code,
        "request_payload_sha256": value.request_sha256,
        "response_sha256": value.response_sha256,
        "returned_counts": response_counts(value.response),
    }


def list_request(
    collection: str,
    snapshot: RevisionSnapshot,
) -> dict[str, Any]:
    return {
        "collection": collection,
        "limit": 500,
        "offset": 0,
        "sort_field": "_key",
        "sort_order": "ASC",
        "filters": {
            "run_id": snapshot.run_id,
            "revision_id": snapshot.revision_id,
        },
    }


def list_documents(client: MemoryClient, collection: str, snapshot: RevisionSnapshot) -> tuple[list[dict[str, Any]], HttpEvidence]:
    evidence = client.post("/list", list_request(collection, snapshot))
    documents = evidence.response.get("documents")
    if not isinstance(documents, list) or not all(isinstance(item, dict) for item in documents):
        raise GateBlocked(
            "BLOCKED_MEMORY_LIST_RESPONSE_INVALID",
            details={"response": response_counts(evidence.response)},
            exit_code=4,
        )
    return [dict(item) for item in documents], evidence


def assert_document_contract(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> None:
    forbidden = FORBIDDEN_VECTOR_FIELDS.intersection(observed)
    if forbidden:
        raise GateBlocked(
            "BLOCKED_MEMORY_INLINE_VECTOR_FORBIDDEN",
            details={"key": expected.get("_key"), "fields": sorted(forbidden)},
            exit_code=3,
        )
    unexpected = set(observed) - set(expected) - SERVER_OWNED_FIELDS
    if unexpected:
        raise GateBlocked(
            "BLOCKED_MEMORY_DOCUMENT_UNEXPECTED_FIELDS",
            details={
                "key": expected.get("_key"),
                "unexpected_fields": sorted(unexpected),
            },
        )
    for key, expected_value in expected.items():
        if observed.get(key) != expected_value:
            raise GateBlocked(
                "BLOCKED_MEMORY_DOCUMENT_MISMATCH",
                details={
                    "key": expected.get("_key"),
                    "field": key,
                    "expected": expected_value,
                    "observed": observed.get(key),
                },
            )


def _key_record_type(key: str) -> str | None:
    for prefix, record_type in QUALIFICATION_KEY_PREFIXES.items():
        if key.startswith(prefix):
            return record_type
    return None


def scope_qualification_documents(
    observed_documents: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition observed Memory documents into qualification vs governance.

    The (run_id, revision_id) filter keyspace legitimately also holds
    governance/audit records.  The exact-match gate must count and re-read ONLY
    the qualification records, selected by their record identity (qualification
    schema, record_type, and stable-key prefix) rather than by raw keyspace
    membership.

    A document makes a *qualification claim* if it matches the qualification
    contract on ANY of the three axes (schema, record_type, key prefix).  A
    qualification claim must be self-consistent: all three axes must be present
    and agree on the same record_type.  An inconsistent or partial claim is a
    malformed qualification record -> fail closed (never silently ignored, never
    silently counted).  A document that makes NO qualification claim on any axis
    is a governance/audit record: readable, never counted.  Fails closed on any
    duplicate qualification _key.
    """
    qualification: list[dict[str, Any]] = []
    governance: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    seen_keys: dict[str, int] = {}

    for raw in observed_documents:
        document = dict(raw)
        key = str(document.get("_key") or "")
        schema = document.get("schema")
        record_type = document.get("record_type")
        schema_type = QUALIFICATION_SCHEMA_RECORD_TYPES.get(str(schema))
        type_claim = (
            record_type if record_type in QUALIFICATION_RECORD_TYPES else None
        )
        key_type = _key_record_type(key)

        if schema_type is None and type_claim is None and key_type is None:
            governance.append(document)
            continue

        claimed_types = {schema_type, type_claim, key_type}
        claimed_types.discard(None)
        if (
            schema_type is None
            or type_claim is None
            or key_type is None
            or len(claimed_types) != 1
        ):
            ambiguous.append(
                {
                    "key": key,
                    "schema": schema,
                    "record_type": record_type,
                    "schema_record_type": schema_type,
                    "key_record_type": key_type,
                }
            )
            continue

        seen_keys[key] = seen_keys.get(key, 0) + 1
        qualification.append(document)

    if ambiguous:
        raise GateBlocked(
            "BLOCKED_MEMORY_QUALIFICATION_RECORD_MALFORMED",
            details={
                "ambiguous_count": len(ambiguous),
                "records": ambiguous[:20],
            },
        )
    duplicate_keys = sorted(key for key, count in seen_keys.items() if count > 1)
    if duplicate_keys:
        raise GateBlocked(
            "BLOCKED_MEMORY_QUALIFICATION_RECORD_DUPLICATE",
            details={"duplicate_keys": duplicate_keys},
        )
    return qualification, governance


def classify_records(documents: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "revision": sum(item.get("record_type") == "revision" for item in documents),
        "phase": sum(item.get("record_type") == "phase" for item in documents),
        "required_artifact": sum(
            item.get("record_type") == "required_artifact" for item in documents
        ),
        "total": len(documents),
    }


def validate_exact_records(
    expected_documents: Sequence[Mapping[str, Any]],
    observed_documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    qualification_documents, governance_documents = scope_qualification_documents(
        observed_documents
    )
    expected_by_key = {str(item["_key"]): item for item in expected_documents}
    observed_by_key = {
        str(item.get("_key") or ""): item for item in qualification_documents
    }
    expected_keys = sorted(expected_by_key)
    observed_keys = sorted(observed_by_key)
    if expected_keys != observed_keys:
        raise GateBlocked(
            "BLOCKED_MEMORY_RECORD_KEYS_MISMATCH",
            details={
                "missing_keys": sorted(set(expected_keys) - set(observed_keys)),
                "unexpected_keys": sorted(set(observed_keys) - set(expected_keys)),
                "governance_ignored_count": len(governance_documents),
            },
        )
    for key in expected_keys:
        assert_document_contract(expected_by_key[key], observed_by_key[key])
    counts = classify_records(qualification_documents)
    if counts != {
        "revision": 1,
        "phase": 10,
        "required_artifact": 16,
        "total": EXPECTED_RECORD_COUNT,
    }:
        raise GateBlocked(
            "BLOCKED_MEMORY_RECORD_COUNT_MISMATCH",
            details={"counts": counts},
        )
    return {
        "exact_keys": expected_keys,
        "counts": counts,
        "governance_ignored_count": len(governance_documents),
    }


def validate_semantic_pointers(
    documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    qualification_documents, _ = scope_qualification_documents(documents)
    missing: list[dict[str, Any]] = []
    states: dict[str, int] = {}
    for document in qualification_documents:
        absent = [
            field
            for field in SEMANTIC_REQUIRED_FIELDS
            if document.get(field) in (None, "")
        ]
        state = str(document.get("semantic_sync_state") or "missing")
        states[state] = states.get(state, 0) + 1
        if absent or state != "synced":
            missing.append(
                {
                    "key": document.get("_key"),
                    "missing_fields": absent,
                    "semantic_sync_state": state,
                    "semantic_sync_error": document.get("semantic_sync_error"),
                }
            )
    if missing:
        raise GateBlocked(
            "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
            details={"unsynchronized_count": len(missing), "records": missing[:20]},
            exit_code=3,
        )
    return {
        "required": True,
        "expected_pointer_count": len(qualification_documents),
        "pointer_count": len(qualification_documents),
        "states": states,
    }


def recall_document(item: Mapping[str, Any]) -> Mapping[str, Any]:
    document = item.get("doc")
    return document if isinstance(document, Mapping) else item


def dense_score(item: Mapping[str, Any]) -> float:
    scores = item.get("scores")
    if not isinstance(scores, Mapping):
        return 0.0
    try:
        return float(scores.get("dense") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def recall_request(collection: str, snapshot: RevisionSnapshot) -> dict[str, Any]:
    return {
        "q": (
            "Which immutable Persona Dream revision stores the explicit human idea "
            f"'{snapshot.idea_lineage.text}' for run {snapshot.run_id} revision "
            f"{snapshot.revision_id}, and which Phase 01 through Phase 10 records "
            "are bound to that exact idea?"
        ),
        "collections": [collection],
        "tags": [f"revision:{snapshot.revision_id}"],
        "k": 50,
        "threshold": 0.0,
    }


def validate_recall(
    evidence: HttpEvidence,
    snapshot: RevisionSnapshot,
) -> dict[str, Any]:
    raw_items = evidence.response.get("items")
    if not isinstance(raw_items, list):
        raise GateBlocked(
            "BLOCKED_MEMORY_RECALL_RESPONSE_INVALID",
            details={"response_keys": sorted(evidence.response)},
            exit_code=4,
        )
    expected_keys = {
        stable_memory_key("revision", snapshot.run_id, snapshot.revision_id): (
            "revision",
            None,
        ),
        **{
            stable_memory_key(
                "phase", snapshot.run_id, snapshot.revision_id, phase_id
            ): ("phase", phase_id)
            for phase_id in EXPECTED_PHASE_IDS
        },
    }
    matching: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            continue
        document = recall_document(raw_item)
        key = str(document.get("_key") or "")
        if key in expected_keys:
            record_type, phase_id = expected_keys[key]
            matching.append(
                {
                    "key": key,
                    "record_type": record_type,
                    "phase_id": phase_id,
                    "dense": dense_score(raw_item),
                }
            )
    dense_matching = [item for item in matching if item["dense"] > 0.0]
    revision_key = stable_memory_key("revision", snapshot.run_id, snapshot.revision_id)
    revision_dense = [
        item for item in dense_matching
        if item["key"] == revision_key and item["record_type"] == "revision"
    ]
    if not revision_dense:
        raise GateBlocked(
            "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
            details={"reason": "human_idea_revision_dense_match_missing", "matching_items": matching[:20]},
            exit_code=3,
        )
    if not dense_matching:
        raise GateBlocked(
            "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED",
            details={
                "matching_identity_count": len(matching),
                "matching_items": matching[:20],
            },
            exit_code=3,
        )
    return {
        "question": recall_request("unused", snapshot)["q"],
        "item_count": len(raw_items),
        "matching_identity_count": len(matching),
        "dense_matching_count": len(dense_matching),
        "human_idea_revision_dense_count": len(revision_dense),
        "max_dense": max(item["dense"] for item in dense_matching),
        "evidence": dense_matching,
    }


def validate_upsert_result(evidence: HttpEvidence, expected_count: int) -> None:
    response = evidence.response
    errors = response.get("errors")
    if isinstance(errors, list) and errors:
        raise GateBlocked(
            "BLOCKED_MEMORY_UPSERT_ERRORS",
            details={"errors": errors[:20]},
            exit_code=4,
        )
    total = response.get("total")
    if total is not None and total != expected_count:
        raise GateBlocked(
            "BLOCKED_MEMORY_UPSERT_COUNT_MISMATCH",
            details={"expected": expected_count, "observed": total},
            exit_code=4,
        )
    inserted = response.get("inserted")
    updated = response.get("updated")
    if isinstance(inserted, int) and isinstance(updated, int) and inserted + updated != expected_count:
        raise GateBlocked(
            "BLOCKED_MEMORY_UPSERT_COUNT_MISMATCH",
            details={
                "expected": expected_count,
                "inserted": inserted,
                "updated": updated,
            },
            exit_code=4,
        )


def command_metadata(source_commit: str) -> dict[str, Any]:
    script_path = Path(__file__).resolve()
    return {
        "argv": list(sys.argv),
        "cwd": str(Path.cwd()),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "script_path": str(script_path),
        "script_sha256": sha256_file(script_path),
        "source_commit": source_commit,
    }


def hash_validation_value(value: HashValidation) -> dict[str, Any]:
    return {
        "artifact_count": value.artifact_count,
        "recomputed_count": value.recomputed_count,
        "matched_count": value.matched_count,
        "mismatch_count": value.mismatch_count,
        "symlink_count": value.symlink_count,
        "escape_count": value.escape_count,
        "artifact_hash_manifest_sha256": value.artifact_hash_manifest_sha256,
    }


def evidence_flags(args: argparse.Namespace) -> dict[str, Any]:
    mocked = bool(args.test_fixture)
    return {
        "mocked": mocked,
        "live": not mocked,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "actual_provider_call_attempts": 0,
    }


def schema_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / name


def validate_receipt(receipt: Mapping[str, Any], schema_name: str) -> None:
    schema = read_object(schema_path(schema_name))
    pydantic_messages = pydantic_error_messages(schema, dict(receipt))
    if pydantic_messages:
        raise GateBlocked(
            "BLOCKED_MEMORY_RECEIPT_SCHEMA",
            details={"errors": pydantic_messages[:20]},
        )
    errors = sorted(
        Draft202012Validator(schema).iter_errors(receipt),
        key=lambda error: list(error.path),
    )
    if errors:
        raise GateBlocked(
            "BLOCKED_MEMORY_RECEIPT_SCHEMA",
            details={"errors": [error.message for error in errors[:20]]},
        )


def receipt_identity(receipt: Mapping[str, Any]) -> str:
    return sha256_json(
        {
            "schema": receipt.get("schema"),
            "status": receipt.get("status"),
            "run_id": receipt.get("run_id"),
            "revision_id": receipt.get("revision_id"),
            "source_commit": receipt.get("source_commit"),
            "memory_url": receipt.get("memory_url"),
            "artifact_index_sha256": receipt.get("artifact_index_sha256"),
            "exact_keys": (receipt.get("records") or {}).get("exact_keys"),
            "request_hashes": sorted(
                value.get("request_payload_sha256")
                for value in (receipt.get("requests") or {}).values()
                if isinstance(value, Mapping)
                and isinstance(value.get("request_payload_sha256"), str)
            ),
        }
    )


def write_immutable_receipt(
    path: Path,
    receipt: dict[str, Any],
    schema_name: str,
) -> dict[str, Any]:
    validate_receipt(receipt, schema_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = read_object(path)
        validate_receipt(existing, schema_name)
        if receipt_identity(existing) != receipt_identity(receipt):
            raise GateBlocked(
                "BLOCKED_MEMORY_RECEIPT_ALREADY_EXISTS_DIFFERENT",
                details={"path": str(path)},
            )
        return existing

    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = read_object(path)
            if receipt_identity(existing) != receipt_identity(receipt):
                raise GateBlocked(
                    "BLOCKED_MEMORY_RECEIPT_ALREADY_EXISTS_DIFFERENT",
                    details={"path": str(path)},
                )
            return existing
        return receipt
    finally:
        temporary.unlink(missing_ok=True)


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    snapshot = load_snapshot(args.run_root, args.revision_id, args.source_commit)
    documents, keys = build_documents(snapshot, lifecycle_state="PREPARED")
    verified_documents, _ = build_documents(snapshot, lifecycle_state="VERIFIED")
    revision_document = documents[0]
    receipt_path = snapshot.revision_root / PREPARE_RECEIPT_NAME

    if receipt_path.is_file():
        existing_receipt = read_object(receipt_path)
        validate_receipt(
            existing_receipt,
            "revision_memory_prepare_receipt.v1.schema.json",
        )
        if (
            existing_receipt.get("artifact_index_sha256") != snapshot.index_sha256
            or existing_receipt.get("source_commit") != snapshot.source_commit
            or existing_receipt.get("collection") != args.collection
            or existing_receipt.get("status") != "PASS_MEMORY_REVISION_PREPARED"
        ):
            raise GateBlocked("BLOCKED_MEMORY_PREPARE_RECEIPT_STALE")
        with MemoryClient(
            args.memory_url,
            connect_timeout=args.connect_timeout,
            read_timeout=args.read_timeout,
        ) as client:
            observed, _ = list_documents(client, args.collection, snapshot)
        revision_state = next(
            (
                str(item.get("lifecycle_state") or "")
                for item in observed
                if item.get("record_type") == "revision"
            ),
            "",
        )
        expected = verified_documents if revision_state == "VERIFIED" else documents
        validate_exact_records(expected, observed)
        validate_semantic_pointers(observed)
        return existing_receipt

    control_payload = {
        "collection": args.collection,
        "documents": [revision_document],
        "skip_embedding": True,
    }
    semantic_payload = {
        "collection": args.collection,
        "documents": documents,
    }

    with MemoryClient(
        args.memory_url,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
    ) as client:
        control_evidence = client.post("/upsert", control_payload)
        validate_upsert_result(control_evidence, 1)
        try:
            semantic_evidence = client.post("/upsert", semantic_payload)
        except GateBlocked as exc:
            if exc.code == "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED":
                exc.details.update(
                    {
                        "revision_lifecycle_state": "PREPARED",
                        "control_record_persisted": True,
                        "control_upsert": http_evidence(control_evidence),
                    }
                )
            raise
        validate_upsert_result(semantic_evidence, len(documents))
        observed_documents, list_evidence = list_documents(
            client, args.collection, snapshot
        )

    record_validation = validate_exact_records(documents, observed_documents)
    semantic_validation = validate_semantic_pointers(observed_documents)

    receipt = {
        "schema": "persona_dream.revision_memory_prepare_receipt.v1",
        "status": "PASS_MEMORY_REVISION_PREPARED",
        "run_id": snapshot.run_id,
        "revision_id": snapshot.revision_id,
        "source_revision_id": snapshot.source_revision_id,
        "source_commit": snapshot.source_commit,
        "runtime_release_id": snapshot.runtime_release_id,
        "memory_url": args.memory_url.rstrip("/"),
        "collection": args.collection,
        "lifecycle_state": "PREPARED",
        "revision_root": str(snapshot.revision_root),
        "artifact_index_path": str(snapshot.index_path),
        "artifact_index_sha256": snapshot.index_sha256,
        "revision_manifest_sha256": snapshot.manifest_sha256,
        "hash_validation": hash_validation_value(snapshot.hash_validation),
        "records": {
            **keys,
            "expected_counts": {
                "revision": 1,
                "phase": 10,
                "required_artifact": 16,
                "total": EXPECTED_RECORD_COUNT,
            },
            "returned_counts": record_validation["counts"],
        },
        "requests": {
            "control_upsert": http_evidence(control_evidence),
            "semantic_upsert": http_evidence(semantic_evidence),
            "list_after_prepare": http_evidence(list_evidence),
        },
        "semantic_sync": semantic_validation,
        "command": command_metadata(snapshot.source_commit),
        "claims": {
            "proves": [
                "the immutable Phase 01-10 revision hashes were recomputed locally",
                "one revision, ten phase, and sixteen required-artifact records were durably re-read from Memory",
                "Memory returned semantic pointer metadata for every prepared record",
            ],
            "does_not_prove": [
                "Memory revision verification or active-revision promotion",
                "ACTIVE_CONSISTENT state",
                "provider readiness, publication, payment, or submission",
            ],
        },
        "prepared_at": utc_now(),
        **evidence_flags(args),
    }
    return write_immutable_receipt(
        receipt_path,
        receipt,
        "revision_memory_prepare_receipt.v1.schema.json",
    )


def verify(args: argparse.Namespace) -> dict[str, Any]:
    snapshot = load_snapshot(args.run_root, args.revision_id, args.source_commit)
    prepared_documents, keys = build_documents(snapshot, lifecycle_state="PREPARED")
    verified_documents, _ = build_documents(snapshot, lifecycle_state="VERIFIED")

    prepare_receipt_path = snapshot.revision_root / PREPARE_RECEIPT_NAME
    if not prepare_receipt_path.is_file():
        raise GateBlocked(
            "BLOCKED_MEMORY_PREPARE_RECEIPT_MISSING",
            details={"path": str(prepare_receipt_path)},
        )
    prepare_receipt = read_object(prepare_receipt_path)
    validate_receipt(
        prepare_receipt,
        "revision_memory_prepare_receipt.v1.schema.json",
    )
    if (
        prepare_receipt.get("status") != "PASS_MEMORY_REVISION_PREPARED"
        or prepare_receipt.get("artifact_index_sha256") != snapshot.index_sha256
        or prepare_receipt.get("source_commit") != snapshot.source_commit
    ):
        raise GateBlocked("BLOCKED_MEMORY_PREPARE_RECEIPT_STALE")

    with MemoryClient(
        args.memory_url,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
    ) as client:
        observed_before, list_before = list_documents(
            client, args.collection, snapshot
        )
        actual_revision = next(
            (
                item
                for item in observed_before
                if item.get("record_type") == "revision"
            ),
            None,
        )
        if not isinstance(actual_revision, dict):
            raise GateBlocked("BLOCKED_MEMORY_REVISION_RECORD_MISSING")
        observed_lifecycle = str(actual_revision.get("lifecycle_state") or "")
        if observed_lifecycle not in {"PREPARED", "VERIFIED"}:
            raise GateBlocked(
                "BLOCKED_MEMORY_REVISION_LIFECYCLE",
                details={"observed": observed_lifecycle},
            )
        expected_before = (
            verified_documents
            if observed_lifecycle == "VERIFIED"
            else prepared_documents
        )
        record_validation_before = validate_exact_records(
            expected_before, observed_before
        )
        semantic_validation_before = validate_semantic_pointers(observed_before)

        recall_payload = recall_request(args.collection, snapshot)
        recall_evidence = client.post("/recall", recall_payload)
        recall_validation = validate_recall(recall_evidence, snapshot)
        recall_validation["question"] = recall_payload["q"]

        finalize_payload = {
            "collection": args.collection,
            "documents": [verified_documents[0]],
        }
        try:
            finalize_evidence = client.post("/upsert", finalize_payload)
        except GateBlocked as exc:
            if exc.code == "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED":
                exc.details.update(
                    {
                        "revision_lifecycle_state": observed_lifecycle,
                        "verification_finalized": False,
                    }
                )
            raise
        validate_upsert_result(finalize_evidence, 1)

        observed_after, list_after = list_documents(
            client, args.collection, snapshot
        )

    record_validation_after = validate_exact_records(
        verified_documents, observed_after
    )
    semantic_validation_after = validate_semantic_pointers(observed_after)

    requests: dict[str, Any] = {
        "list_before_verify": http_evidence(list_before),
        "recall": http_evidence(recall_evidence),
        "list_after_verify": http_evidence(list_after),
    }
    requests["finalize_revision"] = http_evidence(finalize_evidence)

    receipt = {
        "schema": "persona_dream.revision_memory_verify_receipt.v1",
        "status": "PASS_MEMORY_REVISION_VERIFIED",
        "run_id": snapshot.run_id,
        "revision_id": snapshot.revision_id,
        "source_revision_id": snapshot.source_revision_id,
        "source_commit": snapshot.source_commit,
        "runtime_release_id": snapshot.runtime_release_id,
        "memory_url": args.memory_url.rstrip("/"),
        "collection": args.collection,
        "lifecycle_state": "VERIFIED",
        "revision_root": str(snapshot.revision_root),
        "artifact_index_path": str(snapshot.index_path),
        "artifact_index_sha256": snapshot.index_sha256,
        "revision_manifest_sha256": snapshot.manifest_sha256,
        "prepare_receipt_sha256": sha256_file(prepare_receipt_path),
        "hash_validation": hash_validation_value(snapshot.hash_validation),
        "records": {
            **keys,
            "expected_counts": {
                "revision": 1,
                "phase": 10,
                "required_artifact": 16,
                "total": EXPECTED_RECORD_COUNT,
            },
            "before_counts": record_validation_before["counts"],
            "after_counts": record_validation_after["counts"],
        },
        "requests": requests,
        "semantic_sync": {
            "before": semantic_validation_before,
            "after": semantic_validation_after,
            "recall": recall_validation,
        },
        "command": command_metadata(snapshot.source_commit),
        "claims": {
            "proves": [
                "the immutable Phase 01-10 revision hashes were recomputed again before verification",
                "Memory durably returned the exact revision, phase, and required-artifact records",
                "question-shaped recall returned the expected run and revision with a positive dense score",
                "the revision record lifecycle advanced from PREPARED to VERIFIED through Memory",
            ],
            "does_not_prove": [
                "Memory active-revision compare-and-swap",
                "file active-pointer mutation or ACTIVE_CONSISTENT state",
                "repair queue completion",
                "provider readiness, publication, payment, or submission",
            ],
        },
        "verified_at": utc_now(),
        **evidence_flags(args),
    }
    receipt_path = snapshot.revision_root / VERIFY_RECEIPT_NAME
    return write_immutable_receipt(
        receipt_path,
        receipt,
        "revision_memory_verify_receipt.v1.schema.json",
    )


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id", required=True)
    value.add_argument("--source-commit", required=True)
    value.add_argument("--memory-url", default=DEFAULT_MEMORY_URL)
    value.add_argument("--collection", default=DEFAULT_COLLECTION)
    value.add_argument("--connect-timeout", type=float, default=5.0)
    value.add_argument("--read-timeout", type=float, default=60.0)
    value.add_argument(
        "--test-fixture",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    subcommands = value.add_subparsers(dest="command", required=True)
    subcommands.add_parser("prepare")
    subcommands.add_parser("verify")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = prepare(args) if args.command == "prepare" else verify(args)
    except GateBlocked as exc:
        output = {
            "status": exc.code,
            "gate": "memory-revision-prepare-verify",
            "details": exc.details,
            **evidence_flags(args),
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
