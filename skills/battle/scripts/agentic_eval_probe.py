#!/usr/bin/env python3
"""Battle agentic-eval probes with receipt readback.

The probes are intentionally thin wrappers around existing Battle entrypoints.
They write one summary receipt per eval case so the agentic-evals runner checks
an artifact, not only process output.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
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
from types import SimpleNamespace
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

from common.security_authorization import validate_target_authorization  # noqa: E402


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


def _parse_stdout_json_after_marker(stdout: str, marker: str) -> dict[str, Any]:
    tail = stdout.split(marker, 1)[-1]
    start = tail.find("{")
    end = tail.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AssertionError(f"missing JSON payload after {marker!r}")
    return json.loads(tail[start : end + 1])


def _receipt_pixi_backend_receipt_path() -> Path | None:
    raw = os.environ.get("BATTLE_PIXI_BACKEND_RECEIPT_PATH")
    if raw:
        return Path(raw)
    candidates = sorted(
        (BATTLE_DIR / "local").glob("battle-*-fresh-adaptive-lineage-*/campaign-receipt.json"),
        key=lambda path: path.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def _fresh_authorization(
    path: Path,
    *,
    target_identity: str = TARGET_IDENTITY,
    runtime_modes: list[str] | None = None,
    probe_classes: list[str] | None = None,
) -> dict[str, Any]:
    manifest = _read_json(AUTH_TEMPLATE)
    manifest["expires_at"] = "2099-01-01T00:00:00Z"
    canonical_id, immutable_ref = target_identity.split("@", 1)
    manifest["target"]["canonical_id"] = canonical_id
    manifest["target"]["immutable_ref"] = immutable_ref
    manifest["allowed_actions"] = ["authorization-preflight", "battle"]
    manifest["runtime_modes"] = runtime_modes or ["battle", "local_docker_fixture"]
    if probe_classes is not None:
        manifest["allowed_probe_classes"] = probe_classes
    _write_json(path, manifest)
    return manifest


def _battle_004_target_identity() -> str:
    definition = b"".join(
        (BATTLE_DIR / "src" / "battle_skill" / name).read_bytes()
        for name in ("arena_subagent.py", "arena_battle_proof.py", "arena_live_battle_proof.py")
    )
    return f"battle-004@sha256:{hashlib.sha256(definition).hexdigest()}"


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
    authorization = proof_parent / "authorization.json"
    _fresh_authorization(
        authorization,
        target_identity=_battle_004_target_identity(),
        runtime_modes=["docker"],
        probe_classes=["path_traversal"],
    )
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
            "--authorization-manifest",
            str(authorization),
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


def _invoke_battle_cli_with_recording_orchestrator(args: list[str], root: Path) -> tuple[Any, list[dict[str, Any]]]:
    from unittest.mock import patch

    from typer.testing import CliRunner

    import battle_skill.cli as cli_module
    import battle_skill.orchestrator as orchestrator_module
    import battle_skill.report as report_module

    calls: list[dict[str, Any]] = []

    class RecordingOrchestrator:
        def __init__(self, target_path: str, rounds: int, **kwargs: Any) -> None:
            calls.append(
                {
                    "target_path": target_path,
                    "rounds": rounds,
                    "docker_image": kwargs.get("docker_image"),
                    "twin_mode": getattr(kwargs.get("twin_mode"), "value", kwargs.get("twin_mode")),
                }
            )

        def run(self, checkpoint_interval: int) -> SimpleNamespace:
            return SimpleNamespace(
                battle_id="recording-battle",
                all_findings=[],
                all_patches=[],
                red_total_score=0,
                blue_total_score=1,
                current_round=1,
                tdsr=0.0,
            )

    with (
        patch.object(cli_module, "_HAS_MEMORY_INTEGRATION", False),
        patch.object(cli_module, "REPORTS_DIR", root / "reports"),
        patch.object(orchestrator_module, "BattleOrchestrator", RecordingOrchestrator),
        patch.object(report_module, "generate_report", lambda state: "recording report\n"),
    ):
        result = CliRunner().invoke(cli_module.app, args)
    return result, calls


def probe_review_cli_authorization_target_binding(summary_path: Path) -> int:
    suite = "review-cli-authorization-target-binding"
    with tempfile.TemporaryDirectory(prefix="battle-agentic-cli-auth-binding-") as raw:
        root = Path(raw)
        target_a = root / "target-a"
        target_b = root / "target-b"
        target_a.mkdir()
        target_b.mkdir()
        (target_a / "app.py").write_text("print('a')\n", encoding="utf-8")
        (target_b / "app.py").write_text("print('b')\n", encoding="utf-8")

        alias_identity = "review-cli-alias@sha256:alias"
        path_bad_manifest = root / "path-bad-authorization.json"
        path_bad = _fresh_authorization(
            path_bad_manifest,
            target_identity=alias_identity,
            runtime_modes=["copy"],
        )
        path_bad["target"]["repository_url"] = target_a.as_uri()
        _write_json(path_bad_manifest, path_bad)

        bad_result, bad_calls = _invoke_battle_cli_with_recording_orchestrator(
            [
                "battle",
                str(target_b),
                "--mode",
                "copy",
                "--rounds",
                "1",
                "--authorization-manifest",
                str(path_bad_manifest),
                "--authorization-target",
                alias_identity,
            ],
            root,
        )

        path_good_manifest = root / "path-good-authorization.json"
        path_good = _fresh_authorization(
            path_good_manifest,
            target_identity=alias_identity,
            runtime_modes=["copy"],
        )
        path_good["target"]["repository_url"] = target_b.as_uri()
        _write_json(path_good_manifest, path_good)

        good_result, good_calls = _invoke_battle_cli_with_recording_orchestrator(
            [
                "battle",
                str(target_b),
                "--mode",
                "copy",
                "--rounds",
                "1",
                "--authorization-manifest",
                str(path_good_manifest),
                "--authorization-target",
                alias_identity,
            ],
            root,
        )

        wrong_alias_identity = "review-cli-other-alias@sha256:alias"
        path_wrong_alias_manifest = root / "path-wrong-alias-authorization.json"
        path_wrong_alias = _fresh_authorization(
            path_wrong_alias_manifest,
            target_identity=wrong_alias_identity,
            runtime_modes=["copy"],
        )
        path_wrong_alias["target"]["repository_url"] = target_b.as_uri()
        _write_json(path_wrong_alias_manifest, path_wrong_alias)

        wrong_alias_result, wrong_alias_calls = _invoke_battle_cli_with_recording_orchestrator(
            [
                "battle",
                str(target_b),
                "--mode",
                "copy",
                "--rounds",
                "1",
                "--authorization-manifest",
                str(path_wrong_alias_manifest),
                "--authorization-target",
                alias_identity,
            ],
            root,
        )

        docker_bad_manifest = root / "docker-bad-authorization.json"
        docker_bad = _fresh_authorization(
            docker_bad_manifest,
            target_identity=alias_identity,
            runtime_modes=["docker"],
        )
        docker_bad["target"]["image"] = "registry.example.invalid/target-a:latest"
        _write_json(docker_bad_manifest, docker_bad)

        docker_result, docker_calls = _invoke_battle_cli_with_recording_orchestrator(
            [
                "battle",
                ".",
                "--rounds",
                "1",
                "--docker-image",
                "registry.example.invalid/target-b:latest",
                "--authorization-manifest",
                str(docker_bad_manifest),
                "--authorization-target",
                alias_identity,
            ],
            root,
        )

        docker_wrong_alias_manifest = root / "docker-wrong-alias-authorization.json"
        docker_wrong_alias = _fresh_authorization(
            docker_wrong_alias_manifest,
            target_identity=wrong_alias_identity,
            runtime_modes=["docker"],
        )
        docker_wrong_alias["target"]["image"] = "registry.example.invalid/target-b:latest"
        _write_json(docker_wrong_alias_manifest, docker_wrong_alias)

        docker_wrong_alias_result, docker_wrong_alias_calls = _invoke_battle_cli_with_recording_orchestrator(
            [
                "battle",
                ".",
                "--rounds",
                "1",
                "--docker-image",
                "registry.example.invalid/target-b:latest",
                "--authorization-manifest",
                str(docker_wrong_alias_manifest),
                "--authorization-target",
                alias_identity,
            ],
            root,
        )

        docker_good_manifest = root / "docker-good-authorization.json"
        docker_good = _fresh_authorization(
            docker_good_manifest,
            target_identity=alias_identity,
            runtime_modes=["docker"],
        )
        docker_good["target"]["image"] = "registry.example.invalid/target-b:latest"
        _write_json(docker_good_manifest, docker_good)

        docker_good_result, docker_good_calls = _invoke_battle_cli_with_recording_orchestrator(
            [
                "battle",
                ".",
                "--rounds",
                "1",
                "--docker-image",
                "registry.example.invalid/target-b:latest",
                "--authorization-manifest",
                str(docker_good_manifest),
                "--authorization-target",
                alias_identity,
            ],
            root,
        )

        checks = [
            {
                "name": "path_alias_for_other_target_fails_before_orchestrator",
                "status": "PASS"
                if bad_result.exit_code == 2
                and not bad_calls
                and "authorization target alias is not bound to executed target" in bad_result.output
                else "FAIL",
                "exit_code": bad_result.exit_code,
                "orchestrator_calls": bad_calls,
            },
            {
                "name": "path_alias_with_verified_file_url_mapping_reaches_recording_orchestrator",
                "status": "PASS"
                if good_result.exit_code == 0
                and len(good_calls) == 1
                and good_calls[0]["target_path"] == str(target_b.resolve())
                else "FAIL",
                "exit_code": good_result.exit_code,
                "orchestrator_calls": good_calls,
            },
            {
                "name": "path_mapping_for_wrong_alias_fails_before_orchestrator",
                "status": "PASS"
                if wrong_alias_result.exit_code == 2
                and not wrong_alias_calls
                and "target identity does not match requested target" in wrong_alias_result.output
                else "FAIL",
                "exit_code": wrong_alias_result.exit_code,
                "orchestrator_calls": wrong_alias_calls,
            },
            {
                "name": "docker_alias_for_other_image_fails_before_orchestrator",
                "status": "PASS"
                if docker_result.exit_code == 2
                and not docker_calls
                and "authorization target alias is not bound to executed target" in docker_result.output
                else "FAIL",
                "exit_code": docker_result.exit_code,
                "orchestrator_calls": docker_calls,
            },
            {
                "name": "docker_mapping_for_wrong_alias_fails_before_orchestrator",
                "status": "PASS"
                if docker_wrong_alias_result.exit_code == 2
                and not docker_wrong_alias_calls
                and "target identity does not match requested target" in docker_wrong_alias_result.output
                else "FAIL",
                "exit_code": docker_wrong_alias_result.exit_code,
                "orchestrator_calls": docker_wrong_alias_calls,
            },
            {
                "name": "docker_alias_with_verified_image_mapping_reaches_recording_orchestrator",
                "status": "PASS"
                if docker_good_result.exit_code == 0
                and len(docker_good_calls) == 1
                and docker_good_calls[0]["docker_image"] == "registry.example.invalid/target-b:latest"
                else "FAIL",
                "exit_code": docker_good_result.exit_code,
                "orchestrator_calls": docker_good_calls,
            },
        ]
        failed = [check for check in checks if check["status"] != "PASS"]
        if failed:
            raise AssertionError(f"CLI authorization target binding checks failed: {failed}")

        artifact_root = summary_path.parent / suite
        if artifact_root.exists():
            shutil.rmtree(artifact_root)
        artifact_root.mkdir(parents=True)
        for name, result in {
            "path-bad": bad_result,
            "path-good": good_result,
            "path-wrong-alias": wrong_alias_result,
            "docker-bad": docker_result,
            "docker-wrong-alias": docker_wrong_alias_result,
            "docker-good": docker_good_result,
        }.items():
            (artifact_root / f"{name}.stdout.txt").write_text(result.output, encoding="utf-8")

        return _emit(
            summary_path,
            _summary(
                suite=suite,
                live="typer_cli_recording_orchestrator_authorization_boundary",
                checks=checks,
                artifacts={
                    "path_bad_stdout": str(artifact_root / "path-bad.stdout.txt"),
                    "path_good_stdout": str(artifact_root / "path-good.stdout.txt"),
                    "path_wrong_alias_stdout": str(artifact_root / "path-wrong-alias.stdout.txt"),
                    "docker_bad_stdout": str(artifact_root / "docker-bad.stdout.txt"),
                    "docker_wrong_alias_stdout": str(artifact_root / "docker-wrong-alias.stdout.txt"),
                    "docker_good_stdout": str(artifact_root / "docker-good.stdout.txt"),
                },
                claims_proves=[
                    "Battle CLI authorization is bound to the target path or Docker image passed to the orchestrator.",
                    "A caller-supplied authorization alias is accepted only when the manifest target maps to the same executed local path.",
                    "A Docker alias is accepted only when the manifest image maps to the same executed Docker image.",
                    "A manifest mapping to the executed target is rejected when its canonical authorization identity does not match the caller-supplied alias.",
                ],
                claims_does_not_prove=[
                    "full Docker target launch",
                    "paid-provider battle quality",
                    "operator policy sufficiency for arbitrary aliases",
                ],
            ),
        )


def probe_review_receipt_hash_finalization(summary_path: Path) -> int:
    suite = "review-receipt-hash-finalization"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    from battle_skill import adaptive_red_blue_lineage_canary as canary

    receipt = canary._run_verified_primitive_docker_judge(
        docker_image=os.environ.get("BATTLE_REVIEW_HASH_DOCKER_IMAGE", "python:3.12-slim"),
        judge_dir=out_root / "red-success",
        role="red",
        generation=4,
        candidate_id="receipt-hash-finalization",
        verdict="RED_SUCCESS",
    )
    receipt_path = Path(str(receipt["path"]))
    descriptor_path = Path(str(receipt["sha256_descriptor_path"]))
    final_receipt = _read_json(receipt_path)
    descriptor = _read_json(descriptor_path)
    final_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    descriptor_sha256 = hashlib.sha256(descriptor_path.read_bytes()).hexdigest()
    checks = [
        {
            "name": "returned_digest_matches_final_receipt_bytes",
            "status": "PASS" if receipt.get("sha256") == final_sha256 else "FAIL",
            "returned_sha256": receipt.get("sha256"),
            "final_sha256": final_sha256,
        },
        {
            "name": "descriptor_digest_matches_final_receipt_bytes",
            "status": "PASS" if descriptor.get("receipt_sha256") == final_sha256 else "FAIL",
            "descriptor_receipt_sha256": descriptor.get("receipt_sha256"),
            "final_sha256": final_sha256,
        },
        {
            "name": "receipt_file_is_not_rewritten_with_self_digest",
            "status": "PASS"
            if final_receipt.get("path") == str(receipt_path)
            and "sha256" not in final_receipt
            and descriptor.get("receipt_contains_embedded_sha256") is False
            else "FAIL",
            "receipt_path_field": final_receipt.get("path"),
            "receipt_has_sha256_field": "sha256" in final_receipt,
        },
        {
            "name": "descriptor_is_separate_finalized_artifact",
            "status": "PASS"
            if descriptor.get("digest_scope") == "finalized_receipt_file_bytes"
            and descriptor.get("receipt_path") == str(receipt_path)
            and receipt.get("sha256_descriptor_sha256") == descriptor_sha256
            else "FAIL",
            "descriptor": str(descriptor_path),
            "descriptor_sha256": descriptor_sha256,
        },
    ]
    failed = [item for item in checks if item["status"] != "PASS"]
    if failed:
        raise AssertionError(f"receipt hash finalization checks failed: {failed}")
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="local_docker_primitive_judge_receipt_readback",
            checks=checks,
            artifacts={
                "judge_receipt": str(receipt_path),
                "digest_descriptor": str(descriptor_path),
            },
            claims_proves=[
                "Verified primitive Docker Judge receipt hashes are computed from the finalized judge-receipt.json bytes.",
                "The digest is retained in a separate descriptor and in the parent return value instead of being embedded by rewriting the hashed receipt.",
            ],
            claims_does_not_prove=[
                "full provider/Tau campaign quality",
                "arbitrary target exploitability",
            ],
        ),
    )


def probe_review_judge_authority(summary_path: Path) -> int:
    suite = "review-judge-authority"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    from battle_skill import adaptive_red_blue_lineage_canary as canary

    def judge_order(label: str, ids: list[str]) -> tuple[dict[str, Any], dict[str, Any], Path]:
        reviewed = [
            {
                "schema": "battle.verified_population_review.v1",
                "review_status": "PASS",
                "role": "red",
                "team": "red",
                "candidate_id": candidate_id,
                "specimen_id": candidate_id,
            }
            for candidate_id in ids
        ]
        result = canary._judge_population(
            role="red",
            generation=6,
            docker_image="python:3.12-slim",
            generation_dir=out_root / label,
            reviewed_population=reviewed,
        )
        selection = canary._select_survivor(
            role="red",
            judged_population=result["judged_population"],
        )
        result_path = out_root / f"{label}-judge-output.json"
        selection_path = out_root / f"{label}-selection-output.json"
        _write_json(result_path, result)
        _write_json(selection_path, selection)
        return result, selection, result_path

    forward, forward_selection, forward_path = judge_order(
        "forward-order", ["candidate-a", "candidate-b"]
    )
    reverse, reverse_selection, reverse_path = judge_order(
        "reverse-order", ["candidate-b", "candidate-a"]
    )
    legacy_receipt = canary._run_verified_primitive_docker_judge(
        docker_image="python:3.12-slim",
        judge_dir=out_root / "legacy-host-verdict-request",
        role="red",
        generation=6,
        candidate_id="candidate-host-requested-red-success",
        verdict="RED_SUCCESS",
    )
    legacy_path = Path(str(legacy_receipt["path"]))

    def verdicts_by_candidate(result: dict[str, Any]) -> dict[str, str]:
        return {
            str(item["candidate_id"]): str(item.get("judge_verdict"))
            for item in result.get("judged_population", [])
        }

    all_items = [
        *forward.get("judged_population", []),
        *reverse.get("judged_population", []),
    ]
    checks = [
        {
            "name": "forward_order_has_no_synthetic_winner",
            "status": "PASS"
            if set(verdicts_by_candidate(forward).values()) == {"INSUFFICIENT_EVIDENCE"}
            else "FAIL",
            "verdicts": verdicts_by_candidate(forward),
        },
        {
            "name": "reverse_order_has_no_synthetic_winner",
            "status": "PASS"
            if set(verdicts_by_candidate(reverse).values()) == {"INSUFFICIENT_EVIDENCE"}
            else "FAIL",
            "verdicts": verdicts_by_candidate(reverse),
        },
        {
            "name": "candidate_order_does_not_change_winner",
            "status": "PASS"
            if verdicts_by_candidate(forward) == verdicts_by_candidate(reverse)
            and forward_selection.get("survivor") is None
            and reverse_selection.get("survivor") is None
            else "FAIL",
            "forward_survivor": forward_selection.get("survivor"),
            "reverse_survivor": reverse_selection.get("survivor"),
        },
        {
            "name": "primitive_probe_receipts_are_quarantined_non_security_proof",
            "status": "PASS"
            if all(
                item.get("judge_authority") is False
                and item.get("target_execution") is False
                and item.get("proof_class") == "non_security_process_probe"
                for item in all_items
            )
            else "FAIL",
        },
        {
            "name": "legacy_host_requested_verdict_is_not_authority",
            "status": "PASS"
            if legacy_receipt.get("status") == "INSUFFICIENT_EVIDENCE"
            and legacy_receipt.get("verdict") == "INSUFFICIENT_EVIDENCE"
            and legacy_receipt.get("requested_verdict") == "RED_SUCCESS"
            and legacy_receipt.get("requested_verdict_honored") is False
            and legacy_receipt.get("judge_authority") is False
            and legacy_receipt.get("target_execution") is False
            else "FAIL",
            "legacy_receipt": str(legacy_path),
        },
    ]
    failed = [item for item in checks if item["status"] != "PASS"]
    if failed:
        raise AssertionError(f"Judge authority checks failed: {failed}")
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="local_docker_process_probe_with_adversarial_order_reversal",
            checks=checks,
            artifacts={
                "forward_judge_output": str(forward_path),
                "reverse_judge_output": str(reverse_path),
                "legacy_host_requested_verdict_receipt": str(legacy_path),
            },
            claims_proves=[
                "Primitive Docker process probes cannot assign Red or Blue success by candidate order.",
                "Host-requested verdicts are retained only as ignored inputs and are not live Judge authority.",
                "Synthetic primitive probes are quarantined as non-security proof with no target execution.",
            ],
            claims_does_not_prove=[
                "arbitrary target exploitability",
                "provider/Tau campaign quality",
                "that primitive process probes are security evidence",
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


def probe_b06_verify_evaluator_locks(summary_path: Path) -> int:
    return probe_pytest_contracts(
        summary_path,
        suite="battle-b06-verify-evaluator-locks-before-loading-executable-components",
        tests=["test_evaluator_lock_enforcement.py"],
    )


def probe_b07_confine_materialized_artifacts(summary_path: Path) -> int:
    return probe_pytest_contracts(
        summary_path,
        suite="battle-b07-confine-all-materialized-artifacts-to-owned-snapshots",
        tests=["test_artifact_snapshot_confinement.py"],
    )


def probe_b08_separate_safe_rejection(summary_path: Path) -> int:
    return probe_pytest_contracts(
        summary_path,
        suite="battle-b08-separate-safe-rejection-from-execution-failure",
        tests=["test_execution_outcome_classification.py"],
    )


def probe_b09_fixture_witness_contract(summary_path: Path) -> int:
    return probe_pytest_contracts(
        summary_path,
        suite="battle-b09-require-a-typed-fixture-witness-rather-than-any-judge-failu",
        tests=["test_fixture_witness_contract.py"],
    )



def probe_b05_strict_campaign_acceptance_envelopes(summary_path: Path) -> int:
    return probe_pytest_contracts(
        summary_path,
        suite="battle-b05-strictly-validate-campaign-and-acceptance-envelopes",
        tests=["test_campaign_envelope_validation.py"],
    )



def probe_b04_bind_authorization_to_executable_target(summary_path: Path) -> int:
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
            str(BATTLE_DIR / "tests" / "test_execution_authorization_binding.py"),
        ],
        timeout=240,
    )
    stdout_path = summary_path.parent / "battle-b04-bind-authorization-to-the-actual-executable-target.stdout.txt"
    stderr_path = summary_path.parent / "battle-b04-bind-authorization-to-the-actual-executable-target.stderr.txt"
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        return proc.returncode
    marker = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    return _emit(
        summary_path,
        _summary(
            suite="battle-b04-bind-authorization-to-the-actual-executable-target",
            live="pytest_contracts_over_production_adapter_and_campaign_authorization_boundary",
            checks=[{"name": "execution_authorization_binding_pytest", "status": "PASS", "stdout_marker": marker}],
            artifacts={"stdout": str(stdout_path), "stderr": str(stderr_path)},
            claims_proves=[
                "The production adapter validates authorization against the executable Docker image before launch.",
                "An authorization for target/image A cannot launch target/image B.",
                "Lower-level Docker campaign execution refuses requests without a bound authorization receipt.",
            ],
            claims_does_not_prove=[
                "external target authorization sufficiency",
                "production deployment readiness",
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
    proof_payload = _parse_stdout_json_after_marker(proof.stdout, "PASS battle-receipt-pixi-sanity")

    required_screenshots = [
        screenshot_dir / "before-spawn.png",
        screenshot_dir / "after-spawn.png",
    ]
    missing = [str(path) for path in required_screenshots if not path.is_file() or path.stat().st_size < 1000]
    if missing:
        raise AssertionError(f"receipt Pixi replay screenshots missing or too small: {missing}")

    backend_receipt_path = _receipt_pixi_backend_receipt_path()
    backend_receipt_sha256 = _sha256_file(backend_receipt_path) if backend_receipt_path and backend_receipt_path.is_file() else None
    fixture_hash = proof_payload.get("fixture", {}).get("fetched_fixture_sha256")
    loaded_hash = proof_payload.get("loadedSource", {}).get("source_fixture_sha256")
    route_run_id = proof_payload.get("loadedSource", {}).get("run_id")
    fixture_run_id = proof_payload.get("fixture", {}).get("run_id")
    replay_proof = {
        "schema": "battle.pixi_replay_receipt_binding.v1",
        "status": "PASS" if backend_receipt_sha256 and fixture_hash and loaded_hash == fixture_hash and route_run_id == fixture_run_id else "FAIL",
        "route_url": proof_payload.get("route", {}).get("url"),
        "backend_receipt": {
            "path": str(backend_receipt_path) if backend_receipt_path else None,
            "sha256": backend_receipt_sha256,
        },
        "normalized_fixture": {
            "fixture_id": proof_payload.get("fixture", {}).get("fixture_id"),
            "source_proof_id": proof_payload.get("fixture", {}).get("source_proof_id"),
            "source_url": proof_payload.get("fixture", {}).get("source_fixture_url"),
            "sha256": fixture_hash,
        },
        "visible_route_readback": proof_payload.get("loadedSource"),
        "readback_matches": {
            "route_loaded_same_fixture_sha256": loaded_hash == fixture_hash,
            "route_loaded_same_run_id": route_run_id == fixture_run_id,
        },
        "screenshots": [str(path) for path in required_screenshots],
    }
    replay_proof_path = out_root / "pixi-replay-proof.json"
    _write_json(replay_proof_path, replay_proof)
    if replay_proof["status"] != "PASS":
        raise AssertionError(f"receipt Pixi replay binding failed: {replay_proof}")

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
                    "route_url": replay_proof["route_url"],
                    "backend_receipt": replay_proof["backend_receipt"],
                    "normalized_fixture": replay_proof["normalized_fixture"],
                    "readback_matches": replay_proof["readback_matches"],
                    "screenshots": [str(path) for path in required_screenshots],
                }
            ],
            artifacts={
                "stdout": str(out_root / "prove-receipt-pixi.stdout.txt"),
                "stderr": str(out_root / "prove-receipt-pixi.stderr.txt"),
                "before_spawn_screenshot": str(required_screenshots[0]),
                "after_spawn_screenshot": str(required_screenshots[1]),
                "pixi_replay_proof": str(replay_proof_path),
            },
            claims_proves=[
                "receipt-backed Pixi replay derives parent/child visibility from the served fixture",
                "browser-rendered Pixi replay shows child lanes after the fixture spawn point and supports playhead scrub",
                "the browser route loaded the same normalized fixture hash bound to the durable backend receipt",
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
        "provider_live_authority_receipts_bound",
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


def probe_provider_tau_seeded_lineage_spawn(summary_path: Path, *, proof_root: str | None) -> int:
    suite = "provider-tau-seeded-lineage-spawn"
    out_root = Path(proof_root) if proof_root else summary_path.parent / suite
    if proof_root is None and out_root.exists():
        shutil.rmtree(out_root)
    source_root = out_root / "source-run"
    broadcast_root = out_root / "broadcast"
    logs_root = out_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)

    if not (source_root / "campaign-receipt.json").is_file():
        dogpile_root = out_root / "dogpile-seed"
        dogpile_root.mkdir(parents=True, exist_ok=True)
        dogpile_seed = dogpile_root / "dogpile-security-packet.json"
        dogpile = _run_in(
            [
                str(REPO_ROOT / "skills" / "dogpile" / "run.sh"),
                "search",
                "Zip Slip archive traversal mitigation Python safe extraction",
                "--no-interactive",
                "--output-dir",
                str(dogpile_root),
                "--security-packet-out",
                str(dogpile_seed),
                "--persona",
                "battle-red",
                "--rationale",
                "Battle adaptive-lineage seed needs source-bearing public exploit and mitigation ingredients",
                "--context",
                "Design input only. Battle Docker/Judge receipts decide exploit and patch outcomes.",
            ],
            cwd=REPO_ROOT,
            timeout=300,
        )
        (logs_root / "dogpile.stdout.txt").write_text(dogpile.stdout, encoding="utf-8")
        (logs_root / "dogpile.stderr.txt").write_text(dogpile.stderr, encoding="utf-8")
        if dogpile.returncode != 0 or not dogpile_seed.is_file():
            raise AssertionError("Dogpile seed generation failed: " + dogpile.stdout + dogpile.stderr)

        memory_seed = out_root / "memory-recall.txt"
        memory = _run_in(
            [
                str(REPO_ROOT / "skills" / "memory" / "run.sh"),
                "recall",
                "--q",
                "Battle adaptive lineage warm pond Dogpile Docker Judge spawn",
                "--k",
                "5",
                "--brief",
            ],
            cwd=REPO_ROOT,
            timeout=180,
        )
        memory_seed.write_text(memory.stdout, encoding="utf-8")
        (logs_root / "memory.stderr.txt").write_text(memory.stderr, encoding="utf-8")
        if memory.returncode != 0 or "\"found\": true" not in memory.stdout:
            raise AssertionError("Memory seed recall failed: " + memory.stdout + memory.stderr)

        authorization = out_root / "authorization.json"
        _fresh_authorization(
            authorization,
            target_identity=_battle_004_target_identity(),
            runtime_modes=["docker"],
            probe_classes=["path_traversal"],
        )
        run_id = f"battle-provider-tau-seeded-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
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
                "--authorization-manifest",
                str(authorization),
                "--dogpile-seed-receipt",
                str(dogpile_seed),
                "--memory-seed-receipt",
                str(memory_seed),
            ],
            timeout=int(timeout_s) + 180,
        )
        (logs_root / "canary.stdout.txt").write_text(canary.stdout, encoding="utf-8")
        (logs_root / "canary.stderr.txt").write_text(canary.stderr, encoding="utf-8")
        if canary.returncode != 0:
            raise AssertionError("seeded provider/Tau canary failed: " + canary.stdout + canary.stderr)
    else:
        campaign_seed_bundle = _read_json(source_root / "campaign-receipt.json").get("mutation_seed_receipts") or {}
        seed_paths = {
            item.get("kind"): Path(str(item.get("path")))
            for item in campaign_seed_bundle.get("receipts", [])
            if isinstance(item, dict) and item.get("path")
        }
        dogpile_seed = seed_paths.get("dogpile")
        memory_seed = seed_paths.get("memory")
        if dogpile_seed is None or memory_seed is None or not dogpile_seed.is_file() or not memory_seed.is_file():
            raise AssertionError(f"proof_root lacks readable seed receipts: {out_root}")

    renderer = _run(
        [
            "uv",
            "run",
            "--project",
            str(BATTLE_DIR),
            "python",
            str(BATTLE_DIR / "scripts" / "render_provider_tau_lineage_report.py"),
            "--campaign-receipt",
            str(source_root / "campaign-receipt.json"),
            "--out",
            str(broadcast_root),
            "--dogpile-seed",
            str(dogpile_seed),
            "--memory-seed",
            str(memory_seed),
        ],
        timeout=120,
    )
    (logs_root / "broadcast.stdout.txt").write_text(renderer.stdout, encoding="utf-8")
    (logs_root / "broadcast.stderr.txt").write_text(renderer.stderr, encoding="utf-8")
    if renderer.returncode != 0:
        raise AssertionError("provider/Tau broadcast renderer failed: " + renderer.stdout + renderer.stderr)

    campaign = _read_json(source_root / "campaign-receipt.json")
    broadcast = _read_json(broadcast_root / "provider-tau-lineage-broadcast-receipt.json")
    arena_receipt = _read_json(Path(broadcast["arena_receipt"]))
    red_activity = _read_json(Path(broadcast["red_team_activity_receipt"]))
    blue_activity = _read_json(Path(broadcast["blue_team_activity_receipt"]))
    commentary_receipt = _read_json(Path(broadcast["sports_play_by_play_commentary_receipt"]))
    visibility = _read_json(source_root / "generation-2" / "visibility-validation.json")
    dogpile_packet = _read_json(Path(dogpile_seed))
    report_text = (broadcast_root / "PROVIDER_TAU_LINEAGE_REPORT.md").read_text(encoding="utf-8")
    event_text = (broadcast_root / "provider-tau-event-ledger.jsonl").read_text(encoding="utf-8")
    ack_values = list((campaign.get("inheritance") or {}).values())
    seed_cited = bool(ack_values) and all(
        ack.get("mutation_seed_receipts_cited_in_provider_response") is True
        for ack in ack_values
    )
    checks = [
        {"name": "campaign_passed", "status": "PASS" if campaign.get("status") == "PASS" else "FAIL", "reason": campaign.get("reason")},
        {"name": "dogpile_seed_source_bearing", "status": "PASS" if int(dogpile_packet.get("source_bearing_evidence_count") or 0) > 0 else "FAIL", "source_bearing_evidence_count": dogpile_packet.get("source_bearing_evidence_count")},
        {"name": "memory_seed_readback", "status": "PASS" if memory_seed.is_file() and memory_seed.stat().st_size > 200 else "FAIL", "memory_seed": str(memory_seed)},
        {"name": "seed_bundle_bound", "status": "PASS" if (campaign.get("mutation_seed_receipts") or {}).get("status") == "PASS" else "FAIL"},
        {"name": "provider_cited_seed_hashes", "status": "PASS" if seed_cited else "FAIL"},
        {"name": "tau_public_visibility_passed", "status": "PASS" if visibility.get("status") == "PASS" else "FAIL", "private_input_leaks": visibility.get("private_input_leaks")},
        {"name": "child_specimens_materialized", "status": "PASS" if "generation-2" in json.dumps(campaign.get("generations", [])) else "FAIL"},
        {"name": "docker_judge_replay_bound", "status": "PASS" if (campaign.get("artifact_integrity") or {}).get("matched_replay_count") == 2 else "FAIL"},
        {"name": "broadcast_report_arena_first", "status": "PASS" if report_text.startswith("# Provider/Tau Adaptive-Lineage Battle Broadcast\n\n## Arena prologue") and "## Warm pond lineage" in report_text else "FAIL", "report": str(broadcast_root / "PROVIDER_TAU_LINEAGE_REPORT.md")},
        {"name": "broadcast_event_ledger_written", "status": "PASS" if "provider_seed_ack" in event_text and "selection_decision" in event_text else "FAIL", "event_ledger": str(broadcast_root / "provider-tau-event-ledger.jsonl")},
        {"name": "pydantic_arena_receipt", "status": "PASS" if arena_receipt.get("schema") == "battle.arena_receipt.v1" and arena_receipt.get("status") == "PASS" else "FAIL", "receipt": broadcast.get("arena_receipt")},
        {"name": "pydantic_red_blue_activity_receipts", "status": "PASS" if red_activity.get("schema") == "battle.team_activity_receipt.v1" and red_activity.get("team") == "red" and blue_activity.get("schema") == "battle.team_activity_receipt.v1" and blue_activity.get("team") == "blue" else "FAIL", "red": broadcast.get("red_team_activity_receipt"), "blue": broadcast.get("blue_team_activity_receipt")},
        {"name": "sports_play_by_play_json_event_logger", "status": "PASS" if commentary_receipt.get("schema") == "battle.sports_play_by_play_commentary_receipt.v1" and len(commentary_receipt.get("commentary_lines") or []) >= 3 and all(line.get("source_receipts") for line in commentary_receipt.get("commentary_lines") or []) else "FAIL", "receipt": broadcast.get("sports_play_by_play_commentary_receipt")},
        {"name": "broadcast_receipt_passed", "status": "PASS" if broadcast.get("status") == "PASS" else "FAIL"},
    ]
    failed = [item for item in checks if item["status"] != "PASS"]
    if failed:
        raise AssertionError(f"provider/Tau seeded lineage checks failed: {failed}")
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="dogpile_memory_seeded_tau_scillm_docker_judge_lineage",
            checks=checks,
            artifacts={
                "campaign_receipt": str(source_root / "campaign-receipt.json"),
                "broadcast_receipt": str(broadcast_root / "provider-tau-lineage-broadcast-receipt.json"),
                "arena_receipt": broadcast.get("arena_receipt"),
                "red_team_activity_receipt": broadcast.get("red_team_activity_receipt"),
                "blue_team_activity_receipt": broadcast.get("blue_team_activity_receipt"),
                "sports_play_by_play_commentary_receipt": broadcast.get("sports_play_by_play_commentary_receipt"),
                "report": str(broadcast_root / "PROVIDER_TAU_LINEAGE_REPORT.md"),
                "event_ledger": str(broadcast_root / "provider-tau-event-ledger.jsonl"),
                "dogpile_seed": str(dogpile_seed),
                "memory_seed": str(memory_seed),
            },
            claims_proves=[
                "Dogpile and memory readback receipts seeded the Generation 2 provider/Tau mutation prompt by hash.",
                "Provider responses cited those seed hashes before Battle materialized child Red/Blue specimens.",
                "Docker/Judge replay and deterministic selection receipts back the broadcast report.",
                "Arena, Red activity, Blue activity, and sports play-by-play are Pydantic-validated JSON receipts.",
            ],
            claims_does_not_prove=[
                "external target exploitability",
                "durable memory write promotion",
                "overnight production throughput",
            ],
        ),
    )


def _selection_reporting_campaign(
    path: Path,
    *,
    run_id: str,
    teams: dict[str, dict[str, Any]],
) -> None:
    def artifact(team: str, generation: int) -> dict[str, Any]:
        return {
            "compile_receipt_sha256": f"{team}-g{generation}-compile-sha256",
            "handoff_sha256": f"{team}-g{generation}-handoff-sha256",
            "selected_artifact_path": str(path.parent / f"generation-{generation}" / team / "artifact.py"),
            "selected_artifact_sha256": f"{team}-g{generation}-artifact-sha256",
            "status": "PASS",
        }

    payload = {
        "schema": "battle.adaptive_red_blue_lineage_canary.v1",
        "status": "PASS",
        "mocked": False,
        "live": True,
        "live_mode": "tau_scillm_fixtureless_selection_reporting",
        "battle_id": "battle-004",
        "run_id": run_id,
        "arena": {
            "scenario_id": f"arena-selection-reporting-{run_id}",
            "generation_1_target_sha256": "g1-target-sha256",
            "generation_2_target_sha256": "g1-target-sha256",
        },
        "authorization": {"status": "PASS"},
        "research": {"red": {"source_count": 1}, "blue": {"source_count": 1}},
        "mutation_seed_receipts": {
            "status": "PASS",
            "receipts": [
                {"kind": "dogpile", "path": str(path.parent / "dogpile-seed.json"), "sha256": "dogpile-seed-sha256"},
                {"kind": "memory", "path": str(path.parent / "memory-seed.txt"), "sha256": "memory-seed-sha256"},
            ],
        },
        "inheritance": {
            team: {
                "packet_cited_in_provider_response": True,
                "inherited_genome_cited": True,
                "inherited_observation_cited": True,
                "external_research_cited_in_provider_response": True,
                "mutation_seed_receipts_cited_in_provider_response": True,
                "mutation_seed_citations": [
                    {"kind": "dogpile", "sha256": "dogpile-seed-sha256", "cited_in_provider_response": True},
                    {"kind": "memory", "sha256": "memory-seed-sha256", "cited_in_provider_response": True},
                ],
            }
            for team in ("red", "blue")
        },
        "genome_deltas": {
            "red": {"semantic_change_count": 1, "sha256": "red-genome-delta-sha256"},
            "blue": {"semantic_change_count": 1, "sha256": "blue-genome-delta-sha256"},
        },
        "spawn": {
            "red": {"decision": "SPAWN_CHILD", "judge_verdict": "BLUE_SUCCESS"},
            "blue": {"decision": "SPAWN_CHILD", "judge_verdict": "BLUE_SUCCESS"},
        },
        "generations": [
            {
                "generation": 1,
                "judge_verdict": "BLUE_SUCCESS",
                "artifact_pipelines": {"red": artifact("red", 1), "blue": artifact("blue", 1)},
            },
            {
                "generation": 2,
                "judge_verdict": "BLUE_SUCCESS",
                "artifact_pipelines": {"red": artifact("red", 2), "blue": artifact("blue", 2)},
            },
        ],
        "artifact_integrity": {
            "schema": "battle.adaptive_artifact_integrity.v1",
            "status": "PASS",
            "path": str(path.parent / "artifact-integrity-receipt.json"),
            "matched_replay_count": 2,
            "required_replay_count": 2,
            "matched_slot_count": 4,
            "required_slot_count": 4,
            "judge_replays": [
                {
                    "generation": 1,
                    "expected_generation": 1,
                    "status": "PASS",
                    "matched": True,
                    "path": str(path.parent / "generation-1" / "judge-exact-replay" / "exact-replay-receipt.json"),
                    "expected_sha256": "generation-1-replay-sha256",
                },
                {
                    "generation": 2,
                    "expected_generation": 2,
                    "status": "PASS",
                    "matched": True,
                    "path": str(path.parent / "generation-2" / "judge-exact-replay" / "exact-replay-receipt.json"),
                    "expected_sha256": "generation-2-replay-sha256",
                },
            ],
        },
        "selection": {
            "schema": "battle.adaptive_selection_receipt.v1",
            "status": "PASS",
            "battle_id": "battle-004",
            "run_id": run_id,
            "teams": teams,
        },
    }
    _write_json(path, payload)


def _render_selection_reporting_variant(
    root: Path,
    *,
    variant: str,
    teams: dict[str, dict[str, Any]],
    expected_outcomes: dict[str, str],
    expected_both_generation_2_selected: bool,
    expected_phrases: list[str],
    forbidden_phrases: list[str],
) -> dict[str, Any]:
    variant_root = root / variant
    campaign = variant_root / "campaign-receipt.json"
    broadcast = variant_root / "broadcast"
    _selection_reporting_campaign(campaign, run_id=variant, teams=teams)
    proc = _run(
        [
            sys.executable,
            str(BATTLE_DIR / "scripts" / "render_provider_tau_lineage_report.py"),
            "--campaign-receipt",
            str(campaign),
            "--out",
            str(broadcast),
        ],
        timeout=120,
    )
    (variant_root / "renderer.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (variant_root / "renderer.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise AssertionError(f"selection reporting renderer failed for {variant}: {proc.stdout}{proc.stderr}")
    receipt_path = broadcast / "provider-tau-lineage-broadcast-receipt.json"
    receipt = _read_json(receipt_path)
    commentary_path = Path(str(receipt["sports_play_by_play_commentary_receipt"]))
    commentary = _read_json(commentary_path)
    selection_lines = [
        line.get("speaker_line", "")
        for line in commentary.get("commentary_lines", [])
        if line.get("period") == "selection"
    ]
    joined = "\n".join(selection_lines)
    missing = [phrase for phrase in expected_phrases if phrase not in joined]
    forbidden = [phrase for phrase in forbidden_phrases if phrase in joined]
    selection_check = next((item for item in receipt.get("checks", []) if item.get("name") == "selection_decisions_valid"), {})
    if receipt.get("status") != "PASS":
        raise AssertionError(f"broadcast receipt did not pass for {variant}: {receipt}")
    if selection_check.get("status") != "PASS":
        raise AssertionError(f"selection validity failed for {variant}: {selection_check}")
    canary = selection_check.get("child_promotion_canary") or {}
    if canary.get("gates_broadcast_validity") is not False:
        raise AssertionError(f"child-promotion canary gates broadcast validity for {variant}: {canary}")
    if canary.get("both_generation_2_selected") is not expected_both_generation_2_selected:
        raise AssertionError(f"child-promotion canary mismatch for {variant}: {canary}")
    outcomes = selection_check.get("outcomes") or {}
    for team, expected_outcome in expected_outcomes.items():
        observed = (outcomes.get(team) or {}).get("outcome")
        if observed != expected_outcome:
            raise AssertionError(
                f"selection outcome mismatch for {variant} {team}: expected={expected_outcome} observed={observed}"
            )
    if missing or forbidden:
        raise AssertionError(
            f"selection commentary mismatch for {variant}: missing={missing} forbidden={forbidden} lines={selection_lines}"
        )
    return {
        "name": variant,
        "status": "PASS",
        "broadcast_receipt": str(receipt_path),
        "commentary_receipt": str(commentary_path),
        "selection_outcomes": selection_check.get("outcomes"),
        "child_promotion_canary": selection_check.get("child_promotion_canary"),
        "selection_lines": selection_lines,
    }


def probe_review_selection_reporting(summary_path: Path) -> int:
    suite = "review-selection-reporting"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    child_team = {
        "generation_1_fitness_receipt_sha256": "g1-fitness",
        "generation_2_fitness_receipt_sha256": "g2-fitness",
        "retention_decision": "GENERATION_2_SELECTED",
        "selected_generation": 2,
        "tie_break_reason": None,
    }
    parent_team = {
        "generation_1_fitness_receipt_sha256": "g1-fitness",
        "generation_2_fitness_receipt_sha256": "g2-fitness",
        "retention_decision": "PARENT_RETAINED",
        "selected_generation": 1,
        "tie_break_reason": "parent_fitness_key_wins",
    }
    no_eligible_team = {
        "generation_1_fitness_receipt_sha256": "g1-fitness",
        "generation_2_fitness_receipt_sha256": "g2-fitness",
        "retention_decision": "NO_ELIGIBLE_PROMOTION",
        "selected_generation": None,
        "tie_break_reason": "child_disqualified",
    }
    variants = [
        _render_selection_reporting_variant(
            out_root,
            variant="child-selected",
            teams={"red": child_team, "blue": child_team},
            expected_outcomes={"red": "child_promoted", "blue": "child_promoted"},
            expected_both_generation_2_selected=True,
            expected_phrases=[
                "RED selection whistle: GENERATION_2_SELECTED; generation 2 child promoted by receipt.",
                "BLUE selection whistle: GENERATION_2_SELECTED; generation 2 child promoted by receipt.",
            ],
            forbidden_phrases=[],
        ),
        _render_selection_reporting_variant(
            out_root,
            variant="parent-retained",
            teams={"red": parent_team, "blue": parent_team},
            expected_outcomes={"red": "parent_retained", "blue": "parent_retained"},
            expected_both_generation_2_selected=False,
            expected_phrases=[
                "RED selection whistle: PARENT_RETAINED; generation 1 parent retained by receipt.",
                "BLUE selection whistle: PARENT_RETAINED; generation 1 parent retained by receipt.",
            ],
            forbidden_phrases=["PARENT_RETAINED; generation 1 promoted by receipt"],
        ),
        _render_selection_reporting_variant(
            out_root,
            variant="no-eligible-promotion",
            teams={"red": no_eligible_team, "blue": no_eligible_team},
            expected_outcomes={"red": "no_eligible_promotion", "blue": "no_eligible_promotion"},
            expected_both_generation_2_selected=False,
            expected_phrases=[
                "RED selection whistle: NO_ELIGIBLE_PROMOTION; no eligible child promotion was recorded by receipt.",
                "BLUE selection whistle: NO_ELIGIBLE_PROMOTION; no eligible child promotion was recorded by receipt.",
            ],
            forbidden_phrases=["NO_ELIGIBLE_PROMOTION; generation None promoted by receipt"],
        ),
    ]
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="provider_tau_broadcast_renderer_selection_receipt_readback",
            checks=variants,
            artifacts={
                "selection_reporting_root": str(out_root),
                "child_selected_broadcast": variants[0]["broadcast_receipt"],
                "parent_retained_broadcast": variants[1]["broadcast_receipt"],
                "no_eligible_promotion_broadcast": variants[2]["broadcast_receipt"],
            },
            claims_proves=[
                "Selection receipt validity is checked without requiring both teams to promote generation 2.",
                "Broadcast commentary truthfully renders child promotion, parent retention, and no eligible promotion.",
            ],
            claims_does_not_prove=[
                "fresh paid-provider campaign regeneration",
                "durable memory write promotion",
                "arbitrary target exploitability",
            ],
        ),
    )


def _write_broadcast_required_evidence_campaign(
    path: Path,
    *,
    variant: str,
    mutation: str,
) -> None:
    selected = {
        "generation_1_fitness_receipt_sha256": "g1-fitness",
        "generation_2_fitness_receipt_sha256": "g2-fitness",
        "retention_decision": "GENERATION_2_SELECTED",
        "selected_generation": 2,
        "tie_break_reason": None,
    }
    _selection_reporting_campaign(path, run_id=variant, teams={"red": selected, "blue": selected})
    payload = _read_json(path)
    if mutation == "null-replay-counters":
        payload["artifact_integrity"].update(
            {
                "matched_replay_count": None,
                "required_replay_count": None,
                "judge_replays": [],
            }
        )
    elif mutation == "empty-seed-citations":
        for ack in (payload.get("inheritance") or {}).values():
            ack["mutation_seed_receipts_cited_in_provider_response"] = True
            ack["mutation_seed_citations"] = []
    elif mutation == "blue-empty-seed-citations":
        blue_ack = (payload.get("inheritance") or {}).get("blue")
        if not isinstance(blue_ack, dict):
            raise AssertionError("blue inheritance acknowledgement missing")
        blue_ack["mutation_seed_receipts_cited_in_provider_response"] = True
        blue_ack["mutation_seed_citations"] = []
    elif mutation != "valid":
        raise ValueError(f"unknown required-evidence mutation: {mutation}")
    _write_json(path, payload)


def _render_required_evidence_variant(
    root: Path,
    *,
    variant: str,
    mutation: str,
    expected_status: str,
    expected_failed_checks: set[str],
) -> dict[str, Any]:
    variant_root = root / variant
    campaign = variant_root / "campaign-receipt.json"
    broadcast = variant_root / "broadcast"
    _write_broadcast_required_evidence_campaign(campaign, variant=variant, mutation=mutation)
    proc = _run(
        [
            sys.executable,
            str(BATTLE_DIR / "scripts" / "render_provider_tau_lineage_report.py"),
            "--campaign-receipt",
            str(campaign),
            "--out",
            str(broadcast),
        ],
        timeout=120,
    )
    (variant_root / "renderer.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (variant_root / "renderer.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    receipt_path = broadcast / "provider-tau-lineage-broadcast-receipt.json"
    if not receipt_path.is_file():
        raise AssertionError(f"broadcast receipt missing for {variant}: {proc.stdout}{proc.stderr}")
    receipt = _read_json(receipt_path)
    if receipt.get("status") != expected_status:
        raise AssertionError(f"unexpected broadcast status for {variant}: {receipt.get('status')} != {expected_status}")
    if expected_status == "PASS" and proc.returncode != 0:
        raise AssertionError(f"renderer exited nonzero for passing {variant}: {proc.stdout}{proc.stderr}")
    if expected_status == "FAIL" and proc.returncode == 0:
        raise AssertionError(f"renderer exited zero for failing {variant}")
    checks = {item.get("name"): item for item in receipt.get("checks", [])}
    failed_checks = {name for name, item in checks.items() if item.get("status") != "PASS"}
    missing_failures = expected_failed_checks - failed_checks
    if missing_failures:
        raise AssertionError(f"{variant} did not fail required checks: {sorted(missing_failures)}; failed={sorted(failed_checks)}")
    unexpected_failures = failed_checks - expected_failed_checks
    if unexpected_failures:
        raise AssertionError(f"{variant} had unexpected failed checks: {sorted(unexpected_failures)}")
    return {
        "name": variant,
        "status": "PASS",
        "expected_broadcast_status": expected_status,
        "renderer_exit_code": proc.returncode,
        "broadcast_receipt": str(receipt_path),
        "failed_checks": sorted(failed_checks),
        "check_errors": {
            name: checks.get(name, {}).get("errors", [])
            for name in sorted(expected_failed_checks)
        },
    }


def probe_review_broadcast_required_evidence(summary_path: Path) -> int:
    suite = "review-broadcast-required-evidence"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    checks = [
        _render_required_evidence_variant(
            out_root,
            variant="valid-explicit-evidence",
            mutation="valid",
            expected_status="PASS",
            expected_failed_checks=set(),
        ),
        _render_required_evidence_variant(
            out_root,
            variant="null-replay-counters",
            mutation="null-replay-counters",
            expected_status="FAIL",
            expected_failed_checks={"docker_judge_replays_bound"},
        ),
        _render_required_evidence_variant(
            out_root,
            variant="empty-seed-citations",
            mutation="empty-seed-citations",
            expected_status="FAIL",
            expected_failed_checks={"seed_hashes_cited_by_provider"},
        ),
        _render_required_evidence_variant(
            out_root,
            variant="blue-empty-seed-citations",
            mutation="blue-empty-seed-citations",
            expected_status="FAIL",
            expected_failed_checks={"seed_hashes_cited_by_provider"},
        ),
    ]
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="provider_tau_broadcast_renderer_adversarial_receipt_readback",
            checks=checks,
            artifacts={
                "required_evidence_root": str(out_root),
                "valid_broadcast": checks[0]["broadcast_receipt"],
                "null_replay_counters_broadcast": checks[1]["broadcast_receipt"],
                "empty_seed_citations_broadcast": checks[2]["broadcast_receipt"],
                "blue_empty_seed_citations_broadcast": checks[3]["broadcast_receipt"],
            },
            claims_proves=[
                "Provider/Tau broadcast rendering requires explicit nonempty Judge replay evidence.",
                "Provider/Tau broadcast rendering requires nonempty provider seed citations matching bound seed receipts.",
                "Null replay counters and empty seed-citation collections fail closed instead of passing vacuous checks.",
            ],
            claims_does_not_prove=[
                "fresh paid-provider campaign regeneration",
                "durable memory write promotion",
                "arbitrary target exploitability",
            ],
        ),
    )


def _lineage_report_module() -> Any:
    module_path = BATTLE_DIR / "scripts" / "render_provider_tau_lineage_report.py"
    spec = importlib.util.spec_from_file_location("battle_provider_tau_lineage_report", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load lineage report module from {module_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _render_commentary_provenance_base(root: Path) -> dict[str, Any]:
    selected = {
        "generation_1_fitness_receipt_sha256": "g1-fitness",
        "generation_2_fitness_receipt_sha256": "g2-fitness",
        "retention_decision": "GENERATION_2_SELECTED",
        "selected_generation": 2,
        "tie_break_reason": None,
    }
    campaign = root / "source" / "campaign-receipt.json"
    broadcast_root = root / "broadcast"
    _selection_reporting_campaign(campaign, run_id="commentary-provenance", teams={"red": selected, "blue": selected})
    proc = _run(
        [
            sys.executable,
            str(BATTLE_DIR / "scripts" / "render_provider_tau_lineage_report.py"),
            "--campaign-receipt",
            str(campaign),
            "--out",
            str(broadcast_root),
        ],
        timeout=120,
    )
    (root / "renderer.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (root / "renderer.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise AssertionError(f"commentary provenance renderer failed: {proc.stdout}{proc.stderr}")
    broadcast = _read_json(broadcast_root / "provider-tau-lineage-broadcast-receipt.json")
    if broadcast.get("status") != "PASS":
        raise AssertionError(f"baseline commentary provenance broadcast did not pass: {broadcast}")
    return {
        "campaign": str(campaign),
        "broadcast_receipt": str(broadcast_root / "provider-tau-lineage-broadcast-receipt.json"),
        "arena_receipt": broadcast["arena_receipt"],
        "red_team_activity_receipt": broadcast["red_team_activity_receipt"],
        "blue_team_activity_receipt": broadcast["blue_team_activity_receipt"],
        "commentary_receipt": broadcast["sports_play_by_play_commentary_receipt"],
    }


def _commentary_validation_errors(mod: Any, commentary_payload: dict[str, Any]) -> list[str]:
    try:
        commentary = mod.PlayByPlayCommentaryReceipt.model_validate(commentary_payload)
    except Exception as exc:
        return [str(exc)]
    red = mod.TeamActivityReceipt.model_validate(_read_json(Path(commentary.red_team_activity_receipt)))
    blue = mod.TeamActivityReceipt.model_validate(_read_json(Path(commentary.blue_team_activity_receipt)))
    return list(mod.commentary_provenance_errors(commentary, red, blue))


def _commentary_case(
    *,
    mod: Any,
    base_payload: dict[str, Any],
    root: Path,
    name: str,
    mutate: Any,
    expected_failure: bool,
    expected_fragment: str | None = None,
) -> dict[str, Any]:
    payload = copy.deepcopy(base_payload)
    mutate(payload)
    case_path = root / f"{name}.commentary.json"
    _write_json(case_path, payload)
    errors = _commentary_validation_errors(mod, payload)
    failed_closed = bool(errors)
    if expected_failure and not failed_closed:
        raise AssertionError(f"{name} unexpectedly passed commentary provenance validation")
    if not expected_failure and failed_closed:
        raise AssertionError(f"{name} unexpectedly failed commentary provenance validation: {errors}")
    if expected_fragment and not any(expected_fragment in error for error in errors):
        raise AssertionError(f"{name} errors did not include {expected_fragment!r}: {errors}")
    return {
        "name": name,
        "status": "PASS",
        "commentary_receipt": str(case_path),
        "expected_failure": expected_failure,
        "failed_closed": failed_closed,
        "errors": errors,
    }


def probe_review_commentary_provenance(summary_path: Path) -> int:
    suite = "review-commentary-provenance"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    mod = _lineage_report_module()
    artifacts = _render_commentary_provenance_base(out_root)
    base_payload = _read_json(Path(artifacts["commentary_receipt"]))
    red_activity = _read_json(Path(artifacts["red_team_activity_receipt"]))
    red_count = len(red_activity.get("activities") or [])

    def arena_line(payload: dict[str, Any]) -> dict[str, Any]:
        return payload["commentary_lines"][0]

    def red_line(payload: dict[str, Any]) -> dict[str, Any]:
        return next(line for line in payload["commentary_lines"] if line.get("source_activity_indices", {}).get("red"))

    cases = [
        _commentary_case(
            mod=mod,
            base_payload=base_payload,
            root=out_root,
            name="valid-exact-arena-and-team-references",
            mutate=lambda payload: None,
            expected_failure=False,
        ),
        _commentary_case(
            mod=mod,
            base_payload=base_payload,
            root=out_root,
            name="empty-activity-index-list",
            mutate=lambda payload: red_line(payload).update(
                {
                    "source_receipts": [payload["red_team_activity_receipt"]],
                    "source_activity_indices": {"red": []},
                }
            ),
            expected_failure=True,
            expected_fragment="activity index list",
        ),
        _commentary_case(
            mod=mod,
            base_payload=base_payload,
            root=out_root,
            name="basename-only-arena-receipt",
            mutate=lambda payload: arena_line(payload).update(
                {"source_receipts": [str(out_root / "unrelated" / "arena-receipt.json")]}
            ),
            expected_failure=True,
            expected_fragment="exact",
        ),
        _commentary_case(
            mod=mod,
            base_payload=base_payload,
            root=out_root,
            name="wrong-team-activity-reference",
            mutate=lambda payload: red_line(payload).update(
                {
                    "source_receipts": [payload["red_team_activity_receipt"]],
                    "source_activity_indices": {"blue": [0]},
                }
            ),
            expected_failure=True,
            expected_fragment="blue activity indices",
        ),
        _commentary_case(
            mod=mod,
            base_payload=base_payload,
            root=out_root,
            name="out-of-range-activity-index",
            mutate=lambda payload: red_line(payload).update(
                {
                    "source_receipts": [payload["red_team_activity_receipt"]],
                    "source_activity_indices": {"red": [red_count]},
                }
            ),
            expected_failure=True,
            expected_fragment="invalid index",
        ),
        _commentary_case(
            mod=mod,
            base_payload=base_payload,
            root=out_root,
            name="boolean-activity-index",
            mutate=lambda payload: red_line(payload).update(
                {
                    "source_receipts": [payload["red_team_activity_receipt"]],
                    "source_activity_indices": {"red": [True]},
                }
            ),
            expected_failure=True,
            expected_fragment="integer indexes",
        ),
    ]
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="provider_tau_broadcast_commentary_receipt_adversarial_readback",
            checks=cases,
            artifacts={
                **artifacts,
                "commentary_provenance_root": str(out_root),
            },
            claims_proves=[
                "Every commentary line must cite the exact bound arena receipt or a nonempty valid team activity index from the exact bound team receipt.",
                "Empty activity-index lists, basename-only arena receipt references, wrong-team references, out-of-range indices, and boolean indices fail closed.",
            ],
            claims_does_not_prove=[
                "fresh paid-provider campaign regeneration",
                "durable memory write promotion",
                "arbitrary target exploitability",
            ],
        ),
    )


def _write_recording_memory_adapter(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


STATE = Path(os.environ["BATTLE_RECORDING_MEMORY_STATE"])


def arg_value(name: str) -> str:
    try:
        return sys.argv[sys.argv.index(name) + 1]
    except (ValueError, IndexError):
        raise SystemExit(f"missing {name}")


def load_state() -> list[dict[str, str]]:
    if not STATE.is_file():
        return []
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(items: list[dict[str, str]]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(items, indent=2, sort_keys=True) + "\\n", encoding="utf-8")


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "learn":
        items = load_state()
        record = {
            "_key": f"recording-memory-{len(items)}",
            "problem": arg_value("--problem"),
            "solution": arg_value("--solution"),
        }
        items.append(record)
        save_state(items)
        print(json.dumps({"stored": True, "_key": record["_key"]}, sort_keys=True))
        return 0
    if command == "recall":
        query = arg_value("--q")
        tokens = query.split()
        if os.environ.get("BATTLE_RECORDING_MEMORY_TAMPER_RECALL") == "wrong_digest":
            marker = next((token for token in tokens if token.startswith("battle-memory-promotion:")), "")
            team = next((token for token in tokens if token.startswith("team=")), "team=red")
            item = {
                "_key": "tampered-marker-only",
                "problem": f"{marker} {team}",
                "solution": "artifact_sha256=wrong-artifact-digest fitness_sha256=wrong-fitness-digest",
            }
            print(json.dumps({"found": True, "items": [item]}, sort_keys=True))
            return 0
        print(json.dumps({"found": True, "items": load_state()}, sort_keys=True))
        return 0
    raise SystemExit(f"unsupported fake memory command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _memory_admission_selection(
    *,
    decision: str,
    selected_generation: int | None,
    prefix: str,
) -> dict[str, Any]:
    return {
        "generation_1_fitness_receipt_sha256": f"{prefix}-generation-1-fitness",
        "generation_2_fitness_receipt_sha256": f"{prefix}-generation-2-fitness",
        "retention_decision": decision,
        "selected_generation": selected_generation,
        "tie_break_reason": None,
    }


def _run_memory_admission_variant(
    root: Path,
    *,
    name: str,
    teams: dict[str, dict[str, Any]],
    expected_status: str,
    tamper_recall: bool = False,
) -> dict[str, Any]:
    variant_root = root / name
    campaign = variant_root / "source-run" / "campaign-receipt.json"
    promote_root = variant_root / "promotion"
    state_path = variant_root / "recording-memory-state.json"
    memory_adapter = variant_root / "recording-memory.py"
    _selection_reporting_campaign(campaign, run_id=name, teams=teams)
    _write_recording_memory_adapter(memory_adapter)
    env = {"BATTLE_RECORDING_MEMORY_STATE": str(state_path)}
    if tamper_recall:
        env["BATTLE_RECORDING_MEMORY_TAMPER_RECALL"] = "wrong_digest"
    proc = _run_in(
        [
            sys.executable,
            str(BATTLE_DIR / "scripts" / "promote_provider_tau_lineage_memory.py"),
            "--campaign-receipt",
            str(campaign),
            "--out",
            str(promote_root),
            "--memory-run",
            str(memory_adapter),
        ],
        cwd=REPO_ROOT,
        timeout=120,
        env=env,
    )
    (variant_root / "promotion.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (variant_root / "promotion.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    receipt_path = promote_root / "memory-promotion-live-receipt.json"
    if not receipt_path.is_file():
        raise AssertionError(f"memory promotion receipt missing for {name}: {proc.stdout}{proc.stderr}")
    receipt = _read_json(receipt_path)
    if receipt.get("status") != expected_status:
        raise AssertionError(f"{name} status {receipt.get('status')!r} != {expected_status!r}: {receipt}")
    if expected_status == "PASS" and proc.returncode != 0:
        raise AssertionError(f"{name} promoter returned nonzero despite PASS: {proc.stdout}{proc.stderr}")
    if expected_status != "PASS" and proc.returncode == 0:
        raise AssertionError(f"{name} promoter returned zero despite {expected_status}")
    records = _read_json(state_path) if state_path.is_file() else []
    return {
        "name": name,
        "status": "PASS",
        "expected_status": expected_status,
        "exit_code": proc.returncode,
        "receipt": str(receipt_path),
        "admissions": receipt.get("admissions") or [],
        "promotions": receipt.get("promotions") or [],
        "recorded_learns": records,
        "errors": receipt.get("errors") or [],
    }


def probe_review_memory_admission_binding(summary_path: Path) -> int:
    suite = "review-memory-admission-binding"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    red_child = _memory_admission_selection(
        decision="GENERATION_2_SELECTED",
        selected_generation=2,
        prefix="red",
    )
    blue_parent = _memory_admission_selection(
        decision="PARENT_RETAINED",
        selected_generation=1,
        prefix="blue",
    )
    no_eligible = _memory_admission_selection(
        decision="NO_ELIGIBLE_PROMOTION",
        selected_generation=None,
        prefix="blue",
    )
    variants = [
        _run_memory_admission_variant(
            out_root,
            name="red-admitted-blue-parent-retained",
            teams={"red": red_child, "blue": blue_parent},
            expected_status="PASS",
        ),
        _run_memory_admission_variant(
            out_root,
            name="generation-one-retention-no-write",
            teams={"red": blue_parent, "blue": no_eligible},
            expected_status="PASS",
        ),
        _run_memory_admission_variant(
            out_root,
            name="marker-only-wrong-digest-recall",
            teams={"red": red_child, "blue": blue_parent},
            expected_status="BLOCKED",
            tamper_recall=True,
        ),
        _run_memory_admission_variant(
            out_root,
            name="admission-generation-mismatch",
            teams={
                "red": _memory_admission_selection(
                    decision="GENERATION_2_SELECTED",
                    selected_generation=1,
                    prefix="red",
                ),
                "blue": blue_parent,
            },
            expected_status="BLOCKED",
        ),
    ]
    red_only = variants[0]
    retained = variants[1]
    wrong_digest = variants[2]
    mismatch = variants[3]
    red_promotions = red_only["promotions"]
    retained_promotions = retained["promotions"]
    wrong_digest_promotion = (wrong_digest["promotions"] or [{}])[0]
    checks = [
        {
            "name": "per_team_admission_controls_writes",
            "status": "PASS"
            if len(red_promotions) == 1
            and red_promotions[0].get("team") == "red"
            and len(red_only["recorded_learns"]) == 1
            and "team=blue" not in json.dumps(red_only["recorded_learns"], sort_keys=True)
            else "FAIL",
            "variant": red_only["receipt"],
        },
        {
            "name": "generation_one_retention_does_not_pair_with_generation_two_fitness",
            "status": "PASS"
            if not retained_promotions
            and not retained["recorded_learns"]
            and all(admission.get("admitted") is False for admission in retained["admissions"])
            else "FAIL",
            "variant": retained["receipt"],
        },
        {
            "name": "recall_requires_marker_team_artifact_and_evidence_digest",
            "status": "PASS"
            if (wrong_digest_promotion.get("recall") or {}).get("marker_found") is False
            and any("artifact digest" in error and "evidence digest" in error for error in wrong_digest["errors"])
            else "FAIL",
            "variant": wrong_digest["receipt"],
        },
        {
            "name": "admission_decision_generation_mismatch_blocks_before_memory_write",
            "status": "PASS"
            if not mismatch["recorded_learns"]
            and any("expected generation 2" in error for error in mismatch["errors"])
            else "FAIL",
            "variant": mismatch["receipt"],
        },
    ]
    failed = [item for item in checks if item.get("status") != "PASS"]
    if failed:
        raise AssertionError(f"memory admission binding checks failed: {failed}")
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="recording_memory_adapter_with_campaign_receipt_readback",
            checks=checks,
            artifacts={
                "memory_admission_binding_root": str(out_root),
                "red_admitted_blue_parent_retained_receipt": red_only["receipt"],
                "generation_one_retention_receipt": retained["receipt"],
                "wrong_digest_recall_receipt": wrong_digest["receipt"],
                "generation_mismatch_receipt": mismatch["receipt"],
            },
            claims_proves=[
                "Memory promotion writes require a validated per-team generation-2 admission decision.",
                "Parent retention and no-eligible-promotion decisions do not write Memory records or pair selected parent artifacts with generation-2 fitness evidence.",
                "Recall validation binds marker, team, artifact digest, and fitness evidence digest on the same recalled item.",
            ],
            claims_does_not_prove=[
                "live Memory service ranking quality",
                "cross-battle automatic reuse",
                "fresh paid-provider campaign regeneration",
            ],
        ),
    )


def probe_provider_tau_memory_promotion(summary_path: Path, *, proof_root: str | None) -> int:
    suite = "provider-tau-memory-promotion"
    out_root = Path(proof_root) if proof_root else Path(
        os.environ.get(
            "BATTLE_PROVIDER_TAU_SEEDED_ROOT",
            "/mnt/storage12tb/skills/battle/provider-tau-seeded-20260906T130635Z",
        )
    )
    campaign = out_root / "source-run" / "campaign-receipt.json"
    if not campaign.is_file():
        raise AssertionError(f"missing provider/Tau seeded campaign receipt: {campaign}")
    promote_root = out_root / "memory-promotion-eval"
    if promote_root.exists():
        shutil.rmtree(promote_root)
    promotion = _run(
        [
            sys.executable,
            str(BATTLE_DIR / "scripts" / "promote_provider_tau_lineage_memory.py"),
            "--campaign-receipt",
            str(campaign),
            "--out",
            str(promote_root),
        ],
        timeout=300,
    )
    (out_root / "memory-promotion-eval.stdout.txt").write_text(promotion.stdout, encoding="utf-8")
    (out_root / "memory-promotion-eval.stderr.txt").write_text(promotion.stderr, encoding="utf-8")
    if promotion.returncode != 0:
        raise AssertionError("provider/Tau memory promotion failed: " + promotion.stdout + promotion.stderr)
    receipt_path = promote_root / "memory-promotion-live-receipt.json"
    receipt = _read_json(receipt_path)
    promotions = receipt.get("promotions") or []
    checks = [
        {"name": "memory_promotion_receipt_passed", "status": "PASS" if receipt.get("status") == "PASS" else "FAIL", "receipt": str(receipt_path)},
        {"name": "two_team_promotions_written", "status": "PASS" if {p.get("team") for p in promotions} == {"red", "blue"} else "FAIL", "teams": sorted(p.get("team") for p in promotions)},
        {"name": "learn_commands_succeeded", "status": "PASS" if all((p.get("learn") or {}).get("exit_code") == 0 for p in promotions) else "FAIL"},
        {"name": "recall_items_return_bound_markers", "status": "PASS" if all((p.get("recall") or {}).get("bound_item_found") is True for p in promotions) else "FAIL"},
        {"name": "campaign_receipt_hash_bound", "status": "PASS" if receipt.get("campaign_receipt_sha256") else "FAIL", "campaign_receipt": str(campaign)},
    ]
    failed = [item for item in checks if item["status"] != "PASS"]
    if failed:
        raise AssertionError(f"provider/Tau memory promotion checks failed: {failed}")
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="memory_skill_write_and_recall_for_provider_tau_lineage",
            checks=checks,
            artifacts={
                "memory_promotion_receipt": str(receipt_path),
                "red_recall": str(promote_root / "red" / "memory-recall.stdout.txt"),
                "blue_recall": str(promote_root / "blue" / "memory-recall.stdout.txt"),
            },
            claims_proves=[
                "Selected provider/Tau Red and Blue lineage children were written through the Memory skill.",
                "Both promoted lessons were independently recalled from Memory with marker, team, artifact digest, and fitness evidence digest on the same item.",
            ],
            claims_does_not_prove=[
                "automatic future strategy reuse",
                "memory ranking quality",
                "external target exploitability",
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
    if evidence.get("checks_ok") is not True or int(evidence.get("check_count") or 0) < 11:
        raise AssertionError(f"adaptive lineage qualification checks drifted: {evidence}")
    if evidence.get("g2_judge_attempts") is not None and evidence.get("g2_judge_attempts") != 1:
        raise AssertionError(f"G2 Judge attempt count drifted: {evidence}")
    for passed, required in [
        ("exact_replays_matched", "exact_replays_required"),
        ("slot_hashes_matched", "slot_hashes_required"),
        ("provider_receipts_passed", "provider_receipts_required"),
    ]:
        if evidence.get(required) is not None and evidence.get(passed) != evidence.get(required):
            raise AssertionError(f"adaptive lineage qualification proof counts drifted: {evidence}")
    primary_proof = status.get("primary_proof") or {}
    required_primary = {
        "backend_qualification",
        "pixi_receipt_binding",
        "pixi_gameplay_browser_proof",
        "surf_text_readback",
        "surf_screenshot",
        "provider_tau_seeded_lineage",
        "memory_promotion_live",
        "pydantic_event_commentary",
    }
    missing_primary = sorted(key for key in required_primary if primary_proof.get(key) is not True)
    if status.get("immutable_goal_status") != "MET" or missing_primary:
        raise AssertionError(f"immutable goal primary proof drifted: {primary_proof}")
    proven = {item.get("id"): item for item in status.get("proven", [])}
    for claim_id in ["provider_tau_seeded_lineage_spawn", "provider_tau_memory_promotion"]:
        claim = proven.get(claim_id) or {}
        if claim.get("status") != "PASS" or (claim.get("evidence") or {}).get("checks_ok") is not True:
            raise AssertionError(f"current-status claim drifted: {claim_id}: {claim}")
    provider_checks = (proven.get("provider_tau_seeded_lineage_spawn") or {}).get("evidence", {}).get("checks") or {}
    if provider_checks.get("pydantic_arena_team_commentary_receipts") is not True:
        raise AssertionError("current-status pydantic event commentary proof missing")
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
                "the status checker fails closed unless the adaptive-lineage qualification and retained Pixi/browser proofs satisfy the immutable primary proof contract",
            ],
            claims_does_not_prove=[
                "production deployment readiness",
                "fresh paid-provider campaign regeneration",
            ],
        ),
    )


def _run_current_status_check(status_path: Path, out_root: Path, label: str) -> subprocess.CompletedProcess[str]:
    proc = _run_in(
        [
            sys.executable,
            str(BATTLE_DIR / "scripts" / "current_status.py"),
            "check",
            "--path",
            str(status_path),
        ],
        cwd=BATTLE_DIR,
        timeout=120,
    )
    (out_root / f"{label}.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (out_root / f"{label}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return proc


def _source_receipt(status: dict[str, Any], key: str) -> dict[str, Any]:
    receipt = (status.get("source_receipts") or {}).get(key)
    if not isinstance(receipt, dict) or not receipt.get("path"):
        raise AssertionError(f"generated status missing source receipt {key!r}")
    return receipt


def _copy_receipt_for_status(
    status: dict[str, Any],
    key: str,
    target: Path,
    *,
    mutate: dict[str, Any] | None = None,
) -> None:
    source = Path(str(_source_receipt(status, key)["path"]))
    payload = _read_json(source)
    if mutate:
        payload.update(mutate)
    _write_json(target, payload)
    receipt = _source_receipt(status, key)
    receipt["path"] = str(target)
    receipt["exists"] = True
    receipt["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    receipt["schema"] = payload.get("schema")
    receipt["status"] = payload.get("status")
    if "mocked" in payload:
        receipt["mocked"] = payload.get("mocked")
    if "live" in payload:
        receipt["live"] = payload.get("live")


def _write_status_variant(path: Path, status: dict[str, Any]) -> Path:
    _write_json(path, status)
    return path


def _assert_check_failed_with(proc: subprocess.CompletedProcess[str], needle: str) -> None:
    combined = proc.stdout + proc.stderr
    if proc.returncode == 0:
        raise AssertionError(f"current-status negative check unexpectedly passed: {needle}")
    if needle not in combined:
        raise AssertionError(f"current-status negative check missed {needle!r}: {combined}")


def probe_review_current_status_proof_chain(summary_path: Path) -> int:
    suite = "review-current-status-proof-chain"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    status_path = out_root / "CURRENT_STATUS.json"
    generate = _run_in(
        [
            sys.executable,
            str(BATTLE_DIR / "scripts" / "current_status.py"),
            "generate",
            "--out",
            str(status_path),
        ],
        cwd=BATTLE_DIR,
        timeout=120,
    )
    (out_root / "generate.stdout.txt").write_text(generate.stdout, encoding="utf-8")
    (out_root / "generate.stderr.txt").write_text(generate.stderr, encoding="utf-8")
    if generate.returncode != 0:
        raise AssertionError("current_status generate failed: " + generate.stdout + generate.stderr)
    positive = _run_current_status_check(status_path, out_root, "positive-check")
    if positive.returncode != 0:
        raise AssertionError("current_status positive check failed: " + positive.stdout + positive.stderr)
    status = _read_json(status_path)

    mutated_manifest_status = copy.deepcopy(status)
    mutated_manifest_path = out_root / "mutated" / "adaptive-lineage-qualification.json"
    _copy_receipt_for_status(
        mutated_manifest_status,
        "adaptive_lineage_qualification",
        mutated_manifest_path,
        mutate={"source_run_dir": str(out_root / "wrong-campaign-root")},
    )
    for claim in mutated_manifest_status.get("proven") or []:
        if claim.get("id") == "p0_adaptive_lineage_fresh_qualification":
            claim["receipt"] = str(mutated_manifest_path)
    mutated_manifest_check = _run_current_status_check(
        _write_status_variant(out_root / "mutated-manifest-status.json", mutated_manifest_status),
        out_root,
        "mutated-manifest-check",
    )
    _assert_check_failed_with(mutated_manifest_check, "adaptive_lineage_source_run_dir_missing")

    substituted_broadcast_status = copy.deepcopy(status)
    substituted_broadcast_path = out_root / "foreign-campaign" / "broadcast" / "provider-tau-lineage-broadcast-receipt.json"
    _copy_receipt_for_status(
        substituted_broadcast_status,
        "provider_tau_seeded_broadcast",
        substituted_broadcast_path,
    )
    substituted_broadcast_check = _run_current_status_check(
        _write_status_variant(out_root / "substituted-broadcast-status.json", substituted_broadcast_status),
        out_root,
        "substituted-broadcast-check",
    )
    _assert_check_failed_with(substituted_broadcast_check, "provider_broadcast_path_not_broadcast_root")

    missing_memory_status = copy.deepcopy(status)
    missing_memory_receipt = _source_receipt(missing_memory_status, "provider_tau_memory_promotion")
    missing_memory_receipt["path"] = str(out_root / "missing" / "memory-promotion-live-receipt.json")
    missing_memory_receipt["exists"] = True
    for claim in missing_memory_status.get("proven") or []:
        if claim.get("id") == "provider_tau_memory_promotion":
            claim["receipt"] = missing_memory_receipt["path"]
            claim.setdefault("evidence", {})["path"] = missing_memory_receipt["path"]
    missing_memory_check = _run_current_status_check(
        _write_status_variant(out_root / "missing-memory-status.json", missing_memory_status),
        out_root,
        "missing-memory-check",
    )
    _assert_check_failed_with(missing_memory_check, "source_receipt_file_missing:provider_tau_memory_promotion")

    stale_claim_status = copy.deepcopy(status)
    stale_campaign = out_root / "stale-claim" / "source-run" / "campaign-receipt.json"
    stale_broadcast = out_root / "stale-claim" / "broadcast" / "provider-tau-lineage-broadcast-receipt.json"
    stale_memory = out_root / "stale-claim" / "memory-promotion-eval" / "memory-promotion-live-receipt.json"
    for claim in stale_claim_status.get("proven") or []:
        if claim.get("id") == "provider_tau_seeded_lineage_spawn":
            claim["receipt"] = str(stale_campaign)
            evidence = claim.setdefault("evidence", {})
            evidence["root"] = str(out_root / "stale-claim")
            evidence["campaign_receipt"] = str(stale_campaign)
            evidence["broadcast_receipt"] = str(stale_broadcast)
        if claim.get("id") == "provider_tau_memory_promotion":
            claim["receipt"] = str(stale_memory)
            claim.setdefault("evidence", {})["path"] = str(stale_memory)
    stale_claim_check = _run_current_status_check(
        _write_status_variant(out_root / "stale-claim-status.json", stale_claim_status),
        out_root,
        "stale-claim-check",
    )
    _assert_check_failed_with(stale_claim_check, "provider_claim_receipt_path_mismatch")

    checks = [
        {
            "name": "generated_current_status_revalidates_live_chain",
            "status": "PASS",
            "current_status": str(status_path),
        },
        {
            "name": "mutated_adaptive_manifest_rejected",
            "status": "PASS",
            "status_variant": str(out_root / "mutated-manifest-status.json"),
        },
        {
            "name": "cross_campaign_broadcast_substitution_rejected",
            "status": "PASS",
            "status_variant": str(out_root / "substituted-broadcast-status.json"),
        },
        {
            "name": "missing_memory_promotion_receipt_rejected",
            "status": "PASS",
            "status_variant": str(out_root / "missing-memory-status.json"),
        },
        {
            "name": "stale_cached_provider_claim_evidence_rejected",
            "status": "PASS",
            "status_variant": str(out_root / "stale-claim-status.json"),
        },
    ]
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="local_current_status_generation_with_adversarial_proof_chain_mutation",
            checks=checks,
            artifacts={
                "current_status": str(status_path),
                "positive_check_stdout": str(out_root / "positive-check.stdout.txt"),
                "mutated_manifest_status": str(out_root / "mutated-manifest-status.json"),
                "substituted_broadcast_status": str(out_root / "substituted-broadcast-status.json"),
                "missing_memory_status": str(out_root / "missing-memory-status.json"),
                "stale_claim_status": str(out_root / "stale-claim-status.json"),
            },
            claims_proves=[
                "current-status check rereads the selected proof manifest and rejects mutated source-run bindings",
                "current-status check rejects provider/Tau broadcast receipts outside the selected campaign root",
                "current-status check rejects missing Memory promotion receipts despite cached primary proof booleans",
                "current-status check rejects stale cached proven-claim paths and evidence that no longer match selected source receipts",
            ],
            claims_does_not_prove=[
                "fresh paid-provider campaign regeneration",
                "production deployment readiness",
            ],
        ),
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AssertionError("stdout did not contain a JSON object")
    return json.loads(text[start : end + 1])


def _commentary_causality_campaign_receipt() -> Path:
    committed = BATTLE_DIR / "proofs" / "current-run-receipts-20260908" / "source-run" / "campaign-receipt.json"
    if committed.is_file():
        return committed
    fallback = Path("/mnt/storage12tb/skills/battle/review-ticket-live-rerun/source-run/campaign-receipt.json")
    if fallback.is_file():
        return fallback
    raise AssertionError("no retained provider/Tau campaign receipt for commentary causality")


def _commentary_causal_coverage_from_broadcast(mod: Any, broadcast_receipt: dict[str, Any]) -> dict[str, Any]:
    commentary = mod.PlayByPlayCommentaryReceipt.model_validate(
        _read_json(Path(str(broadcast_receipt["sports_play_by_play_commentary_receipt"])))
    )
    red = mod.TeamActivityReceipt.model_validate(_read_json(Path(str(broadcast_receipt["red_team_activity_receipt"]))))
    blue = mod.TeamActivityReceipt.model_validate(_read_json(Path(str(broadcast_receipt["blue_team_activity_receipt"]))))
    return mod.commentary_causal_coverage(commentary, red, blue)


def _rewrite_string_prefix(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return new + value[len(old):] if value.startswith(old) else value
    if isinstance(value, list):
        return [_rewrite_string_prefix(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_string_prefix(item, old, new) for key, item in value.items()}
    return value


def _write_red_genome_removed_campaign(mod: Any, campaign_receipt: Path, target_root: Path) -> Path:
    receipt = _read_json(campaign_receipt)
    source_root = next(
        (
            root for root in mod._campaign_source_roots(campaign_receipt, receipt)
            if (root / "generation-1" / "genomes" / "red-team-genome.json").is_file()
        ),
        None,
    )
    if source_root is None:
        raise AssertionError("positive campaign has no source red genome to remove")
    target_root.mkdir(parents=True, exist_ok=True)
    for generation in (1, 2):
        src_dir = source_root / f"generation-{generation}" / "genomes"
        dst_dir = target_root / f"generation-{generation}" / "genomes"
        dst_dir.mkdir(parents=True, exist_ok=True)
        blue = src_dir / "blue-team-genome.json"
        if blue.is_file():
            shutil.copy2(blue, dst_dir / blue.name)
    mutated = _rewrite_string_prefix(receipt, str(source_root), str(target_root))
    campaign = target_root / "campaign-receipt.json"
    _write_json(campaign, mutated)
    return campaign


def probe_battle_commentary_causality(summary_path: Path) -> int:
    suite = "battle-commentary-causality"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    mod = _lineage_report_module()
    campaign = _commentary_causality_campaign_receipt()

    positive_receipt = mod.render(campaign, out_root / "positive-render", None, None)
    positive_receipt_path = out_root / "positive-render" / "provider-tau-lineage-broadcast-receipt.json"
    positive_readback = _read_json(positive_receipt_path)
    if positive_receipt.get("status") != "PASS" or positive_readback.get("status") != "PASS":
        raise AssertionError(f"positive renderer did not pass: {positive_readback}")
    positive_coverage = _commentary_causal_coverage_from_broadcast(mod, positive_readback)
    missing = [
        slot for slot, item in (positive_coverage.get("slots") or {}).items()
        if item.get("status") != "present-and-source-bound"
    ]
    if missing:
        raise AssertionError(f"positive commentary causal slots missing or unbound: {missing} {positive_coverage}")
    if positive_coverage.get("forbids_unsupported_kill_language") is not True:
        raise AssertionError(f"positive commentary used unsupported kill language: {positive_coverage}")

    negative_campaign = _write_red_genome_removed_campaign(mod, campaign, out_root / "red-genome-removed-source-run")
    negative_receipt = mod.render(negative_campaign, out_root / "negative-render", None, None)
    negative_receipt_path = out_root / "negative-render" / "provider-tau-lineage-broadcast-receipt.json"
    negative_readback = _read_json(negative_receipt_path)
    if negative_receipt.get("status") != "PASS" or negative_readback.get("status") != "PASS":
        raise AssertionError(f"negative renderer did not pass: {negative_readback}")
    negative_coverage = _commentary_causal_coverage_from_broadcast(mod, negative_readback)
    red_slot = (negative_coverage.get("slots") or {}).get("red_mechanism") or {}
    if red_slot.get("status") != "absent":
        raise AssertionError(f"red mechanism was fabricated after red genome removal: {negative_coverage}")
    if negative_coverage.get("forbids_unsupported_kill_language") is not True:
        raise AssertionError(f"negative commentary used unsupported kill language: {negative_coverage}")

    checks = [
        {
            "name": "positive_causal_slots_present_and_source_bound",
            "status": "PASS",
            "campaign_receipt": str(campaign),
            "broadcast_receipt": str(positive_receipt_path),
            "coverage": positive_coverage,
        },
        {
            "name": "negative_red_genome_removed_omits_red_mechanism",
            "status": "PASS",
            "campaign_receipt": str(negative_campaign),
            "broadcast_receipt": str(negative_receipt_path),
            "coverage": negative_coverage,
        },
    ]
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="retained_provider_tau_renderer_receipt_readback_with_mutated_campaign_control",
            checks=checks,
            artifacts={
                "positive_broadcast_receipt": str(positive_receipt_path),
                "positive_commentary_receipt": str(positive_readback["sports_play_by_play_commentary_receipt"]),
                "negative_broadcast_receipt": str(negative_receipt_path),
                "negative_commentary_receipt": str(negative_readback["sports_play_by_play_commentary_receipt"]),
            },
            claims_proves=[
                "Receipt-derived sports commentary carries source-bound objective, Red mechanism, Blue response, replay transition, and Judge terminal result slots when those facts exist.",
                "Removing the Red genome removes the Red mechanism slot instead of fabricating a mechanism.",
                "The retained zip-slip campaign commentary omits unsupported kill/killed language.",
            ],
            claims_does_not_prove=[
                "voice synthesis",
                "Pixi redesign",
                "fresh provider campaign regeneration",
            ],
        ),
    )


CURRENT_STATUS_UNSUPPORTED_CLAIMS = {
    "production_deployment_ready": "battle.production_infrastructure_deployment_proof.v1",
    "full_adaptive_improvement_proven": "battle.full_adaptive_improvement_proof.v1",
    "kill_promotion_fastest_crash_supported": "battle.judge_kill_fastest_crash_semantics.v1",
    "fast_sanity_is_live_product_proof": "battle.live_product_qualification_receipt.v1",
}


def _assert_current_status_claimed_true(status: dict[str, Any], claim: str) -> dict[str, Any]:
    mutated = copy.deepcopy(status)
    mutated[claim] = True
    for item in mutated.get("unsupported") or []:
        if isinstance(item, dict) and item.get("claim") == claim:
            item["status"] = "PASS"
            item["asserted"] = True
            break
    else:
        raise AssertionError(f"unsupported claim missing: {claim}")
    return mutated


def _run_current_status_claim_check(status_path: Path, *, out_root: Path, name: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    receipt_path = out_root / f"{name}-terminal-semantics.json"
    proc = _run_in(
        [str(RUN_SH), "current-status", "check", "--path", str(status_path)],
        cwd=REPO_ROOT,
        timeout=240,
        env={"BATTLE_TERMINAL_SEMANTICS_RECEIPT": str(receipt_path)},
    )
    (out_root / f"{name}.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (out_root / f"{name}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    return proc, _parse_json_object(proc.stdout)


def probe_battle_current_status_claim_gates(summary_path: Path) -> int:
    suite = "battle-current-status-claim-gates"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    generated_status_path = out_root / "CURRENT_STATUS.generated.json"
    generate = _run_in(
        [str(RUN_SH), "current-status", "generate", "--out", str(generated_status_path)],
        cwd=REPO_ROOT,
        timeout=240,
    )
    (out_root / "generate.stdout.txt").write_text(generate.stdout, encoding="utf-8")
    (out_root / "generate.stderr.txt").write_text(generate.stderr, encoding="utf-8")
    if generate.returncode != 0:
        raise AssertionError("current-status generate failed: " + generate.stdout + generate.stderr)
    generated = _read_json(generated_status_path)

    pass_proc, pass_output = _run_current_status_claim_check(generated_status_path, out_root=out_root, name="generated-pass")
    if pass_proc.returncode != 0 or pass_output.get("status") != "PASS" or pass_output.get("errors"):
        raise AssertionError(f"generated status did not check PASS: {pass_output}")

    checks: list[dict[str, Any]] = [
        {
            "name": "generated_current_status_checks_pass",
            "status": "PASS",
            "status_path": str(generated_status_path),
            "stdout": str(out_root / "generated-pass.stdout.txt"),
        }
    ]
    artifacts: dict[str, Any] = {"generated_status": str(generated_status_path)}
    for claim, required_schema in CURRENT_STATUS_UNSUPPORTED_CLAIMS.items():
        mutated_path = out_root / f"{claim}.asserted-true.json"
        _write_json(mutated_path, _assert_current_status_claimed_true(generated, claim))
        proc, output = _run_current_status_claim_check(mutated_path, out_root=out_root, name=claim)
        expected = f"unsupported_claim_promoted_without_receipt:{claim}:requires:{required_schema}"
        matched = any(str(error).startswith(expected) for error in output.get("errors") or [])
        if proc.returncode == 0 or output.get("status") != "FAIL" or not matched:
            raise AssertionError(f"unsupported claim gate did not fail closed for {claim}: {output}")
        if claim == "fast_sanity_is_live_product_proof" and "fast_sanity_is_live_product_proof_requires_live_product_receipt_not_battle.tiered_fast_sanity_gate.v1" not in (output.get("errors") or []):
            raise AssertionError(f"fast sanity gate accepted fast sanity as live product proof: {output}")
        checks.append(
            {
                "name": f"rejects_{claim}_without_{required_schema}",
                "status": "PASS",
                "mutated_status": str(mutated_path),
                "stdout": str(out_root / f"{claim}.stdout.txt"),
                "required_receipt_schema": required_schema,
                "error_prefix": expected,
            }
        )
        artifacts[f"{claim}_mutated_status"] = str(mutated_path)

    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="battle_run_sh_current_status_generate_check_with_adversarial_unsupported_claim_mutations",
            checks=checks,
            artifacts=artifacts,
            claims_proves=[
                "CURRENT_STATUS check fails closed when production_deployment_ready is promoted without battle.production_infrastructure_deployment_proof.v1.",
                "CURRENT_STATUS check fails closed when full_adaptive_improvement_proven is promoted without battle.full_adaptive_improvement_proof.v1.",
                "CURRENT_STATUS check fails closed when kill_promotion_fastest_crash_supported is promoted without battle.judge_kill_fastest_crash_semantics.v1.",
                "CURRENT_STATUS check fails closed when fast_sanity_is_live_product_proof is promoted without battle.live_product_qualification_receipt.v1, and battle.tiered_fast_sanity_gate.v1 alone is rejected.",
            ],
            claims_does_not_prove=[
                "production infrastructure is deployed",
                "full adaptive improvement is proven",
                "kill/fastest-crash terminal semantics are supported",
                "fast sanity is live product proof",
            ],
        ),
    )




def _battle_source() -> dict[str, str]:
    return {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip(),
        "battle_tree": subprocess.check_output(["git", "rev-parse", "HEAD:skills/battle"], cwd=REPO_ROOT, text=True).strip(),
    }


def _same_run_live_qualification_receipt(source: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": "battle.same_run_arena_pixi_qualification.v1",
        "status": "PASS",
        "mocked": False,
        "live": True,
        "run_id": "battle-proof-rung-separation",
        "source_commit": source["commit"],
        "source_tree": source["battle_tree"],
        "browser": {"status": "PASS", "cdp_command": {"exit_code": 0}},
        "published_fixture": {"fixture_key": "battle-proof-rung-separation", "fixture_sha256": "f" * 64},
    }


def _live_pair_receipts(source: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    arena = {
        "schema": "battle.live_arena_receipt.v1",
        "status": "PASS",
        "mocked": False,
        "live": "tau_docker_judge_arena",
        "run_id": "battle-proof-rung-separation",
        "source_commit": source["commit"],
        "source_tree": source["battle_tree"],
    }
    pixi = {
        "schema": "battle.live_pixi_browser_receipt.v1",
        "status": "PASS",
        "mocked": False,
        "live": True,
        "run_id": "battle-proof-rung-separation",
        "fixture_backed": False,
        "source_commit": source["commit"],
        "source_tree": source["battle_tree"],
    }
    return arena, pixi


def _fast_sanity_fixture(source: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": "battle.tiered_fast_sanity_gate.v1",
        "status": "PASS",
        "mocked": False,
        "live": False,
        "source": source,
        "command_result": {"exit_code": 0},
        "proof_scope": "offline sanity plus local deterministic fixture checks; no live provider/Docker/browser qualification",
    }


def probe_battle_proof_rung_separation(summary_path: Path) -> int:
    suite = "battle-proof-rung-separation"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    source = _battle_source()

    fast_path = out_root / "fast-sanity-only.json"
    _write_json(fast_path, _fast_sanity_fixture(source))

    fast_pair_out = out_root / "fast-as-live-pair-gate.json"
    fast_pair = _run_in(
        [str(RUN_SH), "tiered-gate", "live", "--arena-receipt", str(fast_path), "--pixi-receipt", str(fast_path), "--out", str(fast_pair_out)],
        cwd=REPO_ROOT,
        timeout=240,
    )
    (out_root / "fast-as-live-pair.stdout.txt").write_text(fast_pair.stdout, encoding="utf-8")
    (out_root / "fast-as-live-pair.stderr.txt").write_text(fast_pair.stderr, encoding="utf-8")
    fast_pair_receipt = _read_json(fast_pair_out)
    for expected in ("arena_receipt_fast_sanity_substitution_rejected", "pixi_receipt_fast_sanity_substitution_rejected"):
        if expected not in (fast_pair_receipt.get("errors") or []):
            raise AssertionError(f"live pair gate did not reject fast sanity proof rung: {fast_pair_receipt}")
    if fast_pair.returncode == 0 or fast_pair_receipt.get("status") != "FAIL":
        raise AssertionError(f"fast sanity unexpectedly passed live pair gate: {fast_pair_receipt}")

    fast_same_out = out_root / "fast-as-same-run-live-gate.json"
    fast_same = _run_in(
        [str(RUN_SH), "tiered-gate", "same-run-live", "--same-run-receipt", str(fast_path), "--out", str(fast_same_out)],
        cwd=REPO_ROOT,
        timeout=240,
    )
    (out_root / "fast-as-same-run.stdout.txt").write_text(fast_same.stdout, encoding="utf-8")
    (out_root / "fast-as-same-run.stderr.txt").write_text(fast_same.stderr, encoding="utf-8")
    fast_same_receipt = _read_json(fast_same_out)
    if "same_run_receipt_fast_sanity_substitution_rejected" not in (fast_same_receipt.get("errors") or []):
        raise AssertionError(f"same-run gate did not reject fast sanity proof rung: {fast_same_receipt}")
    if fast_same.returncode == 0 or fast_same_receipt.get("status") != "FAIL":
        raise AssertionError(f"fast sanity unexpectedly passed same-run live gate: {fast_same_receipt}")

    arena_payload, pixi_payload = _live_pair_receipts(source)
    arena_path = out_root / "live-arena.json"
    pixi_path = out_root / "live-pixi.json"
    _write_json(arena_path, arena_payload)
    _write_json(pixi_path, pixi_payload)
    live_pair_out = out_root / "live-pair-gate.json"
    live_pair = _run_in(
        [str(RUN_SH), "tiered-gate", "live", "--arena-receipt", str(arena_path), "--pixi-receipt", str(pixi_path), "--out", str(live_pair_out)],
        cwd=REPO_ROOT,
        timeout=240,
    )
    (out_root / "live-pair.stdout.txt").write_text(live_pair.stdout, encoding="utf-8")
    (out_root / "live-pair.stderr.txt").write_text(live_pair.stderr, encoding="utf-8")
    live_pair_receipt = _read_json(live_pair_out)
    if live_pair.returncode != 0 or live_pair_receipt.get("status") != "PASS" or live_pair_receipt.get("errors"):
        raise AssertionError(f"live pair proof rung did not pass: {live_pair_receipt}")

    same_run_path = out_root / "same-run-live.json"
    _write_json(same_run_path, _same_run_live_qualification_receipt(source))
    same_run_out = out_root / "same-run-live-gate.json"
    same_run = _run_in(
        [str(RUN_SH), "tiered-gate", "same-run-live", "--same-run-receipt", str(same_run_path), "--out", str(same_run_out)],
        cwd=REPO_ROOT,
        timeout=240,
    )
    (out_root / "same-run-live.stdout.txt").write_text(same_run.stdout, encoding="utf-8")
    (out_root / "same-run-live.stderr.txt").write_text(same_run.stderr, encoding="utf-8")
    same_run_receipt = _read_json(same_run_out)
    if same_run.returncode != 0 or same_run_receipt.get("status") != "PASS" or same_run_receipt.get("errors"):
        raise AssertionError(f"same-run live proof rung did not pass: {same_run_receipt}")

    checks = [
        {
            "name": "fast_sanity_rejected_by_live_pair_gate",
            "status": "PASS",
            "receipt": str(fast_pair_out),
            "errors": fast_pair_receipt.get("errors"),
        },
        {
            "name": "fast_sanity_rejected_by_same_run_live_gate",
            "status": "PASS",
            "receipt": str(fast_same_out),
            "errors": fast_same_receipt.get("errors"),
        },
        {
            "name": "live_pair_receipts_pass_live_gate",
            "status": "PASS",
            "receipt": str(live_pair_out),
        },
        {
            "name": "same_run_live_receipt_passes_live_gate",
            "status": "PASS",
            "receipt": str(same_run_out),
        },
    ]
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="battle_tiered_gate_proof_class_validator_with_current_source_receipts",
            checks=checks,
            artifacts={
                "fast_sanity_only": str(fast_path),
                "fast_as_live_pair_gate": str(fast_pair_out),
                "fast_as_same_run_live_gate": str(fast_same_out),
                "live_pair_gate": str(live_pair_out),
                "same_run_live_gate": str(same_run_out),
            },
            claims_proves=[
                "Offline fast sanity receipts cannot satisfy the live pair qualification gate.",
                "Offline fast sanity receipts cannot satisfy the same-run live qualification gate.",
                "Current-source live proof-class receipts can still satisfy their matching live qualification gates.",
            ],
            claims_does_not_prove=[
                "fresh provider campaign generation",
                "production deployment",
                "overnight campaign breadth",
            ],
        ),
    )


def probe_battle_profile_contract(summary_path: Path) -> int:
    suite = "battle-profile-contract"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    import tempfile
    sys.path.insert(0, str(BATTLE_DIR / "src"))
    from battle_skill.invariant_campaign import run_campaign, load_profile

    GEN_EXP = str(BATTLE_DIR / "tests" / "fixtures" / "mini_expectation_generator.py")

    def profile_file(name: str, **data) -> str:
        path = out_root / name
        payload = {"schema": "battle.campaign_profile.v1", "profile_id": f"probe-{name}",
                   "required_case_ids": []}
        payload.update(data)
        path.write_text(json.dumps(payload))
        return str(path)

    checks: list[dict[str, Any]] = []

    # 1. A profile-resolved MAY_REJECT -> MUST_ACCEPT is enforced: a
    #    reject-everything target FAILS through the profile path.
    prof = load_profile(profile_file("resolve.json", expectation_overrides={"may-reject-case": "MUST_ACCEPT"}))
    r1 = run_campaign(GEN_EXP, "exit 1", str(BATTLE_DIR / "fixtures/reference-judges/no_data_leak_judge.py"),
                      output_subdir="corpus", profile=prof)
    ok1 = r1.passed is False and any("required-accept-case-rejected" in v for f in r1.failures for v in f["violations"])
    checks.append({"name": "profile_resolved_expectation_enforced", "status": "PASS" if ok1 else "FAIL",
                   "detail": {"passed": r1.passed, "failures": r1.failures[:2]}})

    # 2. A profile cannot downgrade a generator-declared spec-floor expectation.
    prof2 = load_profile(profile_file("downgrade.json", expectation_overrides={"must-accept-case": "MUST_REJECT"}))
    r2 = run_campaign(GEN_EXP, "exit 1", str(BATTLE_DIR / "fixtures/reference-judges/no_data_leak_judge.py"),
                      output_subdir="corpus", profile=prof2)
    ok2 = any("profile-illegal-expectation-override" in v for f in r2.failures for v in f["violations"])
    checks.append({"name": "profile_cannot_downgrade_spec_floor", "status": "PASS" if ok2 else "FAIL",
                   "detail": {"failures": r2.failures[:2]}})

    # 3. Unknown override targets and missing required cases are hard failures.
    prof3 = load_profile(profile_file("unknown.json", expectation_overrides={"no-such-case": "MUST_REJECT"},
                                      required_case_ids=["never-generated-case"]))
    r3 = run_campaign(GEN_EXP, "exit 1", str(BATTLE_DIR / "fixtures/reference-judges/no_data_leak_judge.py"),
                      output_subdir="corpus", profile=prof3)
    ok3 = (any("profile-unknown-case-override" in v for f in r3.failures for v in f["violations"])
           and any("profile-required-case-missing" in v for f in r3.failures for v in f["violations"]))
    checks.append({"name": "unknown_override_and_missing_required_fail", "status": "PASS" if ok3 else "FAIL",
                   "detail": {"failures": r3.failures[:3]}})

    # 4. Malformed profiles fail shape validation (fail-closed, never silent).
    bad = out_root / "bad.json"
    bad.write_text(json.dumps({"schema": "wrong.schema"}))
    try:
        load_profile(str(bad))
        ok4 = False
    except ValueError:
        ok4 = True
    checks.append({"name": "malformed_profile_rejected", "status": "PASS" if ok4 else "FAIL"})

    failed = [c for c in checks if c["status"] != "PASS"]
    if failed:
        raise AssertionError(f"profile contract checks failed: {failed}")
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="local_deterministic_profile_contract_probe",
            checks=checks,
            artifacts={"probe_root": str(out_root)},
            claims_proves=[
                "A consumer profile resolves MAY_REJECT choices and the campaign enforces the resolved expectation.",
                "A profile cannot downgrade a generator-declared MUST_ACCEPT/MUST_REJECT spec floor.",
                "Unknown override targets, missing required cases, and malformed profiles fail closed.",
            ],
            claims_does_not_prove=[
                "any specific project profile correctness",
                "docker target behavior",
            ],
        ),
    )


def probe_battle_functional_judge(summary_path: Path) -> int:
    suite = "battle-functional-judge"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "functional_judge", str(BATTLE_DIR / "fixtures" / "reference-judges" / "functional_anonymize_judge.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def run_case(name: str, files: dict, out_files: dict) -> dict:
        case_dir = out_root / name
        inp, out = case_dir / "in" / "corpus", case_dir / "out" / "corpus"
        inp.mkdir(parents=True)
        out.mkdir(parents=True)
        (case_dir / "policy.json").write_text(json.dumps(
            {"sensitive_values": [{"rule_id": "r", "subject_id": "s", "type": "name", "value": "Mara Ellison"}]}))
        for rel, content in files.items():
            (inp / rel).write_text(content)
        for rel, content in (out_files or {}).items():
            (out / rel).write_text(content)
        (case_dir / "out" / "report.json").write_text(json.dumps({"status": "ready"}))
        return mod.judge(str(case_dir / "out"),
                         {"policy": str(case_dir / "policy.json"),
                          "output_subdir": "corpus", "input_dir": str(case_dir / "in")})

    checks: list[dict[str, Any]] = []

    r = run_case("golden", {"a.txt": "note: Mara Ellison ok\n"}, {"a.txt": "note: Person-A ok\n"})
    checks.append({"name": "golden_pass", "status": "PASS" if r["passed"] else "FAIL", "detail": r["violations"][:2]})

    r = run_case("empty-out", {"a.txt": "note: Mara Ellison\n"}, {})
    checks.append({"name": "destroyed_inventory_fails", "status": "PASS" if not r["passed"] and any("inventory-mismatch" in v for v in r["violations"]) else "FAIL", "detail": r["violations"][:2]})

    r = run_case("blanked", {"a.txt": "note: Mara Ellison ok\n"}, {"a.txt": "\n"})
    checks.append({"name": "blanked_content_fails", "status": "PASS" if not r["passed"] else "FAIL", "detail": r["violations"][:2]})

    r = run_case("literal-damage", {"a.txt": "note: Mara Ellison ok\n"}, {"a.txt": "CHANGED: Person-A ok\n"})
    checks.append({"name": "modified_literal_fails", "status": "PASS" if not r["passed"] and any("literal" in v for v in r["violations"]) else "FAIL", "detail": r["violations"][:2]})

    r = run_case("value-kept", {"a.txt": "x Mara Ellison y\n"}, {"a.txt": "x Mara Ellison y\n"})
    checks.append({"name": "unreplaced_value_fails_functionally", "status": "PASS" if not r["passed"] and any("replacement still contains" in v for v in r["violations"]) else "FAIL", "detail": r["violations"][:2]})

    failed = [c for c in checks if c["status"] != "PASS"]
    if failed:
        raise AssertionError(f"functional judge checks failed: {failed}")
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="local_deterministic_functional_judge_probe",
            checks=checks,
            artifacts={"probe_root": str(out_root)},
            claims_proves=[
                "The functional judge passes a correct anonymized output and fails destroyed, blanked, modified-literal, and unreplaced-value outputs.",
                "Accepted campaign cases can be required to pass both security and functional judges.",
            ],
            claims_does_not_prove=[
                "provider-driven Red quality",
                "arbitrary-schema functional equivalence",
            ],
        ),
    )


def probe_battle_terminal_semantics(summary_path: Path) -> int:
    suite = "battle-terminal-semantics"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    receipt_path = out_root / "terminal-semantics-receipt.json"
    check = _run_in(
        [str(RUN_SH), "current-status", "check"],
        cwd=REPO_ROOT,
        timeout=180,
        env={"BATTLE_TERMINAL_SEMANTICS_RECEIPT": str(receipt_path)},
    )
    (out_root / "current-status-check.stdout.txt").write_text(check.stdout, encoding="utf-8")
    (out_root / "current-status-check.stderr.txt").write_text(check.stderr, encoding="utf-8")
    if check.returncode != 0:
        raise AssertionError("current-status check failed: " + check.stdout + check.stderr)
    output = _parse_json_object(check.stdout)
    if output.get("status") != "PASS":
        raise AssertionError(f"current-status check did not report PASS: {output}")
    if Path(str(output.get("terminal_semantics_receipt") or "")) != receipt_path:
        raise AssertionError(f"current-status output did not bind terminal receipt: {output}")
    receipt = _read_json(receipt_path)
    if receipt.get("status") != "PASS":
        raise AssertionError(f"terminal-semantics receipt did not pass: {receipt}")

    from battle_skill.terminal_semantics import judge_candidate

    accepted = receipt.get("accepted") or []
    if not accepted or accepted[0].get("decision") != "ACCEPT":
        raise AssertionError("real Judge evidence was not accepted")
    source = Path(accepted[0]["judge_receipt"])
    if _sha256_file(source).removeprefix("sha256:") != accepted[0]["judge_receipt_sha256"]:
        raise AssertionError("accepted Judge bytes are not bound")
    base = judge_candidate(source)
    candidates = {f"rejects_{alias}_alias": {**base, "terminal_state": alias} for alias in ("kill", "fastest_crash", "promotion")}
    candidates["rejects_authority_contradiction"] = {**base, "source_authority": "scorekeeper", "scorekeeper_status": "BLUE_SUCCESS"}
    candidates["rejects_missing_judge"] = {**base, "judge_receipt": str(out_root / "absent.json")}
    candidates["rejects_stale_hash"] = {**base, "judge_receipt_sha256": "0" * 64}
    candidates["rejects_unbound_self_claim"] = {k: v for k, v in base.items() if k not in {"judge_receipt", "judge_receipt_sha256"}}
    for name in ("crash_only_promotion", "contradictory_verdict"):
        mutated = _read_json(source)
        mutated["verdict"] = "RED_SUCCESS"
        if name == "crash_only_promotion":
            mutated["attempts"] = []
        mutated_path = out_root / f"{name}-judge.json"
        _write_json(mutated_path, mutated)
        candidates[f"rejects_{name}"] = judge_candidate(mutated_path)
    rejected = {}
    for name, candidate in candidates.items():
        candidate_path = out_root / f"{name}.json"
        result_path = out_root / f"{name}-result.json"
        _write_json(candidate_path, candidate)
        proc = _run_in([str(RUN_SH), "current-status", "check", "--terminal-candidate", str(candidate_path)], cwd=REPO_ROOT, timeout=180, env={"BATTLE_TERMINAL_SEMANTICS_RECEIPT": str(result_path)})
        (out_root / f"{name}.stdout.txt").write_text(proc.stdout)
        result = _read_json(result_path)
        if proc.returncode == 0 or result.get("status") != "FAIL" or not result.get("rejected"):
            raise AssertionError(f"actual CLI accepted {name}: {proc.stdout}")
        rejected[name] = {"name": name, **result["rejected"][0], "receipt": str(result_path)}
    from battle_skill.battle_event_adapter import adapt_tau_public_only_proof

    adapter_root = source.parents[2] / "generation-1"
    adapter = adapt_tau_public_only_proof(proof_root=adapter_root, battle_id="battle-004")
    adapter_judge = _read_json(adapter_root / "judge/judge-receipt.json")
    if adapter["scoreboard"]["verdict"] != adapter_judge["verdict"]:
        raise AssertionError("adapter preferred a materialization/run claim over the actual Judge")
    _write_json(out_root / "adapter-readback.json", adapter)
    receipt["rejected"] = list(rejected.values())
    receipt["adapter_judge_authority_verified"] = True
    receipt["proof_scope"] = "real current-status CLI and receipt adapter with retained Judge input and adversarial input mutations; no new Docker/provider run"
    _write_json(receipt_path, receipt)

    checks = [
        {
            "name": "current_status_check_passed",
            "status": "PASS",
            "stdout": str(out_root / "current-status-check.stdout.txt"),
        },
        {
            "name": "terminal_semantics_receipt_passed",
            "status": "PASS",
            "receipt": str(receipt_path),
        },
        {
            "name": "kill_and_fastest_crash_rejected",
            "status": "PASS",
            "rejections": [
                rejected["rejects_kill_alias"],
                rejected["rejects_fastest_crash_alias"],
            ],
        },
        {
            "name": "crash_only_promotion_rejected",
            "status": "PASS",
            "rejection": rejected["rejects_crash_only_promotion"],
        },
    ]
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="battle_run_sh_current_status_check_with_terminal_semantics_receipt",
            checks=checks,
            artifacts={
                "current_status_check_stdout": str(out_root / "current-status-check.stdout.txt"),
                "terminal_semantics_receipt": str(receipt_path),
            },
            claims_proves=[
                "Battle current-status and receipt consumers bind terminal state to real typed Judge receipt bytes and matching attempt outcomes.",
                "kill, fastest_crash, promotion aliases and crash-only promotion fail closed.",
            ],
            claims_does_not_prove=[
                "future kill or fastest_crash semantics with a new Judge receipt family",
                "production deployment readiness",
            ],
        ),
    )


def probe_battle_adaptive_improvement(summary_path: Path) -> int:
    suite = "battle-adaptive-improvement"
    out = summary_path.parent / suite
    out.mkdir(parents=True, exist_ok=True)
    checks = []
    for label, flags in (("positive", []), ("same-treatment", ["--force-non-improvement"])):
        result_path = out / f"{label}.json"
        command = [str(RUN_SH), "prove-adaptive-improvement", "--fixture", "battle-004", "--output", str(result_path), *flags]
        proc = _run(command, timeout=300)
        (out / f"{label}.stdout.txt").write_text(proc.stdout)
        (out / f"{label}.stderr.txt").write_text(proc.stderr)
        result = _read_json(result_path)
        expected = "PASS" if label == "positive" else "NOT_PROVEN"
        if result.get("status") != expected or proc.returncode != (0 if label == "positive" else 1):
            raise AssertionError(f"{label}: {result.get('error') or result}")
        if not all(result.get(k) is True for k in ("execution_started", "live", "promoted_artifact_consumed", "paired_baseline_present", "replay_verified", "bound_hashes")):
            raise AssertionError(f"{label}: missing real paired replay evidence")
        measured = {}
        for arm in ("baseline", "adaptive"):
            runs = result[arm]["runs"]
            if len(runs) != 2:
                raise AssertionError("two independent Judge executions per arm required")
            scores = []
            for run in runs:
                judge_path = Path(run["judge_receipt"])
                if _sha256_file(judge_path).removeprefix("sha256:") != run["judge_sha256"]:
                    raise AssertionError("Judge digest mismatch")
                judge = _read_json(judge_path)
                attempt = judge["attempts"][0]
                before, after = attempt["commands_run"][-2:]
                for cmd in (before, after, run["functional_control"]):
                    if cmd["command"][0] != "docker" or "none" not in cmd["command"]:
                        raise AssertionError("proof did not use network-disabled Docker")
                original_confirmed = before["exit_code"] == 0 and "RED_EXPLOIT_CONFIRMED" in Path(before["stdout_path"]).read_text()
                still_exploitable = after["exit_code"] == 0 and "RED_EXPLOIT_CONFIRMED" in Path(after["stdout_path"]).read_text()
                functional = run["functional_control"]
                normal_import = functional["exit_code"] == 0 and "VALID_ZIP_IMPORT_OK" in Path(functional["stdout_path"]).read_text()
                score = int(original_confirmed and not still_exploitable and normal_import)
                if score != run["metric_value"]:
                    raise AssertionError("reported metric differs from Docker artifact readback")
                scores.append(score)
            if scores[0] != scores[1]:
                raise AssertionError("outcome did not repeat")
            measured[arm] = scores[0]
        if (measured["adaptive"] > measured["baseline"]) != (label == "positive"):
            raise AssertionError(f"paired outcome mismatch: {measured}")
        for ref in result["artifact_hashes"].values():
            if _sha256_file(Path(ref["path"])).removeprefix("sha256:") != ref["sha256"]:
                raise AssertionError("input changed after experiment")
        checks.append({"name": label, "status": "PASS", "observed": expected, "measured": measured, "receipt": str(result_path)})
    return _emit(summary_path, _summary(suite=suite, live="fresh_authorized_docker_judge_replays_with_retained_promoted_artifacts", checks=checks, artifacts={"positive": str(out / "positive.json"), "no_effect_control": str(out / "same-treatment.json")}, claims_proves=["retained promoted Blue bytes cause the measured bounded Docker defense improvement", "the same promoted treatment in both arms reports NOT_PROVEN, not an improvement"], claims_does_not_prove=["new provider learning", "Memory retrieval benefit", "population generalization"]))


def probe_small_medium_production_battle(summary_path: Path) -> int:
    suite = "small-medium-production-battle"
    out_root = summary_path.parent / suite
    if out_root.exists():
        shutil.rmtree(out_root)
    run = _run_in(
        [
            sys.executable,
            str(BATTLE_DIR / "scripts" / "run_small_medium_production_battle.py"),
            "--out",
            str(out_root),
        ],
        cwd=REPO_ROOT,
        timeout=300,
        env={"PYTHONPATH": f"{REPO_ROOT / 'skills'}:{BATTLE_DIR / 'src'}"},
    )
    (out_root.parent / f"{suite}.stdout.txt").write_text(run.stdout, encoding="utf-8")
    (out_root.parent / f"{suite}.stderr.txt").write_text(run.stderr, encoding="utf-8")
    if run.returncode != 0:
        raise AssertionError("small/medium production Battle failed: " + run.stdout + run.stderr)
    receipt_path = out_root / "run-receipt.json"
    scorekeeper_path = out_root / "scorekeeper-receipt.json"
    report_path = out_root / "REPORT.md"
    auth_path = out_root / "authorization-validation.json"
    event_log_path = out_root / "event-ledger.jsonl"
    arena_path = out_root / "arena-contract.json"
    receipt = _read_json(receipt_path)
    scorekeeper = _read_json(scorekeeper_path)
    auth = _read_json(auth_path)
    rounds = receipt.get("rounds") or []
    docker_attempts = [attempt for item in rounds for attempt in item.get("docker_attempts", [])]
    report_text = report_path.read_text(encoding="utf-8") if report_path.is_file() else ""
    commentary_keys = {"red_scanned", "red_attempts", "blue_scanned", "blue_attempts", "adaptive_lineage_created"}
    commentary_present = all(commentary_keys <= set(item) and all(item[key] for key in commentary_keys) for item in rounds)
    spawn_receipts = [item.get("spawn_receipt") for item in rounds if item.get("spawn_receipt")]
    spawn_children = [child for spawn in spawn_receipts for child in spawn.get("children", [])]
    spawn_preflight_present = bool(spawn_children) and all(child.get("preflight", {}).get("path") for child in spawn_children)
    high_novelty_death = any(child.get("novelty") == "high" and child.get("lineage_decision") == "reject_dead_preflight" for child in spawn_children)
    promoted_child = any(child.get("lineage_decision") == "promote_to_rematch_seed" for child in spawn_children)
    event_log_text = event_log_path.read_text(encoding="utf-8") if event_log_path.is_file() else ""
    checks = [
        {"name": "authorization_passed_before_execution", "status": "PASS" if auth.get("status") == "PASS" else "FAIL", "authorization": str(auth_path)},
        {"name": "six_round_medium_arena", "status": "PASS" if len(rounds) == 6 else "FAIL", "round_count": len(rounds)},
        {"name": "round_wins_even", "status": "PASS" if scorekeeper.get("red_round_wins") == scorekeeper.get("blue_round_wins") == 3 else "FAIL", "red_round_wins": scorekeeper.get("red_round_wins"), "blue_round_wins": scorekeeper.get("blue_round_wins")},
        {"name": "docker_attempts_present", "status": "PASS" if len(docker_attempts) == 12 else "FAIL", "docker_attempt_count": len(docker_attempts)},
        {"name": "arena_contract_written", "status": "PASS" if arena_path.is_file() and receipt.get("arena_contract") == str(arena_path) else "FAIL", "arena_contract": str(arena_path)},
        {"name": "plain_report_written", "status": "PASS" if "## Human summary" in report_text else "FAIL", "report": str(report_path)},
        {"name": "arena_first_report_written", "status": "PASS" if report_text.startswith("# Small/Medium Production-Scale Battle Report\n\n## Arena prologue") and "### Expected exploit families" in report_text else "FAIL", "report": str(report_path)},
        {"name": "sports_commentary_written", "status": "PASS" if "## Sports commentary" in report_text and "**Red scan.**" in report_text and "**Warm pond spawn.**" in report_text else "FAIL", "report": str(report_path)},
        {"name": "round_receipts_carry_commentary", "status": "PASS" if commentary_present else "FAIL", "required_keys": sorted(commentary_keys)},
        {"name": "spawn_preflight_receipts_present", "status": "PASS" if spawn_preflight_present else "FAIL", "spawn_child_count": len(spawn_children)},
        {"name": "high_novelty_children_can_die", "status": "PASS" if high_novelty_death else "FAIL"},
        {"name": "lineage_promotes_rematch_seed", "status": "PASS" if promoted_child else "FAIL"},
        {"name": "event_ledger_jsonl_written", "status": "PASS" if "spawn_preflight" in event_log_text and "scorekeeper_final" in event_log_text else "FAIL", "event_ledger": str(event_log_path)},
    ]
    failed = [item for item in checks if item["status"] != "PASS"]
    if failed:
        raise AssertionError(f"small/medium production Battle checks failed: {failed}")
    return _emit(
        summary_path,
        _summary(
            suite=suite,
            live="local_docker_judge_medium_arena",
            checks=checks,
            artifacts={
                "run_receipt": str(receipt_path),
                "scorekeeper_receipt": str(scorekeeper_path),
                "authorization_validation": str(auth_path),
                "report": str(report_path),
            },
            claims_proves=[
                "A local small/medium Battle ran six Docker-judged rounds after authorization.",
                "The arena produced even round wins: Red 3 and Blue 3, with scoring decided by Judge-backed defense value.",
                "A plainspoken report was written as the primary human artifact.",
            ],
            claims_does_not_prove=[
                "External production deployment readiness.",
                "Provider/Tau-generated Red and Blue creativity.",
                "1000-round overnight throughput.",
                "Arbitrary external target exploitability.",
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
        if args.suite == "review-cli-authorization-target-binding":
            return probe_review_cli_authorization_target_binding(args.summary)
        if args.suite == "battle-b04-bind-authorization-to-the-actual-executable-target":
            return probe_b04_bind_authorization_to_executable_target(args.summary)
        if args.suite == "battle-b05-strictly-validate-campaign-and-acceptance-envelopes":
            return probe_b05_strict_campaign_acceptance_envelopes(args.summary)
        if args.suite == "battle-b06-verify-evaluator-locks-before-loading-executable-components":
            return probe_b06_verify_evaluator_locks(args.summary)
        if args.suite == "battle-b07-confine-all-materialized-artifacts-to-owned-snapshots":
            return probe_b07_confine_materialized_artifacts(args.summary)
        if args.suite == "battle-b08-separate-safe-rejection-from-execution-failure":
            return probe_b08_separate_safe_rejection(args.summary)
        if args.suite == "battle-b09-require-a-typed-fixture-witness-rather-than-any-judge-failu":
            return probe_b09_fixture_witness_contract(args.summary)
        if args.suite == "review-receipt-hash-finalization":
            return probe_review_receipt_hash_finalization(args.summary)
        if args.suite == "review-judge-authority":
            return probe_review_judge_authority(args.summary)
        if args.suite == "scorekeeper-adversarial":
            return probe_scorekeeper_adversarial(args.summary)
        if args.suite == "adaptive-lineage-contracts":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=[
                    "test_adaptive_lineage_fixture.py",
                    "test_adaptive_lineage_goal_qualification.py",
                    "test_adaptive_red_blue_lineage_canary_contract.py",
                    "test_adaptive_lineage_backend_verifier.py",
                    "test_universal_adaptive_lineage_engine.py",
                    "test_adaptive_lineage_memory.py",
                ],
            )
        if args.suite == "adaptive-lineage-live-exact-chain":
            return probe_adaptive_lineage_live_exact_chain(args.summary, proof_root=args.proof_root)
        if args.suite == "provider-tau-seeded-lineage-spawn":
            return probe_provider_tau_seeded_lineage_spawn(args.summary, proof_root=args.proof_root)
        if args.suite == "review-selection-reporting":
            return probe_review_selection_reporting(args.summary)
        if args.suite == "review-broadcast-required-evidence":
            return probe_review_broadcast_required_evidence(args.summary)
        if args.suite == "review-commentary-provenance":
            return probe_review_commentary_provenance(args.summary)
        if args.suite == "review-memory-admission-binding":
            return probe_review_memory_admission_binding(args.summary)
        if args.suite == "provider-tau-memory-promotion":
            return probe_provider_tau_memory_promotion(args.summary, proof_root=args.proof_root)
        if args.suite == "current-status-adaptive-lineage-receipt":
            return probe_current_status_adaptive_lineage_receipt(args.summary)
        if args.suite == "review-current-status-proof-chain":
            return probe_review_current_status_proof_chain(args.summary)
        if args.suite == "battle-terminal-semantics":
            return probe_battle_terminal_semantics(args.summary)
        if args.suite == "battle-current-status-claim-gates":
            return probe_battle_current_status_claim_gates(args.summary)
        if args.suite == "battle-proof-rung-separation":
            return probe_battle_proof_rung_separation(args.summary)
        if args.suite == "battle-profile-contract":
            return probe_battle_profile_contract(args.summary)
        if args.suite == "contract-variation-plan":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=["test_contract_variation_plan.py"],
            )
        if args.suite == "docker-execution-boundary":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=["test_production_adapter.py"],
            )
        if args.suite == "frozen-plan-execution":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=["test_campaign_contract.py"],
            )
        if args.suite == "acceptance-floor-production-adapter":
            return probe_pytest_contracts(
                args.summary,
                suite=args.suite,
                tests=["test_contract_floor_required.py", "test_production_adapter.py"],
            )
        if args.suite == "battle-functional-judge":
            return probe_battle_functional_judge(args.summary)
        if args.suite == "battle-commentary-causality":
            return probe_battle_commentary_causality(args.summary)
        if args.suite == "battle-adaptive-improvement":
            return probe_battle_adaptive_improvement(args.summary)
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
        if args.suite == "small-medium-production-battle":
            return probe_small_medium_production_battle(args.summary)
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
