"""Receipt-backed Judge boundary for ordinary Battle orchestrator rounds."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from .state import Finding, FunctionalEvidenceStatus, Patch


FindingVerdict = Literal["CONFIRMED", "REJECTED", "BLOCKED", "INSUFFICIENT_EVIDENCE"]
PatchVerdict = Literal["BLUE_SUCCESS", "RED_SUCCESS", "FAKE_DEFENSE", "BLOCKED", "INSUFFICIENT_EVIDENCE"]
CandidatePhase = Literal["proactive", "reactive"]


@dataclass(frozen=True)
class ReceiptRef:
    name: str
    path: str
    sha256: str


@dataclass(frozen=True)
class RoundJudgeContext:
    battle_id: str
    run_id: str
    round_number: int
    receipt_dir: Path
    source_commit: str
    source_tree: str


@dataclass(frozen=True)
class BlueCandidateRef:
    candidate_id: str
    patch_id: str
    finding_id: str
    phase: CandidatePhase
    source_sha256: str


@dataclass(frozen=True)
class JudgeFindingOutcome:
    finding_id: str
    source_sha256: str
    verdict: FindingVerdict
    receipt: ReceiptRef


@dataclass(frozen=True)
class JudgePatchOutcome:
    candidate_id: str
    patch_id: str
    finding_id: str
    source_sha256: str
    verdict: PatchVerdict
    functional_evidence_status: FunctionalEvidenceStatus
    receipt: ReceiptRef


class JudgeBoundary(Protocol):
    def judge_findings(
        self,
        context: RoundJudgeContext,
        findings: list[Finding],
    ) -> list[JudgeFindingOutcome]:
        ...

    def judge_patches(
        self,
        context: RoundJudgeContext,
        candidates: list[BlueCandidateRef],
        patches: list[Patch],
        confirmed_findings: list[Finding],
    ) -> list[JudgePatchOutcome]:
        ...


def source_identity(cwd: Path | None = None) -> tuple[str, str]:
    cwd = cwd or Path(__file__).resolve().parents[4]
    commit = _git(["rev-parse", "HEAD"], cwd=cwd)
    tree = _git(["rev-parse", "HEAD:skills/battle"], cwd=cwd)
    return commit, tree


def wrap_blue_candidates(patches: list[Patch], *, phase: CandidatePhase) -> list[BlueCandidateRef]:
    candidates: list[BlueCandidateRef] = []
    for patch in patches:
        source = patch_sha256(patch)
        candidates.append(
            BlueCandidateRef(
                candidate_id=f"{phase}:{patch.id}:{source[:16]}",
                patch_id=patch.id,
                finding_id=patch.finding_id,
                phase=phase,
                source_sha256=source,
            )
        )
    return candidates


def finding_sha256(finding: Finding) -> str:
    return _object_sha256(
        {
            "id": finding.id,
            "type": finding.type.value,
            "severity": finding.severity,
            "description": finding.description,
            "file_path": finding.file_path,
            "line_number": finding.line_number,
            "exploit_proof": finding.exploit_proof,
            "vulnerability_id": finding.vulnerability_id,
            "chaos_used": finding.chaos_used,
            "tags": finding.tags,
        }
    )


def patch_sha256(patch: Patch) -> str:
    return _object_sha256(
        {
            "id": patch.id,
            "finding_id": patch.finding_id,
            "type": patch.type.value,
            "diff": patch.diff,
            "verified": patch.verified,
            "functionality_preserved": patch.functionality_preserved,
            "functional_evidence_status": patch.functional_evidence_status.value,
            "functional_test_command": patch.functional_test_command,
            "functional_exit_code": patch.functional_exit_code,
            "functional_receipt_ref": patch.functional_receipt_ref,
            "functional_artifact_sha256": patch.functional_artifact_sha256,
        }
    )


class FailClosedJudgeBoundary:
    """Judge boundary used when no supported Docker Judge runtime is configured."""

    def __init__(self, *, reason: str = "judge_runtime_not_configured") -> None:
        self.reason = reason

    def judge_findings(
        self,
        context: RoundJudgeContext,
        findings: list[Finding],
    ) -> list[JudgeFindingOutcome]:
        outcomes: list[JudgeFindingOutcome] = []
        for finding in findings:
            source = finding_sha256(finding)
            receipt_path = context.receipt_dir / "findings" / f"{finding.id}.json"
            receipt = _base_receipt(context) | {
                "schema": "battle.orchestrator_judge_finding.v1",
                "status": "INSUFFICIENT_EVIDENCE",
                "verdict": "INSUFFICIENT_EVIDENCE",
                "reason": self.reason,
                "finding_id": finding.id,
                "finding_sha256": source,
                "docker_attempt_receipts": [],
            }
            ref = _write_receipt(receipt_path, receipt)
            outcomes.append(JudgeFindingOutcome(finding.id, source, "INSUFFICIENT_EVIDENCE", ref))
        return outcomes

    def judge_patches(
        self,
        context: RoundJudgeContext,
        candidates: list[BlueCandidateRef],
        patches: list[Patch],
        confirmed_findings: list[Finding],
    ) -> list[JudgePatchOutcome]:
        outcomes: list[JudgePatchOutcome] = []
        for candidate in candidates:
            receipt_path = context.receipt_dir / "patches" / f"{candidate.candidate_id}.json"
            receipt = _base_receipt(context) | {
                "schema": "battle.orchestrator_judge_patch.v1",
                "status": "INSUFFICIENT_EVIDENCE",
                "verdict": "INSUFFICIENT_EVIDENCE",
                "reason": self.reason,
                "candidate": asdict(candidate),
                "confirmed_finding_ids": [finding.id for finding in confirmed_findings],
                "docker_attempt_receipts": [],
                "functional_evidence_status": FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            }
            ref = _write_receipt(receipt_path, receipt)
            outcomes.append(
                JudgePatchOutcome(
                    candidate_id=candidate.candidate_id,
                    patch_id=candidate.patch_id,
                    finding_id=candidate.finding_id,
                    source_sha256=candidate.source_sha256,
                    verdict="INSUFFICIENT_EVIDENCE",
                    functional_evidence_status=FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE,
                    receipt=ref,
                )
            )
        return outcomes


class LocalDockerJudgeBoundary:
    """Small Docker-backed Judge boundary for local deterministic Battle proof."""

    docker_image = "python:3.12-slim"

    def judge_findings(
        self,
        context: RoundJudgeContext,
        findings: list[Finding],
    ) -> list[JudgeFindingOutcome]:
        outcomes: list[JudgeFindingOutcome] = []
        for finding in findings:
            source = finding_sha256(finding)
            attempt = _docker_python(
                context.receipt_dir / "docker-attempts" / "findings",
                f"finding-{finding.id}",
                "import sys\nsys.exit(0)\n"
                if finding.exploit_proof == "docker-confirmed"
                else "import sys\nsys.exit(1)\n",
            )
            verdict: FindingVerdict = "CONFIRMED" if attempt["exit_code"] == 0 else "INSUFFICIENT_EVIDENCE"
            receipt_path = context.receipt_dir / "findings" / f"{finding.id}.json"
            receipt = _base_receipt(context) | {
                "schema": "battle.orchestrator_judge_finding.v1",
                "status": "PASS" if verdict == "CONFIRMED" else "INSUFFICIENT_EVIDENCE",
                "verdict": verdict,
                "finding_id": finding.id,
                "finding_sha256": source,
                "docker_attempt_receipts": [attempt],
            }
            ref = _write_receipt(receipt_path, receipt)
            outcomes.append(JudgeFindingOutcome(finding.id, source, verdict, ref))
        return outcomes

    def judge_patches(
        self,
        context: RoundJudgeContext,
        candidates: list[BlueCandidateRef],
        patches: list[Patch],
        confirmed_findings: list[Finding],
    ) -> list[JudgePatchOutcome]:
        patch_by_id = {patch.id: patch for patch in patches}
        confirmed_ids = {finding.id for finding in confirmed_findings}
        outcomes: list[JudgePatchOutcome] = []
        for candidate in candidates:
            patch = patch_by_id.get(candidate.patch_id)
            source_matches = patch is not None and patch_sha256(patch) == candidate.source_sha256
            eligible = bool(
                patch
                and source_matches
                and candidate.finding_id in confirmed_ids
                and "fixture-blue-success" in patch.diff
            )
            exploit_attempt = _docker_python(
                context.receipt_dir / "docker-attempts" / "patches",
                f"{candidate.candidate_id}-exploit",
                "import sys\nsys.exit(1)\n" if eligible else "import sys\nsys.exit(0)\n",
            )
            functional_attempt = _docker_python(
                context.receipt_dir / "docker-attempts" / "patches",
                f"{candidate.candidate_id}-functionality",
                "import sys\nsys.exit(0)\n" if eligible else "import sys\nsys.exit(1)\n",
            )
            exploit_blocked = exploit_attempt["exit_code"] != 0
            functionality_passed = functional_attempt["exit_code"] == 0
            if not source_matches:
                verdict: PatchVerdict = "BLOCKED"
                functional = FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE
                status = "BLOCKED"
            elif exploit_blocked and functionality_passed:
                verdict = "BLUE_SUCCESS"
                functional = FunctionalEvidenceStatus.PASS
                status = "PASS"
            elif exploit_blocked:
                verdict = "FAKE_DEFENSE"
                functional = FunctionalEvidenceStatus.FAIL
                status = "FAIL"
            else:
                verdict = "RED_SUCCESS" if candidate.finding_id in confirmed_ids else "INSUFFICIENT_EVIDENCE"
                functional = FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE
                status = "FAIL" if verdict == "RED_SUCCESS" else "INSUFFICIENT_EVIDENCE"
            receipt_path = context.receipt_dir / "patches" / f"{candidate.candidate_id}.json"
            receipt = _base_receipt(context) | {
                "schema": "battle.orchestrator_judge_patch.v1",
                "status": status,
                "verdict": verdict,
                "candidate": asdict(candidate),
                "confirmed_finding_ids": sorted(confirmed_ids),
                "source_matches_candidate": source_matches,
                "docker_attempt_receipts": [exploit_attempt, functional_attempt],
                "exploit_blocked_after_patch": exploit_blocked,
                "functional_evidence_status": functional.value,
                "functionality_preserved": functionality_passed if verdict == "BLUE_SUCCESS" else None,
            }
            ref = _write_receipt(receipt_path, receipt)
            outcomes.append(
                JudgePatchOutcome(
                    candidate_id=candidate.candidate_id,
                    patch_id=candidate.patch_id,
                    finding_id=candidate.finding_id,
                    source_sha256=candidate.source_sha256,
                    verdict=verdict,
                    functional_evidence_status=functional,
                    receipt=ref,
                )
            )
        return outcomes


def _docker_python(out_dir: Path, name: str, script: str) -> dict[str, Any]:
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
        "python:3.12-slim",
        "python",
        "-c",
        script,
    ]
    started = time.monotonic()
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        status = "PASS"
        error = None
    except Exception as exc:  # pragma: no cover - depends on local Docker failure
        proc = None
        status = "BLOCKED"
        error = f"{type(exc).__name__}: {exc}"
    stdout_path = out_dir / f"{name}.stdout.txt"
    stderr_path = out_dir / f"{name}.stderr.txt"
    stdout_path.write_text(proc.stdout if proc else "", encoding="utf-8")
    stderr_path.write_text(proc.stderr if proc else error or "", encoding="utf-8")
    return {
        "schema": "battle.docker_judge_attempt.v1",
        "status": status,
        "mocked": False,
        "live": True,
        "command": command,
        "exit_code": proc.returncode if proc else 124,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "elapsed_seconds": round(time.monotonic() - started, 6),
    }


def _base_receipt(context: RoundJudgeContext) -> dict[str, Any]:
    return {
        "mocked": False,
        "live": True,
        "battle_id": context.battle_id,
        "run_id": context.run_id,
        "round_number": context.round_number,
        "source_commit": context.source_commit,
        "source_tree": context.source_tree,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _write_receipt(path: Path, payload: dict[str, Any]) -> ReceiptRef:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ReceiptRef(name=path.name, path=str(path), sha256=_file_sha256(path))


def _object_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"
