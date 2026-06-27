"""Verify Watch tracking identity claims before memory persistence.

This is a fail-closed identity gate for live tracker overlay payloads. It does
not run ML, write memory, write Qdrant points, or approve character labels. It
checks whether each UI overlay has the independent evidence required to promote
a provisional domain candidate into a supported Watch observation.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
DEFAULT_OVERLAY_PAYLOAD = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_yolo_overlay_payload"
    / "watch_ui_overlay_payload.bad_santa_marcus.json"
)
DEFAULT_OUT_DIR = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_identity_verification"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay-payload", type=Path, default=DEFAULT_OVERLAY_PAYLOAD)
    parser.add_argument("--crop-manifest", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    payload = _read_json(args.overlay_payload)
    crop_manifest = _read_json(args.crop_manifest) if args.crop_manifest else None
    report = _build_report(args.overlay_payload, payload, args.crop_manifest, crop_manifest)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.out_dir / "watch_identity_verification.bad_santa_marcus.json"
    _write_json(report_path, report)
    inspection_path = args.out_dir / "inspection.md"
    inspection_path.write_text(_inspection(report_path, report), encoding="utf-8")

    counts = report["counts"]
    print("identity_verification_ok", counts["track_count"])
    print("supported_count", counts["supported"])
    print("inconclusive_count", counts["inconclusive"])
    print("failure_codes", sorted(report["failure_code_counts"].keys()))
    print("report", report_path)
    return 0


def _build_report(
    payload_path: Path,
    payload: dict[str, Any],
    crop_manifest_path: Path | None,
    crop_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    if payload.get("schema_version") != "watch.ui_overlay_payload.v1":
        raise ValueError("expected watch.ui_overlay_payload.v1 payload")
    overlays = payload.get("overlays") or []
    if not isinstance(overlays, list):
        raise TypeError("payload.overlays must be a list")

    crop_refs = _crop_refs_by_overlay(crop_manifest)
    results = [_verify_overlay(overlay, crop_refs.get(overlay.get("overlay_id"))) for overlay in overlays]
    verdict_counts = Counter(result["verdict"] for result in results)
    failure_code_counts = Counter(
        code for result in results for code in result["failure_codes"]
    )
    candidate_names = sorted(
        {
            result["candidate_entity"]["name"]
            for result in results
            if result.get("candidate_entity")
        }
    )

    return {
        "schema_version": "watch.identity_verification_report.v1",
        "status": "DRY_RUN_ONLY",
        "posted": False,
        "source_overlay_payload": _display_path(payload_path),
        "source_crop_manifest": _display_path(crop_manifest_path) if crop_manifest_path else None,
        "source_overlay_status": payload.get("status"),
        "proof_scope": ["identity_gate"],
        "excluded_proofs": [
            "person_reid",
            "frame_crop_embedding",
            "human_approval",
            "memory_write",
            "qdrant_write",
            "recall",
        ],
        "counts": {
            "track_count": len(results),
            "supported": verdict_counts.get("SUPPORTED", 0),
            "refuted": verdict_counts.get("REFUTED", 0),
            "inconclusive": verdict_counts.get("INCONCLUSIVE", 0),
        },
        "candidate_names": candidate_names,
        "failure_code_counts": dict(sorted(failure_code_counts.items())),
        "results": results,
        "claim_boundary": (
            "This report verifies the fail-closed identity gate only. It proves "
            "the current overlay payload does not contain enough independent "
            "evidence to promote provisional domain candidates to supported "
            "character identities. It does not write memory, create Qdrant "
            "points, perform re-identification, or prove recall."
        ),
        "next_required_evidence": [
            "per_track_crop_embedding_or_reid_score",
            "frame_or_clip_evidence_binding_candidate_to_track",
            "transcript_or_scene_row_evidence_binding_candidate_to_track",
            "human_overlay_approval_or_correction",
        ],
    }


def _verify_overlay(
    overlay: dict[str, Any],
    crop_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    candidate = overlay.get("identity_candidate")
    evidence = {
        "has_live_track_events": int(overlay.get("source_event_count", 0)) > 0,
        "has_domain_candidate": bool(candidate),
        "has_track_crop_image": bool(crop_ref),
        "has_per_track_reid": _has_basis(candidate, "person_reid_embedding")
        and _candidate_is_verified(candidate),
        "has_track_crop_embedding": bool(overlay.get("track_crop_embedding_ref")),
        "has_frame_clip_binding": bool(overlay.get("frame_clip_identity_evidence")),
        "has_transcript_track_binding": bool(overlay.get("transcript_identity_evidence")),
        "has_human_approval": bool(overlay.get("human_approval_ref")),
    }

    support_reasons: list[str] = []
    if evidence["has_live_track_events"]:
        support_reasons.append("live tracker events exist")
    if evidence["has_domain_candidate"]:
        support_reasons.append("domain candidate attached")

    required_identity_support = [
        evidence["has_per_track_reid"],
        evidence["has_track_crop_embedding"],
        evidence["has_frame_clip_binding"],
        evidence["has_transcript_track_binding"],
        evidence["has_human_approval"],
    ]
    if evidence["has_live_track_events"] and evidence["has_domain_candidate"] and any(required_identity_support):
        verdict = "SUPPORTED"
        failure_codes: list[str] = []
        route = "ANSWER"
        reason = "Track has live events, a domain candidate, and independent identity support."
    else:
        verdict = "INCONCLUSIVE"
        failure_codes = ["TRACK_IDENTITY_UNCERTAIN"]
        if candidate and _candidate_is_provisional(candidate):
            failure_codes.append("DOMAIN_PRIOR_ONLY")
        if not evidence["has_human_approval"]:
            failure_codes.append("NEEDS_HUMAN_REVIEW")
        route = "CLARIFY"
        reason = (
            "YOLO/ByteTrack produced a person track and a domain candidate is "
            "available, but no per-track crop/re-ID, frame binding, transcript "
            "binding, or human approval evidence supports the character label."
        )

    return {
        "overlay_id": overlay.get("overlay_id"),
        "asset_uid": overlay.get("asset_uid"),
        "segment_id": overlay.get("segment_id"),
        "track_id": overlay.get("track_id"),
        "time_range": overlay.get("time_range"),
        "candidate_entity": candidate,
        "crop_ref": crop_ref,
        "source_event_count": overlay.get("source_event_count", 0),
        "evidence_flags": evidence,
        "support_reasons": support_reasons,
        "verdict": verdict,
        "failure_codes": sorted(set(failure_codes)),
        "route": route,
        "reason": reason,
    }


def _has_basis(candidate: dict[str, Any] | None, basis: str) -> bool:
    if not candidate:
        return False
    return basis in set(candidate.get("basis") or [])


def _candidate_is_verified(candidate: dict[str, Any] | None) -> bool:
    if not candidate:
        return False
    return str(candidate.get("status", "")).upper() in {"VERIFIED", "HUMAN_OVERRIDE"}


def _candidate_is_provisional(candidate: dict[str, Any] | None) -> bool:
    if not candidate:
        return False
    return str(candidate.get("status", "")).upper() in {"PROVISIONAL", "CANDIDATE"}


def _crop_refs_by_overlay(crop_manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not crop_manifest:
        return {}
    refs: dict[str, dict[str, Any]] = {}
    for crop in crop_manifest.get("crops") or []:
        refs[crop["overlay_id"]] = {
            "crop_path": crop["crop_path"],
            "crop_size": crop["crop_size"],
            "identity_evidence_status": crop["identity_evidence_status"],
        }
    return refs


def _inspection(report_path: Path, report: dict[str, Any]) -> str:
    counts = report["counts"]
    failure_codes = ", ".join(
        f"`{code}`={count}" for code, count in report["failure_code_counts"].items()
    )
    result_lines = "\n".join(
        "- `{track}` `{verdict}` `{codes}` candidate `{candidate}`".format(
            track=result["track_id"],
            verdict=result["verdict"],
            codes=", ".join(result["failure_codes"]) or "none",
            candidate=(
                result["candidate_entity"]["name"]
                if result.get("candidate_entity")
                else "unresolved"
            ),
        )
        for result in report["results"]
    )
    return f"""# Watch Identity Verification Inspection

Status: `DRY_RUN_ONLY`

Report: `{_display_path(report_path)}`

This artifact is the fail-closed identity gate for the live YOLO/ByteTrack
overlay payload. It consumes UI overlay records and refuses to promote a
character label unless independent per-track evidence supports the domain
candidate.

## Counts

- Tracks inspected: `{counts['track_count']}`
- Supported identities: `{counts['supported']}`
- Inconclusive identities: `{counts['inconclusive']}`
- Refuted identities: `{counts['refuted']}`
- Failure codes: {failure_codes or "`none`"}

## Track Results

{result_lines}

## Claim Boundary

{report['claim_boundary']}

## Next Required Evidence

{chr(10).join(f"- `{item}`" for item in report['next_required_evidence'])}
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
