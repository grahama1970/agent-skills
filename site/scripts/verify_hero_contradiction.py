#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


REQUIRED_FIELDS = {
    "schema",
    "source_receipt",
    "source_receipt_sha256",
    "source_url",
    "reported_claim",
    "observed_evidence",
    "artifact_path",
    "artifact_digest",
    "deterministic_rule",
    "bounded_judgment",
    "does_not_prove",
    "primary_action",
    "secondary_action",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def validate(fixture_path: Path) -> list[str]:
    errors: list[str] = []
    data = json.loads(fixture_path.read_text())
    missing = sorted(REQUIRED_FIELDS - set(data))
    if missing:
        errors.append(f"fixture missing required fields: {', '.join(missing)}")
    if data.get("schema") != "grahama.hero_contradiction.v1":
        errors.append("schema must be grahama.hero_contradiction.v1")

    receipt_path = repo_path(str(data.get("source_receipt", "")))
    if not receipt_path.is_file():
        errors.append(f"source receipt missing: {receipt_path}")
        receipt = {}
    else:
        receipt = json.loads(receipt_path.read_text())
        actual_digest = sha256(receipt_path)
        if data.get("source_receipt_sha256") != actual_digest:
            errors.append("source_receipt_sha256 does not match source receipt")
        if data.get("artifact_digest") != actual_digest:
            errors.append("artifact_digest does not match source receipt")

    if receipt:
        if receipt.get("status") != "PILOT_EVIDENCE_ONLY":
            errors.append("source receipt must remain PILOT_EVIDENCE_ONLY")
        overflow = (((receipt.get("geometry_results") or {}).get("mobile") or {}).get(
            "document_overflow_ignoring_fixed_layers"
        ))
        if overflow != 639:
            errors.append("source receipt must expose mobile document overflow of 639")

    for field in ("reported_claim", "observed_evidence", "deterministic_rule", "bounded_judgment", "does_not_prove"):
        if not str(data.get(field, "")).strip():
            errors.append(f"{field} is required")
    if "PILOT_EVIDENCE_ONLY" not in str(data.get("bounded_judgment", "")):
        errors.append("bounded_judgment must preserve PILOT_EVIDENCE_ONLY")
    if not str(data.get("source_url", "")).startswith("https://github.com/grahama1970/agent-skills/"):
        errors.append("source_url must resolve to the public agent-skills repository")
    for action in ("primary_action", "secondary_action"):
        value = data.get(action)
        if not isinstance(value, dict) or not value.get("label") or not value.get("href"):
            errors.append(f"{action} must contain label and href")

    page = (ROOT / "app" / "page.tsx").read_text()
    banned_imports = ["HeroLineage", "HeroProofBridge", "StripVideo", "@/generated/battle-lineage"]
    for token in banned_imports:
        if token in page:
            errors.append(f"homepage still imports or renders {token}")
    if "HeroContradictionPlate" not in page:
        errors.append("homepage must render HeroContradictionPlate")
    hero_actions = re.findall(r'data-qid="hero:action:[^"]+"', page)
    if len(hero_actions) != 2:
        errors.append(f"hero must expose exactly 2 hero actions, found {len(hero_actions)}")

    component = (ROOT / "components" / "hero-contradiction-plate.tsx").read_text()
    for label in ("Reported claim", "Observed evidence", "Immutable locator", "Deterministic rule", "Bounded judgment", "What this does not prove"):
        if label not in component:
            errors.append(f"component missing label: {label}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(ROOT / "hero-contradiction.json"))
    parser.add_argument("--expect-fail", action="store_true")
    args = parser.parse_args()
    errors = validate(Path(args.fixture))
    if args.expect_fail:
        if errors:
            print("OK: invalid hero contradiction fixture failed validation")
            return 0
        print("expected fixture to fail, but it passed", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("OK: hero contradiction plate is source-bound and replaces hero dashboard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
