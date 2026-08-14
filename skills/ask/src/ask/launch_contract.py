"""Per-node launch contract, verified before Tau executes (#1403).

Purpose
    A node's ceiling has to be decided and hashed BEFORE anything runs, and the
    runtime must be checkable against it afterwards. Otherwise a node acquires
    whatever the ambient host happens to expose: a reviewer inherits mutation
    tools because the shell has them, a worker writes outside its declared
    paths, or a resume quietly swaps in a different model.

    ``ask.node_launch_contract.v1`` is the logical ceiling; a runtime receipt
    records what was actually resolved. Tau may TIGHTEN a ceiling and may never
    widen one -- that asymmetry is the whole contract, because tightening is a
    safety decision and widening is an escalation.

    The digest deliberately covers only logical intent. Pane ids, tab ids, run
    directories, receipt paths and timestamps are excluded: a contract whose
    hash changed because a browser tab was reassigned would be unusable for
    comparison, which is what makes widening detectable at all.

Inputs
    A node specification dict, and optionally a runtime resolution to verify.

Outputs
    ``compile_contract(spec)`` returns the contract with its canonical digest.
    ``verify_runtime(contract, resolved)`` returns an accept/reject receipt.

Failure modes
    Contradictory intent, unknown effect classes, or an unsupported
    target/adapter pairing raise ``ContractError`` at compile time -- before
    any execution, which is the only point where refusing is free.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA = "ask.node_launch_contract.v1"
RUNTIME_SCHEMA = "ask.node_launch_runtime.v1"

ADAPTERS = ("tau_native_agent", "tau_opaque_compat")

TARGET_KINDS = ("model", "browser_seat", "session", "local", "join", "human")

# Adapter/target pairings that are real. A browser seat is never Tau-native --
# it runs behind a compat transport -- and pairing them would let a browser
# node claim native guarantees it cannot provide.
SUPPORTED_PAIRS = {
    ("model", "tau_native_agent"),
    ("local", "tau_native_agent"),
    ("join", "tau_native_agent"),
    ("human", "tau_native_agent"),
    ("browser_seat", "tau_opaque_compat"),
    ("session", "tau_opaque_compat"),
}

KNOWN_EFFECTS = ("filesystem_write", "network", "provider_call", "session_write", "git_write")

# Ceilings, in the direction they may move. A runtime may shrink a set or
# lower a number; the reverse is an escalation.
SET_CEILINGS = ("tools", "skills", "effects", "allowed_paths")
NUMERIC_CEILINGS = ("timeout_seconds", "max_attempts")

# Excluded from the logical digest: identities that change without the node's
# intent changing.
EPHEMERAL_FIELDS = (
    "tab_id",
    "pane_id",
    "run_dir",
    "receipt_path",
    "artifact_dir",
    "created_at",
    "observed_at",
    "lease",
    "endpoint",
)


class ContractError(ValueError):
    """A launch contract that must not reach execution."""


def _canonical(value: Any) -> Any:
    """Order-insensitive canonical form for hashing.

    Sets and unordered lists are sorted so that reordering a tool list does not
    read as a different ceiling, while changing its membership does.
    """
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items()) if k not in EPHEMERAL_FIELDS}
    if isinstance(value, (list, tuple, set)):
        canon = [_canonical(v) for v in value]
        try:
            return sorted(canon, key=lambda item: json.dumps(item, sort_keys=True))
        except TypeError:  # pragma: no cover - defensive
            return canon
    return value


def contract_digest(contract: dict[str, Any]) -> str:
    """sha256 over logical intent only."""
    payload = {k: v for k, v in contract.items() if k not in {"digest", "runtime"}}
    canonical = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compile_contract(spec: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate a node spec into a hashed launch contract.

    Compilation is side-effect-free by construction: it reads a dict and
    returns a dict. Refusing here costs nothing; refusing after a provider call
    costs the call.
    """
    node_id = str(spec.get("node_id") or "").strip()
    if not node_id:
        raise ContractError("node_id is required")

    target_kind = str(spec.get("target_kind") or "").strip()
    if target_kind not in TARGET_KINDS:
        raise ContractError(f"unknown target_kind {target_kind!r}; known: {list(TARGET_KINDS)}")

    adapter = str(spec.get("adapter") or "").strip()
    if adapter not in ADAPTERS:
        raise ContractError(f"unknown adapter {adapter!r}; known: {list(ADAPTERS)}")

    if (target_kind, adapter) not in SUPPORTED_PAIRS:
        raise ContractError(
            f"unsupported target/adapter pair {target_kind!r}/{adapter!r}: "
            "a browser seat or session runs behind a compat transport and cannot claim native guarantees"
        )

    effects = sorted({str(e) for e in spec.get("effects") or []})
    unknown = [e for e in effects if e not in KNOWN_EFFECTS]
    if unknown:
        raise ContractError(f"unknown effect class(es) {unknown}; known: {list(KNOWN_EFFECTS)}")

    write_intent = bool(spec.get("write_intent"))
    allowed_paths = sorted({str(p) for p in spec.get("allowed_paths") or []})
    if write_intent and not allowed_paths:
        raise ContractError("write_intent requires at least one allowed path")
    if not write_intent and "filesystem_write" in effects:
        raise ContractError(
            "contradictory intent: filesystem_write effect declared with write_intent false"
        )
    if write_intent and "filesystem_write" not in effects:
        raise ContractError(
            "contradictory intent: write_intent true without the filesystem_write effect"
        )

    contract: dict[str, Any] = {
        "schema": SCHEMA,
        "node_id": node_id,
        "role": str(spec.get("role") or ""),
        "goal_hash": str(spec.get("goal_hash") or ""),
        "target_kind": target_kind,
        "target_selector": str(spec.get("target_selector") or ""),
        "adapter": adapter,
        "accepted_context_from": sorted({str(c) for c in spec.get("accepted_context_from") or []}),
        "context_policy": str(spec.get("context_policy") or "fresh"),
        "model_requirements": dict(spec.get("model_requirements") or {}),
        "substitution_allowed": bool(spec.get("substitution_allowed", False)),
        "tools": sorted({str(t) for t in spec.get("tools") or []}),
        "skills": sorted({str(s) for s in spec.get("skills") or []}),
        "effects": effects,
        "allowed_paths": allowed_paths,
        "write_intent": write_intent,
        "output_mode": str(spec.get("output_mode") or "text"),
        "output_schema": str(spec.get("output_schema") or ""),
        "required_evidence": sorted({str(e) for e in spec.get("required_evidence") or []}),
        "human_approvals": sorted({str(a) for a in spec.get("human_approvals") or []}),
        "timeout_seconds": int(spec.get("timeout_seconds") or 0),
        "max_attempts": int(spec.get("max_attempts") or 1),
    }
    contract["digest"] = contract_digest(contract)
    return contract


def _widened_sets(contract: dict[str, Any], resolved: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for field in SET_CEILINGS:
        ceiling = set(contract.get(field) or [])
        actual = {str(v) for v in resolved.get(field) or []}
        extra = sorted(actual - ceiling)
        if extra:
            problems.append(f"{field} widened by {extra}")
    return problems


def _widened_numbers(contract: dict[str, Any], resolved: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for field in NUMERIC_CEILINGS:
        ceiling = contract.get(field)
        actual = resolved.get(field)
        if isinstance(ceiling, int) and isinstance(actual, int) and ceiling and actual > ceiling:
            problems.append(f"{field} widened from {ceiling} to {actual}")
    return problems


def verify_runtime(contract: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    """Check a runtime resolution against its logical ceiling.

    Tightening is accepted and reported so an operator can see what Tau
    narrowed; widening is rejected. Evidence and goal are treated as ceilings
    too: weakening required evidence is how a node would launder an
    unadmitted answer into a pass.
    """
    problems = _widened_sets(contract, resolved) + _widened_numbers(contract, resolved)

    # Only compare what the runtime actually declares. A field absent from a
    # partial resolution is not a claim, and treating it as one would flag every
    # narrow receipt as weakening its own contract.
    if "required_evidence" in resolved:
        ceiling_evidence = set(contract.get("required_evidence") or [])
        actual_evidence = {str(e) for e in resolved.get("required_evidence") or []}
        if ceiling_evidence and not ceiling_evidence <= actual_evidence:
            problems.append(
                f"required_evidence weakened; missing {sorted(ceiling_evidence - actual_evidence)}"
            )

    if resolved.get("goal_hash") and contract.get("goal_hash"):
        if resolved["goal_hash"] != contract["goal_hash"]:
            problems.append("goal_hash changed between contract and runtime")

    if not contract.get("substitution_allowed"):
        wanted = (contract.get("model_requirements") or {}).get("model")
        got = resolved.get("model")
        if wanted and got and wanted != got:
            problems.append(f"model substituted {wanted!r} -> {got!r} without substitution_allowed")

    tightened: list[str] = []
    for field in SET_CEILINGS:
        ceiling = set(contract.get(field) or [])
        actual = {str(v) for v in resolved.get(field) or []}
        removed = sorted(ceiling - actual)
        if removed:
            tightened.append(f"{field} tightened, removed {removed}")

    return {
        "schema": RUNTIME_SCHEMA,
        "node_id": contract.get("node_id"),
        "contract_digest": contract.get("digest"),
        "accepted": not problems,
        "problems": problems,
        "tightened": tightened,
        # Ephemeral identities live here and nowhere near the logical digest.
        "runtime_binding": {
            key: resolved[key] for key in EPHEMERAL_FIELDS if key in resolved
        },
    }


def preflight_blocks(contract: dict[str, Any], capability: dict[str, Any] | None) -> list[str]:
    """Reasons this node must not be submitted, from live readiness (#1405).

    Required proof 7: a browser target lacking the attachment capability its
    contract needs, or a session whose binding went stale, blocks BEFORE task
    submission rather than failing after the prompt is already in.
    """
    if not capability:
        return []
    entries = {c["capability_id"]: c for c in capability.get("capabilities", [])}
    blocks: list[str] = []

    if contract["target_kind"] == "browser_seat":
        entry = entries.get(f"browser.{contract['target_selector']}")
        if entry is None:
            return [f"no readiness known for browser seat {contract['target_selector']!r}"]
        if entry["state"] in {"BLOCKED", "UNAVAILABLE"}:
            blocks.append(f"seat {entry['capability_id']} is {entry['state']} ({entry['reason_code']})")
        if entry.get("stale"):
            blocks.append(f"seat readiness is stale ({entry.get('stale_reason')})")
        needs_attachment = contract["output_mode"] == "attachment" or "attachment" in contract.get("tools", [])
        if needs_attachment and entry["operations"].get("attachment") is not True:
            blocks.append(
                f"seat {entry['capability_id']} cannot take attachments "
                f"(attachment={entry['operations'].get('attachment')})"
            )

    if contract["target_kind"] == "session":
        entry = entries.get("session.herdr")
        if entry is None or entry["state"] in {"BLOCKED", "UNAVAILABLE"}:
            blocks.append("no addressable standing session")
        elif entry.get("stale"):
            blocks.append(f"session readiness is stale ({entry.get('stale_reason')})")

    return blocks
