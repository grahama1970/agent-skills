"""Mandatory required-source receipts (LinkedIn top-applicant, client research).

These sources must be attempted on every live run (see config/required_sources.json
and pipeline._enforce_required_sources). Inputs: whether human LinkedIn evidence
was supplied; the skill dir for locating brave-search. Outputs: honest typed
receipts. Failure modes: brave-search unavailable -> FEED_DOWN receipt.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from .receipts import base_receipt, finalize_receipt

def linkedin_required_receipt(evidence_supplied: bool) -> dict[str, Any]:
    """Honest receipt for the mandatory LinkedIn top-applicant source.

    LinkedIn platform automation is forbidden, so this source is satisfied by
    human-supplied read-only evidence (--linkedin-evidence / surf capture). When
    none is supplied the receipt is AUTH_REQUIRED — an honest 'human capture
    required', never a silent skip.
    """
    receipt = base_receipt("A", "linkedin", "LinkedIn top-applicant", "human_supplied_linkedin")
    receipt["automation_policy"] = "linkedin_authorized_read_only_no_actions"
    receipt["request_summary"] = "LinkedIn top-applicant requires human-supplied read-only capture"
    if evidence_supplied:
        receipt["result_status"] = "MATCHES"
        receipt["parser_result"] = "PARSED"
    else:
        receipt["result_status"] = "AUTH_REQUIRED"
        receipt["parser_result"] = "BLOCKED"
        receipt["limitations"].append("No --linkedin-evidence supplied; run a read-only surf capture of the top-applicant collection and re-run.")
    return finalize_receipt(receipt)


def client_research_receipt(skill_dir: Path) -> dict[str, Any]:
    """Mandatory client-services research over the candidate's mandates.

    Runs a live brave-search sweep for companies that could use the candidate's
    services (document extraction, agentic pipelines, compliance, Buffalo
    prospects). Honest FEED_DOWN receipt if the search tool is unavailable.
    """
    receipt = base_receipt("C", "client-research", "Client-services prospects", "source_locator")
    queries = [
        "companies hiring document extraction AI agentic pipelines compliance",
        "Buffalo NY AI consulting document extraction machine learning company",
        "aerospace defense CMMC compliance AI services contract",
    ]
    brave = skill_dir.parents[0] / "brave-search" / "run.sh"
    receipt["request_summary"] = f"brave-search client-services research: {len(queries)} queries"
    hits = 0
    try:
        for q in queries:
            proc = subprocess.run([str(brave), "web", q, "--count", "5"], capture_output=True, text=True, timeout=60)
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    hits += len(json.loads(proc.stdout).get("results", []))
                except (ValueError, KeyError) as exc:
                    logger.warning("client research: unparsable brave-search output for query {!r}: {}", q, exc)
        receipt["response_status"] = 200
        receipt["result_status"] = "MATCHES" if hits > 0 else "NO_MATCHES"
        receipt["parser_result"] = "PARSED"
        receipt["evidence_refs"].append(f"client_research_hits:{hits}")
    except Exception as exc:  # brave-search unavailable is an honest feed-down
        logger.error("client research brave-search sweep failed: {}", exc)
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"client research unavailable: {type(exc).__name__}")
    return finalize_receipt(receipt)

