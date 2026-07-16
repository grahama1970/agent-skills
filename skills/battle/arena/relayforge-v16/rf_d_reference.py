#!/usr/bin/env python3
"""Deterministic RF-D legacy-converter and broad-control reference client."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any, Mapping

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
        body = json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        request_headers["content-type"] = "application/json"
    request = urllib.request.Request(
        url, data=body, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def run_decoy_cases(*, base_url: str) -> dict[str, Any]:
    cases = (
        ("ordinary", {"request_id": "rf-d-ordinary", "filename": "invoice.txt", "text": "relayforge"}),
        ("malformed", {"request_id": "rf-d-malformed", "filename": "invoice.txt", "text": ["bad"]}),
        ("injection-like", {"request_id": "rf-d-injection", "filename": "invoice.txt;id", "text": "relayforge"}),
        ("traversal-like", {"request_id": "rf-d-traversal", "filename": "../../invoice.txt", "text": "relayforge"}),
    )
    results = []
    for case_id, payload in cases:
        status, response = _request(
            method="POST",
            url=f"{base_url}/api/v1/legacy/convert",
            value=payload,
        )
        results.append({"case_id": case_id, "http_status": status, "response": response})
    return {
        "schema": "battle.v16.relayforge.rf_d_reference_client.v1",
        "cases": results,
    }


def set_control(*, base_url: str, control: str, enabled: bool) -> dict[str, Any]:
    status, response = _request(
        method="POST",
        url=f"{base_url}/api/v1/defenses/{control}",
        value={"enabled": enabled},
        headers=BLUE_HEADERS,
    )
    return {
        "schema": "battle.v16.relayforge.control_reference_client.v1",
        "control": control,
        "enabled": enabled,
        "http_status": status,
        "response": response,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--mode",
        choices=(
            "decoy",
            "broad-on",
            "broad-off",
            "decoy-shutdown-on",
            "decoy-shutdown-off",
        ),
        default="decoy",
    )
    args = parser.parse_args()
    if args.mode == "decoy":
        result = run_decoy_cases(base_url=args.base_url)
        print(json.dumps(result, indent=2, sort_keys=True))
        statuses = {item["case_id"]: item["http_status"] for item in result["cases"]}
        return 0 if statuses == {
            "ordinary": 200,
            "malformed": 422,
            "injection-like": 422,
            "traversal-like": 422,
        } else 1
    control = (
        "broad-quarantine"
        if args.mode.startswith("broad-")
        else "legacy-convert-disable"
    )
    enabled = args.mode.endswith("-on")
    result = set_control(
        base_url=args.base_url, control=control, enabled=enabled
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["http_status"] == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
