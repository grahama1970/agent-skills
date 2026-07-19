#!/usr/bin/env python3
"""Rebind and validate a deferred voice handoff plan against the compiled canonical.

Breaks the voiced-run phase-11 ordering cycle safely: the voice handoff plan is
first written with request_binding.status=PENDING_COMPILE (no canonical yet), the
canonical live request is compiled, then this step binds the plan to the compiled
canonical request_body_sha256 and re-validates the audio-strategy gate. It FAILS
CLOSED: if the canonical hash is missing, if the rebound plan hash does not equal
the canonical hash, or if the audio-strategy assessment is not valid, it writes a
BLOCKED receipt and exits non-zero. The only sanctioned terminal state is a receipt
whose plan_request_body_sha256 == canonical_request_body_sha256 with a valid gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from audio_strategy_gate import (
    VOICE_HANDOFF_RELATIVE,
    assess_revision_audio_strategy,
)

CANONICAL_RELATIVE = Path("phase_11_submit_return/canonical/phase11_live_request.v1.json")
RECEIPT_RELATIVE = Path(
    "phase_11_submit_return/preflight/voice_handoff_binding_validation_receipt.v1.json"
)
RECEIPT_SCHEMA = "persona_dream.voice_handoff_binding_validation_receipt.v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _canonical_request_sha(canonical: Any) -> str | None:
    if not isinstance(canonical, Mapping):
        return None
    bindings = canonical.get("approval_bindings")
    if not isinstance(bindings, Mapping):
        return None
    value = bindings.get("request_body_sha256")
    return value if isinstance(value, str) and value else None


def rebind(revision_root: Path) -> dict[str, Any]:
    plan_path = revision_root / VOICE_HANDOFF_RELATIVE
    canonical_path = revision_root / CANONICAL_RELATIVE
    if not plan_path.is_file():
        return _fail(revision_root, "BLOCKED_VOICE_HANDOFF_PLAN_MISSING", {"plan_path": str(plan_path)})
    if not canonical_path.is_file():
        return _fail(
            revision_root,
            "BLOCKED_CANONICAL_REQUEST_MISSING",
            {"canonical_path": str(canonical_path)},
        )

    plan = read_json(plan_path)
    canonical = read_json(canonical_path)
    canonical_sha = _canonical_request_sha(canonical)
    if not canonical_sha or not canonical_sha.startswith("sha256:") or len(canonical_sha) != 71:
        return _fail(
            revision_root,
            "BLOCKED_CANONICAL_REQUEST_HASH_INVALID",
            {"canonical_request_body_sha256": canonical_sha},
        )

    request_binding = plan.get("request_binding") if isinstance(plan.get("request_binding"), Mapping) else {}
    prior_status = str(request_binding.get("status") or "BOUND")
    provider_request = plan.get("provider_request") if isinstance(plan.get("provider_request"), Mapping) else {}
    prior_plan_sha = provider_request.get("request_body_sha256")

    # Rebind pending -> bound to the compiled canonical hash. For an already-BOUND
    # plan this is an idempotent verification; a BOUND plan that disagrees with the
    # canonical is a genuine mismatch and must fail closed (not be silently rewritten).
    if prior_status == "BOUND" and prior_plan_sha and prior_plan_sha != canonical_sha:
        return _fail(
            revision_root,
            "BLOCKED_BOUND_PLAN_HASH_DISAGREES_WITH_CANONICAL",
            {"plan_request_body_sha256": prior_plan_sha, "canonical_request_body_sha256": canonical_sha},
        )

    plan.setdefault("provider_request", {})["request_body_sha256"] = canonical_sha
    plan["request_binding"] = {
        **request_binding,
        "status": "BOUND",
        "request_body_sha256": canonical_sha,
        "canonical_relative_path": str(CANONICAL_RELATIVE),
        "rebound_from_status": prior_status,
        "note": "Rebound post-compile to the compiled canonical request_body_sha256.",
    }
    atomic_write_json(plan_path, plan)

    # Fail-closed final validation: re-run the audio-strategy gate against the
    # now-present canonical. This re-derives the plan hash from disk and compares it
    # to the canonical; any mismatch surfaces as VOICE_HANDOFF_PROVIDER_REQUEST_HASH_MISMATCH.
    assessment = assess_revision_audio_strategy(revision_root)
    reread_plan = read_json(plan_path)
    plan_sha = ((reread_plan.get("provider_request") or {}).get("request_body_sha256"))
    hashes_equal = plan_sha == canonical_sha
    passed = hashes_equal and assessment.voice_handoff_valid and not assessment.validation_errors

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "PASS_VOICE_HANDOFF_BINDING" if passed else "BLOCKED_VOICE_HANDOFF_BINDING_MISMATCH",
        "revision_id": revision_root.name,
        "rebound_from_status": prior_status,
        "canonical_request_body_sha256": canonical_sha,
        "plan_request_body_sha256": plan_sha,
        "hashes_equal": hashes_equal,
        "voice_handoff_plan_relative_path": str(VOICE_HANDOFF_RELATIVE),
        "voice_handoff_plan_sha256": sha256_file(plan_path),
        "canonical_relative_path": str(CANONICAL_RELATIVE),
        "audio_strategy_assessment": assessment.to_dict(),
        "fail_closed": True,
        "mocked": False,
        "live": True,
    }
    _write_receipt(revision_root, receipt)
    receipt["_exit_code"] = 0 if passed else 2
    return receipt


def _fail(revision_root: Path, code: str, details: Mapping[str, Any]) -> dict[str, Any]:
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": code,
        "revision_id": revision_root.name,
        "details": dict(details),
        "hashes_equal": False,
        "fail_closed": True,
        "mocked": False,
        "live": True,
    }
    _write_receipt(revision_root, receipt)
    receipt["_exit_code"] = 2
    return receipt


def _write_receipt(revision_root: Path, receipt: Mapping[str, Any]) -> None:
    atomic_write_json(revision_root / RECEIPT_RELATIVE, {k: v for k, v in receipt.items() if k != "_exit_code"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision_root", type=Path)
    args = parser.parse_args(argv)
    revision_root = args.revision_root.expanduser().resolve()
    receipt = rebind(revision_root)
    exit_code = receipt.pop("_exit_code", 2)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
