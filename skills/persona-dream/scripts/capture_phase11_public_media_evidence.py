#!/usr/bin/env python3
"""Capture exact public-byte evidence for Phase 11 request media without publishing."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from phase11_canonical_common import (
    DEFAULT_CANDIDATE_RELATIVE,
    DEFAULT_TRANSITION_RELATIVE,
    Phase11Blocked,
    artifact_for_url,
    compile_request_body,
    load_inputs,
    now_from_argument,
    portable_run_path,
    sha256_file,
    validate_schema,
    write_json,
)

COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")


def fetch_bytes(url: str, timeout: float) -> tuple[int, str, Mapping[str, str], bytes]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "image/*,*/*;q=0.1", "User-Agent": "persona-dream-phase11-media-probe/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.geturl(), dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        raise Phase11Blocked(
            "BLOCKED_PUBLIC_MEDIA_HTTP_STATUS",
            details={"url": url, "http_status": exc.code},
        ) from exc
    except OSError as exc:
        raise Phase11Blocked(
            "BLOCKED_PUBLIC_MEDIA_NETWORK_ERROR",
            details={"url": url, "error": str(exc)},
        ) from exc


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def commit_from_raw_url(url: str, *, allow_test_host: bool = False) -> str:
    parsed = urlparse(url)
    if allow_test_host:
        return "0" * 40
    if parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com":
        raise Phase11Blocked("BLOCKED_PUBLIC_MEDIA_NOT_COMMIT_PINNED_GITHUB", details={"url": url})
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4 or not COMMIT_RE.fullmatch(parts[2]):
        raise Phase11Blocked("BLOCKED_PUBLIC_MEDIA_NOT_COMMIT_PINNED_GITHUB", details={"url": url})
    return parts[2]


def request_bindings(body: Mapping[str, Any]) -> list[tuple[str, str]]:
    bindings: list[tuple[str, str]] = []
    for pointer, field in (("/input/start_image_url", "start_image_url"), ("/input/end_image_url", "end_image_url")):
        value = body.get(field)
        if isinstance(value, str) and value:
            bindings.append((pointer, value))
    elements = body.get("elements")
    if isinstance(elements, list):
        for element_index, element in enumerate(elements):
            if not isinstance(element, Mapping):
                continue
            frontal = element.get("frontal_image_url")
            if isinstance(frontal, str) and frontal:
                bindings.append((f"/input/elements/{element_index}/frontal_image_url", frontal))
            references = element.get("reference_image_urls")
            if isinstance(references, list):
                for reference_index, value in enumerate(references):
                    if isinstance(value, str) and value:
                        bindings.append((f"/input/elements/{element_index}/reference_image_urls/{reference_index}", value))
    return bindings


def local_ref(run_root: Path, path: Path) -> dict[str, str]:
    return {
        "relative_path": path.resolve(strict=True).relative_to(run_root.resolve(strict=True)).as_posix(),
        "sha256": sha256_file(path),
    }


def evidence_documents(
    *,
    artifact_id: str,
    url: str,
    expected_sha256: str,
    commit: str,
    checked_at: str,
    status_code: int,
    final_url: str,
    headers: Mapping[str, str],
    byte_count: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    publication = {
        "schema": "persona_dream.phase11_existing_publication_receipt.v1",
        "status": "OBSERVED_EXISTING_PUBLIC_COMMIT_PINNED",
        "artifact_id": artifact_id,
        "url": url,
        "sha256": expected_sha256,
        "source_commit": commit,
        "publication_performed_by_this_command": False,
        "publication_authorization_present": False,
        "observed_at": checked_at,
        "actual_provider_call_attempts": 0,
    }
    probe = {
        "schema": "persona_dream.phase11_public_media_probe_receipt.v1",
        "status": "PASS_PROVIDER_MEDIA_PUBLIC_FETCH",
        "artifact_id": artifact_id,
        "url": url,
        "final_url": final_url,
        "http_status": status_code,
        "content_type": str(headers.get("Content-Type") or headers.get("content-type") or ""),
        "content_length": byte_count,
        "downloaded_sha256": expected_sha256,
        "checked_at": checked_at,
        "actual_provider_call_attempts": 0,
    }
    teardown = {
        "schema": "persona_dream.phase11_teardown_policy_receipt.v1",
        "status": "NOT_REQUIRED_PERSISTENT_COMMIT_PINNED",
        "artifact_id": artifact_id,
        "url": url,
        "source_commit": commit,
        "reason": "The URL names immutable Git commit content and this command did not create an ephemeral publication.",
        "actual_provider_call_attempts": 0,
    }
    return publication, probe, teardown


def capture(
    *,
    inputs: Any,
    timeout: float,
    checked_at: str,
    allow_test_host: bool = False,
) -> dict[str, Any]:
    request_body, request_blockers, _ = compile_request_body(inputs)
    if request_blockers:
        raise Phase11Blocked("BLOCKED_PHASE11_REQUEST_NOT_READY_FOR_MEDIA_PROBE", details={"blockers": request_blockers})

    grouped: dict[str, dict[str, Any]] = {}
    for pointer, url in request_bindings(request_body):
        artifact_id, entry = artifact_for_url(inputs.context, url)
        expected_sha256 = str(entry.get("sha256") or "")
        current = grouped.setdefault(
            artifact_id,
            {"artifact_id": artifact_id, "url": url, "sha256": expected_sha256, "json_pointers": []},
        )
        if current["url"] != url or current["sha256"] != expected_sha256:
            raise Phase11Blocked("BLOCKED_PUBLIC_MEDIA_ARTIFACT_MULTI_BINDING_CONFLICT", details={"artifact_id": artifact_id})
        current["json_pointers"].append(pointer)

    if len(grouped) != 6:
        raise Phase11Blocked(
            "BLOCKED_PUBLIC_MEDIA_REQUEST_ASSET_CARDINALITY",
            details={"observed": len(grouped), "expected": 6, "artifact_ids": sorted(grouped)},
        )

    evidence_root = inputs.context.revision_root / "phase_11_submit_return" / "preflight" / "provider_media_evidence"
    entries: list[dict[str, Any]] = []
    for artifact_id in sorted(grouped):
        binding = grouped[artifact_id]
        url = str(binding["url"])
        expected_sha256 = str(binding["sha256"])
        commit = commit_from_raw_url(url, allow_test_host=allow_test_host)
        status_code, final_url, headers, body = fetch_bytes(url, timeout)
        observed_sha256 = sha256_bytes(body)
        if status_code != 200 or final_url != url or observed_sha256 != expected_sha256:
            raise Phase11Blocked(
                "BLOCKED_PUBLIC_MEDIA_PROBE",
                details={
                    "artifact_id": artifact_id,
                    "http_status": status_code,
                    "url": url,
                    "final_url": final_url,
                    "expected_sha256": expected_sha256,
                    "observed_sha256": observed_sha256,
                },
            )
        directory = evidence_root / re.sub(r"[^A-Za-z0-9._-]", "_", artifact_id)
        publication, probe, teardown = evidence_documents(
            artifact_id=artifact_id,
            url=url,
            expected_sha256=expected_sha256,
            commit=commit,
            checked_at=checked_at,
            status_code=status_code,
            final_url=final_url,
            headers=headers,
            byte_count=len(body),
        )
        publication_path = directory / "existing_publication_receipt.json"
        probe_path = directory / "public_probe_receipt.json"
        teardown_path = directory / "teardown_policy_receipt.json"
        for path, value, schema in (
            (publication_path, publication, "phase11_existing_publication_receipt.v1.schema.json"),
            (probe_path, probe, "phase11_public_media_probe_receipt.v1.schema.json"),
            (teardown_path, teardown, "phase11_teardown_policy_receipt.v1.schema.json"),
        ):
            errors = validate_schema(value, schema)
            if errors:
                raise Phase11Blocked("BLOCKED_PUBLIC_MEDIA_RECEIPT_SCHEMA", details={"artifact_id": artifact_id, "errors": errors})
            write_json(path, value)
        entries.append(
            {
                "artifact_id": artifact_id,
                "json_pointers": sorted(binding["json_pointers"]),
                "url": url,
                "sha256": expected_sha256,
                "publication_authorization": {
                    "approval_type": "publication_authorization",
                    "state": "MISSING_HUMAN_APPROVAL",
                },
                "publication_receipt": local_ref(inputs.context.run_root, publication_path),
                "public_probe": local_ref(inputs.context.run_root, probe_path),
                "teardown_policy": local_ref(inputs.context.run_root, teardown_path),
            }
        )

    manifest = {
        "schema": "persona_dream.provider_media_transition_manifest.v1",
        "status": "PASS_PROVIDER_MEDIA_TRANSITIONS_TECHNICAL",
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "checked_at": checked_at,
        "request_asset_count": len(entries),
        "entries": entries,
        "publication_authorization_required": True,
        "publication_authorization_present": False,
        "publication_performed_by_this_command": False,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "submitted": False,
    }
    errors = validate_schema(manifest, "provider_media_transition_manifest.v1.schema.json")
    if errors:
        raise Phase11Blocked("BLOCKED_PUBLIC_MEDIA_TRANSITION_MANIFEST_SCHEMA", details={"errors": errors})
    write_json(inputs.transition_manifest_path, manifest)
    return manifest


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id")
    value.add_argument("--provider-snapshot", type=Path)
    value.add_argument("--timeout", type=float, default=30.0)
    value.add_argument("--now")
    value.add_argument("--test-fixture", action="store_true", help=argparse.SUPPRESS)
    value.add_argument("--json", action="store_true")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        current = now_from_argument(args.now)
        inputs = load_inputs(
            args.run_root,
            revision_override=args.revision_id,
            phase10_payload=None,
            candidate_binding=None,
            media_lock=None,
            provider_snapshot=args.provider_snapshot,
            transition_manifest=None,
            approval_root=None,
            current=current,
        )
        manifest = capture(
            inputs=inputs,
            timeout=args.timeout,
            checked_at=current.isoformat(),
            allow_test_host=args.test_fixture,
        )
        result = {
            "status": manifest["status"],
            "manifest": str(inputs.transition_manifest_path),
            "manifest_sha256": sha256_file(inputs.transition_manifest_path),
            "request_asset_count": manifest["request_asset_count"],
            "publication_authorization_present": False,
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "submitted": False,
        }
    except Phase11Blocked as exc:
        result = {
            "status": exc.code,
            "details": exc.details,
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "submitted": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
