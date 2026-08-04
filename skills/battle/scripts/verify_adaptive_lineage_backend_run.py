#!/usr/bin/env python3
"""Verify a Battle adaptive Red/Blue lineage backend run from local receipts.

This verifier deliberately reopens files and recomputes hashes instead of
trusting producer-declared PASS fields in campaign receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_SLOT_KEYS = {
    "generation-1:red",
    "generation-1:blue",
    "generation-2:red",
    "generation-2:blue",
}
EXPECTED_BINDING_ROLES = {
    "red_original_exploit",
    "red_patched_exploit",
    "blue_patched_app",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def verify(run_dir: Path) -> dict[str, Any]:
    root = run_dir.resolve()
    errors: list[str] = []
    checked_files: list[str] = []

    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    campaign_path = root / "campaign-receipt.json"
    integrity_path = root / "artifact-integrity-receipt.json"
    require(campaign_path.is_file(), "missing_campaign_receipt")
    require(integrity_path.is_file(), "missing_artifact_integrity_receipt")
    if errors:
        return _result(run_dir=root, errors=errors, checked_files=checked_files)

    campaign = _load(campaign_path)
    integrity = _load(integrity_path)
    checked_files.extend([str(campaign_path), str(integrity_path)])

    require(campaign.get("status") == "PASS", "campaign_status_not_pass")
    require(campaign.get("mocked") is False, "campaign_mocked_not_false")
    require(campaign.get("fixture_fallback_used") is False, "fixture_fallback_used")
    require(integrity.get("status") == "PASS", "artifact_integrity_status_not_pass")

    slots = integrity.get("slots") if isinstance(integrity.get("slots"), list) else []
    require({item.get("slot_key") for item in slots} == EXPECTED_SLOT_KEYS, "slot_key_set_invalid")
    require(len(slots) == 4, "slot_count_invalid")
    slot_paths: list[Path] = []
    for slot in slots:
        path = Path(str(slot.get("path") or ""))
        slot_paths.append(path.resolve())
        checked_files.append(str(path))
        require(path.is_file() and not path.is_symlink(), f"slot_not_regular:{slot.get('slot_key')}")
        require(_inside(path, root), f"slot_outside_run:{slot.get('slot_key')}")
        actual = _sha256(path) if path.is_file() else None
        require(actual == slot.get("expected_sha256"), f"slot_hash_mismatch:{slot.get('slot_key')}")
        require(actual == slot.get("actual_sha256"), f"slot_actual_field_mismatch:{slot.get('slot_key')}")
        require(slot.get("matched") is True, f"slot_declared_unmatched:{slot.get('slot_key')}")
    require(len(set(slot_paths)) == 4, "slot_paths_not_unique")

    replays = (
        integrity.get("judge_replays")
        if isinstance(integrity.get("judge_replays"), list)
        else []
    )
    require({item.get("generation") for item in replays} == {1, 2}, "replay_generation_set_invalid")
    require(len(replays) == 2, "replay_count_invalid")
    for replay in replays:
        generation = replay.get("generation")
        path = Path(str(replay.get("path") or ""))
        checked_files.append(str(path))
        require(path.is_file() and not path.is_symlink(), f"replay_not_regular:g{generation}")
        require(_inside(path, root), f"replay_outside_run:g{generation}")
        actual = _sha256(path) if path.is_file() else None
        require(actual == replay.get("expected_sha256"), f"replay_hash_mismatch:g{generation}")
        require(actual == replay.get("actual_sha256"), f"replay_actual_field_mismatch:g{generation}")
        require(replay.get("status") == "PASS", f"replay_status_not_pass:g{generation}")
        require(replay.get("matched") is True, f"replay_declared_unmatched:g{generation}")
        require(replay.get("receipt_valid") is True, f"replay_receipt_invalid:g{generation}")

    attempt_paths = sorted(root.glob("generation-[12]/judge/replays/*/attempt-receipt.json"))
    exact_attempt_paths = sorted(
        root.glob("generation-[12]/judge-exact-replay/judge/replays/*/attempt-receipt.json")
    )
    require(len(attempt_paths) == 2, "judge_attempt_count_invalid")
    require(len(exact_attempt_paths) == 2, "exact_replay_attempt_count_invalid")
    for path in [*attempt_paths, *exact_attempt_paths]:
        checked_files.append(str(path))
        _verify_attempt(path=path, root=root, errors=errors, checked_files=checked_files)

    generations = (
        campaign.get("generations")
        if isinstance(campaign.get("generations"), list)
        else []
    )
    require(len(generations) == 2, "generation_summary_count_invalid")
    for item in generations:
        generation = item.get("generation")
        require(item.get("judge_status") == "PASS", f"generation_judge_status_not_pass:g{generation}")
        require(item.get("judged_pair_count") == 1, f"generation_judged_pair_count_invalid:g{generation}")
        require(item.get("tau_status") == "PASS", f"generation_tau_status_not_pass:g{generation}")

    return _result(run_dir=root, errors=errors, checked_files=checked_files)


def _verify_attempt(
    *,
    path: Path,
    root: Path,
    errors: list[str],
    checked_files: list[str],
) -> None:
    attempt = _load(path)

    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(f"{path}:{code}")

    require(attempt.get("status") == "PASS", "attempt_status_not_pass")
    require(attempt.get("judge_input_byte_binding_pass") is True, "byte_binding_not_pass")
    bindings = (
        attempt.get("judge_input_byte_bindings")
        if isinstance(attempt.get("judge_input_byte_bindings"), list)
        else []
    )
    require({item.get("role") for item in bindings} == EXPECTED_BINDING_ROLES, "binding_roles_invalid")
    require(len(bindings) == 3, "binding_count_invalid")
    for binding in bindings:
        role = binding.get("role")
        source = Path(str(binding.get("source_path") or ""))
        execution = Path(str(binding.get("execution_path") or ""))
        checked_files.extend([str(source), str(execution)])
        require(source.is_file() and not source.is_symlink(), f"source_not_regular:{role}")
        require(execution.is_file() and not execution.is_symlink(), f"execution_not_regular:{role}")
        require(_inside(source, root), f"source_outside_run:{role}")
        require(_inside(execution, root), f"execution_outside_run:{role}")
        source_sha = _sha256(source) if source.is_file() else None
        execution_sha = _sha256(execution) if execution.is_file() else None
        require(source_sha == binding.get("source_sha256"), f"source_hash_mismatch:{role}")
        require(execution_sha == binding.get("execution_sha256"), f"execution_hash_mismatch:{role}")
        require(source_sha == execution_sha, f"source_execution_hash_mismatch:{role}")
        require(binding.get("matched") is True, f"binding_declared_unmatched:{role}")
        docker_path = binding.get("docker_workspace_path")
        require(isinstance(docker_path, str) and docker_path.startswith("/workspace/"), f"docker_path_invalid:{role}")


def _result(*, run_dir: Path, errors: list[str], checked_files: list[str]) -> dict[str, Any]:
    unique_checked = sorted(set(checked_files))
    return {
        "schema": "battle.adaptive_lineage_backend_verification.v1",
        "status": "PASS" if not errors else "FAIL",
        "run_dir": str(run_dir),
        "checked_file_count": len(unique_checked),
        "checked_files": unique_checked,
        "errors": errors,
        "mocked": False,
        "live": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = verify(args.run_dir)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
