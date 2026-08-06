"""Decision memory across rebuilds (#1225).

A rebuild must not discard prior human claim decisions. carry_decisions merges
a prior ledger into a freshly planned one, keyed by SPAN-NORMALIZED claim text
(whitespace/case/punctuation-insensitive): an unchanged claim inherits its
prior status, approval, qualifier, spans, and formula; a changed or new claim
stays candidate and is re-proposed. Approvals are NEVER transferred to changed
text (review condition: approvals never silently inherited). Failure modes:
none silent — every carry and re-proposal is counted and logged.
"""

from __future__ import annotations

import re

from loguru import logger

from .models import Claim, ClaimLedger, ClaimStatus


def normalize_decision_key(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", re.sub(r"\s+", " ", text.strip().lower()))


def carry_decisions(prior: ClaimLedger, planned: ClaimLedger) -> tuple[ClaimLedger, dict[str, int]]:
    """Merge prior human decisions into a freshly planned ledger."""
    prior_by_key: dict[str, Claim] = {}
    for claim in prior.claims:
        prior_by_key.setdefault(normalize_decision_key(claim.text), claim)

    carried = re_proposed = fresh = 0
    merged: list[Claim] = []
    for claim in planned.claims:
        previous = prior_by_key.get(normalize_decision_key(claim.text))
        if previous is None:
            fresh += 1
            merged.append(claim)
        elif previous.status == ClaimStatus.CANDIDATE:
            re_proposed += 1
            merged.append(claim)
        else:
            carried += 1
            merged.append(
                claim.model_copy(
                    update={
                        "status": previous.status,
                        "approval": previous.approval,
                        "required_qualifier": previous.required_qualifier or claim.required_qualifier,
                        "evidence_spans": previous.evidence_spans or claim.evidence_spans,
                        "formula": previous.formula or claim.formula,
                        "risk": previous.risk,
                        "kind": previous.kind,
                    }
                )
            )
    counts = {"carried": carried, "re_proposed": re_proposed, "fresh": fresh}
    logger.info("decision memory: {}", counts)
    return planned.model_copy(update={"claims": merged}), counts
