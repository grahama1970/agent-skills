#!/usr/bin/env python3
"""Check Persona Dream stale-write fencing fixtures.

This checker proves a narrow local invariant: staged creator/reviewer output
cannot be promoted into accepted evidence unless revision, lease, hash,
reviewer, scope, policy, and media-lock preconditions all match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_STALE_WRITE_FENCE"
BLOCKED_STATUS = "BLOCKED_STALE_WRITE_FENCE"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def resolve_sha(value: Any, fixture_dir: Path) -> Any:
    if isinstance(value, str) and value.startswith("sha256:file:"):
        return sha256_file(fixture_dir / value.removeprefix("sha256:file:"))
    if isinstance(value, dict):
        return {key: resolve_sha(item, fixture_dir) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_sha(item, fixture_dir) for item in value]
    return value


def relpath_in_scope(path_text: str, scope_text: str) -> bool:
    path = Path(path_text)
    scope = Path(scope_text)
    if path.is_absolute() or scope.is_absolute():
        return False
    try:
        path.relative_to(scope)
        return True
    except ValueError:
        return False


def add_blocker(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


def policy_checks(fixture: dict[str, Any], blockers: list[str]) -> None:
    policy = fixture.get("run_policy") or {}
    if policy.get("provider_live") is not False:
        add_blocker(blockers, "BLOCKED_PROVIDER_LIVE_IN_LOCAL_CHECK")
    if policy.get("paid_call_authorized") is not False:
        add_blocker(blockers, "BLOCKED_PAID_CALL_NOT_AUTHORIZED")
    if policy.get("provider_accessible_url_created") is not False:
        add_blocker(blockers, "BLOCKED_PROVIDER_URL_CREATION_NOT_ALLOWED")
    if policy.get("submitted") is not False:
        add_blocker(blockers, "BLOCKED_KLING_SUBMIT_NOT_ALLOWED")
    if policy.get("manual_acceptance_claimed") is not False:
        add_blocker(blockers, "BLOCKED_MANUAL_ACCEPTANCE_CLAIM")


def existing_accepted_checks(fixture: dict[str, Any], fixture_dir: Path, blockers: list[str]) -> None:
    locks = (fixture.get("artifact_lock_index_before") or {}).get("locks") or []
    for lock in locks:
        if lock.get("accepted") is True and not lock.get("reviewer_receipt_path"):
            add_blocker(blockers, "BLOCKED_REVIEWER_RECEIPT_MISSING_FOR_ACCEPTED_ARTIFACT")
        accepted_path = lock.get("accepted_path")
        locked_sha = lock.get("sha256")
        if accepted_path and locked_sha:
            path = fixture_dir / accepted_path
            if path.exists() and sha256_file(path) != locked_sha:
                add_blocker(blockers, "BLOCKED_ACCEPTED_HASH_MUTATED")
        current_refs = fixture.get("current_reference_hashes") or {}
        locked_refs = lock.get("reference_hashes") or {}
        for ref_id, locked_ref_sha in locked_refs.items():
            current_ref_sha = current_refs.get(ref_id)
            if current_ref_sha and current_ref_sha != locked_ref_sha:
                add_blocker(blockers, "BLOCKED_REFERENCE_HASH_CHANGED")


def media_lock_checks(fixture: dict[str, Any], blockers: list[str]) -> None:
    work_item = fixture.get("work_item") or {}
    lock_index = fixture.get("artifact_lock_index_before") or {}
    replacing = any(
        lock.get("artifact_id") == work_item.get("artifact_id") and lock.get("accepted") is True
        for lock in lock_index.get("locks") or []
    )
    if replacing:
        media_lock = fixture.get("media_lock_before") or {}
        if media_lock.get("status") != "STALE":
            add_blocker(blockers, "BLOCKED_MEDIA_LOCK_NOT_STALED_AFTER_ACCEPTED_FRAME_REPLACEMENT")


def promotion_checks(fixture: dict[str, Any], fixture_dir: Path, blockers: list[str]) -> None:
    revision = fixture.get("dream_revision_manifest") or {}
    active_revision_id = revision.get("active_revision_id") or revision.get("revision_id")
    work_item = fixture.get("work_item") or {}
    lease = fixture.get("work_lease") or {}
    creator = fixture.get("creator_receipt") or {}
    reviewer = fixture.get("reviewer_receipt") or {}

    if work_item.get("revision_id") != active_revision_id:
        add_blocker(blockers, "BLOCKED_ACTIVE_REVISION_MISMATCH")
    if creator.get("revision_id") != work_item.get("revision_id"):
        add_blocker(blockers, "BLOCKED_STALE_CREATOR_OUTPUT")
    if reviewer.get("revision_id") != work_item.get("revision_id"):
        add_blocker(blockers, "BLOCKED_STALE_REVIEWER_RECEIPT")
    if reviewer.get("accepted") is not True:
        add_blocker(blockers, "BLOCKED_STALE_REVIEWER_RECEIPT")

    candidate_path = str(creator.get("output_path") or "")
    reviewed_path = str(reviewer.get("reviewed_path") or "")
    write_scope = str(work_item.get("write_scope") or "")
    promotion_target = str(work_item.get("promotion_target") or "")
    if not candidate_path or not relpath_in_scope(candidate_path, write_scope):
        add_blocker(blockers, "BLOCKED_OUT_OF_SCOPE_WRITE")
    if reviewed_path and reviewed_path != candidate_path:
        add_blocker(blockers, "BLOCKED_STALE_REVIEWER_RECEIPT")
    if not promotion_target.startswith("accepted/"):
        add_blocker(blockers, "BLOCKED_OUT_OF_SCOPE_WRITE")

    candidate_file = fixture_dir / candidate_path
    if candidate_file.exists():
        candidate_sha = sha256_file(candidate_file)
        if creator.get("output_sha256") != candidate_sha:
            add_blocker(blockers, "BLOCKED_STALE_CREATOR_OUTPUT")
        if reviewer.get("reviewed_sha256") != candidate_sha:
            add_blocker(blockers, "BLOCKED_STALE_REVIEWER_RECEIPT")
    else:
        add_blocker(blockers, "BLOCKED_STALE_CREATOR_OUTPUT")

    if lease.get("state") != "ACTIVE":
        add_blocker(blockers, "BLOCKED_ACTIVE_LEASE_CONFLICT")
    if lease.get("artifact_id") != work_item.get("artifact_id"):
        add_blocker(blockers, "BLOCKED_ACTIVE_LEASE_CONFLICT")
    if lease.get("promotion_target") != promotion_target:
        add_blocker(blockers, "BLOCKED_ACTIVE_LEASE_CONFLICT")
    fencing_token = lease.get("fencing_token")
    if not fencing_token or creator.get("fencing_token") != fencing_token or reviewer.get("fencing_token") != fencing_token:
        add_blocker(blockers, "BLOCKED_ACTIVE_LEASE_CONFLICT")
    for conflict in fixture.get("active_lease_conflicts") or []:
        if conflict.get("artifact_id") == work_item.get("artifact_id") or conflict.get("promotion_target") == promotion_target:
            add_blocker(blockers, "BLOCKED_ACTIVE_LEASE_CONFLICT")

    for key, expected_sha in (work_item.get("input_hashes") or {}).items():
        current_sha = (fixture.get("current_input_hashes") or {}).get(key)
        if current_sha and current_sha != expected_sha:
            add_blocker(blockers, "BLOCKED_ACTIVE_REVISION_MISMATCH")


def evaluate_fixture(fixture_dir: Path) -> dict[str, Any]:
    fixture = resolve_sha(read_json(fixture_dir / "fixture.json"), fixture_dir)
    blockers: list[str] = []
    policy_checks(fixture, blockers)
    existing_accepted_checks(fixture, fixture_dir, blockers)
    media_lock_checks(fixture, blockers)
    promotion_checks(fixture, fixture_dir, blockers)

    result = "PROMOTION_ALLOWED"
    if any(blocker in blockers for blocker in ("BLOCKED_STALE_CREATOR_OUTPUT", "BLOCKED_STALE_REVIEWER_RECEIPT")):
        result = "OUTPUT_QUARANTINED"
    elif "BLOCKED_REFERENCE_HASH_CHANGED" in blockers:
        result = "REVALIDATE_REQUIRED"
    elif blockers:
        result = "PROMOTION_BLOCKED"

    expected = fixture.get("expected") or {}
    ok = result == expected.get("result") and sorted(blockers) == sorted(expected.get("blockers") or [])
    return {
        "fixture": fixture_dir.name,
        "ok": ok,
        "result": result,
        "expected_result": expected.get("result"),
        "blockers": blockers,
        "expected_blockers": expected.get("blockers") or [],
    }


def iter_fixture_dirs(root: Path) -> list[Path]:
    return sorted(path for path in root.iterdir() if path.is_dir() and (path / "fixture.json").exists())


def build_aggregate(fixtures_root: Path) -> dict[str, Any]:
    fixture_results = [evaluate_fixture(path) for path in iter_fixture_dirs(fixtures_root)]
    observed_results = sorted({item["result"] for item in fixture_results})
    observed_blockers = sorted({blocker for item in fixture_results for blocker in item["blockers"]})
    failures = [item for item in fixture_results if not item["ok"]]
    policy_false = {
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "manual_acceptance_claimed": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
    }
    receipt = {
        "schema": "persona_dream.stale_write_fence_checker_receipt.v1",
        "status": PASS_STATUS if not failures and len(fixture_results) == 9 else BLOCKED_STATUS,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "fixture_count": len(fixture_results),
        "observed_results": observed_results,
        "observed_blockers": observed_blockers,
        "promotion_allowed_count": sum(1 for item in fixture_results if item["result"] == "PROMOTION_ALLOWED"),
        "promotion_blocked_count": sum(1 for item in fixture_results if item["result"] == "PROMOTION_BLOCKED"),
        "quarantine_count": sum(1 for item in fixture_results if item["result"] == "OUTPUT_QUARANTINED"),
        "revalidate_required_count": sum(1 for item in fixture_results if item["result"] == "REVALIDATE_REQUIRED"),
        "promotion_not_allowed_count": sum(1 for item in fixture_results if item["result"] != "PROMOTION_ALLOWED"),
        **policy_false,
        "fixture_results": fixture_results,
        "failures": failures,
        "non_claims": {
            "kling_called": False,
            "paid_call_authorized": False,
            "provider_accessible_url_created": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "manual_acceptance_claimed": False,
            "fixture_is_production_proof": False,
            "ui_progress_bar_is_proof_authority": False,
        },
    }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-root", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_aggregate(args.fixtures_root)
    write_json(args.receipt_out, receipt)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
