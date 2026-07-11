#!/usr/bin/env python3
"""Stage a locked provider-media image into the repo without publishing it.

This is a pre-publication step. It copies the exact locked media bytes from a
provider-media publication work order into the proposed repository path and
writes a receipt proving local byte/hash parity. It does not push, upload, call
Kling, or upgrade provider readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _repo_relative_path(repo_root: Path, target_repo_path: str) -> Path:
    target = Path(target_repo_path)
    if target.is_absolute() or ".." in target.parts:
        raise ValueError(f"target_repo_path must be repo-relative: {target_repo_path}")
    resolved = (repo_root / target).resolve()
    if repo_root.resolve() not in (resolved, *resolved.parents):
        raise ValueError(f"target_repo_path escapes repo root: {target_repo_path}")
    return resolved


def stage_provider_media_local_asset(
    *,
    work_order_path: Path,
    repo_root: Path = DEFAULT_REPO_ROOT,
    created_at: str | None = None,
) -> dict[str, Any]:
    work_order_path = work_order_path.resolve()
    repo_root = repo_root.resolve()
    work_order = _read_json(work_order_path)
    if not isinstance(work_order, dict):
        raise ValueError("work order must be a JSON object")
    if work_order.get("schema") != "persona_dream.provider_media_publication_work_order.v1":
        raise ValueError(f"wrong work order schema: {work_order.get('schema')}")

    locked_media = work_order.get("locked_media")
    publication = work_order.get("proposed_publication")
    if not isinstance(locked_media, dict):
        raise ValueError("work order missing locked_media")
    if not isinstance(publication, dict):
        raise ValueError("work order missing proposed_publication")

    source_path_value = locked_media.get("local_path")
    expected_sha256 = locked_media.get("sha256")
    target_repo_path = publication.get("target_repo_path")
    proposed_url = publication.get("proposed_url")
    if not isinstance(source_path_value, str) or not source_path_value:
        raise ValueError("locked_media.local_path is required")
    if not isinstance(expected_sha256, str) or not expected_sha256.startswith("sha256:"):
        raise ValueError("locked_media.sha256 must start with sha256:")
    if not isinstance(target_repo_path, str) or not target_repo_path:
        raise ValueError("proposed_publication.target_repo_path is required")
    if not isinstance(proposed_url, str) or not proposed_url.startswith("https://"):
        raise ValueError("proposed_publication.proposed_url must be https")

    source_path = Path(source_path_value).resolve()
    if not source_path.exists():
        raise ValueError(f"locked media source is missing: {source_path}")
    source_sha256 = _sha256_file(source_path)
    if source_sha256 != expected_sha256:
        raise ValueError(f"locked source hash mismatch: expected {expected_sha256}, got {source_sha256}")

    staged_path = _repo_relative_path(repo_root, target_repo_path)
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, staged_path)
    staged_sha256 = _sha256_file(staged_path)
    if staged_sha256 != expected_sha256:
        raise ValueError(f"staged hash mismatch: expected {expected_sha256}, got {staged_sha256}")

    return {
        "schema": "persona_dream.provider_media_local_staging_receipt.v1",
        "created_at": created_at or _now_iso(),
        "created_by": "project_agent",
        "status": "PASS_PROVIDER_MEDIA_LOCAL_STAGING",
        "work_order": str(work_order_path),
        "run_id": work_order.get("run_id"),
        "panel_id": work_order.get("panel_id"),
        "source_path": str(source_path),
        "source_sha256": source_sha256,
        "staged_asset_path": str(staged_path),
        "target_repo_path": target_repo_path,
        "staged_sha256": staged_sha256,
        "bytes": staged_path.stat().st_size,
        "proposed_url": proposed_url,
        "next_required_probe_command": (
            "./run.sh validate-provider-media-url "
            f"--url {proposed_url} --expected-sha256 {expected_sha256} --json"
        ),
        "does_not_authorize": [
            "git_push",
            "public_upload",
            "provider_readiness",
            "direct_kling_submit",
            "paid_provider_call",
        ],
        "mocked": "no",
        "live": "no",
        "exercised": "local copy of locked provider-media bytes and sha256 comparison",
        "unverified": "public URL fetch, GitHub raw availability, Kling provider fetch behavior, paid-call authorization, Kling submission",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = stage_provider_media_local_asset(
            work_order_path=args.work_order,
            repo_root=args.repo_root,
            created_at=args.created_at,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = {"status": "WROTE", "output": str(args.output), "receipt": receipt}
    except Exception as exc:
        result = {
            "schema": "persona_dream.provider_media_local_staging_receipt.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "provider_media_local_staging", "reason": str(exc)},
            "mocked": "no",
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} {result.get('output', '')}".strip())
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
