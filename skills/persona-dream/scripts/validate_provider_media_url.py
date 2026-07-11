#!/usr/bin/env python3
"""Probe a provider media URL and verify fetched bytes against a sha256 hash.

This command performs an ordinary public HTTP(S) fetch only. It does not call
Kling, upload media, authorize paid work, or mutate provider state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _looks_public_http_url(url: str) -> tuple[bool, str | None]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "url_scheme_must_be_http_or_https"
    if parsed.hostname in {None, "", "localhost", "127.0.0.1", "example.invalid"}:
        return False, "url_host_is_not_public_provider_accessible"
    if parsed.hostname and parsed.hostname.endswith(".invalid"):
        return False, "url_host_is_invalid_tld"
    return True, None


def validate_provider_media_url(
    url: str,
    expected_sha256: str,
    *,
    expected_content_type: str | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "persona_dream.provider_media_url_probe_receipt.v1",
        "created_at": _now_iso(),
        "url": url,
        "expected_sha256": expected_sha256,
        "status": "BLOCKED",
        "blockers": [],
        "http_status": None,
        "final_url": None,
        "content_type": None,
        "expected_content_type": expected_content_type,
        "content_length": None,
        "observed_sha256": None,
        "mocked": "no",
        "live": "yes",
        "exercised": "public HTTP(S) GET and sha256 comparison",
        "unverified": "Kling provider fetch behavior, provider task submission, paid-call authorization",
    }

    public_ok, public_reason = _looks_public_http_url(url)
    if not public_ok:
        result["blockers"].append(public_reason)
        result["live"] = "no"
        result["exercised"] = "URL policy check only"
        return result
    if not expected_sha256.startswith("sha256:"):
        result["blockers"].append("expected_sha256_must_start_with_sha256")
        return result

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "persona-dream-provider-media-probe/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            result["http_status"] = response.status
            result["final_url"] = response.geturl()
            result["content_type"] = response.headers.get_content_type()
            result["content_length"] = len(body)
            result["observed_sha256"] = _sha256_bytes(body)
    except Exception as exc:  # noqa: BLE001 - receipt must capture network failure.
        result["blockers"].append(f"fetch_failed:{exc}")
        return result

    if result["http_status"] != 200:
        result["blockers"].append(f"http_status_not_200:{result['http_status']}")
    if result["observed_sha256"] != expected_sha256:
        result["blockers"].append("sha256_mismatch")
    if expected_content_type and result["content_type"] != expected_content_type:
        result["blockers"].append(
            f"content_type_mismatch:expected={expected_content_type}:observed={result['content_type']}"
        )

    if not result["blockers"]:
        result["status"] = "PASS_PROVIDER_MEDIA_URL_PROBE"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-content-type")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = validate_provider_media_url(
        args.url,
        args.expected_sha256,
        expected_content_type=args.expected_content_type,
        timeout=args.timeout,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["status"])
    return 0 if result["status"] == "PASS_PROVIDER_MEDIA_URL_PROBE" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
