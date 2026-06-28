#!/usr/bin/env python3
"""Build concrete Watch reference download/review/approval receipts.

This receipt step records reviewed local reference artifacts before any
embedding, Qdrant write, memory recall, or identity promotion. It supports the
current canary manifest shape so the Watch pipeline can prove local artifact
hashing and review gates without pretending canary crops are production
identity references.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any


RECEIPT_SCHEMA = "watch.reference_download_review_approval_receipt.v1"
SUPPORTED_MANIFEST_SCHEMAS = {
    "watch.approved_reference_manifest.v1",
    "watch.reference_manifest.v1",
}
WATCH_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def stable_id(prefix: str, value: Any) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def assert_no_raw_vectors(value: Any, path: str = "$") -> None:
    forbidden = {"vector", "vectors", "embedding", "embeddings", "dense_vector"}
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in forbidden:
                raise ValueError(f"raw vector field is forbidden at {child_path}")
            assert_no_raw_vectors(child, child_path)
    elif isinstance(value, list):
        if len(value) > 8 and all(isinstance(item, (int, float)) for item in value):
            raise ValueError(f"raw numeric vector array is forbidden at {path}")
        for idx, child in enumerate(value):
            assert_no_raw_vectors(child, f"{path}[{idx}]")


def resolve_local_path(path_value: str | None, *, manifest_path: Path | None = None) -> Path | None:
    if not path_value:
        return None

    raw = Path(path_value)
    if raw.is_absolute():
        return raw

    candidates: list[Path] = []
    if manifest_path is not None:
        candidates.append(manifest_path.parent / raw)
    candidates.extend(
        [
            WATCH_ROOT / raw,
            WATCH_ROOT / "docs" / "architecture" / "generated" / raw,
            Path.cwd() / raw,
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return (WATCH_ROOT / raw).resolve()


def png_dimensions(data: bytes) -> dict[str, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return {"width": int(width), "height": int(height)}


def artifact_metadata(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    media_type = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "application/octet-stream"
    return {
        "local_path": str(path),
        "byte_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "media_type": media_type,
        "dimensions": png_dimensions(data),
    }


def manifest_references(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    refs = manifest.get("references")
    if isinstance(refs, list):
        return [ref for ref in refs if isinstance(ref, dict)]
    return []


def is_canary_reference(ref: dict[str, Any], manifest: dict[str, Any]) -> bool:
    material = " ".join(
        str(value)
        for value in [
            ref.get("approval_source"),
            ref.get("approval_note"),
            ref.get("reference_source"),
            manifest.get("reference_source"),
            manifest.get("approval_boundary"),
        ]
        if value
    ).lower()
    return "canary" in material or "existing_track_crop" in material


def build_reference_receipt_item(
    ref: dict[str, Any],
    *,
    manifest: dict[str, Any],
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    reference_id = str(ref.get("reference_id") or stable_id("watch_ref", ref))
    local_path = resolve_local_path(
        ref.get("local_path") or ref.get("downloaded_artifact_ref") or ref.get("crop_path"),
        manifest_path=manifest_path,
    )
    artifact: dict[str, Any] | None = None
    download_status = "BLOCKED_MISSING_LOCAL_ARTIFACT"
    if local_path is not None and local_path.exists():
        artifact = artifact_metadata(local_path)
        download_status = "DOWNLOADED_LOCAL_ARTIFACT"

    approval_status = str(ref.get("approval_status") or "NOT_APPROVED").upper()
    canary = is_canary_reference(ref, manifest)
    if approval_status == "APPROVED" and artifact and canary:
        source_review_status = "SOURCE_REVIEWED_CANARY"
        receipt_approval_status = "APPROVED_CANARY_PIPELINE_ONLY"
        approved_reference_status = "APPROVED_FOR_PIPELINE_CANARY_ONLY"
    elif approval_status == "APPROVED" and artifact:
        source_review_status = "SOURCE_REVIEWED"
        receipt_approval_status = "APPROVED"
        approved_reference_status = "APPROVED"
    elif artifact:
        source_review_status = "BLOCKED_PENDING_HUMAN_REVIEW"
        receipt_approval_status = "BLOCKED_PENDING_SOURCE_REVIEW"
        approved_reference_status = "NOT_APPROVED"
    else:
        source_review_status = "BLOCKED_PENDING_DOWNLOAD"
        receipt_approval_status = "BLOCKED_PENDING_DOWNLOAD"
        approved_reference_status = "NOT_APPROVED"

    identity_promotion_allowed = False
    return {
        "reference_id": reference_id,
        "asset_id": ref.get("asset_id") or manifest.get("asset_id"),
        "entity_id": ref.get("entity_id") or manifest.get("entity_id"),
        "character_name": ref.get("character_name") or manifest.get("character_name"),
        "actor_name": ref.get("actor_name") or manifest.get("actor_name"),
        "provider": ref.get("provider"),
        "source_url": ref.get("source_url"),
        "image_url": ref.get("image_url"),
        "thumbnail_url": ref.get("thumbnail_url"),
        "source_overlay_id": ref.get("source_overlay_id"),
        "download_receipt": {
            "receipt_id": stable_id("watch_ref_download_receipt", reference_id),
            "status": download_status,
            "required": True,
            "artifact": artifact,
        },
        "source_review_receipt": {
            "receipt_id": stable_id("watch_ref_source_review_receipt", reference_id),
            "status": source_review_status,
            "required": True,
            "review_basis": ref.get("approval_note") or manifest.get("approval_boundary"),
            "checks": [
                "source_or_local_artifact_present",
                "review_scope_recorded",
                "character_or_actor_reference_label_recorded",
                "not_scene_truth",
            ],
        },
        "approval_receipt": {
            "receipt_id": stable_id("watch_ref_approval_receipt", reference_id),
            "status": receipt_approval_status,
            "required": True,
            "approved_by": ref.get("approved_by"),
            "approval_time": ref.get("approval_time"),
            "approval_source": ref.get("approval_source") or manifest.get("reference_source"),
            "approval_scope": "CANARY_PIPELINE_ONLY" if canary else "REFERENCE_REVIEW",
        },
        "approved_reference_status": approved_reference_status,
        "scene_truth_claimed": False,
        "identity_promotion_allowed": identity_promotion_allowed,
        "promotion_blockers": [
            "CROP_REFERENCE_SIMILARITY_NOT_PROVEN",
            "MEMORY_RECALL_PROOF_REQUIRED",
            *(
                ["CANARY_REFERENCES_ARE_NOT_INDEPENDENT_PRODUCTION_REFERENCES"]
                if canary
                else []
            ),
        ],
    }


def build_receipt(manifest: dict[str, Any], *, manifest_path: Path | None = None) -> dict[str, Any]:
    schema = manifest.get("schema")
    if schema not in SUPPORTED_MANIFEST_SCHEMAS:
        raise ValueError(f"unsupported reference manifest schema: {schema!r}")

    items = [
        build_reference_receipt_item(ref, manifest=manifest, manifest_path=manifest_path)
        for ref in manifest_references(manifest)
    ]
    downloaded = sum(1 for item in items if item["download_receipt"]["status"] == "DOWNLOADED_LOCAL_ARTIFACT")
    approved = sum(1 for item in items if item["approval_receipt"]["status"] in {"APPROVED", "APPROVED_CANARY_PIPELINE_ONLY"})
    canary_approved = sum(1 for item in items if item["approval_receipt"]["status"] == "APPROVED_CANARY_PIPELINE_ONLY")
    blocked = sum(1 for item in items if item["approval_receipt"]["status"].startswith("BLOCKED"))

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "RECEIPTS_WRITTEN" if items else "NO_REFERENCES",
        "asset_id": manifest.get("asset_id"),
        "source_reference_manifest_schema": schema,
        "source_reference_manifest_path": str(manifest_path) if manifest_path else None,
        "reference_receipts": items,
        "receipt_requirements": {
            "download_receipts_required": True,
            "source_review_receipts_required": True,
            "approval_receipts_required": True,
            "approved_before_embedding": True,
            "independent_reference_package_required_for_identity_promotion": True,
        },
        "promotion_policy": {
            "candidate_url_can_promote_identity": False,
            "download_without_approval_can_promote_identity": False,
            "approval_without_crop_similarity_can_promote_identity": False,
            "canary_reference_can_promote_identity": False,
            "scene_truth_claim_allowed": False,
        },
        "counts": {
            "reference_count": len(items),
            "local_artifact_count": downloaded,
            "downloaded_reference_count": downloaded,
            "approved_reference_count": approved,
            "canary_approved_reference_count": canary_approved,
            "blocked_reference_count": blocked,
        },
        "proof_scope": [
            "reference_download_review_approval_receipts",
            "local_artifact_hashes",
            "canary_fail_closed_identity_gate",
        ],
        "claims": {
            "proves": [
                "local reference artifacts have deterministic download, source-review, and approval receipts",
                "local reference artifacts were hashed and counted before embedding or similarity comparison",
                "canary references remain blocked from identity promotion without crop/reference similarity and memory recall proof",
            ],
            "does_not_prove": [
                "public web image download success",
                "license suitability for external images",
                "production human approval",
                "Jina embedding success",
                "Qdrant write success",
                "crop/reference similarity",
                "supported character identity",
            ],
        },
    }
    assert_no_raw_vectors(receipt)
    return receipt


def write_inspection_markdown(path: Path, receipt: dict[str, Any]) -> None:
    counts = receipt["counts"]
    lines = [
        "# Watch Reference Download/Review/Approval Receipt",
        "",
        f"- schema: `{receipt['schema']}`",
        f"- status: `{receipt['status']}`",
        f"- references: {counts['reference_count']}",
        f"- local artifacts: {counts['local_artifact_count']}",
        f"- approved references: {counts['approved_reference_count']}",
        f"- canary approved references: {counts['canary_approved_reference_count']}",
        f"- blocked references: {counts['blocked_reference_count']}",
        "",
        "## Boundary",
        "",
        "This receipt hashes reviewed local artifacts and records approval scope. It does not prove identity, embedding, Qdrant writes, crop/reference similarity, memory recall, or scene truth.",
        "",
        "## References",
        "",
    ]
    for item in receipt["reference_receipts"]:
        artifact = item["download_receipt"].get("artifact") or {}
        lines.extend(
            [
                f"- `{item['reference_id']}`",
                f"  - entity: `{item.get('entity_id')}`",
                f"  - actor/character: `{item.get('actor_name')}` / `{item.get('character_name')}`",
                f"  - download: `{item['download_receipt']['status']}`",
                f"  - approval: `{item['approval_receipt']['status']}`",
                f"  - sha256: `{artifact.get('sha256')}`",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-manifest", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    manifest = load_json(args.reference_manifest)
    receipt = build_receipt(manifest, manifest_path=args.reference_manifest.resolve())
    name = args.name or args.reference_manifest.stem
    args.out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.out_dir / f"watch_reference_download_review_approval_receipt.{name}.json"
    inspection_path = args.out_dir / f"watch_reference_download_review_approval_receipt.{name}.inspection.md"
    write_json(receipt_path, receipt)
    write_inspection_markdown(inspection_path, receipt)
    print("watch_reference_download_review_approval_receipt", receipt["status"])
    print("references", receipt["counts"]["reference_count"])
    print("local_artifacts", receipt["counts"]["local_artifact_count"])
    print("approved", receipt["counts"]["approved_reference_count"])
    print("receipt", receipt_path)
    print("inspection", inspection_path)


if __name__ == "__main__":
    main()
