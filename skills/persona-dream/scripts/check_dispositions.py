#!/usr/bin/env python3
"""Validate Persona Dream research dispositions and transfer decisions."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_REGISTRY = ROOT / "DISPOSITION_REGISTRY.json"

RESULT_CLASSES = {
    "NOT_RUN",
    "APPARATUS_VALID_ONLY",
    "POSITIVE",
    "NULL_OR_TIE",
    "NEGATIVE",
    "BLOCKED_VALID_RESULT",
    "INVALIDATED_EXPERIMENT",
}
PRODUCT_DECISIONS = {
    "ADOPT",
    "CONSTRAIN",
    "REJECT",
    "RETIRE",
    "RETAIN_CREATIVE_ONLY",
    "DEFER_WITH_EXPLICIT_REASON",
}
TRANSFER_OUTCOMES = {
    "DOWNSTREAM_PR",
    "DOWNSTREAM_ISSUE",
    "NO_ADOPTION_WITH_REASON",
    "LOCAL_ONLY_WITH_REASON",
}
TERMINAL_RESULT_CLASSES = {
    "POSITIVE",
    "NULL_OR_TIE",
    "NEGATIVE",
    "BLOCKED_VALID_RESULT",
    "INVALIDATED_EXPERIMENT",
}


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def resolve_path(path: str | None) -> Path | None:
    if not path:
        return None
    p = Path(path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_downstream_artifact(kind: str, repo: str, number: int) -> dict[str, Any]:
    if kind == "DOWNSTREAM_PR":
        command = ["gh", "pr", "view", str(number), "--repo", repo, "--json", "number,state,url"]
    else:
        command = ["gh", "issue", "view", str(number), "--repo", repo, "--json", "number,state,url"]
    proc = subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"gh exited {proc.returncode}")
    return json.loads(proc.stdout)


def validate_registry(
    doc: dict[str, Any],
    *,
    strict: bool = False,
    allow_live_github: bool = False,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    live_checks: list[dict[str, Any]] = []

    def fail(code: str, hypothesis: str | None = None, detail: str | None = None) -> None:
        failures.append({"code": code, "hypothesis": hypothesis, "detail": detail})

    if doc.get("schema") != "persona_dream.disposition_registry.v1":
        fail("registry_schema")
    required = set(doc.get("required_hypotheses") or [])
    records = {str(row.get("id")): row for row in doc.get("hypotheses") or []}
    for hyp in sorted(required):
        if hyp not in records:
            fail("missing_required_hypothesis", hyp)

    goal = doc.get("goal") or {}
    goal_path = resolve_path(goal.get("source"))
    if goal_path and goal_path.is_file():
        if sha_file(goal_path) != goal.get("sha256"):
            fail("goal_sha256_mismatch", detail=str(goal_path))
    elif strict:
        fail("goal_source_missing", detail=str(goal_path))

    for hyp_id, row in records.items():
        result_class = row.get("result_class")
        decision = row.get("product_decision")
        safety = row.get("safety_invariant_status")
        terminal_receipt = row.get("terminal_result_receipt")
        terminal_sha = row.get("terminal_result_receipt_sha256")

        if result_class not in RESULT_CLASSES:
            fail("invalid_result_class", hyp_id, str(result_class))
        if decision not in PRODUCT_DECISIONS:
            fail("invalid_product_decision", hyp_id, str(decision))

        if terminal_receipt:
            path = resolve_path(terminal_receipt)
            if path is None or not path.is_file():
                fail("terminal_receipt_missing", hyp_id, str(path))
            elif terminal_sha and sha_file(path) != terminal_sha:
                fail("terminal_receipt_sha256_mismatch", hyp_id, str(path))
        elif result_class in TERMINAL_RESULT_CLASSES:
            fail("terminal_result_missing_receipt", hyp_id)

        for support in row.get("supporting_receipts") or []:
            path = resolve_path(support.get("path"))
            expected = support.get("sha256")
            if path is None or not path.is_file():
                fail("supporting_receipt_missing", hyp_id, str(path))
            elif expected and sha_file(path) != expected:
                fail("supporting_receipt_sha256_mismatch", hyp_id, str(path))

        if result_class == "APPARATUS_VALID_ONLY":
            if decision in {"ADOPT", "REJECT", "RETIRE"}:
                fail("apparatus_validity_promoted_to_product_decision", hyp_id, str(decision))
            if "benefit" in str(row.get("what_it_proves", "")).lower():
                fail("apparatus_validity_claims_benefit", hyp_id)

        if result_class in {"POSITIVE", "NULL_OR_TIE", "NEGATIVE"}:
            evidence_role = row.get("terminal_result_evidence_role")
            if evidence_role == "apparatus_validity_only":
                fail("terminal_result_backed_only_by_apparatus_validity", hyp_id)
            if evidence_role == "technical_screen_only":
                fail("terminal_result_backed_only_by_technical_screen", hyp_id)

        if result_class in {"POSITIVE", "NULL_OR_TIE", "NEGATIVE"} and not terminal_receipt:
            fail("terminal_effect_without_receipt", hyp_id)

        if decision == "ADOPT" and safety != "PASS":
            fail("adopt_with_failed_safety_invariant", hyp_id, str(safety))

        if decision == "RETIRE":
            if "retired" not in str(row.get("retained_subsystem_scope", "")).lower():
                fail("retire_without_retired_scope", hyp_id)
            if not row.get("successor_or_retirement_action"):
                fail("retire_without_action", hyp_id)
            if row.get("runtime_advertises_required") is not False:
                fail("retire_while_runtime_advertises_required", hyp_id)

        if decision == "DEFER_WITH_EXPLICIT_REASON":
            if not row.get("external_blocker"):
                fail("defer_without_external_blocker", hyp_id)
            if not row.get("review_condition"):
                fail("defer_without_review_condition", hyp_id)

        outcomes = row.get("transfer_outcomes") or []
        if result_class in TERMINAL_RESULT_CLASSES and not outcomes:
            fail("terminal_result_without_transfer_outcome", hyp_id)
        for outcome in outcomes:
            kind = outcome.get("type")
            if kind not in TRANSFER_OUTCOMES:
                fail("invalid_transfer_outcome", hyp_id, str(kind))
            if kind in {"DOWNSTREAM_PR", "DOWNSTREAM_ISSUE"}:
                for key in ("repo", "number", "url", "state", "relationship"):
                    if not outcome.get(key):
                        fail("downstream_transfer_missing_field", hyp_id, key)
                if allow_live_github and outcome.get("repo") and outcome.get("number"):
                    try:
                        live = read_downstream_artifact(kind, str(outcome["repo"]), int(outcome["number"]))
                    except Exception as exc:  # noqa: BLE001 - preserve the external command error.
                        fail("downstream_live_read_failed", hyp_id, str(exc))
                    else:
                        live_check = {
                            "type": kind,
                            "hypothesis": hyp_id,
                            "repo": outcome["repo"],
                            "number": int(outcome["number"]),
                            "expected_state": outcome.get("state"),
                            "actual_state": live.get("state"),
                            "expected_url": outcome.get("url"),
                            "actual_url": live.get("url"),
                        }
                        live_checks.append(live_check)
                        if live.get("state") != outcome.get("state"):
                            fail("downstream_live_state_mismatch", hyp_id, json.dumps(live_check, sort_keys=True))
                        if live.get("url") != outcome.get("url"):
                            fail("downstream_live_url_mismatch", hyp_id, json.dumps(live_check, sort_keys=True))
            if kind in {"NO_ADOPTION_WITH_REASON", "LOCAL_ONLY_WITH_REASON"} and not outcome.get("reason"):
                fail("transfer_reason_missing", hyp_id, str(kind))

        if result_class in {"NULL_OR_TIE", "NEGATIVE"} and row.get("later_exploratory_overrides") is True:
            fail("null_or_negative_replaced_by_exploratory_run", hyp_id)

        if row.get("status", "").startswith("TERMINAL") and decision == "DEFER_WITH_EXPLICIT_REASON":
            fail("terminal_status_with_defer_decision", hyp_id)

    if doc.get("immutable_goal_completion_claimed") is True:
        for hyp in sorted(required):
            row = records.get(hyp) or {}
            if row.get("result_class") in {"NOT_RUN", "APPARATUS_VALID_ONLY"}:
                fail("immutable_goal_completion_claimed_with_nonterminal_hypothesis", hyp)

    status = "PASS_DISPOSITION_REGISTRY" if not failures else "BLOCKED_DISPOSITION_REGISTRY"
    terminal = [
        hyp_id for hyp_id, row in records.items()
        if row.get("result_class") in TERMINAL_RESULT_CLASSES
    ]
    nonterminal = [
        hyp_id for hyp_id, row in records.items()
        if row.get("result_class") in {"NOT_RUN", "APPARATUS_VALID_ONLY"}
    ]
    return {
        "schema": "persona_dream.disposition_registry_check.v1",
        "created_at": utc_now(),
        "status": status,
        "mocked": False,
        "live": bool(live_checks),
        "live_github_enabled": allow_live_github,
        "live_checks": live_checks,
        "strict": strict,
        "required_hypothesis_count": len(required),
        "hypothesis_count": len(records),
        "terminal_hypotheses": sorted(terminal),
        "nonterminal_hypotheses": sorted(nonterminal),
        "immutable_goal_completion_claimed": doc.get("immutable_goal_completion_claimed") is True,
        "failures": failures,
        "claims": {
            "proves": [
                "disposition registry hashes and result/product/transfer combinations are internally consistent",
                "immutable-goal completion is claimed only when no required hypothesis remains nonterminal"
                if doc.get("immutable_goal_completion_claimed") is True
                else "immutable-goal completion is not claimed while required hypotheses remain nonterminal",
            ],
            "does_not_prove": [
                "any new experimental result",
                "human listener perception",
                "downstream repository adoption beyond recorded issue/PR state readbacks",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--allow-live-github", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = validate_registry(
        load_json(args.registry),
        strict=args.strict,
        allow_live_github=args.allow_live_github,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report if args.json else {"status": report["status"], "failures": report["failures"]}, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS_DISPOSITION_REGISTRY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
