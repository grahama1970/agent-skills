from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_adaptive_lineage_backend_run.py"
)


def test_backend_verifier_accepts_rehashed_receipts(tmp_path: Path) -> None:
    run_dir = _write_minimal_run(tmp_path / "run")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(run_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "PASS"
    assert result["checked_file_count"] > 10


def test_backend_verifier_rejects_rewired_blue_execution_bytes(tmp_path: Path) -> None:
    run_dir = _write_minimal_run(tmp_path / "run")
    blue_exec = next(
        run_dir.glob("generation-2/judge/replays/red-0__blue-0/patched/app.py")
    )
    blue_exec.write_text("def import_zip(): return 'tampered'\n", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(run_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["status"] == "FAIL"
    assert any("execution_hash_mismatch:blue_patched_app" in error for error in result["errors"])


def _write_minimal_run(root: Path) -> Path:
    root.mkdir(parents=True)
    slots: list[dict[str, object]] = []
    for generation in (1, 2):
        for team in ("red", "blue"):
            slot = (
                root
                / f"generation-{generation}"
                / "reviewed"
                / "immutable-slots"
                / f"generation-{generation}-{team}.py"
            )
            slot.parent.mkdir(parents=True, exist_ok=True)
            body = f"# g{generation} {team}\n"
            if team == "red":
                body += "print('RED_EXPLOIT_CONFIRMED')\n"
            else:
                body += "def import_zip(): return 'blocked'\n"
            slot.write_text(body, encoding="utf-8")
            sha = _sha(slot)
            slots.append(
                {
                    "slot_key": f"generation-{generation}:{team}",
                    "generation": generation,
                    "team": team,
                    "path": str(slot),
                    "expected_sha256": sha,
                    "actual_sha256": sha,
                    "matched": True,
                    "regular_file": True,
                    "inside_run_root": True,
                }
            )

    replay_records: list[dict[str, object]] = []
    for generation in (1, 2):
        judge = root / f"generation-{generation}" / "judge" / "replays" / "red-0__blue-0"
        exact = (
            root
            / f"generation-{generation}"
            / "judge-exact-replay"
            / "judge"
            / "replays"
            / "red-0__blue-0"
        )
        _write_attempt(root=root, generation=generation, attempt_dir=judge)
        _copy_attempt_with_workspaces(judge, exact)
        replay_receipt = root / f"generation-{generation}" / "judge-exact-replay" / "exact-replay-receipt.json"
        _write_json(
            replay_receipt,
            {
                "schema": "battle.exact_judge_pair_replay.v1",
                "status": "PASS",
                "matched": True,
                "generation": generation,
            },
        )
        replay_sha = _sha(replay_receipt)
        replay_records.append(
            {
                "generation": generation,
                "status": "PASS",
                "matched": True,
                "path": str(replay_receipt),
                "expected_sha256": replay_sha,
                "actual_sha256": replay_sha,
                "receipt_valid": True,
                "regular_file": True,
                "inside_run_root": True,
            }
        )

    _write_json(
        root / "artifact-integrity-receipt.json",
        {
            "schema": "battle.adaptive_artifact_integrity.v1",
            "status": "PASS",
            "required_slot_count": 4,
            "matched_slot_count": 4,
            "required_replay_count": 2,
            "matched_replay_count": 2,
            "unique_slot_paths": True,
            "slots": slots,
            "judge_replays": replay_records,
        },
    )
    _write_json(
        root / "campaign-receipt.json",
        {
            "schema": "battle.adaptive_red_blue_lineage_canary.v1",
            "status": "PASS",
            "mocked": False,
            "fixture_fallback_used": False,
            "generations": [
                {
                    "generation": 1,
                    "tau_status": "PASS",
                    "judge_status": "PASS",
                    "judge_verdict": "BLUE_SUCCESS",
                    "judged_pair_count": 1,
                },
                {
                    "generation": 2,
                    "tau_status": "PASS",
                    "judge_status": "PASS",
                    "judge_verdict": "BLUE_SUCCESS",
                    "judged_pair_count": 1,
                },
            ],
        },
    )
    return root


def _write_attempt(*, root: Path, generation: int, attempt_dir: Path) -> None:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    original = attempt_dir / "original"
    patched = attempt_dir / "patched"
    original.mkdir()
    patched.mkdir()
    red_source = (
        root
        / f"generation-{generation}"
        / "reviewed"
        / "immutable-slots"
        / f"generation-{generation}-red.py"
    )
    blue_source = (
        root
        / f"generation-{generation}"
        / "reviewed"
        / "immutable-slots"
        / f"generation-{generation}-blue.py"
    )
    original_red = original / "red_exploit_submission.py"
    patched_red = patched / "red_exploit_submission.py"
    patched_blue = patched / "app.py"
    shutil.copyfile(red_source, original_red)
    shutil.copyfile(red_source, patched_red)
    shutil.copyfile(blue_source, patched_blue)
    red_sha = _sha(red_source)
    blue_sha = _sha(blue_source)
    _write_json(
        attempt_dir / "attempt-receipt.json",
        {
            "schema": "battle.arena_tau_public_only_pair_attempt_receipt.v1",
            "status": "PASS",
            "verdict": "BLUE_SUCCESS",
            "pair_id": "red-0__blue-0",
            "red_artifact_sha256": red_sha,
            "blue_artifact_sha256": blue_sha,
            "judge_input_byte_binding_pass": True,
            "judge_input_byte_bindings": [
                _binding("red_original_exploit", red_source, original_red, red_sha),
                _binding("red_patched_exploit", red_source, patched_red, red_sha),
                _binding("blue_patched_app", blue_source, patched_blue, blue_sha),
            ],
        },
    )


def _copy_attempt_with_workspaces(source: Path, target: Path) -> None:
    shutil.copytree(source, target)
    receipt = target / "attempt-receipt.json"
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    for binding in payload["judge_input_byte_bindings"]:
        for key in ("execution_path",):
            binding[key] = binding[key].replace(str(source), str(target))
    receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _binding(role: str, source: Path, execution: Path, source_sha: str) -> dict[str, object]:
    return {
        "role": role,
        "source_path": str(source),
        "source_sha256": source_sha,
        "execution_path": str(execution),
        "execution_sha256": _sha(execution),
        "docker_workspace_path": "/workspace/app.py"
        if role == "blue_patched_app"
        else "/workspace/red_exploit_submission.py",
        "matched": True,
        "regular_file": True,
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
