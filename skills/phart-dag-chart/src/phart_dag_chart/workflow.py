"""Receipt-backed workflow projections for actual runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from phart_dag_chart.chart import render_chart
from phart_dag_chart.errors import DagChartError

WATCHDOG_TICK_SCHEMA = "agent_skills.project_watchdog.tick_receipt.v1"
REPAIR_PROOF_SCHEMA = "agent_skills.project_watchdog.repair_proof_gate.v1"
AGENTIC_EVAL_SCHEMA = "agentic_evals.report.v2"


def detect_chart_view(raw: dict[str, Any]) -> str:
    """Return workflow for observed receipts, structure for DAG contracts."""
    schema = raw.get("schema")
    if schema == WATCHDOG_TICK_SCHEMA:
        return "workflow"
    if schema == "tau.dag_contract.v1":
        return "structure"
    if raw.get("schema_version") == "ask.dag.v1":
        return "structure"
    if raw.get("exec_graph_version") == "scillm.exec.graph.v1":
        return "structure"
    raise DagChartError(
        "Unsupported chart input schema.",
        code="unsupported_chart_schema",
        hint="Use a supported DAG contract or an agent_skills.project_watchdog.tick_receipt.v1 receipt.",
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def load_evidence(paths: list[Path]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, dict[str, str]]:
    proof = None
    eval_report = None
    issue = None
    hashes: dict[str, str] = {}
    for path in paths:
        try:
            raw = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise DagChartError(f"Evidence JSON is malformed: {path}: {exc}", code="evidence_json_malformed") from None
        hashes[str(path)] = _sha256(path)
        if raw.get("schema") == REPAIR_PROOF_SCHEMA:
            proof = raw
        elif raw.get("schema") == AGENTIC_EVAL_SCHEMA:
            eval_report = raw
        elif isinstance(raw.get("number"), int):
            issue = raw
    return proof, eval_report, issue, hashes


def _handled_issue(receipt: dict[str, Any]) -> dict[str, Any]:
    issues = receipt.get("handled_issues") or []
    if not isinstance(issues, list) or not issues or not isinstance(issues[0], dict):
        raise DagChartError("Watchdog receipt has no handled_issues[0] object.", code="workflow_receipt_missing_issue")
    return issues[0]


def _issue_from_receipt(receipt: dict[str, Any], number: int) -> dict[str, Any] | None:
    for item in receipt.get("scanned_issues") or []:
        if isinstance(item, dict) and item.get("number") == number:
            return item
    return None


def _label_list(issue: dict[str, Any] | None) -> str:
    if not issue:
        return ""
    labels = issue.get("labels") or []
    names: list[str] = []
    for label in labels:
        if isinstance(label, dict) and label.get("name"):
            names.append(str(label["name"]))
        elif isinstance(label, str):
            names.append(label)
    return ", ".join(names)


def _eval_counts(eval_report: dict[str, Any] | None) -> str | None:
    if not eval_report:
        return None
    readiness = eval_report.get("readiness")
    outcome = (eval_report.get("outcome_counts") or {}).get("PASS")
    trial_count = eval_report.get("trial_count")
    cases = eval_report.get("cases") or []
    if cases and isinstance(cases[0], dict):
        passed = cases[0].get("passed_trials")
        total = cases[0].get("total_trials")
        name = cases[0].get("name")
        return f"{name}: {readiness} / PASS · {passed}/{total} trials"
    if readiness and outcome is not None and trial_count is not None:
        return f"{readiness} / PASS={outcome} · trials={trial_count}"
    return None


def watchdog_workflow_projection(receipt: dict[str, Any], receipt_path: Path, evidence_paths: list[Path]) -> tuple[dict[str, Any], list[str]]:
    if receipt.get("schema") != WATCHDOG_TICK_SCHEMA:
        raise DagChartError("Workflow view currently supports only project-watchdog tick receipts.", code="unsupported_workflow_schema")
    if receipt.get("schema_validation", {}).get("valid") is False:
        raise DagChartError("Receipt schema_validation.valid=false; refusing completion workflow chart.", code="receipt_schema_invalid")

    handled = _handled_issue(receipt)
    issue_no = int(handled.get("issue_number") or 0)
    proof, eval_report, issue_evidence, hashes = load_evidence(evidence_paths)
    hashes[str(receipt_path)] = _sha256(receipt_path)
    receipt_issue = _issue_from_receipt(receipt, issue_no)
    issue = issue_evidence or receipt_issue
    if issue_evidence and issue_evidence.get("number") != issue_no:
        raise DagChartError(
            f"receipt handles issue {issue_no} but issue evidence is #{issue_evidence.get('number')}",
            code="evidence_mismatch",
        )

    proof_passed = bool(proof and proof.get("ok") is True and all(a.get("passed") is True for a in proof.get("artifact_results") or []))
    eval_detail = _eval_counts(eval_report)
    ticket_closed = handled.get("ticket_closed") is True
    terminal_status = str(receipt.get("status") or handled.get("status") or "UNKNOWN")
    terminal_ok = receipt.get("ok") is True
    seats = handled.get("seats") or {}
    creator = seats.get("creator")
    creator_handler = seats.get("creator_handler")
    reviewer = seats.get("reviewer")

    nodes = [
        {"id": f"ticket_{issue_no}_filed_agent_work", "type": "skill.run", "depends_on": []},
        {"id": "watchdog_selected_ticket", "type": "skill.run", "depends_on": [f"ticket_{issue_no}_filed_agent_work"]},
        {"id": f"classified_{handled.get('action') or 'unknown'}", "type": "skill.run", "depends_on": ["watchdog_selected_ticket"]},
    ]
    last = nodes[-1]["id"]
    if creator_handler or creator:
        node_id = f"creator_{creator_handler or 'handler'}_{creator or 'model'}".replace("-", "_").replace(".", "_")[:80]
        nodes.append({"id": node_id, "type": "skill.run", "depends_on": [last]})
        last = node_id
    if reviewer:
        node_id = f"reviewer_{reviewer}".replace("-", "_").replace(".", "_")[:80]
        nodes.append({"id": node_id, "type": "skill.run", "depends_on": [last]})
        last = node_id
    if proof or eval_report:
        node_id = "proof_PASS_READY" if proof_passed and eval_detail else "proof_NOT_PROVEN"
        nodes.append({"id": node_id, "type": "skill.run", "depends_on": [last]})
        last = node_id
    if ticket_closed:
        nodes.append({"id": f"native_close_{issue_no}_ticket_closed_true", "type": "skill.run", "depends_on": [last]})
        last = nodes[-1]["id"]
    nodes.append({"id": f"watchdog_receipt_{terminal_status}_ok_{str(terminal_ok).lower()}", "type": "skill.run", "depends_on": [last]})

    dag = {
        "schema_version": "ask.dag.v1",
        "graph_id": str(receipt.get("run_id") or "project-watchdog-workflow"),
        "description": "receipt-backed project-watchdog workflow projection",
        "nodes": nodes,
    }

    details = [
        f"Workflow projection · {dag['graph_id']}",
        f"source={WATCHDOG_TICK_SCHEMA}",
        f"ticket #{issue_no}: {issue.get('title') if issue else '(title not supplied)'}",
        f"target={', '.join(handled.get('targets') or [])}",
        f"labels={_label_list(issue) or '(not supplied)'}",
        f"classification={handled.get('action')}",
        f"creator={creator_handler or '?'} / {creator or '?'}",
        f"reviewer={reviewer or '?'}",
    ]
    if proof:
        verdicts = proof.get("seat_verdicts") or {}
        details.append(f"seat_verdicts={json.dumps(verdicts, sort_keys=True)}")
    if eval_detail:
        details.append(f"proof={eval_detail}")
    elif proof:
        details.append("proof=NOT PROVEN: eval report not supplied")
    details.append(f"ticket_closed={str(ticket_closed).lower()}")
    details.append(f"terminal={terminal_status} · ok={str(terminal_ok).lower()}")
    details.append("rule: receipt facts are observations; DAG nodes are only structure/enrichment")
    details.append("evidence_hashes:")
    for path, digest in sorted(hashes.items()):
        details.append(f"  {path}: {digest}")
    return dag, details


def render_workflow_chart(receipt: dict[str, Any], receipt_path: Path, evidence_paths: list[Path], *, plain: bool, show_evidence: bool) -> str:
    dag, details = watchdog_workflow_projection(receipt, receipt_path, evidence_paths)
    chart = render_chart(dag, validate=True, plain=True)
    visible = details if show_evidence else details[: details.index("evidence_hashes:")]
    body = chart + "\n\n" + "\n".join(visible)
    if plain:
        return body
    return "```text\n" + body + "\n```"
