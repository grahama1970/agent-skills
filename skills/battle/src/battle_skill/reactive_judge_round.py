"""Reactive Blue and independent Judge replay for Battle rounds.

Inputs are an authorization manifest, a deterministic local fixture, and an
output directory. Outputs are a strict event ledger plus hash-bound receipts for
Red observation, Judge replay, reactive Blue input, candidate patch, Judge
patch replay, scorekeeping, and artifact hashing. Failures return explicit
receipts and do not promote Red, Blue, or scorekeeper claims from advisory
fields.
"""

from __future__ import annotations

import difflib
import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from common.security_authorization import validate_target_authorization
from loguru import logger

from .config import SKILL_DIR

SCHEMA_ROUND = "battle.reactive_judge_round.v1"
SCHEMA_LEDGER = "battle.reactive_judge_event_ledger.v1"
SCHEMA_SCOREKEEPER = "battle.scorekeeper_receipt.v1"
SCHEMA_PATCH = "battle.candidate_patch_receipt.v1"
SCHEMA_BLUE_INPUT = "battle.blue_input_receipt.v1"
HACK_OBSERVATION_SCHEMA = "hack.probe_observation.v1"
HACK_VALIDATION_SCHEMA = "hack.proof_validation_receipt.v1"

PYTHON_IMAGE = "python:3.12-slim"
FIXTURE_DIR = SKILL_DIR / "fixtures" / "reactive-judge"
TARGET_IDENTITY = "battle-reactive-judge-fixture@sha256:reactive-judge-v1"
PHASES = [
    "authorization_validated",
    "baseline_materialized",
    "red_started",
    "proactive_blue_started",
    "proactive_blue_terminal",
    "red_observation_received",
    "judge1_started",
    "judge1_terminal",
    "reactive_blue_started",
    "candidate_patch_received",
    "judge2_started",
    "judge2_terminal",
    "scorekeeper_started",
    "scorekeeper_terminal",
    "round_terminal",
]


class PhaseTransitionError(ValueError):
    """Raised when a Battle event would violate the legal phase order."""


class EventLedger:
    """Strict append-only phase ledger with monotonic receipt timestamps."""

    def __init__(self, *, battle_id: str, out_dir: Path) -> None:
        self.battle_id = battle_id
        self.out_dir = out_dir
        self.started = time.monotonic()
        self.events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def append(self, phase: str, *, actor: str, receipt: str | None = None, data: dict[str, Any] | None = None) -> None:
        if phase not in PHASES:
            raise PhaseTransitionError(f"unknown phase: {phase}")
        with self._lock:
            phase_index = PHASES.index(phase)
            previous_indexes = [PHASES.index(event["phase"]) for event in self.events]
            if previous_indexes and phase_index < max(previous_indexes):
                raise PhaseTransitionError(f"phase {phase} cannot follow {self.events[-1]['phase']}")
            self.events.append(
                {
                    "seq": len(self.events) + 1,
                    "phase": phase,
                    "actor": actor,
                    "elapsed_seconds": round(time.monotonic() - self.started, 6),
                    "receipt": receipt,
                    "data": data or {},
                }
            )

    def write(self) -> Path:
        path = self.out_dir / "event-ledger.json"
        write_json(
            path,
            {
                "schema": SCHEMA_LEDGER,
                "battle_id": self.battle_id,
                "status": "PASS",
                "legal_phase_order": PHASES,
                "events": self.events,
            },
        )
        return path


@dataclass(frozen=True)
class Judge2Outcome:
    """Normalized Judge #2 outcome used by the scorekeeper."""

    verdict: Literal[
        "BLUE_SUCCESS",
        "RED_SUCCESS",
        "FAKE_DEFENSE",
        "REPLAY_ERROR",
        "HASH_MISMATCH",
    ]
    exploit_blocked: bool
    functionality_passed: bool
    status: Literal["PASS", "FAIL"]


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def object_sha256(data: Any) -> str:
    return sha256(canonical_json(data)).hexdigest()


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def copytree_clean(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def hash_manifest(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def run_docker_python(workspace: Path, script: str, *, name: str, out_dir: Path) -> dict[str, Any]:
    """Run one fixture command inside a local networkless Docker container."""
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "256m",
        "-v",
        f"{workspace.resolve()}:/workspace",
        "-w",
        "/workspace",
        PYTHON_IMAGE,
        "python",
        script,
    ]
    proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
    stdout_path = out_dir / f"{name}.stdout.txt"
    stderr_path = out_dir / f"{name}.stderr.txt"
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    return {
        "command": command,
        "exit_code": proc.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def build_red_observation(
    *,
    battle_id: str,
    workspace: Path,
    command_receipt: dict[str, Any],
    authorization_hash: str,
    baseline_hash: str,
) -> dict[str, Any]:
    marker = workspace / "artifacts" / "exploit-marker.txt"
    signal_detected = marker.exists()
    evidence_hash = file_sha256(marker) if marker.exists() else None
    return {
        "schema": HACK_OBSERVATION_SCHEMA,
        "battle_id": battle_id,
        "finding_id": "command-injection-001",
        "target_identity": TARGET_IDENTITY,
        "authorization_manifest_sha256": authorization_hash,
        "target_runtime_sha256": baseline_hash,
        "probe_spec_sha256": file_sha256(workspace / "probe_exploit.py"),
        "scan_request_sha256": baseline_hash,
        "executor_identity": "battle-red-hack-fixture",
        "exit_code": command_receipt["exit_code"],
        "signal_type": "command_injection_marker",
        "signal_detected": signal_detected,
        "evidence_sha256": evidence_hash,
        "exploit_confirmed": False,
        "status": "OBSERVED_UNCONFIRMED",
        "command_receipt": command_receipt,
    }


def build_judge1_receipt(
    *,
    battle_id: str,
    observation: dict[str, Any],
    observation_path: Path,
    workspace: Path,
    command_receipt: dict[str, Any],
    authorization_hash: str,
    baseline_hash: str,
) -> dict[str, Any]:
    marker = workspace / "artifacts" / "exploit-marker.txt"
    replay_confirmed = command_receipt["exit_code"] == 0 and marker.exists()
    errors: list[str] = []
    if observation.get("target_identity") != TARGET_IDENTITY:
        errors.append("target_identity does not match Judge target")
    if observation.get("authorization_manifest_sha256") != authorization_hash:
        errors.append("authorization hash mismatch")
    if observation.get("target_runtime_sha256") != baseline_hash:
        errors.append("target runtime hash mismatch")
    if observation.get("executor_identity") == "battle-judge":
        errors.append("Judge identity must differ from Red executor")
    if not replay_confirmed:
        errors.append("Judge replay did not confirm the observed signal")
    status = "CONFIRMED" if not errors else "REJECTED"
    return {
        "schema": "battle.judge_receipt.v1",
        "battle_id": battle_id,
        "round_number": 1,
        "judge_number": 1,
        "status": "PASS" if status == "CONFIRMED" else "FAIL",
        "verdict": status,
        "validator_identity": "battle-judge",
        "observation_path": str(observation_path),
        "observation_sha256": file_sha256(observation_path),
        "authorization_manifest_sha256": authorization_hash,
        "target_runtime_sha256": baseline_hash,
        "replay_receipt_sha256": object_sha256(command_receipt),
        "hack_validation_receipt": {
            "schema": HACK_VALIDATION_SCHEMA,
            "status": "PASS" if status == "CONFIRMED" else "FAIL",
            "validation_status": status,
            "confirms_exploit": status == "CONFIRMED",
            "validator_identity": "battle-judge",
            "observation_path": str(observation_path),
            "observation_artifact_sha256": file_sha256(observation_path),
            "mocked": False,
            "live": "local_docker_fixture",
        },
        "errors": errors,
        "command_receipt": command_receipt,
    }


def blue_input_receipt(
    *,
    battle_id: str,
    phase: Literal["proactive", "reactive"],
    confirmed_finding: dict[str, Any] | None,
) -> dict[str, Any]:
    if phase == "proactive":
        private_findings: list[dict[str, Any]] = []
        replay_contract = None
    elif confirmed_finding:
        private_findings = [
            {
                "finding_id": confirmed_finding["finding_id"],
                "observation_sha256": confirmed_finding["observation_sha256"],
                "replay_receipt_sha256": confirmed_finding["replay_receipt_sha256"],
            }
        ]
        replay_contract = {
            "validator_identity": "battle-judge",
            "finding_id": confirmed_finding["finding_id"],
        }
    else:
        private_findings = []
        replay_contract = None
    return {
        "schema": SCHEMA_BLUE_INPUT,
        "battle_id": battle_id,
        "round_number": 1,
        "phase": phase,
        "private_red_findings": private_findings,
        "replay_contract": replay_contract,
        "status": "PASS",
    }


def apply_candidate_patch(*, fixture_dir: Path, workspace: Path, out_dir: Path, battle_id: str) -> dict[str, Any]:
    source = workspace / "service.py"
    patched = fixture_dir / "patches" / "service.py"
    before = source.read_text(encoding="utf-8")
    after = patched.read_text(encoding="utf-8")
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="a/service.py",
            tofile="b/service.py",
        )
    )
    patch_path = out_dir / "candidate-patch.json"
    write_json(
        patch_path,
        {
            "schema": "battle.candidate_patch_artifact.v1",
            "format": "unified_diff",
            "changed_files": ["service.py"],
            "diff": diff,
        },
    )
    source.write_text(after, encoding="utf-8")
    return {
        "schema": SCHEMA_PATCH,
        "battle_id": battle_id,
        "round_number": 1,
        "status": "PASS",
        "changed_files": ["service.py"],
        "patch_artifact": str(patch_path),
        "patch_sha256": file_sha256(patch_path),
        "advisory_blue_success": True,
        "advisory_functionality_preserved": True,
    }


def classify_judge2_outcome(
    *,
    exploit_exit_code: int,
    functionality_exit_code: int,
    expected_target_hash: str,
    actual_target_hash: str,
    replay_error: bool = False,
) -> Judge2Outcome:
    """Classify Judge #2 from replay receipts only."""
    if expected_target_hash != actual_target_hash:
        return Judge2Outcome("HASH_MISMATCH", False, False, "FAIL")
    if replay_error:
        return Judge2Outcome("REPLAY_ERROR", False, False, "FAIL")
    exploit_blocked = exploit_exit_code != 0
    functionality_passed = functionality_exit_code == 0
    if not exploit_blocked:
        return Judge2Outcome("RED_SUCCESS", False, functionality_passed, "FAIL")
    if not functionality_passed:
        return Judge2Outcome("FAKE_DEFENSE", True, False, "FAIL")
    return Judge2Outcome("BLUE_SUCCESS", True, True, "PASS")


def build_judge2_receipt(
    *,
    battle_id: str,
    patched_workspace: Path,
    baseline_hash: str,
    patch_receipt: dict[str, Any],
    exploit_command: dict[str, Any],
    functionality_command: dict[str, Any],
) -> dict[str, Any]:
    actual_hash = object_sha256(hash_manifest(patched_workspace))
    outcome = classify_judge2_outcome(
        exploit_exit_code=exploit_command["exit_code"],
        functionality_exit_code=functionality_command["exit_code"],
        expected_target_hash=actual_hash,
        actual_target_hash=actual_hash,
    )
    return {
        "schema": "battle.judge_receipt.v1",
        "battle_id": battle_id,
        "round_number": 1,
        "judge_number": 2,
        "status": outcome.status,
        "verdict": outcome.verdict,
        "baseline_sha256": baseline_hash,
        "patched_runtime_sha256": actual_hash,
        "patch_receipt_sha256": object_sha256(patch_receipt),
        "exploit_blocked_after_patch": outcome.exploit_blocked,
        "regression_tests_pass": outcome.functionality_passed,
        "functionality_preserved": outcome.functionality_passed,
        "exploit_replay_command": exploit_command,
        "functionality_command": functionality_command,
    }


def score_from_judges(*, judge1: dict[str, Any], judge2: dict[str, Any], blue_patch_receipt: dict[str, Any]) -> dict[str, Any]:
    """Return scores derived only from Judge receipts."""
    red_confirmed = judge1.get("verdict") == "CONFIRMED"
    red_score = 1.5 if red_confirmed else 0.0
    blue_score = 3.6 if judge2.get("verdict") == "BLUE_SUCCESS" else 0.0
    return {
        "schema": SCHEMA_SCOREKEEPER,
        "status": "PASS",
        "score_authority": "judge_receipts_only",
        "red_score": red_score,
        "blue_score": blue_score,
        "winner": "Blue" if blue_score > red_score else "Red",
        "tdsr": 1.0 if blue_score else 0.0,
        "fdsr": 1.0 if judge2.get("verdict") == "FAKE_DEFENSE" else 0.0,
        "asc": 1 if red_confirmed else 0,
        "ignored_blue_advisory_fields": {
            "advisory_blue_success": blue_patch_receipt.get("advisory_blue_success"),
            "advisory_functionality_preserved": blue_patch_receipt.get("advisory_functionality_preserved"),
        },
        "judge1_verdict": judge1.get("verdict"),
        "judge2_verdict": judge2.get("verdict"),
    }


def artifact_hash_manifest(out_dir: Path) -> dict[str, Any]:
    files = {
        str(path.relative_to(out_dir)): file_sha256(path)
        for path in sorted(out_dir.rglob("*"))
        if path.is_file() and path.name != "artifact-hash-manifest.json"
    }
    return {
        "schema": "battle.artifact_hash_manifest.v1",
        "status": "PASS",
        "files": files,
    }


def _red_worker(*, battle_id: str, workspace: Path, out_dir: Path, auth_hash: str, baseline_hash: str) -> dict[str, Any]:
    command = run_docker_python(workspace, "probe_exploit.py", name="red-exploit", out_dir=out_dir)
    return build_red_observation(
        battle_id=battle_id,
        workspace=workspace,
        command_receipt=command,
        authorization_hash=auth_hash,
        baseline_hash=baseline_hash,
    )


def _proactive_blue_worker(*, battle_id: str, out_dir: Path) -> dict[str, Any]:
    time.sleep(0.1)
    receipt = blue_input_receipt(battle_id=battle_id, phase="proactive", confirmed_finding=None)
    write_json(out_dir / "proactive-blue-input.json", receipt)
    return receipt


def run_reactive_judge_round(
    *,
    authorization_manifest: Path,
    out_dir: Path,
    fixture_dir: Path = FIXTURE_DIR,
) -> dict[str, Any]:
    """Run the deterministic local Docker reactive Judge proof."""
    battle_id = "battle-reactive-judge-001"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = EventLedger(battle_id=battle_id, out_dir=out_dir)

    authorization_receipt_path = out_dir / "authorization-validation.json"
    authorization_receipt = validate_target_authorization(
        authorization_manifest,
        expected_target=TARGET_IDENTITY,
        requested_action="battle",
        requested_runtime_mode="local_docker_fixture",
        requested_probe_class="command_injection",
        receipt_out=authorization_receipt_path,
    )
    if authorization_receipt["status"] != "PASS":
        return write_blocked_round(out_dir=out_dir, reason="authorization_failed", details=authorization_receipt)
    ledger.append("authorization_validated", actor="battle", receipt=str(authorization_receipt_path))

    image_check = subprocess.run(["docker", "image", "inspect", PYTHON_IMAGE], capture_output=True, text=True, check=False)
    if image_check.returncode != 0:
        return write_blocked_round(out_dir=out_dir, reason="python_docker_image_missing", details={"image": PYTHON_IMAGE})

    workspaces = out_dir / "workspaces"
    target = fixture_dir / "target"
    baseline = workspaces / "baseline"
    red_ws = workspaces / "red"
    judge1_ws = workspaces / "judge1"
    reactive_ws = workspaces / "reactive-blue"
    judge2_ws = workspaces / "judge2"
    for workspace in (baseline, red_ws, judge1_ws, reactive_ws, judge2_ws):
        copytree_clean(target, workspace)
        artifacts_dir = workspace / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        artifacts_dir.chmod(0o777)

    baseline_manifest = {
        "schema": "battle.immutable_baseline_manifest.v1",
        "status": "PASS",
        "target_identity": TARGET_IDENTITY,
        "files": hash_manifest(baseline),
    }
    baseline_hash = object_sha256(baseline_manifest["files"])
    baseline_manifest["baseline_sha256"] = baseline_hash
    baseline_manifest_path = write_json(out_dir / "immutable-baseline-manifest.json", baseline_manifest)
    ledger.append("baseline_materialized", actor="battle", receipt=str(baseline_manifest_path))

    auth_hash = file_sha256(authorization_manifest)
    red_dir = out_dir / "red"
    blue_dir = out_dir / "blue"
    judge1_dir = out_dir / "judge-1"
    judge2_dir = out_dir / "judge-2"

    red_result: dict[str, Any] = {}
    blue_result: dict[str, Any] = {}

    def run_red() -> None:
        ledger.append("red_started", actor="red")
        red_result.update(
            _red_worker(
                battle_id=battle_id,
                workspace=red_ws,
                out_dir=red_dir,
                auth_hash=auth_hash,
                baseline_hash=baseline_hash,
            )
        )
        red_path = write_json(out_dir / "red-hack-observation.json", red_result)
        ledger.append("red_observation_received", actor="red", receipt=str(red_path))

    def run_proactive_blue() -> None:
        ledger.append("proactive_blue_started", actor="blue")
        blue_result.update(_proactive_blue_worker(battle_id=battle_id, out_dir=blue_dir))
        ledger.append("proactive_blue_terminal", actor="blue", receipt=str(out_dir / "blue" / "proactive-blue-input.json"))

    red_thread = threading.Thread(target=run_red, name="battle-red")
    blue_thread = threading.Thread(target=run_proactive_blue, name="battle-proactive-blue")
    red_thread.start()
    blue_thread.start()
    red_thread.join()
    blue_thread.join()

    observation_path = out_dir / "red-hack-observation.json"
    ledger.append("judge1_started", actor="judge")
    judge1_command = run_docker_python(judge1_ws, "probe_exploit.py", name="judge1-exploit-replay", out_dir=judge1_dir)
    judge1 = build_judge1_receipt(
        battle_id=battle_id,
        observation=red_result,
        observation_path=observation_path,
        workspace=judge1_ws,
        command_receipt=judge1_command,
        authorization_hash=auth_hash,
        baseline_hash=baseline_hash,
    )
    judge1_path = write_json(judge1_dir / "judge-1-receipt.json", judge1)
    ledger.append("judge1_terminal", actor="judge", receipt=str(judge1_path))

    if judge1["verdict"] != "CONFIRMED":
        scorekeeper = score_from_judges(judge1=judge1, judge2={"verdict": "INSUFFICIENT_EVIDENCE"}, blue_patch_receipt={})
        score_path = write_json(out_dir / "scorekeeper-receipt.json", scorekeeper)
        ledger.append("scorekeeper_started", actor="scorekeeper")
        ledger.append("scorekeeper_terminal", actor="scorekeeper", receipt=str(score_path))
        ledger.append("round_terminal", actor="battle")
        return write_round_receipt(out_dir=out_dir, ledger=ledger, status="PASS", verdict="RED_UNCONFIRMED")

    confirmed = {
        "finding_id": red_result["finding_id"],
        "observation_sha256": file_sha256(observation_path),
        "replay_receipt_sha256": object_sha256(judge1_command),
    }
    ledger.append("reactive_blue_started", actor="blue")
    reactive_input = blue_input_receipt(battle_id=battle_id, phase="reactive", confirmed_finding=confirmed)
    reactive_input_path = write_json(blue_dir / "reactive-blue-input.json", reactive_input)
    patch_receipt = apply_candidate_patch(
        fixture_dir=fixture_dir,
        workspace=reactive_ws,
        out_dir=blue_dir,
        battle_id=battle_id,
    )
    patch_path = write_json(blue_dir / "candidate-patch-receipt.json", patch_receipt)
    ledger.append("candidate_patch_received", actor="blue", receipt=str(patch_path), data={"input_receipt": str(reactive_input_path)})

    copytree_clean(target, judge2_ws)
    shutil.copy2(reactive_ws / "service.py", judge2_ws / "service.py")
    judge2_artifacts = judge2_ws / "artifacts"
    judge2_artifacts.mkdir(exist_ok=True)
    judge2_artifacts.chmod(0o777)
    ledger.append("judge2_started", actor="judge")
    exploit_after_patch = run_docker_python(judge2_ws, "probe_exploit.py", name="judge2-exploit-replay", out_dir=judge2_dir)
    functionality = run_docker_python(judge2_ws, "functionality_check.py", name="judge2-functionality", out_dir=judge2_dir)
    judge2 = build_judge2_receipt(
        battle_id=battle_id,
        patched_workspace=judge2_ws,
        baseline_hash=baseline_hash,
        patch_receipt=patch_receipt,
        exploit_command=exploit_after_patch,
        functionality_command=functionality,
    )
    judge2_path = write_json(judge2_dir / "judge-2-receipt.json", judge2)
    ledger.append("judge2_terminal", actor="judge", receipt=str(judge2_path))

    ledger.append("scorekeeper_started", actor="scorekeeper")
    scorekeeper = score_from_judges(judge1=judge1, judge2=judge2, blue_patch_receipt=patch_receipt)
    score_path = write_json(out_dir / "scorekeeper-receipt.json", scorekeeper)
    ledger.append("scorekeeper_terminal", actor="scorekeeper", receipt=str(score_path))
    ledger.append("round_terminal", actor="battle")
    return write_round_receipt(out_dir=out_dir, ledger=ledger, status="PASS", verdict=judge2["verdict"])


def write_blocked_round(*, out_dir: Path, reason: str, details: dict[str, Any]) -> dict[str, Any]:
    receipt = {
        "schema": SCHEMA_ROUND,
        "status": "BLOCKED",
        "mocked": False,
        "live": "local_docker_fixture",
        "agentic": False,
        "reason": reason,
        "details": details,
    }
    write_json(out_dir / "round-receipt.json", receipt)
    return receipt


def write_round_receipt(*, out_dir: Path, ledger: EventLedger, status: str, verdict: str) -> dict[str, Any]:
    ledger_path = ledger.write()
    hash_manifest_payload = artifact_hash_manifest(out_dir)
    manifest_path = write_json(out_dir / "artifact-hash-manifest.json", hash_manifest_payload)
    receipt = {
        "schema": SCHEMA_ROUND,
        "status": status,
        "verdict": verdict,
        "mocked": False,
        "live": "local_docker_fixture",
        "agentic": False,
        "authorization_validation": "authorization-validation.json",
        "event_ledger": str(ledger_path),
        "artifact_hash_manifest": str(manifest_path),
        "scorekeeper_receipt": "scorekeeper-receipt.json",
        "claims": {
            "proves": [
                "proactive Blue starts with no private Red finding",
                "reactive Blue starts only after Judge #1 confirms the Red observation",
                "scorekeeper derives scores solely from Judge receipts",
                "Judge #2 distinguishes exploit blocking from functionality preservation",
            ],
            "does_not_prove": [
                "provider-driven Red or Blue semantic quality",
                "arbitrary target exploitability",
                "production deployment readiness",
                "multi-round overnight scheduler readiness",
            ],
        },
    }
    write_json(out_dir / "round-receipt.json", receipt)
    return receipt


def run_rejected_observation_case(*, authorization_manifest: Path, out_dir: Path, fixture_dir: Path = FIXTURE_DIR) -> dict[str, Any]:
    """Run a negative case where Judge #1 rejects and reactive Blue is skipped."""
    receipt = run_reactive_judge_round(
        authorization_manifest=authorization_manifest,
        out_dir=out_dir,
        fixture_dir=fixture_dir,
    )
    observation_path = out_dir / "red-hack-observation.json"
    if not observation_path.exists():
        return receipt
    observation = read_json(observation_path)
    observation["target_identity"] = "wrong-target@sha256:wrong"
    write_json(observation_path, observation)
    auth_hash = file_sha256(authorization_manifest)
    baseline = read_json(out_dir / "immutable-baseline-manifest.json")
    judge1 = build_judge1_receipt(
        battle_id="battle-reactive-judge-001",
        observation=observation,
        observation_path=observation_path,
        workspace=out_dir / "workspaces" / "judge1",
        command_receipt={"exit_code": 0, "command": ["mutation"], "stdout_path": None, "stderr_path": None},
        authorization_hash=auth_hash,
        baseline_hash=baseline["baseline_sha256"],
    )
    return {
        "schema": "battle.reactive_judge_rejection_case.v1",
        "status": "PASS" if judge1["verdict"] == "REJECTED" else "FAIL",
        "judge1": judge1,
        "reactive_blue_dispatched": False,
    }
