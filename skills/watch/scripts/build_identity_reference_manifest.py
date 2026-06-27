"""Build a Watch identity reference manifest from tracking crops.

This artifact is the bridge between domain priors and identity verification. It
does not approve identities. It tells the next rung exactly which crop images
need reference comparison, human approval, and Qdrant/Jina embedding before a
track can be persisted as a supported character observation.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
DEFAULT_CROP_MANIFEST = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_tracking_crops"
    / "watch_tracking_crops.bad_santa_marcus.json"
)
DEFAULT_IDENTITY_REPORT = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_identity_verification"
    / "watch_identity_verification.bad_santa_marcus.json"
)
DEFAULT_REFERENCE_SOURCES = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_character_reference_sources"
    / "summary.json"
)
DEFAULT_OUT_DIR = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_identity_references"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crop-manifest", type=Path, default=DEFAULT_CROP_MANIFEST)
    parser.add_argument("--identity-report", type=Path, default=DEFAULT_IDENTITY_REPORT)
    parser.add_argument("--reference-sources", type=Path, default=DEFAULT_REFERENCE_SOURCES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    crop_manifest = _read_json(args.crop_manifest)
    identity_report = _read_json(args.identity_report)
    reference_sources = _read_json(args.reference_sources) if args.reference_sources.exists() else None
    manifest = _build_manifest(
        args.crop_manifest,
        crop_manifest,
        args.identity_report,
        identity_report,
        args.reference_sources if reference_sources else None,
        reference_sources,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "watch_identity_reference_manifest.bad_santa_marcus.json"
    _write_json(manifest_path, manifest)
    inspection_path = args.out_dir / "inspection.md"
    inspection_path.write_text(_inspection(manifest_path, manifest), encoding="utf-8")

    print("identity_reference_manifest_ok", manifest["candidate_count"])
    print("review_crop_count", manifest["review_crop_count"])
    print("approved_reference_count", manifest["approved_reference_count"])
    print("manifest", manifest_path)
    return 0


def _build_manifest(
    crop_manifest_path: Path,
    crop_manifest: dict[str, Any],
    identity_report_path: Path,
    identity_report: dict[str, Any],
    reference_sources_path: Path | None,
    reference_sources: dict[str, Any] | None,
) -> dict[str, Any]:
    candidates: dict[str, dict[str, Any]] = {}
    review_crops_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)

    crop_by_overlay = {crop["overlay_id"]: crop for crop in crop_manifest.get("crops", [])}
    for result in identity_report.get("results", []):
        candidate = result.get("candidate_entity") or {}
        name = candidate.get("name") or "unresolved"
        key = candidate.get("entity_id") or f"unresolved/{name}"
        candidate_record = candidates.setdefault(
            key,
            {
                "entity_id": candidate.get("entity_id"),
                "name": name,
                "kind": candidate.get("kind"),
                "actor_name": candidate.get("actor_name"),
                "source_status": candidate.get("status"),
                "approved_references": [],
                "rejected_references": [],
                "reference_source_candidates": [],
                "required_positive_reference_count": 3,
                "required_negative_reference_count": 3,
                "required_embedding_modalities": ["frame_crop", "reference_image"],
                "promotion_rule": (
                    "A track can become SUPPORTED only after approved reference "
                    "images or embeddings compare the candidate to the specific "
                    "track crop, or a human approves the overlay."
                ),
            },
        )
        if not candidate_record["reference_source_candidates"]:
            candidate_record["reference_source_candidates"] = _matching_reference_sources(
                candidate_record,
                reference_sources,
            )
        crop = crop_by_overlay.get(result.get("overlay_id"))
        if crop:
            review_crops_by_candidate[key].append(
                {
                    "overlay_id": crop["overlay_id"],
                    "track_id": crop["track_id"],
                    "crop_path": crop["crop_path"],
                    "crop_size": crop["crop_size"],
                    "time_range": result.get("time_range"),
                    "current_verdict": result.get("verdict"),
                    "current_failure_codes": result.get("failure_codes", []),
                    "qdrant_point_plan": {
                        "collection": "watch_multimodal",
                        "point_id": f"{crop['asset_uid']}_{crop['segment_id']}_{crop['track_id']}_frame_crop",
                        "modality": "frame_crop",
                        "embedding_model": "jina-clip-or-current-watch-multimodal-model",
                        "write_status": "PLANNED_NOT_WRITTEN",
                    },
                }
            )

    candidate_records = []
    for key, record in sorted(candidates.items()):
        review_crops = review_crops_by_candidate.get(key, [])
        record["review_crops"] = review_crops
        record["review_crop_count"] = len(review_crops)
        record["reference_status"] = (
            "MISSING_APPROVED_REFERENCES"
            if not record["approved_references"]
            else "HAS_APPROVED_REFERENCES"
        )
        candidate_records.append(record)

    approved_count = sum(
        len(candidate["approved_references"]) for candidate in candidate_records
    )
    review_crop_count = sum(candidate["review_crop_count"] for candidate in candidate_records)
    return {
        "schema_version": "watch.identity_reference_manifest.v1",
        "status": "DRY_RUN_ONLY",
        "posted": False,
        "source_crop_manifest": _display_path(crop_manifest_path),
        "source_identity_report": _display_path(identity_report_path),
        "source_reference_sources": _display_path(reference_sources_path) if reference_sources_path else None,
        "candidate_count": len(candidate_records),
        "review_crop_count": review_crop_count,
        "approved_reference_count": approved_count,
        "qdrant_write_status": "PLANNED_NOT_WRITTEN",
        "memory_write_status": "PLANNED_NOT_WRITTEN",
        "candidates": candidate_records,
        "claim_boundary": (
            "This manifest records reference-image and embedding requirements. "
            "It does not prove identity and must not promote any track to "
            "SUPPORTED until the reference requirements are satisfied."
        ),
    }


def _matching_reference_sources(
    candidate: dict[str, Any],
    reference_sources: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not reference_sources:
        return []
    needles = {
        str(candidate.get("name") or "").lower(),
        str(candidate.get("actor_name") or "").lower(),
    }
    needles.discard("")
    matches: list[dict[str, Any]] = []
    for query in reference_sources.get("queries", []):
        haystack = " ".join(
            [
                str(query.get("query") or ""),
                " ".join(str(title or "") for title in query.get("titles", [])),
                " ".join(str(url or "") for url in query.get("urls", [])),
            ]
        ).lower()
        if not any(needle in haystack for needle in needles):
            continue
        matches.append(
            {
                "query": query.get("query"),
                "result_count": query.get("count", 0),
                "urls": query.get("urls", []),
                "status": "DOMAIN_REFERENCE_SOURCE_CANDIDATE",
            }
        )
    return matches


def _inspection(manifest_path: Path, manifest: dict[str, Any]) -> str:
    candidate_lines = "\n".join(
        "- `{name}` refs `{refs}` review crops `{crops}` status `{status}`".format(
            name=candidate["name"],
            refs=len(candidate["approved_references"]),
            crops=candidate["review_crop_count"],
            status=candidate["reference_status"],
        )
        for candidate in manifest["candidates"]
    )
    return f"""# Watch Identity Reference Manifest Inspection

Status: `DRY_RUN_ONLY`

Manifest: `{_display_path(manifest_path)}`

This artifact defines the missing reference-image and embedding evidence needed
to convert live track crops into supported character identities.

## Counts

- Candidates: `{manifest['candidate_count']}`
- Review crops: `{manifest['review_crop_count']}`
- Approved references: `{manifest['approved_reference_count']}`
- Reference source summary: `{manifest.get('source_reference_sources')}`
- Qdrant writes: `{manifest['qdrant_write_status']}`
- Memory writes: `{manifest['memory_write_status']}`

## Candidates

{candidate_lines}

## Claim Boundary

{manifest['claim_boundary']}
"""


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
