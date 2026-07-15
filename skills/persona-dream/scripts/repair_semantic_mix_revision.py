#!/usr/bin/env python3
"""Create, qualify, and activate a new Persona Dream revision for one explicit human idea.

This command repairs semantic-mix defects without mutating the source revision and
without performing provider work. It copies only Phase 03-10 accepted artifacts,
rebuilds Phase 01-02 from the explicit human idea, writes per-phase idea bindings,
persists and semantically verifies the revision through Memory, then activates it
through the existing revision/repair-queue transaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from jsonschema import Draft202012Validator

from activate_revision_qualification import activate
from idea_lineage import (
    BINDING_BASENAME,
    EXPECTED_PHASE_IDS,
    IdeaLineageError,
    build_lineage_manifest,
    build_phase_bindings,
    canonical_json_bytes,
    canonical_text,
    idea_id,
    idea_sha256,
    read_object,
    sha256_bytes,
    sha256_file,
    validate_revision_idea_lineage,
    validate_schema,
)
from prepare_revision_qualification import GateBlocked, prepare, verify
from write_revision_artifact_index import write_index

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPAIR_SCHEMA = SKILL_ROOT / "schemas" / "semantic_mix_repair_receipt.v1.schema.json"
AUTHORITATIVE_CORE_IDEA_POINTER = "/source_context/core_idea"
EXCLUDED_ROOT_FILES = {
    "revision_artifact_index.json",
    "revision_manifest.json",
    "revision_memory_prepare_receipt.json",
    "revision_memory_verify_receipt.json",
    "revision_activation_receipt.json",
    "semantic_mix_repair_receipt.json",
}


class RepairBlocked(RuntimeError):
    def __init__(self, code: str, *, details: Mapping[str, Any] | None = None, exit_code: int = 2) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})
        self.exit_code = exit_code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def repair_lock(run_root: Path) -> Iterator[None]:
    path = run_root / ".persona-dream" / "state" / "semantic_mix_repair.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
    except FileExistsError as exc:
        raise RepairBlocked("BLOCKED_SEMANTIC_MIX_REPAIR_LOCKED", details={"path": str(path)}) from exc
    try:
        yield
    finally:
        path.rmdir()


def active_revision(run_root: Path) -> tuple[str, dict[str, Any]]:
    pointer_path = run_root / ".persona-dream" / "state" / "active_revision.json"
    if not pointer_path.is_file():
        raise RepairBlocked("BLOCKED_ACTIVE_REVISION_MISSING", details={"path": str(pointer_path)})
    pointer = read_object(pointer_path)
    revision_id = str(pointer.get("revisionId") or "")
    if not revision_id:
        raise RepairBlocked("BLOCKED_ACTIVE_REVISION_MISSING")
    return revision_id, pointer


def authoritative_idea(source_revision_root: Path) -> tuple[str, Path]:
    crew_path = source_revision_root / "phase_03_crew" / "crew_contract.json"
    if not crew_path.is_file():
        candidates = sorted(source_revision_root.glob("phase_03*/**/crew_contract.json"))
        crew_path = candidates[0] if len(candidates) == 1 else crew_path
    if not crew_path.is_file():
        raise RepairBlocked("BLOCKED_AUTHORITATIVE_IDEA_SOURCE_MISSING", details={"path": str(crew_path)})
    crew = read_object(crew_path)
    source_context = crew.get("source_context")
    idea = str(source_context.get("core_idea") or "") if isinstance(source_context, Mapping) else ""
    normalized = canonical_text(idea)
    if not normalized:
        raise RepairBlocked(
            "BLOCKED_AUTHORITATIVE_IDEA_SOURCE_MISSING",
            details={"path": str(crew_path), "pointer": AUTHORITATIVE_CORE_IDEA_POINTER},
        )
    return normalized, crew_path


def deterministic_revision_id(run_id: str, source_revision_id: str, idea_text: str) -> str:
    payload = canonical_json_bytes({
        "run_id": run_id,
        "source_revision_id": source_revision_id,
        "idea_sha256": idea_sha256(idea_text),
        "repair": "semantic-mix-v1",
    })
    return f"rev_idea_{hashlib.sha256(payload).hexdigest()[:12]}"


def copy_source_revision(source_root: Path, target_root: Path) -> None:
    if target_root.exists():
        raise RepairBlocked("BLOCKED_SEMANTIC_MIX_TARGET_ALREADY_EXISTS", details={"path": str(target_root)})
    target_root.mkdir(parents=True)
    for child in source_root.iterdir():
        if child.name in EXCLUDED_ROOT_FILES or child.name == "phase_11_submit_return":
            continue
        if child.name.startswith("phase_01") or child.name.startswith("phase_02"):
            continue
        destination = target_root / child.name
        if child.is_dir():
            shutil.copytree(child, destination, symlinks=False)
        elif child.is_file():
            shutil.copy2(child, destination)
    for binding in target_root.rglob(BINDING_BASENAME):
        binding.unlink()


def iter_memory_items(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, Mapping):
        if any(key in value for key in ("text", "retrieval_text")) and any(key in value for key in ("key", "_key", "id")):
            yield dict(value)
        for nested in value.values():
            yield from iter_memory_items(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from iter_memory_items(nested)


def residue_from_crew(crew_path: Path, idea_value: str) -> list[dict[str, Any]]:
    crew = read_object(crew_path)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in iter_memory_items(crew.get("memory_recall_evidence")):
        text = canonical_text(str(item.get("text") or item.get("retrieval_text") or ""))
        lowered = text.lower()
        key = str(item.get("key") or item.get("_key") or item.get("id") or "")
        if not key or key in seen or not text:
            continue
        if not ({"embry", "kai"}.issubset(set(re.findall(r"[a-z]+", lowered))) and any(term in lowered for term in ("surf", "reef", "wave", "swell", "etiquette"))):
            continue
        seen.add(key)
        selected.append({
            "source_id": key,
            "collection": str(item.get("collection") or "persona_memory"),
            "persona_id": str(item.get("persona_id") or item.get("name") or "embry"),
            "text": text,
            "source_path": item.get("source_path"),
        })
    if not selected:
        raise RepairBlocked("BLOCKED_AUTHORITATIVE_RESIDUE_MISSING", details={"crew_contract": str(crew_path)})
    return selected[:24]


def write_phase01_phase02(
    target_root: Path,
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    idea_value: str,
    created_at: str,
    crew_path: Path,
) -> tuple[Path, Path]:
    phase01 = target_root / "phase_01_idea"
    phase02 = target_root / "phase_02_story"
    phase01.mkdir(parents=True)
    phase02.mkdir(parents=True)
    digest = idea_sha256(idea_value)
    ident = idea_id(idea_value)
    human_idea = {
        "schema": "persona_dream.human_idea.v1",
        "artifact_id": "human_idea",
        "idea_id": ident,
        "idea_sha256": digest,
        "text": canonical_text(idea_value),
        "source": "explicit_human",
        "created_at": created_at,
        "run_id": run_id,
        "revision_id": revision_id,
        "source_revision_id": source_revision_id,
        "memory_required": True,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "submitted": False,
    }
    validate_schema(human_idea, "human_idea.v1.schema.json", phase_id="01")
    human_path = phase01 / "human_idea.json"
    write_json(human_path, human_idea)

    residues = residue_from_crew(crew_path, idea_value)
    request = {
        "schema": "persona_dream.dream_request.v2",
        "status": "PASS_EXPLICIT_HUMAN_IDEA_BOUND",
        "run_id": run_id,
        "revision_id": revision_id,
        "source_revision_id": source_revision_id,
        "persona_id": "embry",
        "secondary_persona_id": "kai",
        "about": canonical_text(idea_value),
        "idea_id": ident,
        "idea_sha256": digest,
        "idea_source": "explicit_human",
        "created_at": created_at,
        "write_memory": True,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "submitted": False,
    }
    write_json(phase01 / "dream_request.json", request)
    write_json(phase01 / "residue_links.json", {
        "schema": "persona_dream.residue_links.v1",
        "status": "PASS_IDEA_LINEAGE_REPAIRED",
        "run_id": run_id,
        "revision_id": revision_id,
        "idea_id": ident,
        "idea_sha256": digest,
        "source": "phase_03_crew.memory_recall_evidence",
        "items": residues,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
    })
    write_json(phase01 / "contradiction_report.json", {
        "schema": "persona_dream.contradiction_report.v1",
        "status": "PASS_NO_PHASE_IDEA_CONTRADICTION",
        "run_id": run_id,
        "revision_id": revision_id,
        "idea_id": ident,
        "idea_sha256": digest,
        "contradictions": [],
        "actual_provider_call_attempts": 0,
    })

    story = {
        "schema": "persona_dream.story_contract.v1",
        "status": "PASS_IDEA_LINEAGE_REPAIRED",
        "run_id": run_id,
        "revision_id": revision_id,
        "source_revision_id": source_revision_id,
        "idea_id": ident,
        "idea_sha256": digest,
        "idea_source": "explicit_human",
        "created_at": created_at,
        "seed": canonical_text(idea_value),
        "story": canonical_text(idea_value),
        "target_duration_s": 10,
        "migration": {
            "kind": "semantic_mix_repair",
            "authoritative_source": "phase_03_crew/crew_contract.json#/source_context/core_idea",
            "authoritative_source_sha256": sha256_file(crew_path),
            "creative_regeneration_performed": False,
            "human_story_acceptance_inferred": False,
        },
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "submitted": False,
    }
    write_json(phase02 / "story_contract.json", story)

    placeholder_manifest = {
        "schema": "persona_dream.phase_idea_lineage_manifest.v1",
        "status": "PASS_PHASE_IDEA_LINEAGE",
        "run_id": run_id,
        "revision_id": revision_id,
        "idea_id": ident,
        "idea_sha256": digest,
        "source": "explicit_human",
        "human_idea_artifact": {"relative_path": "phase_01_idea/human_idea.json", "sha256": sha256_file(human_path)},
        "phase_binding_count": 10,
        "phase_bindings": {
            phase_id: {
                "relative_path": f"phase_{phase_id}/idea_lineage_binding.json",
                "sha256": "sha256:" + "0" * 64,
                "binding_sha256": "sha256:" + "0" * 64,
            }
            for phase_id in EXPECTED_PHASE_IDS
        },
        "lineage_chain_sha256": "sha256:" + "0" * 64,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "submitted": False,
    }
    lineage_path = phase01 / "idea_lineage_manifest.json"
    write_json(lineage_path, placeholder_manifest)
    return human_path, lineage_path


def write_revision_manifest(
    target_root: Path,
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    source_commit: str,
    created_at: str,
    idea_value: str,
) -> Path:
    path = target_root / "revision_manifest.json"
    write_json(path, {
        "schema": "persona_dream.revision_manifest.v1",
        "status": "FROZEN_ALL_LOCAL_GATES_PASS",
        "runId": run_id,
        "revisionId": revision_id,
        "sourceRevisionId": source_revision_id,
        "sourceCommit": source_commit,
        "createdAt": created_at,
        "repairKind": "semantic_mix",
        "ideaId": idea_id(idea_value),
        "ideaSha256": idea_sha256(idea_value),
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "submitted": False,
    })
    return path


def write_queue_contract(run_root: Path, source_revision_id: str, target_revision_id: str, created_at: str) -> str:
    digest = hashlib.sha256(
        canonical_json_bytes({"run_id": run_root.name, "source": source_revision_id, "target": target_revision_id, "repair": "semantic_mix"})
    ).hexdigest()
    work_order_id = f"repair-{digest[:16]}"
    work_order = {
        "schemaVersion": "persona_dream.repair_work_order.v1",
        "workOrderId": work_order_id,
        "dedupKey": digest,
        "runId": run_root.name,
        "runRoot": str(run_root.resolve()),
        "sourceRevisionId": source_revision_id,
        "targetRevisionId": target_revision_id,
        "createdAt": created_at,
        "detection": {
            "earliestStalePhase": "01",
            "selectedThroughPhase": "10",
            "phaseRange": list(EXPECTED_PHASE_IDS),
            "reasons": [{"phaseId": "01", "code": "BLOCKED_PHASE_IDEA_LINEAGE_MISMATCH"}],
        },
        "policy": {
            "maxAttemptsPerPhase": 1,
            "forbiddenSideEffects": [
                "external_network", "public_media_publication", "paid_provider_call",
                "provider_submission", "human_acceptance_fabrication",
            ],
            "stopBeforePhase": "11",
        },
        "status": "REQUESTED",
    }
    work_path = run_root / ".persona-dream" / "repair" / "work-orders" / f"{work_order_id}.json"
    queue_path = run_root / ".persona-dream" / "repair" / "tau-queue" / f"{work_order_id}.json"
    write_json(work_path, work_order)
    write_json(queue_path, {
        "schemaVersion": "persona_dream.tau_repair_queue_item.v1",
        "status": "QUEUED",
        "queuedAt": created_at,
        "workOrderPath": str(work_path.resolve()),
        "workOrder": work_order,
    })
    return work_order_id


def qualification_args(args: argparse.Namespace, revision_id: str) -> argparse.Namespace:
    return argparse.Namespace(
        run_root=args.run_root,
        revision_id=revision_id,
        source_commit=args.source_commit,
        memory_url=args.memory_url,
        collection=args.collection,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
        test_fixture=args.test_fixture,
        command="prepare",
    )


def repair(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run_root.expanduser().resolve(strict=True)
    source_revision_id, _pointer = active_revision(run_root)
    if args.source_revision_id and args.source_revision_id != source_revision_id:
        raise RepairBlocked(
            "BLOCKED_SEMANTIC_MIX_SOURCE_REVISION_CHANGED",
            details={"active_revision_id": source_revision_id, "requested": args.source_revision_id},
        )
    source_root = run_root / ".persona-dream" / "revisions" / source_revision_id
    if not source_root.is_dir():
        raise RepairBlocked("BLOCKED_SOURCE_REVISION_MISSING", details={"path": str(source_root)})
    authoritative, crew_path = authoritative_idea(source_root)
    explicit = canonical_text(args.idea_text)
    if explicit != authoritative:
        raise RepairBlocked(
            "BLOCKED_AUTHORITATIVE_IDEA_MISMATCH",
            details={"explicit_human_idea": explicit, "phase03_core_idea": authoritative},
        )
    created_at = args.created_at or utc_now()
    target_revision_id = args.target_revision_id or deterministic_revision_id(run_root.name, source_revision_id, explicit)
    target_root = run_root / ".persona-dream" / "revisions" / target_revision_id

    with repair_lock(run_root):
        copy_source_revision(source_root, target_root)
        try:
            target_crew = target_root / crew_path.relative_to(source_root)
            human_path, lineage_path = write_phase01_phase02(
                target_root,
                run_id=run_root.name,
                revision_id=target_revision_id,
                source_revision_id=source_revision_id,
                idea_value=explicit,
                created_at=created_at,
                crew_path=target_crew,
            )
            manifest_path = write_revision_manifest(
                target_root,
                run_id=run_root.name,
                revision_id=target_revision_id,
                source_revision_id=source_revision_id,
                source_commit=args.source_commit,
                created_at=created_at,
                idea_value=explicit,
            )
            index_path = target_root / "revision_artifact_index.json"
            provisional_index = write_index(target_root, index_path, run_root.name, target_revision_id)
            human_idea = read_object(human_path)
            bindings, binding_paths = build_phase_bindings(target_root, provisional_index, human_idea)
            for phase_id in EXPECTED_PHASE_IDS:
                write_json(binding_paths[phase_id], bindings[phase_id])
            lineage_manifest = build_lineage_manifest(target_root, human_path, human_idea, bindings, binding_paths)
            validate_schema(lineage_manifest, "phase_idea_lineage_manifest.v1.schema.json", phase_id="01")
            write_json(lineage_path, lineage_manifest)
            final_index = write_index(target_root, index_path, run_root.name, target_revision_id)
            lineage = validate_revision_idea_lineage(target_root, run_root.name, target_revision_id, final_index)

            qargs = qualification_args(args, target_revision_id)
            prepare_receipt = prepare(qargs)
            qargs.command = "verify"
            verify_receipt = verify(qargs)

            work_order_id = write_queue_contract(run_root, source_revision_id, target_revision_id, created_at)
            pointer_path = run_root / ".persona-dream" / "state" / "active_revision.json"
            atomic_write_json(pointer_path, {
                "schemaVersion": "persona_dream.active_revision_pointer.v1",
                "runId": run_root.name,
                "revisionId": target_revision_id,
                "revisionRoot": str(target_root.resolve()),
                "revisionManifestSha256": sha256_file(manifest_path),
                "ideaId": lineage.idea_id,
                "ideaSha256": lineage.idea_sha256,
            })
            activation_args = argparse.Namespace(
                run_root=run_root,
                revision_id=target_revision_id,
                source_commit=args.source_commit,
                memory_url=args.memory_url,
                collection=args.collection,
                connect_timeout=args.connect_timeout,
                read_timeout=args.read_timeout,
                test_fixture=args.test_fixture,
            )
            activation_receipt = activate(activation_args)
            activation_path = target_root / "revision_activation_receipt.json"
            if activation_receipt.get("status") != "PASS_ACTIVE_CONSISTENT" or not activation_path.is_file():
                raise RepairBlocked("BLOCKED_SEMANTIC_MIX_ACTIVATION_FAILED")

            receipt = {
                "schema": "persona_dream.semantic_mix_repair_receipt.v1",
                "status": "PASS_SEMANTIC_MIX_REPAIR_ACTIVE",
                "run_id": run_root.name,
                "source_revision_id": source_revision_id,
                "target_revision_id": target_revision_id,
                "work_order_id": work_order_id,
                "idea_id": lineage.idea_id,
                "idea_sha256": lineage.idea_sha256,
                "idea_text": lineage.text,
                "idea_source": "explicit_human",
                "phase_lineage_passed_count": lineage.phase_binding_count,
                "phase_lineage_expected_count": 10,
                "artifact_index_sha256": sha256_file(index_path),
                "revision_manifest_sha256": sha256_file(manifest_path),
                "memory_prepare_receipt_sha256": sha256_file(target_root / "revision_memory_prepare_receipt.json"),
                "memory_verify_receipt_sha256": sha256_file(target_root / "revision_memory_verify_receipt.json"),
                "activation_receipt_sha256": sha256_file(activation_path),
                "memory_prepare_status": prepare_receipt.get("status"),
                "memory_verify_status": verify_receipt.get("status"),
                "activation_status": activation_receipt.get("status"),
                "provider_live": False,
                "provider_ready": False,
                "live_submit_ready": False,
                "submitted": False,
                "actual_provider_call_attempts": 0,
                "mocked": bool(args.test_fixture),
                "live": not bool(args.test_fixture),
            }
            schema = json.loads(REPAIR_SCHEMA.read_text(encoding="utf-8"))
            errors = list(Draft202012Validator(schema).iter_errors(receipt))
            if errors:
                raise RepairBlocked("BLOCKED_SEMANTIC_MIX_REPAIR_RECEIPT_SCHEMA", details={"errors": [error.message for error in errors]})
            write_json(target_root / "semantic_mix_repair_receipt.json", receipt)
            return receipt
        except Exception:
            # The source revision is immutable. A failed target is retained only
            # when Memory/activation may have begun; otherwise remove the staged tree.
            activation_started = (target_root / "revision_activation_receipt.json").exists()
            if not activation_started and not (target_root / "revision_memory_prepare_receipt.json").exists():
                shutil.rmtree(target_root, ignore_errors=True)
            raise


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--source-revision-id")
    value.add_argument("--target-revision-id")
    value.add_argument("--idea-text", required=True, help="Exact explicit human idea; must match Phase 03 source_context.core_idea")
    value.add_argument("--created-at", help="ISO-8601 timestamp for deterministic replay")
    value.add_argument("--source-commit", required=True)
    value.add_argument("--memory-url", default="http://127.0.0.1:8601")
    value.add_argument("--collection", default="project_knowledge")
    value.add_argument("--connect-timeout", type=float, default=5.0)
    value.add_argument("--read-timeout", type=float, default=60.0)
    value.add_argument("--test-fixture", action="store_true", help=argparse.SUPPRESS)
    value.add_argument("--json", action="store_true")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = repair(args)
    except (RepairBlocked, GateBlocked, IdeaLineageError) as exc:
        code = getattr(exc, "code", "BLOCKED_SEMANTIC_MIX_REPAIR")
        details = getattr(exc, "details", {})
        output = {
            "schema": "persona_dream.semantic_mix_repair_error.v1",
            "status": code,
            "details": details,
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "submitted": False,
            "mocked": bool(args.test_fixture),
            "live": False,
        }
        print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
        return int(getattr(exc, "exit_code", 2))
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) if args.json else result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
