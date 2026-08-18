"""No-change detection so the monitor never re-nudges an agent that did nothing.

Herdr owns `state_change_seq`, a monotonic per-agent counter that advances on
every lifecycle transition (idle -> working -> idle is two transitions). If it
has not moved since the prompt we sent, that agent never even started a turn on
our nudge, so sending the same nudge again is spam rather than supervision.

The transcript digest is the second, weaker signal: it catches an agent that
transitioned but produced no new visible output. Both must be unchanged before
the monitor suppresses a prompt, and either being unavailable degrades to the
other rather than failing open.
"""

from __future__ import annotations

import hashlib
from typing import Any

DEFAULT_MAX_NO_CHANGE_STRIKES = 2


def transcript_digest(text: str) -> str:
    """Stable digest of the transcript region used for change comparison."""
    normalized = " ".join((text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def change_signature(agent_record: dict[str, Any] | None, transcript: str) -> dict[str, Any]:
    """Capture the change-detection signature for a pane at one point in time."""
    seq = None
    if isinstance(agent_record, dict):
        raw = agent_record.get("state_change_seq")
        if isinstance(raw, int):
            seq = raw
        elif isinstance(raw, str) and raw.isdigit():
            seq = int(raw)
    return {"state_change_seq": seq, "transcript_digest": transcript_digest(transcript)}


def unchanged_since_prompt(signature: dict[str, Any], prompt_state: dict[str, Any] | None) -> dict[str, Any]:
    """Decide whether a pane has done anything since the monitor last prompted it.

    Returns a verdict dict rather than a bare bool so the receipt can record the
    exact evidence that suppressed (or allowed) the prompt.
    """
    if not prompt_state:
        return {"unchanged": False, "reason": "no_prior_prompt", "comparable": False}

    prior_seq = prompt_state.get("state_change_seq_at_prompt")
    prior_digest = prompt_state.get("transcript_digest_at_prompt")
    current_seq = signature.get("state_change_seq")
    current_digest = signature.get("transcript_digest")

    seq_comparable = isinstance(prior_seq, int) and isinstance(current_seq, int)
    digest_comparable = bool(prior_digest) and bool(current_digest)
    if not seq_comparable and not digest_comparable:
        return {"unchanged": False, "reason": "no_comparable_signal", "comparable": False}

    # A moved sequence proves a real lifecycle transition even when the visible
    # transcript region happens to render identically.
    if seq_comparable and current_seq != prior_seq:
        return {
            "unchanged": False,
            "reason": "state_change_seq_advanced",
            "comparable": True,
            "state_change_seq_at_prompt": prior_seq,
            "state_change_seq_now": current_seq,
        }
    if digest_comparable and current_digest != prior_digest:
        return {
            "unchanged": False,
            "reason": "transcript_changed",
            "comparable": True,
        }

    evidence = []
    if seq_comparable:
        evidence.append(f"state_change_seq_frozen:{current_seq}")
    if digest_comparable:
        evidence.append("transcript_digest_identical")
    return {
        "unchanged": True,
        "reason": "no_agent_progress_since_last_prompt",
        "comparable": True,
        "evidence": evidence,
        "state_change_seq_at_prompt": prior_seq if seq_comparable else None,
    }


def record_prompt_signature(prompt_state: dict[str, Any], signature: dict[str, Any], *, unchanged_before: bool) -> dict[str, Any]:
    """Merge a freshly sent prompt's signature into the pane's stored state."""
    strikes = int(prompt_state.get("no_change_strikes", 0) or 0)
    prompt_state["no_change_strikes"] = strikes + 1 if unchanged_before else 0
    prompt_state["state_change_seq_at_prompt"] = signature.get("state_change_seq")
    prompt_state["transcript_digest_at_prompt"] = signature.get("transcript_digest")
    return prompt_state


def nudge_exhausted(prompt_state: dict[str, Any] | None, *, max_strikes: int = DEFAULT_MAX_NO_CHANGE_STRIKES) -> bool:
    """True once repeated nudges have provably failed to move the agent."""
    if not prompt_state:
        return False
    return int(prompt_state.get("no_change_strikes", 0) or 0) >= max_strikes
