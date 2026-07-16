#!/usr/bin/env python3
"""Deterministic RF-C preview/capability/renderer reference client."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

DEFAULT_TENANT = "tenant-red"
BLUE_HEADERS = {"x-relayforge-team": "blue"}
ROOT = Path(__file__).resolve().parent


def _load_rf_a_reference():
    path = ROOT / "rf_a_reference.py"
    spec = importlib.util.spec_from_file_location("relayforge_rf_a_for_rf_c", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rf_a_reference = _load_rf_a_reference()


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
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def _set_defenses(base_url: str, enabled: Mapping[str, bool]) -> dict[str, Any]:
    receipts: dict[str, Any] = {}
    for name in (
        "redirect-destination-policy",
        "capability-audience-policy",
        "renderer-resource-policy",
    ):
        status, payload = _request(
            method="POST",
            url=f"{base_url}/api/v1/defenses/{name}",
            value={"enabled": bool(enabled.get(name, False))},
            headers=BLUE_HEADERS,
        )
        receipts[name] = {"http_status": status, "receipt": payload}
    return receipts


def run_sequence(
    *,
    base_url: str,
    tenant_id: str = DEFAULT_TENANT,
    defense_mode: str = "vulnerable",
) -> dict[str, Any]:
    """Run import -> OBS-30 -> capability -> renderer through public routes."""

    modes = {
        "vulnerable": {},
        "defended": {
            "redirect-destination-policy": True,
            "capability-audience-policy": True,
            "renderer-resource-policy": True,
        },
        "preview-defense": {"redirect-destination-policy": True},
        "capability-defense": {"capability-audience-policy": True},
        "renderer-defense": {"renderer-resource-policy": True},
    }
    if defense_mode not in modes:
        raise ValueError(f"unsupported defense mode: {defense_mode}")
    defenses = _set_defenses(base_url, modes[defense_mode])
    tenant_headers = {"x-relayforge-tenant": tenant_id}
    package = rf_a_reference.regular_package(
        request_id="rf-c-reference", tenant_id=tenant_id
    )
    import_status, imported = _request(
        method="POST",
        url=f"{base_url}/api/v1/jobs/import",
        value=package,
        headers=tenant_headers,
    )
    material = imported.get("capability_material") if isinstance(imported, dict) else None
    preview_status = 0
    preview: dict[str, Any] = {}
    render_status = 0
    rendered: dict[str, Any] = {}
    if isinstance(material, dict):
        preview_status, preview = _request(
            method="POST",
            url=f"{base_url}{material['preview_path']}",
            value={"url": material["preview_locator"]},
            headers=tenant_headers,
        )
        capability = preview.get("capability") if isinstance(preview, dict) else None
        if isinstance(capability, dict):
            render_status, rendered = _request(
                method="POST",
                url=f"{base_url}{material['report_profile_path']}",
                value={
                    "profile_alias": material["report_profile_alias"],
                    "capability_token": capability["token"],
                    "audience": capability["audience"],
                    "scope": capability["scope"],
                    "operation": capability["operation"],
                },
                headers=tenant_headers,
            )
    return {
        "schema": "battle.v16.relayforge.rf_c_reference_client.v1",
        "mode": defense_mode.upper().replace("-", "_"),
        "defenses": defenses,
        "import_status": import_status,
        "imported": imported,
        "preview_status": preview_status,
        "preview": preview,
        "render_status": render_status,
        "rendered": rendered,
    }


def run_safe_regressions(
    *, base_url: str, tenant_id: str = DEFAULT_TENANT
) -> dict[str, Any]:
    tenant_headers = {"x-relayforge-tenant": tenant_id}
    package = rf_a_reference.regular_package(
        request_id="rf-c-safe-regression", tenant_id=tenant_id
    )
    import_status, imported = _request(
        method="POST",
        url=f"{base_url}/api/v1/jobs/import",
        value=package,
        headers=tenant_headers,
    )
    material = imported.get("capability_material", {})
    preview_status, preview = _request(
        method="POST",
        url=f"{base_url}{material.get('preview_path', '')}",
        value={"url": "https://public.example/preview/safe"},
        headers=tenant_headers,
    )
    render_status, rendered = _request(
        method="POST",
        url=f"{base_url}{material.get('report_profile_path', '')}",
        value={"profile": "summary-safe"},
        headers=tenant_headers,
    )
    return {
        "schema": "battle.v16.relayforge.rf_c_safe_regressions.v1",
        "import_status": import_status,
        "preview_status": preview_status,
        "render_status": render_status,
        "preview": preview,
        "rendered": rendered,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT)
    parser.add_argument(
        "--mode",
        choices=(
            "vulnerable",
            "defended",
            "preview-defense",
            "capability-defense",
            "renderer-defense",
            "safe-regressions",
        ),
        default="vulnerable",
    )
    args = parser.parse_args()
    if args.mode == "safe-regressions":
        result = run_safe_regressions(
            base_url=args.base_url, tenant_id=args.tenant_id
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["preview_status"] == 200 and result["render_status"] == 200 else 1
    result = run_sequence(
        base_url=args.base_url,
        tenant_id=args.tenant_id,
        defense_mode=args.mode,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    expected = 200 if args.mode == "vulnerable" else 0
    if args.mode == "vulnerable":
        return 0 if result["render_status"] == expected else 1
    return 0 if result["render_status"] != 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
