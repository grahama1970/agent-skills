"""What model actually answered, versus the one the lane asked for.

Purpose
    A browser lane's receipt recorded `model: None` and `requested_model: None`
    for every browser handler -- webgpt, webclaude, webkimi, the seats used
    most -- because those fields were hardcoded to `None` unless the handler
    was an API model. Meanwhile Surf's submit meta already carried the answer:
    `requested_reasoning: "Pro"` alongside `selected_reasoning: null` and
    `reasoning_selection_status: null` (observed 2026-08-16 in the newest
    webgpt receipts on disk).

    So a panel could ask three seats for `Pro` reasoning, get three answers
    from whatever tier the dropdown happened to be on, and produce a receipt in
    which that is invisible. Recording provenance does not fix the selector; it
    stops the run from claiming a rigour it cannot show.

Design
    A requested setting with no confirmation is `unconfirmed`, never
    `confirmed`. Absence of evidence is the whole failure mode here: the
    dropdown silently not taking is exactly the case that produces no error and
    no confirmation. Only an explicit observation that matches the request
    counts as confirmation, and an explicit observation that differs is a
    `mismatch` -- a stronger signal than either.
"""

from __future__ import annotations

from typing import Any

SCHEMA = "ask.model_provenance.v1"

CONFIRMED = "confirmed"
UNCONFIRMED = "unconfirmed"
MISMATCH = "mismatch"
FAILED = "selection_failed"
NOT_REQUESTED = "not_requested"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def from_submit_meta(meta: dict[str, Any] | None, *, handler: str = "") -> dict[str, Any]:
    """Build the provenance block for one browser lane from Surf's submit meta."""
    meta = meta if isinstance(meta, dict) else {}

    requested_model = _clean(meta.get("requested_model"))
    requested_reasoning = _clean(meta.get("requested_reasoning"))
    selected_reasoning = _clean(meta.get("selected_reasoning"))
    observed_reasoning = _clean(meta.get("observed_requested_reasoning"))
    selection_status = _clean(meta.get("reasoning_selection_status"))
    selection_error = _clean(meta.get("reasoning_selection_error"))

    # The strongest available observation of what the provider was actually set
    # to. Surf reports it under two names depending on the code path.
    confirmed_reasoning = selected_reasoning or observed_reasoning

    if selection_error:
        status = FAILED
    elif not requested_reasoning:
        status = NOT_REQUESTED
    elif not confirmed_reasoning:
        # Asked for a tier, got no confirmation. The dropdown silently not
        # taking produces exactly this shape, so it must not read as success.
        status = UNCONFIRMED
    elif confirmed_reasoning.casefold() == requested_reasoning.casefold():
        status = CONFIRMED
    else:
        status = MISMATCH

    return {
        "schema": SCHEMA,
        "handler": _clean(handler),
        "requested_model": requested_model or None,
        "requested_reasoning": requested_reasoning or None,
        "confirmed_reasoning": confirmed_reasoning or None,
        "selection_status": selection_status or None,
        "selection_error": selection_error or None,
        "provenance_status": status,
        # The single field a reader should key off. A panel that cannot show
        # which tier answered has not shown what it claims to have shown.
        "reasoning_proven": status == CONFIRMED,
    }


def summarize(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll per-lane provenance into one panel-level statement."""
    considered = [b for b in blocks if isinstance(b, dict)]
    by_status: dict[str, list[str]] = {}
    for block in considered:
        by_status.setdefault(str(block.get("provenance_status")), []).append(
            str(block.get("handler") or "")
        )
    unproven = [
        str(b.get("handler") or "")
        for b in considered
        if b.get("provenance_status") in {UNCONFIRMED, MISMATCH, FAILED}
    ]
    return {
        "schema": "ask.model_provenance_summary.v1",
        "lanes": len(considered),
        "by_status": {k: sorted(v) for k, v in sorted(by_status.items())},
        "unproven_handlers": sorted(unproven),
        "all_reasoning_proven": bool(considered) and not unproven,
    }
