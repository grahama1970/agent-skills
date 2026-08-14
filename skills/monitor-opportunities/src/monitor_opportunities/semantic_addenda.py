"""Install provider semantic addenda into a run-local projection."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .tau_semantic_provider import _safe_id, _validate_addendum
from .util import read_json, sha256_json, utc_now, write_json


def install_semantic_addendum(*, run_dir: Path, provider_receipt_path: Path) -> dict[str, Any]:
    receipt = read_json(provider_receipt_path)
    if receipt.get("status") != "PASS":
        raise ValueError("provider_receipt_not_pass")
    if receipt.get("provider_live") is not True or receipt.get("external_effects") is not False:
        raise ValueError("provider_receipt_policy_invalid")
    addendum_path = Path(str(receipt.get("semantic_addendum") or ""))
    if not addendum_path.is_file():
        raise ValueError("semantic_addendum_missing")
    addendum = read_json(addendum_path)
    opportunity_id = str(receipt.get("opportunity_id") or addendum.get("opportunity_id") or "")
    errors = _validate_addendum(addendum, opportunity_id)
    if errors:
        raise ValueError("semantic_addendum_invalid:" + ",".join(errors))

    semantic_dir = run_dir / "semantic-addenda"
    installed_path = semantic_dir / f"{_safe_id(opportunity_id)}.json"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(addendum_path, installed_path)
    if read_json(installed_path) != addendum:
        raise RuntimeError(f"semantic addendum readback failed: {installed_path}")

    index_path = semantic_dir / "index.json"
    existing = read_json(index_path) if index_path.exists() else {
        "schema": "monitor_opportunities.semantic_addendum_index.v1",
        "items": [],
        "external_effects": False,
    }
    retained = [
        row for row in existing.get("items", []) if row.get("opportunity_id") != opportunity_id
    ]
    row = {
        "opportunity_id": opportunity_id,
        "installed_at": utc_now(),
        "addendum": str(installed_path),
        "addendum_sha256": "sha256:" + sha256_json(addendum),
        "provider_receipt": str(provider_receipt_path),
        "provider_receipt_sha256": "sha256:" + sha256_json(receipt),
        "handler": receipt.get("handler"),
        "verdict": addendum.get("verdict"),
        "external_effects": False,
    }
    index = {
        "schema": "monitor_opportunities.semantic_addendum_index.v1",
        "items": [*retained, row],
        "external_effects": False,
        "updated_at": utc_now(),
    }
    write_json(index_path, index)
    return {
        "schema": "monitor_opportunities.semantic_addendum_install_receipt.v1",
        "status": "PASS",
        "run_dir": str(run_dir),
        "opportunity_id": opportunity_id,
        "index": str(index_path),
        "addendum": str(installed_path),
        "provider_receipt": str(provider_receipt_path),
        "external_effects": False,
        "mocked": False,
        "live": bool(receipt.get("live")),
        "provider_live": True,
    }
