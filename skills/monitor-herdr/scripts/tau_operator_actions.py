"""Tau operator-action client for monitor-herdr (agent-skills#1221 part 2, tau#310).

Composes ``tau.operator_action_request.v1``, submits it to Tau, and validates
the returned ``tau.operator_action_receipt.v1``. Tau owns the decision; this
module never applies an action itself and never invents a receipt.

Two hard rules from the ticket, enforced here rather than documented:

- A failed structured action NEVER falls back to terminal key injection. A
  refusal is a typed error and the caller is expected to stop, not to reach for
  ``tick --apply``.
- Herdr state is a projection. The request's ``observed_journal_seq`` comes from
  the attached Tau projection, so a request built against a stale card is
  rejected by Tau's own optimistic-concurrency check instead of racing it.

Composition and validation carry no Tau import, so they run headless and are
provable without a live run. Submission is injected: the default submitter
requires the real ``tau_coding`` package, so an unavailable Tau produces a typed
``tau_unavailable`` refusal rather than a fabricated success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

REQUEST_SCHEMA = "tau.operator_action_request.v1"
RECEIPT_SCHEMA = "tau.operator_action_receipt.v1"

# Mirrors tau_coding.dag_runtime.agent_projection.OPERATOR_ACTIONS.
OPERATOR_ACTIONS = (
    "cancel",
    "add_next_turn_instruction",
    "retry_requested",
    "request_independent_review",
    "request_human_approval",
    "pause",
    "resume",
)
AUTHORIZED_ACTORS = ("human_operator", "project_watchdog")
TERMINAL_LIFECYCLES = ("completed", "failed", "cancelled", "blocked")
# Typed outcomes Tau returns when the harness cannot honor the action now.
DEFERRED_OUTCOMES = ("unsupported", "queued_for_next_turn", "fork_required")
# Tau's permitted_actions() never advertises these, but its applier answers them
# with a typed outcome. Gating them locally would hide the very answer the
# operator asked for, so they bypass the permitted-set check and Tau replies.
ALWAYS_SUBMITTABLE_ACTIONS = ("pause", "resume")


class OperatorActionError(RuntimeError):
    """Fail-closed operator-action refusal with a stable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code + (f": {detail}" if detail else ""))
        self.code = code
        self.detail = detail


def canonical_sha256(payload: Any) -> str:
    """Byte-parity with tau_coding.dag_runtime.model.canonical_sha256."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def find_card(state: dict[str, Any], node_id: str) -> dict[str, Any]:
    for card in state.get("cards", []):
        if str(card.get("node_id")) == node_id:
            return card
    raise OperatorActionError("unknown_node", node_id)


def build_action_request(
    *,
    state: dict[str, Any],
    node_id: str,
    action: str,
    actor: str,
    instruction: str | None = None,
) -> dict[str, Any]:
    """Compose a request Tau will accept, refusing locally-provable violations.

    Local refusals exist to avoid burning a Tau round-trip on a request that is
    already known-bad; Tau re-validates everything and remains authoritative.
    """
    if action not in OPERATOR_ACTIONS:
        raise OperatorActionError("operator_action_unknown", action)
    if actor not in AUTHORIZED_ACTORS:
        raise OperatorActionError("operator_action_unauthorized_actor", actor)

    card = find_card(state, node_id)
    lifecycle = str(card.get("lifecycle", ""))
    permitted = list(card.get("permitted_operator_actions", []))

    if lifecycle in TERMINAL_LIFECYCLES and action != "retry_requested":
        raise OperatorActionError("operator_action_node_terminal", lifecycle)
    if action not in permitted and action not in ALWAYS_SUBMITTABLE_ACTIONS:
        raise OperatorActionError(
            "operator_action_not_permitted_for_node",
            f"{action} not in {permitted or 'none'} (lifecycle={lifecycle})",
        )
    if action == "add_next_turn_instruction" and not (instruction or "").strip():
        raise OperatorActionError("operator_action_instruction_required", action)

    request: dict[str, Any] = {
        "schema": REQUEST_SCHEMA,
        "action": action,
        "actor": actor,
        "run_id": str(state["run_id"]),
        "node_id": node_id,
        "goal_hash": card.get("goal_hash") or state.get("goal_hash"),
        "observed_journal_seq": int(card.get("journal_seq", 0)),
    }
    if action == "add_next_turn_instruction":
        request["instruction"] = str(instruction)
    return request


def validate_action_receipt(receipt: Any, request: dict[str, Any]) -> dict[str, Any]:
    """Refuse any receipt that does not prove Tau handled exactly our request."""
    if not isinstance(receipt, dict):
        raise OperatorActionError("operator_action_receipt_missing", type(receipt).__name__)
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise OperatorActionError("operator_action_receipt_schema_invalid", str(receipt.get("schema")))

    claimed = receipt.get("sha256")
    if claimed:
        body = {k: v for k, v in receipt.items() if k != "sha256"}
        if canonical_sha256(body) != claimed:
            raise OperatorActionError("operator_action_receipt_sha_mismatch", str(claimed))

    expected_request_sha = canonical_sha256(request)
    if receipt.get("request_sha256") not in (None, expected_request_sha):
        raise OperatorActionError("operator_action_receipt_request_mismatch", str(receipt.get("request_sha256")))
    for field in ("run_id", "node_id", "goal_hash"):
        if receipt.get(field) != request.get(field):
            raise OperatorActionError("operator_action_receipt_identity_mismatch", field)

    outcome = receipt.get("outcome")
    if outcome != "applied" and outcome not in DEFERRED_OUTCOMES:
        raise OperatorActionError("operator_action_receipt_outcome_unknown", str(outcome))

    transition = receipt.get("journal_transition")
    if not isinstance(transition, dict):
        raise OperatorActionError("operator_action_receipt_transition_missing")
    if transition.get("observed_seq") != request["observed_journal_seq"]:
        raise OperatorActionError("operator_action_receipt_transition_stale", str(transition.get("observed_seq")))
    return receipt


def tau_submitter(request: dict[str, Any], *, run: Any = None) -> dict[str, Any]:
    """Default submitter: hand the request to Tau's own applier.

    Tau exposes no out-of-process operator-action endpoint, so submission binds
    to the in-process applier. Without an importable Tau and a live run handle
    this refuses; it never simulates the decision Tau is supposed to make.
    """
    try:
        from tau_coding.dag_runtime.agent_projection import apply_operator_action
    except ImportError as exc:
        raise OperatorActionError("tau_unavailable", str(exc)) from exc
    if run is None:
        raise OperatorActionError("tau_run_handle_required", request["node_id"])
    try:
        return apply_operator_action(run=run, request=request)
    except Exception as exc:  # noqa: BLE001 - surface Tau's own refusal code verbatim
        raise OperatorActionError(getattr(exc, "code", "tau_rejected_action"), str(exc)) from exc


def submit_action(
    *,
    state: dict[str, Any],
    node_id: str,
    action: str,
    actor: str,
    instruction: str | None = None,
    submitter: Callable[..., dict[str, Any]] = tau_submitter,
    run: Any = None,
) -> dict[str, Any]:
    """Compose, submit, and validate one bounded operator action."""
    request = build_action_request(
        state=state, node_id=node_id, action=action, actor=actor, instruction=instruction
    )
    receipt = validate_action_receipt(submitter(request, run=run), request)
    return {
        "schema": "monitor_herdr.tau_operator_action.v1",
        "ok": True,
        "run_id": request["run_id"],
        "node_id": node_id,
        "action": action,
        "actor": actor,
        "outcome": receipt["outcome"],
        "deferred": receipt["outcome"] in DEFERRED_OUTCOMES,
        "journal_changed": bool(receipt["journal_transition"].get("journal_changed")),
        "request_sha256": canonical_sha256(request),
        "receipt_sha256": receipt.get("sha256"),
        "receipt": receipt,
        "proof_boundary": {
            "tau_owns_the_decision": True,
            "no_terminal_fallback_on_failure": True,
        },
    }


def load_state(run_id: str, state_dir: Path) -> dict[str, Any]:
    state_path = state_dir / f"{run_id}.json"
    if not state_path.is_file():
        raise OperatorActionError("unknown_run", run_id)
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise OperatorActionError("state_unreadable", str(exc)) from exc


def available_actions(state: dict[str, Any]) -> dict[str, Any]:
    """Report which Tau actions each attached node currently permits."""
    return {
        "schema": "monitor_herdr.tau_actions.v1",
        "run_id": state.get("run_id"),
        "nodes": [
            {
                "node_id": card.get("node_id"),
                "label": card.get("label"),
                "lifecycle": card.get("lifecycle"),
                "terminal": card.get("terminal"),
                "journal_seq": card.get("journal_seq"),
                "permitted_operator_actions": list(card.get("permitted_operator_actions", [])),
            }
            for card in state.get("cards", [])
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Tau operator-action client")
    sub = parser.add_subparsers(dest="cmd", required=True)
    default_state_dir = Path.home() / ".local/state/monitor-herdr/tau-runs"

    p_list = sub.add_parser("tau-actions", help="List permitted Tau actions per node.")
    p_list.add_argument("--run-id", required=True)
    p_list.add_argument("--state-dir", type=Path, default=default_state_dir)

    p_act = sub.add_parser("tau-action", help="Submit one operator action through Tau.")
    p_act.add_argument("--run-id", required=True)
    p_act.add_argument("--node-id", required=True)
    p_act.add_argument("--action", required=True, choices=list(OPERATOR_ACTIONS))
    p_act.add_argument("--actor", default="human_operator", choices=list(AUTHORIZED_ACTORS))
    p_act.add_argument("--instruction", default=None)
    p_act.add_argument("--state-dir", type=Path, default=default_state_dir)

    args = parser.parse_args()
    try:
        state = load_state(args.run_id, args.state_dir)
        if args.cmd == "tau-actions":
            out = available_actions(state)
        else:
            out = submit_action(
                state=state,
                node_id=args.node_id,
                action=args.action,
                actor=args.actor,
                instruction=args.instruction,
            )
    except OperatorActionError as exc:
        print(json.dumps({
            "schema": "monitor_herdr.tau_operator_action.v1",
            "ok": False,
            "error": exc.code,
            "detail": exc.detail,
            "terminal_fallback_attempted": False,
        }, indent=2, sort_keys=True))
        return 2
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
