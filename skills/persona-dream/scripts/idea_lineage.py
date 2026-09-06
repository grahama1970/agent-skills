#!/usr/bin/env python3
"""Deterministic semantic lineage contract for Persona Dream Phase 01-10.

The validator is intentionally independent of producer PASS fields. It hashes the
explicit human idea, validates the Phase 01 request, recomputes every per-phase
binding from immutable artifacts, and rejects mixed revisions with one stable
blocker code.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator
from pydantic_step_gate import pydantic_error_messages

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = SKILL_ROOT / "schemas"
PHASE_CONTRACT_PATH = SKILL_ROOT / "contracts" / "persona_dream_phase_artifacts.v1.json"
EXPECTED_PHASE_IDS = tuple(f"{value:02d}" for value in range(1, 11))
HUMAN_IDEA_ARTIFACT_ID = "human_idea"
LINEAGE_MANIFEST_ARTIFACT_ID = "idea_lineage_manifest"
BINDING_BASENAME = "idea_lineage_binding.json"
SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")

# Phases 08 and 09 are structural routing/lock phases. Their semantic identity is
# proven by exact immutable artifact hashes chained from the prior semantic phase.
STRUCTURAL_PHASES = {"08", "09"}


class IdeaLineageError(RuntimeError):
    def __init__(self, reason: str, *, phase_id: str | None = None, details: Mapping[str, Any] | None = None) -> None:
        super().__init__("BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH")
        self.code = "BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH"
        self.phase_id = phase_id
        self.reason = reason
        self.details = {"reason": reason, **({"phase_id": phase_id} if phase_id else {}), **dict(details or {})}


@dataclass(frozen=True)
class IdeaLineage:
    idea_id: str
    idea_sha256: str
    text: str
    source: str
    created_at: str
    run_id: str
    revision_id: str
    human_idea_path: Path
    human_idea_artifact_sha256: str
    lineage_manifest_path: Path
    lineage_manifest_sha256: str
    phase_binding_count: int
    phase_binding_hashes: Mapping[str, str]

    def receipt_value(self) -> dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "idea_sha256": self.idea_sha256,
            "source": self.source,
            "created_at": self.created_at,
            "human_idea_artifact_sha256": self.human_idea_artifact_sha256,
            "lineage_manifest_sha256": self.lineage_manifest_sha256,
            "phase_binding_count": self.phase_binding_count,
            "phase_binding_hashes": dict(self.phase_binding_hashes),
        }


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise IdeaLineageError("JSON_OBJECT_REQUIRED", details={"path": str(path)})
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()


def idea_sha256(text: str) -> str:
    normalized = canonical_text(text)
    if not normalized:
        raise IdeaLineageError("HUMAN_IDEA_TEXT_EMPTY", phase_id="01")
    return sha256_bytes(normalized.encode("utf-8"))


def idea_id(text: str) -> str:
    return f"pd_idea_{idea_sha256(text).removeprefix('sha256:')[:32]}"


def binding_sha256(value: Mapping[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "binding_sha256"}
    return sha256_bytes(canonical_json_bytes(unsigned))


def validate_schema(value: Mapping[str, Any], schema_name: str, *, phase_id: str | None = None) -> None:
    path = SCHEMA_ROOT / schema_name
    if not path.is_file():
        raise IdeaLineageError("IDEA_SCHEMA_MISSING", phase_id=phase_id, details={"schema": schema_name})
    schema = json.loads(path.read_text(encoding="utf-8"))
    pydantic_messages = pydantic_error_messages(schema, value)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: list(error.path))
    if pydantic_messages or errors:
        raise IdeaLineageError(
            "IDEA_SCHEMA_INVALID",
            phase_id=phase_id,
            details={"schema": schema_name, "errors": (pydantic_messages + [error.message for error in errors])[:20]},
        )


def safe_relative_file(root: Path, relative_path: str, *, phase_id: str | None = None) -> Path:
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise IdeaLineageError("IDEA_PATH_ESCAPE", phase_id=phase_id, details={"relative_path": relative_path})
    resolved_root = root.resolve(strict=True)
    candidate = (resolved_root / pure).resolve(strict=True)
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise IdeaLineageError("IDEA_PATH_ESCAPE", phase_id=phase_id, details={"relative_path": relative_path}) from exc
    if not candidate.is_file():
        raise IdeaLineageError("IDEA_FILE_NOT_REGULAR", phase_id=phase_id, details={"relative_path": relative_path})
    return candidate


def phase_contract() -> dict[str, Any]:
    return read_object(PHASE_CONTRACT_PATH)


def required_artifact_ids_by_phase() -> dict[str, tuple[str, ...]]:
    contract = phase_contract()
    phases = contract.get("phases")
    if not isinstance(phases, Mapping):
        raise IdeaLineageError("PHASE_ARTIFACT_CONTRACT_INVALID")
    result: dict[str, tuple[str, ...]] = {}
    for phase_id in EXPECTED_PHASE_IDS:
        phase = phases.get(phase_id)
        required = phase.get("required_artifacts") if isinstance(phase, Mapping) else None
        if not isinstance(required, list):
            raise IdeaLineageError("PHASE_ARTIFACT_CONTRACT_INVALID", phase_id=phase_id)
        result[phase_id] = tuple(
            str(item.get("artifact_id"))
            for item in required
            if isinstance(item, Mapping) and item.get("artifact_id")
        )
    return result


def index_artifacts(index: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    value = index.get("artifacts")
    if not isinstance(value, Mapping):
        raise IdeaLineageError("REVISION_ARTIFACT_INDEX_INVALID")
    return {str(key): dict(item) for key, item in value.items() if isinstance(item, Mapping)}


def artifact_paths_for_phase(
    revision_root: Path,
    artifacts: Mapping[str, Mapping[str, Any]],
    phase_id: str,
    artifact_ids: Sequence[str],
) -> list[tuple[str, Path, str]]:
    result: list[tuple[str, Path, str]] = []
    for artifact_id in artifact_ids:
        entry = artifacts.get(artifact_id)
        if not isinstance(entry, Mapping):
            raise IdeaLineageError("REQUIRED_ARTIFACT_MISSING", phase_id=phase_id, details={"artifact_id": artifact_id})
        if str(entry.get("phase_id") or "") != phase_id:
            raise IdeaLineageError(
                "REQUIRED_ARTIFACT_PHASE_MISMATCH",
                phase_id=phase_id,
                details={"artifact_id": artifact_id, "observed_phase": entry.get("phase_id")},
            )
        relative_path = str(entry.get("relative_path") or "")
        expected_sha = str(entry.get("sha256") or "")
        if not SHA256_RE.fullmatch(expected_sha):
            raise IdeaLineageError("REQUIRED_ARTIFACT_HASH_INVALID", phase_id=phase_id, details={"artifact_id": artifact_id})
        path = safe_relative_file(revision_root, relative_path, phase_id=phase_id)
        observed_sha = sha256_file(path)
        if observed_sha != expected_sha:
            raise IdeaLineageError(
                "REQUIRED_ARTIFACT_HASH_MISMATCH",
                phase_id=phase_id,
                details={"artifact_id": artifact_id, "expected": expected_sha, "observed": observed_sha},
            )
        result.append((artifact_id, path, observed_sha))
    return result


def flattened_text(value: Any) -> str:
    parts: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, Mapping):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return canonical_text(" ".join(parts)).lower()


def artifact_text(paths: Sequence[tuple[str, Path, str]]) -> str:
    values: list[str] = []
    for _artifact_id, path, _digest in paths:
        if path.suffix.lower() == ".json":
            try:
                values.append(flattened_text(json.loads(path.read_text(encoding="utf-8"))))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        elif path.suffix.lower() in {".txt", ".md", ".jsonl", ".yaml", ".yml"}:
            try:
                values.append(canonical_text(path.read_text(encoding="utf-8")).lower())
            except UnicodeDecodeError:
                continue
    return canonical_text(" ".join(values)).lower()


def semantic_evidence(phase_id: str, paths: Sequence[tuple[str, Path, str]], idea_text: str) -> dict[str, Any]:
    normalized_idea = canonical_text(idea_text)
    corpus = artifact_text(paths)
    person_hits = sorted(name for name in ("embry", "kai") if name in corpus)
    domain_terms = ("surf", "kahalu", "kona", "big island", "reef", "swell", "shortboard", "lineup")
    domain_hits = sorted(term for term in domain_terms if term in corpus)

    if phase_id == "01":
        return {"mode": "exact_human_idea", "person_hits": person_hits, "domain_hits": domain_hits}

    if phase_id == "02":
        story = read_object(paths[0][1]) if paths else {}
        if story.get("idea_id") != idea_id(normalized_idea) or story.get("idea_sha256") != idea_sha256(normalized_idea):
            raise IdeaLineageError("PHASE_02_IDEA_BINDING_MISSING", phase_id=phase_id)
        story_text = canonical_text(str(story.get("story") or story.get("seed") or ""))
        if normalized_idea not in story_text and story_text not in normalized_idea:
            raise IdeaLineageError("PHASE_02_STORY_IDEA_MISMATCH", phase_id=phase_id)
        return {"mode": "exact_story_binding", "person_hits": person_hits, "domain_hits": domain_hits}

    if phase_id == "03":
        crew = read_object(paths[0][1]) if paths else {}
        source_context = crew.get("source_context")
        core_idea = str(source_context.get("core_idea") or "") if isinstance(source_context, Mapping) else ""
        if canonical_text(core_idea) != normalized_idea:
            raise IdeaLineageError(
                "PHASE_03_AUTHORITATIVE_IDEA_MISMATCH",
                phase_id=phase_id,
                details={"observed_core_idea": canonical_text(core_idea)},
            )
        return {"mode": "exact_core_idea", "person_hits": person_hits, "domain_hits": domain_hits}

    if phase_id in STRUCTURAL_PHASES:
        if not paths:
            raise IdeaLineageError("STRUCTURAL_PHASE_ARTIFACTS_MISSING", phase_id=phase_id)
        return {"mode": "structural_hash_chain", "person_hits": person_hits, "domain_hits": domain_hits}

    if set(person_hits) != {"embry", "kai"} or not domain_hits:
        raise IdeaLineageError(
            "PHASE_SEMANTIC_ANCHORS_MISSING",
            phase_id=phase_id,
            details={"person_hits": person_hits, "domain_hits": domain_hits},
        )
    return {"mode": "semantic_anchor_and_hash", "person_hits": person_hits, "domain_hits": domain_hits}


def build_phase_bindings(
    revision_root: Path,
    index: Mapping[str, Any],
    human_idea: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    artifacts = index_artifacts(index)
    required = required_artifact_ids_by_phase()
    idea_text = str(human_idea["text"])
    previous_sha: str | None = None
    bindings: dict[str, dict[str, Any]] = {}
    paths_by_phase: dict[str, Path] = {}

    for phase_id in EXPECTED_PHASE_IDS:
        artifact_ids = list(required[phase_id])
        if phase_id == "01":
            artifact_ids = [item for item in artifact_ids if item != LINEAGE_MANIFEST_ARTIFACT_ID]
        phase_paths = artifact_paths_for_phase(revision_root, artifacts, phase_id, artifact_ids)
        evidence = semantic_evidence(phase_id, phase_paths, idea_text)
        artifact_hashes = {artifact_id: digest for artifact_id, _path, digest in phase_paths}
        binding: dict[str, Any] = {
            "schema": "persona_dream.phase_idea_binding.v1",
            "status": "PASS_PHASE_IDEA_BOUND",
            "run_id": human_idea["run_id"],
            "revision_id": human_idea["revision_id"],
            "phase_id": phase_id,
            "idea_id": human_idea["idea_id"],
            "idea_sha256": human_idea["idea_sha256"],
            "source": "explicit_human",
            "required_artifact_hashes": artifact_hashes,
            "previous_phase_binding_sha256": previous_sha,
            "semantic_evidence": evidence,
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "submitted": False,
        }
        binding["binding_sha256"] = binding_sha256(binding)
        phase_dir = phase_paths[0][1].relative_to(revision_root).parts[0] if phase_paths else f"phase_{phase_id}"
        binding_path = revision_root / phase_dir / BINDING_BASENAME
        bindings[phase_id] = binding
        paths_by_phase[phase_id] = binding_path
        previous_sha = str(binding["binding_sha256"])
    return bindings, paths_by_phase


def build_lineage_manifest(
    revision_root: Path,
    human_idea_path: Path,
    human_idea: Mapping[str, Any],
    bindings: Mapping[str, Mapping[str, Any]],
    binding_paths: Mapping[str, Path],
) -> dict[str, Any]:
    phase_bindings = {
        phase_id: {
            "relative_path": binding_paths[phase_id].relative_to(revision_root).as_posix(),
            "sha256": sha256_file(binding_paths[phase_id]),
            "binding_sha256": bindings[phase_id]["binding_sha256"],
        }
        for phase_id in EXPECTED_PHASE_IDS
    }
    chain_sha = sha256_bytes(canonical_json_bytes([phase_bindings[phase_id]["binding_sha256"] for phase_id in EXPECTED_PHASE_IDS]))
    return {
        "schema": "persona_dream.phase_idea_lineage_manifest.v1",
        "status": "PASS_PHASE_IDEA_LINEAGE",
        "run_id": human_idea["run_id"],
        "revision_id": human_idea["revision_id"],
        "idea_id": human_idea["idea_id"],
        "idea_sha256": human_idea["idea_sha256"],
        "source": "explicit_human",
        "human_idea_artifact": {
            "relative_path": human_idea_path.relative_to(revision_root).as_posix(),
            "sha256": sha256_file(human_idea_path),
        },
        "phase_binding_count": 10,
        "phase_bindings": phase_bindings,
        "lineage_chain_sha256": chain_sha,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "submitted": False,
    }


def validate_revision_idea_lineage(
    revision_root: Path,
    run_id: str,
    revision_id: str,
    index: Mapping[str, Any],
) -> IdeaLineage:
    artifacts = index_artifacts(index)
    human_entry = artifacts.get(HUMAN_IDEA_ARTIFACT_ID)
    manifest_entry = artifacts.get(LINEAGE_MANIFEST_ARTIFACT_ID)
    if not isinstance(human_entry, Mapping) or not isinstance(manifest_entry, Mapping):
        raise IdeaLineageError("HUMAN_IDEA_OR_LINEAGE_ARTIFACT_MISSING", phase_id="01")

    human_path = safe_relative_file(revision_root, str(human_entry.get("relative_path") or ""), phase_id="01")
    manifest_path = safe_relative_file(revision_root, str(manifest_entry.get("relative_path") or ""), phase_id="01")
    if sha256_file(human_path) != human_entry.get("sha256") or sha256_file(manifest_path) != manifest_entry.get("sha256"):
        raise IdeaLineageError("HUMAN_IDEA_OR_LINEAGE_HASH_MISMATCH", phase_id="01")

    human = read_object(human_path)
    validate_schema(human, "human_idea.v1.schema.json", phase_id="01")
    text = canonical_text(str(human.get("text") or ""))
    try:
        created_at = datetime.fromisoformat(str(human.get("created_at") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise IdeaLineageError("HUMAN_IDEA_CREATED_AT_INVALID", phase_id="01") from exc
    if created_at.tzinfo is None:
        raise IdeaLineageError("HUMAN_IDEA_CREATED_AT_INVALID", phase_id="01")
    expected_sha = idea_sha256(text)
    expected_id = idea_id(text)
    if (
        human.get("source") != "explicit_human"
        or human.get("run_id") != run_id
        or human.get("revision_id") != revision_id
        or human.get("idea_sha256") != expected_sha
        or human.get("idea_id") != expected_id
    ):
        raise IdeaLineageError("HUMAN_IDEA_IDENTITY_MISMATCH", phase_id="01")

    dream_request_entry = artifacts.get("dream_request")
    if not isinstance(dream_request_entry, Mapping):
        raise IdeaLineageError("DREAM_REQUEST_MISSING", phase_id="01")
    request_path = safe_relative_file(revision_root, str(dream_request_entry.get("relative_path") or ""), phase_id="01")
    request = read_object(request_path)
    if (
        request.get("run_id") != run_id
        or request.get("write_memory") is not True
        or request.get("idea_id") != expected_id
        or request.get("idea_sha256") != expected_sha
        or canonical_text(str(request.get("about") or "")) != text
    ):
        raise IdeaLineageError(
            "PHASE_01_REQUEST_IDENTITY_MISMATCH",
            phase_id="01",
            details={"observed_run_id": request.get("run_id"), "write_memory": request.get("write_memory")},
        )

    manifest = read_object(manifest_path)
    validate_schema(manifest, "phase_idea_lineage_manifest.v1.schema.json", phase_id="01")
    if (
        manifest.get("run_id") != run_id
        or manifest.get("revision_id") != revision_id
        or manifest.get("idea_id") != expected_id
        or manifest.get("idea_sha256") != expected_sha
        or manifest.get("phase_binding_count") != 10
    ):
        raise IdeaLineageError("LINEAGE_MANIFEST_IDENTITY_MISMATCH", phase_id="01")
    human_ref = manifest.get("human_idea_artifact")
    if not isinstance(human_ref, Mapping) or human_ref.get("sha256") != sha256_file(human_path):
        raise IdeaLineageError("LINEAGE_MANIFEST_HUMAN_IDEA_HASH_MISMATCH", phase_id="01")

    manifest_bindings = manifest.get("phase_bindings")
    if not isinstance(manifest_bindings, Mapping) or set(manifest_bindings) != set(EXPECTED_PHASE_IDS):
        raise IdeaLineageError("LINEAGE_PHASE_BINDING_SET_MISMATCH")

    required = required_artifact_ids_by_phase()
    previous_sha: str | None = None
    binding_hashes: dict[str, str] = {}
    for phase_id in EXPECTED_PHASE_IDS:
        ref = manifest_bindings.get(phase_id)
        if not isinstance(ref, Mapping):
            raise IdeaLineageError("LINEAGE_PHASE_BINDING_MISSING", phase_id=phase_id)
        path = safe_relative_file(revision_root, str(ref.get("relative_path") or ""), phase_id=phase_id)
        observed_file_sha = sha256_file(path)
        if observed_file_sha != ref.get("sha256"):
            raise IdeaLineageError("LINEAGE_PHASE_BINDING_FILE_HASH_MISMATCH", phase_id=phase_id)
        binding = read_object(path)
        validate_schema(binding, "phase_idea_binding.v1.schema.json", phase_id=phase_id)
        if (
            binding.get("run_id") != run_id
            or binding.get("revision_id") != revision_id
            or binding.get("phase_id") != phase_id
            or binding.get("idea_id") != expected_id
            or binding.get("idea_sha256") != expected_sha
            or binding.get("previous_phase_binding_sha256") != previous_sha
        ):
            raise IdeaLineageError("LINEAGE_PHASE_BINDING_IDENTITY_MISMATCH", phase_id=phase_id)
        observed_binding_sha = binding_sha256(binding)
        if binding.get("binding_sha256") != observed_binding_sha or ref.get("binding_sha256") != observed_binding_sha:
            raise IdeaLineageError("LINEAGE_PHASE_BINDING_HASH_MISMATCH", phase_id=phase_id)

        artifact_ids = list(required[phase_id])
        if phase_id == "01":
            artifact_ids = [item for item in artifact_ids if item != LINEAGE_MANIFEST_ARTIFACT_ID]
        phase_paths = artifact_paths_for_phase(revision_root, artifacts, phase_id, artifact_ids)
        expected_hashes = {artifact_id: digest for artifact_id, _path, digest in phase_paths}
        if binding.get("required_artifact_hashes") != expected_hashes:
            raise IdeaLineageError("LINEAGE_PHASE_ARTIFACT_HASH_SET_MISMATCH", phase_id=phase_id)
        expected_evidence = semantic_evidence(phase_id, phase_paths, text)
        observed_evidence = binding.get("semantic_evidence")
        if not isinstance(observed_evidence, Mapping) or dict(observed_evidence) != expected_evidence:
            raise IdeaLineageError("LINEAGE_PHASE_SEMANTIC_EVIDENCE_MISMATCH", phase_id=phase_id)
        binding_hashes[phase_id] = observed_binding_sha
        previous_sha = observed_binding_sha

    chain_sha = sha256_bytes(canonical_json_bytes([binding_hashes[phase_id] for phase_id in EXPECTED_PHASE_IDS]))
    if manifest.get("lineage_chain_sha256") != chain_sha:
        raise IdeaLineageError("LINEAGE_CHAIN_HASH_MISMATCH")

    return IdeaLineage(
        idea_id=expected_id,
        idea_sha256=expected_sha,
        text=text,
        source="explicit_human",
        created_at=str(human["created_at"]),
        run_id=run_id,
        revision_id=revision_id,
        human_idea_path=human_path,
        human_idea_artifact_sha256=sha256_file(human_path),
        lineage_manifest_path=manifest_path,
        lineage_manifest_sha256=sha256_file(manifest_path),
        phase_binding_count=10,
        phase_binding_hashes=binding_hashes,
    )
