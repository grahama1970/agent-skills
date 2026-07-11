#!/usr/bin/env python3
"""Validate a persona-dream panel repair gate receipt.

This intentionally avoids an external jsonschema dependency so the gate can run
inside lightweight review and sanity environments.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


FINAL_STATUSES = {
    "PASS_PANEL_REVIEWED",
    "HUMAN_ACCEPTED_WITH_WAIVER",
    "BLOCKED_UNREVIEWED_GENERATION",
    "BLOCKED_PENDING_INDEPENDENT_VERIFICATION",
    "BLOCKED_SCRIPT_COVERAGE",
    "BLOCKED_REFERENCE_EVIDENCE",
    "BLOCKED_VISUAL_CONTRADICTION",
    "BLOCKED_OVERLAY_OR_COMPOSITE",
    "BLOCKED_MAX_ATTEMPTS",
    "BLOCKED_ARTIFACT_INACCESSIBLE",
    "BLOCKED_PROVIDER_MEDIA_URLS",
    "BLOCKED_HUMAN_REVIEW_REQUIRED",
}

PARTIAL_PASS_STATUSES = {
    "PASS_SCRIPT_COVERAGE",
    "PASS_REFERENCE_EVIDENCE",
    "PASS_VISUAL_REVIEW",
}

SUBGATES = [
    "script_coverage_status",
    "post_generation_script_coverage_status",
    "reference_evidence_status",
    "visual_review_status",
    "no_overlay_status",
    "provider_media_status",
]

REQUIRED_RECEIPTS = [
    "requirement_matrix",
    "script_coverage_receipt",
    "post_generation_script_coverage_receipt",
    "reference_receipt",
    "generation_receipt",
    "visual_review_receipt",
    "no_overlay_receipt",
]

RECEIPT_STATUS_FIELDS = {
    "script_coverage_receipt": "script_coverage_status",
    "post_generation_script_coverage_receipt": "post_generation_script_coverage_status",
    "reference_receipt": "reference_evidence_status",
    "visual_review_receipt": "visual_review_status",
    "no_overlay_receipt": "no_overlay_status",
}

PROVIDER_REQUIRED_FIELDS = {
    "provider_media_urls",
    "provider_media_probe_receipt",
    "media_hashes",
    "callback_or_polling_plan",
    "cost_estimate",
    "provider_voice_ids",
}

FORBIDDEN_FINAL_PANEL_BACKENDS = {
    "nano-banana",
    "nano_banana",
    "nanobanana",
    "gemini",
    "gemini-image",
    "gemini_image",
}


def non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def resolve_artifact_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def read_json_artifact(value: str, base_dir: Path, field: str, errors: list[str]) -> dict[str, Any] | None:
    path = resolve_artifact_path(value, base_dir)
    if not path.exists():
        fail(errors, f"{field} does not exist: {path}")
        return None
    try:
        loaded = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 - validator should report data errors.
        fail(errors, f"{field} is not valid JSON: {path}: {exc}")
        return None
    if not isinstance(loaded, dict):
        fail(errors, f"{field} must contain a JSON object: {path}")
        return None
    return loaded


def status_matches(artifact: dict[str, Any], expected: str) -> bool:
    observed = artifact.get("status") or artifact.get("verdict")
    if isinstance(observed, str) and observed.upper() == expected:
        return True
    if expected == "PASS" and observed in {"ok", "passed", "PASS"}:
        return True
    return False


def voice_source_matches(
    artifact: dict[str, Any],
    token: str,
    provider: str,
    voice_id: str,
) -> list[str]:
    errors: list[str] = []
    observed = artifact.get("status") or artifact.get("verdict")
    if not (
        isinstance(observed, str)
        and observed.upper() in {"PASS", "READY", "PROVIDER_VOICE_ID_READY"}
    ):
        errors.append("voice source receipt status/verdict must be PASS or READY")
    if artifact.get("provider") != provider:
        errors.append("voice source receipt provider does not match claimed provider")
    if artifact.get("voice_id") != voice_id:
        errors.append("voice source receipt voice_id does not match claimed voice_id")
    if artifact.get("voice_token") != token:
        errors.append("voice source receipt voice_token does not match claimed token")
    return errors


def provider_media_probe_matches(
    artifact: dict[str, Any],
    provider_urls: list[Any],
    media_hashes: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if artifact.get("schema") != "persona_dream.provider_media_url_probe_receipt.v1":
        errors.append("provider media probe receipt schema is invalid")
    if artifact.get("status") != "PASS_PROVIDER_MEDIA_URL_PROBE":
        errors.append("provider media probe receipt status must be PASS_PROVIDER_MEDIA_URL_PROBE")
    if artifact.get("url") not in provider_urls:
        errors.append("provider media probe URL is not listed in provider_media_urls")
    if artifact.get("expected_sha256") not in set(media_hashes.values()):
        errors.append("provider media probe expected_sha256 is not listed in media_hashes")
    if artifact.get("observed_sha256") != artifact.get("expected_sha256"):
        errors.append("provider media probe observed_sha256 does not match expected_sha256")
    if artifact.get("http_status") != 200:
        errors.append("provider media probe http_status must be 200")
    if artifact.get("mocked") != "yes" and artifact.get("live") != "yes":
        errors.append("provider media probe must be a live public HTTP(S) fetch")
    return errors


def forbidden_final_panel_fallback_errors(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if receipt.get("nano_banana_fallback_used") is True:
        errors.append("nano_banana_fallback_used is forbidden for final/provider-eligible panels")
    if receipt.get("gemini_fallback_used") is True:
        errors.append("gemini_fallback_used is forbidden for final/provider-eligible panels")
    for field in ("generation_backend", "image_backend", "final_panel_backend", "model_backend"):
        value = receipt.get(field)
        if isinstance(value, str) and value.strip().lower() in FORBIDDEN_FINAL_PANEL_BACKENDS:
            errors.append(f"{field}={value} is forbidden for final/provider-eligible panels")
    return errors


def validate_receipt(
    receipt: dict[str, Any],
    require_provider_eligible: bool,
    base_dir: Path,
) -> list[str]:
    errors: list[str] = []

    if receipt.get("schema") != "persona_dream.panel_repair_gate_receipt.v1":
        fail(errors, "schema must be persona_dream.panel_repair_gate_receipt.v1")

    for field in ("run_id", "panel_id"):
        if not non_empty_string(receipt.get(field)):
            fail(errors, f"{field} is required")

    status = receipt.get("status")
    if status in PARTIAL_PASS_STATUSES:
        fail(errors, f"{status} is an intermediate subgate, not a final panel status")
    if status not in FINAL_STATUSES:
        fail(errors, f"status must be one of {sorted(FINAL_STATUSES)}")

    for subgate in SUBGATES:
        value = receipt.get(subgate)
        if value not in {"PASS", "FAIL", "WAIVED"}:
            fail(errors, f"{subgate} must be PASS, FAIL, or WAIVED")

    for receipt_field in REQUIRED_RECEIPTS:
        if not non_empty_string(receipt.get(receipt_field)):
            fail(errors, f"{receipt_field} is required")

    provider_eligible = receipt.get("provider_eligibility")
    if not isinstance(provider_eligible, bool):
        fail(errors, "provider_eligibility must be boolean")

    remaining_blockers = receipt.get("remaining_blockers")
    if not isinstance(remaining_blockers, list) or not all(
        isinstance(item, str) for item in remaining_blockers
    ):
        fail(errors, "remaining_blockers must be a list of strings")

    if receipt.get("provider_mode") != "std" and not receipt.get("provider_mode_waiver"):
        fail(errors, "provider_mode must default to std unless provider_mode_waiver is true")

    if receipt.get("provider_resolution") != "720p" and not receipt.get("provider_mode_waiver"):
        fail(
            errors,
            "provider_resolution must default to 720p unless provider_mode_waiver is true",
        )

    if not non_empty_string(receipt.get("external_task_id")):
        fail(errors, "external_task_id is required")

    if not non_empty_string(receipt.get("callback_or_polling_plan")):
        fail(errors, "callback_or_polling_plan is required")

    voice_status = receipt.get("voice_id_status")
    if voice_status not in {
        "PROVIDER_VOICE_ID_READY",
        "SILENT_SCENE",
        "BLOCKED_MISSING_PROVIDER_VOICE_ID",
    }:
        fail(errors, "voice_id_status is invalid")

    provider_voice_ids = receipt.get("provider_voice_ids")
    if not isinstance(provider_voice_ids, dict):
        fail(errors, "provider_voice_ids must be an object")
    if voice_status == "PROVIDER_VOICE_ID_READY":
        if not provider_voice_ids:
            fail(errors, "provider_voice_ids is required when voice_id_status=PROVIDER_VOICE_ID_READY")
        else:
            for token, voice in provider_voice_ids.items():
                if not isinstance(token, str) or not token.startswith("voice_"):
                    fail(errors, f"provider_voice_ids key must be a voice token: {token!r}")
                if not isinstance(voice, dict):
                    fail(errors, f"provider_voice_ids.{token} must be an object")
                    continue
                if not non_empty_string(voice.get("provider")):
                    fail(errors, f"provider_voice_ids.{token}.provider is required")
                if not non_empty_string(voice.get("voice_id")):
                    fail(errors, f"provider_voice_ids.{token}.voice_id is required")
                if not non_empty_string(voice.get("source_receipt")):
                    fail(errors, f"provider_voice_ids.{token}.source_receipt is required")
                elif require_provider_eligible:
                    source_artifact = read_json_artifact(
                        voice["source_receipt"],
                        base_dir,
                        f"provider_voice_ids.{token}.source_receipt",
                        errors,
                    )
                    if source_artifact is not None:
                        source_errors = voice_source_matches(
                            source_artifact,
                            token,
                            voice["provider"],
                            voice["voice_id"],
                        )
                        for source_error in source_errors:
                            fail(errors, f"provider_voice_ids.{token}.source_receipt: {source_error}")

    if not non_empty_string(receipt.get("cost_estimate")):
        fail(errors, "cost_estimate is required")

    provider_urls = receipt.get("provider_media_urls")
    if not isinstance(provider_urls, list) or not provider_urls:
        fail(errors, "provider_media_urls must contain at least one URL")
    elif not all(isinstance(url, str) and url.startswith(("http://", "https://")) for url in provider_urls):
        fail(errors, "provider_media_urls must be provider-accessible http(s) URLs")
    elif any(
        str(url).startswith(("http://localhost", "https://localhost", "http://127.0.0.1", "https://127.0.0.1"))
        or ".invalid/" in str(url)
        or str(url).endswith(".invalid")
        for url in provider_urls
    ):
        fail(errors, "provider_media_urls must not use localhost or .invalid placeholders")

    media_hashes = receipt.get("media_hashes")
    if not isinstance(media_hashes, dict) or not media_hashes:
        fail(errors, "media_hashes must contain at least one sha256 hash")
    elif not all(isinstance(value, str) and value.startswith("sha256:") for value in media_hashes.values()):
        fail(errors, "media_hashes values must start with sha256:")

    provider_media_probe_receipt = receipt.get("provider_media_probe_receipt")
    provider_media_probe_pass = False
    if receipt.get("provider_media_status") == "PASS" or require_provider_eligible:
        if not non_empty_string(provider_media_probe_receipt):
            fail(errors, "provider_media_probe_receipt is required when provider_media_status=PASS or provider eligibility is required")

    provider_packet_status = receipt.get("provider_packet_status")
    if provider_packet_status not in {
        "BLOCKED_PROVIDER_GATE",
        "DRY_RUN_NOT_LIVE_SUBMITTABLE",
        "PROVIDER_READY",
    }:
        fail(errors, "provider_packet_status is invalid")

    fallback_errors = forbidden_final_panel_fallback_errors(receipt)
    for fallback_error in fallback_errors:
        fail(errors, fallback_error)

    if require_provider_eligible:
        for receipt_field in REQUIRED_RECEIPTS:
            value = receipt.get(receipt_field)
            if non_empty_string(value):
                artifact = read_json_artifact(value, base_dir, receipt_field, errors)
                expected_status_field = RECEIPT_STATUS_FIELDS.get(receipt_field)
                if artifact is not None and expected_status_field:
                    expected_status = receipt.get(expected_status_field)
                    if expected_status == "PASS" and not status_matches(artifact, "PASS"):
                        fail(errors, f"{receipt_field} does not contain matching PASS evidence")

        for field in ("callback_or_polling_plan", "cost_estimate"):
            value = receipt.get(field)
            if non_empty_string(value):
                read_json_artifact(value, base_dir, field, errors)

        if non_empty_string(provider_media_probe_receipt):
            probe_artifact = read_json_artifact(
                provider_media_probe_receipt,
                base_dir,
                "provider_media_probe_receipt",
                errors,
            )
            if probe_artifact is not None and isinstance(provider_urls, list) and isinstance(media_hashes, dict):
                probe_errors = provider_media_probe_matches(probe_artifact, provider_urls, media_hashes)
                if not probe_errors:
                    provider_media_probe_pass = True
                for probe_error in probe_errors:
                    fail(errors, f"provider_media_probe_receipt: {probe_error}")

    hard_pass = (
        status == "PASS_PANEL_REVIEWED"
        and all(receipt.get(subgate) == "PASS" for subgate in SUBGATES)
        and voice_status in {"PROVIDER_VOICE_ID_READY", "SILENT_SCENE"}
        and (
            voice_status == "SILENT_SCENE"
            or (isinstance(provider_voice_ids, dict) and bool(provider_voice_ids))
        )
        and receipt.get("provider_mode") == "std"
        and receipt.get("provider_resolution") == "720p"
        and provider_packet_status == "PROVIDER_READY"
        and isinstance(provider_urls, list)
        and bool(provider_urls)
        and isinstance(media_hashes, dict)
        and bool(media_hashes)
        and non_empty_string(provider_media_probe_receipt)
        and provider_media_probe_pass
        and not fallback_errors
        and not remaining_blockers
    )

    if provider_eligible and not hard_pass:
        fail(errors, "provider_eligibility=true requires PASS_PANEL_REVIEWED and all provider subgates")

    if require_provider_eligible and provider_eligible is not True:
        fail(errors, "--require-provider-eligible requires provider_eligibility=true")

    if require_provider_eligible and not hard_pass:
        fail(errors, "receipt is not provider eligible")

    if status == "PASS_PANEL_REVIEWED" and not hard_pass:
        fail(errors, "PASS_PANEL_REVIEWED requires all subgates and provider fields to pass")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Base directory for relative receipt paths. Defaults to the panel receipt directory.",
    )
    parser.add_argument(
        "--require-provider-eligible",
        action="store_true",
        help="Fail unless the receipt is provider-eligible.",
    )
    args = parser.parse_args(argv)

    receipt_path = args.receipt.resolve()
    receipt = json.loads(receipt_path.read_text())
    if not isinstance(receipt, dict):
        print(json.dumps({"status": "FAIL", "errors": ["receipt must be a JSON object"]}, indent=2))
        return 1
    base_dir = args.artifact_root.resolve() if args.artifact_root else receipt_path.parent
    errors = validate_receipt(receipt, args.require_provider_eligible, base_dir)
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        return 1

    print(json.dumps({"status": "PASS", "receipt": str(args.receipt)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
