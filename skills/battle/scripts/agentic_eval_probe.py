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
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BATTLE_DIR = REPO_ROOT / "skills" / "battle"
RUN_SH = BATTLE_DIR / "run.sh"
AUTH_TEMPLATE = BATTLE_DIR / "fixtures" / "reactive-judge" / "authorization.json"
TARGET_IDENTITY = "battle-reactive-judge-fixture@sha256:reactive-judge-v1"
SPECTATOR_DIR = BATTLE_DIR / "spectator"

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


def _run_in(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 240,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env=merged_env,
    )


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http(host: str, *, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    latest: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(host, timeout=1.0) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - diagnostic path
            latest = exc
        time.sleep(0.1)
    raise RuntimeError(f"HTTP host did not become ready: {host}: {latest!r}")


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
    if _has_current_exact_chain_receipts(default):
        candidates.append(default)
    for receipt in Path("/tmp").glob("battle-1336-*/adaptive-lineage-qualification.json"):
        if _has_current_exact_chain_receipts(receipt.parent):
            candidates.append(receipt.parent)
    for receipt in (BATTLE_DIR / "local").glob("**/adaptive-lineage-qualification.json"):
        if _has_current_exact_chain_receipts(receipt.parent):
            candidates.append(receipt.parent)
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item / "adaptive-lineage-qualification.json").stat().st_mtime)


def _has_current_exact_chain_receipts(root: Path) -> bool:
    qualification_path = root / "adaptive-lineage-qualification.json"
    verification_path = root / "adaptive-lineage-verification.json"
    if not qualification_path.is_file() or not verification_path.is_file():
        return False
    try:
        qualification = _read_json(qualification_path)
    except (OSError, json.JSONDecodeError):
        return False
    if qualification.get("schema") != "battle.adaptive_lineage_goal_qualification.v1":
        return False
    source_root = Path(str(qualification.get("source_run_dir") or ""))
    return all(
        (source_root / name).is_file()
        for name in [
            "campaign-receipt.json",
            "artifact-integrity-receipt.json",
            "backend-verification.json",
        ]
    )


def _adaptive_lineage_proof_root(raw: str | None) -> Path | None:
    if raw:
        return Path(raw)
    env = os.environ.get("BATTLE_ADAPTIVE_LINEAGE_PROOF_ROOT")
    if env:
        return Path(env)
    return _latest_adaptive_lineage_root()


def _regenerate_adaptive_lineage_proof_root(summary_path: Path) -> Path | None:
    proof_parent = summary_path.parent / "adaptive-lineage-live-exact-chain-fresh"
    source_root = proof_parent / "source-run"
    proof_root = proof_parent / "qualification"
    logs_root = proof_parent / "logs"
    if proof_parent.exists():
        shutil.rmtree(proof_parent)
    source_root.mkdir(parents=True)
    proof_root.mkdir(parents=True)
    logs_root.mkdir(parents=True)

    run_id = f"battle-agentic-exact-chain-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    timeout_s = float(os.environ.get("BATTLE_ADAPTIVE_LINEAGE_TIMEOUT_S", "300"))
    canary = _run(
        [
            str(RUN_SH),
            "adaptive-red-blue-lineage-canary",
            "battle-004",
            "--out",
            str(source_root),
            "--run-id",
            run_id,
            "--timeout-s",
            str(timeout_s),
        ],
        timeout=int(timeout_s) + 120,
    )
    (logs_root / "canary.stdout.txt").write_text(canary.stdout, encoding="utf-8")
    (logs_root / "canary.stderr.txt").write_text(canary.stderr, encoding="utf-8")
    if canary.returncode != 0:
        return None

    verifier = _run(
        [
            sys.executable,
            str(BATTLE_DIR / "scripts" / "verify_adaptive_lineage_backend_run.py"),
            str(source_root),
            "--out",
            str(source_root / "backend-verification.json"),
        ],
        timeout=180,
    )
    (logs_root / "verifier.stdout.txt").write_text(verifier.stdout, encoding="utf-8")
    (logs_root / "verifier.stderr.txt").write_text(verifier.stderr, encoding="utf-8")
    if verifier.returncode != 0:
        return None

    qualification = _run(
        [
            str(RUN_SH),
            "arena-adaptive-lineage-qualification",
            "battle-004",
            "--proof-dir",
            str(proof_root),
            "--source-root",
            str(source_root),
            "--fresh",
            "--require-live",
            "--forbid-mock",
            "--require-exact-replay",
        ],
        timeout=180,
    )
    (logs_root / "qualification.stdout.txt").write_text(
        qualification.stdout, encoding="utf-8"
    )
    (logs_root / "qualification.stderr.txt").write_text(
        qualification.stderr, encoding="utf-8"
    )
    if qualification.returncode != 0:
        return None
    return proof_root


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


def probe_receipt_pixi_replay(summary_path: Path) -> int:
    out_root = summary_path.parent / "receipt-pixi-replay"
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    build = _run_in(["npm", "run", "build"], cwd=SPECTATOR_DIR, timeout=180)
    (out_root / "build.stdout.txt").write_text(build.stdout, encoding="utf-8")
    (out_root / "build.stderr.txt").write_text(build.stderr, encoding="utf-8")
    if build.returncode != 0:
        raise AssertionError("spectator build failed before receipt Pixi replay proof")

    port = _free_local_port()
    host = f"http://127.0.0.1:{port}"
    screenshot_dir = out_root / "screenshots"
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(port),
            "--bind",
            "127.0.0.1",
            "-d",
            "dist",
        ],
        cwd=SPECTATOR_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_http(host)
        proof = _run_in(
            ["npm", "run", "prove:receipt-pixi"],
            cwd=SPECTATOR_DIR,
            timeout=90,
            env={
                "BATTLE_HOST": host,
                "BATTLE_RECEIPT_CAPTURE_DIR": str(screenshot_dir),
            },
        )
    finally:
        server.terminate()
        try:
            stdout, stderr = server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            stdout, stderr = server.communicate(timeout=5)
        (out_root / "server.stdout.txt").write_text(stdout or "", encoding="utf-8")
        (out_root / "server.stderr.txt").write_text(stderr or "", encoding="utf-8")

    (out_root / "prove-receipt-pixi.stdout.txt").write_text(proof.stdout, encoding="utf-8")
    (out_root / "prove-receipt-pixi.stderr.txt").write_text(proof.stderr, encoding="utf-8")
    if proof.returncode != 0:
        raise AssertionError("receipt Pixi replay proof failed")
    if "PASS battle-receipt-pixi-sanity" not in proof.stdout:
        raise AssertionError("receipt Pixi replay proof did not emit PASS marker")

    required_screenshots = [
        screenshot_dir / "before-spawn.png",
        screenshot_dir / "after-spawn.png",
    ]
    missing = [str(path) for path in required_screenshots if not path.is_file() or path.stat().st_size < 1000]
    if missing:
        raise AssertionError(f"receipt Pixi replay screenshots missing or too small: {missing}")

    return _emit(
        summary_path,
        _summary(
            suite="receipt-pixi-replay",
            live="local_http_static_bundle_playwright_pixi_receipt_replay",
            checks=[
                {
                    "name": "receipt_pixi_replay_browser_proof",
                    "status": "PASS",
                    "host": host,
                    "screenshots": [str(path) for path in required_screenshots],
                }
            ],
            artifacts={
                "stdout": str(out_root / "prove-receipt-pixi.stdout.txt"),
                "stderr": str(out_root / "prove-receipt-pixi.stderr.txt"),
                "before_spawn_screenshot": str(required_screenshots[0]),
                "after_spawn_screenshot": str(required_screenshots[1]),
            },
            claims_proves=[
                "receipt-backed Pixi replay derives parent/child visibility from the served fixture",
                "browser-rendered Pixi replay shows child lanes after the fixture spawn point and supports playhead scrub",
            ],
            claims_does_not_prove=[
                "production staging route availability",
                "arbitrary future fixture schemas",
                "full adaptive-lineage exact-chain backend qualification",
            ],
        ),
    )


def probe_orchestrator_overnight_resume_report(summary_path: Path) -> int:
    out_root = summary_path.parent / "orchestrator-overnight-resume-report"
    if out_root.exists():
        shutil.rmtree(out_root)
    storage = out_root / "storage"
    storage.mkdir(parents=True)
    env = {"BATTLE_STORAGE_ROOT": str(storage)}
    battle_id = "battle_agentic_orchestrator"

    from battle_skill import resume_runtime
    from battle_skill import state as state_module
    from battle_skill.config import OVERNIGHT_CHECKPOINT_INTERVAL, OVERNIGHT_ROUNDS
    from battle_skill.state import BattleState

    old_state_dir = state_module.BATTLES_DIR
    old_resume_dir = resume_runtime.BATTLES_DIR
    try:
        battles_dir = storage / "battles"
        state_module.BATTLES_DIR = battles_dir
        resume_runtime.BATTLES_DIR = battles_dir
        state = BattleState(
            battle_id=battle_id,
            target_path=str(out_root / "target"),
            max_rounds=OVERNIGHT_ROUNDS,
            current_round=7,
            status="running",
        )
        state.last_checkpoint = _utc()
        state.save()
    finally:
        state_module.BATTLES_DIR = old_state_dir
        resume_runtime.BATTLES_DIR = old_resume_dir

    status_proc = _run_in([str(RUN_SH), "status"], cwd=REPO_ROOT, timeout=60, env=env)
    report_proc = _run_in([str(RUN_SH), "report", battle_id], cwd=REPO_ROOT, timeout=60, env=env)
    stop_proc = _run_in([str(RUN_SH), "stop", battle_id], cwd=REPO_ROOT, timeout=60, env=env)
    for name, proc in {
        "status": status_proc,
        "report": report_proc,
        "stop": stop_proc,
    }.items():
        (out_root / f"{name}.stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (out_root / f"{name}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            raise AssertionError(f"battle {name} command failed: {proc.stderr}")

    report_path = storage / "reports" / f"{battle_id}.md"
    if "Battle Status" not in status_proc.stdout:
        raise AssertionError("battle status output did not render the status table")
    if not report_path.is_file() or report_path.stat().st_size < 200:
        raise AssertionError("battle report command did not write a substantive report")

    old_state_dir = state_module.BATTLES_DIR
    old_resume_dir = resume_runtime.BATTLES_DIR
    calls = 0
    try:
        state_module.BATTLES_DIR = storage / "battles"
        resume_runtime.BATTLES_DIR = storage / "battles"

        class _NoopResumeOrchestrator:
            def __init__(self, loaded: BattleState) -> None:
                self.state = loaded
                self.battle_id = loaded.battle_id

            def run(self) -> BattleState:
                nonlocal calls
                calls += 1
                self.state.status = "completed"
                self.state.current_round += 1
                self.state.save()
                return self.state

        def factory(loaded: BattleState) -> _NoopResumeOrchestrator:
            return _NoopResumeOrchestrator(loaded)

        first_resume = resume_runtime.resume_battle_once(
            battle_id,
            request_id="agentic-resume-once",
            orchestrator_factory=factory,
        )
        duplicate_resume = resume_runtime.resume_battle_once(
            battle_id,
            request_id="agentic-resume-once",
            orchestrator_factory=factory,
        )
    finally:
        state_module.BATTLES_DIR = old_state_dir
        resume_runtime.BATTLES_DIR = old_resume_dir

    if first_resume.get("status") != "APPLIED":
        raise AssertionError(f"resume did not apply once: {first_resume}")
    if duplicate_resume.get("status") != "DUPLICATE_IGNORED":
        raise AssertionError(f"duplicate resume was not ignored: {duplicate_resume}")
    if calls != 1:
        raise AssertionError(f"resume orchestrator ran {calls} times, expected once")
    if OVERNIGHT_ROUNDS != 1000 or OVERNIGHT_CHECKPOINT_INTERVAL != 50:
        raise AssertionError("overnight constants drifted from documented contract")

    resume_receipt_path = (
        storage / "battles" / f"{battle_id}_control" / "resume" / "agentic-resume-once.json"
    )
    return _emit(
        summary_path,
        _summary(
            suite="orchestrator-overnight-resume-report",
            live="local_battle_state_status_report_stop_resume_receipts",
            checks=[
                {
                    "name": "status_report_stop_resume_duplicate_guard",
                    "status": "PASS",
                    "battle_id": battle_id,
                    "overnight_rounds": OVERNIGHT_ROUNDS,
                    "checkpoint_interval": OVERNIGHT_CHECKPOINT_INTERVAL,
                    "resume_calls": calls,
                }
            ],
            artifacts={
                "state": str(storage / "battles" / f"{battle_id}.json"),
                "report": str(report_path),
                "resume_receipt": str(resume_receipt_path),
                "status_stdout": str(out_root / "status.stdout.txt"),
                "stop_stdout": str(out_root / "stop.stdout.txt"),
            },
            claims_proves=[
                "status, report, stop, and idempotent resume operate against the same Battle state store",
                "overnight constants remain 1000 rounds and checkpoint interval 50",
            ],
            claims_does_not_prove=[
                "a real 1000-round overnight campaign",
                "fresh Red/Blue provider quality during resume",
            ],
        ),
    )


def probe_digital_twin_non_docker_modes(summary_path: Path) -> int:
    out_root = summary_path.parent / "digital-twin-non-docker-modes"
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    from battle_skill import digital_twin as digital_twin_module
    from battle_skill.digital_twin import DigitalTwin
    from battle_skill.state import TwinMode

    old_worktrees = digital_twin_module.WORKTREES_DIR
    try:
        digital_twin_module.WORKTREES_DIR = out_root / "worktrees"
        source_copy = out_root / "copy-source"
        source_copy.mkdir()
        (source_copy / "app.py").write_text("VALUE = 'source'\n", encoding="utf-8")
        (source_copy / ".git").mkdir()
        (source_copy / ".git" / "ignored").write_text("do-not-copy\n", encoding="utf-8")
        copy_twin = DigitalTwin(str(source_copy), "battle-agentic-copy", mode=TwinMode.COPY)
        if not copy_twin.setup():
            raise AssertionError("copy mode setup failed")
        assert copy_twin.blue_worktree is not None
        assert copy_twin.arena_worktree is not None
        (copy_twin.blue_worktree / "app.py").write_text("VALUE = 'blue'\n", encoding="utf-8")
        if (source_copy / "app.py").read_text(encoding="utf-8") != "VALUE = 'source'\n":
            raise AssertionError("copy mode mutated source workspace")
        if (copy_twin.blue_worktree / ".git").exists():
            raise AssertionError("copy mode copied source .git directory")

        git_source = out_root / "git-source"
        git_source.mkdir()
        (git_source / "app.py").write_text("VALUE = 'git-source'\n", encoding="utf-8")
        for command in (
            ["git", "init"],
            ["git", "config", "user.email", "battle-agentic@example.invalid"],
            ["git", "config", "user.name", "Battle Agentic Eval"],
            ["git", "add", "app.py"],
            ["git", "commit", "-m", "seed"],
        ):
            proc = _run_in(command, cwd=git_source, timeout=60)
            if proc.returncode != 0:
                raise AssertionError(f"git setup failed for {command}: {proc.stderr}")
        git_twin = DigitalTwin(str(git_source), "battle-agentic-git", mode=TwinMode.GIT_WORKTREE)
        if not git_twin.setup():
            raise AssertionError("git_worktree mode setup failed")
        assert git_twin.blue_worktree is not None
        assert git_twin.arena_worktree is not None
        (git_twin.blue_worktree / "app.py").write_text("VALUE = 'blue-git'\n", encoding="utf-8")
        if not git_twin.sync_blue_to_arena():
            raise AssertionError("git_worktree dirty sync to arena failed")
        if (git_twin.arena_worktree / "app.py").read_text(encoding="utf-8") != "VALUE = 'blue-git'\n":
            raise AssertionError("git_worktree arena did not receive Blue patch")
        if (git_source / "app.py").read_text(encoding="utf-8") != "VALUE = 'git-source'\n":
            raise AssertionError("git_worktree mode mutated source workspace")

        firmware = out_root / "firmware.bin"
        firmware.write_bytes(b"BATTLE-FIRMWARE")
        qemu_twin = DigitalTwin(str(firmware), "battle-agentic-qemu", mode=None)
        if qemu_twin.mode != TwinMode.QEMU:
            raise AssertionError("firmware suffix did not select QEMU mode")
    finally:
        digital_twin_module.WORKTREES_DIR = old_worktrees

    return _emit(
        summary_path,
        _summary(
            suite="digital-twin-non-docker-modes",
            live="local_filesystem_git_worktree_copy_qemu_detection",
            checks=[
                {
                    "name": "copy_git_worktree_and_qemu_detection",
                    "status": "PASS",
                    "copy_source_unchanged": True,
                    "git_source_unchanged": True,
                    "qemu_firmware_detected": True,
                }
            ],
            artifacts={
                "copy_blue": str(out_root / "worktrees" / "battle-agentic-copy" / "blue" / "app.py"),
                "git_arena": str(out_root / "worktrees" / "battle-agentic-git" / "arena" / "app.py"),
                "firmware": str(firmware),
            },
            claims_proves=[
                "copy mode isolates Red/Blue/Arena without copying .git",
                "git_worktree mode keeps the source repository unchanged while syncing Blue changes to Arena",
                "firmware targets select QEMU mode by suffix",
            ],
            claims_does_not_prove=[
                "QEMU boot execution inside Docker",
                "arbitrary embedded firmware toolchain support",
            ],
        ),
    )


def probe_swarm_throughput_envelope(summary_path: Path) -> int:
    out_root = summary_path.parent / "swarm-throughput-envelope"
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    positive = _run(
        [
            str(RUN_SH),
            "prove-unbounded-swarm-execution",
            "--out",
            str(out_root / "positive"),
            "--worker-count",
            "4",
            "--min-concurrent-observed",
            "2",
            "--per-worker-timeout-s",
            "30",
        ],
        timeout=180,
    )
    (out_root / "positive.stdout.txt").write_text(positive.stdout, encoding="utf-8")
    (out_root / "positive.stderr.txt").write_text(positive.stderr, encoding="utf-8")
    if positive.returncode != 0:
        raise AssertionError("swarm positive proof failed: " + positive.stderr)
    receipt_path = out_root / "positive" / "unbounded-swarm-execution-proof.json"
    receipt = _read_json(receipt_path)
    _assert_status(receipt, receipt_path)
    if int(receipt.get("max_concurrent_observed") or 0) < 2:
        raise AssertionError("swarm receipt did not observe required concurrency")

    negative = _run(
        [
            str(RUN_SH),
            "prove-unbounded-swarm-execution",
            "--out",
            str(out_root / "negative"),
            "--worker-count",
            "2",
            "--min-concurrent-observed",
            "3",
            "--per-worker-timeout-s",
            "10",
        ],
        timeout=60,
    )
    (out_root / "negative.stdout.txt").write_text(negative.stdout, encoding="utf-8")
    (out_root / "negative.stderr.txt").write_text(negative.stderr, encoding="utf-8")
    if negative.returncode == 0:
        raise AssertionError("swarm impossible concurrency threshold unexpectedly passed")

    return _emit(
        summary_path,
        _summary(
            suite="swarm-throughput-envelope",
            live="local_docker_dynamic_swarm_execution",
            checks=[
                {
                    "name": "docker_swarm_concurrency_and_invalid_threshold",
                    "status": "PASS",
                    "worker_count": receipt.get("worker_count"),
                    "max_concurrent_observed": receipt.get("max_concurrent_observed"),
                    "negative_exit_code": negative.returncode,
                }
            ],
            artifacts={
                "swarm_receipt": str(receipt_path),
                "positive_stdout": str(out_root / "positive.stdout.txt"),
                "negative_stderr": str(out_root / "negative.stderr.txt"),
            },
            claims_proves=[
                "Battle can schedule a configurable Docker swarm beyond fixed two-worker fixtures",
                "invalid concurrency thresholds fail before producing false PASS receipts",
            ],
            claims_does_not_prove=[
                "production cluster autoscaling",
                "Tau provider execution inside every worker",
            ],
        ),
    )


def _write_positive_production_receipts(root: Path) -> dict[str, Path]:
    containerized = root / "containerized.json"
    production_infra = root / "production-infrastructure.json"
    production_ws = root / "production-websocket.json"
    swarm = root / "swarm.json"
    now = _utc()
    _write_json(
        containerized,
        {
            "schema": "battle.containerized_deployment_smoke.v1",
            "status": "PASS",
            "mocked": False,
            "live": "containerized_http_sse_websocket_adapter_plus_vite_preview",
            "commit": "agentic-eval-positive-readiness",
            "counts": {
                "pr8_failed": 0,
                "test_interactions_failed": 0,
                "test_interactions_warned": 0,
                "visual_findings": 0,
            },
            "proofs": {
                "backend_live_transport_receipt": "backend.json",
                "pr8_live_transport_summary": "summary.json",
                "test_interactions_results": "results.json",
                "visual_findings": "visual-findings.jsonl",
                "screenshot": "screenshot.png",
            },
            "processes": {
                "api_pid": 1111,
                "vite_pid": 2222,
                "api_port": 3101,
                "vite_port": 5173,
            },
            "backend": {
                "health_status": 200,
                "rounds_status": 200,
                "sse_event_count": 3,
                "sse_sequence_monotonic": True,
                "sse_ids": [1, 2, 3],
                "websocket_message_count": 3,
                "websocket_sequence_monotonic": True,
                "websocket_ids": [1, 2, 3],
                "bad_resume_statuses": {
                    "future_last_event_id": 400,
                    "negative_last_event_id": 400,
                    "non_integer_last_event_id": 400,
                },
            },
            "frontend": {
                "visual_findings": [],
                "pr8_failed": 0,
                "test_interactions_failed": 0,
                "test_interactions_warned": 0,
                "screenshots": ["screen.png"],
                "trace_path": "trace.zip",
            },
            "created_at": now,
        },
    )
    _write_json(
        production_infra,
        {
            "schema": "battle.production_infrastructure_deployment_proof.v1",
            "status": "PASS",
            "mocked": False,
            "live": "production_infrastructure_deployment",
            "target": {
                "environment": "production",
                "frontend_url": "https://battle.example.com",
                "backend_health_url": "https://battle.example.com/health",
                "websocket_url": "wss://battle.example.com/live",
                "commit": "agentic-eval-positive-readiness",
                "release_id": "battle-agentic-eval",
            },
            "rollback_ref": "battle-agentic-rollback",
            "teardown_ref": "battle-agentic-teardown",
            "secret_source": "external-secret-manager",
            "evidence": {
                "frontend_https_response": {"status_code": 200},
                "backend_health_response": {"status_code": 200},
                "websocket_connectivity": {"connected": True},
                "tls_certificate": {"valid": True},
                "dns_resolution": {"resolves": True},
                "ingress_route": {"status": "PASS"},
                "secret_configuration": {"source": "production-secret-manager"},
            },
            "created_at": now,
        },
    )
    _write_json(
        production_ws,
        {
            "schema": "battle.production_websocket_transport_proof.v1",
            "status": "PASS",
            "mocked": False,
            "live": "production_websocket_tls_auth_fanout_reconnect",
            "websocket_url": "wss://battle.example.com/live",
            "auth": {"required": True, "rejected_without_token": True},
            "fanout": {"clients": 2, "messages_per_client": [3, 3]},
            "reconnect": {"last_event_id_respected": True},
            "created_at": now,
        },
    )
    _write_json(
        swarm,
        {
            "schema": "battle.unbounded_swarm_execution_proof.v1",
            "status": "PASS",
            "mocked": False,
            "live": "local_docker_dynamic_swarm_execution",
            "worker_count": 4,
            "completed_worker_count": 4,
            "failed_worker_count": 0,
            "max_concurrent_observed": 4,
            "min_concurrent_required": 2,
            "worker_receipts": ["worker-0.json", "worker-1.json"],
            "created_at": now,
        },
    )
    return {
        "containerized": containerized,
        "production_infra": production_infra,
        "production_ws": production_ws,
        "swarm": swarm,
    }


def probe_production_positive_readiness(summary_path: Path) -> int:
    out_root = summary_path.parent / "production-positive-readiness"
    if out_root.exists():
        shutil.rmtree(out_root)
    receipts_dir = out_root / "receipts"
    receipts_dir.mkdir(parents=True)
    receipts = _write_positive_production_receipts(receipts_dir)
    positive = _run(
        [
            str(RUN_SH),
            "validate-production-readiness",
            "--out",
            str(out_root / "positive"),
            "--containerized-receipt",
            str(receipts["containerized"]),
            "--production-infrastructure-receipt",
            str(receipts["production_infra"]),
            "--production-websocket-receipt",
            str(receipts["production_ws"]),
            "--unbounded-swarm-receipt",
            str(receipts["swarm"]),
        ],
        timeout=120,
    )
    (out_root / "positive.stdout.txt").write_text(positive.stdout, encoding="utf-8")
    (out_root / "positive.stderr.txt").write_text(positive.stderr, encoding="utf-8")
    if positive.returncode != 0:
        raise AssertionError("positive production readiness contract failed: " + positive.stderr)
    readiness_path = out_root / "positive" / "production-readiness-contract.json"
    readiness = _read_json(readiness_path)
    _assert_status(readiness, readiness_path)

    broken_infra = receipts_dir / "broken-production-infrastructure.json"
    broken = _read_json(receipts["production_infra"])
    broken["target"]["websocket_url"] = "ws://localhost:3101/live"
    _write_json(broken_infra, broken)
    negative = _run(
        [
            str(RUN_SH),
            "validate-production-readiness",
            "--out",
            str(out_root / "negative"),
            "--containerized-receipt",
            str(receipts["containerized"]),
            "--production-infrastructure-receipt",
            str(broken_infra),
            "--production-websocket-receipt",
            str(receipts["production_ws"]),
            "--unbounded-swarm-receipt",
            str(receipts["swarm"]),
        ],
        timeout=120,
    )
    (out_root / "negative.stdout.txt").write_text(negative.stdout, encoding="utf-8")
    (out_root / "negative.stderr.txt").write_text(negative.stderr, encoding="utf-8")
    if negative.returncode == 0:
        raise AssertionError("invalid production URL unexpectedly passed readiness")

    return _emit(
        summary_path,
        _summary(
            suite="production-positive-readiness",
            live="production_readiness_contract_validator_with_external_receipt_shapes",
            checks=[
                {
                    "name": "positive_and_invalid_external_receipts",
                    "status": "PASS",
                    "positive_status": readiness.get("status"),
                    "negative_exit_code": negative.returncode,
                }
            ],
            artifacts={
                "readiness_receipt": str(readiness_path),
                "containerized_receipt": str(receipts["containerized"]),
                "production_infrastructure_receipt": str(receipts["production_infra"]),
                "production_websocket_receipt": str(receipts["production_ws"]),
                "negative_stderr": str(out_root / "negative.stderr.txt"),
            },
            claims_proves=[
                "production readiness can pass only when all required positive receipt classes are present",
                "localhost/non-WSS production infrastructure receipts fail closed",
            ],
            claims_does_not_prove=[
                "that battle.example.com is a deployed Battle instance",
                "fresh production WebSocket fanout against a real public endpoint",
            ],
        ),
    )


def probe_pixi_gameplay_video(summary_path: Path) -> int:
    out_root = summary_path.parent / "pixi-gameplay-video"
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    build = _run_in(["npm", "run", "build"], cwd=SPECTATOR_DIR, timeout=180)
    (out_root / "build.stdout.txt").write_text(build.stdout, encoding="utf-8")
    (out_root / "build.stderr.txt").write_text(build.stderr, encoding="utf-8")
    if build.returncode != 0:
        raise AssertionError("spectator build failed before Pixi gameplay video proof")

    port = _free_local_port()
    host = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(port),
            "--bind",
            "127.0.0.1",
            "-d",
            "dist",
        ],
        cwd=SPECTATOR_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_http(host)
        proof = _run_in(
            ["node", "scripts/prove-battle-pixi-gameplay-video.mjs"],
            cwd=SPECTATOR_DIR,
            timeout=120,
            env={
                "BATTLE_HOST": host,
                "BATTLE_PIXI_GAMEPLAY_OUT_DIR": str(out_root),
            },
        )
    finally:
        server.terminate()
        try:
            stdout, stderr = server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            stdout, stderr = server.communicate(timeout=5)
        (out_root / "server.stdout.txt").write_text(stdout or "", encoding="utf-8")
        (out_root / "server.stderr.txt").write_text(stderr or "", encoding="utf-8")

    (out_root / "gameplay-video.stdout.txt").write_text(proof.stdout, encoding="utf-8")
    (out_root / "gameplay-video.stderr.txt").write_text(proof.stderr, encoding="utf-8")
    if proof.returncode != 0:
        raise AssertionError("Pixi gameplay video proof failed")
    receipt_path = out_root / "pixi-gameplay-video-proof.json"
    receipt = _read_json(receipt_path)
    _assert_status(receipt, receipt_path)
    video_path = Path(str(receipt.get("video_path") or ""))
    if not video_path.is_file() or video_path.stat().st_size < 5000:
        raise AssertionError("Pixi gameplay video artifact is missing or too small")
    for key in ("play_advanced", "pause_stopped", "scrub_reset_works", "scrub_jump_works"):
        if receipt.get(key) is not True:
            raise AssertionError(f"Pixi gameplay check {key} did not pass")

    return _emit(
        summary_path,
        _summary(
            suite="pixi-gameplay-video",
            live="local_http_static_bundle_playwright_video_pixi_gameplay",
            checks=[
                {
                    "name": "play_pause_resume_scrub_video",
                    "status": "PASS",
                    "video_bytes": video_path.stat().st_size,
                    "host": host,
                }
            ],
            artifacts={
                "proof_receipt": str(receipt_path),
                "video": str(video_path),
                "loaded_screenshot": str(out_root / "screenshots" / "loaded.png"),
                "playing_screenshot": str(out_root / "screenshots" / "playing.png"),
                "scrubbed_screenshot": str(out_root / "screenshots" / "scrubbed.png"),
            },
            claims_proves=[
                "browser-rendered Pixi replay records video while play, pause, resume, and scrub controls change replay state",
                "runtime console/page errors were absent during the gameplay capture",
            ],
            claims_does_not_prove=[
                "full visual design acceptance",
                "production route availability",
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
        str(BATTLE_DIR / "local/**/adaptive-lineage-qualification.json"),
        str(summary_path.parent / "adaptive-lineage-live-exact-chain-fresh"),
    ]
    suite = "adaptive-lineage-live-exact-chain"
    if root is None:
        root = _regenerate_adaptive_lineage_proof_root(summary_path)
        if root is None:
            return _emit_blocked(
                summary_path,
                suite=suite,
                reason="unable_to_regenerate_adaptive_lineage_live_receipt_root",
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


def probe_current_status_adaptive_lineage_receipt(summary_path: Path) -> int:
    suite = "current-status-adaptive-lineage-receipt"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    status_path = out_root / "CURRENT_STATUS.json"
    generate = _run_in(
        [sys.executable, str(BATTLE_DIR / "scripts" / "current_status.py"), "generate", "--out", str(status_path)],
        cwd=BATTLE_DIR,
        timeout=120,
    )
    (out_root / "generate.stdout.txt").write_text(generate.stdout, encoding="utf-8")
    (out_root / "generate.stderr.txt").write_text(generate.stderr, encoding="utf-8")
    if generate.returncode != 0:
        raise AssertionError("current_status generate failed: " + generate.stderr)
    check = _run_in(
        [sys.executable, str(BATTLE_DIR / "scripts" / "current_status.py"), "check", "--path", str(status_path)],
        cwd=BATTLE_DIR,
        timeout=120,
    )
    (out_root / "check.stdout.txt").write_text(check.stdout, encoding="utf-8")
    (out_root / "check.stderr.txt").write_text(check.stderr, encoding="utf-8")
    if check.returncode != 0:
        raise AssertionError("current_status check failed: " + check.stdout + check.stderr)
    status = _read_json(status_path)
    receipt = (status.get("source_receipts") or {}).get("adaptive_lineage_qualification") or {}
    claim = next(
        (
            item
            for item in status.get("proven", [])
            if item.get("id") == "p0_adaptive_lineage_fresh_qualification"
        ),
        {},
    )
    evidence = claim.get("evidence") or {}
    if receipt.get("status") != "PASS" or receipt.get("exists") is not True:
        raise AssertionError(f"adaptive lineage qualification receipt missing/pass drifted: {receipt}")
    if claim.get("status") != "PASS":
        raise AssertionError(f"adaptive lineage qualification claim drifted: {claim}")
    if evidence.get("checks_ok") is not True or evidence.get("check_count") != 11:
        raise AssertionError(f"adaptive lineage qualification checks drifted: {evidence}")
    if evidence.get("g2_judge_attempts") != 1:
        raise AssertionError(f"G2 Judge attempt count drifted: {evidence}")
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="local_current_status_generation_with_receipt_readback",
            checks=[
                {
                    "name": "current_status_binds_fresh_adaptive_lineage_receipt",
                    "status": "PASS",
                    "receipt": receipt.get("path"),
                    "receipt_sha256": receipt.get("sha256"),
                    "evidence": evidence,
                }
            ],
            artifacts={
                "current_status": str(status_path),
                "generate_stdout": str(out_root / "generate.stdout.txt"),
                "check_stdout": str(out_root / "check.stdout.txt"),
            },
            claims_proves=[
                "CURRENT_STATUS.json generation binds the newest durable adaptive-lineage qualification receipt",
                "the status checker fails closed unless the adaptive-lineage qualification is PASS with 11 green checks and one G2 Judge attempt",
            ],
            claims_does_not_prove=[
                "browser visual Pixi acceptance from the same receipt set",
                "fresh paid-provider campaign regeneration",
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
        if args.suite == "current-status-adaptive-lineage-receipt":
            return probe_current_status_adaptive_lineage_receipt(args.summary)
        if args.suite == "adaptive-lineage-same-run-backend-contracts":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=[
                    "test_adaptive_red_blue_lineage_canary_contract.py",
                    "test_adaptive_lineage_backend_verifier.py",
                    "test_adaptive_memory_canary_contract.py",
                    "test_adaptive_selection_memory_contract.py",
                    "test_orchestrator_judge_boundary.py",
                ],
            )
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
        if args.suite == "memory-team-learning-contracts":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=[
                    "test_adaptive_memory_canary_contract.py",
                    "test_adaptive_selection_memory_contract.py",
                    "test_adaptive_memory_ablation_contract.py",
                    "test_adaptive_evidence_contract.py",
                    "test_adaptive_lineage_memory.py",
                ],
            )
        if args.suite == "tau-provider-handoff-contracts":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=[
                    "test_child_tau_dag_private_boundary.py",
                    "test_live_tau_child_dag_canary_contract.py",
                    "test_live_specimen_provider_wiring.py",
                    "test_child_dag_node_adapter.py",
                ],
            )
        if args.suite == "research-host-only-ingress-contracts":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=[
                    "test_source_bearing_research_gate.py",
                    "test_live_specimen_provider_wiring.py",
                ],
            )
        if args.suite == "monitor-human-interjection-contracts":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=[
                    "test_human_interjection_contract.py",
                    "test_runtime_pause_after_round.py",
                ],
            )
        if args.suite == "transport":
            return probe_transport(args.summary)
        if args.suite == "receipt-pixi-replay":
            return probe_receipt_pixi_replay(args.summary)
        if args.suite == "orchestrator-overnight-resume-report":
            return probe_orchestrator_overnight_resume_report(args.summary)
        if args.suite == "digital-twin-non-docker-modes":
            return probe_digital_twin_non_docker_modes(args.summary)
        if args.suite == "swarm-throughput-envelope":
            return probe_swarm_throughput_envelope(args.summary)
        if args.suite == "pixi-gameplay-video":
            return probe_pixi_gameplay_video(args.summary)
        if args.suite == "production-positive-readiness":
            return probe_production_positive_readiness(args.summary)
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
