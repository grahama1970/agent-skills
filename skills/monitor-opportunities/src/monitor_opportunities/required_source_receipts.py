"""Mandatory required-source receipts (LinkedIn top-applicant, client research).

These sources must be attempted on every live run (see config/required_sources.json
and pipeline._enforce_required_sources). Inputs: whether human LinkedIn evidence
was supplied; the skill dir for locating brave-search. Outputs: honest typed
receipts. Failure modes: brave-search unavailable -> FEED_DOWN receipt.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from .receipts import base_receipt, finalize_receipt

# Bounded fallback vocabulary used ONLY when the mandate extractor is unavailable,
# so lane B is not silently dropped when extract-entities is down. Not the primary
# relevance path (that is relevance.mandate_hits against the vocabulary corpus).
_AI_FALLBACK_TERMS = (
    "artificial intelligence", " ai ", " ai/", "machine learning", " ml ",
    "autonom", "data science", "large language", " llm", "computer vision",
    "natural language", "algorithm", "predictive", "automat",
)


def _sam_relevance(title: str) -> tuple[bool, float, list[str]]:
    """Is a SAM notice on-mandate, and its fit_score. (relevant, fit_score, hits).

    SAM's keyword search is loose ("ALL words"), so it returns many off-mandate
    notices (renovations, vent replacements). We keep only AI/ML-relevant ones and
    scale fit by hit count. Primary signal is the mandate vocabulary; a small
    keyword allowlist is the fallback when the extractor is unavailable.
    """
    from .relevance import mandate_hits

    hits = mandate_hits(title)
    if hits is None:  # extractor unavailable -> bounded keyword fallback
        low = f" {title.lower()} "
        kw = [t for t in _AI_FALLBACK_TERMS if t in low]
        if not kw:
            return False, 0.0, []
        return True, min(0.85, 0.5 + 0.08 * len(kw)), kw
    if not hits:
        return False, 0.0, []
    return True, min(0.85, 0.55 + 0.08 * len(hits)), hits

def linkedin_required_receipt(evidence_supplied: bool) -> dict[str, Any]:
    """Honest receipt for the mandatory LinkedIn top-applicant source.

    LinkedIn platform automation is forbidden, so this source is satisfied by
    human-supplied read-only evidence (--linkedin-evidence / surf capture). When
    none is supplied the receipt is AUTH_REQUIRED — an honest 'human capture
    required', never a silent skip.
    """
    receipt = base_receipt("A", "linkedin", "LinkedIn top-applicant", "human_supplied_linkedin")
    receipt["required_source_id"] = "linkedin_top_applicant"
    receipt["channel"] = "browser_human_supplied"
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


def human_browser_required_receipt(
    *,
    provider: str,
    required_source_id: str,
    target: str,
    source_class: str,
    website_fallback: str,
) -> dict[str, Any]:
    """Honest required-source receipt when human browser evidence is absent."""

    receipt = base_receipt("A", provider, target, source_class)
    receipt["required_source_id"] = required_source_id
    receipt["channel"] = "browser_human_supplied"
    receipt["request_summary"] = f"{target} requires read-only browser evidence"
    receipt["result_status"] = "AUTH_REQUIRED"
    receipt["parser_result"] = "BLOCKED"
    receipt["evidence_refs"] = [website_fallback]
    receipt["limitations"].append(
        f"No human/browser evidence supplied for {target}; capture {website_fallback} and re-run."
    )
    return finalize_receipt(receipt)


def client_research_receipt(skill_dir: Path) -> dict[str, Any]:
    """Mandatory client-services research over the candidate's mandates.

    Runs a live brave-search sweep for companies that could use the candidate's
    services (document extraction, agentic pipelines, compliance, Buffalo
    prospects). Honest FEED_DOWN receipt if the search tool is unavailable.
    """
    receipt = base_receipt("C", "client-research", "Client-services prospects", "source_locator")
    receipt["required_source_id"] = "client_research"
    receipt["channel"] = "brave_search"
    queries = [
        "companies hiring document extraction AI agentic pipelines compliance",
        "Buffalo NY AI consulting document extraction machine learning company",
        "aerospace defense CMMC compliance AI services contract",
    ]
    brave = skill_dir.parents[0] / "brave-search" / "run.sh"
    receipt["request_summary"] = f"brave-search client-services research: {len(queries)} queries"
    hits = 0

    def _search(q: str) -> subprocess.CompletedProcess[str]:
        """Free key first; paid-key fallback on quota 429 (authorized 2026-08-12)."""
        import os

        proc = subprocess.run(
            [str(brave), "web", q, "--count", "5"],
            capture_output=True, text=True, timeout=60,
        )
        paid = os.environ.get("BRAVE_API_KEY_PAID")
        failed = proc.returncode != 0 or not proc.stdout.strip()
        quota = (
            "429" in proc.stderr or "QUOTA" in proc.stderr.upper()
            or "not found in env" in proc.stderr
        )
        if failed and paid and quota:
            proc = subprocess.run(
                [str(brave), "web", q, "--count", "5"],
                capture_output=True, text=True, timeout=60,
                env=dict(os.environ, BRAVE_API_KEY=paid),
            )
        return proc

    try:
        for q in queries:
            proc = _search(q)
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



def federal_website_receipt(evidence_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Honest MATCHES receipt from a read-only SAM.gov website capture.

    Satisfies the API-break-must-use-website rule when the SAM API is down:
    source_class 'sam.gov_website' marks a browser fallback capture.
    """
    receipt = base_receipt("B", "sam.gov", "SAM.gov website capture", "sam.gov_website")
    receipt["required_source_id"] = "sam.gov"
    receipt["channel"] = "browser_or_api"
    receipt["request_summary"] = "read-only surf capture of SAM.gov opportunity search"
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("federal website evidence unreadable {}: {}", evidence_path, exc)
        receipt["result_status"] = "INVALID_RESPONSE"
        receipt["parser_result"] = "ERROR"
        return finalize_receipt(receipt), []
    opps = data.get("opportunities", [])
    receipt["response_status"] = 200
    receipt["parser_result"] = "PARSED"
    # Emit one candidate per RELEVANT SAM notice (was dropped entirely before, so
    # lane B produced 0 candidates even on a successful capture). Off-mandate
    # notices are filtered here because lane B is not title-filtered downstream.
    candidates: list[dict[str, Any]] = []
    receipt_id = receipt["receipt_id"]
    for opp in opps[:40]:
        title = str(opp.get("title") or "").strip()
        url = opp.get("url") or opp.get("href")
        if not title or not url:
            continue
        relevant, fit, hits = _sam_relevance(title)
        if not relevant:
            continue
        opp_id = str(opp.get("opp_id") or hashlib.sha256(str(url).encode()).hexdigest()[:16])
        candidates.append({
            "lane": "B",
            "source_receipt_id": receipt_id,
            "source_provider": "sam.gov_website",
            "source_class": "sam.gov_website",
            "source_identity": url,
            "organization": "Federal (SAM.gov)",
            "title": title,
            "location_display": "Federal notice; delivery model not applicable",
            "workplace_type": "NOT_APPLICABLE",
            "relocation_required": False,
            "clearance_required": False,
            "posting_url": url,
            "apply_url": None,
            "primary_evidence_url": url,
            "published_at": opp.get("published_at"),
            "updated_at": opp.get("updated_at"),
            "content_hash": hashlib.sha256(f"sam:{opp_id}".encode()).hexdigest(),
            "posting_text": f"SAM.gov notice. Mandate hits: {', '.join(hits)}",
            "fit_score": fit,
            "candidate_id": f"candidate:b:sam:{opp_id}",
        })
    receipt["result_status"] = "MATCHES" if candidates else "NO_MATCHES"
    receipt["evidence_refs"].append(f"sam_website_capture:{len(opps)}")
    receipt["limitations"].append(
        f"{len(opps)} notices captured; {len(candidates)} on-mandate after relevance gate"
    )
    return finalize_receipt(receipt), candidates
