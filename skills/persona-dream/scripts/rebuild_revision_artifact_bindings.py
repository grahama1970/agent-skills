#!/usr/bin/env python3
"""Rebuild an existing Persona Dream revision's artifact index and phase bindings.

This command re-derives the revision artifact index, the ten phase idea bindings,
and the idea lineage manifest for an already-created immutable revision, without
copying, re-binding identity, or mutating any source revision. It exists so that
evidence added to a revision after its original creation (for example the Phase C
regenerated storyboard frames and their actual-pixel review receipts) is folded
into the index while montage-derived frames stay marked stale.

It reuses the exact, proven building blocks from ``create_successor_revision`` and
``repair_semantic_mix_revision``:

1. ``write_index`` to recompute ``revision_artifact_index.json`` (Phase C frames
   become the canonical accepted Phase 07 evidence; the ledger-superseded montage
   frames keep stable path-based ids and a ``superseded_frame`` role).
2. ``build_phase_bindings`` / ``build_lineage_manifest`` to rewrite the ten phase
   bindings and the lineage manifest deterministically.
3. ``write_index`` again so the final index covers the rewritten binding files.
4. ``validate_revision_idea_lineage`` to fail closed if the rebuilt lineage does
   not validate.

The command performs no provider work and no Memory writes; run the qualification
chain (prepare/verify/activation) separately after it succeeds.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from idea_lineage import (
    EXPECTED_PHASE_IDS,
    IdeaLineageError,
    build_lineage_manifest,
    build_phase_bindings,
    read_object,
    sha256_file,
    validate_revision_idea_lineage,
    validate_schema,
)
from write_revision_artifact_index import write_index

HUMAN_IDEA_RELPATH = "phase_01_idea/human_idea.json"
LINEAGE_MANIFEST_RELPATH = "phase_01_idea/idea_lineage_manifest.json"
INDEX_NAME = "revision_artifact_index.json"


class RebuildBlocked(RuntimeError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def rebuild(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run_root.expanduser().resolve(strict=True)
    run_id = run_root.name
    revision_id = args.revision_id
    revision_root = (
        run_root / ".persona-dream" / "revisions" / revision_id
    ).resolve(strict=True)
    try:
        revision_root.relative_to(run_root)
    except ValueError as exc:  # pragma: no cover - defensive
        raise RebuildBlocked("BLOCKED_REVISION_PATH_ESCAPE") from exc

    human_path = revision_root / HUMAN_IDEA_RELPATH
    if not human_path.is_file():
        raise RebuildBlocked(
            "BLOCKED_HUMAN_IDEA_MISSING", details={"path": str(human_path)}
        )
    human_idea = read_object(human_path)

    index_path = revision_root / INDEX_NAME
    index_sha_before = sha256_file(index_path) if index_path.is_file() else None

    # 1) Provisional index over the current on-disk tree (now including Phase C).
    provisional_index = write_index(revision_root, index_path, run_id, revision_id)

    # 2) Rewrite the ten phase bindings and the lineage manifest deterministically.
    bindings, binding_paths = build_phase_bindings(
        revision_root, provisional_index, human_idea
    )
    for phase_id in EXPECTED_PHASE_IDS:
        write_json(binding_paths[phase_id], bindings[phase_id])
    lineage_manifest = build_lineage_manifest(
        revision_root, human_path, human_idea, bindings, binding_paths
    )
    validate_schema(
        lineage_manifest, "phase_idea_lineage_manifest.v1.schema.json", phase_id="01"
    )
    write_json(revision_root / LINEAGE_MANIFEST_RELPATH, lineage_manifest)

    # 3) Final index that now covers the rewritten binding files, then 4) validate.
    final_index = write_index(revision_root, index_path, run_id, revision_id)
    lineage = validate_revision_idea_lineage(
        revision_root, run_id, revision_id, final_index
    )

    accepted_frames = sorted(
        artifact_id
        for artifact_id, entry in final_index["artifacts"].items()
        if "accepted_frame" in entry.get("roles", [])
    )
    superseded_frames = sorted(
        entry["relative_path"]
        for entry in final_index["artifacts"].values()
        if "superseded_frame" in entry.get("roles", [])
    )
    return {
        "schema": "persona_dream.revision_artifact_rebuild.v1",
        "status": "PASS_REVISION_ARTIFACT_REBUILT",
        "run_id": run_id,
        "revision_id": revision_id,
        "artifact_index_path": str(index_path),
        "artifact_index_sha256_before": index_sha_before,
        "artifact_index_sha256_after": sha256_file(index_path),
        "artifact_count": final_index["artifact_count"],
        "required_artifact_count": final_index["required_artifact_count"],
        "accepted_frame_artifact_ids": accepted_frames,
        "accepted_frame_count": len(accepted_frames),
        "superseded_frame_relative_paths": superseded_frames,
        "superseded_frame_count": len(superseded_frames),
        "phase_binding_count": lineage.phase_binding_count,
        "idea_id": lineage.idea_id,
        "idea_sha256": lineage.idea_sha256,
        "mocked": False,
        "live": False,
        "actual_provider_call_attempts": 0,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id", required=True)
    value.add_argument("--json", action="store_true")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = rebuild(args)
    except (RebuildBlocked, IdeaLineageError, ValueError) as exc:
        code = getattr(exc, "code", "BLOCKED_REVISION_ARTIFACT_REBUILD")
        output = {
            "schema": "persona_dream.revision_artifact_rebuild_error.v1",
            "status": str(code),
            "details": getattr(exc, "details", {}),
            "mocked": False,
            "live": False,
        }
        print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
        return 2
    print(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False)
        if args.json
        else result["status"]
    )
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
