#!/usr/bin/env python3
"""Assemble and review one immutable Persona Dream Phase 01-10 revision.

Inputs are an immutable repair work order and an explicit source manifest.
Outputs are a staged revision, per-phase attempt receipts, a revision manifest,
and (only after independent review) an atomically replaced active pointer.
The command performs local filesystem operations only and fails before Phase 11.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import typer

from phase_artifact_contract import validate_revision_artifacts

app = typer.Typer(add_completion=False)

def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def write_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def inventory(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def safe_destination(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root.resolve() and root.resolve() not in candidate.parents:
        raise ValueError(f"destination escapes revision root: {relative}")
    return candidate


def copy_entry(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"repair source missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, copy_function=shutil.copy2)
    else:
        shutil.copy2(source, destination)


def derive_normalized_evidence(revision_root: Path) -> list[Path]:
    crew = read_object(revision_root / "phase_03_crew/crew_contract.json")
    crew_ok = crew.get("mocked") is False and crew.get("live") is True
    crew_receipt = revision_root / "phase_03_crew/crew_gate_receipt.json"
    write_exclusive(
        crew_receipt,
        {
            "schema": "persona_dream.crew_migration_gate_receipt.v1",
            "status": "PASS_CREW_SOURCE_REBOUND" if crew_ok else "BLOCKED_CREW_SOURCE_REBIND",
            "source_sha256": sha256_file(revision_root / "phase_03_crew/crew_contract.json"),
            "checks": {
                "mocked_false": crew.get("mocked") is False,
                "live_true": crew.get("live") is True,
            },
            "claims": {
                "proves": [
                    "the existing crew contract was copied byte-for-byte and locally checked"
                ],
                "does_not_prove": ["a new Memory recall or creative crew selection was executed"],
            },
        },
    )
    if not crew_ok:
        raise ValueError("crew source failed migration gate")

    phase04 = revision_root / "phase_04_contact_sheets"
    source_manifest_path = phase04 / "source_artifacts/reference_asset_manifest.json"
    source_manifest = read_object(source_manifest_path)
    assets = (
        source_manifest.get("assets") if isinstance(source_manifest.get("assets"), list) else []
    )
    checks: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        image = Path(str(asset.get("image_path") or ""))
        copied = phase04 / "source_artifacts/images" / image.name
        expected = str(asset.get("sha256") or "")
        actual = sha256_file(copied).removeprefix("sha256:") if copied.is_file() else ""
        checks.append(
            {
                "asset_id": asset.get("asset_id"),
                "path": str(copied),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "match": bool(expected and expected == actual),
            }
        )
    contact_ok = len(checks) == 5 and all(item["match"] for item in checks)
    requirements_path = phase04 / "contact_sheet_requirements.json"
    manifest_path = phase04 / "contact_sheet_manifest.json"
    gate_path = phase04 / "contact_sheet_gate_receipt.json"
    write_exclusive(
        requirements_path,
        {
            "schema": "persona_dream.contact_sheet_requirements.v1",
            "required_asset_ids": [item["asset_id"] for item in checks],
            "required_count": 5,
        },
    )
    shutil.copy2(source_manifest_path, manifest_path)
    write_exclusive(
        gate_path,
        {
            "schema": "persona_dream.contact_sheet_migration_gate_receipt.v1",
            "status": "PASS_CONTACT_SHEET_SOURCE_REBOUND"
            if contact_ok
            else "BLOCKED_CONTACT_SHEET_SOURCE_REBIND",
            "asset_count": len(checks),
            "checks": checks,
            "claims": {
                "proves": [
                    "five existing accepted contact-sheet image hashes match their source manifest"
                ],
                "does_not_prove": ["new image generation or new visual review"],
            },
        },
    )
    if not contact_ok:
        raise ValueError("contact-sheet source failed migration gate")

    phase05 = revision_root / "phase_05_voices"
    voice_items: list[dict[str, Any]] = []
    for character in ("embry", "kai"):
        receipt_path = phase05 / f"{character}_voice_audition.json"
        wav_path = phase05 / f"{character}_voice_audition.wav"
        receipt = read_object(receipt_path)
        expected = str(receipt.get("chatterbox_receipt", {}).get("metrics", {}).get("sha256", ""))
        actual = sha256_file(wav_path).removeprefix("sha256:")
        voice_items.append(
            {
                "character": character,
                "receipt_sha256": sha256_file(receipt_path),
                "wav_sha256": f"sha256:{actual}",
                "expected_wav_sha256": f"sha256:{expected}",
                "hash_match": expected == actual,
                "mocked": receipt.get("mocked"),
                "live": receipt.get("live"),
                "answer_text_sha256": receipt.get("answer_text_sha256"),
            }
        )
    voice_ok = all(
        item["hash_match"] and item["mocked"] is False and item["live"] is True
        for item in voice_items
    )
    voice_path = phase05 / "voice_evidence.json"
    write_exclusive(
        voice_path,
        {
            "schema": "persona_dream.voice_evidence.v1",
            "status": "PASS_VOICE_EVIDENCE_REBOUND"
            if voice_ok
            else "BLOCKED_VOICE_EVIDENCE_REBIND",
            "items": voice_items,
            "claims": {
                "proves": [
                    "the exact Embry and Kai surf-line Chatterbox audition WAV hashes match their live receipts"
                ],
                "does_not_prove": [
                    "provider voice IDs, public audio URLs, or live provider readiness"
                ],
            },
        },
    )
    if not voice_ok:
        raise ValueError("voice source failed migration gate")
    return [crew_receipt, gate_path, voice_path]


def requirement_results(root: Path) -> dict[str, dict[str, Any]]:
    results = validate_revision_artifacts(root)
    return {
        phase_id: {
            **result,
            "missing": [
                artifact["artifact_id"]
                for artifact in result["artifacts"]
                if artifact["status"] != "CURRENT"
            ],
        }
        for phase_id, result in results.items()
    }


def write_attempts(
    run_root: Path,
    work_order: dict[str, Any],
    results: dict[str, dict[str, Any]],
    revision_root: Path,
) -> list[str]:
    paths: list[str] = []
    for phase_id, result in results.items():
        path = (
            run_root
            / ".persona-dream/repair/attempts"
            / str(work_order["workOrderId"])
            / phase_id
            / "attempt_01.json"
        )
        phase_files = {
            key: value
            for key, value in inventory(revision_root).items()
            if f"phase_{phase_id}" in key
        }
        write_exclusive(
            path,
            {
                "schemaVersion": "persona_dream.repair_attempt.v1",
                "workOrderId": work_order["workOrderId"],
                "phaseId": phase_id,
                "attemptNumber": 1,
                "status": "PASS_REPAIR_PHASE" if not result["missing"] else "BLOCKED_REPAIR_PHASE",
                "inputHashes": {},
                "outputHashes": phase_files,
                "gateReceipts": [],
                "blockers": result["missing"],
            },
        )
        paths.append(str(path))
    return paths


def assemble(work_order_path: Path, source_manifest_path: Path) -> dict[str, Any]:
    work_order = read_object(work_order_path)
    sources = read_object(source_manifest_path)
    if sources.get("source_revision_id") != work_order.get("sourceRevisionId"):
        raise ValueError("source revision mismatch")
    run_root = Path(str(work_order["runRoot"])).resolve()
    revision_id = str(work_order["targetRevisionId"])
    revisions_root = run_root / ".persona-dream/revisions"
    final_root = revisions_root / revision_id
    temporary_root = revisions_root / f".{revision_id}.assembling-{os.getpid()}"
    if final_root.exists():
        manifest = read_object(final_root / "revision_manifest.json")
        return {
            "status": "REUSED_FROZEN_REVISION",
            "revision_root": str(final_root),
            "revision_manifest": str(final_root / "revision_manifest.json"),
            "manifest": manifest,
        }
    temporary_root.mkdir(parents=True, exist_ok=False)
    try:
        for entry in sources.get("entries", []):
            if not isinstance(entry, dict):
                raise ValueError("source entries must be objects")
            copy_entry(
                Path(str(entry["source"])).resolve(),
                safe_destination(temporary_root, str(entry["destination"])),
            )
        derived = derive_normalized_evidence(temporary_root)
        results = requirement_results(temporary_root)
        blockers = [
            f"phase_{phase_id}:{name}"
            for phase_id, result in results.items()
            for name in result["missing"]
        ]
        attempts = write_attempts(run_root, work_order, results, temporary_root)
        manifest_path = temporary_root / "revision_manifest.json"
        manifest = {
            "schema": "persona_dream.revision_manifest.v1",
            "runId": work_order["runId"],
            "revisionId": revision_id,
            "sourceRevisionId": work_order["sourceRevisionId"],
            "status": "FROZEN_ALL_LOCAL_GATES_PASS" if not blockers else "BLOCKED_LOCAL_GATES",
            "mocked": False,
            "live": False,
            "provider_live": False,
            "actual_provider_call_attempts": 0,
            "selectedThroughPhase": "10",
            "sourceManifestPath": str(source_manifest_path.resolve()),
            "sourceManifestSha256": sha256_file(source_manifest_path),
            "artifactHashes": inventory(temporary_root),
            "derivedEvidence": [str(path.relative_to(temporary_root)) for path in derived],
            "phaseResults": results,
            "attemptReceipts": attempts,
            "blockers": blockers,
            "claims": {
                "proves": [
                    "local Phase 01-10 artifacts were assembled and required filenames are present"
                ]
                if not blockers
                else [],
                "does_not_prove": [
                    "external publication",
                    "provider submission",
                    "human acceptance",
                    "semantic equivalence beyond the recorded gates",
                ],
            },
        }
        write_exclusive(manifest_path, manifest)
        if blockers:
            raise ValueError(f"local phase gates blocked: {blockers}")
        os.replace(temporary_root, final_root)
        return {
            "status": "PASS_LOCAL_REVISION_ASSEMBLY",
            "revision_root": str(final_root),
            "revision_manifest": str(final_root / "revision_manifest.json"),
            "manifest": manifest,
        }
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise


def review_and_promote(work_order_path: Path) -> dict[str, Any]:
    work_order = read_object(work_order_path)
    run_root = Path(str(work_order["runRoot"])).resolve()
    revision_id = str(work_order["targetRevisionId"])
    revision_root = run_root / ".persona-dream/revisions" / revision_id
    manifest_path = revision_root / "revision_manifest.json"
    manifest = read_object(manifest_path)
    current_hashes = inventory(revision_root)
    expected_hashes = dict(manifest.get("artifactHashes") or {})
    manifest_relative = "revision_manifest.json"
    current_hashes.pop(manifest_relative, None)
    hash_match = current_hashes == expected_hashes
    results = requirement_results(revision_root)
    blockers = [
        f"phase_{phase_id}:{name}"
        for phase_id, result in results.items()
        for name in result["missing"]
    ]
    if manifest.get("status") != "FROZEN_ALL_LOCAL_GATES_PASS" or not hash_match or blockers:
        raise ValueError(f"revision review blocked: hash_match={hash_match}, blockers={blockers}")
    state_root = run_root / ".persona-dream/state"
    state_root.mkdir(parents=True, exist_ok=True)
    pointer_path = state_root / "active_revision.json"
    if pointer_path.exists():
        current = read_object(pointer_path)
        if current.get("revisionId") != work_order.get("sourceRevisionId"):
            raise ValueError("active revision changed before promotion")
    else:
        current = {"runId": work_order["runId"], "revisionId": work_order["sourceRevisionId"]}
    next_pointer = {
        "schemaVersion": "persona_dream.active_revision_pointer.v1",
        "runId": current["runId"],
        "revisionId": revision_id,
        "revisionRoot": str(revision_root),
        "revisionManifestSha256": sha256_file(manifest_path),
    }
    temporary = pointer_path.with_name(f"{pointer_path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(next_pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, pointer_path)
    receipt_path = state_root / f"revision_promotion_{revision_id}.json"
    write_exclusive(
        receipt_path,
        {
            "schemaVersion": "persona_dream.revision_promotion_receipt.v1",
            "status": "PASS_REVISION_PROMOTION",
            "expectedSourceRevisionId": work_order["sourceRevisionId"],
            "targetRevisionId": revision_id,
            "targetManifestPath": str(manifest_path),
            "targetManifestSha256": sha256_file(manifest_path),
            "activePointerPath": str(pointer_path),
        },
    )
    return {
        "status": "PASS_LOCAL_REVISION_REVIEW_AND_PROMOTION",
        "revision_root": str(revision_root),
        "revision_manifest": str(manifest_path),
        "promotion_receipt": str(receipt_path),
        "active_pointer": str(pointer_path),
    }


def tau_handoff(payload: dict[str, Any], result: dict[str, Any], role: str) -> dict[str, Any]:
    status = "PASS"
    next_name = "repair-reviewer" if role == "repair-installer" else "human"
    evidence_kind = (
        "repair_revision_manifest" if role == "repair-installer" else "revision_promotion_receipt"
    )
    evidence_path = (
        result["revision_manifest"] if role == "repair-installer" else result["promotion_receipt"]
    )
    return {
        "schema": "tau.agent_handoff.v1",
        "github": payload.get("github", {}),
        "goal": payload["goal"],
        "previous_subagent": role,
        "context": {"summary": result["status"], "artifacts": [evidence_path]},
        "result": {
            "status": status,
            "summary": result["status"],
            "evidence": [
                {
                    "kind": evidence_kind,
                    "path": evidence_path,
                    "goal_hash": payload["goal"]["goal_hash"],
                }
            ],
        },
        "rationale": "The immutable Persona Dream repair DAG controls promotion.",
        "next_agent": {
            "name": next_name,
            "executor": "local" if role == "repair-installer" else "human",
            "reason": "Continue through the bounded repair DAG.",
        },
        "required_evidence": [evidence_kind],
        "stop_condition": "Stop at human or any local validation failure.",
    }


@app.command()
def install(
    work_order: Path = typer.Option(...),
    sources: Path = typer.Option(...),
    tau_handoff_mode: bool = typer.Option(False, "--tau-handoff"),
) -> None:
    result = assemble(work_order.resolve(), sources.resolve())
    if tau_handoff_mode:
        payload = json.load(sys.stdin)
        typer.echo(json.dumps(tau_handoff(payload, result, "repair-installer"), sort_keys=True))
    else:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command()
def review(
    work_order: Path = typer.Option(...),
    tau_handoff_mode: bool = typer.Option(False, "--tau-handoff"),
) -> None:
    result = review_and_promote(work_order.resolve())
    if tau_handoff_mode:
        payload = json.load(sys.stdin)
        typer.echo(json.dumps(tau_handoff(payload, result, "repair-reviewer"), sort_keys=True))
    else:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
