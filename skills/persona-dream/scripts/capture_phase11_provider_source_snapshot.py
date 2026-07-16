#!/usr/bin/env python3
"""Capture official fal schema/pricing evidence for the zero-call Phase 11 gate."""
from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from phase11_canonical_common import (
    DEFAULT_CANDIDATE_RELATIVE,
    DEFAULT_MEDIA_LOCK_RELATIVE,
    DEFAULT_PHASE10_RELATIVE,
    DEFAULT_PROVIDER_SNAPSHOT_RELATIVE,
    Phase11Blocked,
    canonical_sha256,
    now_from_argument,
    read_object,
    resolve_active_context,
    sha256_file,
    write_json,
)
from phase11_payload_binding import PayloadBindingBlocked, load_and_validate_payload_binding

DEFAULT_SCHEMA_URL = "https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video/api"
DEFAULT_PRICING_URL = "https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video"
STANDARD_ENDPOINT = "fal-ai/kling-video/v3/standard/image-to-video"
REQUIRED_SCHEMA_TOKENS = (
    "start_image_url",
    "end_image_url",
    "multi_prompt",
    "elements",
    "generate_audio",
    "duration",
    "shot_type",
    "negative_prompt",
    "cfg_scale",
)


@dataclass(frozen=True)
class RemoteBody:
    requested_url: str
    final_url: str
    http_status: int
    content_type: str
    body: bytes


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_remote(url: str, timeout: float) -> RemoteBody:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.1",
            "User-Agent": "persona-dream-phase11-evidence/1",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return RemoteBody(
                requested_url=url,
                final_url=response.geturl(),
                http_status=int(response.status),
                content_type=str(response.headers.get("Content-Type") or ""),
                body=response.read(),
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise Phase11Blocked(
            "BLOCKED_PROVIDER_SOURCE_HTTP_ERROR",
            details={"url": url, "http_status": exc.code, "detail": detail[-2000:]},
        ) from exc
    except OSError as exc:
        raise Phase11Blocked(
            "BLOCKED_PROVIDER_SOURCE_NETWORK_ERROR",
            details={"url": url, "error": str(exc)},
        ) from exc


def endpoint_from_payload(payload: Mapping[str, Any]) -> str:
    preview = payload.get("assembled_request_preview")
    if isinstance(preview, Mapping) and preview.get("model"):
        return str(preview["model"])
    return str(payload.get("endpoint") or payload.get("model") or "")


def normalized_input_schema(schema_text: str) -> dict[str, Any]:
    missing = [token for token in REQUIRED_SCHEMA_TOKENS if token not in schema_text]
    if missing:
        raise Phase11Blocked(
            "BLOCKED_PROVIDER_SOURCE_SCHEMA_TOKENS_MISSING",
            details={"missing": missing},
        )
    if STANDARD_ENDPOINT not in schema_text:
        raise Phase11Blocked("BLOCKED_PROVIDER_SOURCE_ENDPOINT_MISSING")
    if not re.search(r"start_image_url.{0,1000}required", schema_text, flags=re.IGNORECASE | re.DOTALL):
        raise Phase11Blocked("BLOCKED_PROVIDER_START_IMAGE_SCHEMA")
    missing_durations = [
        value
        for value in range(3, 16)
        if not re.search(rf"(?<![0-9])['\"]?{value}['\"]?(?![0-9])", schema_text)
    ]
    if missing_durations:
        raise Phase11Blocked("BLOCKED_PROVIDER_DURATION_NOT_SUPPORTED")
    return {
        "prompt": {"type": "string", "required": "one_of_prompt_or_multi_prompt"},
        "multi_prompt": {"type": "list<KlingV3MultiPromptElement>", "required": "one_of_prompt_or_multi_prompt"},
        "start_image_url": {"type": "string", "required": True},
        "duration": {"type": "DurationEnum", "required": False, "enum": list(range(3, 16))},
        "generate_audio": {"type": "boolean", "required": False, "default": True},
        "end_image_url": {"type": "string", "required": False},
        "elements": {"type": "list<KlingV3ComboElementInput>", "required": False},
        "shot_type": {"type": "ShotTypeEnum", "required": False, "enum": ["customize", "intelligent"]},
        "negative_prompt": {"type": "string", "required": False},
        "cfg_scale": {"type": "float", "required": False, "default": 0.5},
    }


def parse_pricing(pricing_text: str) -> dict[str, float]:
    required = {
        "usd_per_second_audio_off": 0.084,
        "usd_per_second_audio_on": 0.126,
        "usd_per_second_voice_control": 0.154,
    }
    for field, value in required.items():
        token = f"{value:.3f}"
        if not re.search(rf"(?<![0-9.]){re.escape(token)}(?![0-9])", pricing_text):
            raise Phase11Blocked(
                "BLOCKED_PROVIDER_PRICING_TOKEN_MISSING",
                details={"field": field, "expected": value},
            )
    return required


def official_url(url: str, expected_path: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.netloc == "fal.ai" and parsed.path.rstrip("/") == expected_path.rstrip("/")


def build_snapshot(
    *,
    context: Any,
    phase10_payload_path: Path,
    candidate_binding_path: Path,
    schema_remote: RemoteBody,
    pricing_remote: RemoteBody,
    retrieved_at: str,
    ttl_seconds: int,
    snapshot_path: Path,
    argv: list[str],
) -> dict[str, Any]:
    if not 200 <= schema_remote.http_status < 300 or not 200 <= pricing_remote.http_status < 300:
        raise Phase11Blocked("BLOCKED_PROVIDER_SOURCE_HTTP_STATUS")
    if not official_url(schema_remote.final_url, "/models/fal-ai/kling-video/v3/standard/image-to-video/api"):
        raise Phase11Blocked("BLOCKED_PROVIDER_SCHEMA_SOURCE_FINAL_URL", details={"final_url": schema_remote.final_url})
    if not official_url(pricing_remote.final_url, "/models/fal-ai/kling-video/v3/standard/image-to-video"):
        raise Phase11Blocked("BLOCKED_PROVIDER_PRICING_SOURCE_FINAL_URL", details={"final_url": pricing_remote.final_url})

    phase10 = read_object(phase10_payload_path)
    try:
        candidate = load_and_validate_payload_binding(
            candidate_binding_path,
            context=context,
            phase10_payload_path=phase10_payload_path,
            media_lock_path=context.revision_root / DEFAULT_MEDIA_LOCK_RELATIVE,
        )
    except PayloadBindingBlocked as exc:
        raise Phase11Blocked(exc.code, details=exc.details, exit_code=exc.exit_code) from exc
    phase10_endpoint = endpoint_from_payload(phase10)
    candidate_endpoint = str(candidate.get("model") or "")
    if candidate_endpoint != STANDARD_ENDPOINT:
        raise Phase11Blocked(
            "BLOCKED_PROVIDER_ENDPOINT_CANDIDATE_MISMATCH",
            details={"candidate_endpoint": candidate_endpoint, "expected": STANDARD_ENDPOINT},
        )

    schema_text = schema_remote.body.decode("utf-8", errors="replace")
    pricing_text = pricing_remote.body.decode("utf-8", errors="replace")
    input_schema = normalized_input_schema(schema_text)
    prices = parse_pricing(pricing_text)

    snapshot_parent = snapshot_path.parent
    schema_body_path = snapshot_parent / "provider_schema_response.body"
    pricing_body_path = snapshot_parent / "provider_pricing_response.body"
    schema_body_path.parent.mkdir(parents=True, exist_ok=True)
    schema_body_path.write_bytes(schema_remote.body)
    pricing_body_path.write_bytes(pricing_remote.body)

    migration = {
        "status": "NOT_REQUIRED" if phase10_endpoint == STANDARD_ENDPOINT else "APPLIED",
        "from_endpoint": phase10_endpoint,
        "to_endpoint": STANDARD_ENDPOINT,
        "phase10_payload_sha256": sha256_file(phase10_payload_path),
        "candidate_binding_sha256": sha256_file(candidate_binding_path),
        "reason": "Phase 11 canonical request is bound to the current official Kling v3 Standard endpoint; historical Phase 10 endpoint identity is retained as migration evidence.",
    }
    return {
        "schema": "persona_dream.phase11_provider_source_snapshot.v1",
        "status": "PASS_PROVIDER_SOURCE_SNAPSHOT",
        "provider_id": "kling",
        "endpoint": STANDARD_ENDPOINT,
        "mode": "standard",
        "run_id": context.run_id,
        "revision_id": context.revision_id,
        "activation_transaction_id": context.activation_transaction_id,
        "retrieved_at": retrieved_at,
        "ttl_seconds": ttl_seconds,
        "retrieval": {
            "command": argv,
            "provider_generation_call_attempted": False,
            "actual_provider_call_attempts": 0,
        },
        "phase10_endpoint_migration": migration,
        "schema_source": {
            "requested_url": schema_remote.requested_url,
            "final_url": schema_remote.final_url,
            "http_status": schema_remote.http_status,
            "content_type": schema_remote.content_type,
            "body_relative_path": schema_body_path.relative_to(snapshot_parent).as_posix(),
            "remote_content_sha256": sha256_file(schema_body_path),
            "normalized_schema_sha256": canonical_sha256(input_schema),
            "input_schema": input_schema,
        },
        "pricing_source": {
            "requested_url": pricing_remote.requested_url,
            "final_url": pricing_remote.final_url,
            "http_status": pricing_remote.http_status,
            "content_type": pricing_remote.content_type,
            "body_relative_path": pricing_body_path.relative_to(snapshot_parent).as_posix(),
            "remote_content_sha256": sha256_file(pricing_body_path),
            "currency": "USD",
            **prices,
            "duration_seconds": 10,
            "maximum_expected_cost_usd": round(prices["usd_per_second_audio_off"] * 10, 6),
        },
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "submitted": False,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id")
    value.add_argument("--schema-url", default=DEFAULT_SCHEMA_URL)
    value.add_argument("--pricing-url", default=DEFAULT_PRICING_URL)
    value.add_argument("--ttl-seconds", type=int, default=86400)
    value.add_argument("--timeout", type=float, default=30.0)
    value.add_argument("--now")
    value.add_argument("--output", type=Path)
    value.add_argument("--json", action="store_true")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        current = now_from_argument(args.now)
        context = resolve_active_context(args.run_root, args.revision_id)
        output = args.output.expanduser().resolve() if args.output else context.revision_root / DEFAULT_PROVIDER_SNAPSHOT_RELATIVE
        phase10_path = context.revision_root / DEFAULT_PHASE10_RELATIVE
        candidate_path = context.revision_root / DEFAULT_CANDIDATE_RELATIVE
        try:
            load_and_validate_payload_binding(
                candidate_path,
                context=context,
                phase10_payload_path=phase10_path,
                media_lock_path=context.revision_root / DEFAULT_MEDIA_LOCK_RELATIVE,
            )
        except PayloadBindingBlocked as exc:
            raise Phase11Blocked(exc.code, details=exc.details, exit_code=exc.exit_code) from exc
        schema_remote = fetch_remote(args.schema_url, args.timeout)
        pricing_remote = fetch_remote(args.pricing_url, args.timeout)
        snapshot = build_snapshot(
            context=context,
            phase10_payload_path=phase10_path,
            candidate_binding_path=candidate_path,
            schema_remote=schema_remote,
            pricing_remote=pricing_remote,
            retrieved_at=current.isoformat(),
            ttl_seconds=args.ttl_seconds,
            snapshot_path=output,
            argv=[
                "skills/persona-dream/run.sh",
                "capture-phase11-provider-source-snapshot",
                "--run-root",
                "<RUN_ROOT>",
                "--revision-id",
                context.revision_id,
                "--schema-url",
                args.schema_url,
                "--pricing-url",
                args.pricing_url,
                "--ttl-seconds",
                str(args.ttl_seconds),
                "--now",
                current.isoformat(),
            ],
        )
        from phase11_canonical_common import validate_schema
        errors = validate_schema(snapshot, "phase11_provider_source_snapshot.v1.schema.json")
        if errors:
            raise Phase11Blocked("BLOCKED_PROVIDER_SOURCE_SNAPSHOT_SCHEMA", details={"errors": errors})
        write_json(output, snapshot)
        result = {
            "schema": "persona_dream.phase11_provider_source_capture_receipt.v1",
            "status": "PASS_PROVIDER_SOURCE_SNAPSHOT",
            "snapshot": str(output),
            "snapshot_sha256": sha256_file(output),
            "retrieved_at": snapshot["retrieved_at"],
            "endpoint": STANDARD_ENDPOINT,
            "mode": "standard",
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "paid_call_authorized": False,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
        }
    except Phase11Blocked as exc:
        result = {
            "schema": "persona_dream.phase11_provider_source_capture_receipt.v1",
            "status": exc.code,
            "gate_status": "BLOCKED_PROVIDER_GATE",
            "details": exc.details,
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "paid_call_authorized": False,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return exc.exit_code
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "persona_dream.phase11_provider_source_capture_receipt.v1",
            "status": "BLOCKED_PROVIDER_SOURCE_INPUT_INVALID",
            "gate_status": "BLOCKED_PROVIDER_GATE",
            "details": {"error": str(exc)},
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "paid_call_authorized": False,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
