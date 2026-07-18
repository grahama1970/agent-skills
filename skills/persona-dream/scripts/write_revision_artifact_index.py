#!/usr/bin/env python3
"""Write or verify an immutable Persona Dream revision artifact index."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Sequence

from phase_artifact_contract import (
    load_phase_artifact_contract,
    resolve_required_artifact,
    validate_revision_artifacts,
)

INDEX_NAME = "revision_artifact_index.json"
# Qualification receipts are written after the index (see create_successor_revision
# and reconstruct_upstream_contract_revision ordering) and are overwritten on every
# re-run. Excluding them keeps build_index deterministic and idempotent so an
# existing revision can be re-indexed without listing stale hashes for files that a
# subsequent prepare/verify/activate pass rewrites.
VOLATILE_QUALIFICATION_RECEIPTS = frozenset(
    {
        "revision_memory_prepare_receipt.json",
        "revision_memory_verify_receipt.json",
        "revision_activation_receipt.json",
        # The acceptance rung receipt cites the activation receipt, which cites the
        # artifact index; indexing it would be circular, so it is treated the same
        # way as the qualification receipts above.
        "acceptance_rung_receipt.v1.json",
    }
)
FRAME_NAME = re.compile(
    r"^(sb_\d{3})_(start|end)_frame\.(png|jpe?g|webp)$",
    re.IGNORECASE,
)
INVALIDATION_LEDGER_SCHEMA = "persona_dream.upstream_invalidation_ledger.v1"
SUPERSEDED_FRAME_ROLE = "superseded_frame"
PHASE_01_IDENTITY_ARTIFACT_IDS = {
    "human_idea.json": "human_idea",
    "idea_lineage_manifest.json": "idea_lineage_manifest",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def artifact_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if suffix in {".wav", ".mp3", ".flac", ".m4a"}:
        return "audio"
    if suffix in {".mp4", ".webm", ".mov"}:
        return "video"
    if suffix in {".md", ".txt", ".html"}:
        return "text"
    return "other"


def phase_id_for(relative_path: str) -> str | None:
    match = re.search(r"(?:^|/)phase_(\d{2})(?:_|/)", relative_path)
    return match.group(1) if match else None


def optional_artifact_id(phase_id: str | None, relative_path: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", ".", relative_path.lower()).strip(".")
    prefix = f"phase{phase_id}" if phase_id else "revision"
    return f"{prefix}.{normalized}"


def canonical_artifact_id(path: Path, phase_id: str | None, relative_path: str) -> str:
    if phase_id == "01":
        stable_id = PHASE_01_IDENTITY_ARTIFACT_IDS.get(path.name.lower())
        if stable_id:
            return stable_id
    match = FRAME_NAME.fullmatch(path.name)
    if match:
        panel_id = match.group(1).lower()
        role = match.group(2).lower()
        return f"{panel_id}.{role}_frame"
    return optional_artifact_id(phase_id, relative_path)


def media_role(path: Path) -> list[str]:
    match = re.fullmatch(r"(sb_\d{3})_(start|end)_frame\.(?:png|jpe?g|webp)", path.name, re.I)
    if match:
        return ["accepted_frame", f"{match.group(1).lower()}_{match.group(2).lower()}_frame"]
    return []


def load_superseded_frame_paths(revision_root: Path) -> set[str]:
    """Collect revision-relative storyboard-frame paths marked stale/superseded.

    The identity-source successor writes an invalidation ledger that marks every
    montage-derived Phase 07 frame stale. Those frames stay in the tree as
    historical evidence but must yield the canonical ``sb_XXX.<role>_frame``
    accepted-frame slot to the regenerated replacement when one exists.
    """
    superseded: set[str] = set()
    for ledger_path in sorted(revision_root.glob("*invalidation_ledger*.json")):
        try:
            data = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("schema") != INVALIDATION_LEDGER_SCHEMA:
            continue
        for entry in data.get("stale_artifacts") or []:
            if not isinstance(entry, dict):
                continue
            relative = entry.get("relative_path")
            disposition = str(entry.get("disposition") or "")
            if not isinstance(relative, str) or not relative:
                continue
            if not FRAME_NAME.fullmatch(Path(relative).name):
                continue
            if disposition.startswith("STALE") or "SUPERSEDED" in disposition:
                superseded.add(relative)
    return superseded


def resolve_frame_decisions(
    revision_root: Path,
    files: Sequence[Path],
    required_paths: set[str],
    superseded_frames: set[str],
) -> dict[str, str]:
    """Decide, per storyboard-frame file, whether it owns the canonical id.

    A superseded frame yields the canonical ``sb_XXX.<role>_frame`` slot only when
    exactly one non-superseded replacement exists for that id. A superseded frame
    with no live competitor keeps the canonical id (pre-regeneration parity). Two
    live frames, or two superseded frames with no live winner, are a genuine
    collision and fail closed.
    """
    groups: dict[str, list[str]] = {}
    for path in files:
        relative_path = str(path.relative_to(revision_root))
        if relative_path in required_paths:
            continue
        if not FRAME_NAME.fullmatch(path.name):
            continue
        phase_id = phase_id_for(relative_path)
        canonical = canonical_artifact_id(path, phase_id, relative_path)
        groups.setdefault(canonical, []).append(relative_path)

    decisions: dict[str, str] = {}
    for canonical, relatives in groups.items():
        live = [rel for rel in relatives if rel not in superseded_frames]
        if len(live) > 1:
            raise ValueError(f"BLOCKED_PHASE_ARTIFACT_ID_COLLISION:{canonical}")
        if live:
            winner = live[0]
        elif len(relatives) == 1:
            winner = relatives[0]
        else:
            raise ValueError(f"BLOCKED_PHASE_ARTIFACT_ID_COLLISION:{canonical}")
        for rel in relatives:
            decisions[rel] = "canonical" if rel == winner else "superseded"
    return decisions


def build_index(revision_root: Path, run_id: str, revision_id: str) -> dict[str, Any]:
    revision_root = revision_root.resolve()
    validation = validate_revision_artifacts(revision_root)
    blocked = {
        phase_id: result
        for phase_id, result in validation.items()
        if result["status"] != "CURRENT"
    }
    if blocked:
        raise ValueError(f"BLOCKED_REVISION_ARTIFACT_CONTRACT:{sorted(blocked)}")

    contract = load_phase_artifact_contract()
    required_by_path: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for phase_id, phase in contract["phases"].items():
        for requirement in phase["required_artifacts"]:
            path = resolve_required_artifact(revision_root, requirement)
            if path is None:
                raise ValueError(f"BLOCKED_PHASE_ARTIFACT_MISSING:{phase_id}:{requirement['artifact_id']}")
            relative_path = str(path.relative_to(revision_root))
            if relative_path in required_by_path:
                raise ValueError(f"BLOCKED_PHASE_ARTIFACT_ID_COLLISION:{relative_path}")
            required_by_path[relative_path] = (phase_id, requirement["artifact_id"], requirement)

    files = [
        path
        for path in sorted(revision_root.rglob("*"))
        if path.is_file()
        and path.name != INDEX_NAME
        and path.name not in VOLATILE_QUALIFICATION_RECEIPTS
    ]
    superseded_frames = load_superseded_frame_paths(revision_root)
    frame_decisions = resolve_frame_decisions(
        revision_root, files, set(required_by_path), superseded_frames
    )

    artifacts: dict[str, dict[str, Any]] = {}
    for path in files:
        relative_path = str(path.relative_to(revision_root))
        required = required_by_path.get(relative_path)
        phase_id = required[0] if required else phase_id_for(relative_path)
        superseded_frame = frame_decisions.get(relative_path) == "superseded"
        if required:
            artifact_id = required[1]
        elif superseded_frame:
            # A montage-derived frame superseded by a regenerated replacement keeps a
            # stable, path-based optional id instead of the accepted-frame slot.
            artifact_id = optional_artifact_id(phase_id, relative_path)
        else:
            artifact_id = canonical_artifact_id(path, phase_id, relative_path)
        if artifact_id in artifacts:
            raise ValueError(f"BLOCKED_PHASE_ARTIFACT_ID_COLLISION:{artifact_id}")
        requirement = required[2] if required else {}
        base_roles = ["required_evidence"] if required else ["optional_evidence"]
        roles = base_roles + ([SUPERSEDED_FRAME_ROLE] if superseded_frame else media_role(path))
        if requirement.get("consumer_contract"):
            roles.append("consumer_input")
        artifacts[artifact_id] = {
            "phase_id": phase_id,
            "relative_path": relative_path,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "kind": artifact_kind(path),
            "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "schema": requirement.get("schema"),
            "consumer_contract": requirement.get("consumer_contract"),
            "roles": roles,
        }

    manifest_path = revision_root / "revision_manifest.json"
    return {
        "schema": "persona_dream.revision_artifact_index.v1",
        "run_id": run_id,
        "revision_id": revision_id,
        "revision_manifest_sha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
        "phase_contract_schema": contract["schema"],
        "artifact_count": len(artifacts),
        "required_artifact_count": len(required_by_path),
        "artifacts": artifacts,
        "claims": {
            "proves": [
                "required Phase 01-10 artifacts passed the local shared contract",
                "indexed artifact paths are revision-relative and bound to observed hashes",
            ],
            "does_not_prove": [
                "production read-model hydration",
                "UI consumer hydration",
                "Memory, ArangoDB, or Qdrant persistence",
                "active revision promotion",
                "provider readiness or submission",
            ],
        },
        "mocked": False,
        "live": False,
        "provider_live": False,
        "actual_provider_call_attempts": 0,
    }


def write_index(revision_root: Path, output: Path, run_id: str, revision_id: str) -> dict[str, Any]:
    value = build_index(revision_root, run_id, revision_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def verify_index(revision_root: Path, index_path: Path) -> dict[str, Any]:
    observed = json.loads(index_path.read_text(encoding="utf-8"))
    expected = build_index(revision_root, str(observed["run_id"]), str(observed["revision_id"]))
    if observed != expected:
        raise ValueError("BLOCKED_REVISION_ARTIFACT_INDEX_MISMATCH")
    return {
        "schema": "persona_dream.revision_artifact_index_verification.v1",
        "status": "PASS_REVISION_ARTIFACT_INDEX",
        "index_path": str(index_path.resolve()),
        "index_sha256": sha256_file(index_path),
        "artifact_count": expected["artifact_count"],
        "required_artifact_count": expected["required_artifact_count"],
        "mocked": False,
        "live": False,
        "actual_provider_call_attempts": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    write_parser = subparsers.add_parser("write")
    write_parser.add_argument("--revision-root", type=Path, required=True)
    write_parser.add_argument("--output", type=Path)
    write_parser.add_argument("--run-id", required=True)
    write_parser.add_argument("--revision-id", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--revision-root", type=Path, required=True)
    verify_parser.add_argument("--index", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "write":
        output = args.output or args.revision_root / INDEX_NAME
        result = write_index(args.revision_root, output, args.run_id, args.revision_id)
    else:
        result = verify_index(args.revision_root, args.index)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
