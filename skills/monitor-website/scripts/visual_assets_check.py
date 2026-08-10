#!/usr/bin/env python3
"""Validate site/visual-assets.yml paths, hashes, and rights metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"
REQUIRED_FIELDS = {
    "id",
    "path",
    "kind",
    "source",
    "creation_method",
    "sha256",
    "project_ids",
    "public_approval",
    "role",
    "caption",
    "alt_text",
    "crop",
    "does_not_establish",
    "rights",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=str(SITE / "visual-assets.yml"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = REPO / registry_path

    data = yaml.safe_load(registry_path.read_text()) or {}
    findings = []
    assets = data.get("assets") or []
    if data.get("schema") != "grahama.visual_assets.v1":
        findings.append({"type": "bad_schema", "expected": "grahama.visual_assets.v1"})
    seen: set[str] = set()
    evidence_assets = 0
    for asset in assets:
        aid = str(asset.get("id") or "")
        if aid in seen:
            findings.append({"type": "duplicate_asset_id", "id": aid})
        seen.add(aid)
        missing = sorted(field for field in REQUIRED_FIELDS if field not in asset or asset.get(field) in (None, ""))
        if missing:
            findings.append({"type": "missing_fields", "id": aid, "fields": missing})
        rights = asset.get("rights") or {}
        for field in ("owner", "license", "third_party_basis"):
            if field not in rights:
                findings.append({"type": "missing_rights_field", "id": aid, "field": field})
        path_value = asset.get("path")
        path = REPO / str(path_value) if path_value else None
        if not path or not path.is_file():
            findings.append({"type": "missing_asset_file", "id": aid, "path": path_value})
            continue
        actual = sha256(path)
        if actual != asset.get("sha256"):
            findings.append({"type": "sha256_mismatch", "id": aid, "path": path_value, "expected": asset.get("sha256"), "actual": actual})
        if asset.get("role") == "evidence":
            evidence_assets += 1

    result = {
        "schema": "monitor_website.visual_assets_check.v1",
        "status": "PASS" if not findings else "FAIL",
        "registry": str(registry_path.relative_to(REPO)),
        "counts": {
            "registered_assets": len(assets),
            "public_visuals": len(assets),
            "evidence_assets": evidence_assets,
            "findings": len(findings),
        },
        "findings": findings,
    }
    print(json.dumps(result, indent=2) if args.json else result["status"])
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
