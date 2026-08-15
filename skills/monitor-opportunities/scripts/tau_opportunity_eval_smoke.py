"""Tau local creator/reviewer smoke over one monitor-opportunities report item.

This proves Tau can execute the monitor's evaluator/reviewer artifact loop over
real report data. It is intentionally deterministic and local: it does not claim
provider/model semantic quality, hidden ATS knowledge, or final shortlist
correctness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


VERDICTS = {"KEEP", "REJECT", "ADJACENT", "CLIENT_SIGNAL", "NEEDS_REVIEW"}
SCRIPT = Path(__file__).resolve()
IMMUTABLE_GOAL = (
    "Daily top opportunities that are highly targeted, delivered in an interactive "
    "report/interview, with human-authorized application preparation using a custom targeted resume given the "
    "algorithm likely employed by the employer or client."
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _first_report_opportunity(report: dict[str, Any]) -> dict[str, Any]:
    for item in report.get("opportunities", []):
        if item.get("visible_in_report") is not False:
            return item
    raise RuntimeError("report_has_no_visible_opportunities")


def _opportunity_evidence(opportunity: dict[str, Any]) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    for idx, text in enumerate(opportunity.get("why_candidate") or []):
        if isinstance(text, str) and text.strip():
            quotes.append({"source": "why_candidate", "index": idx, "quote": text.strip()[:500]})
    profile = opportunity.get("screening_interface_profile")
    if isinstance(profile, dict):
        for idx, text in enumerate(profile.get("observed") or []):
            if isinstance(text, str) and text.strip():
                quotes.append({"source": "screening_interface_profile.observed", "index": idx, "quote": text.strip()[:500]})
    return quotes


def _fit_score(opportunity: dict[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(opportunity.get("fit_score") or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _verdict(opportunity: dict[str, Any]) -> str:
    opp_type = str(opportunity.get("opportunity_type") or "")
    if opp_type == "commercial_signal":
        return "CLIENT_SIGNAL"
    score = _fit_score(opportunity)
    if score >= 0.65:
        return "KEEP"
    if score >= 0.35:
        return "ADJACENT"
    return "NEEDS_REVIEW"


def _build_evaluation(opportunity: dict[str, Any], work_order: dict[str, Any]) -> dict[str, Any]:
    score = _fit_score(opportunity)
    evidence = _opportunity_evidence(opportunity)
    source_ids = opportunity.get("source_receipt_ids") or []
    return {
        "schema": "monitor_opportunities.opportunity_evaluation.v1",
        "status": "PASS",
        "opportunity_id": opportunity.get("opportunity_id") or opportunity.get("candidate_id"),
        "candidate_id": opportunity.get("candidate_id"),
        "title": opportunity.get("title"),
        "organization": opportunity.get("organization"),
        "opportunity_type": opportunity.get("opportunity_type"),
        "verdict": _verdict(opportunity),
        "mandate_fit": {
            "agentic_compliance": score,
            "document_extraction": score if evidence else 0.0,
            "agentic_pipelines": score,
            "verification": score if evidence else 0.0,
        },
        "seniority_scope": {
            "level": "principal_or_staff_plus" if score >= 0.65 else "unknown",
            "ownership": "report-derived",
            "hands_on_vs_managerial": "unknown",
        },
        "employment_type": "fte" if opportunity.get("opportunity_type") == "employment_posting" else "unknown",
        "workplace": (opportunity.get("location") or {}).get("workplace_type") or "unknown",
        "hard_requirements": {
            "clearance": "unknown",
            "citizenship": "unknown",
            "stack_gaps": [],
        },
        "evidence_quotes": evidence,
        "penalties": [],
        "unresolved_requirements": ["semantic JD-reading provider review not exercised"],
        "sources": source_ids,
        "jd_acquired": {
            "method": "report_manifest",
            "source_report_sha256": work_order["report_sha256"],
        },
        "confidence": min(0.75, max(0.25, score)),
        "memory_recall_attempted": False,
        "verified": True,
        "proof_scope": work_order["proof_scope"],
        "claims": work_order["claims"],
    }


def produce(args: argparse.Namespace) -> None:
    context_path = Path(os.environ["TAU_GENERIC_DAG_CONTEXT"])
    context = _read_json(context_path)
    context_sha256 = _sha256_path(context_path)
    if context_sha256 != os.environ["TAU_GENERIC_DAG_CONTEXT_SHA256"]:
        raise RuntimeError("attempt_context_hash_mismatch")

    work_order = _read_json(args.work_order)
    opportunity = work_order["opportunity"]
    evaluation = _build_evaluation(opportunity, work_order)

    artifact_root = args.artifact_root
    artifact_root.mkdir(parents=True, exist_ok=True)
    evaluation_path = artifact_root / "evaluation.json"
    _write_json(evaluation_path, evaluation)

    manifest_path = Path(context["output_contract"]["candidate_manifest_path"])
    manifest = {
        "schema": "tau.media_artifact_manifest.v1",
        "transaction_id": context["transaction_id"],
        "node_id": context["node_id"],
        "attempt": context["attempt"],
        "producer_id": context["producer_id"],
        "work_order_sha256": context["work_order"]["sha256"],
        "attempt_context_sha256": context_sha256,
        "artifacts": [
            {
                "artifact_id": "evaluation",
                "kind": "json",
                "media_type": "application/json",
                "path": str(evaluation_path.resolve()),
                "sha256": _sha256_path(evaluation_path),
                "bytes": evaluation_path.stat().st_size,
            }
        ],
    }
    _write_json(manifest_path, manifest)

    receipt = {
        "schema": "tau.generic_dag_node_receipt.v1",
        "node_id": context["node_id"],
        "status": "PASS",
        "verdict": "PASS",
        "mocked": False,
        "live": True,
        "provider_live": False,
        "artifacts": [str(evaluation_path.resolve())],
        "commands_run": ["monitor-opportunities deterministic evaluator producer"],
        "errors": [],
        "policy_exceptions": [],
        "handoff_summary": "Report-visible opportunity evaluation artifact produced.",
        "work_order_sha256": _sha256_path(args.work_order),
        "goal_hash": context.get("goal_hash"),
    }
    _write_json(args.receipt, receipt)


def validate(_args: argparse.Namespace) -> None:
    context_path = Path(os.environ["TAU_GENERIC_DAG_VALIDATION_CONTEXT"])
    context = _read_json(context_path)
    context_sha256 = _sha256_path(context_path)
    if context_sha256 != os.environ["TAU_GENERIC_DAG_VALIDATION_CONTEXT_SHA256"]:
        raise RuntimeError("validation_context_hash_mismatch")

    errors: list[str] = []
    manifest = _read_json(Path(context["candidate_manifest_path"]))
    artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else []
    if not artifacts:
        errors.append("candidate_manifest_artifacts_required")
    else:
        evaluation = _read_json(Path(artifacts[0]["path"]))
        if evaluation.get("schema") != "monitor_opportunities.opportunity_evaluation.v1":
            errors.append("unexpected_evaluation_schema")
        if evaluation.get("verdict") not in VERDICTS:
            errors.append("invalid_verdict")
        if not evaluation.get("evidence_quotes"):
            errors.append("evidence_quotes_required")
        if not evaluation.get("sources"):
            errors.append("sources_required")
        for key, value in (evaluation.get("mandate_fit") or {}).items():
            if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
                errors.append(f"mandate_fit_invalid:{key}")

    status = "PASS" if not errors else "FAIL"
    output = Path(context["output_contract"]["validation_receipt_path"])
    _write_json(
        output,
        {
            "schema": "tau.generic_artifact_validation.v1",
            "status": status,
            "node_id": context["node_id"],
            "transaction_id": context["transaction_id"],
            "attempt": context["attempt"],
            "validator_id": context["validator_id"],
            "validation_context_sha256": context_sha256,
            "candidate_manifest_sha256": context["candidate_manifest_sha256"],
            "goal_hash": context.get("goal_hash"),
            "errors": errors,
            "mocked": False,
            "live": True,
            "provider_live": False,
        },
    )
    if errors:
        raise SystemExit(1)


def review(_args: argparse.Namespace) -> None:
    context_path = Path(os.environ["TAU_GENERIC_DAG_REVIEW_CONTEXT"])
    context = _read_json(context_path)
    context_sha256 = _sha256_path(context_path)
    if context_sha256 != os.environ["TAU_GENERIC_DAG_REVIEW_CONTEXT_SHA256"]:
        raise RuntimeError("review_context_hash_mismatch")

    artifact = context["validated_artifacts"][0]
    evaluation = _read_json(Path(artifact["path"]))
    defects: list[dict[str, Any]] = []
    if evaluation.get("verdict") == "KEEP" and not evaluation.get("evidence_quotes"):
        defects.append(
            {
                "finding_id": "missing-evidence",
                "code": "FALSE_KEEP_NO_EVIDENCE",
                "severity": "ERROR",
                "message": "KEEP verdict has no report-derived evidence quotes.",
                "artifact_ids": ["evaluation"],
                "revision_instruction": "Provide source-backed evidence or downgrade the verdict.",
            }
        )
    if evaluation.get("verdict") not in VERDICTS:
        defects.append(
            {
                "finding_id": "invalid-verdict",
                "code": "INVALID_VERDICT",
                "severity": "ERROR",
                "message": "Evaluation verdict is outside the closed vocabulary.",
                "artifact_ids": ["evaluation"],
                "revision_instruction": "Use KEEP, REJECT, ADJACENT, CLIENT_SIGNAL, or NEEDS_REVIEW.",
            }
        )
    positive_scores = [
        key for key, value in (evaluation.get("mandate_fit") or {}).items() if isinstance(value, (int, float)) and value > 0
    ]
    if positive_scores and not evaluation.get("evidence_quotes"):
        defects.append(
            {
                "finding_id": "positive-score-without-quote",
                "code": "MANDATE_SCORE_UNBACKED",
                "severity": "ERROR",
                "message": "Positive mandate scores require source evidence.",
                "artifact_ids": ["evaluation"],
                "revision_instruction": "Attach report/source evidence or set unsupported scores to zero.",
            }
        )

    verdict = "PASS" if not defects else "REVISE"
    output = Path(context["output_contract"]["review_feedback_path"])
    _write_json(
        output,
        {
            "schema": "tau.generic_artifact_review.v1",
            "transaction_id": context["transaction_id"],
            "node_id": context["node_id"],
            "attempt": context["attempt"],
            "producer_id": context["producer_id"],
            "reviewer_id": context["reviewer_id"],
            "review_context_sha256": context_sha256,
            "candidate_manifest_sha256": context["candidate_manifest_sha256"],
            "goal_hash": context.get("goal_hash"),
            "verdict": verdict,
            "summary": "Deterministic reviewer accepted the report-bound evaluation." if verdict == "PASS" else "Evaluation needs changes.",
            "findings": defects,
            "mocked": False,
            "live": True,
            "provider_live": False,
            "review_execution_evidence": {
                "runtime_artifact_count": 1,
                "reviewer": "monitor-opportunities deterministic reviewer",
            },
        },
    )


def _build_dag(report_path: Path, out: Path, tau_root: Path) -> Path:
    report = _read_json(report_path)
    opportunity = _first_report_opportunity(report)
    report_sha256 = _sha256_path(report_path)
    proof_scope = "Tau local creator/reviewer plumbing over one report-visible opportunity."
    claims = {
        "proves": "Tau executed a local producer, validator, and reviewer over a real monitor-opportunities report item and admitted the evaluation artifact by receipt.",
        "does_not_prove": "Provider/model semantic quality, full per-opportunity JD-reading, learned ranking correctness, or ATS submission authority.",
    }
    work_order = {
        "schema": "monitor_opportunities.tau_evaluation_work_order.v1",
        "created_at": _utc_now(),
        "report_path": str(report_path.resolve()),
        "report_sha256": report_sha256,
        "opportunity": opportunity,
        "proof_scope": proof_scope,
        "claims": claims,
    }
    work_order_path = out / "work-order.json"
    _write_json(work_order_path, work_order)

    dag = {
        "schema": "tau.generic_dag_spec.v1",
        "run_id": "monitor-opportunities-tau-eval-smoke",
        "run_dir": str((out / "tau-run").resolve()),
        "goal_hash": "sha256:" + _sha256_text(IMMUTABLE_GOAL),
        "nodes": [
            {
                "node_id": "opportunity-evaluation",
                "role": "artifact-transaction",
                "command": [
                    sys.executable,
                    str(SCRIPT),
                    "produce",
                    "--artifact-root",
                    str((out / "artifacts").resolve()),
                    "--receipt",
                    str((out / "producer-receipt.json").resolve()),
                    "--work-order",
                    str(work_order_path.resolve()),
                ],
                "depends_on": [],
                "receipt_path": str((out / "producer-receipt.json").resolve()),
                "work_order_path": str(work_order_path.resolve()),
                "max_attempts": 1,
                "transaction": {
                    "schema": "tau.generic_artifact_transaction.v1",
                    "transaction_id": "tx-opportunity-evaluation",
                    "artifact_root": str((out / "artifacts").resolve()),
                    "producer_id": "opportunity-evaluator",
                    "validator": {
                        "validator_id": "deterministic-evaluation-validator",
                        "command": [sys.executable, str(SCRIPT), "validate"],
                    },
                    "reviewer": {
                        "reviewer_id": "opportunity-evaluation-reviewer",
                        "command": [sys.executable, str(SCRIPT), "review"],
                    },
                },
            }
        ],
        "extensions": {
            "monitor_opportunities": {
                "proof_boundary": {
                    "mocked": False,
                    "live": True,
                    "provider_live": False,
                    "claims": claims,
                },
                "tau_root": str(tau_root.resolve()),
            },
        },
    }
    dag_path = out / "dag.json"
    _write_json(dag_path, dag)
    return dag_path


def run(args: argparse.Namespace) -> None:
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    receipt_path = out / "tau-eval-smoke-receipt.json"
    dag_path = _build_dag(args.report.resolve(), out, args.tau_root.resolve())
    command = ["uv", "run", "--project", str(args.tau_root.resolve()), "tau", "dag-run", str(dag_path)]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout_seconds)
    process_receipt = {
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-8000:],
    }
    _write_json(out / "tau-process.json", process_receipt)
    if proc.returncode != 0:
        receipt = {
            "schema": "monitor_opportunities.tau_eval_smoke_receipt.v1",
            "status": "FAIL",
            "mocked": False,
            "live": True,
            "provider_live": False,
            "dag": str(dag_path),
            "error": proc.stderr[-2000:] or proc.stdout[-2000:],
            "external_effects": False,
        }
        _write_json(receipt_path, receipt)
        print(f"TAU_EVAL_SMOKE FAIL run={out} receipt={receipt_path}")
        raise SystemExit(1)
    try:
        tau_receipt = json.loads(proc.stdout)
    except json.JSONDecodeError:
        tau_receipt = {}
    status = "PASS" if tau_receipt.get("status") == "PASS" else "FAIL"
    receipt = {
        "schema": "monitor_opportunities.tau_eval_smoke_receipt.v1",
        "status": status,
        "mocked": False,
        "live": True,
        "provider_live": False,
        "external_effects": False,
        "dag": str(dag_path),
        "tau_receipt": tau_receipt,
        "process_receipt": str((out / "tau-process.json").resolve()),
        "work_order": str((out / "work-order.json").resolve()),
        "claims": {
            "proves": "Tau executed the local monitor-opportunities creator/validator/reviewer artifact transaction over one report-visible opportunity.",
            "does_not_prove": "Provider/model semantic quality, complete nightly integration, learned relevance, or ATS submission authority.",
        },
    }
    _write_json(receipt_path, receipt)
    if status != "PASS":
        print(f"TAU_EVAL_SMOKE FAIL run={out} receipt={receipt_path}")
        raise SystemExit(1)
    print(f"TAU_EVAL_SMOKE PASS run={out} receipt={receipt_path} provider_live=False")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--report", type=Path, required=True)
    run_parser.add_argument("--out", type=Path, required=True)
    run_parser.add_argument("--tau-root", type=Path, default=Path("/home/graham/workspace/experiments/tau"))
    run_parser.add_argument("--timeout-seconds", type=float, default=240.0)
    run_parser.set_defaults(func=run)

    produce_parser = subparsers.add_parser("produce")
    produce_parser.add_argument("--artifact-root", type=Path, required=True)
    produce_parser.add_argument("--receipt", type=Path, required=True)
    produce_parser.add_argument("--work-order", type=Path, required=True)
    produce_parser.set_defaults(func=produce)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.set_defaults(func=validate)

    review_parser = subparsers.add_parser("review")
    review_parser.set_defaults(func=review)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
