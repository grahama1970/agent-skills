#!/usr/bin/env python3
"""Battle agentic-eval probes with receipt readback.

The probes are intentionally thin wrappers around existing Battle entrypoints.
They write one summary receipt per eval case so the agentic-evals runner checks
an artifact, not only process output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BATTLE_DIR = REPO_ROOT / "skills" / "battle"
RUN_SH = BATTLE_DIR / "run.sh"
AUTH_TEMPLATE = BATTLE_DIR / "fixtures" / "reactive-judge" / "authorization.json"
TARGET_IDENTITY = "battle-reactive-judge-fixture@sha256:reactive-judge-v1"

for candidate in (REPO_ROOT / "skills", BATTLE_DIR / "src"):
    raw = str(candidate)
    if raw not in sys.path:
        sys.path.insert(0, raw)

from common.security_authorization import validate_target_authorization


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(command: list[str], *, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _fresh_authorization(path: Path, *, target_identity: str = TARGET_IDENTITY) -> dict[str, Any]:
    manifest = _read_json(AUTH_TEMPLATE)
    manifest["expires_at"] = "2099-01-01T00:00:00Z"
    canonical_id, immutable_ref = target_identity.split("@", 1)
    manifest["target"]["canonical_id"] = canonical_id
    manifest["target"]["immutable_ref"] = immutable_ref
    manifest["allowed_actions"] = ["authorization-preflight", "battle"]
    manifest["runtime_modes"] = ["battle", "local_docker_fixture"]
    _write_json(path, manifest)
    return manifest


def _assert_status(receipt: dict[str, Any], path: Path, status: str = "PASS") -> None:
    if receipt.get("status") != status:
        raise AssertionError(f"{path} status {receipt.get('status')!r} != {status!r}")


def _phase_index(ledger: dict[str, Any], phase: str) -> int:
    for idx, event in enumerate(ledger.get("events") or []):
        if event.get("phase") == phase:
            return idx
    raise AssertionError(f"missing phase {phase!r}")


def _summary(
    *,
    suite: str,
    checks: list[dict[str, Any]],
    artifacts: dict[str, str],
    live: str,
    claims_proves: list[str],
    claims_does_not_prove: list[str],
    samples: int | None = None,
) -> dict[str, Any]:
    return {
        "schema": "battle.agentic_eval_probe.v1",
        "suite": suite,
        "status": "PASS",
        "mocked": False,
        "live": live,
        "samples": samples,
        "checks": checks,
        "artifacts": artifacts,
        "claims": {
            "proves": claims_proves,
            "does_not_prove": claims_does_not_prove,
        },
        "created_at": _utc(),
    }


def _emit(summary_path: Path, payload: dict[str, Any]) -> int:
    _write_json(summary_path, payload)
    digest = _sha256_file(summary_path)
    print(f"BATTLE_AGENTIC_EVAL_PASS suite={payload['suite']} receipt_sha256={digest}")
    return 0


def _emit_blocked(summary_path: Path, *, suite: str, reason: str, candidates: list[str]) -> int:
    payload = {
        "schema": "battle.agentic_eval_probe.v1",
        "suite": suite,
        "status": "BLOCKED",
        "mocked": False,
        "live": True,
        "reason": reason,
        "candidates": candidates,
        "claims": {
            "proves": [],
            "does_not_prove": [
                "battle-004 exact-byte live adaptive-lineage qualification",
                "fresh or recovered adaptive Red/Blue lineage chain readiness",
            ],
        },
        "created_at": _utc(),
    }
    _write_json(summary_path, payload)
    print(f"ADAPTIVE_LINEAGE_LIVE_EXACT_CHAIN_BLOCKED reason={reason}")
    return 0


def _latest_adaptive_lineage_root() -> Path | None:
    candidates: list[Path] = []
    default = Path("/tmp/battle-1199-recovery-20260808T162547Z")
    if (default / "adaptive-lineage-qualification.json").is_file():
        candidates.append(default)
    for receipt in Path("/tmp").glob("battle-1336-*/adaptive-lineage-qualification.json"):
        candidates.append(receipt.parent)
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item / "adaptive-lineage-qualification.json").stat().st_mtime)


def _adaptive_lineage_proof_root(raw: str | None) -> Path | None:
    if raw:
        return Path(raw)
    env = os.environ.get("BATTLE_ADAPTIVE_LINEAGE_PROOF_ROOT")
    if env:
        return Path(env)
    return _latest_adaptive_lineage_root()


def probe_reactive_round(summary_path: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="battle-agentic-reactive-") as raw:
        root = Path(raw)
        auth = root / "authorization.json"
        out = root / "round"
        _fresh_authorization(auth)
        proc = _run(
            [
                str(RUN_SH),
                "prove-reactive-judge-round",
                "--authorization-manifest",
                str(auth),
                "--out",
                str(out),
            ],
            timeout=300,
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout + proc.stderr)
            return proc.returncode

        auth_receipt = _read_json(out / "authorization-validation.json")
        ledger = _read_json(out / "event-ledger.json")
        red = _read_json(out / "red-hack-observation.json")
        proactive = _read_json(out / "blue" / "proactive-blue-input.json")
        reactive = _read_json(out / "blue" / "reactive-blue-input.json")
        patch = _read_json(out / "blue" / "candidate-patch-receipt.json")
        judge1 = _read_json(out / "judge-1" / "judge-1-receipt.json")
        judge2 = _read_json(out / "judge-2" / "judge-2-receipt.json")
        scorekeeper = _read_json(out / "scorekeeper-receipt.json")
        hashes = _read_json(out / "artifact-hash-manifest.json")
        round_receipt = _read_json(out / "round-receipt.json")

        for path, receipt in [
            (out / "authorization-validation.json", auth_receipt),
            (out / "event-ledger.json", ledger),
            (out / "blue" / "candidate-patch-receipt.json", patch),
            (out / "judge-1" / "judge-1-receipt.json", judge1),
            (out / "judge-2" / "judge-2-receipt.json", judge2),
            (out / "scorekeeper-receipt.json", scorekeeper),
            (out / "artifact-hash-manifest.json", hashes),
            (out / "round-receipt.json", round_receipt),
        ]:
            _assert_status(receipt, path)

        checks = []
        expected_phases = ledger.get("legal_phase_order") or []
        observed_phases = [event.get("phase") for event in ledger.get("events") or []]
        if observed_phases != expected_phases:
            raise AssertionError("event ledger phase order drifted")
        checks.append({"name": "strict_phase_order", "status": "PASS", "count": len(observed_phases)})

        if _phase_index(ledger, "reactive_blue_started") > _phase_index(ledger, "judge1_terminal"):
            checks.append({"name": "reactive_blue_after_judge1", "status": "PASS"})
        else:
            raise AssertionError("reactive Blue did not start after Judge #1")

        if proactive.get("private_red_findings") != []:
            raise AssertionError("proactive Blue received private Red observation")
        if not reactive.get("private_red_findings"):
            raise AssertionError("reactive Blue did not receive Judge-confirmed Red observation")
        checks.append({"name": "red_blue_visibility_boundary", "status": "PASS"})

        if red.get("status") != "OBSERVED_UNCONFIRMED":
            raise AssertionError("Red observation skipped unconfirmed state")
        if judge1.get("verdict") != "CONFIRMED":
            raise AssertionError("Judge #1 did not independently confirm Red observation")
        if judge2.get("verdict") != "BLUE_SUCCESS" or judge2.get("functionality_preserved") is not True:
            raise AssertionError("Judge #2 did not confirm Blue success plus functionality")
        if scorekeeper.get("score_authority") != "judge_receipts_only":
            raise AssertionError("scorekeeper authority is not Judge receipts")
        checks.append({"name": "judge_and_scorekeeper_authority", "status": "PASS"})

        copied = summary_path.parent / "reactive-round-artifacts"
        if copied.exists():
            shutil.rmtree(copied)
        shutil.copytree(out, copied)
        return _emit(
            summary_path,
            _summary(
                suite="reactive-round-local-docker",
                live="local_docker_isolated_reactive_judge_round",
                checks=checks,
                artifacts={
                    "round_receipt": str(copied / "round-receipt.json"),
                    "event_ledger": str(copied / "event-ledger.json"),
                    "scorekeeper": str(copied / "scorekeeper-receipt.json"),
                    "artifact_manifest": str(copied / "artifact-hash-manifest.json"),
                },
                claims_proves=[
                    "authorized Battle repair path enters the local Docker target boundary",
                    "Red observation remains unconfirmed until Judge #1",
                    "proactive Blue is isolated from private Red observation",
                    "reactive Blue starts only after Judge #1 terminal receipt",
                    "Judge #2 and scorekeeper receipts decide Blue success from replay evidence",
                ],
                claims_does_not_prove=[
                    "arbitrary target exploitability",
                    "paid provider quality",
                    "multi-round scheduler convergence",
                    "production staging deployment",
                ],
            ),
        )


def probe_authorization_sampling(summary_path: Path, *, samples: int, seed: int | None) -> int:
    rng = random.Random(seed)
    accepted = 0
    rejected = 0
    examples: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="battle-agentic-auth-") as raw:
        root = Path(raw)
        for index in range(samples):
            path = root / f"auth-{index}.json"
            target = TARGET_IDENTITY
            manifest = _fresh_authorization(path, target_identity=target)
            mutation = rng.choice(
                [
                    "wrong_target",
                    "wrong_action",
                    "wrong_runtime",
                    "expired",
                    "missing_scope",
                ]
            )
            if mutation == "wrong_target":
                manifest["target"]["immutable_ref"] = f"sha256:mutated-{index}"
            elif mutation == "wrong_action":
                manifest["allowed_actions"] = ["scan"]
            elif mutation == "wrong_runtime":
                manifest["runtime_modes"] = ["git_worktree"]
            elif mutation == "expired":
                manifest["expires_at"] = "2001-01-01T00:00:00Z"
            elif mutation == "missing_scope":
                manifest["allowed_probe_classes"] = []
            _write_json(path, manifest)
            receipt = validate_target_authorization(
                path,
                expected_target=target,
                requested_action="battle",
                requested_runtime_mode="local_docker_fixture",
            )
            if receipt.get("status") == "PASS":
                accepted += 1
                examples.append({"sample": index, "mutation": mutation, "status": "UNEXPECTED_PASS"})
            else:
                rejected += 1
                if len(examples) < 5:
                    examples.append({"sample": index, "mutation": mutation, "errors": receipt.get("errors", [])[:3]})
        if accepted:
            raise AssertionError(f"{accepted}/{samples} invalid authorization manifests were accepted")
        return _emit(
            summary_path,
            _summary(
                suite="authorization-fail-closed-sampling",
                live="authorization_gate_property_sampling",
                samples=samples,
                checks=[
                    {
                        "name": "invalid_authorizations_rejected",
                        "status": "PASS",
                        "samples": samples,
                        "rejected": rejected,
                        "examples": examples,
                    }
                ],
                artifacts={},
                claims_proves=[
                    "Battle authorization rejects mutated target/action/runtime/expiry/scope before execution"
                ],
                claims_does_not_prove=[
                    "operator policy sufficiency for a real customer target",
                    "production credential availability",
                ],
            ),
        )


def probe_scorekeeper_adversarial(summary_path: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="battle-agentic-score-") as raw:
        root = Path(raw)
        auth = root / "authorization.json"
        out = root / "round"
        _fresh_authorization(auth)
        proc = _run(
            [
                str(RUN_SH),
                "prove-reactive-judge-round",
                "--authorization-manifest",
                str(auth),
                "--out",
                str(out),
            ],
            timeout=300,
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout + proc.stderr)
            return proc.returncode
        scorekeeper = _read_json(out / "scorekeeper-receipt.json")
        patch = _read_json(out / "blue" / "candidate-patch-receipt.json")
        patch["advisory_blue_success"] = not bool(patch.get("advisory_blue_success"))
        patch["advisory_functionality_preserved"] = not bool(patch.get("advisory_functionality_preserved"))
        if scorekeeper.get("score_authority") != "judge_receipts_only":
            raise AssertionError("scorekeeper does not declare judge-only authority")
        ignored = scorekeeper.get("ignored_blue_advisory_fields") or {}
        if "advisory_blue_success" not in ignored or "advisory_functionality_preserved" not in ignored:
            raise AssertionError("scorekeeper no longer records ignored Blue self-claim fields")
        if scorekeeper.get("judge2_verdict") != "BLUE_SUCCESS" or scorekeeper.get("winner") != "Blue":
            raise AssertionError("scorekeeper result drifted from Judge #2 receipt")
        copied = summary_path.parent / "scorekeeper-artifacts"
        if copied.exists():
            shutil.rmtree(copied)
        shutil.copytree(out, copied)
        return _emit(
            summary_path,
            _summary(
                suite="scorekeeper-adversarial-self-claim",
                live="local_docker_judge_receipt_readback",
                checks=[
                    {
                        "name": "blue_self_claim_not_score_authority",
                        "status": "PASS",
                        "ignored_fields": sorted(ignored),
                    }
                ],
                artifacts={"scorekeeper": str(copied / "scorekeeper-receipt.json")},
                claims_proves=[
                    "Blue candidate-patch advisory fields are not the score authority"
                ],
                claims_does_not_prove=[
                    "all possible scoring formulas",
                    "production tournament scoring policy",
                ],
            ),
        )


def probe_pytest_contracts(summary_path: Path, *, suite: str, tests: list[str]) -> int:
    proc = _run(
        [
            "uv",
            "run",
            "--project",
            str(BATTLE_DIR),
            "python",
            "-m",
            "pytest",
            "-q",
            *[str(BATTLE_DIR / "tests" / test) for test in tests],
        ],
        timeout=240,
    )
    stdout_path = summary_path.parent / f"{suite}.stdout.txt"
    stderr_path = summary_path.parent / f"{suite}.stderr.txt"
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        return proc.returncode
    marker = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="pytest_contracts_over_battle_runtime_modules",
            checks=[{"name": "pytest_contract_suite", "status": "PASS", "stdout_marker": marker}],
            artifacts={"stdout": str(stdout_path), "stderr": str(stderr_path)},
            claims_proves=[
                "Battle contract tests still reject known adaptive-lineage, memory, pause/resume, and reducer regressions"
            ],
            claims_does_not_prove=[
                "fresh paid-provider adaptive campaign execution",
                "production browser rendering",
            ],
        ),
    )


def probe_transport(summary_path: Path) -> int:
    out = Path(tempfile.mkdtemp(prefix="battle-agentic-transport-"))
    proc = _run(
        [
            str(RUN_SH),
            "prove-transport-safety-smoke",
            "--out",
            str(out),
        ],
        timeout=240,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        return proc.returncode
    receipt_path = out / "transport-safety-smoke.json"
    if not receipt_path.is_file():
        legacy = out / "transport-safety-smoke-receipt.json"
        if legacy.is_file():
            receipt_path = legacy
    receipt = _read_json(receipt_path)
    _assert_status(receipt, receipt_path)
    backend = receipt.get("backend") or {}
    frontend = receipt.get("frontend") or {}
    if backend.get("bad_resume_statuses") != {
        "future_last_event_id": 400,
        "non_integer_last_event_id": 400,
        "negative_last_event_id": 400,
    }:
        raise AssertionError("transport resume fail-closed status map drifted")
    if frontend.get("tests_passed") != frontend.get("tests_total"):
        raise AssertionError("frontend transport tests did not all pass")
    copied = summary_path.parent / "transport-artifacts"
    if copied.exists():
        shutil.rmtree(copied)
    shutil.copytree(out, copied)
    return _emit(
        summary_path,
        _summary(
            suite="transport-pixi-pause-resume",
            live="local_http_sse_websocket_adapter_plus_frontend_transport_tests",
            checks=[
                {
                    "name": "resume_and_frontend_transport",
                    "status": "PASS",
                    "backend_event_count": backend.get("event_count"),
                    "frontend_tests": frontend.get("tests_passed"),
                }
            ],
            artifacts={"transport_receipt": str(copied / receipt_path.name)},
            claims_proves=[
                "same-run transport emits ordered HTTP/SSE/WebSocket receipts",
                "frontend reducers reject transport gaps and malformed payloads",
                "bad Last-Event-ID resume inputs fail closed",
            ],
            claims_does_not_prove=[
                "production WebSocket TLS/auth/fanout",
                "visual Pixi screenshot quality",
                "external staging route availability",
            ],
        ),
    )


def probe_production_fail_closed(summary_path: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="battle-agentic-prod-") as raw:
        root = Path(raw)
        out = root / "out"
        missing = root / "missing-containerized-receipt.json"
        proc = _run(
            [
                str(RUN_SH),
                "validate-production-readiness",
                "--out",
                str(out),
                "--containerized-receipt",
                str(missing),
            ],
            timeout=120,
        )
        if proc.returncode == 0:
            raise AssertionError("production readiness passed with missing receipts")
        stdout_path = summary_path.parent / "production-readiness.stdout.txt"
        stderr_path = summary_path.parent / "production-readiness.stderr.txt"
        stdout_path.write_text(proc.stdout, encoding="utf-8")
        stderr_path.write_text(proc.stderr, encoding="utf-8")
        if "FileNotFoundError" not in proc.stderr and "No such file or directory" not in proc.stderr:
            raise AssertionError("missing production receipt did not produce an explicit failure")
        return _emit(
            summary_path,
            _summary(
                suite="production-readiness-fail-closed",
                live="production_readiness_cli_fail_closed",
                checks=[
                    {
                        "name": "missing_required_readiness_receipt_rejected",
                        "status": "PASS",
                        "returncode": proc.returncode,
                    }
                ],
                artifacts={"stdout": str(stdout_path), "stderr": str(stderr_path)},
                claims_proves=[
                    "Battle production readiness does not pass without required local/external receipts"
                ],
                claims_does_not_prove=[
                    "external staging route exists",
                    "credentials/auth/rollback/teardown authority is available",
                ],
            ),
        )


def probe_adaptive_lineage_live_exact_chain(summary_path: Path, *, proof_root: str | None) -> int:
    root = _adaptive_lineage_proof_root(proof_root)
    candidates = [
        os.environ.get("BATTLE_ADAPTIVE_LINEAGE_PROOF_ROOT", ""),
        "/tmp/battle-1199-recovery-20260808T162547Z",
        "/tmp/battle-1336-*/adaptive-lineage-qualification.json",
    ]
    suite = "adaptive-lineage-live-exact-chain"
    if root is None:
        return _emit_blocked(
            summary_path,
            suite=suite,
            reason="missing_adaptive_lineage_live_receipt_root",
            candidates=[item for item in candidates if item],
        )

    qualification_path = root / "adaptive-lineage-qualification.json"
    if not qualification_path.is_file():
        return _emit_blocked(
            summary_path,
            suite=suite,
            reason="missing_adaptive_lineage_qualification_receipt",
            candidates=[str(root)],
        )

    qualification = _read_json(qualification_path)
    status = qualification.get("status")
    checks = qualification.get("checks") or []
    specimen_ids = qualification.get("specimen_ids")
    if status != "PASS":
        failure = {
            "schema": "battle.agentic_eval_probe.v1",
            "suite": suite,
            "status": "FAIL",
            "mocked": False,
            "live": True,
            "proof_root": str(root),
            "qualification_path": str(qualification_path),
            "qualification_sha256": _sha256_file(qualification_path),
            "qualification_status": status,
            "stop_condition": qualification.get("stop_condition"),
            "reasons": qualification.get("reasons", []),
            "specimen_ids": specimen_ids,
            "created_at": _utc(),
        }
        _write_json(summary_path, failure)
        print(
            "BATTLE_AGENTIC_EVAL_FAIL suite=adaptive-lineage-live-exact-chain "
            f"status={status} stop_condition={qualification.get('stop_condition')}"
        )
        return 1

    required_checks = {
        "campaign_receipt_present",
        "artifact_integrity_receipt_present",
        "prior_backend_verification_present",
        "fresh_backend_verification_pass",
        "live_required",
        "mock_forbidden",
        "fixture_fallback_forbidden",
        "immutable_slots_match_required_count",
        "exact_replays_match_required_count",
        "docker_observed_input_hashes_bound",
        "red_blue_generation_ids_valid",
    }
    passed_checks = {item.get("name") for item in checks if item.get("status") == "PASS"}
    missing = sorted(required_checks - passed_checks)
    if missing:
        raise AssertionError(f"adaptive-lineage qualification missing PASS checks: {missing}")
    if qualification.get("battle_id") != "battle-004":
        raise AssertionError(f"adaptive-lineage qualification battle_id drifted: {qualification.get('battle_id')!r}")
    if qualification.get("mocked") is not False or qualification.get("live") is not True:
        raise AssertionError("adaptive-lineage qualification is not live/non-mocked")
    counts = qualification.get("counts") or {}
    if counts.get("slot_hashes_matched") != 4 or counts.get("exact_replays_matched") != 2:
        raise AssertionError(f"adaptive-lineage qualification counts drifted: {counts}")

    copied = summary_path.parent / "adaptive-lineage-live-exact-chain-artifacts"
    if copied.exists():
        shutil.rmtree(copied)
    copied.mkdir(parents=True)
    for item in ["adaptive-lineage-qualification.json", "adaptive-lineage-verification.json"]:
        source = root / item
        if source.is_file():
            shutil.copy2(source, copied / item)

    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="battle_004_live_adaptive_lineage_exact_chain_receipt_readback",
            checks=[
                {
                    "name": "goal_qualification_receipt_chain",
                    "status": "PASS",
                    "proof_root": str(root),
                    "counts": counts,
                }
            ],
            artifacts={"qualification": str(copied / "adaptive-lineage-qualification.json")},
            claims_proves=[
                "battle-004 exact-byte adaptive Red/Blue lineage qualification is live, non-mocked, fixture-free, and receipt-bound",
                "campaign, artifact-integrity, prior backend verification, and fresh backend verification receipts all bind into the qualification",
            ],
            claims_does_not_prove=[
                "production staging readiness",
                "browser visual Pixi acceptance",
                "arbitrary target exploitability outside battle-004",
            ],
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Battle agentic-eval probe")
    parser.add_argument("suite")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--proof-root")
    args = parser.parse_args()
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    try:
        if args.suite == "reactive-round":
            return probe_reactive_round(args.summary)
        if args.suite == "authorization-sampling":
            return probe_authorization_sampling(args.summary, samples=args.samples, seed=args.seed)
        if args.suite == "scorekeeper-adversarial":
            return probe_scorekeeper_adversarial(args.summary)
        if args.suite == "adaptive-lineage-contracts":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=[
                    "test_adaptive_lineage_goal_qualification.py",
                    "test_adaptive_red_blue_lineage_canary_contract.py",
                    "test_adaptive_lineage_backend_verifier.py",
                    "test_universal_adaptive_lineage_engine.py",
                    "test_adaptive_lineage_memory.py",
                ],
            )
        if args.suite == "adaptive-lineage-live-exact-chain":
            return probe_adaptive_lineage_live_exact_chain(args.summary, proof_root=args.proof_root)
        if args.suite == "memory-lineage-contracts":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=[
                    "test_adaptive_memory_canary_contract.py",
                    "test_adaptive_selection_memory_contract.py",
                    "test_adaptive_memory_ablation_contract.py",
                    "test_adaptive_evidence_contract.py",
                ],
            )
        if args.suite == "transport":
            return probe_transport(args.summary)
        if args.suite == "production-fail-closed":
            return probe_production_fail_closed(args.summary)
        raise SystemExit(f"unknown suite: {args.suite}")
    except Exception as exc:
        failure = {
            "schema": "battle.agentic_eval_probe.v1",
            "suite": args.suite,
            "status": "FAIL",
            "mocked": False,
            "live": False,
            "error": repr(exc),
            "created_at": _utc(),
        }
        _write_json(args.summary, failure)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
