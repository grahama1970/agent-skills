#!/usr/bin/env python3
"""Assess a transcript/report for delivery-proof violations.

The infrastructure `assess` pattern from best-practices-skills, applied to
agent output: six misuse patterns, each derived from a 2026-08-18 receipt,
detected with named diagnostics an agent can act on. Input is a JSON incident
file (or plain text) describing what the agent did and claimed; output is a
diagnostic list and a non-zero exit when any error-severity pattern fires.

Two modes of failure this catches, from the incident that created the skill:
an unchanged operation retried after failure with no new variable, and a
delivery claim backed by transport self-status instead of a destination
receipt.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

# proof_status values that support NO success claim (surf vocabulary).
NON_SUCCESS_STATUS = {"not_submitted", "delivery_not_proven", "wrong_tab", "degraded_focus", "rate_limited"}
SELF_STATUS_SOURCES = {"wrapper", "argv", "prepared_prompt", "submitted_md", "heartbeat_unread", "stale_meta"}
CLAIM_WORDS = re.compile(r"\b(sent|delivered|submitted|landed|pushed|written|generating)\b", re.I)


def _diags_for(doc: dict) -> list[str]:
    diags: list[str] = []
    attempts = doc.get("attempts") or []
    claims = doc.get("claims") or []

    # unchanged_retry_or_skipped_rung
    seen: dict[str, int] = {}
    for a in attempts:
        fp = json.dumps({k: a.get(k) for k in ("operation", "transport", "target_id", "variable_changed")}, sort_keys=True)
        if a.get("outcome") == "failed":
            seen[fp] = seen.get(fp, 0) + 1
            if seen[fp] >= 2 and not a.get("variable_changed"):
                diags.append("UNCHANGED_RETRY_AFTER_FAILURE")
                diags.append("MISSING_ONE_VARIABLE_DELTA")
    failed = [a for a in attempts if a.get("outcome") == "failed"]
    if len(failed) >= 2 and not any(a.get("escalation_rung") for a in attempts):
        diags.append("ESCALATION_REQUIRED")

    for c in claims:
        text = str(c.get("text") or "")
        receipt = c.get("receipt") or {}
        if CLAIM_WORDS.search(text):
            # delivery_claim_without_destination_receipt
            if not receipt:
                diags.append("UNPROVEN_DELIVERY_CLAIM")
                diags.append("NEEDS_ATTENTION_REQUIRED")
                continue
            # invalid_receipt_source_or_status
            if receipt.get("source") in SELF_STATUS_SOURCES:
                diags.append("UNPROVEN_DELIVERY_CLAIM")
                diags.append("SELF_STATUS_IS_NOT_DESTINATION_RECEIPT")
                diags.append("NEEDS_ATTENTION_REQUIRED")
            status = receipt.get("proof_status")
            if status in NON_SUCCESS_STATUS:
                diags.append("INCOMPATIBLE_PROOF_STATUS")
            if status == "submitted_no_response_proof" and re.search(r"\b(answer|response|generating)\b", text, re.I):
                diags.append("SUBMITTED_NO_RESPONSE_NOT_PROMOTED_TO_RESPONSE")
            # human_target_rerouted_or_unproved
            named = c.get("named_target")
            if named and receipt.get("target_id") and str(receipt["target_id"]) != str(named):
                diags.append("HUMAN_TARGET_REROUTED")
                diags.append("NEEDS_ATTENTION_REQUIRED")
            # stale_or_shared_attempt_artifact
            if receipt.get("attempt_id") and c.get("attempt_id") and receipt["attempt_id"] != c["attempt_id"]:
                diags.append("STALE_ATTEMPT_ARTIFACT")

    # unsafe_termination_or_orphan_risk
    for k in doc.get("kill_commands") or []:
        if "pkill -f" in k or "grep /proc" in k.replace("*", ""):
            diags.append("UNSAFE_PATTERN_KILL")
    return list(dict.fromkeys(diags))


@app.command()
def transcript(
    input: Path = typer.Option(..., "--input", exists=True),
    require_escalation_ladder: bool = typer.Option(False, "--require-escalation-ladder"),
    require_destination_receipts: bool = typer.Option(False, "--require-destination-receipts"),
) -> None:
    doc = json.loads(input.read_text())
    diags = _diags_for(doc)
    for d in diags:
        typer.echo(d)
    errors = [d for d in diags if d not in ("ESCALATION_REQUIRED",) or require_escalation_ladder]
    if require_escalation_ladder and not any(d.startswith(("UNCHANGED_RETRY", "ESCALATION")) for d in diags):
        typer.echo("ESCALATION_LADDER_SATISFIED")
    if diags and errors:
        raise typer.Exit(2)
    typer.echo("ASSESS_CLEAN")


if __name__ == "__main__":
    app()
