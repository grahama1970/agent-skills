from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_adaptive_lineage_backend_run.py"
)


def test_backend_verifier_accepts_rehashed_receipts(tmp_path: Path) -> None:
    run_dir = _write_minimal_run(tmp_path / "run")
    completed = _run_verifier(run_dir)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "PASS"
    assert result["checked_file_count"] > 10
    assert result["slot_hashes_matched"] == 4
    assert result["exact_replays_matched"] == 2
    report_path = Path(result["battle_report_path"])
    assert report_path.is_file()
    report = report_path.read_text(encoding="utf-8")
    assert "slots_verified: 4/4" in report
    assert "exact_replays_verified: 2/2" in report


def test_backend_verifier_rejects_rewired_blue_execution_bytes(tmp_path: Path) -> None:
    run_dir = _write_minimal_run(tmp_path / "run")
    blue_exec = next(
        run_dir.glob("generation-2/judge/replays/red-0__blue-0/patched/app.py")
    )
    blue_exec.write_text("def import_zip(): return 'tampered'\n", encoding="utf-8")
    completed = _run_verifier(run_dir)
    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["status"] == "FAIL"
    assert any("execution_hash_mismatch:blue_patched_app" in error for error in result["errors"])


def test_backend_verifier_rejects_each_slot_byte_tamper(tmp_path: Path) -> None:
    for generation in (1, 2):
        for team in ("red", "blue"):
            run_dir = _write_minimal_run(tmp_path / f"slot-{generation}-{team}")
            slot = (
                run_dir
                / f"generation-{generation}"
                / "reviewed"
                / "immutable-slots"
                / f"generation-{generation}-{team}.py"
            )
            slot.write_text("tampered\n", encoding="utf-8")
            result = json.loads(_run_verifier(run_dir).stdout)
            assert result["status"] == "FAIL"
            assert f"slot_hash_mismatch:generation-{generation}:{team}" in result["errors"]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("status", "FAIL", "campaign_status_not_pass"),
        ("mocked", True, "campaign_mocked_not_false"),
        ("live", False, "campaign_live_not_true"),
        ("fixture_fallback_used", True, "fixture_fallback_used"),
    ],
)
def test_backend_verifier_rejects_campaign_non_live_or_non_pass(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    run_dir = _write_minimal_run(tmp_path / field)
    campaign_path = run_dir / "campaign-receipt.json"
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    campaign[field] = value
    _write_json(campaign_path, campaign)
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert error in result["errors"]


def test_backend_verifier_rejects_campaign_to_artifact_sha_mismatch(
    tmp_path: Path,
) -> None:
    run_dir = _write_minimal_run(tmp_path / "integrity-binding")
    campaign_path = run_dir / "campaign-receipt.json"
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    campaign["artifact_integrity"]["sha256"] = "0" * 64
    _write_json(campaign_path, campaign)
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert "campaign_artifact_integrity_sha_mismatch" in result["errors"]


def test_backend_verifier_rejects_replay_byte_tamper_and_duplicate_replay(
    tmp_path: Path,
) -> None:
    run_dir = _write_minimal_run(tmp_path / "replay-tamper")
    replay = run_dir / "generation-1" / "judge-exact-replay" / "exact-replay-receipt.json"
    replay.write_text('{"status": "PASS", "matched": true}\n', encoding="utf-8")
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert any("replay_hash_mismatch:g1" in error for error in result["errors"])

    run_dir = _write_minimal_run(tmp_path / "duplicate-replay")
    integrity_path = run_dir / "artifact-integrity-receipt.json"
    integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    integrity["judge_replays"][1]["path"] = integrity["judge_replays"][0]["path"]
    integrity["judge_replays"][1]["expected_sha256"] = integrity["judge_replays"][0][
        "expected_sha256"
    ]
    integrity["judge_replays"][1]["actual_sha256"] = integrity["judge_replays"][0][
        "actual_sha256"
    ]
    _rewrite_integrity_and_campaign(run_dir, integrity)
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert "replay_paths_not_unique" in result["errors"]


def test_backend_verifier_rejects_duplicate_missing_external_and_symlink_slots(
    tmp_path: Path,
) -> None:
    run_dir = _write_minimal_run(tmp_path / "duplicate-slot")
    integrity_path = run_dir / "artifact-integrity-receipt.json"
    integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    integrity["slots"][1]["path"] = integrity["slots"][0]["path"]
    integrity["slots"][1]["expected_sha256"] = integrity["slots"][0]["expected_sha256"]
    integrity["slots"][1]["actual_sha256"] = integrity["slots"][0]["actual_sha256"]
    _rewrite_integrity_and_campaign(run_dir, integrity)
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert "slot_paths_not_unique" in result["errors"]

    run_dir = _write_minimal_run(tmp_path / "missing-slot")
    Path(json.loads((run_dir / "artifact-integrity-receipt.json").read_text(encoding="utf-8"))["slots"][0]["path"]).unlink()
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert any("slot_not_regular:generation-1:red" in error for error in result["errors"])

    run_dir = _write_minimal_run(tmp_path / "external-slot")
    integrity = json.loads((run_dir / "artifact-integrity-receipt.json").read_text(encoding="utf-8"))
    external = tmp_path / "external.py"
    external.write_text("outside\n", encoding="utf-8")
    digest = _sha(external)
    integrity["slots"][0].update(
        {"path": str(external), "expected_sha256": digest, "actual_sha256": digest}
    )
    _rewrite_integrity_and_campaign(run_dir, integrity)
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert "slot_outside_run:generation-1:red" in result["errors"]

    run_dir = _write_minimal_run(tmp_path / "symlink-slot")
    integrity = json.loads((run_dir / "artifact-integrity-receipt.json").read_text(encoding="utf-8"))
    slot = Path(integrity["slots"][0]["path"])
    target = slot.with_suffix(".target.py")
    slot.rename(target)
    slot.symlink_to(target)
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert "slot_not_regular:generation-1:red" in result["errors"]


def test_backend_verifier_rejects_byte_binding_and_docker_hash_defects(
    tmp_path: Path,
) -> None:
    run_dir = _write_minimal_run(tmp_path / "missing-binding")
    attempt = next(run_dir.glob("generation-1/judge/replays/*/attempt-receipt.json"))
    payload = json.loads(attempt.read_text(encoding="utf-8"))
    payload["judge_input_byte_bindings"].pop()
    _write_json(attempt, payload)
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert any("binding_count_invalid" in error for error in result["errors"])

    run_dir = _write_minimal_run(tmp_path / "docker-observed-mismatch")
    attempt = next(run_dir.glob("generation-1/judge/replays/*/attempt-receipt.json"))
    payload = json.loads(attempt.read_text(encoding="utf-8"))
    payload["container_input_hashes"][0]["observed_sha256"] = {
        "red_exploit_submission.py": "0" * 64
    }
    _write_json(attempt, payload)
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert any(
        "container_hash_expected_observed_mismatch" in error
        for error in result["errors"]
    )

    run_dir = _write_minimal_run(tmp_path / "docker-command-failed")
    attempt = next(run_dir.glob("generation-1/judge/replays/*/attempt-receipt.json"))
    payload = json.loads(attempt.read_text(encoding="utf-8"))
    payload["container_input_hashes"][0]["command_receipt"]["exit_code"] = 2
    _write_json(attempt, payload)
    result = json.loads(_run_verifier(run_dir).stdout)
    assert result["status"] == "FAIL"
    assert any("container_hash_command_failed" in error for error in result["errors"])


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
                "receipt_valid": True,
                "generation": generation,
                "docker_image_id": "sha256:" + "d" * 64,
                "replay_docker_image_id": "sha256:" + "d" * 64,
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

    integrity_path = root / "artifact-integrity-receipt.json"
    integrity = {
        "schema": "battle.adaptive_artifact_integrity.v1",
        "status": "PASS",
        "required_slot_count": 4,
        "matched_slot_count": 4,
        "required_replay_count": 2,
        "matched_replay_count": 2,
        "unique_slot_paths": True,
        "unique_replay_paths": True,
        "slots": slots,
        "judge_replays": replay_records,
    }
    _write_json(integrity_path, integrity)
    for team in ("red", "blue"):
        auth_path = root / "generation-2" / team / "research" / "research-query-authorization.json"
        _write_json(
            auth_path,
            {
                "schema": "tau.research_query_authorization.v1",
                "approved": True,
                "allowed_methods": ["brave-search"],
            },
        )
    _write_json(
        root / "campaign-receipt.json",
        {
            "schema": "battle.adaptive_red_blue_lineage_canary.v1",
            "status": "PASS",
            "run_id": "test-run",
            "source_commit": "a" * 40,
            "source_tree": "b" * 40,
            "mocked": False,
            "live": True,
            "fixture_fallback_used": False,
            "artifact_integrity": {
                "path": str(integrity_path),
                "sha256": _sha(integrity_path),
            },
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


def _run_verifier(run_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(run_dir)],
        check=False,
        capture_output=True,
        text=True,
    )


def _rewrite_integrity_and_campaign(run_dir: Path, integrity: dict[str, object]) -> None:
    integrity_path = run_dir / "artifact-integrity-receipt.json"
    _write_json(integrity_path, integrity)
    campaign_path = run_dir / "campaign-receipt.json"
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    campaign["artifact_integrity"] = {
        "path": str(integrity_path),
        "sha256": _sha(integrity_path),
    }
    _write_json(campaign_path, campaign)


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
            "container_input_hash_pass": True,
            "container_input_hashes": [
                _container_hash_receipt(
                    {"red_exploit_submission.py": red_sha}
                ),
                _container_hash_receipt(
                    {
                        "app.py": blue_sha,
                        "red_exploit_submission.py": red_sha,
                    }
                ),
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


def _container_hash_receipt(values: dict[str, str]) -> dict[str, object]:
    return {
        "schema": "battle.judge_container_input_hashes.v1",
        "status": "PASS",
        "expected_sha256": dict(values),
        "observed_sha256": dict(values),
        "matched": True,
        "command_receipt": {"exit_code": 0},
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
