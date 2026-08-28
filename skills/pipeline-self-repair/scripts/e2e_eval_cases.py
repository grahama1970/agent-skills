#!/usr/bin/env python3
"""End-to-end agentic-evals cases for pipeline-self-repair.

Each command drives the public ``run.sh`` entrypoint and then independently reads
back the artifact it claims to have produced. External mutations are not used:
GitHub is queried read-only, tickets are previewed, and provider/Kling effects are
represented by explicit request/response/artifact capsules rather than paid
submissions.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[1]
RUN_SH = SKILL_DIR / "run.sh"
OUT_ROOT = Path("/tmp/pipeline-self-repair-e2e")
REPO = "grahama1970/agent-skills"


def _reset_case(name: str) -> Path:
    root = OUT_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


def _run(args: list[str], *, stdout_path: Path | None = None, expected: int = 0) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, text=True, capture_output=True, check=False)
    if stdout_path is not None:
        stdout_path.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != expected:
        raise AssertionError(
            f"command exit {proc.returncode} != {expected}: {args}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _record(root: Path, *extra: str, signal: str, layer: str, pipeline: str, step_id: str, target: str) -> dict[str, Any]:
    out = root / "record.json"
    ledger = root / "replay_ledger.jsonl"
    cmd = [
        str(RUN_SH),
        "record-failure",
        "--pipeline",
        pipeline,
        "--step-id",
        step_id,
        "--run-id",
        f"e2e-{root.name}",
        "--raw-signal",
        signal,
        "--layer",
        layer,
        "--target",
        target,
        "--run-root",
        str(root),
        "--ledger",
        str(ledger),
        "--repo",
        REPO,
        "--json",
        *extra,
    ]
    _run(cmd, stdout_path=out)
    data = _json(out)
    ledger_line = json.loads(ledger.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert data["event"]["event_hash"] == ledger_line["event_hash"]
    return data


def full_branch() -> None:
    """Known failure goes through triage, memory recall, GitHub issue search, and ticket binding."""
    root = _reset_case("full_branch")
    data = _record(
        root,
        signal="nightly_revision_mismatch expected abc got def",
        layer="monitor-opportunities",
        pipeline="monitor-opportunities",
        step_id="nightly_publish",
        target="skills/monitor-opportunities",
    )
    event = data["event"]
    assert data["status"] == "RECORDED_REPAIR_REQUIRED", data
    assert event["triage"]["code"] == "monitor_opportunities_nightly_revision_mismatch", event["triage"]
    assert event["triage"]["ambiguous"] is False, event["triage"]
    assert event["goal_alignment"]["status"] == "PASS_COMPARED_TO_IMMUTABLE_GOAL", event["goal_alignment"]
    assert event["goal_alignment"]["goal_hash"].startswith("sha256:"), event["goal_alignment"]
    assert event["memory_recall"]["status"] == "PASS", event["memory_recall"]
    assert event["memory_recall"].get("found") is True, event["memory_recall"]
    assert event["github_issue_search"]["status"] == "PASS", event["github_issue_search"]
    assert len(event["github_issue_search"].get("matches", [])) >= 1, event["github_issue_search"]
    assert event["ticket"]["action"] in {"bind_existing", "needs_reopen", "blocked_by_upstream"}, event["ticket"]
    assert event["repair_state"] in {"TICKETED", "NEEDS_HUMAN", "BLOCKED_BY_UPSTREAM"}, event["repair_state"]
    print("PIPELINE_SELF_REPAIR_FULL_BRANCH_E2E_OK")


def provider_unknown_blocks_resubmit() -> None:
    """Unknown paid-provider effect blocks blind retry and records hashes."""
    root = _reset_case("provider_unknown")
    request = root / "kling_request.json"
    response = root / "kling_response.json"
    artifact = root / "dream-preview.mp4"
    request.write_text(json.dumps({"prompt": "render required dream scene", "provider": "kling"}), encoding="utf-8")
    response.write_text(json.dumps({"status": "unknown", "task_id": None}), encoding="utf-8")
    artifact.write_bytes(b"not-real-video-but-content-addressed-artifact")
    data = _record(
        root,
        "--skip-memory",
        "--skip-github",
        "--no-ticket",
        "--request-body",
        str(request),
        "--provider-response",
        str(response),
        "--local-artifact",
        str(artifact),
        "--media-url",
        "https://provider.invalid/kling/task/unknown",
        "--spend-state",
        "unknown",
        signal="Kling provider submit returned no durable task id; effect state unknown",
        layer="kling",
        pipeline="persona-dream",
        step_id="phase_11_kling_submit",
        target="skills/persona-dream",
    )
    effect = data["event"]["provider_effect"]
    assert data["event"]["repair_state"] == "NEEDS_HUMAN", data["event"]["repair_state"]
    assert effect["spend_state"] == "unknown", effect
    assert effect["resubmission_allowed"] is False, effect
    assert effect["next_legal_command"] == "reconcile_provider_effect_before_resubmit", effect
    assert effect["request_body"]["sha256"].startswith("sha256:"), effect
    assert effect["provider_response"]["sha256"].startswith("sha256:"), effect
    assert effect["local_artifacts"][0]["sha256"].startswith("sha256:"), effect
    print("PIPELINE_SELF_REPAIR_PROVIDER_UNKNOWN_E2E_OK")


def provider_task_id_blocks_duplicate_submit() -> None:
    """A provider task id forces poll/reconcile rather than another submit."""
    root = _reset_case("provider_task_id")
    data = _record(
        root,
        "--skip-memory",
        "--skip-github",
        "--no-ticket",
        "--provider-task-id",
        "kling-task-123",
        "--spend-state",
        "intended",
        signal="Kling accepted request but downstream media retrieval failed",
        layer="kling",
        pipeline="persona-dream",
        step_id="phase_11_kling_poll",
        target="skills/persona-dream",
    )
    effect = data["event"]["provider_effect"]
    assert effect["provider_task_id"] == "kling-task-123", effect
    assert effect["resubmission_allowed"] is False, effect
    assert effect["next_legal_command"] == "poll_or_reconcile_existing_task", effect
    print("PIPELINE_SELF_REPAIR_PROVIDER_TASK_ID_E2E_OK")


def missing_immutable_goal_fails_preflight() -> None:
    """A pipeline without a registered human immutable goal cannot enter self-repair."""
    root = _reset_case("missing_immutable_goal")
    ledger = root / "replay_ledger.jsonl"
    out = root / "record.stdout"
    err = root / "record.stderr"
    proc = subprocess.run(
        [
            str(RUN_SH),
            "record-failure",
            "--pipeline",
            "no-such-immutable-goal-project",
            "--step-id",
            "phase_01",
            "--run-id",
            "e2e-missing-goal",
            "--raw-signal",
            "expected complex pipeline failure",
            "--target",
            "skills/no-such-immutable-goal-project",
            "--run-root",
            str(root),
            "--ledger",
            str(ledger),
            "--skip-memory",
            "--skip-github",
            "--no-ticket",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    out.write_text(proc.stdout, encoding="utf-8")
    err.write_text(proc.stderr, encoding="utf-8")
    assert proc.returncode == 2, proc.stderr + proc.stdout
    assert "immutable goal preflight failed" in proc.stderr, proc.stderr
    assert not ledger.exists(), "preflight failure must not append a repair ledger event"
    (root / "preflight.json").write_text(
        json.dumps({"status": "PASS_MISSING_IMMUTABLE_GOAL_REFUSED", "returncode": proc.returncode, "ledger_exists": ledger.exists()}),
        encoding="utf-8",
    )
    print("PIPELINE_SELF_REPAIR_MISSING_GOAL_PREFLIGHT_OK")


def validate_blocks_without_eval() -> None:
    """Checkpoint/resume validation fails when retained agentic-evals proof is missing."""
    root = _reset_case("validate_blocks_without_eval")
    ledger = root / "replay_ledger.jsonl"
    _record(
        root,
        "--skip-memory",
        "--skip-github",
        signal="preflight_logged_out auth/login logged_out",
        layer="surf",
        pipeline="persona-dream",
        step_id="webgpt_review",
        target="skills/persona-dream",
    )
    out = root / "validate.json"
    proc = _run(
        [str(RUN_SH), "validate-ledger", "--ledger", str(ledger), "--require-agentic-eval", "--json"],
        stdout_path=out,
        expected=1,
    )
    result = _json(out)
    assert result["status"] == "FAIL", result
    assert any("lacks retained agentic-evals" in item for item in result["failures"]), result
    assert proc.returncode == 1
    print("PIPELINE_SELF_REPAIR_VALIDATE_BLOCKS_WITHOUT_EVAL_OK")


def validate_accepts_eval_ticket_disposition() -> None:
    """Ledger validation accepts a repair event only after ticket disposition plus eval proof ref."""
    root = _reset_case("validate_accepts_eval")
    report = root / "retained-agentic-report.json"
    report.write_text(
        json.dumps({"schema": "agentic_evals.report.v2", "readiness": "READY", "cases": []}),
        encoding="utf-8",
    )
    ledger = root / "replay_ledger.jsonl"
    _record(
        root,
        "--skip-memory",
        "--skip-github",
        "--agentic-eval-report",
        str(report),
        signal="preflight_logged_out auth/login logged_out",
        layer="surf",
        pipeline="persona-dream",
        step_id="webgpt_review",
        target="skills/persona-dream",
    )
    out = root / "validate.json"
    _run([str(RUN_SH), "validate-ledger", "--ledger", str(ledger), "--require-agentic-eval", "--json"], stdout_path=out)
    result = _json(out)
    assert result["status"] == "PASS", result
    assert result["failure_count"] == 0, result
    print("PIPELINE_SELF_REPAIR_VALIDATE_ACCEPTS_EVAL_OK")


def agentic_eval_remediate_preview() -> None:
    """A failed agentic-evals report is projected through the real remediate preview path."""
    root = _reset_case("agentic_eval_remediate")
    report = root / "failing-agentic-report.json"
    report.write_text(
        json.dumps(
            {
                "schema": "agentic_evals.report.v2",
                "source": "skills/pipeline-self-repair/fixtures/agentic_eval.json",
                "run_id": "e2e-failing-report",
                "cases": [
                    {
                        "case_id": "e2e-c000",
                        "name": "record_failure_dry_run_writes_replay_ledger",
                        "required": True,
                        "outcome": "FAIL",
                        "category": "agentic-evals:agent-skills:pipeline-self-repair-ledger-recording",
                        "seams": ["self_repair.ledger"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger = root / "replay_ledger.jsonl"
    out = root / "remediate.json"
    _run(
        [
            str(RUN_SH),
            "agentic-eval-remediate",
            "--report",
            str(report),
            "--category-map",
            str(SKILL_DIR / "fixtures" / "category_map.json"),
            "--fixture",
            str(SKILL_DIR / "fixtures" / "agentic_eval.json"),
            "--ledger",
            str(ledger),
            "--goal-project",
            "persona-dream",
            "--goal-context",
            "operational_value_disposition fail-closed repair loop for persona-dream-style pipelines",
            "--json",
        ],
        stdout_path=out,
    )
    data = _json(out)
    assert data["status"] == "PASS", data
    event = data["event"]
    assert event["event_type"] == "agentic_eval.remediation_projected", event
    assert event["ticket"]["action"] == "agentic_evals_remediate_preview", event["ticket"]
    assert event["ticket"]["result"]["returncode"] == 0, event["ticket"]
    assert event["goal_alignment"]["status"] == "PASS_COMPARED_TO_IMMUTABLE_GOAL", event["goal_alignment"]
    print("PIPELINE_SELF_REPAIR_AGENTIC_REMEDIATE_E2E_OK")


CASES = {
    "full-branch": full_branch,
    "provider-unknown-blocks-resubmit": provider_unknown_blocks_resubmit,
    "provider-task-id-blocks-duplicate-submit": provider_task_id_blocks_duplicate_submit,
    "missing-immutable-goal-fails-preflight": missing_immutable_goal_fails_preflight,
    "validate-blocks-without-eval": validate_blocks_without_eval,
    "validate-accepts-eval-ticket-disposition": validate_accepts_eval_ticket_disposition,
    "agentic-eval-remediate-preview": agentic_eval_remediate_preview,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=sorted(CASES))
    args = parser.parse_args(argv)
    CASES[args.case]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
