"""Typer CLI for qra-grade-advice.

Commands validate QRA pool items, emit a minimal deterministic advisory packet,
and optionally post that packet to a pool API. Network failures surface as typed
CLI errors; the local fixture path has no external service dependency.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import typer
from loguru import logger
from pydantic import ValidationError

from .models import Finding, LaneReceipt, QraAdvice, QraItem

app = typer.Typer(add_completion=False, help="QRA grade advice helper")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _echo_json(data: Any) -> None:
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False))


def _validation_error(exc: ValidationError) -> dict[str, Any]:
    return {"schema": "qra_grade_advice.validation_error.v1", "errors": exc.errors()}


def build_advice(item: QraItem) -> QraAdvice:
    """Build a small deterministic advice packet from validated input."""
    started = time.monotonic()
    evidence_findings: list[Finding] = []
    source_count = len(item.sources) + len(item.source_context)
    if source_count == 0:
        evidence_findings.append(
            Finding(
                severity="medium",
                category="missing_source_context",
                location="sources|source_context",
                evidence="No source quotes were supplied with the QRA item.",
                smallest_fix="Attach source quotes/locators before final grading.",
            )
        )

    high_value = bool(item.constraints.get("high_priority") or item.constraints.get("client_sensitive"))
    decision = "escalate" if high_value else "skip"
    grade = "revise" if evidence_findings else "weak_pass"
    confidence = "low" if evidence_findings else "medium"
    latency = time.monotonic() - started
    return QraAdvice(
        schema="qra_grade_advice.v1",
        qra_id=item.id,
        grade=grade,
        confidence=confidence,
        grade_rationale={
            "provenance": "model_generated_advisory",
            "text": "Deterministic preflight advice only; Graham must review before final rationale.",
        },
        evidence_findings=evidence_findings,
        rewrite_advice_for_graham={
            "must_keep": ["Keep any source-grounded claim that directly answers the question."],
            "must_fix": ["Resolve every missing source, unsupported claim, or citation mismatch."],
            "suggested_structure": ["grade", "evidence", "objection", "smallest correction"],
            "phrases_to_avoid": ["clearly", "robust", "comprehensive"],
            "line_or_quote_refs_to_use": [],
        },
        optional_graham_style_draft={
            "enabled": False,
            "provenance": "model_generated_graham_style_draft",
            "text": "",
            "requires_graham_review": True,
        },
        browser_advisor_decision=decision,
        do_not_submit=[
            "Do not paste this packet as final reasoning.",
            "Graham writes or approves the final rationale from the evidence and advice.",
        ],
        lane_receipts=[
            LaneReceipt(
                lane="deterministic_preflight",
                status="warn" if evidence_findings else "pass",
                latency_seconds=latency,
                findings_count=len(evidence_findings),
                notes=["Local schema/source preflight only."],
            )
        ],
    )


@app.command("validate-qra")
def validate_qra(path: Path) -> None:
    """Validate one qra_pool.item.v1 JSON file."""
    try:
        item = QraItem.model_validate(_load_json(path))
    except ValidationError as exc:
        _echo_json(_validation_error(exc))
        raise typer.Exit(1) from exc
    _echo_json({"schema": "qra_grade_advice.validate_qra.v1", "status": "PASS", "qra_id": item.id})


@app.command("validate-advice")
def validate_advice(path: Path) -> None:
    """Validate one qra_grade_advice.v1 JSON file."""
    try:
        advice = QraAdvice.model_validate(_load_json(path))
    except ValidationError as exc:
        _echo_json(_validation_error(exc))
        raise typer.Exit(1) from exc
    _echo_json({"schema": "qra_grade_advice.validate_advice.v1", "status": "PASS", "qra_id": advice.qra_id})


@app.command("fixture")
def fixture(path: Path, out: Path = typer.Option(..., "--out", help="Advice JSON output path")) -> None:
    """Build deterministic advice for one local QRA fixture."""
    item = QraItem.model_validate(_load_json(path))
    advice = build_advice(item)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(advice.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _echo_json({"schema": "qra_grade_advice.fixture_receipt.v1", "status": "PASS", "out": str(out)})


@app.command("pool-once")
def pool_once(pool_url: str = typer.Option(..., "--pool-url", help="Base URL for QRA pool API")) -> None:
    """Lease one item, post deterministic advice, and return a receipt."""
    with httpx.Client(base_url=pool_url.rstrip("/"), timeout=30.0) as client:
        leased = client.post("/lease").raise_for_status().json()
        item = QraItem.model_validate(leased)
        advice = build_advice(item)
        posted = client.post("/advice", json=advice.model_dump(mode="json")).raise_for_status().json()
    logger.info("posted advice for {}", item.id)
    _echo_json({"schema": "qra_grade_advice.pool_once_receipt.v1", "status": "PASS", "qra_id": item.id, "pool_response": posted})


if __name__ == "__main__":
    app()
