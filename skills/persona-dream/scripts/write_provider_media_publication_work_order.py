#!/usr/bin/env python3
"""Write a public-media publication work order for one panel.

The work order is an authorization packet, not a publication action. It records
the exact local image/hash, the proposed public URL, and the default
rollback-backed sequence to run only after public-upload authorization exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_provider_media_publication_work_order(
    *,
    run_root: Path,
    panel_id: str,
    panel_repair_gate_receipt: Path,
    provider_media_probe_receipt: Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    receipt_path = panel_repair_gate_receipt.resolve()
    probe_path = provider_media_probe_receipt.resolve()
    receipt = _read_json(receipt_path)
    probe = _read_json(probe_path)
    if not isinstance(receipt, dict):
        raise ValueError("panel repair gate receipt must be an object")
    if not isinstance(probe, dict):
        raise ValueError("provider media probe receipt must be an object")

    image_path_value = receipt.get("generated_image_path") or receipt.get("candidate_image_path")
    if not isinstance(image_path_value, str) or not image_path_value:
        raise ValueError("panel repair gate receipt missing generated image path")
    image_path = Path(image_path_value)
    if not image_path.exists():
        raise ValueError(f"panel image does not exist: {image_path}")
    image_hash = _sha256_file(image_path)
    media_hashes = receipt.get("media_hashes") if isinstance(receipt.get("media_hashes"), dict) else {}
    if image_hash not in set(media_hashes.values()):
        raise ValueError("panel image hash is not listed in media_hashes")

    target_repo_path = f"skills/persona-dream/provider_media/{run_root.name}/{panel_id}.png"
    proposed_url = f"https://raw.githubusercontent.com/grahama1970/agent-skills/main/{target_repo_path}"
    rollback_path = run_root / "storyboard/panel_repair_gate/provider_media_publication_work_orders/rollback"

    return {
        "schema": "persona_dream.provider_media_publication_work_order.v1",
        "created_at": created_at or _now_iso(),
        "created_by": "project_agent",
        "status": "WORK_ORDER_READY_PUBLIC_UPLOAD_AUTH_REQUIRED",
        "run_id": run_root.name,
        "panel_id": panel_id,
        "purpose": "Publish the accepted local Panel 01 candidate to a provider-accessible URL, then prove fetched bytes match the locked hash before any Kling submission.",
        "authorization_required": [
            "public_upload_of_panel_image",
            "git_commit_and_push_or_equivalent_public_asset_publish",
        ],
        "forbidden_actions": [
            "direct_kling_submit",
            "paid_provider_call",
            "nano_banana_final_panel_generation",
            "gemini_final_panel_generation",
            "provider_readiness_without_live_url_probe",
            "hash_or_receipt_rewrite_without_matching_public_fetch",
        ],
        "source_paths": {
            "run_root": str(run_root),
            "panel_repair_gate_receipt": str(receipt_path),
            "provider_media_probe_receipt": str(probe_path),
            "panel_image": str(image_path),
        },
        "current_state": {
            "provider_media_status": receipt.get("provider_media_status"),
            "provider_eligibility": receipt.get("provider_eligibility"),
            "provider_packet_status": receipt.get("provider_packet_status"),
            "probe_status": probe.get("status"),
            "probe_blockers": probe.get("blockers", []),
            "current_provider_media_urls": receipt.get("provider_media_urls", []),
        },
        "locked_media": {
            "local_path": str(image_path),
            "sha256": image_hash,
            "bytes": image_path.stat().st_size,
        },
        "proposed_publication": {
            "method": "git_raw_asset_after_authorized_commit_push",
            "target_repo_path": target_repo_path,
            "proposed_url": proposed_url,
            "rollback_path": str(rollback_path),
        },
        "default_repair_sequence_after_authorization": [
            f"Copy the exact locked image to {target_repo_path}.",
            "Commit and push that asset, or publish the exact same bytes to an equivalent stable public URL.",
            f"Run ./run.sh validate-provider-media-url --url {proposed_url} --expected-sha256 {image_hash} --output <run-root>/storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_20260628T204331Z/provider_media_url_probe_receipt.json --json.",
            "Patch panel_repair_gate_receipt.json provider_media_urls and provider_media_probe_receipt only if the URL probe returns PASS_PROVIDER_MEDIA_URL_PROBE.",
            "Rerun validate-panel-repair-gate --require-provider-eligible, write-panel-source, validate-panel-source, validate-run-root --direction backward.",
        ],
        "verification_commands": [
            f"./run.sh validate-provider-media-url --url {proposed_url} --expected-sha256 {image_hash} --json",
            "./run.sh validate-panel-repair-gate <panel_repair_gate_receipt> --require-provider-eligible",
            "./run.sh validate-panel-source <panel_source_receipt> --run-root <run_root> --json",
            "./run.sh validate-run-root <run_root> --direction backward --json",
        ],
        "fallback_if_verification_fails": [
            "Do not patch provider_eligibility or provider_packet_status.",
            "Keep provider_media_status FAIL and retain the failed probe receipt.",
            "Record the failed URL/probe blocker in the Panel 01 report.",
        ],
        "mocked": "no",
        "live": "no",
        "exercised": "local receipt parse, locked media hash, publication plan generation",
        "unverified": "public upload authorization, public URL fetch, Kling provider fetch behavior, paid-call approval, Kling submission",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--panel-id", required=True)
    parser.add_argument("--panel-repair-gate-receipt", type=Path, required=True)
    parser.add_argument("--provider-media-probe-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        work_order = build_provider_media_publication_work_order(
            run_root=args.run_root,
            panel_id=args.panel_id,
            panel_repair_gate_receipt=args.panel_repair_gate_receipt,
            provider_media_probe_receipt=args.provider_media_probe_receipt,
            created_at=args.created_at,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = {"status": "WROTE", "output": str(args.output), "work_order": work_order}
    except Exception as exc:
        result = {
            "schema": "persona_dream.provider_media_publication_work_order.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "provider_media_publication_work_order", "reason": str(exc)},
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} {result.get('output', '')}".strip())
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
