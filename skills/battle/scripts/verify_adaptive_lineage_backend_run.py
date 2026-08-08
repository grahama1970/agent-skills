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
    slot_records: list[dict[str, Any]] = []
    replay_records: list[dict[str, Any]] = []
    attempt_records: list[dict[str, Any]] = []

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
    require(campaign.get("live") is True, "campaign_live_not_true")
    require(campaign.get("fixture_fallback_used") is False, "fixture_fallback_used")
    require(integrity.get("status") == "PASS", "artifact_integrity_status_not_pass")
    campaign_integrity = (
        campaign.get("artifact_integrity")
        if isinstance(campaign.get("artifact_integrity"), dict)
        else {}
    )
    require(
        campaign_integrity.get("sha256") == _sha256(integrity_path),
        "campaign_artifact_integrity_sha_mismatch",
    )
    campaign_integrity_path = campaign_integrity.get("path")
    if campaign_integrity_path:
        require(
            Path(str(campaign_integrity_path)).resolve() == integrity_path,
            "campaign_artifact_integrity_path_mismatch",
        )
    require(integrity.get("required_slot_count") == 4, "required_slot_count_invalid")
    require(integrity.get("matched_slot_count") == 4, "matched_slot_count_invalid")
    require(integrity.get("required_replay_count") == 2, "required_replay_count_invalid")
    require(integrity.get("matched_replay_count") == 2, "matched_replay_count_invalid")

    slots = integrity.get("slots") if isinstance(integrity.get("slots"), list) else []
    require(
        {item.get("slot_key") for item in slots} == EXPECTED_SLOT_KEYS,
        "slot_key_set_invalid",
    )
    require(len(slots) == 4, "slot_count_invalid")
    slot_paths: list[Path] = []
    for slot in slots:
        path = Path(str(slot.get("path") or ""))
        slot_paths.append(path.resolve())
        checked_files.append(str(path))
        require(
            path.is_file() and not path.is_symlink(),
            f"slot_not_regular:{slot.get('slot_key')}",
        )
        require(_inside(path, root), f"slot_outside_run:{slot.get('slot_key')}")
        actual = _sha256(path) if path.is_file() else None
        require(
            actual == slot.get("expected_sha256"),
            f"slot_hash_mismatch:{slot.get('slot_key')}",
        )
        require(
            actual == slot.get("actual_sha256"),
            f"slot_actual_field_mismatch:{slot.get('slot_key')}",
        )
        require(slot.get("matched") is True, f"slot_declared_unmatched:{slot.get('slot_key')}")
        slot_records.append(
            {
                "slot_key": slot.get("slot_key"),
                "path": str(path),
                "expected_sha256": slot.get("expected_sha256"),
                "actual_sha256": actual,
                "matched": actual == slot.get("expected_sha256")
                and actual == slot.get("actual_sha256")
                and slot.get("matched") is True,
            }
        )
    require(len(set(slot_paths)) == 4, "slot_paths_not_unique")

    replays = (
        integrity.get("judge_replays")
        if isinstance(integrity.get("judge_replays"), list)
        else []
    )
    require(
        {item.get("generation") for item in replays} == {1, 2},
        "replay_generation_set_invalid",
    )
    require(len(replays) == 2, "replay_count_invalid")
    replay_paths: list[Path] = []
    for replay in replays:
        generation = replay.get("generation")
        path = Path(str(replay.get("path") or ""))
        replay_paths.append(path.resolve())
        checked_files.append(str(path))
        require(
            path.is_file() and not path.is_symlink(),
            f"replay_not_regular:g{generation}",
        )
        require(_inside(path, root), f"replay_outside_run:g{generation}")
        actual = _sha256(path) if path.is_file() else None
        replay_body = _load(path) if path.is_file() else {}
        require(
            actual == replay.get("expected_sha256"),
            f"replay_hash_mismatch:g{generation}",
        )
        require(
            actual == replay.get("actual_sha256"),
            f"replay_actual_field_mismatch:g{generation}",
        )
        require(replay.get("status") == "PASS", f"replay_status_not_pass:g{generation}")
        require(replay.get("matched") is True, f"replay_declared_unmatched:g{generation}")
        require(replay.get("receipt_valid") is True, f"replay_receipt_invalid:g{generation}")
        require(replay_body.get("status") == "PASS", f"replay_file_status_not_pass:g{generation}")
        require(replay_body.get("matched") is True, f"replay_file_matched_not_true:g{generation}")
        require(
            replay_body.get("receipt_valid") is True,
            f"replay_file_receipt_valid_not_true:g{generation}",
        )
        replay_records.append(
            {
                "generation": generation,
                "path": str(path),
                "expected_sha256": replay.get("expected_sha256"),
                "actual_sha256": actual,
                "matched": actual == replay.get("expected_sha256")
                and actual == replay.get("actual_sha256")
                and replay.get("matched") is True
                and replay_body.get("matched") is True,
                "docker_image_id": replay_body.get("docker_image_id"),
                "replay_docker_image_id": replay_body.get("replay_docker_image_id"),
            }
        )
    require(len(set(replay_paths)) == 2, "replay_paths_not_unique")

    attempt_paths = sorted(root.glob("generation-[12]/judge/replays/*/attempt-receipt.json"))
    exact_attempt_paths = sorted(
        root.glob("generation-[12]/judge-exact-replay/judge/replays/*/attempt-receipt.json")
    )
    require(len(attempt_paths) == 2, "judge_attempt_count_invalid")
    require(len(exact_attempt_paths) == 2, "exact_replay_attempt_count_invalid")
    for path in [*attempt_paths, *exact_attempt_paths]:
        checked_files.append(str(path))
        _verify_attempt(
            path=path,
            root=root,
            errors=errors,
            checked_files=checked_files,
            attempt_records=attempt_records,
        )

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

    return _result(
        run_dir=root,
        errors=errors,
        checked_files=checked_files,
        slot_records=slot_records,
        replay_records=replay_records,
        attempt_records=attempt_records,
    )


def _verify_attempt(
    *,
    path: Path,
    root: Path,
    errors: list[str],
    checked_files: list[str],
    attempt_records: list[dict[str, Any]],
) -> None:
    if path.is_symlink() or not path.is_file() or not _inside(path, root):
        errors.append(f"{path}:attempt_path_invalid")
        return
    attempt = _load(path)

    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(f"{path}:{code}")

    require(attempt.get("status") == "PASS", "attempt_status_not_pass")
    require(attempt.get("judge_input_byte_binding_pass") is True, "byte_binding_not_pass")
    require(attempt.get("container_input_hash_pass") is True, "container_input_hash_not_pass")
    bindings = (
        attempt.get("judge_input_byte_bindings")
        if isinstance(attempt.get("judge_input_byte_bindings"), list)
        else []
    )
    require(
        {item.get("role") for item in bindings} == EXPECTED_BINDING_ROLES,
        "binding_roles_invalid",
    )
    require(len(bindings) == 3, "binding_count_invalid")
    workspace_hashes: dict[str, str] = {}
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
        if isinstance(docker_path, str) and execution_sha:
            workspace_hashes[Path(docker_path).name] = execution_sha
    container_hashes = (
        attempt.get("container_input_hashes")
        if isinstance(attempt.get("container_input_hashes"), list)
        else []
    )
    require(len(container_hashes) == 2, "container_hash_receipt_count_invalid")
    for item in container_hashes:
        require(item.get("status") == "PASS", "container_hash_status_not_pass")
        require(item.get("matched") is True, "container_hash_declared_unmatched")
        expected = item.get("expected_sha256")
        observed = item.get("observed_sha256")
        require(isinstance(expected, dict), "container_hash_expected_invalid")
        require(isinstance(observed, dict), "container_hash_observed_invalid")
        require(expected == observed, "container_hash_expected_observed_mismatch")
        if isinstance(expected, dict):
            for name, digest in expected.items():
                require(
                    workspace_hashes.get(str(name)) == digest,
                    f"container_hash_execution_mismatch:{name}",
                )
        command = item.get("command_receipt") if isinstance(item.get("command_receipt"), dict) else {}
        require(command.get("exit_code") == 0, "container_hash_command_failed")
    attempt_records.append(
        {
            "path": str(path),
            "binding_role_count": len(bindings),
            "container_hash_receipt_count": len(container_hashes),
            "status": attempt.get("status"),
            "judge_input_byte_binding_pass": attempt.get("judge_input_byte_binding_pass"),
            "container_input_hash_pass": attempt.get("container_input_hash_pass"),
        }
    )


def _result(
    *,
    run_dir: Path,
    errors: list[str],
    checked_files: list[str],
    slot_records: list[dict[str, Any]] | None = None,
    replay_records: list[dict[str, Any]] | None = None,
    attempt_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    unique_checked = sorted(set(checked_files))
    slot_records = slot_records or []
    replay_records = replay_records or []
    attempt_records = attempt_records or []
    return {
        "schema": "battle.adaptive_lineage_backend_verification.v1",
        "status": "PASS" if not errors else "FAIL",
        "run_dir": str(run_dir),
        "checked_file_count": len(unique_checked),
        "checked_files": unique_checked,
        "errors": errors,
        "slot_hashes_matched": sum(1 for item in slot_records if item.get("matched")),
        "slot_hashes_required": 4,
        "exact_replays_matched": sum(
            1 for item in replay_records if item.get("matched")
        ),
        "exact_replays_required": 2,
        "judge_attempt_count": sum(
            1 for item in attempt_records if "/judge/replays/" in item.get("path", "")
        ),
        "exact_replay_attempt_count": sum(
            1
            for item in attempt_records
            if "/judge-exact-replay/judge/replays/" in item.get("path", "")
        ),
        "slot_records": slot_records,
        "replay_records": replay_records,
        "attempt_records": attempt_records,
        "mocked": False,
        "live": True,
    }


def write_backend_report(run_dir: Path, verification: dict[str, Any]) -> Path:
    root = run_dir.resolve()
    campaign_path = root / "campaign-receipt.json"
    integrity_path = root / "artifact-integrity-receipt.json"
    campaign = _load(campaign_path) if campaign_path.is_file() else {}
    integrity = _load(integrity_path) if integrity_path.is_file() else {}
    auth_receipts = _authorization_receipts(root)
    lines = [
        "# Battle Backend Report",
        "",
        f"- run_id: {campaign.get('run_id')}",
        f"- source_commit: {campaign.get('source_commit')}",
        f"- source_tree: {campaign.get('source_tree')}",
        f"- campaign_receipt: {campaign_path}",
        f"- campaign_sha256: {_sha256(campaign_path) if campaign_path.is_file() else None}",
        f"- artifact_integrity_receipt: {integrity_path}",
        f"- artifact_integrity_sha256: {_sha256(integrity_path) if integrity_path.is_file() else None}",
        "",
        "## Authorization Receipts",
        "",
    ]
    if auth_receipts:
        lines.extend(
            f"- {path}: sha256={digest}" for path, digest in auth_receipts
        )
    else:
        lines.append("- NONE")
    lines.extend(["", "## Generations", ""])
    generations = campaign.get("generations") if isinstance(campaign.get("generations"), list) else []
    for item in generations:
        lines.extend(
            [
                f"### Generation {item.get('generation')}",
                "",
                f"- original_judge_status: {item.get('judge_status')}",
                f"- original_judge_verdict: {item.get('judge_verdict')}",
                f"- judged_pair_count: {item.get('judged_pair_count')}",
                "",
            ]
        )
    lines.extend(["## Immutable Slots", ""])
    slots = integrity.get("slots") if isinstance(integrity.get("slots"), list) else []
    for slot in slots:
        lines.append(
            "- "
            f"{slot.get('slot_key')}: path={slot.get('path')} "
            f"expected_sha256={slot.get('expected_sha256')} "
            f"actual_sha256={slot.get('actual_sha256')} "
            f"matched={slot.get('matched')}"
        )
    lines.extend(["", "## Exact Replays", ""])
    replays = integrity.get("judge_replays") if isinstance(integrity.get("judge_replays"), list) else []
    for replay in replays:
        replay_body = _load(Path(str(replay.get("path")))) if replay.get("path") else {}
        lines.append(
            "- "
            f"generation={replay.get('generation')} "
            f"path={replay.get('path')} "
            f"status={replay.get('status')} "
            f"matched={replay.get('matched')} "
            f"receipt_valid={replay.get('receipt_valid')} "
            f"docker_image_id={replay_body.get('docker_image_id')} "
            f"replay_docker_image_id={replay_body.get('replay_docker_image_id')}"
        )
    lines.extend(
        [
            "",
            "## Independent Verifier",
            "",
            f"- status: {verification.get('status')}",
            f"- errors: {verification.get('errors')}",
            f"- slots_verified: {verification.get('slot_hashes_matched')}/4",
            f"- exact_replays_verified: {verification.get('exact_replays_matched')}/2",
            f"- judge_attempt_count: {verification.get('judge_attempt_count')}",
            f"- exact_replay_attempt_count: {verification.get('exact_replay_attempt_count')}",
            "",
            "## Non-Claims",
            "",
            "- no improvement claim",
            "- no production-readiness claim",
            "- no UX-acceptance claim",
            "",
        ]
    )
    report_path = root / "battle-report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _authorization_receipts(root: Path) -> list[tuple[Path, str]]:
    paths = sorted(root.glob("**/research-query-authorization.json"))
    return [(path, _sha256(path)) for path in paths if path.is_file()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = verify(args.run_dir)
    if args.out:
        result["path"] = str(args.out)
    report_path = write_backend_report(args.run_dir, result)
    result["battle_report_path"] = str(report_path)
    result["battle_report_sha256"] = _sha256(report_path)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
