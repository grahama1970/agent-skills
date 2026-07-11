#!/usr/bin/env python3
"""Apply a passing public media probe to a panel repair gate receipt.

This is a fail-closed post-publication step. It refuses blocked probes and only
writes an updated panel repair gate receipt when the resulting receipt passes
the existing provider-eligible validator. It does not upload media, push git,
call Kling, or authorize paid provider work.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from validate_panel_repair_gate import validate_receipt


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _relpath(target: Path, start: Path) -> str:
    return os.path.relpath(target.resolve(), start.resolve())


def _validate_probe(probe: dict[str, Any], *, allow_mocked_probe: bool) -> list[str]:
    errors: list[str] = []
    if probe.get("schema") != "persona_dream.provider_media_url_probe_receipt.v1":
        errors.append(f"wrong_probe_schema:{probe.get('schema')}")
    if probe.get("status") != "PASS_PROVIDER_MEDIA_URL_PROBE":
        blockers = probe.get("blockers")
        blocker_text = ",".join(str(blocker) for blocker in blockers) if isinstance(blockers, list) else str(probe.get("status"))
        errors.append(f"provider_media_probe_not_pass:{blocker_text}")
    if probe.get("http_status") != 200:
        errors.append(f"probe_http_status_not_200:{probe.get('http_status')}")
    if not isinstance(probe.get("url"), str) or not probe["url"].startswith(("http://", "https://")):
        errors.append("probe_url_must_be_http_or_https")
    if not isinstance(probe.get("expected_sha256"), str) or not probe["expected_sha256"].startswith("sha256:"):
        errors.append("probe_expected_sha256_must_start_with_sha256")
    if probe.get("observed_sha256") != probe.get("expected_sha256"):
        errors.append("probe_sha256_mismatch")
    if not allow_mocked_probe and probe.get("live") != "yes":
        errors.append("probe_must_be_live_unless_allow_mocked_probe")
    return errors


def apply_provider_media_public_probe(
    *,
    panel_repair_gate_receipt: Path,
    provider_media_probe_receipt: Path,
    output: Path,
    allow_mocked_probe: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    panel_repair_gate_receipt = panel_repair_gate_receipt.resolve()
    provider_media_probe_receipt = provider_media_probe_receipt.resolve()
    output = output.resolve()
    receipt = _read_json(panel_repair_gate_receipt)
    probe = _read_json(provider_media_probe_receipt)
    if not isinstance(receipt, dict):
        raise ValueError("panel repair gate receipt must be a JSON object")
    if not isinstance(probe, dict):
        raise ValueError("provider media probe receipt must be a JSON object")

    probe_errors = _validate_probe(probe, allow_mocked_probe=allow_mocked_probe)
    if probe_errors:
        return {
            "schema": "persona_dream.provider_media_public_probe_application.v1",
            "created_at": created_at or _now_iso(),
            "status": "BLOCKED",
            "first_blocker": {
                "phase": "provider_media_public_probe_application",
                "reason": ";".join(probe_errors),
            },
            "panel_repair_gate_receipt": str(panel_repair_gate_receipt),
            "provider_media_probe_receipt": str(provider_media_probe_receipt),
            "mocked": "yes" if allow_mocked_probe else "no",
            "live": "no",
            "exercised": "provider media probe schema/status/hash/live policy checks",
            "unverified": "public upload, Kling provider fetch behavior, paid-call authorization, Kling submission",
        }

    patched = dict(receipt)
    media_hashes = dict(patched.get("media_hashes") if isinstance(patched.get("media_hashes"), dict) else {})
    panel_id = str(patched.get("panel_id") or "panel")
    media_hashes[panel_id] = probe["expected_sha256"]
    patched.update(
        {
            "status": "PASS_PANEL_REVIEWED",
            "provider_media_status": "PASS",
            "provider_media_urls": [probe["url"]],
            "provider_media_probe_receipt": _relpath(provider_media_probe_receipt, output.parent),
            "media_hashes": media_hashes,
            "provider_packet_status": "PROVIDER_READY",
            "provider_eligibility": True,
            "remaining_blockers": [],
        }
    )

    validation_errors = validate_receipt(
        patched,
        require_provider_eligible=True,
        base_dir=output.parent,
    )
    if validation_errors:
        return {
            "schema": "persona_dream.provider_media_public_probe_application.v1",
            "created_at": created_at or _now_iso(),
            "status": "BLOCKED",
            "first_blocker": {
                "phase": "patched_panel_repair_gate_validation",
                "reason": ";".join(validation_errors),
            },
            "panel_repair_gate_receipt": str(panel_repair_gate_receipt),
            "provider_media_probe_receipt": str(provider_media_probe_receipt),
            "output": str(output),
            "mocked": "yes" if allow_mocked_probe else "no",
            "live": "no",
            "exercised": "provider media probe checks and panel repair gate dry-run patch validation",
            "unverified": "public upload, Kling provider fetch behavior, paid-call authorization, Kling submission",
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(patched, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "schema": "persona_dream.provider_media_public_probe_application.v1",
        "created_at": created_at or _now_iso(),
        "status": "APPLIED_PROVIDER_MEDIA_PUBLIC_PROBE",
        "panel_repair_gate_receipt": str(panel_repair_gate_receipt),
        "provider_media_probe_receipt": str(provider_media_probe_receipt),
        "output": str(output),
        "provider_media_url": probe["url"],
        "sha256": probe["expected_sha256"],
        "mocked": "yes" if allow_mocked_probe else "no",
        "live": "no",
        "exercised": "provider media probe checks, panel repair gate patch, provider-eligible validator",
        "unverified": "Kling provider fetch behavior, paid-call authorization, Kling submission",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-repair-gate-receipt", type=Path, required=True)
    parser.add_argument("--provider-media-probe-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-mocked-probe", action="store_true")
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = apply_provider_media_public_probe(
            panel_repair_gate_receipt=args.panel_repair_gate_receipt,
            provider_media_probe_receipt=args.provider_media_probe_receipt,
            output=args.output,
            allow_mocked_probe=args.allow_mocked_probe,
            created_at=args.created_at,
        )
    except Exception as exc:
        result = {
            "schema": "persona_dream.provider_media_public_probe_application.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc)},
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] == "APPLIED_PROVIDER_MEDIA_PUBLIC_PROBE" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
