#!/usr/bin/env python3
"""Create an immutable Persona Dream successor revision bound to a qualified identity source.

This command builds a new immutable revision derived from the frozen source
revision and rebinds Embry's identity truth from the rejected character-sheet
montage to the accepted ``embry_contact_sheet_v3`` contact sheet:

1. Create a new immutable revision with ``sourceRevisionId`` equal to the active
   (frozen) revision, under the durable repo-rooted revisions directory. The
   revision tree for Phase 01-10 is copied byte-for-byte from the frozen source;
   only the revision identity artifacts are rebound.
2. Bind the accepted identity source (path, SHA-256, qualification receipt, and
   Memory record key) as the identity truth for Embry, grounded in the durable
   contact-sheet qualification receipt.
3. Emit an upstream invalidation ledger marking every montage-derived Phase
   07-11 artifact (storyboard frames, storyboard packet, media lock, provider
   packet, provider return) stale or superseded. Provider evidence remains
   recorded as historical evidence, referenced by hash, never reused silently.
4. Recompute the revision artifact index, phase bindings, idea lineage, and
   manifest; run Memory prepare/verify and activation with a durable repo-rooted
   ``active_revision.json`` pointer.
5. Persist the deterministic 42-step pipeline record bundle through Memory with
   exact reread (collection ``persona_dream_pipeline_steps``).

The command never mutates the source revision, never performs provider work, and
stops before compiling or submitting any Kling request. The successor's identity
binding claims no new live identity qualification call — it reuses the accepted
qualification receipt and Memory record produced earlier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    sha256_file,
    validate_revision_idea_lineage,
    validate_schema,
)
from prepare_revision_qualification import GateBlocked, prepare, verify
from write_revision_artifact_index import write_index

# Reuse the proven, deterministic building blocks from the upstream-contract
# reconstruction precedent instead of re-implementing revision assembly.
from reconstruct_upstream_contract_revision import (
    ReconstructionBlocked,
    active_revision,
    atomic_write_json,
    copy_source_revision,
    rewrite_identity_artifacts,
    utc_now,
    write_json,
    write_queue_contract,
)

SKILL_ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR_KIND = "identity_source_successor"
LEDGER_NAME = "identity_successor_invalidation_ledger.v1.json"
GATE_SUMMARY_NAME = "identity_successor_gate_summary.v1.json"
STEP_BUNDLE_NAME = "pipeline_step_records.v1.json"
STEP_COLLECTION = "persona_dream_pipeline_steps"
IDENTITY_BINDING_RELPATH = "phase_07_storyboard_live_tau/identity_source_binding.v1.json"
PERSIST_STEP_SCRIPT = SKILL_ROOT / "scripts" / "persist_pipeline_step_records.py"

# The accepted replacement identity source (HANDOFF 2026-07-18 verified facts).
IDENTITY_QUALIFICATION_RELPATH = "reports/embry-contact-sheet-qualification-20260717.json"
ACCEPTED_ASSET_ID = "embry_contact_sheet_v3"
ACCEPTED_IMAGE_PATH = (
    "/mnt/storage12tb/media/personas/embry/assets/contact_sheets/"
    "embry-gpt-image-2-v3/images/embry_contact_sheet_v3.png"
)
ACCEPTED_IMAGE_SHA256 = (
    "sha256:3ce40b3b6839ebba0f468d75a1adbb7f82e0d95457aefd3627e222eb569de00c"
)
ACCEPTED_IMAGE_WIDTH = 1254
ACCEPTED_IMAGE_HEIGHT = 1254
ACCEPTED_DURABLE_RECEIPTS_DIR = (
    "/mnt/storage12tb/media/personas/embry/assets/contact_sheets/"
    "embry-gpt-image-2-v3/receipts/"
)
ACCEPTED_MEMORY_COLLECTION = "persona_dream_visual_assets"
ACCEPTED_MEMORY_RECORD_KEY = "b11474f2fd5b54f332223a253fd743d1"

# The rejected identity source (frozen source revision reference + receipt).
REJECTED_IMAGE_PATH = (
    "/mnt/storage12tb/media/personas/embry/assets/character_sheet_montage.jpg"
)
REJECTED_REFERENCE_RELPATH = (
    "phase_07_storyboard_live_tau/references/01-embry_character_sheet.jpg"
)
REJECTED_RECEIPT_RELPATH = (
    "phase_07_storyboard_live_tau/receipts/identity_reference_qualification.v1.json"
)

# Montage-derived artifacts that are stale for the successor. Storyboard start/end
# frames, storyboard packet, and media lock live in the copied Phase 07-08 tree;
# the provider packet and provider return remain historical evidence in the
# frozen source revision (Phase 11 is intentionally not copied forward).
STALE_TARGET_ARTIFACTS: tuple[tuple[str, str, str], ...] = (
    (REJECTED_REFERENCE_RELPATH, "07", "rejected Embry identity reference montage"),
    (REJECTED_RECEIPT_RELPATH, "07", "montage identity rejection receipt"),
    ("phase_07_storyboard_live_tau/generated_storyboard_frames/sb_001_start_frame.png", "07", "storyboard frame from rejected montage"),
    ("phase_07_storyboard_live_tau/generated_storyboard_frames/sb_001_end_frame.png", "07", "storyboard frame from rejected montage"),
    ("phase_07_storyboard_live_tau/generated_storyboard_frames/sb_002_start_frame.png", "07", "storyboard frame from rejected montage"),
    ("phase_07_storyboard_live_tau/generated_storyboard_frames/sb_002_end_frame.png", "07", "storyboard frame from rejected montage"),
    ("phase_07_storyboard_live_tau/generated_storyboard_frames/sb_003_start_frame.png", "07", "storyboard frame from rejected montage"),
    ("phase_07_storyboard_live_tau/generated_storyboard_frames/sb_003_end_frame.png", "07", "storyboard frame from rejected montage"),
    ("phase_07_storyboard_live_tau/generated_storyboard_frames/sb_004_start_frame.png", "07", "storyboard frame from rejected montage"),
    ("phase_07_storyboard_live_tau/generated_storyboard_frames/sb_004_end_frame.png", "07", "storyboard frame from rejected montage"),
    ("phase_07_storyboard_live_tau/storyboard_packet.json", "07", "storyboard packet from rejected montage"),
    ("phase_08_media_lock/storyboard_media_lock_manifest.json", "08", "media lock over montage-derived storyboard media"),
)
# Provider evidence recorded historically in the frozen source revision.
STALE_SOURCE_ARTIFACTS: tuple[tuple[str, str, str], ...] = (
    ("phase_11_submit_return/canonical/phase11_live_request.v1.json", "11", "provider packet (canonical live request) from montage-derived storyboard"),
    ("phase_11_submit_return/canonical/phase11_media_binding_manifest.v2.json", "11", "provider media binding manifest from montage-derived storyboard"),
)
# The provider return directory (returned MP4 + receipts) referenced as historical.
PROVIDER_RETURN_REQUEST_KEY = "ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f"


class SuccessorBlocked(RuntimeError):
    def __init__(self, code: str, *, details: Mapping[str, Any] | None = None, exit_code: int = 2) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})
        self.exit_code = exit_code


def deterministic_revision_id(run_id: str, source_revision_id: str) -> str:
    payload = canonical_json_bytes(
        {
            "run_id": run_id,
            "source_revision_id": source_revision_id,
            "successor": "identity-source-v1",
        }
    )
    return f"rev_successor_{hashlib.sha256(payload).hexdigest()[:12]}"


def load_identity_qualification() -> dict[str, Any]:
    """Load and ground the accepted identity source in its durable receipt.

    The binding is never a bare literal: the accepted asset id, image SHA-256,
    dimensions, and Memory record key are read from the qualification receipt and
    asserted against the verified HANDOFF facts, failing closed on any drift.
    """
    receipt_path = SKILL_ROOT / IDENTITY_QUALIFICATION_RELPATH
    if not receipt_path.is_file():
        raise SuccessorBlocked(
            "BLOCKED_IDENTITY_QUALIFICATION_RECEIPT_MISSING",
            details={"path": str(receipt_path)},
        )
    receipt = read_object(receipt_path)
    if receipt.get("schema") != "persona_dream.contact_sheet_identity_qualification.v1":
        raise SuccessorBlocked(
            "BLOCKED_IDENTITY_QUALIFICATION_SCHEMA",
            details={"observed": receipt.get("schema")},
        )
    if receipt.get("status") != "PASS_CONTACT_SHEET_IDENTITY_QUALIFIED":
        raise SuccessorBlocked(
            "BLOCKED_IDENTITY_QUALIFICATION_NOT_PASSED",
            details={"status": receipt.get("status")},
        )
    image = receipt.get("image") or {}
    memory = receipt.get("memory") or {}
    checks = {
        "asset_id": (receipt.get("asset_id"), ACCEPTED_ASSET_ID),
        "image.path": (image.get("path"), ACCEPTED_IMAGE_PATH),
        "image.sha256": (image.get("sha256"), ACCEPTED_IMAGE_SHA256),
        "image.width": (image.get("width"), ACCEPTED_IMAGE_WIDTH),
        "image.height": (image.get("height"), ACCEPTED_IMAGE_HEIGHT),
        "memory.record_key": (memory.get("record_key"), ACCEPTED_MEMORY_RECORD_KEY),
        "memory.semantic_sync_state": (memory.get("semantic_sync_state"), "synced"),
    }
    mismatches = {
        field: {"observed": observed, "expected": expected}
        for field, (observed, expected) in checks.items()
        if observed != expected
    }
    if mismatches:
        raise SuccessorBlocked(
            "BLOCKED_IDENTITY_QUALIFICATION_RECEIPT_MISMATCH",
            details={"mismatches": mismatches},
        )
    return {
        "receipt": receipt,
        "receipt_path": receipt_path,
        "receipt_sha256": sha256_file(receipt_path),
    }


def successor_provenance(source_revision_id: str) -> dict[str, Any]:
    return {
        "derivation": "identity_source_successor_from_frozen_revision",
        "source_revision_id": source_revision_id,
        "identity_qualification": IDENTITY_QUALIFICATION_RELPATH,
        "live_identity_qualification_call": False,
        "successor": True,
    }


def bind_identity_source(
    target_root: Path,
    qualification: Mapping[str, Any],
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
    test_fixture: bool,
) -> Path:
    """Write the successor's identity truth binding for Embry."""
    rejection_reference = target_root / REJECTED_REFERENCE_RELPATH
    rejection_receipt = target_root / REJECTED_RECEIPT_RELPATH
    rejected_reference_sha256 = (
        sha256_file(rejection_reference) if rejection_reference.is_file() else None
    )
    rejected_receipt_sha256 = (
        sha256_file(rejection_receipt) if rejection_receipt.is_file() else None
    )

    binding = {
        "schema": "persona_dream.identity_source_binding.v1",
        "run_id": run_id,
        "revision_id": revision_id,
        "source_revision_id": source_revision_id,
        "created_at": created_at,
        "persona": {"id": "embry", "display_name": "Embry"},
        "accepted_identity_source": {
            "asset_id": ACCEPTED_ASSET_ID,
            "path": ACCEPTED_IMAGE_PATH,
            "sha256": ACCEPTED_IMAGE_SHA256,
            "width": ACCEPTED_IMAGE_WIDTH,
            "height": ACCEPTED_IMAGE_HEIGHT,
            "qualification_receipt": IDENTITY_QUALIFICATION_RELPATH,
            "qualification_receipt_sha256": qualification["receipt_sha256"],
            "qualification_status": "PASS_CONTACT_SHEET_IDENTITY_QUALIFIED",
            "durable_receipts_dir": ACCEPTED_DURABLE_RECEIPTS_DIR,
            "memory": {
                "collection": ACCEPTED_MEMORY_COLLECTION,
                "record_key": ACCEPTED_MEMORY_RECORD_KEY,
                "exact_query": ACCEPTED_ASSET_ID,
                "confidence": 1.0,
                "semantic_sync_state": "synced",
            },
        },
        "rejected_identity_source": {
            "path": REJECTED_IMAGE_PATH,
            "revision_relative_reference": REJECTED_REFERENCE_RELPATH,
            "revision_relative_reference_sha256": rejected_reference_sha256,
            "rejection_receipt": REJECTED_RECEIPT_RELPATH,
            "rejection_receipt_sha256": rejected_receipt_sha256,
            "rejection_status": "FAIL_IDENTITY_REFERENCE_INCONSISTENT",
        },
        "binding_rule": (
            "Embry identity truth for this successor revision is embry_contact_sheet_v3. "
            "Every Phase 07-11 artifact derived from the rejected character-sheet montage "
            "is stale and must be regenerated from this accepted identity source before any "
            "provider request; provider evidence from the source revision is superseded, not "
            "reusable."
        ),
        "provenance": successor_provenance(source_revision_id),
        "claims": {
            "proves": [
                "the successor revision binds Embry's identity to the accepted embry_contact_sheet_v3 source",
                "the binding is grounded in the durable contact-sheet qualification receipt and its Memory record",
            ],
            "does_not_prove": [
                "a new live identity qualification call was executed during successor creation",
                "storyboard frames, provider packet, or provider return were regenerated from the accepted source",
            ],
        },
        "mocked": bool(test_fixture),
        "live": not bool(test_fixture),
        "actual_provider_call_attempts": 0,
    }
    path = target_root / IDENTITY_BINDING_RELPATH
    write_json(path, binding)
    return path


def collect_stale_artifacts(target_root: Path, source_root: Path) -> list[dict[str, Any]]:
    """Enumerate every montage-derived artifact marked stale/superseded."""
    entries: list[dict[str, Any]] = []
    for relative, phase_id, reason in STALE_TARGET_ARTIFACTS:
        path = target_root / relative
        if not path.is_file():
            raise SuccessorBlocked(
                "BLOCKED_STALE_ARTIFACT_MISSING",
                details={"location": "successor", "relative_path": relative},
            )
        entries.append(
            {
                "artifact": relative,
                "location": "successor_revision",
                "relative_path": relative,
                "sha256": sha256_file(path),
                "phase_id": phase_id,
                "disposition": "STALE_IDENTITY_SOURCE_SUPERSEDED",
                "reason": reason,
                "required_action": "regenerate from the accepted embry_contact_sheet_v3 identity source",
            }
        )
    for relative, phase_id, reason in STALE_SOURCE_ARTIFACTS:
        path = source_root / relative
        sha256 = sha256_file(path) if path.is_file() else None
        entries.append(
            {
                "artifact": relative,
                "location": "source_revision",
                "relative_path": relative,
                "sha256": sha256,
                "phase_id": phase_id,
                "disposition": "SUPERSEDED_PROVIDER_EVIDENCE_PRIOR_REVISION",
                "reason": reason,
                "required_action": "recompile a fresh provider request from regenerated storyboard evidence",
            }
        )
    provider_return_dir = (
        source_root
        / "phase_11_submit_return"
        / "provider_return"
        / PROVIDER_RETURN_REQUEST_KEY
    )
    entries.append(
        {
            "artifact": f"phase_11_submit_return/provider_return/{PROVIDER_RETURN_REQUEST_KEY}",
            "location": "source_revision",
            "relative_path": f"phase_11_submit_return/provider_return/{PROVIDER_RETURN_REQUEST_KEY}",
            "sha256": None,
            "phase_id": "11",
            "disposition": "SUPERSEDED_PROVIDER_EVIDENCE_PRIOR_REVISION",
            "reason": "live Kling provider return (returned MP4, ffprobe, contact sheet, continuity review) from the montage-derived request",
            "provider_request_hash": f"sha256:{PROVIDER_RETURN_REQUEST_KEY}",
            "present_in_source": provider_return_dir.is_dir(),
            "required_action": "obtain a new hash-bound authorization and a fresh provider return from the regenerated storyboard",
        }
    )
    return entries


def step_dispositions(step_table: Sequence[tuple[int, str, str, str]]) -> dict[int, dict[str, str]]:
    dispositions: dict[int, dict[str, str]] = {}
    for number, slug, name, previous_status in step_table:
        if 1 <= number <= 12:
            status, disposition, action = (
                previous_status,
                "carried_current",
                "none; upstream of the identity reference and not montage-derived",
            )
        elif 13 <= number <= 29:
            status, disposition, action = (
                "STALE_IDENTITY_SOURCE_SUPERSEDED",
                "stale",
                "regenerate against the accepted embry_contact_sheet_v3 identity source in dependency order",
            )
        elif 30 <= number <= 36 or number == 38:
            status, disposition, action = (
                "SUPERSEDED_PROVIDER_EVIDENCE_PRIOR_REVISION",
                "superseded",
                "provider evidence stays bound to the prior revision and consumed request hash; a repaired request and new hash-bound authorization are required",
            )
        elif number == 37:
            status, disposition, action = (
                "PASS_CARRIED_AUDIO_LANE",
                "carried_current",
                "none; the exact Kai voice line is not montage-derived",
            )
        elif number == 41:
            status, disposition, action = (
                "PASS",
                "current",
                "none; this revision's identity-successor invalidation ledger is the step artifact",
            )
        elif number == 42:
            status, disposition, action = (
                "BLOCKED_AWAITING_STORYBOARD_REGENERATION",
                "blocked",
                "final acceptance requires eight regenerated Phase 07 frames, a repaired provider request, new authorization, and a passing post-provider continuity review",
            )
        else:  # 39, 40
            status, disposition, action = (
                "BLOCKED",
                "blocked",
                "regenerate downstream evidence from the accepted identity source before this gate can close",
            )
        dispositions[number] = {
            "step_slug": slug,
            "step_name": name,
            "previous_status": previous_status,
            "status": status,
            "disposition": disposition,
            "required_action": action,
        }
    return dispositions


def write_invalidation_ledger(
    target_root: Path,
    identity_binding_rel: str,
    identity_binding_sha256: str,
    stale_artifacts: Sequence[Mapping[str, Any]],
    dispositions: Mapping[int, Mapping[str, str]],
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
) -> Path:
    affected_steps = [
        {"step_no": number, **dispositions[number]}
        for number in sorted(dispositions)
        if number >= 13
    ]
    ledger = {
        "schema": "persona_dream.upstream_invalidation_ledger.v1",
        "ledger_kind": "identity_source_successor",
        "run_id": run_id,
        "revision_id": revision_id,
        "source_revision_id": source_revision_id,
        "created_at": created_at,
        "changed_upstream_artifact": {
            "relative_path": identity_binding_rel,
            "sha256": identity_binding_sha256,
            "description": "Embry identity source rebound from rejected montage to accepted embry_contact_sheet_v3",
        },
        "rejected_identity_source": {
            "path": REJECTED_IMAGE_PATH,
            "rejection_receipt": REJECTED_RECEIPT_RELPATH,
            "rejection_status": "FAIL_IDENTITY_REFERENCE_INCONSISTENT",
        },
        "accepted_identity_source": {
            "asset_id": ACCEPTED_ASSET_ID,
            "path": ACCEPTED_IMAGE_PATH,
            "sha256": ACCEPTED_IMAGE_SHA256,
        },
        "stale_artifact_count": len(stale_artifacts),
        "stale_artifacts": list(stale_artifacts),
        "affected_steps": affected_steps,
        "rule": (
            "no Phase 07-11 artifact derived from the rejected montage may be claimed current until it "
            "is regenerated from the accepted embry_contact_sheet_v3 identity source; provider evidence "
            "from the prior revision is superseded, not reusable"
        ),
        "claims": {
            "proves": [
                "every montage-derived Phase 07-11 artifact has an explicit stale or superseded disposition",
                "the identity source change is recorded with the accepted and rejected sources by hash",
            ],
            "does_not_prove": [
                "any downstream artifact has been regenerated from the accepted identity source yet",
            ],
        },
    }
    path = target_root / LEDGER_NAME
    write_json(path, ledger)
    return path


def write_gate_summary(
    target_root: Path,
    stale_artifacts: Sequence[Mapping[str, Any]],
    dispositions: Mapping[int, Mapping[str, str]],
    identity_binding_rel: str,
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
    test_fixture: bool,
) -> Path:
    passing = sorted(
        number
        for number, entry in dispositions.items()
        if not entry["status"].startswith(("BLOCKED", "STALE", "SUPERSEDED", "FAIL"))
    )
    stale = sorted(number for number, entry in dispositions.items() if entry["disposition"] == "stale")
    superseded = sorted(number for number, entry in dispositions.items() if entry["disposition"] == "superseded")
    blocked = sorted(number for number, entry in dispositions.items() if entry["disposition"] == "blocked")
    summary = {
        "schema": "persona_dream.identity_successor_gate_summary.v1",
        "status": "PASS_IDENTITY_SOURCE_SUCCESSOR",
        "run_id": run_id,
        "revision_id": revision_id,
        "source_revision_id": source_revision_id,
        "created_at": created_at,
        "identity_source_binding": identity_binding_rel,
        "accepted_identity_source": ACCEPTED_ASSET_ID,
        "accepted_identity_sha256": ACCEPTED_IMAGE_SHA256,
        "stale_artifact_count": len(stale_artifacts),
        "counts": {
            "total_steps": len(dispositions),
            "passing_or_current": len(passing),
            "stale": len(stale),
            "superseded": len(superseded),
            "blocked": len(blocked),
        },
        "passing_steps": passing,
        "stale_steps": stale,
        "superseded_steps": superseded,
        "blocked_steps": blocked,
        "no_downstream_artifact_silently_current": True,
        "invalidation_ledger": LEDGER_NAME,
        "step_record_bundle": STEP_BUNDLE_NAME,
        "next_gate": (
            "regenerate all eight Phase 07 storyboard start/end frames with the accepted "
            "embry_contact_sheet_v3 identity source and run actual-pixel continuity review; "
            "stop before any provider request"
        ),
        "mocked": bool(test_fixture),
        "live": not bool(test_fixture),
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "submitted": False,
    }
    path = target_root / GATE_SUMMARY_NAME
    write_json(path, summary)
    return path


def build_step_records(
    target_root: Path,
    dispositions: Mapping[int, Mapping[str, str]],
    identity_binding_rel: str,
    *,
    run_id: str,
    revision_id: str,
    source_revision_id: str,
    created_at: str,
) -> Path:
    documents = []
    for number in sorted(dispositions):
        entry = dispositions[number]
        blocked = entry["status"].startswith(("BLOCKED", "STALE", "SUPERSEDED"))
        outputs = [LEDGER_NAME]
        if number == 13:
            outputs = [identity_binding_rel, LEDGER_NAME]
        elif number == 41:
            outputs = [LEDGER_NAME]
        elif number == 42:
            outputs = [GATE_SUMMARY_NAME]
        hashes: dict[str, str] = {}
        for relative in outputs:
            path = target_root / relative
            if path.is_file():
                hashes[relative] = sha256_file(path)
        documents.append(
            {
                "_key": f"persona_dream:{run_id}:{revision_id}:{number:02d}:{entry['step_slug']}",
                "schema": "persona_dream.pipeline_step_memory.v1",
                "run_id": run_id,
                "revision_id": revision_id,
                "source_revision_id": source_revision_id,
                "step_no": number,
                "step_slug": entry["step_slug"],
                "step_name": entry["step_name"],
                "status": entry["status"],
                "disposition": entry["disposition"],
                "previous_status_in_source_revision": entry["previous_status"],
                "inputs": {"source_revision_id": source_revision_id, "repair_kind": SUCCESSOR_KIND},
                "outputs": outputs,
                "receipt_paths": [relative for relative in outputs if relative.endswith(".json")],
                "artifact_hashes": hashes,
                "request_hash": None,
                "provider_task_id": None,
                "memory_write_method": "/upsert",
                "claims": {
                    "proves": [f"step {number:02d} state for successor revision {revision_id} is durably recorded"],
                    "does_not_prove": ["downstream regeneration, provider readiness, or final acceptance"],
                },
                "blocker": entry["required_action"] if blocked else None,
                "observed_at": created_at,
                "retrieval_text": (
                    f"Persona Dream {run_id} {revision_id} step {number:02d} {entry['step_name']} "
                    f"status {entry['status']} disposition {entry['disposition']}"
                ),
                "tags": [
                    "persona-dream",
                    "identity-source-successor",
                    f"run:{run_id}",
                    f"revision:{revision_id}",
                    f"step:{number:02d}",
                    f"status:{entry['status'].lower()}",
                    f"disposition:{entry['disposition']}",
                ],
            }
        )
    bundle = {
        "schema": "persona_dream.pipeline_step_memory_bundle.v1",
        "run_id": run_id,
        "revision_id": revision_id,
        "collection": STEP_COLLECTION,
        "count": len(documents),
        "documents": documents,
    }
    path = target_root / STEP_BUNDLE_NAME
    write_json(path, bundle)
    return path


def persist_step_records(
    run_root: Path,
    revision_id: str,
    memory_url: str,
    *,
    test_fixture: bool,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(PERSIST_STEP_SCRIPT),
            "--run-root",
            str(run_root),
            "--revision-id",
            revision_id,
            "--memory-base-url",
            memory_url,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SuccessorBlocked(
            "BLOCKED_PIPELINE_STEP_MEMORY_PERSISTENCE",
            details={
                "returncode": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-2000:],
            },
            exit_code=4,
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"status": "UNKNOWN", "stdout": completed.stdout[-2000:]}


def _qualification_namespace(args: argparse.Namespace, revision_id: str, command: str | None) -> argparse.Namespace:
    return argparse.Namespace(
        run_root=args.run_root,
        revision_id=revision_id,
        source_commit=args.source_commit,
        memory_url=args.memory_url,
        collection=args.collection,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
        test_fixture=args.test_fixture,
        command=command,
    )


def create(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run_root.expanduser().resolve(strict=True)
    run_id = run_root.name
    source_revision_id, _pointer = active_revision(run_root)
    if args.source_revision_id and args.source_revision_id != source_revision_id:
        raise SuccessorBlocked(
            "BLOCKED_SUCCESSOR_SOURCE_REVISION_CHANGED",
            details={"active_revision_id": source_revision_id, "requested": args.source_revision_id},
        )
    source_root = run_root / ".persona-dream" / "revisions" / source_revision_id
    if not source_root.is_dir():
        raise SuccessorBlocked("BLOCKED_SOURCE_REVISION_MISSING", details={"path": str(source_root)})

    qualification = load_identity_qualification()
    created_at = args.created_at or utc_now()
    target_revision_id = args.target_revision_id or deterministic_revision_id(run_id, source_revision_id)
    target_root = run_root / ".persona-dream" / "revisions" / target_revision_id
    if target_root.exists():
        raise SuccessorBlocked("BLOCKED_SUCCESSOR_TARGET_ALREADY_EXISTS", details={"path": str(target_root)})

    # Import the source step table lazily so the module import stays cheap.
    from reconstruct_upstream_contract_revision import STEP_TABLE

    try:
        copy_source_revision(source_root, target_root)

        human_path = rewrite_identity_artifacts(
            target_root,
            source_root,
            run_id=run_id,
            revision_id=target_revision_id,
            source_revision_id=source_revision_id,
            created_at=created_at,
        )
        identity_binding_path = bind_identity_source(
            target_root,
            qualification,
            run_id=run_id,
            revision_id=target_revision_id,
            source_revision_id=source_revision_id,
            created_at=created_at,
            test_fixture=args.test_fixture,
        )
        identity_binding_rel = str(identity_binding_path.relative_to(target_root))
        identity_binding_sha256 = sha256_file(identity_binding_path)

        stale_artifacts = collect_stale_artifacts(target_root, source_root)
        dispositions = step_dispositions(STEP_TABLE)
        ledger_path = write_invalidation_ledger(
            target_root,
            identity_binding_rel,
            identity_binding_sha256,
            stale_artifacts,
            dispositions,
            run_id=run_id,
            revision_id=target_revision_id,
            source_revision_id=source_revision_id,
            created_at=created_at,
        )
        write_gate_summary(
            target_root,
            stale_artifacts,
            dispositions,
            identity_binding_rel,
            run_id=run_id,
            revision_id=target_revision_id,
            source_revision_id=source_revision_id,
            created_at=created_at,
            test_fixture=args.test_fixture,
        )
        build_step_records(
            target_root,
            dispositions,
            identity_binding_rel,
            run_id=run_id,
            revision_id=target_revision_id,
            source_revision_id=source_revision_id,
            created_at=created_at,
        )

        manifest_path = target_root / "revision_manifest.json"
        write_json(
            manifest_path,
            {
                "schema": "persona_dream.revision_manifest.v1",
                "status": "FROZEN_ALL_LOCAL_GATES_PASS",
                "runId": run_id,
                "revisionId": target_revision_id,
                "sourceRevisionId": source_revision_id,
                "sourceCommit": args.source_commit,
                "createdAt": created_at,
                "repairKind": SUCCESSOR_KIND,
                "ideaId": idea_id(canonical_text(str(read_object(human_path).get("text") or ""))),
                "ideaSha256": idea_sha256(canonical_text(str(read_object(human_path).get("text") or ""))),
                "boundIdentitySource": {
                    "asset_id": ACCEPTED_ASSET_ID,
                    "sha256": ACCEPTED_IMAGE_SHA256,
                    "qualification_receipt": IDENTITY_QUALIFICATION_RELPATH,
                    "qualification_receipt_sha256": qualification["receipt_sha256"],
                    "memory_record_key": ACCEPTED_MEMORY_RECORD_KEY,
                    "binding_relative_path": identity_binding_rel,
                    "binding_sha256": identity_binding_sha256,
                },
                "invalidationLedger": LEDGER_NAME,
                "staleArtifactCount": len(stale_artifacts),
                "actual_provider_call_attempts": 0,
                "provider_live": False,
                "provider_ready": False,
                "live_submit_ready": False,
                "submitted": False,
            },
        )

        index_path = target_root / "revision_artifact_index.json"
        provisional_index = write_index(target_root, index_path, run_id, target_revision_id)
        human_idea = read_object(human_path)
        bindings, binding_paths = build_phase_bindings(target_root, provisional_index, human_idea)
        for phase_id in EXPECTED_PHASE_IDS:
            write_json(binding_paths[phase_id], bindings[phase_id])
        lineage_manifest = build_lineage_manifest(target_root, human_path, human_idea, bindings, binding_paths)
        validate_schema(lineage_manifest, "phase_idea_lineage_manifest.v1.schema.json", phase_id="01")
        write_json(target_root / "phase_01_idea" / "idea_lineage_manifest.json", lineage_manifest)
        final_index = write_index(target_root, index_path, run_id, target_revision_id)
        lineage = validate_revision_idea_lineage(target_root, run_id, target_revision_id, final_index)

        prepare_receipt = prepare(_qualification_namespace(args, target_revision_id, "prepare"))
        verify_receipt = verify(_qualification_namespace(args, target_revision_id, "verify"))

        work_order_id = write_queue_contract(run_root, source_revision_id, target_revision_id, created_at)
        pointer_path = run_root / ".persona-dream" / "state" / "active_revision.json"
        atomic_write_json(
            pointer_path,
            {
                "schemaVersion": "persona_dream.active_revision_pointer.v1",
                "runId": run_id,
                "revisionId": target_revision_id,
                "revisionRoot": str(target_root.resolve()),
                "revisionManifestSha256": sha256_file(manifest_path),
                "ideaId": lineage.idea_id,
                "ideaSha256": lineage.idea_sha256,
            },
        )

        activation_receipt = activate(_qualification_namespace(args, target_revision_id, None))
        activation_path = target_root / "revision_activation_receipt.json"
        if activation_receipt.get("status") != "PASS_ACTIVE_CONSISTENT" or not activation_path.is_file():
            raise SuccessorBlocked("BLOCKED_SUCCESSOR_ACTIVATION_FAILED")

        step_memory = persist_step_records(
            run_root, target_revision_id, args.memory_url, test_fixture=args.test_fixture
        )

        receipt = {
            "schema": "persona_dream.identity_source_successor_receipt.v1",
            "status": "PASS_IDENTITY_SOURCE_SUCCESSOR_ACTIVE",
            "run_id": run_id,
            "source_revision_id": source_revision_id,
            "target_revision_id": target_revision_id,
            "work_order_id": work_order_id,
            "repair_kind": SUCCESSOR_KIND,
            "bound_identity_source": {
                "asset_id": ACCEPTED_ASSET_ID,
                "sha256": ACCEPTED_IMAGE_SHA256,
                "qualification_receipt": IDENTITY_QUALIFICATION_RELPATH,
                "qualification_receipt_sha256": qualification["receipt_sha256"],
                "memory_record_key": ACCEPTED_MEMORY_RECORD_KEY,
                "binding_relative_path": identity_binding_rel,
                "binding_sha256": identity_binding_sha256,
            },
            "invalidation_ledger": LEDGER_NAME,
            "invalidation_ledger_sha256": sha256_file(ledger_path),
            "stale_artifact_count": len(stale_artifacts),
            "gate_summary": GATE_SUMMARY_NAME,
            "step_record_bundle": STEP_BUNDLE_NAME,
            "artifact_index_sha256": sha256_file(index_path),
            "revision_manifest_sha256": sha256_file(manifest_path),
            "revision_root": str(target_root.resolve()),
            "active_pointer_path": str(pointer_path),
            "memory_prepare_status": prepare_receipt.get("status"),
            "memory_verify_status": verify_receipt.get("status"),
            "activation_status": activation_receipt.get("status"),
            "pipeline_step_memory_status": step_memory.get("status"),
            "pipeline_step_memory_receipt": step_memory.get("receipt_path"),
            "pipeline_step_memory_exact_reread_count": step_memory.get("exact_reread_count"),
            "phase_lineage_passed_count": lineage.phase_binding_count,
            "phase_lineage_expected_count": 10,
            "provider_live": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "submitted": False,
            "actual_provider_call_attempts": 0,
            "mocked": bool(args.test_fixture),
            "live": not bool(args.test_fixture),
            "observed_at": utc_now(),
        }
        receipt_path = (
            run_root
            / ".persona-dream"
            / "state"
            / f"identity_source_successor_receipt_{target_revision_id}.json"
        )
        write_json(receipt_path, receipt)
        receipt["receipt_path"] = str(receipt_path)
        return receipt
    except Exception:
        activation_started = (target_root / "revision_activation_receipt.json").exists()
        prepared = (target_root / "revision_memory_prepare_receipt.json").exists()
        if not activation_started and not prepared:
            shutil.rmtree(target_root, ignore_errors=True)
        raise


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--source-revision-id")
    value.add_argument("--target-revision-id")
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
        result = create(args)
    except (SuccessorBlocked, ReconstructionBlocked, GateBlocked, IdeaLineageError) as exc:
        code = getattr(exc, "code", "BLOCKED_IDENTITY_SOURCE_SUCCESSOR")
        output = {
            "schema": "persona_dream.identity_source_successor_error.v1",
            "status": code,
            "details": getattr(exc, "details", {}),
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
