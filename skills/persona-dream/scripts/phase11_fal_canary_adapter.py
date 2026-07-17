#!/usr/bin/env python3
"""Zero-call preflight and explicitly authorized exactly-once Fal/Kling canary.

``--preflight`` never performs a provider generation call.  ``--execute`` is
fail-closed behind the current adapter-preflight receipt and all five exact
human approval receipts.  The durable request-hash ledger is fenced before a
submit attempt; a crash or exception before a request ID becomes an ambiguous
submit that requires human reconciliation and can never be automatically
resubmitted.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

import phase11_canonical_common as canonical
from phase11_canonical_common import Phase11Blocked, load_inputs, now_from_argument, read_object, sha256_file, validate_schema, write_json
from phase11_execution_common import (
    ADAPTER_PREFLIGHT_NAME,
    DOWNLOAD_RECEIPT_NAME,
    RETURN_ENVELOPE_NAME,
    adapter_preflight_path,
    attempt_ledger_path,
    build_execution_state,
    canonical_sha256,
    discover_credential,
    download_provider_video,
    extract_video_url,
    ffprobe_video,
    inspect_fal_api,
    iso,
    provider_return_root,
    poll_policy,
    persist_provider_result_error,
    request_attempt_observation,
    run_adapter_preflight,
    submit_once,
    update_poll_state,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    mode = value.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id", help="Optional assertion; must equal active_revision.json")
    value.add_argument("--phase10-payload", type=Path)
    value.add_argument("--candidate-binding", type=Path)
    value.add_argument("--media-lock", type=Path)
    value.add_argument("--provider-snapshot", type=Path)
    value.add_argument("--media-transition-manifest", type=Path)
    value.add_argument("--approval-root", type=Path)
    value.add_argument("--now", help="ISO-8601 clock override")
    value.add_argument("--poll-interval-seconds", type=float, default=5.0)
    value.add_argument("--max-polls", type=int, default=180)
    value.add_argument("--json", action="store_true")
    return value


def load_inputs_from_args(args: argparse.Namespace, current: Any) -> Any:
    return load_inputs(
        args.run_root,
        revision_override=args.revision_id,
        phase10_payload=args.phase10_payload,
        candidate_binding=args.candidate_binding,
        media_lock=args.media_lock,
        provider_snapshot=args.provider_snapshot,
        transition_manifest=args.media_transition_manifest,
        approval_root=args.approval_root,
        current=current,
    )


class FalProvider:
    """Small synchronous wrapper whose submit retry count is forced to one."""

    def __init__(self, module: Any) -> None:
        self.module = module
        self.implementation = importlib.import_module("fal_client.client")
        self.client = module.SyncClient()

    def submit_once(self, endpoint: str, arguments: Mapping[str, Any]) -> str:
        if not hasattr(self.implementation, "MAX_ATTEMPTS"):
            raise Phase11Blocked("BLOCKED_FAL_CLIENT_SINGLE_ATTEMPT_CONTROL_UNAVAILABLE")
        previous = self.implementation.MAX_ATTEMPTS
        self.implementation.MAX_ATTEMPTS = 1
        try:
            handle = self.client.submit(
                endpoint,
                dict(arguments),
                headers={"X-Fal-No-Retry": "1"},
            )
        finally:
            self.implementation.MAX_ATTEMPTS = previous
        request_id = str(getattr(handle, "request_id", "") or "")
        if not request_id:
            raise RuntimeError("fal submit returned no request_id")
        return request_id

    def status(self, endpoint: str, request_id: str) -> Any:
        return self.client.status(endpoint, request_id, with_logs=False)

    def result(self, endpoint: str, request_id: str) -> Mapping[str, Any]:
        value = self.client.result(endpoint, request_id)
        if not isinstance(value, Mapping):
            raise Phase11Blocked("BLOCKED_PHASE11_PROVIDER_RESULT_INVALID")
        return value


def status_name(value: Any) -> str:
    if isinstance(value, Mapping):
        raw = value.get("status") or value.get("state")
        if raw:
            return str(raw).upper()
    return type(value).__name__.upper()


def execute_canary(inputs: Any, args: argparse.Namespace, current: Any) -> dict[str, Any]:
    state = build_execution_state(inputs)
    adapter_blockers = canonical.adapter_preflight_blockers(
        inputs,
        bindings=state.bindings,
        current=current,
    )
    if adapter_blockers:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_ADAPTER_PREFLIGHT_REQUIRED",
            details={"blockers": adapter_blockers},
        )
    approval_statuses, missing, approval_blockers = canonical.inspect_approvals(
        inputs, state.bindings, current
    )
    if approval_blockers:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_APPROVAL_RECEIPTS_INVALID",
            details={"blockers": approval_blockers},
        )
    if missing:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_HUMAN_APPROVALS_MISSING",
            details={"missing_approval_types": missing},
        )
    paid = approval_statuses.get("paid_call_authorization")
    if not isinstance(paid, Mapping) or paid.get("state") != "APPROVED":
        raise Phase11Blocked("BLOCKED_PHASE11_PAID_CALL_AUTHORIZATION_MISSING")

    policy, policy_blockers = poll_policy(
        args.poll_interval_seconds,
        args.max_polls,
    )
    if policy_blockers:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_POLL_POLICY",
            details={"blockers": policy_blockers},
        )
    preflight = read_object(adapter_preflight_path(inputs))
    if preflight.get("poll_policy") != policy:
        raise Phase11Blocked("BLOCKED_PHASE11_POLL_POLICY_CHANGED_AFTER_PREFLIGHT")

    credential, credential_blockers = discover_credential(os.environ)
    if credential_blockers:
        raise Phase11Blocked(credential_blockers[0])
    api = inspect_fal_api()
    if api.blockers or api.module is None:
        raise Phase11Blocked(
            "BLOCKED_FAL_CLIENT_API_SURFACE",
            details={"blockers": list(api.blockers)},
        )
    provider = FalProvider(api.module)
    endpoint = str(state.bindings["endpoint"])
    request_hash = str(state.bindings["request_body_sha256"])
    decision = submit_once(
        inputs,
        request_hash,
        current=current,
        submit=lambda: provider.submit_once(endpoint, state.request_body),
    )
    assert decision.request_id is not None
    request_id = decision.request_id

    terminal = False
    result: Mapping[str, Any] | None = None
    poll_count = 0
    for poll_count in range(1, args.max_polls + 1):
        observed = provider.status(endpoint, request_id)
        name = status_name(observed)
        if name in {"COMPLETED", "SUCCEEDED", "SUCCESS"}:
            try:
                result = provider.result(endpoint, request_id)
            except Exception as exc:
                error_receipt, failed_ledger = persist_provider_result_error(
                    inputs,
                    request_hash,
                    endpoint=endpoint,
                    request_id=request_id,
                    current=now_from_argument(None),
                    poll_count=poll_count,
                    error=exc,
                )
                raise Phase11Blocked(
                    str(error_receipt["status"]),
                    details={
                        "request_id": request_id,
                        "http_status": error_receipt.get("http_status"),
                        "error_count": error_receipt.get("error_count"),
                        "automatic_resubmit_allowed": False,
                        "attempt_ledger_state": failed_ledger.get("state"),
                    },
                ) from exc
            terminal = True
            break
        if name in {"FAILED", "CANCELLED", "CANCELED", "ERROR"}:
            update_poll_state(
                inputs,
                request_hash,
                state="FAILED",
                current=now_from_argument(None),
                poll_count=poll_count,
                fields={"provider_terminal_state": name},
            )
            raise Phase11Blocked(
                "BLOCKED_PHASE11_PROVIDER_TASK_FAILED",
                details={"request_id": request_id, "state": name},
            )
        update_poll_state(
            inputs,
            request_hash,
            state="POLLING",
            current=now_from_argument(None),
            poll_count=poll_count,
            fields={"provider_terminal_state": name},
        )
        time.sleep(args.poll_interval_seconds)
    if not terminal or result is None:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_PROVIDER_POLL_TIMEOUT",
            details={"request_id": request_id, "poll_count": poll_count},
        )

    video_url = extract_video_url(result)
    return_root = provider_return_root(inputs, request_hash)
    video_path = return_root / "provider_return.mp4"
    downloaded_sha, size_bytes, content_type = download_provider_video(video_url, video_path)
    ffprobe_path = str((preflight.get("ffprobe") or {}).get("path") or "")
    if not ffprobe_path:
        raise Phase11Blocked("BLOCKED_PHASE11_FFPROBE_MISSING")
    probe = ffprobe_video(video_path, ffprobe_path)

    download_receipt = {
        "schema": "persona_dream.phase11_download_ffprobe_receipt.v1",
        "status": "PASS_PHASE11_PROVIDER_RETURN_DOWNLOADED",
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "request_body_sha256": request_hash,
        "endpoint": endpoint,
        "request_id": request_id,
        "source_url": video_url,
        "download_relative_path": video_path.relative_to(inputs.context.run_root).as_posix(),
        "downloaded_sha256": downloaded_sha,
        "size_bytes": size_bytes,
        "content_type": content_type,
        "ffprobe": probe,
        "actual_provider_call_attempts": 1,
    }
    download_errors = validate_schema(
        download_receipt, "phase11_download_ffprobe_receipt.v1.schema.json"
    )
    if download_errors:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_DOWNLOAD_RECEIPT_SCHEMA",
            details={"errors": download_errors},
        )
    download_path = return_root / DOWNLOAD_RECEIPT_NAME
    write_json(download_path, download_receipt)

    result_sha = canonical_sha256(result)
    envelope = {
        "schema": "persona_dream.phase11_provider_return_envelope.v1",
        "status": "PASS_PHASE11_PROVIDER_RETURN_RECEIVED",
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "source_revision_id": inputs.context.source_revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "endpoint": endpoint,
        "request_id": request_id,
        "request_body_sha256": request_hash,
        "provider_result_sha256": result_sha,
        "video_url": video_url,
        "download_receipt_relative_path": download_path.relative_to(inputs.context.run_root).as_posix(),
        "download_receipt_sha256": sha256_file(download_path),
        "downloaded_mp4_sha256": downloaded_sha,
        "poll_count": poll_count,
        "actual_provider_call_attempts": 1,
        "provider_live": True,
        "submitted": True,
        "watch_started": False,
    }
    envelope_errors = validate_schema(
        envelope, "phase11_provider_return_envelope.v1.schema.json"
    )
    if envelope_errors:
        raise Phase11Blocked(
            "BLOCKED_PHASE11_PROVIDER_RETURN_ENVELOPE_SCHEMA",
            details={"errors": envelope_errors},
        )
    envelope_path = return_root / RETURN_ENVELOPE_NAME
    write_json(envelope_path, envelope)
    update_poll_state(
        inputs,
        request_hash,
        state="COMPLETED",
        current=now_from_argument(None),
        poll_count=poll_count,
        fields={
            "provider_terminal_state": "COMPLETED",
            "provider_return_envelope_sha256": sha256_file(envelope_path),
            "download_receipt_sha256": sha256_file(download_path),
            "downloaded_mp4_sha256": downloaded_sha,
        },
    )
    return {
        "schema": "persona_dream.phase11_fal_canary_execution_receipt.v1",
        "status": "PASS_PHASE11_PROVIDER_RETURN_RECEIVED",
        "request_id": request_id,
        "action": decision.action,
        "provider_return_envelope": str(envelope_path),
        "download_receipt": str(download_path),
        "actual_provider_call_attempts": 1,
        "provider_live": True,
        "submitted": True,
        "watch_started": False,
        "credential_source_variable": credential["source_variable"],
        "credential_value_persisted": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    inputs: Any | None = None
    request_hash: str | None = None
    try:
        current = now_from_argument(args.now)
        inputs = load_inputs_from_args(args, current)
        request_hash = str(build_execution_state(inputs).bindings["request_body_sha256"])
        if args.preflight:
            result = run_adapter_preflight(
                inputs,
                current=current,
                poll_interval_seconds=args.poll_interval_seconds,
                max_polls=args.max_polls,
                adapter_script_path=Path(__file__).resolve(),
            )
            exit_code = 0 if result["status"] == "PASS_PHASE11_ADAPTER_PREFLIGHT" else 2
        else:
            result = execute_canary(inputs, args, current)
            exit_code = 0
    except Phase11Blocked as exc:
        attempts = 0
        ledger_state = None
        if inputs is not None and request_hash:
            observation, _blockers = request_attempt_observation(inputs, request_hash)
            attempts = int(observation.get("actual_provider_call_attempts") or 0)
            ledger_state = observation.get("state")
        result = {
            "schema": "persona_dream.phase11_fal_canary_error.v1",
            "status": exc.code,
            "details": exc.details,
            "attempt_ledger_state": ledger_state,
            "provider_live": attempts > 0,
            "paid_call_authorized": False,
            "submitted": attempts > 0,
            "provider_ready": False,
            "live_submit_ready": False,
            "actual_provider_call_attempts": attempts,
        }
        exit_code = exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["status"])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
