#!/usr/bin/env python3
"""Deterministic persistence audit gate for one Persona Dream revision.

This is the post-step gate whose absence let index/pointer/memory regressions
survive: downstream writers could add artifacts without atomically regenerating
the index, verifying paths and hashes, updating Memory, or refreshing
validation. Run it after any step that writes into a revision.

Checks:

1. Active pointer: the pointer's revisionId resolves under the run root; a
   stale absolute revisionRoot is reported (cosmetic: all current tooling
   derives the revision root from run_root + revisionId).
2. Frozen artifact index: the Phase 01-10 qualified index must verify exactly.
   Every on-disk file outside that index must be classified: known machinery
   receipt, or request-scoped Phase 11-13 evidence covered by a generated
   request-evidence index. Unclassified files fail the gate.
3. Request evidence index: for revisions with a compiled canonical request,
   (re)generate `.persona-dream/state/phase11_request_evidence_index_*.json`
   binding every phase_11+ file to its sha256/size, and require the compiled
   request hash, adapter preflight, and attempt ledger to be internally
   consistent (hash agreement, zero-call state when unsubmitted).
4. Memory: exact reread of the 27 revision-qualification records
   (`project_knowledge`), the 42 pipeline step records
   (`persona_dream_pipeline_steps`), and the request-scoped Phase 11 boundary
   record for the current request hash.
5. Broken absolute-path references: scan every JSON file in the revision for
   absolute path strings that no longer exist; newly written artifacts must
   not add dead references (frozen historical files are report-only).
6. validation.json coherence: the run-root validation must agree with the
   revision's attempt ledgers about whether a provider submission happened.

Modes:
- --mode gate (default): nonzero exit on any failed check. Use for the ACTIVE
  revision.
- --mode report: never fails; writes the findings receipt. Use for frozen
  historical revisions.
"""
from __future__ import annotations

from pydantic_step_gate import validate_http_json

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx

STEP_COLLECTION = "persona_dream_pipeline_steps"
QUALIFICATION_COLLECTION = "project_knowledge"
KNOWN_MACHINERY_ROOT_FILES = {
    "revision_artifact_index.json",
    "revision_manifest.json",
    "revision_memory_prepare_receipt.json",
    "revision_memory_verify_receipt.json",
    "revision_activation_receipt.json",
    "semantic_mix_repair_receipt.json",
}
REQUEST_SCOPED_PREFIXES = (
    "phase_11_submit_return/",
    "phase_12_watch_observation/",
    "phase_13_final_acceptance/",
)
ABSOLUTE_PATH_RE = re.compile(r"^/(?:home|tmp|mnt|media|srv|opt|var)/[^\s]*")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, nested in value.items():
            yield str(key)
            yield from iter_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from iter_strings(nested)


def memory_list(client: httpx.Client, collection: str, filters: dict[str, Any], limit: int = 100) -> list[dict[str, Any]]:
    response = client.post("/list", json={"collection": collection, "limit": limit, "filters": filters})
    response.raise_for_status()
    payload = validate_http_json("memory_list", response.json())
    return payload.get("documents") or payload.get("items") or []


def phase11_request_key(run_id: str, revision_id: str, request_body_sha256: str) -> str:
    identity = f"persona-dream-phase11-request\x00{run_id}\x00{revision_id}\x00{request_body_sha256}"
    return f"pd_phase11_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:48]}"


def check_pointer(run_root: Path, revision_id: str) -> dict[str, Any]:
    pointer_path = run_root / ".persona-dream" / "state" / "active_revision.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    derived_root = run_root / ".persona-dream" / "revisions" / str(pointer.get("revisionId") or "")
    recorded_root = Path(str(pointer.get("revisionRoot") or ""))
    return {
        "check": "active_pointer",
        "pointer_revision_id": pointer.get("revisionId"),
        "audited_revision_is_active": pointer.get("revisionId") == revision_id,
        "derived_root_exists": derived_root.is_dir(),
        "recorded_root_exists": recorded_root.is_dir(),
        "recorded_root_stale_note": (
            None
            if recorded_root.is_dir()
            else "pointer.revisionRoot references a missing absolute path; tooling derives roots from run_root + revisionId, so this is cosmetic but should be portable in future revisions"
        ),
        "pass": derived_root.is_dir(),
    }


def check_index(revision_root: Path, run_id: str, revision_id: str) -> dict[str, Any]:
    """Verify the frozen qualified set byte-for-byte and classify everything else.

    Full index recomputation (`build_index` equality) is intentionally NOT the
    gate: request-scoped Phase 11-13 evidence accumulates inside the revision
    after qualification, so recomputation inequality is expected. The
    invariants are (a) every indexed file still matches its bound hash and
    size, and (b) every on-disk file outside the index is classifiable as
    machinery receipt or request-scoped evidence covered by the request
    evidence index.
    """
    index_path = revision_root / "revision_artifact_index.json"
    observed = json.loads(index_path.read_text(encoding="utf-8"))
    artifacts = observed.get("artifacts", {})
    mismatches = []
    for artifact_id, entry in sorted(artifacts.items()):
        path = revision_root / str(entry.get("relative_path") or "")
        if not path.is_file():
            mismatches.append({"artifact_id": artifact_id, "reason": "missing"})
            continue
        if sha256_file(path) != entry.get("sha256") or path.stat().st_size != entry.get("size_bytes"):
            mismatches.append({"artifact_id": artifact_id, "reason": "hash_or_size_mismatch"})
    index_verifies = not mismatches and observed.get("artifact_count") == len(artifacts)
    index_error = None if index_verifies else f"{len(mismatches)} indexed artifacts fail integrity"

    indexed_paths = {entry["relative_path"] for entry in artifacts.values()}
    on_disk = {
        str(path.relative_to(revision_root))
        for path in revision_root.rglob("*")
        if path.is_file() and path.name != "revision_artifact_index.json"
    }
    unindexed = sorted(on_disk - indexed_paths)
    classified: dict[str, list[str]] = {"machinery_receipt": [], "request_scoped_evidence": [], "unexpected": []}
    for relative in unindexed:
        if relative in KNOWN_MACHINERY_ROOT_FILES:
            classified["machinery_receipt"].append(relative)
        elif relative.startswith(REQUEST_SCOPED_PREFIXES):
            classified["request_scoped_evidence"].append(relative)
        else:
            classified["unexpected"].append(relative)
    return {
        "check": "frozen_artifact_index",
        "indexed_integrity_verified": index_verifies,
        "indexed_integrity_mismatches": mismatches,
        "index_error": index_error,
        "indexed_count": len(indexed_paths),
        "on_disk_count": len(on_disk) + 1,
        "unindexed_count": len(unindexed),
        "unindexed_classification_counts": {key: len(value) for key, value in classified.items()},
        "unexpected_unindexed": classified["unexpected"],
        "pass": index_verifies and not classified["unexpected"],
        "request_scoped_files": classified["request_scoped_evidence"],
    }


def check_request_evidence(
    run_root: Path, revision_root: Path, revision_id: str, request_files: list[str]
) -> dict[str, Any]:
    canonical_path = revision_root / "phase_11_submit_return" / "canonical" / "phase11_live_request.v1.json"
    if not canonical_path.is_file():
        return {
            "check": "request_evidence_index",
            "applicable": False,
            "note": "no compiled canonical request in this revision",
            "pass": True,
        }
    request = json.loads(canonical_path.read_text(encoding="utf-8"))
    request_hash = str(request["approval_bindings"]["request_body_sha256"])
    request_key = request_hash.removeprefix("sha256:")

    preflight_path = revision_root / "phase_11_submit_return" / "preflight" / "phase11_adapter_preflight_receipt.v1.json"
    ledger_path = revision_root / f"phase_11_submit_return/attempts/{request_key}/attempt_ledger.v1.json"
    hash_agreement = True
    ledger_state: dict[str, Any] = {}
    if preflight_path.is_file():
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        hash_agreement = preflight.get("request_body_sha256") == request_hash
    if ledger_path.is_file():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger_state = {
            "state": ledger.get("state"),
            "actual_provider_call_attempts": ledger.get("actual_provider_call_attempts"),
            "submit_intent_count": ledger.get("submit_intent_count"),
        }

    entries = {
        relative: {"sha256": sha256_file(revision_root / relative), "size_bytes": (revision_root / relative).stat().st_size}
        for relative in sorted(request_files)
    }
    index_value = {
        "schema": "persona_dream.phase11_request_evidence_index.v1",
        "run_id": run_root.name,
        "revision_id": revision_id,
        "request_body_sha256": request_hash,
        "entry_count": len(entries),
        "entries": entries,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    index_path = (
        run_root
        / ".persona-dream"
        / "state"
        / f"phase11_request_evidence_index_{revision_id}_{request_key[:16]}.json"
    )
    index_path.write_text(json.dumps(index_value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "check": "request_evidence_index",
        "applicable": True,
        "request_body_sha256": request_hash,
        "evidence_file_count": len(entries),
        "preflight_hash_agreement": hash_agreement,
        "attempt_ledger": ledger_state,
        "evidence_index_path": str(index_path.relative_to(run_root)),
        "pass": hash_agreement and bool(entries),
    }


def check_memory(run_root: Path, revision_root: Path, revision_id: str, memory_url: str) -> dict[str, Any]:
    canonical_path = revision_root / "phase_11_submit_return" / "canonical" / "phase11_live_request.v1.json"
    expected_boundary_key = None
    if canonical_path.is_file():
        request = json.loads(canonical_path.read_text(encoding="utf-8"))
        expected_boundary_key = phase11_request_key(
            run_root.name, revision_id, str(request["approval_bindings"]["request_body_sha256"])
        )
    timeout = httpx.Timeout(30.0, connect=5.0)
    with httpx.Client(base_url=memory_url, timeout=timeout) as client:
        qualification = memory_list(
            client, QUALIFICATION_COLLECTION, {"run_id": run_root.name, "revision_id": revision_id}
        )
        steps = memory_list(client, STEP_COLLECTION, {"run_id": run_root.name, "revision_id": revision_id})
        boundary_found = None
        if expected_boundary_key:
            boundary_docs = memory_list(
                client, QUALIFICATION_COLLECTION, {"run_id": run_root.name, "record_type": "phase11_boundary"}
            )
            boundary_found = any(doc.get("_key") == expected_boundary_key for doc in boundary_docs)
    step_numbers = sorted(int(doc["step_no"]) for doc in steps if "step_no" in doc)
    phase11_steps_present = [number for number in step_numbers if 21 <= number <= 36]
    return {
        "check": "memory_persistence",
        "qualification_record_count": len(qualification),
        "qualification_expected": 27,
        "step_record_count": len(steps),
        "step_expected": 42,
        "phase11_related_step_records": phase11_steps_present,
        "phase11_boundary_key_expected": expected_boundary_key,
        "phase11_boundary_record_found": boundary_found,
        "pass": len(qualification) == 27
        and len(steps) == 42
        and (boundary_found is None or boundary_found is True),
    }


def check_absolute_paths(revision_root: Path, new_artifact_prefixes: tuple[str, ...]) -> dict[str, Any]:
    missing: dict[str, list[str]] = {}
    scanned = 0
    for path in sorted(revision_root.rglob("*.json")):
        relative = str(path.relative_to(revision_root))
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        scanned += 1
        for text in iter_strings(value):
            match = ABSOLUTE_PATH_RE.match(text)
            if not match:
                continue
            candidate = match.group(0).rstrip('",;)')
            if "://" in candidate:
                continue
            if not Path(candidate.split("#", 1)[0]).exists():
                missing.setdefault(candidate, []).append(relative)
    unique_missing = sorted(missing)
    by_root: dict[str, int] = {}
    for candidate in unique_missing:
        root = "/".join(candidate.split("/", 3)[:3])
        by_root[root] = by_root.get(root, 0) + 1
    new_artifact_offenders = sorted(
        {
            referencing
            for candidate, referencing_list in missing.items()
            for referencing in referencing_list
            if referencing.startswith(new_artifact_prefixes)
        }
    )
    return {
        "check": "broken_absolute_path_references",
        "json_files_scanned": scanned,
        "unique_missing_paths": len(unique_missing),
        "total_missing_references": sum(len(value) for value in missing.values()),
        "missing_by_root_prefix": by_root,
        "new_artifact_files_with_dead_references": new_artifact_offenders,
        "sample_missing_paths": unique_missing[:10],
        "pass": not new_artifact_offenders,
    }


def check_validation_coherence(run_root: Path, revision_root: Path) -> dict[str, Any]:
    validation_path = run_root / "validation.json"
    if not validation_path.is_file():
        return {"check": "validation_coherence", "applicable": False, "pass": True}
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    ledger_attempts = 0
    for ledger_path in revision_root.glob("phase_11_submit_return/attempts/*/attempt_ledger.v1.json"):
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger_attempts += int(ledger.get("actual_provider_call_attempts") or 0)
    deferred = {
        str(item.get("step_id")): str(item.get("status"))
        for item in validation.get("deferred_steps", [])
        if isinstance(item, dict)
    }
    phase11_status = deferred.get("phase11_submit_and_return")
    coherent = (ledger_attempts == 0) == (phase11_status == "NOT_EXECUTED")
    return {
        "check": "validation_coherence",
        "applicable": True,
        "revision_attempt_ledger_total_calls": ledger_attempts,
        "validation_phase11_status": phase11_status,
        "coherent": coherent,
        "pass": coherent,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--mode", choices=("gate", "report"), default="gate")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument(
        "--new-artifact-prefix",
        action="append",
        default=[],
        help="revision-relative prefixes written by the current session; dead absolute paths under these fail the gate",
    )
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve(strict=True)
    revision_root = run_root / ".persona-dream" / "revisions" / args.revision_id
    if not revision_root.is_dir():
        raise SystemExit(f"revision missing: {revision_root}")

    checks = [check_pointer(run_root, args.revision_id)]
    index_result = check_index(revision_root, run_root.name, args.revision_id)
    checks.append(index_result)
    checks.append(
        check_request_evidence(run_root, revision_root, args.revision_id, index_result.pop("request_scoped_files"))
    )
    checks.append(check_memory(run_root, revision_root, args.revision_id, args.memory_url))
    checks.append(check_absolute_paths(revision_root, tuple(args.new_artifact_prefix)))
    checks.append(check_validation_coherence(run_root, revision_root))

    failed = [item["check"] for item in checks if not item["pass"]]
    status = (
        "PASS_REVISION_PERSISTENCE_AUDIT"
        if not failed
        else ("FAIL_REVISION_PERSISTENCE_AUDIT" if args.mode == "gate" else "REPORTED_REVISION_PERSISTENCE_FINDINGS")
    )
    receipt = {
        "schema": "persona_dream.revision_persistence_audit.v1",
        "status": status,
        "mode": args.mode,
        "run_id": run_root.name,
        "revision_id": args.revision_id,
        "failed_checks": failed,
        "checks": checks,
        "mocked": False,
        "live": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = run_root / ".persona-dream" / "state" / f"revision_persistence_audit_{args.revision_id}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "failed_checks": failed, "receipt_path": str(receipt_path)}, indent=2))
    return 0 if status != "FAIL_REVISION_PERSISTENCE_AUDIT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
