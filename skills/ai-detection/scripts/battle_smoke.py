#!/usr/bin/env python3
"""Run the retained, mechanism-only ai-detection Battle smoke campaign.

Candidate source is parsed on the host and executed only by the networkless
Docker command below. This is a fixed provenance-known fixture, not evidence of
real-world authorship detection or detector efficacy.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT.parent
BATTLE_SRC = SKILLS / "battle" / "src"
for path in (ROOT / "src", ROOT / "tests", SKILLS):
    sys.path.insert(0, str(path))
sys.path.insert(0, str(BATTLE_SRC))

from ai_detection.model import model_digest, save_model, train  # noqa: E402
from battle_skill.invariant_judge import run_judge  # noqa: E402
from common.security_authorization import validate_target_authorization  # noqa: E402
from helpers import corpus  # noqa: E402

CANDIDATES = ROOT / "fixtures" / "battle-smoke"
AUTHORIZATION = ROOT / "battle" / "authorization.json"
JUDGE = ROOT / "battle" / "detector_judge.py"
IMAGE = "python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9"
TARGET = "ai-detection-battle-smoke@candidate-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def observations(source: str) -> list[dict[str, str]]:
    tree = ast.parse(source)  # Deliberately parse-only: never execute candidate source on host.
    result: list[dict[str, str]] = []
    if ast.get_docstring(tree):
        result.append({"code": "verbose_module_docstring", "cause": "module docstring narrates fixture provenance"})
    comments = sum(line.lstrip().startswith("#") for line in source.splitlines())
    if comments:
        result.append({"code": "excessive_narrative_comments", "cause": f"{comments} narrative comments"})
    names = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if any(len(name) > 32 for name in names):
        result.append({"code": "overlong_identifier", "cause": "function names exceed 32 characters"})
    if len(names) > 1 and any(ast.get_docstring(node) for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        result.append({"code": "redundant_explanatory_docstrings", "cause": "simple helpers repeat explanatory docstrings"})
    return result


def docker_behavior(source: Path, out: Path) -> dict[str, Any]:
    workspace = out / "docker-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    candidate = workspace / "candidate.py"
    shutil.copyfile(source, candidate)
    command = [
        "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "65534:65534",
        "--pids-limit", "64", "--memory", "128m",
        "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "-v", f"{workspace.resolve()}:/workspace:ro", "-w", "/workspace", IMAGE,
        "python", "candidate.py", "41",
    ]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    stdout = out / f"docker-{source.stem}.stdout.txt"
    stderr = out / f"docker-{source.stem}.stderr.txt"
    stdout.write_text(proc.stdout, encoding="utf-8")
    stderr.write_text(proc.stderr, encoding="utf-8")
    return {
        "schema": "battle.docker_behavior_receipt.v1",
        "source_sha256": sha256(source), "command": command, "network": "none",
        "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr,
        "stdout_sha256": sha256(stdout), "stderr_sha256": sha256(stderr),
        "expected_stdout": '{"result": 42}\n',
        "passed": proc.returncode == 0 and proc.stdout == '{"result": 42}\n',
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "evidence" / "battle-smoke-eval")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    authorization = validate_target_authorization(
        AUTHORIZATION, expected_target=TARGET, requested_action="battle",
        requested_runtime_mode="local_docker_fixture", requested_probe_class="code_behavior_equivalence",
        receipt_out=out / "authorization-validation.json",
    )
    if authorization["status"] != "PASS":
        write(out / "campaign.json", {"schema": "ai_detection.battle_smoke.v1", "terminal_state": "blocked_authorization", "authorization": authorization, "mechanism_only": True, "efficacy": "NOT_ESTABLISHED"})
        return 1

    baseline, repaired = CANDIDATES / "agent_written_verbose.py", CANDIDATES / "repaired.py"
    baseline_observations, repaired_observations = observations(baseline.read_text()), observations(repaired.read_text())
    write(out / "baseline-observations.json", {"schema": "ai_detection.violation_observations.v1", "source_sha256": sha256(baseline), "provenance": "agent_authored_fixture", "observations": baseline_observations})
    write(out / "repaired-observations.json", {"schema": "ai_detection.violation_observations.v1", "source_sha256": sha256(repaired), "observations": repaired_observations})

    model, _ = train(corpus())
    model = model.model_copy(update={"created_at": "2026-09-19T00:00:00Z"})
    model_path = out / "frozen-synthetic-model.json"
    save_model(model_path, model)
    params = {"model_path": str(model_path), "threshold": model.calibration.threshold}
    write(out / "frozen-detector-panel.json", {"schema": "ai_detection.frozen_detector_panel.v1", "model_sha256": model_digest(model), "model_file_sha256": sha256(model_path), "threshold": model.calibration.threshold, "synthetic_training": True, "efficacy": "NOT_ESTABLISHED"})

    before_behavior, after_behavior = docker_behavior(baseline, out), docker_behavior(repaired, out)
    write(out / "docker-before.json", before_behavior)
    write(out / "docker-after.json", after_behavior)
    baseline_target, repaired_target = out / "judge-baseline", out / "judge-repaired"
    baseline_target.mkdir(exist_ok=True)
    repaired_target.mkdir(exist_ok=True)
    shutil.copyfile(baseline, baseline_target / "candidate.py")
    shutil.copyfile(repaired, repaired_target / "candidate.py")
    before_judge = run_judge(str(JUDGE), str(baseline_target), params).to_dict()
    after_judge = run_judge(str(JUDGE), str(repaired_target), params).to_dict()
    write(out / "judge-before.json", before_judge)
    write(out / "judge-after.json", after_judge)

    behavior_preserved = before_behavior["passed"] and after_behavior["passed"] and before_behavior["stdout"] == after_behavior["stdout"]
    detector_invariant_preserved = before_judge["passed"] and after_judge["passed"]
    if not behavior_preserved:
        terminal = "behavior_regression"
    elif not detector_invariant_preserved:
        terminal = "detector_invariant_failed"
    else:
        terminal = "mechanism_smoke_complete"
    campaign = {
        "schema": "ai_detection.battle_smoke.v1", "campaign_id": "ai-detection-battle-smoke-001",
        "terminal_state": terminal, "mechanism_only": True, "efficacy": "NOT_ESTABLISHED",
        "deslop_scope": {
            "covered": ["extra-comments", "generated-docs", "style-inconsistency"],
            "not_applicable": ["any-cast", "defensive-checks", "ui-slop"],
            "reused_instead_of_reinvented": ["authorization validator", "Battle invariant Judge"],
        },
        "does_not_prove": ["human authorship", "real-world detector efficacy", "qualified-detector evasion"],
        "authorization_manifest_sha256": sha256(AUTHORIZATION), "baseline_source_sha256": sha256(baseline),
        "repaired_source_sha256": sha256(repaired), "frozen_model_sha256": sha256(model_path),
        "behavior_preserved": behavior_preserved, "detector_invariant_preserved": detector_invariant_preserved,
        "baseline_violation_count": len(baseline_observations),
        "repaired_violation_count": len(repaired_observations), "judge_before_passed": before_judge["passed"],
        "judge_after_passed": after_judge["passed"],
    }
    write(out / "campaign.json", campaign)
    receipt_hashes = {path.name: sha256(path) for path in sorted(out.glob("*.json")) if path.name != "receipt-manifest.json"}
    write(out / "receipt-manifest.json", {"schema": "battle.receipt_manifest.v1", "campaign_sha256": sha256(out / "campaign.json"), "artifacts": receipt_hashes})
    print(json.dumps(campaign, sort_keys=True))
    return 0 if terminal == "mechanism_smoke_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
