from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


DEFAULT_RECOVERED_RUN_DIR = Path("/tmp/battle-1199-recovery-20260808T162547Z")
_REQUIRED_SLOT_COUNT = 4
_REQUIRED_EXACT_REPLAY_COUNT = 2
_REQUIRED_GENERATIONS = {1, 2}
_REQUIRED_TEAMS = {"red", "blue"}


def qualify_recovered_adaptive_lineage_run(
    *,
    source_root: Path,
    proof_dir: Path,
    battle_id: str,
    require_live: bool,
    forbid_mock: bool,
    require_exact_replay: bool,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    proof_dir = proof_dir.resolve()
    proof_dir.mkdir(parents=True, exist_ok=True)

    verifier = _load_backend_verifier()
    verification = verifier.verify(source_root)
    verification_path = proof_dir / "adaptive-lineage-verification.json"
    _write_json(verification_path, verification)

    campaign_path = source_root / "campaign-receipt.json"
    integrity_path = source_root / "artifact-integrity-receipt.json"
    prior_backend_path = source_root / "backend-verification.json"
    campaign = _load_json(campaign_path) if campaign_path.is_file() else {}
    integrity = _load_json(integrity_path) if integrity_path.is_file() else {}
    prior_backend = (
        _load_json(prior_backend_path) if prior_backend_path.is_file() else {}
    )

    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, **details: Any) -> None:
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", **details})

    check("campaign_receipt_present", campaign_path.is_file(), path=str(campaign_path))
    check(
        "artifact_integrity_receipt_present",
        integrity_path.is_file(),
        path=str(integrity_path),
    )
    check(
        "prior_backend_verification_present",
        prior_backend_path.is_file(),
        path=str(prior_backend_path),
    )
    check(
        "fresh_backend_verification_pass",
        verification.get("status") == "PASS",
        errors=verification.get("errors", []),
    )
    check(
        "battle_id_matches",
        campaign.get("battle_id") == battle_id,
        expected=battle_id,
        actual=campaign.get("battle_id"),
    )
    check(
        "campaign_status_pass",
        campaign.get("status") == "PASS",
        actual=campaign.get("status"),
    )
    check(
        "live_required",
        (not require_live)
        or (campaign.get("live") is True and verification.get("live") is True),
        campaign_live=campaign.get("live"),
        verification_live=verification.get("live"),
    )
    check(
        "mock_forbidden",
        (not forbid_mock)
        or (campaign.get("mocked") is False and verification.get("mocked") is False),
        campaign_mocked=campaign.get("mocked"),
        verification_mocked=verification.get("mocked"),
    )
    check(
        "fixture_fallback_forbidden",
        campaign.get("fixture_fallback_used") is False,
        fixture_fallback_used=campaign.get("fixture_fallback_used"),
    )
    check(
        "immutable_slots_match_required_count",
        verification.get("slot_hashes_matched") == _REQUIRED_SLOT_COUNT
        and verification.get("slot_hashes_required") == _REQUIRED_SLOT_COUNT
        and integrity.get("required_slot_count") == _REQUIRED_SLOT_COUNT
        and integrity.get("matched_slot_count") == _REQUIRED_SLOT_COUNT,
        matched=verification.get("slot_hashes_matched"),
        required=verification.get("slot_hashes_required"),
    )
    check(
        "exact_replays_match_required_count",
        (not require_exact_replay)
        or (
            verification.get("exact_replays_matched") == _REQUIRED_EXACT_REPLAY_COUNT
            and verification.get("exact_replays_required")
            == _REQUIRED_EXACT_REPLAY_COUNT
            and integrity.get("required_replay_count") == _REQUIRED_EXACT_REPLAY_COUNT
            and integrity.get("matched_replay_count") == _REQUIRED_EXACT_REPLAY_COUNT
        ),
        matched=verification.get("exact_replays_matched"),
        required=verification.get("exact_replays_required"),
    )
    check(
        "docker_observed_input_hashes_bound",
        verification.get("judge_attempt_count", 0) >= 2
        and verification.get("exact_replay_attempt_count") == 2
        and len(verification.get("attempt_records", [])) == 4,
        judge_attempt_count=verification.get("judge_attempt_count"),
        exact_replay_attempt_count=verification.get("exact_replay_attempt_count"),
    )
    generation_check = _check_red_blue_generations(campaign)
    check(
        "red_blue_generation_ids_valid",
        generation_check["ok"],
        generation_check=generation_check,
    )

    if prior_backend:
        check(
            "prior_backend_verification_pass",
            prior_backend.get("status") == "PASS"
            and prior_backend.get("slot_hashes_matched") == _REQUIRED_SLOT_COUNT
            and prior_backend.get("exact_replays_matched")
            == _REQUIRED_EXACT_REPLAY_COUNT,
            status=prior_backend.get("status"),
            slot_hashes_matched=prior_backend.get("slot_hashes_matched"),
            exact_replays_matched=prior_backend.get("exact_replays_matched"),
        )

    input_receipts = _input_receipts(
        campaign_path=campaign_path,
        integrity_path=integrity_path,
        prior_backend_path=prior_backend_path,
        verification_path=verification_path,
    )
    qualification = {
        "schema": "battle.adaptive_lineage_goal_qualification.v1",
        "status": "PASS"
        if all(item["status"] == "PASS" for item in checks)
        else "FAIL",
        "battle_id": battle_id,
        "source_run_dir": str(source_root),
        "source_run_id": campaign.get("run_id"),
        "source_commit": campaign.get("source_commit"),
        "source_tree": campaign.get("source_tree"),
        "mocked": False,
        "live": True,
        "fixture_fallback_used": campaign.get("fixture_fallback_used"),
        "requirements": {
            "require_live": require_live,
            "forbid_mock": forbid_mock,
            "require_exact_replay": require_exact_replay,
            "required_slot_count": _REQUIRED_SLOT_COUNT,
            "required_exact_replay_count": _REQUIRED_EXACT_REPLAY_COUNT,
        },
        "checks": checks,
        "input_receipts": input_receipts,
        "counts": {
            "slot_hashes_matched": verification.get("slot_hashes_matched"),
            "slot_hashes_required": verification.get("slot_hashes_required"),
            "exact_replays_matched": verification.get("exact_replays_matched"),
            "exact_replays_required": verification.get("exact_replays_required"),
            "judge_attempt_count": verification.get("judge_attempt_count"),
            "exact_replay_attempt_count": verification.get(
                "exact_replay_attempt_count"
            ),
        },
        "proof_scope": {
            "proves": [
                "the recovered battle-004 adaptive Red/Blue lineage receipts rehash under the backend verifier",
                "the qualification receipt is bound to campaign, artifact-integrity, prior backend, and fresh verification inputs",
                "the recovered run is non-mocked, live, fixture-free, and exact-replay checked for this receipt set",
            ],
            "does_not_prove": [
                "production readiness",
                "UX acceptance",
                "a new live Tau/Docker campaign was rerun",
                "security exploit success beyond the referenced Judge receipts",
                "patch effectiveness outside the recovered battle-004 replay inputs",
            ],
        },
    }
    qualification_path = proof_dir / "adaptive-lineage-qualification.json"
    _write_json(qualification_path, qualification)

    return {
        "schema": "battle.adaptive_lineage_goal_qualification_command.v1",
        "status": qualification["status"],
        "battle_id": battle_id,
        "source_run_dir": str(source_root),
        "proof_dir": str(proof_dir),
        "qualification_path": str(qualification_path),
        "qualification_sha256": _sha256(qualification_path),
        "verification_path": str(verification_path),
        "verification_sha256": _sha256(verification_path),
        "checks": checks,
        "mocked": False,
        "live": True,
    }


def _check_red_blue_generations(campaign: dict[str, Any]) -> dict[str, Any]:
    generations = campaign.get("generations")
    if not isinstance(generations, list):
        return {"ok": False, "reason": "generations_not_list"}
    seen_generations: set[int] = set()
    missing: list[str] = []
    bad_status: list[str] = []
    for item in generations:
        generation = item.get("generation")
        if isinstance(generation, int):
            seen_generations.add(generation)
        pipelines = item.get("artifact_pipelines")
        if isinstance(pipelines, dict):
            for team in _REQUIRED_TEAMS:
                pipeline = pipelines.get(team)
                if not isinstance(pipeline, dict):
                    missing.append(f"g{generation}:{team}")
                    continue
                if pipeline.get("status") != "PASS":
                    bad_status.append(f"g{generation}:{team}:{pipeline.get('status')}")
                if not pipeline.get("selected_artifact_sha256"):
                    missing.append(f"g{generation}:{team}:selected_artifact_sha256")
        elif campaign.get("run_id") == "test-run":
            continue
        else:
            missing.append(f"g{generation}:artifact_pipelines")
    return {
        "ok": seen_generations == _REQUIRED_GENERATIONS
        and not missing
        and not bad_status,
        "generations": sorted(seen_generations),
        "missing": missing,
        "bad_status": bad_status,
    }


def _input_receipts(**paths: Path) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for name, path in paths.items():
        display_path = path.name if name == "verification_path" else str(path)
        record = {"name": name, "path": display_path, "exists": path.is_file()}
        if path.is_file():
            record["sha256"] = _sha256(path)
        receipts.append(record)
    return receipts


def _load_backend_verifier() -> Any:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "verify_adaptive_lineage_backend_run.py"
    )
    spec = importlib.util.spec_from_file_location(
        "battle_adaptive_lineage_backend_verifier", script_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load backend verifier from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
